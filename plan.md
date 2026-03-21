# Finbooks-Lint: Financial Books & Records Validation System

## Phased Roadmap

| Phase | Scope | Customers | Asset Classes | Status |
|---|---|---|---|---|
| **1** | PDF template + data models + 10-customer demo data | 10 | Cash, CDs, Equities | 🔨 In Progress |
| 2 | Scale to 1,000 customers, add fixed income + margin | 1,000 | + Bonds, Margin | ⏳ Planned |
| 3 | Claude Agent SDK orchestrator + specialist agents | 1,000 | All | ⏳ Planned |
| 4 | Validation rules engine + break reports | 1,000 | All | ⏳ Planned |

---

## Phase 1 — Statements + Data (10 customers)

### Asset classes in scope
- **Cash** — checking and savings accounts
- **CDs** — certificates of deposit (fixed term, fixed rate)
- **Equities** — common stocks and ETFs

### Build sequence
- [x] Project scaffold (pyproject.toml, directories)
- [ ] `src/finbooks/settings.py` + `storage/`
- [ ] Pydantic models: customer, account, position, transaction, price, statement
- [ ] `statements/base.py` — PDF base class with neutral palette + header/footer
- [ ] `statements/renderers/` — matplotlib chart renderer + formatters
- [ ] `statements/sections/` — cover, asset_allocation, positions, transactions, banking
- [ ] `statements/statement.py` + `statements/builder.py`
- [ ] `statements/demo.py` — 10-PDF demo (hardcoded then wired to datagen)
- [ ] `datagen/` — universe, prices, customers, accounts, transactions, pipeline
- [ ] `scripts/` — generate_data.py, generate_statements.py

### Run it
```bash
pip install -e ".[dev]"
python -m finbooks.statements.demo          # → data/statements/*.pdf
python scripts/generate_data.py            # → data/raw/*.parquet
python scripts/generate_statements.py     # → data/statements/*.pdf from real data
pytest tests/
```

---

## Phase 2 — Scale + Expand (planned)
- 1,000 customers
- Fixed income: treasuries, corporate bonds
- Margin accounts: margin balance, buying power, Reg-T
- Quarterly + monthly statement variants

## Phase 3 — Claude Agent SDK (planned)
- Orchestrator (`claude-opus-4-6`) dispatches to specialist agents (`claude-sonnet-4-6`)
- Specialists: DataGen, Pricing, Statement, Validation
- Tools via `@tool` + `create_sdk_mcp_server`

## Phase 4 — Validation (planned)
- Position reconciliation: `SUM(buy_qty) - SUM(sell_qty)` = current position qty
- Cash reconciliation: opening + credits − debits = closing balance (tolerance $0.01)
- P&L attribution: realized P&L ties to GL; unrealized = mark-to-market (tolerance $0.10)
- Statement vs. ledger: statement figures match general ledger
- Output: `data/processed/validation_breaks.csv` + PDF summary report
