"""Integration tests for the Excel rate-card import endpoints.

POST /api/v1/proposals/{id}/rate-card-import          — multipart xlsx upload; returns preview (not persisted)
POST /api/v1/proposals/{id}/rate-card-import/confirm  — accepts preview JSON; writes to rate_card_override;
                                                         clears rate_card_gaps; enqueues run_research.
"""

from __future__ import annotations

from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from openpyxl import Workbook

from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from tests.conftest import API


def _build_sample_xlsx() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Rates"
    ws.append(["Role", "Hourly rate (INR)"])
    ws.append(["Senior Strategist", 4500])
    ws.append(["Junior Designer", 1800])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def _setup(http, headers):
    """Create a client + proposal via the API; return the proposal dict."""
    client_resp = await http.post(f"{API}/clients", headers=headers, json={"name": "Import Client"})
    assert client_resp.status_code == 201, client_resp.text
    c = client_resp.json()
    p_resp = await http.post(
        f"{API}/proposals",
        headers=headers,
        json={"client_id": c["id"], "project_name": "Import Project"},
    )
    assert p_resp.status_code == 201, p_resp.text
    return p_resp.json()


@pytest.mark.asyncio
async def test_import_upload_returns_preview(
    client, registered, arq_pool, db, monkeypatch
):
    """POST /rate-card-import accepts an xlsx + returns the parsed preview
    WITHOUT writing to rate_card_override yet."""
    from app.services import rate_card_excel_parser

    fake_extracted = {
        "hourly_rates": {"senior_strategist": 4500, "junior_designer": 1800},
        "offerings": {},
        "multipliers": {},
        "low_confidence_fields": [],
    }
    monkeypatch.setattr(
        rate_card_excel_parser,
        "extract_with_llm",
        AsyncMock(return_value=fake_extracted),
    )

    p = await _setup(client, registered.headers)
    xlsx_bytes = _build_sample_xlsx()

    resp = await client.post(
        f"{API}/proposals/{p['id']}/rate-card-import",
        headers=registered.headers,
        files={"file": ("rates.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["hourly_rates"]["senior_strategist"] == 4500
    assert body["hourly_rates"]["junior_designer"] == 1800

    # NOT persisted — rate_card_override must still be None
    proposal = await ProposalRepository(db).get_by_id(p["id"])
    await db.refresh(proposal)
    assert proposal.rate_card_override is None


@pytest.mark.asyncio
async def test_import_confirm_writes_override_and_resumes(
    client, registered, arq_pool, db
):
    """POST /rate-card-import/confirm writes proposal.rate_card_override,
    clears gaps, enqueues run_research."""
    p = await _setup(client, registered.headers)

    # Stamp gaps directly so we can verify they get cleared.
    _GAPS = {
        "missing_roles": ["senior_strategist"],
        "missing_offerings": [],
        "needed_roles": ["senior_strategist"],
        "needed_offerings": [],
    }
    await ProposalRepository(db).update(p["id"], rate_card_gaps=_GAPS)
    await db.commit()

    preview = {
        "hourly_rates": {"senior_strategist": 4500, "junior_designer": 1800},
        "offerings": {},
        "multipliers": {},
        "low_confidence_fields": [],
    }

    resp = await client.post(
        f"{API}/proposals/{p['id']}/rate-card-import/confirm",
        headers=registered.headers,
        json=preview,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True}

    # rate_card_override was written
    proposal = await ProposalRepository(db).get_by_id(p["id"])
    await db.refresh(proposal)
    assert proposal.rate_card_override is not None
    assert proposal.rate_card_override["hourly_rates"]["senior_strategist"] == 4500

    # gaps cleared
    assert proposal.rate_card_gaps is None

    # enqueue was called with run_research
    arq_pool.enqueue_job.assert_awaited()
    assert arq_pool.enqueue_job.await_args.args[0] == "run_research"


@pytest.mark.asyncio
async def test_import_rejects_non_xlsx(client, registered, arq_pool):
    """Non-xlsx upload returns 400."""
    p = await _setup(client, registered.headers)

    resp = await client.post(
        f"{API}/proposals/{p['id']}/rate-card-import",
        headers=registered.headers,
        files={"file": ("data.csv", b"role,rate\nstrategist,4500", "text/plain")},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_import_rejects_oversize(client, registered, arq_pool):
    """File larger than 5 MB returns 400."""
    from app.services.rate_card_excel_parser import MAX_BYTES

    p = await _setup(client, registered.headers)
    big_content = b"x" * (MAX_BYTES + 1)

    resp = await client.post(
        f"{API}/proposals/{p['id']}/rate-card-import",
        headers=registered.headers,
        files={"file": ("big.xlsx", big_content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert resp.status_code == 400
