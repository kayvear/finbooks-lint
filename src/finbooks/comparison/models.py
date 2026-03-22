"""Pydantic models for comparison results and break reports."""

from __future__ import annotations

import uuid
from enum import Enum

from pydantic import BaseModel, Field

from finbooks.discrepancies.schema import ErrorType, Severity


class BreakSeverity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Break(BaseModel):
    """A single detected discrepancy between the PDF and the books."""

    break_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    customer_id: str
    period: str

    break_type: ErrorType
    section: str
    """PDF section where the break was detected (e.g. ``"positions"``)."""

    field: str
    """Column or field name that differs."""

    pdf_value: float | str | None = None
    """The value as extracted from the PDF."""

    books_value: float | str | None = None
    """The value from the parquet books data (ground truth)."""

    delta: float | None = None
    """Absolute numeric difference ``|pdf_value - books_value|``.  ``None`` for
    non-numeric breaks."""

    severity: BreakSeverity = BreakSeverity.MEDIUM
    description: str = ""
    """Human-readable summary of the break."""


class ComparisonResult(BaseModel):
    """All breaks found for one customer statement."""

    customer_id: str
    period: str
    breaks: list[Break] = []

    @property
    def has_breaks(self) -> bool:
        return bool(self.breaks)

    @property
    def highest_severity(self) -> BreakSeverity | None:
        if not self.breaks:
            return None
        order = {BreakSeverity.HIGH: 0, BreakSeverity.MEDIUM: 1, BreakSeverity.LOW: 2}
        return min(self.breaks, key=lambda b: order[b.severity]).severity
