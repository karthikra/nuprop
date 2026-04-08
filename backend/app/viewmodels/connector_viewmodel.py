from __future__ import annotations

import time
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.infrastructure.db.models.base import IS_SQLITE, _uuid_default
from app.infrastructure.db.repositories.agency_repo import AgencyRepository
from app.infrastructure.db.repositories.client_repo import ClientRepository
from app.infrastructure.db.repositories.email_index_repo import EmailIndexRepository
from app.infrastructure.external.gcal_client import GCalClient
from app.infrastructure.external.gdrive_client import GDriveClient
from app.infrastructure.external.gmail_client import GmailClient
from app.infrastructure.external.slack_client import SlackClient
from app.services.ai.email_classifier import EmailClassifier
from app.viewmodels.shared.viewmodel import ViewModelBase

FREEMAIL_DOMAINS = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com", "aol.com", "protonmail.com"}


class ConnectorViewModel(ViewModelBase):
    def __init__(self, request: Request, db: AsyncSession):
        super().__init__(request, db)
        self._gmail = GmailClient()
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
        key = get_settings().ENCRYPTION_KEY
        if not key:
            return text  # No encryption in dev
        from cryptography.fernet import Fernet
        return Fernet(key.encode()).encrypt(text.encode()).decode()

    def _decrypt(self, text: str) -> str:
        key = get_settings().ENCRYPTION_KEY
        if not key:
            return text
        from cryptography.fernet import Fernet
        return Fernet(key.encode()).decrypt(text.encode()).decode()

    # ── OAuth flow ───────────────────────────────────────────

    async def get_auth_url(self, agency_id: UUID) -> str:
        if not self._gmail.is_configured:
            self.error = "Google OAuth not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."
            self.status_code = 400
            return ""
        return self._gmail.get_auth_url(str(agency_id))

    async def handle_callback(self, agency_id: UUID, code: str) -> dict:
        tokens = await self._gmail.exchange_code(code)
        access_token = tokens["access_token"]
        refresh_token = tokens.get("refresh_token", "")

        email = await self._gmail.get_user_email(access_token)

        agency = await self.agency_repo.get_by_id(agency_id)
        if not agency:
            self.error = "Agency not found"
            self.status_code = 404
            return {}

        settings = dict(agency.settings or {})
        settings["gmail"] = {
            "connected": True,
            "email": email,
            "refresh_token": self._encrypt(refresh_token),
            "last_sync": None,
            "email_count": 0,
        }
        await self.agency_repo.update(agency_id, settings=settings)

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
            except Exception:
                pass

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

        refresh_token = self._decrypt(gmail["refresh_token"])
        access_token = await self._gmail.refresh_access_token(refresh_token)

        # Get client domains
        clients = await self.client_repo.search(agency_id, limit=500)
        domain_map = self._extract_domains(clients)
        if not domain_map:
            return {"new_emails": 0, "total_emails": 0, "domains_synced": [], "duration_seconds": 0}

        # Parse last_sync
        since = None
        if gmail.get("last_sync"):
            try:
                since = datetime.fromisoformat(str(gmail["last_sync"]))
            except Exception:
                pass

        classifier = EmailClassifier()
        total_new = 0
        synced_domains = []

        for domain, client_name in domain_map.items():
            try:
                messages = await self._gmail.fetch_messages_for_domain(access_token, domain, since, limit=100)
                if not messages:
                    continue

                # Filter out already-indexed
                msg_ids = [m["id"] for m in messages]
                existing = await self.email_repo.get_existing_message_ids(agency_id, msg_ids)
                new_messages = [m for m in messages if m["id"] not in existing]

                if not new_messages:
                    synced_domains.append(domain)
                    continue

                # Classify
                classifications = await classifier.classify_batch(new_messages, concurrency=5)

                # Store
                now = datetime.now(timezone.utc)
                for msg, cls in zip(new_messages, classifications):
                    from app.infrastructure.db.models.email_index import EmailIndex
                    email = EmailIndex(
                        id=_uuid_default(),
                        agency_id=str(agency_id) if IS_SQLITE else agency_id,
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
                        to_addresses=msg.get("to", "").split(","),
                        subject=msg.get("subject", ""),
                        date=msg["date"] if isinstance(msg["date"], datetime) else now,
                        has_attachments=msg.get("has_attachments", False),
                        synced_at=now,
                    )
                    self._db.add(email)

                total_new += len(new_messages)
                synced_domains.append(domain)

            except Exception:
                continue  # Don't let one domain failure stop the whole sync

        # Update last_sync
        settings = dict(agency.settings or {})
        gmail_settings = dict(settings.get("gmail", {}))
        gmail_settings["last_sync"] = datetime.now(timezone.utc).isoformat()
        email_count = await self.email_repo.count_by_agency(agency_id)
        gmail_settings["email_count"] = email_count
        settings["gmail"] = gmail_settings
        await self.agency_repo.update(agency_id, settings=settings)

        duration = round(time.time() - start, 1)

        return {
            "new_emails": total_new,
            "total_emails": email_count,
            "domains_synced": synced_domains,
            "duration_seconds": duration,
        }

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
                continue

        return {"clients_synced": len(clients), "meetings_found": meetings_found}

    # ── Slack ────────────────────────────────────────────────

    async def get_slack_auth_url(self, agency_id: UUID) -> str:
        slack = SlackClient()
        if not slack.is_configured:
            self.error = "Slack OAuth not configured"
            self.status_code = 400
            return ""
        return slack.get_auth_url(str(agency_id))

    async def handle_slack_callback(self, agency_id: UUID, code: str) -> dict:
        slack = SlackClient()
        data = await slack.exchange_code(code)

        access_token = data.get("access_token", "")
        team = data.get("team", {})
        workspace_name = team.get("name", "")

        agency = await self.agency_repo.get_by_id(agency_id)
        if not agency:
            return {}

        settings = dict(agency.settings or {})
        settings["slack"] = {
            "connected": True,
            "workspace": workspace_name,
            "access_token": self._encrypt(access_token),
            "last_sync": None,
        }
        await self.agency_repo.update(agency_id, settings=settings)

        return {"connected": True, "workspace": workspace_name}

    async def get_slack_status(self, agency_id: UUID) -> dict:
        agency = await self.agency_repo.get_by_id(agency_id)
        if not agency:
            return {"connected": False}
        slack_settings = (agency.settings or {}).get("slack", {})
        slack = SlackClient()
        return {
            "connected": slack_settings.get("connected", False),
            "configured": slack.is_configured,
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
        slack = SlackClient()
        clients = await self.client_repo.search(agency_id, limit=500)
        mentions_found = 0

        from app.services.context_service import ContextService
        ctx_svc = ContextService()

        for client in clients:
            try:
                messages = await slack.search_messages(access_token, client.name, count=10)
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
                continue

        # Update last sync
        settings = dict(agency.settings or {})
        slack_s = dict(settings.get("slack", {}))
        slack_s["last_sync"] = datetime.now(timezone.utc).isoformat()
        settings["slack"] = slack_s
        await self.agency_repo.update(agency_id, settings=settings)

        return {"clients_synced": len(clients), "mentions_found": mentions_found}
