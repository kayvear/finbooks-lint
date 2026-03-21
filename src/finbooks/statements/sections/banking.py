from finbooks.models.statement import StatementData
from finbooks.statements.base import C_ACCENT, C_DARK, C_LIGHT, C_MID, C_PRIMARY, C_WHITE, BaseStatement
from finbooks.statements.renderers.formatters import DateFormatter, NumberFormatter


def render_banking(pdf: BaseStatement, data: StatementData) -> None:
    """Render cash account balances and CD summary."""
    has_cash = bool(data.cash_accounts)
    has_cds = bool(data.cd_accounts)

    if not has_cash and not has_cds:
        return

    pdf.section_title("Banking & Cash Management")

    # ── Cash accounts ─────────────────────────────────────────────────────────
    if has_cash:
        pdf.set_font(pdf.FONT_FAMILY, style="B", size=9)
        pdf.set_text_color(*C_ACCENT)
        pdf.cell(0, 6, "Cash Accounts", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

        headers = ["Account Type", "Account #", "Opening Balance", "Closing Balance", "APY"]
        col_widths = [40.0, 30.0, 38.0, 38.0, 18.0]

        pdf.set_font(pdf.FONT_FAMILY, style="B", size=8)
        pdf.set_fill_color(*C_PRIMARY)
        pdf.set_text_color(*C_WHITE)
        for hdr, cw in zip(headers, col_widths):
            align = "R" if hdr in ("Opening Balance", "Closing Balance") else "L"
            pdf.cell(cw, 6, hdr, fill=True, border=0, align=align)
        pdf.ln(6)

        for i, acct in enumerate(data.cash_accounts):
            fill = i % 2 == 0
            pdf.set_fill_color(*C_LIGHT)
            pdf.set_font(pdf.FONT_FAMILY, size=8)
            pdf.set_text_color(*C_DARK)
            pdf.cell(col_widths[0], 5.5, acct.type_label, fill=fill, border=0)
            pdf.cell(col_widths[1], 5.5, acct.display_id, fill=fill, border=0)
            pdf.cell(col_widths[2], 5.5, NumberFormatter.currency(acct.opening_balance), fill=fill, border=0, align="R")
            pdf.cell(col_widths[3], 5.5, NumberFormatter.currency(acct.current_balance), fill=fill, border=0, align="R")
            pdf.cell(col_widths[4], 5.5, NumberFormatter.rate(acct.interest_rate) if acct.interest_rate else "—", fill=fill, border=0, align="R")
            pdf.ln(5.5)
        pdf.ln(4)

    # ── CD accounts ───────────────────────────────────────────────────────────
    if has_cds:
        pdf.set_font(pdf.FONT_FAMILY, style="B", size=9)
        pdf.set_text_color(*C_ACCENT)
        pdf.cell(0, 6, "Certificates of Deposit", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

        headers = ["Account #", "Principal", "Rate", "Term", "Issue Date", "Maturity Date", "Interest Accrued", "Current Value"]
        col_widths = [22.0, 25.0, 14.0, 14.0, 22.0, 24.0, 28.0, 25.0]

        pdf.set_font(pdf.FONT_FAMILY, style="B", size=7.5)
        pdf.set_fill_color(*C_PRIMARY)
        pdf.set_text_color(*C_WHITE)
        for hdr, cw in zip(headers, col_widths):
            align = "R" if hdr in ("Principal", "Interest Accrued", "Current Value") else "L"
            pdf.cell(cw, 6, hdr, fill=True, border=0, align=align)
        pdf.ln(6)

        for i, cd in enumerate(data.cd_accounts):
            fill = i % 2 == 0
            pdf.set_fill_color(*C_LIGHT)
            pdf.set_font(pdf.FONT_FAMILY, size=7.5)
            pdf.set_text_color(*C_DARK)
            pdf.cell(col_widths[0], 5.5, cd.display_id, fill=fill, border=0)
            pdf.cell(col_widths[1], 5.5, NumberFormatter.currency(cd.principal), fill=fill, border=0, align="R")
            pdf.cell(col_widths[2], 5.5, NumberFormatter.rate(cd.rate), fill=fill, border=0, align="R")
            pdf.cell(col_widths[3], 5.5, f"{cd.term_months}mo", fill=fill, border=0, align="R")
            pdf.cell(col_widths[4], 5.5, DateFormatter.short(cd.issue_date), fill=fill, border=0)
            pdf.cell(col_widths[5], 5.5, DateFormatter.short(cd.maturity_date), fill=fill, border=0)
            pdf.cell(col_widths[6], 5.5, NumberFormatter.currency(cd.interest_accrued), fill=fill, border=0, align="R")
            pdf.cell(col_widths[7], 5.5, NumberFormatter.currency(cd.current_value), fill=fill, border=0, align="R")
            pdf.ln(5.5)
        pdf.ln(3)
