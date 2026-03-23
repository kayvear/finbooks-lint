"""Specialist validation agent — one call per PDF.

run_validation_agent(pdf_path, mode) → ComparisonResult

The agent is given the MCP server for the requested mode and a system prompt.
It calls tools to extract, compare, and write the break report.

Result capture:
    We intercept the ToolUseBlock for "write_break_report" in the message stream.
    The agent's call to that tool is both the output mechanism (it writes the CSV)
    and our extraction hook (we parse the breaks_json argument to build a
    ComparisonResult to return to the orchestrator).
"""

from __future__ import annotations

import json
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ToolUseBlock,
    query,
)

from finbooks.agents.mcp_server import create_server
from finbooks.agents.modes.hybrid.repl_tool import reset_namespace
from finbooks.comparison.models import Break, ComparisonResult
from finbooks.settings import settings

_FIXED_SYSTEM_PROMPT = """\
You are a financial statement validator.

For each PDF statement, follow these steps in order — do not skip any step:
1. Call extract_pdf(pdf_path) to extract structured data from the PDF.
2. Call get_books_data(customer_id, period) to load the books-of-record snapshot.
3. Call compare_statement(extracted_json, books_json) to run all 4 discrepancy checks.
   Pass the full JSON strings from steps 1 and 2 as arguments.
   compare_statement returns a JSON array of breaks — use it directly in step 4.
4. Call write_break_report(
       breaks_json=<the exact JSON string returned by compare_statement>,
       customer_id=<customer_id>,
       period=<period>
   ).

You MUST call write_break_report as the final step, even if no breaks were found.
"""


def _customer_period_from_path(pdf_path: Path) -> tuple[str, str]:
    stem = pdf_path.stem
    parts = stem.rsplit("_", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return stem, "unknown"


async def run_validation_agent(pdf_path: Path, mode: str) -> ComparisonResult:
    """Run the specialist agent for one PDF and return its ComparisonResult."""
    customer_id, period = _customer_period_from_path(pdf_path)

    if mode == "hybrid":
        reset_namespace()  # fresh exec namespace for each validation run
        from finbooks.agents.modes.hybrid.prompts import SPECIALIST_SYSTEM_PROMPT
        system_prompt = SPECIALIST_SYSTEM_PROMPT
    else:
        system_prompt = _FIXED_SYSTEM_PROMPT

    server = create_server(mode)

    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        mcp_servers={"finbooks": server},
        model=settings.specialist_model,
        permission_mode="bypassPermissions",
        max_turns=25,
    )

    user_prompt = (
        f"Validate the statement at: {pdf_path}\n"
        f"customer_id: {customer_id}\n"
        f"period: {period}"
    )

    # Capture the write_break_report call to extract breaks
    captured: dict | None = None

    async for msg in query(prompt=user_prompt, options=options):
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if (
                    isinstance(block, ToolUseBlock)
                    and block.name.endswith("write_break_report")
                ):
                    captured = block.input

    if captured is None:
        return ComparisonResult(customer_id=customer_id, period=period, breaks=[])
    raw_breaks = json.loads(captured.get("breaks_json", "[]"))
    breaks = [
        Break(customer_id=customer_id, period=period, **{k: v for k, v in b.items() if k not in ("customer_id", "period")})
        for b in raw_breaks
    ]
    return ComparisonResult(
        customer_id=captured.get("customer_id", customer_id),
        period=captured.get("period", period),
        breaks=breaks,
    )
