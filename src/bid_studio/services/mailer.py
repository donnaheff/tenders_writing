"""Deliver an email and always record it in the delivery log.

If SMTP_HOST is configured the message is sent over SMTP; otherwise it is only
logged (status "logged"), which is the default for local and demo use.
"""

import smtplib
from email.message import EmailMessage

from sqlalchemy.orm import Session

from bid_studio.config import settings
from bid_studio.models import EmailDeliveryLog


def _send_smtp(to: str, subject: str, body: str, sender: str) -> None:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(msg)


def deliver(
    db: Session,
    *,
    workspace_id: int,
    to: str,
    subject: str,
    body: str,
    delivery_type: str,
    reference_id: int | None = None,
    sender: str | None = None,
) -> EmailDeliveryLog:
    status = "logged"
    if settings.smtp_host:
        try:
            _send_smtp(to, subject, body, sender or settings.delivery_sender_email)
            status = "sent"
        except Exception:
            status = "failed"
    log = EmailDeliveryLog(
        workspace_id=workspace_id,
        recipient_email=to,
        subject=subject[:240],
        delivery_type=delivery_type,
        reference_id=reference_id,
        body_preview=body[:2000],
        status=status,
    )
    db.add(log)
    return log
