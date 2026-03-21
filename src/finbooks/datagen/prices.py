"""
Price generator using Geometric Brownian Motion (GBM).

GBM formula:  S(t+1) = S(t) * exp((mu - sigma²/2)*dt + sigma*sqrt(dt)*Z)
  where Z ~ N(0,1), dt = 1/252 (one trading day), mu = 0.08 (8% annual drift)
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd

from finbooks.datagen.universe import AssetUniverse
from finbooks.models.price import Price, PriceHistory
from finbooks.settings import settings


def _trading_days(start: date, end: date) -> list[date]:
    """Return all weekdays (Mon–Fri) between start and end inclusive."""
    days: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:  # 0=Mon … 4=Fri
            days.append(current)
        current += timedelta(days=1)
    return days


class PriceGenerator:
    """
    Generates daily OHLCV price history for all equity instruments via GBM.
    Prices are seeded so every run with the same settings.random_seed produces
    identical price paths — essential for reproducible validation.
    """

    ANNUAL_DRIFT = 0.08   # 8% expected annual return
    TRADING_DAYS = 252

    def __init__(self) -> None:
        self._rng = np.random.default_rng(settings.random_seed)

    def generate(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, PriceHistory]:
        """
        Generate price history for all tickers. Returns {symbol: PriceHistory}.
        """
        start = start_date or settings.statement_start
        end = end_date or settings.statement_end
        trading_days = _trading_days(start, end)
        dt = 1 / self.TRADING_DAYS

        histories: dict[str, PriceHistory] = {}

        for spec in AssetUniverse.equities:
            prices: list[Price] = []
            S = spec.seed_price
            mu = self.ANNUAL_DRIFT
            sigma = spec.annual_vol

            for d in trading_days:
                Z = self._rng.standard_normal()
                S = S * np.exp((mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * Z)
                S = max(S, 0.01)  # floor at $0.01

                # Intraday range: ±0.5% * vol
                intraday_range = S * sigma * np.sqrt(dt) * 0.5
                high = S + abs(self._rng.normal(0, intraday_range))
                low = S - abs(self._rng.normal(0, intraday_range))
                open_ = low + self._rng.random() * (high - low)

                prices.append(Price(
                    symbol=spec.symbol,
                    price_date=d,
                    open=Decimal(str(round(open_, 4))),
                    high=Decimal(str(round(high, 4))),
                    low=Decimal(str(round(low, 4))),
                    close=Decimal(str(round(S, 4))),
                    volume=int(self._rng.integers(500_000, 50_000_000)),
                ))

            histories[spec.symbol] = PriceHistory(symbol=spec.symbol, prices=prices)

        return histories

    def to_dataframe(self, histories: dict[str, PriceHistory]) -> pd.DataFrame:
        """Convert PriceHistory dict to a flat DataFrame for parquet storage."""
        records = []
        for history in histories.values():
            for p in history.prices:
                records.append({
                    "symbol": p.symbol,
                    "price_date": p.price_date,
                    "open": float(p.open),
                    "high": float(p.high),
                    "low": float(p.low),
                    "close": float(p.close),
                    "volume": p.volume,
                })
        return pd.DataFrame(records)
