from finbooks.models.statement import StatementData
from finbooks.statements.base import BaseStatement
from finbooks.statements.renderers.charts import MatplotlibChartRenderer
from finbooks.statements.renderers.formatters import NumberFormatter


def render_asset_allocation(pdf: BaseStatement, data: StatementData) -> None:
    """Render asset allocation section with pie chart and value breakdown table."""
    alloc = data.summary.allocation

    pdf.section_title("Asset Allocation")

    # ── Pie chart (left) + breakdown table (right) ────────────────────────────
    chart_path = MatplotlibChartRenderer.asset_allocation_pie(
        equity_pct=alloc.equity_pct,
        cash_pct=alloc.cash_pct,
        cd_pct=alloc.cd_pct,
    )

    chart_w = 75.0
    table_x = pdf.MARGIN_LEFT + chart_w + 5
    start_y = pdf.get_y()

    pdf.image(str(chart_path), x=pdf.MARGIN_LEFT, y=start_y, w=chart_w)

    # Breakdown table to the right of the chart
    pdf.set_xy(table_x, start_y + 5)
    pdf.set_font(pdf.FONT_FAMILY, style="B", size=9)

    rows = [
        ("Equities", NumberFormatter.currency(alloc.equity_value), f"{alloc.equity_pct:.1f}%"),
        ("Cash", NumberFormatter.currency(alloc.cash_value), f"{alloc.cash_pct:.1f}%"),
        ("CDs", NumberFormatter.currency(alloc.cd_value), f"{alloc.cd_pct:.1f}%"),
        ("Total", NumberFormatter.currency(alloc.total_value), "100.0%"),
    ]

    col_widths = [35.0, 35.0, 20.0]

    # Header
    from finbooks.statements.base import C_PRIMARY, C_WHITE
    pdf.set_fill_color(*C_PRIMARY)
    pdf.set_text_color(*C_WHITE)
    for hdr, cw in zip(["Asset Class", "Value", "Weight"], col_widths):
        pdf.set_xy(pdf.get_x(), pdf.get_y()) if hdr != "Asset Class" else None
        pdf.cell(cw, 6, hdr, fill=True, border=0)
    pdf.ln(6)

    from finbooks.statements.base import C_DARK, C_LIGHT, C_MID
    for i, (label, value, weight) in enumerate(rows):
        fill = i % 2 == 0
        pdf.set_fill_color(*C_LIGHT)
        pdf.set_text_color(*C_DARK)
        is_total = label == "Total"
        pdf.set_font(pdf.FONT_FAMILY, style="B" if is_total else "", size=9)
        pdf.set_xy(table_x, pdf.get_y())
        pdf.cell(col_widths[0], 6, label, fill=fill, border=0)
        pdf.cell(col_widths[1], 6, value, fill=fill, border=0, align="R")
        pdf.cell(col_widths[2], 6, weight, fill=fill, border=0, align="R")
        pdf.ln(6)

    # Clean up temp file
    try:
        chart_path.unlink(missing_ok=True)
    except Exception:
        pass

    pdf.ln(3)
