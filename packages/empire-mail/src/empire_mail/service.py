"""Convenience helpers for common mail sending workflows."""

from __future__ import annotations

from pathlib import Path

from empire_mail.config import MailConfig
from empire_mail.models import AddressInput, AttachmentInput, MailMessage
from empire_mail.smtp_client import SMTPMailClient


def _resolve_to(config: MailConfig, to: AddressInput) -> AddressInput:
    return to if to else config.to_default


def send_email(
    *,
    subject: str,
    text: str,
    to: AddressInput = None,
    html: str | None = None,
    cc: AddressInput = None,
    bcc: AddressInput = None,
    attachments: AttachmentInput = None,
    config: MailConfig | None = None,
    client: SMTPMailClient | None = None,
):
    """Send a fully specified email message."""

    mail_config = config or (client.config if client else MailConfig.from_env())
    mail_client = client or SMTPMailClient(mail_config)
    message = MailMessage(
        to=_resolve_to(mail_config, to),
        subject=subject,
        text=text,
        html=html,
        cc=cc,
        bcc=bcc,
        attachments=attachments,
    )
    return mail_client.send(message)


def send_text_email(
    *,
    subject: str,
    text: str,
    to: AddressInput = None,
    cc: AddressInput = None,
    bcc: AddressInput = None,
    attachments: AttachmentInput = None,
    config: MailConfig | None = None,
    client: SMTPMailClient | None = None,
):
    """Send a plain-text email."""

    return send_email(
        subject=subject,
        text=text,
        to=to,
        cc=cc,
        bcc=bcc,
        attachments=attachments,
        config=config,
        client=client,
    )


def send_html_email(
    *,
    subject: str,
    text: str,
    html: str,
    to: AddressInput = None,
    cc: AddressInput = None,
    bcc: AddressInput = None,
    attachments: AttachmentInput = None,
    config: MailConfig | None = None,
    client: SMTPMailClient | None = None,
):
    """Send an email with text and HTML alternatives."""

    return send_email(
        subject=subject,
        text=text,
        html=html,
        to=to,
        cc=cc,
        bcc=bcc,
        attachments=attachments,
        config=config,
        client=client,
    )


def send_report_email(
    *,
    subject: str,
    text: str,
    report_path: str | Path,
    to: AddressInput = None,
    html: str | None = None,
    cc: AddressInput = None,
    bcc: AddressInput = None,
    config: MailConfig | None = None,
    client: SMTPMailClient | None = None,
):
    """Send a report email with one file attachment."""

    return send_email(
        subject=subject,
        text=text,
        html=html,
        to=to,
        cc=cc,
        bcc=bcc,
        attachments=[report_path],
        config=config,
        client=client,
    )
