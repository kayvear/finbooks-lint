# finbooks-lint

A multi-agent financial books & records validation system. Generates synthetic customer data for a bank + brokerage, produces PDF statements, injects deliberate discrepancies, and validates the books across positions, cash, P&L, and cross-section consistency using Claude agents.

---

## Status

| Phase | Description | Status |
|---|---|---|
| 1 | Data models, PDF statements, synthetic datagen | ✅ Complete |
| 2a | Discrepancy injection, PDF extraction, comparison engine, break reports | ✅ Complete |
| 2b | Claude Agent SDK — dual-mode MCP server + specialist + orchestrator | 🔨 Planned |
| 3 | General Ledger reconciliation | 🔲 Planned |
| 4 | New asset classes (bonds, margin) | 🔲 Optional |

---

## Setup

```bash
pip install -e ".[dev]"
cp .env.example .env   # add ANTHROPIC_API_KEY for Phase 2b agents
```

---

## Usage

### Phase 1 — Generate data and statements

```bash
# Standalone demo: 10 hardcoded PDFs (no datagen required)
python -m finbooks.statements.demo

# Generate synthetic parquet data → data/raw/*.parquet
python scripts/generate_data.py

# Render clean PDFs from parquet → data/statements/*.pdf
python scripts/generate_statements.py
```

### Phase 2a — Inject discrepancies and validate

```bash
# Render PDFs with deliberate errors → data/statements_injected/*.pdf
# Errors are configured in config/discrepancies.yaml
python scripts/generate_statements.py --inject

# Validate clean PDFs against books (no agents, no API key required)
python scripts/validate_statements.py --no-vision

# Validate injected PDFs
python scripts/validate_statements.py --injected --no-vision

# Outputs → data/validation/
#   breaks_{customer_id}.csv   per-customer structured break report
#   all_breaks.json            combined JSON for all customers
#   audit_memo_{timestamp}.pdf narrative audit memo PDF
```

### Phase 2b — Agent-driven validation (coming next)

```bash
# Requires ANTHROPIC_API_KEY in .env

# Hybrid mode (default): agent writes its own comparison logic
python scripts/validate_statements.py --injected --agents

# Fixed mode: agent calls pre-built comparison tools
python scripts/validate_statements.py --injected --agents --mode fixed

# Override mode via .env: FINBOOKS_AGENT_MODE=fixed
```

---

## Architecture

### Validation pipeline (Phase 2a)

```
generate_statements.py --inject
  └── StatementInjector
        └── mutates StatementData (per config/discrepancies.yaml)
              └── StatementBuilder renders injected PDF

validate_statements.py
  ├── PdfExtractor (pdfplumber)     ← primary, confidence-scored
  │     └── VisionExtractor         ← fallback if confidence < 0.7
  ├── BooksRetriever (parquet)      ← ground truth
  ├── StatementComparator           ← 4-check diff engine
  │     ├── numeric footing         sum(rows) vs reported aggregate
  │     ├── cross-section           same figure differs across sections
  │     ├── non-numeric content     wrong symbol / bad text field
  │     └── missing / extra data    row present on one side only
  └── Reports
        ├── break_report.py         CSV + JSON
        └── audit_memo.py           narrative PDF (fpdf2)
```

### Agent architecture (Phase 2b) — two modes

Both modes are implemented and selectable at runtime. See [ADR-001](docs/adr/ADR-001-agent-architecture-hybrid.md) for the full rationale.

```
agent_mode = "fixed"   (deterministic, auditable — best for production / compliance)

  Specialist receives:  extract_pdf → get_books_data → compare_statement → write_break_report
  Orchestrator:         fan-out over PDFs → write_audit_memo


agent_mode = "hybrid"  (flexible, exploratory — best for development / schema evolution)

  Specialist receives:  read_pdf_raw + read_books_raw (raw data, no logic)
                        python_repl (agent writes its own comparison code)
                        write_break_report
  Orchestrator:         fan-out over PDFs → write_audit_memo
```

The key difference: in `hybrid` mode the agent reasons about *what* to compare and writes the comparison code itself. Adding a new asset class requires a prompt update rather than a tool rewrite.

---

## Project structure

```
config/
└── discrepancies.yaml       # injection spec — which errors, which customers, severity

docs/
└── adr/                     # Architecture Decision Records
    ├── ADR-001-agent-architecture-hybrid.md   agent tool boundary: fixed vs hybrid modes
    ├── ADR-002-pdf-extraction-strategy.md     pdfplumber primary + Claude vision fallback
    ├── ADR-003-discrepancy-injection-design.md YAML spec + StatementData mutation
    └── ADR-004-storage-format.md              parquet for data, CSV/JSON for reports

src/finbooks/
├── settings.py              # config, asset universe, seed prices, agent_mode flag
├── models/                  # Pydantic — customer, account, position, transaction, statement
├── statements/              # PDF generation (fpdf2)
│   ├── base.py              # BaseStatement(FPDF) — palette, header/footer, Unicode fix
│   ├── sections/            # cover, asset_allocation, positions, transactions, banking
│   ├── renderers/           # matplotlib charts, number/date formatters
│   └── builder.py           # StatementBuilder.build(StatementData, path)
├── datagen/                 # synthetic data generation
│   ├── prices.py            # GBM simulation (seeded, reproducible)
│   ├── customers.py         # Faker-based customer generator
│   ├── transactions.py      # bank activity, trades, dividends, CD lifecycle
│   └── pipeline.py          # orchestrates all generators → parquet
├── discrepancies/           # deliberate error injection
│   ├── schema.py            # ErrorType, Injection, DiscrepancySpec (Pydantic)
│   ├── loader.py            # load_spec(yaml_path) → DiscrepancySpec
│   └── injector.py          # StatementInjector (PDF-side), BooksInjector (parquet-side)
├── extraction/              # PDF data extraction
│   ├── models.py            # ExtractedStatement / Section / Row / Field
│   ├── pdf_extractor.py     # pdfplumber — section detection, table parsing, confidence scoring
│   └── vision_extractor.py  # Claude vision — page→PNG→API→structured JSON
├── comparison/              # diff engine
│   ├── models.py            # Break, BreakSeverity, ComparisonResult
│   ├── books_retriever.py   # parquet → BooksSnapshot (ground truth)
│   └── comparator.py        # 4-check StatementComparator
├── validation/reports/      # output writers
│   ├── break_report.py      # write_csv + write_json
│   └── audit_memo.py        # AuditMemo(BaseStatement) — narrative PDF
└── storage/                 # read/write parquet + canonical paths

data/
├── raw/                     # source-of-truth parquet (gitignored)
├── statements/              # clean PDFs (gitignored)
├── statements_injected/     # PDFs with injected errors (gitignored)
└── validation/              # break reports + audit memos (gitignored)
```

---

## Data model

```
Customer
  └── Account (checking | savings | cd | brokerage)
        ├── Transaction (bank | trade | dividend | cd)
        └── Position (equity — derived from trade blotter)

Price          (GBM simulation, daily per ticker)
StatementData  (assembled for PDF rendering — injected copy used for error testing)
BooksSnapshot  (assembled from parquet for comparison — always clean ground truth)
```

---

## Key design decisions

See [`docs/adr/`](docs/adr/) for the full rationale behind each decision.

| Decision | ADR |
|---|---|
| Agent tool boundary: stable I/O + agent-written comparison vs fully pre-built tools | [ADR-001](docs/adr/ADR-001-agent-architecture-hybrid.md) |
| PDF extraction: pdfplumber primary, Claude vision fallback at confidence < 0.7 | [ADR-002](docs/adr/ADR-002-pdf-extraction-strategy.md) |
| Injection: YAML spec + pre-render StatementData mutation, never touches originals | [ADR-003](docs/adr/ADR-003-discrepancy-injection-design.md) |
| Storage: parquet for financial data, CSV+JSON for break reports | [ADR-004](docs/adr/ADR-004-storage-format.md) |
