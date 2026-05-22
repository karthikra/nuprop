from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConnectorAuthError, TokenVaultError
from app.infrastructure.db.models.base import _uuid_default
from app.infrastructure.db.repositories.agency_repo import AgencyRepository
from app.infrastructure.db.repositories.client_repo import ClientRepository
from app.infrastructure.db.repositories.email_index_repo import EmailIndexRepository
from app.infrastructure.external.gcal_client import GCalClient
from app.infrastructure.external.gdrive_client import GDriveClient
from app.infrastructure.external.gmail_client import GmailClient
from app.infrastructure.external.slack_client import SlackClient
from app.infrastructure.security.token_vault import TokenVault
from app.services.ai.email_classifier import EmailClassifier
from app.domain.schemas.discovery_schemas import DiscoveryResponse
from app.services.connectors.discovery_aggregator import FREEMAIL_DOMAINS, aggregate
from app.viewmodels.shared.viewmodel import ViewModelBase

logger = logging.getLogger(__name__)


class ConnectorViewModel(ViewModelBase):
    def __init__(
        self,
        request: Request,
        db: AsyncSession,
        *,
        gmail_client: GmailClient | None = None,
        slack_client: SlackClient | None = None,
        token_vault: TokenVault | None = None,
    ):
        super().__init__(request, db)
        self._gmail = gmail_client or GmailClient()
        self._slack = slack_client or SlackClient()
        if token_vault is not None:
            self._vault = token_vault
        else:
            from app.core.deps import get_token_vault
            self._vault = get_token_vault()
        self._agency_repo: AgencyRepository | None = None
        self._client_repo: ClientRepository | None = None
        self._email_repo: EmailIndexRepository | None = None

    @property
    def agency_repo(self) -> AgencyRepository:
        if not self._agency_repo:
            self._agency_repo = AgencyRepository(self._db)
        return self._agency_repo

    @property
    def client_repo(self) -> ClientRepository:
        if not self._client_repo:
            self._client_repo = ClientRepository(self._db)
        return self._client_repo

    @property
    def email_repo(self) -> EmailIndexRepository:
        if not self._email_repo:
            self._email_repo = EmailIndexRepository(self._db)
        return self._email_repo

    # ── Token encryption ─────────────────────────────────────

    def _encrypt(self, text: str) -> str:
        """Encrypt via the injected TokenVault. Raises TokenVaultError if the
        vault is not configured; the route handler converts that to 5xx."""
        return self._vault.encrypt(text)

    def _decrypt(self, text: str) -> str:
        """Decrypt via the injected TokenVault. Raises TokenVaultError on
        InvalidToken (rotated key / corruption); caller maps that to
        ConnectorAuthError("needs_reauth")."""
        return self._vault.decrypt(text)

    # ── OAuth flow ───────────────────────────────────────────

    async def get_auth_url(self, agency_id: UUID) -> str:
        from app.core.config import get_settings
        from app.infrastructure.security.oauth_state import issue_state

        if not self._gmail.is_configured:
            self.error = "Google OAuth not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."
            self.status_code = 400
            return ""
        state = issue_state(
            agency_id=agency_id,
            provider="gmail",
            secret=get_settings().JWT_SECRET_KEY,
        )
        return self._gmail.get_auth_url(state)

    async def handle_callback(self, agency_id_from_state: UUID, code: str) -> dict:
        """Caller (route handler) must have already verified the OAuth state
        token and resolved the agency_id from its payload — do NOT trust the
        URL/session for agency_id during the callback."""
        try:
            tokens = await self._gmail.exchange_code(code)
        except Exception as exc:
            logger.exception(
                "gmail.exchange_code failed",
                extra={"event": "connector.gmail.exchange_failed"},
            )
            self.error = "Google rejected the authorization code"
            self.status_code = 400
            return {}

        access_token = tokens.get("access_token") or ""
        refresh_token = tokens.get("refresh_token") or ""
        if not access_token or not refresh_token:
            logger.warning(
                "gmail.exchange_code returned without refresh_token",
                extra={"event": "connector.gmail.missing_refresh_token"},
            )
            self.error = (
                "Google did not return a refresh token. "
                "Revoke the existing app authorization in your Google account and try again."
            )
            self.status_code = 400
            return {}

        try:
            email = await self._gmail.get_user_email(access_token)
        except Exception as exc:
            logger.exception(
                "gmail.get_user_email failed",
                extra={"event": "connector.gmail.profile_failed"},
            )
            self.error = "Failed to read Google profile"
            self.status_code = 502
            return {}

        agency = await self.agency_repo.get_by_id(agency_id_from_state)
        if not agency:
            self.error = "Agency not found"
            self.status_code = 404
            return {}

        try:
            encrypted_refresh = self._encrypt(refresh_token)
        except TokenVaultError:
            self.error = "Server encryption key is not configured; cannot store credentials"
            self.status_code = 500
            return {}

        settings = dict(agency.settings or {})
        settings["gmail"] = {
            "connected": True,
            "email": email,
            "refresh_token": encrypted_refresh,
            "last_sync": None,
            "email_count": 0,
        }
        await self.agency_repo.update(agency_id_from_state, settings=settings)

        return {"connected": True, "email": email, "last_sync": None, "email_count": 0}

    async def get_status(self, agency_id: UUID) -> dict:
        agency = await self.agency_repo.get_by_id(agency_id)
        if not agency:
            return {"connected": False, "configured": self._gmail.is_configured}

        gmail = (agency.settings or {}).get("gmail", {})
        email_count = await self.email_repo.count_by_agency(agency_id)

        return {
            "connected": gmail.get("connected", False),
            "configured": self._gmail.is_configured,
            "email": gmail.get("email"),
            "last_sync": gmail.get("last_sync"),
            "email_count": email_count,
        }

    async def disconnect(self, agency_id: UUID) -> None:
        agency = await self.agency_repo.get_by_id(agency_id)
        if not agency:
            return

        gmail = (agency.settings or {}).get("gmail", {})
        if gmail.get("refresh_token"):
            try:
                token = self._decrypt(gmail["refresh_token"])
                await self._gmail.revoke_token(token)
            except TokenVaultError:
                logger.warning(
                    "skipping Gmail token revoke — stored token could not be decrypted",
                    extra={"event": "connector.gmail.disconnect_decrypt_failed"},
                )
            except Exception:
                logger.exception(
                    "Gmail token revoke failed; clearing local credentials anyway",
                    extra={"event": "connector.gmail.revoke_failed"},
                )

        settings = dict(agency.settings or {})
        settings.pop("gmail", None)
        await self.agency_repo.update(agency_id, settings=settings)
        await self.email_repo.delete_by_agency(agency_id)

    # ── Sync ─────────────────────────────────────────────────

    async def sync_emails(self, agency_id: UUID) -> dict:
        start = time.time()

        agency = await self.agency_repo.get_by_id(agency_id)
        if not agency:
            self.error = "Agency not found"
            self.status_code = 404
            return {}

        gmail = (agency.settings or {}).get("gmail", {})
        if not gmail.get("connected") or not gmail.get("refresh_token"):
            self.error = "Gmail not connected"
            self.status_code = 400
            return {}

        try:
            refresh_token = self._decrypt(gmail["refresh_token"])
        except TokenVaultError:
            self.error = "Stored Gmail credentials could not be decrypted; please reconnect"
            self.status_code = 400
            return {}

        try:
            access_token = await self._gmail.refresh_access_token(refresh_token)
        except Exception:
            logger.exception(
                "gmail.refresh_access_token failed",
                extra={"event": "connector.gmail.refresh_failed"},
            )
            self.error = "Failed to refresh Google access token; please reconnect"
            self.status_code = 400
            return {}

        clients = await self.client_repo.search(agency_id, limit=500)
        domain_map = self._extract_domains(clients)
        if not domain_map:
            return {"new_emails": 0, "total_emails": 0, "domains_synced": [], "duration_seconds": 0}

        per_domain_watermark: dict[str, str] = dict(
            gmail.get("last_sync_per_domain") or {}
        )
        classifier = EmailClassifier()
        total_new = 0
        synced_domains: list[str] = []

        # domain -> client.id, for enqueueing context enrichment after the sync.
        domain_to_client_id: dict[str, str] = {}
        for _c in clients:
            for _contact in (_c.contacts or []):
                _email = (_contact or {}).get("email") if isinstance(_contact, dict) else None
                if _email and "@" in _email:
                    domain_to_client_id[_email.split("@")[-1].lower()] = str(_c.id)
        clients_with_new_email: set[str] = set()

        for domain, client_name in domain_map.items():
            # Per-domain `since` from the watermark (falls back to None)
            since: datetime | None = None
            iso = per_domain_watermark.get(domain)
            if iso:
                try:
                    since = datetime.fromisoformat(iso)
                except ValueError:
                    logger.warning(
                        "per-domain last_sync ISO parse failed; running full sync for domain",
                        extra={
                            "event": "connector.gmail.bad_per_domain_iso",
                            "domain": domain,
                            "value": iso,
                        },
                    )

            try:
                messages = await self._gmail.fetch_messages_for_domain(
                    access_token, domain, since, limit=100,
                )
                if not messages:
                    # No messages between `since` and now — confirm we're up to date.
                    # Advance the watermark to "now" so the next run doesn't re-fetch
                    # an empty window from the same `since`.
                    per_domain_watermark[domain] = datetime.now(timezone.utc).isoformat()
                    await self._persist_gmail_watermark(agency_id, per_domain_watermark)
                    synced_domains.append(domain)
                    continue

                msg_ids = [m["id"] for m in messages]
                existing = await self.email_repo.get_existing_message_ids(agency_id, msg_ids)
                new_messages = [m for m in messages if m["id"] not in existing]

                if not new_messages:
                    synced_domains.append(domain)
                    # Even with no new messages, advance the per-domain watermark
                    per_domain_watermark[domain] = datetime.now(timezone.utc).isoformat()
                    await self._persist_gmail_watermark(agency_id, per_domain_watermark)
                    continue

                classifications = await classifier.classify_batch(new_messages, concurrency=5)

                now = datetime.now(timezone.utc)
                rows = []
                from app.infrastructure.db.models.email_index import EmailIndex
                for msg, cls in zip(new_messages, classifications):
                    rows.append(EmailIndex(
                        id=_uuid_default(),
                        agency_id=str(agency_id),
                        gmail_message_id=msg["id"],
                        gmail_thread_id=msg.get("thread_id", ""),
                        client_domain=domain,
                        client_name=client_name,
                        message_type=cls["message_type"],
                        sentiment=cls["sentiment"],
                        priority=cls["priority"],
                        summary=cls["summary"],
                        entities=cls["entities"],
                        from_address=msg.get("from", ""),
                        to_addresses=msg.get("to", "").split(",") if msg.get("to") else [],
                        subject=msg.get("subject", ""),
                        date=msg["date"] if isinstance(msg["date"], datetime) else now,
                        has_attachments=msg.get("has_attachments", False),
                        synced_at=now,
                    ))

                # Persist this domain's emails in chunks, committing as we go
                await self.email_repo.upsert_many(rows, chunk_size=50)

                # Track which clients received new email for post-sync enrichment.
                _cid = domain_to_client_id.get(domain)
                if _cid:
                    clients_with_new_email.add(_cid)

                # Advance per-domain watermark to the newest persisted email's date
                newest_iso = max(
                    (m["date"] for m in new_messages if isinstance(m.get("date"), datetime)),
                    default=now,
                ).isoformat()
                per_domain_watermark[domain] = newest_iso
                await self._persist_gmail_watermark(agency_id, per_domain_watermark)

                total_new += len(new_messages)
                synced_domains.append(domain)

            except ConnectorAuthError:
                raise
            except Exception:
                logger.exception(
                    "Gmail sync failed for one domain; skipping and continuing",
                    extra={"event": "connector.gmail.domain_sync_failed", "domain": domain},
                )
                continue

        # Final refresh of the coarse last_sync + email_count for the UI
        await self._persist_gmail_watermark(agency_id, per_domain_watermark)
        email_count = await self.email_repo.count_by_agency(agency_id)
        agency = await self.agency_repo.get_by_id(agency_id)
        settings = dict(agency.settings or {})
        gmail_settings = dict(settings.get("gmail", {}))
        gmail_settings["email_count"] = email_count
        settings["gmail"] = gmail_settings
        await self.agency_repo.update(agency_id, settings=settings)
        await self._db.commit()

        if clients_with_new_email:
            try:
                pool = self._request.app.state.arq_pool
                await pool.enqueue_job(
                    "enrich_context_from_emails",
                    str(agency_id),
                    sorted(clients_with_new_email),
                    _job_id=f"{agency_id}:enrich_context:{int(time.time())}",
                )
            except Exception:  # noqa: BLE001 — enqueue failure must not fail the sync
                logger.exception(
                    "failed to enqueue enrich_context_from_emails",
                    extra={"event": "connector.enrich.enqueue_failed"},
                )

        duration = round(time.time() - start, 1)
        return {
            "new_emails": total_new,
            "total_emails": email_count,
            "domains_synced": synced_domains,
            "duration_seconds": duration,
        }

    async def discover_clients(
        self, agency_id: UUID, lookback_days: int,
    ) -> DiscoveryResponse:
        start = time.time()

        agency = await self.agency_repo.get_by_id(agency_id)
        if not agency:
            self.error = "Agency not found"
            self.status_code = 404
            return DiscoveryResponse()

        gmail = (agency.settings or {}).get("gmail", {})
        if not gmail.get("connected") or not gmail.get("refresh_token"):
            self.error = "Gmail not connected"
            self.status_code = 400
            return DiscoveryResponse()

        try:
            refresh_token = self._decrypt(gmail["refresh_token"])
        except TokenVaultError:
            self.error = "Stored Gmail credentials could not be decrypted; please reconnect"
            self.status_code = 400
            return DiscoveryResponse()

        try:
            access_token = await self._gmail.refresh_access_token(refresh_token)
        except Exception:
            logger.exception(
                "gmail.refresh_access_token failed during discovery",
                extra={"event": "connector.discovery.refresh_failed"},
            )
            self.error = "Failed to refresh Google access token; please reconnect"
            self.status_code = 400
            return DiscoveryResponse()

        # Per-window limits chosen to bound Gmail API calls. See spec.
        limit_for_window = {30: 500, 90: 1500, 365: 3000}[lookback_days]

        try:
            messages = await self._gmail.fetch_recent_messages(
                access_token, lookback_days=lookback_days, limit=limit_for_window,
            )
        except Exception:
            logger.exception(
                "gmail.fetch_recent_messages failed",
                extra={"event": "connector.discovery.fetch_failed"},
            )
            self.error = "Couldn't scan your inbox right now. Try again in a minute."
            self.status_code = 500
            return DiscoveryResponse()

        # Build the already-linked domain set from existing clients.
        clients = await self.client_repo.search(agency_id, limit=500)
        linked_domains: set[str] = set()
        for client in clients:
            for contact in (client.contacts or []):
                if isinstance(contact, dict) and contact.get("email"):
                    linked_domains.add(contact["email"].split("@")[-1].lower())

        # Own domain inferred from the connected Gmail account.
        own_email = (gmail.get("email") or "").strip()
        own_domain = own_email.split("@")[-1].lower() if "@" in own_email else None

        candidates = aggregate(
            messages,
            own_domain=own_domain,
            excluded_domains=linked_domains,
        )

        return DiscoveryResponse(
            candidates=candidates,
            excluded_existing=len(linked_domains),
            scanned_messages=len(messages),
            duration_seconds=round(time.time() - start, 2),
        )

    async def _persist_gmail_watermark(
        self, agency_id: UUID, per_domain: dict[str, str],
    ) -> None:
        """Write the per-domain watermark map AND the coarse last_sync to the
        agency's settings JSON, committing immediately so a later domain
        failure cannot revert it."""
        agency = await self.agency_repo.get_by_id(agency_id)
        if not agency:
            return
        settings = dict(agency.settings or {})
        gmail = dict(settings.get("gmail", {}))
        gmail["last_sync_per_domain"] = per_domain
        if per_domain:
            gmail["last_sync"] = max(per_domain.values())
        else:
            gmail["last_sync"] = datetime.now(timezone.utc).isoformat()
        settings["gmail"] = gmail
        await self.agency_repo.update(agency_id, settings=settings)
        await self._db.commit()

    def _extract_domains(self, clients: list) -> dict[str, str]:
        """Extract email domains from client contacts. Returns {domain: client_name}."""
        domain_map: dict[str, str] = {}
        for client in clients:
            contacts = client.contacts or []
            for contact in contacts:
                if isinstance(contact, dict) and contact.get("email"):
                    email = contact["email"]
                    domain = email.split("@")[-1].lower()
                    if domain not in FREEMAIL_DOMAINS:
                        domain_map[domain] = client.name
        return domain_map

    # ── Google Drive ─────────────────────────────────────────

    async def sync_drive(self, agency_id: UUID) -> dict:
        """Search Drive for documents about each client. Enriches context profiles."""
        agency = await self.agency_repo.get_by_id(agency_id)
        if not agency:
            return {"error": "Agency not found"}

        gmail = (agency.settings or {}).get("gmail", {})
        if not gmail.get("connected") or not gmail.get("refresh_token"):
            return {"error": "Google not connected (connect Gmail first — same OAuth)"}

        refresh_token = self._decrypt(gmail["refresh_token"])
        # Reuse Gmail's refresh token — Drive uses same Google account
        from app.infrastructure.external.gmail_client import GmailClient
        gmail_client = GmailClient()
        access_token = await gmail_client.refresh_access_token(refresh_token)

        drive = GDriveClient()
        clients = await self.client_repo.search(agency_id, limit=500)
        docs_found = 0

        from app.services.context_service import ContextService
        ctx_svc = ContextService()

        for client in clients:
            try:
                docs = await drive.search_client_documents(access_token, client.name, max_results=5)
                if not docs:
                    continue

                doc_summaries = "\n".join(
                    f"- {d['name']} ({d['type']}, modified {d['modified'][:10]})"
                    for d in docs
                )

                # Extract context from document names/descriptions
                existing = client.context_profile or {}
                extraction = await ctx_svc.extract_context(
                    f"Documents found in Google Drive about {client.name}:\n{doc_summaries}\n\n"
                    f"These documents suggest past work or ongoing relationship."
                )
                merged = await ctx_svc.merge_context(existing, extraction)

                # Add drive source info
                merged.setdefault("_sources", {})["drive"] = {
                    "document_count": len(docs),
                    "last_sync": datetime.now(timezone.utc).isoformat(),
                }

                await self.client_repo.update(client.id, context_profile=merged)
                docs_found += len(docs)

            except Exception:
                logger.exception(
                    "Drive sync failed for one client; skipping",
                    extra={"event": "connector.drive.client_sync_failed", "client_id": str(client.id)},
                )
                continue

        return {"clients_synced": len(clients), "documents_found": docs_found}

    # ── Google Calendar ──────────────────────────────────────

    async def sync_calendar(self, agency_id: UUID) -> dict:
        """Analyze meeting patterns with each client. Enriches context profiles."""
        agency = await self.agency_repo.get_by_id(agency_id)
        if not agency:
            return {"error": "Agency not found"}

        gmail = (agency.settings or {}).get("gmail", {})
        if not gmail.get("connected") or not gmail.get("refresh_token"):
            return {"error": "Google not connected"}

        refresh_token = self._decrypt(gmail["refresh_token"])
        from app.infrastructure.external.gmail_client import GmailClient
        gmail_client = GmailClient()
        access_token = await gmail_client.refresh_access_token(refresh_token)

        cal = GCalClient()
        clients = await self.client_repo.search(agency_id, limit=500)
        meetings_found = 0

        for client in clients:
            try:
                stats = await cal.get_client_meeting_stats(access_token, client.name)
                if stats["meeting_count"] == 0:
                    continue

                existing = client.context_profile or {}
                # Update relationship info from calendar
                rel = dict(existing.get("relationship", {}))
                rel["meeting_frequency"] = stats["frequency"]
                rel["meeting_count"] = stats["meeting_count"]
                rel["last_meeting"] = stats["last_meeting"]
                if stats["attendees"]:
                    rel["meeting_attendees"] = stats["attendees"]
                existing["relationship"] = rel

                # Add calendar source info
                existing.setdefault("_sources", {})["calendar"] = {
                    "meeting_count": stats["meeting_count"],
                    "frequency": stats["frequency"],
                    "last_sync": datetime.now(timezone.utc).isoformat(),
                }

                await self.client_repo.update(client.id, context_profile=existing)
                meetings_found += stats["meeting_count"]

            except Exception:
                logger.exception(
                    "Calendar sync failed for one client; skipping",
                    extra={"event": "connector.calendar.client_sync_failed", "client_id": str(client.id)},
                )
                continue

        return {"clients_synced": len(clients), "meetings_found": meetings_found}

    # ── Slack ────────────────────────────────────────────────

    async def get_slack_auth_url(self, agency_id: UUID) -> str:
        from app.core.config import get_settings
        from app.infrastructure.security.oauth_state import issue_state

        if not self._slack.is_configured:
            self.error = "Slack OAuth not configured"
            self.status_code = 400
            return ""
        state = issue_state(
            agency_id=agency_id,
            provider="slack",
            secret=get_settings().JWT_SECRET_KEY,
        )
        return self._slack.get_auth_url(state)

    async def handle_slack_callback(self, agency_id_from_state: UUID, code: str) -> dict:
        """Caller (route handler) must have already verified the OAuth state
        token and resolved the agency_id from its payload."""
        try:
            data = await self._slack.exchange_code(code)
        except Exception:
            logger.exception(
                "slack.exchange_code failed",
                extra={"event": "connector.slack.exchange_failed"},
            )
            return {}

        access_token = data.get("access_token", "")
        team = data.get("team", {})
        workspace_name = team.get("name", "")
        if not access_token:
            logger.warning(
                "slack.exchange_code returned without access_token",
                extra={"event": "connector.slack.missing_access_token"},
            )
            return {}

        agency = await self.agency_repo.get_by_id(agency_id_from_state)
        if not agency:
            return {}

        try:
            encrypted_access = self._encrypt(access_token)
        except TokenVaultError:
            logger.exception(
                "token vault not configured during Slack callback",
                extra={"event": "connector.slack.vault_not_configured"},
            )
            return {}

        settings = dict(agency.settings or {})
        settings["slack"] = {
            "connected": True,
            "workspace": workspace_name,
            "access_token": encrypted_access,
            "last_sync": None,
        }
        await self.agency_repo.update(agency_id_from_state, settings=settings)

        return {"connected": True, "workspace": workspace_name}

    async def get_slack_status(self, agency_id: UUID) -> dict:
        agency = await self.agency_repo.get_by_id(agency_id)
        if not agency:
            return {"connected": False}
        slack_settings = (agency.settings or {}).get("slack", {})
        return {
            "connected": slack_settings.get("connected", False),
            "configured": self._slack.is_configured,
            "workspace": slack_settings.get("workspace"),
            "last_sync": slack_settings.get("last_sync"),
        }

    async def disconnect_slack(self, agency_id: UUID) -> None:
        agency = await self.agency_repo.get_by_id(agency_id)
        if not agency:
            return
        settings = dict(agency.settings or {})
        settings.pop("slack", None)
        await self.agency_repo.update(agency_id, settings=settings)

    async def sync_slack(self, agency_id: UUID) -> dict:
        """Search Slack for mentions of each client. Enriches context profiles."""
        agency = await self.agency_repo.get_by_id(agency_id)
        if not agency:
            return {"error": "Agency not found"}

        slack_settings = (agency.settings or {}).get("slack", {})
        if not slack_settings.get("connected") or not slack_settings.get("access_token"):
            return {"error": "Slack not connected"}

        access_token = self._decrypt(slack_settings["access_token"])
        clients = await self.client_repo.search(agency_id, limit=500)
        mentions_found = 0

        from app.services.context_service import ContextService
        ctx_svc = ContextService()

        for client in clients:
            try:
                messages = await self._slack.search_messages(access_token, client.name, count=10)
                if not messages:
                    continue

                # Separate internal vs external discussions
                internal = [m for m in messages if m.get("is_internal", True)]
                external = [m for m in messages if not m.get("is_internal", True)]

                slack_summary = ""
                if internal:
                    slack_summary += f"Internal Slack discussions about {client.name}:\n"
                    for m in internal[:5]:
                        slack_summary += f"- [{m.get('channel', '')}] {m.get('user', '')}: {m.get('text', '')[:200]}\n"
                if external:
                    slack_summary += f"\nShared channel messages with {client.name}:\n"
                    for m in external[:5]:
                        slack_summary += f"- {m.get('text', '')[:200]}\n"

                if slack_summary:
                    existing = client.context_profile or {}
                    extraction = await ctx_svc.extract_context(slack_summary)
                    merged = await ctx_svc.merge_context(existing, extraction)

                    # Mark internal discussions source
                    merged.setdefault("_sources", {})["slack"] = {
                        "mention_count": len(messages),
                        "internal_count": len(internal),
                        "last_sync": datetime.now(timezone.utc).isoformat(),
                    }

                    await self.client_repo.update(client.id, context_profile=merged)
                    mentions_found += len(messages)

            except Exception:
                logger.exception(
                    "Slack sync failed for one client; skipping",
                    extra={"event": "connector.slack.client_sync_failed", "client_id": str(client.id)},
                )
                continue

        # Update last sync
        settings = dict(agency.settings or {})
        slack_s = dict(settings.get("slack", {}))
        slack_s["last_sync"] = datetime.now(timezone.utc).isoformat()
        settings["slack"] = slack_s
        await self.agency_repo.update(agency_id, settings=settings)

        return {"clients_synced": len(clients), "mentions_found": mentions_found}
