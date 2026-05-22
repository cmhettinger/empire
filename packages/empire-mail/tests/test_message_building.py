from email.message import EmailMessage
from unittest.mock import patch

import pytest

from empire_mail import (
    MailConfig,
    MailMessage,
    MissingAttachmentError,
    MissingRecipientError,
    SMTPMailClient,
)


def make_client(to_default: str | None = "default@example.com") -> SMTPMailClient:
    return SMTPMailClient(
        MailConfig(
            smtp_host="smtp.example.com",
            from_address="sender@example.com",
            to_default=to_default,
        )
    )


def test_builds_plain_text_message():
    client = make_client()
    message = MailMessage(
        to="recipient@example.com",
        subject="Hello",
        text="Plain text body",
    )

    built = client.build_email_message(message)

    assert isinstance(built, EmailMessage)
    assert built["From"] == "sender@example.com"
    assert built["To"] == "recipient@example.com"
    assert built["Subject"] == "Hello"
    assert built.get_content().strip() == "Plain text body"


def test_builds_html_alternative_message():
    client = make_client()
    message = MailMessage(
        to=["recipient@example.com"],
        cc=["copy@example.com"],
        bcc=["hidden@example.com"],
        subject="Hello HTML",
        text="Fallback text",
        html="<p>Hello</p>",
    )

    built = client.build_email_message(message)

    assert built["To"] == "recipient@example.com"
    assert built["Cc"] == "copy@example.com"
    assert "Bcc" not in built
    assert message.recipients == [
        "recipient@example.com",
        "copy@example.com",
        "hidden@example.com",
    ]
    alternatives = built.get_payload()
    assert alternatives[0].get_content().strip() == "Fallback text"
    assert alternatives[1].get_content_type() == "text/html"
    assert alternatives[1].get_content().strip() == "<p>Hello</p>"


def test_builds_message_with_attachment(tmp_path):
    report = tmp_path / "report.txt"
    report.write_text("report body")
    client = make_client()
    message = MailMessage(
        to="recipient@example.com",
        subject="Report",
        text="Attached",
        attachments=[report],
    )

    built = client.build_email_message(message)

    attachments = list(built.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "report.txt"
    assert attachments[0].get_content().strip() == b"report body"


def test_build_uses_default_recipient_when_to_is_omitted():
    client = make_client()
    message = MailMessage(to=None, subject="Default", text="Body")

    built = client.build_email_message(message)

    assert built["To"] == "default@example.com"


def test_missing_attachment_raises_clear_exception(tmp_path):
    client = make_client()
    message = MailMessage(
        to="recipient@example.com",
        subject="Report",
        text="Attached",
        attachments=[tmp_path / "missing.csv"],
    )

    with pytest.raises(MissingAttachmentError, match="Attachment not found"):
        client.build_email_message(message)


def test_missing_recipient_raises_clear_exception():
    client = make_client(to_default=None)
    message = MailMessage(to=None, subject="No one", text="Body")

    with pytest.raises(MissingRecipientError, match="recipient"):
        client.build_email_message(message)


def test_send_uses_default_recipient_for_smtp_envelope(caplog):
    config = MailConfig(
        smtp_host="smtp.example.com",
        from_address="sender@example.com",
        to_default="default@example.com",
        username="user",
        password="secret",
    )
    client = SMTPMailClient(config)
    message = MailMessage(to=None, subject="Default", text="Body")

    caplog.set_level("DEBUG", logger="empire_mail.smtp_client")
    with patch("empire_mail.smtp_client.smtplib.SMTP") as smtp_class:
        smtp = smtp_class.return_value.__enter__.return_value

        built = client.send(message)

    smtp_class.assert_called_once_with("smtp.example.com", 587, timeout=30.0)
    smtp.starttls.assert_called_once()
    smtp.ehlo.assert_called_once()
    smtp.login.assert_called_once_with("user", "secret")
    smtp.send_message.assert_called_once_with(
        built,
        from_addr="sender@example.com",
        to_addrs=["default@example.com"],
    )
    log_text = caplog.text
    assert "secret" not in log_text
    assert "default@example.com" not in log_text
    assert "Body" not in log_text
    assert "Sending email via SMTP" in log_text
    assert "Email sent via SMTP" in log_text

    send_attempt = next(
        record for record in caplog.records if record.message == "Sending email via SMTP"
    )
    assert send_attempt.smtp_host == "smtp.example.com"
    assert send_attempt.smtp_port == 587
    assert send_attempt.starttls is True
    assert send_attempt.ssl is False
    assert send_attempt.recipient_count == 1
    assert send_attempt.attachment_count == 0
