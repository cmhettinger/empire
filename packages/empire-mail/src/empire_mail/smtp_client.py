"""SMTP transport for Empire mail."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from empire_mail.attachments import load_attachment
from empire_mail.config import MailConfig
from empire_mail.exceptions import MailSendError, MissingRecipientError
from empire_mail.models import MailMessage, normalize_addresses


logger = logging.getLogger(__name__)


class SMTPMailClient:
    """Send messages through an SMTP server."""

    def __init__(self, config: MailConfig | None = None) -> None:
        self.config = config or MailConfig.from_env()

    def build_email_message(self, message: MailMessage) -> EmailMessage:
        """Build an EmailMessage without sending it."""

        sender = message.from_address or self.config.require_sender()
        to_recipients, _recipients = self._resolve_recipients(message)

        email_message = EmailMessage()
        email_message["From"] = sender
        email_message["To"] = ", ".join(to_recipients)
        if message.normalized_cc:
            email_message["Cc"] = ", ".join(message.normalized_cc)
        email_message["Subject"] = message.subject
        email_message.set_content(message.text)

        if message.html:
            email_message.add_alternative(message.html, subtype="html")

        for attachment_path in message.attachment_paths:
            attachment = load_attachment(attachment_path)
            email_message.add_attachment(
                attachment.content,
                maintype=attachment.maintype,
                subtype=attachment.subtype,
                filename=attachment.filename,
            )

        logger.debug(
            "Built email message",
            extra={
                "recipient_count": len(_recipients),
                "attachment_count": len(message.attachment_paths),
                "has_html": bool(message.html),
            },
        )
        return email_message

    def send(self, message: MailMessage) -> EmailMessage:
        """Send a message and return the serialized message object."""

        email_message = self.build_email_message(message)
        sender = message.from_address or self.config.require_sender()
        _to_recipients, recipients = self._resolve_recipients(message)

        logger.info(
            "Sending email via SMTP",
            extra={
                "smtp_host": self.config.smtp_host,
                "smtp_port": self.config.smtp_port,
                "starttls": self.config.smtp_starttls,
                "ssl": self.config.smtp_ssl,
                "recipient_count": len(recipients),
                "attachment_count": len(message.attachment_paths),
            },
        )

        try:
            if self.config.smtp_ssl:
                context = ssl.create_default_context()
                logger.debug("Using SMTP over SSL")
                with smtplib.SMTP_SSL(
                    self.config.smtp_host,
                    self.config.smtp_port,
                    timeout=self.config.timeout,
                    context=context,
                ) as smtp:
                    self._send_with_connection(smtp, sender, recipients, email_message)
            else:
                with smtplib.SMTP(
                    self.config.smtp_host,
                    self.config.smtp_port,
                    timeout=self.config.timeout,
                ) as smtp:
                    if self.config.smtp_starttls:
                        context = ssl.create_default_context()
                        logger.debug("Starting SMTP TLS")
                        smtp.starttls(context=context)
                        smtp.ehlo()
                    self._send_with_connection(smtp, sender, recipients, email_message)
        except (OSError, smtplib.SMTPException) as exc:
            raise MailSendError(f"Failed to send email via SMTP: {exc}") from exc

        logger.info(
            "Email sent via SMTP",
            extra={
                "smtp_host": self.config.smtp_host,
                "smtp_port": self.config.smtp_port,
                "recipient_count": len(recipients),
                "attachment_count": len(message.attachment_paths),
            },
        )
        return email_message

    def _resolve_recipients(self, message: MailMessage) -> tuple[list[str], list[str]]:
        to_recipients = message.normalized_to or normalize_addresses(
            self.config.to_default
        )
        recipients = to_recipients + message.normalized_cc + message.normalized_bcc
        if not recipients:
            raise MissingRecipientError(
                "At least one recipient is required, or set EMPIRE_MAIL_TO_DEFAULT."
            )
        return to_recipients, recipients

    def _send_with_connection(
        self,
        smtp: smtplib.SMTP,
        sender: str,
        recipients: list[str],
        email_message: EmailMessage,
    ) -> None:
        if self.config.username:
            smtp.login(self.config.username, self.config.password)
        smtp.send_message(email_message, from_addr=sender, to_addrs=recipients)
