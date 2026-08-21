"""
Sends email notifications for trade events. Uses plain SMTP so it works
with any provider (Gmail, Outlook, etc.) - this runs unattended as part
of the bot's own process, so it needs its own credentials, separate from
whatever email tools a human might use interactively.

Required env vars (all optional - if any are missing, notify() prints a
warning and does nothing rather than crashing the trading loop):
  EMAIL_SMTP_HOST     e.g. smtp.gmail.com
  EMAIL_SMTP_PORT     e.g. 587 (STARTTLS) - defaults to 587
  EMAIL_USERNAME      the account to send from
  EMAIL_APP_PASSWORD  an app-specific password (NOT your main account password -
                       for Gmail: Google Account -> Security -> 2-Step Verification
                       -> App Passwords)
  EMAIL_TO            where to send notifications (can be same as EMAIL_USERNAME)

Never put these values in code or config.py - set them as environment
variables on the machine that runs the bot.
"""

import os
import smtplib
from email.message import EmailMessage


def _config_from_env():
    host = os.environ.get("EMAIL_SMTP_HOST")
    port = os.environ.get("EMAIL_SMTP_PORT", "587")
    username = os.environ.get("EMAIL_USERNAME")
    password = os.environ.get("EMAIL_APP_PASSWORD")
    to_addr = os.environ.get("EMAIL_TO")
    if not all([host, username, password, to_addr]):
        return None
    return {"host": host, "port": int(port), "username": username,
            "password": password, "to": to_addr}


def notify(subject: str, body: str) -> bool:
    """Best-effort email send. Returns True if sent, False if skipped/failed -
    callers should never let a notification failure interrupt trading."""
    cfg = _config_from_env()
    if cfg is None:
        print(f"[notifier] EMAIL_* env vars not fully set - skipping email. "
              f"Would have sent: '{subject}'")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["username"]
    msg["To"] = cfg["to"]
    msg.set_content(body)

    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as server:
            server.starttls()
            server.login(cfg["username"], cfg["password"])
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"[notifier] failed to send email: {e}")
        return False


def trade_notification(profile_label: str, action: str, price: float, size_myr: float,
                        balance: float, reason: str, is_big: bool) -> None:
    flag = "[BIG TRADE] " if is_big else ""
    subject = f"{flag}luno_bot [{profile_label}]: {action} @ {price:.2f}"
    body = (
        f"Profile: {profile_label}\n"
        f"Action: {action}\n"
        f"Price: {price:.2f}\n"
        f"Size: {size_myr:.2f} MYR\n"
        f"Balance after: {balance:.2f} MYR\n"
        f"Reason: {reason}\n"
    )
    notify(subject, body)
