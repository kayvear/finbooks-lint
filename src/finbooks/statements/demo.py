"""
Demo entry point — produces 10 sample PDFs from hardcoded data.
No datagen, no storage, no agents required.

    python -m finbooks.statements.demo
"""

from __future__ import annotations

import argparse
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

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
    DividendTransaction,
    TradeTransaction,
    TradeSide,
)
from finbooks.statements.builder import StatementBuilder
from finbooks.storage.paths import StoragePaths

console = Console()

PERIOD = StatementPeriod(
    start_date=date(2024, 10, 1),
    end_date=date(2024, 12, 31),
    frequency="quarterly",
)

# ── Hardcoded demo customers ──────────────────────────────────────────────────

_DEMO_PROFILES: list[dict] = [
    {"first": "Alexandra", "last": "Chen",     "tier": CustomerTier.PRIVATE,  "equity": 285000, "cash": 42000,  "cd": 100000},
    {"first": "Marcus",    "last": "Williams",  "tier": CustomerTier.RETAIL,   "equity": 48500,  "cash": 12300,  "cd": 25000},
    {"first": "Priya",     "last": "Patel",     "tier": CustomerTier.RETAIL,   "equity": 0,      "cash": 34000,  "cd": 50000},
    {"first": "James",     "last": "O'Brien",   "tier": CustomerTier.PRIVATE,  "equity": 520000, "cash": 88000,  "cd": 200000},
    {"first": "Sofia",     "last": "Rodriguez", "tier": CustomerTier.RETAIL,   "equity": 21000,  "cash": 8500,   "cd": 0},
    {"first": "David",     "last": "Kim",       "tier": CustomerTier.RETAIL,   "equity": 67000,  "cash": 15000,  "cd": 30000},
    {"first": "Natalie",   "last": "Thompson",  "tier": CustomerTier.RETAIL,   "equity": 0,      "cash": 55000,  "cd": 75000},
    {"first": "Robert",    "last": "Nakamura",  "tier": CustomerTier.PRIVATE,  "equity": 410000, "cash": 62000,  "cd": 150000},
    {"first": "Amara",     "last": "Okafor",    "tier": CustomerTier.RETAIL,   "equity": 33000,  "cash": 9800,   "cd": 0},
    {"first": "William",   "last": "Foster",    "tier": CustomerTier.RETAIL,   "equity": 15500,  "cash": 7200,   "cd": 20000},
]

_STATES = ["NY", "CA", "TX", "FL", "IL", "WA", "MA", "GA", "CO", "OH"]
_STREETS = [
    "142 Elm Street", "89 Oak Avenue", "501 Maple Drive", "37 Cedar Lane",
    "1024 Pine Road", "76 Birch Court", "220 Walnut Blvd", "15 Spruce Way",
    "330 Willow Path", "9 Chestnut Place",
]
_CITIES = [
    "New York", "Los Angeles", "Houston", "Miami", "Chicago",
    "Seattle", "Boston", "Atlanta", "Denver", "Columbus",
]


def _make_customer(profile: dict, idx: int) -> Customer:
    cid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"demo-customer-{idx}"))
    return Customer(
        customer_id=cid,
        first_name=profile["first"],
        last_name=profile["last"],
        email=f"{profile['first'].lower()}.{profile['last'].lower().replace(' ', '')}@example.com",
        phone=f"212-555-{1000 + idx:04d}",
        address=Address(
            street=_STREETS[idx],
            city=_CITIES[idx],
            state=_STATES[idx],
            zip_code=f"{10000 + idx * 1111:05d}",
        ),
        tier=profile["tier"],
        date_of_birth=date(1965 + idx * 3, (idx % 12) + 1, (idx % 28) + 1),
        created_at=date(2018, 1, 15),
    )


def _make_statement_data(customer: Customer, profile: dict, idx: int) -> StatementData:
    cid = customer.customer_id
    equity_val = Decimal(str(profile["equity"]))
    cash_val = Decimal(str(profile["cash"]))
    cd_val = Decimal(str(profile["cd"]))
    total = equity_val + cash_val + cd_val
    opening = (total * Decimal("0.962")).quantize(Decimal("0.01"))

    allocation = AssetAllocationBreakdown(
        equity_value=equity_val,
        cash_value=cash_val,
        cd_value=cd_val,
    )

    summary = StatementSummary(
        customer=customer,
        period=PERIOD,
        allocation=allocation,
        opening_value=opening,
        closing_value=total,
    )

    # ── Accounts ──────────────────────────────────────────────────────────────
    chk_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{cid}-checking"))
    sav_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{cid}-savings"))
    brk_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{cid}-brokerage"))
    cd_id  = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{cid}-cd"))

    cash_split = cash_val * Decimal("0.65")
    savings_split = cash_val * Decimal("0.35")

    checking = CashAccount(
        account_id=chk_id, customer_id=cid,
        account_type=AccountType.CHECKING,
        opened_date=date(2018, 1, 15),
        current_balance=cash_split.quantize(Decimal("0.01")),
        opening_balance=(cash_split * Decimal("0.95")).quantize(Decimal("0.01")),
        interest_rate=Decimal("0.00"),
    )
    savings = CashAccount(
        account_id=sav_id, customer_id=cid,
        account_type=AccountType.SAVINGS,
        opened_date=date(2018, 3, 1),
        current_balance=savings_split.quantize(Decimal("0.01")),
        opening_balance=(savings_split * Decimal("0.97")).quantize(Decimal("0.01")),
        interest_rate=Decimal("0.042"),
    )

    cash_accounts = [checking, savings]

    cd_accounts: list[CDAccount] = []
    if cd_val > 0:
        cd_accounts.append(CDAccount(
            account_id=cd_id, customer_id=cid,
            account_type=AccountType.CD,
            opened_date=date(2024, 4, 1),
            principal=cd_val,
            rate=Decimal("0.051"),
            term_months=12,
            issue_date=date(2024, 4, 1),
            maturity_date=date(2025, 4, 1),
            interest_accrued=(cd_val * Decimal("0.051") * Decimal("0.75")).quantize(Decimal("0.01")),
        ))

    brokerage_accounts: list[BrokerageAccount] = []
    equity_positions: list[EquityPosition] = []
    if equity_val > 0:
        brokerage_accounts.append(BrokerageAccount(
            account_id=brk_id, customer_id=cid,
            account_type=AccountType.BROKERAGE,
            opened_date=date(2020, 6, 1),
            cash_balance=Decimal("1500.00"),
            opening_cash_balance=Decimal("1200.00"),
        ))

        # Distribute equity across 3-5 positions
        symbols_qty = [
            ("AAPL", Decimal("50"), Decimal("195.00"), Decimal("229.00")),
            ("MSFT", Decimal("30"), Decimal("380.00"), Decimal("425.00")),
            ("SPY",  Decimal("20"), Decimal("520.00"), Decimal("578.00")),
            ("NVDA", Decimal("15"), Decimal("85.00"),  Decimal("135.00")),
            ("GOOGL",Decimal("25"), Decimal("148.00"), Decimal("167.00")),
        ]
        # Scale quantities to approximate equity_val
        base_value = sum(float(q) * float(cp) for _, q, _, cp in symbols_qty)
        scale = float(equity_val) / base_value if base_value else 1.0

        for sym, qty, cost, curr in symbols_qty[:3 + (idx % 3)]:
            scaled_qty = Decimal(str(round(float(qty) * scale, 0)))
            if scaled_qty < 1:
                scaled_qty = Decimal("1")
            equity_positions.append(EquityPosition(
                position_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{cid}-{sym}")),
                account_id=brk_id,
                symbol=sym,
                quantity=scaled_qty,
                cost_basis_per_share=cost,
                current_price=curr,
            ))

    # ── Sample transactions (bank) ────────────────────────────────────────────
    bank_transactions: list[BankTransaction] = [
        BankTransaction(
            transaction_id=str(uuid.uuid4()),
            account_id=chk_id,
            transaction_date=date(2024, 10, 1),
            amount=Decimal("0.00"),
            description="Opening Balance",
            running_balance=checking.opening_balance,
            txn_type=BankTxnType.DEPOSIT,
        ),
        BankTransaction(
            transaction_id=str(uuid.uuid4()),
            account_id=chk_id,
            transaction_date=date(2024, 10, 15),
            amount=Decimal("4500.00"),
            description="Direct Deposit — Payroll",
            running_balance=checking.opening_balance + Decimal("4500.00"),
            txn_type=BankTxnType.DEPOSIT,
        ),
        BankTransaction(
            transaction_id=str(uuid.uuid4()),
            account_id=chk_id,
            transaction_date=date(2024, 11, 1),
            amount=Decimal("-1200.00"),
            description="ACH Payment — Rent",
            running_balance=checking.opening_balance + Decimal("3300.00"),
            txn_type=BankTxnType.WITHDRAWAL,
        ),
        BankTransaction(
            transaction_id=str(uuid.uuid4()),
            account_id=chk_id,
            transaction_date=date(2024, 11, 15),
            amount=Decimal("4500.00"),
            description="Direct Deposit — Payroll",
            running_balance=checking.opening_balance + Decimal("7800.00"),
            txn_type=BankTxnType.DEPOSIT,
        ),
        BankTransaction(
            transaction_id=str(uuid.uuid4()),
            account_id=chk_id,
            transaction_date=date(2024, 12, 31),
            amount=Decimal("-350.00"),
            description="ACH Payment — Utilities",
            running_balance=checking.current_balance,
            txn_type=BankTxnType.WITHDRAWAL,
        ),
    ]

    # ── Sample trade transactions ─────────────────────────────────────────────
    trade_transactions: list[TradeTransaction] = []
    dividend_transactions: list[DividendTransaction] = []

    if equity_positions:
        pos0 = equity_positions[0]
        buy_qty = Decimal("5")
        gross = buy_qty * pos0.current_price
        trade_transactions.append(TradeTransaction(
            transaction_id=str(uuid.uuid4()),
            account_id=brk_id,
            transaction_date=date(2024, 10, 8),
            symbol=pos0.symbol,
            side=TradeSide.BUY,
            quantity=buy_qty,
            price_per_share=pos0.current_price,
            commission=Decimal("0.00"),
            gross_amount=gross,
            amount=-gross,
            description=f"Buy {pos0.symbol}",
            running_balance=Decimal("1200.00") - gross,
        ))

        # Dividend on AAPL (quarterly)
        if any(p.symbol == "AAPL" for p in equity_positions):
            aapl_pos = next(p for p in equity_positions if p.symbol == "AAPL")
            div_per_share = Decimal("0.25")
            div_total = (aapl_pos.quantity * div_per_share).quantize(Decimal("0.01"))
            dividend_transactions.append(DividendTransaction(
                transaction_id=str(uuid.uuid4()),
                account_id=brk_id,
                transaction_date=date(2024, 11, 15),
                symbol="AAPL",
                shares_held=aapl_pos.quantity,
                dividend_per_share=div_per_share,
                amount=div_total,
                description=f"Dividend — AAPL Q4 2024",
                running_balance=Decimal("1200.00") + div_total,
            ))

    return StatementData(
        summary=summary,
        cash_accounts=cash_accounts,
        cd_accounts=cd_accounts,
        brokerage_accounts=brokerage_accounts,
        equity_positions=equity_positions,
        bank_transactions=bank_transactions,
        trade_transactions=trade_transactions,
        dividend_transactions=dividend_transactions,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate demo statements for 10 sample customers.")
    parser.add_argument(
        "--output-dir", type=Path,
        default=StoragePaths.statements,
        help="Directory to write PDFs (default: data/statements/)",
    )
    args = parser.parse_args()

    StoragePaths.ensure_dirs()
    builder = StatementBuilder()

    console.print("[bold]Finbooks-Lint — Demo Statement Generator[/bold]")
    console.print(f"Period: {PERIOD.label}  |  Output: {args.output_dir}\n")

    with Progress(console=console) as progress:
        task = progress.add_task("Rendering statements...", total=len(_DEMO_PROFILES))

        for idx, profile in enumerate(_DEMO_PROFILES):
            customer = _make_customer(profile, idx)
            data = _make_statement_data(customer, profile, idx)

            out_path = Path(args.output_dir) / f"{customer.customer_id}_{PERIOD.label}.pdf"
            builder.build(data, out_path)

            progress.advance(task)
            console.print(f"  [green]✓[/green] {customer.full_name} → {out_path.name}")

    console.print(f"\n[bold green]Done.[/bold green] {len(_DEMO_PROFILES)} PDFs written to {args.output_dir}")


if __name__ == "__main__":
    main()
