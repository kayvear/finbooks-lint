from __future__ import annotations

import random
import uuid
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

import pandas as pd

from finbooks.datagen.universe import AssetUniverse
from finbooks.models.account import BrokerageAccount, CashAccount, CDAccount
from finbooks.models.customer import Customer
from finbooks.models.price import PriceHistory
from finbooks.models.transaction import (
    BankTransaction,
    BankTxnType,
    CDTransaction,
    CDTxnType,
    DividendTransaction,
    TradeTransaction,
    TradeSide,
)
from finbooks.settings import settings

_BILL_DESCRIPTIONS = [
    "ACH Payment — Rent", "ACH Payment — Utilities", "ACH Payment — Internet",
    "ACH Payment — Insurance", "ACH Payment — Phone", "ACH Payment — Streaming",
    "ACH Payment — Gym", "ACH Payment — Car Loan",
]

_DEPOSIT_DESCRIPTIONS = [
    "Direct Deposit — Payroll", "Direct Deposit — Payroll",
    "Transfer In — Savings", "ACH Credit — Refund",
]


def _working_days_in_range(start: date, end: date) -> list[date]:
    days: list[date] = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


class TransactionGenerator:
    """
    Generates realistic transaction histories for all accounts.

    Each BankTransaction maintains a running balance.
    Each TradeTransaction records cost basis data needed for P&L validation.
    """

    def __init__(self) -> None:
        self._rng = random.Random(settings.random_seed + 2)

    def generate_bank_transactions(
        self,
        cash_accounts: list[CashAccount],
        start: date,
        end: date,
    ) -> list[BankTransaction]:
        txns: list[BankTransaction] = []
        working_days = _working_days_in_range(start, end)

        for acct in cash_accounts:
            balance = acct.opening_balance
            acct_txns: list[BankTransaction] = []

            if acct.account_type.value == "checking":
                # Bi-weekly payroll + random bills
                for i, d in enumerate(working_days):
                    # Bi-weekly payroll on 1st and 15th-ish
                    if d.day in (1, 15) or (d.day in (2, 3) and d.weekday() == 0):
                        amount = Decimal(str(round(self._rng.uniform(3000, 8000), 2)))
                        balance += amount
                        acct_txns.append(BankTransaction(
                            transaction_id=str(uuid.uuid4()),
                            account_id=acct.account_id,
                            transaction_date=d,
                            amount=amount,
                            description=self._rng.choice(_DEPOSIT_DESCRIPTIONS[:2]),
                            running_balance=balance,
                            txn_type=BankTxnType.DEPOSIT,
                        ))

                    # Random bill payments (3–5 per month)
                    if d.day in (5, 10, 18, 22, 28) and self._rng.random() < 0.75:
                        amount = -Decimal(str(round(self._rng.uniform(80, 1500), 2)))
                        balance += amount
                        acct_txns.append(BankTransaction(
                            transaction_id=str(uuid.uuid4()),
                            account_id=acct.account_id,
                            transaction_date=d,
                            amount=amount,
                            description=self._rng.choice(_BILL_DESCRIPTIONS),
                            running_balance=balance,
                            txn_type=BankTxnType.WITHDRAWAL,
                        ))

            elif acct.account_type.value == "savings":
                # Monthly interest + 1-2 transfers from checking per month
                for d in working_days:
                    if d.day == 1:
                        interest = (acct.opening_balance * acct.interest_rate / 12).quantize(
                            Decimal("0.01"), rounding=ROUND_HALF_UP
                        )
                        balance += interest
                        acct_txns.append(BankTransaction(
                            transaction_id=str(uuid.uuid4()),
                            account_id=acct.account_id,
                            transaction_date=d,
                            amount=interest,
                            description="Interest Credit",
                            running_balance=balance,
                            txn_type=BankTxnType.INTEREST,
                        ))
                    if d.day == 10 and self._rng.random() < 0.50:
                        amount = Decimal(str(round(self._rng.uniform(200, 1000), 2)))
                        balance += amount
                        acct_txns.append(BankTransaction(
                            transaction_id=str(uuid.uuid4()),
                            account_id=acct.account_id,
                            transaction_date=d,
                            amount=amount,
                            description="Transfer In — Checking",
                            running_balance=balance,
                            txn_type=BankTxnType.TRANSFER_IN,
                        ))

            txns.extend(acct_txns)

        return txns

    def generate_trade_transactions(
        self,
        brokerage_accounts: list[BrokerageAccount],
        price_histories: dict[str, PriceHistory],
        start: date,
        end: date,
    ) -> tuple[list[TradeTransaction], list[DividendTransaction]]:
        trades: list[TradeTransaction] = []
        dividends: list[DividendTransaction] = []
        working_days = _working_days_in_range(start, end)

        for acct in brokerage_accounts:
            cash = acct.opening_cash_balance
            # Assign 3–6 random symbols to this account
            symbols = self._rng.sample(AssetUniverse.equity_symbols(), k=self._rng.randint(3, 6))
            holdings: dict[str, Decimal] = {}  # symbol → shares held

            # Generate 5–15 trades spread over the period
            n_trades = self._rng.randint(5, 15)
            trade_days = sorted(self._rng.sample(working_days, k=min(n_trades, len(working_days))))

            for d in trade_days:
                sym = self._rng.choice(symbols)
                hist = price_histories.get(sym)
                if not hist:
                    continue
                price = hist.close_on(d)
                if price is None:
                    # Fall back to nearest prior price
                    prior = [p for p in hist.prices if p.price_date <= d]
                    if not prior:
                        continue
                    price = prior[-1].close

                current_qty = holdings.get(sym, Decimal("0"))

                # Decide buy or sell
                if current_qty > 0 and self._rng.random() < 0.35:
                    side = TradeSide.SELL
                    qty = Decimal(str(self._rng.randint(1, max(1, int(current_qty) // 2))))
                else:
                    side = TradeSide.BUY
                    max_affordable = int(float(cash) / float(price))
                    if max_affordable < 1:
                        continue
                    qty = Decimal(str(self._rng.randint(1, max(1, max_affordable))))

                gross = (qty * price).quantize(Decimal("0.01"))

                if side == TradeSide.BUY:
                    amount = -gross
                    cash += amount
                    holdings[sym] = holdings.get(sym, Decimal("0")) + qty
                else:
                    amount = gross
                    cash += amount
                    holdings[sym] = holdings.get(sym, Decimal("0")) - qty

                trades.append(TradeTransaction(
                    transaction_id=str(uuid.uuid4()),
                    account_id=acct.account_id,
                    transaction_date=d,
                    symbol=sym,
                    side=side,
                    quantity=qty,
                    price_per_share=price,
                    commission=Decimal("0.00"),
                    gross_amount=gross,
                    amount=amount,
                    description=f"{'Buy' if side == TradeSide.BUY else 'Sell'} {qty} {sym} @ {price}",
                    running_balance=cash,
                ))

            # Quarterly dividends for dividend-paying symbols held at period end
            div_date = date(end.year, end.month, 15) if date(end.year, end.month, 15) <= end else end
            for sym, qty in holdings.items():
                if qty <= 0:
                    continue
                spec = AssetUniverse.get_equity(sym)
                if not spec or spec.annual_div_yield == 0:
                    continue
                hist = price_histories.get(sym)
                if not hist:
                    continue
                price = hist.close_on(end) or Decimal("100")
                quarterly_yield = spec.annual_div_yield / 4
                div_per_share = (price * Decimal(str(quarterly_yield))).quantize(Decimal("0.0001"))
                div_total = (qty * div_per_share).quantize(Decimal("0.01"))
                cash += div_total

                dividends.append(DividendTransaction(
                    transaction_id=str(uuid.uuid4()),
                    account_id=acct.account_id,
                    transaction_date=div_date,
                    symbol=sym,
                    shares_held=qty,
                    dividend_per_share=div_per_share,
                    amount=div_total,
                    description=f"Dividend — {sym} Q4",
                    running_balance=cash,
                ))

        return trades, dividends

    def generate_cd_transactions(
        self,
        cd_accounts: list[CDAccount],
    ) -> list[CDTransaction]:
        txns: list[CDTransaction] = []
        for cd in cd_accounts:
            # CD open transaction
            txns.append(CDTransaction(
                transaction_id=str(uuid.uuid4()),
                account_id=cd.account_id,
                transaction_date=cd.issue_date,
                amount=cd.principal,
                description=f"CD Opened — {cd.term_months}-month at {float(cd.rate)*100:.2f}%",
                running_balance=cd.principal,
                txn_type=CDTxnType.OPEN,
            ))
            # Monthly interest within statement period
            d = settings.statement_start
            monthly_interest = (cd.principal * cd.rate / 12).quantize(Decimal("0.01"))
            balance = cd.principal
            while d <= settings.statement_end:
                if d >= cd.issue_date and d.day == 1:
                    balance += monthly_interest
                    txns.append(CDTransaction(
                        transaction_id=str(uuid.uuid4()),
                        account_id=cd.account_id,
                        transaction_date=d,
                        amount=monthly_interest,
                        description=f"CD Interest — {d.strftime('%B %Y')}",
                        running_balance=balance,
                        txn_type=CDTxnType.INTEREST,
                    ))
                from datetime import timedelta
                d = date(d.year + (d.month // 12), (d.month % 12) + 1, 1)

        return txns

    def to_dataframe(
        self,
        bank: list[BankTransaction],
        trades: list[TradeTransaction],
        dividends: list[DividendTransaction],
        cd: list[CDTransaction],
    ) -> pd.DataFrame:
        records: list[dict] = []

        for t in bank:
            records.append({
                "transaction_id": t.transaction_id, "account_id": t.account_id,
                "transaction_date": t.transaction_date, "txn_category": "bank",
                "txn_type": t.txn_type.value, "description": t.description,
                "amount": float(t.amount), "running_balance": float(t.running_balance),
                "symbol": None, "side": None, "quantity": None,
                "price_per_share": None, "commission": None,
            })

        for t in trades:
            records.append({
                "transaction_id": t.transaction_id, "account_id": t.account_id,
                "transaction_date": t.transaction_date, "txn_category": "trade",
                "txn_type": t.txn_type, "description": t.description,
                "amount": float(t.amount), "running_balance": float(t.running_balance),
                "symbol": t.symbol, "side": t.side.value,
                "quantity": float(t.quantity), "price_per_share": float(t.price_per_share),
                "commission": float(t.commission),
            })

        for t in dividends:
            records.append({
                "transaction_id": t.transaction_id, "account_id": t.account_id,
                "transaction_date": t.transaction_date, "txn_category": "dividend",
                "txn_type": t.txn_type, "description": t.description,
                "amount": float(t.amount), "running_balance": float(t.running_balance),
                "symbol": t.symbol, "side": None, "quantity": float(t.shares_held),
                "price_per_share": float(t.dividend_per_share), "commission": None,
            })

        for t in cd:
            records.append({
                "transaction_id": t.transaction_id, "account_id": t.account_id,
                "transaction_date": t.transaction_date, "txn_category": "cd",
                "txn_type": t.txn_type.value, "description": t.description,
                "amount": float(t.amount), "running_balance": float(t.running_balance),
                "symbol": None, "side": None, "quantity": None,
                "price_per_share": None, "commission": None,
            })

        return pd.DataFrame(records)
