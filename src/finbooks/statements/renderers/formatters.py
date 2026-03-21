from datetime import date
from decimal import Decimal


class NumberFormatter:
    @staticmethod
    def currency(value: Decimal | float, show_sign: bool = False) -> str:
        v = float(value)
        if show_sign and v >= 0:
            return f"+${v:,.2f}"
        if v < 0:
            return f"-${abs(v):,.2f}"
        return f"${v:,.2f}"

    @staticmethod
    def shares(value: Decimal | float) -> str:
        v = float(value)
        if v == int(v):
            return f"{int(v):,}"
        return f"{v:,.4f}"

    @staticmethod
    def pct(value: Decimal | float, show_sign: bool = True) -> str:
        v = float(value)
        if show_sign and v >= 0:
            return f"+{v:.2f}%"
        return f"{v:.2f}%"

    @staticmethod
    def rate(value: Decimal | float) -> str:
        """Format a decimal rate as percentage, e.g. 0.051 → '5.10%'."""
        return f"{float(value) * 100:.2f}%"


class DateFormatter:
    @staticmethod
    def short(d: date) -> str:
        return d.strftime("%m/%d/%Y")

    @staticmethod
    def medium(d: date) -> str:
        return d.strftime("%b %d, %Y")

    @staticmethod
    def period(start: date, end: date) -> str:
        return f"{start.strftime('%B %d, %Y')} to {end.strftime('%B %d, %Y')}"
