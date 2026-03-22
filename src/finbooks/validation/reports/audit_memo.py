"""Narrative audit memo PDF — generated from all comparison results.

The memo reuses :class:`~finbooks.statements.base.BaseStatement` (same palette,
header/footer, section_title helpers) so it has a consistent look with the
customer statements.

Sections rendered:
1. Cover — run summary (date, total customers reviewed, total breaks by severity)
2. Break summary table — one row per customer (id, period, # breaks, highest severity)
3. Detail section — grouped by customer, one table per customer listing all breaks
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from finbooks.comparison.models import Break, BreakSeverity, ComparisonResult
from finbooks.statements.base import BaseStatement, C_NEGATIVE, C_POSITIVE, C_PRIMARY, C_MID, C_DARK


_SEVERITY_COLOR = {
    BreakSeverity.HIGH: C_NEGATIVE,
    BreakSeverity.MEDIUM: (200, 130, 0),   # amber
    BreakSeverity.LOW: C_POSITIVE,
}


class AuditMemo(BaseStatement):
    """PDF audit memo — renders a summary and per-customer break details."""

    def __init__(self) -> None:
        super().__init__(institution_name="Financial Services, Inc.")
        self.set_statement_meta(
            account_display="Validation Run",
            period_label=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )

    def render(
        self,
        results: list[ComparisonResult],
        output_path: Path,
    ) -> None:
        """Render the full audit memo to *output_path*."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        self.add_page()
        self._render_run_summary(results)
        self._render_customer_summary_table(results)
        self._render_break_details(results)

        self.output(str(output_path))

    # ── Run summary ──────────────────────────────────────────────────────────

    def _render_run_summary(self, results: list[ComparisonResult]) -> None:
        self.section_title("Validation Run Summary")

        all_breaks = [b for r in results for b in r.breaks]
        high = sum(1 for b in all_breaks if b.severity == BreakSeverity.HIGH)
        med = sum(1 for b in all_breaks if b.severity == BreakSeverity.MEDIUM)
        low = sum(1 for b in all_breaks if b.severity == BreakSeverity.LOW)

        self.label_value_row("Run date:", datetime.now().strftime("%B %d, %Y %H:%M"))
        self.label_value_row("Customers reviewed:", str(len(results)))
        self.label_value_row("Customers with breaks:",
                             str(sum(1 for r in results if r.has_breaks)))
        self.label_value_row("Total breaks:", str(len(all_breaks)))
        self.label_value_row("  High severity:", str(high))
        self.label_value_row("  Medium severity:", str(med))
        self.label_value_row("  Low severity:", str(low))
        self.ln(4)

    # ── Customer summary table ────────────────────────────────────────────────

    def _render_customer_summary_table(self, results: list[ComparisonResult]) -> None:
        self.section_title("Customer Break Summary")

        if not results:
            self.set_font(self.FONT_FAMILY, size=9)
            self.cell(0, 6, "No customers reviewed.", new_x="LMARGIN", new_y="NEXT")
            return

        col_widths = [65, 20, 25, 55]
        headers = ["Customer ID", "Period", "Breaks", "Highest Severity"]

        # Header row
        self.set_font(self.FONT_FAMILY, style="B", size=9)
        self.set_fill_color(*C_PRIMARY)
        self.set_text_color(255, 255, 255)
        for w, h in zip(col_widths, headers):
            self.cell(w, 7, h, border=1, fill=True)
        self.ln()

        self.set_font(self.FONT_FAMILY, size=9)
        for i, r in enumerate(results):
            fill = (i % 2 == 0)
            if fill:
                self.set_fill_color(240, 244, 248)
            self.set_text_color(*C_DARK)

            sev = r.highest_severity
            sev_label = sev.value.upper() if sev else "NONE"
            sev_color = _SEVERITY_COLOR.get(sev, C_DARK) if sev else C_POSITIVE

            # Customer ID (truncated)
            self.cell(col_widths[0], 6, r.customer_id[:30], border=1, fill=fill)
            self.cell(col_widths[1], 6, r.period, border=1, fill=fill)
            self.cell(col_widths[2], 6, str(len(r.breaks)), border=1, fill=fill)
            self.set_text_color(*sev_color)
            self.cell(col_widths[3], 6, sev_label, border=1, fill=fill)
            self.set_text_color(*C_DARK)
            self.ln()

        self.ln(4)

    # ── Per-customer break details ────────────────────────────────────────────

    def _render_break_details(self, results: list[ComparisonResult]) -> None:
        self.section_title("Break Details by Customer")

        for r in results:
            if not r.has_breaks:
                continue

            self.set_font(self.FONT_FAMILY, style="B", size=10)
            self.set_text_color(*C_PRIMARY)
            self.cell(0, 6, f"Customer: {r.customer_id}", new_x="LMARGIN", new_y="NEXT")
            self.set_font(self.FONT_FAMILY, size=8)
            self.set_text_color(*C_MID)
            self.cell(0, 5, f"Period: {r.period}  |  Breaks: {len(r.breaks)}",
                      new_x="LMARGIN", new_y="NEXT")
            self.ln(1)

            self._render_breaks_table(r.breaks)
            self.ln(4)

    def _render_breaks_table(self, breaks: list[Break]) -> None:
        col_widths = [22, 22, 22, 28, 28, 16, 45]
        headers = ["Type", "Section", "Field", "PDF Value", "Books Value", "Sev", "Description"]

        # Table header
        self.set_font(self.FONT_FAMILY, style="B", size=8)
        self.set_fill_color(*C_PRIMARY)
        self.set_text_color(255, 255, 255)
        for w, h in zip(col_widths, headers):
            self.cell(w, 6, h, border=1, fill=True)
        self.ln()

        self.set_font(self.FONT_FAMILY, size=7.5)
        for i, b in enumerate(breaks):
            fill = (i % 2 == 0)
            if fill:
                self.set_fill_color(240, 244, 248)
            sev_color = _SEVERITY_COLOR.get(b.severity, C_DARK)

            def _fmt(v: float | str | None) -> str:
                if v is None:
                    return ""
                if isinstance(v, float):
                    return f"{v:,.2f}"
                return str(v)[:18]

            cells = [
                b.break_type.value[:14],
                b.section[:14],
                b.field[:16],
                _fmt(b.pdf_value),
                _fmt(b.books_value),
                b.severity.value[:4].upper(),
                b.description[:42],
            ]
            for j, (w, cell) in enumerate(zip(col_widths, cells)):
                if j == 5:  # severity column
                    self.set_text_color(*sev_color)
                else:
                    self.set_text_color(*C_DARK)
                self.cell(w, 5, cell, border=1, fill=fill)
            self.ln()

        self.set_text_color(*C_DARK)
