from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, Cookie, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.repositories import fixed_assets_repository as assets_repo
from app.repositories import inventory_sessions_repository as repo
from app.services import auth_service
from app.services import inventory_sessions_service as svc
from app.views.pages import (
    render_add_inventory_session_page,
    render_edit_inventory_session_page,
    render_inventory_session_details_page,
    render_inventory_sessions_page,
    render_login_page,
)

router = APIRouter()


def _build_filters(
    *,
    status: str,
    responsible_person: str,
    date_from: str,
    date_to: str,
) -> dict[str, str]:
    return {
        "status": status,
        "responsible_person": responsible_person,
        "date_from": date_from,
        "date_to": date_to,
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


def _render_edit_page(
    *,
    user_email: str,
    inv_session: object,
    linked_asset_rows: list[dict[str, str]],
    error: str | None = None,
    prefill: dict[str, str] | None = None,
) -> HTMLResponse:
    current_status = str(inv_session["status"])
    return render_edit_inventory_session_page(
        inv_session=inv_session,
        current_email=user_email,
        statuses=svc.available_target_statuses(current_status),
        fixed_assets=assets_repo.list_assets(),
        linked_asset_rows=linked_asset_rows,
        is_read_only=svc.is_terminal_status(current_status),
        error=error,
        prefill=prefill,
    )


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
) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to access inventory sessions.")

    sessions = repo.list_sessions(
        status=status or None,
        responsible_person=responsible_person or None,
        date_from=date_from or None,
        date_to=date_to or None,
    )
    filters = _build_filters(
        status=status,
        responsible_person=responsible_person,
        date_from=date_from,
        date_to=date_to,
    )
    return render_inventory_sessions_page(
        sessions=sessions,
        current_email=user["email"],
        statuses=list(svc.STATUSES),
        filters=filters,
        summary=_calculate_summary(sessions),
    )


@router.get("/inventory-sessions/export.csv")
def export_inventory_sessions_csv(
    session_token: str | None = Cookie(default=None),
    status: str = Query(default=""),
    responsible_person: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
) -> Response:
    user = auth_service.current_user(session_token)
    if user is None:
        return Response(content="Please log in to export inventory sessions.", status_code=401)

    sessions = repo.list_sessions(
        status=status or None,
        responsible_person=responsible_person or None,
        date_from=date_from or None,
        date_to=date_to or None,
    )
    summary = _calculate_summary(sessions)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Filters", "Value"])
    writer.writerow(["status", status or "ALL"])
    writer.writerow(["responsible_person", responsible_person or "ALL"])
    writer.writerow(["date_from", date_from or "ALL"])
    writer.writerow(["date_to", date_to or "ALL"])
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
) -> Response:
    user = auth_service.current_user(session_token)
    if user is None:
        return Response(content="Please log in to export inventory sessions.", status_code=401)

    sessions = repo.list_sessions(
        status=status or None,
        responsible_person=responsible_person or None,
        date_from=date_from or None,
        date_to=date_to or None,
    )
    summary = _calculate_summary(sessions)

    payload = {
        "filters": _build_filters(
            status=status,
            responsible_person=responsible_person,
            date_from=date_from,
            date_to=date_to,
        ),
        "summary": summary,
        "sessions": [
            {
                "id": str(row["id"]),
                "date_from": str(row["date_from"]),
                "date_to": str(row["date_to"]),
                "status": str(row["status"]),
                "responsible_person": str(row["responsible_person"]),
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
        linked_asset_rows=[{"fixed_asset_id": "", "quantity": "1"}],
    )


@router.post("/inventory-sessions/add", response_class=HTMLResponse)
def add_inventory_session(
    session_token: str | None = Cookie(default=None),
    date_from: str = Form(...),
    date_to: str = Form(...),
    responsible_person: str = Form(...),
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
    combined_error = error or linked_assets_error
    if combined_error:
        fixed_assets = assets_repo.list_assets()
        linked_asset_rows = [
            {"fixed_asset_id": fixed_asset_ids[index], "quantity": fixed_asset_quantities[index]}
            for index in range(min(len(fixed_asset_ids), len(fixed_asset_quantities)))
        ]
        if not linked_asset_rows:
            linked_asset_rows = [{"fixed_asset_id": "", "quantity": "1"}]
        return render_add_inventory_session_page(
            current_email=user["email"],
            error=combined_error,
            prefill={
                "date_from": date_from,
                "date_to": date_to,
                "responsible_person": responsible_person,
            },
            fixed_assets=fixed_assets,
            linked_asset_rows=linked_asset_rows,
        )

    session = repo.create_session(
        date_from=date_from,
        date_to=date_to,
        responsible_person=responsible_person,
        linked_assets=linked_assets,
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
    linked_assets = repo.list_linked_assets(session_id)
    return render_inventory_session_details_page(
        inv_session=inv_session,
        current_email=user["email"],
        linked_assets=linked_assets,
    )


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
    linked_assets = repo.list_linked_assets_with_quantity(session_id)
    linked_asset_rows = [
        {"fixed_asset_id": fixed_asset_id, "quantity": str(quantity)}
        for fixed_asset_id, quantity in linked_assets
    ]
    if not linked_asset_rows:
        linked_asset_rows = [{"fixed_asset_id": "", "quantity": "1"}]
    return _render_edit_page(
        user_email=str(user["email"]),
        inv_session=inv_session,
        linked_asset_rows=linked_asset_rows,
    )


@router.post("/inventory-sessions/id/{session_id}/edit", response_class=HTMLResponse)
def edit_inventory_session(
    session_id: str,
    session_token: str | None = Cookie(default=None),
    date_from: str = Form(...),
    date_to: str = Form(...),
    status: str = Form(...),
    responsible_person: str = Form(...),
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
    if svc.is_terminal_status(current_status):
        linked_assets = repo.list_linked_assets_with_quantity(session_id)
        linked_asset_rows = [
            {"fixed_asset_id": fixed_asset_id, "quantity": str(quantity)}
            for fixed_asset_id, quantity in linked_assets
        ]
        if not linked_asset_rows:
            linked_asset_rows = [{"fixed_asset_id": "", "quantity": "1"}]
        return _render_edit_page(
            user_email=str(user["email"]),
            inv_session=inv_session,
            linked_asset_rows=linked_asset_rows,
            error="Terminal sessions are read-only.",
        )

    error = svc.validate_session_form(
        date_from=date_from,
        date_to=date_to,
        status=status,
        responsible_person=responsible_person,
    )
    linked_assets, linked_assets_error = svc.parse_linked_assets(
        fixed_asset_ids=fixed_asset_ids,
        fixed_asset_quantities=fixed_asset_quantities,
    )
    status_transition_error = svc.transition_error(current_status, status)
    combined_error = error or linked_assets_error or status_transition_error
    if combined_error:
        linked_asset_rows = [
            {"fixed_asset_id": fixed_asset_ids[index], "quantity": fixed_asset_quantities[index]}
            for index in range(min(len(fixed_asset_ids), len(fixed_asset_quantities)))
        ]
        if not linked_asset_rows:
            linked_asset_rows = [{"fixed_asset_id": "", "quantity": "1"}]
        return _render_edit_page(
            user_email=str(user["email"]),
            inv_session=inv_session,
            error=combined_error,
            prefill={
                "date_from": date_from,
                "date_to": date_to,
                "status": status,
                "responsible_person": responsible_person,
            },
            linked_asset_rows=linked_asset_rows,
        )

    updated = repo.update_session(
        session_id=session_id,
        date_from=date_from,
        date_to=date_to,
        status=status,
        responsible_person=responsible_person,
        linked_assets=linked_assets,
    )
    if updated is None:
        return render_login_page("Inventory session not found.")
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

    linked_assets = repo.list_linked_assets_with_quantity(session_id)
    repo.update_session(
        session_id=session_id,
        date_from=str(inv_session["date_from"]),
        date_to=str(inv_session["date_to"]),
        status="Active",
        responsible_person=str(inv_session["responsible_person"]),
        linked_assets=linked_assets,
    )

    return RedirectResponse(
        url=f"/inventory-sessions/id/{session_id}/edit",
        status_code=303,
    )


@router.post(
    "/inventory-sessions/id/{session_id}/complete",
    response_class=HTMLResponse,
)
def complete_inventory_session(
    session_id: str,
    session_token: str | None = Cookie(default=None),
) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to complete inventory sessions.")

    inv_session = repo.get_session_by_id(session_id)
    if inv_session is None:
        return render_login_page("Inventory session not found.")

    current_status = str(inv_session["status"])
    transition_error = svc.transition_error(current_status, "Completed")
    if transition_error:
        return _render_details_with_message(
            user_email=str(user["email"]),
            session_id=session_id,
            message=transition_error,
        )

    linked_assets = repo.list_linked_assets_with_quantity(session_id)
    repo.update_session(
        session_id=session_id,
        date_from=str(inv_session["date_from"]),
        date_to=str(inv_session["date_to"]),
        status="Completed",
        responsible_person=str(inv_session["responsible_person"]),
        linked_assets=linked_assets,
    )

    return RedirectResponse(
        url=f"/inventory-sessions/id/{session_id}/edit",
        status_code=303,
    )


@router.post(
    "/inventory-sessions/id/{session_id}/cancel",
    response_class=HTMLResponse,
)
def cancel_inventory_session(
    session_id: str,
    session_token: str | None = Cookie(default=None),
) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to cancel inventory sessions.")

    inv_session = repo.get_session_by_id(session_id)
    if inv_session is None:
        return render_login_page("Inventory session not found.")

    current_status = str(inv_session["status"])
    transition_error = svc.transition_error(current_status, "Cancelled")
    if transition_error:
        return _render_details_with_message(
            user_email=str(user["email"]),
            session_id=session_id,
            message=transition_error,
        )

    linked_assets = repo.list_linked_assets_with_quantity(session_id)
    repo.update_session(
        session_id=session_id,
        date_from=str(inv_session["date_from"]),
        date_to=str(inv_session["date_to"]),
        status="Cancelled",
        responsible_person=str(inv_session["responsible_person"]),
        linked_assets=linked_assets,
    )

    return RedirectResponse(
        url=f"/inventory-sessions/id/{session_id}/edit",
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
    return RedirectResponse(url="/inventory-sessions", status_code=303)
