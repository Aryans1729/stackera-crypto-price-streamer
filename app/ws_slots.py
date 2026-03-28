import asyncio


class WebSocketSlotPool:
    def __init__(self, max_slots: int) -> None:
        if max_slots < 1:
            raise ValueError("max_slots must be >= 1")
        self._max = max_slots
        self._n = 0
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        async with self._lock:
            if self._n >= self._max:
                return False
            self._n += 1
            return True

    async def release(self) -> None:
        async with self._lock:
            self._n = max(0, self._n - 1)
