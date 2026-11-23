"""Account approval and administrator rights stored in the database.

These tests run against a throwaway SQLite file so they exercise the real SQL.
"""

from __future__ import annotations

import sqlite3

import pytest

from app import db
from app.repositories import audit_repository
from app.services import auth_service, email_service


@pytest.fixture(autouse=True)
def temp_database(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    db.initialize_database()
    audit_repository.initialize_audit_storage()


@pytest.fixture
def notices(monkeypatch) -> list[tuple[list[str], str]]:
    sent: list[tuple[list[str], str]] = []
    monkeypatch.setattr(email_service, "send_new_account_notice", lambda admins, email: sent.append((admins, email)))
    return sent


@pytest.fixture
def admin() -> sqlite3.Row:
    return db.create_user("boss@example.com", "secret-password", is_admin=True)


def _events(event: str) -> list[sqlite3.Row]:
    return audit_repository.list_events({"event": event}, limit=50)


# ---------------------------------------------------------------------------
# Registering and logging in
# ---------------------------------------------------------------------------


def test_new_account_waits_for_approval(admin, notices):
    user, session_token, error = auth_service.register_user("new@example.com", "pw", "pw")

    assert error is None and session_token is None
    assert user["status"] == "pending" and not user["is_admin"]
    assert notices == [(["boss@example.com"], "new@example.com")]


def test_pending_account_cannot_log_in(notices):
    auth_service.register_user("new@example.com", "pw", "pw")

    _, token, error = auth_service.login_user("new@example.com", "pw")
    assert token is None and error == auth_service.PENDING_LOGIN_MESSAGE

    # A wrong password doesn't reveal that the account exists.
    _, _, error = auth_service.login_user("new@example.com", "wrong")
    assert error == "Invalid email or password."


def test_sessions_only_work_for_active_accounts(notices):
    user, _, _ = auth_service.register_user("new@example.com", "pw", "pw")
    token, _ = db.create_session(user["id"])

    assert db.get_user_by_session_token(token) is None
    db.approve_user(user["id"], user["id"])
    assert db.get_user_by_session_token(token)["email"] == "new@example.com"


def test_configured_admin_email_is_active_at_once(monkeypatch, notices):
    monkeypatch.setenv("ADMIN_EMAILS", "first@example.com")

    user, session_token, _ = auth_service.register_user("First@example.com", "pw", "pw")

    assert session_token is not None
    assert user["status"] == "active" and user["is_admin"]
    assert notices == []


# ---------------------------------------------------------------------------
# Approving and rejecting
# ---------------------------------------------------------------------------


def test_approve_lets_the_user_log_in(admin, notices):
    user, _, _ = auth_service.register_user("new@example.com", "pw", "pw")

    assert auth_service.approve_account(admin, user["id"]) is None
    _, token, error = auth_service.login_user("new@example.com", "pw")

    assert error is None and token
    assert db.get_user_by_id(user["id"])["approved_at"]
    assert auth_service.approve_account(admin, user["id"]) == "That account is not waiting for approval."
    assert len(_events("auth.account_approved")) == 1


def test_reject_deletes_the_request(admin, notices):
    user, _, _ = auth_service.register_user("spam@example.com", "pw", "pw")

    assert auth_service.reject_account(user["id"]) is None
    assert db.get_user_by_email("spam@example.com") is None
    assert auth_service.reject_account(admin["id"]) == "That account is not waiting for approval."
    assert db.get_user_by_id(admin["id"]) is not None


def test_pending_count(admin, notices):
    auth_service.register_user("a@example.com", "pw", "pw")
    auth_service.register_user("b@example.com", "pw", "pw")
    assert auth_service.pending_account_count() == 2


# ---------------------------------------------------------------------------
# Administrator rights
# ---------------------------------------------------------------------------


def test_give_and_remove_admin_rights(admin):
    user = db.create_user("helper@example.com", "pw")

    assert auth_service.set_admin_rights(admin, user["id"], True) is None
    assert auth_service.is_admin("HELPER@example.com")
    assert auth_service.set_admin_rights(admin, user["id"], False) is None
    assert not auth_service.is_admin("helper@example.com")
    assert [len(_events(e)) for e in ("auth.admin_granted", "auth.admin_revoked")] == [1, 1]


def test_cannot_change_own_rights(admin):
    assert "your own" in auth_service.set_admin_rights(admin, admin["id"], False)
    assert auth_service.is_admin(admin["email"])


def test_last_admin_cannot_be_removed(admin):
    with pytest.raises(ValueError):
        db.set_user_admin(admin["id"], False)


def test_pending_accounts_cannot_be_made_admin(admin, notices):
    user, _, _ = auth_service.register_user("new@example.com", "pw", "pw")
    assert auth_service.set_admin_rights(admin, user["id"], True) == "That account does not exist or is not active."


def test_admin_rights_need_an_active_account():
    db.create_user("odd@example.com", "pw", status="pending", is_admin=True)
    assert not auth_service.is_admin("odd@example.com")


def test_configured_admins_are_restored_at_startup(monkeypatch, admin):
    user = db.create_user("ops@example.com", "pw", status="pending")
    monkeypatch.setenv("ADMIN_EMAILS", "ops@example.com")

    db.ensure_configured_admins()

    restored = db.get_user_by_id(user["id"])
    assert (restored["status"], restored["is_admin"]) == ("active", 1)


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


def test_existing_users_stay_active(tmp_path, monkeypatch):
    legacy_path = tmp_path / "legacy.db"
    monkeypatch.setenv("DATABASE_PATH", str(legacy_path))
    connection = sqlite3.connect(legacy_path)
    connection.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO users (email, password_hash) VALUES ('old@example.com', 'x'), ('admin@example.com', 'x');
        """
    )
    connection.close()

    db.initialize_database()
    db.ensure_configured_admins()  # development: admin@example.com

    users = {row["email"]: row for row in db.list_users()}
    assert users["old@example.com"]["status"] == "active" and not users["old@example.com"]["is_admin"]
    assert users["admin@example.com"]["is_admin"] == 1
