"""Runtime configuration read from environment variables.

Local development needs no configuration: without ``APP_ENV`` the app behaves as
before (demo admin account, reset links shown on screen). Setting
``APP_ENV=production`` switches every default to the safe production behaviour.
See the "Configuration" section of README.md for the full list of variables.
"""

from __future__ import annotations

import os
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent

DEV_ADMIN_EMAIL = "admin@example.com"
DEV_ADMIN_PASSWORD = "password123"
MIN_ADMIN_PASSWORD_LENGTH = 12


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_flag(name: str, default: bool) -> bool:
    value = _env(name).lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def is_production() -> bool:
    return _env("APP_ENV").lower() in {"prod", "production"}


# --- Storage -----------------------------------------------------------------

def database_path() -> Path:
    """SQLite file. Point it at a persistent disk when deploying."""
    return Path(_env("DATABASE_PATH") or _APP_DIR.parent / "app.db")


def uploads_dir() -> Path:
    """Folder for uploaded asset images. Point it at a persistent disk when deploying."""
    return Path(_env("UPLOADS_DIR") or _APP_DIR / "uploads")


# --- Admin account -----------------------------------------------------------

def bootstrap_admin() -> tuple[str, str] | None:
    """Account to create on startup if it does not exist yet.

    Development: the demo account admin@example.com / password123.
    Production: only ADMIN_EMAIL / ADMIN_PASSWORD when both are set; never the demo account.
    """
    if not is_production():
        return DEV_ADMIN_EMAIL, DEV_ADMIN_PASSWORD

    email = _env("ADMIN_EMAIL").lower()
    password = os.getenv("ADMIN_PASSWORD", "")
    if not email or not password:
        return None
    if len(password) < MIN_ADMIN_PASSWORD_LENGTH or password == DEV_ADMIN_PASSWORD:
        raise RuntimeError(
            f"ADMIN_PASSWORD must be at least {MIN_ADMIN_PASSWORD_LENGTH} characters "
            "and must not be the demo password."
        )
    return email, password


def admin_emails() -> set[str]:
    """Emails allowed to use admin-only actions (e.g. reopening closed inventory sessions).

    ADMIN_EMAILS (comma-separated) wins. Otherwise: the demo admin in development,
    ADMIN_EMAIL in production.
    """
    configured = {e.strip().lower() for e in _env("ADMIN_EMAILS").split(",") if e.strip()}
    if configured:
        return configured
    if not is_production():
        return {DEV_ADMIN_EMAIL}
    admin_email = _env("ADMIN_EMAIL").lower()
    return {admin_email} if admin_email else set()


def show_demo_credentials() -> bool:
    return not is_production()


# --- Password reset ----------------------------------------------------------

def show_reset_link_on_screen() -> bool:
    """Only for local development: anyone could reset any account otherwise."""
    return not is_production()


def smtp_settings() -> dict[str, object] | None:
    """SMTP settings for emailing reset links, or None when email is not configured."""
    host = _env("SMTP_HOST")
    sender = _env("SMTP_FROM")
    if not host or not sender or not app_base_url():
        return None
    return {
        "host": host,
        "port": int(_env("SMTP_PORT") or 587),
        "username": _env("SMTP_USERNAME"),
        "password": os.getenv("SMTP_PASSWORD", ""),
        "sender": sender,
        "starttls": _env_flag("SMTP_STARTTLS", True),
    }


def app_base_url() -> str:
    """Public URL of the site, e.g. https://assets.example.com (used in emailed links)."""
    return _env("APP_BASE_URL").rstrip("/")


def password_reset_available() -> bool:
    return show_reset_link_on_screen() or smtp_settings() is not None


# --- HTTP ----------------------------------------------------------------------

def session_cookie_secure() -> bool:
    return _env_flag("SESSION_COOKIE_SECURE", is_production())


def session_cookie_samesite() -> str:
    return "strict" if is_production() else "lax"
