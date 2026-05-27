"""The proposal-generation pipeline, extracted from ChatViewModel.

Each method runs one phase against the session it was constructed with, commits
its own writes, and publishes WebSocket events through Redis *after* the commit.
The worker process constructs this with a fresh per-job session; nothing here
touches a request-scoped session.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.schemas.chat_schemas import ChatMessageResponse
from app.infrastructure.db.models.agency import Agency
from app.infrastructure.db.models.chat_message import MessageRole, MessageType
from app.infrastructure.db.repositories.chat_message_repo import ChatMessageRepository
from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from app.infrastructure.queue.events import publish
from app.infrastructure.db.repositories.rate_card_repo import RateCardRepository
from app.services.ai.benchmark_agent import BenchmarkAgent
from app.services.ai.brief_analyzer import BriefAnalyzer
from app.services.ai.cost_model_builder import CostModelBuilder
from app.services.ai.rate_gap_analyzer import analyze_gaps
from app.services.ai.research_agent import RESEARCH_SYSTEM, ResearchAgent
from app.services.ai.section_facts import generate_fact_section
from app.services.ai.section_synthesis import generate_synthesis_section
from app.services.ai.web_search_loop import synthesize_research
from app.services.llm import Tier, get_ai_service
from app.services.research_planner import generate_benchmarks_plan, generate_research_plan
from app.services.research_streaming import ActivityFlusher, process_stream
from app.services.sections import (
    FACT_SECTIONS,
    SECTION_ORDER,
    SYNTHESIS_SECTIONS,
    default_sections_for_template,
)

logger = logging.getLogger(__name__)


class PipelineService:
    def __init__(self, session: AsyncSession, redis):
        self.session = session
        self.redis = redis
        self.proposal_repo = ProposalRepository(session)
        self.msg_repo = ChatMessageRepository(session)

    # ── WS helpers ───────────────────────────────────────────────────────────
    async def _emit(self, proposal_id, payload: dict) -> None:
        await publish(self.redis, str(proposal_id), payload)

    async def _emit_progress(self, proposal_id, agent: str, status: str, detail: str) -> None:
        await self._emit(
            proposal_id,
            {"type": "progress", "agent": agent, "status": status, "detail": detail},
        )

    async def _emit_message(self, proposal_id, msg) -> None:
        await self._emit(
            proposal_id,
            {
                "type": "new_message",
                "message": ChatMessageResponse.model_validate(msg).model_dump(mode="json"),
            },
        )

    async def _emit_phase_change(self, proposal_id, phase: str) -> None:
        await self._emit(proposal_id, {"type": "phase_change", "phase": phase})

    async def _load_template_config(self, proposal) -> dict | None:
        if not proposal.template_id:
            return None
        from app.infrastructure.db.models.template import StrategyTemplate
        result = await self.session.execute(
            select(StrategyTemplate).where(StrategyTemplate.template_key == proposal.template_id)
        )
        tmpl = result.scalar_one_or_none()
        if tmpl and isinstance(tmpl.config, dict):
            return tmpl.config
        return None

    async def _load_context_brief(self, proposal) -> str | None:
        from app.services.context_service import get_or_create_proposal_brief
        return await get_or_create_proposal_brief(self.session, proposal)

    async def _detect_rate_card_gaps(self, proposal, brief: dict) -> None:
        """Identify hourly roles + offerings the cost-model phase will need that
        the agency's active rate card does not yet have, and persist them on
        the proposal. Pipeline pause is enforced later by the template-approval gate."""
        gaps_input = await analyze_gaps(brief)
        needed_roles = gaps_input["needed_roles"]
        needed_offerings = gaps_input["needed_offerings"]

        rc_repo = RateCardRepository(self.session)
        rate_card = await rc_repo.get_active(proposal.agency_id)

        existing_roles = set((rate_card.hourly_rates or {}).keys()) if rate_card else set()
        existing_offerings = set((rate_card.offerings or {}).keys()) if rate_card else set()

        missing_roles = [r for r in needed_roles if r not in existing_roles]
        missing_offerings = [o for o in needed_offerings if o not in existing_offerings]

        if not missing_roles and not missing_offerings:
            return  # nothing to write — proposal.rate_card_gaps stays NULL

        await self.proposal_repo.update(proposal.id, rate_card_gaps={
            "missing_roles": missing_roles,
            "missing_offerings": missing_offerings,
            "needed_roles": needed_roles,
            "needed_offerings": needed_offerings,
        })

    async def analyze_brief(self, proposal_id: UUID | str) -> None:
        """Brief-intake phase. Extracted from ChatViewModel._handle_brief_phase."""
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        if proposal is None:
            logger.warning("analyze_brief: proposal %s not found", proposal_id)
            return

        all_messages = await self.msg_repo.list_by_proposal(proposal_id)
        chat_history = [
            {"role": m.role, "content": m.content}
            for m in all_messages
            if m.role in (MessageRole.USER.value, MessageRole.ASSISTANT.value)
            and m.message_type == MessageType.TEXT.value
        ]

        context_brief = await self._load_context_brief(proposal)
        result = await BriefAnalyzer().analyze(
            chat_history=chat_history,
            current_brief=proposal.brief,
            context_brief=context_brief,
        )

        msg_type = MessageType.TEXT.value
        extra_data: dict = {}
        if result.brief_complete:
            msg_type = MessageType.BRIEF_SUMMARY.value
            extra_data = {"brief": result.brief_data, "requires_approval": True}
            await self.proposal_repo.update(proposal.id, brief=result.brief_data)
            await self._detect_rate_card_gaps(proposal, result.brief_data)

        assistant_msg = await self.msg_repo.create(
            proposal_id=proposal_id,
            role=MessageRole.ASSISTANT.value,
            message_type=msg_type,
            content=result.response_text,
            extra_data=extra_data,
            phase="brief",
        )
        await self.session.commit()          # commit BEFORE broadcasting
        await self._emit_message(proposal_id, assistant_msg)
        await self._emit(proposal_id, {"type": "typing", "typing": False})

    async def run_research(self, proposal_id: UUID | str) -> None:
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        if proposal is None:
            return

        # 1. Pre-flight plan (Haiku) — short structured JSON, ~1s.
        plan = await generate_research_plan(brief=proposal.brief or {})
        plan_msg = await self.msg_repo.create(
            proposal_id=proposal_id,
            role=MessageRole.ASSISTANT.value,
            message_type="research_plan",
            content="",
            extra_data={"phase": "research", **plan},
            phase="research",
        )
        await self.session.commit()
        await self._emit_message(proposal_id, plan_msg)

        # 2. Activity log (starts empty, status="running").
        log_msg = await self.msg_repo.create(
            proposal_id=proposal_id,
            role=MessageRole.ASSISTANT.value,
            message_type="research_activity_log",
            content="",
            extra_data={"phase": "research", "status": "running", "events": []},
            phase="research",
        )
        await self.session.commit()
        await self._emit_message(proposal_id, log_msg)

        # 3. Streaming Sonnet 4.6 call with web_search.
        #
        # Should be Opus 4.7 for agentic-loop quality, but: (a) this AWS account
        # lacks 4.7 access (403), (b) Opus 4.6 doesn't accept the web_search_20250305
        # tool. Sonnet 4.6 supports the tool and already powers run_benchmarks below.
        # Revert to Tier.HEAVY when Opus 4.7 access is granted by AWS.
        flusher = ActivityFlusher(
            session=self.session,
            msg_repo=self.msg_repo,
            redis=self.redis,
            log_msg_id=log_msg.id,
            proposal_id=proposal_id,
            phase="research",
        )

        client_name = (proposal.brief or {}).get("client", {}).get("name", "the client")
        industry = (proposal.brief or {}).get("client", {}).get("industry")
        context_brief = await self._load_context_brief(proposal)
        user_msg = (
            f"Research {client_name}"
            + (f" (industry: {industry})" if industry else "")
            + ". Be thorough — this research directly feeds into a high-value proposal."
            + " Search the web comprehensively."
        )
        if context_brief:
            user_msg += f"\n\n## Existing context\n{context_brief}"

        # Build the system-prompt substitutions (the same pattern ResearchAgent.research_client used).
        _context_section_text = ""
        if context_brief:
            _context_section_text = (
                f"## Existing Context (from past interactions)\n"
                f"The agency already knows this about the client:\n{context_brief}\n\n"
                f"Focus your research on what's NEW or what fills gaps in the existing context. "
                f"Don't repeat what's already known."
            )
        system_prompt = RESEARCH_SYSTEM.format(
            client_name=client_name,
            max_searches=10,
            context_section=_context_section_text,
            template_section="",  # template-queries path not wired in this orchestration; v2.
        )

        # 4. Search via Serper + synthesize via Sonnet 4.6.
        #
        # Anthropic's hosted web_search tool is not exposed on AWS Bedrock
        # in ap-northeast-1 (see HANDOFF § 5e + docs/superpowers/specs/
        # bedrock-web-search-fix.md Option 2). Instead we run the planner's
        # queries through our Serper-backed WebSearchClient and feed the
        # results into a single synthesis LLM call.
        try:
            body, citations, spans = await synthesize_research(
                queries=(plan.get("queries") or []),
                system_prompt=system_prompt,
                user_message=user_msg,
                on_event=flusher.append,
            )
            await flusher.flush(final_status="complete")
        except Exception as exc:  # noqa: BLE001
            logger.exception("run_research failed for %s", proposal_id)
            try:
                await flusher.flush(final_status="failed", error=str(exc))
            except Exception:  # noqa: BLE001
                logger.exception("flusher.flush failed during exception handling")
            raise

        # 5. Findings — annotated.
        findings_msg = await self.msg_repo.create(
            proposal_id=proposal_id,
            role=MessageRole.ASSISTANT.value,
            message_type="research_findings",
            content=body,
            extra_data={"phase": "research", "citations": citations, "spans": spans},
            phase="research",
        )
        await self.proposal_repo.update(proposal.id, research=body)
        await self.session.commit()
        await self._emit_message(proposal_id, findings_msg)

    async def run_benchmarks(self, proposal_id: UUID | str) -> None:
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        if proposal is None:
            return

        from app.services.ai.benchmark_agent import BENCHMARK_SYSTEM

        # 1. Pre-flight plan.
        plan = await generate_benchmarks_plan(brief=proposal.brief or {})
        plan_msg = await self.msg_repo.create(
            proposal_id=proposal_id,
            role=MessageRole.ASSISTANT.value,
            message_type="benchmarks_plan",
            content="",
            extra_data={"phase": "benchmarks", **plan},
            phase="benchmarks",
        )
        await self.session.commit()
        await self._emit_message(proposal_id, plan_msg)

        # 2. Activity log.
        log_msg = await self.msg_repo.create(
            proposal_id=proposal_id,
            role=MessageRole.ASSISTANT.value,
            message_type="benchmarks_activity_log",
            content="",
            extra_data={"phase": "benchmarks", "status": "running", "events": []},
            phase="benchmarks",
        )
        await self.session.commit()
        await self._emit_message(proposal_id, log_msg)

        # 3. Streaming Sonnet 4.6 call with web_search.
        flusher = ActivityFlusher(
            session=self.session,
            msg_repo=self.msg_repo,
            redis=self.redis,
            log_msg_id=log_msg.id,
            proposal_id=proposal_id,
            phase="benchmarks",
        )

        deliverables = (proposal.brief or {}).get("project", {}).get("deliverables", []) or []
        categories = sorted({d.get("category", "") for d in deliverables if d.get("category")})
        country = "India"  # NUPROP is India-focused; future: pull from agency settings.
        user_msg = (
            f"Find pricing benchmarks for these design / creative-agency services in {country}: "
            + ", ".join(categories or ["general design services"])
            + ". Search the web for real published data."
        )
        context_brief = await self._load_context_brief(proposal)
        if context_brief:
            client_name = (proposal.brief or {}).get("client", {}).get("name", "the client")
            user_msg += (
                f"\n\n## Existing context on {client_name}\n{context_brief}\n"
                f"Use this to focus the benchmark search on the client's actual segment."
            )

        # Build the system-prompt substitutions — same pattern as BenchmarkAgent.find_benchmarks
        # (benchmark_agent.py:74-83). BENCHMARK_SYSTEM is a str.format template with
        # {max_searches} and {categories_section} placeholders; pass the raw template
        # to Bedrock and the model receives literal curly-brace text.
        max_searches = 8
        categories_section = (
            "\n".join(f"- {c}" for c in categories)
            if categories else "- General design agency services"
        )
        system_prompt = BENCHMARK_SYSTEM.format(
            max_searches=max_searches,
            categories_section=categories_section,
        )

        # Search via Serper + synthesize via Sonnet 4.6 — same shape as
        # run_research (see HANDOFF § 5e + bedrock-web-search-fix.md Option 2).
        try:
            body, citations, spans = await synthesize_research(
                queries=(plan.get("queries") or []),
                system_prompt=system_prompt,
                user_message=user_msg,
                on_event=flusher.append,
            )
            await flusher.flush(final_status="complete")
        except Exception as exc:  # noqa: BLE001
            logger.exception("run_benchmarks failed for %s", proposal_id)
            try:
                await flusher.flush(final_status="failed", error=str(exc))
            except Exception:  # noqa: BLE001
                logger.exception("flusher.flush failed during exception handling")
            raise

        # 4. Findings — annotated, separate message from research_findings.
        findings_msg = await self.msg_repo.create(
            proposal_id=proposal_id,
            role=MessageRole.ASSISTANT.value,
            message_type="benchmarks_findings",
            content=body,
            extra_data={"phase": "benchmarks", "citations": citations, "spans": spans},
            phase="benchmarks",
        )
        await self.proposal_repo.update(proposal.id, benchmarks=body)
        await self.session.commit()
        await self._emit_message(proposal_id, findings_msg)

        # Advance pipeline state to cost_model_review (unchanged from previous behaviour).
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        pipeline = (proposal.pipeline_state or {}).copy()
        pipeline["phases_completed"] = pipeline.get("phases_completed", []) + ["research"]
        pipeline["current_phase"] = "cost_model_review"
        await self.proposal_repo.update(proposal.id, pipeline_state=pipeline)
        await self.session.commit()
        await self._emit_phase_change(proposal_id, "cost_model_review")

    async def build_cost_model(self, proposal_id: UUID | str) -> None:
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        if proposal is None:
            return
        template_config = await self._load_template_config(proposal)
        effective_config = self._merge_preferences_into_config(
            template_config, proposal.preferences or {}
        )

        await self._emit_progress(proposal_id, "cost_model", "searching", "Building cost model from rate card...")
        rc_repo = RateCardRepository(self.session)
        rate_card_row = await rc_repo.get_active(proposal.agency_id)
        model = await CostModelBuilder().build(
            brief=proposal.brief or {},
            rate_card_row=rate_card_row,
            template_config=effective_config,
            rate_card_override=proposal.rate_card_override,
        )
        cost_dict = CostModelBuilder.model_to_dict(model)
        await self.proposal_repo.update(proposal.id, cost_model=cost_dict)
        await self.session.commit()                       # commit BEFORE broadcast

        # human-readable summary — verbatim from ChatViewModel._build_cost_model
        lines = ["**Cost Model — Review & Approve**\n"]
        lines.append(f"| Deliverable | Package | Qty | Unit Cost | Total | Match |")
        lines.append(f"|---|---|---|---|---|---|")
        for item in model.line_items:
            lines.append(
                f"| {item.deliverable} | {item.package_name[:40]} | {item.quantity} "
                f"| ₹{item.unit_cost:,} | ₹{item.total:,} | {item.match_quality} |"
            )
        lines.append(f"\n**Subtotal**: ₹{model.subtotal:,}")
        if model.discount_percent > 0:
            lines.append(f"**Discount** ({model.discount_percent}%): −₹{model.discount_amount:,}")
        lines.append(f"**Total (excl. GST)**: ₹{model.total:,}")
        lines.append(f"**GST (18%)**: ₹{model.gst_amount:,}")
        lines.append(f"**Grand Total**: ₹{model.grand_total:,}")
        if model.multipliers_applied:
            lines.append(f"\n*Multipliers applied: {', '.join(model.multipliers_applied)}*")
        content = "\n".join(lines)

        msg = await self.msg_repo.create(
            proposal_id=proposal_id,
            role=MessageRole.ASSISTANT.value,
            message_type=MessageType.COST_MODEL.value,
            content=content,
            extra_data={"cost_model": cost_dict, "requires_approval": True, "gate_type": "cost_model"},
            phase="cost_model_review",
        )
        await self.session.commit()
        await self._emit_progress(proposal_id, "cost_model", "complete", "Cost model ready for review")
        await self._emit_message(proposal_id, msg)

    async def generate_sections(self, proposal_id: UUID | str) -> None:
        """Pass-1 facts (parallel) + Pass-2 synthesis (sequential). Writes each
        section's payload to its dedicated column on the proposal."""
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        if proposal is None:
            logger.warning("generate_sections: proposal %s not found", proposal_id)
            return

        agency_row = await self.session.execute(
            select(Agency).where(Agency.id == proposal.agency_id)
        )
        agency = agency_row.scalar_one()
        agency_name = agency.name

        template_config = await self._load_template_config(proposal)
        context_brief = await self._load_context_brief(proposal)
        default_sections = default_sections_for_template(template_config)

        # ── Pass 1 — fact sections in parallel ────────────────────────────────
        fact_targets = [s for s in FACT_SECTIONS if s in default_sections]

        async def _one_fact(section_type: str) -> tuple[str, dict]:
            payload = await generate_fact_section(
                section_type=section_type,
                brief=proposal.brief or {},
                research=proposal.research,
                cost_model=proposal.cost_model or {},
                template_config=template_config,
                context_brief=context_brief,
                agency_name=agency_name,
            )
            return section_type, payload

        await self._emit_progress(
            proposal_id, "sections", "running",
            f"generating {len(fact_targets)} fact sections in parallel",
        )
        fact_results = await asyncio.gather(*[_one_fact(s) for s in fact_targets])
        pass1_sections: dict[str, dict] = dict(fact_results)

        for section_type, payload in pass1_sections.items():
            await self.proposal_repo.update(proposal_id, **{section_type: payload})

        # ── Pass 2 — synthesis sections sequentially ──────────────────────────
        synth_targets = [s for s in SYNTHESIS_SECTIONS if s in default_sections]
        for section_type in synth_targets:
            await self._emit_progress(
                proposal_id, "sections", "running", f"synthesising {section_type}",
            )
            payload = await generate_synthesis_section(
                section_type=section_type,
                brief=proposal.brief or {},
                pass1_sections=pass1_sections,
                context_brief=context_brief,
                agency_name=agency_name,
            )
            await self.proposal_repo.update(proposal_id, **{section_type: payload})
            pass1_sections[section_type] = payload   # make this section visible to later synthesis sections

        await self.session.commit()

        pipeline = (proposal.pipeline_state or {}).copy()
        pipeline["current_phase"] = "section_editor"
        pipeline["phases_completed"] = pipeline.get("phases_completed", []) + ["sections"]
        await self.proposal_repo.update(proposal_id, pipeline_state=pipeline)
        await self.session.commit()

        await self._emit_phase_change(proposal_id, "section_editor")

    @staticmethod
    def _merge_preferences_into_config(template_config: dict | None, preferences: dict) -> dict:
        """Overlay user preferences onto template config for AI services."""
        config = dict(template_config or {})
        if not preferences:
            return config

        narr = dict(config.get("narrative", {}))
        if preferences.get("letter_strategy"):
            narr["letter_strategy"] = preferences["letter_strategy"]
        if preferences.get("letter_opening"):
            narr["letter_opening_instruction"] = preferences["letter_opening"]
        if preferences.get("scope_detail_level"):
            narr["scope_detail_level"] = preferences["scope_detail_level"]
        if preferences.get("letter_length"):
            narr["letter_length"] = preferences["letter_length"]
        if preferences.get("letter_custom_instructions"):
            narr["letter_custom_instructions"] = preferences["letter_custom_instructions"]
        if narr:
            config["narrative"] = narr

        cm = dict(config.get("cost_model", {}))
        if preferences.get("pricing_model"):
            cm["pricing_model"] = preferences["pricing_model"]
        if preferences.get("discount_tags"):
            cm["default_multipliers"] = preferences["discount_tags"]
        if cm:
            config["cost_model"] = cm

        out = dict(config.get("output", {}))
        if preferences.get("site_theme"):
            out["site_theme"] = preferences["site_theme"]
        if preferences.get("primary_format"):
            out["primary_format"] = preferences["primary_format"]
        if out:
            config["output"] = out

        return config
