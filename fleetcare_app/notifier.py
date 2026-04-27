import os
import smtplib
from email.message import EmailMessage


SMTP_HOST = os.environ.get("SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587") or 587)
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USERNAME).strip()
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").strip().lower() not in {"0", "false", "no"}


def notifications_enabled():
    return bool(SMTP_HOST and SMTP_FROM)


def send_owner_notification(owner_email, owner_sms_email, subject, body):
    if not notifications_enabled():
        print(f"Notifications skipped: SMTP is not configured. Subject={subject}")
        return False

    recipients = [address for address in {clean_address(owner_email), clean_address(owner_sms_email)} if address]
    if not recipients:
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = SMTP_FROM
    message["To"] = ", ".join(recipients)
    message.set_content(body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
        smtp.ehlo()
        if SMTP_USE_TLS:
            smtp.starttls()
            smtp.ehlo()
        if SMTP_USERNAME:
            smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
        smtp.send_message(message)
    return True


def clean_address(value):
    text = (value or "").strip()
    return text or None
