from finbooks.models.statement import StatementData
from finbooks.statements.base import C_ACCENT, C_DARK, C_LIGHT, C_MID, C_PRIMARY, C_WHITE, BaseStatement
from finbooks.statements.renderers.formatters import DateFormatter, NumberFormatter


def render_cover(pdf: BaseStatement, data: StatementData) -> None:
    """Render the cover page: customer info, period summary, net worth box."""
    summary = data.summary
    pdf.add_page()

    # ── Title bar ─────────────────────────────────────────────────────────────
    pdf.set_fill_color(*C_PRIMARY)
    pdf.rect(pdf.MARGIN_LEFT, pdf.get_y(), pdf.w - pdf.MARGIN_LEFT - pdf.MARGIN_RIGHT, 18, style="F")

    pdf.set_font(pdf.FONT_FAMILY, style="B", size=16)
    pdf.set_text_color(*C_WHITE)
    pdf.set_xy(pdf.MARGIN_LEFT + 3, pdf.get_y() + 3)
    pdf.cell(0, 8, "ACCOUNT STATEMENT", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font(pdf.FONT_FAMILY, size=9)
    pdf.set_xy(pdf.MARGIN_LEFT + 3, pdf.get_y())
    pdf.cell(
        0, 6,
        DateFormatter.period(summary.period.start_date, summary.period.end_date),
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.ln(5)

    # ── Customer + account info ───────────────────────────────────────────────
    pdf.set_text_color(*C_DARK)
    pdf.set_font(pdf.FONT_FAMILY, style="B", size=13)
    pdf.cell(0, 7, summary.customer.full_name, new_x="LMARGIN", new_y="NEXT")

    pdf.set_font(pdf.FONT_FAMILY, size=9)
    pdf.set_text_color(*C_MID)
    pdf.cell(0, 5, str(summary.customer.address), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, summary.customer.email, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # ── Account list ──────────────────────────────────────────────────────────
    pdf.set_font(pdf.FONT_FAMILY, style="B", size=9)
    pdf.set_text_color(*C_PRIMARY)
    pdf.cell(0, 5, "Accounts Included in This Statement", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    all_accounts: list = list(data.cash_accounts) + list(data.cd_accounts) + list(data.brokerage_accounts)
    for acct in all_accounts:
        pdf.set_font(pdf.FONT_FAMILY, size=9)
        pdf.set_text_color(*C_DARK)
        pdf.cell(55, 5, acct.type_label)
        pdf.set_text_color(*C_MID)
        pdf.cell(0, 5, acct.display_id, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    # ── Net worth summary box ─────────────────────────────────────────────────
    pdf.set_font(pdf.FONT_FAMILY, style="B", size=10)
    pdf.set_text_color(*C_WHITE)
    pdf.set_fill_color(*C_ACCENT)
    box_y = pdf.get_y()
    pdf.rect(pdf.MARGIN_LEFT, box_y, pdf.w - pdf.MARGIN_LEFT - pdf.MARGIN_RIGHT, 8, style="F")
    pdf.set_xy(pdf.MARGIN_LEFT + 3, box_y + 1)
    pdf.cell(0, 6, "Portfolio Summary", new_x="LMARGIN", new_y="NEXT")

    pdf.set_fill_color(*C_LIGHT)
    pdf.rect(
        pdf.MARGIN_LEFT, pdf.get_y(),
        pdf.w - pdf.MARGIN_LEFT - pdf.MARGIN_RIGHT, 44,
        style="F",
    )
    pdf.ln(2)

    col_w = (pdf.w - pdf.MARGIN_LEFT - pdf.MARGIN_RIGHT) / 2

    def summary_row(label: str, value: str, bold_value: bool = False) -> None:
        pdf.set_font(pdf.FONT_FAMILY, size=9)
        pdf.set_text_color(*C_MID)
        pdf.cell(pdf.MARGIN_LEFT + col_w - pdf.MARGIN_LEFT, 7, f"  {label}")
        pdf.set_text_color(*C_DARK)
        if bold_value:
            pdf.set_font(pdf.FONT_FAMILY, style="B", size=9)
        pdf.cell(0, 7, value, new_x="LMARGIN", new_y="NEXT")

    summary_row("Opening Portfolio Value", NumberFormatter.currency(summary.opening_value))
    summary_row("Closing Portfolio Value", NumberFormatter.currency(summary.closing_value), bold_value=True)
    summary_row(
        "Net Change",
        NumberFormatter.currency(summary.net_change, show_sign=True),
        bold_value=True,
    )
    summary_row(
        "Period Return",
        NumberFormatter.pct(summary.period_return_pct),
        bold_value=True,
    )
    summary_row("Statement Period", summary.period.label)
    pdf.ln(4)
