from pathlib import Path

from finbooks.settings import settings


class StoragePaths:
    raw = settings.data_dir / "raw"
    processed = settings.data_dir / "processed"
    statements = settings.data_dir / "statements"

    customers = raw / "customers.parquet"
    accounts = raw / "accounts.parquet"
    positions = raw / "positions.parquet"
    transactions = raw / "transactions.parquet"
    prices = raw / "prices.parquet"

    account_summaries = processed / "account_summaries.parquet"
    pnl_by_account = processed / "pnl_by_account.parquet"

    @classmethod
    def ensure_dirs(cls) -> None:
        for d in (cls.raw, cls.processed, cls.statements):
            d.mkdir(parents=True, exist_ok=True)

    @classmethod
    def statement_pdf(cls, customer_id: str, period_label: str) -> Path:
        return cls.statements / f"{customer_id}_{period_label}.pdf"
