"""
Sends notifications for trade/approval events over two channels:
- Email via SMTP (any provider) - see EMAIL_* env vars below.
- Push via ntfy.sh (https://ntfy.sh) - a free, account-less push service.
  Install the ntfy app and subscribe to your topic to get phone push
  notifications. See NTFY_TOPIC below.

Both are best-effort and independent: if one is unconfigured or fails, the
other still tries, and neither ever raises - a notification failure must
never interrupt trading.

Required env vars (all optional per-channel):
  EMAIL_SMTP_HOST     e.g. smtp.gmail.com
  EMAIL_SMTP_PORT     e.g. 587 (STARTTLS) - defaults to 587
  EMAIL_USERNAME      the account to send from
  EMAIL_APP_PASSWORD  an app-specific password (NOT your main account password -
                       for Gmail: Google Account -> Security -> 2-Step Verification
                       -> App Passwords)
  EMAIL_TO            where to send notifications (can be same as EMAIL_USERNAME)
  NTFY_TOPIC          a private, hard-to-guess topic name (ntfy topics are public -
                       anyone who knows the topic name can read it, so treat the
                       name itself as a secret). Subscribe to it in the ntfy app.

Never put these values in code or config.py - set them as environment
variables / repo secrets on whatever runs the bot.
"""

import os
import smtplib
from email.message import EmailMessage

import requests


def _email_config_from_env():
    host = os.environ.get("EMAIL_SMTP_HOST")
    port = os.environ.get("EMAIL_SMTP_PORT", "587")
    username = os.environ.get("EMAIL_USERNAME")
    password = os.environ.get("EMAIL_APP_PASSWORD")
    to_addr = os.environ.get("EMAIL_TO")
    if not all([host, username, password, to_addr]):
        return None
    return {"host": host, "port": int(port), "username": username,
            "password": password, "to": to_addr}


def _send_email(subject: str, body: str) -> bool:
    cfg = _email_config_from_env()
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


def _send_push(subject: str, body: str, priority: str = "default") -> bool:
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        print(f"[notifier] NTFY_TOPIC not set - skipping push. Would have sent: '{subject}'")
        return False
    try:
        resp = requests.post(
            f"https://ntfy.sh/{topic}",
            data=body.encode("utf-8"),
            headers={"Title": subject, "Priority": priority},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[notifier] failed to send push: {e}")
        return False


def notify(subject: str, body: str, urgent: bool = False) -> None:
    """Best-effort send over both channels. Never raises - callers should
    never let a notification failure interrupt trading."""
    _send_email(subject, body)
    _send_push(subject, body, priority="urgent" if urgent else "default")


def notify_push_only(subject: str, body: str, urgent: bool = False) -> None:
    """Push-only send (no email) - used for news awareness, which is
    high-frequency (every 30 min) and would otherwise flood an inbox."""
    _send_push(subject, body, priority="urgent" if urgent else "default")


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
    notify(subject, body, urgent=is_big)
