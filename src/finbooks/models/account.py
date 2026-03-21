from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


class AccountType(str, Enum):
    CHECKING = "checking"
    SAVINGS = "savings"
    CD = "cd"
    BROKERAGE = "brokerage"


class Account(BaseModel):
    account_id: str  # UUID string
    customer_id: str
    account_type: AccountType
    opened_date: date
    currency: str = "USD"
    is_active: bool = True

    @property
    def display_id(self) -> str:
        """Masked account number for statements: ****XXXX."""
        suffix = self.account_id[-4:].upper()
        return f"****{suffix}"

    @property
    def type_label(self) -> str:
        return self.account_type.value.replace("_", " ").title()


class CashAccount(Account):
    """Checking or savings account with a running balance."""

    current_balance: Decimal = Decimal("0.00")
    opening_balance: Decimal = Decimal("0.00")  # Balance at start of statement period
    interest_rate: Decimal = Decimal("0.00")  # Annual APY


class CDAccount(Account):
    """Certificate of deposit."""

    account_type: AccountType = AccountType.CD
    principal: Decimal
    rate: Decimal  # Annual rate, e.g. 0.051 = 5.1%
    term_months: int
    issue_date: date
    maturity_date: date
    interest_accrued: Decimal = Decimal("0.00")
    is_matured: bool = False

    @property
    def annual_interest(self) -> Decimal:
        return (self.principal * self.rate).quantize(Decimal("0.01"))

    @property
    def current_value(self) -> Decimal:
        return self.principal + self.interest_accrued


class BrokerageAccount(Account):
    """Equity brokerage account."""

    account_type: AccountType = AccountType.BROKERAGE
    cash_balance: Decimal = Decimal("0.00")
    opening_cash_balance: Decimal = Decimal("0.00")
