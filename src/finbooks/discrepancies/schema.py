"""Pydantic models for the discrepancy injection spec."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ErrorType(str, Enum):
    NUMERIC_FOOTING = "numeric_footing"
    """Reported total/aggregate doesn't match the sum of the underlying rows."""

    CROSS_SECTION = "cross_section"
    """The same figure appears in two separate sections with different values."""

    NON_NUMERIC_CONTENT = "non_numeric_content"
    """A text field contains a wrong/corrupted value (e.g. bad ticker, transposed name)."""

    MISSING_EXTRA_DATA = "missing_extra_data"
    """A row is present on one side (PDF or books) but absent on the other."""


class InjectionSide(str, Enum):
    PDF = "pdf"
    """Corrupt the StatementData object before it is rendered to PDF."""

    BOOKS = "books"
    """Write a dirty copy of the parquet files with the corruption applied."""


class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Injection(BaseModel):
    """One deliberate discrepancy to introduce into the data."""

    id: str
    """Unique identifier — propagated into break reports for traceability."""

    customer_id: str
    """Target customer UUID, or ``"all"`` to apply to every customer."""

    error_type: ErrorType

    target_section: Literal["positions", "cover", "asset_allocation", "banking", "transactions"]
    """PDF section where the corruption is applied."""

    target_field: str
    """Column or field name to corrupt within the target section."""

    side: InjectionSide = InjectionSide.PDF

    # ── Numeric errors ───────────────────────────────────────────────────────
    magnitude: float | None = None
    """Fractional over/under-statement for numeric fields (0.05 = 5% inflation)."""

    # ── Content errors ───────────────────────────────────────────────────────
    swap_value: str | None = None
    """Replacement string for non_numeric_content errors."""

    # ── Missing / extra data ─────────────────────────────────────────────────
    drop_index: int | None = None
    """0-based index of the row to remove/corrupt (used by several error types)."""

    severity: Severity = Severity.MEDIUM


class DiscrepancySpec(BaseModel):
    """Root model parsed from ``config/discrepancies.yaml``."""

    version: str = "1"
    seed: int = 42
    injections: list[Injection] = Field(default_factory=list)

    def for_customer(self, customer_id: str) -> list[Injection]:
        """Return injections that apply to *customer_id* (includes ``"all"`` entries)."""
        return [
            inj for inj in self.injections
            if inj.customer_id == "all" or inj.customer_id == customer_id
        ]
