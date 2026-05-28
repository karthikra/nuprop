from __future__ import annotations

from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ws_manager import ws_manager
from app.domain.schemas.chat_schemas import ChatMessageResponse
from app.infrastructure.db.models.chat_message import ChatMessage, MessageRole, MessageType
from app.infrastructure.db.repositories.chat_message_repo import ChatMessageRepository
from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from app.infrastructure.queue.enqueue import enqueue_phase_job
from app.services.ai.chat_intent import PHASE_TO_JOB, classify_intent
from app.services.ai.template_matcher import TemplateMatcher
from app.services.cost_model_service import (
    CostItemEditError,
    apply_cost_item_edit,
    find_line_item_index,
)
from app.services.llm import Tier, get_ai_service
from app.services.sections import SECTION_ORDER
from app.services.sections.regeneration import regenerate_section_content
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
        """Thin wrapper around the shared :func:`enqueue_phase_job` helper.

        See ``app.infrastructure.queue.enqueue`` for the full rationale on why
        the result-key DEL is needed before every enqueue.
        """
        await enqueue_phase_job(
            self._request.app.state.arq_pool,
            job_name=job_name,
            proposal_id=str(proposal_id),
            idempotency_key=idempotency_key,
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

        # Non-brief phases: classify the message (Path B) and route it.
        await ws_manager.broadcast(str(proposal_id), {"type": "typing", "typing": True})
        intent = await classify_intent(
            user_message=content,
            current_phase=current_phase,
            proposal_state_hint=self._intent_hint(proposal),
        )
        assistant_msg = await self._dispatch_intent(proposal, intent, current_phase)
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
                "sections", "generate_sections",
                "Cost model approved. Drafting the proposal sections...",
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

    # ── Path B: intent dispatch ───────────────────────────────────────────────
    def _intent_hint(self, proposal) -> dict:
        cost = proposal.cost_model or {}
        items = cost.get("line_items") or []
        return {
            "section_types": list(SECTION_ORDER),
            "cost_items": [
                str(i.get("deliverable", "")) for i in items if i.get("deliverable")
            ],
        }

    async def _ack(self, proposal_id, text: str, phase: str) -> ChatMessage:
        return await self._echo_response(proposal_id, "", phase, override_text=text)

    async def _dispatch_intent(self, proposal, intent, current_phase) -> ChatMessage:
        kind = intent.get("kind", "unknown")
        proposal_id = proposal.id

        if kind == "re_run_phase":
            job = PHASE_TO_JOB[intent["phase"]]
            pipeline = await self._set_job_queued(proposal, job)
            await self.proposal_repo.update(proposal_id, pipeline_state=pipeline)
            await self._db.commit()  # commit before enqueue so the worker sees queued state
            await self._enqueue(job, proposal_id)
            label = intent["phase"].replace("_", " ")
            return await self._ack(proposal_id, f"Re-running {label}…", current_phase)

        if kind in ("regenerate_section", "refine_section"):
            section_type = intent["section_type"]
            instructions = intent.get("instructions") if kind == "refine_section" else None
            new_payload = await regenerate_section_content(
                proposal, section_type, instructions, self._db,
            )
            current = getattr(proposal, section_type, None) or {}
            new_payload["assets"] = current.get("assets", [])
            await self.proposal_repo.update(proposal_id, **{section_type: new_payload})
            await self._db.commit()
            label = section_type.replace("_", " ")
            verb = "Refining" if kind == "refine_section" else "Regenerating"
            return await self._ack(proposal_id, f"{verb} {label}…", current_phase)

        if kind == "edit_cost_item":
            cost = proposal.cost_model or {}
            idx = find_line_item_index(cost, intent["deliverable"])
            if idx is None:
                return await self._ack(
                    proposal_id,
                    f'I couldn\'t find a cost item called "{intent["deliverable"]}".',
                    current_phase,
                )
            try:
                updated = apply_cost_item_edit(
                    cost, index=idx, field=intent["field"], value=intent["value"],
                )
            except CostItemEditError:
                return await self._ack(
                    proposal_id, "I couldn't apply that cost-model edit.", current_phase,
                )
            await self.proposal_repo.update(proposal_id, cost_model=updated)
            await self._db.commit()
            await ws_manager.broadcast(
                str(proposal_id), {"type": "cost_model_update", "cost_model": updated},
            )
            label = intent["field"].replace("_", " ")
            return await self._ack(
                proposal_id, f"Updated {label} for {intent['deliverable']}.", current_phase,
            )

        if kind == "ask_question":
            answer = await self._answer_question(proposal, intent["question"])
            return await self._ack(proposal_id, answer, current_phase)

        # unknown
        return await self._echo_response(
            proposal_id, "", current_phase,
            override_text=(
                "I can re-run a phase (research, benchmarks, cost model, sections), "
                "regenerate or refine a section, edit a cost item, or answer questions "
                'about your proposal. Try: "redo research" or '
                '"regenerate the problem statement".'
            ),
        )

    async def _answer_question(self, proposal, question: str) -> str:
        context = (
            f"Project: {proposal.project_name}\n"
            f"Brief: {proposal.brief or {}}\n"
            f"Cost model: {proposal.cost_model or {}}\n"
        )
        result = await get_ai_service().complete(
            f"Answer the user's question about this proposal concisely.\n\n"
            f"{context}\nQuestion: {question}",
            tier=Tier.BALANCED,
            system=(
                "You are a helpful proposal assistant. Answer in 1-3 sentences "
                "using only the provided context."
            ),
            max_tokens=400,
        )
        return result.text
