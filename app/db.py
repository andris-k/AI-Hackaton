from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import uuid
from typing import Any
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
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS fixed_asset_categories (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE CHECK (length(name) <= 100)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_fixed_asset_categories_name ON fixed_asset_categories(name)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS fixed_assets (
                id TEXT PRIMARY KEY,
                category_id TEXT NOT NULL,
                name TEXT NOT NULL CHECK (length(name) <= 100),
                category TEXT NOT NULL CHECK (length(category) <= 100),
                initial_value REAL NOT NULL,
                responsible_person TEXT NOT NULL CHECK (length(responsible_person) <= 100),
                registration_date TEXT NOT NULL,
                FOREIGN KEY (category_id) REFERENCES fixed_asset_categories(id)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_fixed_assets_name ON fixed_assets(name)"
        )

        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(fixed_assets)").fetchall()
        }
        if "category_id" not in columns:
            connection.execute("ALTER TABLE fixed_assets ADD COLUMN category_id TEXT")

        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_fixed_assets_category_id ON fixed_assets(category_id)"
        )

        distinct_categories = connection.execute(
            """
            SELECT DISTINCT category
            FROM fixed_assets
            WHERE category IS NOT NULL AND trim(category) <> ''
            """
        ).fetchall()
        for row in distinct_categories:
            category_name = row["category"]
            category_id = _get_or_create_fixed_asset_category_id(connection, category_name)
            connection.execute(
                """
                UPDATE fixed_assets
                SET category_id = ?
                WHERE (category_id IS NULL OR trim(category_id) = '')
                  AND lower(category) = lower(?)
                """,
                (category_id, category_name),
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


def list_users(email_filter: str | None = None) -> list[sqlite3.Row]:
    with db_session() as connection:
        if email_filter:
            cursor = connection.execute(
                """
                SELECT id, email, created_at
                FROM users
                WHERE lower(email) LIKE lower(?)
                ORDER BY email ASC
                """,
                (f"%{email_filter}%",),
            )
        else:
            cursor = connection.execute(
                "SELECT id, email, created_at FROM users ORDER BY email ASC"
            )
        return cursor.fetchall()


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


def _get_or_create_fixed_asset_category_id(connection: sqlite3.Connection, category_name: str) -> str:
    normalized_name = category_name.strip()
    cursor = connection.execute(
        "SELECT id FROM fixed_asset_categories WHERE lower(name) = lower(?)",
        (normalized_name,),
    )
    row = cursor.fetchone()
    if row is not None:
        return row["id"]

    category_id = str(uuid.uuid4())
    connection.execute(
        "INSERT INTO fixed_asset_categories (id, name) VALUES (?, ?)",
        (category_id, normalized_name),
    )
    return category_id


def list_fixed_asset_categories() -> list[sqlite3.Row]:
    with db_session() as connection:
        cursor = connection.execute(
            "SELECT id, name FROM fixed_asset_categories ORDER BY name ASC"
        )
        return cursor.fetchall()


def list_fixed_asset_categories_with_usage() -> list[sqlite3.Row]:
    with db_session() as connection:
        cursor = connection.execute(
            """
            SELECT
                fixed_asset_categories.id,
                fixed_asset_categories.name,
                COUNT(fixed_assets.id) AS assets_count
            FROM fixed_asset_categories
            LEFT JOIN fixed_assets ON fixed_assets.category_id = fixed_asset_categories.id
            GROUP BY fixed_asset_categories.id, fixed_asset_categories.name
            ORDER BY fixed_asset_categories.name ASC
            """
        )
        return cursor.fetchall()


def get_fixed_asset_category_by_id(category_id: str) -> sqlite3.Row | None:
    with db_session() as connection:
        cursor = connection.execute(
            "SELECT id, name FROM fixed_asset_categories WHERE id = ?",
            (category_id,),
        )
        return cursor.fetchone()


def create_fixed_asset_category(name: str) -> sqlite3.Row:
    normalized_name = name.strip()
    with db_session() as connection:
        category_id = _get_or_create_fixed_asset_category_id(connection, normalized_name)
        cursor = connection.execute(
            "SELECT id, name FROM fixed_asset_categories WHERE id = ?",
            (category_id,),
        )
        return cursor.fetchone()


def update_fixed_asset_category(category_id: str, name: str) -> sqlite3.Row | None:
    normalized_name = name.strip()
    with db_session() as connection:
        existing = connection.execute(
            "SELECT id, name FROM fixed_asset_categories WHERE id = ?",
            (category_id,),
        ).fetchone()
        if existing is None:
            return None

        conflict = connection.execute(
            "SELECT id FROM fixed_asset_categories WHERE lower(name) = lower(?) AND id <> ?",
            (normalized_name, category_id),
        ).fetchone()
        if conflict is not None:
            raise ValueError("Category name already exists.")

        connection.execute(
            "UPDATE fixed_asset_categories SET name = ? WHERE id = ?",
            (normalized_name, category_id),
        )
        connection.execute(
            "UPDATE fixed_assets SET category = ? WHERE category_id = ?",
            (normalized_name, category_id),
        )
        cursor = connection.execute(
            "SELECT id, name FROM fixed_asset_categories WHERE id = ?",
            (category_id,),
        )
        return cursor.fetchone()


def delete_fixed_asset_category(category_id: str) -> bool:
    with db_session() as connection:
        usage = connection.execute(
            "SELECT COUNT(1) AS total FROM fixed_assets WHERE category_id = ?",
            (category_id,),
        ).fetchone()
        if usage and int(usage["total"]) > 0:
            return False

        connection.execute("DELETE FROM fixed_asset_categories WHERE id = ?", (category_id,))
        return True


def create_fixed_asset(
    name: str,
    category_id: str,
    initial_value: float,
    responsible_person: str,
    registration_date: str,
) -> sqlite3.Row:
    fixed_asset_id = str(uuid.uuid4())
    with db_session() as connection:
        category = connection.execute(
            "SELECT name FROM fixed_asset_categories WHERE id = ?",
            (category_id,),
        ).fetchone()
        if category is None:
            raise ValueError("Category not found.")

        connection.execute(
            """
            INSERT INTO fixed_assets (
                id,
                category_id,
                name,
                category,
                initial_value,
                responsible_person,
                registration_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fixed_asset_id,
                category_id,
                name,
                category["name"],
                initial_value,
                responsible_person,
                registration_date,
            ),
        )
        cursor = connection.execute(
            """
            SELECT
                fixed_assets.id,
                fixed_assets.name,
                COALESCE(fixed_asset_categories.name, fixed_assets.category) AS category,
                fixed_assets.initial_value,
                fixed_assets.responsible_person,
                fixed_assets.registration_date,
                fixed_assets.category_id
            FROM fixed_assets
            LEFT JOIN fixed_asset_categories ON fixed_asset_categories.id = fixed_assets.category_id
            WHERE fixed_assets.id = ?
            """,
            (fixed_asset_id,),
        )
        return cursor.fetchone()


def get_fixed_asset_by_id(fixed_asset_id: str) -> sqlite3.Row | None:
    with db_session() as connection:
        cursor = connection.execute(
            """
            SELECT
                fixed_assets.id,
                fixed_assets.name,
                COALESCE(fixed_asset_categories.name, fixed_assets.category) AS category,
                fixed_assets.initial_value,
                fixed_assets.responsible_person,
                fixed_assets.registration_date,
                fixed_assets.category_id
            FROM fixed_assets
            LEFT JOIN fixed_asset_categories ON fixed_asset_categories.id = fixed_assets.category_id
            WHERE fixed_assets.id = ?
            """,
            (fixed_asset_id,),
        )
        return cursor.fetchone()


def update_fixed_asset(
    fixed_asset_id: str,
    name: str,
    category_id: str,
    initial_value: float,
    responsible_person: str,
    registration_date: str,
) -> sqlite3.Row | None:
    with db_session() as connection:
        category = connection.execute(
            "SELECT name FROM fixed_asset_categories WHERE id = ?",
            (category_id,),
        ).fetchone()
        if category is None:
            raise ValueError("Category not found.")

        connection.execute(
            """
            UPDATE fixed_assets
            SET
                name = ?,
                category_id = ?,
                category = ?,
                initial_value = ?,
                responsible_person = ?,
                registration_date = ?
            WHERE id = ?
            """,
            (
                name,
                category_id,
                category["name"],
                initial_value,
                responsible_person,
                registration_date,
                fixed_asset_id,
            ),
        )
        cursor = connection.execute(
            """
            SELECT
                fixed_assets.id,
                fixed_assets.name,
                COALESCE(fixed_asset_categories.name, fixed_assets.category) AS category,
                fixed_assets.initial_value,
                fixed_assets.responsible_person,
                fixed_assets.registration_date,
                fixed_assets.category_id
            FROM fixed_assets
            LEFT JOIN fixed_asset_categories ON fixed_asset_categories.id = fixed_assets.category_id
            WHERE fixed_assets.id = ?
            """,
            (fixed_asset_id,),
        )
        return cursor.fetchone()


def _fixed_assets_filter_clause(filters: dict[str, str] | None = None) -> tuple[str, list[Any]]:
    if not filters:
        return "", []

    conditions: list[str] = []
    params: list[Any] = []

    if filters.get("name"):
        conditions.append("lower(fixed_assets.name) LIKE lower(?)")
        params.append(f"%{filters['name']}%")

    if filters.get("category"):
        conditions.append("lower(COALESCE(fixed_asset_categories.name, fixed_assets.category)) LIKE lower(?)")
        params.append(f"%{filters['category']}%")

    if filters.get("responsible_person"):
        conditions.append("lower(fixed_assets.responsible_person) LIKE lower(?)")
        params.append(f"%{filters['responsible_person']}%")

    if filters.get("initial_value"):
        conditions.append("abs(fixed_assets.initial_value - ?) < 0.000001")
        params.append(float(filters["initial_value"]))

    if filters.get("registration_date_from"):
        conditions.append("fixed_assets.registration_date >= ?")
        params.append(filters["registration_date_from"])

    if filters.get("registration_date_to"):
        conditions.append("fixed_assets.registration_date <= ?")
        params.append(filters["registration_date_to"])

    if not conditions:
        return "", params

    return " WHERE " + " AND ".join(conditions), params


def count_fixed_assets(filters: dict[str, str] | None = None) -> int:
    where_clause, params = _fixed_assets_filter_clause(filters)
    with db_session() as connection:
        cursor = connection.execute(
            f"""
            SELECT COUNT(1) AS total
            FROM fixed_assets
            LEFT JOIN fixed_asset_categories ON fixed_asset_categories.id = fixed_assets.category_id
            {where_clause}
            """,
            params,
        )
        row = cursor.fetchone()
        return int(row["total"]) if row else 0


def list_fixed_assets(
    page: int | None = None,
    page_size: int | None = None,
    filters: dict[str, str] | None = None,
) -> list[sqlite3.Row]:
    where_clause, params = _fixed_assets_filter_clause(filters)
    with db_session() as connection:
        if page is None or page_size is None:
            cursor = connection.execute(
                f"""
                SELECT
                    fixed_assets.id,
                    fixed_assets.name,
                    COALESCE(fixed_asset_categories.name, fixed_assets.category) AS category,
                    fixed_assets.initial_value,
                    fixed_assets.responsible_person,
                    fixed_assets.registration_date,
                    fixed_assets.category_id
                FROM fixed_assets
                LEFT JOIN fixed_asset_categories ON fixed_asset_categories.id = fixed_assets.category_id
                {where_clause}
                ORDER BY fixed_assets.registration_date DESC, fixed_assets.name ASC
                """,
                params,
            )
            return cursor.fetchall()

        offset = max(page - 1, 0) * page_size
        paged_params = [*params, page_size, offset]
        cursor = connection.execute(
            f"""
            SELECT
                fixed_assets.id,
                fixed_assets.name,
                COALESCE(fixed_asset_categories.name, fixed_assets.category) AS category,
                fixed_assets.initial_value,
                fixed_assets.responsible_person,
                fixed_assets.registration_date,
                fixed_assets.category_id
            FROM fixed_assets
            LEFT JOIN fixed_asset_categories ON fixed_asset_categories.id = fixed_assets.category_id
            {where_clause}
            ORDER BY fixed_assets.registration_date DESC, fixed_assets.name ASC
            LIMIT ? OFFSET ?
            """,
            paged_params,
        )
        return cursor.fetchall()