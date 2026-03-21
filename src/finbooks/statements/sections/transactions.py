from finbooks.models.statement import StatementData
from finbooks.models.transaction import BankTxnType
from finbooks.statements.base import C_DARK, C_LIGHT, C_NEGATIVE, C_PRIMARY, C_POSITIVE, C_WHITE, BaseStatement
from finbooks.statements.renderers.formatters import DateFormatter, NumberFormatter


def render_transactions(pdf: BaseStatement, data: StatementData) -> None:
    """Render combined transaction history table (bank + trades + dividends)."""

    # Combine all transactions into a flat list with a type tag
    rows: list[dict] = []

    for txn in data.bank_transactions:
        rows.append({
            "date": txn.transaction_date,
            "type": txn.txn_type.value.replace("_", " ").title(),
            "description": txn.description,
            "amount": txn.amount,
            "balance": txn.running_balance,
            "account": txn.account_id[-4:].upper(),
        })

    for txn in data.trade_transactions:
        action = "Buy" if txn.side.value == "buy" else "Sell"
        rows.append({
            "date": txn.transaction_date,
            "type": f"{action} {txn.symbol}",
            "description": f"{NumberFormatter.shares(txn.quantity)} sh @ {NumberFormatter.currency(txn.price_per_share)}",
            "amount": txn.amount,
            "balance": txn.running_balance,
            "account": txn.account_id[-4:].upper(),
        })

    for txn in data.dividend_transactions:
        rows.append({
            "date": txn.transaction_date,
            "type": f"Dividend {txn.symbol}",
            "description": f"{NumberFormatter.shares(txn.shares_held)} sh × {NumberFormatter.currency(txn.dividend_per_share)}/sh",
            "amount": txn.amount,
            "balance": txn.running_balance,
            "account": txn.account_id[-4:].upper(),
        })

    for txn in data.cd_transactions:
        rows.append({
            "date": txn.transaction_date,
            "type": txn.txn_type.value.replace("_", " ").title(),
            "description": txn.description,
            "amount": txn.amount,
            "balance": txn.running_balance,
            "account": txn.account_id[-4:].upper(),
        })

    if not rows:
        return

    # Sort by date ascending
    rows.sort(key=lambda r: r["date"])

    pdf.section_title("Transaction History")

    headers = ["Date", "Account", "Type", "Description", "Amount", "Balance"]
    col_widths = [22.0, 17.0, 30.0, 65.0, 25.0, 25.0]

    # Header row
    pdf.set_font(pdf.FONT_FAMILY, style="B", size=8)
    pdf.set_fill_color(*C_PRIMARY)
    pdf.set_text_color(*C_WHITE)
    for hdr, cw in zip(headers, col_widths):
        align = "R" if hdr in ("Amount", "Balance") else "L"
        pdf.cell(cw, 7, hdr, fill=True, border=0, align=align)
    pdf.ln(7)

    for i, row in enumerate(rows):
        fill = i % 2 == 0
        pdf.set_fill_color(*C_LIGHT)
        pdf.set_font(pdf.FONT_FAMILY, size=7.5)
        pdf.set_text_color(*C_DARK)

        amount_positive = row["amount"] >= 0
        cells = [
            (DateFormatter.short(row["date"]), "L"),
            (f"...{row['account']}", "L"),
            (str(row["type"])[:18], "L"),
            (str(row["description"])[:40], "L"),
            (NumberFormatter.currency(row["amount"], show_sign=True), "R"),
            (NumberFormatter.currency(row["balance"]), "R"),
        ]

        for j, ((cell_text, align), cw) in enumerate(zip(cells, col_widths)):
            if j == 4:  # Amount column — color by sign
                pdf.set_text_color(*(C_POSITIVE if amount_positive else C_NEGATIVE))
            else:
                pdf.set_text_color(*C_DARK)
            pdf.cell(cw, 5.5, cell_text, fill=fill, border=0, align=align)
        pdf.ln(5.5)

    pdf.ln(3)
