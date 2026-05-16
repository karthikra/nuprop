# S2 — Manual Context UI on Client Detail page — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the manual-context paste flow on the Client Detail page so M16 is end-to-end usable: an agency owner can paste raw text (emails, notes), preview the LLM extraction, commit it, and see the natural-language brief that proposals will receive — all without starting a proposal first.

**Architecture:** Two new thin backend endpoints split the existing extract-and-save into a preview-then-commit flow (`POST /context/preview` extracts only; `POST /context/save` merges a pre-extracted profile). On the frontend, extract the existing `ContextProfileCard` from `detail.tsx`, add an inline `<AddContextSection>` state machine (collapsed → textarea → preview → save), an on-demand `<ContextBriefToggle>` that calls the existing `GET /context-brief`, and a "Reset context" destructive button. Four new TanStack hooks in `api/clients.ts`. No new HTTP verbs invented beyond the two preview/save routes — reset reuses the existing `PATCH /clients/{id}`.

**Tech Stack:** FastAPI + async SQLAlchemy + Pydantic v2 + pytest + httpx ASGI (backend); React 19 + TypeScript + Vite + Tailwind + TanStack Query + Vitest + RTL + MSW (frontend).

**Spec:** `docs/superpowers/specs/2026-05-16-s2-context-ui-design.md` (commit `7f8da94`)

**Audit context:** `docs/superpowers/audits/2026-05-16-m16-m20-state-audit.md`

**Baseline (before S2):** 289 backend pytest passing, 131 frontend vitest passing across 24 files. After S2: ≥291 backend (+2), ≥139 frontend (+8) across 27 files (+3).

---

## File Structure

**New backend files:**

- `backend/tests/integration/test_clients_context_preview.py` — preview returns extracted structure without persisting
- `backend/tests/integration/test_clients_context_save.py` — save merges a structure into existing context_profile

**Modified backend files:**

- `backend/app/domain/schemas/client_schemas.py` — add `ContextPreviewResponse`, `ContextSaveRequest`
- `backend/app/views/v1/clients.py` — add `POST /clients/{client_id}/context/preview` and `POST /clients/{client_id}/context/save`

**New frontend files:**

- `frontend/src/components/clients/context-profile-card.tsx` — extracted from `detail.tsx`, gains brief-toggle slot + reset button
- `frontend/src/components/clients/context-brief-toggle.tsx` — on-demand `GET /context-brief` fetch + render
- `frontend/src/components/clients/add-context-section.tsx` — inline state machine: collapsed → textarea → preview → save
- `frontend/src/components/clients/__tests__/context-profile-card.test.tsx` — renders profile + reset confirm + brief toggle
- `frontend/src/components/clients/__tests__/context-brief-toggle.test.tsx` — closed = no fetch, opened = one fetch, cached
- `frontend/src/components/clients/__tests__/add-context-section.test.tsx` — paste→preview→save (happy), edit-and-re-preview, error paths

**Modified frontend files:**

- `frontend/src/api/clients.ts` — add `useContextPreview`, `useContextSave`, `useContextBrief`, `useResetContext`
- `frontend/src/pages/clients/detail.tsx` — slim down: remove inline `ContextProfileCard` function (now imported), add `<AddContextSection />` between Contacts and Context cards

**Total:** 6 new files + 4 modified files (2 backend, 2 frontend). No deletions.

---

## Task 1: Backend — add preview/save Pydantic schemas

**Files:**
- Modify: `backend/app/domain/schemas/client_schemas.py`

- [ ] **Step 1: Add the two new schemas**

Open `backend/app/domain/schemas/client_schemas.py`. Append after the existing `ClientResponse` class:

```python


class ContextPreviewRequest(BaseModel):
    raw_text: str


class ContextPreviewResponse(BaseModel):
    """The extracted context structure, NOT yet persisted. The client is
    expected to roundtrip this back via /context/save to commit it."""

    extracted: dict


class ContextSaveRequest(BaseModel):
    """A previously-previewed profile, ready to merge into the client's
    existing context_profile. The server does NOT re-extract from raw_text."""

    profile: dict
```

- [ ] **Step 2: Verify the module imports**

Run: `cd backend && .venv/bin/python -c "from app.domain.schemas.client_schemas import ContextPreviewRequest, ContextPreviewResponse, ContextSaveRequest; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/domain/schemas/client_schemas.py
git commit -m "feat(S2): add context preview/save schemas"
```

---

## Task 2: Backend — `POST /clients/{id}/context/preview` endpoint

**Files:**
- Create: `backend/tests/integration/test_clients_context_preview.py`
- Modify: `backend/app/views/v1/clients.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_clients_context_preview.py`:

```python
"""S2: POST /clients/{id}/context/preview must return the extracted structure
without persisting it. Distinct from POST /context which does both."""

from __future__ import annotations

from app.core.deps import get_context_service
from app.main import app
from tests.conftest import API


class _FakeCtx:
    def __init__(self):
        self.extract_calls: list[str] = []

    async def extract_context(self, raw_text: str) -> dict:
        self.extract_calls.append(raw_text)
        return {"relationship": {"status": "warm_intro", "primary_contact": {"name": "Priya"}}}

    # merge_context must NOT be called for preview
    async def merge_context(self, existing: dict, new: dict) -> dict:
        raise AssertionError("merge_context should not run during preview")


async def _make_client(http, headers, name: str = "Acme Co") -> str:
    resp = await http.post(f"{API}/clients", headers=headers, json={"name": name})
    return resp.json()["id"]


async def test_preview_returns_extracted_structure(client, registered):
    fake = _FakeCtx()
    app.dependency_overrides[get_context_service] = lambda: fake
    try:
        client_id = await _make_client(client, registered.headers)
        resp = await client.post(
            f"{API}/clients/{client_id}/context/preview",
            headers=registered.headers,
            json={"raw_text": "Met Priya from Acme last week, warm intro from Suresh."},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "extracted" in body
        assert body["extracted"]["relationship"]["status"] == "warm_intro"
        assert fake.extract_calls == ["Met Priya from Acme last week, warm intro from Suresh."]
    finally:
        app.dependency_overrides.pop(get_context_service, None)


async def test_preview_does_not_persist(client, registered):
    fake = _FakeCtx()
    app.dependency_overrides[get_context_service] = lambda: fake
    try:
        client_id = await _make_client(client, registered.headers)
        await client.post(
            f"{API}/clients/{client_id}/context/preview",
            headers=registered.headers,
            json={"raw_text": "anything"},
        )
        # GET the client and confirm context_profile is still empty
        get_resp = await client.get(f"{API}/clients/{client_id}", headers=registered.headers)
        assert get_resp.json()["context_profile"] == {}
    finally:
        app.dependency_overrides.pop(get_context_service, None)


async def test_preview_404_for_unknown_client(client, registered):
    fake = _FakeCtx()
    app.dependency_overrides[get_context_service] = lambda: fake
    try:
        resp = await client.post(
            f"{API}/clients/00000000-0000-0000-0000-000000000000/context/preview",
            headers=registered.headers,
            json={"raw_text": "anything"},
        )
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_context_service, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_clients_context_preview.py -v`
Expected: FAIL with 404s or `route not found` — the endpoint doesn't exist yet.

- [ ] **Step 3: Add the route handler to `clients.py`**

Open `backend/app/views/v1/clients.py`. After the existing `add_context` route handler (the one that handles `POST /clients/{client_id}/context`), insert the new endpoint:

```python


@router.post("/{client_id}/context/preview", response_model=ContextPreviewResponse)
async def preview_context(
    client_id: UUID,
    body: ContextPreviewRequest,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ClientViewModel = Depends(get_vm),
    ctx: ContextService = Depends(get_context_service),
):
    """Extract a structured context profile from raw text WITHOUT persisting.
    The client is expected to roundtrip the result via /context/save to commit."""
    client = await vm.get_client(client_id, agency_id)
    if not client:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)

    extracted = await ctx.extract_context(body.raw_text)
    return ContextPreviewResponse(extracted=extracted)
```

Update the imports at the top of `clients.py` to include the new schemas:

Find:
```python
from app.domain.schemas.client_schemas import ClientCreate, ClientResponse, ClientUpdate
```

Replace with:
```python
from app.domain.schemas.client_schemas import (
    ClientCreate,
    ClientResponse,
    ClientUpdate,
    ContextPreviewRequest,
    ContextPreviewResponse,
    ContextSaveRequest,
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_clients_context_preview.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/views/v1/clients.py backend/tests/integration/test_clients_context_preview.py
git commit -m "feat(S2): POST /clients/{id}/context/preview — extract without persist"
```

---

## Task 3: Backend — `POST /clients/{id}/context/save` endpoint

**Files:**
- Create: `backend/tests/integration/test_clients_context_save.py`
- Modify: `backend/app/views/v1/clients.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_clients_context_save.py`:

```python
"""S2: POST /clients/{id}/context/save must merge a pre-extracted profile
into the client's existing context_profile, without re-calling the LLM."""

from __future__ import annotations

from app.core.deps import get_context_service
from app.main import app
from tests.conftest import API


class _FakeCtx:
    def __init__(self):
        self.merge_calls: list[tuple[dict, dict]] = []

    # extract_context must NOT be called for save
    async def extract_context(self, raw_text: str) -> dict:
        raise AssertionError("extract_context should not run during save")

    async def merge_context(self, existing: dict, new: dict) -> dict:
        self.merge_calls.append((existing, new))
        # Simple union for the test
        return {**existing, **new}


async def _make_client(http, headers, name: str = "Acme Co") -> str:
    resp = await http.post(f"{API}/clients", headers=headers, json={"name": name})
    return resp.json()["id"]


async def test_save_merges_profile_into_client(client, registered):
    fake = _FakeCtx()
    app.dependency_overrides[get_context_service] = lambda: fake
    try:
        client_id = await _make_client(client, registered.headers)
        # Initial context — set via the existing PATCH so we test the merge path
        await client.patch(
            f"{API}/clients/{client_id}",
            headers=registered.headers,
            json={"context_profile": {"existing_key": "old"}},
        )
        # Save a new structure
        resp = await client.post(
            f"{API}/clients/{client_id}/context/save",
            headers=registered.headers,
            json={"profile": {"relationship": {"status": "warm_intro"}}},
        )
        assert resp.status_code == 200, resp.text

        # Confirm merge_context was called with (existing, new)
        assert len(fake.merge_calls) == 1
        existing, new = fake.merge_calls[0]
        assert existing == {"existing_key": "old"}
        assert new == {"relationship": {"status": "warm_intro"}}

        # GET the client and confirm context_profile is the merged result
        get_resp = await client.get(f"{API}/clients/{client_id}", headers=registered.headers)
        merged = get_resp.json()["context_profile"]
        assert merged == {"existing_key": "old", "relationship": {"status": "warm_intro"}}
    finally:
        app.dependency_overrides.pop(get_context_service, None)


async def test_save_returns_updated_client_response(client, registered):
    fake = _FakeCtx()
    app.dependency_overrides[get_context_service] = lambda: fake
    try:
        client_id = await _make_client(client, registered.headers, name="Beta Inc")
        resp = await client.post(
            f"{API}/clients/{client_id}/context/save",
            headers=registered.headers,
            json={"profile": {"relationship": {"status": "existing_client"}}},
        )
        assert resp.status_code == 200
        body = resp.json()
        # The endpoint returns the full ClientResponse, like add_context does
        assert body["id"] == client_id
        assert body["name"] == "Beta Inc"
        assert body["context_profile"]["relationship"]["status"] == "existing_client"
    finally:
        app.dependency_overrides.pop(get_context_service, None)


async def test_save_404_for_unknown_client(client, registered):
    fake = _FakeCtx()
    app.dependency_overrides[get_context_service] = lambda: fake
    try:
        resp = await client.post(
            f"{API}/clients/00000000-0000-0000-0000-000000000000/context/save",
            headers=registered.headers,
            json={"profile": {"x": "y"}},
        )
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_context_service, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_clients_context_save.py -v`
Expected: FAIL — the endpoint doesn't exist yet.

- [ ] **Step 3: Add the route handler to `clients.py`**

Open `backend/app/views/v1/clients.py`. Insert the new endpoint immediately after the `preview_context` handler from Task 2:

```python


@router.post("/{client_id}/context/save", response_model=ClientResponse)
async def save_context(
    client_id: UUID,
    body: ContextSaveRequest,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ClientViewModel = Depends(get_vm),
    ctx: ContextService = Depends(get_context_service),
):
    """Merge a previously-previewed context profile into the client's existing
    context_profile. No LLM call — the structure was already extracted via
    /context/preview."""
    client = await vm.get_client(client_id, agency_id)
    if not client:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)

    existing = client.context_profile or {}
    merged = await ctx.merge_context(existing, body.profile)

    updated = await vm.update_client(client_id, agency_id, ClientUpdate(context_profile=merged))  # type: ignore
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update context")
    return updated
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_clients_context_save.py -v`
Expected: 3 passed.

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: 289 + 3 (Task 2) + 3 (Task 3) = 295 passing.

- [ ] **Step 6: Commit**

```bash
git add backend/app/views/v1/clients.py backend/tests/integration/test_clients_context_save.py
git commit -m "feat(S2): POST /clients/{id}/context/save — merge pre-extracted profile"
```

---

## Task 4: Frontend — add the four TanStack hooks to `api/clients.ts`

**Files:**
- Modify: `frontend/src/api/clients.ts`

- [ ] **Step 1: Add the new hooks**

Open `frontend/src/api/clients.ts`. Append after the existing `useDeleteClient` function (currently ends around line 57):

```typescript


// ── S2: Manual context UI hooks ──────────────────────────────────────────

export interface ContextPreview {
  extracted: Record<string, unknown>
}

export interface ContextBrief {
  brief: string
  has_context: boolean
  email_count: number
}

/** Extract a context structure from raw text WITHOUT persisting. The result
 *  is roundtripped to useContextSave to commit. */
export function useContextPreview(clientId: string) {
  return useMutation({
    mutationFn: async (rawText: string) => {
      const { data } = await api.post<ContextPreview>(
        `/clients/${clientId}/context/preview`,
        { raw_text: rawText },
      )
      return data
    },
  })
}

/** Merge a previously-previewed profile into the client's existing
 *  context_profile. Invalidates the client + brief + intelligence queries. */
export function useContextSave(clientId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (profile: Record<string, unknown>) => {
      const { data } = await api.post<Client>(
        `/clients/${clientId}/context/save`,
        { profile },
      )
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['clients'] })
      qc.invalidateQueries({ queryKey: ['client-intelligence', clientId] })
      qc.invalidateQueries({ queryKey: ['client-context-brief', clientId] })
    },
  })
}

/** Reset the entire context_profile to {} via PATCH /clients/{id}. */
export function useResetContext(clientId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.patch<Client>(`/clients/${clientId}`, {
        context_profile: {},
      })
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['clients'] })
      qc.invalidateQueries({ queryKey: ['client-intelligence', clientId] })
      qc.invalidateQueries({ queryKey: ['client-context-brief', clientId] })
    },
  })
}

/** On-demand fetch of the natural-language context brief. Caller passes
 *  `enabled` so the query only runs when the toggle is open. */
export function useContextBrief(clientId: string, enabled: boolean) {
  return useQuery({
    queryKey: ['client-context-brief', clientId],
    queryFn: async () => {
      const { data } = await api.get<ContextBrief>(
        `/clients/${clientId}/context-brief`,
      )
      return data
    },
    enabled: !!clientId && enabled,
  })
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && pnpm tsc --noEmit 2>&1 | tail -10`
Expected: no errors.

- [ ] **Step 3: Run the existing frontend test suite to confirm no regression**

Run: `cd frontend && pnpm test --run 2>&1 | tail -5`
Expected: 131 passing (unchanged — no tests use these hooks yet).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/clients.ts
git commit -m "feat(S2): add useContextPreview, useContextSave, useContextBrief, useResetContext hooks"
```

---

## Task 5: Frontend — extract `ContextProfileCard` into its own file

**Files:**
- Create: `frontend/src/components/clients/context-profile-card.tsx`
- Modify: `frontend/src/pages/clients/detail.tsx`

This task is a PURE refactor with no behavior change. Tasks 6/7 add the brief toggle and reset button.

- [ ] **Step 1: Create the new component file**

Create `frontend/src/components/clients/context-profile-card.tsx`. Copy the existing `ContextProfileCard` function from `detail.tsx` (lines 183-234) into the new file, with the necessary export:

```typescript
interface ContextProfileCardProps {
  profile: Record<string, unknown>
}

export function ContextProfileCard({ profile }: ContextProfileCardProps) {
  if (!profile || Object.keys(profile).length === 0) return null

  const rel = profile.relationship as Record<string, unknown> | undefined
  const pricing = profile.pricing_intelligence as Record<string, unknown> | undefined
  const pastWork = Array.isArray(profile.past_work) ? profile.past_work as Array<Record<string, unknown>> : []
  const risks = Array.isArray(profile.risks) ? profile.risks as Array<Record<string, unknown>> : []

  return (
    <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-5 md:col-span-2">
      <h3 className="text-sm font-semibold text-indigo-700 uppercase tracking-wide">Client Context</h3>
      <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
        {rel?.status != null ? (
          <div>
            <dt className="text-indigo-500 font-medium">Relationship</dt>
            <dd className="mt-0.5 text-stone-800 capitalize">{String(rel.status)}</dd>
          </div>
        ) : null}
        {pricing?.price_sensitivity != null ? (
          <div>
            <dt className="text-indigo-500 font-medium">Price Sensitivity</dt>
            <dd className="mt-0.5 text-stone-800 capitalize">{String(pricing.price_sensitivity)}</dd>
          </div>
        ) : null}
        {pastWork.length > 0 && (
          <div className="md:col-span-2">
            <dt className="text-indigo-500 font-medium">Past Work</dt>
            <dd className="mt-1 space-y-1">
              {pastWork.map((w, i) => (
                <p key={i} className="text-stone-700">
                  <span className="font-medium">{String(w.project || '')}</span>
                  {w.value != null ? <span className="text-stone-500"> — ₹{Number(w.value).toLocaleString()}</span> : null}
                  {w.status != null ? <span className="text-stone-400"> ({String(w.status)})</span> : null}
                </p>
              ))}
            </dd>
          </div>
        )}
        {risks.length > 0 ? (
          <div className="md:col-span-2">
            <dt className="text-indigo-500 font-medium">Risks</dt>
            <dd className="mt-1 space-y-1">
              {risks.map((r, i) => (
                <p key={i} className="text-stone-700 text-xs">⚠ {String(r.signal || '')}</p>
              ))}
            </dd>
          </div>
        ) : null}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Update `detail.tsx`**

Open `frontend/src/pages/clients/detail.tsx`. Add the import after the existing client-form import (around line 5):

```typescript
import { ContextProfileCard } from '../../components/clients/context-profile-card'
```

Then DELETE the inline `ContextProfileCard` function definition (currently lines 183-234, the entire function from `function ContextProfileCard({ profile }: ...)` through its closing `}`). Keep `QualityBadge` inline — it stays in `detail.tsx`.

The render-site reference (around line 115) `<ContextProfileCard profile={client.context_profile} />` does not need to change.

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && pnpm tsc --noEmit 2>&1 | tail -5`
Expected: no errors.

- [ ] **Step 4: Run the frontend test suite**

Run: `cd frontend && pnpm test --run 2>&1 | tail -5`
Expected: 131 passing (refactor — no behavior change).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/clients/context-profile-card.tsx frontend/src/pages/clients/detail.tsx
git commit -m "refactor(S2): extract ContextProfileCard from detail.tsx"
```

---

## Task 6: Frontend — `<ContextBriefToggle>` component

**Files:**
- Create: `frontend/src/components/clients/context-brief-toggle.tsx`
- Create: `frontend/src/components/clients/__tests__/context-brief-toggle.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/clients/__tests__/context-brief-toggle.test.tsx`:

```typescript
import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { renderWithProviders } from '../../../test/utils'
import { ContextBriefToggle } from '../context-brief-toggle'

describe('ContextBriefToggle', () => {
  it('shows the toggle button collapsed by default and does NOT fetch', async () => {
    let fetched = 0
    server.use(
      http.get(`${API}/clients/c1/context-brief`, () => {
        fetched += 1
        return HttpResponse.json({ brief: 'Should not be called', has_context: true, email_count: 0 })
      }),
    )
    renderWithProviders(<ContextBriefToggle clientId="c1" />)
    expect(screen.getByRole('button', { name: /show what the AI sees/i })).toBeInTheDocument()
    // Brief content NOT rendered
    expect(screen.queryByText(/Should not be called/i)).not.toBeInTheDocument()
    // And no network call made
    expect(fetched).toBe(0)
  })

  it('fetches and renders the brief when expanded', async () => {
    const user = userEvent.setup()
    server.use(
      http.get(`${API}/clients/c1/context-brief`, () =>
        HttpResponse.json({
          brief: 'This client is an existing partner. Tone: warm.',
          has_context: true,
          email_count: 0,
        }),
      ),
    )
    renderWithProviders(<ContextBriefToggle clientId="c1" />)
    await user.click(screen.getByRole('button', { name: /show what the AI sees/i }))
    await waitFor(() =>
      expect(screen.getByText(/existing partner/i)).toBeInTheDocument(),
    )
  })

  it('does not refetch on close + reopen (cached)', async () => {
    const user = userEvent.setup()
    let calls = 0
    server.use(
      http.get(`${API}/clients/c1/context-brief`, () => {
        calls += 1
        return HttpResponse.json({ brief: 'cached brief', has_context: true, email_count: 0 })
      }),
    )
    renderWithProviders(<ContextBriefToggle clientId="c1" />)
    await user.click(screen.getByRole('button', { name: /show what the AI sees/i }))
    await waitFor(() => expect(screen.getByText(/cached brief/i)).toBeInTheDocument())
    expect(calls).toBe(1)

    // Close — the same button now reads "Hide"
    await user.click(screen.getByRole('button', { name: /hide what the AI sees/i }))
    expect(screen.queryByText(/cached brief/i)).not.toBeInTheDocument()

    // Reopen — should serve from cache, no second network call
    await user.click(screen.getByRole('button', { name: /show what the AI sees/i }))
    await waitFor(() => expect(screen.getByText(/cached brief/i)).toBeInTheDocument())
    expect(calls).toBe(1)
  })

  it('renders an empty-state message when has_context is false', async () => {
    const user = userEvent.setup()
    server.use(
      http.get(`${API}/clients/c1/context-brief`, () =>
        HttpResponse.json({ brief: '', has_context: false, email_count: 0 }),
      ),
    )
    renderWithProviders(<ContextBriefToggle clientId="c1" />)
    await user.click(screen.getByRole('button', { name: /show what the AI sees/i }))
    await waitFor(() =>
      expect(screen.getByText(/no context to summarise/i)).toBeInTheDocument(),
    )
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm test --run -t ContextBriefToggle 2>&1 | tail -10`
Expected: FAIL with "Cannot find module" or "Cannot read properties of undefined" — the component doesn't exist.

- [ ] **Step 3: Implement the component**

Create `frontend/src/components/clients/context-brief-toggle.tsx`:

```typescript
import { useState } from 'react'
import { useContextBrief } from '../../api/clients'

interface ContextBriefToggleProps {
  clientId: string
}

export function ContextBriefToggle({ clientId }: ContextBriefToggleProps) {
  const [open, setOpen] = useState(false)
  const { data, isLoading } = useContextBrief(clientId, open)

  return (
    <div className="mt-3 border-t border-indigo-200 pt-3">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="text-xs font-medium text-indigo-700 hover:text-indigo-900 inline-flex items-center gap-1"
      >
        <span aria-hidden>{open ? '▾' : '▸'}</span>
        {open ? 'Hide what the AI sees' : 'Show what the AI sees'}
      </button>

      {open ? (
        <div className="mt-2 rounded-lg bg-white border border-indigo-100 p-3 text-sm text-stone-700">
          {isLoading ? (
            <p className="text-stone-400 text-xs">Generating brief...</p>
          ) : data == null ? (
            <p className="text-stone-400 text-xs">Failed to load brief.</p>
          ) : !data.has_context ? (
            <p className="text-stone-500 text-xs italic">No context to summarise yet. Paste some text above to get started.</p>
          ) : (
            <p className="whitespace-pre-wrap">{data.brief}</p>
          )}
        </div>
      ) : null}
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm test --run -t ContextBriefToggle 2>&1 | tail -10`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/clients/context-brief-toggle.tsx \
        frontend/src/components/clients/__tests__/context-brief-toggle.test.tsx
git commit -m "feat(S2): ContextBriefToggle — on-demand fetch of context brief"
```

---

## Task 7: Frontend — add brief-toggle + reset button to `ContextProfileCard`

**Files:**
- Modify: `frontend/src/components/clients/context-profile-card.tsx`
- Create: `frontend/src/components/clients/__tests__/context-profile-card.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/clients/__tests__/context-profile-card.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { renderWithProviders } from '../../../test/utils'
import { ContextProfileCard } from '../context-profile-card'

const populatedProfile = {
  relationship: { status: 'existing_client' },
  pricing_intelligence: { price_sensitivity: 'high' },
  past_work: [{ project: 'Q4 Brand Sprint', value: 250000, status: 'completed' }],
  risks: [{ signal: 'budget tight this quarter' }],
}

describe('ContextProfileCard', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('returns nothing for an empty profile', () => {
    const { container } = renderWithProviders(<ContextProfileCard profile={{}} clientId="c1" />)
    expect(container.firstChild).toBeNull()
  })

  it('renders the populated profile fields', () => {
    renderWithProviders(<ContextProfileCard profile={populatedProfile} clientId="c1" />)
    expect(screen.getByText(/existing_client/i)).toBeInTheDocument()
    expect(screen.getByText(/high/i)).toBeInTheDocument()
    expect(screen.getByText(/Q4 Brand Sprint/i)).toBeInTheDocument()
    expect(screen.getByText(/budget tight/i)).toBeInTheDocument()
  })

  it('exposes the brief toggle for populated profiles', () => {
    renderWithProviders(<ContextProfileCard profile={populatedProfile} clientId="c1" />)
    expect(screen.getByRole('button', { name: /show what the AI sees/i })).toBeInTheDocument()
  })

  it('shows a reset button that confirms then PATCHes context_profile to {}', async () => {
    const user = userEvent.setup()
    let patchedBody: Record<string, unknown> | null = null
    server.use(
      http.patch(`${API}/clients/c1`, async ({ request }) => {
        patchedBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({
          id: 'c1', name: 'Acme', slug: 'acme', industry: null, size: null,
          contacts: [], notes: null, tags: [], context_profile: {},
          created_at: '', updated_at: '',
        })
      }),
    )
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true))

    renderWithProviders(<ContextProfileCard profile={populatedProfile} clientId="c1" />)
    await user.click(screen.getByRole('button', { name: /reset context/i }))
    await waitFor(() => expect(patchedBody).toEqual({ context_profile: {} }))
  })

  it('does NOT reset when the user cancels the confirm dialog', async () => {
    const user = userEvent.setup()
    let calls = 0
    server.use(
      http.patch(`${API}/clients/c1`, () => {
        calls += 1
        return HttpResponse.json({})
      }),
    )
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(false))

    renderWithProviders(<ContextProfileCard profile={populatedProfile} clientId="c1" />)
    await user.click(screen.getByRole('button', { name: /reset context/i }))
    // Give the click handler a tick
    await new Promise((r) => setTimeout(r, 50))
    expect(calls).toBe(0)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm test --run -t ContextProfileCard 2>&1 | tail -15`
Expected: most fail — the component doesn't accept `clientId`, doesn't render the brief toggle, doesn't have a reset button.

- [ ] **Step 3: Update the component**

Open `frontend/src/components/clients/context-profile-card.tsx` and replace the entire file with:

```typescript
import { useResetContext } from '../../api/clients'
import { ContextBriefToggle } from './context-brief-toggle'

interface ContextProfileCardProps {
  profile: Record<string, unknown>
  clientId: string
}

export function ContextProfileCard({ profile, clientId }: ContextProfileCardProps) {
  const resetContext = useResetContext(clientId)

  if (!profile || Object.keys(profile).length === 0) return null

  const rel = profile.relationship as Record<string, unknown> | undefined
  const pricing = profile.pricing_intelligence as Record<string, unknown> | undefined
  const pastWork = Array.isArray(profile.past_work) ? profile.past_work as Array<Record<string, unknown>> : []
  const risks = Array.isArray(profile.risks) ? profile.risks as Array<Record<string, unknown>> : []

  const handleReset = () => {
    if (!confirm('Reset all context for this client? This cannot be undone.')) return
    resetContext.mutate()
  }

  return (
    <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-5 md:col-span-2">
      <div className="flex items-start justify-between">
        <h3 className="text-sm font-semibold text-indigo-700 uppercase tracking-wide">Client Context</h3>
        <button
          type="button"
          onClick={handleReset}
          disabled={resetContext.isPending}
          className="text-[10px] font-medium text-indigo-500 hover:text-red-600 disabled:opacity-50 uppercase tracking-wide"
        >
          {resetContext.isPending ? 'Resetting...' : 'Reset context'}
        </button>
      </div>

      <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
        {rel?.status != null ? (
          <div>
            <dt className="text-indigo-500 font-medium">Relationship</dt>
            <dd className="mt-0.5 text-stone-800 capitalize">{String(rel.status)}</dd>
          </div>
        ) : null}
        {pricing?.price_sensitivity != null ? (
          <div>
            <dt className="text-indigo-500 font-medium">Price Sensitivity</dt>
            <dd className="mt-0.5 text-stone-800 capitalize">{String(pricing.price_sensitivity)}</dd>
          </div>
        ) : null}
        {pastWork.length > 0 && (
          <div className="md:col-span-2">
            <dt className="text-indigo-500 font-medium">Past Work</dt>
            <dd className="mt-1 space-y-1">
              {pastWork.map((w, i) => (
                <p key={i} className="text-stone-700">
                  <span className="font-medium">{String(w.project || '')}</span>
                  {w.value != null ? <span className="text-stone-500"> — ₹{Number(w.value).toLocaleString()}</span> : null}
                  {w.status != null ? <span className="text-stone-400"> ({String(w.status)})</span> : null}
                </p>
              ))}
            </dd>
          </div>
        )}
        {risks.length > 0 ? (
          <div className="md:col-span-2">
            <dt className="text-indigo-500 font-medium">Risks</dt>
            <dd className="mt-1 space-y-1">
              {risks.map((r, i) => (
                <p key={i} className="text-stone-700 text-xs">⚠ {String(r.signal || '')}</p>
              ))}
            </dd>
          </div>
        ) : null}
      </div>

      <ContextBriefToggle clientId={clientId} />
    </div>
  )
}
```

- [ ] **Step 4: Update the render site in `detail.tsx`**

Open `frontend/src/pages/clients/detail.tsx`. Find the line:
```typescript
<ContextProfileCard profile={client.context_profile} />
```
Replace with:
```typescript
<ContextProfileCard profile={client.context_profile} clientId={client.id} />
```

- [ ] **Step 5: Run the test**

Run: `cd frontend && pnpm test --run -t ContextProfileCard 2>&1 | tail -10`
Expected: 5 passed.

- [ ] **Step 6: Run the full frontend suite to confirm no regression**

Run: `cd frontend && pnpm test --run 2>&1 | tail -5`
Expected: 131 + 4 (Task 6) + 5 (Task 7) = 140 passing across 26 files.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/clients/context-profile-card.tsx \
        frontend/src/components/clients/__tests__/context-profile-card.test.tsx \
        frontend/src/pages/clients/detail.tsx
git commit -m "feat(S2): ContextProfileCard gains reset button + brief toggle"
```

---

## Task 8: Frontend — `<AddContextSection>` state machine + tests

**Files:**
- Create: `frontend/src/components/clients/add-context-section.tsx`
- Create: `frontend/src/components/clients/__tests__/add-context-section.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/clients/__tests__/add-context-section.test.tsx`:

```typescript
import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { server } from '../../../test/mocks/server'
import { API } from '../../../test/mocks/handlers'
import { renderWithProviders } from '../../../test/utils'
import { AddContextSection } from '../add-context-section'

const STUB_EXTRACTED = {
  relationship: { status: 'existing_client', primary_contact: { name: 'Priya' } },
  past_work: [{ project: 'Brand Sprint', value: 250000, status: 'completed' }],
}

describe('AddContextSection', () => {
  it('starts collapsed and shows an Add button', () => {
    renderWithProviders(<AddContextSection clientId="c1" />)
    expect(screen.getByRole('button', { name: /add or update context/i })).toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })

  it('expands to a textarea when the Add button is clicked', async () => {
    const user = userEvent.setup()
    renderWithProviders(<AddContextSection clientId="c1" />)
    await user.click(screen.getByRole('button', { name: /add or update context/i }))
    expect(screen.getByRole('textbox')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /extract preview/i })).toBeInTheDocument()
  })

  it('runs preview, shows the extracted structure, then commits on save', async () => {
    const user = userEvent.setup()
    let previewBody: Record<string, unknown> | null = null
    let saveBody: Record<string, unknown> | null = null

    server.use(
      http.post(`${API}/clients/c1/context/preview`, async ({ request }) => {
        previewBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ extracted: STUB_EXTRACTED })
      }),
      http.post(`${API}/clients/c1/context/save`, async ({ request }) => {
        saveBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({
          id: 'c1', name: 'Acme', slug: 'acme', industry: null, size: null,
          contacts: [], notes: null, tags: [],
          context_profile: STUB_EXTRACTED,
          created_at: '', updated_at: '',
        })
      }),
    )

    renderWithProviders(<AddContextSection clientId="c1" />)
    await user.click(screen.getByRole('button', { name: /add or update context/i }))
    await user.type(screen.getByRole('textbox'), 'Met Priya last week, brand sprint went well.')
    await user.click(screen.getByRole('button', { name: /extract preview/i }))

    await waitFor(() =>
      expect(previewBody).toEqual({ raw_text: 'Met Priya last week, brand sprint went well.' }),
    )
    // Preview rendered
    await waitFor(() => expect(screen.getByText(/Priya/i)).toBeInTheDocument())
    expect(screen.getByText(/Brand Sprint/i)).toBeInTheDocument()

    // Save
    await user.click(screen.getByRole('button', { name: /save to client/i }))
    await waitFor(() => expect(saveBody).toEqual({ profile: STUB_EXTRACTED }))

    // Collapses back after save (the "Add" button is visible again)
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /add or update context/i })).toBeInTheDocument(),
    )
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })

  it('preserves the textarea content when "Edit text" is clicked from preview', async () => {
    const user = userEvent.setup()
    server.use(
      http.post(`${API}/clients/c1/context/preview`, () =>
        HttpResponse.json({ extracted: STUB_EXTRACTED }),
      ),
    )

    renderWithProviders(<AddContextSection clientId="c1" />)
    await user.click(screen.getByRole('button', { name: /add or update context/i }))
    await user.type(screen.getByRole('textbox'), 'first attempt')
    await user.click(screen.getByRole('button', { name: /extract preview/i }))

    await waitFor(() => expect(screen.getByText(/Priya/i)).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /edit text/i }))

    // Textarea reappears, retains content
    expect(screen.getByRole('textbox')).toHaveValue('first attempt')
  })

  it('clears state on Cancel', async () => {
    const user = userEvent.setup()
    renderWithProviders(<AddContextSection clientId="c1" />)
    await user.click(screen.getByRole('button', { name: /add or update context/i }))
    await user.type(screen.getByRole('textbox'), 'discarded')
    await user.click(screen.getByRole('button', { name: /cancel/i }))

    // Collapsed
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()

    // Re-expanding shows an empty textarea (state cleared)
    await user.click(screen.getByRole('button', { name: /add or update context/i }))
    expect(screen.getByRole('textbox')).toHaveValue('')
  })

  it('shows an error message when preview fails', async () => {
    const user = userEvent.setup()
    server.use(
      http.post(`${API}/clients/c1/context/preview`, () =>
        HttpResponse.json({ detail: 'AI service unavailable' }, { status: 503 }),
      ),
    )

    renderWithProviders(<AddContextSection clientId="c1" />)
    await user.click(screen.getByRole('button', { name: /add or update context/i }))
    await user.type(screen.getByRole('textbox'), 'anything')
    await user.click(screen.getByRole('button', { name: /extract preview/i }))

    await waitFor(() =>
      expect(screen.getByText(/AI service unavailable|extraction failed/i)).toBeInTheDocument(),
    )
    // Textarea still present so user can retry
    expect(screen.getByRole('textbox')).toBeInTheDocument()
  })

  it('disables the Extract preview button when textarea is empty', async () => {
    const user = userEvent.setup()
    renderWithProviders(<AddContextSection clientId="c1" />)
    await user.click(screen.getByRole('button', { name: /add or update context/i }))
    expect(screen.getByRole('button', { name: /extract preview/i })).toBeDisabled()

    await user.type(screen.getByRole('textbox'), 'now non-empty')
    expect(screen.getByRole('button', { name: /extract preview/i })).not.toBeDisabled()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm test --run -t AddContextSection 2>&1 | tail -15`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement the component**

Create `frontend/src/components/clients/add-context-section.tsx`:

```typescript
import { useState } from 'react'
import { useContextPreview, useContextSave, type ContextPreview } from '../../api/clients'
import { formatApiError } from '../../api/client'

interface AddContextSectionProps {
  clientId: string
}

type Mode = 'collapsed' | 'editing' | 'preview'

export function AddContextSection({ clientId }: AddContextSectionProps) {
  const [mode, setMode] = useState<Mode>('collapsed')
  const [text, setText] = useState('')
  const [preview, setPreview] = useState<ContextPreview | null>(null)
  const previewMut = useContextPreview(clientId)
  const saveMut = useContextSave(clientId)

  const handleExtract = async () => {
    if (!text.trim()) return
    previewMut.mutate(text, {
      onSuccess: (data) => {
        setPreview(data)
        setMode('preview')
      },
    })
  }

  const handleSave = () => {
    if (!preview) return
    saveMut.mutate(preview.extracted, {
      onSuccess: () => {
        // Collapse back to the closed state and clear inputs
        setMode('collapsed')
        setText('')
        setPreview(null)
      },
    })
  }

  const handleEditText = () => {
    setMode('editing')
    setPreview(null)
  }

  const handleCancel = () => {
    setMode('collapsed')
    setText('')
    setPreview(null)
    previewMut.reset()
    saveMut.reset()
  }

  if (mode === 'collapsed') {
    return (
      <div className="md:col-span-2">
        <button
          type="button"
          onClick={() => setMode('editing')}
          className="w-full rounded-xl border border-dashed border-indigo-300 bg-indigo-50 hover:bg-indigo-100 px-5 py-3 text-left text-sm text-indigo-700 font-medium transition-colors"
        >
          ✨ Add or update context
          <span className="block text-xs text-indigo-500 mt-0.5">Paste emails, notes, or meeting summaries — I'll extract relationship, pricing signals, and past work.</span>
        </button>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-5 md:col-span-2">
      <h3 className="text-sm font-semibold text-indigo-700 uppercase tracking-wide">Add Context</h3>

      {mode === 'editing' ? (
        <>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={'Paste email threads, meeting notes, past proposal feedback, budget discussions...\n\nExample:\n"We did a poster project for them in August for ₹2.4L. Priya from IC is the main contact. Budget for this might be tight."'}
            rows={8}
            className="mt-3 w-full rounded-lg border border-indigo-200 bg-white px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500"
            autoFocus
          />
          {previewMut.isError ? (
            <p className="mt-2 text-sm text-red-600">{formatApiError(previewMut.error)}</p>
          ) : null}
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={handleExtract}
              disabled={previewMut.isPending || !text.trim()}
              className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
            >
              {previewMut.isPending ? 'Extracting...' : 'Extract preview'}
            </button>
            <button
              type="button"
              onClick={handleCancel}
              className="rounded-lg border border-stone-300 px-4 py-2 text-sm text-stone-600 hover:bg-stone-50"
            >
              Cancel
            </button>
          </div>
        </>
      ) : null}

      {mode === 'preview' && preview != null ? (
        <>
          <p className="mt-3 text-sm text-indigo-700">Here's what the AI extracted. Review and save, or edit your text and try again.</p>
          <ExtractedPreview profile={preview.extracted} />
          {saveMut.isError ? (
            <p className="mt-2 text-sm text-red-600">{formatApiError(saveMut.error)}</p>
          ) : null}
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={handleSave}
              disabled={saveMut.isPending}
              className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
            >
              {saveMut.isPending ? 'Saving...' : 'Save to client'}
            </button>
            <button
              type="button"
              onClick={handleEditText}
              className="rounded-lg border border-stone-300 px-4 py-2 text-sm text-stone-600 hover:bg-stone-50"
            >
              Edit text
            </button>
            <button
              type="button"
              onClick={handleCancel}
              className="rounded-lg border border-stone-300 px-4 py-2 text-sm text-stone-600 hover:bg-stone-50"
            >
              Cancel
            </button>
          </div>
        </>
      ) : null}
    </div>
  )
}

/** Inline render of the extracted preview — visually parallels ContextProfileCard
 *  so the user can compare before and after. Kept here (not extracted) because it's
 *  only used in this file. */
function ExtractedPreview({ profile }: { profile: Record<string, unknown> }) {
  const rel = profile.relationship as Record<string, unknown> | undefined
  const pricing = profile.pricing_intelligence as Record<string, unknown> | undefined
  const pastWork = Array.isArray(profile.past_work) ? profile.past_work as Array<Record<string, unknown>> : []
  const risks = Array.isArray(profile.risks) ? profile.risks as Array<Record<string, unknown>> : []
  const opportunities = Array.isArray(profile.opportunities) ? profile.opportunities as Array<Record<string, unknown>> : []

  const isEmpty = !rel?.status && !pricing?.price_sensitivity && pastWork.length === 0 && risks.length === 0 && opportunities.length === 0
  if (isEmpty) {
    return <p className="mt-3 text-sm text-stone-500 italic">The AI didn't find any structured signals in that text. Try pasting something more specific (emails, meeting notes, past project details).</p>
  }

  return (
    <div className="mt-3 rounded-lg border border-indigo-100 bg-white p-4 grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
      {rel?.status != null ? (
        <div>
          <p className="text-indigo-500 font-medium text-xs uppercase tracking-wide">Relationship</p>
          <p className="text-stone-800 capitalize">{String(rel.status)}</p>
          {(rel.primary_contact as Record<string, unknown> | undefined)?.name != null ? (
            <p className="text-stone-500 text-xs">Contact: {String((rel.primary_contact as Record<string, unknown>).name)}</p>
          ) : null}
        </div>
      ) : null}
      {pricing?.price_sensitivity != null ? (
        <div>
          <p className="text-indigo-500 font-medium text-xs uppercase tracking-wide">Price Sensitivity</p>
          <p className="text-stone-800 capitalize">{String(pricing.price_sensitivity)}</p>
        </div>
      ) : null}
      {pastWork.length > 0 ? (
        <div className="md:col-span-2">
          <p className="text-indigo-500 font-medium text-xs uppercase tracking-wide">Past Work</p>
          {pastWork.map((w, i) => (
            <p key={i} className="text-stone-700">
              <span className="font-medium">{String(w.project || '')}</span>
              {w.value != null ? <span className="text-stone-500"> — ₹{Number(w.value).toLocaleString()}</span> : null}
            </p>
          ))}
        </div>
      ) : null}
      {risks.length > 0 ? (
        <div className="md:col-span-2">
          <p className="text-indigo-500 font-medium text-xs uppercase tracking-wide">Risks</p>
          {risks.map((r, i) => (
            <p key={i} className="text-stone-700 text-xs">⚠ {String(r.signal || '')}</p>
          ))}
        </div>
      ) : null}
      {opportunities.length > 0 ? (
        <div className="md:col-span-2">
          <p className="text-indigo-500 font-medium text-xs uppercase tracking-wide">Opportunities</p>
          {opportunities.map((o, i) => (
            <p key={i} className="text-stone-700 text-xs">✨ {String(o.signal || '')}</p>
          ))}
        </div>
      ) : null}
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm test --run -t AddContextSection 2>&1 | tail -15`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/clients/add-context-section.tsx \
        frontend/src/components/clients/__tests__/add-context-section.test.tsx
git commit -m "feat(S2): AddContextSection — inline paste → preview → save state machine"
```

---

## Task 9: Frontend — wire `<AddContextSection>` into `detail.tsx`

**Files:**
- Modify: `frontend/src/pages/clients/detail.tsx`

- [ ] **Step 1: Import the new component**

Open `frontend/src/pages/clients/detail.tsx`. Add the import next to the existing `ContextProfileCard` import:

```typescript
import { AddContextSection } from '../../components/clients/add-context-section'
```

- [ ] **Step 2: Render `<AddContextSection>` between the Contacts card and the Context card**

Find the existing render block (around line 115 after the refactor):

```typescript
          {/* Context Profile card */}
          <ContextProfileCard profile={client.context_profile} clientId={client.id} />
```

Insert ABOVE that block:

```typescript
          {/* Manual Context input */}
          <AddContextSection clientId={client.id} />
```

So the final order in the grid becomes: Details, Contacts, AddContextSection, ContextProfileCard, Intelligence cards, Proposals placeholder.

- [ ] **Step 3: Run the full frontend test suite**

Run: `cd frontend && pnpm test --run 2>&1 | tail -5`
Expected: ≥139 passing across 27 files (was 131; +4 from Task 6, +5 from Task 7, +7 from Task 8 = 147 actually; the spec target was conservative).

- [ ] **Step 4: TypeScript check**

Run: `cd frontend && pnpm tsc --noEmit 2>&1 | tail -5`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/clients/detail.tsx
git commit -m "feat(S2): mount AddContextSection on Client Detail page"
```

---

## Task 10: Acceptance checklist + merge prep

**Files:** none modified (verification only).

- [ ] **Step 1: Full backend suite**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: 289 baseline + 6 new tests (3 preview + 3 save) = 295 passing. No skipped.

- [ ] **Step 2: Full frontend suite**

Run: `cd frontend && pnpm test --run`
Expected: 131 baseline + ≥16 new tests (4 brief-toggle + 5 profile-card + 7 add-context) = 147+ passing across 27 files.

- [ ] **Step 3: TypeScript clean**

Run: `cd frontend && pnpm tsc --noEmit && cd ../backend && .venv/bin/python -c "from app.main import app; print(len(app.routes))"`
Expected: tsc silent. Backend prints `66` (was 64 → +2 new routes for preview and save).

- [ ] **Step 4: Manual smoke — paste flow**

Start the dev stack (in two terminals):

```bash
# Terminal 1
cd /Users/karthikramesh/Developer/nuprop/.claude/worktrees/m16-m20-s2-context-ui/backend && .venv/bin/uvicorn app.main:app --reload

# Terminal 2
cd /Users/karthikramesh/Developer/nuprop/.claude/worktrees/m16-m20-s2-context-ui/frontend && pnpm dev
```

Manually verify:
1. Register a new user or log in.
2. Create a client.
3. Click into the client.
4. Click "Add or update context" — the section expands to a textarea.
5. Paste: `"We worked with Acme on a brand sprint in Q4 for ₹2.5L. Priya from their marketing team was the lead — she's very responsive but quite price-sensitive. They rejected our retainer pitch last year as too expensive."`
6. Click "Extract preview" — wait ~3-5s for Claude.
7. Verify the parsed structure appears (relationship.status, pricing_intelligence.price_sensitivity, past_work).
8. Click "Save to client".
9. Verify the Client Context card appears (or updates) with the same data.
10. Click "Show what the AI sees" on the Client Context card.
11. Verify a natural-language brief loads (~3-5s).
12. Click "Reset context" → confirm dialog → verify the Client Context card disappears.

- [ ] **Step 5: Update HANDOFF + memory**

Open `docs/superpowers/HANDOFF.md` and mark S2 as done in the slicing table. Replace the line:

```markdown
| **S2** — Manual context UI on Client page | 1d | M16 shippable end-to-end |
```

With:

```markdown
| ~~S2~~ — Manual context UI on Client page | ~~1d~~ ✅ done 2026-05-DD | New `/context/preview` + `/context/save` endpoints, `<AddContextSection>` state machine, `<ContextBriefToggle>`, reset button. 6 new pytest cases, 16 new vitest cases. M16 is shippable end-to-end. |
```

(Replace `DD` with the actual day.)

Update `~/.claude/projects/-Users-karthikramesh-Developer-nuprop/memory/project_build_progress.md` to flip S2 to DONE and set "Active slice" to S3.

Commit:

```bash
git add docs/superpowers/HANDOFF.md
git commit -m "docs(S2): mark slice complete in handoff"
```

- [ ] **Step 6: Merge prep**

When the user approves at the S2 checkpoint:

```bash
# From the worktree, push the branch so the merge can happen from main
git log --oneline origin/main..HEAD   # confirm the S2 commits

# Then from the main checkout:
cd /Users/karthikramesh/Developer/nuprop
git fetch origin
git merge --ff-only worktree-m16-m20-s2-context-ui
git push origin main
```

GitHub Actions auto-deploy from S1 will pick this up. The two new routes are inert in prod until users start using the Client Detail page (no breaking change to existing flows).

---

## What lands next (S3 preview)

After S2 merges and the user approves at the S2 checkpoint:

- Open worktree `m16-m20-s3-connector-frontend`.
- Write spec covering: Drive/Calendar React Query hooks, Slack OAuth callback route + page (currently MISSING — backend has the endpoint but frontend has nowhere for the popup to redirect to), sync status UI for Drive/Calendar parity with Gmail, tests across all of it.
- Estimated 1.5 days.
