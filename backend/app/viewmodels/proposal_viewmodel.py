from __future__ import annotations

from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.schemas.proposal_schemas import PREF_PHASE_MAP, PreferencesUpdate, ProposalCreate, ProposalListItem, ProposalUpdate
from app.infrastructure.db.models.proposal import Proposal, ProposalStatus
from app.infrastructure.db.repositories.client_repo import ClientRepository
from app.infrastructure.db.repositories.proposal_repo import ProposalRepository
from app.viewmodels.shared.viewmodel import ViewModelBase


class ProposalViewModel(ViewModelBase):
    def __init__(self, request: Request, db: AsyncSession):
        super().__init__(request, db)
        self._repo: ProposalRepository | None = None

    @property
    def repo(self) -> ProposalRepository:
        if not self._repo:
            self._repo = ProposalRepository(self._db)
        return self._repo

    async def create_proposal(self, agency_id: UUID, data: ProposalCreate) -> Proposal | None:
        client_repo = ClientRepository(self._db)
        client = await client_repo.get_by_id(data.client_id)
        if not client or str(client.agency_id) != str(agency_id):
            self.error = "Client not found"
            self.status_code = 404
            return None

        # Auto-apply context-aware preference overrides
        initial_prefs: dict = {}
        context_overrides: list[dict] = []
        if client.context_profile:
            from app.services.context_intelligence import generate_preference_overrides
            overrides = generate_preference_overrides(client.context_profile)
            for o in overrides:
                if o.key not in ("scope_note", "generate_one_pager", "negotiation_buffer"):
                    initial_prefs[o.key] = o.value
                context_overrides.append({"key": o.key, "value": o.value, "reason": o.reason})

        proposal = await self.repo.create(
            agency_id=agency_id,
            client_id=data.client_id,
            project_name=data.project_name,
            status=ProposalStatus.DRAFT.value,
            preferences=initial_prefs,
            pipeline_state={
                "current_phase": "brief",
                "phases_completed": [],
                "context_overrides": context_overrides,
                "context": {},
            },
        )
        self.status_code = 201
        return proposal

    async def list_proposals(
        self,
        agency_id: UUID,
        status: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ProposalListItem]:
        rows = await self.repo.list_by_agency(agency_id, status, skip, limit)
        return [
            ProposalListItem(
                id=p.id,
                client_id=p.client_id,
                client_name=name,
                project_name=p.project_name,
                status=p.status,
                pipeline_state=p.pipeline_state,
                created_at=p.created_at,
                updated_at=p.updated_at,
            )
            for p, name in rows
        ]

    async def get_proposal(self, proposal_id: UUID, agency_id: UUID) -> Proposal | None:
        proposal = await self.repo.get_by_id(proposal_id)
        if not proposal or str(proposal.agency_id) != str(agency_id):
            self.error = "Proposal not found"
            self.status_code = 404
            return None
        return proposal

    async def update_proposal(self, proposal_id: UUID, agency_id: UUID, data: ProposalUpdate) -> Proposal | None:
        proposal = await self.get_proposal(proposal_id, agency_id)
        if not proposal:
            return None
        update_data = data.model_dump(exclude_unset=True)
        return await self.repo.update(proposal_id, **update_data)

    async def delete_proposal(self, proposal_id: UUID, agency_id: UUID) -> bool:
        proposal = await self.get_proposal(proposal_id, agency_id)
        if not proposal:
            return False
        return await self.repo.delete(proposal_id)

    async def update_preferences(self, proposal_id: UUID, agency_id: UUID, data: PreferencesUpdate) -> Proposal | None:
        proposal = await self.get_proposal(proposal_id, agency_id)
        if not proposal:
            return None

        # Merge new prefs into existing
        current_prefs = proposal.preferences.copy() if proposal.preferences else {}
        new_prefs = data.model_dump(exclude_unset=True)
        current_prefs.update(new_prefs)

        # Track staleness — which completed phases are affected
        pipeline = proposal.pipeline_state.copy() if proposal.pipeline_state else {}
        completed = pipeline.get("phases_completed", [])
        stale = set(pipeline.get("stale_phases", []))

        for pref_key in new_prefs:
            affected_phase = PREF_PHASE_MAP.get(pref_key)
            if affected_phase and affected_phase in completed:
                stale.add(affected_phase)

        pipeline["stale_phases"] = sorted(stale)

        return await self.repo.update(
            proposal_id,
            preferences=current_prefs,
            pipeline_state=pipeline,
        )
