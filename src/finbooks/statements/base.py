from fpdf import FPDF
from fpdf.fonts import FontFace

# ── Brand palette ─────────────────────────────────────────────────────────────
# Neutral professional colors — no firm branding
C_PRIMARY = (30, 60, 114)     # Deep navy  — headings, borders
C_ACCENT = (0, 120, 180)      # Steel blue — section titles, highlights
C_LIGHT = (240, 244, 248)     # Light gray-blue — table alt rows, header bg
C_DARK = (30, 30, 30)         # Near-black — body text
C_MID = (100, 110, 125)       # Mid gray   — secondary text, footers
C_WHITE = (255, 255, 255)
C_POSITIVE = (22, 130, 70)    # Green — positive P&L
C_NEGATIVE = (192, 40, 40)    # Red   — negative P&L


class BaseStatement(FPDF):
    """
    Base PDF class for all customer statements.
    Provides consistent header/footer and shared style helpers.
    """

    FONT_FAMILY = "helvetica"  # built-in, no embedding needed for Phase 1
    MARGIN_LEFT = 15.0
    MARGIN_RIGHT = 15.0
    MARGIN_TOP = 20.0

    def __init__(self, institution_name: str = "Financial Services, Inc.") -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.institution_name = institution_name
        self._account_display: str = ""
        self._period_label: str = ""

        self.set_margins(self.MARGIN_LEFT, self.MARGIN_TOP, self.MARGIN_RIGHT)
        self.set_auto_page_break(auto=True, margin=18)
        self.set_font(self.FONT_FAMILY, size=10)

    def set_statement_meta(self, account_display: str, period_label: str) -> None:
        self._account_display = account_display
        self._period_label = period_label

    def normalize_text(self, txt: str) -> str:  # type: ignore[override]
        """Sanitize non-Latin-1 chars before fpdf2 encoding check."""
        txt = (
            txt.replace("\u2014", "-")   # em dash
               .replace("\u2013", "-")   # en dash
               .replace("\u2018", "'")   # left single quote
               .replace("\u2019", "'")   # right single quote / apostrophe
               .replace("\u201c", '"')   # left double quote
               .replace("\u201d", '"')   # right double quote
               .replace("\u2022", "*")   # bullet
               .replace("\u00a0", " ")   # non-breaking space
        )
        return super().normalize_text(txt)  # type: ignore[misc]

    # ── fpdf2 auto-called hooks ───────────────────────────────────────────────

    def header(self) -> None:
        # Left: institution name
        self.set_font(self.FONT_FAMILY, style="B", size=11)
        self.set_text_color(*C_PRIMARY)
        self.cell(0, 8, self.institution_name, new_x="LEFT", new_y="NEXT")

        # Thin rule beneath header
        self.set_draw_color(*C_PRIMARY)
        self.set_line_width(0.4)
        self.line(self.MARGIN_LEFT, self.get_y(), self.w - self.MARGIN_RIGHT, self.get_y())

        # Account + period on same line
        self.set_font(self.FONT_FAMILY, size=8)
        self.set_text_color(*C_MID)
        if self._account_display:
            self.cell(95, 5, f"Account: {self._account_display}", new_x="RIGHT", new_y="TOP")
        if self._period_label:
            self.cell(0, 5, f"Period: {self._period_label}", align="R", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def footer(self) -> None:
        self.set_y(-14)
        self.set_draw_color(*C_LIGHT)
        self.set_line_width(0.3)
        self.line(self.MARGIN_LEFT, self.get_y(), self.w - self.MARGIN_RIGHT, self.get_y())
        self.ln(1)

        self.set_font(self.FONT_FAMILY, style="I", size=7)
        self.set_text_color(*C_MID)
        self.cell(
            0, 5,
            "CONFIDENTIAL — For the sole use of the named account holder. "
            "Not for redistribution.",
            align="C",
            new_x="LMARGIN", new_y="NEXT",
        )
        self.cell(0, 4, f"Page {self.page_no()}", align="C")

    # ── Style helpers ─────────────────────────────────────────────────────────

    def section_title(self, text: str) -> None:
        """Render a bold section header with an accent underline."""
        self.ln(3)
        self.set_font(self.FONT_FAMILY, style="B", size=11)
        self.set_text_color(*C_PRIMARY)
        self.cell(0, 7, text, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*C_ACCENT)
        self.set_line_width(0.5)
        self.line(self.MARGIN_LEFT, self.get_y(), self.w - self.MARGIN_RIGHT, self.get_y())
        self.ln(2)
        self.set_text_color(*C_DARK)

    def table_header_face(self) -> FontFace:
        return FontFace(
            family=self.FONT_FAMILY,
            emphasis="BOLD",
            size_pt=9,
            color=C_WHITE,
            fill_color=C_PRIMARY,
        )

    def alt_row_face(self) -> FontFace:
        return FontFace(fill_color=C_LIGHT)

    def label_value_row(self, label: str, value: str, indent: float = 0) -> None:
        """Render a simple two-column label: value row."""
        self.set_font(self.FONT_FAMILY, size=9)
        self.set_text_color(*C_MID)
        self.cell(60 + indent, 6, label)
        self.set_text_color(*C_DARK)
        self.set_font(self.FONT_FAMILY, style="B", size=9)
        self.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")
        self.set_font(self.FONT_FAMILY, size=9)

    def colored_amount(self, value_str: str, positive: bool) -> None:
        """Write a currency string in green (positive) or red (negative)."""
        self.set_text_color(*(C_POSITIVE if positive else C_NEGATIVE))
        self.set_font(self.FONT_FAMILY, style="B", size=9)
        self.cell(0, 6, value_str, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(*C_DARK)
        self.set_font(self.FONT_FAMILY, size=9)
