from __future__ import annotations

import random
import uuid
from datetime import date
from decimal import Decimal

import pandas as pd

from finbooks.datagen.universe import AssetUniverse
from finbooks.models.account import AccountType, BrokerageAccount, CashAccount, CDAccount
from finbooks.models.customer import Customer, CustomerTier
from finbooks.settings import settings


class AccountGenerator:
    """
    Generates accounts for each customer.

    Rules:
      - Every customer gets 1 checking + 1 savings
      - 60% retail / 100% private get a brokerage account
      - 40% of customers get 1 CD; 15% get 2 CDs
    """

    def __init__(self) -> None:
        self._rng = random.Random(settings.random_seed + 1)

    def generate(
        self,
        customers: list[Customer],
    ) -> tuple[list[CashAccount], list[CDAccount], list[BrokerageAccount]]:
        cash: list[CashAccount] = []
        cds: list[CDAccount] = []
        brokerage: list[BrokerageAccount] = []

        for customer in customers:
            cid = customer.customer_id
            opened = customer.created_at

            # ── Checking ───────────────────────────────────────────────────────
            chk_balance = Decimal(str(round(self._rng.uniform(3000, 25000), 2)))
            cash.append(CashAccount(
                account_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{cid}-checking")),
                customer_id=cid,
                account_type=AccountType.CHECKING,
                opened_date=opened,
                current_balance=chk_balance,
                opening_balance=(chk_balance * Decimal("0.92")).quantize(Decimal("0.01")),
                interest_rate=Decimal("0.00"),
            ))

            # ── Savings ────────────────────────────────────────────────────────
            sav_balance = Decimal(str(round(self._rng.uniform(1000, 50000), 2)))
            cash.append(CashAccount(
                account_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{cid}-savings")),
                customer_id=cid,
                account_type=AccountType.SAVINGS,
                opened_date=date(opened.year, min(opened.month + 1, 12), 1),
                current_balance=sav_balance,
                opening_balance=(sav_balance * Decimal("0.97")).quantize(Decimal("0.01")),
                interest_rate=Decimal("0.042"),
            ))

            # ── CD(s) ──────────────────────────────────────────────────────────
            p_cd = self._rng.random()
            cd_count = 0 if p_cd > 0.55 else (2 if p_cd < 0.15 else 1)
            for k in range(cd_count):
                cd_spec = self._rng.choice(AssetUniverse.cds)
                principal = Decimal(str(round(self._rng.uniform(5000, 100000), 2)))
                issue = date(2024, self._rng.randint(1, 9), 1)
                # Compute months elapsed from issue to statement_end
                months_elapsed = (
                    (settings.statement_end.year - issue.year) * 12
                    + settings.statement_end.month - issue.month
                )
                months_elapsed = max(0, months_elapsed)
                interest = (
                    principal * Decimal(str(cd_spec.annual_rate)) * Decimal(str(months_elapsed / 12))
                ).quantize(Decimal("0.01"))

                maturity_month = ((issue.month - 1 + cd_spec.term_months) % 12) + 1
                maturity_year = issue.year + (issue.month - 1 + cd_spec.term_months) // 12
                cds.append(CDAccount(
                    account_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{cid}-cd-{k}")),
                    customer_id=cid,
                    account_type=AccountType.CD,
                    opened_date=issue,
                    principal=principal,
                    rate=Decimal(str(cd_spec.annual_rate)),
                    term_months=cd_spec.term_months,
                    issue_date=issue,
                    maturity_date=date(maturity_year, maturity_month, 1),
                    interest_accrued=interest,
                ))

            # ── Brokerage ─────────────────────────────────────────────────────
            open_brokerage = (
                customer.tier == CustomerTier.PRIVATE or self._rng.random() < 0.60
            )
            if open_brokerage:
                brk_cash = Decimal(str(round(self._rng.uniform(500, 10000), 2)))
                brokerage.append(BrokerageAccount(
                    account_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{cid}-brokerage")),
                    customer_id=cid,
                    account_type=AccountType.BROKERAGE,
                    opened_date=date(opened.year + 1, 1, 1),
                    cash_balance=brk_cash,
                    opening_cash_balance=(brk_cash * Decimal("0.94")).quantize(Decimal("0.01")),
                ))

        return cash, cds, brokerage

    def to_dataframe(
        self,
        cash: list[CashAccount],
        cds: list[CDAccount],
        brokerage: list[BrokerageAccount],
    ) -> pd.DataFrame:
        records: list[dict] = []

        for a in cash:
            records.append({
                "account_id": a.account_id, "customer_id": a.customer_id,
                "account_type": a.account_type.value, "opened_date": a.opened_date,
                "current_balance": float(a.current_balance),
                "opening_balance": float(a.opening_balance),
                "interest_rate": float(a.interest_rate),
                "principal": None, "rate": None, "term_months": None,
                "issue_date": None, "maturity_date": None, "interest_accrued": None,
            })

        for a in cds:
            records.append({
                "account_id": a.account_id, "customer_id": a.customer_id,
                "account_type": a.account_type.value, "opened_date": a.opened_date,
                "current_balance": float(a.current_value),
                "opening_balance": float(a.principal),
                "interest_rate": float(a.rate),
                "principal": float(a.principal), "rate": float(a.rate),
                "term_months": a.term_months, "issue_date": a.issue_date,
                "maturity_date": a.maturity_date,
                "interest_accrued": float(a.interest_accrued),
            })

        for a in brokerage:
            records.append({
                "account_id": a.account_id, "customer_id": a.customer_id,
                "account_type": a.account_type.value, "opened_date": a.opened_date,
                "current_balance": float(a.cash_balance),
                "opening_balance": float(a.opening_cash_balance),
                "interest_rate": None,
                "principal": None, "rate": None, "term_months": None,
                "issue_date": None, "maturity_date": None, "interest_accrued": None,
            })

        return pd.DataFrame(records)
