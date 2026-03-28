from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Sequence

import httpx

from app.models.price import Price

logger = logging.getLogger(__name__)

BINANCE_REST_24H = "https://api.binance.com/api/v3/ticker/24hr"

DEFAULT_POLL_INTERVAL_S = float(os.environ.get("BINANCE_REST_POLL_SECONDS", "2"))


async def poll_binance_rest_loop(
    out_queue: asyncio.Queue[Price],
    symbols: Sequence[str],
    stop_event: asyncio.Event,
    *,
    interval_s: float | None = None,
    client_timeout_s: float = 15.0,
    put_timeout_s: float = 5.0,
) -> None:
    """
    Poll Binance REST on an interval. Used when WebSocket is blocked (e.g. HTTP 451
    from cloud IPs). Updates the same ingest queue as the WS listener.
    """
    wait_s = DEFAULT_POLL_INTERVAL_S if interval_s is None else interval_s
    last_451_warning = False

    async with httpx.AsyncClient(timeout=client_timeout_s) as client:
        while not stop_event.is_set():
            batch_ok = False
            batch_all_451 = True

            for sym in symbols:
                if stop_event.is_set():
                    return
                try:
                    r = await client.get(BINANCE_REST_24H, params={"symbol": sym})
                    if r.status_code == 451:
                        continue
                    batch_all_451 = False
                    r.raise_for_status()
                    body = r.json()
                    if not isinstance(body, dict):
                        continue
                    price = Price.from_binance_rest_24hr(body)
                    await asyncio.wait_for(out_queue.put(price), timeout=put_timeout_s)
                    batch_ok = True
                except httpx.HTTPStatusError as e:
                    batch_all_451 = False
                    logger.warning("Binance REST HTTP error for %s: %s", sym, e.response.status_code)
                except Exception:
                    batch_all_451 = False
                    logger.exception("Binance REST poll failed for %s", sym)

            if batch_all_451 and symbols:
                if not last_451_warning:
                    logger.error(
                        "Binance returned HTTP 451 for REST from this host. "
                        "Their API is unavailable from this server region/IP (same as WebSocket). "
                        "Deploy in a different region/provider or demo via local run."
                    )
                    last_451_warning = True
            elif batch_ok:
                last_451_warning = False

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=wait_s)
            except asyncio.TimeoutError:
                pass
