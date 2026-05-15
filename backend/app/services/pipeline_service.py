"""The proposal-generation pipeline, extracted from ChatViewModel.

Each method runs one phase against the session it was constructed with, commits
its own writes, and publishes WebSocket events through Redis *after* the commit.
The worker process constructs this with a fresh per-job session; nothing here
touches a request-scoped session.
"""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.schemas.chat_schemas import ChatMessageResponse
from app.infrastructure.db.models.chat_message import MessageRole, MessageType
from app.infrastructure.db.repositories.chat_message_repo import ChatMessageRepository
from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from app.infrastructure.queue.events import publish
from app.services.ai.benchmark_agent import BenchmarkAgent
from app.services.ai.brief_analyzer import BriefAnalyzer
from app.services.ai.cost_model_builder import CostModelBuilder
from app.services.ai.narrative_generator import NarrativeGenerator
from app.services.ai.research_agent import ResearchAgent

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
        try:
            from app.infrastructure.db.models.client import Client
            from app.services.context_service import ContextService
            result = await self.session.execute(
                select(Client).where(Client.id == str(proposal.client_id))
            )
            client_row = result.scalar_one_or_none()
            if client_row and client_row.context_profile:
                client_name = proposal.brief.get("client", {}).get("name", "the client")
                return await ContextService().generate_context_brief(
                    client_name, client_row.context_profile
                )
        except Exception:  # noqa: BLE001 — context is best-effort
            logger.exception("context brief load failed")
        return None

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

        result = await BriefAnalyzer().analyze(chat_history=chat_history, current_brief=proposal.brief)

        msg_type = MessageType.TEXT.value
        extra_data: dict = {}
        if result.brief_complete:
            msg_type = MessageType.BRIEF_SUMMARY.value
            extra_data = {"brief": result.brief_data, "requires_approval": True}
            await self.proposal_repo.update(proposal.id, brief=result.brief_data)

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
        brief = proposal.brief
        client_name = brief.get("client", {}).get("name", "the client")
        industry = brief.get("client", {}).get("industry")
        template_config = await self._load_template_config(proposal)
        context_brief = await self._load_context_brief(proposal)
        research_queries = (
            (template_config or {}).get("research", {}).get("client_queries")
        )

        await self._emit_progress(proposal_id, "research", "searching", f"Researching {client_name}...")
        research_md = await ResearchAgent().research_client(
            client_name, industry, research_queries, context_brief=context_brief
        )
        await self.proposal_repo.update(proposal.id, research=research_md)
        await self.session.commit()                       # commit BEFORE broadcast
        await self._emit_progress(proposal_id, "research", "complete", "Client research done")

    async def run_benchmarks(self, proposal_id: UUID | str) -> None:
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        if proposal is None:
            return
        brief = proposal.brief
        deliverables = brief.get("project", {}).get("deliverables", [])
        template_config = await self._load_template_config(proposal)
        benchmark_queries = (
            (template_config or {}).get("research", {}).get("benchmark_queries")
        )

        await self._emit_progress(proposal_id, "benchmarks", "searching", "Finding pricing benchmarks...")
        benchmarks_md = await BenchmarkAgent().find_benchmarks(deliverables, "India", benchmark_queries)
        await self.proposal_repo.update(proposal.id, benchmarks=benchmarks_md)
        await self.session.commit()                       # commit BEFORE broadcast
        await self._emit_progress(proposal_id, "benchmarks", "complete", "Pricing benchmarks done")

        # combined research + benchmarks findings message
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        summary = (
            f"**Research and benchmarking complete.**\n\n---\n\n"
            f"{proposal.research}\n\n---\n\n{benchmarks_md}"
        )
        msg = await self.msg_repo.create(
            proposal_id=proposal_id,
            role=MessageRole.ASSISTANT.value,
            message_type=MessageType.RESEARCH_FINDINGS.value,
            content=summary,
            extra_data={"has_research": True, "has_benchmarks": True},
            phase="research",
        )
        # advance pipeline
        pipeline = proposal.pipeline_state.copy()
        pipeline["phases_completed"] = pipeline.get("phases_completed", []) + ["research"]
        pipeline["current_phase"] = "cost_model_review"
        await self.proposal_repo.update(proposal.id, pipeline_state=pipeline)
        await self.session.commit()                       # commit BEFORE broadcast
        await self._emit_message(proposal_id, msg)
        await self._emit_phase_change(proposal_id, "cost_model_review")

    async def build_cost_model(self, proposal_id: UUID | str) -> None:
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        if proposal is None:
            return
        template_config = await self._load_template_config(proposal)

        await self._emit_progress(proposal_id, "cost_model", "searching", "Building cost model from rate card...")
        model = await CostModelBuilder().build(
            brief=proposal.brief,
            db=self.session,
            agency_id=str(proposal.agency_id),
            benchmarks_md=proposal.benchmarks,
            template_config=template_config,
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

    async def generate_narrative(self, proposal_id: UUID | str) -> None:
        """Generate all narrative sections.

        Extraction of ChatViewModel._generate_narrative — agency/rate-card loads
        kept inline because they were inline in the source; template config goes
        through _load_template_config + _merge_preferences_into_config.
        """
        from app.infrastructure.db.models.agency import Agency
        from app.infrastructure.db.models.rate_card import RateCard

        proposal = await self.proposal_repo.get_by_id(proposal_id)
        if proposal is None:
            return

        result = await self.session.execute(
            select(Agency).where(Agency.id == str(proposal.agency_id))
        )
        agency = result.scalar_one_or_none()

        template_config = await self._load_template_config(proposal)

        result = await self.session.execute(
            select(RateCard)
            .where(RateCard.agency_id == str(proposal.agency_id), RateCard.is_active == True)
            .limit(1)
        )
        rate_card = result.scalar_one_or_none()

        effective_config = self._merge_preferences_into_config(
            template_config, proposal.preferences or {}
        )

        await self._emit_progress(
            proposal_id, "narrative", "searching", "Writing covering letter (2 variants)..."
        )

        narr = await NarrativeGenerator().generate_all(
            brief=proposal.brief,
            research=proposal.research,
            benchmarks=proposal.benchmarks,
            cost_model=proposal.cost_model or {},
            template_config=effective_config,
            agency_name=agency.name if agency else "the agency",
            agency_voice=agency.voice_profile if agency else None,
            agency_default_terms=agency.default_terms if agency else None,
            agency_payment_terms=agency.payment_terms if agency else None,
            agency_gst_rate=agency.gst_rate if agency else 0.18,
            rate_card_offerings=rate_card.offerings if rate_card else None,
            standard_options=rate_card.standard_options if rate_card else 3,
            standard_revisions=rate_card.standard_revisions if rate_card else 2,
        )

        await self.proposal_repo.update(
            proposal.id,
            covering_letter=narr.covering_letter,
            covering_letter_alt=narr.covering_letter_alt,
            executive_summary=narr.executive_summary,
            scope_sections=narr.scope_sections,
            cost_rationale=narr.cost_rationale,
            terms=narr.terms,
        )

        pipeline = proposal.pipeline_state.copy()
        pipeline["phases_completed"] = pipeline.get("phases_completed", []) + ["narrative_generation"]
        pipeline["current_phase"] = "narrative_review"
        await self.proposal_repo.update(proposal.id, pipeline_state=pipeline)
        await self.session.commit()                       # commit BEFORE broadcast

        await self._emit_progress(proposal_id, "narrative", "complete", "Narrative ready for review")
        await self._emit_phase_change(proposal_id, "narrative_review")

        scope_count = len(narr.scope_sections)
        content = (
            f"**Proposal narrative ready for review.**\n\n"
            f"I've written two covering letter variants ({narr.letter_strategy_primary} and {narr.letter_strategy_alt}), "
            f"the executive summary, {scope_count} scope descriptions"
            f"{', cost rationale,' if narr.cost_rationale else ''} and terms & conditions.\n\n"
            f"Review each section below and approve when ready."
        )
        msg = await self.msg_repo.create(
            proposal_id=proposal_id,
            role=MessageRole.ASSISTANT.value,
            message_type=MessageType.NARRATIVE_PREVIEW.value,
            content=content,
            extra_data={
                "requires_approval": True,
                "gate_type": "narrative",
                "sections": {
                    "covering_letter": narr.covering_letter,
                    "covering_letter_alt": narr.covering_letter_alt,
                    "letter_strategy_primary": narr.letter_strategy_primary,
                    "letter_strategy_alt": narr.letter_strategy_alt,
                    "executive_summary": narr.executive_summary,
                    "scope_sections": narr.scope_sections,
                    "cost_rationale": narr.cost_rationale,
                    "terms": narr.terms,
                },
            },
            phase="narrative_review",
        )
        await self.session.commit()
        await self._emit_message(proposal_id, msg)

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
