# Client Discovery from Gmail — Design

**Status:** Brainstormed 2026-05-19. Implementation plan: pending.
**Surfaces:** `frontend/src/pages/clients/list.tsx` (new empty-state + secondary button) and a new `frontend/src/components/clients/discovery/` directory. New backend endpoint `POST /api/v1/connectors/gmail/discover-clients`. Existing `connector_viewmodel.sync_emails` and the manual `ClientForm` flow remain untouched.

---

## Goal

Let an agency populate their `clients` table by scanning their connected Gmail inbox and reviewing AI-suggested candidates, instead of typing every client manually. Solves the chicken-and-egg problem where Gmail sync requires clients to exist (it searches *by client domain*) but a brand-new user has no clients yet.

## Non-goals

- **Background scheduled discovery.** Manual user-triggered only. No cron/ARQ job.
- **LLM-powered company naming.** Heuristic only for v1 — strip TLD + capitalize. Review wizard exists to fix bad names inline.
- **Industry / size auto-detection.** Wizard leaves these fields blank.
- **Separating sent vs received emails for ranking.** Gmail's `after:<date>` search includes both directions; we use the union without differentiation.
- **Email body content used for ranking.** Only sender/recipient + count + date metadata.
- **Slack or Drive discovery analogues.** Gmail only.
- **Configurable noise list per agency.** `SAAS_NOISE_DOMAINS` is a backend constant.
- **Pagination of existing clients during the already-linked check.** First 500 only (matches `sync_emails`). If an agency has 500+ clients, future work.
- **Migration of existing data.** No DB schema changes.

## User flow

```
/clients page (existing, modified)
   │
   ├─ If 0 clients exist                                Empty-state card with TWO CTAs:
   │                                                      ┌─ Add a client manually      (existing form)
   │                                                      └─ Discover from Gmail        (new; only if Gmail connected)
   │
   └─ If N>0 clients exist                              Header keeps primary "Add client" + new secondary "Discover from Gmail"
                                                          (secondary button only if Gmail connected)

                                ↓ click "Discover from Gmail"

   Lookback picker modal                                "Look back how far?" with three buttons:  30 days | 90 days | 365 days
                                                          (90 days is the default highlighted button)

                                ↓ pick → POST /api/v1/connectors/gmail/discover-clients { lookback_days }

   Scanning state                                       Spinner "Scanning your inbox..." (typical: 3-20s by window)

                                ↓ response arrives

   Candidate list modal                                 ┌─────────────────────────────────────┐
                                                        │ Found 12 candidate clients          │
                                                        │ (3 domains already linked excluded) │
                                                        │                                     │
                                                        │ ☑ acme.com → "Acme"                 │
                                                        │   47 emails · 3 senders · Apr–May   │
                                                        │ ☑ tatacomms.com → "Tatacomms"       │
                                                        │   32 emails · 2 senders · Mar–May   │
                                                        │ ☐ zoho.com → "Zoho"                 │
                                                        │   18 emails · 1 sender · Apr        │
                                                        │ ...                                 │
                                                        │                                     │
                                                        │ [Skip all]    [Review 2 selected →] │
                                                        └─────────────────────────────────────┘

                                ↓ "Review N selected"

   Candidate review wizard                              Sequential, one candidate per screen:
                                                        ┌─────────────────────────────────────┐
                                                        │ Reviewing 1 of 2 · acme.com         │
                                                        │                                     │
                                                        │ Name *      [Acme               ]   │
                                                        │ Industry    [                   ]   │
                                                        │ Size        [▾                  ]   │
                                                        │ Tags        [                   ]   │
                                                        │                                     │
                                                        │ Contacts (auto-filled)              │
                                                        │  Jane Doe   <jane@acme.com>   ✕     │
                                                        │  Bob Smith  <bob@acme.com>    ✕     │
                                                        │  + Add contact                      │
                                                        │                                     │
                                                        │ [Skip this]    [Save & Next →]      │
                                                        └─────────────────────────────────────┘

                                ↓ after final candidate

   Done                                                 Toast "Created N clients" → close modal → invalidate /clients query → list refreshes.
```

The full flow exists only as ephemeral state in `<ClientDiscoveryFlow>`. No persisted "pending candidates" — closing mid-flow means re-running discovery (cheap, idempotent).

## Backend architecture

### Endpoint

```
POST /api/v1/connectors/gmail/discover-clients
   body:     { "lookback_days": 30 | 90 | 365 }
   response: {
     "candidates": [
       {
         "domain": "acme.com",
         "suggested_name": "Acme",
         "message_count": 47,
         "sender_count": 3,
         "top_senders": [
           {"name": "Jane Doe", "email": "jane@acme.com", "message_count": 28},
           {"name": "Bob Smith", "email": "bob@acme.com", "message_count": 12},
           {"name": "Carol Wu", "email": "carol@acme.com", "message_count": 7}
         ],
         "first_date": "2026-04-02T09:13:00Z",
         "last_date": "2026-05-18T16:44:00Z"
       },
       ...
     ],
     "excluded_existing": 3,
     "scanned_messages": 247,
     "duration_seconds": 4.2
   }

   401 if Gmail not connected or stored token undecryptable
   400 if lookback_days not in {30, 90, 365}
   500 if Gmail API failures exceed retry threshold
```

### Files created

```
backend/app/services/connectors/discovery_aggregator.py    NEW
  - Pure function: aggregate(messages, own_domain, excluded_domains) → list[Candidate]
  - Module constants: SAAS_NOISE_DOMAINS, NO_REPLY_PATTERN
  - Pure function: suggest_name_from_domain(domain) → str
  - Fully unit-testable without Gmail

backend/app/domain/schemas/discovery_schemas.py            NEW
  - DiscoveryRequest:   { lookback_days: Literal[30, 90, 365] }
  - TopSender:          { name: str, email: str, message_count: int }
  - Candidate:          { domain, suggested_name, message_count, sender_count,
                          top_senders, first_date, last_date }
  - DiscoveryResponse:  { candidates: list[Candidate], excluded_existing: int,
                          scanned_messages: int, duration_seconds: float }
```

### Files modified

```
backend/app/infrastructure/external/gmail_client.py        MODIFIED
  + async def fetch_recent_messages(access_token, lookback_days, limit) -> list[dict]
    Same paging pattern as fetch_messages_for_domain. Query: f"after:{since.strftime('%Y/%m/%d')}".

backend/app/viewmodels/connector_viewmodel.py              MODIFIED
  + async def discover_clients(agency_id, lookback_days) -> DiscoveryResponse
    Orchestrates: refresh token → fetch_recent_messages → aggregate → filter existing → return.

backend/app/views/v1/connectors.py                         MODIFIED
  + POST /gmail/discover-clients route handler. Auth + Depends() injection of ConnectorViewModel.
```

### Aggregation algorithm

`discovery_aggregator.aggregate(messages, own_domain, excluded_domains)`:

```
candidates_by_domain: dict[str, dict] = {}
for msg in messages:
    sender_email = parse_email(msg["from"])
    sender_domain = sender_email.split("@")[-1].lower()
    if sender_domain in FREEMAIL_DOMAINS: continue
    if sender_domain in SAAS_NOISE_DOMAINS: continue
    if sender_domain == own_domain: continue
    if NO_REPLY_PATTERN.match(sender_email.split("@")[0]): continue
    if sender_domain in excluded_domains: continue
    
    if sender_domain not in candidates_by_domain:
        candidates_by_domain[sender_domain] = {
            "domain": sender_domain,
            "message_count": 0,
            "senders": {},  # email → {name, count}
            "first_date": msg["date"],
            "last_date": msg["date"],
        }
    c = candidates_by_domain[sender_domain]
    c["message_count"] += 1
    if msg["date"] < c["first_date"]: c["first_date"] = msg["date"]
    if msg["date"] > c["last_date"]: c["last_date"] = msg["date"]
    sender_email_lower = sender_email.lower()
    if sender_email_lower not in c["senders"]:
        c["senders"][sender_email_lower] = {"name": parse_display_name(msg["from"]), "count": 0}
    c["senders"][sender_email_lower]["count"] += 1

# Same loop applied to recipient addresses (msg["to"]) so sent-items count.

# Build final Candidate list
final = []
for c in candidates_by_domain.values():
    top_senders = sorted(c["senders"].items(), key=lambda kv: -kv[1]["count"])[:3]
    final.append(Candidate(
        domain=c["domain"],
        suggested_name=suggest_name_from_domain(c["domain"]),
        message_count=c["message_count"],
        sender_count=len(c["senders"]),
        top_senders=[TopSender(name=v["name"], email=k, message_count=v["count"]) for k, v in top_senders],
        first_date=c["first_date"],
        last_date=c["last_date"],
    ))

# Rank: message_count desc, then last_date desc as tiebreaker
final.sort(key=lambda c: (-c.message_count, -c.last_date.timestamp()))
return final[:30]  # cap at 30 to avoid overwhelming review
```

`SAAS_NOISE_DOMAINS` (constant): `github.com, gitlab.com, bitbucket.org, linear.app, notion.so, slack.com, atlassian.com, jira.com, figma.com, calendly.com, zoom.us, mailchimp.com, sendgrid.net, hubspot.com, salesforce.com, stripe.com, paypal.com, docusign.com, dropbox.com, box.com`. Documented as subjective; expected to grow as patterns emerge.

`NO_REPLY_PATTERN` (constant): `re.compile(r'^(noreply|no-reply|notifications?|mailer-daemon|donotreply|do-not-reply|automated)@', re.IGNORECASE)` — matches the local part. Excludes the **message** but the domain's count from other senders at the same domain is preserved (so `noreply@acme.com` + `jane@acme.com` → domain shows count=1 sender = Jane, not zero).

`suggest_name_from_domain('tatacomms.com')` → `'Tatacomms'`. Intentionally crude; review wizard fixes bad guesses.

### Own-domain inference

```python
def _extract_own_domain(agency) -> str | None:
    # The Gmail-connected account is the agency owner's email; its domain
    # is what the agency sends FROM. Use that as the own-domain filter.
    settings = agency.settings or {}
    gmail = settings.get("gmail", {})
    email = (gmail.get("email") or "").strip()
    if "@" in email:
        return email.split("@")[-1].lower()
    return None
```

If `None` (e.g., Gmail not connected — which means discovery wouldn't be triggered anyway), no own-domain filter applies. Safe by construction: discovery is only callable after Gmail is connected, at which point `settings.gmail.email` is always populated by the OAuth callback.

### Limits

| Lookback | Max messages fetched | Soft cap on candidates returned |
|---|---|---|
| 30 days  | 500  | 30 |
| 90 days  | 1500 | 30 |
| 365 days | 3000 | 30 |

If the message limit is hit: backend logs `event: discovery.message_limit_hit` and processes whatever was fetched. If the candidate limit is hit: backend logs `event: discovery.candidates_truncated`.

## Frontend architecture

### Files created

```
frontend/src/components/clients/discovery/
  client-discovery-flow.tsx           NEW — modal stack state machine (~80 LOC)
  lookback-picker.tsx                 NEW — "Look back how far?" 3-button picker (~30 LOC)
  candidate-list.tsx                  NEW — checkbox table + bulk-select + footer (~100 LOC)
  candidate-review-wizard.tsx         NEW — sequential ClientForm with Next/Save (~80 LOC)
  index.ts                            NEW — barrel export
  __tests__/
    client-discovery-flow.test.tsx
    lookback-picker.test.tsx
    candidate-list.test.tsx
    candidate-review-wizard.test.tsx

frontend/src/api/discovery.ts         NEW — useDiscoverClients mutation hook
frontend/src/types/discovery.ts       NEW — Candidate, TopSender, DiscoveryResponse types
```

### Files modified

```
frontend/src/pages/clients/list.tsx           MODIFIED
  - Empty state: replace single "No clients yet." with a card showing two CTAs
  - Header: add secondary "Discover from Gmail" button next to "Add client" (rendered iff gmail.connected)
  - Mount <ClientDiscoveryFlow agencyId open={openDiscovery} onClose={...} onComplete={...} />

frontend/src/components/clients/client-form.tsx   MODIFIED
  - New optional prop: initialContacts?: ContactInfo[]
  - Add an inline contacts editor (list of {name, email} rows with delete + "Add contact" link)
  - On submit, include contacts in the payload (today's form drops them — Client schema has the field
    but the form doesn't surface it)
```

That last point: **the existing ClientForm doesn't let you edit contacts at all.** Today contacts only exist via the API directly or via context-brief extraction. This change adds the inline editor as a prerequisite — the review wizard depends on it, and it's a useful side-effect for the manual creation path too.

### Component state machine (`<ClientDiscoveryFlow>`)

```
type FlowState =
  | { phase: 'idle' }
  | { phase: 'lookback' }
  | { phase: 'scanning' }
  | { phase: 'review_list', response: DiscoveryResponse }
  | { phase: 'review_wizard', candidates: Candidate[], index: number, created: number }
  | { phase: 'done', created: number }
  | { phase: 'error', message: string }
```

Transitions:
- `idle → lookback` on user click "Discover from Gmail"
- `lookback → scanning` on user pick (fires mutation)
- `scanning → review_list` on mutation success
- `scanning → error` on mutation failure (e.g., 401 → "Reconnect Gmail")
- `review_list → review_wizard` on "Review N selected" (if selected count > 0)
- `review_list → done` on "Skip all" (created=0)
- `review_wizard → review_wizard` (index++) on "Skip this" or "Save & Next"
- `review_wizard → done` when index reaches end
- `done` closes modal + invalidates `useClients` cache

### `useDiscoverClients` hook

Plain TanStack `useMutation` posting to `/api/v1/connectors/gmail/discover-clients`. No caching (it's expensive, user-initiated, never auto-refetch).

## Validation, defaults, and edge cases

| Concern | Behavior |
|---|---|
| Gmail not connected | "Discover from Gmail" CTA only renders when `agency.settings.gmail.connected === true`. Endpoint also returns `400 "Gmail not connected"` if invoked anyway. Frontend shows friendly error linking to Settings. |
| Token expired / decrypt fails | `401 "Stored Gmail credentials could not be decrypted; please reconnect"` — same path `sync_emails` uses. Frontend renders a Reconnect prompt. |
| No candidates found | `{candidates: [], excluded_existing: 0, scanned_messages: N}` — frontend shows "We scanned N messages but didn't find any client-looking domains. Try a wider lookback or add clients manually." |
| All candidates already linked | `{candidates: [], excluded_existing: N}` — frontend shows "N candidate domains are already linked to existing clients. Nothing new to discover." |
| User selects 0 candidates, clicks "Review N" | Button is disabled when 0 selected. |
| User clicks "Skip this" on every candidate | Wizard completes with `created=0`. Frontend shows "Nothing created — closing." Doesn't error. |
| Mid-flow close (modal X or escape) | Selected candidates discarded. No persistence. Re-run is the recovery. |
| `lookback_days` not in {30, 90, 365} | `400 "Invalid lookback_days; must be 30, 90, or 365"`. Frontend prevents this; defense-in-depth on backend. |
| Default lookback | 90 days. Middle button is pre-highlighted. |
| Already-linked domain check | A domain is "linked" if ANY existing `client.contacts[i].email` has that domain. Computed via `client_repo.search(agency_id, limit=500)`. If agency has 500+ clients, paginator is future work. |
| Aggressive noise: SaaS sender that's actually your client | E.g., a real `someone@github.com` employee. Filtered out by default — user has to add manually. Documented as known limitation. |
| Rate limit / Gmail 429 or transient errors | Each `get_message` call is wrapped in try/except — individual failures are logged with `event: connector.gmail.message_fetch_failed` and skipped, same pattern as today's `fetch_messages_for_domain`. No retry/backoff at the per-message layer. If the top-level `search_messages` pagination call itself fails, the ViewModel catches the exception and returns `500` with a structured error; frontend shows "Couldn't scan right now. Try again in a minute." Retry-with-backoff is documented as future work if rate limits prove to be a real problem in practice. |
| Idempotency | Read-only on Gmail side. Doesn't write to `email_index`. Safe and cheap to re-run. |
| Concurrent users | No shared state. Each request scoped to its own agency. |
| What about emails the agency *sent* to clients? | Backend query `after:<date>` includes BOTH sent and received in Gmail's search. Recipients are tallied alongside senders. |

## Tests

### Backend (pytest)

`tests/unit/test_discovery_aggregator.py` — pure-logic, no Gmail dependency. Cases:
- empty messages → empty candidates
- single message → single candidate with count=1
- two senders at same domain → one candidate, sender_count=2, both in top_senders
- freemail sender (gmail.com) → filtered out
- SaaS-noise sender (github.com) → filtered out
- noreply@acme.com + jane@acme.com → candidate has count=1 (jane only)
- own-domain sender → filtered out
- sort order: message_count desc, last_date desc as tiebreaker
- top_senders capped at 3, ordered by message_count
- candidate list truncated at 30
- excluded_domains argument removes matching domains entirely
- recipient-direction message counts toward sender's domain (sent emails)
- mixed sent+received emails for same domain combine into one candidate

`tests/unit/test_suggest_name_from_domain.py`:
- `acme.com → "Acme"`, `tatacomms.com → "Tatacomms"`, `mckinsey.com → "Mckinsey"`, `single.io → "Single"`
- subdomain handling: `mail.acme.com → "Mail"` (acknowledged limitation; documented)

`tests/integration/test_discover_clients_endpoint.py`:
- end-to-end with stubbed `GmailClient.fetch_recent_messages` returning fixture messages
- asserts response shape and ordering
- asserts `excluded_existing` count when fixture clients exist with matching contact domains
- asserts `401` when Gmail not connected
- asserts `401` when `TokenVaultError` on decrypt
- asserts `400` when `lookback_days` is invalid

### Frontend (vitest)

`components/clients/discovery/__tests__/lookback-picker.test.tsx`:
- renders 3 buttons (30, 90, 365)
- 90-day button has the default-highlighted style
- clicking each fires `onPick` with the right number

`components/clients/discovery/__tests__/candidate-list.test.tsx`:
- renders candidates from response with name, count, sender count, date range
- checkbox toggles selection (uses stateful test wrapper — Wrapper component with useState per the lesson from rate-card-wizard)
- "Review N selected" is disabled when 0 selected, enabled with count when ≥1
- "Skip all" calls onComplete with empty selection
- `excluded_existing > 0` renders the explanatory note
- empty `candidates` array renders the friendly "no candidates" message

`components/clients/discovery/__tests__/candidate-review-wizard.test.tsx`:
- starts at index 0 with first candidate pre-filled
- name field starts with `candidate.suggested_name`
- contacts list starts with `candidate.top_senders` mapped to `{name, email}`
- "Skip this" advances without calling `onSave`
- "Save & Next" calls `onSave` with the form data, then advances
- final candidate's primary button reads "Save & Finish" (not "Save & Next")
- after final, `onComplete` is called with `{ created: N }`

`components/clients/discovery/__tests__/client-discovery-flow.test.tsx`:
- full state-machine flow with MSW mocking `POST /discover-clients`
- pick lookback → scanning shown → response → review_list → select 1 → review_wizard → save → done
- error from mutation → error state with reconnect link
- closing modal mid-wizard discards selection

`pages/clients/__tests__/list.test.tsx` (extend if exists; create if not):
- empty state with Gmail connected: both "Add a client manually" and "Discover from Gmail" buttons render
- empty state without Gmail connected: only "Add a client manually" renders
- populated state with Gmail connected: header shows primary "Add client" + secondary "Discover from Gmail"
- populated state without Gmail connected: header shows only primary "Add client"

`components/clients/__tests__/client-form.test.tsx` (extend):
- new prop `initialContacts` pre-fills the contacts editor
- adding/removing contacts mutates state correctly
- submit payload includes the contacts array

## Acceptance criteria

A reviewer should be able to verify the slice is done by checking:

- [ ] `POST /api/v1/connectors/gmail/discover-clients` exists and accepts `{lookback_days: 30 | 90 | 365}`
- [ ] Endpoint returns the documented `DiscoveryResponse` shape
- [ ] Aggregator filters freemail + SaaS noise + own-domain + no-reply senders + already-linked domains
- [ ] Sort order is message_count desc, last_date desc as tiebreaker
- [ ] /clients empty state shows both CTAs when Gmail connected; only "Add client" otherwise
- [ ] /clients populated state shows primary + secondary buttons when Gmail connected
- [ ] Discovery flow walks through lookback → scanning → candidate list → review wizard → done
- [ ] Review wizard pre-fills name (heuristic) + contacts (top 3 senders)
- [ ] ClientForm now supports `initialContacts` and an inline contacts editor
- [ ] After completion, `/clients` list refreshes to show newly-created clients
- [ ] `pnpm test` and `pytest` are green; `pnpm build` clean

## Open questions

None — all design decisions were resolved during brainstorming.

## Future work (post-merge)

- **LLM-powered company naming** — opt-in batch via Haiku 4.5; adds ~3-5s but produces much better starting names ("Tata Communications" not "Tatacomms")
- **Industry / size auto-detection** — use email content samples + Bedrock to suggest
- **Background scheduled discovery** — weekly ARQ job that auto-scans and surfaces new candidates as a dashboard nudge
- **Per-agency configurable noise list** — agencies have their own real SaaS-domain clients
- **Pagination of existing-client check** — for agencies with 500+ clients
- **Slack discovery analogue** — same pattern, find #channels with new participants
