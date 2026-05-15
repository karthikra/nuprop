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
