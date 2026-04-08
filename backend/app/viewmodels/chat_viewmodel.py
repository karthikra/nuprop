from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.ws_manager import ws_manager
from app.domain.schemas.chat_schemas import ChatMessageResponse
from app.infrastructure.db.models.chat_message import ChatMessage, MessageRole, MessageType
from app.infrastructure.db.repositories.chat_message_repo import ChatMessageRepository
from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from app.infrastructure.external.anthropic_client import AnthropicClient
from app.services.ai.benchmark_agent import BenchmarkAgent
from app.services.ai.brief_analyzer import BriefAnalyzer
from app.services.ai.cost_model_builder import CostModelBuilder
from app.services.ai.narrative_generator import NarrativeGenerator
from app.services.ai.research_agent import ResearchAgent
from app.services.ai.template_matcher import TemplateMatcher
from app.viewmodels.shared.viewmodel import ViewModelBase


class ChatViewModel(ViewModelBase):
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
        return await self.msg_repo.list_by_proposal(proposal_id, skip, limit)

    async def send_message(
        self,
        proposal_id: UUID,
        agency_id: UUID,
        content: str,
    ) -> tuple[ChatMessage, ChatMessage] | None:
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        if not proposal or str(proposal.agency_id) != str(agency_id):
            self.error = "Proposal not found"
            self.status_code = 404
            return None

        current_phase = proposal.pipeline_state.get("current_phase", "brief")

        # Persist user message
        user_msg = await self.msg_repo.create(
            proposal_id=proposal_id,
            role=MessageRole.USER.value,
            message_type=MessageType.TEXT.value,
            content=content,
            phase=current_phase,
        )

        # Broadcast user message via WS
        await ws_manager.broadcast(
            str(proposal_id),
            {
                "type": "new_message",
                "message": ChatMessageResponse.model_validate(user_msg).model_dump(mode="json"),
            },
        )

        # Send typing indicator
        await ws_manager.broadcast(str(proposal_id), {"type": "typing", "typing": True})

        # Route to the appropriate AI handler based on phase
        if current_phase == "brief":
            assistant_msg = await self._handle_brief_phase(proposal, proposal_id)
        elif current_phase == "template_confirm":
            assistant_msg = await self._handle_template_confirm(proposal, proposal_id, content)
        else:
            assistant_msg = await self._echo_response(proposal_id, content, current_phase)

        # Clear typing indicator
        await ws_manager.broadcast(str(proposal_id), {"type": "typing", "typing": False})

        # Broadcast assistant message via WS
        await ws_manager.broadcast(
            str(proposal_id),
            {
                "type": "new_message",
                "message": ChatMessageResponse.model_validate(assistant_msg).model_dump(mode="json"),
            },
        )

        self.status_code = 201
        return (user_msg, assistant_msg)

    async def _handle_brief_phase(
        self,
        proposal,
        proposal_id: UUID,
    ) -> ChatMessage:
        """Use BriefAnalyzer to process the brief intake conversation."""
        anthropic = AnthropicClient()

        if not anthropic.is_configured:
            return await self._echo_response(
                proposal_id,
                "API key not configured",
                "brief",
                "Set ANTHROPIC_API_KEY in .env to enable AI. Using echo mode.",
            )

        # Build chat history from DB
        all_messages = await self.msg_repo.list_by_proposal(proposal_id)
        chat_history = [
            {"role": msg.role, "content": msg.content}
            for msg in all_messages
            if msg.role in (MessageRole.USER.value, MessageRole.ASSISTANT.value)
            and msg.message_type == MessageType.TEXT.value
        ]

        analyzer = BriefAnalyzer()
        result = await analyzer.analyze(
            chat_history=chat_history,
            current_brief=proposal.brief,
        )

        # Determine message type
        msg_type = MessageType.TEXT.value
        extra_data: dict = {}

        if result.brief_complete:
            msg_type = MessageType.BRIEF_SUMMARY.value
            extra_data = {"brief": result.brief_data, "requires_approval": True}

            # Update proposal brief (but don't advance phase yet — wait for approval)
            await self.proposal_repo.update(
                proposal.id,
                brief=result.brief_data,
            )

        # Persist assistant message
        assistant_msg = await self.msg_repo.create(
            proposal_id=proposal_id,
            role=MessageRole.ASSISTANT.value,
            message_type=msg_type,
            content=result.response_text,
            extra_data=extra_data,
            phase="brief",
        )

        return assistant_msg

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

    async def _run_research_and_benchmarks(
        self,
        proposal,
        proposal_id: UUID,
        template_config: dict | None = None,
    ) -> ChatMessage:
        """Run research + benchmarks and return a summary message."""
        brief = proposal.brief
        client_name = brief.get("client", {}).get("name", "the client")
        industry = brief.get("client", {}).get("industry")
        deliverables = brief.get("project", {}).get("deliverables", [])

        # Progress: research starting
        await self._broadcast_progress(proposal_id, "research", "searching", f"Researching {client_name}...")

        # Research
        research_queries = None
        if template_config:
            research_queries = template_config.get("research", {}).get("client_queries")

        agent = ResearchAgent()
        research_md = await agent.research_client(client_name, industry, research_queries)
        await self.proposal_repo.update(proposal.id, research=research_md)

        await self._broadcast_progress(proposal_id, "research", "complete", "Client research done")

        # Progress: benchmarks starting
        await self._broadcast_progress(proposal_id, "benchmarks", "searching", "Finding pricing benchmarks...")

        benchmark_queries = None
        if template_config:
            benchmark_queries = template_config.get("research", {}).get("benchmark_queries")

        bench_agent = BenchmarkAgent()
        benchmarks_md = await bench_agent.find_benchmarks(deliverables, "India", benchmark_queries)
        await self.proposal_repo.update(proposal.id, benchmarks=benchmarks_md)

        await self._broadcast_progress(proposal_id, "benchmarks", "complete", "Pricing benchmarks done")

        # Create a combined findings message
        summary = (
            f"**Research and benchmarking complete.**\n\n"
            f"---\n\n"
            f"{research_md}\n\n"
            f"---\n\n"
            f"{benchmarks_md}"
        )

        msg = await self.msg_repo.create(
            proposal_id=proposal_id,
            role=MessageRole.ASSISTANT.value,
            message_type=MessageType.RESEARCH_FINDINGS.value,
            content=summary,
            extra_data={"has_research": True, "has_benchmarks": True},
            phase="research",
        )

        # Advance to cost model phase
        pipeline = proposal.pipeline_state.copy()
        pipeline["phases_completed"] = pipeline.get("phases_completed", []) + ["research"]
        pipeline["current_phase"] = "cost_model_review"
        await self.proposal_repo.update(proposal.id, pipeline_state=pipeline)

        await ws_manager.broadcast(str(proposal_id), {"type": "phase_change", "phase": "cost_model_review"})

        # Auto-trigger cost model building
        await self._broadcast_progress(proposal_id, "cost_model", "searching", "Building cost model from rate card...")
        cost_msg = await self._build_cost_model(proposal, proposal_id, template_config)
        await self._broadcast_progress(proposal_id, "cost_model", "complete", "Cost model ready for review")
        await self._broadcast_msg(proposal_id, cost_msg)

        return msg

    async def _broadcast_progress(self, proposal_id: UUID, agent: str, status: str, detail: str):
        """Send a progress update via WebSocket."""
        await ws_manager.broadcast(
            str(proposal_id),
            {
                "type": "progress",
                "agent": agent,
                "status": status,
                "detail": detail,
            },
        )

    async def _build_cost_model(
        self,
        proposal,
        proposal_id: UUID,
        template_config: dict | None = None,
    ) -> ChatMessage:
        """Build cost model from brief + rate card and present as approval gate."""
        builder = CostModelBuilder()
        model = await builder.build(
            brief=proposal.brief,
            db=self._db,
            agency_id=str(proposal.agency_id),
            benchmarks_md=proposal.benchmarks,
            template_config=template_config,
        )

        cost_dict = CostModelBuilder.model_to_dict(model)
        await self.proposal_repo.update(proposal.id, cost_model=cost_dict)

        # Format a human-readable summary
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

        return await self.msg_repo.create(
            proposal_id=proposal_id,
            role=MessageRole.ASSISTANT.value,
            message_type=MessageType.COST_MODEL.value,
            content=content,
            extra_data={
                "cost_model": cost_dict,
                "requires_approval": True,
                "gate_type": "cost_model",
            },
            phase="cost_model_review",
        )

    async def _generate_narrative(self, proposal, proposal_id: UUID) -> ChatMessage:
        """Generate all narrative sections and return a narrative_preview message."""
        from sqlalchemy import select as sa_select
        from app.infrastructure.db.models.agency import Agency
        from app.infrastructure.db.models.template import StrategyTemplate
        from app.infrastructure.db.models.rate_card import RateCard

        # Load agency
        result = await self._db.execute(sa_select(Agency).where(Agency.id == str(proposal.agency_id)))
        agency = result.scalar_one_or_none()

        # Load template config
        template_config = None
        if proposal.template_id:
            result = await self._db.execute(
                sa_select(StrategyTemplate).where(StrategyTemplate.template_key == proposal.template_id)
            )
            tmpl = result.scalar_one_or_none()
            if tmpl:
                template_config = tmpl.config if isinstance(tmpl.config, dict) else None

        # Load rate card
        result = await self._db.execute(
            sa_select(RateCard).where(RateCard.agency_id == str(proposal.agency_id), RateCard.is_active == True).limit(1)
        )
        rate_card = result.scalar_one_or_none()

        generator = NarrativeGenerator()

        # Merge user preferences on top of template config
        effective_config = self._merge_preferences_into_config(template_config, proposal.preferences or {})

        await self._broadcast_progress(proposal_id, "narrative", "searching", "Writing covering letter (2 variants)...")

        narr = await generator.generate_all(
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

        # Save all sections to proposal
        await self.proposal_repo.update(
            proposal.id,
            covering_letter=narr.covering_letter,
            covering_letter_alt=narr.covering_letter_alt,
            executive_summary=narr.executive_summary,
            scope_sections=narr.scope_sections,
            cost_rationale=narr.cost_rationale,
            terms=narr.terms,
        )

        # Advance to narrative_review
        pipeline = proposal.pipeline_state.copy()
        pipeline["phases_completed"] = pipeline.get("phases_completed", []) + ["narrative_generation"]
        pipeline["current_phase"] = "narrative_review"
        await self.proposal_repo.update(proposal.id, pipeline_state=pipeline)

        await self._broadcast_progress(proposal_id, "narrative", "complete", "Narrative ready for review")
        await ws_manager.broadcast(str(proposal_id), {"type": "phase_change", "phase": "narrative_review"})

        scope_count = len(narr.scope_sections)
        content = (
            f"**Proposal narrative ready for review.**\n\n"
            f"I've written two covering letter variants ({narr.letter_strategy_primary} and {narr.letter_strategy_alt}), "
            f"the executive summary, {scope_count} scope descriptions"
            f"{', cost rationale,' if narr.cost_rationale else ''} and terms & conditions.\n\n"
            f"Review each section below and approve when ready."
        )

        return await self.msg_repo.create(
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

    async def _generate_outputs(self, proposal, proposal_id: UUID) -> ChatMessage:
        """Generate DOCX, print-ready HTML, and email drafts."""
        from app.infrastructure.db.models.agency import Agency
        from sqlalchemy import select as sa_select

        result = await self._db.execute(sa_select(Agency).where(Agency.id == str(proposal.agency_id)))
        agency = result.scalar_one_or_none()

        # Get the latest narrative content from the last narrative_preview message
        narr_msgs = [
            m for m in await self.msg_repo.list_by_proposal(proposal_id)
            if m.message_type == MessageType.NARRATIVE_PREVIEW.value
        ]

        # Build proposal data dict from the narrative message's extra_data
        prop_data = {
            "project_name": proposal.project_name,
            "brief": proposal.brief,
            "cost_model": proposal.cost_model or {},
            "covering_letter": proposal.covering_letter,
            "covering_letter_alt": proposal.covering_letter_alt,
            "executive_summary": proposal.executive_summary,
            "scope_sections": proposal.scope_sections or [],
            "cost_rationale": proposal.cost_rationale,
            "terms": proposal.terms,
        }

        # If proposal fields are empty, pull from narrative message extra_data
        if narr_msgs and not prop_data["covering_letter"]:
            sections = narr_msgs[-1].extra_data.get("sections", {})
            prop_data["covering_letter"] = sections.get("covering_letter", "")
            prop_data["covering_letter_alt"] = sections.get("covering_letter_alt", "")
            prop_data["executive_summary"] = sections.get("executive_summary", "")
            prop_data["scope_sections"] = sections.get("scope_sections", [])
            prop_data["cost_rationale"] = sections.get("cost_rationale")
            prop_data["terms"] = sections.get("terms", "")

        from app.services.document_generator import DocumentGenerator

        await self._broadcast_progress(proposal_id, "documents", "searching", "Generating DOCX...")
        gen = DocumentGenerator()
        outputs = gen.generate_all(
            proposal=prop_data,
            agency_name=agency.name if agency else "Agency",
            agency_colours=agency.colours if agency else None,
        )

        # Save files locally (R2 in production)
        settings = get_settings()
        output_dir = Path(settings.LOCAL_STORAGE_PATH if hasattr(settings, 'LOCAL_STORAGE_PATH') else "outputs")
        output_dir = Path("outputs") / str(proposal_id)
        output_dir.mkdir(parents=True, exist_ok=True)

        files_generated = []

        if outputs.docx_bytes:
            docx_path = output_dir / "proposal.docx"
            docx_path.write_bytes(outputs.docx_bytes)
            await self.proposal_repo.update(proposal.id, docx_path=str(docx_path))
            files_generated.append({"type": "docx", "filename": "proposal.docx", "size": len(outputs.docx_bytes)})

        if outputs.pdf_bytes:
            pdf_path = output_dir / "proposal.pdf"
            pdf_path.write_bytes(outputs.pdf_bytes)
            await self.proposal_repo.update(proposal.id, pdf_path=str(pdf_path))
            files_generated.append({"type": "pdf", "filename": "proposal.pdf", "size": len(outputs.pdf_bytes)})

        if outputs.pdf_html:
            html_path = output_dir / "proposal-print.html"
            html_path.write_text(outputs.pdf_html, encoding="utf-8")
            files_generated.append({"type": "html", "filename": "proposal-print.html", "size": len(outputs.pdf_html)})

        if outputs.email_confident:
            email_path = output_dir / "email-drafts.md"
            email_content = f"# Email Draft — Confident\n\n{outputs.email_confident}\n\n---\n\n# Email Draft — Warm\n\n{outputs.email_warm}"
            email_path.write_text(email_content, encoding="utf-8")
            files_generated.append({"type": "email", "filename": "email-drafts.md"})

        await self._broadcast_progress(proposal_id, "documents", "complete", "Documents ready")

        # Generate interactive proposal site
        await self._broadcast_progress(proposal_id, "site", "searching", "Generating interactive proposal site...")
        try:
            from sqlalchemy import select as sa_select
            from app.services.site_generator import SiteGenerator

            # Determine theme from template config
            site_theme = "editorial"
            if proposal.template_id:
                from app.infrastructure.db.models.template import StrategyTemplate
                tmpl_result = await self._db.execute(
                    sa_select(StrategyTemplate).where(StrategyTemplate.template_key == proposal.template_id)
                )
                tmpl = tmpl_result.scalar_one_or_none()
                if tmpl and isinstance(tmpl.config, dict):
                    site_theme = tmpl.config.get("output", {}).get("site_theme", "editorial")

            site_gen = SiteGenerator()
            agency_dict = {
                "name": agency.name if agency else "Agency",
                "logo_url": agency.logo_url if agency else None,
                "colours": agency.colours if agency else {},
                "fonts": agency.fonts if agency else {},
                "email": "",
            }

            site_html = site_gen.generate(
                proposal_data=prop_data,
                agency=agency_dict,
                theme=site_theme,
                proposal_id=str(proposal_id),
                tracking_endpoint="/api/v1/track",
            )

            site_dir = output_dir / "site"
            site_dir.mkdir(parents=True, exist_ok=True)
            (site_dir / "index.html").write_text(site_html, encoding="utf-8")

            settings = get_settings()
            site_url = f"/p/{proposal_id}"
            await self.proposal_repo.update(proposal.id, site_url=site_url)

            files_generated.append({
                "type": "site",
                "filename": "site/index.html",
                "url": site_url,
                "theme": site_theme,
            })
            await self._broadcast_progress(proposal_id, "site", "complete", f"Proposal site ready ({site_theme} theme)")
        except Exception as e:
            await self._broadcast_progress(proposal_id, "site", "error", f"Site generation failed: {str(e)[:100]}")

        # Advance to complete
        pipeline = proposal.pipeline_state.copy()
        pipeline["phases_completed"] = pipeline.get("phases_completed", []) + ["output_generation"]
        pipeline["current_phase"] = "complete"
        await self.proposal_repo.update(proposal.id, pipeline_state=pipeline, status="review")

        await ws_manager.broadcast(str(proposal_id), {"type": "phase_change", "phase": "complete"})

        # Format content
        file_list = "\n".join(f"- **{f['type'].upper()}**: {f['filename']}" for f in files_generated)
        content = (
            f"**All outputs generated.**\n\n"
            f"{file_list}\n\n"
            f"Download your files below. The proposal is ready to send."
        )

        return await self.msg_repo.create(
            proposal_id=proposal_id,
            role=MessageRole.ASSISTANT.value,
            message_type=MessageType.OUTPUT_READY.value,
            content=content,
            extra_data={
                "files": files_generated,
                "email_confident": outputs.email_confident,
                "email_warm": outputs.email_warm,
            },
            phase="complete",
        )

    async def approve_gate(
        self,
        proposal_id: UUID,
        agency_id: UUID,
        gate_id: str,
        gate_data: dict | None = None,
    ) -> ChatMessage | None:
        """Handle approval of a pipeline gate."""
        proposal = await self.proposal_repo.get_by_id(proposal_id)
        if not proposal or str(proposal.agency_id) != str(agency_id):
            self.error = "Proposal not found"
            self.status_code = 404
            return None

        pipeline = proposal.pipeline_state.copy()

        if gate_id == "brief":
            pipeline["phases_completed"] = pipeline.get("phases_completed", []) + ["brief"]
            pipeline["current_phase"] = "template_confirm"
            await self.proposal_repo.update(proposal.id, pipeline_state=pipeline)

            msg = await self.msg_repo.create(
                proposal_id=proposal_id,
                role=MessageRole.ASSISTANT.value,
                message_type=MessageType.TEXT.value,
                content="Brief approved. Let me find the best template for this project...",
                phase="template_confirm",
            )
            await self._broadcast_msg(proposal_id, msg)
            await ws_manager.broadcast(str(proposal_id), {"type": "phase_change", "phase": "template_confirm"})

            # Auto-trigger template suggestion
            await ws_manager.broadcast(str(proposal_id), {"type": "typing", "typing": True})
            template_msg = await self._handle_template_confirm(proposal, proposal_id, "")
            await ws_manager.broadcast(str(proposal_id), {"type": "typing", "typing": False})
            await self._broadcast_msg(proposal_id, template_msg)

            return msg

        elif gate_id == "template":
            # Template confirmed — save template_id and start research
            template_key = (gate_data or {}).get("template_key")
            pipeline["phases_completed"] = pipeline.get("phases_completed", []) + ["template_confirm"]
            pipeline["current_phase"] = "research"
            update_kwargs = {"pipeline_state": pipeline}
            if template_key:
                update_kwargs["template_id"] = template_key
            await self.proposal_repo.update(proposal.id, **update_kwargs)

            # Get template config if one was selected
            template_config = None
            # Refresh proposal to get latest state
            proposal = await self.proposal_repo.get_by_id(proposal_id)
            if proposal.template_id:
                from sqlalchemy import select as sa_select
                from app.infrastructure.db.models.template import StrategyTemplate
                result = await self._db.execute(
                    sa_select(StrategyTemplate).where(StrategyTemplate.template_key == proposal.template_id)
                )
                tmpl = result.scalar_one_or_none()
                if tmpl:
                    template_config = tmpl.config if isinstance(tmpl.config, dict) else None

            msg = await self.msg_repo.create(
                proposal_id=proposal_id,
                role=MessageRole.ASSISTANT.value,
                message_type=MessageType.TEXT.value,
                content="Template confirmed. Starting client research and market benchmarking — this takes about 30-60 seconds...",
                phase="research",
            )
            await self._broadcast_msg(proposal_id, msg)
            await ws_manager.broadcast(str(proposal_id), {"type": "phase_change", "phase": "research"})
            await ws_manager.broadcast(str(proposal_id), {"type": "typing", "typing": True})

            # Run research + benchmarks (synchronous for now)
            research_msg = await self._run_research_and_benchmarks(proposal, proposal_id, template_config)
            await ws_manager.broadcast(str(proposal_id), {"type": "typing", "typing": False})
            await self._broadcast_msg(proposal_id, research_msg)

            return msg

        elif gate_id == "cost_model":
            pipeline["phases_completed"] = pipeline.get("phases_completed", []) + ["cost_model_review"]
            pipeline["current_phase"] = "narrative_generation"
            await self.proposal_repo.update(proposal.id, pipeline_state=pipeline)

            msg = await self.msg_repo.create(
                proposal_id=proposal_id,
                role=MessageRole.ASSISTANT.value,
                message_type=MessageType.TEXT.value,
                content="Cost model approved. Writing the proposal narrative — covering letter, executive summary, scope descriptions, and cost rationale...",
                phase="narrative_generation",
            )
            await self._broadcast_msg(proposal_id, msg)
            await ws_manager.broadcast(str(proposal_id), {"type": "phase_change", "phase": "narrative_generation"})
            await ws_manager.broadcast(str(proposal_id), {"type": "typing", "typing": True})

            narrative_msg = await self._generate_narrative(proposal, proposal_id)
            await ws_manager.broadcast(str(proposal_id), {"type": "typing", "typing": False})
            await self._broadcast_msg(proposal_id, narrative_msg)

            return msg

        elif gate_id == "narrative":
            selected_letter = (gate_data or {}).get("selected_letter", "primary")

            proposal = await self.proposal_repo.get_by_id(proposal_id)
            if selected_letter == "alt" and proposal.covering_letter_alt:
                await self.proposal_repo.update(
                    proposal.id,
                    covering_letter=proposal.covering_letter_alt,
                )

            pipeline["phases_completed"] = pipeline.get("phases_completed", []) + ["narrative_review"]
            pipeline["current_phase"] = "output_generation"
            await self.proposal_repo.update(proposal.id, pipeline_state=pipeline)

            msg = await self.msg_repo.create(
                proposal_id=proposal_id,
                role=MessageRole.ASSISTANT.value,
                message_type=MessageType.TEXT.value,
                content="Narrative approved. Generating DOCX, print-ready PDF, and email drafts...",
                phase="output_generation",
            )
            await self._broadcast_msg(proposal_id, msg)
            await ws_manager.broadcast(str(proposal_id), {"type": "phase_change", "phase": "output_generation"})
            await ws_manager.broadcast(str(proposal_id), {"type": "typing", "typing": True})

            output_msg = await self._generate_outputs(proposal, proposal_id)
            await ws_manager.broadcast(str(proposal_id), {"type": "typing", "typing": False})
            await self._broadcast_msg(proposal_id, output_msg)

            return msg

        self.error = f"Unknown gate: {gate_id}"
        self.status_code = 400
        return None

    async def _broadcast_msg(self, proposal_id: UUID, msg: ChatMessage):
        """Broadcast a chat message via WebSocket."""
        await ws_manager.broadcast(
            str(proposal_id),
            {
                "type": "new_message",
                "message": ChatMessageResponse.model_validate(msg).model_dump(mode="json"),
            },
        )

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
