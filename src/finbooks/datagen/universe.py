"""
Asset universe master — the canonical list of instruments available for simulation.
"""

from dataclasses import dataclass

from finbooks.settings import ALL_EQUITY_TICKERS, CD_RATES, SEED_PRICES, VOLATILITY, DIVIDEND_YIELD


@dataclass(frozen=True)
class EquitySpec:
    symbol: str
    seed_price: float
    annual_vol: float
    annual_div_yield: float


@dataclass(frozen=True)
class CDSpec:
    term_months: int
    annual_rate: float


class AssetUniverse:
    """Central registry of all tradeable instruments."""

    equities: list[EquitySpec] = [
        EquitySpec(
            symbol=sym,
            seed_price=SEED_PRICES[sym],
            annual_vol=VOLATILITY[sym],
            annual_div_yield=DIVIDEND_YIELD.get(sym, 0.0),
        )
        for sym in ALL_EQUITY_TICKERS
    ]

    cds: list[CDSpec] = [
        CDSpec(term_months=term, annual_rate=rate)
        for term, rate in CD_RATES.items()
    ]

    @classmethod
    def equity_symbols(cls) -> list[str]:
        return [e.symbol for e in cls.equities]

    @classmethod
    def get_equity(cls, symbol: str) -> EquitySpec | None:
        for e in cls.equities:
            if e.symbol == symbol:
                return e
        return None

    @classmethod
    def dividend_payers(cls) -> list[EquitySpec]:
        return [e for e in cls.equities if e.annual_div_yield > 0]
