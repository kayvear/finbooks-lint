"""Hybrid-mode I/O tools — stable data access layer.

These tools hand raw data to the agent without performing any comparison.
The agent writes its own comparison logic via python_repl.

Tools:
    read_pdf_raw(pdf_path)                    → ExtractedStatement JSON
    read_books_raw(customer_id, period)        → BooksSnapshot JSON
"""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

from finbooks.comparison.books_retriever import BooksRetriever
from finbooks.extraction.pdf_extractor import PdfExtractor

_FALLBACK_THRESHOLD = 0.7


@tool(
    name="read_pdf_raw",
    description=(
        "Extract all structured data from a PDF statement. "
        "Returns raw ExtractedStatement JSON — sections, rows, fields, confidence scores. "
        "Use this to load the PDF side before writing comparison logic."
    ),
    input_schema={"pdf_path": str},
)
async def read_pdf_raw(args: dict[str, Any]) -> dict[str, Any]:
    try:
        pdf_path = Path(args["pdf_path"])
        stem = pdf_path.stem
        parts = stem.rsplit("_", 1)
        customer_id = parts[0] if len(parts) == 2 else stem

        extractor = PdfExtractor(fallback_threshold=_FALLBACK_THRESHOLD)
        extracted = extractor.extract(pdf_path, customer_id)

        if extracted.confidence < _FALLBACK_THRESHOLD and os.environ.get("ANTHROPIC_API_KEY"):
            from finbooks.extraction.vision_extractor import VisionExtractor
            extracted = VisionExtractor().extract(pdf_path, customer_id)

        return {"content": [{"type": "text", "text": extracted.model_dump_json()}]}
    except Exception as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "is_error": True}


@tool(
    name="read_books_raw",
    description=(
        "Retrieve books-of-record data for a customer and period. "
        "Returns BooksSnapshot JSON with positions, cash accounts, CD accounts, "
        "and computed totals (equity_value, cash_value, cd_value). "
        "Use this to load the books side before writing comparison logic."
    ),
    input_schema={"customer_id": str, "period": str},
)
async def read_books_raw(args: dict[str, Any]) -> dict[str, Any]:
    try:
        snapshot = BooksRetriever().get_snapshot(args["customer_id"], args["period"])
        d = dataclasses.asdict(snapshot)
        d["equity_value"] = snapshot.equity_value
        d["cash_value"] = snapshot.cash_value
        d["cd_value"] = snapshot.cd_value
        d["total_value"] = snapshot.total_value
        return {"content": [{"type": "text", "text": json.dumps(d)}]}
    except Exception as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "is_error": True}
