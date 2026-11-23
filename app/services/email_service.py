from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app import config

logger = logging.getLogger(__name__)


def send_password_reset_email(recipient: str, reset_path: str) -> bool:
    """Email a password reset link. Returns False (and logs) if sending fails."""
    settings = config.smtp_settings()
    if settings is None:
        logger.error("Password reset email requested but SMTP is not configured.")
        return False

    link = f"{config.app_base_url()}{reset_path}"
    return _send(
        settings,
        [recipient],
        "Reset your Asset Registry password",
        "Someone asked to reset the password for this email address in Asset Registry.\n\n"
        f"To choose a new password, open this link within 1 hour:\n{link}\n\n"
        "If you didn't ask for this, you can ignore this email. Your password won't change.\n",
    )


def send_new_account_notice(admin_emails: list[str], new_email: str) -> bool:
    """Tell administrators that an account is waiting for approval. Does nothing
    without SMTP and APP_BASE_URL; the Users page shows waiting accounts anyway."""
    settings = config.smtp_settings()
    if settings is None or not config.app_base_url() or not admin_emails:
        return False
    return _send(
        settings,
        admin_emails,
        "New Asset Registry account waiting for approval",
        f"{new_email} has registered in Asset Registry and is waiting for approval.\n\n"
        f"Approve or reject the account on the Users page:\n{config.app_base_url()}/users\n",
    )


def _send(settings: dict[str, object], recipients: list[str], subject: str, body: str) -> bool:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = str(settings["sender"])
    message["To"] = ", ".join(recipients)
    message.set_content(body)

    try:
        with smtplib.SMTP(str(settings["host"]), int(settings["port"]), timeout=15) as smtp:
            if settings["starttls"]:
                smtp.starttls()
            if settings["username"]:
                smtp.login(str(settings["username"]), str(settings["password"]))
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException):
        logger.exception("Could not send email.", extra={"subject": subject})
        return False
    return True
