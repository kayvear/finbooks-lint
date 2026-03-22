"""Retrieve a customer's snapshot from the parquet books data.

``BooksRetriever`` reads the raw parquet files and reconstructs enough of the
customer's financial data to support the four comparison checks:

* Equity positions (symbol, quantity, market_value)
* Cash account balances (closing_balance)
* CD account current values (principal + interest_accrued)
* Asset allocation totals (equity_value, cash_value, cd_value)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import pandas as pd

from finbooks.storage.paths import StoragePaths


@dataclass
class PositionSnapshot:
    symbol: str
    quantity: float
    cost_basis_per_share: float
    current_price: float
    market_value: float
    unrealized_pnl: float


@dataclass
class CashAccountSnapshot:
    account_id: str
    account_type: str  # "checking" | "savings"
    opening_balance: float
    closing_balance: float


@dataclass
class CDAccountSnapshot:
    account_id: str
    principal: float
    interest_accrued: float
    current_value: float


@dataclass
class BooksSnapshot:
    """Minimal snapshot of a customer's books for one statement period."""

    customer_id: str
    period: str

    positions: list[PositionSnapshot] = field(default_factory=list)
    cash_accounts: list[CashAccountSnapshot] = field(default_factory=list)
    cd_accounts: list[CDAccountSnapshot] = field(default_factory=list)

    @property
    def equity_value(self) -> float:
        return sum(p.market_value for p in self.positions)

    @property
    def cash_value(self) -> float:
        return sum(a.closing_balance for a in self.cash_accounts)

    @property
    def cd_value(self) -> float:
        return sum(a.current_value for a in self.cd_accounts)

    @property
    def total_value(self) -> float:
        return self.equity_value + self.cash_value + self.cd_value

    @property
    def position_symbols(self) -> set[str]:
        return {p.symbol for p in self.positions}


class BooksRetriever:
    """Load books data from parquet files and return a :class:`BooksSnapshot`.

    Parameters
    ----------
    raw_dir:
        Directory containing the parquet files.  Defaults to ``StoragePaths.raw``.
    """

    def __init__(self, raw_dir: Path | None = None) -> None:
        self._raw_dir = Path(raw_dir) if raw_dir else StoragePaths.raw

    def get_snapshot(self, customer_id: str, period: str) -> BooksSnapshot:
        """Return a :class:`BooksSnapshot` for *customer_id* and *period*."""
        accounts_df = pd.read_parquet(self._raw_dir / "accounts.parquet")
        positions_df = pd.read_parquet(self._raw_dir / "positions.parquet")

        cust_accounts = accounts_df[accounts_df["customer_id"] == customer_id]

        # ── Cash accounts ──────────────────────────────────────────────────
        cash_accounts: list[CashAccountSnapshot] = []
        cash_rows = cust_accounts[cust_accounts["account_type"].isin(["checking", "savings"])]
        for _, row in cash_rows.iterrows():
            cash_accounts.append(CashAccountSnapshot(
                account_id=row["account_id"],
                account_type=row["account_type"],
                opening_balance=float(row.get("opening_balance", 0) or 0),
                closing_balance=float(row.get("current_balance", 0) or 0),
            ))

        # ── CD accounts ────────────────────────────────────────────────────
        cd_accounts: list[CDAccountSnapshot] = []
        cd_rows = cust_accounts[cust_accounts["account_type"] == "cd"]
        for _, row in cd_rows.iterrows():
            principal = float(row.get("principal", 0) or 0)
            interest = float(row.get("interest_accrued", 0) or 0)
            cd_accounts.append(CDAccountSnapshot(
                account_id=row["account_id"],
                principal=principal,
                interest_accrued=interest,
                current_value=principal + interest,
            ))

        # ── Equity positions ───────────────────────────────────────────────
        brokerage_ids = set(
            cust_accounts[cust_accounts["account_type"] == "brokerage"]["account_id"].tolist()
        )
        positions: list[PositionSnapshot] = []
        if brokerage_ids:
            cust_pos = positions_df[positions_df["account_id"].isin(brokerage_ids)]
            for _, row in cust_pos.iterrows():
                qty = float(row["quantity"])
                price = float(row["current_price"])
                cost = float(row["cost_basis_per_share"])
                mv = round(qty * price, 2)
                positions.append(PositionSnapshot(
                    symbol=str(row["symbol"]),
                    quantity=qty,
                    cost_basis_per_share=cost,
                    current_price=price,
                    market_value=mv,
                    unrealized_pnl=round(mv - qty * cost, 2),
                ))

        return BooksSnapshot(
            customer_id=customer_id,
            period=period,
            positions=positions,
            cash_accounts=cash_accounts,
            cd_accounts=cd_accounts,
        )
