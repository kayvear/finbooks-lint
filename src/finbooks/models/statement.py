from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, computed_field

from finbooks.models.account import BrokerageAccount, CashAccount, CDAccount
from finbooks.models.customer import Customer
from finbooks.models.position import EquityPosition
from finbooks.models.transaction import BankTransaction, CDTransaction, DividendTransaction, TradeTransaction


class StatementPeriod(BaseModel):
    start_date: date
    end_date: date
    frequency: Literal["monthly", "quarterly"]

    @property
    def label(self) -> str:
        if self.frequency == "quarterly":
            q = (self.start_date.month - 1) // 3 + 1
            return f"{self.start_date.year}Q{q}"
        return self.start_date.strftime("%Y-%m")


class AssetAllocationBreakdown(BaseModel):
    equity_value: Decimal = Decimal("0.00")
    cash_value: Decimal = Decimal("0.00")
    cd_value: Decimal = Decimal("0.00")

    @computed_field  # type: ignore[misc]
    @property
    def total_value(self) -> Decimal:
        return self.equity_value + self.cash_value + self.cd_value

    @computed_field  # type: ignore[misc]
    @property
    def equity_pct(self) -> float:
        if self.total_value == 0:
            return 0.0
        return float(self.equity_value / self.total_value * 100)

    @computed_field  # type: ignore[misc]
    @property
    def cash_pct(self) -> float:
        if self.total_value == 0:
            return 0.0
        return float(self.cash_value / self.total_value * 100)

    @computed_field  # type: ignore[misc]
    @property
    def cd_pct(self) -> float:
        if self.total_value == 0:
            return 0.0
        return float(self.cd_value / self.total_value * 100)


class StatementSummary(BaseModel):
    customer: Customer
    period: StatementPeriod
    allocation: AssetAllocationBreakdown
    opening_value: Decimal
    closing_value: Decimal

    @computed_field  # type: ignore[misc]
    @property
    def net_change(self) -> Decimal:
        return (self.closing_value - self.opening_value).quantize(Decimal("0.01"))

    @computed_field  # type: ignore[misc]
    @property
    def period_return_pct(self) -> Decimal:
        if self.opening_value == 0:
            return Decimal("0.00")
        return (self.net_change / self.opening_value * 100).quantize(Decimal("0.01"))


class StatementData(BaseModel):
    """All data needed to render a full customer statement."""

    summary: StatementSummary

    # Accounts
    cash_accounts: list[CashAccount] = []
    cd_accounts: list[CDAccount] = []
    brokerage_accounts: list[BrokerageAccount] = []

    # Positions
    equity_positions: list[EquityPosition] = []

    # Transactions (period only)
    bank_transactions: list[BankTransaction] = []
    trade_transactions: list[TradeTransaction] = []
    dividend_transactions: list[DividendTransaction] = []
    cd_transactions: list[CDTransaction] = []


class StatementRequest(BaseModel):
    customer_id: str
    period: StatementPeriod
    output_path: str  # resolved PDF path
