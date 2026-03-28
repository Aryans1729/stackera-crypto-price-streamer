from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence

import httpx

from app.models.price import Price

logger = logging.getLogger(__name__)

BINANCE_REST_24H = "https://api.binance.com/api/v3/ticker/24hr"


async def seed_prices_from_rest(
    out_queue: asyncio.Queue[Price],
    symbols: Sequence[str],
    *,
    client_timeout_s: float = 15.0,
    put_timeout_s: float = 5.0,
) -> None:
    """
    One-shot seed from Binance REST so /price works even when outbound WS
    from the host (e.g. some cloud regions) is blocked or slow.
    The WebSocket listener continues and replaces these with live ticks.
    """
    try:
        async with httpx.AsyncClient(timeout=client_timeout_s) as client:
            for sym in symbols:
                try:
                    r = await client.get(BINANCE_REST_24H, params={"symbol": sym})
                    r.raise_for_status()
                    body = r.json()
                    if not isinstance(body, dict):
                        continue
                    price = Price.from_binance_rest_24hr(body)
                    await asyncio.wait_for(out_queue.put(price), timeout=put_timeout_s)
                    logger.info("Binance REST seed ok: %s", sym)
                except Exception:
                    logger.exception("Binance REST seed failed for %s", sym)
    except Exception:
        logger.exception("Binance REST seed aborted")
