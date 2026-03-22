"""Compare an extracted PDF statement against the books-of-record snapshot.

Four break types are checked in sequence:

1. **Numeric footing** — reported aggregate ≠ sum of underlying rows.
2. **Cross-section** — the same figure disagrees across two sections.
3. **Non-numeric content** — a text field (e.g. ticker symbol) doesn't match books.
4. **Missing / extra data** — a row is present on one side but absent on the other.
"""

from __future__ import annotations

from finbooks.comparison.books_retriever import BooksSnapshot
from finbooks.comparison.models import Break, BreakSeverity, ComparisonResult
from finbooks.discrepancies.schema import ErrorType
from finbooks.extraction.models import ExtractedStatement

# Numeric tolerance for floating-point comparisons (absolute, in dollars)
_TOLERANCE = 0.02


class StatementComparator:
    """Diff an :class:`ExtractedStatement` against a :class:`BooksSnapshot`.

    Usage::

        comparator = StatementComparator()
        result = comparator.compare(extracted, books)
        for b in result.breaks:
            print(b.description)
    """

    def compare(
        self,
        extracted: ExtractedStatement,
        books: BooksSnapshot,
    ) -> ComparisonResult:
        breaks: list[Break] = []
        cid = extracted.customer_id
        period = extracted.period

        breaks.extend(self._check_numeric_footing(extracted, books, cid, period))
        breaks.extend(self._check_cross_section(extracted, books, cid, period))
        breaks.extend(self._check_non_numeric_content(extracted, books, cid, period))
        breaks.extend(self._check_missing_extra(extracted, books, cid, period))

        return ComparisonResult(customer_id=cid, period=period, breaks=breaks)

    # ── 1. Numeric footing ────────────────────────────────────────────────────

    def _check_numeric_footing(
        self,
        ex: ExtractedStatement,
        books: BooksSnapshot,
        cid: str,
        period: str,
    ) -> list[Break]:
        breaks: list[Break] = []

        # ── Positions table: sum of rows vs reported totals row ────────────
        pos_rows = ex.positions_rows()
        if pos_rows:
            row_sum = sum(
                r.get_float("Market Value") or 0.0
                for r in pos_rows
                if r.get_float("Market Value") is not None
            )
            pos_total = ex.positions_total()
            if pos_total is not None and abs(row_sum - pos_total) > _TOLERANCE:
                breaks.append(Break(
                    customer_id=cid, period=period,
                    break_type=ErrorType.NUMERIC_FOOTING,
                    section="positions", field="total_market_value",
                    pdf_value=pos_total, books_value=row_sum,
                    delta=abs(pos_total - row_sum),
                    severity=BreakSeverity.HIGH,
                    description=(
                        f"Positions TOTAL row ({pos_total:,.2f}) does not equal "
                        f"the sum of individual rows ({row_sum:,.2f}). "
                        f"Delta: {abs(pos_total - row_sum):,.2f}"
                    ),
                ))

        # ── Asset allocation: sum of components vs total row ───────────────
        alloc_section = ex.sections.get("asset_allocation")
        if alloc_section and alloc_section.totals_row:
            comp_sum = 0.0
            for row in alloc_section.rows:
                v = row.get_float("Value")
                if v is not None:
                    comp_sum += v
            alloc_total = alloc_section.totals_row.get_float("Value")
            if alloc_total is not None and abs(comp_sum - alloc_total) > _TOLERANCE:
                breaks.append(Break(
                    customer_id=cid, period=period,
                    break_type=ErrorType.NUMERIC_FOOTING,
                    section="asset_allocation", field="total_value",
                    pdf_value=alloc_total, books_value=comp_sum,
                    delta=abs(alloc_total - comp_sum),
                    severity=BreakSeverity.HIGH,
                    description=(
                        f"Asset allocation TOTAL ({alloc_total:,.2f}) does not equal "
                        f"sum of components ({comp_sum:,.2f}). "
                        f"Delta: {abs(alloc_total - comp_sum):,.2f}"
                    ),
                ))

        # ── Allocation equity_value vs books equity_value ──────────────────
        pdf_equity = ex.allocation_value("Equities")
        if pdf_equity is not None:
            books_equity = books.equity_value
            if abs(pdf_equity - books_equity) > _TOLERANCE:
                breaks.append(Break(
                    customer_id=cid, period=period,
                    break_type=ErrorType.NUMERIC_FOOTING,
                    section="asset_allocation", field="equity_value",
                    pdf_value=pdf_equity, books_value=books_equity,
                    delta=abs(pdf_equity - books_equity),
                    severity=BreakSeverity.HIGH,
                    description=(
                        f"PDF equity allocation ({pdf_equity:,.2f}) differs from "
                        f"books equity value ({books_equity:,.2f}). "
                        f"Delta: {abs(pdf_equity - books_equity):,.2f}"
                    ),
                ))

        return breaks

    # ── 2. Cross-section ──────────────────────────────────────────────────────

    def _check_cross_section(
        self,
        ex: ExtractedStatement,
        books: BooksSnapshot,
        cid: str,
        period: str,
    ) -> list[Break]:
        breaks: list[Break] = []

        # ── Cover closing_value vs allocation total ─────────────────────────
        cover_close = ex.cover_field("closing_value")
        alloc_total = ex.allocation_value("Total")
        if cover_close is not None and alloc_total is not None:
            if abs(cover_close - alloc_total) > _TOLERANCE:
                breaks.append(Break(
                    customer_id=cid, period=period,
                    break_type=ErrorType.CROSS_SECTION,
                    section="cover", field="closing_value",
                    pdf_value=cover_close, books_value=alloc_total,
                    delta=abs(cover_close - alloc_total),
                    severity=BreakSeverity.MEDIUM,
                    description=(
                        f"Cover 'Closing Portfolio Value' ({cover_close:,.2f}) disagrees "
                        f"with asset allocation total ({alloc_total:,.2f}). "
                        f"Delta: {abs(cover_close - alloc_total):,.2f}"
                    ),
                ))

        # ── Allocation equity_value vs positions total ──────────────────────
        alloc_equity = ex.allocation_value("Equities")
        pos_total = ex.positions_total()
        if alloc_equity is not None and pos_total is not None:
            if abs(alloc_equity - pos_total) > _TOLERANCE:
                breaks.append(Break(
                    customer_id=cid, period=period,
                    break_type=ErrorType.CROSS_SECTION,
                    section="asset_allocation", field="equity_value",
                    pdf_value=alloc_equity, books_value=pos_total,
                    delta=abs(alloc_equity - pos_total),
                    severity=BreakSeverity.MEDIUM,
                    description=(
                        f"Asset allocation equity ({alloc_equity:,.2f}) differs from "
                        f"positions table total ({pos_total:,.2f}). "
                        f"Delta: {abs(alloc_equity - pos_total):,.2f}"
                    ),
                ))

        # ── Allocation cd_value vs banking CD total ─────────────────────────
        alloc_cd = ex.allocation_value("CDs")
        banking_cd_section = ex.sections.get("banking_cd")
        if alloc_cd is not None and banking_cd_section:
            cd_sum = sum(
                r.get_float("Current Value") or 0.0
                for r in banking_cd_section.rows
            )
            if abs(alloc_cd - cd_sum) > _TOLERANCE:
                breaks.append(Break(
                    customer_id=cid, period=period,
                    break_type=ErrorType.CROSS_SECTION,
                    section="banking_cd", field="current_value_total",
                    pdf_value=alloc_cd, books_value=cd_sum,
                    delta=abs(alloc_cd - cd_sum),
                    severity=BreakSeverity.MEDIUM,
                    description=(
                        f"Asset allocation CD value ({alloc_cd:,.2f}) differs from "
                        f"sum of CD current values in banking section ({cd_sum:,.2f}). "
                        f"Delta: {abs(alloc_cd - cd_sum):,.2f}"
                    ),
                ))

        return breaks

    # ── 3. Non-numeric content ────────────────────────────────────────────────

    def _check_non_numeric_content(
        self,
        ex: ExtractedStatement,
        books: BooksSnapshot,
        cid: str,
        period: str,
    ) -> list[Break]:
        breaks: list[Break] = []
        books_symbols = books.position_symbols

        for row in ex.positions_rows():
            symbol = row.get_str("Symbol")
            if not symbol:
                continue
            symbol = symbol.strip()
            if symbol and symbol not in books_symbols:
                breaks.append(Break(
                    customer_id=cid, period=period,
                    break_type=ErrorType.NON_NUMERIC_CONTENT,
                    section="positions", field="symbol",
                    pdf_value=symbol, books_value=None,
                    delta=None,
                    severity=BreakSeverity.LOW,
                    description=(
                        f"Position symbol '{symbol}' in PDF is not found in books positions. "
                        f"Expected one of: {sorted(books_symbols)[:5]}..."
                    ),
                ))

        return breaks

    # ── 4. Missing / extra data ───────────────────────────────────────────────

    def _check_missing_extra(
        self,
        ex: ExtractedStatement,
        books: BooksSnapshot,
        cid: str,
        period: str,
    ) -> list[Break]:
        breaks: list[Break] = []

        pdf_symbols = {
            (row.get_str("Symbol") or "").strip()
            for row in ex.positions_rows()
            if row.get_str("Symbol")
        }
        books_symbols = books.position_symbols

        # In books but not in PDF → missing from PDF
        for sym in sorted(books_symbols - pdf_symbols):
            breaks.append(Break(
                customer_id=cid, period=period,
                break_type=ErrorType.MISSING_EXTRA_DATA,
                section="positions", field="row",
                pdf_value=None, books_value=sym,
                delta=None,
                severity=BreakSeverity.HIGH,
                description=(
                    f"Position '{sym}' exists in books but is absent from the PDF statement."
                ),
            ))

        # In PDF but not in books → extra row in PDF (possibly injected or erroneous)
        for sym in sorted(pdf_symbols - books_symbols):
            if sym:  # skip empty strings
                breaks.append(Break(
                    customer_id=cid, period=period,
                    break_type=ErrorType.MISSING_EXTRA_DATA,
                    section="positions", field="row",
                    pdf_value=sym, books_value=None,
                    delta=None,
                    severity=BreakSeverity.MEDIUM,
                    description=(
                        f"Position '{sym}' appears in the PDF statement but has no "
                        f"corresponding entry in the books."
                    ),
                ))

        return breaks
