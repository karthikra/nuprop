"""
Pure aggregation logic for client discovery from Gmail.

The single source of truth for:
- which domains are considered freemail (FREEMAIL_DOMAINS) and noise (SAAS_NOISE_DOMAINS)
- which sender local-parts are automated (NO_REPLY_PATTERN)
- the company-name guess heuristic (suggest_name_from_domain)
- the per-domain aggregation (aggregate)

Stateless. No I/O. Fully unit-testable.
"""
from __future__ import annotations

import re
from datetime import datetime
from email.utils import getaddresses

from app.domain.schemas.discovery_schemas import Candidate, TopSender

# Personal email providers — sender being on one of these is a strong signal it's
# not a corporate client. Mirrors what was inline in connector_viewmodel.py (which
# now re-imports from here to keep one source of truth).
FREEMAIL_DOMAINS: frozenset[str] = frozenset({
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
    "icloud.com", "aol.com", "protonmail.com",
})

# Domains that are almost certainly tooling, not clients. Subjective; grow as patterns emerge.
SAAS_NOISE_DOMAINS: frozenset[str] = frozenset({
    "github.com", "gitlab.com", "bitbucket.org",
    "linear.app", "notion.so", "slack.com",
    "atlassian.com", "jira.com",
    "figma.com", "calendly.com", "zoom.us",
    "mailchimp.com", "sendgrid.net",
    "hubspot.com", "salesforce.com",
    "stripe.com", "paypal.com", "docusign.com",
    "dropbox.com", "box.com",
})

# Local-part prefixes that indicate automated senders. Matches messages but
# preserves the domain's count from human senders at the same domain.
NO_REPLY_PATTERN: re.Pattern[str] = re.compile(
    r"^(noreply|no-reply|notifications?|mailer-daemon|donotreply|do-not-reply|automated)@",
    re.IGNORECASE,
)

MAX_CANDIDATES = 30
MAX_TOP_SENDERS = 3


def suggest_name_from_domain(domain: str) -> str:
    """Strip TLD + subdomains, capitalize the leftmost label.

    'acme.com' -> 'Acme', 'tatacomms.com' -> 'Tatacomms', 'mail.acme.com' -> 'Mail'.
    Intentionally crude -- the review wizard exists to fix bad guesses.
    """
    base = domain.split(".", 1)[0]
    if not base:
        return domain
    return base[:1].upper() + base[1:]


def _parse_addresses(field: str) -> list[tuple[str, str]]:
    """Parse a 'From:' or 'To:' header value into [(display_name, address), ...].

    Returns empty list if parsing yields no usable addresses.
    """
    if not field:
        return []
    parsed = getaddresses([field])
    return [(name, addr.lower()) for name, addr in parsed if addr and "@" in addr]


def _should_skip(
    address: str,
    own_domain: str | None,
    excluded_domains: set[str],
) -> tuple[bool, str | None]:
    """Return (skip, domain). If skip=True, domain may be None.

    Logic order matches the spec:
    - skip messages from no-reply addresses entirely
    - extract domain and check against freemail, SaaS noise, own-domain, excluded
    """
    if NO_REPLY_PATTERN.match(address):
        return True, None
    domain = address.split("@")[-1].lower()
    if not domain:
        return True, None
    if domain in FREEMAIL_DOMAINS:
        return True, None
    if domain in SAAS_NOISE_DOMAINS:
        return True, None
    if own_domain and domain == own_domain.lower():
        return True, None
    if domain in excluded_domains:
        return True, None
    return False, domain


def aggregate(
    messages: list[dict],
    own_domain: str | None,
    excluded_domains: set[str],
) -> list[Candidate]:
    """Group messages by sender/recipient domain into candidate clients.

    A "message" must have keys: id, from, to, date.
    Returns up to MAX_CANDIDATES candidates ranked by message_count desc,
    then last_date desc as tiebreaker.
    """
    by_domain: dict[str, dict] = {}

    for message in messages:
        date = message.get("date")
        if not isinstance(date, datetime):
            continue

        parties: list[tuple[str, str]] = []
        parties.extend(_parse_addresses(message.get("from", "")))
        parties.extend(_parse_addresses(message.get("to", "")))

        domains_in_this_message: set[str] = set()
        for display_name, address in parties:
            skip, domain = _should_skip(address, own_domain, excluded_domains)
            if skip or domain is None:
                continue
            if domain in domains_in_this_message:
                bucket = by_domain[domain]
                if address not in bucket["senders"]:
                    bucket["senders"][address] = {"name": display_name or address, "count": 0}
                bucket["senders"][address]["count"] += 1
                continue
            domains_in_this_message.add(domain)

            if domain not in by_domain:
                by_domain[domain] = {
                    "message_count": 0,
                    "senders": {},
                    "first_date": date,
                    "last_date": date,
                }
            bucket = by_domain[domain]
            bucket["message_count"] += 1
            if date < bucket["first_date"]:
                bucket["first_date"] = date
            if date > bucket["last_date"]:
                bucket["last_date"] = date
            if address not in bucket["senders"]:
                bucket["senders"][address] = {"name": display_name or address, "count": 0}
            bucket["senders"][address]["count"] += 1

    candidates: list[Candidate] = []
    for domain, bucket in by_domain.items():
        top = sorted(
            bucket["senders"].items(),
            key=lambda kv: (-kv[1]["count"], kv[0]),
        )[:MAX_TOP_SENDERS]
        candidates.append(Candidate(
            domain=domain,
            suggested_name=suggest_name_from_domain(domain),
            message_count=bucket["message_count"],
            sender_count=len(bucket["senders"]),
            top_senders=[
                TopSender(name=v["name"], email=k, message_count=v["count"])
                for k, v in top
            ],
            first_date=bucket["first_date"],
            last_date=bucket["last_date"],
        ))

    candidates.sort(key=lambda c: (-c.message_count, -c.last_date.timestamp()))
    return candidates[:MAX_CANDIDATES]
