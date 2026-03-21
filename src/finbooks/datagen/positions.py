"""
Derives end-of-period equity positions from trade transactions + end prices.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pandas as pd

from finbooks.models.position import EquityPosition
from finbooks.models.price import PriceHistory
from finbooks.models.transaction import TradeTransaction, TradeSide
from finbooks.settings import settings


class PositionBuilder:
    """
    Reconstructs positions from trade blotter.
    Average cost basis is computed using FIFO-like weighted average method.
    """

    def build(
        self,
        trades: list[TradeTransaction],
        price_histories: dict[str, PriceHistory],
    ) -> list[EquityPosition]:
        # Group trades by account
        by_account: dict[str, list[TradeTransaction]] = {}
        for t in trades:
            by_account.setdefault(t.account_id, []).append(t)

        positions: list[EquityPosition] = []

        for account_id, account_trades in by_account.items():
            # Per symbol: track qty and weighted avg cost
            qty: dict[str, Decimal] = {}
            cost_basis: dict[str, Decimal] = {}  # total cost, not per share

            for t in sorted(account_trades, key=lambda x: x.transaction_date):
                sym = t.symbol
                if t.side == TradeSide.BUY:
                    prev_qty = qty.get(sym, Decimal("0"))
                    prev_cost = cost_basis.get(sym, Decimal("0"))
                    new_cost = t.quantity * t.price_per_share
                    qty[sym] = prev_qty + t.quantity
                    cost_basis[sym] = prev_cost + new_cost
                else:  # SELL
                    prev_qty = qty.get(sym, Decimal("0"))
                    if prev_qty > 0:
                        sell_qty = min(t.quantity, prev_qty)
                        # Reduce cost basis proportionally
                        proportion = sell_qty / prev_qty
                        cost_basis[sym] = cost_basis.get(sym, Decimal("0")) * (1 - proportion)
                        qty[sym] = prev_qty - sell_qty

            # Build EquityPosition for each symbol with positive quantity
            for sym, shares in qty.items():
                if shares <= 0:
                    continue
                hist = price_histories.get(sym)
                end_price = Decimal("100.00")  # fallback
                if hist:
                    p = hist.close_on(settings.statement_end)
                    if p is None:
                        prior = [x for x in hist.prices if x.price_date <= settings.statement_end]
                        if prior:
                            p = prior[-1].close
                    if p:
                        end_price = p

                total_cost = cost_basis.get(sym, Decimal("0"))
                avg_cost = (total_cost / shares).quantize(Decimal("0.0001")) if shares > 0 else Decimal("0")

                positions.append(EquityPosition(
                    position_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{account_id}-{sym}")),
                    account_id=account_id,
                    symbol=sym,
                    quantity=shares.quantize(Decimal("0.0001")),
                    cost_basis_per_share=avg_cost,
                    current_price=end_price,
                ))

        return positions

    def to_dataframe(self, positions: list[EquityPosition]) -> pd.DataFrame:
        records = []
        for p in positions:
            records.append({
                "position_id": p.position_id,
                "account_id": p.account_id,
                "symbol": p.symbol,
                "quantity": float(p.quantity),
                "cost_basis_per_share": float(p.cost_basis_per_share),
                "current_price": float(p.current_price),
                "market_value": float(p.market_value),
                "total_cost_basis": float(p.total_cost_basis),
                "unrealized_pnl": float(p.unrealized_pnl),
                "unrealized_pnl_pct": float(p.unrealized_pnl_pct),
            })
        return pd.DataFrame(records)
