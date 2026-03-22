"""
Generate PDF statements from real datagen output (data/raw/*.parquet).

Usage:
    python scripts/generate_statements.py
    python scripts/generate_statements.py --customer-id <uuid>
    python scripts/generate_statements.py --inject
    python scripts/generate_statements.py --inject --spec config/discrepancies.yaml

When --inject is given, deliberate discrepancies from the spec are applied to each
customer's StatementData before the PDF is rendered.  The injected PDFs are written
to data/statements_injected/ so the clean copies in data/statements/ are preserved.

Requires: data/raw/*.parquet files (run generate_data.py first).
"""
from __future__ import annotations

import argparse
import sys
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd
from rich.console import Console
from rich.progress import Progress

from finbooks.models.account import AccountType, BrokerageAccount, CashAccount, CDAccount
from finbooks.models.customer import Address, Customer, CustomerTier
from finbooks.models.position import EquityPosition
from finbooks.models.statement import (
    AssetAllocationBreakdown,
    StatementData,
    StatementPeriod,
    StatementSummary,
)
from finbooks.models.transaction import (
    BankTransaction,
    BankTxnType,
    CDTransaction,
    CDTxnType,
    DividendTransaction,
    TradeTransaction,
    TradeSide,
)
from finbooks.discrepancies.injector import StatementInjector
from finbooks.discrepancies.loader import load_spec
from finbooks.statements.builder import StatementBuilder
from finbooks.storage.io import read_parquet
from finbooks.storage.paths import StoragePaths
from finbooks.settings import settings

console = Console()

PERIOD = StatementPeriod(
    start_date=settings.statement_start,
    end_date=settings.statement_end,
    frequency="quarterly",
)


def load_statement_data(customer_row: pd.Series, all_data: dict) -> StatementData:
    cid = customer_row["customer_id"]
    accounts_df: pd.DataFrame = all_data["accounts"]
    positions_df: pd.DataFrame = all_data["positions"]
    transactions_df: pd.DataFrame = all_data["transactions"]

    customer = Customer(
        customer_id=cid,
        first_name=customer_row["first_name"],
        last_name=customer_row["last_name"],
        email=customer_row["email"],
        phone=customer_row["phone"],
        address=Address(
            street=customer_row["street"],
            city=customer_row["city"],
            state=customer_row["state"],
            zip_code=customer_row["zip_code"],
        ),
        tier=CustomerTier(customer_row["tier"]),
        date_of_birth=pd.Timestamp(customer_row["date_of_birth"]).date(),
        created_at=pd.Timestamp(customer_row["created_at"]).date(),
    )

    # Customer accounts
    cust_accounts = accounts_df[accounts_df["customer_id"] == cid]
    account_ids = set(cust_accounts["account_id"].tolist())

    cash_accounts: list[CashAccount] = []
    cd_accounts: list[CDAccount] = []
    brokerage_accounts: list[BrokerageAccount] = []

    for _, row in cust_accounts.iterrows():
        atype = row["account_type"]
        if atype in ("checking", "savings"):
            cash_accounts.append(CashAccount(
                account_id=row["account_id"], customer_id=cid,
                account_type=AccountType(atype),
                opened_date=pd.Timestamp(row["opened_date"]).date(),
                current_balance=Decimal(str(row["current_balance"])),
                opening_balance=Decimal(str(row["opening_balance"])),
                interest_rate=Decimal(str(row["interest_rate"] or 0)),
            ))
        elif atype == "cd" and pd.notna(row.get("principal")):
            cd_accounts.append(CDAccount(
                account_id=row["account_id"], customer_id=cid,
                account_type=AccountType.CD,
                opened_date=pd.Timestamp(row["opened_date"]).date(),
                principal=Decimal(str(row["principal"])),
                rate=Decimal(str(row["rate"])),
                term_months=int(row["term_months"]),
                issue_date=pd.Timestamp(row["issue_date"]).date(),
                maturity_date=pd.Timestamp(row["maturity_date"]).date(),
                interest_accrued=Decimal(str(row["interest_accrued"] or 0)),
            ))
        elif atype == "brokerage":
            brokerage_accounts.append(BrokerageAccount(
                account_id=row["account_id"], customer_id=cid,
                account_type=AccountType.BROKERAGE,
                opened_date=pd.Timestamp(row["opened_date"]).date(),
                cash_balance=Decimal(str(row["current_balance"])),
                opening_cash_balance=Decimal(str(row["opening_balance"])),
            ))

    # Positions
    brk_ids = {a.account_id for a in brokerage_accounts}
    cust_positions_df = positions_df[positions_df["account_id"].isin(brk_ids)]
    equity_positions: list[EquityPosition] = []
    for _, row in cust_positions_df.iterrows():
        equity_positions.append(EquityPosition(
            position_id=str(uuid.uuid4()),
            account_id=row["account_id"],
            symbol=row["symbol"],
            quantity=Decimal(str(row["quantity"])),
            cost_basis_per_share=Decimal(str(row["cost_basis_per_share"])),
            current_price=Decimal(str(row["current_price"])),
        ))

    # Transactions within period
    cust_txns = transactions_df[
        transactions_df["account_id"].isin(account_ids) &
        (pd.to_datetime(transactions_df["transaction_date"]).dt.date >= PERIOD.start_date) &
        (pd.to_datetime(transactions_df["transaction_date"]).dt.date <= PERIOD.end_date)
    ]

    bank_transactions: list[BankTransaction] = []
    trade_transactions: list[TradeTransaction] = []
    dividend_transactions: list[DividendTransaction] = []
    cd_transactions: list[CDTransaction] = []

    for _, row in cust_txns.iterrows():
        cat = row["txn_category"]
        txn_date = pd.Timestamp(row["transaction_date"]).date()
        common = dict(
            transaction_id=row["transaction_id"],
            account_id=row["account_id"],
            transaction_date=txn_date,
            amount=Decimal(str(row["amount"])),
            description=str(row["description"]),
            running_balance=Decimal(str(row["running_balance"])),
        )
        if cat == "bank":
            bank_transactions.append(BankTransaction(**common, txn_type=BankTxnType(row["txn_type"])))
        elif cat == "trade":
            trade_transactions.append(TradeTransaction(
                **common,
                symbol=row["symbol"], side=TradeSide(row["side"]),
                quantity=Decimal(str(row["quantity"])),
                price_per_share=Decimal(str(row["price_per_share"])),
                commission=Decimal(str(row["commission"] or 0)),
                gross_amount=Decimal(str(abs(float(row["amount"])))),
            ))
        elif cat == "dividend":
            dividend_transactions.append(DividendTransaction(
                **common,
                symbol=row["symbol"],
                shares_held=Decimal(str(row["quantity"])),
                dividend_per_share=Decimal(str(row["price_per_share"])),
            ))
        elif cat == "cd":
            cd_transactions.append(CDTransaction(**common, txn_type=CDTxnType(row["txn_type"])))

    # Compute allocation
    equity_val = sum(p.market_value for p in equity_positions)
    cash_val = sum(a.current_balance for a in cash_accounts)
    cd_val = sum(a.current_value for a in cd_accounts)
    total = equity_val + cash_val + cd_val
    opening = (total * Decimal("0.96")).quantize(Decimal("0.01"))

    allocation = AssetAllocationBreakdown(
        equity_value=equity_val, cash_value=cash_val, cd_value=cd_val
    )
    summary = StatementSummary(
        customer=customer, period=PERIOD,
        allocation=allocation, opening_value=opening, closing_value=total,
    )

    return StatementData(
        summary=summary,
        cash_accounts=cash_accounts, cd_accounts=cd_accounts,
        brokerage_accounts=brokerage_accounts,
        equity_positions=equity_positions,
        bank_transactions=bank_transactions,
        trade_transactions=trade_transactions,
        dividend_transactions=dividend_transactions,
        cd_transactions=cd_transactions,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate PDF statements from parquet data.")
    parser.add_argument("--customer-id", type=str, default=None)
    parser.add_argument(
        "--inject", action="store_true",
        help="Apply discrepancy injections from --spec before rendering PDFs.",
    )
    parser.add_argument(
        "--spec", type=str,
        default=str(Path(__file__).parent.parent / "config" / "discrepancies.yaml"),
        help="Path to discrepancies YAML spec (default: config/discrepancies.yaml).",
    )
    args = parser.parse_args()

    for path in (StoragePaths.customers, StoragePaths.accounts,
                 StoragePaths.positions, StoragePaths.transactions):
        if not path.exists():
            console.print(f"[red]Missing:[/red] {path}. Run generate_data.py first.")
            return

    all_data = {
        "customers": read_parquet(StoragePaths.customers),
        "accounts": read_parquet(StoragePaths.accounts),
        "positions": read_parquet(StoragePaths.positions),
        "transactions": read_parquet(StoragePaths.transactions),
    }

    customers_df = all_data["customers"]
    if args.customer_id:
        customers_df = customers_df[customers_df["customer_id"] == args.customer_id]

    # Injection setup
    injector: StatementInjector | None = None
    output_dir = StoragePaths.statements
    if args.inject:
        spec = load_spec(args.spec)
        injector = StatementInjector(spec)
        output_dir = settings.data_dir / "statements_injected"
        output_dir.mkdir(parents=True, exist_ok=True)
        console.print(f"[yellow]Injection mode:[/yellow] {len(spec.injections)} rule(s) from {args.spec}")

    StoragePaths.ensure_dirs()
    builder = StatementBuilder()

    label = "[bold yellow]INJECTED[/bold yellow]" if args.inject else "[bold]Clean[/bold]"
    console.print(f"[bold]Finbooks-Lint — Statement Generator[/bold] ({label})")
    console.print(f"Generating {len(customers_df)} statements for period {PERIOD.label}\n")

    with Progress(console=console) as progress:
        task = progress.add_task("Rendering...", total=len(customers_df))
        for _, row in customers_df.iterrows():
            cid = row["customer_id"]
            data = load_statement_data(row, all_data)
            if injector is not None:
                data = injector.inject(data, cid)
            out = output_dir / f"{cid}_{PERIOD.label}.pdf"
            builder.build(data, out)
            progress.advance(task)
            console.print(f"  [green]✓[/green] {row['first_name']} {row['last_name']} → {out.name}")

    console.print(f"\n[bold green]Done.[/bold green]")


if __name__ == "__main__":
    main()
