from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import uuid
from typing import Any
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app import config

PASSWORD_ITERATIONS = 210000
SESSION_DURATION_HOURS = 24


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection() -> sqlite3.Connection:
    database_path = config.database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
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


# `quantity` is the counted quantity; 0 means the asset was not found.
# `expected_quantity` is the asset's quantity saved when the session starts;
# it is NULL while the session is New.
_SESSION_ASSET_LINK_COLUMNS = """
    inventory_session_id TEXT NOT NULL,
    fixed_asset_id TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity >= 0),
    expected_quantity INTEGER CHECK (expected_quantity >= 0),
    PRIMARY KEY (inventory_session_id, fixed_asset_id),
    FOREIGN KEY (inventory_session_id) REFERENCES inventory_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (fixed_asset_id) REFERENCES fixed_assets(id) ON DELETE CASCADE
"""


def initialize_database() -> None:
    with db_session() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('pending', 'active')),
                is_admin INTEGER NOT NULL DEFAULT 0 CHECK (is_admin IN (0, 1)),
                approved_at TEXT,
                approved_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL
            )
            """
        )
        # Accounts that existed before approval was introduced stay active.
        user_columns = {row["name"] for row in connection.execute("PRAGMA table_info(users)").fetchall()}
        for column_name, column_definition in (
            ("status", "TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('pending', 'active'))"),
            ("is_admin", "INTEGER NOT NULL DEFAULT 0 CHECK (is_admin IN (0, 1))"),
            ("approved_at", "TEXT"),
            ("approved_by_user_id", "INTEGER REFERENCES users(id) ON DELETE SET NULL"),
        ):
            if column_name not in user_columns:
                connection.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_definition}")
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
                name TEXT NOT NULL CHECK (length(name) <= 100),
                deleted_at TEXT
            )
            """
        )
        _migrate_fixed_asset_categories_for_soft_delete(connection)
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_fixed_asset_categories_name ON fixed_asset_categories(name)"
        )
        # Names only need to be unique among categories that are not deleted, so a
        # deleted category's name can be reused.
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_fixed_asset_categories_active_name
            ON fixed_asset_categories(lower(name))
            WHERE deleted_at IS NULL
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS locations (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL CHECK (length(name) <= 100),
                deleted_at TEXT
            )
            """
        )
        # Like categories, names are unique (ignoring case) among locations that
        # are not deleted.
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_locations_active_name
            ON locations(lower(name))
            WHERE deleted_at IS NULL
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS fixed_assets (
                id TEXT PRIMARY KEY,
                category_id TEXT NOT NULL,
                name TEXT NOT NULL CHECK (length(name) <= 100),
                category TEXT NOT NULL CHECK (length(category) <= 100),
                quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity >= 0),
                initial_value REAL NOT NULL,
                responsible_person TEXT NOT NULL CHECK (length(responsible_person) <= 100),
                registration_date TEXT NOT NULL,
                image_path TEXT,
                deleted_at TEXT,
                location_id TEXT REFERENCES locations(id),
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
        if "quantity" not in columns:
            connection.execute(
                "ALTER TABLE fixed_assets ADD COLUMN quantity INTEGER NOT NULL DEFAULT 1"
            )
        if "image_path" not in columns:
            connection.execute("ALTER TABLE fixed_assets ADD COLUMN image_path TEXT")
        if "deleted_at" not in columns:
            connection.execute("ALTER TABLE fixed_assets ADD COLUMN deleted_at TEXT")
        if "location_id" not in columns:
            connection.execute(
                "ALTER TABLE fixed_assets ADD COLUMN location_id TEXT REFERENCES locations(id)"
            )

        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_fixed_assets_category_id ON fixed_assets(category_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_fixed_assets_deleted_at ON fixed_assets(deleted_at)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_fixed_assets_location_id ON fixed_assets(location_id)"
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS inventory_sessions (
                id TEXT PRIMARY KEY,
                date_from TEXT NOT NULL,
                date_to TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('New', 'Active', 'Completed', 'Cancelled')),
                responsible_person TEXT NOT NULL CHECK (length(responsible_person) <= 100),
                notes TEXT,
                completion_reason TEXT,
                cancellation_reason TEXT,
                started_at TEXT,
                completed_at TEXT,
                cancelled_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_edited_at TEXT,
                created_by_user_id INTEGER,
                started_by_user_id INTEGER,
                completed_by_user_id INTEGER,
                cancelled_by_user_id INTEGER,
                last_edited_by_user_id INTEGER,
                location_id TEXT REFERENCES locations(id),
                FOREIGN KEY (created_by_user_id) REFERENCES users(id),
                FOREIGN KEY (started_by_user_id) REFERENCES users(id),
                FOREIGN KEY (completed_by_user_id) REFERENCES users(id),
                FOREIGN KEY (cancelled_by_user_id) REFERENCES users(id),
                FOREIGN KEY (last_edited_by_user_id) REFERENCES users(id)
            )
            """
        )
        inventory_session_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(inventory_sessions)").fetchall()
        }
        migration_columns: dict[str, str] = {
            "notes": "TEXT",
            "completion_reason": "TEXT",
            "cancellation_reason": "TEXT",
            "started_at": "TEXT",
            "completed_at": "TEXT",
            "cancelled_at": "TEXT",
            "created_at": "TEXT",
            "updated_at": "TEXT",
            "last_edited_at": "TEXT",
            "created_by_user_id": "INTEGER",
            "started_by_user_id": "INTEGER",
            "completed_by_user_id": "INTEGER",
            "cancelled_by_user_id": "INTEGER",
            "last_edited_by_user_id": "INTEGER",
            "location_id": "TEXT REFERENCES locations(id)",
        }
        for column_name, column_type in migration_columns.items():
            if column_name in inventory_session_columns:
                continue
            connection.execute(
                f"ALTER TABLE inventory_sessions ADD COLUMN {column_name} {column_type}"
            )
        connection.execute(
            """
            UPDATE inventory_sessions
            SET created_at = COALESCE(created_at, CURRENT_TIMESTAMP),
                updated_at = COALESCE(updated_at, CURRENT_TIMESTAMP),
                last_edited_at = COALESCE(last_edited_at, CURRENT_TIMESTAMP)
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_inventory_sessions_status ON inventory_sessions(status)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_inventory_sessions_date_from ON inventory_sessions(date_from)"
        )
        connection.execute(
            f"CREATE TABLE IF NOT EXISTS inventory_session_fixed_assets ({_SESSION_ASSET_LINK_COLUMNS})"
        )
        _migrate_inventory_session_fixed_assets_for_counts(connection)
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_inventory_session_fixed_assets_session_id ON inventory_session_fixed_assets(inventory_session_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_inventory_session_fixed_assets_asset_id ON inventory_session_fixed_assets(fixed_asset_id)"
        )
        # Created after the links table's own migration above: rebuilding a
        # parent table would cascade-delete these rows.
        _create_session_location_tables(connection)

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


def _migrate_fixed_asset_categories_for_soft_delete(connection: sqlite3.Connection) -> None:
    """Add ``deleted_at`` and drop the table-level UNIQUE(name) constraint.

    Older databases declared ``name`` as UNIQUE, which would stop a deleted
    category's name from being reused. SQLite cannot drop a constraint in place,
    so the table is rebuilt; uniqueness is then enforced by a partial index that
    only covers categories that are not deleted.
    """
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(fixed_asset_categories)").fetchall()
    }
    has_unique_name = any(
        row["origin"] == "u"
        for row in connection.execute("PRAGMA index_list(fixed_asset_categories)").fetchall()
    )
    if not has_unique_name:
        if "deleted_at" not in columns:
            connection.execute("ALTER TABLE fixed_asset_categories ADD COLUMN deleted_at TEXT")
        return

    deleted_at_source = "deleted_at" if "deleted_at" in columns else "NULL"
    # PRAGMA foreign_keys cannot change inside a transaction, and dropping the
    # parent table with foreign keys on would fail, so commit and turn them off.
    connection.commit()
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.execute("BEGIN")
        connection.execute(
            """
            CREATE TABLE fixed_asset_categories_new (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL CHECK (length(name) <= 100),
                deleted_at TEXT
            )
            """
        )
        connection.execute(
            f"""
            INSERT INTO fixed_asset_categories_new (id, name, deleted_at)
            SELECT id, name, {deleted_at_source} FROM fixed_asset_categories
            """
        )
        connection.execute("DROP TABLE fixed_asset_categories")
        connection.execute(
            "ALTER TABLE fixed_asset_categories_new RENAME TO fixed_asset_categories"
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA foreign_keys = ON")


def _create_session_location_tables(connection: sqlite3.Connection) -> None:
    """Counts per location and the history of a session's active location.

    ``inventory_session_counts`` holds what was counted of an asset at one
    location (``location_id`` NULL: counted with no active location). The
    link row in ``inventory_session_fixed_assets`` keeps the expected quantity
    and, in ``quantity``, the total of these counts, kept up to date in the
    same transaction by every write. On first creation each existing link gets
    one count at its session's location, and each session with a location gets
    that as the first entry of its history.
    """
    tables = {
        row["name"]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory_session_counts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inventory_session_id TEXT NOT NULL,
            fixed_asset_id TEXT NOT NULL,
            location_id TEXT REFERENCES locations(id),
            quantity INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
            updated_at TEXT NOT NULL,
            FOREIGN KEY (inventory_session_id, fixed_asset_id)
                REFERENCES inventory_session_fixed_assets(inventory_session_id, fixed_asset_id)
                ON DELETE CASCADE
        )
        """
    )
    # One count per asset and location; SQLite treats NULLs as distinct, so
    # "no location" needs its own index.
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_inventory_session_counts_location
        ON inventory_session_counts(inventory_session_id, fixed_asset_id, location_id)
        WHERE location_id IS NOT NULL
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_inventory_session_counts_no_location
        ON inventory_session_counts(inventory_session_id, fixed_asset_id)
        WHERE location_id IS NULL
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory_session_locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inventory_session_id TEXT NOT NULL REFERENCES inventory_sessions(id) ON DELETE CASCADE,
            location_id TEXT REFERENCES locations(id),
            activated_at TEXT NOT NULL,
            activated_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_inventory_session_locations_session ON inventory_session_locations(inventory_session_id)"
    )

    now = _utc_now_text()
    if "inventory_session_counts" not in tables:
        connection.execute(
            """
            INSERT INTO inventory_session_counts (inventory_session_id, fixed_asset_id, location_id, quantity, updated_at)
            SELECT links.inventory_session_id, links.fixed_asset_id, inventory_sessions.location_id, links.quantity, ?
            FROM inventory_session_fixed_assets AS links
            JOIN inventory_sessions ON inventory_sessions.id = links.inventory_session_id
            WHERE links.quantity > 0
            """,
            (now,),
        )
    if "inventory_session_locations" not in tables:
        connection.execute(
            """
            INSERT INTO inventory_session_locations (inventory_session_id, location_id, activated_at, activated_by_user_id)
            SELECT id, location_id, COALESCE(started_at, created_at, ?), created_by_user_id
            FROM inventory_sessions
            WHERE location_id IS NOT NULL
            """,
            (now,),
        )


def _set_count(
    connection: sqlite3.Connection,
    session_id: str,
    fixed_asset_id: str,
    location_id: str | None,
    *,
    quantity: int | None = None,
    delta: int | None = None,
) -> None:
    """Set (``quantity``) or change (``delta``) one asset's count at one location.

    The UPDATE comes first, so it takes the write lock before a missing row is
    inserted, and a second writer waits instead of inserting a duplicate.
    """
    now = _utc_now_text()
    if quantity is not None:
        cursor = connection.execute(
            """
            UPDATE inventory_session_counts SET quantity = ?, updated_at = ?
            WHERE inventory_session_id = ? AND fixed_asset_id = ? AND location_id IS ?
            """,
            (quantity, now, session_id, fixed_asset_id, location_id),
        )
        new_quantity = quantity
    else:
        cursor = connection.execute(
            """
            UPDATE inventory_session_counts SET quantity = MAX(0, quantity + ?), updated_at = ?
            WHERE inventory_session_id = ? AND fixed_asset_id = ? AND location_id IS ?
            """,
            (delta, now, session_id, fixed_asset_id, location_id),
        )
        new_quantity = max(0, int(delta or 0))
    # A missing count is the same as 0; adding a 0 row would only list an
    # empty location against the asset.
    if cursor.rowcount == 0 and new_quantity > 0:
        connection.execute(
            """
            INSERT INTO inventory_session_counts (inventory_session_id, fixed_asset_id, location_id, quantity, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, fixed_asset_id, location_id, new_quantity, now),
        )


def _update_count_totals(connection: sqlite3.Connection, session_id: str) -> None:
    """Set each link's ``quantity`` to the total of its counts."""
    connection.execute(
        """
        UPDATE inventory_session_fixed_assets
        SET quantity = (
            SELECT COALESCE(SUM(counts.quantity), 0) FROM inventory_session_counts AS counts
            WHERE counts.inventory_session_id = inventory_session_fixed_assets.inventory_session_id
              AND counts.fixed_asset_id = inventory_session_fixed_assets.fixed_asset_id
        )
        WHERE inventory_session_id = ?
        """,
        (session_id,),
    )


def _migrate_inventory_session_fixed_assets_for_counts(connection: sqlite3.Connection) -> None:
    """Add ``expected_quantity`` and allow a counted ``quantity`` of 0.

    Older databases required ``quantity > 0``, which SQLite cannot change in
    place, so the table is rebuilt. Links in sessions that were already started
    get the asset's current quantity as their expected quantity. The quantity at
    the time they started is not known, but this stops later edits to the asset
    from changing their results.
    """
    columns = {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(inventory_session_fixed_assets)"
        ).fetchall()
    }
    if "expected_quantity" in columns:
        return

    quantity_source = "links.quantity" if "quantity" in columns else "1"
    connection.execute(
        f"CREATE TABLE inventory_session_fixed_assets_new ({_SESSION_ASSET_LINK_COLUMNS})"
    )
    connection.execute(
        f"""
        INSERT INTO inventory_session_fixed_assets_new (
            inventory_session_id, fixed_asset_id, quantity, expected_quantity
        )
        SELECT
            links.inventory_session_id,
            links.fixed_asset_id,
            {quantity_source},
            CASE WHEN inventory_sessions.status = 'New' THEN NULL ELSE fixed_assets.quantity END
        FROM inventory_session_fixed_assets AS links
        LEFT JOIN inventory_sessions ON inventory_sessions.id = links.inventory_session_id
        LEFT JOIN fixed_assets ON fixed_assets.id = links.fixed_asset_id
        """
    )
    connection.execute("DROP TABLE inventory_session_fixed_assets")
    connection.execute(
        "ALTER TABLE inventory_session_fixed_assets_new RENAME TO inventory_session_fixed_assets"
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
    """Create the bootstrap admin account (see config.bootstrap_admin) if it is missing.

    In production, refuse to start while the demo account still has the demo password,
    e.g. when a development database was copied to the server.
    """
    if config.is_production():
        with db_session() as connection:
            row = connection.execute(
                "SELECT password_hash FROM users WHERE email = ?",
                (config.DEV_ADMIN_EMAIL,),
            ).fetchone()
        if row is not None and verify_password(config.DEV_ADMIN_PASSWORD, row["password_hash"]):
            raise RuntimeError(
                f"The demo account {config.DEV_ADMIN_EMAIL} still uses the demo password. "
                "Delete that user or change its password before running with APP_ENV=production."
            )

    account = config.bootstrap_admin()
    if account is None:
        return
    email, password = account

    with db_session() as connection:
        cursor = connection.execute(
            "SELECT id FROM users WHERE email = ?",
            (email,),
        )
        if cursor.fetchone() is None:
            connection.execute(
                "INSERT INTO users (email, password_hash, is_admin) VALUES (?, ?, 1)",
                (email, hash_password(password)),
            )


def ensure_configured_admins() -> None:
    """Make the accounts named in ADMIN_EMAIL / ADMIN_EMAILS active admins.

    Runs at every startup, so a configured admin can always get in, even after
    being removed as admin on the Users page.
    """
    emails = sorted(config.admin_emails())
    if not emails:
        return
    placeholders = ", ".join("?" for _ in emails)
    with db_session() as connection:
        connection.execute(
            f"""
            UPDATE users
            SET is_admin = 1,
                status = 'active',
                approved_at = COALESCE(approved_at, ?)
            WHERE lower(email) IN ({placeholders})
            """,
            (_utc_now_text(), *emails),
        )


_USER_COLUMNS = "id, email, password_hash, created_at, status, is_admin, approved_at"


def create_user(email: str, password: str, *, status: str = "active", is_admin: bool = False) -> sqlite3.Row:
    with db_session() as connection:
        cursor = connection.execute(
            "INSERT INTO users (email, password_hash, status, is_admin) VALUES (?, ?, ?, ?)",
            (email, hash_password(password), status, int(is_admin)),
        )
        user_id = cursor.lastrowid
        user_cursor = connection.execute(
            f"SELECT {_USER_COLUMNS} FROM users WHERE id = ?",
            (user_id,),
        )
        return user_cursor.fetchone()


def get_user_by_email(email: str) -> sqlite3.Row | None:
    with db_session() as connection:
        cursor = connection.execute(
            f"SELECT {_USER_COLUMNS} FROM users WHERE email = ?",
            (email,),
        )
        return cursor.fetchone()


def get_user_by_id(user_id: int) -> sqlite3.Row | None:
    with db_session() as connection:
        cursor = connection.execute(
            f"SELECT {_USER_COLUMNS} FROM users WHERE id = ?",
            (user_id,),
        )
        return cursor.fetchone()


def list_users(email_filter: str | None = None) -> list[sqlite3.Row]:
    with db_session() as connection:
        if email_filter:
            cursor = connection.execute(
                """
                SELECT id, email, created_at, status, is_admin, approved_at
                FROM users
                WHERE lower(email) LIKE lower(?)
                ORDER BY email ASC
                """,
                (f"%{email_filter}%",),
            )
        else:
            cursor = connection.execute(
                "SELECT id, email, created_at, status, is_admin, approved_at FROM users ORDER BY email ASC"
            )
        return cursor.fetchall()


def is_admin_email(email: str | None) -> bool:
    if not email:
        return False
    with db_session() as connection:
        row = connection.execute(
            "SELECT 1 FROM users WHERE lower(email) = lower(?) AND is_admin = 1 AND status = 'active'",
            (email.strip(),),
        ).fetchone()
        return row is not None


def list_admin_emails() -> list[str]:
    with db_session() as connection:
        rows = connection.execute(
            "SELECT email FROM users WHERE is_admin = 1 AND status = 'active' ORDER BY email"
        ).fetchall()
        return [str(row["email"]) for row in rows]


def count_pending_users() -> int:
    with db_session() as connection:
        return int(connection.execute("SELECT COUNT(*) FROM users WHERE status = 'pending'").fetchone()[0])


def approve_user(user_id: int, approved_by_user_id: int) -> bool:
    """Activate a pending account. Returns False if it is not pending."""
    with db_session() as connection:
        cursor = connection.execute(
            """
            UPDATE users
            SET status = 'active', approved_at = ?, approved_by_user_id = ?
            WHERE id = ? AND status = 'pending'
            """,
            (_utc_now_text(), approved_by_user_id, user_id),
        )
        return cursor.rowcount > 0


def delete_pending_user(user_id: int) -> sqlite3.Row | None:
    """Delete a pending account (rejecting it). Returns the deleted user, or
    None if there is no pending account with that id."""
    with db_session() as connection:
        user = connection.execute(
            f"SELECT {_USER_COLUMNS} FROM users WHERE id = ? AND status = 'pending'",
            (user_id,),
        ).fetchone()
        if user is None:
            return None
        connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return user


def set_user_admin(user_id: int, is_admin: bool) -> bool:
    """Give or remove admin rights on an active account. Returns False if there
    is no such account. Raises ValueError rather than remove the last admin."""
    with db_session() as connection:
        user = connection.execute(
            "SELECT is_admin FROM users WHERE id = ? AND status = 'active'",
            (user_id,),
        ).fetchone()
        if user is None:
            return False
        if not is_admin and user["is_admin"]:
            admins = connection.execute(
                "SELECT COUNT(*) FROM users WHERE is_admin = 1 AND status = 'active'"
            ).fetchone()[0]
            if admins <= 1:
                raise ValueError("There must be at least one administrator.")
        connection.execute("UPDATE users SET is_admin = ? WHERE id = ?", (int(is_admin), user_id))
        return True


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
            WHERE sessions.token = ? AND sessions.expires_at > ? AND users.status = 'active'
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
        "SELECT id FROM fixed_asset_categories WHERE lower(name) = lower(?) AND deleted_at IS NULL",
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
            "SELECT id, name FROM fixed_asset_categories WHERE deleted_at IS NULL ORDER BY name ASC"
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
            LEFT JOIN fixed_assets
                ON fixed_assets.category_id = fixed_asset_categories.id
               AND fixed_assets.deleted_at IS NULL
            WHERE fixed_asset_categories.deleted_at IS NULL
            GROUP BY fixed_asset_categories.id, fixed_asset_categories.name
            ORDER BY fixed_asset_categories.name ASC
            """
        )
        return cursor.fetchall()


def get_fixed_asset_category_by_id(category_id: str) -> sqlite3.Row | None:
    with db_session() as connection:
        cursor = connection.execute(
            "SELECT id, name FROM fixed_asset_categories WHERE id = ? AND deleted_at IS NULL",
            (category_id,),
        )
        return cursor.fetchone()


def create_fixed_asset_category(name: str) -> sqlite3.Row:
    normalized_name = name.strip()
    with db_session() as connection:
        category_id = _get_or_create_fixed_asset_category_id(connection, normalized_name)
        cursor = connection.execute(
            "SELECT id, name FROM fixed_asset_categories WHERE id = ? AND deleted_at IS NULL",
            (category_id,),
        )
        return cursor.fetchone()


def update_fixed_asset_category(category_id: str, name: str) -> sqlite3.Row | None:
    normalized_name = name.strip()
    with db_session() as connection:
        existing = connection.execute(
            "SELECT id, name FROM fixed_asset_categories WHERE id = ? AND deleted_at IS NULL",
            (category_id,),
        ).fetchone()
        if existing is None:
            return None

        conflict = connection.execute(
            "SELECT id FROM fixed_asset_categories WHERE lower(name) = lower(?) AND id <> ? AND deleted_at IS NULL",
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
            "SELECT id, name FROM fixed_asset_categories WHERE id = ? AND deleted_at IS NULL",
            (category_id,),
        )
        return cursor.fetchone()


def delete_fixed_asset_category(category_id: str) -> bool:
    """Logically delete a category.

    The row is kept so that deleted fixed assets (and the inventory sessions
    they appear in) still resolve their category name. A category cannot be
    deleted while fixed assets that are not deleted still use it.
    """
    with db_session() as connection:
        usage = connection.execute(
            "SELECT COUNT(1) AS total FROM fixed_assets WHERE category_id = ? AND deleted_at IS NULL",
            (category_id,),
        ).fetchone()
        if usage and int(usage["total"]) > 0:
            return False

        cursor = connection.execute(
            "UPDATE fixed_asset_categories SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
            (_utc_now_text(), category_id),
        )
        return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------

_LOCATION_NAME_EXISTS = "Location name already exists."


def _active_location_name_taken(
    connection: sqlite3.Connection, name: str, exclude_id: str | None = None
) -> bool:
    return connection.execute(
        """
        SELECT 1 FROM locations
        WHERE lower(name) = lower(?) AND deleted_at IS NULL AND id IS NOT ?
        """,
        (name, exclude_id),
    ).fetchone() is not None


def list_locations() -> list[sqlite3.Row]:
    with db_session() as connection:
        return connection.execute(
            "SELECT id, name FROM locations WHERE deleted_at IS NULL ORDER BY name ASC"
        ).fetchall()


def list_locations_with_usage() -> list[sqlite3.Row]:
    with db_session() as connection:
        return connection.execute(
            """
            SELECT
                locations.id,
                locations.name,
                (
                    SELECT COUNT(1) FROM fixed_assets
                    WHERE fixed_assets.location_id = locations.id
                      AND fixed_assets.deleted_at IS NULL
                ) AS assets_count,
                (
                    SELECT COUNT(1) FROM inventory_sessions
                    WHERE inventory_sessions.location_id = locations.id
                ) AS sessions_count
            FROM locations
            WHERE locations.deleted_at IS NULL
            ORDER BY locations.name ASC
            """
        ).fetchall()


def get_location_by_id(location_id: str) -> sqlite3.Row | None:
    with db_session() as connection:
        return connection.execute(
            "SELECT id, name FROM locations WHERE id = ? AND deleted_at IS NULL",
            (location_id,),
        ).fetchone()


def create_location(name: str) -> sqlite3.Row:
    """Create a location. Raises ValueError if the name is already used."""
    normalized_name = name.strip()
    location_id = str(uuid.uuid4())
    with db_session() as connection:
        if _active_location_name_taken(connection, normalized_name):
            raise ValueError(_LOCATION_NAME_EXISTS)
        connection.execute(
            "INSERT INTO locations (id, name) VALUES (?, ?)",
            (location_id, normalized_name),
        )
        return connection.execute(
            "SELECT id, name FROM locations WHERE id = ?",
            (location_id,),
        ).fetchone()


def update_location(location_id: str, name: str) -> sqlite3.Row | None:
    """Rename a location. Returns None if it does not exist; raises ValueError
    if another location already uses the name."""
    normalized_name = name.strip()
    with db_session() as connection:
        existing = connection.execute(
            "SELECT id FROM locations WHERE id = ? AND deleted_at IS NULL",
            (location_id,),
        ).fetchone()
        if existing is None:
            return None
        if _active_location_name_taken(connection, normalized_name, exclude_id=location_id):
            raise ValueError(_LOCATION_NAME_EXISTS)
        connection.execute(
            "UPDATE locations SET name = ? WHERE id = ?",
            (normalized_name, location_id),
        )
        return connection.execute(
            "SELECT id, name FROM locations WHERE id = ?",
            (location_id,),
        ).fetchone()


def delete_location(location_id: str) -> bool:
    """Logically delete a location.

    The row is kept so that inventory sessions and deleted fixed assets still
    show its name. A location cannot be deleted while fixed assets that are not
    deleted are at it.
    """
    with db_session() as connection:
        in_use = connection.execute(
            "SELECT 1 FROM fixed_assets WHERE location_id = ? AND deleted_at IS NULL",
            (location_id,),
        ).fetchone()
        if in_use is not None:
            return False
        cursor = connection.execute(
            "UPDATE locations SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
            (_utc_now_text(), location_id),
        )
        return cursor.rowcount > 0


def _require_active_location(connection: sqlite3.Connection, location_id: str | None) -> None:
    if location_id is None:
        return
    found = connection.execute(
        "SELECT 1 FROM locations WHERE id = ? AND deleted_at IS NULL",
        (location_id,),
    ).fetchone()
    if found is None:
        raise ValueError("Location not found.")


def create_fixed_asset(
    name: str,
    category_id: str,
    quantity: int,
    initial_value: float,
    responsible_person: str,
    registration_date: str,
    image_path: str | None = None,
    location_id: str | None = None,
) -> sqlite3.Row:
    fixed_asset_id = str(uuid.uuid4())
    with db_session() as connection:
        _require_active_location(connection, location_id)
        category = connection.execute(
            "SELECT name FROM fixed_asset_categories WHERE id = ? AND deleted_at IS NULL",
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
                quantity,
                initial_value,
                responsible_person,
                registration_date,
                image_path,
                location_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fixed_asset_id,
                category_id,
                name,
                category["name"],
                quantity,
                initial_value,
                responsible_person,
                registration_date,
                image_path,
                location_id,
            ),
        )
        cursor = connection.execute(
            """
            SELECT
                fixed_assets.id,
                fixed_assets.name,
                COALESCE(fixed_asset_categories.name, fixed_assets.category) AS category,
                fixed_assets.quantity,
                fixed_assets.initial_value,
                fixed_assets.responsible_person,
                fixed_assets.registration_date,
                fixed_assets.category_id,
                fixed_assets.image_path,
                fixed_assets.deleted_at,
                fixed_assets.location_id,
                locations.name AS location
            FROM fixed_assets
            LEFT JOIN fixed_asset_categories ON fixed_asset_categories.id = fixed_assets.category_id
            LEFT JOIN locations ON locations.id = fixed_assets.location_id
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
                fixed_assets.quantity,
                fixed_assets.initial_value,
                fixed_assets.responsible_person,
                fixed_assets.registration_date,
                fixed_assets.category_id,
                fixed_assets.image_path,
                fixed_assets.deleted_at,
                fixed_assets.location_id,
                locations.name AS location
            FROM fixed_assets
            LEFT JOIN fixed_asset_categories ON fixed_asset_categories.id = fixed_assets.category_id
            LEFT JOIN locations ON locations.id = fixed_assets.location_id
            WHERE fixed_assets.id = ?
            """,
            (fixed_asset_id,),
        )
        return cursor.fetchone()


def update_fixed_asset(
    fixed_asset_id: str,
    name: str,
    category_id: str,
    quantity: int,
    initial_value: float,
    responsible_person: str,
    registration_date: str,
    image_path: str | None = None,
    location_id: str | None = None,
) -> sqlite3.Row | None:
    with db_session() as connection:
        current = connection.execute(
            "SELECT location_id FROM fixed_assets WHERE id = ?",
            (fixed_asset_id,),
        ).fetchone()
        # An asset may keep a location it already has; a new one must exist.
        if current is None or current["location_id"] != location_id:
            _require_active_location(connection, location_id)
        category = connection.execute(
            "SELECT name FROM fixed_asset_categories WHERE id = ? AND deleted_at IS NULL",
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
                quantity = ?,
                initial_value = ?,
                responsible_person = ?,
                registration_date = ?,
                image_path = ?,
                location_id = ?
            WHERE id = ? AND deleted_at IS NULL
            """,
            (
                name,
                category_id,
                category["name"],
                quantity,
                initial_value,
                responsible_person,
                registration_date,
                image_path,
                location_id,
                fixed_asset_id,
            ),
        )
        cursor = connection.execute(
            """
            SELECT
                fixed_assets.id,
                fixed_assets.name,
                COALESCE(fixed_asset_categories.name, fixed_assets.category) AS category,
                fixed_assets.quantity,
                fixed_assets.initial_value,
                fixed_assets.responsible_person,
                fixed_assets.registration_date,
                fixed_assets.category_id,
                fixed_assets.image_path,
                fixed_assets.deleted_at,
                fixed_assets.location_id,
                locations.name AS location
            FROM fixed_assets
            LEFT JOIN fixed_asset_categories ON fixed_asset_categories.id = fixed_assets.category_id
            LEFT JOIN locations ON locations.id = fixed_assets.location_id
            WHERE fixed_assets.id = ?
            """,
            (fixed_asset_id,),
        )
        return cursor.fetchone()


def delete_fixed_asset(fixed_asset_id: str) -> bool:
    """Logically delete a fixed asset.

    The row is kept (with ``deleted_at`` set) so that inventory sessions that
    reference it keep their history. Deleted assets are hidden from the fixed
    assets list, reports and the asset pickers for inventory sessions.
    """
    with db_session() as connection:
        cursor = connection.execute(
            "UPDATE fixed_assets SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
            (_utc_now_text(), fixed_asset_id),
        )
        return cursor.rowcount > 0


# Location filter value that matches assets without a location.
NO_LOCATION_FILTER = "(none)"


def _filter_values(filters: dict[str, Any], key: str) -> list[str]:
    """Values of a multi-value filter, given as a list (``<key>_values``) or a
    comma-separated string (``<key>``)."""
    raw_values = filters.get(f"{key}_values")
    if isinstance(raw_values, Sequence) and not isinstance(raw_values, str):
        return [str(value).strip() for value in raw_values if str(value).strip()]
    return [value.strip() for value in str(filters.get(key) or "").split(",") if value.strip()]


def _fixed_assets_filter_clause(filters: dict[str, Any] | None = None) -> tuple[str, list[Any]]:
    conditions: list[str] = ["fixed_assets.deleted_at IS NULL"]
    params: list[Any] = []
    filters = filters or {}

    if filters.get("name"):
        conditions.append("lower(fixed_assets.name) LIKE lower(?)")
        params.append(f"%{filters['name']}%")

    raw_category_values = filters.get("category_values")
    category_values: list[str] = []
    if isinstance(raw_category_values, Sequence) and not isinstance(raw_category_values, str):
        category_values = [str(value).strip() for value in raw_category_values if str(value).strip()]
    elif filters.get("category"):
        category_values = [
            value.strip()
            for value in str(filters["category"]).split(",")
            if value.strip()
        ]

    if category_values:
        placeholders = ", ".join("lower(?)" for _ in category_values)
        conditions.append(
            f"lower(COALESCE(fixed_asset_categories.name, fixed_assets.category)) IN ({placeholders})"
        )
        params.extend(category_values)

    location_values = _filter_values(filters, "location")
    if location_values:
        location_names = [value for value in location_values if value != NO_LOCATION_FILTER]
        location_conditions: list[str] = []
        if location_names:
            placeholders = ", ".join("lower(?)" for _ in location_names)
            location_conditions.append(f"lower(locations.name) IN ({placeholders})")
            params.extend(location_names)
        if NO_LOCATION_FILTER in location_values:
            location_conditions.append("fixed_assets.location_id IS NULL")
        conditions.append("(" + " OR ".join(location_conditions) + ")")

    if filters.get("location_id"):
        conditions.append("fixed_assets.location_id = ?")
        params.append(filters["location_id"])

    if filters.get("responsible_person"):
        conditions.append("lower(fixed_assets.responsible_person) LIKE lower(?)")
        params.append(f"%{filters['responsible_person']}%")

    if filters.get("initial_value_from"):
        conditions.append("fixed_assets.initial_value >= ?")
        params.append(float(filters["initial_value_from"]))

    if filters.get("initial_value_to"):
        conditions.append("fixed_assets.initial_value <= ?")
        params.append(float(filters["initial_value_to"]))

    if filters.get("registration_date_from"):
        conditions.append("fixed_assets.registration_date >= ?")
        params.append(filters["registration_date_from"])

    if filters.get("registration_date_to"):
        conditions.append("fixed_assets.registration_date <= ?")
        params.append(filters["registration_date_to"])

    return " WHERE " + " AND ".join(conditions), params


def count_fixed_assets(filters: dict[str, Any] | None = None) -> int:
    where_clause, params = _fixed_assets_filter_clause(filters)
    with db_session() as connection:
        cursor = connection.execute(
            f"""
            SELECT COUNT(1) AS total
            FROM fixed_assets
            LEFT JOIN fixed_asset_categories ON fixed_asset_categories.id = fixed_assets.category_id
            LEFT JOIN locations ON locations.id = fixed_assets.location_id
            {where_clause}
            """,
            params,
        )
        row = cursor.fetchone()
        return int(row["total"]) if row else 0


def list_fixed_assets(
    page: int | None = None,
    page_size: int | None = None,
    filters: dict[str, Any] | None = None,
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
                    fixed_assets.quantity,
                    fixed_assets.initial_value,
                    fixed_assets.responsible_person,
                    fixed_assets.registration_date,
                    fixed_assets.category_id,
                    fixed_assets.image_path,
                    fixed_assets.deleted_at,
                    fixed_assets.location_id,
                    locations.name AS location
                FROM fixed_assets
                LEFT JOIN fixed_asset_categories ON fixed_asset_categories.id = fixed_assets.category_id
                LEFT JOIN locations ON locations.id = fixed_assets.location_id
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
                fixed_assets.quantity,
                fixed_assets.initial_value,
                fixed_assets.responsible_person,
                fixed_assets.registration_date,
                fixed_assets.category_id,
                fixed_assets.image_path,
                fixed_assets.deleted_at,
                fixed_assets.location_id,
                locations.name AS location
            FROM fixed_assets
            LEFT JOIN fixed_asset_categories ON fixed_asset_categories.id = fixed_assets.category_id
            LEFT JOIN locations ON locations.id = fixed_assets.location_id
            {where_clause}
            ORDER BY fixed_assets.registration_date DESC, fixed_assets.name ASC
            LIMIT ? OFFSET ?
            """,
            paged_params,
        )
        return cursor.fetchall()


# ---------------------------------------------------------------------------
# InventorySession CRUD
# ---------------------------------------------------------------------------

INVENTORY_SESSION_STATUSES = ("New", "Active", "Completed", "Cancelled")

# Default for update_inventory_session(location_id=...): keep the current location.
KEEP_LOCATION = object()

_INVENTORY_SESSION_SELECT = """
    SELECT id, date_from, date_to, status, responsible_person
    FROM inventory_sessions
"""


def _save_expected_quantities(connection: sqlite3.Connection, session_id: str, *, save_expected: bool) -> None:
    """With ``save_expected`` (any status but New), each link keeps the expected
    quantity it already has, and a link without one gets the asset's current
    quantity. Otherwise (New) expected quantities are cleared."""
    if save_expected:
        connection.execute(
            """
            UPDATE inventory_session_fixed_assets
            SET expected_quantity = (
                SELECT fixed_assets.quantity FROM fixed_assets
                WHERE fixed_assets.id = inventory_session_fixed_assets.fixed_asset_id
            )
            WHERE inventory_session_id = ? AND expected_quantity IS NULL
            """,
            (session_id,),
        )
    else:
        connection.execute(
            "UPDATE inventory_session_fixed_assets SET expected_quantity = NULL WHERE inventory_session_id = ?",
            (session_id,),
        )


def _set_inventory_session_fixed_assets(
    connection: sqlite3.Connection,
    session_id: str,
    linked_assets: Sequence[tuple[str, int]] | None,
    *,
    save_expected: bool,
    count_location_id: str | None = None,
) -> None:
    """Make the session's assets match ``linked_assets`` (asset id, counted quantity).

    Each quantity is the count at ``count_location_id`` (the active location);
    counts the asset has at other locations are kept. Assets left out are
    removed from the session with all their counts; new ones are added. An
    asset that is removed and added again gets a new expected quantity.
    ``linked_assets`` None leaves the assets and counts as they are.
    """
    if linked_assets is None:
        _save_expected_quantities(connection, session_id, save_expected=save_expected)
        return

    normalized_assets: list[tuple[str, int]] = []
    aggregated_quantities: dict[str, int] = {}
    for fixed_asset_id, quantity in linked_assets:
        asset_id = fixed_asset_id.strip()
        if not asset_id:
            continue
        if quantity < 0:
            continue
        aggregated_quantities[asset_id] = aggregated_quantities.get(asset_id, 0) + quantity

    for asset_id, quantity in aggregated_quantities.items():
        normalized_assets.append((asset_id, quantity))

    valid_assets: list[tuple[str, int]] = []
    if normalized_assets:
        candidate_ids = [asset_id for asset_id, _ in normalized_assets]
        placeholders = ",".join("?" for _ in candidate_ids)
        # Deleted assets cannot be newly linked, but ones already linked to this
        # session stay linked so its history is preserved.
        cursor = connection.execute(
            f"""
            SELECT id FROM fixed_assets
            WHERE id IN ({placeholders})
              AND (
                deleted_at IS NULL
                OR id IN (
                    SELECT fixed_asset_id FROM inventory_session_fixed_assets
                    WHERE inventory_session_id = ?
                )
              )
            """,
            [*candidate_ids, session_id],
        )
        valid_ids = {str(row["id"]) for row in cursor.fetchall()}
        valid_assets = [
            (asset_id, quantity)
            for asset_id, quantity in normalized_assets
            if asset_id in valid_ids
        ]

    kept_ids = [asset_id for asset_id, _ in valid_assets]
    # Removing a link removes its counts too (foreign key ON DELETE CASCADE).
    placeholders = ",".join("?" for _ in kept_ids)
    connection.execute(
        f"""
        DELETE FROM inventory_session_fixed_assets
        WHERE inventory_session_id = ?
          {f"AND fixed_asset_id NOT IN ({placeholders})" if kept_ids else ""}
        """,
        [session_id, *kept_ids],
    )
    connection.executemany(
        """
        INSERT OR IGNORE INTO inventory_session_fixed_assets (inventory_session_id, fixed_asset_id, quantity)
        VALUES (?, ?, 0)
        """,
        [(session_id, asset_id) for asset_id in kept_ids],
    )
    for asset_id, quantity in valid_assets:
        _set_count(connection, session_id, asset_id, count_location_id, quantity=quantity)
    _update_count_totals(connection, session_id)
    _save_expected_quantities(connection, session_id, save_expected=save_expected)


def list_inventory_sessions(
    status: str | None = None,
    responsible_person: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    location_id: str | None = None,
) -> list[sqlite3.Row]:
    conditions: list[str] = []
    params: list[Any] = []

    if status:
        conditions.append("inventory_sessions.status = ?")
        params.append(status)
    if location_id:
        # Sessions that have used the location, now or earlier.
        conditions.append(
            """(
                inventory_sessions.location_id = ?
                OR EXISTS (
                    SELECT 1 FROM inventory_session_locations AS history
                    WHERE history.inventory_session_id = inventory_sessions.id AND history.location_id = ?
                )
            )"""
        )
        params.extend([location_id, location_id])
    if responsible_person:
        conditions.append("lower(inventory_sessions.responsible_person) LIKE lower(?)")
        params.append(f"%{responsible_person}%")
    if date_from:
        conditions.append("inventory_sessions.date_from >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("inventory_sessions.date_to <= ?")
        params.append(date_to)

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    with db_session() as connection:
        cursor = connection.execute(
            f"""
            SELECT
                inventory_sessions.id,
                inventory_sessions.date_from,
                inventory_sessions.date_to,
                inventory_sessions.status,
                inventory_sessions.responsible_person,
                inventory_sessions.started_at,
                inventory_sessions.completed_at,
                inventory_sessions.cancelled_at,
                inventory_sessions.created_at,
                inventory_sessions.updated_at,
                inventory_sessions.notes,
                inventory_sessions.completion_reason,
                inventory_sessions.cancellation_reason,
                inventory_sessions.location_id,
                locations.name AS location,
                COUNT(inventory_session_fixed_assets.fixed_asset_id) AS linked_assets_count,
                COALESCE(SUM(inventory_session_fixed_assets.quantity), 0) AS linked_assets_quantity_total
            FROM inventory_sessions
            LEFT JOIN locations ON locations.id = inventory_sessions.location_id
            LEFT JOIN inventory_session_fixed_assets
                ON inventory_session_fixed_assets.inventory_session_id = inventory_sessions.id
            {where}
            GROUP BY
                inventory_sessions.id,
                inventory_sessions.date_from,
                inventory_sessions.date_to,
                inventory_sessions.status,
                inventory_sessions.responsible_person,
                inventory_sessions.started_at,
                inventory_sessions.completed_at,
                inventory_sessions.cancelled_at,
                inventory_sessions.created_at,
                inventory_sessions.updated_at,
                inventory_sessions.notes,
                inventory_sessions.completion_reason,
                inventory_sessions.cancellation_reason,
                inventory_sessions.location_id,
                locations.name
            ORDER BY inventory_sessions.date_from DESC, inventory_sessions.date_to DESC
            """,
            params,
        )
        return cursor.fetchall()


def get_inventory_session_by_id(session_id: str) -> sqlite3.Row | None:
    with db_session() as connection:
        cursor = connection.execute(
            """
            SELECT
                inventory_sessions.id,
                inventory_sessions.date_from,
                inventory_sessions.date_to,
                inventory_sessions.status,
                inventory_sessions.responsible_person,
                inventory_sessions.started_at,
                inventory_sessions.completed_at,
                inventory_sessions.cancelled_at,
                inventory_sessions.created_at,
                inventory_sessions.updated_at,
                inventory_sessions.last_edited_at,
                inventory_sessions.notes,
                inventory_sessions.completion_reason,
                inventory_sessions.cancellation_reason,
                inventory_sessions.created_by_user_id,
                inventory_sessions.started_by_user_id,
                inventory_sessions.completed_by_user_id,
                inventory_sessions.cancelled_by_user_id,
                inventory_sessions.last_edited_by_user_id,
                created_by_user.email AS created_by_email,
                started_by_user.email AS started_by_email,
                completed_by_user.email AS completed_by_email,
                cancelled_by_user.email AS cancelled_by_email,
                last_edited_by_user.email AS last_edited_by_email,
                inventory_sessions.location_id,
                locations.name AS location,
                COUNT(inventory_session_fixed_assets.fixed_asset_id) AS linked_assets_count,
                COALESCE(SUM(inventory_session_fixed_assets.quantity), 0) AS linked_assets_quantity_total
            FROM inventory_sessions
            LEFT JOIN users AS created_by_user
                ON created_by_user.id = inventory_sessions.created_by_user_id
            LEFT JOIN users AS started_by_user
                ON started_by_user.id = inventory_sessions.started_by_user_id
            LEFT JOIN users AS completed_by_user
                ON completed_by_user.id = inventory_sessions.completed_by_user_id
            LEFT JOIN users AS cancelled_by_user
                ON cancelled_by_user.id = inventory_sessions.cancelled_by_user_id
            LEFT JOIN users AS last_edited_by_user
                ON last_edited_by_user.id = inventory_sessions.last_edited_by_user_id
            LEFT JOIN locations ON locations.id = inventory_sessions.location_id
            LEFT JOIN inventory_session_fixed_assets
                ON inventory_session_fixed_assets.inventory_session_id = inventory_sessions.id
            WHERE inventory_sessions.id = ?
            GROUP BY
                inventory_sessions.id,
                inventory_sessions.date_from,
                inventory_sessions.date_to,
                inventory_sessions.status,
                inventory_sessions.responsible_person,
                inventory_sessions.started_at,
                inventory_sessions.completed_at,
                inventory_sessions.cancelled_at,
                inventory_sessions.created_at,
                inventory_sessions.updated_at,
                inventory_sessions.last_edited_at,
                inventory_sessions.notes,
                inventory_sessions.completion_reason,
                inventory_sessions.cancellation_reason,
                inventory_sessions.created_by_user_id,
                inventory_sessions.started_by_user_id,
                inventory_sessions.completed_by_user_id,
                inventory_sessions.cancelled_by_user_id,
                inventory_sessions.last_edited_by_user_id,
                created_by_user.email,
                started_by_user.email,
                completed_by_user.email,
                cancelled_by_user.email,
                last_edited_by_user.email,
                inventory_sessions.location_id,
                locations.name
            """,
            (session_id,),
        )
        return cursor.fetchone()


def list_fixed_assets_for_inventory_session(session_id: str) -> list[sqlite3.Row]:
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
                fixed_assets.category_id,
                COALESCE(
                    inventory_session_fixed_assets.expected_quantity,
                    fixed_assets.quantity
                ) AS expected_quantity,
                fixed_assets.deleted_at,
                fixed_assets.location_id,
                locations.name AS location,
                inventory_session_fixed_assets.quantity
            FROM inventory_session_fixed_assets
            JOIN fixed_assets ON fixed_assets.id = inventory_session_fixed_assets.fixed_asset_id
            LEFT JOIN fixed_asset_categories ON fixed_asset_categories.id = fixed_assets.category_id
            LEFT JOIN locations ON locations.id = fixed_assets.location_id
            WHERE inventory_session_fixed_assets.inventory_session_id = ?
            ORDER BY fixed_assets.name ASC
            """,
            (session_id,),
        )
        return cursor.fetchall()


def adjust_inventory_count(session_id: str, fixed_asset_id: str, delta: int) -> dict[str, Any]:
    """Add ``delta`` (may be negative) to one asset's counted quantity in an Active session.

    Used for counting by scanning labels. An asset that is not in the session yet
    is added with a count of ``delta`` and its current quantity as expected, even
    if it is at another location (``other_location`` is then True): it was found
    here, so it is counted. Counts never go below 0. The session's ``updated_at``
    is bumped, so an edit page opened earlier can tell its rows are out of date.

    The count changes at the session's active location (or with no location);
    ``quantity`` is the asset's total over all locations and ``here_quantity``
    its count at the active one.

    Returns a dict whose ``result`` is one of ``counted``, ``added``,
    ``session_not_found``, ``not_active``, ``asset_not_found``, ``asset_deleted``,
    ``not_linked`` (a negative delta for an asset that is not in the session) or
    ``not_counted_here`` (a negative delta where nothing was counted at the
    active location).
    """
    with db_session() as connection:
        session = connection.execute(
            "SELECT status, location_id FROM inventory_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if session is None:
            return {"result": "session_not_found"}
        if session["status"] != "Active":
            return {"result": "not_active"}

        asset = connection.execute(
            "SELECT id, name, quantity, location_id, deleted_at FROM fixed_assets WHERE id = ?",
            (fixed_asset_id,),
        ).fetchone()
        if asset is None:
            return {"result": "asset_not_found"}
        was_linked = connection.execute(
            """
            SELECT 1 FROM inventory_session_fixed_assets
            WHERE inventory_session_id = ? AND fixed_asset_id = ?
            """,
            (session_id, fixed_asset_id),
        ).fetchone() is not None
        base = {"name": asset["name"], "asset_id": asset["id"]}
        if not was_linked and asset["deleted_at"] is not None:
            return {**base, "result": "asset_deleted"}
        if not was_linked and delta <= 0:
            return {**base, "result": "not_linked"}

        location_id = session["location_id"]
        if delta < 0:
            counted_here = connection.execute(
                """
                SELECT quantity FROM inventory_session_counts
                WHERE inventory_session_id = ? AND fixed_asset_id = ? AND location_id IS ?
                """,
                (session_id, fixed_asset_id, location_id),
            ).fetchone()
            if counted_here is None or counted_here["quantity"] == 0:
                return {**base, "result": "not_counted_here"}

        # Another scan may add the same asset at the same moment; then it is
        # already linked and the count below adds to it.
        connection.execute(
            """
            INSERT OR IGNORE INTO inventory_session_fixed_assets (
                inventory_session_id, fixed_asset_id, quantity, expected_quantity
            )
            VALUES (?, ?, 0, ?)
            """,
            (session_id, fixed_asset_id, asset["quantity"]),
        )
        _set_count(connection, session_id, fixed_asset_id, location_id, delta=delta)
        _update_count_totals(connection, session_id)
        connection.execute(
            "UPDATE inventory_sessions SET updated_at = ? WHERE id = ?",
            (_utc_now_text(), session_id),
        )
        link = connection.execute(
            """
            SELECT
                links.quantity,
                COALESCE(links.expected_quantity, ?) AS expected_quantity,
                counts.quantity AS here_quantity,
                locations.name AS location
            FROM inventory_session_fixed_assets AS links
            LEFT JOIN inventory_session_counts AS counts
                ON counts.inventory_session_id = links.inventory_session_id
               AND counts.fixed_asset_id = links.fixed_asset_id
               AND counts.location_id IS ?
            LEFT JOIN locations ON locations.id = ?
            WHERE links.inventory_session_id = ? AND links.fixed_asset_id = ?
            """,
            (asset["quantity"], location_id, location_id, session_id, fixed_asset_id),
        ).fetchone()
        return {
            **base,
            "result": "counted" if was_linked else "added",
            "quantity": int(link["quantity"]),
            "here_quantity": int(link["here_quantity"] or 0),
            "expected_quantity": int(link["expected_quantity"]),
            "location": link["location"],
            # Found somewhere else than the location it is registered at.
            "other_location": location_id is not None and asset["location_id"] != location_id,
        }


def list_fixed_asset_names() -> list[str]:
    """Names of all assets that are not deleted (to warn about duplicates on import)."""
    with db_session() as connection:
        rows = connection.execute("SELECT name FROM fixed_assets WHERE deleted_at IS NULL").fetchall()
        return [str(row["name"]) for row in rows]


def import_fixed_assets(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Insert many assets in one transaction: all of them or, on any error, none.

    Each row has ``name``, ``category``, ``location`` (may be empty), ``quantity``,
    ``initial_value``, ``responsible_person`` and ``registration_date``. Categories
    and locations are matched by name, ignoring case, and created when missing.
    Returns the new asset ids and the names of the categories and locations created.
    """
    with db_session() as connection:
        category_ids = {
            str(row["name"]).lower(): str(row["id"])
            for row in connection.execute(
                "SELECT id, name FROM fixed_asset_categories WHERE deleted_at IS NULL"
            ).fetchall()
        }
        location_ids = {
            str(row["name"]).lower(): str(row["id"])
            for row in connection.execute("SELECT id, name FROM locations WHERE deleted_at IS NULL").fetchall()
        }
        created_categories: list[str] = []
        created_locations: list[str] = []
        asset_ids: list[str] = []

        for row in rows:
            category_name = str(row["category"]).strip()
            category_key = category_name.lower()
            if category_key not in category_ids:
                category_ids[category_key] = str(uuid.uuid4())
                connection.execute(
                    "INSERT INTO fixed_asset_categories (id, name) VALUES (?, ?)",
                    (category_ids[category_key], category_name),
                )
                created_categories.append(category_name)

            location_id = None
            location_name = str(row.get("location") or "").strip()
            if location_name:
                location_key = location_name.lower()
                if location_key not in location_ids:
                    location_ids[location_key] = str(uuid.uuid4())
                    connection.execute(
                        "INSERT INTO locations (id, name) VALUES (?, ?)",
                        (location_ids[location_key], location_name),
                    )
                    created_locations.append(location_name)
                location_id = location_ids[location_key]

            asset_id = str(uuid.uuid4())
            connection.execute(
                """
                INSERT INTO fixed_assets (
                    id, category_id, name, category, quantity, initial_value,
                    responsible_person, registration_date, location_id
                )
                SELECT ?, ?, ?, name, ?, ?, ?, ?, ?
                FROM fixed_asset_categories WHERE id = ?
                """,
                (
                    asset_id,
                    category_ids[category_key],
                    str(row["name"]).strip(),
                    int(row["quantity"]),
                    float(row["initial_value"]),
                    str(row["responsible_person"]).strip(),
                    str(row["registration_date"]),
                    location_id,
                    category_ids[category_key],
                ),
            )
            asset_ids.append(asset_id)

        return {
            "asset_ids": asset_ids,
            "created_categories": created_categories,
            "created_locations": created_locations,
        }


def find_fixed_asset_ids_by_prefix(prefix: str, limit: int = 2) -> list[str]:
    """Ids of assets that are not deleted and whose id starts with ``prefix``
    (the short id printed on labels)."""
    with db_session() as connection:
        rows = connection.execute(
            """
            SELECT id FROM fixed_assets
            WHERE deleted_at IS NULL AND substr(id, 1, ?) = lower(?)
            LIMIT ?
            """,
            (len(prefix), prefix, limit),
        ).fetchall()
        return [str(row["id"]) for row in rows]


def list_active_sessions_for_asset(fixed_asset_id: str) -> list[sqlite3.Row]:
    """Every Active session, with ``location`` its active location and
    ``quantity`` the asset's total count in it (NULL if not in it yet). Any
    asset can be counted in any session; the count goes to its active location."""
    with db_session() as connection:
        return connection.execute(
            """
            SELECT
                inventory_sessions.id,
                inventory_sessions.date_from,
                inventory_sessions.date_to,
                inventory_sessions.responsible_person,
                locations.name AS location,
                links.quantity
            FROM inventory_sessions
            JOIN fixed_assets ON fixed_assets.id = ?
            LEFT JOIN locations ON locations.id = inventory_sessions.location_id
            LEFT JOIN inventory_session_fixed_assets AS links
                ON links.inventory_session_id = inventory_sessions.id
               AND links.fixed_asset_id = fixed_assets.id
            WHERE inventory_sessions.status = 'Active'
            ORDER BY inventory_sessions.date_from DESC
            """,
            (fixed_asset_id,),
        ).fetchall()


def list_linked_fixed_asset_ids_for_inventory_session(session_id: str) -> list[str]:
    with db_session() as connection:
        cursor = connection.execute(
            """
            SELECT fixed_asset_id
            FROM inventory_session_fixed_assets
            WHERE inventory_session_id = ?
            ORDER BY fixed_asset_id
            """,
            (session_id,),
        )
        return [str(row["fixed_asset_id"]) for row in cursor.fetchall()]


def list_session_counts_at_location(session_id: str) -> list[sqlite3.Row]:
    """Each asset in the session with its count at the session's active location
    (``here``) and its total over all locations (``total``)."""
    with db_session() as connection:
        return connection.execute(
            """
            SELECT
                links.fixed_asset_id,
                COALESCE(counts.quantity, 0) AS here,
                links.quantity AS total
            FROM inventory_session_fixed_assets AS links
            JOIN inventory_sessions ON inventory_sessions.id = links.inventory_session_id
            LEFT JOIN inventory_session_counts AS counts
                ON counts.inventory_session_id = links.inventory_session_id
               AND counts.fixed_asset_id = links.fixed_asset_id
               AND counts.location_id IS inventory_sessions.location_id
            WHERE links.inventory_session_id = ?
            ORDER BY links.fixed_asset_id
            """,
            (session_id,),
        ).fetchall()


def list_linked_fixed_assets_for_inventory_session(session_id: str) -> list[tuple[str, int]]:
    with db_session() as connection:
        cursor = connection.execute(
            """
            SELECT fixed_asset_id, quantity
            FROM inventory_session_fixed_assets
            WHERE inventory_session_id = ?
            ORDER BY fixed_asset_id
            """,
            (session_id,),
        )
        return [
            (str(row["fixed_asset_id"]), int(row["quantity"]))
            for row in cursor.fetchall()
        ]


def create_inventory_session(
    date_from: str,
    date_to: str,
    responsible_person: str,
    linked_assets: Sequence[tuple[str, int]] = (),
    created_by_user_id: int | None = None,
    notes: str = "",
    location_id: str | None = None,
) -> sqlite3.Row:
    session_id = str(uuid.uuid4())
    now_text = datetime.now(timezone.utc).isoformat()
    with db_session() as connection:
        _require_active_location(connection, location_id)
        connection.execute(
            """
            INSERT INTO inventory_sessions (
                id,
                date_from,
                date_to,
                status,
                responsible_person,
                notes,
                created_at,
                updated_at,
                last_edited_at,
                created_by_user_id,
                last_edited_by_user_id,
                location_id
            )
            VALUES (?, ?, ?, 'New', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                date_from,
                date_to,
                responsible_person.strip(),
                notes.strip(),
                now_text,
                now_text,
                now_text,
                created_by_user_id,
                created_by_user_id,
                location_id,
            ),
        )
        if location_id is not None:
            _record_active_location(connection, session_id, location_id, created_by_user_id, now_text)
        _set_inventory_session_fixed_assets(
            connection, session_id, linked_assets, save_expected=False, count_location_id=location_id
        )
        cursor = connection.execute(
            """
            SELECT
                inventory_sessions.id,
                inventory_sessions.date_from,
                inventory_sessions.date_to,
                inventory_sessions.status,
                inventory_sessions.responsible_person,
                COUNT(inventory_session_fixed_assets.fixed_asset_id) AS linked_assets_count,
                COALESCE(SUM(inventory_session_fixed_assets.quantity), 0) AS linked_assets_quantity_total
            FROM inventory_sessions
            LEFT JOIN inventory_session_fixed_assets
                ON inventory_session_fixed_assets.inventory_session_id = inventory_sessions.id
            WHERE inventory_sessions.id = ?
            GROUP BY
                inventory_sessions.id,
                inventory_sessions.date_from,
                inventory_sessions.date_to,
                inventory_sessions.status,
                inventory_sessions.responsible_person
            """,
            (session_id,),
        )
        return cursor.fetchone()


def update_inventory_session(
    session_id: str,
    date_from: str,
    date_to: str,
    status: str,
    responsible_person: str,
    linked_assets: Sequence[tuple[str, int]] | None = None,
    notes: str = "",
    completion_reason: str = "",
    cancellation_reason: str = "",
    actor_user_id: int | None = None,
    location_id: str | None | object = KEEP_LOCATION,
) -> sqlite3.Row | None:
    """Save a session.

    ``linked_assets`` (asset id, count at the active location) replaces the
    session's assets; None keeps them and their counts. Leave out
    ``location_id`` to keep the active location; a different one (None for
    no location) becomes active and is added to the location history.
    """
    if status not in INVENTORY_SESSION_STATUSES:
        raise ValueError(f"Invalid status: {status!r}")
    now_text = datetime.now(timezone.utc).isoformat()
    with db_session() as connection:
        existing = connection.execute(
            """
            SELECT
                id,
                status,
                started_at,
                completed_at,
                cancelled_at,
                started_by_user_id,
                completed_by_user_id,
                cancelled_by_user_id,
                location_id
            FROM inventory_sessions
            WHERE id = ?
            """,
            (session_id,),
        ).fetchone()
        if existing is None:
            return None

        if location_id is KEEP_LOCATION:
            location_id = existing["location_id"]
        elif location_id != existing["location_id"]:
            # A session may keep a location that was deleted later; a new one must exist.
            _require_active_location(connection, location_id)
            _record_active_location(connection, session_id, location_id, actor_user_id, now_text)

        previous_status = str(existing["status"])
        started_at = existing["started_at"]
        completed_at = existing["completed_at"]
        cancelled_at = existing["cancelled_at"]
        started_by_user_id = existing["started_by_user_id"]
        completed_by_user_id = existing["completed_by_user_id"]
        cancelled_by_user_id = existing["cancelled_by_user_id"]

        if previous_status != status:
            if status == "Active" and started_at is None:
                started_at = now_text
                started_by_user_id = actor_user_id
            if status == "Completed" and completed_at is None:
                completed_at = now_text
                completed_by_user_id = actor_user_id
            if status == "Cancelled" and cancelled_at is None:
                cancelled_at = now_text
                cancelled_by_user_id = actor_user_id

            if previous_status == "Completed" and status != "Completed":
                completed_at = None
                completed_by_user_id = None
            if previous_status == "Cancelled" and status != "Cancelled":
                cancelled_at = None
                cancelled_by_user_id = None

        connection.execute(
            """
            UPDATE inventory_sessions
            SET
                date_from = ?,
                date_to = ?,
                status = ?,
                responsible_person = ?,
                notes = ?,
                completion_reason = ?,
                cancellation_reason = ?,
                started_at = ?,
                completed_at = ?,
                cancelled_at = ?,
                updated_at = ?,
                last_edited_at = ?,
                started_by_user_id = ?,
                completed_by_user_id = ?,
                cancelled_by_user_id = ?,
                last_edited_by_user_id = ?,
                location_id = ?
            WHERE id = ?
            """,
            (
                date_from,
                date_to,
                status,
                responsible_person.strip(),
                notes.strip(),
                completion_reason.strip(),
                cancellation_reason.strip(),
                started_at,
                completed_at,
                cancelled_at,
                now_text,
                now_text,
                started_by_user_id,
                completed_by_user_id,
                cancelled_by_user_id,
                actor_user_id,
                location_id,
                session_id,
            ),
        )
        _set_inventory_session_fixed_assets(
            connection, session_id, linked_assets, save_expected=status != "New", count_location_id=location_id
        )
        cursor = connection.execute(
            """
            SELECT
                inventory_sessions.id,
                inventory_sessions.date_from,
                inventory_sessions.date_to,
                inventory_sessions.status,
                inventory_sessions.responsible_person,
                COUNT(inventory_session_fixed_assets.fixed_asset_id) AS linked_assets_count,
                COALESCE(SUM(inventory_session_fixed_assets.quantity), 0) AS linked_assets_quantity_total
            FROM inventory_sessions
            LEFT JOIN inventory_session_fixed_assets
                ON inventory_session_fixed_assets.inventory_session_id = inventory_sessions.id
            WHERE inventory_sessions.id = ?
            GROUP BY
                inventory_sessions.id,
                inventory_sessions.date_from,
                inventory_sessions.date_to,
                inventory_sessions.status,
                inventory_sessions.responsible_person
            """,
            (session_id,),
        )
        return cursor.fetchone()


def _record_active_location(
    connection: sqlite3.Connection, session_id: str, location_id: str | None, user_id: int | None, at: str
) -> None:
    connection.execute(
        """
        INSERT INTO inventory_session_locations (inventory_session_id, location_id, activated_at, activated_by_user_id)
        VALUES (?, ?, ?, ?)
        """,
        (session_id, location_id, at, user_id),
    )


def set_active_location(session_id: str, location_id: str | None, user_id: int | None) -> str:
    """Make a location (None: no location) the session's active one.

    Returns ``changed``, ``unchanged``, ``session_not_found`` or ``closed``
    (only New and Active sessions can change it). Raises ValueError for a
    location that doesn't exist. Bumps ``updated_at``: an edit page opened
    before would otherwise save its counts at the new location.
    """
    now = _utc_now_text()
    with db_session() as connection:
        session = connection.execute(
            "SELECT status, location_id FROM inventory_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if session is None:
            return "session_not_found"
        if session["status"] not in ("New", "Active"):
            return "closed"
        if session["location_id"] == location_id:
            return "unchanged"
        _require_active_location(connection, location_id)
        connection.execute(
            "UPDATE inventory_sessions SET location_id = ?, updated_at = ? WHERE id = ?",
            (location_id, now, session_id),
        )
        _record_active_location(connection, session_id, location_id, user_id, now)
        return "changed"


def list_session_location_history(session_id: str) -> list[sqlite3.Row]:
    """The session's active locations in the order they were set (location
    NULL: counting with no location)."""
    with db_session() as connection:
        return connection.execute(
            """
            SELECT
                history.activated_at,
                history.location_id,
                locations.name AS location,
                users.email AS activated_by_email
            FROM inventory_session_locations AS history
            LEFT JOIN locations ON locations.id = history.location_id
            LEFT JOIN users ON users.id = history.activated_by_user_id
            WHERE history.inventory_session_id = ?
            ORDER BY history.activated_at ASC, history.id ASC
            """,
            (session_id,),
        ).fetchall()


def list_session_counts(session_id: str) -> list[sqlite3.Row]:
    """Every count in the session: asset, location (NULL: no location) and quantity."""
    with db_session() as connection:
        return connection.execute(
            """
            SELECT counts.fixed_asset_id, counts.location_id, locations.name AS location, counts.quantity
            FROM inventory_session_counts AS counts
            LEFT JOIN locations ON locations.id = counts.location_id
            WHERE counts.inventory_session_id = ?
            ORDER BY lower(COALESCE(locations.name, '')), counts.id
            """,
            (session_id,),
        ).fetchall()


def delete_inventory_session(session_id: str) -> bool:
    with db_session() as connection:
        cursor = connection.execute(
            "DELETE FROM inventory_sessions WHERE id = ?",
            (session_id,),
        )
        return cursor.rowcount > 0