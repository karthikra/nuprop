# NUPROP — Complete Technical Documentation

## AI-Powered Proposal Copilot for Design & Professional Services Agencies

**Version**: 1.0 (M1-M21 Complete)
**Repo**: https://github.com/karthikra/nuprop
**Stack**: FastAPI (Python) + React 19 (TypeScript) + Claude Sonnet 4.6 + PostgreSQL

---

## Table of Contents

1. [What NUPROP Does](#1-what-nuprop-does)
2. [Architecture Overview](#2-architecture-overview)
3. [Getting Started](#3-getting-started)
4. [The Proposal Pipeline — Step by Step](#4-the-proposal-pipeline)
5. [API Reference](#5-api-reference)
6. [WebSocket Protocol](#6-websocket-protocol)
7. [AI Services Deep Dive](#7-ai-services)
8. [Interactive Proposal Sites — 5 Themes](#8-proposal-site-themes)
9. [Analytics & Engagement Scoring](#9-analytics)
10. [Notification Engine](#10-notifications)
11. [Client Context Engine](#11-context-engine)
12. [Context Intelligence Layer](#12-context-intelligence)
13. [Rate Card & Template Management](#13-rate-cards-templates)
14. [Preference Panel & Speculative Execution](#14-preferences)
15. [Frontend Architecture](#15-frontend)
16. [Database Schema](#16-database)
17. [Deployment](#17-deployment)

---

## 1. What NUPROP Does

NUPROP turns a client brief into a complete, defensible proposal through an AI-powered chat conversation. The user describes their client and project, and the system:

1. **Analyzes the brief** — asks clarifying questions, extracts structured data
2. **Selects a strategy template** — matches against 8 proposal types (brand, tech, campaign, retainer, etc.)
3. **Researches the client** — uses Claude's web search to find company info, leadership, recent news
4. **Benchmarks pricing** — searches for market rates per deliverable category
5. **Builds a cost model** — maps deliverables to the agency's rate card with market comparison
6. **Generates narrative** — covering letter (2 variants), executive summary, scope descriptions, cost rationale, terms
7. **Produces outputs** — DOCX, PDF, email drafts, and an interactive proposal website

Every step happens in a chat interface with real-time progress updates, and the user approves at 3 key gates before the AI proceeds.

---

## 2. Architecture Overview

### Monorepo Structure

```
nuprop/
├── backend/                     # FastAPI + MVVM
│   ├── app/
│   │   ├── core/                # Config, security, deps, WebSocket manager
│   │   ├── domain/schemas/      # Pydantic request/response models
│   │   ├── infrastructure/
│   │   │   ├── db/models/       # 13 SQLAlchemy ORM models
│   │   │   ├── db/repositories/ # Data access layer (BaseRepository pattern)
│   │   │   └── external/        # Anthropic, Gmail, Drive, Calendar, Slack clients
│   │   ├── services/            # Business logic
│   │   │   └── ai/             # 7 AI service classes
│   │   ├── viewmodels/          # MVVM orchestration (ViewModelBase pattern)
│   │   ├── views/v1/           # 15 FastAPI routers, 50+ endpoints
│   │   └── proposal_site_themes/ # 5 Jinja2 site templates
│   ├── alembic/                 # Database migrations
│   └── pyproject.toml           # uv-managed Python deps
├── frontend/                    # React 19 + TypeScript + Vite
│   └── src/
│       ├── api/                 # 10 TanStack Query hook files
│       ├── stores/              # 2 Zustand stores (auth, chat)
│       ├── components/          # 20+ React components
│       ├── pages/               # 15+ route-level pages
│       └── types/               # 7 TypeScript type files
├── Dockerfile                   # 3-stage build (Node → Python → Runtime)
├── docker-compose.yml           # PostgreSQL + app for local dev
└── fly.toml                     # Fly.io production config
```

### MVVM Pattern

Every feature follows this exact pattern (copied from the nuedit project):

```
Router (views/v1/) → ViewModel (viewmodels/) → Repository (db/repositories/) → ORM Model (db/models/)
         ↓                    ↓                         ↓
    Thin handler         Orchestration              Data access
    validates input      calls services             SQL queries
    returns response     composes results           CRUD operations
```

**ViewModelBase** (`viewmodels/shared/viewmodel.py`):
```python
class ViewModelBase:
    def __init__(self, request: Request, db: AsyncSession):
        self._request = request
        self._db = db
        self.status_code: int | None = None
        self.error: str | None = None
```

**Router dependency injection**:
```python
def get_vm(request: Request, db: AsyncSession = Depends(get_db)) -> SomeViewModel:
    return SomeViewModel(request, db)

@router.get("/")
async def list_things(vm: SomeViewModel = Depends(get_vm)):
    return await vm.list_things()
```

---

## 3. Getting Started

### Prerequisites

- Python 3.13+ with `uv`
- Node.js 22+ with `pnpm`
- Anthropic API key
- Docker (for PostgreSQL local dev)

### Development Setup (SQLite)

```bash
# Backend
cd backend
cp .env.example .env
# Edit .env: add ANTHROPIC_API_KEY
DYLD_LIBRARY_PATH=/opt/homebrew/lib uv run uvicorn app.main:app --reload
# → http://localhost:8000

# Frontend (separate terminal)
cd frontend
pnpm install
pnpm dev
# → http://localhost:5173 (proxies /api to backend)
```

### Docker Setup (PostgreSQL)

```bash
# Create .env.docker with your ANTHROPIC_API_KEY
docker compose up --build
# → http://localhost:8080 (full app: API + React SPA)
```

### First Use

1. Open `http://localhost:5173` (or `:8080` with Docker)
2. Click **Register** → enter name, agency name, email, password
3. Complete the **4-step onboarding wizard**:
   - Step 1: Agency profile (name, brand colours, fonts)
   - Step 2: Rate card (paste JSON or skip)
   - Step 3: Voice calibration (paste sample writing)
   - Step 4: Done
4. **Create a client** → name, industry, contacts
5. **New Proposal** → select client, name project → chat builder opens

---

## 4. The Proposal Pipeline

The pipeline is an 8-phase state machine stored in `proposal.pipeline_state`:

```
brief → template_confirm → research → cost_model_review →
narrative_generation → narrative_review → output_generation → complete
```

### Phase-by-Phase Walkthrough

#### Phase 1: Brief Intake

**What happens**: User describes the project in natural language. Claude asks clarifying questions one at a time (never dumps all questions). After 2-3 exchanges, produces a structured brief JSON.

**Code path**:
```
POST /api/v1/chat/{id}/send
  → chat_viewmodel.py: send_message()
    → _handle_brief_phase()
      → services/ai/brief_analyzer.py: BriefAnalyzer.analyze()
        → AnthropicClient.complete() (Claude Sonnet 4.6)
      → Returns: message_type="brief_summary" with extra_data.brief
```

**Example chat**:
```
User: "Tata Communications 25th anniversary. Need theme identity, 4 townhalls,
      video production, social media, merchandise. Warm pitch, ₹1.5Cr budget, year-long."

AI:   "Great — that's a comprehensive anniversary campaign. A few questions:
       1. Are the 3 themes already developed, or do you need us to create them?"

User: "Themes are already presented. Summarize the brief."

AI:   [Produces structured brief JSON with client, project, deliverables, context]
      → Shows approval gate: "Approve Brief" / "Adjust"
```

**Approval gate**: User clicks "Approve Brief" →
```
POST /api/v1/chat/{id}/approve/brief
  → chat_viewmodel.py: approve_gate("brief")
    → Advances to template_confirm
    → Auto-triggers _handle_template_confirm()
```

#### Phase 2: Template Selection

**What happens**: The system matches the brief against 8 strategy templates using keyword signals. Presents the best match for confirmation.

**Code path**:
```
approve_gate("brief")
  → _handle_template_confirm()
    → services/ai/template_matcher.py: TemplateMatcher.match()
      → Queries DB for all system templates
      → Matches brief text against auto_detect_signals
    → Returns: message_type="approval_gate" with template suggestion
```

**Templates available** (seeded from `veeville-templates.json`):
| Template | Category | Auto-detect signals |
|----------|----------|---------------------|
| Brand Identity / Rebrand | brand | rebrand, brand identity, visual refresh, logo |
| Website / Digital Platform | technology | website, redesign, app, platform |
| Anniversary / Milestone Campaign | campaign | anniversary, milestone, celebration, 25th |
| Creative Retainer | retainer | retainer, ongoing, monthly, continuous |
| Film & Video Production | film | video, film, corporate film, documentary |
| Employer Branding | brand | employer brand, EVP, internal communications |
| Experiential Learning | consulting | workshop, team building, experiential |
| Exhibition Design | spatial | exhibition, trade show, booth |

**Approval gate**: User confirms template →
```
POST /api/v1/chat/{id}/approve/template
  → approve_gate("template")
    → Saves template_id on proposal
    → Advances to research
    → Auto-triggers _run_research_and_benchmarks()
```

#### Phase 3: Research + Benchmarks

**What happens**: Two parallel operations:
1. **Client research** — Claude searches the web 5-10 times, synthesizes into a structured report
2. **Market benchmarks** — Claude searches for pricing data per deliverable category

**Code path**:
```
_run_research_and_benchmarks(proposal, proposal_id, template_config)
  → Loads client context brief from DB (if context exists)
  → WS broadcast: progress("research", "searching", "Researching Tata Communications...")

  → services/ai/research_agent.py: ResearchAgent.research_client()
    → AnthropicClient._client.messages.create() with web_search_20250305 tool
    → Claude runs 5-10 web searches autonomously
    → Returns: 6,000+ chars markdown with 7 sections
  → Saves research markdown to proposal

  → WS broadcast: progress("benchmarks", "searching", "Finding pricing benchmarks...")

  → services/ai/benchmark_agent.py: BenchmarkAgent.find_benchmarks()
    → Claude searches for market pricing per category
    → Returns: benchmark tables with Budget/Mid-tier/Premium ranges
  → Saves benchmarks to proposal

  → Auto-triggers _build_cost_model()
```

**Research output sections**:
1. Company Overview (revenue, employees, founding)
2. Leadership (CEO, key contacts, recent changes)
3. Recent Developments (last 6-12 months)
4. Industry Position (market share, competitors)
5. Brand & Digital Assessment
6. **Narrative Hooks** (specific facts for the covering letter)
7. Strategic Opportunities

**Example narrative hook found by research**:
> "AI-First Transformation": CEO Lakshminarayanan said "This acquisition marks a significant step in our journey to redefine customer experience in the AI era."

#### Phase 4: Cost Model

**What happens**: AI maps brief deliverables to rate card packages, applies multipliers, generates market comparison.

**Code path**:
```
_build_cost_model(proposal, proposal_id, template_config)
  → services/ai/cost_model_builder.py: CostModelBuilder.build()
    → Loads active RateCard from DB for agency
    → Flattens 15 offering categories into package index
    → AnthropicClient.complete_json() maps deliverables to packages
    → Applies multipliers (urgency_rush, annual_bundle, existing_client)
    → Calculates: subtotal, discount, total, GST (18%), grand total
    → _build_tiered() generates essential/standard/premium tiers (speculative execution)
  → Returns: message_type="cost_model" with interactive table in chat
```

**Cost model line item example**:
```json
{
  "deliverable": "Anniversary Theme Identity",
  "package_id": "bi_visual_identity_system",
  "package_name": "Complete visual identity system",
  "match_quality": "exact",
  "quantity": 1,
  "unit_cost": 350000,
  "total": 350000
}
```

**Inline editing**: User clicks any price or quantity in the chat table →
```
PATCH /api/v1/chat/{id}/cost-model
  → Validates line item index + field
  → Recalculates subtotal, discount, GST, grand total
  → WS broadcast: cost_model_update
```

#### Phase 5: Narrative Generation

**What happens**: Generates all proposal text in one pass with progress updates.

**Code path**:
```
approve_gate("cost_model")
  → _generate_narrative(proposal, proposal_id)
    → Loads Agency, StrategyTemplate config, RateCard
    → _merge_preferences_into_config() overlays user preferences

    → services/ai/narrative_generator.py: NarrativeGenerator.generate_all()
      → generate_covering_letters() — 2 variants via asyncio.gather
        → Primary: uses template's letter_strategy (e.g., "warm")
        → Alternative: uses contrast strategy (e.g., "confident")
      → generate_executive_summary() — 4 paragraphs, 300-400 words
      → generate_scope_sections() — per deliverable, batched 5 at a time
      → generate_cost_rationale() — only for proposals > ₹10L
      → generate_terms() — template substitution, no LLM

    → Returns: message_type="narrative_preview" with tabbed letter selector
```

**Letter rules** (enforced by system prompt):
- ALWAYS open with the client (first 2-3 paragraphs about them)
- Reference at least ONE specific researched fact
- End with specific CTA ("Would Thursday at 3pm work?")
- Sign off with first name only
- 400-600 words
- NEVER use: "leverage", "synergy", "best-in-class", "cutting-edge", "we look forward to hearing from you"

#### Phase 6: Output Generation

**What happens**: Generates all deliverable files.

**Code path**:
```
approve_gate("narrative")
  → _generate_outputs(proposal, proposal_id)
    → services/document_generator.py: DocumentGenerator.generate_all()
      → _generate_docx() — python-docx, 10-section Word document (~40KB)
      → _generate_pdf() — WeasyPrint renders styled HTML to PDF (~17KB)
      → _generate_email_drafts() — 2 variants (confident + warm)

    → services/site_generator.py: SiteGenerator.generate()
      → Selects theme from template config (editorial/bold/minimal/dark/warm)
      → Renders Jinja2 template with proposal data
      → Embeds analytics tracking script (sendBeacon)
      → Saves to outputs/{proposal_id}/site/index.html (~25KB)

    → Saves all files to OUTPUT_DIR/{proposal_id}/
    → Returns: message_type="output_ready" with download buttons + site preview
```

**Files generated per proposal**:
```
outputs/{proposal_id}/
├── proposal.docx          # 10-section Word document
├── proposal.pdf           # Styled PDF via WeasyPrint
├── proposal-print.html    # Print-ready HTML fallback
├── email-drafts.md        # 2 email variants (confident + warm)
└── site/
    └── index.html         # Interactive proposal site with analytics
```

---

## 5. API Reference

### Authentication
| Method | Path | Body | Response | Notes |
|--------|------|------|----------|-------|
| POST | `/api/v1/auth/register` | `{email, password, full_name, agency_name}` | TokenResponse | Creates agency + user |
| POST | `/api/v1/auth/login` | `{email, password}` | TokenResponse | Returns JWT |
| GET | `/api/v1/auth/me` | — | UserResponse | Requires Bearer token |

### Agencies
| Method | Path | Body | Response |
|--------|------|------|----------|
| GET | `/api/v1/agencies/me` | — | AgencyResponse |
| PATCH | `/api/v1/agencies/me` | AgencyUpdate | AgencyResponse |
| POST | `/api/v1/agencies/me/onboarding` | `{step: 1-4, data: {...}}` | AgencyResponse |

### Clients
| Method | Path | Body/Params | Response |
|--------|------|-------------|----------|
| GET | `/api/v1/clients?q=&industry=` | — | list[ClientResponse] |
| POST | `/api/v1/clients` | ClientCreate | ClientResponse |
| GET | `/api/v1/clients/{id}` | — | ClientResponse |
| PATCH | `/api/v1/clients/{id}` | ClientUpdate | ClientResponse |
| DELETE | `/api/v1/clients/{id}` | — | 204 |
| POST | `/api/v1/clients/{id}/context` | `{raw_text: "..."}` | ClientResponse |
| GET | `/api/v1/clients/{id}/context-brief?include_emails=true` | — | `{brief, has_context}` |
| GET | `/api/v1/clients/{id}/intelligence` | — | Quality score + overrides + timeline |

### Proposals
| Method | Path | Body | Response |
|--------|------|------|----------|
| GET | `/api/v1/proposals` | — | list[ProposalListItem] |
| POST | `/api/v1/proposals` | `{client_id, project_name}` | ProposalResponse |
| GET | `/api/v1/proposals/{id}` | — | ProposalResponse |
| PATCH | `/api/v1/proposals/{id}/preferences` | PreferencesUpdate | ProposalResponse |

### Chat
| Method | Path | Body | Response |
|--------|------|------|----------|
| GET | `/api/v1/chat/{id}/messages` | — | list[ChatMessageResponse] |
| POST | `/api/v1/chat/{id}/send` | `{content: "..."}` | list[ChatMessageResponse] |
| POST | `/api/v1/chat/{id}/approve/{gate}` | `{data: {...}}` | ChatMessageResponse |
| PATCH | `/api/v1/chat/{id}/cost-model` | `{index, field, value}` | Updated cost model |
| WS | `/api/v1/chat/{id}/ws?token=JWT` | — | WebSocket connection |

### Rate Cards
| Method | Path | Body | Response |
|--------|------|------|----------|
| GET | `/api/v1/rate-cards/active` | — | RateCardResponse |
| GET | `/api/v1/rate-cards` | — | list[RateCardSummary] |
| PATCH | `/api/v1/rate-cards/{id}` | `{offerings?: ..., hourly_rates?: ...}` | RateCardResponse |
| POST | `/api/v1/rate-cards` | `{version: "2026-Q3"}` | RateCardResponse |

### Templates
| Method | Path | Body | Response |
|--------|------|------|----------|
| GET | `/api/v1/templates` | — | list[TemplateResponse] |
| POST | `/api/v1/templates/{id}/clone` | `{new_key, new_name}` | TemplateResponse |
| PATCH | `/api/v1/templates/{id}` | TemplateUpdate | TemplateResponse (custom only) |

### Connectors
| Method | Path | Response |
|--------|------|----------|
| GET | `/api/v1/connectors/gmail/auth-url` | `{auth_url}` |
| POST | `/api/v1/connectors/gmail/callback` | GmailStatusResponse |
| GET | `/api/v1/connectors/gmail/status` | GmailStatusResponse |
| POST | `/api/v1/connectors/gmail/sync` | GmailSyncResponse |
| POST | `/api/v1/connectors/drive/sync` | `{clients_synced, documents_found}` |
| POST | `/api/v1/connectors/calendar/sync` | `{clients_synced, meetings_found}` |
| POST | `/api/v1/connectors/slack/sync` | `{clients_synced, mentions_found}` |

### Analytics
| Method | Path | Response |
|--------|------|----------|
| GET | `/api/v1/analytics/overview` | OverviewStatsResponse |
| GET | `/api/v1/analytics/proposals/{id}` | ProposalAnalyticsResponse |
| POST | `/api/v1/track` | 204 (beacon from proposal sites) |

### Notifications
| Method | Path | Response |
|--------|------|----------|
| GET | `/api/v1/notifications` | `{items, total, unread_count}` |
| GET | `/api/v1/notifications/unread-count` | `{count}` |
| PATCH | `/api/v1/notifications/{id}/read` | NotificationResponse |

### Public (No Auth)
| Method | Path | Response |
|--------|------|----------|
| GET | `/p/{proposal_id}` | Interactive proposal site HTML |
| GET | `/api/v1/health` | `{"status": "ok"}` |

---

## 6. WebSocket Protocol

**Endpoint**: `WS /api/v1/chat/{proposal_id}/ws?token=JWT`

### Client → Server
```json
{"type": "ping"}
```

### Server → Client

| Type | When | Payload |
|------|------|---------|
| `new_message` | New chat message | `{message: ChatMessage}` |
| `typing` | AI processing starts/stops | `{typing: true/false}` |
| `progress` | Long-running task update | `{agent: "research", status: "searching", detail: "..."}` |
| `phase_change` | Pipeline advances | `{phase: "cost_model_review"}` |
| `cost_model_update` | Line item edited | `{cost_model: {...}}` |
| `pong` | Response to ping | `{}` |

**Message types** in `new_message`:
- `text` — regular chat message
- `brief_summary` — structured brief with approval gate
- `approval_gate` — template confirmation gate
- `research_findings` — research + benchmarks report
- `cost_model` — interactive cost table with approval
- `narrative_preview` — tabbed letter variants + scope sections
- `output_ready` — download buttons + site preview link

---

## 7. AI Services

### Service Architecture

All AI services live in `backend/app/services/ai/` and use the shared `AnthropicClient`:

```python
# infrastructure/external/anthropic_client.py
class AnthropicClient:
    async def complete(system, messages, model, max_tokens, temperature) → str
    async def complete_json(system, messages, model, max_tokens) → dict
    async def stream(system, messages, model, max_tokens, temperature) → AsyncGenerator[str]
```

### Research Agent

**File**: `services/ai/research_agent.py`
**Model**: Claude Sonnet 4.6 + `web_search_20250305` tool
**Searches**: Up to 10 web searches per client

The research agent uses Claude's native web search — Claude decides what to search, reads full pages, and synthesizes. No Serper API needed.

```python
# Usage in chat_viewmodel.py
agent = ResearchAgent()
research_md = await agent.research_client(
    client_name="Tata Communications",
    industry="Telecom",
    template_queries=["client history milestones", ...],  # from template
    context_brief="Past work: poster ₹2.4L, video ₹8L rejected...",  # from context engine
    max_searches=10,
)
```

**Output sections**: Company Overview, Leadership, Recent Developments, Industry Position, Brand Assessment, **Narrative Hooks** (the key differentiator), Strategic Opportunities, Sources.

### Cost Model Builder

**File**: `services/ai/cost_model_builder.py`
**Model**: Claude Sonnet 4.6 (for deliverable-to-package mapping)

The cost model builder:
1. Loads the agency's active rate card (15 offering categories, 60+ packages)
2. Uses Claude to semantically match brief deliverables to packages
3. Falls back to keyword matching if AI unavailable
4. Applies multipliers from template config
5. **Speculatively generates tiered pricing** alongside flat (stored in `cost_model.tiered`)

```python
# Match quality levels
"exact"   — direct description match (e.g., "brand guidelines" → brand_guidelines package)
"close"   — partial match (e.g., "visual identity" → visual_identity_system)
"hourly"  — no package match, estimated from hourly rates × hours
```

### Narrative Generator

**File**: `services/ai/narrative_generator.py`
**Model**: Claude Sonnet 4.6
**Temperature**: 0.8 for letters (creative), 0.5 summary, 0.4 scope, 0.3 rationale

Generates 2 letter variants in parallel via `asyncio.gather`, scope sections batched 5 at a time.

**5 Letter Strategies**:
| Strategy | Contrast | Description |
|----------|----------|-------------|
| confident | warm | Bold, direct, assumes the win |
| warm | confident | Empathetic, relationship-focused |
| research_heavy | relationship_builder | Data-driven, opens with findings |
| technical_showcase | warm | Process-led, demonstrates expertise |
| relationship_builder | research_heavy | Partnership-focused, long-term value |

---

## 8. Proposal Site Themes

Each generated proposal site is a self-contained HTML file (~25KB) with inline CSS, scroll animations, interactive scope cards, and analytics tracking.

### 5 Themes

| Theme | Background | Headings | Feel |
|-------|-----------|----------|------|
| **editorial** | #FAF8F5 (warm cream) | DM Serif Display | Magazine article |
| **bold** | #1A1A1A (dark) | DM Sans bold | High contrast statement |
| **minimal** | #FFFFFF (white) | DM Sans medium | Clean, understated |
| **dark** | #0F0F0F (near-black) | DM Serif Display | Luxury/premium |
| **warm** | #FEFCE8 (soft cream) | DM Sans semibold | Friendly, approachable |

### Site Sections

Every theme includes these sections with `data-section` attributes for analytics:

1. **Cover** — agency name, project title, "Prepared for [client]", confidential badge
2. **Covering Letter** — full editorial text, max-width 640px, line-height 1.9
3. **Executive Summary** — (if present)
4. **Scope Cards** — 2-col grid, click to expand. Each card: deliverable name, price tag, full scope on expand
5. **Investment Summary** — cost table with subtotals, discount, GST, grand total
6. **Timeline** — horizontal phases (vertical on mobile)
7. **CTA** — "Schedule a Call" + "Download PDF" buttons

### Tracking Script

Embedded in every generated site via the `_base.html` Jinja2 macro:

```javascript
// Sends beacons to POST /api/v1/track every 5 seconds
// Events tracked:
// - page_view (referrer, viewport)
// - scroll_depth (25%, 50%, 75%, 100%)
// - section_enter / section_exit (with duration in seconds)
// - card_expand / card_collapse
// - cta_click (schedule, download)
```

---

## 9. Analytics & Engagement Scoring

### 8-Factor Scoring (0-100)

| Factor | Max Points | Scoring Logic |
|--------|-----------|---------------|
| Opened within 24h | 10 | first_seen - sent_at < 24 hours |
| Time on site | 20 | <1m=0, 1-3m=8, 3-5m=14, >5m=20 |
| Sections viewed | 15 | % of total sections: <50%=3, 50-75%=8, >75%=15 |
| Cards expanded | 15 | count: 0=0, 1-2=5, 3-5=10, ≥5=15 |
| Investment section time | 10 | <30s=0, 30s-2m=5, >2m=10 |
| PDF downloaded | 5 | CTA click with "download" |
| Return visits | 15 | 0=0, 1=8, ≥2=15 |
| CTA clicked | 10 | any CTA click event |

### Classifications

| Score | Level | Meaning |
|-------|-------|---------|
| 81-100 | Ready | Multiple stakeholders engaged, CTA clicked |
| 61-80 | Hot | Strong interest, preparing to decide |
| 41-60 | Warm | Actively reviewing, comparing options |
| 21-40 | Cool | Glanced but not engaged |
| 0-20 | Cold | Hasn't viewed or minimal engagement |

### Analytics Dashboard

- **Overview page** (`/analytics`): stat cards + proposals table sorted by engagement score
- **Detail page** (`/analytics/{id}`): score breakdown bars, section time heatmap, visitor table

---

## 10. Notification Engine

### 6 Notification Rules

Evaluated on every analytics beacon received at `POST /api/v1/track`:

| Rule | Urgency | Trigger |
|------|---------|---------|
| First view | normal | page_view + session_count == 1 |
| Return visit | normal | page_view + session_count > 1 |
| PDF download | normal | cta_click with "download" |
| CTA click | **high** | any cta_click (non-download) |
| High engagement | **high** | score crosses 60 threshold |
| New visitor | normal | first visit + other visitors exist (forwarded) |

### Delivery

- **In-app**: notification bell in nav with unread count badge (30s polling)
- **Dropdown**: last 10 notifications with alert-type icons, relative timestamps, click to navigate
- **Email**: via Resend (when configured) — fire-and-forget

---

## 11. Client Context Engine

### Data Sources (4 connectors + manual)

| Source | Auth | What it captures |
|--------|------|------------------|
| **Manual paste** | None | Emails, notes, meeting summaries pasted into chat |
| **Gmail** | Google OAuth | Email threads with client domains, classified by Haiku |
| **Google Drive** | Same Google OAuth | Past proposals, meeting notes, contracts |
| **Google Calendar** | Same Google OAuth | Meeting frequency, attendees, relationship depth |
| **Slack** | Slack OAuth | Internal discussions, shared channel messages |

### Context Profile Structure

```json
{
  "relationship": {
    "status": "existing_client",
    "primary_contact": {"name": "Priya Sharma", "role": "Head IC"},
    "other_contacts": [{"name": "Rahul Menon", "role": "VP Corp Affairs"}],
    "decision_chain": "Priya shortlists → Rahul approves above ₹10L",
    "meeting_frequency": "monthly",
    "meeting_count": 8
  },
  "past_work": [
    {"project": "Poster Series", "value": 240000, "status": "completed", "feedback": "loved speed, revision delays"},
    {"project": "Video Proposal", "value": 800000, "status": "proposal_rejected", "feedback": "too expensive"}
  ],
  "pricing_intelligence": {
    "price_sensitivity": "high",
    "past_accepted_range": "₹2.4L",
    "past_rejected_range": "₹8L",
    "negotiation_style": "always asks for 10-15% discount"
  },
  "preferences": {
    "communication": "email-first, shares PDFs internally",
    "creative": "clean corporate, not experimental"
  },
  "opportunities": [{"signal": "wants to consolidate creative with one agency"}],
  "risks": [{"signal": "budget constraints this quarter"}]
}
```

### How Context Flows Into the Pipeline

1. **Research**: context brief tells Claude to skip known facts, focus on gaps
2. **Cost Model**: avoids rejected price points, applies negotiation buffer
3. **Narrative**: letter references shared history, warm tone for deep relationships
4. **Output**: PDF-first if client prefers, one-pager generated for finance approver

---

## 12. Context Intelligence Layer

### Quality Score (0-100)

| Factor | Max | What it measures |
|--------|-----|------------------|
| Recency | 25 | Any interaction in last 30 days |
| Volume | 20 | Total interactions across all sources (>10 = full points) |
| Depth | 20 | Pricing data available (budget signals, accepted/rejected ranges) |
| Breadth | 15 | Multiple data sources (Gmail + Drive + Calendar = 15) |
| Past work | 10 | Completed projects exist |
| Decision chain | 10 | Decision-making process known |

### Auto-Applied Preference Overrides

When creating a new proposal for a client with context, these are auto-applied:

| Signal | Override | Reason |
|--------|----------|--------|
| Past price rejection | `pricing_model → tiered` | Gives budget options |
| High sensitivity | `negotiation_buffer → 12%` | Build in room for negotiation |
| Deep relationship | `letter_strategy → warm` | Reference shared history |
| Client prefers PDFs | `primary_format → docx_first` | Match their workflow |
| Revision complaints | Scope note: 48hr turnaround | Show we learned |
| Finance approver | Generate one-pager | For CFO/VP review |

### Sentiment Timeline

Chronological view of relationship health on the client detail page:
- Green dots: positive events (project delivered, praised)
- Red dots: negative events (price rejection, revision delays)
- Amber: neutral (scheduling, admin)

---

## 13. Rate Card & Template Management

### Rate Card

The rate card is the pricing backbone. Structure:
- **15 offering categories** (Brand Identity, Communication Design, Digital, Film, etc.)
- **60+ packages** per category with base price, description, includes, typical hours
- **14 hourly rates** (Project Director ₹8K, Creative Director ₹6K, Designer ₹3K, etc.)
- **10 multipliers** (urgency_rush 1.5x, annual_bundle 0.88x, etc.)

**Rate card editor** (`/rate-card`): 3 tabs (Packages, Hourly Rates, Multipliers), inline editing via click-to-edit cells, version management (clone active → new version).

### Strategy Templates

Templates encode *strategy*, not layout. Each template changes:
- Which questions the AI asks during brief intake
- Which web searches it runs for research
- How it frames pricing (bundled_value, investment_roi, market_rate)
- The covering letter tone (warm, confident, technical_showcase)
- The proposal site theme (editorial, bold, minimal)

**8 system templates** are seeded on startup. Users can clone and customize.

---

## 14. Preference Panel & Speculative Execution

### Preference Panel

Collapsible right sidebar in the chat builder with controls:
- **Letter**: tone, opening, length, custom instructions
- **Pricing**: model (flat/tiered), payment terms
- **Scope**: detail level (brief/standard/detailed/exhaustive)
- **Output**: site theme

Each field shows "template" (gray) or "custom" (blue) provenance. Changes trigger `PATCH /proposals/{id}/preferences` with 300ms debounce.

### Staleness Tracking

When a preference changes after a phase is complete, that phase is marked stale:
```
letter_strategy changed → narrative_review marked stale (amber dot in sidebar)
pricing_model changed → cost_model_review marked stale
site_theme changed → output_generation marked stale
```

### Speculative Execution

The CostModelBuilder always generates both flat and tiered pricing in `cost_model.tiered`. Switching from flat to tiered reads from pre-computed data — no re-generation needed.

---

## 15. Frontend Architecture

### State Management

**Zustand** for cross-cutting state:
- `auth-store`: token, user, agency, login/logout/initialize
- `chat-store`: messages, pipelinePhase, isConnected, isTyping, progress

**TanStack Query** for server state:
- 10 API hook files with `useQuery` for reads, `useMutation` for writes
- Auto-invalidation on mutations
- 30s polling for notification unread count

### Key Components

| Component | Path | What it renders |
|-----------|------|-----------------|
| `AppShell` | `layout/app-shell.tsx` | Nav + sidebar + content area |
| `ChatContainer` | `chat/chat-container.tsx` | Message list + input + context check |
| `MessageBubble` | `chat/message-bubble.tsx` | Routes to 7 specialized message cards |
| `ApprovalGate` | `chat/approval-gate.tsx` | Brief/template approval cards |
| `CostModelCard` | `chat/cost-model-card.tsx` | Interactive cost table with inline edit |
| `NarrativePreview` | `chat/narrative-preview.tsx` | Tabbed letter variants + collapsible sections |
| `OutputReadyCard` | `chat/output-ready-card.tsx` | Download buttons + site preview |
| `PreferencePanel` | `chat/preference-panel.tsx` | Right sidebar with preference controls |
| `PipelineSidebar` | `chat/pipeline-sidebar.tsx` | Phase progress with staleness indicators |

---

## 16. Database Schema

### 13 Tables

| Table | Key Fields | Relations |
|-------|-----------|-----------|
| agencies | name, slug, colours, fonts, voice_profile, settings | → clients, proposals, rate_cards, templates, notifications |
| users | email, hashed_password, full_name, is_owner | → agency |
| clients | name, industry, contacts (JSON), context_profile (JSON) | → agency, proposals |
| proposals | project_name, status, brief (JSON), preferences (JSON), pipeline_state (JSON), cost_model (JSON), covering_letter, scope_sections (JSON) | → agency, client, messages, visitors |
| chat_messages | role, message_type, content, extra_data (JSON), phase | → proposal |
| rate_cards | version, is_active, offerings (JSON), hourly_rates (JSON), multipliers (JSON) | → agency |
| strategy_templates | template_key, name, category, config (JSON), is_system | → agency (null=system) |
| visitors | fingerprint, session_count, total_time_seconds, engagement_score, classification | → proposal |
| analytics_events | event_type, section_id, card_id, data (JSON), timestamp | → proposal, visitor |
| feedback | visitor_fingerprint, rating, note | → proposal |
| notifications | alert_type, message, urgency, sent_at, read_at | → proposal, agency |
| email_index | gmail_message_id, client_domain, message_type, sentiment, summary, entities (JSON) | → agency |

---

## 17. Deployment

### Local with Docker Compose

```bash
# 1. Create .env.docker
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env.docker

# 2. Start PostgreSQL + app
docker compose up --build
# → http://localhost:8080

# What happens:
# - PostgreSQL 16 starts with health check
# - Alembic creates all 12 tables
# - Templates seeded (8 system templates)
# - FastAPI serves API + React SPA + proposal sites
```

### Production on Fly.io

```bash
# 1. Create app + volume
fly apps create nuprop
fly volumes create nuprop_data --region bom --size 1

# 2. Set secrets
fly secrets set \
  DATABASE_URL="postgresql+asyncpg://user:pass@db.supabase.co:5432/postgres" \
  ANTHROPIC_API_KEY="sk-ant-..." \
  JWT_SECRET_KEY="$(openssl rand -hex 32)" \
  CORS_ORIGINS='["https://nuprop.fly.dev"]'

# 3. Deploy
fly deploy
# → https://nuprop.fly.dev

# What happens:
# - 3-stage Docker build (Node → Python → Runtime with WeasyPrint)
# - Alembic migration runs as release command (before traffic switch)
# - Templates seeded on first startup
# - Persistent volume at /data for generated files
# - Health check at /api/v1/health every 30s
# - Auto-suspend when idle, resume on request
```

### CI/CD

GitHub Actions (`.github/workflows/deploy.yml`):
```yaml
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: superfly/flyctl-actions/setup-flyctl@master
      - run: flyctl deploy --remote-only
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
```

---

## Summary

NUPROP is a complete AI-powered proposal platform with:
- **8-phase conversational pipeline** from brief to interactive website
- **7 AI services** (brief analysis, research, benchmarks, cost model, narrative, email classification, context extraction)
- **5 output formats** (DOCX, PDF, HTML, email drafts, interactive site)
- **5 proposal site themes** (editorial, bold, minimal, dark, warm)
- **4 data connectors** (Gmail, Drive, Calendar, Slack)
- **8-factor engagement scoring** with 6 notification rules
- **Context intelligence** with quality scoring and auto-preference overrides

Built with: FastAPI MVVM + React 19 + Claude Sonnet 4.6 + PostgreSQL + WebSocket + WeasyPrint + Jinja2

**21 milestones, 13 commits, 200+ files, 25K+ lines of code.**
