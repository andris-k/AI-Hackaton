from __future__ import annotations

from fastapi import APIRouter, Cookie, Form
from fastapi.responses import HTMLResponse

from app.logging_config import audit
from app.repositories import locations_repository as locations_repo
from app.services import auth_service
from app.services import fixed_assets_service as assets_service
from app.views.pages import (
    render_edit_location_page,
    render_locations_page,
    render_login_page,
    render_page,
)

router = APIRouter()
_LOGIN_MESSAGE = "Please log in to manage locations."


def _not_found(current_email: str) -> HTMLResponse:
    return render_page(
        "AI Hackaton Edit Location",
        "Location Not Found",
        "The requested location does not exist.",
        '<div class="links"><a href="/locations">Back to locations</a></div>',
        message="Location not found.",
        message_kind="error",
        current_email=current_email,
        active_nav="locations",
    )


@router.get("/locations", response_class=HTMLResponse)
def locations_page(session_token: str | None = Cookie(default=None)) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page(_LOGIN_MESSAGE)
    return render_locations_page(user["email"])


@router.post("/locations", response_class=HTMLResponse)
def create_location_route(
    session_token: str | None = Cookie(default=None),
    name: str = Form(...),
) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page(_LOGIN_MESSAGE)

    normalized_name, name_error = assets_service.validate_location_name(name)
    if name_error:
        return render_locations_page(user["email"], message=name_error, message_kind="error")
    try:
        created = locations_repo.create(normalized_name)
    except ValueError as error:
        return render_locations_page(user["email"], message=str(error), message_kind="error")

    audit("location.created", location_id=created["id"], name=created["name"])
    return render_locations_page(user["email"], message="Location created successfully.", message_kind="success")


@router.get("/locations/{location_id}/edit", response_class=HTMLResponse)
def edit_location_page(
    location_id: str,
    session_token: str | None = Cookie(default=None),
) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page(_LOGIN_MESSAGE)
    location = locations_repo.get_by_id(location_id)
    if location is None:
        return _not_found(user["email"])
    return render_edit_location_page(user["email"], location)


@router.post("/locations/{location_id}/edit", response_class=HTMLResponse)
def edit_location_route(
    location_id: str,
    session_token: str | None = Cookie(default=None),
    name: str = Form(...),
) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page(_LOGIN_MESSAGE)
    location = locations_repo.get_by_id(location_id)
    if location is None:
        return _not_found(user["email"])

    normalized_name, name_error = assets_service.validate_location_name(name)
    if name_error:
        return render_edit_location_page(user["email"], location, message=name_error, message_kind="error")
    try:
        updated = locations_repo.update(location_id, normalized_name)
    except ValueError as error:
        return render_edit_location_page(user["email"], location, message=str(error), message_kind="error")
    if updated is None:
        return _not_found(user["email"])

    if location["name"] != updated["name"]:
        audit("location.renamed", location_id=location_id, changes={"name": [location["name"], updated["name"]]})
    return render_edit_location_page(
        user["email"], updated, message="Location updated successfully.", message_kind="success"
    )


@router.post("/locations/{location_id}/delete", response_class=HTMLResponse)
def delete_location_route(
    location_id: str,
    session_token: str | None = Cookie(default=None),
) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page(_LOGIN_MESSAGE)

    location = locations_repo.get_by_id(location_id)
    if location is None:
        return render_locations_page(
            user["email"], message="Location not found or already deleted.", message_kind="error"
        )
    if not locations_repo.delete(location_id):
        return render_locations_page(
            user["email"],
            message="Cannot delete a location while fixed assets are at it. Move them first.",
            message_kind="error",
        )

    audit("location.deleted", location_id=location_id, name=location["name"])
    return render_locations_page(user["email"], message="Location deleted successfully.", message_kind="success")
