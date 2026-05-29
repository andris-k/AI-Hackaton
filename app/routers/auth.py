from __future__ import annotations

from html import escape

from fastapi import APIRouter, Cookie, Form, Query
from fastapi.responses import HTMLResponse

from app.repositories import auth_repository
from app.services import auth_service
from app.views.pages import (
    render_dashboard_page,
    render_forgot_password_page,
    render_login_page,
    render_page,
    render_register_page,
    render_reset_password_page,
    render_users_page,
)

router = APIRouter()

SESSION_COOKIE_NAME = "session_token"
SESSION_MAX_AGE_SECONDS = 24 * 60 * 60


def set_session_cookie(response: HTMLResponse, session_token: str) -> HTMLResponse:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        samesite="lax",
        max_age=SESSION_MAX_AGE_SECONDS,
    )
    return response


@router.get("/", response_class=HTMLResponse)
def read_root(session_token: str | None = Cookie(default=None)) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is not None:
        return render_dashboard_page(user["email"], session_token or "")

    return render_login_page()


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(session_token: str | None = Cookie(default=None)) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to access the dashboard.")

    return render_dashboard_page(user["email"], session_token or "")


@router.get("/users", response_class=HTMLResponse)
def users_page(
    session_token: str | None = Cookie(default=None),
    email: str = Query(default=""),
) -> HTMLResponse:
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to access the users page.")

    users = auth_service.list_users(email)
    return render_users_page(user["email"], users, email)


@router.post("/", response_class=HTMLResponse)
def login(email: str = Form(...), password: str = Form(...)) -> HTMLResponse:
    user, session_token, error = auth_service.login_user(email, password)
    if error:
        return render_login_page(error, email=email)

    response = set_session_cookie(
        render_dashboard_page(user["email"], session_token, message="You are now logged in."),
        session_token,
    )
    return response


@router.get("/register", response_class=HTMLResponse)
def register_page() -> HTMLResponse:
    return render_register_page()


@router.post("/register", response_class=HTMLResponse)
def register(email: str = Form(...), password: str = Form(...), confirm_password: str = Form(...)) -> HTMLResponse:
    user, session_token, error = auth_service.register_user(email, password, confirm_password)
    if error:
        return render_register_page(error, email=email)

    response = set_session_cookie(
        render_dashboard_page(user["email"], session_token, message="Account created successfully."),
        session_token,
    )
    return response


@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_page() -> HTMLResponse:
    return render_forgot_password_page()


@router.post("/forgot-password", response_class=HTMLResponse)
def forgot_password(email: str = Form(...)) -> HTMLResponse:
    token, error = auth_service.create_password_reset_link(email)
    if error:
        return render_forgot_password_page(error)

    if token is None:
        return render_forgot_password_page(
            "If that account exists, a reset link will be created here.",
            email=email,
        )

    reset_link = f"/reset-password/{token}"
    content = f"""
    <div class="stack">
        <section class="panel wide">
            <h2>Reset link created</h2>
            <p>A reset link is ready for <strong>{escape(email)}</strong>.</p>
            <code>{escape(reset_link)}</code>
            <div class="links">
                <a href="{escape(reset_link)}">Open reset page</a>
                <a href="/">Back to login</a>
            </div>
        </section>
    </div>
    """
    return render_page(
        "AI Hackaton Reset Link",
        "Password reset link",
        "Open the generated link to set a new password.",
        content,
        width="520px",
        message="For local testing, the reset link is shown on screen instead of being emailed.",
        message_kind="success",
    )


@router.get("/reset-password/{token}", response_class=HTMLResponse)
def reset_password_page(token: str) -> HTMLResponse:
    reset_token = auth_repository.find_reset_token(token)
    if reset_token is None:
        return render_page(
            "AI Hackaton Reset Password",
            "Reset link expired",
            "The password reset token is invalid or expired.",
            '<div class="links"><a href="/forgot-password">Request a new reset link</a></div>',
            message="That reset link cannot be used.",
            message_kind="error",
        )

    return render_reset_password_page(token)


@router.post("/reset-password/{token}", response_class=HTMLResponse)
def reset_password(
    token: str,
    password: str = Form(...),
    confirm_password: str = Form(...),
) -> HTMLResponse:
    user, error, invalid_token = auth_service.reset_password(token, password, confirm_password)
    if invalid_token:
        return render_page(
            "AI Hackaton Reset Password",
            "Reset link expired",
            "The password reset token is invalid or expired.",
            '<div class="links"><a href="/forgot-password">Request a new reset link</a></div>',
            message=error,
            message_kind="error",
        )

    if error:
        if error == "Password updated, but the account could not be reloaded.":
            return render_login_page(error)
        return render_reset_password_page(token, error)

    session_token = auth_service.create_session_for_user(user["id"])
    response = set_session_cookie(
        render_dashboard_page(user["email"], session_token, message="Password updated successfully."),
        session_token,
    )
    return response


@router.get("/logout", response_class=HTMLResponse)
def logout(session_token: str | None = Cookie(default=None)) -> HTMLResponse:
    auth_service.logout_user(session_token)

    response = render_login_page("You have been logged out.")
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response
