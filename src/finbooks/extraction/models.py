"""Pydantic models for extracted PDF statement data.

These models are the *output* of both ``PdfExtractor`` and ``VisionExtractor``.
Both extractors produce the same shape so the comparison layer can work against
either without caring which extractor was used.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, field_validator


# ── Field-level ───────────────────────────────────────────────────────────────

class ExtractedField(BaseModel):
    """A single cell value as read from the PDF."""

    raw_text: str
    """Exact string as returned by pdfplumber / Claude — no post-processing."""

    parsed_value: float | str | None = None
    """Numeric parse of ``raw_text`` if applicable; ``None`` if the cell couldn't
    be parsed as a number.  String value is kept as-is for text fields."""

    confidence: float = 1.0
    """0–1.  Lowered when the cell text couldn't be parsed, was empty, or
    the vision model flagged low certainty."""

    @field_validator("confidence")
    @classmethod
    def _clamp(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


def make_field(raw: str | None) -> ExtractedField:
    """Convenience factory: create an :class:`ExtractedField` from raw cell text.

    Attempts to parse a numeric value from *raw* automatically.
    """
    raw = (raw or "").strip()
    if not raw:
        return ExtractedField(raw_text="", parsed_value=None, confidence=0.5)

    # Try to parse as float after stripping currency/percentage decorators
    cleaned = re.sub(r"[,$%+\s]", "", raw).lstrip("-+")
    negative = raw.lstrip().startswith("-") or raw.lstrip().startswith("(")

    try:
        val = float(cleaned)
        if negative and val > 0:
            val = -val
        return ExtractedField(raw_text=raw, parsed_value=val, confidence=1.0)
    except ValueError:
        # Non-numeric text field — store as string
        return ExtractedField(raw_text=raw, parsed_value=raw, confidence=1.0)


# ── Row-level ─────────────────────────────────────────────────────────────────

class ExtractedRow(BaseModel):
    """One data row from an extracted table, keyed by column header."""

    fields: dict[str, ExtractedField]

    def get_float(self, column: str) -> float | None:
        """Return the numeric parsed value for *column*, or ``None``."""
        f = self.fields.get(column)
        if f is None:
            return None
        if isinstance(f.parsed_value, (int, float)):
            return float(f.parsed_value)
        return None

    def get_str(self, column: str) -> str | None:
        """Return raw text for *column*, or ``None``."""
        f = self.fields.get(column)
        return f.raw_text if f else None


# ── Section-level ─────────────────────────────────────────────────────────────

class ExtractedSection(BaseModel):
    """All rows extracted from one named section of the PDF."""

    section_name: str
    """One of: cover | asset_allocation | positions | transactions | banking_cash | banking_cd"""

    rows: list[ExtractedRow] = []
    """Data rows (excludes the header row)."""

    totals_row: ExtractedRow | None = None
    """The bold totals/summary row at the end of the table, if present."""

    raw_text: str = ""
    """Full raw text of the section as extracted by pdfplumber — useful for
    debugging extraction failures."""

    @property
    def confidence(self) -> float:
        """Minimum confidence across all cells in the section."""
        all_fields = [
            f
            for row in self.rows
            for f in row.fields.values()
        ]
        if self.totals_row:
            all_fields.extend(self.totals_row.fields.values())
        if not all_fields:
            return 0.5
        return min(f.confidence for f in all_fields)


# ── Statement-level ───────────────────────────────────────────────────────────

class ExtractedStatement(BaseModel):
    """Complete structured extraction of one customer's PDF statement."""

    customer_id: str
    period: str
    """Period label as parsed from the filename or cover page (e.g. ``"2024Q4"``)."""

    extraction_method: Literal["pdfplumber", "vision"]

    sections: dict[str, ExtractedSection] = {}
    """Keyed by ``section_name``.  May not contain all sections if extraction failed."""

    @property
    def confidence(self) -> float:
        """Overall extraction confidence — minimum across all sections."""
        if not self.sections:
            return 0.0
        return min(s.confidence for s in self.sections.values())

    # ── Convenience accessors ─────────────────────────────────────────────────

    def cover_field(self, label: str) -> float | None:
        """Look up a labelled value from the cover section (e.g. ``"closing_value"``)."""
        section = self.sections.get("cover")
        if not section:
            return None
        for row in section.rows:
            if row.get_str("label") == label:
                return row.get_float("value")
        return None

    def allocation_value(self, asset_class: str) -> float | None:
        """Return the dollar value for *asset_class* from the allocation section.

        *asset_class* should be one of ``"Equities"``, ``"Cash"``, ``"CDs"``, ``"Total"``.
        """
        section = self.sections.get("asset_allocation")
        if not section:
            return None
        for row in section.rows:
            if (row.get_str("Asset Class") or "").strip() == asset_class:
                return row.get_float("Value")
        if self.sections["asset_allocation"].totals_row:
            tr = self.sections["asset_allocation"].totals_row
            if (tr.get_str("Asset Class") or "").strip() == asset_class:
                return tr.get_float("Value")
        return None

    def positions_rows(self) -> list[ExtractedRow]:
        s = self.sections.get("positions")
        return s.rows if s else []

    def positions_total(self) -> float | None:
        s = self.sections.get("positions")
        if not s or not s.totals_row:
            return None
        return s.totals_row.get_float("Market Value")
