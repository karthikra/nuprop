from __future__ import annotations

import inspect

from app.infrastructure.db.repositories.client_repo import ClientRepository


def test_client_repo_search_default_limit_is_500():
    """Agencies with more than 50 clients must not silently lose the tail
    of their client list."""
    sig = inspect.signature(ClientRepository.search)
    assert sig.parameters["limit"].default == 500
