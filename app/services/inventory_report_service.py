"""PDF report for a completed inventory session."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from fpdf.fonts import FontFace

from app.services.pdf_report_base import (
    DANGER as _DANGER,
    FONT as _FONT,
    HEAD_BG as _HEAD_BG,
    INK as _INK,
    LINE as _LINE,
    MUTED as _MUTED,
    SUCCESS as _SUCCESS,
    ReportPDF as _ReportPDF,
    fmt_money as _fmt_money,
    utc_now_label,
)


def report_filename(inv_session: Mapping[str, Any]) -> str:
    return f"inventory-session-{inv_session['date_from']}-to-{inv_session['date_to']}.pdf"


def _fmt_timestamp(value: object) -> str:
    """'2026-11-14T18:54:02.383+00:00' -> '2026-11-14 18:54 UTC'."""
    text = str(value or "").strip()
    if not text:
        return "-"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return text
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)
        return parsed.strftime("%Y-%m-%d %H:%M UTC")
    return parsed.strftime("%Y-%m-%d %H:%M")


def _fmt_diff(value: int) -> str:
    return f"+{value}" if value > 0 else str(value)


def build_session_report(inv_session: Mapping[str, Any], linked_assets: Sequence[Mapping[str, Any]]) -> bytes:
    generated = utc_now_label()
    running_title = (
        f"Inventory session {inv_session['date_from']} to {inv_session['date_to']}"
        f"  ·  {inv_session['responsible_person']}"
    )
    pdf = _ReportPDF(running_title, generated)
    pdf.add_page()

    # --- Title ---------------------------------------------------------------
    pdf.set_font(_FONT, "B", 18)
    pdf.set_text_color(*_INK)
    pdf.cell(0, 9, "Inventory session report", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(_FONT, "", 10)
    pdf.set_text_color(*_MUTED)
    pdf.cell(
        0, 6,
        f"{inv_session['date_from']} to {inv_session['date_to']}  ·  {inv_session['responsible_person']}"
        f"  ·  {inv_session['status']}",
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.ln(4)

    # --- Totals --------------------------------------------------------------
    rows = []
    for asset in linked_assets:
        total_qty = int(asset["total_quantity"] or 0)
        session_qty = int(asset["quantity"] or 0)
        unit_value = float(asset["initial_value"] or 0)
        is_deleted = "deleted_at" in asset.keys() and bool(asset["deleted_at"])
        rows.append({
            "name": str(asset["name"]) + (" (deleted)" if is_deleted else ""),
            "category": str(asset["category"] or "-"),
            "total": total_qty,
            "session": session_qty,
            "diff": session_qty - total_qty,
            "unit": unit_value,
            "line": unit_value * session_qty,
        })

    sum_total = sum(r["total"] for r in rows)
    sum_session = sum(r["session"] for r in rows)
    sum_line = sum(r["line"] for r in rows)
    discrepancies = sum(1 for r in rows if r["diff"] != 0)

    tiles = [
        ("Assets in session", str(len(rows))),
        ("Total quantity", str(sum_total)),
        ("Session quantity", str(sum_session)),
        ("Rows with difference", str(discrepancies)),
    ]
    tile_w, gap, top = 42, 4, pdf.get_y()
    for i, (label, value) in enumerate(tiles):
        x = 15 + i * (tile_w + gap)
        pdf.set_draw_color(*_LINE)
        pdf.rect(x, top, tile_w, 16)
        pdf.set_xy(x + 3, top + 2)
        pdf.set_font(_FONT, "", 7.5)
        pdf.set_text_color(*_MUTED)
        pdf.cell(tile_w - 6, 4, label)
        pdf.set_xy(x + 3, top + 7)
        pdf.set_font(_FONT, "B", 13)
        color = _DANGER if label == "Rows with difference" and discrepancies else _INK
        pdf.set_text_color(*color)
        pdf.cell(tile_w - 6, 7, value)
    pdf.set_y(top + 22)

    # --- Session details -----------------------------------------------------
    def section(title: str) -> None:
        pdf.set_font(_FONT, "B", 11)
        pdf.set_text_color(*_INK)
        pdf.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

    def by(timestamp_key: str, email_key: str) -> str:
        text = _fmt_timestamp(inv_session[timestamp_key])
        email = inv_session[email_key]
        return f"{text} by {email}" if email and text != "-" else text

    section("Session details")
    details = [
        ("Responsible person", str(inv_session["responsible_person"])),
        ("Date window", f"{inv_session['date_from']} to {inv_session['date_to']}"),
        ("Status", str(inv_session["status"])),
        ("Created", by("created_at", "created_by_email")),
        ("Started", by("started_at", "started_by_email")),
        ("Completed", by("completed_at", "completed_by_email")),
        ("Completion reason", str(inv_session["completion_reason"] or "-")),
        ("Notes", str(inv_session["notes"] or "-")),
        ("Session id", str(inv_session["id"])),
    ]
    for label, value in details:
        pdf.set_font(_FONT, "", 9)
        pdf.set_text_color(*_MUTED)
        pdf.cell(42, 5.5, label)
        pdf.set_text_color(*_INK)
        pdf.multi_cell(0, 5.5, value, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    # --- Asset table ---------------------------------------------------------
    section("Fixed assets in session")
    if not rows:
        pdf.set_font(_FONT, "", 9)
        pdf.set_text_color(*_MUTED)
        pdf.cell(0, 6, "No fixed assets were linked to this session.", new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.set_font(_FONT, "", 8.5)
        pdf.set_text_color(*_INK)
        pdf.set_draw_color(*_LINE)
        headings = FontFace(emphasis="BOLD", color=_MUTED, fill_color=_HEAD_BG)
        align = ("RIGHT", "LEFT", "LEFT", "RIGHT", "RIGHT", "RIGHT", "RIGHT", "RIGHT")
        with pdf.table(
            col_widths=(8, 45, 27, 17, 20, 20, 21, 22),
            text_align=align,
            headings_style=headings,
            borders_layout="HORIZONTAL_LINES",
            line_height=4.8,
            padding=(1.2, 1.5),
        ) as table:
            head = table.row()
            for text in ("#", "Asset", "Category", "Total qty", "Session qty", "Difference", "Unit value", "Line value"):
                head.cell(text)
            for index, r in enumerate(rows, start=1):
                row = table.row()
                row.cell(str(index))
                row.cell(r["name"])
                row.cell(r["category"])
                row.cell(str(r["total"]))
                row.cell(str(r["session"]))
                diff_color = _SUCCESS if r["diff"] > 0 else _DANGER if r["diff"] < 0 else _MUTED
                row.cell(_fmt_diff(r["diff"]), style=FontFace(color=diff_color, emphasis="BOLD" if r["diff"] else None))
                row.cell(_fmt_money(r["unit"]))
                row.cell(_fmt_money(r["line"]))
            total_style = FontFace(emphasis="BOLD", fill_color=_HEAD_BG)
            total = table.row()
            total.cell("Total", colspan=3, style=total_style, align="LEFT")
            total.cell(str(sum_total), style=total_style)
            total.cell(str(sum_session), style=total_style)
            total.cell(_fmt_diff(sum_session - sum_total), style=total_style)
            total.cell("", style=total_style)
            total.cell(_fmt_money(sum_line), style=total_style)

        pdf.ln(2)
        pdf.set_font(_FONT, "", 7.5)
        pdf.set_text_color(*_MUTED)
        pdf.multi_cell(
            0, 4,
            "Total qty is the quantity registered on the fixed asset record when this report was generated. "
            "Difference = session qty - total qty. Line value = unit value × session qty.",
            new_x="LMARGIN", new_y="NEXT",
        )

    # --- Sign-off ------------------------------------------------------------
    if pdf.get_y() > 245:
        pdf.add_page()
    pdf.ln(12)
    y = pdf.get_y()
    for i, label in enumerate(("Responsible person", "Approved by")):
        x = 15 + i * 95
        pdf.set_draw_color(*_MUTED)
        pdf.line(x, y + 10, x + 80, y + 10)
        pdf.set_xy(x, y + 11)
        pdf.set_font(_FONT, "", 8)
        pdf.set_text_color(*_MUTED)
        pdf.cell(80, 4, f"{label}: name, signature, date")

    return bytes(pdf.output())
