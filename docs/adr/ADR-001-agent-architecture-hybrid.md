# ADR-001: Agent Tool Boundary — Stable I/O Wrappers vs Agent-Written Comparison Logic

**Status:** Accepted
**Date:** 2026-03-21
**Deciders:** Krish

---

## Context

The agent validation workflow requires a decision about *how much* logic is pre-built into tools vs how much the agent reasons and generates dynamically at runtime.

Three approaches were considered:

### Option A — Fixed-tool orchestration
Pre-build a tool for every step (`extract_pdf`, `compare_statement`, `write_break_report`). The agent calls them in sequence. All validation logic lives inside the tools.

### Option B — Full code-writing agent
Give the agent only a `python_repl` execution tool and a description of the problem. The agent writes all extraction, comparison, and reporting code from scratch each run.

### Option C — Hybrid
Split responsibility by stability:
- **I/O tools are pre-built and stable**: `read_pdf_raw` and `read_books_raw` handle data access (pdfplumber, parquet reads). Deterministic, fast, auditable.
- **Comparison logic is agent-written**: the agent receives both data payloads and writes Python code in a `python_repl` tool. The agent decides *what* to compare and *how*.
- **Output tools are pre-built and stable**: `write_break_report` and `write_audit_memo` persist results in canonical formats.

---

## Decision

**Both Option A (fixed) and Option C (hybrid) are implemented and retained.**

Neither approach is rejected — they have genuinely different trade-offs, and the right choice depends on the operational context (exploratory vs audited, development vs production). Both modes are available via the `agent_mode` feature flag.

### `agent_mode = "fixed"` — pre-built tools for every step

The agent receives:
1. `extract_pdf(pdf_path)` → full `ExtractedStatement` (pdfplumber + vision fallback)
2. `get_books_data(customer_id, period)` → `BooksSnapshot` JSON
3. `compare_statement(extracted, books)` → `list[Break]` JSON
4. `write_break_report(breaks_json, customer_id)` → CSV path
5. `write_audit_memo(all_breaks_json)` → PDF path

All comparison logic is pre-built. The agent orchestrates the call sequence and interprets results but cannot deviate from the built-in checks.

### `agent_mode = "hybrid"` — stable I/O + agent-written comparison

The agent receives:
1. `read_pdf_raw(pdf_path)` → raw extracted tables + text as JSON (no logic)
2. `read_books_raw(customer_id, period)` → raw parquet data as JSON (no logic)
3. `python_repl(code)` → sandboxed Python execution; agent writes its own comparison
4. `write_break_report(breaks_json, customer_id)` → CSV path
5. `write_audit_memo(all_breaks_json)` → PDF path

The agent's system prompt describes the PDF structure, the types of discrepancies to look for, and the expected `breaks_json` output schema.

---

## Feature Flag

### Via `.env` file
```
FINBOOKS_AGENT_MODE=fixed    # or: hybrid
```

### Via CLI (overrides `.env`)
```bash
python scripts/validate_statements.py --agents --mode fixed
python scripts/validate_statements.py --agents --mode hybrid
```

### Via `settings.py`
```python
agent_mode: Literal["fixed", "hybrid"] = "hybrid"  # default
```

The MCP server reads `settings.agent_mode` at startup and registers the appropriate tool set. Only one tool set is active per run — there is no mixing.

---

## Rationale

### When to use `fixed` mode
- **Audited / production runs** where every step must be traceable to a named, versioned function
- **Regression testing** — same PDF → same breaks, every run
- **Compliance reviews** — "what ran against this data?" has a deterministic answer
- **Performance-sensitive** runs — no LLM tokens spent on comparison logic

### When to use `hybrid` mode
- **Exploratory validation** — discovering unanticipated issues beyond the spec
- **Schema evolution** — adding a new asset class or changing column headers requires only a prompt update
- **Development / research** — understanding what the agent notices vs what fixed rules find
- **Situations where the PDF layout varies** — agent can adapt dynamically

### Why Option B (full code-writing) was not retained
Even with `hybrid` mode, data access (pdfplumber, parquet reads) remains in stable pre-built tools. Fully dynamic I/O would:
- Add LLM cost and latency to mechanical operations that don't benefit from reasoning
- Create a security surface: fully LLM-generated code running against customer data with no fixed boundary
- Make runs non-reproducible even at the I/O layer

Option B is the logical extreme of `hybrid` mode and is not retained as a named mode.

---

## Implementation: Tool Registration by Mode

```python
# agents/mcp_server.py

def create_server(mode: str):
    if mode == "fixed":
        from finbooks.agents.modes.fixed import tools as fixed_tools
        return create_sdk_mcp_server(tools=fixed_tools)
    else:  # "hybrid"
        from finbooks.agents.modes.hybrid import tools as hybrid_tools
        return create_sdk_mcp_server(tools=hybrid_tools)
```

```
src/finbooks/agents/
├── modes/
│   ├── fixed/
│   │   ├── __init__.py          # exports: tools list
│   │   └── tools.py             # extract_pdf, get_books_data, compare_statement
│   └── hybrid/
│       ├── __init__.py          # exports: tools list
│       ├── io_tools.py          # read_pdf_raw, read_books_raw
│       ├── repl_tool.py         # python_repl
│       └── prompts.py           # specialist system prompt with PDF structure + invariants
├── output_tools.py              # write_break_report, write_audit_memo (shared by both modes)
├── mcp_server.py                # create_server(mode) dispatcher
├── validation_agent.py          # specialist — prompt varies by mode
└── orchestrator.py             # orchestrator — same for both modes
```

---

## Trade-off Summary

| Dimension | `fixed` mode | `hybrid` mode |
|---|---|---|
| Determinism | ✅ Same input → same breaks | ❌ Comparison code may vary |
| Auditability | ✅ Named, versioned functions | ⚠️ Agent-generated code at runtime |
| Unit-testability | ✅ Full coverage possible | ❌ Comparison logic generated at runtime |
| Schema flexibility | ❌ Column header change = tool fix | ✅ Prompt update only |
| Unanticipated findings | ❌ Only what tools detect | ✅ Agent can reason beyond the spec |
| Token cost | ✅ Minimal (tool calls only) | ⚠️ Agent generates comparison code |
| Best for | Production, compliance, regression | Exploration, development, schema evolution |

---

## Alternatives Considered and Not Retained

| Option | Disposition |
|---|---|
| Full code-writing agent (Option B) | Not retained — LLM involvement in mechanical I/O adds cost/risk with no benefit |

---

## Related ADRs

- **[ADR-005 — python_repl Execution Safety](ADR-005-python-repl-execution-safety.md)** — Documents where agent-generated code runs (full call chain), why `python_repl` exists as an MCP tool rather than using Bash, and options for safely running hybrid mode in production (RestrictedPython, subprocess sandbox, sidecar microservice).
