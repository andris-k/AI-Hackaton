"""What the dashboard and the analytics page show, worked out from stored data."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

from app.db import NO_LOCATION_FILTER
from app.repositories import audit_repository, auth_repository
from app.repositories import reporting_repository as reports
from app.services import audit_view_service as audit_view

RECENT_RESULTS_DAYS = 30
ANALYTICS_MAX_BARS = 8
ANALYTICS_MONTHS = 12
# Login noise would push real work out of the short activity list.
_ACTIVITY_HIDDEN_EVENTS = {"auth.login", "auth.logout", "auth.login_failed"}


def fmt_money(value: float) -> str:
    """1234567.8 -> '1 234 567.80', as in the PDF reports."""
    return f"{value:,.2f}".replace(",", " ")


def fmt_count(value: int) -> str:
    return f"{value:,}"


def _plural(count: int, one: str, many: str) -> str:
    return f"{fmt_count(count)} {one if count == 1 else many}"


def session_title(row: Mapping[str, Any]) -> str:
    return f"{row['date_from']} – {row['date_to']} · {row['location'] or 'All locations'}"


def session_progress(row: Mapping[str, Any]) -> dict[str, Any]:
    total, matched = int(row["total_assets"]), int(row["matched_assets"])
    percent = round(matched / total * 100) if total else 0
    if total:
        label = f"{matched} of {total} assets match the expected quantity"
    else:
        label = "No assets in this session yet"
    return {
        "id": str(row["id"]),
        "title": session_title(row),
        "responsible_person": str(row["responsible_person"]),
        "total": total,
        "matched": matched,
        "differences": total - matched,
        "percent": percent,
        "complete": bool(total) and matched == total,
        "label": label,
    }


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def attention_items(
    *,
    is_admin: bool,
    pending_accounts: int,
    without_location: int,
    recent_results: Sequence[Mapping[str, Any]],
    new_sessions: int,
) -> list[dict[str, str]]:
    """The "Needs attention" list, most urgent first. ``tone`` is warning,
    danger or neutral and always comes with text, never color alone."""
    items: list[dict[str, str]] = []
    if is_admin and pending_accounts:
        items.append({
            "tone": "warning",
            "kind": "Approval",
            "text": f"{_plural(pending_accounts, 'account is', 'accounts are')} waiting for approval",
            "action": "Review",
            "href": "/users",
        })
    for session in recent_results:
        if session["differences"]:
            items.append({
                "tone": "danger",
                "kind": "Results",
                "text": f"{session['title']} was completed with "
                        f"{_plural(session['differences'], 'difference', 'differences')}",
                "action": "View",
                "href": f"/inventory-sessions/id/{session['id']}",
            })
    if without_location:
        items.append({
            "tone": "warning",
            "kind": "Register",
            "text": f"{_plural(without_location, 'asset has', 'assets have')} no location",
            "action": "Show",
            "href": "/fixed-assets?" + urlencode({"location": NO_LOCATION_FILTER}),
        })
    if new_sessions:
        items.append({
            "tone": "neutral",
            "kind": "Planning",
            "text": f"{_plural(new_sessions, 'session has', 'sessions have')} not been started",
            "action": "Open",
            "href": "/inventory-sessions?status=New",
        })
    return items


def _recent_activity(limit: int = 6) -> list[dict[str, Any]]:
    rows = [
        row for row in audit_repository.list_events({}, limit=limit * 5)
        if row["event"] not in _ACTIVITY_HIDDEN_EVENTS
    ][:limit]
    labels = audit_view.session_labels(rows)
    return [audit_view.present(row, labels) for row in rows]


def build_dashboard(user_email: str) -> dict[str, Any]:
    is_admin = auth_repository.is_admin(user_email)
    summary = reports.asset_summary()
    sessions_by_status = summary["sessions_by_status"]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RECENT_RESULTS_DAYS)).isoformat()
    active = [session_progress(row) for row in reports.sessions_with_progress("Active")]
    recent_results = [
        session_progress(row)
        for row in reports.sessions_with_progress("Completed", limit=3, completed_since=cutoff)
    ]
    new_sessions = sessions_by_status.get("New", 0)

    tiles = [
        {
            "label": "Fixed assets",
            "value": fmt_count(summary["assets"]),
            "sub": f"in {_plural(summary['categories'], 'category', 'categories')}",
            "href": "/fixed-assets",
            "tone": "",
        },
        {
            "label": "Total initial value",
            "value": fmt_money(summary["total_value"]),
            "sub": "initial value × quantity",
            "href": "/analytics",
            "tone": "",
        },
        {
            "label": "Active sessions",
            "value": fmt_count(len(active)),
            "sub": f"{_plural(new_sessions, 'more', 'more')} not started" if new_sessions else "none waiting to start",
            "href": "/inventory-sessions?status=Active",
            "tone": "accent" if active else "",
        },
        {
            "label": "Without location",
            "value": fmt_count(summary["without_location"]),
            "sub": f"{_plural(summary['locations'], 'location', 'locations')} set up",
            "href": "/fixed-assets?" + urlencode({"location": NO_LOCATION_FILTER}),
            "tone": "warning" if summary["without_location"] else "",
        },
    ]
    return {
        "is_admin": is_admin,
        "tiles": tiles,
        "active_sessions": active,
        "attention": attention_items(
            is_admin=is_admin,
            pending_accounts=auth_repository.pending_count() if is_admin else 0,
            without_location=summary["without_location"],
            recent_results=recent_results,
            new_sessions=new_sessions,
        ),
        "activity": _recent_activity() if is_admin else [],
        "has_assets": summary["assets"] > 0,
    }


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

MEASURES = {"value": "Initial value", "count": "Number of assets"}


def bar_rows(
    rows: Sequence[Mapping[str, Any]],
    measure: str,
    *,
    empty_label: str = "",
    max_bars: int = ANALYTICS_MAX_BARS,
) -> list[dict[str, Any]]:
    """Rows for a horizontal bar list: label, shown value and bar width in %.

    Sorted by the chosen measure. Past ``max_bars`` the rest folds into one
    "Other" bar, so a long tail never turns into a long, unreadable list.
    """
    key = "value" if measure == "value" else "assets"
    items = [
        {"label": row["label"] or empty_label, "value": float(row["value"]), "assets": int(row["assets"])}
        for row in rows
    ]
    items.sort(key=lambda item: item[key], reverse=True)
    if len(items) > max_bars:
        rest = items[max_bars - 1:]
        items = items[: max_bars - 1] + [{
            "label": f"Other ({len(rest)})",
            "value": sum(item["value"] for item in rest),
            "assets": sum(item["assets"] for item in rest),
        }]
    peak = max((item[key] for item in items), default=0)
    return [
        {
            "label": item["label"],
            "display": fmt_money(item["value"]) if measure == "value" else fmt_count(item["assets"]),
            "detail": f"{_plural(item['assets'], 'asset', 'assets')} · {fmt_money(item['value'])}",
            "percent": round(item[key] / peak * 100, 1) if peak else 0,
        }
        for item in items
    ]


def month_columns(counts: Mapping[str, int], today: date, months: int = ANALYTICS_MONTHS) -> list[dict[str, Any]]:
    """The last ``months`` calendar months, oldest first, including months with
    no registrations. Only the peak month carries a visible label."""
    year, month = today.year, today.month
    keys: list[tuple[int, int]] = []
    for _ in range(months):
        keys.append((year, month))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    keys.reverse()
    values = [counts.get(f"{y:04d}-{m:02d}", 0) for y, m in keys]
    peak = max(values, default=0)
    peak_index = values.index(peak) if peak else -1
    return [
        {
            "key": f"{y:04d}-{m:02d}",
            "label": date(y, m, 1).strftime("%b"),
            "full_label": date(y, m, 1).strftime("%B %Y"),
            "count": value,
            "percent": round(value / peak * 100, 1) if peak else 0,
            "is_peak": index == peak_index,
        }
        for index, ((y, m), value) in enumerate(zip(keys, values))
    ]


def first_month(today: date, months: int = ANALYTICS_MONTHS) -> str:
    return month_columns({}, today, months)[0]["key"]


def build_analytics(measure: str, today: date | None = None) -> dict[str, Any]:
    measure = measure if measure in MEASURES else "value"
    today = today or date.today()
    summary = reports.asset_summary()
    completed = [session_progress(row) for row in reports.sessions_with_progress("Completed", limit=6)]
    counted = [session for session in completed if session["total"]]
    last = counted[0] if counted else None
    months = month_columns(reports.registrations_by_month(first_month(today)), today)
    return {
        "measure": measure,
        "measure_label": MEASURES[measure],
        "measures": [
            {"key": key, "label": label, "href": f"/analytics?measure={key}", "selected": key == measure}
            for key, label in MEASURES.items()
        ],
        "tiles": [
            {"label": "Fixed assets", "value": fmt_count(summary["assets"])},
            {"label": "Total initial value", "value": fmt_money(summary["total_value"])},
            {
                "label": "Average value per asset",
                "value": fmt_money(summary["total_value"] / summary["assets"]) if summary["assets"] else "—",
            },
            {
                "label": "Matched in the last count",
                "value": f"{last['percent']}%" if last else "—",
                "sub": last["title"] if last else "No completed sessions yet",
            },
        ],
        "by_category": bar_rows(reports.totals_by("category"), measure),
        "by_location": bar_rows(reports.totals_by("location"), measure, empty_label="No location"),
        "months": months,
        "months_total": sum(month["count"] for month in months),
        "session_results": [
            {
                "label": session["title"],
                "display": f"{session['percent']}%",
                "detail": session["label"],
                "percent": session["percent"],
                "href": f"/inventory-sessions/id/{session['id']}",
            }
            for session in counted
        ],
        "has_assets": summary["assets"] > 0,
    }
