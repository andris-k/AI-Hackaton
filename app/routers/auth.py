from __future__ import annotations

from html import escape

from fastapi import APIRouter, Cookie, Form, Query
from fastapi.responses import HTMLResponse

from app import config
from app.repositories import auth_repository
from app.services import auth_service, email_service
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


def _cookie_secure() -> bool:
    # SESSION_COOKIE_SECURE overrides; otherwise secure cookies only in production.
    return config.session_cookie_secure()


def _cookie_samesite() -> str:
    # Keep local workflow unchanged in development but tighten default in production.
    return config.session_cookie_samesite()


def set_session_cookie(response: HTMLResponse, session_token: str) -> HTMLResponse:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=_cookie_secure(),
        samesite=_cookie_samesite(),
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

    return _users_page(user, email)


def _users_page(user: object, email_filter: str = "", message: str | None = None, message_kind: str = "info") -> HTMLResponse:
    return render_users_page(
        user["email"],
        auth_service.list_users(email_filter),
        email_filter,
        current_user_id=int(user["id"]),
        is_admin=auth_service.is_admin(user["email"]),
        message=message,
        message_kind=message_kind,
    )


def _admin_action(session_token: str | None, action) -> HTMLResponse:
    """Run an admin-only action on the Users page and show the result there."""
    user = auth_service.current_user(session_token)
    if user is None:
        return render_login_page("Please log in to access the users page.")
    if not auth_service.is_admin(user["email"]):
        return _users_page(user, message="Only administrators can do that.", message_kind="error")
    error, success = action(user)
    return _users_page(user, message=error or success, message_kind="error" if error else "success")


@router.post("/users/{user_id}/approve", response_class=HTMLResponse)
def approve_user(user_id: int, session_token: str | None = Cookie(default=None)) -> HTMLResponse:
    return _admin_action(
        session_token,
        lambda admin: (auth_service.approve_account(admin, user_id), "Account approved. The user can now log in."),
    )


@router.post("/users/{user_id}/reject", response_class=HTMLResponse)
def reject_user(user_id: int, session_token: str | None = Cookie(default=None)) -> HTMLResponse:
    return _admin_action(
        session_token,
        lambda admin: (auth_service.reject_account(user_id), "Account rejected and deleted."),
    )


@router.post("/users/{user_id}/admin", response_class=HTMLResponse)
def set_user_admin(
    user_id: int,
    session_token: str | None = Cookie(default=None),
    make_admin: str = Form(default=""),
) -> HTMLResponse:
    grant = make_admin in {"1", "true", "on", "yes"}
    return _admin_action(
        session_token,
        lambda admin: (
            auth_service.set_admin_rights(admin, user_id, grant),
            "Administrator rights given." if grant else "Administrator rights removed.",
        ),
    )


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
    if session_token is None:
        return render_login_page(
            notice="Your account has been created and is waiting for an administrator's approval. "
            "You can log in once it has been approved.",
            email=user["email"],
        )

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
    if not config.password_reset_available():
        return render_forgot_password_page()

    token, error = auth_service.create_password_reset_link(email)
    if error:
        return render_forgot_password_page(error)

    if not config.show_reset_link_on_screen():
        # Production: email the link and give the same answer whether or not the
        # account exists, so the form can't be used to discover registered emails.
        if token is not None:
            email_service.send_password_reset_email(email, f"/reset-password/{token}")
        return render_forgot_password_page(
            notice="If an account exists for that email, we've sent a link to reset the password. "
            "The link works for 1 hour.",
        )

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

    if user["status"] != "active":
        return render_login_page(notice="Password updated. " + auth_service.PENDING_LOGIN_MESSAGE, email=user["email"])
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
