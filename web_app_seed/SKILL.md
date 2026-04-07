---
name: proposal-gen
description: "AI Proposal Copilot. Use this skill when asked to create a client proposal, pitch, quote, or commercial offer. Triggers include: 'new proposal', 'pitch for [client]', 'build a proposal', 'quote for [project]', 'prepare a pitch', or any request involving client proposal creation. Handles the full lifecycle: brief intake, template selection, client research, market benchmarking, cost modelling, narrative writing, interactive site generation, and formal document output."
license: Proprietary — Veeville Technologies
---

# proposal-gen — AI Proposal Copilot

## Overview

This skill transforms a client brief into a complete, defensible, interactive proposal with market-benchmarked pricing, a narrative covering letter, and multiple output formats (interactive website, DOCX, PDF, slide deck, one-pager, email draft).

The workflow mirrors a senior business development lead's process but executes in hours instead of days by automating research, benchmarking, cost modelling, and narrative generation — while keeping the human in the loop for all pricing and strategic decisions.

## When to Trigger

Use this skill when the user says any of:
- "new proposal", "pitch for [client]", "build a proposal"
- "quote for [project]", "prepare a pitch", "proposal for [client]"
- "how much should we charge for...", "cost estimate for..."
- Any request involving client proposal creation or pricing

Also trigger when a client brief document is uploaded (PDF, DOCX, email, spreadsheet) with an instruction to respond to it or create a proposal from it.

## File Structure

```
~/.claude/skills/proposal-gen/
├── SKILL.md                          # This file
├── rate-card/
│   └── veeville-rates-v2.json        # Service packages, hourly rates, multipliers
├── templates/
│   └── veeville-templates.json       # Strategy templates for different proposal types
├── research/
│   ├── benchmarks-cache.json         # Cached market research
│   └── [client-slug]/               # Per-client research folders
│       ├── findings.md
│       ├── benchmarks.md
│       └── brief.json
├── proposals/
│   └── [client-slug]-[date]/         # Generated proposal outputs
│       ├── proposal.docx
│       ├── cost-rationale.html
│       ├── site/
│       └── email-draft.md
├── examples/
│   └── tata-communications/          # Reference implementation
└── proposal-log.json                 # Track all proposals generated
```

---

## Workflow

Execute these steps in order. Each step has explicit inputs, outputs, and human review gates.

---

### Step 1: Brief Intake (INTERACTIVE — requires human input)

**Goal**: Understand what the client needs and extract a structured brief.

**If a document is uploaded** (PDF, DOCX, email, spreadsheet):
1. Parse the document to extract: client name, project description, deliverables mentioned, timeline references, budget signals, constraints, contact names
2. Present a summary of what was extracted
3. Ask the user to confirm or correct

**If no document — ask these questions one at a time** (don't dump all at once):

1. **Client**: "Who's the client? Tell me their name and what they do."
2. **Project**: "What do they need from us? Be as specific as possible about deliverables."
3. **Duration**: "Is this a one-time project or an ongoing engagement? What's the timeline?"
4. **Budget**: "Have they mentioned a budget or given any pricing signals?"
5. **Competition**: "Who else might be pitching? What's our angle — why should they pick us?"
6. **Relationship**: "Is this cold, warm intro, or existing client? Who's the decision-maker?"

**After gathering answers, produce a structured brief object:**

```json
{
  "client": {
    "name": "",
    "industry": "",
    "size": "",
    "contacts": []
  },
  "project": {
    "type": "",
    "deliverables": [
      {"category": "", "details": "", "quantity": 1}
    ],
    "timeline": "",
    "budget_signal": ""
  },
  "context": {
    "relationship": "cold_pitch | warm_intro | existing_client",
    "competition": "",
    "urgency": "low | medium | high",
    "decision_maker": ""
  }
}
```

Present this to the user: "Here's what I've captured. Anything to add or change?"

Save to `research/[client-slug]/brief.json`

---

### Step 1b: Template Selection (AUTO + HUMAN CONFIRM)

**Goal**: Select the right strategy template to govern the rest of the workflow.

1. **Load templates** from `templates/veeville-templates.json`

2. **Match the brief against templates**: Read the `auto_detect_signals` array in each template. Count keyword matches against the structured brief's project type, deliverables, and description.

3. **Present the best match to the user:**

   ```
   This looks like a [Template Name] project.

   Using this template shapes everything:
   - Questions I'll ask: [template-specific, e.g., "brand-focused"]
   - Research I'll do: [e.g., "brand identity benchmarks in India"]
   - How I write the letter: [e.g., "confident tone, opens with their brand problem"]
   - How I frame pricing: [e.g., "investment ROI framing"]
   - Site theme: [e.g., "bold"]

   Want a different template? Available options:
   1. Brand Identity / Rebrand
   2. Website / Digital Platform
   3. Anniversary / Milestone Campaign
   4. Creative Retainer
   5. Film & Video Production
   6. Employer Branding & Internal Comms
   7. Experiential Learning
   8. Exhibition / Environment Design

   Or I can skip the template and use defaults.
   ```

4. **User confirms or picks a different template.**

5. **If the user asks template-specific questions** from `brief_intake.required_questions` that weren't covered in Step 1, ask them now.

6. **Store the selected template ID** for use in Steps 2–6.

**If no template matches** (score is low across all templates), proceed without a template and use generic defaults for all steps.

---

### Step 2: Client Research (AUTOMATED — uses web search)

**Goal**: Build a knowledge base about the client so the proposal feels informed, not generic.

**Query selection**:
- If a template is active: use `template.research.client_queries`, replacing `{client}` and `{industry}` with actual values from the brief.
- If no template: use these defaults:
  - `[client name] company overview`
  - `[client name] recent news [year]`
  - `[client name] CEO leadership`

**Research the following using web_search:**

1. **Company overview**: Revenue, employee count, founding year, headquarters, public/private status
2. **Recent news**: Last 6 months of press coverage, product launches, leadership changes, funding rounds
3. **Industry position**: Market share, key competitors, industry trends
4. **Leadership**: CEO/MD name, key decision-makers, recent appointments
5. **Current brand/digital presence**: Visit their website (web_fetch), note design quality, messaging, technology signals
6. **Awards and recognition**: Any recent industry recognition

**Output format**: Save a markdown file to `research/[client-slug]/findings.md`

```markdown
# Client Research: [Client Name]

## Company Overview
- Founded: [year]
- Revenue: [amount]
- Employees: ~[number]
- Industry: [sector]
- Headquarters: [city]

## Recent Developments
- [bullet points from news search]

## Leadership
- CEO/MD: [name]
- Key contact: [name, role]

## Current Brand Assessment
- Website: [quality notes]
- Social presence: [notes]
- Design observations: [notes]

## Relevance to Our Proposal
- [2-3 observations that should inform our approach]

## Sources
- [list URLs used]
```

**Present key findings to the user**: "Here's what I found about [Client]. Anything I should know that isn't public?"

---

### Step 3: Market Benchmarking (AUTOMATED — uses web search)

**Goal**: Find published pricing data for each deliverable category so our cost model is defensible.

**Query selection**:
- If a template is active: use `template.research.benchmark_queries`, replacing `{country}`, `{year}`, `{service_type}` with actual values. Only benchmark the categories listed in `template.research.benchmark_categories`.
- If no template: benchmark every major deliverable category from the brief.

**Search query patterns:**
- `[service type] cost India 2025 2026 agency`
- `[service type] pricing guide agency`
- `[service type] agency retainer India enterprise`

**For each category, extract:**
- Low-end price (freelancer/budget tier)
- Mid-range price (boutique/mid-tier agency)
- High-end price (premium/enterprise agency)
- Source URL and publication date

**Aim for 3-5 data points per major deliverable category.**

**Output**: Save to `research/[client-slug]/benchmarks.md`

**IMPORTANT**: Never fabricate benchmark data. If real benchmarks can't be found for a specific service, note "No published benchmark found — estimate based on rate card and comparable services" and use the rate card as the basis.

---

### Step 4: Cost Model (AI-GENERATED, HUMAN-APPROVED)

**Goal**: Build a defensible pricing model with line-item detail.

**Process:**

1. **Load the rate card** from `rate-card/veeville-rates-v2.json`

2. **Build a deliverable index** by reading every package across all 15 offerings. For each package, index:
   - Package ID (the key, e.g., `fm_corporate_film_premium`)
   - Package description (used for semantic matching)
   - Base price
   - Typical hours
   - What's included

3. **Determine starting package list**:
   - If a template is active: start with `template.cost_model.typical_deliverables` as the suggested list. This pre-selects the most common packages for this proposal type.
   - If no template: start with an empty list and match everything from the brief.

4. **For each deliverable in the client brief**, find the best match in the index:

   **Match priority:**
   - **EXACT**: Brief says "brand guidelines" → a package description contains "brand guidelines" → direct match, use base price
   - **CLOSE**: Brief says "visual identity" → a package description contains "visual identity system" → close match, use base price, flag for review
   - **COMPOSITE**: Brief says "full rebrand" → matches a single bundled package (e.g., `bi_full_rebrand`)
   - **HOURLY**: No package match → estimate using relevant hourly rates × estimated hours → flag as "custom estimate — no standard package"

   **Do NOT rely on memorised package IDs.** Always read the rate card file fresh. The rate card may have been updated with new packages, renamed services, or changed prices since the last proposal.

5. **Apply multipliers**:
   - If a template is active: auto-apply `template.cost_model.default_multipliers`
   - Always evaluate: `complexity_enterprise` (if Fortune 500 / large enterprise), `urgency_rush` or `urgency_tight` (if timeline is compressed), `annual_bundle` (if engagement spans 6+ months), `existing_client` (if repeat client), `multi_theme` (if multiple creative directions), `batch_production` (if template-driven volume production)

6. **Calculate:**
   - Per-deliverable cost (base × quantity × multipliers)
   - Workstream subtotals (group related deliverables)
   - Overall subtotal
   - Bundle discount (if applicable)
   - Grand total (agency fees)
   - Pass-through costs at actuals (printing, hosting, media spend, travel, fabrication) with markup from rate card (`pass_through_markup`)
   - GST line (rate from rate card)

7. **Generate market comparison** for each major line item:
   - Our price vs. benchmark range (from Step 3)
   - Position indicator: "below market" / "at market" / "above market"

8. **Determine pricing framing**:
   - If a template is active: use `template.cost_model.pricing_framing` and `template.cost_model.pricing_anchor_text` to frame the total.
   - Options: `bundled_value` (compare against hiring separate agencies), `investment_roi` (frame against revenue/business impact), `cost_comparison` (compare against internal team), `time_savings` (compare against freelancer hours), `market_rate` (position against published benchmarks)

9. **Present to the user as a clear table** showing: deliverable, matched package ID, quantity, unit cost, total, market range, match quality (EXACT/CLOSE/HOURLY).

**⚠️ HUMAN REVIEW GATE: The cost model MUST be approved by the user before proceeding.**

Ask:
- "Does this pricing feel right?"
- "Any items you want to adjust up or down?"
- "Should I apply a different discount?"
- "Any deliverables to add or remove?"

Iterate until the user says the cost model is approved.

---

### Step 5: Narrative Generation (AI-GENERATED, HUMAN-REVIEWED)

Generate the following documents in sequence. Present each to the user for review before moving to the next.

**Template influence**: If a template is active, it governs the narrative style for all sub-steps below.

#### 5a. Covering Letter

**Strategy selection**:
- If a template is active: use `template.narrative.letter_strategy` — one of: `confident`, `warm`, `technical_showcase`, `research_heavy`, `relationship_builder`
- If no template: default to `confident`

**Opening instruction**:
- If a template is active: follow `template.narrative.letter_opening_instruction` exactly. This is the single most important instruction for letter quality.
- If no template: "Open with the CLIENT, not with Veeville. The first 2-3 paragraphs should be entirely about the client — their story, challenges, or recent developments drawn from Step 2 research."

**Universal rules (apply regardless of template):**
- Reference at least one specific, recent fact about the client (a news item, a milestone, a challenge they face) from Step 2 research.
- Middle section: position Veeville's fit — tell a story, don't list credentials.
- Close: confident CTA with a specific next step. No "we look forward to hearing from you" — propose a specific action.
- Sign off with "Karthik" (or the user's name if specified).
- Length: 400-600 words.

**Words to avoid**:
- If a template is active: also avoid words in `template.narrative.letter_avoid_words`
- Always avoid: "leverage", "synergy", "best-in-class", "world-class", "cutting-edge", "state-of-the-art", "we look forward to hearing from you", "please find attached"

**Generate 2 variants:**
1. **Primary**: Uses the template's letter_strategy
2. **Alternative**: Uses a contrasting strategy (if primary is `confident`, alternative is `warm`, and vice versa)

Present both. Let the user pick or blend.

#### 5b. Executive Summary

- Paragraph 1: What we're proposing (the engagement structure)
- Paragraph 2: Why this approach (strategic reasoning)
- Paragraph 3: The team and how we work
- Paragraph 4: Investment overview (one line with the total, framed using the template's `pricing_framing`)
- Length: 300-400 words

#### 5c. Scope Descriptions

**Detail level**:
- If a template is active: use `template.narrative.scope_detail_level` — one of: `brief` (50-100 words per deliverable), `standard` (100-150 words), `detailed` (150-250 words)
- If no template: default to `standard`

For EACH deliverable or deliverable group:
- **What's included**: Specific, concrete items (pulled from the matched package's `includes` field in the rate card, then expanded with project-specific detail)
- **What's excluded**: Prevents scope creep (e.g., "Printing costs not included")
- **Creative standard**: Number of options presented (from rate card's `standard_options_per_deliverable`), revision rounds (from `standard_revision_rounds`)
- **Timeline**: When this is delivered relative to project start
- **Dependencies**: What we need from the client to deliver this

#### 5d. Cost Rationale

**Depth**:
- If a template is active: use `template.narrative.rationale_depth` — one of: `light` (1-2 sentences per category), `standard` (150-250 words per category), `exhaustive` (250-400 words with multiple benchmarks)
- If no template: default to `standard`
- Only generate for proposals > ₹10L. For smaller proposals, skip this document.

For EACH major cost category:
- What the market typically charges (cite specific benchmarks from Step 3)
- What we charge and why it's fair
- What makes our approach unique or more valuable
- If applicable: volume efficiency or bundle savings explanation

#### 5e. Terms & Conditions

Load standard terms. Customise with:
- Client name
- Project-specific dates
- Payment schedule from rate card (`payment_terms`)
- GST notice (rate from rate card)
- IP transfer clause (from rate card)
- Proposal validity period (from rate card's `proposal_validity_days`)

---

### Step 6: Output Generation (AUTOMATED)

**Format selection**:
- If a template is active: generate the formats listed in `template.output.suggested_formats`
- If no template: generate `site` + `docx` + `email` as defaults
- User can always override and request additional formats

**Available output formats:**

| Format | Description | When |
|---|---|---|
| `site` | Interactive proposal website (scroll-driven, animated, analytics-tracked) | Proposals > ₹10L |
| `docx` | Formal Word document (10-section structure) | Always |
| `pdf` | PDF from DOCX (LibreOffice conversion) | On request |
| `pdf_designed` | PDF from HTML (beautiful designed report) | On request |
| `cost_rationale` | HTML document with benchmark cards and value comparison | Proposals > ₹10L |
| `one_pager` | Single A4 page executive summary | On request |
| `deck` | 15-20 slide PowerPoint presentation | On request |
| `email` | Introduction email draft (2 variants) | Always |

#### 6a. Interactive Proposal Website

**Site theme**:
- If a template is active: use `template.output.site_theme` — one of: `editorial`, `bold`, `minimal`, `dark`, `warm`
- If no template: default to `editorial`

**Sections to include**:
- If a template is active: include only `template.output.sections_include`, skip `template.output.sections_skip`
- If no template: include all standard sections

**Demo embed**:
- If a template is active AND `template.output.demo_embed_eligible` is true: ask the user "Want to include a live demo of [technology deliverable] in the proposal? This is a working prototype the client can interact with."
- If user says yes: generate a minimal prototype (chat component for AI deliverables, HTML mockup for websites, interactive chart for dashboards)

**Technical requirements:**
- Use DM Serif Display for headings, DM Sans for body
- Agency brand colours applied from rate card
- Scroll-triggered animations (fade up, 0.6s duration)
- Fully responsive (desktop, tablet, mobile)
- Include Plausible/Fathom analytics snippet
- Add `<meta name="robots" content="noindex">`
- Lighthouse score > 90

Save to: `proposals/[client-slug]-[date]/site/`

#### 6b. Formal Proposal Document (DOCX)

Use the docx skill (`/mnt/skills/public/docx/SKILL.md`) to generate a professional Word document.

**Document structure:**
1. Cover page
2. Table of contents
3. Covering letter
4. Executive summary
5. Scope of engagement (per-workstream with tables)
6. Cost summary (table with subtotals, discounts, total)
7. Team structure
8. Timeline
9. Terms & conditions
10. Contact information

Follow all docx skill rules: Arial font, proper heading styles, DXA table widths, ShadingType.CLEAR, no unicode bullets, validate with validate.py.

Save to: `proposals/[client-slug]-[date]/proposal.docx`

#### 6c. Cost Rationale Document (HTML)

Generate for proposals > ₹10L. A beautifully designed HTML document with:
- Per-category benchmark cards showing market range + our price + sources
- Value comparison table (our bundled price vs. à la carte from separate vendors)
- Savings calculation and percentage
- Source citations with URLs

Save to: `proposals/[client-slug]-[date]/cost-rationale.html`

#### 6d. One-Pager (HTML or PDF)

Single A4 page with: project title, 3-sentence problem statement, approach (3-5 bullets), key deliverables (listed), total investment with monthly equivalent, timeline summary, CTA with contact details.

Save to: `proposals/[client-slug]-[date]/one-pager.html`

#### 6e. Email Draft

Generate an introduction email in 2 variants:

**Confident**: "We've built something for you. Open this link..."
**Warm**: "Following our conversation, I've put together..."

Each includes: proposal URL (if site generated), PDF attachment reference, specific next step (propose a date/time), signature.

Save to: `proposals/[client-slug]-[date]/email-draft.md`

---

### Step 7: Review & Iterate (INTERACTIVE)

Present all outputs to the user:

1. Show the covering letter — "Here's the letter. Want to adjust the tone or add anything?"
2. Show the cost model summary — "Final pricing looks like this. All good?"
3. Show the email draft — "Pick a variant, or I'll blend them."
4. Confirm the interactive site content — "Ready to deploy?"

Make edits in-place. Regenerate specific sections without redoing the entire pipeline.

---

### Step 8: Deploy & Log (AUTOMATED)

1. **Deploy the interactive site** to Vercel/Netlify (if configured) or provide the files for manual deployment
2. **Copy all outputs** to `/mnt/user-data/outputs/` for download
3. **Log the proposal** in `proposal-log.json`:

```json
{
  "proposals": [
    {
      "client": "Client Name",
      "project": "Project Name",
      "date": "2026-04-06",
      "template_used": "anniversary-milestone-campaign",
      "total_value": 17415000,
      "currency": "INR",
      "status": "sent",
      "site_url": "proposals.veeville.com/client-name",
      "outputs": ["proposal.docx", "cost-rationale.html", "site/", "email-draft.md"],
      "win_status": null,
      "notes": ""
    }
  ]
}
```

4. **Remind the user** to update `win_status` when they hear back.

---

## Rules & Guardrails

### Rate Card
- Always read `rate-card/veeville-rates-v2.json` fresh at the start of every proposal. Never rely on memorised prices — the file may have been updated.
- Match deliverables to packages using the `description` field, not by memorising package IDs. The rate card may have new packages, renamed services, or changed prices.
- Round all prices to nearest ₹10,000 for clean presentation.

### Templates
- Always read `templates/veeville-templates.json` at the start of every proposal.
- Template selection happens AFTER brief intake, BEFORE research.
- If no template matches (low keyword overlap), proceed with generic defaults — don't force a template.
- The user can override any template-driven decision at any step.
- Template selections are logged in `proposal-log.json` for future win/loss analysis.

### Research Integrity
- NEVER fabricate benchmark data. If real benchmarks can't be found, state this clearly.
- Always cite sources (URL + date) for benchmark claims.
- Prefer recent data (2025-2026) over older sources.
- Prefer Indian sources for India-based proposals.

### Pricing Integrity
- NEVER generate final pricing without human approval.
- Always present the cost model as a clear table with line items.
- Always show market comparison alongside our pricing.

### Narrative Quality
- Covering letters ALWAYS open with the client, never with Veeville.
- Reference at least one specific, researched fact about the client.
- Never use: "leverage", "synergy", "best-in-class", "world-class", "cutting-edge", "state-of-the-art", "we look forward to hearing from you", "please find attached", "our team of experienced professionals". Write like a human.
- Apply Veeville's 3-option creative standard in scope descriptions where applicable.
- Generate 2 letter variants for every proposal. Let the user choose.

### Technical Standards
- All FastAPI code follows MVVM architecture.
- DOCX generation follows the docx skill best practices.
- Interactive sites must be fully responsive and score > 90 on Lighthouse.
- No client data should be committed to public repositories.

### Output Standards
- Every proposal gets minimum: DOCX + email draft.
- Proposals > ₹10L also get: interactive site + cost rationale.
- All documents include Veeville branding and confidentiality notice.
- All files saved to `proposals/[client-slug]-[date]/` for organised retrieval.
