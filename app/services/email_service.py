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
    message = EmailMessage()
    message["Subject"] = "Reset your Asset Registry password"
    message["From"] = str(settings["sender"])
    message["To"] = recipient
    message.set_content(
        "Someone asked to reset the password for this email address in Asset Registry.\n\n"
        f"To choose a new password, open this link within 1 hour:\n{link}\n\n"
        "If you didn't ask for this, you can ignore this email. Your password won't change.\n"
    )

    try:
        with smtplib.SMTP(str(settings["host"]), int(settings["port"]), timeout=15) as smtp:
            if settings["starttls"]:
                smtp.starttls()
            if settings["username"]:
                smtp.login(str(settings["username"]), str(settings["password"]))
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException):
        logger.exception("Could not send password reset email.")
        return False
    return True
