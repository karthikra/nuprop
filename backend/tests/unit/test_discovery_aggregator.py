from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.connectors.discovery_aggregator import (
    aggregate,
    suggest_name_from_domain,
)


def msg(*, from_: str = "", to: str = "", date: datetime | None = None, msg_id: str = "m"):
    return {
        "id": msg_id,
        "from": from_,
        "to": to,
        "date": date or datetime(2026, 5, 1, tzinfo=timezone.utc),
    }


# ── suggest_name_from_domain ─────────────────────────────────


@pytest.mark.parametrize("domain,expected", [
    ("acme.com", "Acme"),
    ("tatacomms.com", "Tatacomms"),
    ("single.io", "Single"),
    ("mckinsey.com", "Mckinsey"),
])
def test_suggest_name_from_domain(domain: str, expected: str) -> None:
    assert suggest_name_from_domain(domain) == expected


def test_suggest_name_from_subdomain_uses_first_segment() -> None:
    assert suggest_name_from_domain("mail.acme.com") == "Mail"


# ── aggregate ────────────────────────────────────────────────


def test_aggregate_empty_messages_returns_empty() -> None:
    assert aggregate([], own_domain=None, excluded_domains=set()) == []


def test_aggregate_single_message_yields_one_candidate() -> None:
    out = aggregate(
        [msg(from_="Jane Doe <jane@acme.com>")],
        own_domain=None,
        excluded_domains=set(),
    )
    assert len(out) == 1
    c = out[0]
    assert c.domain == "acme.com"
    assert c.suggested_name == "Acme"
    assert c.message_count == 1
    assert c.sender_count == 1
    assert c.top_senders[0].email == "jane@acme.com"
    assert c.top_senders[0].name == "Jane Doe"


def test_aggregate_two_senders_same_domain_combine() -> None:
    out = aggregate(
        [
            msg(from_="Jane <jane@acme.com>", msg_id="1"),
            msg(from_="Bob <bob@acme.com>", msg_id="2"),
        ],
        own_domain=None,
        excluded_domains=set(),
    )
    assert len(out) == 1
    assert out[0].message_count == 2
    assert out[0].sender_count == 2
    emails = {s.email for s in out[0].top_senders}
    assert emails == {"jane@acme.com", "bob@acme.com"}


def test_aggregate_filters_freemail_sender() -> None:
    out = aggregate(
        [msg(from_="someone@gmail.com")],
        own_domain=None,
        excluded_domains=set(),
    )
    assert out == []


def test_aggregate_filters_saas_noise_sender() -> None:
    # 'support@' is a real human-looking local-part, so this exercises the
    # SAAS_NOISE_DOMAINS branch specifically (not the no-reply branch).
    out = aggregate(
        [msg(from_="support@github.com")],
        own_domain=None,
        excluded_domains=set(),
    )
    assert out == []


def test_aggregate_filters_noreply_local_part() -> None:
    out = aggregate(
        [
            msg(from_="noreply@acme.com", msg_id="1"),
            msg(from_="jane@acme.com", msg_id="2"),
        ],
        own_domain=None,
        excluded_domains=set(),
    )
    assert len(out) == 1
    assert out[0].message_count == 1
    assert out[0].sender_count == 1
    assert out[0].top_senders[0].email == "jane@acme.com"


def test_aggregate_filters_own_domain() -> None:
    out = aggregate(
        [msg(from_="me@veeville.com")],
        own_domain="veeville.com",
        excluded_domains=set(),
    )
    assert out == []


def test_aggregate_filters_excluded_domain() -> None:
    out = aggregate(
        [msg(from_="jane@acme.com")],
        own_domain=None,
        excluded_domains={"acme.com"},
    )
    assert out == []


def test_aggregate_sort_by_message_count_desc() -> None:
    out = aggregate(
        [
            msg(from_="a@small.com", msg_id="1"),
            msg(from_="a@big.com", msg_id="2"),
            msg(from_="b@big.com", msg_id="3"),
            msg(from_="c@big.com", msg_id="4"),
        ],
        own_domain=None,
        excluded_domains=set(),
    )
    assert [c.domain for c in out] == ["big.com", "small.com"]


def test_aggregate_sort_tiebreaker_by_last_date_desc() -> None:
    old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    new = datetime(2026, 5, 1, tzinfo=timezone.utc)
    out = aggregate(
        [
            msg(from_="x@old.com", date=old, msg_id="1"),
            msg(from_="x@new.com", date=new, msg_id="2"),
        ],
        own_domain=None,
        excluded_domains=set(),
    )
    assert [c.domain for c in out] == ["new.com", "old.com"]


def test_aggregate_top_senders_capped_at_three_ordered_by_count() -> None:
    msgs = []
    for i, (name, count) in enumerate([("a", 4), ("b", 3), ("c", 2), ("d", 1)]):
        for j in range(count):
            msgs.append(msg(from_=f"{name}@acme.com", msg_id=f"{name}{j}"))
    out = aggregate(msgs, own_domain=None, excluded_domains=set())
    assert len(out[0].top_senders) == 3
    assert [s.email for s in out[0].top_senders] == [
        "a@acme.com", "b@acme.com", "c@acme.com",
    ]


def test_aggregate_truncates_at_30_candidates() -> None:
    msgs = [msg(from_=f"x@dom{i}.com", msg_id=f"{i}") for i in range(50)]
    out = aggregate(msgs, own_domain=None, excluded_domains=set())
    assert len(out) == 30


def test_aggregate_recipient_direction_counts() -> None:
    out = aggregate(
        [msg(from_="me@veeville.com", to="Jane <jane@acme.com>")],
        own_domain="veeville.com",
        excluded_domains=set(),
    )
    assert len(out) == 1
    assert out[0].domain == "acme.com"
    assert out[0].message_count == 1


def test_aggregate_mixed_directions_combine() -> None:
    out = aggregate(
        [
            msg(from_="jane@acme.com", to="me@veeville.com", msg_id="1"),
            msg(from_="me@veeville.com", to="bob@acme.com", msg_id="2"),
        ],
        own_domain="veeville.com",
        excluded_domains=set(),
    )
    assert len(out) == 1
    assert out[0].domain == "acme.com"
    assert out[0].message_count == 2
    assert out[0].sender_count == 2
