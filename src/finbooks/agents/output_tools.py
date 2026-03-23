"""Shared output tools — used by both fixed and hybrid agent modes.

These tools are the stable write layer: they accept JSON from the agent and
delegate to the existing Phase 2a report writers.

Tools:
    write_break_report(breaks_json, customer_id, period) → CSV path
    write_audit_memo(results_json)                       → PDF path
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from claude_agent_sdk import tool

from finbooks.comparison.models import Break, ComparisonResult
from finbooks.storage.paths import StoragePaths
from finbooks.validation.reports.audit_memo import AuditMemo
from finbooks.validation.reports.break_report import write_csv


@tool(
    name="write_break_report",
    description=(
        "Write a break report CSV for one customer statement. "
        "Call this as the final step after identifying all discrepancies."
    ),
    input_schema={
        "breaks_json": str,   # JSON array of Break dicts
        "customer_id": str,
        "period": str,
    },
)
async def write_break_report(args: dict[str, Any]) -> dict[str, Any]:
    try:
        cid, period = args["customer_id"], args["period"]
        raw = json.loads(args["breaks_json"])
        breaks = [
            Break(customer_id=cid, period=period, **{k: v for k, v in b.items() if k not in ("customer_id", "period")})
            for b in raw
        ]
        out_path = StoragePaths.break_csv(args["customer_id"])
        write_csv(breaks, out_path)
        return {"content": [{"type": "text", "text": str(out_path)}]}
    except Exception as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "is_error": True}


@tool(
    name="write_audit_memo",
    description=(
        "Render a narrative audit memo PDF summarising all customer results. "
        "Call this once after all per-customer break reports are written."
    ),
    input_schema={"results_json": str},  # JSON array of ComparisonResult dicts
)
async def write_audit_memo(args: dict[str, Any]) -> dict[str, Any]:
    try:
        raw = json.loads(args["results_json"])
        results = [ComparisonResult(**r) for r in raw]
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = StoragePaths.audit_memo_pdf(run_id)
        AuditMemo().render(results, out_path)
        return {"content": [{"type": "text", "text": str(out_path)}]}
    except Exception as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "is_error": True}


OUTPUT_TOOLS = [write_break_report, write_audit_memo]
