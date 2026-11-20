"""Shared look and feel for the app's PDF reports (fonts, palette, page chrome)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from fpdf import FPDF

_FONT_DIR = Path(__file__).resolve().parent.parent / "fonts"
_LOGO = Path(__file__).resolve().parent.parent / "static" / "favicon.svg"
FONT = "PlexSans"

# Colours match the app's Slate Ledger palette.
INK = (20, 32, 44)
MUTED = (100, 114, 131)
LINE = (226, 231, 236)
HEAD_BG = (244, 246, 248)
SUCCESS = (20, 121, 79)
DANGER = (196, 53, 43)


def utc_now_label() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def fmt_money(value: float) -> str:
    return f"{value:,.2f}".replace(",", " ")


def register_fonts(pdf: FPDF) -> None:
    """Add the app's fonts to a PDF as FONT (regular) and FONT "B" (semibold)."""
    pdf.add_font(FONT, "", str(_FONT_DIR / "IBMPlexSans-Regular.ttf"))
    pdf.add_font(FONT, "B", str(_FONT_DIR / "IBMPlexSans-SemiBold.ttf"))


class ReportPDF(FPDF):
    def __init__(self, title: str, generated: str) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.report_title = title
        self.generated = generated
        register_fonts(self)
        self.set_margins(15, 15, 15)
        self.set_auto_page_break(auto=True, margin=18)
        self.set_title(title)
        self.set_creator("Asset Registry")

    def header(self) -> None:
        self.image(str(_LOGO), x=15, y=10.8, w=6.4, h=6.4)
        self.set_xy(23, 10.6)
        self.set_font(FONT, "B", 10)
        self.set_text_color(*INK)
        self.cell(80, 7, "Asset Registry")
        self.set_font(FONT, "", 8)
        self.set_text_color(*MUTED)
        self.set_xy(105, 10.6)
        self.cell(90, 7, self.report_title, align="R")
        self.set_draw_color(*LINE)
        self.line(15, 19.5, 195, 19.5)
        self.set_y(24)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font(FONT, "", 7.5)
        self.set_text_color(*MUTED)
        self.cell(90, 5, f"Generated {self.generated}")
        self.cell(90, 5, f"Page {self.page_no()} of {{nb}}", align="R")

    # --- Building blocks ------------------------------------------------------
    def report_heading(self, title: str, subtitle: str) -> None:
        self.set_font(FONT, "B", 18)
        self.set_text_color(*INK)
        self.cell(0, 9, title, new_x="LMARGIN", new_y="NEXT")
        self.set_font(FONT, "", 10)
        self.set_text_color(*MUTED)
        self.cell(0, 6, subtitle, new_x="LMARGIN", new_y="NEXT")
        self.ln(4)

    def summary_tiles(self, tiles: Sequence[tuple[str, str, tuple[int, int, int]]]) -> None:
        """Row of four bordered stat tiles: (label, value, value colour)."""
        tile_w, gap, top = 42, 4, self.get_y()
        for i, (label, value, color) in enumerate(tiles):
            x = 15 + i * (tile_w + gap)
            self.set_draw_color(*LINE)
            self.rect(x, top, tile_w, 16)
            self.set_xy(x + 3, top + 2)
            self.set_font(FONT, "", 7.5)
            self.set_text_color(*MUTED)
            self.cell(tile_w - 6, 4, label)
            self.set_xy(x + 3, top + 7)
            self.set_font(FONT, "B", 13)
            self.set_text_color(*color)
            self.cell(tile_w - 6, 7, value)
        self.set_y(top + 22)

    def section(self, title: str) -> None:
        self.set_font(FONT, "B", 11)
        self.set_text_color(*INK)
        self.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def note(self, text: str) -> None:
        self.set_font(FONT, "", 7.5)
        self.set_text_color(*MUTED)
        self.multi_cell(0, 4, text, new_x="LMARGIN", new_y="NEXT")

    def empty_state(self, text: str) -> None:
        self.set_font(FONT, "", 9)
        self.set_text_color(*MUTED)
        self.cell(0, 6, text, new_x="LMARGIN", new_y="NEXT")

    def table_text_style(self) -> None:
        self.set_font(FONT, "", 8.5)
        self.set_text_color(*INK)
        self.set_draw_color(*LINE)
