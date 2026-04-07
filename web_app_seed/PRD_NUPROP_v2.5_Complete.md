# NUPROP — Product Requirements Document
## AI-Powered Proposal Copilot for Design & Professional Services Agencies

**Version**: 2.5
**Author**: Veeville Technologies
**Date**: April 2026
**Status**: Phase A (Internal Tool) → Phase C (Micro-SaaS)

---

## Table of Contents

1. [Product Vision & Problem Statement](#1-product-vision--problem-statement)
2. [Market Context & Competitive Landscape](#2-market-context--competitive-landscape)
3. [Competitive Moat & Defensibility](#3-competitive-moat--defensibility)
4. [Product Architecture](#4-product-architecture)
5. [Phase A: Claude Code Skill (Internal Tool)](#5-phase-a-claude-code-skill)
6. [Phase C: NUPROP Platform (Micro-SaaS)](#6-phase-c-nuprop-platform)
7. [Strategy Template System](#7-strategy-template-system)
8. [The Proposal Engine — AI Pipeline](#8-the-proposal-engine--ai-pipeline)
9. [Output Options — Comprehensive Format Guide](#9-output-options--comprehensive-format-guide)
10. [Interactive Proposal Site Generator](#10-interactive-proposal-site-generator)
11. [Document Generation Engine](#11-document-generation-engine)
12. [Analytics & Tracking](#12-analytics--tracking)
13. [Data Model](#13-data-model)
14. [Tech Stack](#14-tech-stack)
15. [User Experience Flows](#15-user-experience-flows)
16. [Pricing & Business Model](#16-pricing--business-model)
17. [Unit Economics](#17-unit-economics)
18. [Roadmap & Milestones](#18-roadmap--milestones)
19. [Narrative Quality Standards](#19-narrative-quality-standards)
20. [Proposal Delivery Playbook](#20-proposal-delivery-playbook)
21. [Success Metrics](#21-success-metrics)
22. [Appendices](#appendices)

---

## 1. Product Vision & Problem Statement

### Vision Statement

**NUPROP is an AI copilot that turns a client brief into a complete, defensible, interactive proposal — with market-benchmarked pricing, a narrative covering letter, and an interactive web presentation — in hours, not days.**

PandaDoc helps you *send* proposals. NUPROP helps you *win* them.

### The Problem

Professional services firms (design agencies, consulting firms, architecture studios, technology consultancies) spend enormous effort on proposals that yield uncertain results:

- **960+ hours per year** spent on proposals by the average firm (OpenAsset 2025)
- **33 hours per RFP** on average, down from 35 (Loopio 2026 Benchmark Report)
- **51% of firms** still write proposals from scratch "sometimes" (OpenAsset)
- **Only 25%** of firms hit all their submission goals
- **39% average win rate** across industries (Loopio 2026)
- **87% of proposals** go through 2–5 rounds of review
- **64% of teams** still submit proposals on the due date

The hidden costs are worse: unbillable hours, senior creative time diverted from client work, formatting struggles in Word/InDesign, inconsistent pricing across proposals, and the morale drain of repetitive proposal assembly.

### What Existing Tools Miss

Every proposal tool on the market — PandaDoc, Proposify, Qwilr, Better Proposals — solves the *assembly* and *delivery* problem: templating, drag-and-drop editing, e-signatures, tracking. None of them solve the *thinking* problem:

| Proposal Stage | Time Spent | Existing Tool Support | NUPROP Support |
|---|---|---|---|
| Understanding the brief | 15% | None | AI brief analysis + clarifying questions |
| Researching the market/client | 20% | None | Automated web research + benchmarking |
| Building the cost model | 20% | Pricing tables only | AI cost modelling with market justification |
| Writing the narrative | 25% | Basic AI rewrite | Full narrative generation (letter, rationale, scope) |
| Designing the presentation | 15% | Templates | Interactive site generator |
| Tracking & follow-up | 5% | Yes (well-served) | Basic analytics |

NUPROP focuses on the 80% of effort that existing tools ignore.

### Target Users

**Primary (Phase A)**: Veeville Technologies internal team — Karthik and designers using Claude Code to generate proposals for agency clients.

**Primary (Phase C)**: Founders, creative directors, and business development leads at design agencies, branding studios, technology consultancies, and professional services firms with 2–50 employees. These are people who pitch for work, not people who send contracts.

**Anti-target**: Enterprise sales teams doing high-volume transactional proposals (PandaDoc's market), legal teams managing contracts (DocuSign's market), government RFP responders (Loopio's market).

---


## 2. Market Context & Competitive Landscape

### Direct Competitors (Proposal Tools)

| Tool | Price | Strength | Weakness vs NUPROP |
|---|---|---|---|
| PandaDoc | $35–65/user/mo | Full doc lifecycle, CRM integration | No AI thinking, template-dependent, PDF output |
| Proposify | $49/user/mo | Beautiful templates, analytics | No research, no cost justification, no web output |
| Qwilr | $35–59/user/mo | Web-based proposals, interactive pricing | No AI narrative, no market research, no covering letter |
| Better Proposals | $19–49/user/mo | Simple, fast, affordable | No AI, no cost benchmarking, basic output |
| AiDocX | ~$20/mo | AI contract generation | Contract-focused, not proposal-focused |

### Indirect Competitors (AI Writing Tools)

| Tool | What It Does | Gap |
|---|---|---|
| Claude / ChatGPT (direct) | General-purpose writing | No proposal-specific workflow, no pricing engine, no web output |
| Jasper / Copy.ai | Marketing copy generation | No proposal structure, no research, no cost modelling |
| Scribbl / Sembly | Meeting-to-proposal | Discovery only, no full proposal generation |

### NUPROP's Unique Position

No product on the market combines:
1. **AI brief analysis** — understands a client brief and asks clarifying questions
2. **Market research** — automatically searches for pricing benchmarks in the relevant industry and geography
3. **Cost modelling with justification** — builds a pricing model and writes a rationale for every line item
4. **Narrative generation** — writes a covering letter, executive summary, and scope descriptions with a persuasive arc
5. **Interactive web output** — generates a hosted proposal website, not just a PDF
6. **Document generation** — also produces DOCX/PDF for formal submission

This is a category of one.

---


## 3. Competitive Moat & Defensibility

### Why PandaDoc Can't Just Add This

The question every investor and competitor will ask: "What stops PandaDoc from adding AI research to their product next quarter?"

**Four structural moats:**

**1. Architecture mismatch.** PandaDoc, Proposify, and Qwilr are document platforms. Their output is a styled document (PDF or web page). NUPROP's output is a *generated application* — a hosted website with scroll animations, interactive cost cards, embedded demos, and analytics. Retrofitting a document editor to generate websites is an architecture rewrite, not a feature addition. Qwilr is the closest (web-based output), but their web pages are assembled from drag-and-drop blocks, not AI-generated from narrative content.

**2. Research pipeline.** NUPROP's AI researches the client (company news, leadership, financials) and the market (pricing benchmarks by service category and geography) before generating anything. This requires web search integration, source quality evaluation, and synthesis — capabilities that document tools have never built. PandaDoc's AI features are limited to rewriting existing text; they don't create knowledge.

**3. Template intelligence.** NUPROP's templates encode *strategy*, not layout. The "Anniversary Campaign" template changes which questions the AI asks, which benchmarks it searches for, how it frames pricing (bundled value vs. ROI vs. cost comparison), and what tone the covering letter takes. A PandaDoc template changes fonts and section order. The strategic layer improves with every proposal as win/loss data feeds back.

**4. Accumulated learning.** After 100 proposals, NUPROP knows: which price ranges win for each industry, which letter styles get the most engagement, which sections clients spend the most time on, and what the average time-to-response is for won proposals. This data flywheel makes the product more valuable over time and creates switching costs. A new entrant starts at zero.

### What NUPROP Does NOT Compete With

- **CRM integration** — Salesforce, HubSpot own this. NUPROP reads from them (Phase D), doesn't replace them.
- **E-signatures** — DocuSign, PandaDoc own this. NUPROP links to them post-acceptance.
- **Contract management** — Ironclad, Juro own this. NUPROP generates proposals, not contracts.
- **Government RFPs** — Loopio, RFPIO own this. NUPROP is for considered sales, not compliance-heavy bid responses.

NUPROP's moat is narrow and deep: it's the best tool for turning a brief into a winning proposal for professional services firms.

---


---


## 4. Product Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    NUPROP PLATFORM                      │
├─────────────┬──────────────┬──────────────┬──────────────┤
│  INTAKE     │  AI ENGINE   │  OUTPUT      │  TRACKING    │
│             │              │              │              │
│ Brief       │ Brief        │ Interactive  │ View         │
│ Parser      │ Analyzer     │ Proposal     │ Tracking     │
│             │              │ Site         │              │
│ Rate Card   │ Market       │              │ Engagement   │
│ Manager     │ Researcher   │ DOCX / PDF   │ Scoring      │
│             │              │              │              │
│ Template    │ Cost Model   │ Slide Deck   │ Win/Loss     │
│ Selector    │ Builder      │              │ Learning     │
│             │              │ One-Pager    │              │
│ Portfolio   │ Narrative    │              │ Follow-up    │
│ Library     │ Writer       │ Email        │ Suggestions  │
│             │              │ Composer     │              │
│ Client      │              │              │              │
│ Profiles    │              │ Notion/GDocs │              │
└─────────────┴──────────────┴──────────────┴──────────────┘
                     │
                     ▼
              ┌──────────────┐
              │ Claude API   │
              │ (Sonnet 4.6) │
              │              │
              │ + Web Search │
              └──────────────┘
```

### Core Principles

1. **AI does the thinking, human does the deciding.** NUPROP generates options; the user picks, edits, and approves.
2. **Research-backed, not template-stuffed.** Every price, every claim, every comparison is sourced from real market data.
3. **Multiple output formats.** The same proposal content renders as an interactive website, DOCX, PDF, slide deck, one-pager, or email — from one source of truth.
4. **Conversational workflow.** The user interacts via chat, not forms. The AI asks questions, proposes structures, and iterates in real-time.
5. **Portfolio-aware.** Over time, NUPROP learns from your past proposals, win rates, and client feedback.
6. **Single LLM.** Claude handles everything. No multi-provider complexity.

### LLM Decision: Claude Only

**Decision**: Use Claude Sonnet 4.6 for all pipeline steps. Use Claude Opus 4.6 for high-value pitches (>₹50L).

**Rationale**: Our cost analysis of the most exhaustive proposal type (Tata Communications — year-long, 3 themes, 35+ deliverables, full research and benchmarking) showed total API cost of $2.62 (₹220) on Sonnet 4.6. At this cost level, maintaining a second LLM provider (Qwen on Modal) saves ~₹150 per proposal while adding significant architectural complexity. The complexity cost exceeds the savings.

**Cost per proposal by model**:
| Model | Cost | Use When |
|---|---|---|
| Sonnet 4.6 | $2.62 / ₹220 | Default for all proposals |
| Sonnet 4.6 + caching | $1.40 / ₹117 | After first proposal (rate card cached) |
| Opus 4.6 | $4.37 / ₹365 | Pitches above ₹50L where narrative quality is critical |
| Opus 4.6 + caching | $2.30 / ₹192 | High-value with repeated elements |

**Prompt caching architecture**: The rate card JSON (~4,000 tokens), system prompt (~2,000 tokens), and active template (~1,500 tokens) are identical across proposals for the same agency. With prompt caching enabled (90% discount on repeated context), these ~7,500 tokens cost $0.002 per call instead of $0.023. Over a typical 8-call proposal pipeline, this saves ~$0.17 — a 7% reduction that compounds at platform scale.

---


---


## 5. Phase A: Claude Code Skill (Internal Tool)

### Overview

Phase A is a Claude Code skill (`~/.claude/skills/proposal-gen/`) that codifies the proposal workflow into a repeatable, scriptable process. No UI, no platform — just a structured skill file that Claude Code follows.

### Skill Structure

```
~/.claude/skills/proposal-gen/
├── SKILL.md                    # Master instructions
├── templates/
│   ├── covering-letter.md      # Letter template with variable slots
│   ├── cost-rationale.md       # Justification document template
│   ├── executive-summary.md    # Summary template
│   └── scope-section.md        # Per-deliverable scope template
├── rate-card/
│   ├── veeville-rates.json     # Veeville's standard rate card
│   └── multipliers.json        # Complexity/urgency multipliers
├── research/
│   └── benchmarks-cache.json   # Cached market research data
├── output-templates/
│   ├── proposal-site/          # HTML template for interactive site
│   │   ├── index.html
│   │   ├── styles.css
│   │   └── components/
│   ├── docx-template.js        # Node.js docx generation script
│   └── pdf-styles.css          # Print stylesheet
└── examples/
    └── tata-communications/    # The Tata Comms proposal as reference
        ├── brief.md
        ├── output/
        └── research-notes.md
```

### SKILL.md — Master Instructions

```markdown
# proposal-gen — AI Proposal Copilot Skill

## Trigger
Use this skill when Karthik says any of:
- "new proposal", "pitch for [client]", "build a proposal"
- "quote for [project]", "prepare a pitch"
- Any request involving client proposal creation

## Workflow

### Step 1: Brief Intake (INTERACTIVE)
Ask the user for the following, one question at a time:

1. **Client name and context**: Who are they? What do they do?
   What's their approximate size/industry?
2. **What they need**: What's the project or engagement? Be as
   specific as possible about deliverables.
3. **Duration**: Is this a one-time project or ongoing engagement?
   Timeline?
4. **Budget signals**: Have they mentioned a budget? Any constraints?
5. **Competition**: Who else might be pitching? What's our angle?
6. **Relationship**: Is this a cold pitch, warm intro, or existing
   client? Who's the decision-maker?
7. **Special requirements**: Any uploaded documents (brief, RFP,
   previous correspondence)?

If the user uploads a document (PDF, DOCX, email), parse it to
extract the brief and pre-fill answers.

### Step 2: Client Research (AUTOMATED)
Using web_search, research:
- The client's company (revenue, employees, recent news, leadership)
- Their industry's current landscape
- Any recent press, awards, or announcements
- Their current website/brand (screenshot if possible)

Save research to `research/[client-slug]/findings.md`

### Step 3: Market Benchmarking (AUTOMATED)
For each deliverable category in the brief, search for:
- Published pricing benchmarks for that service in the client's
  geography
- Comparable agency case studies with known pricing
- Industry reports on typical costs

Save to `research/[client-slug]/benchmarks.md`

Aim for 3-5 benchmark data points per major deliverable category.

### Step 4: Cost Model (AI + HUMAN)
Load `rate-card/veeville-rates.json` and build a cost model:

1. Map each deliverable to rate card items
2. Apply complexity multipliers based on brief analysis
3. Calculate subtotals per workstream
4. Apply bundle/annual engagement discounts
5. Generate "at-actuals" estimates for pass-through costs
6. Calculate per-deliverable market comparison

Present the cost model to the user as a table. Ask:
- "Does this pricing feel right?"
- "Any items you want to adjust?"
- "Should I apply a discount?"

Iterate until approved.

### Step 5: Narrative Generation (AI)
Generate the following documents in sequence:

#### 5a. Covering Letter
- Open with the CLIENT, not with Veeville
- Reference specific details from client research (recent news,
  milestones, challenges)
- Explain why Veeville is the right fit (don't list credentials —
  tell a story)
- End with a clear, confident CTA
- Tone: warm, confident, specific, not salesy
- Length: 400-600 words

#### 5b. Executive Summary
- What we're proposing (2 paragraphs)
- Why this approach (1 paragraph)
- Investment overview (1 paragraph)
- Length: 300-400 words

#### 5c. Scope Descriptions
For each deliverable:
- What's included (specific, not vague)
- What's excluded (prevents scope creep)
- Number of creative options / revision rounds
- Timeline / dependencies
- Market benchmark reference

#### 5d. Cost Rationale
For each major cost category:
- What the market charges (with source)
- What we charge and why it's fair
- What makes our approach unique / valuable
- Length: 150-250 words per category

#### 5e. Terms & Conditions
Standard payment terms, IP transfer, cancellation
(use template, customise dates and percentages)

### Step 6: Output Generation (AUTOMATED)

Generate three outputs:

#### 6a. Interactive Proposal Website
- Use `output-templates/proposal-site/` as base
- Populate with generated content
- Include: cover, letter, scope cards, cost breakdown,
  timeline, CTA
- Deploy to `[client-slug].veeville.com`
- Include basic analytics (Plausible/Fathom snippet)

#### 6b. Formal Proposal Document (DOCX)
- Use `docx-template.js` to generate
- Professional formatting with Veeville branding
- Include all sections, tables, terms
- Validate with docx skill's validate.py

#### 6c. Cost Rationale Document (HTML or DOCX)
- Market-benchmarked justification for every line item
- Designed to be shared alongside the proposal
- or internal reference for negotiation

### Step 7: Review & Iterate (INTERACTIVE)
Present all outputs to the user. Ask:
- "Want to adjust any pricing?"
- "Should I rephrase anything in the letter?"
- "Ready to deploy the site?"

Make edits in-place. Regenerate outputs as needed.

### Step 8: Deploy (AUTOMATED)
- Deploy proposal site to Fly.io
- Generate shareable URL
- Create email draft introducing the proposal
- Log the proposal in `research/proposal-log.json`

## Rules
- NEVER fabricate benchmark data. If you can't find real
  benchmarks, say "benchmark data not found" and estimate
  based on rate card.
- ALWAYS present the cost model for human approval before
  generating documents.
- ALWAYS open covering letters with the client, not with Veeville.
- Use Veeville's 3-option creative standard where applicable.
- Apply MVVM architecture for any FastAPI components.
```

### Rate Card Schema (veeville-rates.json)

```json
{
  "version": "2026-Q2",
  "currency": "INR",
  "hourly_rates": {
    "project_director": 8000,
    "creative_director": 6000,
    "senior_designer": 4000,
    "motion_designer": 4500,
    "copywriter": 3500,
    "web_developer": 5000,
    "video_producer": 5500,
    "event_coordinator": 3000
  },
  "package_rates": {
    "brand_identity": {
      "base": 200000,
      "description": "Logo + colour + typography + guidelines (single theme)",
      "includes": "3 concepts, 2 revision rounds, production-ready files",
      "typical_hours": 50
    },
    "email_template_responsive": {
      "base": 35000,
      "description": "Single responsive HTML email with 3 creative options",
      "typical_hours": 10
    },
    "social_media_post_batch": {
      "base": 60000,
      "description": "10 posts with copy, hashtags, scheduling notes, 3 options each",
      "typical_hours": 16
    },
    "corporate_video_basic": {
      "base": 150000,
      "description": "2-3 min video, single location, 1-camera, basic edit",
      "typical_hours": 30
    },
    "corporate_video_premium": {
      "base": 500000,
      "description": "3-5 min cinematic, multi-location, 2-camera, motion graphics, licensed music",
      "typical_hours": 80
    },
    "documentary_episode": {
      "base": 500000,
      "description": "5-8 min episode, research + interviews + edit",
      "typical_hours": 100
    },
    "website_microsite": {
      "base": 300000,
      "description": "5-10 page responsive site, CMS-driven",
      "typical_hours": 60
    },
    "ai_chatbot_rag": {
      "base": 800000,
      "description": "RAG-powered conversational interface with custom knowledge base",
      "typical_hours": 160
    },
    "event_creative_small": {
      "base": 150000,
      "description": "Event branding, invitation, signage, run-of-show",
      "typical_hours": 35
    },
    "event_creative_flagship": {
      "base": 600000,
      "description": "Full event creative: stage, branding, collateral, on-ground direction",
      "typical_hours": 120
    },
    "presentation_template": {
      "base": 50000,
      "description": "PowerPoint master template with 15+ slide layouts",
      "typical_hours": 12
    },
    "coffee_table_book_design": {
      "base": 600000,
      "description": "100-150 pages, editorial + layout + print-ready",
      "typical_hours": 120
    },
    "communications_plan": {
      "base": 80000,
      "description": "Channel strategy + messaging framework + amplification ideas",
      "typical_hours": 20
    },
    "monthly_creative_retainer": {
      "base": 350000,
      "description": "Dedicated designer + copywriter + PM, ~120 hours/month",
      "typical_hours": 120
    }
  },
  "multipliers": {
    "urgency_rush": 1.5,
    "complexity_high": 1.3,
    "complexity_enterprise": 1.5,
    "multi_theme": 0.7,
    "annual_bundle": 0.88,
    "existing_client": 0.95
  },
  "pass_through_markup": 0.10,
  "standard_options_per_deliverable": 3,
  "standard_revision_rounds": 2,
  "gst_rate": 0.18
}
```

---


## 6. Phase C: NUPROP Platform (Micro-SaaS)

### Overview

Phase C transforms the Claude Code skill into a hosted web application that other agencies can use. The core AI pipeline remains the same; the wrapper becomes a self-service platform.

### Platform Features

#### 6.1 Onboarding & Setup

**Agency Profile Setup** (first-time, 10 minutes):
- Agency name, logo, brand colours, fonts
- Contact information, address
- Rate card entry (guided wizard or CSV upload)
- Portfolio upload (case studies, past work images)
- Brand voice calibration: paste 2-3 past proposals or marketing copy; AI analyses tone, vocabulary, sentence structure to establish the agency's writing voice
- Standard terms & conditions template
- Payment preferences (currency, GST/VAT rate, payment terms)

**Client CRM** (lightweight):
- Client profiles: name, industry, contacts, past proposals
- Tag system: industry, size, relationship status
- Notes and follow-up reminders
- NOT a full CRM — no pipeline stages, no deal tracking (that's Salesforce/HubSpot territory)

#### 6.2 Proposal Builder (The Core Product)

This is a **conversational interface**, not a form. The user chats with NUPROP, which guides them through the proposal creation process.

**The Conversation Flow**:

```
NUPROP: "Hi! Let's build a proposal. Who's the client?"

USER: "Titan Company — they're a Tata Group watch/jewellery brand.
They want a complete rebrand of their digital presence."

NUPROP: "Got it. Let me pull up some background on Titan..."
[AI researches Titan: revenue, recent campaigns, competitors,
digital presence]
"Titan Company — ₹38,000 Cr revenue, publicly traded, known for
Tanishq, Fastrack, Titan Eye Plus. Recent focus on premiumisation
and D2C channels. Their current website was last redesigned in 2023.

A few questions to shape the proposal:
1. Is this a full rebrand or a digital-only refresh?
2. Which brands are in scope — parent Titan, Tanishq, Fastrack, all?
3. What's the expected timeline?
4. Any budget range they've shared?"

USER: "Digital refresh for parent brand only. 4 months.
They mentioned 15-20L budget."

NUPROP: "Here's what I'd recommend for scope at that budget..."
[AI maps deliverables from rate card, applies multipliers,
suggests scope that fits the budget signal]

"I've found some market benchmarks:
- Full digital brand refresh (India, mid-tier agency): ₹12-25L
- Website redesign (enterprise, 20+ pages): ₹8-15L
- Brand guidelines update: ₹2-6L

Your budget of ₹15-20L sits right in the mid-market range.
Here's a proposed scope..."

[Presents cost model as interactive cards]

USER: "Looks good, but add social media templates."

NUPROP: "Done. Updated total: ₹18,40,000.
Ready to generate the covering letter?"

USER: "Yes, make it confident but not arrogant."

NUPROP: [Generates covering letter, presents for review]
"Here's a draft. The opening references Titan's recent
premiumisation push — I found a LiveMint article from last month.
Want to adjust anything?"

[Iterates until approved]

NUPROP: "All sections are ready. Generating your outputs now..."
[Creates interactive site + DOCX + cost rationale]
"Your proposal is live at titan-refresh.youragency.nuprop.app
PDF is ready for download. Want me to draft the introduction email?"
```

#### 6.3 Rate Card Manager

**Features**:
- Guided wizard for entering service rates (hourly or per-deliverable)
- Import from CSV/spreadsheet
- Multiplier configuration: urgency, complexity, client size, geographic
- Package builder: combine multiple services into named packages
- Version history: track rate changes over time
- "Smart pricing" suggestions based on market benchmarks (web research) — e.g., "Your website design rate is 30% below the Indian market median. Consider adjusting."

#### 6.4 Portfolio & Content Library

**Case Studies**:
- Upload past work with images, client name, industry, scope, outcome
- AI auto-generates "relevance scores" when building proposals — surfaces the most relevant case studies for each new client
- Privacy controls: mark case studies as "internal only" (for AI reference) vs. "client-facing" (can be included in proposals)

**Content Blocks**:
- Reusable text blocks: team bios, methodology descriptions, process explanations
- AI learns from these blocks to maintain consistent voice across proposals
- Version tracking: know which content block was used in which proposal

**Image Library**:
- Upload team photos, office images, past work screenshots, mockups
- Auto-tagged by AI for easy retrieval
- Used in interactive site and document generation

#### 6.5 Proposal Templates

**Not layout templates — *strategy* templates.**

Each template encodes a proposal *approach*, not just a visual style:

- **The Confident Pitch**: Bold covering letter, three creative options prominently displayed, investment section framed as ROI, no apology for pricing
- **The Research-Heavy**: Opens with market analysis, positions the proposal as a strategic response to industry trends, includes competitor benchmarking
- **The Relationship Builder**: Warm covering letter, heavy on "we understand you" language, references past conversations, positions as partnership not transaction
- **The Technical Showcase**: Demo-first (like the Tata Communications pitch), includes live prototypes, technical architecture diagrams, emphasises capability proof
- **The Value Comparison**: Side-by-side comparison of what you're offering vs. what the market charges, emphasises savings and bundled value

Users can create custom templates by combining elements from the defaults.

#### 6.6 Interactive Proposal Site Generator

This is the *output* that makes NUPROP different from every competitor. Instead of a PDF, the client receives a URL.

**Site Generator Features**:

- **Scroll-driven narrative**: Sections reveal on scroll with smooth animations
- **Interactive cost cards**: Click to expand, see scope details and market benchmarks
- **Visual timeline**: Phase-by-phase rollout with expandable milestones
- **Embedded portfolio**: Relevant case studies displayed as a gallery
- **Team section**: Auto-populated from agency profile with role assignments
- **CTA section**: Meeting scheduler embed (Calendly/Cal.com), download PDF button, contact details
- **Analytics**: View tracking, time-per-section, scroll depth, return visits

**Customisation**:
- Agency brand colours and fonts applied automatically from profile
- Choose from 5 visual themes (editorial, bold, minimal, dark, warm)
- Custom domain support: `proposals.youragency.com/client-name`
- Password protection for sensitive proposals
- Expiry dates for time-limited offers

**Technical Implementation**:
- Static site generation (Astro or 11ty) deployed to Fly.io
- Each proposal gets its own subdomain or path
- No server needed after deployment — pure static hosting
- Analytics via lightweight script (Plausible/Fathom)

#### 6.7 Document Generation

**DOCX Output**:
- Professional formatting using docx-js (same engine as the Tata Communications proposal)
- Auto-populated with agency branding, client details, scope tables, cost model
- Table of contents, headers/footers, page numbers
- Validated and error-free output

**PDF Output**:
- Generated from DOCX via LibreOffice or from HTML via Puppeteer
- Print-optimised layout
- Optional: beautifully designed HTML-to-PDF using a custom print stylesheet (closer to the cost rationale document aesthetic)

**Email Draft**:
- AI-generated introduction email to send with the proposal link
- Three variants: formal, confident, warm
- Pre-formatted for Gmail/Outlook with the proposal URL embedded

#### 6.8 Proposal Analytics Dashboard

**What's tracked** (per proposal):
- First view timestamp and viewer IP/location (anonymised)
- Total views and unique visitors
- Time spent per section
- Scroll depth (how far they got)
- Which cost cards were expanded
- Whether the PDF was downloaded
- Return visits (shows sustained interest)
- Referral source (did they forward it?)

**Dashboard views**:
- Per-proposal detail view (timeline of engagement)
- Portfolio view (all proposals, sortable by date, status, engagement)
- Win/loss tracking: mark proposals as Won / Lost / Pending / Expired
- Win rate calculation by industry, client size, proposal value
- Average time from send to client response

**Notifications**:
- Real-time alerts (email or Slack): "Titan Company just opened your proposal"
- "They've spent 4 minutes on the Investment section"
- "They downloaded the PDF — good sign"
- Daily digest: proposals viewed in the last 24 hours

---


## 7. Strategy Template System — Full Specification

Templates in NUPROP are not layout templates. They encode *proposal strategy* — changing how the AI thinks, researches, writes, and prices.

### Template Schema

```json
{
  "id": "string",
  "name": "string",
  "description": "string",
  "category": "brand | technology | campaign | retainer | consulting",

  "brief_intake": {
    "required_questions": ["array of questions specific to this proposal type"],
    "optional_questions": ["array of follow-up questions if time allows"],
    "auto_detect_signals": ["keywords that trigger this template"]
  },

  "research": {
    "client_queries": ["search query templates with {client} and {industry} placeholders"],
    "benchmark_queries": ["search query templates for pricing research"],
    "benchmark_categories": ["rate card categories to benchmark"]
  },

  "cost_model": {
    "typical_deliverables": ["rate card item IDs commonly used"],
    "default_multipliers": ["multiplier IDs to consider"],
    "pricing_framing": "bundled_value | investment_roi | cost_comparison | time_savings | market_rate",
    "pricing_anchor_text": "how to frame the total for this proposal type"
  },

  "narrative": {
    "letter_strategy": "confident | warm | technical_showcase | research_heavy | relationship_builder",
    "letter_opening_instruction": "specific instruction for how the letter should open",
    "letter_tone_words": ["adjective descriptors for the tone"],
    "letter_avoid_words": ["phrases to never use in this template type"],
    "scope_detail_level": "brief | standard | detailed",
    "rationale_depth": "light | standard | exhaustive"
  },

  "output": {
    "site_theme": "editorial | bold | minimal | dark | warm",
    "sections_include": ["section IDs to include"],
    "sections_skip": ["section IDs to skip"],
    "suggested_formats": ["site", "docx", "pdf", "one_pager", "deck"],
    "demo_embed_eligible": true | false
  }
}
```

### Built-in Templates

**1. Design Agency — Brand Identity / Rebrand**
```json
{
  "id": "design-rebrand",
  "category": "brand",
  "brief_intake": {
    "required_questions": [
      "What's the trigger for the rebrand — merger, new leadership, repositioning, growth?",
      "Which brand elements are in scope — logo, full identity, guidelines, collateral?",
      "Who are their top 3 competitors visually?",
      "Any elements they absolutely want to keep?"
    ],
    "auto_detect_signals": ["rebrand", "brand identity", "visual refresh", "logo redesign", "brand guidelines"]
  },
  "narrative": {
    "letter_strategy": "confident",
    "letter_opening_instruction": "Start with the client's current brand perception problem. Reference a specific competitor who's doing it better. Position the rebrand as a strategic weapon, not cosmetic."
  },
  "cost_model": {
    "pricing_framing": "investment_roi",
    "pricing_anchor_text": "Frame against revenue impact of stronger brand recognition. Branded companies grow 3-4× faster."
  },
  "output": {
    "site_theme": "bold",
    "demo_embed_eligible": false
  }
}
```

**2. Technology Consultancy — Development Project**
```json
{
  "id": "tech-project",
  "category": "technology",
  "brief_intake": {
    "required_questions": [
      "What's the business problem this technology solves?",
      "What's the current tech stack / existing system?",
      "Are there integration requirements?",
      "What does success look like — metrics, KPIs?"
    ],
    "auto_detect_signals": ["website", "app", "platform", "AI", "chatbot", "dashboard", "development", "build"]
  },
  "narrative": {
    "letter_strategy": "technical_showcase",
    "letter_opening_instruction": "Start with the technical challenge. Show you understand the architecture problem. Reference a similar system you've built."
  },
  "cost_model": {
    "pricing_framing": "cost_comparison",
    "pricing_anchor_text": "Compare against cost of building an internal team (3 engineers × N months) vs. our fixed-price delivery."
  },
  "output": {
    "site_theme": "dark",
    "demo_embed_eligible": true
  }
}
```

**3. Corporate Campaign — Anniversary / Milestone**
```json
{
  "id": "anniversary-campaign",
  "category": "campaign",
  "brief_intake": {
    "required_questions": [
      "What's the milestone — anniversary, founding, IPO, acquisition?",
      "Internal-facing, external-facing, or both?",
      "What channels are in scope?",
      "Is there a flagship event planned?"
    ],
    "auto_detect_signals": ["anniversary", "milestone", "celebration", "campaign", "25th", "50th", "founding"]
  },
  "narrative": {
    "letter_strategy": "warm",
    "letter_opening_instruction": "Open with the client's origin story — when they were founded, what the world looked like then. Make them feel the weight of the milestone before talking about how to celebrate it."
  },
  "cost_model": {
    "pricing_framing": "bundled_value",
    "pricing_anchor_text": "Frame as year-long partnership, not project fee. Show monthly equivalent. Compare against hiring 4-6 separate specialist agencies."
  },
  "output": {
    "site_theme": "editorial",
    "demo_embed_eligible": true
  }
}
```

**4. Creative Retainer Pitch**
```json
{
  "id": "creative-retainer",
  "category": "retainer",
  "brief_intake": {
    "required_questions": [
      "What ongoing creative needs do they have?",
      "How are they currently handling this — in-house, freelancers, another agency?",
      "What's the volume — how many deliverables per month?",
      "What's the pain — inconsistency, speed, quality, cost?"
    ],
    "auto_detect_signals": ["retainer", "ongoing", "monthly", "continuous", "always-on", "on-call"]
  },
  "narrative": {
    "letter_strategy": "relationship_builder",
    "letter_opening_instruction": "Start with their current frustration. Acknowledge the hassle of managing multiple freelancers or an overloaded internal team. Position the retainer as peace of mind."
  },
  "cost_model": {
    "pricing_framing": "time_savings",
    "pricing_anchor_text": "Compare monthly retainer against hourly cost of equivalent freelancer hours or internal headcount (salary + benefits + management overhead)."
  },
  "output": {
    "site_theme": "warm",
    "demo_embed_eligible": false
  }
}
```

**5. Website Redesign**
```json
{
  "id": "website-redesign",
  "category": "technology",
  "brief_intake": {
    "required_questions": [
      "What's wrong with the current site — design, performance, conversion, CMS?",
      "What's the page count and content volume?",
      "Do they need CMS, e-commerce, or integrations?",
      "Who's the target audience and what action should they take?"
    ],
    "auto_detect_signals": ["website", "redesign", "web", "homepage", "landing page", "site refresh"]
  },
  "narrative": {
    "letter_strategy": "research_heavy",
    "letter_opening_instruction": "Open with a specific observation about their current website — a performance issue, a UX problem, or a missed conversion opportunity. Show you've done your homework."
  },
  "cost_model": {
    "pricing_framing": "market_rate",
    "pricing_anchor_text": "Position against published Indian agency website pricing. Show we're at market rate with more included."
  },
  "output": {
    "site_theme": "minimal",
    "demo_embed_eligible": true
  }
}
```

**6. Social Media Management**
```json
{
  "id": "social-media",
  "category": "retainer",
  "brief_intake": {
    "required_questions": [
      "Which platforms — Instagram, LinkedIn, Twitter, YouTube?",
      "What's the posting frequency they want?",
      "Do they need content creation, community management, or both?",
      "Current follower count and engagement rate?"
    ],
    "auto_detect_signals": ["social media", "Instagram", "LinkedIn", "content calendar", "community management", "social"]
  },
  "narrative": {
    "letter_strategy": "confident",
    "letter_opening_instruction": "Open with a specific observation about their current social presence — a missed opportunity, a competitor doing it better, or a content gap."
  },
  "cost_model": {
    "pricing_framing": "market_rate",
    "pricing_anchor_text": "Benchmark against Indian social media agency retainer rates (₹30K-2L/month)."
  },
  "output": {
    "site_theme": "bold",
    "demo_embed_eligible": false
  }
}
```

**7. Product Launch Campaign**
```json
{
  "id": "product-launch",
  "category": "campaign",
  "brief_intake": {
    "required_questions": [
      "What's the product and when does it launch?",
      "Who's the target audience?",
      "What channels are in budget — digital only or ATL+BTL?",
      "Is there a launch event?"
    ],
    "auto_detect_signals": ["launch", "product launch", "go-to-market", "GTM", "new product", "release"]
  },
  "narrative": {
    "letter_strategy": "confident",
    "letter_opening_instruction": "Open with the market opportunity. Why this product, why now, why does the launch need to be exceptional."
  },
  "cost_model": {
    "pricing_framing": "investment_roi",
    "pricing_anchor_text": "Frame launch campaign cost as a percentage of expected first-quarter revenue from the product."
  },
  "output": {
    "site_theme": "bold",
    "demo_embed_eligible": false
  }
}
```

### Template Auto-Selection

When the user describes a project in Step 1, the AI classifies it against the template library:

1. Extract keywords from the user's description
2. Match against `auto_detect_signals` across all templates
3. Rank matches by signal density
4. Present the top match: "This looks like a [Template Name] proposal. I'll use that template — want a different one?"
5. User confirms or overrides

### Custom Templates

Users can create custom templates by:
1. Starting from a built-in template and modifying fields
2. After completing a proposal, selecting "Save as template" — the system captures the questions asked, research done, pricing framing used, and narrative approach
3. Importing a JSON template file

---


---


## 8. The Proposal Engine — AI Pipeline

This is the technical core of NUPROP. It defines how the AI processes a brief and produces a complete proposal.

### Pipeline Stages

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  INTAKE  │───▶│ RESEARCH │───▶│  MODEL   │───▶│ GENERATE │
│          │    │          │    │          │    │          │
│ Parse    │    │ Client   │    │ Cost     │    │ Letter   │
│ brief    │    │ research │    │ model    │    │ Summary  │
│          │    │          │    │          │    │ Scope    │
│ Extract  │    │ Market   │    │ Market   │    │ Rationale│
│ require- │    │ bench-   │    │ compari- │    │ Terms    │
│ ments    │    │ marks    │    │ son      │    │          │
│          │    │          │    │          │    │ Site     │
│ Clarify  │    │ Industry │    │ Bundle   │    │ DOCX     │
│ gaps     │    │ context  │    │ pricing  │    │ Email    │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
     ▲                                              │
     │              HUMAN REVIEW GATES              │
     └──────────────────────────────────────────────┘
```

### 8.1 Brief Intake Module

**Input formats accepted**:
- Free-text description (typed or pasted)
- Uploaded document (PDF, DOCX, email .eml, spreadsheet)
- Meeting transcript (from Scribbl, Otter, or plain text)
- URL (client's website for context)

**AI processing**:
1. Extract: Client name, project type, deliverables mentioned, timeline, budget signals, constraints
2. Classify: Map deliverables to the agency's rate card categories
3. Identify gaps: What's missing from the brief? What needs clarification?
4. Generate clarifying questions (max 5): Present to user for answering

**Output**: Structured brief object

```json
{
  "client": {
    "name": "Titan Company",
    "industry": "Retail / Luxury / Consumer",
    "size": "Enterprise (₹38,000 Cr revenue)",
    "contacts": ["Priya Sharma, Head of Digital"]
  },
  "project": {
    "type": "Digital Brand Refresh",
    "deliverables": [
      {"category": "website_redesign", "details": "Parent brand, 20+ pages"},
      {"category": "brand_guidelines", "details": "Digital-only update"},
      {"category": "social_templates", "details": "Instagram, LinkedIn, Twitter"}
    ],
    "timeline": "4 months",
    "budget_signal": "15-20L mentioned"
  },
  "context": {
    "relationship": "cold_pitch",
    "competition": "unknown",
    "urgency": "medium",
    "decision_maker": "Priya Sharma"
  }
}
```

### 8.2 Research Module

**Client Research** (web search):
- Company overview: revenue, employees, industry position
- Recent news: last 6 months of press coverage
- Leadership: key decision-makers, recent appointments
- Current brand audit: screenshot of website, note design observations
- Social presence: follower counts, posting frequency, content quality

**Market Benchmarking** (web search):
- For each deliverable category, search for published pricing in the client's geography
- Search queries follow a pattern: `[service type] cost [country] [year] agency`
- Example: "website redesign cost India 2026 agency"
- Extract 3-5 data points per category
- Source quality ranking: industry reports > agency price guides > Clutch/DesignRush data > Quora/Reddit anecdotes

**Output**: Research report (markdown) with sourced data points

### 8.3 Cost Model Builder

**Inputs**: Structured brief + rate card + benchmarks + multipliers

**Process**:
1. Map each deliverable to the closest rate card item
2. Apply quantity multipliers (e.g., 3 themes × brand guidelines)
3. Apply complexity multipliers based on client size and project type
4. Calculate subtotals per workstream
5. Apply bundle discounts if annual engagement
6. Calculate pass-through costs (printing, hosting, media spend, etc.)
7. Generate market comparison: Veeville price vs. benchmark range
8. Calculate savings percentage

**HUMAN REVIEW GATE**: The cost model is ALWAYS presented to the user for approval before proceeding. The user can adjust any line item, change quantities, add/remove deliverables, or override prices.

### 8.4 Narrative Generator

**Covering Letter**:
- Uses agency's calibrated voice profile
- Opens with the CLIENT (references research findings)
- Middle: positions the agency's fit (draws from portfolio library)
- Close: confident CTA, specific next step
- Length: 400-600 words
- Generated as 3 variants: Confident / Warm / Research-Heavy

**Executive Summary**:
- What we're proposing
- Why this approach
- Investment overview
- Length: 300-400 words

**Scope Descriptions**:
- Per-deliverable: what's included, excluded, options, revisions, timeline
- References market benchmarks naturally
- Length: 100-200 words per deliverable

**Cost Rationale**:
- Per-category: benchmark data, uniqueness of approach, value justification
- Sourced from research module
- Length: 150-250 words per category

**Terms & Conditions**:
- Populated from agency's standard template
- Dates, percentages, and client-specific details auto-filled

---


---


---

## 8A. Agentic Architecture

### The Shift: Pipeline → Agent System

The current NUPROP pipeline is sequential and human-gated:

```
CURRENT: LINEAR PIPELINE
═══════════════════════════════════════════════════

User → Brief → Template → Research → Benchmark → Cost Model → Narrative → Output
          ↑        ↑                                   ↑                     ↑
        human    human                               human                human
        input    confirm                            approve               review

Time: 30-60 minutes of active user interaction
Problem: User waits while AI researches. AI waits while user reviews.
```

The agentic version runs parallel autonomous agents that work ahead, speculate intelligently, and only interrupt the user when a decision is needed:

```
AGENTIC: PARALLEL AGENT SYSTEM
═══════════════════════════════════════════════════

User says: "new proposal for Tata Communications,
           25th anniversary campaign"
                │
                ▼
    ┌───────────────────────┐
    │   ORCHESTRATOR AGENT  │
    │   (plans, delegates,  │
    │    manages state)     │
    └───────┬───────────────┘
            │
            │ spawns immediately, in parallel:
            │
    ┌───────┼───────────────────────────────────┐
    │       │                                   │
    ▼       ▼              ▼              ▼     ▼
┌────────┐┌──────────┐┌──────────┐┌──────────┐┌──────────┐
│RESEARCH││BENCHMARK ││TEMPLATE  ││PORTFOLIO ││COMPETITOR│
│AGENT   ││AGENT     ││AGENT     ││AGENT     ││AGENT     │
│        ││          ││          ││          ││          │
│Searches││Searches  ││Selects   ││Finds     ││Analyses  │
│client  ││market    ││best      ││relevant  ││competing │
│news,   ││pricing   ││template, ││past work ││agencies' │
│leader- ││data for  ││prepares  ││and case  ││proposals │
│ship,   ││each      ││preference││studies   ││for this  │
│history ││category  ││defaults  ││from      ││client    │
│        ││          ││          ││portfolio ││          │
└────┬───┘└────┬─────┘└────┬─────┘└────┬─────┘└────┬─────┘
     │         │           │           │           │
     └─────────┴───────┬───┴───────────┴───────────┘
                       │
                       ▼
              ┌─────────────────┐
              │  ORCHESTRATOR   │
              │  merges results │
              │  into proposal  │
              │  state object   │
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐
              │  USER APPROVAL  │◄── only interruption
              │  GATE           │    before output
              │                 │
              │  "Here's the    │
              │  full proposal. │
              │  Cost model,    │
              │  letter, scope. │
              │  Approve or     │
              │  adjust."       │
              └────────┬────────┘
                       │
                       ▼ (if approved, in parallel again)
              ┌────────┼────────────────┐
              ▼        ▼                ▼
         ┌────────┐┌────────┐    ┌──────────┐
         │DOCX    ││SITE    │    │EMAIL     │
         │AGENT   ││AGENT   │    │AGENT     │
         │        ││        │    │          │
         │Builds  ││Builds  │    │Composes  │
         │Word doc││Astro   │    │intro     │
         │        ││site    │    │email     │
         └────┬───┘└───┬────┘    └────┬─────┘
              │        │              │
              └────────┴──────┬───────┘
                              ▼
                     ┌─────────────────┐
                     │  DEPLOY AGENT   │
                     │  Deploys site,  │
                     │  presents files,│
                     │  logs proposal  │
                     └─────────────────┘

Time: 5-10 minutes of user interaction (the rest runs autonomously)
```

### 8A.1 The Seven Agents

#### 1. Orchestrator Agent (always running)

The brain. Manages the proposal state object, delegates tasks to specialist agents, resolves conflicts, and decides when to surface to the user.

**Responsibilities:**
- Parse the user's initial request and extract: client name, project type, any explicit constraints
- Decide which agents to spawn and in what order
- Maintain the **Proposal State Object** (see 8A.2)
- Merge results from parallel agents
- Detect conflicts (e.g., research agent found the client is in financial trouble — should we still pitch?)
- Decide when to present to the user vs. continue autonomously
- Handle failures (agent timed out, search returned nothing) by retrying or routing to fallback

**Decision rules:**
```
IF user gives client name + project type:
  → spawn Research, Benchmark, Template, Portfolio, Competitor agents in parallel
  → don't wait for user — start working immediately

IF user gives only client name:
  → spawn Research agent first
  → once research returns, infer project type from context
  → then spawn remaining agents

IF user uploads a brief document:
  → parse document (sync)
  → extract all signals
  → spawn all agents with enriched context

IF any agent fails after 2 retries:
  → mark that section as "needs human input"
  → continue with other agents
  → present partial results with gaps flagged
```

#### 2. Research Agent

Autonomously researches the client. Runs 5-10 web searches, fetches key pages, synthesises findings.

**Inputs:** Client name, industry (if known)
**Outputs:** `research/findings.md` — structured client profile
**Autonomous decisions:**
- Which searches to run (adapts based on what each search returns)
- Whether to fetch full pages or rely on snippets
- When it has "enough" (stops after finding: company overview, leadership, recent news, 2-3 narrative hooks)
- Whether the client is publicly traded (triggers different research paths — annual reports, analyst coverage)

**Self-healing:**
- If initial search returns nothing useful → try alternative name spellings, parent company, subsidiaries
- If the client is very small/unknown → flag this and reduce research scope, suggest the user provide background

#### 3. Benchmark Agent

Autonomously finds pricing data for each deliverable category.

**Inputs:** Deliverable list (from brief or template), country, industry
**Outputs:** `research/benchmarks.md` — structured pricing data with sources
**Autonomous decisions:**
- Which categories need benchmarking (skips commodity items like "email template" where pricing is well-known)
- How many sources per category (aims for 3, accepts 2, flags if only 1)
- Whether to search India-specific or global benchmarks based on client geography
- Quality assessment of sources (prefers Clutch, agency review sites, and published rate cards over forum posts)

**Self-healing:**
- If no benchmarks found for a specific service → search for the closest comparable service
- If all sources are outdated (>2 years) → flag as "limited benchmark data" and note the year

#### 4. Template Agent

Selects the optimal strategy template and prepares preference defaults.

**Inputs:** Structured brief, client research (when available)
**Outputs:** Selected template ID, merged preferences, additional brief questions
**Autonomous decisions:**
- Template selection (keyword matching against `auto_detect_signals`)
- Whether to suggest a hybrid (e.g., "This is 60% anniversary campaign, 40% employer branding — I'll use the anniversary template but add employer branding deliverables")
- Which template-specific questions still need answers from the user

**Does NOT make autonomous decisions about:**
- Pricing model (flat vs. tiered) — always surfaces to user
- Letter tone — surfaces to user with recommendation
- Budget — never assumes

#### 5. Portfolio Agent

Searches the agency's past proposals and case studies for relevant work to reference.

**Inputs:** Client industry, project type, deliverable categories
**Outputs:** List of 2-5 relevant past projects with: client name, project summary, outcome, relevance score
**Data sources:**
- `proposal-log.json` (past proposals with win/loss data)
- Portfolio library (if configured — case studies, testimonials)
- Google Drive (search for relevant past work — decks, case studies)

**Autonomous decisions:**
- Which past projects are most relevant (industry match > project type match > recency)
- Whether to include won proposals only or also highly-engaged losses
- Which specific case studies to suggest embedding in the proposal site

#### 6. Competitor Agent (Phase C)

Analyses what competing agencies might pitch for this client.

**Inputs:** Client name, project type, industry
**Outputs:** Competitive intelligence brief — 2-3 likely competitors, their strengths, pricing positioning, and how to differentiate
**Searches:**
- `[client name] agency` — find who they've worked with before
- `[industry] [project type] agency India` — find likely competitors
- Check competitor websites for relevant case studies

**Autonomous decisions:**
- Whether competitor intelligence is relevant (skip for existing clients with deep relationship)
- How to position against each competitor (price, quality, speed, specialisation)

#### 7. Output Agents (Parallelised)

Three sub-agents that generate outputs simultaneously after the user approves the cost model and narrative:

**DOCX Agent:** Generates the Word document using the docx skill. Autonomous — no user input needed once content is approved.

**Site Agent:** Builds the interactive proposal site. Selects theme from preferences, populates all sections, embeds analytics script, configures password protection if set. Deploys to Fly.io via CLI. Returns the live URL.

**Email Agent:** Composes the introduction email with the proposal URL, attaches PDF, generates 2 tone variants. Drafts a follow-up sequence (Day 2 nudge, Day 5 one-pager, Day 10 final).

### 8A.2 Proposal State Object

The central data structure that all agents read from and write to. The Orchestrator manages merge conflicts.

```json
{
  "id": "proposal_2026-04-06_tata-comms",
  "status": "generating",
  "phase": "research_complete",

  "brief": {
    "client_name": "Tata Communications",
    "project_type": "anniversary_campaign",
    "deliverables_raw": ["theme development", "visual identity", "films", "events", "microsite"],
    "timeline": "12 months",
    "budget_signal": null,
    "relationship": "warm_pitch",
    "source": "uploaded_pdf"
  },

  "template": {
    "id": "anniversary-milestone-campaign",
    "confidence": 0.92,
    "hybrid_with": null
  },

  "preferences": {
    "letter_tone": "warm",
    "letter_opening": "client_story",
    "pricing_model": "flat",
    "discounts": ["annual_bundle"],
    "scope_detail": "detailed",
    "outputs": ["site", "docx", "pdf", "cost_rationale", "email"]
  },

  "research": {
    "status": "complete",
    "agent_id": "research_001",
    "findings": { "...structured findings..." },
    "confidence": 0.88,
    "sources_count": 12,
    "narrative_hooks": [
      "VSNL launched India's first public internet on Independence Day 1995",
      "CEO transition happening April 13 — new leadership opportunity",
      "13th consecutive Gartner Magic Quadrant Leader"
    ]
  },

  "benchmarks": {
    "status": "complete",
    "agent_id": "benchmark_001",
    "categories_benchmarked": 6,
    "data_points": 37,
    "gaps": ["no benchmark found for AI microsite in India — used global estimates"]
  },

  "cost_model": {
    "status": "pending_approval",
    "line_items": [ "...35 items..." ],
    "subtotal": 19790000,
    "discount": 2375000,
    "total": 17415000,
    "market_comparison": "30-60% below market à la carte"
  },

  "narrative": {
    "status": "pending_approval",
    "covering_letter_variants": [
      { "strategy": "confident", "text": "..." },
      { "strategy": "warm", "text": "..." }
    ],
    "executive_summary": "...",
    "scope_sections": [ "...35 sections..." ],
    "cost_rationale": "..."
  },

  "portfolio": {
    "status": "complete",
    "relevant_projects": [
      { "client": "Titan Company", "project": "Brand Refresh", "relevance": 0.72 }
    ]
  },

  "outputs": {
    "docx": { "status": "not_started" },
    "site": { "status": "not_started" },
    "email": { "status": "not_started" }
  },

  "approval_gates": {
    "cost_model_approved": false,
    "narrative_approved": false,
    "outputs_approved": false
  },

  "agent_log": [
    { "agent": "orchestrator", "action": "spawned_research", "ts": "2026-04-06T10:23:00Z" },
    { "agent": "research", "action": "search_complete", "ts": "2026-04-06T10:23:45Z", "searches": 7 },
    { "agent": "benchmark", "action": "search_complete", "ts": "2026-04-06T10:24:10Z", "searches": 12 },
    { "agent": "template", "action": "selected", "ts": "2026-04-06T10:23:05Z", "template": "anniversary-milestone-campaign" }
  ]
}
```

### 8A.3 Approval Gates (Human-in-the-Loop)

Agents run autonomously, but three gates require human approval:

**Gate 1: Brief + Preferences** (after Step 1)
```
"Here's what I've captured and how I'll approach this:

CLIENT: Tata Communications (₹23,109 Cr revenue, 8,000 employees)
PROJECT: 25th anniversary campaign, year-long, 3 themes
TEMPLATE: Anniversary / Milestone Campaign
LETTER: Warm tone, opens with origin story
PRICING: Flat with annual bundle discount

Meanwhile, I've already:
✓ Researched the client (found CEO transition, Gartner streak)
✓ Found 37 pricing benchmarks across 6 categories
✓ Identified 2 relevant past projects from your portfolio

Ready to build the cost model, or want to adjust anything?"
```

The key shift: by the time the user sees this, the agents have already done 5-10 minutes of background work. The user isn't waiting.

**Gate 2: Cost Model** (after Step 4)
```
"Here's the cost model. 35 line items, ₹1.74 Cr total.

[table]

⚠️ One item flagged: 'Employee survey app' has no standard package.
I estimated ₹4.8L based on 60 hours of development. Adjust?

Approve, or tell me what to change."
```

**Gate 3: Narrative Review** (after Step 5)
```
"Everything's ready for your review:

📝 Covering letter (2 variants — tap to read)
📋 Executive summary
📦 35 scope descriptions
💰 Cost rationale with benchmarks
📜 Terms & conditions

Approve to generate all outputs, or tap any section to edit."
```

After Gate 3 approval, the output agents run fully autonomously — DOCX, site, and email generate in parallel, deploy, and present the results. No further human input needed.

### 8A.4 Speculative Execution

The most powerful agentic pattern: agents predict what the user will want and pre-compute it.

**Examples:**

1. **Pre-generate both letter variants before the user asks.**
   The Narrative Agent always generates 2 variants (confident + warm) without waiting for the user to pick. When the user reaches Gate 3, both are ready.

2. **Pre-build the site while the user reviews the cost model.**
   After Gate 1, the Site Agent starts scaffolding the site template with the research data and client name. It can't populate the cost section yet (pending Gate 2), but the cover, letter section, timeline, and team sections are all ready. After Gate 2, only the investment section needs to be filled — the site is 80% complete before the user even approves the narrative.

3. **Pre-search for the next likely question.**
   If the Benchmark Agent finds that video production costs in India have a wide range (₹25K-₹10L), it pre-fetches 3 detailed case studies of comparable video projects so the cost rationale has specific examples, anticipating the user or client will ask "why is the video ₹5L?"

4. **Pre-draft the follow-up email sequence.**
   The Email Agent doesn't just write the intro email — it pre-drafts a 3-email follow-up sequence: Day 2 check-in, Day 5 one-pager with different angle, Day 10 final nudge. These are ready to send from the dashboard without the user writing anything.

5. **Pre-compute tiered pricing even when flat is selected.**
   The Cost Model agent always computes a 3-tier version in the background. If the user later says "actually, give me tiered pricing," it's instant — no re-computation needed.

### 8A.5 Agent Communication Protocol

Agents communicate through the Proposal State Object (shared state) and a message bus (Redis pub/sub):

```python
# Agent communication protocol

class AgentMessage:
    agent_id: str           # who sent it
    message_type: str       # "result", "error", "need_input", "progress"
    payload: dict           # agent-specific data
    timestamp: datetime
    proposal_id: str

# Message types:

# Agent completed its work
{"type": "result", "agent": "research", "payload": {"findings": {...}}}

# Agent needs information from another agent
{"type": "need_input", "agent": "benchmark", "needs": "deliverable_list",
 "from": "template"}

# Agent failed and needs human help
{"type": "need_human", "agent": "benchmark", "reason": "no_data_found",
 "category": "ai_microsite_pricing", "fallback": "rate_card_estimate"}

# Progress update (for real-time UI)
{"type": "progress", "agent": "research", "step": "searching",
 "detail": "Found CEO transition — searching for more details"}
```

### 8A.6 Real-Time UI During Agent Execution

While agents work in the background, the chat UI shows live progress:

```
You: "new proposal for Tata Communications, 25th anniversary campaign"

NUPROP: Starting proposal generation...

  🔍 Researching Tata Communications...
     ✓ Company overview: ₹23,109 Cr revenue, 8,000 employees
     ✓ CEO transition: A.S. Lakshminarayanan retiring April 13
     ✓ 13th consecutive Gartner MQ Leader (confirmed April 2)
     ● Searching for recent awards...

  📊 Finding pricing benchmarks...
     ✓ Brand identity: ₹40K-6L (Jigsaw Kraft 2026, Clutch)
     ✓ Corporate video: ₹25K-10L (ARD Digital Media 2025)
     ● Searching AI microsite costs...
     ● Searching event management costs...

  📋 Template: Anniversary / Milestone Campaign (92% match)
     Pre-loading typical deliverables...

  📁 Portfolio: Found 2 relevant past projects
     • Titan Company — Brand Refresh (72% relevant)
     • GENUNITY Survey — Engagement Campaign (58% relevant)

  ──────────────────────────────────────────

  Research complete. Ready to build cost model.

  Here's what I know: [summary]
  Here's how I'll approach this: [preferences]

  Approve to continue, or adjust anything.
```

Each line appears in real-time as the agent completes that sub-task. The user sees progress, feels confident the system is working, and can already start thinking about adjustments while waiting.

### 8A.7 Post-Send Agentic Behaviours

The agentic system doesn't stop when the proposal is sent. Background agents continue:

**Follow-Up Agent:**
- Monitors proposal engagement via analytics
- At configurable intervals, drafts contextual follow-up messages:
  - Day 2 (if opened but no CTA): "Checking in — any questions about the scope?"
  - Day 5 (if not opened): "Resending with a different angle" + generates a one-pager
  - Day 5 (if opened, investment section most viewed): "I noticed you spent time on the pricing. Happy to walk through the cost rationale."
  - Day 10 (no response): "Final nudge before the proposal expires on [date]"
- User reviews and sends with one click — never writes follow-ups from scratch

**Win/Loss Agent:**
- When the user marks a proposal as Won or Lost, the agent:
  - Analyses which attributes correlated with the outcome
  - Compares engagement patterns (won proposals vs. lost)
  - Updates template confidence scores
  - Suggests adjustments: "Your last 3 lost proposals used confident tone. Consider warm for similar clients."

**Renewal Agent:**
- For retainer proposals, monitors the contract end date
- 60 days before expiry: drafts a renewal proposal with updated rates, scope adjustments based on the past year's work, and a covering letter that references specific outcomes delivered
- User reviews and sends

**Competitive Alert Agent:**
- If the user enabled competitor monitoring for a specific client:
  - Periodically searches for `[client name] + agency + new` to detect if the client is shopping
  - Alerts: "Tata Communications posted a new RFP on India Mart for video production — relevant to your active retainer"

### 8A.8 Agent Reliability & Fallbacks

Every agent has a timeout, retry logic, and a graceful degradation path:

| Agent | Timeout | Retries | Fallback |
|---|---|---|---|
| Research | 60 seconds | 2 | Present with gaps: "I couldn't find revenue data — do you know?" |
| Benchmark | 90 seconds | 2 | Use rate card as benchmark: "No published data — estimated from our rates" |
| Template | 5 seconds | 0 | Default to generic (no template) |
| Portfolio | 10 seconds | 1 | Skip portfolio section |
| Competitor | 60 seconds | 1 | Skip competitor intel |
| DOCX Output | 120 seconds | 2 | Generate markdown fallback |
| Site Output | 180 seconds | 2 | Generate static HTML without Astro build |
| Email Output | 30 seconds | 1 | Generate plain text |

**Circuit breaker:** If the Claude API is down or rate-limited, the Orchestrator:
1. Queues the proposal as "pending"
2. Notifies the user: "API is temporarily unavailable. Your proposal is queued and will resume automatically."
3. Retries every 5 minutes for 1 hour
4. After 1 hour, escalates: "Unable to complete — here's what was generated so far [partial outputs]"

### 8A.9 Implementation: FastAPI + Background Workers

```python
# Agentic architecture — FastAPI MVVM

# viewmodels/orchestrator_vm.py
class OrchestratorViewModel:
    """Central coordinator for proposal generation."""

    async def start_proposal(self, brief: Brief, user_id: str) -> ProposalState:
        state = ProposalState.create(brief, user_id)

        # Spawn parallel agents as background tasks
        await asyncio.gather(
            self.spawn_agent(ResearchAgent, state),
            self.spawn_agent(BenchmarkAgent, state),
            self.spawn_agent(TemplateAgent, state),
            self.spawn_agent(PortfolioAgent, state),
            return_exceptions=True  # don't fail if one agent fails
        )

        # Merge results into state
        state = await self.merge_agent_results(state)

        # Check if we can proceed or need human input
        if state.has_gaps():
            state.phase = "needs_human_input"
            await self.notify_user(state, state.get_gaps())
        else:
            state.phase = "ready_for_approval"
            await self.present_for_approval(state)

        return state

    async def spawn_agent(self, agent_class, state: ProposalState):
        agent = agent_class(state)
        try:
            result = await asyncio.wait_for(
                agent.run(),
                timeout=agent.timeout_seconds
            )
            await state.merge(agent.name, result)
            await self.publish_progress(state, agent.name, "complete")
        except asyncio.TimeoutError:
            await self.handle_timeout(agent, state)
        except Exception as e:
            await self.handle_error(agent, state, e)

    async def on_user_approval(self, state: ProposalState, gate: str):
        if gate == "cost_model":
            state.approval_gates["cost_model_approved"] = True
            # Narrative agent can now use approved prices
            await self.spawn_agent(NarrativeAgent, state)

        elif gate == "narrative":
            state.approval_gates["narrative_approved"] = True
            # Spawn output agents in parallel
            await asyncio.gather(
                self.spawn_agent(DocxAgent, state),
                self.spawn_agent(SiteAgent, state),
                self.spawn_agent(EmailAgent, state),
            )

# viewmodels/research_agent_vm.py
class ResearchAgent:
    name = "research"
    timeout_seconds = 60

    async def run(self) -> ResearchResult:
        client = self.state.brief.client_name
        industry = self.state.brief.industry or "unknown"

        # Parallel web searches
        searches = await asyncio.gather(
            self.search(f"{client} company overview revenue"),
            self.search(f"{client} CEO leadership 2026"),
            self.search(f"{client} recent news {datetime.now().year}"),
            self.search(f"{client} awards recognition"),
        )

        # Synthesise into structured findings
        findings = await self.synthesise(searches)

        # Extract narrative hooks
        hooks = await self.extract_hooks(findings)

        return ResearchResult(
            findings=findings,
            hooks=hooks,
            sources=[s.url for s in searches],
            confidence=self.assess_confidence(findings)
        )

# Real-time progress via WebSocket
# viewmodels/progress_vm.py
class ProgressViewModel:
    async def publish_progress(self, state, agent, status):
        await self.redis.publish(
            f"proposal:{state.id}",
            json.dumps({
                "agent": agent,
                "status": status,
                "detail": state.get_agent_summary(agent),
                "timestamp": datetime.utcnow().isoformat()
            })
        )
```

### 8A.10 What Changes for the User

| Before (Pipeline) | After (Agentic) |
|---|---|
| User describes brief, waits while AI researches | User describes brief, AI immediately starts working while asking clarifying questions in parallel |
| 7-8 back-and-forth interactions | 3 approval gates + optional adjustments |
| 30-60 minutes of active interaction | 10-15 minutes of active interaction |
| Sequential: research → benchmark → cost → narrative | Parallel: research + benchmark + template + portfolio run simultaneously |
| User waits for each output | All outputs generate in parallel after final approval |
| Follow-up emails written manually | Follow-up sequence pre-drafted, sent with one click |
| Win/loss data entered but not used | Win/loss agent actively learns and adjusts recommendations |
| One proposal at a time | Queue multiple proposals: "Also start one for Smartworks" |

### 8A.11 Phase Rollout

| Phase | Agentic Features |
|---|---|
| A (Claude Code) | None — linear pipeline, fully interactive |
| B (Validation) | Parallel research + benchmark (agents run while user answers brief questions) |
| C (Platform Launch) | Full agent system: Orchestrator, Research, Benchmark, Template, Portfolio. Speculative execution. Real-time progress UI. |
| C+ (Month 4-6) | Output agents parallelised. Follow-up agent. Email sequences. |
| D (Growth) | Competitor agent. Win/loss learning agent. Renewal agent. Multi-proposal queuing. |

---


---

## 8B. Client Context Engine

### The Problem

The Research Agent searches the web and finds: "Tata Communications, ₹23,109 Cr revenue, 8,000 employees, CEO transition April 13."

What it doesn't know:

- You've emailed Priya from their IC team 14 times over the last 3 months
- She mentioned in a Slack DM that their budget got cut by 20% this quarter
- You did a small poster job for them 8 months ago and they loved the turnaround time but complained about revision delays
- The last proposal you sent them (₹8L for a video project) was rejected — "too expensive" was the feedback
- Their CFO, not the IC head, signs off on anything above ₹10L
- In a meeting note from February, they mentioned wanting to consolidate all creative work with one agency instead of managing five vendors

This context completely changes how you write the letter, how you frame pricing, which deliverables you emphasise, and how aggressive you can be on the total. No amount of web research surfaces this. It lives in your email, your Slack, your Google Drive, your CRM, and your memory.

### Architecture

```
┌──────────────────────────────────────────────────────────┐
│                  CLIENT CONTEXT ENGINE                     │
│                                                          │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐    │
│  │ CONNECTORS  │ │ INGESTION   │ │ CONTEXT STORE    │    │
│  │             │ │             │ │                   │    │
│  │ Gmail ──────┼─┼─→ Extract   │ │ Client Profile    │    │
│  │ Slack ──────┼─┼─→ Classify  │ │ ├── contacts[]    │    │
│  │ Google ─────┼─┼─→ Summarise │ │ ├── interactions[] │    │
│  │   Drive     │ │             │ │ ├── sentiments[]   │    │
│  │ Calendar ───┼─┼─→ Link to   │ │ ├── decisions[]    │    │
│  │ CRM ────────┼─┼─→   client  │ │ ├── past_work[]   │    │
│  │ WhatsApp ───┼─┤             │ │ ├── pricing_history│    │
│  │ Manual ─────┼─┘             │ │ ├── preferences[]  │    │
│  │   upload    │               │ │ └── signals[]      │    │
│  └─────────────┘               │ └───────────────────┘    │
│                                │          │               │
│                                │          ▼               │
│                                │  ┌───────────────────┐   │
│                                │  │ CONTEXT AGENT     │   │
│                                │  │                   │   │
│                                │  │ Reads all context │   │
│                                │  │ before proposal   │   │
│                                │  │ generation.       │   │
│                                │  │ Produces a        │   │
│                                │  │ Client Brief for  │   │
│                                │  │ the Orchestrator.  │   │
│                                │  └───────────────────┘   │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### 8B.1 Data Sources & Connectors

#### Gmail Connector

**What it pulls**: All email threads with the client's domain (e.g., `*@tatacommunications.com`).

**What gets extracted per thread:**
- Participants (names, roles if inferrable from signature)
- Date range
- Thread summary (AI-generated, 2-3 sentences)
- Sentiment (positive / neutral / negative / mixed)
- Key decisions or commitments mentioned
- Attachments referenced (briefs, contracts, feedback documents)
- Budget or pricing references
- Follow-up items mentioned

**How it works (Phase C):**
```python
# Gmail connector — uses Gmail MCP or Google API
class GmailConnector:
    async def fetch_client_threads(self, client_domain: str, 
                                     since: datetime = None) -> list[EmailThread]:
        # Search: from:*@tatacommunications.com OR to:*@tatacommunications.com
        threads = await self.gmail.search(
            query=f"{{from:{client_domain} OR to:{client_domain}}}",
            after=since or (datetime.now() - timedelta(days=365))
        )
        return threads

    async def extract_context(self, thread: EmailThread) -> ThreadContext:
        # Send thread to Claude for extraction
        response = await self.claude.messages.create(
            model="claude-sonnet-4-20250514",
            system="""Extract from this email thread:
                1. Participants (name, inferred role)
                2. 2-sentence summary of the thread
                3. Sentiment (positive/neutral/negative)
                4. Key decisions or commitments
                5. Budget/pricing mentions (exact numbers)
                6. Any complaints or concerns
                7. Any praise or positive feedback
                8. Follow-up items or next steps
                Respond as JSON.""",
            messages=[{"role": "user", "content": thread.full_text}]
        )
        return ThreadContext.parse(response)
```

**Privacy**: Only threads matching the client domain are pulled. The user authorises access via Google OAuth. Email bodies are processed by Claude for extraction but not stored raw — only the structured extraction (summary, sentiment, decisions) is retained.

#### Slack Connector

**What it pulls**: Messages mentioning the client name or from shared channels with the client.

**What gets extracted:**
- Internal discussions about the client (strategy conversations, pricing debates, feedback discussions)
- DMs with client contacts
- Shared channel messages (if the client has a shared Slack channel)
- Reactions and sentiment on client-related messages

**Key insight**: Internal Slack messages reveal what your team *really* thinks about the client — "they're slow to approve," "they always negotiate hard on price," "their IC team is great but procurement is a nightmare." This context is gold for calibrating the proposal.

#### Google Drive Connector

**What it pulls**: Documents shared with or about the client.

**What gets extracted:**
- Past proposals (DOCX/PDF) → deliverables proposed, pricing, outcome
- Meeting notes → decisions, action items, client preferences
- Contracts/SOWs → actual pricing agreed, payment terms, scope boundaries
- Presentations → what was pitched, client feedback
- Creative briefs → what the client asked for vs. what was delivered

#### Calendar Connector

**What it pulls**: Meetings with client contacts.

**What gets extracted:**
- Meeting frequency (how often do you meet? weekly = deep relationship, quarterly = arms-length)
- Attendees (who from the client is involved? just IC, or does leadership attend?)
- Meeting titles and descriptions (topics discussed)
- Last meeting date (how recent is the relationship?)

#### CRM Connector (Phase D)

**What it pulls**: Deal records, contact records, pipeline stage, notes.

**Supported CRMs**: HubSpot, Pipedrive (read-only integration via API)

**What gets extracted:**
- Deal history (proposals sent, values, outcomes)
- Contact hierarchy (who reports to whom, who's the decision maker)
- Pipeline notes (what the BD person noted about this client)
- Tags and segments

#### WhatsApp Connector (Phase D)

**What it pulls**: WhatsApp Business API messages with client contacts.

**What gets extracted**: Same as email — summary, sentiment, decisions, pricing references.

#### Manual Upload

For agencies that don't use connectors, the user can:
- Paste email threads into the chat: "Here's my last 5 emails with Priya from Tata Comms"
- Upload meeting notes: "Here's my notes from our meeting last week"
- Upload past proposals: "Here's what we sent them 6 months ago"
- Type context directly: "They rejected our last proposal for being too expensive. Their budget for this is around 15-20L. The CFO signs off on everything above 10L."

The Context Agent processes these the same way as connector data.

### 8B.2 Client Context Profile

All connector data is processed and stored as a structured **Client Context Profile**:

```json
{
  "client_id": "tata-communications",
  "client_name": "Tata Communications",
  "context_updated_at": "2026-04-06T08:00:00Z",
  "data_sources": ["gmail", "google_drive", "calendar", "manual"],

  "relationship": {
    "status": "warm",
    "duration_months": 11,
    "first_contact": "2025-05-14",
    "last_interaction": "2026-04-03",
    "interaction_count": 47,
    "meeting_count": 8,
    "meeting_frequency": "monthly",
    "primary_contact": {
      "name": "Priya Sharma",
      "role": "Head of Internal Communications",
      "email": "priya.sharma@tatacommunications.com",
      "communication_style": "Detailed, process-oriented, prefers email over calls",
      "responsiveness": "Typically replies within 24 hours"
    },
    "other_contacts": [
      {
        "name": "Rahul Menon",
        "role": "VP Corporate Affairs",
        "involvement": "Signs off on campaigns above ₹10L",
        "seen_in": ["2 email threads", "1 meeting"]
      },
      {
        "name": "Anjali Desai",
        "role": "Procurement Manager",
        "involvement": "Handles contracts and POs",
        "seen_in": ["3 email threads"]
      }
    ],
    "decision_making": {
      "authority": "Priya approves scope, Rahul approves budget above ₹10L, procurement issues PO",
      "process": "Priya shortlists → Rahul reviews → Procurement negotiates → PO issued",
      "typical_cycle": "3-4 weeks from proposal to PO"
    }
  },

  "past_work": [
    {
      "project": "Quarterly Poster Series",
      "date": "2025-08",
      "value": 240000,
      "status": "completed",
      "outcome": "delivered_on_time",
      "client_feedback": "Loved the turnaround speed. Complained about revision delays on the 3rd poster — took 5 days instead of 2.",
      "lesson": "Fast first drafts are important to this client. Build in buffer for revisions."
    },
    {
      "project": "Corporate Video — Annual Day",
      "date": "2025-11",
      "value": 800000,
      "status": "proposal_rejected",
      "rejection_reason": "Price — said ₹8L was above their budget. Went with a production house at ₹4.5L.",
      "lesson": "Price-sensitive for video. They compare agency rates against production houses. Need to justify the premium or offer a leaner option."
    }
  ],

  "pricing_intelligence": {
    "budget_signals": [
      {"source": "email_2026-02-15", "signal": "Priya mentioned 'budget constraints this quarter'"},
      {"source": "email_2025-11-03", "signal": "Rejected ₹8L video proposal — 'above our budget'"},
      {"source": "meeting_2026-01-20", "signal": "Rahul said they want to consolidate with one agency to reduce total spend"}
    ],
    "price_sensitivity": "high",
    "past_accepted_range": "₹2.4L (posters)",
    "past_rejected_range": "₹8L (video)",
    "negotiation_style": "Procurement will always ask for 10-15% discount. Factor this in.",
    "payment_behaviour": "Pays on time, but PO process takes 2 weeks after approval"
  },

  "preferences": {
    "communication": "Email-first. Priya prefers detailed written proposals over presentations. She shares PDFs internally, not links.",
    "creative": "They prefer clean, corporate aesthetics. Not experimental. Past feedback: 'too creative' on one concept.",
    "process": "They want to see 3 options. They always pick the middle one. They want revisions done within 48 hours.",
    "reporting": "They like weekly status updates during active projects."
  },

  "opportunities": [
    {
      "source": "meeting_2026-01-20",
      "signal": "Rahul mentioned wanting to consolidate all creative work with one agency — currently using 5 vendors for different things",
      "implication": "Position the anniversary proposal as the start of a full consolidation. Offer retainer pricing."
    },
    {
      "source": "email_2026-03-28",
      "signal": "Priya asked about our video capabilities — may be reconsidering after the previous rejection",
      "implication": "Include video in the anniversary proposal at a competitive rate. Don't repeat the ₹8L pricing mistake."
    }
  ],

  "risks": [
    {
      "source": "email_2026-02-15",
      "signal": "Budget constraints this quarter",
      "implication": "Offer tiered pricing so they can choose a level that fits. Don't lead with the full ₹1.74Cr."
    },
    {
      "source": "past_work",
      "signal": "Revision delays caused friction on the poster project",
      "implication": "Explicitly mention 48-hour revision turnaround in the scope. Show we learned from last time."
    }
  ],

  "sentiment_timeline": [
    {"date": "2025-05", "sentiment": "positive", "event": "First contact, enthusiastic about working together"},
    {"date": "2025-08", "sentiment": "positive", "event": "Poster project delivered, praised turnaround"},
    {"date": "2025-09", "sentiment": "slightly_negative", "event": "Revision delays, Priya expressed frustration"},
    {"date": "2025-11", "sentiment": "negative", "event": "Video proposal rejected — price too high"},
    {"date": "2026-01", "sentiment": "positive", "event": "Meeting with Rahul, consolidation discussion, warm again"},
    {"date": "2026-03", "sentiment": "positive", "event": "Priya reaching out about video — re-engaged"}
  ]
}
```

### 8B.3 The Context Agent

A new agent in the agentic system (Section 8A). Runs in parallel with the Research Agent.

**Inputs**: Client name or domain
**Outputs**: Client Context Profile (above) + a **Context Brief** for the Orchestrator

**The Context Brief** is a natural-language summary that gets injected into every other agent's prompt:

```markdown
## Client Context Brief: Tata Communications

RELATIONSHIP: 11-month warm relationship. 47 interactions across email
and meetings. Primary contact is Priya Sharma (Head of IC), who prefers
detailed email communication and shares PDFs internally.

PAST WORK: One completed project (₹2.4L poster series — delivered on time,
client praised speed but had friction over revision delays). One rejected
proposal (₹8L video — rejected as too expensive, they went with a cheaper
production house).

PRICING INTELLIGENCE: Price-sensitive client. Budget constraints mentioned
this quarter. Procurement will always negotiate 10-15% discount. The CFO
(Rahul Menon) approves anything above ₹10L — he's interested in consolidating
all creative work with one agency.

WHAT THIS MEANS FOR THIS PROPOSAL:
1. Don't lead with the full price. Offer tiered pricing (Essential /
   Recommended / Premium) so they can choose their comfort level.
2. Price video competitively — they rejected ₹8L last time. Position video
   as part of a bundle, not a standalone line item.
3. Emphasise consolidation value — "one agency for everything" is what
   Rahul wants. Frame the total as cheaper than 5 separate vendors.
4. Address revision speed head-on in the scope — "48-hour turnaround on
   all revisions" shows we learned from the poster project.
5. Letter tone should be warm, not confident — this is a relationship
   we're deepening, not a cold pitch.
6. Send as PDF (Priya's preference), not just a link.
7. Factor in 10-15% negotiation buffer — price at ₹1.74Cr knowing
   they'll negotiate to ~₹1.55Cr.

DECISION CHAIN: Priya shortlists → Rahul approves budget → Procurement
issues PO. Typical cycle: 3-4 weeks. Proposal should be addressed to
Priya but structured to survive Rahul's financial review.
```

**How the Context Brief changes the other agents:**

| Agent | Without Context | With Context |
|---|---|---|
| **Research** | Searches broadly for company info | Skips known facts (already knows Priya, Rahul). Focuses on new developments since last interaction. |
| **Benchmark** | Standard market benchmarks | Also benchmarks against the client's past accepted price points. Flags any line item that exceeds what they've paid before. |
| **Template** | Selects based on project type keywords | Also considers relationship status. Overrides letter tone from "confident" to "warm" because of relationship depth. |
| **Cost Model** | Flat pricing with standard discounts | Switches to tiered pricing (flagged by context). Builds in 10-15% negotiation buffer. Positions video competitively. |
| **Narrative** | Generic covering letter opening | References the consolidation conversation with Rahul. Mentions the poster project success. Addresses revision speed proactively. Writes to survive the CFO's financial review. |
| **Email** | Generic intro email | Addresses Priya by name, references their last conversation, attaches PDF (her preference). |
| **Output** | Default format selection | Generates PDF as primary (Priya shares PDFs), site as secondary. Includes one-pager formatted for Rahul's financial review. |

### 8B.4 Context Ingestion Flow

#### Automatic (Connector-based)

```
User connects Gmail in NUPROP Settings
         │
         ▼
Initial Sync (background, one-time):
  → Fetch all threads with client domains in proposal-log.json
  → Process each thread through Claude (extract → classify → summarise)
  → Build Client Context Profiles for all known clients
  → Takes 5-30 minutes depending on email volume
         │
         ▼
Incremental Sync (every 6 hours):
  → Check for new emails with known client domains
  → Process new threads only
  → Update existing Client Context Profiles
  → Detect new client domains → prompt user: "I found emails 
    with smartworks.com — want me to create a client profile?"
         │
         ▼
Proposal-Triggered Deep Sync:
  → When user starts a new proposal for a client
  → Fetch ALL data for that client across ALL connectors
  → Refresh the Context Profile completely
  → Run in parallel with the Research Agent
```

#### Manual (Upload-based)

```
User: "Here's my last 5 emails with Priya from Tata Comms"
  → Paste or upload
  → Context Agent processes immediately
  → Extracts and updates Client Context Profile
  → Confirms: "Got it. I now know about the budget constraints
    and the revision feedback. This will shape the proposal."

User: "We did a poster project for them last year, ₹2.4L,
       they loved the speed but complained about revision delays"
  → Natural language input
  → Context Agent parses and stores as past_work entry
  → Confirms: "Noted. I'll emphasise fast revisions in the scope
    and reference the poster project success in the letter."
```

### 8B.5 Context-Aware Preference Overrides

The Context Agent can automatically override Proposal Preferences (Section 8.5) based on what it learns:

| Context Signal | Automatic Override | User Sees |
|---|---|---|
| Past proposal rejected for price | `pricing_model` → `tiered` | "Switching to tiered pricing — they rejected a flat quote before" |
| Client prefers PDFs over links | `primary_output` → `docx_first` | "Primary output set to PDF — Priya shares PDFs internally" |
| Budget constraints mentioned | Add `negotiation_buffer: 0.12` | "Building in 12% negotiation buffer based on procurement patterns" |
| Client likes "clean, corporate" | `site_theme` → `minimal` | "Using minimal theme — they've preferred corporate aesthetics" |
| Deep relationship (11 months, 47 interactions) | `letter_tone` → `warm` | "Warm tone — this is a relationship you're deepening" |
| Previous revision complaints | Add scope note: "48hr revisions" | "Adding explicit revision turnaround commitment to scope" |
| CFO approves >₹10L | Generate `one_pager` for Rahul | "Generating a one-pager formatted for CFO review" |

These overrides are always shown to the user with the reasoning. The user can accept or reject each one. The system never silently changes the proposal strategy.

### 8B.6 Privacy & Data Handling

**Principle**: Context data is the agency's data about their own client relationships. It never leaves the agency's account. It is never used to train models. It is never shared across agencies.

**Data storage:**
- Raw email/Slack content is processed by Claude for extraction, then discarded. Only the structured extraction (summary, sentiment, decisions, signals) is stored.
- Structured extractions are stored in PostgreSQL, encrypted at rest, scoped to the agency's account.
- No cross-agency data sharing. Agency A's client intelligence about Tata Communications is invisible to Agency B.
- User can delete all context data for a client at any time.

**Access control:**
- Gmail/Slack connectors use OAuth with minimum required scopes (read-only)
- User explicitly authorises each connector
- User can disconnect a connector at any time — all data from that connector is deleted within 24 hours
- Connector tokens are encrypted and stored separately from context data

**GDPR / Data protection:**
- Client contacts' names and email addresses are stored (necessary for the feature to work)
- No data about the client's employees beyond what's in the agency's own emails
- Agency can request full data export or deletion
- Context data has a configurable retention period (default: 24 months, adjustable)

### 8B.7 Context Quality Score

Not all context is equally useful. The engine scores context quality to decide how much to rely on it:

| Factor | Score Contribution |
|---|---|
| Recency (interaction in last 30 days) | +25 |
| Volume (>10 interactions) | +20 |
| Depth (pricing data available) | +20 |
| Breadth (multiple data sources) | +15 |
| Past work history (completed projects) | +10 |
| Decision chain known | +10 |

**Score interpretation:**
- 0-30: **Thin context** — treat like a cold pitch. Rely on web research. Don't make assumptions.
- 31-60: **Moderate context** — some relationship data. Use it to calibrate tone but verify pricing assumptions with the user.
- 61-80: **Rich context** — deep relationship data. Auto-suggest preferences, reference past work, calibrate pricing.
- 81-100: **Full context** — the system knows this client almost as well as you do. Autonomous preference overrides are highly reliable.

The Context Brief includes the quality score so the Orchestrator knows how much to trust it:

```
Context quality: 72/100 (Rich)
Sources: Gmail (34 threads), Google Drive (6 documents), 
         Calendar (8 meetings), Manual notes (2)
Gaps: No CRM data. No Slack channel. Last interaction 3 days ago.
```

### 8B.8 Updated Agent System (with Context Agent)

The Context Agent joins the parallel agent spawning in Section 8A:

```
User: "new proposal for Tata Communications"
              │
              ▼
     ORCHESTRATOR spawns in parallel:
              │
    ┌─────────┼──────────────────────────────────────────┐
    │         │                                          │
    ▼         ▼         ▼         ▼         ▼           ▼
┌────────┐┌────────┐┌────────┐┌────────┐┌────────┐┌────────┐
│CONTEXT ││RESEARCH││BENCH-  ││TEMPLATE││PORT-   ││COMPET- │
│AGENT   ││AGENT   ││MARK    ││AGENT   ││FOLIO   ││ITOR   │
│        ││        ││AGENT   ││        ││AGENT   ││AGENT   │
│Pulls   ││Web     ││Market  ││Selects ││Past    ││Compet- │
│Gmail,  ││search  ││pricing ││template││work    ││itive   │
│Drive,  ││for     ││data    ││        ││matches ││intel   │
│Cal,    ││public  ││        ││        ││        ││        │
│Slack   ││info    ││        ││        ││        ││        │
└───┬────┘└───┬────┘└───┬────┘└───┬────┘└───┬────┘└───┬────┘
    │         │         │         │         │         │
    └─────────┴─────────┴────┬────┴─────────┴─────────┘
                             │
                             ▼
                    ORCHESTRATOR merges
                             │
    Context Brief ───────────┤
    shapes all other ────────┤
    agent outputs            │
                             ▼
                    Present to user with
                    context-aware recommendations
```

**Critical flow**: The Context Agent's output (the Context Brief) is injected into the prompts of all other agents. It arrives before or alongside the Research Agent's results. If the Context Agent is slow (e.g., Gmail API latency), the Orchestrator proceeds with other agents and retroactively applies context when it arrives.

### 8B.9 Phase Rollout

| Phase | Context Features |
|---|---|
| A (Claude Code) | Manual only — user pastes emails or types context into chat. Context Agent extracts and stores in `research/[client]/context.json` |
| B (Validation) | Manual + Google Drive connector (search for past proposals and meeting notes about the client) |
| C (Platform) | Gmail + Google Drive + Calendar connectors. Automatic sync. Context-aware preference overrides. Context Brief in agent prompts. |
| C+ (Month 4-6) | Slack connector. Sentiment timeline. Context quality scoring. |
| D (Growth) | CRM connectors (HubSpot, Pipedrive). WhatsApp connector. Cross-proposal learning (what worked for similar clients). |

### 8B.10 For Phase A (Immediate Use in Claude Code)

Even without connectors, you can use this today. Add this to SKILL.md Step 1:

```markdown
### Step 0: Context Check

Before starting the brief intake, check if context exists for this client:

1. Check `research/[client-slug]/context.json` — if it exists, load it.
2. If no context file, ask the user:

   "Do you have any history with [Client]? This could be:
   - Past emails or conversations
   - Previous proposals (won or lost)
   - Meeting notes
   - Budget signals or pricing feedback
   - Anything about how they make decisions or what they prefer

   Paste anything relevant, or say 'cold pitch' if this is first contact."

3. If the user provides context, process it:
   - Extract contacts, sentiment, pricing signals, past work, preferences
   - Save structured context to `research/[client-slug]/context.json`
   - Generate a Context Brief

4. Inject the Context Brief into all subsequent steps.

5. If returning to an existing client, remind the user:
   "I have context from your previous interactions with [Client]:
   - [summary of past work]
   - [key pricing signal]
   - [relationship status]
   
   Anything new to add?"
```

---

### 8B.11 Email Intelligence Layer — Vector Search & Auto-Classification

#### Why Vector Search

The connectors in 8B.1 fetch emails by client domain — exact match. But the most valuable signals are often in emails you wouldn't think to search for:

- A sales team member emailed a Tata Communications contact 6 months ago about something unrelated — an existing relationship you didn't know about
- Someone forwarded a competitor's proposal for a different client in the same industry — pricing intelligence buried in an unrelated thread
- A meeting note from a conference mentions the client's VP complaining about their current agency — hidden in a thread about the event, not the client

Vector search finds these because it matches on meaning, not keywords. "Budget constraints at a telecom company" matches even if the email never mentions "Tata Communications" by name.

#### Architecture: Process at Ingestion, Not Query Time

The common mistake is building a RAG pipeline that does expensive synthesis at query time — when the user is waiting. Instead, do the expensive work continuously in the background so that when a proposal starts, the context is already built.

```
CONTINUOUS BACKGROUND PIPELINE (always running)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Gmail/Slack/Drive sync (every 15 min)
         │
         ▼
Haiku classifier (per email, ~₹0.01)
  → client, type, sentiment, entities, priority, summary
         │
         ▼
Voyage-3-large embedder (per email, ~₹0.001)
  → 1024-dim vector
         │
         ▼
PostgreSQL + pgvector (Supabase)
  → structured metadata + vector stored together
  → raw email body NOT stored (stays in Gmail)

AT PROPOSAL TIME (instant retrieval)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Metadata filter: all emails for this client domain
2. Vector search: semantically related emails across ALL clients
3. Merge + deduplicate
4. Sonnet synthesis → context.json (one call)
```

#### Auto-Classification Module

Every new email that arrives is processed by Haiku automatically:

```python
# Background sync worker — runs every 15 minutes
class EmailSyncWorker:
    """Syncs new emails, classifies with Haiku, embeds, stores in pgvector."""

    async def run(self):
        for agency in await self.get_agencies_with_gmail():
            new_messages = await self.gmail.fetch_since(
                agency.gmail_credentials,
                agency.last_sync_timestamp
            )

            for msg in new_messages:
                # Classify with Haiku (₹0.01 per email)
                classification = await self.classify_with_haiku(msg)

                # Auto-detect client from domain or entity matching
                client = await self.resolve_client(msg, classification)

                # Embed the summary (not raw body)
                embedding = await self.embed(classification['summary'])

                # Store in pgvector
                await self.store(agency.id, msg, classification,
                                client, embedding)

            await self.update_last_sync(agency)

    async def classify_with_haiku(self, message: dict) -> dict:
        """Haiku classification — structured extraction per email."""
        response = await self.claude.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system="""Classify this email. Return ONLY JSON:
            {
              "client_domain": "detected domain",
              "client_name": "resolved name or null",
              "message_type": "brief | feedback | negotiation | scheduling |
                              follow_up | internal_discussion | general",
              "sentiment": "positive | neutral | negative",
              "entities": {
                "people": [{"name": "", "role_guess": ""}],
                "money": ["any amounts mentioned"],
                "projects": ["any project names"]
              },
              "priority": "high | medium | low",
              "summary": "2-sentence summary"
            }""",
            messages=[{"role": "user", "content": message['body'][:2000]}]
        )
        return json.loads(response.content[0].text)

    async def resolve_client(self, msg, classification) -> str:
        """Auto-detect which client this email belongs to."""
        domain = extract_domain(msg['from'])

        # 1. Check known client domains
        known = await self.db.query(
            "SELECT client_name FROM clients WHERE domain = :d", d=domain)
        if known:
            return known.client_name

        # 2. Check entities against known contact names
        for entity in classification.get('entities', {}).get('people', []):
            match = await self.db.query(
                "SELECT client_name FROM client_contacts WHERE name ILIKE :n",
                n=f"%{entity['name']}%")
            if match:
                return match.client_name

        # 3. Unmatched — flagged for manual review in dashboard
        return None
```

#### Database Schema (PostgreSQL + pgvector on Supabase)

```sql
-- Enable pgvector extension (one-time, already available on Supabase)
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE email_index (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agency_id UUID NOT NULL REFERENCES agencies(id),
    gmail_message_id TEXT NOT NULL,
    gmail_thread_id TEXT NOT NULL,

    -- Classification (from Haiku)
    client_domain TEXT,
    client_name TEXT,
    message_type TEXT,
    sentiment TEXT,
    priority TEXT,
    summary TEXT NOT NULL,
    entities JSONB,

    -- Metadata (from Gmail headers)
    from_address TEXT,
    to_addresses TEXT[],
    subject TEXT,
    date TIMESTAMPTZ,
    has_attachments BOOLEAN DEFAULT false,

    -- Vector embedding (1024-dim, Voyage-3-large)
    embedding vector(1024),

    -- Housekeeping
    synced_at TIMESTAMPTZ DEFAULT now(),

    -- No raw email body — only summary and classification
    -- Raw stays in Gmail; fetched on-demand if Sonnet needs it
    UNIQUE(agency_id, gmail_message_id)
);

-- Fast client lookup
CREATE INDEX idx_email_client ON email_index(agency_id, client_domain);
CREATE INDEX idx_email_date ON email_index(agency_id, date DESC);
CREATE INDEX idx_email_type ON email_index(agency_id, message_type);
CREATE INDEX idx_email_sentiment ON email_index(agency_id, sentiment);

-- Vector similarity search (IVFFlat — good for <1M rows)
CREATE INDEX idx_email_vector ON email_index
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Unmatched emails for manual review
CREATE VIEW unmatched_emails AS
    SELECT * FROM email_index
    WHERE client_name IS NULL
    ORDER BY date DESC;
```

#### Hybrid Retrieval at Proposal Time

When the Context Agent runs for a new proposal:

```python
# viewmodels/context_agent_vm.py

class ContextAgentViewModel:
    async def build_context(self, agency_id: str, client_domain: str,
                            project_description: str) -> dict:
        """Hybrid retrieval: metadata filter + vector search."""

        # 1. DIRECT: All emails for this client (exact domain match)
        direct = await self.db.fetch_all("""
            SELECT summary, sentiment, entities, message_type,
                   from_address, date, subject
            FROM email_index
            WHERE agency_id = :agency_id
            AND client_domain = :domain
            ORDER BY date DESC
            LIMIT 100
        """, agency_id=agency_id, domain=client_domain)

        # 2. SEMANTIC: Related emails across ALL clients
        #    This finds hidden connections — competitor intel,
        #    industry pricing, internal strategy discussions
        project_embedding = await self.embed(project_description)
        semantic = await self.db.fetch_all("""
            SELECT summary, sentiment, entities, client_name,
                   message_type, date, subject,
                   embedding <=> :query AS distance
            FROM email_index
            WHERE agency_id = :agency_id
            AND client_domain != :domain  -- exclude direct matches
            AND embedding <=> :query < 0.35  -- similarity threshold
            ORDER BY distance ASC
            LIMIT 20
        """, agency_id=agency_id, domain=client_domain,
            query=project_embedding)

        # 3. MERGE: Direct relationship + hidden connections
        all_relevant = {
            "direct_emails": direct,       # "what we know about this client"
            "related_signals": semantic     # "what else is relevant"
        }

        # 4. SYNTHESISE: One Sonnet call → context.json
        context_profile = await self.synthesise_with_sonnet(all_relevant)

        return context_profile
```

The vector search in step 2 is where discovery happens. It might find:
- An email to a different telecom client quoting ₹5L for a similar video → pricing benchmark from your own history
- An internal thread where a designer said "Tata's brand is quite conservative, they won't go for anything experimental" → creative direction signal
- A competitor's proposal that someone forwarded for reference → competitive intelligence

None of these would surface from a domain search for "tatacommunications.com."

#### What Gets Stored vs. What Stays in Gmail

| Data | Stored in pgvector | Stays in Gmail |
|---|---|---|
| 2-sentence summary | ✓ | — |
| Classification (type, sentiment, priority) | ✓ | — |
| Entities (people, money, projects) | ✓ | — |
| 1024-dim embedding | ✓ | — |
| Email headers (from, to, date, subject) | ✓ | — |
| Full email body | ✗ | ✓ |
| Attachments | ✗ | ✓ |
| Images | ✗ | ✓ |

If Sonnet needs the full email text during synthesis (rare — the summary is usually enough), it fetches from Gmail API on demand. This keeps storage small (~1KB per email in pgvector vs ~50KB for full body), avoids PII liability, and means if a user disconnects Gmail, you delete the index rows and nothing sensitive remains.

#### Cost at Scale

| Component | 10 users, 1K emails/day | 50 users, 10K emails/day |
|---|---|---|
| Haiku classification | ₹300/month | ₹3,000/month |
| Voyage embedding | ₹30/month | ₹300/month |
| pgvector storage (Supabase) | Included in plan | Included in plan |
| Background worker (Railway) | ₹500/month | ₹1,500/month |
| Gmail API | Free (quota: 250M/day) | Free |
| **Total** | **~₹830/month** | **~₹4,800/month** |

Under 1% of projected MRR at each scale tier.

#### Phase Rollout

| Phase | Email Intelligence |
|---|---|
| A (Claude Code) | Manual: user pastes emails. No vector search. |
| B (Validation) | Gmail API direct fetch on demand. No background sync. No vectors. |
| C (Platform launch) | Background sync + Haiku classification + pgvector. Hybrid retrieval. |
| C+ (Month 4-6) | Add Slack and Drive to the sync pipeline. Cross-source entity resolution. |
| D (Growth) | Semantic alerts: "I found a new email that's relevant to your pending proposal for [Client]." Auto-update context profiles when new emails arrive. | — User-Configurable Controls

### Why This Matters

The template system auto-selects sensible defaults, but every proposal has nuances that only the user knows:

- "This client hates hard-sell language — keep it soft"
- "They asked for tiered pricing with 3 options"
- "Don't include a cost rationale — they explicitly said they don't want justification"
- "Make it short — this is a ₹2L job, not a ₹2Cr campaign"

These are decisions the AI can't infer from the brief. The user needs a way to set them explicitly.

### Two-Level Configuration

```
AGENCY DEFAULTS (set once in Settings)
    │
    ▼
TEMPLATE DEFAULTS (auto-selected per proposal type)
    │
    ▼
USER OVERRIDES (set per proposal during Step 1b)
    │
    ▼
AI GENERATES with final merged preferences
```

Each level overrides the one above. If the agency default letter tone is "confident," the template can override to "warm," and the user can override to "technical_showcase" for this specific proposal.

### 8.5.1 Covering Letter Preferences

**Mood / Tone** (single select):

| Option | Description | When to Use |
|---|---|---|
| `confident` | Bold, direct, assumes the win, makes claims about impact | Strong competitive position, proven track record with similar clients |
| `warm` | Empathetic, collaborative, relationship-focused | Warm introductions, culture-driven clients, long-term partnerships |
| `technical_showcase` | Evidence-based, architecture-first, shows depth | Technology projects, engineering-led decision makers |
| `research_heavy` | Opens with data about the client's problem, backs everything with sources | Analytical clients, consultancy-style engagements |
| `relationship_builder` | Acknowledges pain, positions as partner not vendor | Retainer pitches, clients burned by previous agencies |
| `understated` | Minimal, no adjectives, lets the work speak | Design-savvy clients who hate marketing language |

**Opening Strategy** (single select):

| Option | First 2-3 Paragraphs Focus On |
|---|---|
| `client_story` | The client's origin, history, recent milestones (default) |
| `client_problem` | The specific challenge they face, with evidence |
| `market_context` | Industry trends that make this project urgent |
| `provocative_question` | Opens with a question that reframes their thinking |
| `shared_connection` | A mutual contact, event, or conversation that led to this |
| `straight_to_scope` | Skip the preamble, go directly to what we're proposing (for clients who said "just send me the quote") |

**Length** (single select):
- `concise` — 200-300 words (quick quotes, existing relationships)
- `standard` — 400-600 words (default)
- `extended` — 600-900 words (complex multi-workstream proposals)

**Custom instructions** (free text):
The user can type specific guidance that overrides everything else:
```
"Mention that we met at the Nasscom event last week.
Don't mention our Tata Communications work — they're a competitor.
The decision maker is the CFO, not the CMO — frame everything in ROI terms."
```

This free-text field is injected directly into the AI's prompt for Step 5a, giving the user precise control without needing to understand the template system.

### 8.5.2 Pricing Structure Preferences

**Pricing Model** (single select):

| Model | Description | How the Cost Model Is Presented |
|---|---|---|
| `flat` | Single total price for the entire scope | One table, one number, one discount line (default) |
| `tiered` | 2-3 pricing tiers (Good / Better / Best) | Three columns showing what's included at each level |
| `modular` | Pick-and-choose modules, each priced independently | Grouped modules with individual prices, client selects what they want |
| `phased` | Price broken into phases (Phase 1: ₹X, Phase 2: ₹Y) | Sequential phases with clear deliverables and costs per phase |
| `retainer_plus_project` | Monthly retainer + separate project fees | Two sections: fixed monthly retainer table + variable project items |
| `day_rate` | Daily or hourly rate × estimated days | Rate card presentation with effort estimates |

**Tiered Pricing Detail** (if `tiered` selected):

The AI generates 3 tiers automatically from the deliverable list:

```
                    ESSENTIAL        RECOMMENDED       PREMIUM
                    (Good)           (Better)          (Best)

Brand Identity      Logo only        Logo + Guidelines  Full rebrand
Website            5-page site       10-page + CMS     20-page + AI demo
Video              1 corporate film  3 films + reels   Docu-series
Social             10 posts          25 posts + mgmt   Full retainer

                    ₹8,50,000        ₹16,40,000        ₹28,00,000
```

**User controls for tiered pricing:**
- Which tier to recommend (highlight) — default: middle tier
- Tier names — customisable (e.g., "Starter / Growth / Enterprise" or "Phase 1 / Full / With Retainer")
- Which deliverables to include/exclude per tier
- Whether to show savings vs. à la carte

**Discount Strategy** (multi-select):

| Option | Effect |
|---|---|
| `annual_bundle` | 12% discount for year-long commitment |
| `half_year_bundle` | 7% discount for 6-month commitment |
| `early_bird` | X% discount if signed within N days |
| `volume_discount` | Tiered discount based on total value |
| `loyalty_discount` | 5% for existing clients |
| `strategic_discount` | Manual discount with custom rationale ("portfolio-building rate") |
| `no_discount` | Full rate card pricing, no discounts |

**Payment Terms** (single select):

| Option | Schedule |
|---|---|
| `milestone` | 20% advance, 50% mid-project, 30% completion (default) |
| `monthly` | Equal monthly installments across project duration |
| `quarterly` | Quarterly billing for retainer engagements |
| `50_50` | 50% advance, 50% on completion |
| `on_completion` | 100% on completion (high-trust existing clients only) |
| `custom` | User specifies custom payment schedule |

### 8.5.3 Scope & Detail Preferences

**Scope Detail Level** (single select):
- `brief` — 50-100 words per deliverable (quick quotes)
- `standard` — 100-150 words per deliverable (default)
- `detailed` — 150-250 words per deliverable (enterprise RFPs, procurement)
- `exhaustive` — 250-400 words per deliverable with sub-tasks, dependencies, acceptance criteria (large-scale projects)

**Revision Policy** (single select):
- `standard` — 3 options, 2 revision rounds (Veeville default)
- `generous` — 3 options, 3 revision rounds (high-value clients)
- `lean` — 2 options, 1 revision round (budget-conscious)
- `custom` — User specifies options and rounds per deliverable

**Include/Exclude Sections** (multi-select toggle):

| Section | Default | User Can Toggle |
|---|---|---|
| Covering letter | Always | ✓ (can skip for "just send the quote" requests) |
| Executive summary | On | ✓ |
| Scope descriptions | Always | — |
| Cost model | Always | — |
| Cost rationale | >₹10L | ✓ |
| Timeline | On | ✓ |
| Team section | On | ✓ |
| Terms & conditions | On | ✓ |
| Case studies / portfolio | Off | ✓ |
| Testimonials | Off | ✓ |
| Demo embed | Off | ✓ (only if template allows) |

### 8.5.4 Output Format Preferences

**Primary delivery** (single select):
- `site_first` — Interactive site as primary, DOCX as backup (default for >₹10L)
- `docx_first` — DOCX as primary, site optional (default for <₹10L)
- `email_only` — Embed everything in the email (for quick quotes <₹5L)
- `deck_first` — Slide deck as primary (for presentation-oriented clients)

**Additional outputs** (multi-select):
- [ ] PDF (from DOCX)
- [ ] PDF (designed, from HTML)
- [ ] One-pager
- [ ] Cost rationale document
- [ ] Slide deck (PPTX)

**Site preferences** (if site selected):
- Theme override (editorial / bold / minimal / dark / warm)
- Password protection (on/off, custom password)
- Custom domain or default nuprop.app subdomain
- Expiry date (auto-disable after N days)

### 8.5.5 How Preferences Flow Through the Pipeline

**In Claude Code (Phase A):**

After Step 1b (template selection), the AI asks:

```
Template selected: Anniversary / Milestone Campaign

I'll use these defaults — change anything?

LETTER:     Warm tone, opens with client's origin story
PRICING:    Flat pricing with annual bundle discount
SCOPE:      Detailed (150-250 words per deliverable)
OUTPUTS:    Interactive site + DOCX + PDF + cost rationale + email

Want to change any of these? For example:
- "Use tiered pricing with 3 options"
- "Make the letter more confident"
- "Skip the cost rationale"
- "Add a one-pager"
```

The user responds in natural language. The AI parses the overrides and merges them with the template defaults.

**In the Web App (Phase C):**

A collapsible **Proposal Settings** panel sits in the right sidebar of the chat interface. It pre-fills from the selected template. The user can click to change any setting without typing:

```
┌──────────────────────────────────┐
│ PROPOSAL SETTINGS                │
│ Template: Anniversary Campaign   │
├──────────────────────────────────┤
│                                  │
│ LETTER                           │
│ Tone:    [Warm ▼]                │
│ Opening: [Client story ▼]       │
│ Length:  [Standard ▼]            │
│ Notes:   [_________________]     │
│                                  │
│ PRICING                          │
│ Model:   [Flat ▼]               │
│ Discount: ☑ Annual bundle       │
│           ☐ Early bird          │
│           ☐ Loyalty             │
│ Payment:  [Milestone ▼]         │
│                                  │
│ SCOPE                            │
│ Detail:   [Detailed ▼]          │
│ Revisions: [3 options, 2 rounds] │
│                                  │
│ OUTPUTS                          │
│ Primary:  [Site first ▼]        │
│ ☑ DOCX  ☑ PDF  ☐ One-pager     │
│ ☑ Cost rationale  ☐ Deck        │
│                                  │
│ SITE                             │
│ Theme:    [Editorial ▼]         │
│ Password: [Off ▼]               │
│ Expires:  [30 days ▼]           │
│                                  │
│ SECTIONS                         │
│ ☑ Letter  ☑ Summary  ☑ Scope   │
│ ☑ Investment  ☑ Timeline        │
│ ☑ Team  ☐ Case studies          │
│ ☐ Testimonials  ☐ Demo          │
│                                  │
└──────────────────────────────────┘
```

Every change updates in real-time. The chat continues with the AI using the updated preferences. If the user changes "Pricing Model" from "Flat" to "Tiered" mid-conversation, the AI regenerates the cost model with 3 tiers.

### 8.5.6 Preference Persistence

**Agency defaults** are stored on the Agency profile in PostgreSQL:
```json
{
  "default_preferences": {
    "letter_tone": "confident",
    "letter_opening": "client_story",
    "letter_length": "standard",
    "pricing_model": "flat",
    "discounts": ["annual_bundle"],
    "payment_terms": "milestone",
    "scope_detail": "standard",
    "revision_policy": "standard",
    "primary_output": "site_first",
    "additional_outputs": ["docx", "pdf", "cost_rationale"],
    "site_theme": "editorial",
    "site_password": false,
    "site_expiry_days": 30
  }
}
```

**Per-proposal overrides** are stored on the Proposal record:
```json
{
  "preferences": {
    "letter_tone": "warm",
    "pricing_model": "tiered",
    "tier_names": ["Essential", "Recommended", "Premium"],
    "recommended_tier": 2,
    "custom_instructions": "Mention Nasscom event. Don't reference Tata Communications."
  }
}
```

**Template defaults** are in `veeville-templates.json` as already defined.

**Merge order**: Agency defaults → Template defaults → User overrides. Last write wins.

### 8.5.7 Tiered Pricing — Full Implementation

Since tiered pricing is the most complex preference, here's the full spec:

**How the AI generates tiers:**

1. Start with the full deliverable list from the cost model (all items the user approved)

2. Split into 3 tiers:
   - **Essential**: Core deliverables only. Remove "nice to have" items. Reduce quantities (e.g., 10 social posts instead of 25). Remove premium options (basic film instead of premium).
   - **Recommended**: The original cost model as-is. This is what you'd pitch with flat pricing.
   - **Premium**: Add premium upgrades. More deliverables. Higher-end options (brand film instead of corporate film). Add retainer. Add demo embed. Add additional outputs.

3. Price each tier independently (no discounts applied to Essential, standard discounts to Recommended, premium pricing with extras on Premium)

4. Calculate savings vs. à la carte for Recommended and Premium tiers

**Output format in the proposal:**

```
THREE WAYS TO WORK TOGETHER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

                 ESSENTIAL         RECOMMENDED ★        PREMIUM
                                   (Best value)

Brand Identity   Logo refresh      Full identity        Full rebrand +
                                   system               sub-brand architecture

Video            1 corporate       Corporate film +     4-episode
                 film (3 min)      4 social reels       docu-series + reels

Digital          Email             Microsite +          AI-powered
                 templates         social campaign      interactive microsite

Events           Townhall          Townhall +           Flagship event +
                 creative          2 activations        townhall + 5 activations

Annual Support   —                 —                    12-month creative
                                                        retainer

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INVESTMENT       ₹42,00,000        ₹1,04,00,000         ₹1,74,00,000

Monthly          ₹3,50,000/mo      ₹8,67,000/mo         ₹14,50,000/mo
equivalent       (for 12 months)

Savings vs.      —                 18% vs. à la carte   24% vs. à la carte
separate

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**In the interactive site**: Each tier is a clickable column. The recommended tier is visually highlighted. Clicking a tier reveals full deliverable details for that tier. A "Compare tiers" toggle shows a row-by-row feature comparison.

**In the DOCX**: A 3-column table with the same structure, followed by individual scope descriptions for the recommended tier only (with notes on what Essential removes and Premium adds).

**Why tiered works**: Research shows tiered pricing increases close rates by 20-30% because it gives the client agency over the decision. They choose their budget level rather than accepting/rejecting a single number. The middle tier wins ~60% of the time.

---

---

## 9. Output Options — Comprehensive Format Guide

This is NUPROP's key differentiator: the same proposal content, generated once, renders into multiple output formats from a single source of truth. The user creates the proposal through the chat interface; the system generates all requested formats simultaneously.

### 9.1 Output Format Matrix

| Format | Best For | When To Use | Phase |
|---|---|---|---|
| **Interactive Proposal Site** | Design agencies, tech consultancies | High-value pitches where the proposal itself demonstrates capability | A |
| **DOCX Proposal Document** | All industries | Formal submission, procurement processes, internal circulation | A |
| **PDF Proposal** | All industries | Email attachment, printing, archival | A |
| **Cost Rationale Document** | Complex/expensive proposals | When pricing needs justification, negotiations, procurement review | A |
| **One-Pager / Executive Summary** | Senior decision-makers | When the full proposal is too detailed for initial review | A |
| **Slide Deck (PPTX)** | Presentation-oriented clients | When the client expects a deck for an in-person/virtual walkthrough | C |
| **Notion Page** | Tech-savvy clients, startups | When the client's team works in Notion | C |
| **Google Doc** | Collaborative review | When the client wants to comment/edit inline | C |
| **Email-Embedded Proposal** | Quick quotes, small projects | Sub-₹5L proposals where a full site is overkill | C |
| **Deal Room** | Enterprise pitches | Multi-document proposals with NDAs, case studies, credentials | D |

### 9.2 Interactive Proposal Site (Primary Output)

The flagship output. A hosted website that replaces the PDF.

**What it is**: A single-page, scroll-driven website with animated sections, interactive cost cards, embedded portfolio, team profiles, and a CTA section. Hosted on a unique URL (e.g., `proposals.veeville.com/tata-communications`). Password-protectable. Analytics-tracked.

**Sections available** (user selects which to include per proposal):

| Section | Description | Always / Optional |
|---|---|---|
| Cover | Agency logo, client name, project title, date | Always |
| Covering Letter | Full editorial text, max-width 640px | Always |
| Theme Showcase | Visual reveal of creative themes (if applicable) | Optional |
| About / Credentials | Agency intro, relevant case studies from portfolio library | Optional |
| Scope Cards | Deliverable cards in 2-col grid, expandable on click | Always |
| Investment Summary | Animated counter, workstream table, market comparison | Always |
| Cost Rationale | Per-category benchmark cards (inline or linked) | Optional |
| Timeline | Visual phase timeline, horizontal/vertical responsive | Always |
| Team | Member cards with photo, role, allocation | Optional |
| Demo Embed | Working prototype embedded in the proposal (see 9.2.1) | Optional |
| Gallery | Portfolio images, mockups, campaign previews | Optional |
| Testimonials | Client quotes from portfolio library | Optional |
| CTA | Schedule call / Download PDF / Email us | Always |

**Site themes** (5 built-in, custom available):

| Theme | Vibe | Best For |
|---|---|---|
| Editorial | Warm cream, serif headings, magazine feel | Brand/campaign proposals |
| Bold | Dark bg, large type, high contrast | Technology/product proposals |
| Minimal | White bg, sans-serif, grid-aligned | Architecture/consulting proposals |
| Dark | Near-black, subtle gradients, premium | Luxury/enterprise proposals |
| Warm | Soft palette, rounded corners, friendly | Startup/SMB proposals |

**Technical details**: Static Astro build, deployed to Fly.io per-site. Zero JS by default, hydrated on demand for interactive components. Lighthouse >90. Mobile responsive. Loads in <2 seconds. `noindex` meta tag prevents search indexing.

#### 9.2.1 Demo-in-Proposal (Proof of Concept Embedding)

**The most powerful feature in NUPROP.** For proposals that include a technology deliverable (website, app, AI chatbot, dashboard), the user can embed a working prototype directly in the proposal site.

**How it works**:
1. During proposal generation, if a deliverable involves technology (microsite, chatbot, dashboard), NUPROP asks: "Want to include a live demo of this in the proposal?"
2. If yes, it generates a minimal working prototype:
   - AI chatbot → React chat component with Claude API, pre-loaded with client knowledge
   - Website → Static HTML/CSS mockup of the proposed homepage
   - Dashboard → Interactive chart with sample data
3. The prototype is embedded as an iframe in the proposal site's "Demo" section
4. The client interacts with it directly — no separate link, no Figma prototype

**Why this wins pitches**: No other agency shows a working product in their pitch. They show Figma mockups or slide renderings. When a client types a question into a chatbot demo and gets a real answer about their own company's history, the pitch is essentially over.

**Reference implementation**: The Tata Communications T-COMM demo (see Appendix C).

### 9.3 DOCX Proposal Document

The formal document for procurement processes and internal circulation.

**Structure**:
1. Cover page (agency logo, client name, project title, date, confidentiality)
2. Table of contents
3. Covering letter (full text)
4. Executive summary (300-400 words)
5. Scope of engagement (per-workstream, with tables)
6. Cost summary (line-item table with subtotals, discounts, total)
7. Team structure (table with roles and allocation)
8. Timeline (table with phases and key milestones)
9. Terms & conditions
10. Contact information

**Technical**: Generated using `docx` npm package. Arial font, proper heading styles, DXA table widths, ShadingType.CLEAR. Validated with the docx skill's validate.py. All tables have dual widths (columnWidths + cell width) for cross-platform compatibility.

### 9.4 PDF Proposal

**Two generation paths**:
1. **From DOCX** (default): LibreOffice headless conversion. Reliable, matches DOCX exactly. Best for formal documents.
2. **From HTML** (premium): Puppeteer renders the interactive site with a print stylesheet. More beautiful — the PDF looks like a designed report, not a Word doc. Best for design agencies where the PDF itself is a portfolio piece.

Both paths produce a single PDF with embedded fonts and images.

### 9.5 Cost Rationale Document

A standalone companion document that justifies every line item.

**Structure**: HTML document (renders beautifully in browser, prints well) with:
- Per-category benchmark cards showing market range + our price + sources
- Value comparison table (our bundled price vs. à la carte from separate vendors)
- Savings calculation and percentage
- Source citations with URLs

**When to generate**: Automatically for proposals >₹10L. Optional for smaller proposals. Can be embedded in the proposal site as an expandable section or provided as a separate document.

### 9.6 One-Pager / Executive Summary

A single-page PDF or HTML document for senior decision-makers who don't have time for the full proposal.

**Structure** (A4 single page):
- Client name + project title (header)
- 3-sentence problem statement
- Proposed approach (3-5 bullet points)
- Key deliverables (listed, not described)
- Investment: single total number with monthly equivalent
- Timeline: single-line phase summary
- CTA: one line with contact details

**Design**: Uses the agency's brand colours. Clean, spacious, no tables. Feels like a premium brief, not a compressed proposal.

### 9.7 Slide Deck (PPTX) — Phase C

For clients who expect a presentation format, especially for in-person pitches.

**Structure** (15-20 slides):
1. Title slide
2. "We understand your challenge" (1-2 slides from client research)
3. "Our approach" (1-2 slides)
4. Scope overview (1 slide per workstream, visual cards not tables)
5. Investment summary (1 slide, clean table)
6. Timeline (1 slide, visual)
7. Team (1 slide, photo grid)
8. Relevant case studies (2-3 slides from portfolio)
9. "Let's start" (CTA slide)

**Technical**: Generated using `python-pptx` or the pptx skill. Agency brand template applied automatically. Speaker notes generated from the narrative content.

### 9.8 Notion Page — Phase C

For tech-savvy clients and startups who live in Notion.

**How it works**: NUPROP generates the proposal content as structured Notion blocks via the Notion API. The proposal appears as a page in a shared Notion workspace. The client can comment inline, toggle sections, and the engagement is tracked via Notion's built-in analytics.

### 9.9 Google Doc — Phase C

For clients who want collaborative review.

**How it works**: NUPROP generates the proposal content and creates a Google Doc via the Google Docs API. Shared with the client's email. They can comment and suggest edits. The agency gets notifications. Formatting is simpler than DOCX but the collaboration experience is native.

### 9.10 Email-Embedded Proposal — Phase C

For quick quotes and small projects (sub-₹5L) where a full site or document is overkill.

**How it works**: The proposal is composed as a responsive HTML email with inline CSS. Sent directly from NUPROP (or via Gmail/Outlook integration). Contains: brief scope summary, pricing table, timeline, and CTA button. The client can accept/respond without opening an attachment.

### 9.11 Deal Room — Phase D

For enterprise pitches that require multiple documents.

**How it works**: A password-protected microsite containing multiple documents: the proposal, the cost rationale, relevant case studies, team credentials, NDAs, and any supplementary material. The client sees a clean dashboard of documents. Each document is tracked individually (who opened what, when, for how long).

### 9.12 Output Selection UX

During Step 6 of the pipeline, NUPROP suggests outputs based on proposal value and type:

| Proposal Value | Suggested Outputs |
|---|---|
| < ₹5L | Email-embedded + PDF attachment |
| ₹5L - ₹25L | DOCX + PDF + one-pager |
| ₹25L - ₹1Cr | Interactive site + DOCX + PDF + cost rationale |
| > ₹1Cr | Interactive site + demo embed + DOCX + PDF + cost rationale + one-pager + slide deck |

The user can override and select any combination.

---


---


## 10. Interactive Proposal Site Generator

### Site Architecture

Every generated proposal site follows this structure:

```
/                           → Cover + agency branding
/#letter                    → Covering letter (editorial layout)
/#about                     → About the agency + relevant case studies
/#scope                     → Deliverable cards (expandable)
/#investment                → Cost breakdown with benchmarks
/#timeline                  → Visual phase timeline
/#team                      → Team members assigned to project
/#next-steps                → CTA: schedule call, download PDF, email
```

### Design System

The site generator ships with 5 visual themes:

1. **Editorial** — Warm cream background, serif headings, generous whitespace, feels like a magazine article (used for the Tata Communications pitch)
2. **Bold** — Dark background, large type, high-contrast accent colours, makes a statement
3. **Minimal** — White background, sans-serif only, grid-aligned, lets the content speak
4. **Dark** — Near-black background, subtle gradients, premium/luxury feel
5. **Warm** — Soft colour palette, rounded corners, approachable and friendly

Each theme applies the agency's brand colours and fonts automatically.

### Component Library

**Cover Component**:
- Agency logo, client name, project title
- Date, version, confidentiality notice
- Animated entrance (fade + slide)

**Letter Component**:
- Full-width editorial text layout
- Max-width 640px, line-height 1.9
- Signature with name and title

**Scope Cards**:
- Grid of cards (2-col desktop, 1-col mobile)
- Each card: title, brief description, price tag
- Click to expand: full scope, inclusions, exclusions, market benchmark
- Animate expand/collapse

**Investment Summary**:
- Animated total counter
- Workstream breakdown table
- Discount line
- Market comparison bar
- Monthly equivalent calculation

**Timeline**:
- Horizontal (desktop) or vertical (mobile) timeline
- Phase blocks with expand-on-click
- Colour-coded by phase

**Team Section**:
- Grid of team member cards
- Photo, name, role, allocation percentage
- Optional LinkedIn link

**CTA Section**:
- Three buttons: Schedule Call / Download PDF / Email Us
- Calendly or Cal.com embed option
- Dark background, centred layout

### Analytics Integration

Every generated site includes a lightweight analytics snippet:

```javascript
// Tracks: page views, scroll depth, section visibility,
// card expansions, PDF downloads, CTA clicks, time on page
// Reports back to NUPROP dashboard via API
```

---


## 11. Document Generation Engine

### DOCX Generation

Uses the `docx` npm package (same approach as the Tata Communications proposal).

**Document Structure**:
1. Cover page (agency logo, client name, project title, date)
2. Table of contents
3. Covering letter
4. Executive summary
5. Scope of engagement (per-workstream sections with tables)
6. Cost summary (table with subtotals, discounts, total)
7. Team structure (table)
8. Timeline (table)
9. Terms & conditions
10. Contact information

**Styling**: Follows docx skill best practices (Arial font, proper heading styles, DXA table widths, ShadingType.CLEAR, no unicode bullets).

### PDF Generation

Two paths:
1. **From DOCX**: LibreOffice headless conversion (reliable, matches DOCX exactly)
2. **From HTML**: Puppeteer screenshot of the interactive site with print stylesheet (more beautiful, but less reliable for text-heavy content)

Default: Path 1 for formal proposal, Path 2 for cost rationale.

### Email Draft Generation

**Three variants**:

1. **Formal**: "Dear [Name], please find attached our proposal for [Project]..."
2. **Confident**: "[Name], we've built something for you. Open this link..."
3. **Warm**: "Hi [Name], following our conversation, I've put together..."

Each includes: proposal URL, PDF attachment reference, specific next step, Karthik's signature.

---


## 12. Analytics, Instrumentation & Client Intelligence

This is not a nice-to-have — it's a core differentiator. When you send a proposal, you need to know: who opened it, when, on what device, which sections they read, how long they spent, whether they forwarded it to a colleague, and whether they came back. This intelligence shapes your follow-up strategy and, over time, teaches you what wins.

### 12.1 Instrumentation Architecture

Every proposal output — HTML site, PDF, email — is instrumented. The tracking system has three layers:

```
┌────────────────────────────────────────────────────┐
│              CLIENT TOUCHES PROPOSAL                │
│                                                    │
│  HTML Site ──→ JS tracker (embedded, <2KB)          │
│  PDF File  ──→ Tracking pixel + link wrapping       │
│  Email     ──→ Open pixel + link click tracking     │
│                                                    │
├────────────────────────────────────────────────────┤
│              COLLECTION LAYER                       │
│                                                    │
│  Events ──→ FastAPI /api/track endpoint             │
│          ──→ PostgreSQL (analytics_events table)    │
│          ──→ Redis (real-time session aggregation)  │
│                                                    │
├────────────────────────────────────────────────────┤
│              INTELLIGENCE LAYER                     │
│                                                    │
│  Fingerprint ──→ Visitor identification             │
│  Scoring     ──→ Engagement score (0-100)           │
│  Alerts      ──→ Notification service               │
│  Learning    ──→ Win/loss correlation engine         │
│                                                    │
├────────────────────────────────────────────────────┤
│              PRESENTATION LAYER                     │
│                                                    │
│  Dashboard   ──→ Per-proposal timeline              │
│  Portfolio   ──→ All proposals, sortable            │
│  Digest      ──→ Daily email summary                │
│  Mobile push ──→ Real-time alerts                   │
│                                                    │
└────────────────────────────────────────────────────┘
```

### 12.2 HTML Site Tracking (Primary Channel)

Every generated proposal site includes a lightweight tracking script (`nuprop-track.js`, <2KB gzipped) that fires events to NUPROP's collection endpoint.

**Events tracked:**

| Event | When Fired | Data Captured |
|---|---|---|
| `page_view` | Page loads | Timestamp, referrer, UTM params, fingerprint |
| `scroll_depth` | Every 25% scroll threshold (25, 50, 75, 100) | Depth percentage, time to reach |
| `section_enter` | Section scrolls into viewport | Section ID, timestamp |
| `section_exit` | Section scrolls out of viewport | Section ID, time spent (seconds) |
| `card_expand` | Deliverable card clicked/expanded | Card ID (maps to deliverable), timestamp |
| `card_collapse` | Card closed | Card ID, time spent expanded |
| `cost_section_hover` | Mouse hovers over a price for >2 seconds | Line item ID, duration |
| `cta_click` | Any CTA button clicked | CTA type (schedule, download, email) |
| `pdf_download` | PDF download button clicked | Timestamp, fingerprint |
| `demo_interact` | User interacts with embedded demo (types in chatbot, clicks timeline) | Interaction type, content (for chatbot: the question asked) |
| `link_click` | Any outbound link clicked | URL, anchor text |
| `tab_visibility` | Page becomes hidden/visible (tab switching) | State, timestamp |
| `session_end` | Page unloads or 30min inactivity timeout | Total time on page, max scroll depth |

**Tracking script implementation:**

```javascript
// nuprop-track.js — embedded in every generated proposal site
// < 2KB gzipped, no external dependencies, no cookies
(function() {
  const P = '{proposal_id}';
  const E = '{endpoint}'; // https://api.nuprop.app/track
  const F = fingerprint(); // see 12.4

  // Queue events and flush every 5 seconds or on unload
  let q = [];
  const push = (type, data) => q.push({
    t: type,
    p: P,
    f: F,
    ts: Date.now(),
    ...data
  });

  const flush = () => {
    if (!q.length) return;
    navigator.sendBeacon(E, JSON.stringify(q));
    q = [];
  };

  // Flush on interval + page unload
  setInterval(flush, 5000);
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) flush();
  });
  window.addEventListener('pagehide', flush);

  // Page view
  push('page_view', {
    ref: document.referrer,
    ua: navigator.userAgent,
    w: window.innerWidth,
    h: window.innerHeight,
    tz: Intl.DateTimeFormat().resolvedOptions().timeZone
  });

  // Scroll depth tracking
  let maxScroll = 0;
  const thresholds = [25, 50, 75, 100];
  const fired = new Set();
  window.addEventListener('scroll', () => {
    const pct = Math.round(
      (window.scrollY + window.innerHeight) /
      document.body.scrollHeight * 100
    );
    if (pct > maxScroll) maxScroll = pct;
    thresholds.forEach(t => {
      if (pct >= t && !fired.has(t)) {
        fired.add(t);
        push('scroll_depth', { depth: t });
      }
    });
  }, { passive: true });

  // Section visibility tracking (IntersectionObserver)
  const sectionTimers = {};
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(e => {
      const id = e.target.dataset.section;
      if (e.isIntersecting) {
        sectionTimers[id] = Date.now();
        push('section_enter', { section: id });
      } else if (sectionTimers[id]) {
        push('section_exit', {
          section: id,
          duration: Math.round((Date.now() - sectionTimers[id]) / 1000)
        });
        delete sectionTimers[id];
      }
    });
  }, { threshold: 0.3 });

  document.querySelectorAll('[data-section]').forEach(
    el => observer.observe(el)
  );

  // Card expand/collapse tracking
  document.querySelectorAll('[data-card]').forEach(el => {
    el.addEventListener('click', () => {
      const id = el.dataset.card;
      const expanded = el.classList.contains('expanded');
      push(expanded ? 'card_collapse' : 'card_expand', { card: id });
    });
  });

  // CTA click tracking
  document.querySelectorAll('[data-cta]').forEach(el => {
    el.addEventListener('click', () => {
      push('cta_click', { cta: el.dataset.cta });
    });
  });

  // Expose for demo tracking
  window.__nuprop = { push, flush };
})();
```

**Every generated site section gets a `data-section` attribute:**
```html
<section data-section="cover">...</section>
<section data-section="letter">...</section>
<section data-section="scope">...</section>
<section data-section="investment">...</section>
<section data-section="timeline">...</section>
<section data-section="team">...</section>
<section data-section="cta">...</section>
```

**Every deliverable card gets a `data-card` attribute:**
```html
<div data-card="bi_visual_identity_system" class="card">...</div>
<div data-card="fm_corporate_film_premium" class="card">...</div>
```

This maps tracked events directly back to rate card package IDs, so the win/loss learning engine knows which specific services clients engage with most.

### 12.3 PDF Tracking

PDFs are static files — they can't run JavaScript. Two mechanisms solve this:

#### 12.3.1 Tracked PDF Links (Primary)

Instead of attaching a raw PDF, NUPROP generates a **tracked download link**:

```
https://api.nuprop.app/dl/{proposal_id}/{token}
```

When the client clicks this link:
1. The server logs: timestamp, IP, user-agent, referrer, fingerprint (from query params or headers)
2. The server returns the PDF with `Content-Disposition: inline` (opens in browser) or `attachment` (downloads), based on the client's browser
3. If opened in browser, a lightweight HTML wrapper loads first with tracking, then embeds the PDF

**The HTML wrapper approach:**
```html
<!-- Served at the tracked link URL -->
<!-- Loads tracking, then displays the PDF -->
<html>
<body style="margin:0;padding:0;height:100vh">
  <script>
    // Fire tracking event
    fetch('https://api.nuprop.app/track', {
      method: 'POST',
      body: JSON.stringify({
        t: 'pdf_open',
        p: '{proposal_id}',
        f: fingerprint(),
        ts: Date.now()
      })
    });
  </script>
  <iframe src="/pdf/{proposal_id}/raw.pdf"
    style="width:100%;height:100vh;border:none"></iframe>
</body>
</html>
```

This means: when someone opens the "PDF link" in a browser, they see the PDF, but NUPROP also records the open event. If they right-click and "Save As," they get the raw PDF — no tracking possible after that, but the initial open is captured.

#### 12.3.2 Tracking Pixel in PDF (Secondary)

For PDFs that will be emailed as attachments (not via tracked link), embed a 1×1 tracking pixel as an image in the PDF footer:

```
https://api.nuprop.app/px/{proposal_id}.png
```

When the PDF is opened in a viewer that loads remote images (most desktop PDF readers, Apple Preview, many email clients), the pixel fires and logs:
- Timestamp
- IP address → approximate location
- User-agent (PDF reader type)

**Limitations**: This doesn't work if the reader blocks remote images (some corporate environments, Adobe Reader's default settings). It provides partial coverage, not complete.

**Combined strategy**: Always use tracked links as primary. Embed the pixel as a fallback. The proposal email says "View your proposal: [tracked link]" with the PDF also attached. Most clients click the link (which is fully tracked) rather than opening the attachment.

### 12.4 Client Fingerprinting

**Goal**: Identify unique visitors across sessions without requiring login or cookies.

**Why not cookies?** Cookies can be blocked, cleared, or rejected. For a proposal that might be viewed across multiple devices and shared with colleagues, cookies provide incomplete data. Fingerprinting provides a more reliable visitor identifier.

**Fingerprint components** (combined into a hash):

| Signal | Source | Reliability |
|---|---|---|
| Screen resolution | `screen.width × screen.height` | High |
| Colour depth | `screen.colorDepth` | Medium |
| Timezone | `Intl.DateTimeFormat().resolvedOptions().timeZone` | High |
| Language | `navigator.language` | High |
| Platform | `navigator.platform` | Medium |
| Hardware concurrency | `navigator.hardwareConcurrency` | Medium |
| Device memory | `navigator.deviceMemory` | Medium (Chrome only) |
| Canvas fingerprint | Render a hidden canvas element, hash the pixel data | High |
| WebGL renderer | `WEBGL_debug_renderer_info` extension | High |
| Installed fonts (subset) | CSS font detection for 10 common fonts | Medium |
| Touch support | `navigator.maxTouchPoints` | High |
| User agent (structured) | Parsed browser + OS, not raw UA string | Medium |

**Fingerprint generation:**

```javascript
function fingerprint() {
  const signals = [
    screen.width, screen.height, screen.colorDepth,
    Intl.DateTimeFormat().resolvedOptions().timeZone,
    navigator.language,
    navigator.platform,
    navigator.hardwareConcurrency || 0,
    navigator.deviceMemory || 0,
    navigator.maxTouchPoints || 0,
    canvasHash(),
    webglRenderer()
  ];
  // FNV-1a hash of concatenated signals → 8-char hex string
  return fnv1a(signals.join('|')).toString(16).slice(0, 12);
}
```

**What the fingerprint enables:**

1. **Multi-session linking**: Same person returns 3 days later → recognised as the same visitor, engagement score accumulates
2. **Device detection**: "They viewed it on mobile first, then desktop" → shared with colleagues or reviewing at home
3. **Forwarding detection**: A different fingerprint views the same proposal → "They forwarded it to someone else"
4. **Multiple stakeholder mapping**: 3 different fingerprints view the proposal in 24 hours → "At least 3 people are reviewing"

**Privacy handling:**
- The fingerprint is a one-way hash — it cannot be reversed to identify a person
- No PII is collected (no names, no email addresses, no IP storage beyond the session)
- IP addresses are used for geolocation (city-level) then discarded — only the city is stored
- The tracking script respects `Do Not Track` (DNT) headers: if DNT is enabled, only `page_view` events fire (no section/card tracking)
- Fingerprints are proposal-scoped: the same person viewing two different proposals generates two unlinked fingerprint records
- GDPR note: for EU clients, add a minimal consent banner to the proposal site (Phase D)

### 12.5 Visitor Intelligence Profile

Each unique fingerprint builds a **Visitor Profile** for that proposal:

```json
{
  "visitor_id": "a3f8c2e1b9d4",
  "proposal_id": "tata-comms-25th",
  "first_seen": "2026-04-07T10:23:00Z",
  "last_seen": "2026-04-09T14:15:00Z",
  "sessions": 3,
  "total_time_seconds": 847,
  "device_types": ["desktop", "mobile"],
  "locations": ["Mumbai, India"],
  "browser": "Chrome 124 / macOS",

  "sections_viewed": {
    "cover": { "time_seconds": 8, "visits": 3 },
    "letter": { "time_seconds": 145, "visits": 3 },
    "scope": { "time_seconds": 210, "visits": 2 },
    "investment": { "time_seconds": 312, "visits": 3 },
    "timeline": { "time_seconds": 45, "visits": 1 },
    "team": { "time_seconds": 22, "visits": 1 },
    "cta": { "time_seconds": 15, "visits": 2 }
  },

  "cards_expanded": [
    "fm_corporate_film_premium",
    "dg_ai_microsite",
    "ee_anniversary_campaign"
  ],

  "actions": [
    { "type": "pdf_download", "ts": "2026-04-07T10:30:00Z" },
    { "type": "cta_click", "cta": "schedule_call", "ts": "2026-04-09T14:15:00Z" }
  ],

  "engagement_score": 78,
  "classification": "very_high"
}
```

**When multiple visitors exist for one proposal**, the dashboard shows:

```
Proposal: Tata Communications — 25th Anniversary
Status: Viewed by 3 people

Visitor 1 (desktop, Mumbai) — Score: 78 / Very High
  3 sessions, 14 min total, downloaded PDF, clicked Schedule Call

Visitor 2 (desktop, Mumbai) — Score: 42 / Moderate
  1 session, 4 min, viewed letter + investment only

Visitor 3 (mobile, Delhi) — Score: 25 / Low
  1 session, 1 min, viewed cover + letter only (likely quick forward view)
```

### 12.6 Engagement Scoring (Updated)

Each proposal receives an aggregate engagement score (0-100) and each visitor gets their own score.

**Per-visitor scoring:**

| Signal | Weight | Scoring |
|---|---|---|
| Opened within 24 hours of send | 10 | Yes = 10, No = 0 |
| Total time on site | 20 | <1 min = 0, 1-3 min = 8, 3-5 min = 14, >5 min = 20 |
| Sections viewed (% of total) | 15 | <50% = 3, 50-75% = 8, >75% = 15 |
| Cost cards expanded | 15 | None = 0, 1-2 = 5, 3-5 = 10, All = 15 |
| Investment section time | 10 | <30s = 0, 30s-2min = 5, >2min = 10 |
| PDF downloaded | 5 | Yes = 5, No = 0 |
| Return visits | 15 | 0 = 0, 1 = 8, 2+ = 15 |
| CTA clicked | 10 | Yes = 10, No = 0 |

**Per-proposal scoring** (aggregate):
- Take the highest individual visitor score as the proposal score
- Add bonus: +5 if 2+ unique visitors, +10 if 3+ unique visitors (signals internal sharing)
- Cap at 100

**Score interpretation:**
- 0-20: **Cold** — likely not interested, or hasn't seen it yet
- 21-40: **Cool** — glanced but not engaged, might need a nudge
- 41-60: **Warm** — actively reviewing, probably comparing with other proposals
- 61-80: **Hot** — strong interest, preparing to make a decision
- 81-100: **Ready** — multiple stakeholders engaged, CTA clicked, follow up now

### 12.7 Feedback Collection

**Goal**: Let clients leave structured feedback on the proposal without requiring a login or a separate form.

#### 12.7.1 Inline Feedback Widget (HTML Site)

A non-intrusive feedback bar appears at the bottom of the proposal site after the client has scrolled past 75% or spent >3 minutes:

```
┌──────────────────────────────────────────────────────┐
│  How does this proposal feel?                        │
│                                                      │
│  😐  Needs work    🙂  Good start    🤩  Impressive │
│                                                      │
│  [Optional: Leave a note]          [Send Feedback]   │
└──────────────────────────────────────────────────────┘
```

**After submission:**
- The rating (1-3) and optional note are stored against the proposal + visitor fingerprint
- The widget collapses to "Thanks for your feedback" and doesn't appear again (localStorage flag)
- The agency gets a real-time notification: "Your client rated the proposal as 'Impressive' and left a note: 'Love the three themes. Can we discuss the video budget?'"

**The note field is gold** — clients will tell you exactly what they're thinking about pricing, scope, or approach. This is the signal that no competitor's proposal tool captures.

#### 12.7.2 Post-View Feedback Email (Automated)

If the client views the proposal but doesn't take any CTA action within 48 hours, NUPROP can (optionally) send a one-question feedback email:

```
Subject: Quick question about the proposal

Hi [name],

I noticed you reviewed our proposal for [project]. One quick question
to help us improve — no need for a long reply:

What would make this proposal stronger?

[ ] The pricing needs adjustment
[ ] I need more detail on specific deliverables
[ ] I'd like to see relevant case studies
[ ] I want to discuss the timeline
[ ] We're going in a different direction
[ ] Other: ___________

[Reply to this email or click any option above]
```

Each option is a tracked link that records the selection without requiring the client to type anything. One-click feedback.

#### 12.7.3 Feedback Data Model

```
Feedback
├── id
├── proposal_id
├── visitor_fingerprint
├── type (inline_widget / email_survey / manual_note)
├── rating (1-3 for widget, null for email)
├── selected_option (for email survey)
├── note (free text, optional)
├── timestamp
└── source (site / email)
```

### 12.8 Win/Loss Learning Engine

Over time, NUPROP correlates proposal attributes with outcomes:

**Data points correlated:**
- Proposal value vs. win rate (by industry, client size)
- Template used vs. win rate
- Letter strategy (confident/warm/technical) vs. engagement score
- Sections with highest time-spent in won proposals vs. lost proposals
- Cards most frequently expanded in won proposals
- Time from send to first view (won vs. lost)
- Number of unique visitors (won vs. lost)
- Feedback ratings (won vs. lost)
- Pricing framing used vs. win rate

**Output**: After 30+ proposals with outcome data, NUPROP can surface insights:
- "Your anniversary campaign proposals win 65% of the time when using the warm letter style (vs. 40% with confident)"
- "Proposals where 3+ stakeholders view the site win at 2× the rate of single-viewer proposals"
- "Clients who expand the cost cards spend 3× longer on the proposal and win at 55%"

---

---

## 12A. Hosting Architecture

### Phase A: Proposal Site Hosting

For the Claude Code skill phase, proposal sites are static HTML files. Three hosting options:

**Option 1: Fly.io (Recommended for Phase A)**
```bash
# Deploy from the proposals directory
cd ~/nuprop/proposals/tata-communications-2026-04-06/site/
fly launch --now
# Returns: https://tata-communications-2026-04-06.fly.dev
```
- Free tier: 3 shared VMs, 160GB outbound
- Custom domain: `proposals.veeville.com` (wildcard subdomain)
- SSL automatic via Let's Encrypt
- Edge deployment (anycast, fast globally)
- Simple static site hosting via Dockerfile or `fly launch`

**Option 2: Cloudflare Pages**
- Free tier: unlimited bandwidth
- Fastest CDN globally
- Custom domain support
- Good for cost-sensitive scaling

**Option 3: Netlify**
- Free tier generous
- Deploy via CLI: `npx netlify deploy --prod`
- Custom domain support with wildcard

### Phase C: Platform Hosting Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    HOSTING TOPOLOGY                      │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  NUPROP PLATFORM (app.nuprop.app)                     │
│  ┌─────────────────────────────────────────────┐       │
│  │ Frontend: Next.js on Fly.io                   │       │
│  │ Backend: FastAPI on Fly.io                    │       │
│  │ Database: Supabase PostgreSQL                │       │
│  │ Cache: Upstash Redis                         │       │
│  │ Files: Cloudflare R2                         │       │
│  │ Queues: Inngest / BullMQ                     │       │
│  └─────────────────────────────────────────────┘       │
│                                                         │
│  GENERATED PROPOSAL SITES                               │
│  ┌─────────────────────────────────────────────┐       │
│  │ Static sites on Fly.io (per-site deployment)  │       │
│  │ Each site: *.proposals.nuprop.app           │       │
│  │ OR custom: proposals.clientagency.com        │       │
│  │ Tracking script points to platform backend   │       │
│  └─────────────────────────────────────────────┘       │
│                                                         │
│  TRACKING & ANALYTICS ENDPOINT                          │
│  ┌─────────────────────────────────────────────┐       │
│  │ api.nuprop.app/track (FastAPI)              │       │
│  │ Receives beacon events from all proposal     │       │
│  │ sites, stores in PostgreSQL, triggers        │       │
│  │ notifications via Redis pub/sub              │       │
│  └─────────────────────────────────────────────┘       │
│                                                         │
│  PDF SERVING & TRACKING                                 │
│  ┌─────────────────────────────────────────────┐       │
│  │ api.nuprop.app/dl/{id}/{token}              │       │
│  │ Serves tracked PDFs from R2 storage          │       │
│  │ Logs open events before serving file         │       │
│  └─────────────────────────────────────────────┘       │
│                                                         │
│  NOTIFICATION SERVICE                                   │
│  ┌─────────────────────────────────────────────┐       │
│  │ Redis pub/sub → Notification dispatcher      │       │
│  │ Channels: Email, Slack, WhatsApp, Push       │       │
│  │ Rules engine for alert conditions            │       │
│  └─────────────────────────────────────────────┘       │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Custom Domain Strategy

**Agency-owned domains (Phase C):**
Each agency can configure a custom domain for their proposal sites:
- Agency sets up: `proposals.theiragency.com`
- NUPROP configures: wildcard CNAME → Fly.io
- Each proposal deploys to: `proposals.theiragency.com/client-name`
- The tracking script on these sites still points to `api.nuprop.app/track`

**Default NUPROP domains (free tier):**
- `client-name.proposals.nuprop.app`
- SSL automatic via Fly.io (Let's Encrypt)

### Cost Estimates (Phase C at Scale)

| Service | Free Tier | Growth (100 proposals/month) | Scale (1,000 proposals/month) |
|---|---|---|---|
| Fly.io (platform + backend + sites) | Free (3 shared VMs) | $30/month (dedicated) | $100/month (scaled) |
| Supabase (PostgreSQL) | Free (500MB) | $25/month (8GB) | $75/month (32GB) |
| Upstash Redis | Free (10K commands/day) | $10/month | $30/month |
| Cloudflare R2 (file storage) | Free (10GB) | $5/month (50GB) | $15/month (200GB) |
| Email service (Resend/Postmark) | Free (100/day) | $20/month | $50/month |
| **Total infrastructure** | **$0** | **~$90/month** | **~$290/month** |

At the Growth tier (₹15,000/month × 50 customers = ₹7.5L MRR), infrastructure at $120/month (~₹10K) is 1.3% of revenue. Excellent unit economics.

---

---

## 12B. Notification Service

### Architecture

```
Event arrives at /api/track
         │
         ▼
   Redis pub/sub channel: proposal:{proposal_id}
         │
         ▼
   Notification Dispatcher (background worker)
         │
         ├──→ Rule Engine (should we notify?)
         │         │
         │         ├── Is this a first view? → NOTIFY IMMEDIATELY
         │         ├── Is this a return visit? → NOTIFY IMMEDIATELY
         │         ├── Has the client spent >3 min? → NOTIFY
         │         ├── Has the client expanded cost cards? → NOTIFY
         │         ├── Has the client downloaded PDF? → NOTIFY
         │         ├── Has the client clicked CTA? → NOTIFY IMMEDIATELY
         │         ├── Has the client left feedback? → NOTIFY IMMEDIATELY
         │         ├── New unique visitor detected? → NOTIFY
         │         └── Batch: daily digest of all activity → DIGEST
         │
         ▼
   Channel Router
         │
         ├──→ Email (Resend / Postmark API)
         ├──→ Slack (webhook to agency's workspace)
         ├──→ WhatsApp (Twilio / Exotel API)
         └──→ Browser push (Web Push API)
```

### Notification Types

#### Real-Time Alerts (fire within 30 seconds of event)

| Trigger | Message | Channels |
|---|---|---|
| First view | "🔵 [Client] just opened your proposal for [Project]" | All active channels |
| Return visit | "🔵 [Client] is viewing your proposal again (visit #N)" | Email, Slack |
| PDF download | "📄 [Client] downloaded the PDF for [Project]" | All active channels |
| CTA click | "🟢 [Client] clicked [Schedule Call / Email Us] — follow up NOW" | All active channels (urgent) |
| New unique visitor | "👥 A new person is viewing your [Project] proposal (visitor #N)" | Email, Slack |
| Feedback received | "💬 [Client] rated your proposal: [rating] — Note: '[note text]'" | All active channels |
| High engagement | "🔥 [Client] has spent [X] minutes on your proposal — engagement score: [N]" | Email, Slack |

#### Daily Digest (sent at 9:00 AM agency timezone)

```
NUPROP Daily Digest — April 8, 2026

ACTIVE PROPOSALS
─────────────────────────────────────────────
📊 Tata Communications — 25th Anniversary
   Score: 78/100 (Very High) ↑ from 45 yesterday
   3 viewers, 14 min total, PDF downloaded
   Last activity: 2 hours ago
   ➡ SUGGESTED: Follow up with specific pricing discussion

📊 Smartworks — Website Redesign
   Score: 35/100 (Cool)
   1 viewer, 2 min total
   Last activity: 3 days ago
   ➡ SUGGESTED: Send a nudge email or the one-pager

📊 Titan Company — Digital Refresh
   Score: 0/100 (Cold)
   No views yet (sent 5 days ago)
   ➡ SUGGESTED: Resend with different subject line

WEEKLY STATS
─────────────────────────────────────────────
Proposals sent: 3
Proposals viewed: 2 (67%)
Average engagement score: 38
Proposals won: 0
Proposals lost: 0
Pending: 3
```

### Notification Configuration (Per Agency)

```json
{
  "channels": {
    "email": {
      "enabled": true,
      "address": "karthik@veeville.com",
      "real_time": true,
      "digest": true,
      "digest_time": "09:00",
      "digest_timezone": "Asia/Kolkata"
    },
    "slack": {
      "enabled": true,
      "webhook_url": "https://hooks.slack.com/...",
      "channel": "#proposals",
      "real_time": true,
      "digest": false
    },
    "whatsapp": {
      "enabled": false,
      "phone": "+91...",
      "real_time_only_urgent": true
    },
    "push": {
      "enabled": true,
      "real_time": true
    }
  },
  "rules": {
    "notify_on_first_view": true,
    "notify_on_return_visit": true,
    "notify_on_pdf_download": true,
    "notify_on_cta_click": true,
    "notify_on_feedback": true,
    "notify_on_new_visitor": true,
    "notify_on_high_engagement": true,
    "high_engagement_threshold": 60,
    "quiet_hours": { "start": "22:00", "end": "07:00" },
    "batch_during_quiet_hours": true
  }
}
```

### Backend Implementation (FastAPI)

```python
# Notification service — MVVM architecture

# models/notification.py
class NotificationEvent(BaseModel):
    proposal_id: str
    event_type: str  # first_view, return_visit, pdf_download, etc.
    visitor_fingerprint: str
    metadata: dict
    timestamp: datetime

class NotificationConfig(BaseModel):
    channels: dict
    rules: dict

# viewmodels/notification_vm.py
class NotificationViewModel:
    async def process_tracking_event(self, event: TrackingEvent):
        """Called when a tracking event arrives. Evaluates rules
        and dispatches notifications."""
        proposal = await self.get_proposal(event.proposal_id)
        config = await self.get_agency_config(proposal.agency_id)

        # Evaluate rules
        alerts = self.evaluate_rules(event, proposal, config)

        # Dispatch via channels
        for alert in alerts:
            await self.dispatch(alert, config.channels)

    def evaluate_rules(self, event, proposal, config):
        alerts = []
        rules = config.rules

        if event.type == 'page_view':
            visitor = self.get_or_create_visitor(event)
            if visitor.session_count == 1 and rules.notify_on_first_view:
                alerts.append(Alert(
                    type='first_view',
                    message=f'{proposal.client_name} just opened your proposal',
                    urgency='normal'
                ))
            elif visitor.session_count > 1 and rules.notify_on_return_visit:
                alerts.append(Alert(
                    type='return_visit',
                    message=f'{proposal.client_name} is viewing your proposal again',
                    urgency='normal'
                ))

        if event.type == 'cta_click' and rules.notify_on_cta_click:
            alerts.append(Alert(
                type='cta_click',
                message=f'{proposal.client_name} clicked {event.cta_type} — follow up NOW',
                urgency='urgent'
            ))

        # ... other rules

        return alerts
```

---

---


## 13. Data Model

### Core Entities

```
Agency
├── id, name, logo, colours, fonts
├── rate_card (JSON)
├── voice_profile (calibrated from past writing)
├── default_terms (text)
└── team_members[]

Client
├── id, name, industry, size, contacts[]
├── notes, tags[]
└── proposals[]

Proposal
├── id, client_id, project_name
├── status (draft / sent / viewed / won / lost / expired)
├── brief (structured JSON)
├── research (markdown)
├── cost_model (JSON)
├── covering_letter (markdown)
├── executive_summary (markdown)
├── scope_sections[] (markdown per deliverable)
├── cost_rationale (markdown)
├── terms (markdown)
├── site_url
├── docx_path
├── pdf_path
├── created_at, sent_at, expires_at
├── engagement_score
└── analytics[]

Analytics Event
├── proposal_id
├── event_type (view / scroll / expand / download / click)
├── section_id
├── timestamp
├── duration_seconds
├── visitor_hash (anonymised)
└── device / location (approximate)
```

### Additional Data Model Entities

Add these to the existing data model:

```
Visitor (NEW)
├── id (auto-generated)
├── proposal_id (FK → Proposal)
├── fingerprint (12-char hex hash)
├── first_seen (timestamp)
├── last_seen (timestamp)
├── session_count (integer)
├── total_time_seconds (integer)
├── max_scroll_depth (integer, 0-100)
├── device_types (array: desktop, mobile, tablet)
├── browsers (array)
├── locations (array of city strings)
├── engagement_score (integer, 0-100)
└── classification (cold / cool / warm / hot / ready)

SectionView (NEW)
├── id
├── visitor_id (FK → Visitor)
├── proposal_id (FK → Proposal)
├── section_id (string: cover, letter, scope, investment, etc.)
├── enter_timestamp
├── exit_timestamp
├── duration_seconds
└── visit_number (1st, 2nd, 3rd time viewing this section)

CardInteraction (NEW)
├── id
├── visitor_id (FK → Visitor)
├── proposal_id (FK → Proposal)
├── card_id (string: maps to rate card package ID)
├── action (expand / collapse)
├── timestamp
└── time_expanded_seconds

Feedback (NEW)
├── id
├── proposal_id (FK → Proposal)
├── visitor_fingerprint
├── type (inline_widget / email_survey / manual_note)
├── rating (1-3 for widget, null for email)
├── selected_option (for email survey)
├── note (free text, optional)
├── timestamp
└── source (site / email)

Notification (NEW)
├── id
├── proposal_id (FK → Proposal)
├── alert_type (first_view / return_visit / pdf_download / cta_click / feedback / new_visitor / high_engagement)
├── message (text)
├── urgency (normal / urgent)
├── channels_sent (array: email, slack, whatsapp, push)
├── sent_at (timestamp)
├── read_at (timestamp, nullable)
└── agency_id (FK → Agency)

Analytics Event (UPDATED — extends existing)
├── id
├── proposal_id (FK → Proposal)
├── visitor_id (FK → Visitor, nullable for PDF pixel events)
├── event_type (page_view / scroll_depth / section_enter / section_exit /
│               card_expand / card_collapse / cost_section_hover /
│               cta_click / pdf_download / pdf_open / demo_interact /
│               link_click / tab_visibility / session_end /
│               feedback_submit)
├── section_id (nullable)
├── card_id (nullable)
├── data (JSONB — flexible payload per event type)
├── timestamp
├── session_id (groups events within one visit)
└── ip_city (city-level geolocation, IP not stored)

EmailIndex (NEW — Email Intelligence Layer)
├── id (UUID)
├── agency_id (FK → Agency)
├── gmail_message_id (unique per agency)
├── gmail_thread_id
├── client_domain (auto-detected from from/to)
├── client_name (resolved via domain or entity matching, nullable if unmatched)
├── message_type (brief / feedback / negotiation / scheduling / follow_up / internal_discussion / general)
├── sentiment (positive / neutral / negative)
├── priority (high / medium / low)
├── summary (2-sentence Haiku extraction — NO raw email body stored)
├── entities (JSONB: people[], money[], projects[], dates[])
├── from_address
├── to_addresses (array)
├── subject
├── date (timestamptz)
├── has_attachments (boolean)
├── embedding (vector(1024) — Voyage-3-large, pgvector column)
└── synced_at (timestamptz)

Indexes: agency_id+client_domain, agency_id+date DESC,
         IVFFlat on embedding (vector_cosine_ops, lists=100)
View: unmatched_emails (client_name IS NULL, for manual review)
```

---

---


## 14. Tech Stack

### Phase A (Claude Code Skill)
- **Runtime**: Claude Code (no separate infrastructure)
- **AI**: Claude API (via Claude Code's built-in access)
- **Research**: Web search (via Claude's search tool)
- **Document gen**: Node.js + docx package
- **Site gen**: Static HTML templates populated by Claude Code
- **Hosting**: Fly.io (manual deploy or via CLI)
- **Storage**: Local filesystem + git

### Phase C (Platform)

**Backend**:
- **Framework**: FastAPI (MVVM architecture per Veeville standard)
- **Database**: PostgreSQL via Supabase (managed Postgres with pgvector, connection pooling, auth, realtime subscriptions — NOT used as a platform, just as managed Postgres via standard SQLAlchemy/asyncpg connection string. Zero lock-in: change one connection string to migrate to RDS or self-hosted.)
- **Vector search**: pgvector extension on Supabase Postgres (1024-dim embeddings, IVFFlat index, hybrid metadata+vector queries)
- **Cache**: Redis via Upstash (for rate limiting, session management, pub/sub for notifications)
- **AI — Classification**: Claude Haiku 4.5 (email classification, entity extraction — ₹0.01/email)
- **AI — Embedding**: Voyage-3-large (1024-dim, for email and document vector search)
- **AI — Generation**: Claude Sonnet 4.6 (research, cost model, narrative — default) / Claude Opus 4.6 (high-value pitches >₹50L)
- **Search**: Anthropic web search tool or Serper API
- **File storage**: Cloudflare R2 (S3-compatible, for generated PDFs and DOCX files)
- **Background jobs**: Inngest or BullMQ (email sync worker, classification pipeline, site deployment)
- **Email service**: Resend (transactional emails, notifications, digest)

**Frontend**:
- **Framework**: React (Next.js for SSR/SSG)
- **State**: Zustand (lightweight, no Redux overhead)
- **Chat interface**: Custom conversational UI component
- **Real-time**: WebSocket for streaming AI responses
- **Styling**: Tailwind CSS

**Generated Sites**:
- **Framework**: Astro (static site generation, zero JS by default, hydrate on demand)
- **Hosting**: Fly.io (per-site deployment via CLI)
- **Analytics**: Custom lightweight script (< 2KB)
- **Domain**: Wildcard subdomain on `nuprop.app` or custom domain

**Infrastructure**:
- **Database**: Supabase (Free → $25/month → $75/month as you scale. Includes Postgres, pgvector, connection pooling, auth, realtime, backups — all managed. Access via standard Postgres connection string through SQLAlchemy/asyncpg, not Supabase client libraries.)
- **Backend hosting**: Fly.io (FastAPI + background workers)
- **Frontend hosting**: Fly.io (Next.js app + generated proposal sites)
- **CI/CD**: GitHub Actions
- **Monitoring**: Sentry (errors), Plausible (analytics)


### Additional Infrastructure Components (Phase C)

Add to the existing tech stack section:

**Notification Service:**
- **Email**: Resend (developer-friendly, $20/month for 50K emails) or Postmark (deliverability-focused)
- **Slack**: Incoming webhook (free, no API cost)
- **WhatsApp**: Twilio API or Exotel (₹0.50-1.00 per message) — optional, for urgent alerts only
- **Browser Push**: Web Push API (free, built into browsers) via web-push npm package
- **Dispatcher**: Background worker on same FastAPI server, triggered by Redis pub/sub

**Analytics Pipeline:**
- **Collection**: FastAPI endpoint `/api/track` accepting beacon POST requests
- **Storage**: PostgreSQL `analytics_events` table (partitioned by month for query performance)
- **Real-time**: Redis pub/sub for triggering notifications on event arrival
- **Geolocation**: MaxMind GeoLite2 (free, city-level accuracy) for IP → city resolution, IP discarded after resolution
- **Fingerprinting**: Client-side JS (no server-side component needed), hash computed in browser

**PDF Infrastructure:**
- **Storage**: Cloudflare R2 (generated PDFs stored with proposal ID as key)
- **Serving**: FastAPI endpoint `/api/dl/{proposal_id}/{token}` — logs access then streams PDF from R2
- **Tracking pixel**: 1x1 transparent PNG served from `/api/px/{proposal_id}.png` — logs request headers

---

*End of Addendum v1.2. Merge into PRD_NUPROP.md.*

---


## 15. User Experience Flows

### Flow 1: First Proposal (New User)

```
1. Sign up → Agency profile wizard (name, logo, colours, rate card)
2. "Create new proposal" → Chat opens
3. User describes client and project → AI asks clarifying questions
4. AI researches client and market → Shows findings for review
5. AI proposes cost model → User adjusts
6. AI generates narrative → User reviews and edits
7. AI generates outputs (site + DOCX + email) → User reviews
8. User deploys → Gets shareable URL
9. User sends email → AI drafts introduction
10. Analytics dashboard lights up when client views
```

### Flow 2: Repeat Proposal (Existing Client)

```
1. Select client from CRM → Past proposals and notes pre-loaded
2. "New proposal for [existing client]" → AI already knows context
3. Abbreviated brief intake (AI suggests scope based on history)
4. Cost model pre-populated from past proposal, adjusted for new scope
5. Covering letter references ongoing relationship
6. Faster generation → Deploy
```

### Flow 3: Emergency Pitch (Speed Mode)

```
1. "Quick pitch for [client], [project], [budget]" — one message
2. AI skips clarifying questions, uses defaults
3. Generates a lean proposal (no rationale doc, simplified site)
4. Ready in 15 minutes
5. User can enrich later if opportunity progresses
```

### Flow 4: Post-Proposal Follow-Up

```
1. Dashboard shows: "Titan Company viewed your proposal 3 times"
2. AI suggests follow-up: "They spent 6 min on the investment section
   and expanded the website redesign card. Consider addressing
   pricing in your follow-up."
3. AI drafts follow-up email referencing engagement data
4. User edits and sends
```

---


## 16. Pricing & Business Model

### Phase A: Internal Tool
- Cost: $0 (uses existing Claude Code subscription)
- ROI: measured in proposal win rate improvement and time saved

### Phase C: Micro-SaaS

**Pricing tiers**:

| Tier | Price | Proposals/mo | Features |
|---|---|---|---|
| **Starter** | ₹5,000/mo (~$60) | 3 proposals | Chat builder, DOCX/PDF output, basic analytics |
| **Growth** | ₹15,000/mo (~$180) | 15 proposals | + Interactive site, market research, engagement scoring |
| **Studio** | ₹30,000/mo (~$360) | Unlimited | + Custom domain, portfolio library, win/loss learning, team seats (3) |
| **Agency** | ₹50,000/mo (~$600) | Unlimited | + 10 team seats, white-label sites, API access, priority support |

**Usage-based add-on**: ₹500 per additional proposal beyond tier limit

**Revenue targets (Year 1)**:
- 50 paying agencies by month 6 (mix of Starter and Growth)
- Average revenue per agency: ₹12,000/mo
- Monthly recurring revenue target: ₹6,00,000 by month 12
- Annual run rate: ₹72,00,000 (~$86,000 USD)

---


## 17. Unit Economics

### Cost Per Proposal (API)

Based on the Tata Communications reference implementation — the most exhaustive proposal type: year-long engagement, 3 themes, 35+ deliverables, full client research, market benchmarking across 6 categories, 2 covering letter variants, 35 scope descriptions, 10-category cost rationale, DOCX + HTML + interactive site generation, 2 revision rounds.

**Token usage breakdown**:

| Pipeline Step | Input Tokens | Output Tokens | Sonnet Cost |
|---|---|---|---|
| Brief intake (PDF + Excel parse, structuring) | ~19,000 | ~5,500 | $0.14 |
| Client research (7 web searches + synthesis) | ~35,000 | ~11,500 | $0.28 |
| Market benchmarking (12 searches + synthesis) | ~68,000 | ~17,000 | $0.46 |
| Cost model (rate card mapping + presentation) | ~14,000 | ~7,000 | $0.15 |
| Narrative generation (letter, summary, scope, rationale, terms) | ~61,000 | ~30,000 | $0.63 |
| Output generation (DOCX code, HTML, site scaffold, email) | ~51,000 | ~42,000 | $0.78 |
| Review and iteration (2 rounds) | ~20,000 | ~8,000 | $0.18 |
| **Total** | **~268,000** | **~121,000** | **$2.62** |

**Cost in INR**: ₹220 at current exchange rates.

**With optimisations**:

| Optimisation | Cost | Savings |
|---|---|---|
| Standard (no optimisation) | $2.62 / ₹220 | — |
| Prompt caching (rate card + system prompt cached) | $1.40 / ₹117 | 47% |
| Batch API (non-real-time steps batched) | $1.31 / ₹110 | 50% |
| Caching + batch combined | $0.85 / ₹71 | 68% |

**Web search costs**: ~15 searches per proposal. If using Claude's built-in search tool, included in token costs above. If using Serper API separately: $0.015 per proposal (negligible).

### Gross Margin Analysis

| Pricing Tier | Monthly Price | Proposals/mo | API Cost/mo | Gross Margin |
|---|---|---|---|---|
| Starter (₹5,000) | $60 | 3 | $7.86 | 87% |
| Growth (₹15,000) | $180 | 15 | $39.30 | 78% |
| Studio (₹30,000) | $360 | 30 | $78.60 | 78% |
| Agency (₹50,000) | $600 | 50 | $131.00 | 78% |

Infrastructure costs (Fly.io hosting for generated sites, Supabase DB, R2 storage) add approximately $50-100/month at platform scale, not per-customer. The LLM API is the only variable cost that scales with usage.

**Key insight**: At 78%+ gross margins and sub-₹250 marginal cost per proposal, the pricing constraint is value perception, not cost structure. Even if Claude's pricing doubled, margins would remain above 55%.

### Comparison: NUPROP API Cost vs. Human Cost

| | NUPROP | Human (Manual) |
|---|---|---|
| Time per exhaustive proposal | 30-60 minutes (interactive) | 20-40 hours |
| Direct cost per proposal | ₹220 (API) | ₹60,000-₹1,20,000 (billable hours at ₹3,000/hr) |
| Output formats per run | 4-6 simultaneous | 1 (then manual conversion) |
| Market research included | Yes (automated) | Rarely (too time-consuming) |
| Cost benchmarking included | Yes (with sources) | Rarely |
| Win rate (expected) | 45-55% (with benchmarking) | 39% (industry average) |

**ROI per proposal**: 300-1,000× cost savings. If NUPROP helps win even one additional pitch per quarter, the entire annual subscription pays for itself hundreds of times over.

---


---


## 18. Roadmap & Milestones

### Phase A: Internal Skill (Weeks 1-4)

| Week | Milestone |
|---|---|
| 1 | SKILL.md written, rate card JSON configured, covering letter template tested |
| 2 | Market research module tested on 3 client scenarios, benchmark extraction working |
| 3 | Cost model builder + narrative generator tested end-to-end, DOCX output working |
| 4 | Interactive site template working, deployed for first real pitch |

**Exit criteria for Phase A**: 5 real client proposals generated using the skill, with at least 1 win attributed to the improved proposal quality.

### Phase B: Validation (Weeks 5-12) — Expanded

| Week | Milestone | Details |
|---|---|---|
| 5 | Refine SKILL.md based on first 5 proposals | Fix research query patterns, adjust rate card mappings, improve letter quality based on client feedback |
| 6 | Second real pitch using the skill | Measure time saved vs. manual process, note where AI output needed heavy editing |
| 7 | Recruit 3 beta testers | Approach friendly agency founders (design agencies, tech consultancies, branding studios). Offer: "We'll generate your next proposal for free using our new tool. You give us feedback." |
| 8 | Beta tester onboarding | Walk each tester through the Claude Code skill. Set up their rate card JSON. Generate their first proposal together on a call. |
| 9 | Collect feedback round 1 | Structured interview: What saved time? What felt wrong? Would you pay for this? How much? What output format matters most? |
| 10 | Build minimal web wrapper | React chat interface + output viewer. Not a full platform — just enough to remove the Claude Code dependency for non-technical users. |
| 11 | Beta round 2 with web wrapper | 5-7 users generating proposals through the web UI. Track: completion rate, time spent, output quality ratings, feature requests. |
| 12 | Validation checkpoint | Exit criteria below. |

**Exit Criteria for Phase B** (ALL must be met to proceed to Phase C):
- [ ] 10+ beta users have generated proposals
- [ ] 30+ total proposals generated across all users
- [ ] Net Promoter Score > 40 from beta testers
- [ ] At least 3 users express willingness to pay ₹10,000+/month
- [ ] At least 1 confirmed pitch win attributed to NUPROP-generated proposal
- [ ] Average proposal generation time < 2 hours (from brief to all outputs)
- [ ] No critical quality issues in the last 10 proposals generated

**If exit criteria not met**: Extend Phase B by 4 weeks. Focus on the specific failure point (quality? speed? willingness to pay?). Do not proceed to Phase C until the product is validated.

---

### Phase C: Platform Launch (Weeks 13-26)

| Week | Milestone |
|---|---|
| 13-16 | Full platform build: FastAPI backend, React frontend, proposal engine, site generator |
| 17-18 | Analytics dashboard, engagement scoring, notification system |
| 19-20 | Rate card manager, portfolio library, client CRM |
| 21-22 | Pricing page, Stripe billing integration, onboarding wizard |
| 23-24 | Private beta with 25 agencies, iterate on feedback |
| 25-26 | Public launch, content marketing, ProductHunt launch |

### Phase D: Growth Features (Months 7-12) — Expanded

| Month | Feature | Priority | Effort |
|---|---|---|---|
| 7 | Win/loss learning engine | High | 3 weeks |
| 7 | Slide deck (PPTX) output | Medium | 2 weeks |
| 8 | AI voice calibration (learn agency's writing style from past proposals) | High | 3 weeks |
| 8 | Custom domain support for proposal sites | Medium | 1 week |
| 9 | Notion and Google Docs output | Medium | 2 weeks |
| 9 | CRM read-only integration (HubSpot, Pipedrive) — pull client data | Low | 3 weeks |
| 10 | Multi-language covering letter (Hindi, French, Spanish) | Medium | 2 weeks |
| 10 | Deal room output for enterprise proposals | Low | 3 weeks |
| 11 | Proposal A/B testing (send 2 variants, track which wins) | Medium | 2 weeks |
| 11 | Team collaboration (multiple editors on one proposal) | Medium | 3 weeks |
| 12 | API access for custom integrations | Low | 2 weeks |
| 12 | Shopify App Store listing (cross-sell with NULOOK) | Low | 1 week |

### Multi-Language Strategy (Phase D, Month 10)

Not just translation — the AI adapts research, benchmarks, and cultural tone:

| Language | Research Adaptation | Letter Tone Adaptation |
|---|---|---|
| Hindi | Search Indian sources first, use ₹ pricing, reference Indian market reports | Warmer, more relational, may reference shared cultural context |
| French | Search French/EU sources, use € pricing, reference EU market reports | More formal structure, emphasis on methodology and rigour |
| Spanish | Search LatAm/Spain sources, use local currency, reference regional benchmarks | Warm but professional, emphasis on partnership language |

The covering letter, scope descriptions, and cost rationale are generated in the target language. The cost model calculations remain in the agency's base currency. The interactive site auto-detects the viewer's locale for number formatting.

---

*End of Addendum v1.1. Merge into PRD_NUPROP_ProposalCopilot.md to produce Version 2.0.*


---


## 19. Narrative Quality Standards

These rules govern how NUPROP writes. They are the difference between AI slop and a proposal that wins.

### Covering Letter Rules

1. **Always open with the client, not yourself.** The first 2-3 paragraphs are entirely about the client — their story, their challenge, their recent news. The agency introduction comes after.

2. **Reference at least one specific, researched fact.** Not "your company has grown significantly" but "your 13th consecutive year as a Gartner Magic Quadrant Leader" or "your recent acquisition of Commotion Inc. for AI transformation." This signals you did the work.

3. **Never use these phrases:**
   - "We look forward to hearing from you" (passive, cliché)
   - "Please find attached" (bureaucratic)
   - "We would love the opportunity" (needy)
   - "Leverage", "synergy", "best-in-class", "world-class", "cutting-edge", "state-of-the-art" (corporate emptiness)
   - "Our team of experienced professionals" (says nothing)

4. **Always use these moves:**
   - End with a specific CTA: "Would Thursday at 3pm work for a 30-minute walkthrough?" not "Let us know if you'd like to discuss."
   - Sign off with first name only (e.g., "Karthik") — feels personal, not corporate.
   - Reference the proposal's interactive format: "What you're looking at right now is a working preview of what the engagement could look like."

5. **Generate 2 variants** for every letter:
   - **Confident**: Bold, direct, makes claims about impact, assumes the win
   - **Warm**: Empathetic, relationship-focused, collaborative tone, acknowledges the client's complexity

6. **Length**: 400-600 words. Never shorter (feels thin), never longer (loses attention).

### Scope Description Rules

1. **Be specific, not vague.** Not "we will create brand assets" but "3 logo concepts, each in 12+ file formats (vector, raster, mono, reverse, favicon, social avatar), with 2 revision rounds."

2. **Always state exclusions.** "Printing costs are not included and will be quoted separately upon vendor selection." This prevents scope creep and demonstrates professionalism.

3. **State the creative standard.** "3 creative options presented. 2 revision rounds included." This is Veeville's differentiator — most agencies offer 1-2 concepts.

### Cost Rationale Rules

1. **Every benchmark must be sourced.** Include the publication name, year, and a specific data point. "Indian mid-tier agencies charge ₹5-15L/month for comparable retainers (Gracia Marcom 2026 agency review)" not "agencies typically charge more."

2. **Never fabricate benchmarks.** If no published data exists, say "No published benchmark found for this specific service category — estimate based on our rate card at [hourly rate] × [estimated hours]."

3. **Frame comparisons fairly.** Show the range (budget → mid-tier → premium), position our price within it, and explain why our position is justified.

---


---


## 20. Proposal Delivery Playbook

NUPROP doesn't just generate proposals — it generates a *pitch experience*. This section codifies the delivery strategy.

### Pre-Send Checklist

- [ ] Interactive site loads in <2 seconds
- [ ] Mobile responsive (test on iPhone Safari)
- [ ] PDF attachment is <10MB
- [ ] All client-specific facts in covering letter are verified
- [ ] Analytics tracking is active on the site
- [ ] Password protection enabled (if required)
- [ ] Proposal expiry date set

### Delivery Sequence

**Step 1**: Send the URL 10 minutes before a scheduled call, with the email:

> "We've built something for you. Please open this link before our call: [URL]"

If no call is scheduled, send the URL with a warm email and suggest a specific time.

**Step 2**: Let them explore. Don't screenshare the site — let the client experience it in their own browser. They'll scroll, click, expand cards. The analytics will show you what they looked at.

**Step 3**: If there's a demo embed (T-COMM style), walk them through it live: "Type a question about your company and see what happens." This is the moment that separates you from every other agency.

**Step 4**: Land the key line: "This took us [N] days to build. Imagine what we do in twelve months."

**Step 5**: Close with a specific next step: "Can we schedule a 45-minute working session next week to refine the scope based on your feedback?"

### Post-Send Follow-Up (AI-Assisted)

NUPROP monitors engagement and suggests follow-ups:

| Signal | AI Suggestion |
|---|---|
| Opened within 1 hour | "Strong interest. Follow up in 24 hours with a brief check-in." |
| Spent >3 min on Investment section | "They're evaluating price. Prepare a cost justification talking point." |
| Expanded all scope cards | "They're thorough. They'll likely have detailed questions. Prepare." |
| Downloaded the PDF | "They're sharing internally. Ask who else will be reviewing." |
| Return visit after 2+ days | "Still considering. Send a brief 'anything I can clarify?' note." |
| No open after 48 hours | "Nudge with a different angle. Send the one-pager instead." |
| Multiple unique visitors | "They forwarded it. Ask for a group call." |

---


---


## 21. Success Metrics

### Phase A Metrics

| Metric | Target |
|---|---|
| Time to generate a proposal | < 4 hours (vs. current 2-3 days) |
| Proposals generated per month | 4-6 |
| Win rate improvement | +15% above baseline |
| Client engagement with interactive site | > 3 min average time on site |

### Phase C Metrics

| Metric | Month 3 | Month 6 | Month 12 |
|---|---|---|---|
| Registered agencies | 30 | 100 | 300 |
| Paying agencies | 10 | 50 | 150 |
| MRR | ₹1,00,000 | ₹6,00,000 | ₹18,00,000 |
| Proposals generated (total) | 100 | 500 | 2,000 |
| Average engagement score | 45 | 50 | 55 |
| Platform win rate (reported) | 35% | 40% | 45% |

### North Star Metric

**Proposal win rate of NUPROP users vs. industry average.**

Industry average: 39% (Loopio 2026). Target for NUPROP users: 55%+ within 6 months of adoption.

---


## Appendix A: Market Data Sources

- Loopio 2026 RFP Response Trends & Benchmarks Report (1,500+ teams surveyed)
- OpenAsset 2025 Proposal Efficiency Report
- Jigsaw Kraft 2026 India Branding Cost Guide (52 agencies analysed)
- Clutch 2026 Branding Agency Pricing (average project: $71,651)
- Gracia Marcom 2026 India Agency Retainer Report
- ARD Digital Media 2025 Video Production Pricing Guide (India)
- Filmgoi 2025 Corporate Video Pricing Guide
- KumoHQ / WOW Infotech 2025-2026 AI Chatbot Development Cost Reports
- FICCI-EY 2025 Media & Entertainment Report (₹59,200 Cr digital ad spend)
- Toolradar 2026 AI Proposal Writing Tools Report

## Appendix B: Competitive Pricing Reference

| Tool | Price | Key Feature | What It Lacks |
|---|---|---|---|
| PandaDoc | $35-65/user/mo | Full document lifecycle | No AI research, no interactive output |
| Proposify | $49/user/mo | Beautiful templates, analytics | No AI narrative, no market benchmarking |
| Qwilr | $35-59/user/mo | Web-based proposals | No AI cost justification |
| Better Proposals | $19-49/user/mo | Simple, affordable | No AI at all |
| AiDocX | ~$20/mo | AI document generation | Contract-focused, no proposal workflow |
| Lindy AI | $49/mo | AI automation | General purpose, not proposal-specific |
| NUPROP (proposed) | ₹5,000-50,000/mo | AI research + narrative + interactive output + benchmarking | New, unproven, India-first |

---

*End of PRD. This document should be used as the foundation for both the Claude Code skill (Phase A) and the eventual platform build (Phase C). Start with Phase A — it costs nothing and starts working on your next pitch.*


## Appendix C: Reference Implementation — Tata Communications

The Tata Communications 25th Anniversary proposal, built during NUPROP's design conversation, serves as the reference implementation for the most exhaustive proposal type.

### Inputs
- Client brief: 29-page PDF presentation with creative themes, communication plan, and engagement ideas
- Annual campaigns list: Excel spreadsheet with 21 recurring campaigns across IC, HR, CSR, Legal, and Corporate Services
- Verbal context: year-long engagement, all three themes approved, warm pitch to IC team, no budget signal

### AI Pipeline Execution
- **Client research**: 7 web searches → company overview, CEO transition (A.S. Lakshminarayanan retiring April 13, Ganesh Lakshminarayanan incoming), Gartner 13-year streak, recent awards, VSNL history
- **Market benchmarking**: 12 web searches across 6 categories → 37 data points with sources
- **Cost model**: 35 line items across 4 workstreams → ₹1,97,90,000 subtotal → 12% annual discount → ₹1,74,15,000 total
- **Narrative**: 2 covering letter variants, executive summary, 35 scope descriptions, 10-category cost rationale, standard terms
- **Outputs**: interactive pitch site PRD, DOCX proposal (validated), HTML cost rationale, email draft (2 variants)

### Outputs Produced
1. `Veeville_TataComms_25thAnniversary_Proposal.docx` — 10-section formal proposal with cost tables
2. `Veeville_TataComms_CostRationale.html` — designed document with benchmark cards and value comparison
3. `PRD_TataComms25_InteractivePitch.md` — full PRD for interactive pitch site with T-COMM AI demo
4. `SKILL.md` — standalone Claude Code skill for proposal generation
5. `veeville-rates.json` — full rate card (also as `Veeville_RateCard.xlsx`)
6. Covering letter (2 variants — Confident and Warm)
7. Email draft (2 variants)

### Token Usage & Cost
- Input tokens: ~268,000
- Output tokens: ~121,000
- Model: Claude Sonnet 4.6
- Total API cost: **$2.62 (₹220)**
- With prompt caching: **$1.40 (₹117)**

### Key Innovations Demonstrated
- **Three themes in parallel** — unusual for anniversary campaigns, tripling creative production but giving the client flexibility
- **T-COMM AI demo** — a working prototype embedded in the pitch, powered by Claude API with company-specific knowledge base
- **CEO transition awareness** — research uncovered the leadership change happening on April 13, turning the proposal into a "first initiative under new leadership" opportunity
- **Covering letter technique** — opens on the ocean floor with a fibre optic cable, never mentions Veeville until paragraph 4

---

