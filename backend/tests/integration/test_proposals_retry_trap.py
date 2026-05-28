"""Regression: the three rate-card endpoints that kick off ``run_research``
must DEL the ARQ result-cache key (``arq:result:<pid>:run_research``) before
enqueueing, so a failed prior run doesn't silently swallow the re-enqueue for
the 24h result-cache TTL window.

The endpoints are:
  * POST /proposals/{id}/rate-card-gaps/fill
  * POST /proposals/{id}/rate-card-gaps/skip
  * POST /proposals/{id}/rate-card-import/confirm

All now route through ``app.infrastructure.queue.enqueue.enqueue_phase_job``.
Mirrors the fixture/seeding patterns from ``test_rate_card_gaps_endpoints.py``.
"""

from __future__ import annotations

from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from tests.conftest import API

_GAPS = {
    "missing_roles": ["senior_strategist"],
    "missing_offerings": ["annual_retainer"],
    "needed_roles": ["senior_strategist"],
    "needed_offerings": ["annual_retainer"],
}


async def _setup(http, headers):
    """Create a client + proposal via the API; return the proposal dict."""
    c = (await http.post(
        f"{API}/clients", headers=headers, json={"name": "Trap Client"},
    )).json()
    p = (await http.post(
        f"{API}/proposals",
        headers=headers,
        json={"client_id": c["id"], "project_name": "Trap Project"},
    )).json()
    return p


def _assert_del_then_enqueue(arq_pool, pid):
    arq_pool.delete.assert_awaited()
    assert arq_pool.delete.await_args.args[0] == f"arq:result:{pid}:run_research"
    arq_pool.enqueue_job.assert_awaited()
    assert arq_pool.enqueue_job.await_args.args[0] == "run_research"


async def test_fill_clears_stale_result_key_before_enqueue(
    client, registered, arq_pool, db
):
    p = await _setup(client, registered.headers)
    await ProposalRepository(db).update(p["id"], rate_card_gaps=_GAPS)
    await db.commit()

    resp = await client.post(
        f"{API}/proposals/{p['id']}/rate-card-gaps/fill",
        headers=registered.headers,
        json={
            "hourly_rates": {"senior_strategist": 4500},
            "offerings": {
                "annual_retainer": {"name": "Annual Retainer", "base_price": 100000}
            },
        },
    )
    assert resp.status_code == 200, resp.text
    _assert_del_then_enqueue(arq_pool, p["id"])


async def test_skip_clears_stale_result_key_before_enqueue(
    client, registered, arq_pool, db
):
    p = await _setup(client, registered.headers)
    await ProposalRepository(db).update(p["id"], rate_card_gaps=_GAPS)
    await db.commit()

    resp = await client.post(
        f"{API}/proposals/{p['id']}/rate-card-gaps/skip",
        headers=registered.headers,
    )
    assert resp.status_code == 204, resp.text
    _assert_del_then_enqueue(arq_pool, p["id"])


async def test_import_confirm_clears_stale_result_key_before_enqueue(
    client, registered, arq_pool, db
):
    p = await _setup(client, registered.headers)

    resp = await client.post(
        f"{API}/proposals/{p['id']}/rate-card-import/confirm",
        headers=registered.headers,
        json={
            "hourly_rates": {"senior_strategist": 4500},
            "offerings": {},
            "multipliers": {},
        },
    )
    assert resp.status_code == 200, resp.text
    _assert_del_then_enqueue(arq_pool, p["id"])
