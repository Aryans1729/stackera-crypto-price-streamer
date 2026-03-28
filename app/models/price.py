from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class Price(BaseModel):
    symbol: str
    price: float
    change_percent: float = Field(..., description="24h change %")
    timestamp: datetime = Field(..., description="UTC")

    @classmethod
    def from_binance_ticker(cls, payload: dict[str, Any]) -> "Price":
        symbol = str(payload["s"])
        price = float(payload["c"])
        change_percent = float(payload["P"])
        event_ms = int(payload["E"])
        ts = datetime.fromtimestamp(event_ms / 1000.0, tz=timezone.utc)
        return cls(symbol=symbol, price=price, change_percent=change_percent, timestamp=ts)

