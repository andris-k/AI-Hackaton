from __future__ import annotations

from fastapi import APIRouter, Cookie, Query
from fastapi.responses import HTMLResponse

from app.services import auth_service
from app.views.pages import render_analytics_page, render_login_page

router = APIRouter()


@router.get("/analytics", response_class=HTMLResponse)
def analytics_page(
    session_token: str | None = Cookie(default=None),
    measure: str = Query(default="value"),
) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to see analytics.")
    return render_analytics_page(user["email"], measure)
