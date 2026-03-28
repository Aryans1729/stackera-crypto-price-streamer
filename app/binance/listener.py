from __future__ import annotations

import asyncio
import json
import logging
import random
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

import websockets
from websockets import ConnectionClosed
from websockets.exceptions import InvalidStatus

from app.models.price import Price

logger = logging.getLogger(__name__)

BINANCE_WS_SINGLE = "wss://stream.binance.com:9443/ws"
BINANCE_WS_COMBINED = "wss://stream.binance.com:9443/stream"


def build_stream_url(symbols: Sequence[str]) -> str:
    norm = [s.lower() for s in symbols]
    if len(norm) == 1:
        return f"{BINANCE_WS_SINGLE}/{norm[0]}@ticker"
    joined = "/".join(f"{s}@ticker" for s in norm)
    return f"{BINANCE_WS_COMBINED}?streams={joined}"


class BinanceTickerListener:
    def __init__(
        self,
        *,
        symbols: Sequence[str] = ("BTCUSDT",),
        url_builder: Callable[[Sequence[str]], str] = build_stream_url,
        ping_interval_s: float = 20.0,
        ping_timeout_s: float = 20.0,
        max_queue_put_wait_s: float = 1.0,
    ) -> None:
        if not symbols:
            raise ValueError("At least one symbol is required.")
        self._symbols = tuple(s.upper() for s in symbols)
        self._url_builder = url_builder
        self._ping_interval_s = ping_interval_s
        self._ping_timeout_s = ping_timeout_s
        self._max_queue_put_wait_s = max_queue_put_wait_s

    async def run(
        self,
        *,
        out_queue: asyncio.Queue[Price],
        on_error: Callable[[Exception], Awaitable[None]] | None = None,
        stop_event: asyncio.Event | None = None,
    ) -> None:
        backoff_s = 0.5
        while True:
            if stop_event and stop_event.is_set():
                return

            try:
                await self._connect_once(out_queue=out_queue, stop_event=stop_event)
                backoff_s = 0.5
            except asyncio.CancelledError:
                raise
            except InvalidStatus as exc:
                if exc.response.status_code == 451:
                    logger.warning(
                        "Binance WebSocket HTTP 451 (blocked from this host). "
                        "REST polling supplies /price when api.binance.com allows it."
                    )
                else:
                    logger.warning(
                        "Binance WebSocket rejected: HTTP %s",
                        exc.response.status_code,
                        exc_info=True,
                    )
                if on_error:
                    try:
                        await on_error(exc)
                    except Exception:
                        pass
                jitter = random.random() * 0.2
                sleep_s = min(30.0, backoff_s) + jitter
                backoff_s = min(30.0, backoff_s * 2.0)
                await asyncio.sleep(sleep_s)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Binance WS reconnecting after error: %s", exc, exc_info=True)
                if on_error:
                    try:
                        await on_error(exc)
                    except Exception:
                        pass

                jitter = random.random() * 0.2
                sleep_s = min(30.0, backoff_s) + jitter
                backoff_s = min(30.0, backoff_s * 2.0)
                await asyncio.sleep(sleep_s)

    async def _connect_once(
        self,
        *,
        out_queue: asyncio.Queue[Price],
        stop_event: asyncio.Event | None,
    ) -> None:
        url = self._url_builder(self._symbols)
        logger.info("Binance WS connecting: %s", url)

        async with websockets.connect(
            url,
            ping_interval=self._ping_interval_s,
            ping_timeout=self._ping_timeout_s,
            close_timeout=5.0,
            max_queue=None,
        ) as ws:
            logger.info("Binance WS connected")
            while True:
                if stop_event and stop_event.is_set():
                    return

                try:
                    raw = await ws.recv()
                except ConnectionClosed as exc:
                    raise RuntimeError(f"Binance websocket closed: {exc.code} {exc.reason}") from exc

                payload = self._parse_payload(raw)
                if payload is None:
                    continue

                try:
                    price = Price.from_binance_ticker(payload)
                except Exception:
                    continue

                try:
                    await asyncio.wait_for(out_queue.put(price), timeout=self._max_queue_put_wait_s)
                except TimeoutError:
                    continue

    @staticmethod
    def _parse_payload(raw: Any) -> dict[str, Any] | None:
        if isinstance(raw, (bytes, bytearray)):
            try:
                raw = raw.decode("utf-8")
            except Exception:
                return None

        if not isinstance(raw, str):
            return None

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None

        if not isinstance(payload, dict):
            return None

        if "data" in payload and isinstance(payload["data"], dict):
            inner = payload["data"]
            return inner if isinstance(inner, dict) else None

        return payload
