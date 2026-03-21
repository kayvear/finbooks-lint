from decimal import Decimal

from pydantic import BaseModel, computed_field


class EquityPosition(BaseModel):
    position_id: str  # UUID string
    account_id: str
    symbol: str
    quantity: Decimal  # shares (may be fractional)
    cost_basis_per_share: Decimal  # average cost basis
    current_price: Decimal  # end-of-period mark

    @computed_field  # type: ignore[misc]
    @property
    def market_value(self) -> Decimal:
        return (self.quantity * self.current_price).quantize(Decimal("0.01"))

    @computed_field  # type: ignore[misc]
    @property
    def total_cost_basis(self) -> Decimal:
        return (self.quantity * self.cost_basis_per_share).quantize(Decimal("0.01"))

    @computed_field  # type: ignore[misc]
    @property
    def unrealized_pnl(self) -> Decimal:
        return (self.market_value - self.total_cost_basis).quantize(Decimal("0.01"))

    @computed_field  # type: ignore[misc]
    @property
    def unrealized_pnl_pct(self) -> Decimal:
        if self.total_cost_basis == 0:
            return Decimal("0.00")
        return (self.unrealized_pnl / self.total_cost_basis * 100).quantize(Decimal("0.01"))
