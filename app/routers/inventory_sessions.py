from __future__ import annotations

from fastapi import APIRouter, Cookie, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse

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
    return render_inventory_sessions_page(
        sessions=sessions,
        current_email=user["email"],
        statuses=list(svc.STATUSES),
        filters={
            "status": status,
            "responsible_person": responsible_person,
            "date_from": date_from,
            "date_to": date_to,
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
    fixed_assets = assets_repo.list_assets()
    linked_assets = repo.list_linked_assets_with_quantity(session_id)
    linked_asset_rows = [
        {"fixed_asset_id": fixed_asset_id, "quantity": str(quantity)}
        for fixed_asset_id, quantity in linked_assets
    ]
    if not linked_asset_rows:
        linked_asset_rows = [{"fixed_asset_id": "", "quantity": "1"}]
    is_read_only = str(inv_session["status"]) == "Completed"
    return render_edit_inventory_session_page(
        inv_session=inv_session,
        current_email=user["email"],
        statuses=list(svc.STATUSES),
        fixed_assets=fixed_assets,
        linked_asset_rows=linked_asset_rows,
        is_read_only=is_read_only,
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
    if str(inv_session["status"]) == "Completed":
        fixed_assets = assets_repo.list_assets()
        linked_assets = repo.list_linked_assets_with_quantity(session_id)
        linked_asset_rows = [
            {"fixed_asset_id": fixed_asset_id, "quantity": str(quantity)}
            for fixed_asset_id, quantity in linked_assets
        ]
        if not linked_asset_rows:
            linked_asset_rows = [{"fixed_asset_id": "", "quantity": "1"}]
        return render_edit_inventory_session_page(
            inv_session=inv_session,
            current_email=user["email"],
            statuses=list(svc.STATUSES),
            fixed_assets=fixed_assets,
            linked_asset_rows=linked_asset_rows,
            is_read_only=True,
            error="Completed sessions are read-only.",
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
    combined_error = error or linked_assets_error
    if combined_error:
        fixed_assets = assets_repo.list_assets()
        linked_asset_rows = [
            {"fixed_asset_id": fixed_asset_ids[index], "quantity": fixed_asset_quantities[index]}
            for index in range(min(len(fixed_asset_ids), len(fixed_asset_quantities)))
        ]
        if not linked_asset_rows:
            linked_asset_rows = [{"fixed_asset_id": "", "quantity": "1"}]
        return render_edit_inventory_session_page(
            inv_session=inv_session,
            current_email=user["email"],
            statuses=list(svc.STATUSES),
            error=combined_error,
            prefill={
                "date_from": date_from,
                "date_to": date_to,
                "status": status,
                "responsible_person": responsible_person,
            },
            fixed_assets=fixed_assets,
            linked_asset_rows=linked_asset_rows,
            is_read_only=False,
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

    if str(inv_session["status"]) == "New":
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

    if str(inv_session["status"]) != "Completed":
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
    if str(inv_session["status"]) == "Completed":
        return RedirectResponse(
            url=f"/inventory-sessions/id/{session_id}/edit",
            status_code=303,
        )

    repo.delete_session(session_id)
    return RedirectResponse(url="/inventory-sessions", status_code=303)
