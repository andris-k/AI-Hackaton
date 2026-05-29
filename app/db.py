from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATABASE_PATH = Path(__file__).resolve().parent.parent / "app.db"
PASSWORD_ITERATIONS = 210000
SESSION_DURATION_HOURS = 24


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def db_session() -> sqlite3.Connection:
    connection = get_connection()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> None:
    with db_session() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                expires_at TEXT NOT NULL,
                used_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_token ON password_reset_tokens(token)"
        )


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt_bytes = salt or secrets.token_bytes(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_bytes,
        PASSWORD_ITERATIONS,
    )
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt_bytes.hex()}${password_hash.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_hex, hash_hex = stored_hash.split("$")
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    derived_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        int(iterations_text),
    )
    return hmac.compare_digest(derived_hash.hex(), hash_hex)


def ensure_default_user() -> None:
    default_email = "admin@example.com"
    default_password = "password123"

    with db_session() as connection:
        cursor = connection.execute(
            "SELECT id FROM users WHERE email = ?",
            (default_email,),
        )
        if cursor.fetchone() is None:
            connection.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                (default_email, hash_password(default_password)),
            )


def create_user(email: str, password: str) -> sqlite3.Row:
    with db_session() as connection:
        cursor = connection.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            (email, hash_password(password)),
        )
        user_id = cursor.lastrowid
        user_cursor = connection.execute(
            "SELECT id, email, password_hash, created_at FROM users WHERE id = ?",
            (user_id,),
        )
        return user_cursor.fetchone()


def get_user_by_email(email: str) -> sqlite3.Row | None:
    with db_session() as connection:
        cursor = connection.execute(
            "SELECT id, email, password_hash, created_at FROM users WHERE email = ?",
            (email,),
        )
        return cursor.fetchone()


def get_user_by_id(user_id: int) -> sqlite3.Row | None:
    with db_session() as connection:
        cursor = connection.execute(
            "SELECT id, email, password_hash, created_at FROM users WHERE id = ?",
            (user_id,),
        )
        return cursor.fetchone()


def update_user_password(user_id: int, password: str) -> None:
    with db_session() as connection:
        connection.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(password), user_id),
        )


def create_session(user_id: int) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=SESSION_DURATION_HOURS)
    expires_at_text = expires_at.isoformat()

    with db_session() as connection:
        connection.execute(
            "INSERT INTO sessions (user_id, token, expires_at) VALUES (?, ?, ?)",
            (user_id, token, expires_at_text),
        )

    return token, expires_at_text


def get_session(token: str) -> sqlite3.Row | None:
    now_text = datetime.now(timezone.utc).isoformat()
    with db_session() as connection:
        cursor = connection.execute(
            """
            SELECT sessions.id, sessions.user_id, sessions.token, sessions.created_at, sessions.expires_at, users.email
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token = ? AND sessions.expires_at > ?
            """,
            (token, now_text),
        )
        return cursor.fetchone()


def get_user_by_session_token(token: str) -> sqlite3.Row | None:
    session = get_session(token)
    if session is None:
        return None

    return get_user_by_id(session["user_id"])


def delete_session(token: str) -> None:
    with db_session() as connection:
        connection.execute("DELETE FROM sessions WHERE token = ?", (token,))


def delete_sessions_for_user(user_id: int) -> None:
    with db_session() as connection:
        connection.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


def create_password_reset_token(user_id: int) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    expires_at_text = expires_at.isoformat()

    with db_session() as connection:
        connection.execute(
            """
            INSERT INTO password_reset_tokens (user_id, token, expires_at)
            VALUES (?, ?, ?)
            """,
            (user_id, token, expires_at_text),
        )

    return token, expires_at_text


def get_password_reset_token(token: str) -> sqlite3.Row | None:
    now_text = datetime.now(timezone.utc).isoformat()
    with db_session() as connection:
        cursor = connection.execute(
            """
            SELECT id, user_id, token, created_at, expires_at, used_at
            FROM password_reset_tokens
            WHERE token = ? AND expires_at > ? AND used_at IS NULL
            """,
            (token, now_text),
        )
        return cursor.fetchone()


def mark_password_reset_token_used(token: str) -> None:
    used_at = datetime.now(timezone.utc).isoformat()
    with db_session() as connection:
        connection.execute(
            "UPDATE password_reset_tokens SET used_at = ? WHERE token = ?",
            (used_at, token),
        )