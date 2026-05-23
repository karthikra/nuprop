"""Integration tests for the rate-card-gaps fill + skip endpoints.

POST /api/v1/proposals/{id}/rate-card-gaps/fill   — merge entries into rate
    card and clear gaps, then enqueue run_research.
POST /api/v1/proposals/{id}/rate-card-gaps/skip   — clear gaps without
    touching the rate card, then enqueue run_research (204 No Content).
"""

from __future__ import annotations

from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from app.infrastructure.db.repositories.rate_card_repo import RateCardRepository
from tests.conftest import API

_GAPS = {
    "missing_roles": ["senior_strategist"],
    "missing_offerings": ["annual_retainer"],
    "needed_roles": ["senior_strategist"],
    "needed_offerings": ["annual_retainer"],
}


async def _setup(http, headers):
    """Create a client + proposal via the API; return the proposal dict."""
    client_resp = await http.post(f"{API}/clients", headers=headers, json={"name": "Gaps Client"})
    assert client_resp.status_code == 201, client_resp.text
    c = client_resp.json()
    p_resp = await http.post(
        f"{API}/proposals",
        headers=headers,
        json={"client_id": c["id"], "project_name": "Gaps Project"},
    )
    assert p_resp.status_code == 201, p_resp.text
    return p_resp.json()


async def test_fill_merges_into_agency_rate_card_and_clears_gaps(
    client, registered, arq_pool, db
):
    """Fill endpoint: merges submitted entries into the agency rate card,
    clears proposal.rate_card_gaps, and enqueues run_research."""
    p = await _setup(client, registered.headers)

    # Stamp gaps directly via repo so we don't depend on the pipeline worker.
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
    assert resp.json() == {"ok": True}

    # gaps cleared
    proposal = await ProposalRepository(db).get_by_id(p["id"])
    await db.refresh(proposal)
    assert proposal.rate_card_gaps is None

    # rate card contains the new entries
    rc = await RateCardRepository(db).get_active(registered.agency_id)
    assert rc is not None
    assert rc.hourly_rates.get("senior_strategist") == 4500
    assert "annual_retainer" in rc.offerings

    # enqueue was called with run_research
    arq_pool.enqueue_job.assert_awaited()
    assert arq_pool.enqueue_job.await_args.args[0] == "run_research"


async def test_fill_rejects_keys_outside_detected_gaps(
    client, registered, arq_pool, db
):
    """Fill endpoint: returns 400 when a submitted key is not in the gaps."""
    p = await _setup(client, registered.headers)
    await ProposalRepository(db).update(p["id"], rate_card_gaps=_GAPS)
    await db.commit()

    resp = await client.post(
        f"{API}/proposals/{p['id']}/rate-card-gaps/fill",
        headers=registered.headers,
        json={"hourly_rates": {"unrelated_role": 9999}},
    )
    assert resp.status_code == 400


async def test_skip_clears_gaps_without_touching_rate_card(
    client, registered, arq_pool, db
):
    """Skip endpoint: clears gaps, does NOT create/modify the rate card, and
    enqueues run_research. Returns 204 No Content."""
    p = await _setup(client, registered.headers)
    await ProposalRepository(db).update(p["id"], rate_card_gaps=_GAPS)
    await db.commit()

    # no rate card exists before the call
    rc_before = await RateCardRepository(db).get_active(registered.agency_id)
    assert rc_before is None

    resp = await client.post(
        f"{API}/proposals/{p['id']}/rate-card-gaps/skip",
        headers=registered.headers,
    )
    assert resp.status_code == 204, resp.text

    # gaps cleared
    proposal = await ProposalRepository(db).get_by_id(p["id"])
    await db.refresh(proposal)
    assert proposal.rate_card_gaps is None

    # rate card still absent
    rc_after = await RateCardRepository(db).get_active(registered.agency_id)
    assert rc_after is None

    # enqueue was called with run_research
    arq_pool.enqueue_job.assert_awaited()
    assert arq_pool.enqueue_job.await_args.args[0] == "run_research"
