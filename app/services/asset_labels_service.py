"""Printable QR labels for fixed assets.

Each label has a QR code with the asset's page URL, so scanning it with a phone
camera opens the asset, plus its name, category, location and short id. The
layout matches A4 sheets of 3 × 7 labels of 63.5 × 38.1 mm (such as Avery
L7160), and also works on plain paper cut by hand.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

import segno
from fpdf import FPDF

from app.services.pdf_report_base import FONT, INK, LINE, MUTED, register_fonts

COLUMNS = 3
ROWS = 7
LABELS_PER_PAGE = COLUMNS * ROWS
LABEL_W = 63.5
LABEL_H = 38.1
MARGIN_LEFT = 7.2
MARGIN_TOP = 15.1
COLUMN_GAP = 2.5
PADDING = 2.5
QR_SIZE = 26.0  # about 0.7 mm per module for a typical URL, which phones read easily
SHORT_ID_LENGTH = 8
QR_MASK = 0


def asset_url(base_url: str, asset_id: str) -> str:
    return f"{base_url.rstrip('/')}/fixed-assets/id/{asset_id}"


def short_id(asset_id: str) -> str:
    """The first characters of the id, printed on the label for typing in by hand."""
    return asset_id[:SHORT_ID_LENGTH]


def labels_filename(today: date | None = None) -> str:
    return f"asset-labels-{(today or date.today()).isoformat()}.pdf"


def _draw_qr(pdf: FPDF, data: str, x: float, y: float, size: float) -> None:
    """Draw the QR code as filled squares, so it stays sharp at any print size."""
    # A fixed mask skips trying all eight, which is most of the encoding time.
    # Any mask gives a valid code that every scanner reads.
    qr = segno.make(data, error="m", mask=QR_MASK)
    matrix = [list(row) for row in qr.matrix]
    quiet_zone = 2  # modules of white border; the label padding adds more
    modules = len(matrix) + 2 * quiet_zone
    module = size / modules
    pdf.set_fill_color(*INK)
    for row_index, row in enumerate(matrix):
        run_start = None
        for col_index, dark in enumerate([*row, 0]):
            if dark and run_start is None:
                run_start = col_index
            elif not dark and run_start is not None:
                pdf.rect(
                    x + (quiet_zone + run_start) * module,
                    y + (quiet_zone + row_index) * module,
                    (col_index - run_start) * module,
                    module,
                    style="F",
                )
                run_start = None


def _fit(pdf: FPDF, text: str, width: float) -> str:
    """Cut text with an ellipsis so it fits on one line."""
    if pdf.get_string_width(text) <= width:
        return text
    while text and pdf.get_string_width(text + "…") > width:
        text = text[:-1]
    return text.rstrip() + "…"


def _draw_label(pdf: FPDF, asset: Mapping[str, Any], base_url: str, x: float, y: float) -> None:
    asset_id = str(asset["id"])
    _draw_qr(pdf, asset_url(base_url, asset_id), x + PADDING, y + (LABEL_H - QR_SIZE) / 2, QR_SIZE)

    text_x = x + PADDING + QR_SIZE + 1.5
    text_w = x + LABEL_W - PADDING - text_x
    pdf.set_text_color(*INK)
    pdf.set_font(FONT, "B", 8.5)
    pdf.set_xy(text_x, y + PADDING + 1)
    # Up to two lines for the name.
    name = str(asset["name"])
    lines = pdf.multi_cell(text_w, 3.8, name, dry_run=True, output="LINES")
    if len(lines) > 2:
        lines = [lines[0], _fit(pdf, " ".join(lines[1:]), text_w)]
    for line in lines:
        pdf.set_x(text_x)
        pdf.cell(text_w, 3.8, line, new_x="LEFT", new_y="NEXT")

    pdf.set_font(FONT, "", 7)
    pdf.set_text_color(*MUTED)
    for detail in (asset["category"], asset["location"] if "location" in asset.keys() else None):
        if detail:
            pdf.set_x(text_x)
            pdf.cell(text_w, 3.4, _fit(pdf, str(detail), text_w), new_x="LEFT", new_y="NEXT")

    pdf.set_font(FONT, "B", 9)
    pdf.set_text_color(*INK)
    pdf.set_xy(text_x, y + LABEL_H - PADDING - 4.5)
    pdf.cell(text_w, 4.5, short_id(asset_id))


def build_labels_pdf(assets: Sequence[Mapping[str, Any]], base_url: str) -> bytes:
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    register_fonts(pdf)
    pdf.set_auto_page_break(auto=False)
    pdf.set_title("Asset labels")
    pdf.set_creator("Asset Registry")

    if not assets:
        pdf.add_page()
        pdf.set_font(FONT, "", 11)
        pdf.set_text_color(*MUTED)
        pdf.set_xy(15, 20)
        pdf.cell(0, 8, "No fixed assets match the current filters.")
        return bytes(pdf.output())

    for index, asset in enumerate(assets):
        slot = index % LABELS_PER_PAGE
        if slot == 0:
            pdf.add_page()
        column, row = slot % COLUMNS, slot // COLUMNS
        x = MARGIN_LEFT + column * (LABEL_W + COLUMN_GAP)
        y = MARGIN_TOP + row * LABEL_H
        # Faint outline as a cutting guide on plain paper.
        pdf.set_draw_color(*LINE)
        pdf.set_line_width(0.1)
        pdf.rect(x, y, LABEL_W, LABEL_H)
        _draw_label(pdf, asset, base_url, x, y)
    return bytes(pdf.output())
