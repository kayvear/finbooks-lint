# finbooks-lint

A multi-agent financial books & records validation system. Generates synthetic customer data for a bank + brokerage, produces PDF statements, and validates the books across positions, cash, P&L, and ledger entries.

---

## Status

| Phase | Description | Status |
|---|---|---|
| 1 | Data models, PDF statements, synthetic datagen | ✅ Complete |
| 2 | General ledger + validation rules + break reports | 🔨 Planned |
| 3 | Claude Agent SDK — orchestrator + specialist agents | 🔨 Planned |
| 4 | New asset classes (bonds, margin) | 🔲 Optional |

---

## Setup

```bash
pip install -e ".[dev]"
cp .env.example .env   # add ANTHROPIC_API_KEY for Phase 3
```

---

## Usage

```bash
# Generate 10 sample PDFs from hardcoded data (no datagen required)
python -m finbooks.statements.demo

# Generate synthetic data → data/raw/*.parquet
python scripts/generate_data.py

# Render PDFs from real data → data/statements/*.pdf
python scripts/generate_statements.py

# Override customer count
python scripts/generate_data.py --customers 100
```

---

## Project structure

```
src/finbooks/
├── settings.py          # global config, asset universe, seed prices
├── models/              # Pydantic models — customer, account, position, transaction, price, statement
├── statements/          # fpdf2 PDF generation
│   ├── base.py          # BaseStatement(FPDF) — palette, header/footer, Unicode sanitization
│   ├── sections/        # cover, asset_allocation, positions, transactions, banking
│   ├── renderers/       # matplotlib chart renderer, number/date formatters
│   ├── statement.py     # CustomerStatement — composes all sections
│   └── demo.py          # standalone 10-customer demo entry point
├── datagen/             # synthetic data generation
│   ├── universe.py      # equity + CD instrument registry
│   ├── prices.py        # GBM price simulation (seeded, reproducible)
│   ├── customers.py     # Faker-based customer generator
│   ├── accounts.py      # checking, savings, CD, brokerage accounts
│   ├── transactions.py  # bank activity, trades, dividends, CD lifecycle
│   ├── positions.py     # derives end-of-period positions from trade blotter
│   └── pipeline.py      # orchestrates all generators → parquet
└── storage/             # read_parquet / write_parquet / paths

data/
├── raw/                 # source-of-truth parquet files (gitignored)
├── processed/           # derived aggregates (gitignored)
└── statements/          # generated PDFs (gitignored)
```

---

## Data model

```
Customer
  └── Account (checking | savings | cd | brokerage)
        ├── Transaction (bank | trade | dividend | cd)
        └── Position (equity — derived from trade blotter)

Price (GBM simulation, daily OHLCV per ticker)
StatementData (assembled from above for PDF rendering)
```

---

## Key design decisions

- **Parquet** for raw/processed data — typed columns, columnar compression, fast predicate pushdown
- **GBM prices seeded** with `numpy.random.default_rng(seed)` — identical price paths every run
- **`@computed_field`** for `market_value`, `unrealized_pnl` — derived on read, never stored
- **`normalize_text()`** override in `BaseStatement` — centralises Unicode → ASCII sanitization for fpdf2's Latin-1 font
- **CSV only for break reports** (Phase 2) — analysts need Excel-readable output; raw data stays in parquet
