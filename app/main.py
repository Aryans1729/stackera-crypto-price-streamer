import asyncio
import logging
import os
from contextlib import suppress

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from websockets.exceptions import InvalidStatus

from app.binance.listener import BinanceTickerListener
from app.binance.rest_seed import poll_binance_rest_loop
from app.config import MAX_WEBSOCKET_CONNECTIONS, TRACKED_SYMBOLS
from app.limiter import limiter
from app.services.price_service import PriceService
from app.websocket.manager import ConnectionManager
from app.ws_slots import WebSocketSlotPool

from app.api.routes import router as api_router

log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="Stackera Crypto Price Streamer", version="0.2.0")
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.include_router(api_router)

    _cors = os.getenv("CORS_ORIGINS", "").strip()
    if _cors:
        origins = [o.strip() for o in _cors.split(",") if o.strip()]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.state.price_service = PriceService()
    app.state.ws_manager = ConnectionManager()
    app.state.ws_slots = WebSocketSlotPool(MAX_WEBSOCKET_CONNECTIONS)
    app.state.binance_listener = BinanceTickerListener(symbols=TRACKED_SYMBOLS)
    app.state._stop_event = asyncio.Event()
    app.state._tasks: list[asyncio.Task[None]] = []

    @app.on_event("startup")
    async def _startup() -> None:
        price_service: PriceService = app.state.price_service
        listener: BinanceTickerListener = app.state.binance_listener
        stop_event: asyncio.Event = app.state._stop_event

        async def on_listener_error(exc: Exception) -> None:
            if isinstance(exc, InvalidStatus) and exc.response.status_code == 451:
                return
            log.warning("Binance listener hook: %s", exc, exc_info=True)

        app.state._tasks = [
            asyncio.create_task(price_service.run(), name="price-service"),
            asyncio.create_task(
                listener.run(out_queue=price_service.ingest_queue, on_error=on_listener_error, stop_event=stop_event),
                name="binance-listener",
            ),
            asyncio.create_task(
                poll_binance_rest_loop(price_service.ingest_queue, TRACKED_SYMBOLS, stop_event),
                name="binance-rest-poll",
            ),
        ]

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        stop_event: asyncio.Event = app.state._stop_event
        stop_event.set()

        price_service: PriceService = app.state.price_service
        await price_service.stop()

        tasks: list[asyncio.Task[None]] = app.state._tasks
        for t in tasks:
            t.cancel()
        for t in tasks:
            with suppress(asyncio.CancelledError):
                await t

    return app


app = create_app()
