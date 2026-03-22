# ADR-003: Discrepancy Injection Design — YAML Spec + StatementData Mutation

**Status:** Accepted
**Date:** 2026-03-21
**Deciders:** Krish

---

## Context

To test the validation agents, deliberate errors need to be introduced into either the PDF statements or the books & records data. The key decisions were: how to configure which errors to inject, and where in the pipeline to apply them.

---

## Decision

### Configuration: YAML spec file (`config/discrepancies.yaml`)

Injections are declared in a version-controlled YAML file. Each entry specifies:
- `error_type`: one of `numeric_footing`, `cross_section`, `non_numeric_content`, `missing_extra_data`
- `target_section` / `target_field`: where in the statement to corrupt
- `side`: `pdf` (corrupt before rendering) or `books` (corrupt the parquet copy)
- `magnitude` / `swap_value` / `drop_index`: type-specific parameters
- `customer_id`: `"all"` or a specific UUID
- `severity`: `high` / `medium` / `low`

### Injection point: pre-render mutation (PDF-side)

For PDF-side injections, `StatementInjector` receives a `StatementData` object and returns a new (deep-copied) one with the corruption applied — *before* it is passed to `StatementBuilder.build()`. The original `StatementData` is never mutated.

For books-side injections, `BooksInjector` writes a dirty copy of the parquet files to `data/raw_injected/`. Original files in `data/raw/` are never touched.

---

## Rationale

### Why YAML config vs hardcoded injections?
- Injections can be changed without code modifications — useful for testing different break scenarios
- The spec is version-controlled and reviewable — "what errors were injected in this test run" is always answerable
- Supports partial injection (target one customer, one error type) for debugging

### Why mutate StatementData, not the rendered PDF?
Two alternatives were considered:
1. **Mutate the PDF bytes after rendering** (e.g. with pikepdf) — complex, brittle, hard to predict how pdfplumber will read modified binary
2. **Mutate StatementData before rendering** — clean, uses the existing type system, and the injector operates on well-typed Pydantic objects

Option 2 was selected. The `model_copy(update=...)` pattern creates new Pydantic objects without breaking immutability.

### Why keep dirty parquet in a separate directory?
- `data/raw/` is always the clean ground truth — never modified
- Validation scripts can be pointed at either `--raw-dir data/raw` (clean) or `--raw-dir data/raw_injected` (dirty) to simulate books-side errors
- Avoids accidental data corruption during development

### Why not inject at the comparison layer instead?
Injecting at the data layer (StatementData or parquet) is more realistic — it simulates actual upstream data quality issues, not just comparison logic bugs.

---

## Four Error Types and How They Map

| Error Type | What It Simulates | Injection Mechanism |
|---|---|---|
| `numeric_footing` | Reported aggregate ≠ sum of underlying rows | Inflate `allocation.equity_value` while leaving position rows unchanged |
| `cross_section` | Same figure differs between two sections | Inflate `summary.closing_value` independently of `allocation.total_value` |
| `non_numeric_content` | Wrong ticker, transposed name, bad account number | Replace `equity_positions[i].symbol` with a garbage string |
| `missing_extra_data` | Row in PDF not in books (or vice versa) | Remove `equity_positions[i]` from the list before rendering |

---

## Consequences

### Positive
- YAML spec makes injection scenarios reproducible and documentable
- Clean/dirty data separation means validation can be run against either independently
- Deep-copy mutation pattern is safe — no risk of corrupting clean data in memory
- Injection IDs are tracked through to break reports for full traceability

### Negative / Trade-offs
- PDF-side injection currently only supports `StatementData`-level fields — cannot inject at the rendering level (e.g. add a row to a table that has no corresponding model field)
- Books-side injection creates a full parquet copy even for a single-field change (minor storage overhead)

### Future consideration
If more granular PDF-side injection is needed (e.g. corrupt a specific formatted string in a footer), consider a post-render injection step using `pypdfium2` or `pikepdf`.
