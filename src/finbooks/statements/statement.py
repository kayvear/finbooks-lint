from finbooks.models.statement import StatementData
from finbooks.statements.base import BaseStatement
from finbooks.statements.sections.asset_allocation import render_asset_allocation
from finbooks.statements.sections.banking import render_banking
from finbooks.statements.sections.cover import render_cover
from finbooks.statements.sections.positions import render_positions
from finbooks.statements.sections.transactions import render_transactions


class CustomerStatement(BaseStatement):
    """
    Full customer statement PDF.
    Composes sections in order: Cover → Allocation → Holdings → Transactions → Banking.
    """

    def build(self, data: StatementData) -> None:
        """Render all sections in sequence."""
        self.set_statement_meta(
            account_display=data.summary.customer.display_id,
            period_label=data.summary.period.label,
        )

        render_cover(self, data)
        render_asset_allocation(self, data)

        # Holdings and transactions on subsequent pages (auto page break handles overflow)
        if data.equity_positions:
            render_positions(self, data)

        has_transactions = any([
            data.bank_transactions,
            data.trade_transactions,
            data.dividend_transactions,
            data.cd_transactions,
        ])
        if has_transactions:
            render_transactions(self, data)

        render_banking(self, data)
