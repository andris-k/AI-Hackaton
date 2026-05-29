from __future__ import annotations

import sqlite3

from app.db import (
    create_password_reset_token,
    create_session,
    create_user,
    delete_session,
    delete_sessions_for_user,
    ensure_default_user,
    get_password_reset_token,
    get_user_by_email,
    get_user_by_id,
    get_user_by_session_token,
    initialize_database,
    list_users,
    mark_password_reset_token_used,
    update_user_password,
    verify_password,
)


def initialize_auth_storage() -> None:
    initialize_database()
    ensure_default_user()


def find_user_by_email(email: str) -> sqlite3.Row | None:
    return get_user_by_email(email)


def find_user_by_id(user_id: int) -> sqlite3.Row | None:
    return get_user_by_id(user_id)


def find_user_by_session_token(session_token: str) -> sqlite3.Row | None:
    return get_user_by_session_token(session_token)


def list_registered_users(email_filter: str = "") -> list[sqlite3.Row]:
    return list_users(email_filter)


def create_user_account(email: str, password: str) -> sqlite3.Row:
    return create_user(email, password)


def verify_user_password(password: str, password_hash: str) -> bool:
    return verify_password(password, password_hash)


def create_user_session(user_id: int) -> tuple[str, str]:
    return create_session(user_id)


def delete_user_session(session_token: str) -> None:
    delete_session(session_token)


def create_reset_token(user_id: int) -> tuple[str, str]:
    return create_password_reset_token(user_id)


def find_reset_token(token: str) -> sqlite3.Row | None:
    return get_password_reset_token(token)


def mark_reset_token_used(token: str) -> None:
    mark_password_reset_token_used(token)


def update_password(user_id: int, password: str) -> None:
    update_user_password(user_id, password)


def delete_all_user_sessions(user_id: int) -> None:
    delete_sessions_for_user(user_id)
