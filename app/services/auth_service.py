from __future__ import annotations

import sqlite3

from app import config
from app.logging_config import audit, set_request_user
from app.repositories import auth_repository
from app.services import email_service

PENDING_LOGIN_MESSAGE = (
    "Your account is waiting for an administrator's approval. You can log in once it has been approved."
)


def initialize_defaults() -> None:
    auth_repository.initialize_auth_storage()


def current_user(session_token: str | None) -> sqlite3.Row | None:
    if not session_token:
        return None
    user = auth_repository.find_user_by_session_token(session_token)
    if user is not None:
        set_request_user(user["id"], user["email"])
    return user


def login_user(email: str, password: str) -> tuple[sqlite3.Row | None, str | None, str | None]:
    if not email or not password:
        return None, None, "Both email and password are required."

    user = auth_repository.find_user_by_email(email)
    if user is None or not auth_repository.verify_user_password(password, user["password_hash"]):
        audit("auth.login_failed", actor=email, reason="unknown email" if user is None else "wrong password")
        return None, None, "Invalid email or password."
    # Only said after the password is checked, so the form doesn't reveal who has registered.
    if user["status"] != "active":
        audit("auth.login_failed", actor=email, reason="waiting for approval", user_id=user["id"])
        return None, None, PENDING_LOGIN_MESSAGE

    session_token, _ = auth_repository.create_user_session(user["id"])
    set_request_user(user["id"], user["email"])
    audit("auth.login", user_id=user["id"])
    return user, session_token, None


def register_user(
    email: str,
    password: str,
    confirm_password: str,
) -> tuple[sqlite3.Row | None, str | None, str | None]:
    if not email or not password or not confirm_password:
        return None, None, "All fields are required."

    if password != confirm_password:
        return None, None, "Passwords do not match."

    if auth_repository.find_user_by_email(email) is not None:
        return None, None, "That email is already registered."

    # Accounts named in ADMIN_EMAIL / ADMIN_EMAILS are trusted, so a new
    # installation can always get its first admin in. Everyone else waits for approval.
    if email.strip().lower() in config.admin_emails():
        user = auth_repository.create_user_account(email, password, is_admin=True)
        session_token, _ = auth_repository.create_user_session(user["id"])
        set_request_user(user["id"], user["email"])
        audit("auth.registered", user_id=user["id"], status="active")
        return user, session_token, None

    user = auth_repository.create_user_account(email, password, status="pending")
    audit("auth.registered", actor=user["email"], user_id=user["id"], status="pending")
    email_service.send_new_account_notice(auth_repository.admin_emails(), user["email"])
    return user, None, None


def approve_account(admin: sqlite3.Row, user_id: int) -> str | None:
    """Returns an error message, or None when the account was approved."""
    user = auth_repository.find_user_by_id(user_id)
    if user is None or not auth_repository.approve(user_id, int(admin["id"])):
        return "That account is not waiting for approval."
    audit("auth.account_approved", user_id=user_id, email=user["email"])
    return None


def reject_account(user_id: int) -> str | None:
    rejected = auth_repository.reject(user_id)
    if rejected is None:
        return "That account is not waiting for approval."
    audit("auth.account_rejected", user_id=user_id, email=rejected["email"])
    return None


def set_admin_rights(admin: sqlite3.Row, user_id: int, make_admin: bool) -> str | None:
    if int(admin["id"]) == user_id:
        return "You can't change your own administrator rights. Ask another administrator."
    user = auth_repository.find_user_by_id(user_id)
    try:
        changed = auth_repository.set_admin(user_id, make_admin)
    except ValueError as error:
        return str(error)
    if user is None or not changed:
        return "That account does not exist or is not active."
    if bool(user["is_admin"]) != make_admin:
        audit("auth.admin_granted" if make_admin else "auth.admin_revoked", user_id=user_id, email=user["email"])
    return None


def is_admin(email: str | None) -> bool:
    return auth_repository.is_admin(email)


def pending_account_count() -> int:
    return auth_repository.pending_count()


def create_password_reset_link(email: str) -> tuple[str | None, str | None]:
    if not email:
        return None, "Email is required."

    user = auth_repository.find_user_by_email(email)
    if user is None:
        audit("auth.password_reset_requested", actor=email, account_exists=False)
        return None, None

    token, _ = auth_repository.create_reset_token(user["id"])
    audit("auth.password_reset_requested", actor=email, account_exists=True, user_id=user["id"])
    return token, None


def reset_password(
    token: str,
    password: str,
    confirm_password: str,
) -> tuple[sqlite3.Row | None, str | None, bool]:
    reset_token = auth_repository.find_reset_token(token)
    if reset_token is None:
        return None, "That reset link cannot be used.", True

    if not password or not confirm_password:
        return None, "Both password fields are required.", False

    if password != confirm_password:
        return None, "Passwords do not match.", False

    user_id = reset_token["user_id"]
    auth_repository.update_password(user_id, password)
    auth_repository.delete_all_user_sessions(user_id)
    auth_repository.mark_reset_token_used(token)

    user = auth_repository.find_user_by_id(user_id)
    audit("auth.password_reset_completed", actor=user["email"] if user else None, user_id=user_id)
    if user is None:
        return None, "Password updated, but the account could not be reloaded.", False

    return user, None, False


def create_session_for_user(user_id: int) -> str:
    session_token, _ = auth_repository.create_user_session(user_id)
    return session_token


def logout_user(session_token: str | None) -> None:
    if session_token:
        user = auth_repository.find_user_by_session_token(session_token)
        auth_repository.delete_user_session(session_token)
        if user is not None:
            audit("auth.logout", actor=user["email"], user_id=user["id"])


def list_users(email_filter: str = "") -> list[sqlite3.Row]:
    return auth_repository.list_registered_users(email_filter)
