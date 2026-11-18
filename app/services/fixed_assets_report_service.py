"""PDF register of all fixed assets."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from fpdf.fonts import FontFace

from app.services.pdf_report_base import (
    HEAD_BG,
    INK,
    MUTED,
    ReportPDF,
    fmt_money,
    utc_now_label,
)


def report_filename(today: date | None = None) -> str:
    return f"fixed-assets-{(today or date.today()).isoformat()}.pdf"


def _rows(assets: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for asset in assets:
        quantity = int(asset["quantity"] or 0)
        unit_value = float(asset["initial_value"] or 0)
        rows.append({
            "name": str(asset["name"]),
            "category": str(asset["category"] or "-"),
            "responsible": str(asset["responsible_person"] or "-"),
            "registered": str(asset["registration_date"] or "-"),
            "quantity": quantity,
            "unit": unit_value,
            "total": unit_value * quantity,
        })
    rows.sort(key=lambda r: (r["category"].casefold(), r["name"].casefold()))
    return rows


def _category_summary(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_category: dict[str, dict[str, Any]] = {}
    for r in rows:
        entry = by_category.setdefault(r["category"], {"category": r["category"], "assets": 0, "quantity": 0, "total": 0.0})
        entry["assets"] += 1
        entry["quantity"] += r["quantity"]
        entry["total"] += r["total"]
    return sorted(by_category.values(), key=lambda e: e["category"].casefold())


def build_fixed_assets_report(assets: Sequence[Mapping[str, Any]]) -> bytes:
    generated = utc_now_label()
    rows = _rows(assets)
    categories = _category_summary(rows)
    sum_qty = sum(r["quantity"] for r in rows)
    sum_value = sum(r["total"] for r in rows)

    pdf = ReportPDF("Fixed assets register", generated)
    pdf.add_page()
    pdf.report_heading("Fixed assets report", f"All registered fixed assets  ·  as of {generated}")

    pdf.summary_tiles([
        ("Fixed assets", str(len(rows)), INK),
        ("Total quantity", str(sum_qty), INK),
        ("Total value", fmt_money(sum_value), INK),
        ("Categories", str(len(categories)), INK),
    ])

    if not rows:
        pdf.section("Fixed assets")
        pdf.empty_state("No fixed assets are registered.")
        return bytes(pdf.output())

    headings = FontFace(emphasis="BOLD", color=MUTED, fill_color=HEAD_BG)
    total_style = FontFace(emphasis="BOLD", fill_color=HEAD_BG)
    table_opts = dict(
        headings_style=headings,
        borders_layout="HORIZONTAL_LINES",
        line_height=4.8,
        padding=(1.2, 1.5),
    )

    # --- Summary by category ---------------------------------------------------
    pdf.section("Summary by category")
    pdf.table_text_style()
    with pdf.table(
        col_widths=(70, 25, 25, 35, 25),
        text_align=("LEFT", "RIGHT", "RIGHT", "RIGHT", "RIGHT"),
        **table_opts,
    ) as table:
        head = table.row()
        for text in ("Category", "Assets", "Quantity", "Total value", "Share of value"):
            head.cell(text)
        for c in categories:
            row = table.row()
            row.cell(c["category"])
            row.cell(str(c["assets"]))
            row.cell(str(c["quantity"]))
            row.cell(fmt_money(c["total"]))
            share = (c["total"] / sum_value * 100) if sum_value else 0.0
            row.cell(f"{share:.1f}%", style=FontFace(color=MUTED))
        total = table.row()
        total.cell("Total", style=total_style, align="LEFT")
        total.cell(str(len(rows)), style=total_style)
        total.cell(str(sum_qty), style=total_style)
        total.cell(fmt_money(sum_value), style=total_style)
        total.cell("100.0%" if sum_value else "-", style=total_style)
    pdf.ln(6)

    # --- Asset register ----------------------------------------------------------
    pdf.section("Asset register")
    pdf.table_text_style()
    with pdf.table(
        col_widths=(8, 40, 30, 30, 20, 12, 20, 20),
        text_align=("RIGHT", "LEFT", "LEFT", "LEFT", "LEFT", "RIGHT", "RIGHT", "RIGHT"),
        repeat_headings=1,
        **table_opts,
    ) as table:
        head = table.row()
        for text in ("#", "Asset", "Category", "Responsible", "Registered", "Qty", "Unit value", "Total value"):
            head.cell(text)
        for index, r in enumerate(rows, start=1):
            row = table.row()
            row.cell(str(index), style=FontFace(color=MUTED))
            row.cell(r["name"])
            row.cell(r["category"])
            row.cell(r["responsible"])
            row.cell(r["registered"])
            row.cell(str(r["quantity"]))
            row.cell(fmt_money(r["unit"]))
            row.cell(fmt_money(r["total"]))
        total = table.row()
        total.cell("Total", colspan=5, style=total_style, align="LEFT")
        total.cell(str(sum_qty), style=total_style)
        total.cell("", style=total_style)
        total.cell(fmt_money(sum_value), style=total_style)

    pdf.ln(2)
    pdf.note(
        "Assets are grouped by category and sorted by name. Unit value is the initial value recorded on the "
        "fixed asset. Total value = unit value × quantity."
    )
    return bytes(pdf.output())
