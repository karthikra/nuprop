from __future__ import annotations

from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ws_manager import ws_manager
from app.domain.schemas.chat_schemas import ChatMessageResponse
from app.infrastructure.db.models.chat_message import ChatMessage, MessageRole, MessageType
from app.infrastructure.db.repositories.chat_message_repo import ChatMessageRepository
from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from app.services.ai.template_matcher import TemplateMatcher
from app.viewmodels.shared.viewmodel import ViewModelBase


class ChatViewModel(ViewModelBase):
    """Chat orchestration. Pipeline phases run in the ARQ worker process; this
    viewmodel only validates, persists the user message + ack, and enqueues the
    first phase job. The actual phase work lives in PipelineService.
    """

    def __init__(self, request: Request, db: AsyncSession):
        super().__init__(request, db)
        self._msg_repo: ChatMessageRepository | None = None
        self._proposal_repo: ProposalRepository | None = None

    @property
    def msg_repo(self) -> ChatMessageRepository:
        if not self._msg_repo:
            self._msg_repo = ChatMessageRepository(self._db)
        return self._msg_repo

    @property
    def proposal_repo(self) -> ProposalRepository:
        if not self._proposal_repo:
            self._proposal_repo = ProposalRepository(self._db)
        return self._proposal_repo

    async def _enqueue(
        self,
        job_name: str,
        proposal_id,
        idempotency_key: str | None = None,
    ) -> None:
        """Push a pipeline-phase job onto the ARQ pool held on app.state.

        ARQ uses ``_job_id`` as an idempotency key — once a result exists for an
        ID, subsequent enqueues of the same ID are silently dropped for the
        result-TTL window (24h by default). That's correct for one-shot gate
        approvals (prevents double-runs from accidental double-clicks) but
        breaks multi-turn flows like ``analyze_brief`` where every user message
        must trigger a fresh run.

        Callers that need a fresh run per invocation pass an
        ``idempotency_key`` (e.g. the user message ID); it's appended to the
        job_id so each turn gets its own slot in ARQ's result store.
        """
        pool = self._request.app.state.arq_pool
        suffix = f":{idempotency_key}" if idempotency_key else ""
        await pool.enqueue_job(
            job_name, str(proposal_id), _job_id=f"{proposal_id}:{job_name}{suffix}"
        )

    async def _set_job_queued(self, proposal, phase: str) -> dict:
        """Return a copy of proposal.pipeline_state with job_status set to queued."""
        pipeline = proposal.pipeline_state.copy()
        pipeline["job_status"] = {"phase": phase, "state": "queued", "error": None}
        return pipeline

    async def get_messages(
        self,
        proposal_id: UUID,
        agency_id: UUID,
        skip: int = 0,
        limit: int = 200,
    ) -> list[ChatMessage] | None:
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        if not proposal or str(proposal.agency_id) != str(agency_id):
            self.error = "Proposal not found"
            self.status_code = 404
            return None
        return await self.msg_repo.list_by_proposal(proposal_id, skip=skip, limit=limit)

    async def get_ideation_messages(
        self,
        proposal_id: UUID,
        agency_id: UUID,
        skip: int = 0,
        limit: int = 200,
    ) -> list[ChatMessage] | None:
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        if not proposal or str(proposal.agency_id) != str(agency_id):
            self.error = "Proposal not found"
            self.status_code = 404
            return None
        return await self.msg_repo.list_by_proposal(
            proposal_id, skip=skip, limit=limit, channel="ideation",
        )

    async def send_message(
        self,
        proposal_id: UUID,
        agency_id: UUID,
        content: str,
    ) -> list[ChatMessage] | None:
        """Persist the user message; in the brief phase, enqueue analyze_brief
        and return just the user message — the assistant reply arrives via WS.
        Outside the brief phase, fall back to the echo placeholder (no AI loop).
        """
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        if not proposal or str(proposal.agency_id) != str(agency_id):
            self.error = "Proposal not found"
            self.status_code = 404
            return None

        current_phase = proposal.pipeline_state.get("current_phase", "brief")

        user_msg = await self.msg_repo.create(
            proposal_id=proposal_id,
            role=MessageRole.USER.value,
            message_type=MessageType.TEXT.value,
            content=content,
            phase=current_phase,
        )
        await self._broadcast_msg(proposal_id, user_msg)

        if current_phase == "brief":
            await ws_manager.broadcast(str(proposal_id), {"type": "typing", "typing": True})
            pipeline = await self._set_job_queued(proposal, "analyze_brief")
            await self.proposal_repo.update(proposal.id, pipeline_state=pipeline)
            # Per-turn idempotency: each user message must trigger a fresh
            # analyze_brief run, so we key the job_id on the user_msg.id.
            await self._enqueue(
                "analyze_brief", proposal_id, idempotency_key=str(user_msg.id)
            )
            self.status_code = 201
            return [user_msg]

        # non-brief phases: unchanged echo placeholder, returned synchronously
        assistant_msg = await self._echo_response(proposal_id, content, current_phase)
        await self._broadcast_msg(proposal_id, assistant_msg)
        self.status_code = 201
        return [user_msg, assistant_msg]

    async def send_ideation_message(
        self,
        proposal_id: UUID,
        agency_id: UUID,
        content: str,
    ) -> list[ChatMessage] | None:
        """Persist the user message on the ideation channel and enqueue
        run_ideation. Returns just the user message — the assistant reply
        arrives over the WebSocket."""
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        if not proposal or str(proposal.agency_id) != str(agency_id):
            self.error = "Proposal not found"
            self.status_code = 404
            return None

        user_msg = await self.msg_repo.create(
            proposal_id=proposal_id,
            role=MessageRole.USER.value,
            message_type=MessageType.TEXT.value,
            content=content,
            phase="ideation",
            channel="ideation",
        )
        await self._broadcast_msg(proposal_id, user_msg)
        # Channel-scoped typing event — the frontend routes by `channel` and only
        # the IdeationDrawer subscribes to `isIdeationTyping`. The main chat's
        # `isTyping` is unaffected (the leak fixed in 91bb135 stays fixed).
        await ws_manager.broadcast(
            str(proposal_id),
            {"type": "typing", "typing": True, "channel": "ideation"},
        )

        # Per-turn idempotency: each user message is a fresh ideation run.
        await self._enqueue(
            "run_ideation", proposal_id, idempotency_key=str(user_msg.id),
        )
        self.status_code = 201
        return [user_msg]

    async def _handle_template_confirm(
        self,
        proposal,
        proposal_id: UUID,
        content: str,
    ) -> ChatMessage:
        """Auto-suggest a template based on the brief. User confirms or picks another."""
        matcher = TemplateMatcher()
        match = await matcher.match(proposal.brief, self._db)

        if match:
            return await self.msg_repo.create(
                proposal_id=proposal_id,
                role=MessageRole.ASSISTANT.value,
                message_type=MessageType.APPROVAL_GATE.value,
                content=(
                    f"This looks like a **{match.template_name}** project "
                    f"({int(match.confidence * 100)}% match).\n\n"
                    f"Using this template shapes everything:\n"
                    f"- How I research the market\n"
                    f"- How I frame pricing\n"
                    f"- The tone of the covering letter\n"
                    f"- The proposal site theme\n\n"
                    f"Confirm this template, or tell me to use a different one."
                ),
                extra_data={
                    "gate_type": "template",
                    "template_key": match.template_key,
                    "template_name": match.template_name,
                    "confidence": match.confidence,
                    "requires_approval": True,
                },
                phase="template_confirm",
            )
        else:
            return await self.msg_repo.create(
                proposal_id=proposal_id,
                role=MessageRole.ASSISTANT.value,
                message_type=MessageType.TEXT.value,
                content="I couldn't find a strong template match for this project. I'll proceed with default settings. Let me start researching...",
                phase="template_confirm",
            )

    async def approve_gate(
        self,
        proposal_id: UUID,
        agency_id: UUID,
        gate_id: str,
        gate_data: dict | None = None,
    ) -> ChatMessage | None:
        """Validate the gate, update pipeline_state + create an ack message, then
        enqueue the first job for the next phase. The brief gate is synchronous
        (template matching is local and instant); template/cost_model/narrative
        each enqueue a pipeline job and return immediately.
        """
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        if not proposal or str(proposal.agency_id) != str(agency_id):
            self.error = "Proposal not found"
            self.status_code = 404
            return None

        pipeline = proposal.pipeline_state.copy()

        if gate_id == "brief":
            # synchronous — template matching has no LLM call
            pipeline["phases_completed"] = pipeline.get("phases_completed", []) + ["brief"]
            pipeline["current_phase"] = "template_confirm"
            await self.proposal_repo.update(proposal.id, pipeline_state=pipeline)
            msg = await self.msg_repo.create(
                proposal_id=proposal_id, role=MessageRole.ASSISTANT.value,
                message_type=MessageType.TEXT.value,
                content="Brief approved. Let me find the best template for this project...",
                phase="template_confirm",
            )
            await self._broadcast_msg(proposal_id, msg)
            await ws_manager.broadcast(str(proposal_id), {"type": "phase_change", "phase": "template_confirm"})
            template_msg = await self._handle_template_confirm(proposal, proposal_id, "")
            await self._broadcast_msg(proposal_id, template_msg)
            return msg

        gate_map = {
            "template": (
                "research", "run_research",
                "Template confirmed. Starting client research and market benchmarking...",
            ),
            "cost_model": (
                "narrative_generation", "generate_narrative",
                "Cost model approved. Writing the proposal narrative...",
            ),
            "narrative": (
                "output_generation", "generate_outputs",
                "Narrative approved. Generating DOCX, print-ready PDF, and email drafts...",
            ),
        }
        if gate_id not in gate_map:
            self.error = f"Unknown gate: {gate_id}"
            self.status_code = 400
            return None

        next_phase, job_name, ack_text = gate_map[gate_id]

        if gate_id == "template":
            template_key = (gate_data or {}).get("template_key")
            if template_key:
                await self.proposal_repo.update(proposal.id, template_id=template_key)
            pipeline["phases_completed"] = pipeline.get("phases_completed", []) + ["template_confirm"]

            # If rate-card gaps were detected during analyze_brief, pause here.
            # The user must fill / skip / import-Excel before research can start.
            if proposal.rate_card_gaps:
                pipeline["current_phase"] = "rate_card_gaps"
                await self.proposal_repo.update(proposal.id, pipeline_state=pipeline)
                pause_msg = await self.msg_repo.create(
                    proposal_id=proposal_id, role=MessageRole.ASSISTANT.value,
                    message_type=MessageType.TEXT.value,
                    content=(
                        "Template confirmed. Before I cost this proposal I need a few "
                        "rates that aren't in your rate card yet — fill them, drop in a "
                        "rate-card spreadsheet, or skip to use estimated defaults."
                    ),
                    phase="rate_card_gaps",
                )
                await self._broadcast_msg(proposal_id, pause_msg)
                await ws_manager.broadcast(str(proposal_id), {
                    "type": "phase_change", "phase": "rate_card_gaps",
                })
                return pause_msg
        elif gate_id == "cost_model":
            pipeline["phases_completed"] = pipeline.get("phases_completed", []) + ["cost_model_review"]
        elif gate_id == "narrative":
            selected_letter = (gate_data or {}).get("selected_letter", "primary")
            if selected_letter == "alt" and proposal.covering_letter_alt:
                await self.proposal_repo.update(proposal.id, covering_letter=proposal.covering_letter_alt)
            pipeline["phases_completed"] = pipeline.get("phases_completed", []) + ["narrative_review"]

        pipeline["current_phase"] = next_phase
        pipeline["job_status"] = {"phase": job_name, "state": "queued", "error": None}
        await self.proposal_repo.update(proposal.id, pipeline_state=pipeline)

        msg = await self.msg_repo.create(
            proposal_id=proposal_id, role=MessageRole.ASSISTANT.value,
            message_type=MessageType.TEXT.value, content=ack_text, phase=next_phase,
        )
        await self._broadcast_msg(proposal_id, msg)
        await ws_manager.broadcast(str(proposal_id), {"type": "phase_change", "phase": next_phase})
        await self._enqueue(job_name, proposal_id)
        return msg

    async def _broadcast_msg(self, proposal_id: UUID, msg: ChatMessage):
        """Broadcast a chat message via WebSocket."""
        await ws_manager.broadcast(
            str(proposal_id),
            {
                "type": "new_message",
                "message": ChatMessageResponse.model_validate(msg).model_dump(mode="json"),
            },
        )

    async def _echo_response(
        self,
        proposal_id: UUID,
        content: str,
        phase: str,
        override_text: str | None = None,
    ) -> ChatMessage:
        """Fallback echo response when AI is not available."""
        text = override_text or (
            f'Got it. You said: "{content[:100]}{"..." if len(content) > 100 else ""}"\n\n'
            f"AI pipeline for the **{phase}** phase coming soon."
        )
        return await self.msg_repo.create(
            proposal_id=proposal_id,
            role=MessageRole.ASSISTANT.value,
            message_type=MessageType.TEXT.value,
            content=text,
            phase=phase,
        )
