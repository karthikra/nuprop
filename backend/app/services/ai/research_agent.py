from __future__ import annotations

from app.infrastructure.external.anthropic_client import AnthropicClient
from app.core.config import get_settings


RESEARCH_SYSTEM = """You are a senior research analyst preparing intelligence for a proposal copilot. Your job is to build a comprehensive, fact-based client profile that will directly inform a business proposal.

## Research Strategy
Search the web thoroughly. Run multiple searches to cover all angles. If initial searches are thin, try alternative queries. You have up to {max_searches} web searches available — use them all if needed.

## What to Research (in order of priority)

### 1. Company Fundamentals
- Full legal name, founding year, headquarters
- Revenue, employee count, public/private status
- Parent company or group affiliation
- Core business: what they actually do, who their customers are

### 2. Leadership & Decision-Makers
- CEO/MD name, tenure, background
- Recent leadership changes (incoming, outgoing, reshuffles)
- Board composition if public company
- Key executives in areas relevant to this project

### 3. Recent Developments (last 6-12 months)
- Press releases, product launches, acquisitions
- Funding rounds, IPO plans, financial results
- Strategic pivots, new market entries
- Awards, recognitions, rankings (Gartner, Forrester, industry-specific)

### 4. Industry & Competitive Position
- Market share, competitive landscape
- Key competitors and how they differentiate
- Industry trends affecting this client
- Analyst commentary or ratings

### 5. Brand & Digital Presence
- Website quality, design maturity, technology stack signals
- Social media presence and engagement quality
- Content marketing, thought leadership
- Recent campaigns or brand initiatives

### 6. Proposal-Relevant Intelligence
- Anything that suggests what they NEED from an agency
- Pain points visible in their public communications
- Opportunities a design/creative agency could address
- Cultural signals: are they conservative? innovative? process-heavy?

{context_section}

{template_section}

## Output Format (markdown)

# Client Research: {client_name}

## Company Overview
[Comprehensive paragraph with specific numbers and facts]

## Leadership
[Key people with roles, tenure, recent changes]

## Recent Developments
[Chronological bullet points, most recent first, with dates]

## Industry Position
[Market context, competitors, positioning]

## Brand & Digital Assessment
[Observations about their current presence and quality]

## Narrative Hooks for Our Proposal
[3-5 specific facts, quotes, or observations that should be woven into the covering letter. These are the "I did my homework" signals.]

## Strategic Opportunities
[2-3 observations about what they might need from a creative/design agency]

## Sources
[List all URLs referenced]

IMPORTANT: Only include information you actually found. Never fabricate facts, numbers, or quotes. If a section has no data, write "Not found in public sources" rather than guessing."""


class ResearchAgent:
    def __init__(self):
        self._client = AnthropicClient()

    async def research_client(
        self,
        client_name: str,
        industry: str | None = None,
        template_queries: list[str] | None = None,
        context_brief: str | None = None,
        max_searches: int = 10,
    ) -> str:
        """Research the client using Claude's native web search. Returns markdown."""
        if not self._client.is_configured:
            return f"# Client Research: {client_name}\n\n*AI not configured. Set ANTHROPIC_API_KEY to enable research.*"

        # Build context section
        context_section = ""
        if context_brief:
            context_section = f"""## Existing Context (from past interactions)
The agency already knows this about the client:
{context_brief}

Focus your research on what's NEW or what fills gaps in the existing context. Don't repeat what's already known."""

        # Build template section
        template_section = ""
        if template_queries:
            queries_list = "\n".join(f"- {q}" for q in template_queries)
            template_section = f"""## Template-Specific Research Priorities
This is a specialized proposal type. Also research these angles:
{queries_list}"""

        system = RESEARCH_SYSTEM.format(
            client_name=client_name,
            max_searches=max_searches,
            context_section=context_section,
            template_section=template_section,
        )

        user_msg = f"Research {client_name}"
        if industry:
            user_msg += f" (industry: {industry})"
        user_msg += ". Be thorough — this research directly feeds into a high-value proposal. Search the web comprehensively."

        settings = get_settings()

        # Use Claude's native web search via the Anthropic SDK
        response = await self._client._client.messages.create(
            model=settings.ANTHROPIC_DEFAULT_MODEL,
            max_tokens=4096,
            system=system,
            tools=[{
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": max_searches,
            }],
            messages=[{"role": "user", "content": user_msg}],
        )

        # Extract text from the response (may contain multiple text blocks interspersed with tool use)
        text_parts = []
        for block in response.content:
            if hasattr(block, "text") and block.text:
                text_parts.append(block.text)

        return "".join(text_parts) if text_parts else f"# Client Research: {client_name}\n\nNo research results found."
