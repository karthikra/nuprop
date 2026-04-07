from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel

from app.core.deps import get_current_agency_id
from app.core.security import decode_access_token
from app.core.ws_manager import ws_manager
from app.domain.schemas.chat_schemas import ChatMessageResponse, SendMessageRequest
from app.infrastructure.db.database import async_session_factory, get_db
from app.infrastructure.db.models.proposal import Proposal
from app.infrastructure.db.models.user import User
from app.viewmodels.chat_viewmodel import ChatViewModel

router = APIRouter(prefix="/chat", tags=["chat"])


def get_vm(request: Request, db: AsyncSession = Depends(get_db)) -> ChatViewModel:
    return ChatViewModel(request, db)


@router.get("/{proposal_id}/messages", response_model=list[ChatMessageResponse])
async def get_messages(
    proposal_id: UUID,
    skip: int = 0,
    limit: int = 200,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ChatViewModel = Depends(get_vm),
):
    messages = await vm.get_messages(proposal_id, agency_id, skip, limit)
    if messages is None:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return messages


@router.post("/{proposal_id}/send", response_model=list[ChatMessageResponse], status_code=status.HTTP_201_CREATED)
async def send_message(
    proposal_id: UUID,
    body: SendMessageRequest,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ChatViewModel = Depends(get_vm),
):
    result = await vm.send_message(proposal_id, agency_id, body.content)
    if not result:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)

    user_msg, assistant_msg = result
    # WS broadcasting is handled inside the ViewModel
    return [
        ChatMessageResponse.model_validate(user_msg),
        ChatMessageResponse.model_validate(assistant_msg),
    ]


class ApproveGateRequest(BaseModel):
    data: dict = {}


@router.post("/{proposal_id}/approve/{gate_id}", response_model=ChatMessageResponse)
async def approve_gate(
    proposal_id: UUID,
    gate_id: str,
    body: ApproveGateRequest | None = None,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ChatViewModel = Depends(get_vm),
):
    gate_data = body.data if body else {}
    msg = await vm.approve_gate(proposal_id, agency_id, gate_id, gate_data)
    if not msg:
        raise HTTPException(status_code=vm.status_code, detail=vm.error)
    return ChatMessageResponse.model_validate(msg)


class UpdateCostItemRequest(BaseModel):
    index: int
    field: str  # "quantity" | "unit_cost"
    value: int


@router.patch("/{proposal_id}/cost-model", response_model=dict)
async def update_cost_model_item(
    proposal_id: UUID,
    body: UpdateCostItemRequest,
    agency_id: UUID = Depends(get_current_agency_id),
    vm: ChatViewModel = Depends(get_vm),
):
    """Update a single line item in the cost model."""
    proposal = await vm.proposal_repo.get_by_id(proposal_id)
    if not proposal or str(proposal.agency_id) != str(agency_id):
        raise HTTPException(status_code=404, detail="Proposal not found")

    cost_model = proposal.cost_model
    if not cost_model or "line_items" not in cost_model:
        raise HTTPException(status_code=400, detail="No cost model to update")

    items = cost_model["line_items"]
    if body.index < 0 or body.index >= len(items):
        raise HTTPException(status_code=400, detail="Invalid line item index")

    item = items[body.index]
    if body.field == "quantity":
        item["quantity"] = body.value
        item["total"] = item["unit_cost"] * body.value
    elif body.field == "unit_cost":
        item["unit_cost"] = body.value
        item["total"] = body.value * item["quantity"]
    else:
        raise HTTPException(status_code=400, detail=f"Invalid field: {body.field}")

    # Recalculate totals
    subtotal = sum(i["total"] for i in items)
    discount_pct = cost_model.get("discount_percent", 0)
    discount_amt = int(subtotal * discount_pct / 100)
    total = subtotal - discount_amt
    gst = int(total * 0.18)

    cost_model["subtotal"] = subtotal
    cost_model["discount_amount"] = discount_amt
    cost_model["total"] = total
    cost_model["gst_amount"] = gst
    cost_model["grand_total"] = total + gst

    await vm.proposal_repo.update(proposal_id, cost_model=cost_model)

    # Broadcast updated cost model via WS
    await ws_manager.broadcast(str(proposal_id), {
        "type": "cost_model_update",
        "cost_model": cost_model,
    })

    return cost_model


@router.websocket("/{proposal_id}/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    proposal_id: str,
    token: str = Query(...),
):
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        await websocket.close(code=4001, reason="Invalid token")
        return

    async with async_session_factory() as db:
        user_id = payload["sub"]
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            await websocket.close(code=4001, reason="User not found")
            return

        result = await db.execute(
            select(Proposal).where(
                Proposal.id == proposal_id,
                Proposal.agency_id == str(user.agency_id),
            )
        )
        proposal = result.scalar_one_or_none()
        if not proposal:
            await websocket.close(code=4004, reason="Proposal not found")
            return

    await ws_manager.connect(proposal_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        ws_manager.disconnect(proposal_id, websocket)
