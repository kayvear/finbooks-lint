"""Discrepancy injectors — corrupt data before PDF rendering or before parquet is read.

Two injectors are provided:

* :class:`StatementInjector` — PDF-side.  Operates on a :class:`StatementData` object
  *before* it is passed to ``StatementBuilder.build()``.  Returns a new (mutated copy)
  of ``StatementData`` so the original is never modified.

* :class:`BooksInjector` — Books-side.  Writes a dirty copy of the parquet files to
  a separate directory so the original raw data is preserved.
"""

from __future__ import annotations

import copy
import shutil
from decimal import Decimal
from pathlib import Path

import pandas as pd

from finbooks.discrepancies.schema import (
    DiscrepancySpec,
    ErrorType,
    Injection,
    InjectionSide,
)
from finbooks.models.statement import (
    AssetAllocationBreakdown,
    StatementData,
    StatementSummary,
)


# ── StatementInjector (PDF-side) ──────────────────────────────────────────────

class StatementInjector:
    """Apply PDF-side injections to a :class:`StatementData` instance.

    Produces a deep-copy of the input data with the specified corruptions applied.
    The original ``StatementData`` object is never modified.

    Usage::

        spec = load_spec("config/discrepancies.yaml")
        injector = StatementInjector(spec)
        dirty_data = injector.inject(clean_data, customer_id)
        builder.build(dirty_data, output_path)
    """

    def __init__(self, spec: DiscrepancySpec) -> None:
        self._spec = spec

    # ── Public API ────────────────────────────────────────────────────────────

    def inject(self, data: StatementData, customer_id: str) -> StatementData:
        """Return a new ``StatementData`` with all applicable PDF-side injections applied."""
        injections = [
            inj for inj in self._spec.for_customer(customer_id)
            if inj.side == InjectionSide.PDF
        ]
        if not injections:
            return data

        # Work on a deep copy — never mutate the caller's data.
        result = _deep_copy_statement(data)
        for inj in injections:
            result = self._apply(result, inj)
        return result

    # ── Dispatch ─────────────────────────────────────────────────────────────

    def _apply(self, data: StatementData, inj: Injection) -> StatementData:
        match inj.error_type:
            case ErrorType.NUMERIC_FOOTING:
                return self._numeric_footing(data, inj)
            case ErrorType.CROSS_SECTION:
                return self._cross_section(data, inj)
            case ErrorType.NON_NUMERIC_CONTENT:
                return self._non_numeric_content(data, inj)
            case ErrorType.MISSING_EXTRA_DATA:
                return self._missing_extra_data(data, inj)
            case _:
                raise ValueError(f"Unknown error_type: {inj.error_type}")

    # ── Numeric footing ───────────────────────────────────────────────────────

    def _numeric_footing(self, data: StatementData, inj: Injection) -> StatementData:
        """Inflate a reported aggregate so it no longer matches the underlying rows.

        Supported target_section / target_field combos:
          - asset_allocation / equity_value  → inflate allocation.equity_value
          - asset_allocation / cash_value    → inflate allocation.cash_value
          - asset_allocation / cd_value      → inflate allocation.cd_value
        """
        mag = Decimal(str(inj.magnitude or 0.05))
        factor = Decimal("1") + mag

        section = inj.target_section
        field = inj.target_field

        if section == "asset_allocation":
            alloc = data.summary.allocation
            if field == "equity_value":
                new_alloc = alloc.model_copy(
                    update={"equity_value": (alloc.equity_value * factor).quantize(Decimal("0.01"))}
                )
            elif field == "cash_value":
                new_alloc = alloc.model_copy(
                    update={"cash_value": (alloc.cash_value * factor).quantize(Decimal("0.01"))}
                )
            elif field == "cd_value":
                new_alloc = alloc.model_copy(
                    update={"cd_value": (alloc.cd_value * factor).quantize(Decimal("0.01"))}
                )
            else:
                raise ValueError(f"numeric_footing: unsupported target_field '{field}' in {section}")
            new_summary = data.summary.model_copy(update={"allocation": new_alloc})
            return data.model_copy(update={"summary": new_summary})

        raise ValueError(f"numeric_footing: unsupported target_section '{section}'")

    # ── Cross-section ─────────────────────────────────────────────────────────

    def _cross_section(self, data: StatementData, inj: Injection) -> StatementData:
        """Inflate a summary field so it disagrees with another section's value.

        Supported:
          - cover / closing_value  → inflate StatementSummary.closing_value
          - cover / opening_value  → inflate StatementSummary.opening_value
        """
        mag = Decimal(str(inj.magnitude or 0.03))
        factor = Decimal("1") + mag

        section = inj.target_section
        field = inj.target_field

        if section == "cover":
            if field == "closing_value":
                new_val = (data.summary.closing_value * factor).quantize(Decimal("0.01"))
                new_summary = data.summary.model_copy(update={"closing_value": new_val})
                return data.model_copy(update={"summary": new_summary})
            if field == "opening_value":
                new_val = (data.summary.opening_value * factor).quantize(Decimal("0.01"))
                new_summary = data.summary.model_copy(update={"opening_value": new_val})
                return data.model_copy(update={"summary": new_summary})

        raise ValueError(f"cross_section: unsupported target '{section}.{field}'")

    # ── Non-numeric content ───────────────────────────────────────────────────

    def _non_numeric_content(self, data: StatementData, inj: Injection) -> StatementData:
        """Replace a text field value with a wrong/corrupted string.

        Supported:
          - positions / symbol  → swap the symbol at drop_index (default 0) with swap_value
        """
        section = inj.target_section
        field = inj.target_field
        swap_val = inj.swap_value or "INVALID"
        idx = inj.drop_index or 0

        if section == "positions" and field == "symbol":
            positions = list(data.equity_positions)
            if not positions:
                return data
            idx = min(idx, len(positions) - 1)
            bad_pos = positions[idx].model_copy(update={"symbol": swap_val})
            positions[idx] = bad_pos
            return data.model_copy(update={"equity_positions": positions})

        raise ValueError(f"non_numeric_content: unsupported target '{section}.{field}'")

    # ── Missing / extra data ──────────────────────────────────────────────────

    def _missing_extra_data(self, data: StatementData, inj: Injection) -> StatementData:
        """Drop a row so it appears on one side but not the other.

        Supported:
          - positions / row  → drop the position at drop_index from the PDF
        """
        section = inj.target_section
        field = inj.target_field
        idx = inj.drop_index or 0

        if section == "positions" and field == "row":
            positions = list(data.equity_positions)
            if not positions:
                return data
            idx = min(idx, len(positions) - 1)
            positions.pop(idx)
            return data.model_copy(update={"equity_positions": positions})

        raise ValueError(f"missing_extra_data: unsupported target '{section}.{field}'")


# ── BooksInjector (books-side) ────────────────────────────────────────────────

class BooksInjector:
    """Apply books-side injections by writing dirty copies of the parquet files.

    The original ``data/raw/`` files are **never** modified.  Dirty copies are
    written to ``data/raw_injected/`` (by default).

    Usage::

        spec = load_spec("config/discrepancies.yaml")
        injector = BooksInjector(spec, raw_dir=Path("data/raw"))
        dirty_dir = injector.inject(customer_id)
        # validate_statements.py then reads from dirty_dir instead of raw_dir
    """

    def __init__(
        self,
        spec: DiscrepancySpec,
        raw_dir: Path,
        injected_dir: Path | None = None,
    ) -> None:
        self._spec = spec
        self._raw_dir = Path(raw_dir)
        self._injected_dir = Path(injected_dir) if injected_dir else self._raw_dir.parent / "raw_injected"

    @property
    def injected_dir(self) -> Path:
        return self._injected_dir

    def inject(self, customer_id: str) -> Path:
        """Write dirty parquet copies for *customer_id*.  Returns the injected dir."""
        injections = [
            inj for inj in self._spec.for_customer(customer_id)
            if inj.side == InjectionSide.BOOKS
        ]

        self._injected_dir.mkdir(parents=True, exist_ok=True)

        # Copy all parquet files as base
        for f in self._raw_dir.glob("*.parquet"):
            shutil.copy2(f, self._injected_dir / f.name)

        # Apply each books-side injection
        for inj in injections:
            self._apply(customer_id, inj)

        return self._injected_dir

    def _apply(self, customer_id: str, inj: Injection) -> None:
        """Mutate the injected parquet files in place for *inj*."""
        if inj.target_section == "positions" and inj.error_type == ErrorType.MISSING_EXTRA_DATA:
            self._drop_position_row(customer_id, inj)
        elif inj.target_section == "positions" and inj.error_type == ErrorType.NON_NUMERIC_CONTENT:
            self._corrupt_position_symbol(customer_id, inj)
        # Additional cases can be added here as needed

    def _drop_position_row(self, customer_id: str, inj: Injection) -> None:
        """Remove one position row from the injected positions parquet."""
        path = self._injected_dir / "positions.parquet"
        df = pd.read_parquet(path)
        mask = df["account_id"].isin(self._brokerage_ids(customer_id))
        cust_df = df[mask].reset_index(drop=True)
        idx = min(inj.drop_index or 0, len(cust_df) - 1)
        row_to_drop = cust_df.iloc[idx]
        df = df.drop(index=row_to_drop.name)
        df.to_parquet(path, index=False)

    def _corrupt_position_symbol(self, customer_id: str, inj: Injection) -> None:
        """Replace a symbol in the injected positions parquet."""
        path = self._injected_dir / "positions.parquet"
        df = pd.read_parquet(path)
        mask = df["account_id"].isin(self._brokerage_ids(customer_id))
        cust_idx = df[mask].index
        idx = min(inj.drop_index or 0, len(cust_idx) - 1)
        df.loc[cust_idx[idx], "symbol"] = inj.swap_value or "INVALID"
        df.to_parquet(path, index=False)

    def _brokerage_ids(self, customer_id: str) -> set[str]:
        """Return account_ids for brokerage accounts belonging to *customer_id*."""
        path = self._raw_dir / "accounts.parquet"
        if (self._injected_dir / "accounts.parquet").exists():
            path = self._injected_dir / "accounts.parquet"
        df = pd.read_parquet(path)
        return set(
            df[
                (df["customer_id"] == customer_id) & (df["account_type"] == "brokerage")
            ]["account_id"].tolist()
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _deep_copy_statement(data: StatementData) -> StatementData:
    """Return a Pydantic-safe deep copy of *data* via JSON round-trip."""
    return StatementData.model_validate(data.model_dump())
