"""Shared pytest fixtures for the NUPROP backend test suite.

The test environment is configured at *import time* — before any ``app`` module
is imported — so the application's module-level ``engine`` /
``async_session_factory`` (in ``app.infrastructure.db.database``) bind to an
isolated temp-file SQLite database instead of the real dev database. This also
means code that uses ``async_session_factory`` directly (``track.py``, the
WebSocket endpoint) runs against the test database too.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass

# ── Test environment — MUST be set before importing anything from ``app`` ────
_TMP_DB_FD, _TMP_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="nuprop_test_")
os.close(_TMP_DB_FD)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP_DB_PATH}"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["ENVIRONMENT"] = "test"
os.environ["REDIS_ENABLED"] = "false"
os.environ["DEBUG"] = "false"                 # keep SQLAlchemy engine echo quiet
# AWS region pinned so AsyncAnthropicBedrock can be constructed without warnings;
# no real Bedrock call is ever made — the _no_network guard below blocks them.
os.environ.setdefault("AWS_REGION", "ap-northeast-1")

from unittest.mock import AsyncMock  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.infrastructure.db.database import Base, async_session_factory, engine  # noqa: E402
from app.infrastructure.db.models import *  # noqa: E402,F401,F403  — register every model on Base.metadata
from app.infrastructure.db.models.template import StrategyTemplate  # noqa: E402
from app.infrastructure.db.repositories.agency_repo import AgencyRepository  # noqa: E402
from app.infrastructure.db.repositories.client_repo import ClientRepository  # noqa: E402
from app.infrastructure.db.repositories.proposal_repo import ProposalRepository  # noqa: E402
from app.infrastructure.external.anthropic_client import AnthropicClient  # noqa: E402
from app.main import app  # noqa: E402

API = "/api/v1"


# ── No-network guard ─────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Hard guard: no test may make a real Bedrock / LLM network call.

    Since the Bedrock migration, ``is_configured`` is always True at runtime
    (auth comes from the AWS SDK credential chain at call time, not from a
    config flag). The guard below forces it back to False during tests so AI
    agents fall through to their non-LLM paths, AND replaces the real network
    methods with a loud failure in case anything slips past the gate.

    Tests that exercise an AI path monkeypatch the *service* method (e.g.
    ``BriefAnalyzer.analyze``) — those patches are applied after this fixture
    and therefore win.
    """

    async def _blocked(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("Real Bedrock/Anthropic API call attempted during a test")

    monkeypatch.setattr(AnthropicClient, "complete", _blocked, raising=False)
    monkeypatch.setattr(AnthropicClient, "complete_json", _blocked, raising=False)
    monkeypatch.setattr(AnthropicClient, "stream", _blocked, raising=False)
    monkeypatch.setattr(AnthropicClient, "is_configured", property(lambda self: False))


# ── Database / schema ────────────────────────────────────────────────────────
@pytest_asyncio.fixture
async def _schema():
    """Drop + recreate every table around each test for full isolation."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db(_schema) -> AsyncSession:
    """A plain async session for repository / viewmodel / service tests."""
    async with async_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(_schema) -> AsyncClient:
    """An httpx client wired to the FastAPI app over ASGI (no real socket)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def arq_pool():
    """Install a mock ARQ pool on app.state so enqueue calls are captured.

    The ASGITransport test client does not run the FastAPI lifespan, so
    ``app.state.arq_pool`` is unset by default; tests that exercise the enqueue
    paths require this fixture explicitly.
    """
    pool = AsyncMock()
    app.state.arq_pool = pool
    yield pool
    if hasattr(app.state, "arq_pool"):
        delattr(app.state, "arq_pool")


@pytest.fixture
def ws_publish_spy(monkeypatch):
    """Stub events.publish so a test can assert WS emits without a real Redis.

    Opt-in (not autouse) because making it autouse would break tests that
    legitimately exercise the publish path against a mock ``redis`` client (e.g.
    ``test_publish_pushes_a_json_envelope_to_the_channel``).
    """
    published: list[tuple[str, dict]] = []

    async def _spy(redis, proposal_id, payload):  # noqa: ANN001
        published.append((str(proposal_id), payload))

    monkeypatch.setattr("app.infrastructure.queue.events.publish", _spy)
    # PipelineService imports `publish` by name — patch that binding too
    monkeypatch.setattr("app.services.pipeline_service.publish", _spy, raising=False)
    # IdeationService also imports `publish` by name
    monkeypatch.setattr("app.services.ideation_service.publish", _spy, raising=False)
    return published


# ── Proposal factories ───────────────────────────────────────────────────────
@pytest_asyncio.fixture
async def make_proposal_db(db):
    """DB-level factory: creates agency + client + proposal directly via repos.

    Returns an async callable. Each invocation creates a fresh trio in the test
    DB (unique slug per call so the same test can produce multiple proposals).
    Returns a ``(agency, client, proposal)`` tuple — unpack to taste.

    ::

        agency, client, proposal = await make_proposal_db()
        _, _, proposal = await make_proposal_db(brief={"client": {"name": "Acme"}})
    """
    counter = {"n": 0}

    async def _make(
        *,
        brief: dict | None = None,
        pipeline_state: dict | None = None,
        project_name: str = "Test Project",
    ):
        counter["n"] += 1
        n = counter["n"]
        agency = await AgencyRepository(db).create(name=f"Agency {n}", slug=f"agency-{n}")
        client = await ClientRepository(db).create(
            agency_id=agency.id, name=f"Client {n}", slug=f"client-{n}",
        )
        proposal = await ProposalRepository(db).create(
            agency_id=agency.id,
            client_id=client.id,
            project_name=project_name,
            brief=brief if brief is not None else {},
            pipeline_state=pipeline_state if pipeline_state is not None else {
                "current_phase": "brief",
                "phases_completed": [],
            },
        )
        await db.commit()
        return agency, client, proposal

    return _make


@pytest.fixture
def make_proposal_api():
    """HTTP-level factory: creates client + proposal via the FastAPI endpoints.

    Returns an async callable. Each invocation does two POSTs (clients + proposals)
    and returns the proposal dict from the API response. Caller supplies the
    authenticated httpx client and headers (typically via the ``registered``
    fixture).

    ::

        proposal = await make_proposal_api(client, registered.headers)
    """
    counter = {"n": 0}

    async def _make(http, headers, *, project_name: str = "Test Project"):
        counter["n"] += 1
        n = counter["n"]
        c = (await http.post(
            f"{API}/clients", headers=headers, json={"name": f"Client {n}"},
        )).json()
        p = (await http.post(
            f"{API}/proposals",
            headers=headers,
            json={"client_id": c["id"], "project_name": project_name},
        )).json()
        return p

    return _make


@pytest_asyncio.fixture
async def seeded_templates(db) -> list[StrategyTemplate]:
    """Insert two deterministic system strategy templates.

    Used by template-listing and template-matcher tests so they don't depend on
    the optional ``web_app_seed/veeville-templates.json`` file being present.
    """
    templates = [
        StrategyTemplate(
            template_key="brand_identity",
            name="Brand Identity",
            description="Full brand identity and visual system",
            category="brand",
            config={
                "brief_intake": {
                    "auto_detect_signals": ["rebrand", "logo", "brand guidelines", "visual identity"]
                },
                "narrative": {"letter_strategy": "vision"},
                "cost_model": {"default_multipliers": []},
                "output": {"site_theme": "editorial"},
            },
            is_system=True,
            agency_id=None,
        ),
        StrategyTemplate(
            template_key="campaign",
            name="Campaign",
            description="Integrated marketing campaign",
            category="campaign",
            config={
                "brief_intake": {"auto_detect_signals": ["campaign", "launch", "advertising"]},
                "output": {"site_theme": "bold"},
            },
            is_system=True,
            agency_id=None,
        ),
    ]
    for t in templates:
        db.add(t)
    await db.commit()
    return templates


# ── Auth helpers ─────────────────────────────────────────────────────────────
@dataclass
class RegisteredUser:
    token: str
    user_id: str
    agency_id: str
    email: str
    headers: dict


async def _register(client: AsyncClient, *, email: str, agency_name: str) -> RegisteredUser:
    resp = await client.post(
        f"{API}/auth/register",
        json={
            "email": email,
            "password": "s3cret-password",
            "full_name": "Test Owner",
            "agency_name": agency_name,
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    return RegisteredUser(
        token=data["access_token"],
        user_id=data["user_id"],
        agency_id=data["agency_id"],
        email=email,
        headers={"Authorization": f"Bearer {data['access_token']}"},
    )


@pytest_asyncio.fixture
async def registered(client) -> RegisteredUser:
    """A registered user + agency (the "primary" agency in tests)."""
    return await _register(client, email="owner@acme.example.com", agency_name="Acme Agency")


@pytest_asyncio.fixture
async def second_agency(client) -> RegisteredUser:
    """A second, unrelated agency — used for cross-agency isolation tests."""
    return await _register(client, email="rival@globex.example.com", agency_name="Globex Inc")


# ── Session teardown ─────────────────────────────────────────────────────────
def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    try:
        os.unlink(_TMP_DB_PATH)
    except OSError:
        pass
