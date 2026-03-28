from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator

from app.models.price import Price


class PriceService:
    def __init__(self, *, ingest_queue_maxsize: int = 1000) -> None:
        self.ingest_queue: asyncio.Queue[Price] = asyncio.Queue(maxsize=ingest_queue_maxsize)

        self._latest_by_symbol: dict[str, Price] = {}
        self._latest_lock = asyncio.Lock()

        self._subscribers_all: set[asyncio.Queue[Price]] = set()
        self._subscribers_by_symbol: dict[str, set[asyncio.Queue[Price]]] = defaultdict(set)
        self._subscribers_lock = asyncio.Lock()

        self._stop_event = asyncio.Event()

    async def stop(self) -> None:
        self._stop_event.set()

    async def get_latest(self, symbol: str) -> Price | None:
        sym = symbol.upper()
        async with self._latest_lock:
            return self._latest_by_symbol.get(sym)

    async def get_all_latest(self) -> dict[str, Price]:
        async with self._latest_lock:
            return dict(self._latest_by_symbol)

    async def run(self) -> None:
        while True:
            price = await self._get_next_price_or_stop()
            if price is None:
                return
            await self._set_latest(price)
            await self._fan_out(price)

    async def _get_next_price_or_stop(self) -> Price | None:
        get_task = asyncio.create_task(self.ingest_queue.get())
        stop_task = asyncio.create_task(self._stop_event.wait())
        try:
            done, pending = await asyncio.wait(
                {get_task, stop_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass
            if stop_task in done:
                get_task.cancel()
                try:
                    await get_task
                except asyncio.CancelledError:
                    pass
                return None
            stop_task.cancel()
            try:
                await stop_task
            except asyncio.CancelledError:
                pass
            return get_task.result()
        except asyncio.CancelledError:
            get_task.cancel()
            stop_task.cancel()
            raise

    async def subscribe(self, *, symbol: str | None = None, max_queue_size: int = 1) -> asyncio.Queue[Price]:
        q: asyncio.Queue[Price] = asyncio.Queue(maxsize=max_queue_size)
        async with self._subscribers_lock:
            if symbol is None:
                self._subscribers_all.add(q)
            else:
                self._subscribers_by_symbol[symbol.upper()].add(q)

        if symbol is None:
            async with self._latest_lock:
                for p in self._latest_by_symbol.values():
                    self._put_latest_only(q, p)
        else:
            latest = await self.get_latest(symbol)
            if latest is not None:
                self._put_latest_only(q, latest)
        return q

    async def unsubscribe(self, q: asyncio.Queue[Price], *, symbol: str | None = None) -> None:
        async with self._subscribers_lock:
            if symbol is None:
                self._subscribers_all.discard(q)
            else:
                subs = self._subscribers_by_symbol.get(symbol.upper())
                if subs:
                    subs.discard(q)
                    if not subs:
                        del self._subscribers_by_symbol[symbol.upper()]

    async def stream(self, *, symbol: str | None = None) -> AsyncIterator[Price]:
        q = await self.subscribe(symbol=symbol)
        try:
            while True:
                yield await q.get()
        finally:
            await self.unsubscribe(q, symbol=symbol)

    async def _set_latest(self, price: Price) -> None:
        async with self._latest_lock:
            self._latest_by_symbol[price.symbol] = price

    async def _fan_out(self, price: Price) -> None:
        async with self._subscribers_lock:
            all_qs = list(self._subscribers_all)
            sym_qs = list(self._subscribers_by_symbol.get(price.symbol, ()))

        for q in all_qs:
            self._put_latest_only(q, price)
        for q in sym_qs:
            self._put_latest_only(q, price)

    @staticmethod
    def _put_latest_only(q: asyncio.Queue[Price], price: Price) -> None:
        try:
            q.put_nowait(price)
        except asyncio.QueueFull:
            try:
                q.get_nowait()
            except Exception:
                pass
            try:
                q.put_nowait(price)
            except Exception:
                pass
