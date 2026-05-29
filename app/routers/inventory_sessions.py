from __future__ import annotations

from fastapi import APIRouter, Cookie, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse

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
    return render_add_inventory_session_page(
        current_email=user["email"],
    )


@router.post("/inventory-sessions/add", response_class=HTMLResponse)
def add_inventory_session(
    session_token: str | None = Cookie(default=None),
    date_from: str = Form(...),
    date_to: str = Form(...),
    responsible_person: str = Form(...),
) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to add an inventory session.")

    error = svc.validate_create_form(
        date_from=date_from,
        date_to=date_to,
        responsible_person=responsible_person,
    )
    if error:
        return render_add_inventory_session_page(
            current_email=user["email"],
            error=error,
            prefill={
                "date_from": date_from,
                "date_to": date_to,
                "responsible_person": responsible_person,
            },
        )

    session = repo.create_session(
        date_from=date_from,
        date_to=date_to,
        responsible_person=responsible_person,
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
    return render_inventory_session_details_page(
        inv_session=inv_session,
        current_email=user["email"],
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
    return render_edit_inventory_session_page(
        inv_session=inv_session,
        current_email=user["email"],
        statuses=list(svc.STATUSES),
    )


@router.post("/inventory-sessions/id/{session_id}/edit", response_class=HTMLResponse)
def edit_inventory_session(
    session_id: str,
    session_token: str | None = Cookie(default=None),
    date_from: str = Form(...),
    date_to: str = Form(...),
    status: str = Form(...),
    responsible_person: str = Form(...),
) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to edit inventory sessions.")
    inv_session = repo.get_session_by_id(session_id)
    if inv_session is None:
        return render_login_page("Inventory session not found.")

    error = svc.validate_session_form(
        date_from=date_from,
        date_to=date_to,
        status=status,
        responsible_person=responsible_person,
    )
    if error:
        return render_edit_inventory_session_page(
            inv_session=inv_session,
            current_email=user["email"],
            statuses=list(svc.STATUSES),
            error=error,
            prefill={
                "date_from": date_from,
                "date_to": date_to,
                "status": status,
                "responsible_person": responsible_person,
            },
        )

    updated = repo.update_session(
        session_id=session_id,
        date_from=date_from,
        date_to=date_to,
        status=status,
        responsible_person=responsible_person,
    )
    if updated is None:
        return render_login_page("Inventory session not found.")
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
    repo.delete_session(session_id)
    return RedirectResponse(url="/inventory-sessions", status_code=303)
