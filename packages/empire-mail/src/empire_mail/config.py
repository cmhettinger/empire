"""Configuration loading for SMTP mail delivery."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from empire_mail.exceptions import MailConfigError


def _parse_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None or value == "":
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False

    raise MailConfigError(f"Invalid boolean value for mail configuration: {value!r}")


@dataclass(frozen=True)
class MailConfig:
    """SMTP connection and sender settings."""

    smtp_host: str
    smtp_port: int = 587
    smtp_starttls: bool = True
    smtp_ssl: bool = False
    timeout: float = 30.0
    username: str | None = None
    password: str | None = field(default=None, repr=False)
    from_address: str | None = None
    to_default: str | None = None

    def __post_init__(self) -> None:
        if self.smtp_starttls and self.smtp_ssl:
            raise MailConfigError(
                "EMPIRE_MAIL_SMTP_STARTTLS and EMPIRE_MAIL_SMTP_SSL cannot both be true."
            )
        if self.username and not self.password:
            raise MailConfigError(
                "EMPIRE_MAIL_PASSWORD is required when EMPIRE_MAIL_USERNAME is set."
            )
        if self.timeout <= 0:
            raise MailConfigError("SMTP timeout must be greater than zero.")

    @classmethod
    def from_env(cls) -> "MailConfig":
        """Load mail configuration from the process environment."""

        environ = os.environ

        host = environ.get("EMPIRE_MAIL_SMTP_HOST")
        if not host:
            raise MailConfigError("EMPIRE_MAIL_SMTP_HOST is required.")

        raw_port = environ.get("EMPIRE_MAIL_SMTP_PORT", "587")
        try:
            port = int(raw_port)
        except ValueError as exc:
            raise MailConfigError("EMPIRE_MAIL_SMTP_PORT must be an integer.") from exc

        return cls(
            smtp_host=host,
            smtp_port=port,
            smtp_starttls=_parse_bool(
                environ.get("EMPIRE_MAIL_SMTP_STARTTLS"), default=True
            ),
            smtp_ssl=_parse_bool(environ.get("EMPIRE_MAIL_SMTP_SSL"), default=False),
            username=environ.get("EMPIRE_MAIL_USERNAME") or None,
            password=environ.get("EMPIRE_MAIL_PASSWORD") or None,
            from_address=environ.get("EMPIRE_MAIL_FROM") or None,
            to_default=environ.get("EMPIRE_MAIL_TO_DEFAULT") or None,
        )

    def require_sender(self) -> str:
        """Return the configured sender or raise a clear configuration error."""

        if not self.from_address:
            raise MailConfigError("EMPIRE_MAIL_FROM is required.")
        return self.from_address
