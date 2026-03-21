"""
DataGenPipeline — orchestrates all generators in dependency order:
  1. Prices (no dependencies)
  2. Customers (no dependencies)
  3. Accounts (depends on customers)
  4. Transactions (depends on accounts + prices)
  5. Positions (derived from trades + prices)

Writes parquet files to data/raw/.
"""

from __future__ import annotations

import argparse

from rich.console import Console

from finbooks.datagen.accounts import AccountGenerator
from finbooks.datagen.customers import CustomerGenerator
from finbooks.datagen.positions import PositionBuilder
from finbooks.datagen.prices import PriceGenerator
from finbooks.datagen.transactions import TransactionGenerator
from finbooks.settings import settings
from finbooks.storage.io import write_parquet
from finbooks.storage.paths import StoragePaths

console = Console()


class DataGenPipeline:
    def __init__(self, num_customers: int | None = None) -> None:
        self.num_customers = num_customers or settings.num_customers

    def run(self) -> None:
        StoragePaths.ensure_dirs()

        console.print(f"[bold]Finbooks-Lint — Data Generator[/bold]")
        console.print(f"Customers: {self.num_customers}  |  Period: {settings.statement_start} – {settings.statement_end}\n")

        # 1. Prices
        console.print("[cyan]1/5[/cyan] Generating price history...")
        price_gen = PriceGenerator()
        price_histories = price_gen.generate()
        price_df = price_gen.to_dataframe(price_histories)
        write_parquet(price_df, StoragePaths.prices)
        console.print(f"     {len(price_df):,} price records for {price_df['symbol'].nunique()} symbols")

        # 2. Customers
        console.print("[cyan]2/5[/cyan] Generating customers...")
        cust_gen = CustomerGenerator()
        customers = cust_gen.generate(self.num_customers)
        cust_df = cust_gen.to_dataframe(customers)
        write_parquet(cust_df, StoragePaths.customers)
        console.print(f"     {len(customers)} customers")

        # 3. Accounts
        console.print("[cyan]3/5[/cyan] Generating accounts...")
        acct_gen = AccountGenerator()
        cash_accounts, cd_accounts, brokerage_accounts = acct_gen.generate(customers)
        acct_df = acct_gen.to_dataframe(cash_accounts, cd_accounts, brokerage_accounts)
        write_parquet(acct_df, StoragePaths.accounts)
        console.print(
            f"     {len(cash_accounts)} cash, {len(cd_accounts)} CDs, "
            f"{len(brokerage_accounts)} brokerage accounts"
        )

        # 4. Transactions
        console.print("[cyan]4/5[/cyan] Generating transactions...")
        txn_gen = TransactionGenerator()
        bank_txns = txn_gen.generate_bank_transactions(
            cash_accounts, settings.statement_start, settings.statement_end
        )
        trades, dividends = txn_gen.generate_trade_transactions(
            brokerage_accounts, price_histories, settings.statement_start, settings.statement_end
        )
        cd_txns = txn_gen.generate_cd_transactions(cd_accounts)
        txn_df = txn_gen.to_dataframe(bank_txns, trades, dividends, cd_txns)
        write_parquet(txn_df, StoragePaths.transactions)
        console.print(
            f"     {len(bank_txns)} bank, {len(trades)} trades, "
            f"{len(dividends)} dividends, {len(cd_txns)} CD transactions"
        )

        # 5. Positions
        console.print("[cyan]5/5[/cyan] Building positions from trade blotter...")
        pos_builder = PositionBuilder()
        positions = pos_builder.build(trades, price_histories)
        pos_df = pos_builder.to_dataframe(positions)
        write_parquet(pos_df, StoragePaths.positions)
        console.print(f"     {len(positions)} equity positions across {pos_df['account_id'].nunique()} accounts")

        console.print(f"\n[bold green]Done.[/bold green] Raw data written to {StoragePaths.raw}/")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic financial data.")
    parser.add_argument("--customers", type=int, default=None, help="Override num_customers from settings")
    args = parser.parse_args()
    DataGenPipeline(num_customers=args.customers).run()


if __name__ == "__main__":
    main()
