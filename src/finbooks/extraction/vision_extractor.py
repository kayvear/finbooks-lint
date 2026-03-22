"""Fallback PDF extractor — uses Claude vision to parse pages as images.

This extractor is used when :class:`~finbooks.extraction.pdf_extractor.PdfExtractor`
returns a confidence below the configured threshold, or when pdfplumber raises an
exception for a page.

Flow
----
1. Render each PDF page to a PNG image with ``pypdfium2``.
2. Base64-encode the PNG bytes.
3. Send the image to ``claude-sonnet-4-6`` via the Anthropic SDK with a structured
   JSON extraction prompt.
4. Parse the JSON response into the same :class:`ExtractedStatement` shape that
   ``PdfExtractor`` produces.
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium

from finbooks.extraction.models import (
    ExtractedField,
    ExtractedRow,
    ExtractedSection,
    ExtractedStatement,
    make_field,
)
from finbooks.settings import settings

# ── Extraction prompt sent to the vision model ────────────────────────────────
_SYSTEM_PROMPT = """You are a financial statement data extractor.
Given an image of a page from a customer financial statement, extract ALL tables
and labelled key-value pairs visible on the page.

Return a JSON object with this exact structure:
{
  "page_sections": [
    {
      "section_name": "<one of: cover | asset_allocation | positions | transactions | banking_cash | banking_cd | unknown>",
      "type": "<table | key_value>",
      "headers": ["col1", "col2", ...],   // for tables; omit for key_value
      "rows": [["cell1", "cell2", ...], ...],  // for tables
      "totals_row": ["cell1", ...] or null,    // the bold TOTAL row if present; null otherwise
      "labels": {"label_text": "value_text", ...},  // for key_value sections
      "confidence": 0.0
    }
  ]
}

Rules:
- section_name should match the section title visible on the page.
- For tables, include ALL rows including the header row in "headers", NOT in "rows".
- For the totals/summary row (TOTAL, bold background), put it in "totals_row".
- confidence is your certainty that you read each value correctly (0.0–1.0).
- If a cell is unclear or unreadable, use null for that cell.
- Never guess numeric values — use null if you are not confident.
- Return ONLY the JSON object, no surrounding text."""


class VisionExtractor:
    """Extract PDF statement data using Claude vision as an image reader.

    Parameters
    ----------
    model:
        The Claude model to use.  Defaults to ``settings.specialist_model``.
    dpi:
        Resolution for PDF-to-image rendering.  Higher = better quality but slower.
    """

    def __init__(
        self,
        model: str | None = None,
        dpi: int = 150,
    ) -> None:
        self._model = model or settings.specialist_model
        self._dpi = dpi

    def extract(self, pdf_path: Path, customer_id: str) -> ExtractedStatement:
        """Extract *pdf_path* by rendering each page and sending to Claude vision.

        Returns an :class:`ExtractedStatement` with ``extraction_method="vision"``.
        """
        import anthropic  # lazy import — not required unless vision path is used

        client = anthropic.Anthropic()
        period = _period_from_filename(pdf_path)

        # Render all pages to PNG bytes
        page_images = _render_pages(pdf_path, self._dpi)

        # Call Claude for each page
        all_page_data: list[dict[str, Any]] = []
        for page_bytes in page_images:
            page_data = _extract_page(client, self._model, page_bytes)
            if page_data:
                all_page_data.extend(page_data)

        # Merge across pages into ExtractedSections
        sections = _merge_sections(all_page_data)

        return ExtractedStatement(
            customer_id=customer_id,
            period=period,
            extraction_method="vision",
            sections=sections,
        )


# ── Page rendering ────────────────────────────────────────────────────────────

def _render_pages(pdf_path: Path, dpi: int) -> list[bytes]:
    """Render each page of *pdf_path* to PNG bytes using pypdfium2."""
    doc = pdfium.PdfDocument(str(pdf_path))
    page_bytes: list[bytes] = []

    scale = dpi / 72.0  # pypdfium2 native unit is 72 DPI
    for i in range(len(doc)):
        page = doc[i]
        bitmap = page.render(scale=scale, rotation=0)
        pil_image = bitmap.to_pil()
        import io
        buf = io.BytesIO()
        pil_image.save(buf, format="PNG")
        page_bytes.append(buf.getvalue())

    doc.close()
    return page_bytes


# ── Vision API call ───────────────────────────────────────────────────────────

def _extract_page(
    client: Any,
    model: str,
    page_bytes: bytes,
) -> list[dict[str, Any]]:
    """Send one page image to Claude and return its parsed ``page_sections`` list."""
    b64 = base64.standard_b64encode(page_bytes).decode("utf-8")

    try:
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": "Extract all tables and key-value pairs from this statement page.",
                        },
                    ],
                }
            ],
        )
    except Exception:
        return []

    text = response.content[0].text if response.content else ""

    # Extract JSON from the response (the model may wrap it in markdown)
    json_str = _extract_json(text)
    if not json_str:
        return []

    try:
        parsed = json.loads(json_str)
        return parsed.get("page_sections", [])
    except json.JSONDecodeError:
        return []


def _extract_json(text: str) -> str:
    """Pull the first JSON object from *text* (strips markdown code fences if present)."""
    # Remove markdown fences
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = text.replace("```", "").strip()

    # Find the first { ... }
    start = text.find("{")
    if start == -1:
        return ""

    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return ""


# ── Section merging ───────────────────────────────────────────────────────────

def _merge_sections(
    all_page_data: list[dict[str, Any]],
) -> dict[str, ExtractedSection]:
    """Merge per-page section dicts into a single ``ExtractedSection`` per section name.

    Transactions can span multiple pages — their rows are accumulated.
    """
    accumulator: dict[str, list[dict[str, Any]]] = {}
    for item in all_page_data:
        name = item.get("section_name", "unknown")
        accumulator.setdefault(name, []).append(item)

    sections: dict[str, ExtractedSection] = {}
    for name, items in accumulator.items():
        if name == "unknown":
            continue
        section = _build_section(name, items)
        if section:
            sections[name] = section

    return sections


def _build_section(
    section_name: str,
    items: list[dict[str, Any]],
) -> ExtractedSection | None:
    """Convert a list of same-section page dicts into one :class:`ExtractedSection`."""
    all_rows: list[ExtractedRow] = []
    totals_row: ExtractedRow | None = None
    cover_rows: list[ExtractedRow] = []
    confidence_vals: list[float] = []

    for item in items:
        confidence_vals.append(float(item.get("confidence", 0.8)))
        item_type = item.get("type", "table")

        if item_type == "key_value":
            # Cover / label-value sections
            for label, value in (item.get("labels") or {}).items():
                cover_rows.append(ExtractedRow(fields={
                    "label": ExtractedField(raw_text=label, parsed_value=label, confidence=1.0),
                    "value": make_field(str(value) if value is not None else ""),
                }))

        elif item_type == "table":
            headers: list[str] = item.get("headers") or []
            if not headers:
                continue

            for raw_row in item.get("rows") or []:
                cells = [str(c) if c is not None else "" for c in raw_row]
                row_dict = {
                    h: make_field(c)
                    for h, c in zip(headers, cells)
                    if h
                }
                all_rows.append(ExtractedRow(fields=row_dict))

            # Totals row
            raw_totals = item.get("totals_row")
            if raw_totals:
                cells = [str(c) if c is not None else "" for c in raw_totals]
                tr_dict = {h: make_field(c) for h, c in zip(headers, cells) if h}
                totals_row = ExtractedRow(fields=tr_dict)

    rows = cover_rows if section_name == "cover" else all_rows
    avg_conf = sum(confidence_vals) / len(confidence_vals) if confidence_vals else 0.8

    # Apply the average confidence to all cells that have confidence=1.0 (from make_field)
    # so that the vision extractor's uncertainty is reflected across the section.
    if avg_conf < 1.0:
        rows = _apply_confidence(rows, avg_conf)
        if totals_row:
            totals_row = _apply_confidence([totals_row], avg_conf)[0]

    return ExtractedSection(
        section_name=section_name,
        rows=rows,
        totals_row=totals_row,
    )


def _apply_confidence(
    rows: list[ExtractedRow], confidence: float
) -> list[ExtractedRow]:
    """Return new rows where every field has confidence capped at *confidence*."""
    result = []
    for row in rows:
        new_fields = {
            k: v.model_copy(update={"confidence": min(v.confidence, confidence)})
            for k, v in row.fields.items()
        }
        result.append(ExtractedRow(fields=new_fields))
    return result


# ── Filename helpers ──────────────────────────────────────────────────────────

def _period_from_filename(path: Path) -> str:
    stem = path.stem
    parts = stem.rsplit("_", 1)
    return parts[-1] if len(parts) == 2 else stem
