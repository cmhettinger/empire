"""Reusable SMTP email helpers for Empire."""

from empire_mail.attachments import MailAttachment, load_attachment
from empire_mail.config import MailConfig
from empire_mail.exceptions import (
    EmpireMailError,
    MailConfigError,
    MailSendError,
    MissingAttachmentError,
    MissingRecipientError,
)
from empire_mail.models import MailMessage
from empire_mail.service import (
    send_email,
    send_html_email,
    send_report_email,
    send_text_email,
)
from empire_mail.smtp_client import SMTPMailClient

__all__ = [
    "EmpireMailError",
    "MailAttachment",
    "MailConfig",
    "MailConfigError",
    "MailMessage",
    "MailSendError",
    "MissingAttachmentError",
    "MissingRecipientError",
    "SMTPMailClient",
    "load_attachment",
    "send_email",
    "send_html_email",
    "send_report_email",
    "send_text_email",
]
