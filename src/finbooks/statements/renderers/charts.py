import tempfile
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

matplotlib.use("Agg")  # non-interactive backend — must be set before any other plt calls


class MatplotlibChartRenderer:
    """Renders charts to temporary PNG files for embedding in fpdf2 documents."""

    # Brand palette (matches BaseStatement)
    NAVY = "#1E3C72"
    STEEL = "#0078B4"
    GOLD = "#D4A84B"
    GRAY = "#8E9AAB"
    LIGHT = "#F0F4F8"

    ALLOCATION_COLORS = ["#1E3C72", "#0078B4", "#D4A84B", "#8E9AAB"]

    @classmethod
    def asset_allocation_pie(
        cls,
        equity_pct: float,
        cash_pct: float,
        cd_pct: float,
    ) -> Path:
        """Render an asset allocation pie chart. Returns temp PNG path."""
        labels: list[str] = []
        sizes: list[float] = []
        colors: list[str] = []
        color_map = {
            "Equities": cls.NAVY,
            "Cash": cls.STEEL,
            "CDs": cls.GOLD,
        }
        for label, pct, color in [
            ("Equities", equity_pct, cls.NAVY),
            ("Cash", cash_pct, cls.STEEL),
            ("CDs", cd_pct, cls.GOLD),
        ]:
            if pct > 0:
                labels.append(f"{label}\n{pct:.1f}%")
                sizes.append(pct)
                colors.append(color)

        fig, ax = plt.subplots(figsize=(4.5, 3.2), facecolor="white")
        if sizes:
            wedges, texts = ax.pie(
                sizes,
                labels=labels,
                colors=colors,
                startangle=90,
                wedgeprops={"linewidth": 1.5, "edgecolor": "white"},
                textprops={"fontsize": 9, "color": "#1E1E1E"},
            )
        ax.set_title("Asset Allocation", fontsize=11, fontweight="bold", color="#1E3C72", pad=10)
        fig.tight_layout(pad=0.5)

        tmp = Path(tempfile.mktemp(suffix=".png"))
        fig.savefig(tmp, dpi=150, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        return tmp

    @classmethod
    def portfolio_bar(
        cls,
        labels: list[str],
        values: list[float],
        title: str = "Portfolio Value",
        value_prefix: str = "$",
    ) -> Path:
        """Simple horizontal bar chart. Returns temp PNG path."""
        fig, ax = plt.subplots(figsize=(5.5, max(2.0, len(labels) * 0.55 + 0.5)), facecolor="white")
        y_pos = np.arange(len(labels))
        bars = ax.barh(y_pos, values, color=cls.NAVY, edgecolor="white", height=0.6)

        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels, fontsize=9)
        ax.set_title(title, fontsize=11, fontweight="bold", color="#1E3C72", pad=8)
        ax.tick_params(axis="x", labelsize=8)
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_facecolor(cls.LIGHT)
        fig.patch.set_facecolor("white")

        for bar, val in zip(bars, values):
            ax.text(
                bar.get_width() + max(values) * 0.01,
                bar.get_y() + bar.get_height() / 2,
                f"{value_prefix}{val:,.2f}",
                va="center",
                fontsize=8,
                color="#1E1E1E",
            )
        fig.tight_layout(pad=0.5)

        tmp = Path(tempfile.mktemp(suffix=".png"))
        fig.savefig(tmp, dpi=150, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        return tmp
