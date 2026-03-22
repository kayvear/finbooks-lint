# ADR-004: Storage Format — Parquet for Data, CSV for Break Reports

**Status:** Accepted
**Date:** 2026-03-21
**Deciders:** Krish

---

## Context

The project needs to store two categories of data:
1. **Raw and processed financial data** — customers, accounts, positions, transactions, prices
2. **Validation outputs** — break reports, audit memos

---

## Decision

| Data Category | Format | Rationale |
|---|---|---|
| Raw / processed financial data | **Parquet** | Typed, compressed, columnar — efficient for pandas filtering |
| Break reports (structured) | **CSV + JSON** | CSV per customer for easy inspection; JSON for programmatic consumption |
| Break reports (narrative) | **PDF** (fpdf2) | Human-readable audit memo consistent with customer statement style |

---

## Rationale

### Why Parquet for financial data?
- **Type preservation**: dates stay dates, decimals stay decimals — no CSV stripping of leading zeros or precision loss
- **Compression**: columnar compression is well-suited to financial data (many repeated customer IDs, symbols)
- **pandas interop**: `pd.read_parquet()` / `pd.to_parquet()` is the natural interface for the datagen and retrieval layers
- **Partial reads**: the comparison layer reads only the columns it needs without loading full rows

### Why not SQLite or a full database?
- At the current scale (10–1,000 customers), a file-based system is simpler — no server, no connection management
- Parquet files are portable and can be directly opened in DuckDB, Polars, Spark if scale demands it later
- A database schema would add migration complexity for a project in active development

### Why CSV for break reports (not parquet)?
- Break reports are small (tens to hundreds of rows) — columnar compression offers no benefit
- CSV is immediately human-readable without tooling — an auditor can open it in Excel
- The per-customer CSV pattern (`breaks_{customer_id}.csv`) makes it easy to inspect one customer at a time

### Why JSON for the combined all-breaks file?
- Hierarchical structure (customers → breaks) maps naturally to JSON
- Machine-readable for downstream systems (dashboards, ticketing systems)
- The combined JSON is the natural input for Phase 2b agent aggregation

---

## Consequences

### Positive
- Parquet handles 1,000-customer scale without schema changes
- CSV outputs are immediately usable without tooling
- Clean separation: parquet for computation, CSV/JSON for reporting

### Negative / Trade-offs
- Parquet requires `pyarrow` as a dependency (already present)
- Not human-readable without tooling — developers need pandas or DuckDB to inspect raw data

### Future consideration (Phase 4 — scale)
At 10,000+ customers, consider partitioned parquet (by customer_id prefix or period) or DuckDB as a query layer over the parquet files without changing the file format.
