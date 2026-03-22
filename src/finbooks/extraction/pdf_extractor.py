"""Primary PDF extractor — uses pdfplumber to extract tables and label-value pairs.

Flow
----
1. Open the PDF with ``pdfplumber.open()``.
2. Iterate pages; for each page call ``page.extract_text()`` to detect which
   section(s) the page belongs to.
3. Call ``page.extract_tables()`` to get raw cell data.
4. Route each table to the appropriate section parser based on its column headers.
5. Return a fully populated :class:`ExtractedStatement`.

Cover page is special — it has no table, only labelled rows — so its values are
parsed from the raw text via regex.
"""

from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from finbooks.extraction.models import (
    ExtractedField,
    ExtractedRow,
    ExtractedSection,
    ExtractedStatement,
    make_field,
)


# ── Section title strings (must match what sections/*.py renders) ─────────────
_TITLE_COVER = "ACCOUNT STATEMENT"
_TITLE_ALLOC = "Asset Allocation"
_TITLE_POSITIONS = "Equity Holdings"
_TITLE_TRANSACTIONS = "Transaction History"
_TITLE_BANKING_CASH = "Cash Accounts"
_TITLE_BANKING_CD = "Certificates of Deposit"

# ── Column-header fingerprints per section ────────────────────────────────────
_POSITIONS_HEADERS = {"Symbol", "Shares", "Market Value"}
_TRANSACTIONS_HEADERS = {"Date", "Type", "Amount", "Balance"}
_ALLOC_HEADERS = {"Asset Class", "Value", "Weight"}
_BANKING_CASH_HEADERS = {"Opening Balance", "Closing Balance"}
_BANKING_CD_HEADERS = {"Principal", "Maturity Date"}

# Cover page label → canonical key map
_COVER_LABEL_MAP: dict[str, str] = {
    "Opening Portfolio Value": "opening_value",
    "Closing Portfolio Value": "closing_value",
    "Net Change": "net_change",
    "Period Return": "period_return_pct",
}


class PdfExtractor:
    """Extract structured data from a finbooks-generated PDF using pdfplumber.

    If the overall confidence of the result is below *fallback_threshold*, the
    caller should switch to :class:`~finbooks.extraction.vision_extractor.VisionExtractor`.
    """

    def __init__(self, fallback_threshold: float = 0.7) -> None:
        self.fallback_threshold = fallback_threshold

    def extract(self, pdf_path: Path, customer_id: str) -> ExtractedStatement:
        """Extract *pdf_path* and return an :class:`ExtractedStatement`.

        Parameters
        ----------
        pdf_path:
            Path to the PDF file.
        customer_id:
            Customer UUID — stored in the result for traceability.
        """
        period = _period_from_filename(pdf_path)

        # Accumulators — transactions can span multiple pages
        alloc_section: ExtractedSection | None = None
        cover_section: ExtractedSection | None = None
        positions_section: ExtractedSection | None = None
        tx_rows: list[ExtractedRow] = []
        tx_raw: list[str] = []
        banking_cash_section: ExtractedSection | None = None
        banking_cd_section: ExtractedSection | None = None

        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                tables = page.extract_tables() or []

                # ── Cover ──────────────────────────────────────────────────
                if _TITLE_COVER in text and cover_section is None:
                    cover_section = _parse_cover(text)

                # ── Asset Allocation ────────────────────────────────────────
                if _TITLE_ALLOC in text and alloc_section is None:
                    for tbl in tables:
                        section = _try_parse_table(tbl, _ALLOC_HEADERS, "asset_allocation", text)
                        if section:
                            alloc_section = section
                            break

                # ── Equity Holdings ─────────────────────────────────────────
                if _TITLE_POSITIONS in text and positions_section is None:
                    for tbl in tables:
                        section = _try_parse_table(tbl, _POSITIONS_HEADERS, "positions", text)
                        if section:
                            positions_section = section
                            break

                # ── Transaction History (multi-page) ────────────────────────
                if _TITLE_TRANSACTIONS in text:
                    for tbl in tables:
                        rows, raw = _try_parse_transaction_table(tbl)
                        tx_rows.extend(rows)
                        tx_raw.append(raw)

                # ── Banking — Cash ──────────────────────────────────────────
                if _TITLE_BANKING_CASH in text and banking_cash_section is None:
                    for tbl in tables:
                        section = _try_parse_table(tbl, _BANKING_CASH_HEADERS, "banking_cash", text)
                        if section:
                            banking_cash_section = section
                            break

                # ── Banking — CD ────────────────────────────────────────────
                if _TITLE_BANKING_CD in text and banking_cd_section is None:
                    for tbl in tables:
                        section = _try_parse_table(tbl, _BANKING_CD_HEADERS, "banking_cd", text)
                        if section:
                            banking_cd_section = section
                            break

        # Assemble transactions section
        tx_section: ExtractedSection | None = None
        if tx_rows:
            tx_section = ExtractedSection(
                section_name="transactions",
                rows=tx_rows,
                raw_text="\n".join(tx_raw),
            )

        sections: dict[str, ExtractedSection] = {}
        for name, section in [
            ("cover", cover_section),
            ("asset_allocation", alloc_section),
            ("positions", positions_section),
            ("transactions", tx_section),
            ("banking_cash", banking_cash_section),
            ("banking_cd", banking_cd_section),
        ]:
            if section is not None:
                sections[name] = section

        return ExtractedStatement(
            customer_id=customer_id,
            period=period,
            extraction_method="pdfplumber",
            sections=sections,
        )


# ── Cover page parsing ────────────────────────────────────────────────────────

def _parse_cover(text: str) -> ExtractedSection:
    """Extract key-value pairs from the cover page free text."""
    rows: list[ExtractedRow] = []

    for label, key in _COVER_LABEL_MAP.items():
        # Look for the label followed by a currency or percentage value on the same line
        pattern = re.escape(label) + r"[^\n]*?([\+\-]?\$?[\d,]+\.?\d*\s*%?)"
        m = re.search(pattern, text)
        if m:
            raw = m.group(1).strip()
            rows.append(ExtractedRow(fields={
                "label": ExtractedField(raw_text=key, parsed_value=key, confidence=1.0),
                "value": make_field(raw),
            }))

    return ExtractedSection(section_name="cover", rows=rows, raw_text=text)


# ── Generic table parser ──────────────────────────────────────────────────────

def _try_parse_table(
    table: list[list[str | None]],
    expected_headers: set[str],
    section_name: str,
    raw_text: str,
) -> ExtractedSection | None:
    """Parse *table* into an :class:`ExtractedSection` if its headers match.

    Returns ``None`` if the table's header row doesn't contain all of
    *expected_headers*.
    """
    if not table:
        return None

    # Find the header row — first non-empty row whose cells cover expected headers
    header_row_idx: int | None = None
    headers: list[str] = []

    for i, row in enumerate(table):
        cells = [str(c or "").strip() for c in row]
        non_empty = set(c for c in cells if c)
        if expected_headers.issubset(non_empty):
            header_row_idx = i
            headers = cells
            break

    if header_row_idx is None:
        return None

    data_rows: list[ExtractedRow] = []
    totals_row: ExtractedRow | None = None

    for row in table[header_row_idx + 1:]:
        cells = [str(c or "").strip() for c in row]
        if not any(cells):
            continue  # skip blank rows

        row_dict: dict[str, ExtractedField] = {}
        for header, cell in zip(headers, cells):
            if header:
                row_dict[header] = make_field(cell)

        extracted = ExtractedRow(fields=row_dict)

        # Detect the totals row by checking if the first cell looks like "TOTAL"
        first_cell = cells[0].upper() if cells else ""
        if "TOTAL" in first_cell:
            totals_row = extracted
        else:
            data_rows.append(extracted)

    return ExtractedSection(
        section_name=section_name,
        rows=data_rows,
        totals_row=totals_row,
        raw_text=raw_text,
    )


# ── Transaction table parser ──────────────────────────────────────────────────

def _try_parse_transaction_table(
    table: list[list[str | None]],
) -> tuple[list[ExtractedRow], str]:
    """Parse a transaction table page.

    Returns ``(rows, raw_text)`` — rows may be empty if the table doesn't look
    like a transaction table.
    """
    if not table:
        return [], ""

    # Find header row
    header_row_idx: int | None = None
    headers: list[str] = []
    for i, row in enumerate(table):
        cells = [str(c or "").strip() for c in row]
        non_empty = set(c for c in cells if c)
        if _TRANSACTIONS_HEADERS.issubset(non_empty):
            header_row_idx = i
            headers = cells
            break

    if header_row_idx is None:
        return [], ""

    rows: list[ExtractedRow] = []
    for row in table[header_row_idx + 1:]:
        cells = [str(c or "").strip() for c in row]
        if not any(cells):
            continue
        row_dict = {h: make_field(c) for h, c in zip(headers, cells) if h}
        rows.append(ExtractedRow(fields=row_dict))

    raw = "\n".join(" | ".join(str(c or "") for c in r) for r in table)
    return rows, raw


# ── Filename helpers ──────────────────────────────────────────────────────────

def _period_from_filename(path: Path) -> str:
    """Derive the period label from a filename like ``{uuid}_{period}.pdf``."""
    stem = path.stem  # e.g. "abc123-..._2024Q4"
    parts = stem.rsplit("_", 1)
    return parts[-1] if len(parts) == 2 else stem
