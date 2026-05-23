from __future__ import annotations

from types import SimpleNamespace

from app.viewmodels.connector_viewmodel import ConnectorViewModel


def test_extract_domains_skips_email_without_at_sign():
    """A contact email lacking an '@' must be skipped, not crash or
    produce a bogus domain entry."""
    # _extract_domains does not touch `self`; bypass __init__ to avoid the
    # DB-session dependency.
    vm = ConnectorViewModel.__new__(ConnectorViewModel)
    good = SimpleNamespace(name="Acme", contacts=[{"email": "ceo@acme.com"}])
    malformed = SimpleNamespace(name="Broken", contacts=[{"email": "not-an-email"}])

    result = vm._extract_domains([good, malformed])

    assert result == {"acme.com": "Acme"}
