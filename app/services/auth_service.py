from __future__ import annotations

import sqlite3

from app.logging_config import audit, set_request_user
from app.repositories import auth_repository


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

    user = auth_repository.create_user_account(email, password)
    session_token, _ = auth_repository.create_user_session(user["id"])
    set_request_user(user["id"], user["email"])
    audit("auth.registered", user_id=user["id"])
    return user, session_token, None


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
