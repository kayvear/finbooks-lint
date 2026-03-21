from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel


class BankTxnType(str, Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"
    INTEREST = "interest"
    FEE = "fee"


class TradeSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class CDTxnType(str, Enum):
    OPEN = "open"
    INTEREST = "interest"
    MATURE = "mature"
    EARLY_WITHDRAWAL = "early_withdrawal"


class Transaction(BaseModel):
    """Base transaction — all transactions share these fields."""

    transaction_id: str  # UUID string
    account_id: str
    transaction_date: date
    amount: Decimal  # positive = credit, negative = debit
    description: str
    running_balance: Decimal  # balance after this transaction


class BankTransaction(Transaction):
    """Cash account (checking/savings) transaction."""

    txn_type: BankTxnType
    counterparty: str = ""  # e.g. "ACH PAYMENT - VERIZON"


class TradeTransaction(Transaction):
    """Equity buy/sell trade."""

    txn_type: Literal["trade"] = "trade"
    symbol: str
    side: TradeSide
    quantity: Decimal  # shares
    price_per_share: Decimal
    commission: Decimal = Decimal("0.00")
    gross_amount: Decimal  # quantity * price_per_share
    # amount (inherited) = net_amount = -(gross + commission) for buys, +(gross - commission) for sells

    @property
    def net_amount(self) -> Decimal:
        return self.amount


class DividendTransaction(Transaction):
    """Dividend payment into brokerage cash."""

    txn_type: Literal["dividend"] = "dividend"
    symbol: str
    shares_held: Decimal
    dividend_per_share: Decimal


class CDTransaction(Transaction):
    """CD lifecycle event."""

    txn_type: CDTxnType
