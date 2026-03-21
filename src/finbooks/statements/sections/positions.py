from finbooks.models.statement import StatementData
from finbooks.statements.base import C_DARK, C_LIGHT, C_NEGATIVE, C_PRIMARY, C_POSITIVE, C_WHITE, BaseStatement
from finbooks.statements.renderers.formatters import NumberFormatter


def render_positions(pdf: BaseStatement, data: StatementData) -> None:
    """Render equity holdings table."""
    if not data.equity_positions:
        return

    pdf.section_title("Equity Holdings")

    headers = ["Symbol", "Shares", "Cost Basis/Sh", "Current Price", "Market Value", "Unrealized P&L", "P&L %"]
    col_widths = [22.0, 20.0, 30.0, 28.0, 30.0, 32.0, 20.0]

    # Header row
    pdf.set_font(pdf.FONT_FAMILY, style="B", size=8)
    pdf.set_fill_color(*C_PRIMARY)
    pdf.set_text_color(*C_WHITE)
    for hdr, cw in zip(headers, col_widths):
        align = "R" if hdr != "Symbol" else "L"
        pdf.cell(cw, 7, hdr, fill=True, border=0, align=align)
    pdf.ln(7)

    # Sort by market value descending
    positions = sorted(data.equity_positions, key=lambda p: p.market_value, reverse=True)

    total_market_value = sum(p.market_value for p in positions)
    total_cost_basis = sum(p.total_cost_basis for p in positions)
    total_pnl = total_market_value - total_cost_basis

    for i, pos in enumerate(positions):
        fill = i % 2 == 0
        pdf.set_fill_color(*C_LIGHT)
        pdf.set_font(pdf.FONT_FAMILY, size=8)
        pdf.set_text_color(*C_DARK)

        pnl_positive = pos.unrealized_pnl >= 0

        row = [
            pos.symbol,
            NumberFormatter.shares(pos.quantity),
            NumberFormatter.currency(pos.cost_basis_per_share),
            NumberFormatter.currency(pos.current_price),
            NumberFormatter.currency(pos.market_value),
            NumberFormatter.currency(pos.unrealized_pnl, show_sign=True),
            NumberFormatter.pct(pos.unrealized_pnl_pct),
        ]

        for j, (cell_text, cw) in enumerate(zip(row, col_widths)):
            align = "L" if j == 0 else "R"
            # Color the P&L columns
            if j in (5, 6):
                pdf.set_text_color(*(C_POSITIVE if pnl_positive else C_NEGATIVE))
            else:
                pdf.set_text_color(*C_DARK)
            pdf.cell(cw, 6, cell_text, fill=fill, border=0, align=align)
        pdf.ln(6)

    # Totals row
    pdf.set_font(pdf.FONT_FAMILY, style="B", size=8)
    pdf.set_fill_color(*C_PRIMARY)
    pdf.set_text_color(*C_WHITE)
    total_pnl_positive = total_pnl >= 0
    totals = [
        "TOTAL", "",
        NumberFormatter.currency(total_cost_basis / sum(p.quantity for p in positions) if positions else 0),
        "",
        NumberFormatter.currency(total_market_value),
        NumberFormatter.currency(total_pnl, show_sign=True),
        "",
    ]
    for cell_text, cw in zip(totals, col_widths):
        pdf.cell(cw, 7, cell_text, fill=True, border=0, align="R" if cell_text not in ("TOTAL", "") else "L")
    pdf.ln(7)
    pdf.ln(3)
