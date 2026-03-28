from typing import Optional

from fastapi import APIRouter, HTTPException, Request, WebSocket
from starlette.websockets import WebSocketDisconnect

from app.config import PRICE_RATE_LIMIT, TRACKED_SYMBOLS_SET
from app.limiter import limiter
from app.services.price_service import PriceService
from app.websocket.manager import ConnectionManager
from app.ws_slots import WebSocketSlotPool

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/price")
@limiter.limit(PRICE_RATE_LIMIT)
async def get_price(request: Request, symbol: Optional[str] = None) -> dict:
    price_service: PriceService = request.app.state.price_service

    if symbol:
        sym = symbol.strip().upper()
        if sym not in TRACKED_SYMBOLS_SET:
            raise HTTPException(status_code=400, detail=f"Unknown symbol. Allowed: {sorted(TRACKED_SYMBOLS_SET)}")
        latest = await price_service.get_latest(sym)
        if latest is None:
            raise HTTPException(status_code=404, detail=f"No price available yet for {sym}.")
        return latest.model_dump(mode="json")

    all_latest = await price_service.get_all_latest()
    if not all_latest:
        raise HTTPException(status_code=404, detail="No price available yet.")
    return {s: p.model_dump(mode="json") for s, p in sorted(all_latest.items())}


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    manager: ConnectionManager = websocket.app.state.ws_manager
    price_service: PriceService = websocket.app.state.price_service
    slots: WebSocketSlotPool = websocket.app.state.ws_slots

    sym_raw = websocket.query_params.get("symbol")
    filter_sym: Optional[str] = None
    if sym_raw:
        filter_sym = sym_raw.strip().upper()
        if filter_sym not in TRACKED_SYMBOLS_SET:
            await websocket.close(code=4400, reason="Unknown symbol")
            return

    if not await slots.acquire():
        await websocket.close(code=1008, reason="Connection limit exceeded")
        return

    try:
        await websocket.accept()
        await manager.register(websocket)
        try:
            if filter_sym:
                latest = await price_service.get_latest(filter_sym)
                if latest is not None:
                    await websocket.send_json(latest.model_dump(mode="json"))
            else:
                for p in (await price_service.get_all_latest()).values():
                    await websocket.send_json(p.model_dump(mode="json"))

            async for price in price_service.stream(symbol=filter_sym):
                await websocket.send_json(price.model_dump(mode="json"))
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            await manager.disconnect(websocket)
    finally:
        await slots.release()
