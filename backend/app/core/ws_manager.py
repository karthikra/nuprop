from __future__ import annotations

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, proposal_id: str, websocket: WebSocket):
        await websocket.accept()
        self._connections.setdefault(proposal_id, []).append(websocket)

    def disconnect(self, proposal_id: str, websocket: WebSocket):
        conns = self._connections.get(proposal_id, [])
        if websocket in conns:
            conns.remove(websocket)
        if not conns:
            self._connections.pop(proposal_id, None)

    async def broadcast(self, proposal_id: str, message: dict):
        conns = self._connections.get(proposal_id, [])
        dead = []
        for ws in conns:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(proposal_id, ws)


ws_manager = ConnectionManager()
