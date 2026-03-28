from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        await self.register(websocket)

    async def register(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)

    async def broadcast_json(self, message: Any) -> None:
        async with self._lock:
            conns = list(self._connections)

        if not conns:
            return

        dead: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_json(message)
            except WebSocketDisconnect:
                dead.append(ws)
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections.discard(ws)

    async def broadcast_text(self, message: str) -> None:
        async with self._lock:
            conns = list(self._connections)

        if not conns:
            return

        dead: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_text(message)
            except WebSocketDisconnect:
                dead.append(ws)
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections.discard(ws)

    async def count(self) -> int:
        async with self._lock:
            return len(self._connections)

