"""Fixed-mode MCP tools — every step is a pre-built, named tool.

All comparison logic lives inside these tools.  The agent orchestrates the
call sequence; it cannot deviate from the built-in checks.

Tool call order expected by the specialist:
    extract_pdf → get_books_data → compare_statement → write_break_report
"""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

from finbooks.comparison.books_retriever import (
    BooksRetriever,
    BooksSnapshot,
    CashAccountSnapshot,
    CDAccountSnapshot,
    PositionSnapshot,
)
from finbooks.comparison.comparator import StatementComparator
from finbooks.extraction.models import ExtractedStatement
from finbooks.extraction.pdf_extractor import PdfExtractor

_FALLBACK_THRESHOLD = 0.7


def _customer_period_from_path(pdf_path: str) -> tuple[str, str]:
    """Parse customer_id and period from '{customer_id}_{period}.pdf'."""
    stem = Path(pdf_path).stem
    parts = stem.rsplit("_", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return stem, "unknown"


def _snapshot_to_dict(snapshot: BooksSnapshot) -> dict[str, Any]:
    """Serialize BooksSnapshot to a dict, including computed properties."""
    d = dataclasses.asdict(snapshot)
    d["equity_value"] = snapshot.equity_value
    d["cash_value"] = snapshot.cash_value
    d["cd_value"] = snapshot.cd_value
    d["total_value"] = snapshot.total_value
    return d


def _snapshot_from_dict(d: dict[str, Any]) -> BooksSnapshot:
    """Reconstruct BooksSnapshot from a serialized dict."""
    return BooksSnapshot(
        customer_id=d["customer_id"],
        period=d["period"],
        positions=[PositionSnapshot(**p) for p in d.get("positions", [])],
        cash_accounts=[CashAccountSnapshot(**c) for c in d.get("cash_accounts", [])],
        cd_accounts=[CDAccountSnapshot(**cd) for cd in d.get("cd_accounts", [])],
    )


@tool(
    name="extract_pdf",
    description=(
        "Extract structured data from a PDF statement using pdfplumber. "
        "Falls back to Claude vision if pdfplumber confidence is below 0.7. "
        "Returns an ExtractedStatement JSON object."
    ),
    input_schema={"pdf_path": str},
)
async def extract_pdf(args: dict[str, Any]) -> dict[str, Any]:
    try:
        pdf_path = Path(args["pdf_path"])
        customer_id, _ = _customer_period_from_path(args["pdf_path"])

        extractor = PdfExtractor(fallback_threshold=_FALLBACK_THRESHOLD)
        extracted = extractor.extract(pdf_path, customer_id)

        if extracted.confidence < _FALLBACK_THRESHOLD and os.environ.get("ANTHROPIC_API_KEY"):
            from finbooks.extraction.vision_extractor import VisionExtractor
            extracted = VisionExtractor().extract(pdf_path, customer_id)

        return {"content": [{"type": "text", "text": extracted.model_dump_json()}]}
    except Exception as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "is_error": True}


@tool(
    name="get_books_data",
    description=(
        "Retrieve the books-of-record snapshot for a customer and period. "
        "Returns a BooksSnapshot JSON object with positions, cash accounts, and CDs."
    ),
    input_schema={"customer_id": str, "period": str},
)
async def get_books_data(args: dict[str, Any]) -> dict[str, Any]:
    try:
        snapshot = BooksRetriever().get_snapshot(args["customer_id"], args["period"])
        return {"content": [{"type": "text", "text": json.dumps(_snapshot_to_dict(snapshot))}]}
    except Exception as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "is_error": True}


@tool(
    name="compare_statement",
    description=(
        "Compare an extracted PDF statement against books data to find discrepancies. "
        "Runs 4 checks: numeric footing, cross-section, non-numeric content, missing/extra rows. "
        "Returns a JSON array of Break objects — pass it directly to write_break_report."
    ),
    input_schema={"extracted_json": str, "books_json": str},
)
async def compare_statement(args: dict[str, Any]) -> dict[str, Any]:
    try:
        extracted = ExtractedStatement.model_validate_json(args["extracted_json"])
        books = _snapshot_from_dict(json.loads(args["books_json"]))
        result = StatementComparator().compare(extracted, books)
        breaks_list = [b.model_dump() for b in result.breaks]
        return {"content": [{"type": "text", "text": json.dumps(breaks_list)}]}
    except Exception as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "is_error": True}
