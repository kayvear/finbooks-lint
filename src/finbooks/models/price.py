from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class Price(BaseModel):
    symbol: str
    price_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int = 0

    @property
    def adjusted_close(self) -> Decimal:
        return self.close


class PriceHistory(BaseModel):
    symbol: str
    prices: list[Price]

    def latest(self) -> Price | None:
        if not self.prices:
            return None
        return max(self.prices, key=lambda p: p.price_date)

    def on_date(self, d: date) -> Price | None:
        for p in self.prices:
            if p.price_date == d:
                return p
        return None

    def close_on(self, d: date) -> Decimal | None:
        p = self.on_date(d)
        return p.close if p else None
