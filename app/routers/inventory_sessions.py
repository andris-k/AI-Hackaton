from __future__ import annotations

import csv
import io
import json

from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from app.repositories import fixed_assets_repository as assets_repo
from app.repositories import inventory_sessions_repository as repo
from app.repositories import locations_repository as locations_repo
from app.logging_config import audit
from app.services import auth_service
from app.services import counting_workspace_service as workspace
from app.services import session_results_service as results_svc
from app.services import fixed_assets_service as assets_service
from app.services import inventory_sessions_service as svc
from app.services import inventory_report_service as report_svc
from app.views.pages import (
    render_add_inventory_session_page,
    render_edit_inventory_session_page,
    render_count_row,
    render_inventory_session_count_page,
    render_inventory_session_finish_page,
    render_inventory_session_results_page,
    render_inventory_session_details_page,
    render_inventory_sessions_page,
    render_login_page,
    session_locations,
)

router = APIRouter()
_STATUS_EVENTS = {
    "Active": "started",
    "Completed": "completed",
    "Cancelled": "cancelled",
}


def _asset_options_for_session(session_id: str, active_location_id: str | None) -> list[dict[str, object]]:
    """Assets for the pickers on the session edit page: every asset in the
    register that is not deleted, plus deleted ones already in this session (so
    saving keeps them, marked as deleted). ``at_location`` marks the assets
    registered at the active location, for "Add all assets at ...".
    Assets in the session show the expected quantity saved for it; the others
    their current quantity, which is what would be saved for them.
    """
    options: dict[str, dict[str, object]] = {
        str(asset["id"]): {
            "id": str(asset["id"]),
            "name": str(asset["name"]),
            "category": str(asset["category"]),
            "expected_quantity": int(asset["quantity"]),
            "initial_value": float(asset["initial_value"]),
            "selectable": True,
            "at_location": bool(active_location_id) and asset["location_id"] == active_location_id,
            "note": "",
        }
        for asset in assets_repo.list_assets()
    }
    for asset in repo.list_linked_assets(session_id):
        asset_id = str(asset["id"])
        if asset_id in options:
            options[asset_id]["expected_quantity"] = int(asset["expected_quantity"])
            continue
        options[asset_id] = {
            "id": asset_id,
            "name": str(asset["name"]),
            "category": str(asset["category"]),
            "expected_quantity": int(asset["expected_quantity"]),
            "initial_value": float(asset["initial_value"]),
            "selectable": False,
            "at_location": False,
            "note": "deleted",
        }
    return list(options.values())


def _edit_rows(session_id: str, form_rows: list[tuple[str, str]] | None = None) -> list[dict[str, str]]:
    """Rows for the edit page: the count at the active location, which the page
    edits, and what is counted at other locations (shown, not edited).
    ``form_rows`` re-shows what was posted, after a validation error."""
    counts = {str(row["fixed_asset_id"]): row for row in repo.counts_at_active_location(session_id)}

    def elsewhere(asset_id: str) -> int:
        row = counts.get(asset_id)
        return int(row["total"]) - int(row["here"]) if row else 0

    if form_rows is None:
        form_rows = [(asset_id, str(int(row["here"]))) for asset_id, row in counts.items()]
    return [
        {"fixed_asset_id": asset_id, "quantity": quantity, "elsewhere": str(elsewhere(asset_id))}
        for asset_id, quantity in form_rows
    ]


def _location_choices(current_id: object = None, current_name: object = None) -> list[dict[str, str]]:
    """Locations for a dropdown, plus the session's own one if it was deleted since."""
    choices = [{"id": str(row["id"]), "name": str(row["name"])} for row in locations_repo.list_all()]
    if current_id and all(choice["id"] != str(current_id) for choice in choices):
        choices.append({"id": str(current_id), "name": f"{current_name or 'Unknown'} (deleted)"})
    return choices


def _render_edit_page(
    *,
    user_email: str,
    inv_session: object,
    linked_asset_rows: list[dict[str, str]],
    is_admin_user: bool,
    error: str | None = None,
    prefill: dict[str, str] | None = None,
) -> HTMLResponse:
    current_status = str(inv_session["status"])
    statuses = list(svc.STATUSES) if is_admin_user else svc.available_target_statuses(current_status)
    return render_edit_inventory_session_page(
        inv_session=inv_session,
        current_email=user_email,
        statuses=statuses,
        fixed_assets=_asset_options_for_session(str(inv_session["id"]), inv_session["location_id"]),
        locations=_location_choices(inv_session["location_id"], inv_session["location"]),
        linked_asset_rows=linked_asset_rows,
        is_read_only=svc.is_terminal_status(current_status) and not is_admin_user,
        is_admin_user=is_admin_user,
        error=error,
        prefill=prefill,
    )


def _build_filters(
    *,
    status: str,
    responsible_person: str,
    date_from: str,
    date_to: str,
    location_id: str = "",
) -> dict[str, str]:
    return {
        "status": status,
        "responsible_person": responsible_person,
        "date_from": date_from,
        "date_to": date_to,
        "location_id": location_id,
    }


def _calculate_summary(sessions: list[object]) -> dict[str, object]:
    status_counts = {key: 0 for key in svc.STATUSES}
    total_linked_assets = 0
    total_quantity = 0

    for row in sessions:
        status = str(row["status"])
        status_counts[status] = status_counts.get(status, 0) + 1
        total_linked_assets += int(row["linked_assets_count"])
        total_quantity += int(row["linked_assets_quantity_total"])

    return {
        "total_sessions": len(sessions),
        "status_counts": status_counts,
        "total_linked_assets": total_linked_assets,
        "total_quantity": total_quantity,
    }


def _render_details_with_message(
    *,
    user_email: str,
    session_id: str,
    message: str,
    message_kind: str = "error",
) -> HTMLResponse:
    inv_session = repo.get_session_by_id(session_id)
    if inv_session is None:
        return render_login_page("Inventory session not found.")
    linked_assets = repo.list_linked_assets(session_id)
    return render_inventory_session_details_page(
        inv_session=inv_session,
        current_email=user_email,
        linked_assets=linked_assets,
        message=message,
        message_kind=message_kind,
    )


@router.get("/inventory-sessions", response_class=HTMLResponse)
def inventory_sessions_page(
    session_token: str | None = Cookie(default=None),
    status: str = Query(default=""),
    responsible_person: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    location_id: str = Query(default=""),
) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to access inventory sessions.")

    sessions = repo.list_sessions(
        status=status or None,
        responsible_person=responsible_person or None,
        date_from=date_from or None,
        date_to=date_to or None,
        location_id=location_id or None,
    )
    filters = _build_filters(
        status=status,
        responsible_person=responsible_person,
        date_from=date_from,
        date_to=date_to,
        location_id=location_id,
    )
    return render_inventory_sessions_page(
        sessions=sessions,
        current_email=user["email"],
        statuses=list(svc.STATUSES),
        filters=filters,
        summary=_calculate_summary(sessions),
        locations=_location_choices(),
    )


@router.get("/inventory-sessions/export.csv")
def export_inventory_sessions_csv(
    session_token: str | None = Cookie(default=None),
    status: str = Query(default=""),
    responsible_person: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    location_id: str = Query(default=""),
) -> Response:
    user = auth_service.current_user(session_token)
    if user is None:
        return Response(content="Please log in to export inventory sessions.", status_code=401)

    sessions = repo.list_sessions(
        status=status or None,
        responsible_person=responsible_person or None,
        date_from=date_from or None,
        date_to=date_to or None,
        location_id=location_id or None,
    )
    summary = _calculate_summary(sessions)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Filters", "Value"])
    writer.writerow(["status", status or "ALL"])
    writer.writerow(["responsible_person", responsible_person or "ALL"])
    writer.writerow(["date_from", date_from or "ALL"])
    writer.writerow(["date_to", date_to or "ALL"])
    writer.writerow(["location_id", location_id or "ALL"])
    writer.writerow([])
    writer.writerow(["Summary", "Value"])
    writer.writerow(["total_sessions", summary["total_sessions"]])
    writer.writerow(["total_linked_assets", summary["total_linked_assets"]])
    writer.writerow(["total_quantity", summary["total_quantity"]])
    for status_name in svc.STATUSES:
        writer.writerow([
            f"status_{status_name.lower()}",
            int(summary["status_counts"].get(status_name, 0)),
        ])
    writer.writerow([])
    writer.writerow(
        [
            "id",
            "date_from",
            "date_to",
            "status",
            "responsible_person",
            "location",
            "created_at",
            "started_at",
            "completed_at",
            "cancelled_at",
            "notes",
            "completion_reason",
            "cancellation_reason",
            "linked_assets_count",
            "linked_assets_quantity_total",
        ]
    )
    for row in sessions:
        writer.writerow(
            [
                row["id"],
                row["date_from"],
                row["date_to"],
                row["status"],
                row["responsible_person"],
                row["location"] or "",
                row["created_at"],
                row["started_at"],
                row["completed_at"],
                row["cancelled_at"],
                row["notes"],
                row["completion_reason"],
                row["cancellation_reason"],
                row["linked_assets_count"],
                row["linked_assets_quantity_total"],
            ]
        )

    csv_text = output.getvalue()
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=inventory-sessions-report.csv",
        },
    )


@router.get("/inventory-sessions/export.json")
def export_inventory_sessions_json(
    session_token: str | None = Cookie(default=None),
    status: str = Query(default=""),
    responsible_person: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    location_id: str = Query(default=""),
) -> Response:
    user = auth_service.current_user(session_token)
    if user is None:
        return Response(content="Please log in to export inventory sessions.", status_code=401)

    sessions = repo.list_sessions(
        status=status or None,
        responsible_person=responsible_person or None,
        date_from=date_from or None,
        date_to=date_to or None,
        location_id=location_id or None,
    )
    summary = _calculate_summary(sessions)

    payload = {
        "filters": _build_filters(
            status=status,
            responsible_person=responsible_person,
            date_from=date_from,
            date_to=date_to,
            location_id=location_id,
        ),
        "summary": summary,
        "sessions": [
            {
                "id": str(row["id"]),
                "date_from": str(row["date_from"]),
                "date_to": str(row["date_to"]),
                "status": str(row["status"]),
                "responsible_person": str(row["responsible_person"]),
                "location_id": str(row["location_id"] or ""),
                "location": str(row["location"] or ""),
                "created_at": str(row["created_at"] or ""),
                "started_at": str(row["started_at"] or ""),
                "completed_at": str(row["completed_at"] or ""),
                "cancelled_at": str(row["cancelled_at"] or ""),
                "notes": str(row["notes"] or ""),
                "completion_reason": str(row["completion_reason"] or ""),
                "cancellation_reason": str(row["cancellation_reason"] or ""),
                "linked_assets_count": int(row["linked_assets_count"]),
                "linked_assets_quantity_total": int(row["linked_assets_quantity_total"]),
            }
            for row in sessions
        ],
    }
    return Response(
        content=json.dumps(payload, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": "attachment; filename=inventory-sessions-report.json",
        },
    )


@router.get("/inventory-sessions/add", response_class=HTMLResponse)
def add_inventory_session_page(
    session_token: str | None = Cookie(default=None),
) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to add an inventory session.")
    fixed_assets = assets_repo.list_assets()
    return render_add_inventory_session_page(
        current_email=user["email"],
        fixed_assets=fixed_assets,
        linked_asset_rows=[],
        locations=_location_choices(),
    )


@router.post("/inventory-sessions/add", response_class=HTMLResponse)
def add_inventory_session(
    session_token: str | None = Cookie(default=None),
    date_from: str = Form(...),
    date_to: str = Form(...),
    responsible_person: str = Form(...),
    notes: str = Form(default=""),
    location_id: str = Form(default=""),
    fixed_asset_ids: list[str] = Form(default=[]),
    fixed_asset_quantities: list[str] = Form(default=[]),
) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to add an inventory session.")

    error = svc.validate_create_form(
        date_from=date_from,
        date_to=date_to,
        responsible_person=responsible_person,
    )
    linked_assets, linked_assets_error = svc.parse_linked_assets(
        fixed_asset_ids=fixed_asset_ids,
        fixed_asset_quantities=fixed_asset_quantities,
    )
    session_location_id = assets_service.optional_id(location_id)
    if session_location_id and locations_repo.get_by_id(session_location_id) is None:
        error = error or "Selected location does not exist."
    combined_error = error or linked_assets_error
    if combined_error:
        fixed_assets = assets_repo.list_assets()
        linked_asset_rows = [
            {"fixed_asset_id": fixed_asset_ids[index], "quantity": fixed_asset_quantities[index]}
            for index in range(min(len(fixed_asset_ids), len(fixed_asset_quantities)))
        ]
        if not linked_asset_rows:
            linked_asset_rows = []
        return render_add_inventory_session_page(
            current_email=user["email"],
            error=combined_error,
            prefill={
                "date_from": date_from,
                "date_to": date_to,
                "responsible_person": responsible_person,
                "notes": notes,
                "location_id": location_id,
            },
            fixed_assets=fixed_assets,
            linked_asset_rows=linked_asset_rows,
            locations=_location_choices(),
        )

    session = repo.create_session(
        date_from=date_from,
        date_to=date_to,
        responsible_person=responsible_person,
        linked_assets=linked_assets,
        created_by_user_id=int(user["id"]),
        notes=notes,
        location_id=session_location_id,
    )
    audit(
        "inventory_session.created",
        session_id=session["id"],
        date_from=date_from,
        date_to=date_to,
        responsible_person=responsible_person,
        location=locations_repo.get_by_id(session_location_id)["name"] if session_location_id else None,
        linked_assets=len(linked_assets),
    )
    return RedirectResponse(
        url=f"/inventory-sessions/id/{session['id']}",
        status_code=303,
    )


@router.get("/inventory-sessions/id/{session_id}", response_class=HTMLResponse)
def inventory_session_details_page(
    session_id: str,
    session_token: str | None = Cookie(default=None),
) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to view inventory sessions.")
    inv_session = repo.get_session_by_id(session_id)
    if inv_session is None:
        return render_login_page("Inventory session not found.")
    if str(inv_session["status"]) == "Active":
        return RedirectResponse(url=f"/inventory-sessions/id/{session_id}/count", status_code=303)
    if svc.is_terminal_status(str(inv_session["status"])):
        return render_inventory_session_results_page(str(user["email"]), inv_session)
    linked_assets = repo.list_linked_assets(session_id)
    return render_inventory_session_details_page(
        inv_session=inv_session,
        current_email=user["email"],
        linked_assets=linked_assets,
    )


@router.get("/inventory-sessions/id/{session_id}/report.pdf")
def inventory_session_pdf_report(
    session_id: str,
    session_token: str | None = Cookie(default=None),
    only: str = Query(default=""),
) -> Response:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to download inventory reports.")
    inv_session = repo.get_session_by_id(session_id)
    if inv_session is None:
        return Response("Inventory session not found.", status_code=404, media_type="text/plain")
    if str(inv_session["status"]) != "Completed":
        # Reports are only for completed sessions; send the user back to the session page.
        return RedirectResponse(url=f"/inventory-sessions/id/{session_id}", status_code=303)

    only_differences = only == "differences"
    audit("inventory_session.report_downloaded", session_id=session_id,
          **({"differences_only": True} if only_differences else {}))
    locations_context = session_locations(session_id)
    pdf_bytes = report_svc.build_session_report(
        inv_session,
        repo.list_linked_assets(session_id),
        counted_at=locations_context["counted_at"],
        location_history=locations_context["location_history"],
        only_differences=only_differences,
    )
    filename = report_svc.report_filename(inv_session)
    if only_differences:
        filename = filename.replace(".pdf", "-differences.pdf")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/inventory-sessions/id/{session_id}/results.csv")
def inventory_session_results_csv(
    session_id: str,
    session_token: str | None = Cookie(default=None),
) -> Response:
    """One row per asset with its status, counts, difference and the value of it."""
    user = auth_service.current_user(session_token)
    if user is None:
        return Response(content="Please log in to export inventory results.", status_code=401)
    inv_session = repo.get_session_by_id(session_id)
    if inv_session is None:
        return Response("Inventory session not found.", status_code=404, media_type="text/plain")
    audit("inventory_session.results_exported", session_id=session_id)
    return Response(
        # The byte order mark lets Excel read the file as UTF-8.
        content=results_svc.results_csv(inv_session).encode("utf-8-sig"),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{results_svc.results_filename(inv_session)}"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/inventory-sessions/id/{session_id}/reopen", response_class=HTMLResponse)
def reopen_inventory_session(
    session_id: str,
    session_token: str | None = Cookie(default=None),
    reason: str = Form(default=""),
) -> Response:
    """Administrators can make a Completed or Cancelled session Active again, with a reason."""
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to reopen inventory sessions.")
    inv_session = repo.get_session_by_id(session_id)
    if inv_session is None:
        return render_login_page("Inventory session not found.")
    status = str(inv_session["status"])
    error = None
    if not svc.is_admin_email(str(user["email"])):
        error = "Only administrators can reopen sessions."
    elif not svc.is_terminal_status(status):
        error = "Only completed or cancelled sessions can be reopened."
    elif not reason.strip():
        error = "Give a reason for reopening the session."
    if error:
        if svc.is_terminal_status(status):
            return render_inventory_session_results_page(
                str(user["email"]), inv_session, message=error, message_kind="error"
            )
        return _render_details_with_message(user_email=str(user["email"]), session_id=session_id, message=error)

    repo.update_session(
        session_id=session_id,
        date_from=str(inv_session["date_from"]),
        date_to=str(inv_session["date_to"]),
        status="Active",
        responsible_person=str(inv_session["responsible_person"]),
        notes=str(inv_session["notes"] or ""),
        completion_reason=str(inv_session["completion_reason"] or ""),
        cancellation_reason=str(inv_session["cancellation_reason"] or ""),
        actor_user_id=int(user["id"]),
    )
    audit(
        "inventory_session.reopened",
        session_id=session_id,
        from_status=status,
        to_status="Active",
        admin_override=True,
        reason=reason.strip(),
    )
    return RedirectResponse(url=f"/inventory-sessions/id/{session_id}/count", status_code=303)


_COUNT_RESULTS = {
    "counted", "added", "not_active", "asset_not_found", "asset_deleted", "not_linked", "ambiguous",
    "not_counted_here",
}


def _resolve_asset_code(code: str) -> tuple[str | None, str | None]:
    """(asset id, None), or (None, error result) for a scanned or typed code."""
    asset_id, prefix = svc.parse_asset_code(code)
    if asset_id:
        return asset_id, None
    if prefix:
        matches = assets_repo.find_ids_by_prefix(prefix)
        if len(matches) == 1:
            return matches[0], None
        return None, "ambiguous" if matches else "asset_not_found"
    return None, "asset_not_found"


def _count_outcome(session_id: str, asset_id: str, result: str) -> dict[str, object]:
    """Rebuild a count result after a redirect, from the current data."""
    outcome: dict[str, object] = {"result": result if result in _COUNT_RESULTS else "asset_not_found"}
    inv_session = repo.get_session_by_id(session_id)
    here = {str(row["fixed_asset_id"]): int(row["here"]) for row in repo.counts_at_active_location(session_id)}
    for asset in repo.list_linked_assets(session_id):
        if str(asset["id"]) == asset_id:
            outcome.update(
                name=asset["name"],
                quantity=int(asset["quantity"]),
                here_quantity=here.get(asset_id, 0),
                expected_quantity=int(asset["expected_quantity"]),
                location=inv_session["location"] if inv_session else None,
                other_location=bool(inv_session and inv_session["location_id"])
                and asset["location_id"] != inv_session["location_id"],
            )
            return outcome
    asset = assets_repo.get_asset_by_id(asset_id) if asset_id else None
    if asset is not None:
        outcome["name"] = asset["name"]
    return outcome


@router.get("/inventory-sessions/id/{session_id}/count", response_class=HTMLResponse)
def count_inventory_session_page(
    session_id: str,
    session_token: str | None = Cookie(default=None),
    asset: str = Query(default=""),
    result: str = Query(default=""),
    tab: str = Query(default="all"),
    notice: str = Query(default=""),
) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to count inventory sessions.")
    inv_session = repo.get_session_by_id(session_id)
    if inv_session is None:
        return render_login_page("Inventory session not found.")
    if str(inv_session["status"]) != "Active":
        return _render_details_with_message(
            user_email=str(user["email"]),
            session_id=session_id,
            message="Counting is only possible while the session is Active.",
        )

    message, message_kind = (None, "info")
    if result:
        message, message_kind = svc.count_message(_count_outcome(session_id, asset, result))
    elif notice in _NOTICES:
        message, message_kind = _NOTICES[notice], "success"
    return render_inventory_session_count_page(
        current_email=str(user["email"]),
        inv_session=inv_session,
        locations=_location_choices(inv_session["location_id"], inv_session["location"]),
        selected_tab=tab,
        message=message,
        message_kind=message_kind,
    )


_NOTICES = {"details": "Session details saved.", "removed": "Asset removed from the session."}


def _workspace_payload(session_id: str, asset_id: str | None) -> dict[str, object]:
    """The updated row (as HTML, drawn by the same template as the page) and summary."""
    inv_session = repo.get_session_by_id(session_id)
    if inv_session is None:
        return {}
    rows = workspace.build_rows(inv_session)
    row = next((r for r in rows if r["id"] == asset_id), None)
    return {
        "row_html": render_count_row(row, session_id) if row else None,
        "summary": workspace.summary(rows),
    }


@router.post("/inventory-sessions/id/{session_id}/count")
def count_inventory_session(
    request: Request,
    session_id: str,
    session_token: str | None = Cookie(default=None),
    code: str = Form(default=""),
    delta: int = Form(default=1),
    quantity: str = Form(default=""),
    not_found: str = Form(default=""),
    back: str = Form(default="count"),
) -> Response:
    """Change an asset's count at the active location: add ``delta`` (default 1),
    or set it to ``quantity``; ``not_found`` records a 0 on purpose. Used by the
    counting workspace (form posts, or fetch asking for JSON, which gets the
    updated row back), by the review page (``back=finish``) and by the Count
    button on an asset's page (``back=asset``)."""
    wants_json = "application/json" in request.headers.get("accept", "")
    user = auth_service.current_user(session_token)
    if user is None:
        if wants_json:
            return JSONResponse({"result": "login_required", "message": "Please log in again."}, status_code=401)
        return render_login_page("Please log in to count inventory sessions.")

    delta = max(-1000, min(delta, 1000))
    set_to: int | None = None
    if quantity.strip():
        try:
            set_to = max(0, min(int(quantity), 1_000_000))
        except ValueError:
            set_to = None
    marked_not_found = not_found in {"1", "true", "on", "yes"}
    if marked_not_found:
        set_to = 0
    asset_id, error_result = _resolve_asset_code(code)
    outcome: dict[str, object]
    if asset_id is None:
        outcome = {"result": error_result}
    else:
        if set_to is not None:
            outcome = repo.set_count(session_id, asset_id, set_to, not_found=marked_not_found)
        else:
            outcome = repo.adjust_count(session_id, asset_id, delta)
        if outcome.get("result") in {"counted", "added"}:
            change = {"set_to": set_to} if set_to is not None else {"delta": delta}
            audit(
                "inventory_session.count_changed",
                session_id=session_id,
                asset_id=asset_id,
                name=outcome.get("name"),
                **change,
                **({"not_found": True} if marked_not_found else {}),
                location=outcome.get("location"),
                quantity=outcome.get("quantity"),
                added_to_session=outcome.get("result") == "added",
            )

    message, kind = svc.count_message(outcome)
    if marked_not_found and outcome.get("result") == "counted":
        where = f" at {outcome['location']}" if outcome.get("location") else ""
        message = f"{outcome.get('name')}: marked not found{where}."
    if wants_json:
        payload = {
            key: outcome.get(key)
            for key in (
                "result", "asset_id", "name", "quantity", "here_quantity", "expected_quantity",
                "other_location", "location",
            )
        }
        if outcome.get("result") == "added" and asset_id:
            asset = assets_repo.get_asset_by_id(asset_id)
            payload["category"] = asset["category"] if asset else ""
            payload["asset_location"] = (asset["location"] or "") if asset else ""
        if asset_id and outcome.get("result") in {"counted", "added"}:
            payload.update(_workspace_payload(session_id, asset_id))
        return JSONResponse({**payload, "message": message, "kind": kind})

    result = str(outcome.get("result") or "asset_not_found")
    if back == "finish":
        return RedirectResponse(url=f"/inventory-sessions/id/{session_id}/finish", status_code=303)
    if back == "asset" and asset_id:
        query = urlencode({"count_session": session_id, "count_result": result})
        return RedirectResponse(url=f"/fixed-assets/id/{asset_id}?{query}", status_code=303)
    query = urlencode({"asset": asset_id or "", "result": result})
    return RedirectResponse(url=f"/inventory-sessions/id/{session_id}/count?{query}", status_code=303)


@router.post("/inventory-sessions/id/{session_id}/remove")
def remove_asset_from_session(
    request: Request,
    session_id: str,
    session_token: str | None = Cookie(default=None),
    asset_id: str = Form(default=""),
) -> Response:
    """Take an asset out of the session, with all its counts."""
    wants_json = "application/json" in request.headers.get("accept", "")
    user = auth_service.current_user(session_token)
    if user is None:
        if wants_json:
            return JSONResponse({"result": "login_required", "message": "Please log in again."}, status_code=401)
        return render_login_page("Please log in to count inventory sessions.")
    asset = assets_repo.get_asset_by_id(asset_id) if asset_id else None
    outcome = repo.remove_asset(session_id, asset_id) if asset else {"result": "not_linked"}
    result = str(outcome["result"])
    if result == "removed":
        audit("inventory_session.asset_removed", session_id=session_id, asset_id=asset_id, name=asset["name"],
              counts=outcome["counts"])
        message, kind = f"{asset['name']} was removed from the session.", "success"
    elif result == "closed":
        message, kind = "Assets can only be removed while the session is New or Active.", "error"
    else:
        message, kind = "That asset is not in this session.", "error"
    if wants_json:
        payload = _workspace_payload(session_id, None)
        return JSONResponse({
            "result": result, "removed": result == "removed", "asset_id": asset_id,
            # What Undo sends back to /restore.
            "undo": {"asset_id": asset_id, "counts": outcome["counts"]} if result == "removed" else None,
            "summary": payload.get("summary"), "message": message, "kind": kind,
        })
    notice = "&notice=removed" if result == "removed" else ""
    return RedirectResponse(url=f"/inventory-sessions/id/{session_id}/count?tab=all{notice}", status_code=303)


@router.post("/inventory-sessions/id/{session_id}/restore")
def restore_asset_to_session(
    session_id: str,
    session_token: str | None = Cookie(default=None),
    asset_id: str = Form(default=""),
    counts: str = Form(default="[]"),
) -> Response:
    """Undo a removal: put the asset back with the counts it had ([location id, quantity] pairs, as JSON)."""
    user = auth_service.current_user(session_token)
    if user is None:
        return JSONResponse({"result": "login_required", "message": "Please log in again."}, status_code=401)
    try:
        pairs = [
            [location_id if isinstance(location_id, str) else None, int(quantity)]
            for location_id, quantity in json.loads(counts)
        ][:100]
    except (ValueError, TypeError):
        pairs = []
    result = repo.restore_asset(session_id, asset_id, pairs)
    asset = assets_repo.get_asset_by_id(asset_id) if asset_id else None
    if result == "restored" and asset is not None:
        audit("inventory_session.asset_restored", session_id=session_id, asset_id=asset_id, name=asset["name"])
        message, kind = f"{asset['name']} is back in the session with its counts.", "success"
    elif result == "already_in_session":
        message, kind = "That asset is already in the session again.", "info"
    else:
        message, kind = "The asset could not be put back.", "error"
    return JSONResponse({
        "result": result, "asset_id": asset_id, "message": message, "kind": kind,
        **(_workspace_payload(session_id, asset_id) if result == "restored" else {}),
    })


@router.get("/inventory-sessions/id/{session_id}/search")
def search_assets(
    session_id: str,
    session_token: str | None = Cookie(default=None),
    q: str = Query(default=""),
) -> Response:
    """Assets in the register for the workspace's search box."""
    user = auth_service.current_user(session_token)
    if user is None:
        return JSONResponse({"results": []}, status_code=401)
    return JSONResponse({
        "results": [
            {
                "id": str(row["id"]),
                "name": str(row["name"]),
                "meta": " · ".join(
                    part for part in (
                        str(row["category"] or ""),
                        f"registered at {row['location']}" if row["location"] else "no location",
                        str(row["id"])[:8],
                        "in this session" if row["in_session"] else "",
                    ) if part
                ),
                "in_session": bool(row["in_session"]),
            }
            for row in repo.search_assets(session_id, q[:100])
        ]
    })


@router.post("/inventory-sessions/id/{session_id}/details", response_class=HTMLResponse)
def save_session_details(
    session_id: str,
    session_token: str | None = Cookie(default=None),
    date_from: str = Form(...),
    date_to: str = Form(...),
    responsible_person: str = Form(...),
    notes: str = Form(default=""),
) -> Response:
    """Dates, responsible person and notes, from the workspace's Session details panel."""
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to edit inventory sessions.")
    inv_session = repo.get_session_by_id(session_id)
    if inv_session is None:
        return render_login_page("Inventory session not found.")
    status = str(inv_session["status"])
    if svc.is_terminal_status(status):
        return _render_details_with_message(
            user_email=str(user["email"]), session_id=session_id, message="Terminal sessions are read-only."
        )
    error = svc.validate_session_form(
        date_from=date_from, date_to=date_to, status=status, responsible_person=responsible_person
    )
    if error:
        return render_inventory_session_count_page(
            current_email=str(user["email"]),
            inv_session=inv_session,
            locations=_location_choices(inv_session["location_id"], inv_session["location"]),
            details_open=True,
            message=error,
            message_kind="error",
        )
    repo.update_session(
        session_id=session_id,
        date_from=date_from,
        date_to=date_to,
        status=status,
        responsible_person=responsible_person,
        notes=notes,
        completion_reason=str(inv_session["completion_reason"] or ""),
        cancellation_reason=str(inv_session["cancellation_reason"] or ""),
        actor_user_id=int(user["id"]),
    )
    audit(
        "inventory_session.updated",
        session_id=session_id,
        changes={
            key: [inv_session[key], value]
            for key, value in (("date_from", date_from), ("date_to", date_to),
                               ("responsible_person", responsible_person.strip()), ("notes", notes.strip()))
            if (inv_session[key] or "") != value
        },
    )
    target = "count" if status == "Active" else "edit"
    suffix = "?notice=details" if target == "count" else ""
    return RedirectResponse(url=f"/inventory-sessions/id/{session_id}/{target}{suffix}", status_code=303)


@router.get("/inventory-sessions/id/{session_id}/finish", response_class=HTMLResponse)
def finish_counting_page(
    session_id: str,
    session_token: str | None = Cookie(default=None),
) -> HTMLResponse:
    """Review before completing: not counted yet, differences, locations used."""
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to complete inventory sessions.")
    inv_session = repo.get_session_by_id(session_id)
    if inv_session is None:
        return render_login_page("Inventory session not found.")
    if str(inv_session["status"]) != "Active":
        return RedirectResponse(url=f"/inventory-sessions/id/{session_id}", status_code=303)
    return render_inventory_session_finish_page(str(user["email"]), inv_session)


@router.post("/inventory-sessions/id/{session_id}/active-location", response_class=HTMLResponse)
def set_active_location(
    session_id: str,
    session_token: str | None = Cookie(default=None),
    location_id: str = Form(default=""),
    back: str = Form(default="edit"),
) -> Response:
    """Make another location active. Counts from then on are recorded there,
    and the change is added to the session's location history."""
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to edit inventory sessions.")
    inv_session = repo.get_session_by_id(session_id)
    if inv_session is None:
        return render_login_page("Inventory session not found.")

    new_location_id = assets_service.optional_id(location_id)
    try:
        result = repo.set_active_location(session_id, new_location_id, int(user["id"]))
    except ValueError:
        result = "location_not_found"
    if result == "changed":
        new_location = locations_repo.get_by_id(new_location_id) if new_location_id else None
        audit(
            "inventory_session.location_changed",
            session_id=session_id,
            changes={"location": [inv_session["location"], new_location["name"] if new_location else None]},
        )
    elif result != "unchanged":
        message = {
            "closed": "The active location can only be changed while the session is New or Active.",
            "location_not_found": "Selected location does not exist.",
        }.get(result, "Inventory session not found.")
        return _render_details_with_message(user_email=str(user["email"]), session_id=session_id, message=message)

    target = "count" if back == "count" else "edit"
    return RedirectResponse(url=f"/inventory-sessions/id/{session_id}/{target}", status_code=303)


@router.get("/inventory-sessions/id/{session_id}/edit", response_class=HTMLResponse)
def edit_inventory_session_page(
    session_id: str,
    session_token: str | None = Cookie(default=None),
) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to edit inventory sessions.")
    inv_session = repo.get_session_by_id(session_id)
    if inv_session is None:
        return render_login_page("Inventory session not found.")
    if str(inv_session["status"]) == "Active":
        # Counting happens in the workspace; this page plans New sessions and
        # lets administrators reopen closed ones.
        return RedirectResponse(url=f"/inventory-sessions/id/{session_id}/count", status_code=303)
    is_admin_user = svc.is_admin_email(str(user["email"]))
    return _render_edit_page(
        user_email=str(user["email"]),
        inv_session=inv_session,
        linked_asset_rows=_edit_rows(session_id),
        is_admin_user=is_admin_user,
    )


@router.post("/inventory-sessions/id/{session_id}/edit", response_class=HTMLResponse)
def edit_inventory_session(
    session_id: str,
    session_token: str | None = Cookie(default=None),
    date_from: str = Form(...),
    date_to: str = Form(...),
    status: str = Form(default=""),
    responsible_person: str = Form(...),
    notes: str = Form(default=""),
    completion_reason: str = Form(default=""),
    cancellation_reason: str = Form(default=""),
    loaded_updated_at: str = Form(default=""),
    admin_override: str = Form(default=""),
    fixed_asset_ids: list[str] = Form(default=[]),
    fixed_asset_quantities: list[str] = Form(default=[]),
) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to edit inventory sessions.")
    inv_session = repo.get_session_by_id(session_id)
    if inv_session is None:
        return render_login_page("Inventory session not found.")

    current_status = str(inv_session["status"])
    target_status = status or current_status
    is_admin_user = svc.is_admin_email(str(user["email"]))
    admin_override_requested = admin_override in {"1", "true", "on", "yes"}
    if svc.is_terminal_status(current_status) and not is_admin_user:
        return _render_edit_page(
            user_email=str(user["email"]),
            inv_session=inv_session,
            linked_asset_rows=_edit_rows(session_id),
            is_admin_user=is_admin_user,
            error="Terminal sessions are read-only.",
        )

    if svc.is_stale(loaded_updated_at, inv_session["updated_at"]):
        # Saving would overwrite counts made since the page was opened (for
        # example on a phone), so show the latest version instead.
        return _render_edit_page(
            user_email=str(user["email"]),
            inv_session=inv_session,
            linked_asset_rows=_edit_rows(session_id),
            is_admin_user=is_admin_user,
            error=(
                "This session was changed after you opened this page, for example by counting on a phone "
                "or changing the active location. "
                "Your changes were not saved. The latest counts are shown below; make your changes again."
            ),
        )

    error = svc.validate_session_form(
        date_from=date_from,
        date_to=date_to,
        status=target_status,
        responsible_person=responsible_person,
    )
    linked_assets, linked_assets_error = svc.parse_linked_assets(
        fixed_asset_ids=fixed_asset_ids,
        fixed_asset_quantities=fixed_asset_quantities,
    )
    status_transition_error = svc.transition_error(
        current_status,
        target_status,
        allow_override=is_admin_user and admin_override_requested,
    )
    terminal_reason_error: str | None = None
    if current_status != target_status and target_status == "Completed" and not completion_reason.strip():
        terminal_reason_error = "Completion reason is required when completing a session."
    if current_status != target_status and target_status == "Cancelled" and not cancellation_reason.strip():
        terminal_reason_error = "Cancellation reason is required when cancelling a session."

    combined_error = error or linked_assets_error or status_transition_error or terminal_reason_error
    if combined_error:
        linked_asset_rows = _edit_rows(session_id, list(zip(fixed_asset_ids, fixed_asset_quantities)))
        return _render_edit_page(
            user_email=str(user["email"]),
            inv_session=inv_session,
            error=combined_error,
            prefill={
                "date_from": date_from,
                "date_to": date_to,
                "status": target_status,
                "responsible_person": responsible_person,
                "notes": notes,
                "completion_reason": completion_reason,
                "cancellation_reason": cancellation_reason,
                "admin_override": "1" if admin_override_requested else "",
            },
            linked_asset_rows=linked_asset_rows,
            is_admin_user=is_admin_user,
        )

    updated = repo.update_session(
        session_id=session_id,
        date_from=date_from,
        date_to=date_to,
        status=target_status,
        responsible_person=responsible_person,
        linked_assets=linked_assets,
        notes=notes,
        completion_reason=completion_reason,
        cancellation_reason=cancellation_reason,
        actor_user_id=int(user["id"]),
    )
    if updated is None:
        return render_login_page("Inventory session not found.")
    if target_status != current_status:
        audit(
            "inventory_session.reopened" if svc.is_terminal_status(current_status)
            else f"inventory_session.{_STATUS_EVENTS.get(target_status, 'status_changed')}",
            session_id=session_id,
            from_status=current_status,
            to_status=target_status,
            admin_override=bool(is_admin_user and admin_override_requested
                                and svc.transition_error(current_status, target_status)),
            reason=completion_reason.strip() or cancellation_reason.strip() or None,
        )
    audit(
        "inventory_session.updated",
        session_id=session_id,
        status=target_status,
        location=inv_session["location"],
        linked_assets=len(linked_assets),
        counted_here=sum(quantity for _, quantity in linked_assets),
    )
    return RedirectResponse(
        url=f"/inventory-sessions/id/{session_id}",
        status_code=303,
    )


@router.post(
    "/inventory-sessions/id/{session_id}/start",
    response_class=HTMLResponse,
)
def start_inventory_session(
    session_id: str,
    session_token: str | None = Cookie(default=None),
) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to start inventory sessions.")

    inv_session = repo.get_session_by_id(session_id)
    if inv_session is None:
        return render_login_page("Inventory session not found.")

    current_status = str(inv_session["status"])
    transition_error = svc.transition_error(current_status, "Active")
    if transition_error:
        return _render_details_with_message(
            user_email=str(user["email"]),
            session_id=session_id,
            message=transition_error,
        )

    repo.update_session(
        session_id=session_id,
        date_from=str(inv_session["date_from"]),
        date_to=str(inv_session["date_to"]),
        status="Active",
        responsible_person=str(inv_session["responsible_person"]),
        notes=str(inv_session["notes"] or ""),
        completion_reason=str(inv_session["completion_reason"] or ""),
        cancellation_reason=str(inv_session["cancellation_reason"] or ""),
        actor_user_id=int(user["id"]),
    )

    audit(
        "inventory_session.started",
        session_id=session_id,
        from_status=current_status,
    )
    return RedirectResponse(
        url=f"/inventory-sessions/id/{session_id}",
        status_code=303,
    )


@router.post(
    "/inventory-sessions/id/{session_id}/complete",
    response_class=HTMLResponse,
)
def complete_inventory_session(
    session_id: str,
    session_token: str | None = Cookie(default=None),
    completion_reason: str = Form(default=""),
    back: str = Form(default=""),
) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to complete inventory sessions.")

    inv_session = repo.get_session_by_id(session_id)
    if inv_session is None:
        return render_login_page("Inventory session not found.")

    current_status = str(inv_session["status"])
    transition_error = svc.transition_error(current_status, "Completed")
    if not completion_reason.strip():
        transition_error = transition_error or "Completion reason is required when completing a session."
    if transition_error:
        if back == "finish" and current_status == "Active":
            return render_inventory_session_finish_page(
                str(user["email"]), inv_session, completion_reason=completion_reason,
                message=transition_error, message_kind="error",
            )
        return _render_details_with_message(
            user_email=str(user["email"]),
            session_id=session_id,
            message=transition_error,
        )

    repo.update_session(
        session_id=session_id,
        date_from=str(inv_session["date_from"]),
        date_to=str(inv_session["date_to"]),
        status="Completed",
        responsible_person=str(inv_session["responsible_person"]),
        notes=str(inv_session["notes"] or ""),
        completion_reason=completion_reason,
        cancellation_reason=str(inv_session["cancellation_reason"] or ""),
        actor_user_id=int(user["id"]),
    )

    audit(
        "inventory_session.completed",
        session_id=session_id,
        from_status=current_status,
        reason=completion_reason.strip(),
    )
    return RedirectResponse(
        url=f"/inventory-sessions/id/{session_id}",
        status_code=303,
    )


@router.post(
    "/inventory-sessions/id/{session_id}/cancel",
    response_class=HTMLResponse,
)
def cancel_inventory_session(
    session_id: str,
    session_token: str | None = Cookie(default=None),
    cancellation_reason: str = Form(default=""),
) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to cancel inventory sessions.")

    inv_session = repo.get_session_by_id(session_id)
    if inv_session is None:
        return render_login_page("Inventory session not found.")

    current_status = str(inv_session["status"])
    transition_error = svc.transition_error(current_status, "Cancelled")
    if not cancellation_reason.strip():
        transition_error = transition_error or "Cancellation reason is required when cancelling a session."
    if transition_error:
        return _render_details_with_message(
            user_email=str(user["email"]),
            session_id=session_id,
            message=transition_error,
        )

    repo.update_session(
        session_id=session_id,
        date_from=str(inv_session["date_from"]),
        date_to=str(inv_session["date_to"]),
        status="Cancelled",
        responsible_person=str(inv_session["responsible_person"]),
        notes=str(inv_session["notes"] or ""),
        completion_reason=str(inv_session["completion_reason"] or ""),
        cancellation_reason=cancellation_reason,
        actor_user_id=int(user["id"]),
    )

    audit(
        "inventory_session.cancelled",
        session_id=session_id,
        from_status=current_status,
        reason=cancellation_reason.strip(),
    )
    return RedirectResponse(
        url=f"/inventory-sessions/id/{session_id}",
        status_code=303,
    )


@router.post(
    "/inventory-sessions/id/{session_id}/delete",
    response_class=HTMLResponse,
)
def delete_inventory_session(
    session_id: str,
    session_token: str | None = Cookie(default=None),
) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to delete inventory sessions.")
    inv_session = repo.get_session_by_id(session_id)
    if inv_session is None:
        return render_login_page("Inventory session not found.")
    current_status = str(inv_session["status"])
    if svc.is_terminal_status(current_status):
        return _render_details_with_message(
            user_email=str(user["email"]),
            session_id=session_id,
            message="Terminal sessions are read-only and cannot be deleted.",
        )

    repo.delete_session(session_id)
    audit(
        "inventory_session.deleted",
        session_id=session_id,
        status=str(inv_session["status"]),
        date_from=inv_session["date_from"],
        date_to=inv_session["date_to"],
        responsible_person=inv_session["responsible_person"],
    )
    return RedirectResponse(url="/inventory-sessions", status_code=303)
