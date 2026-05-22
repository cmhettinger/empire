"""Custom exceptions for empire_mail."""


class EmpireMailError(Exception):
    """Base exception for empire_mail failures."""


class MailConfigError(EmpireMailError):
    """Raised when required mail configuration is missing or invalid."""


class MissingRecipientError(EmpireMailError):
    """Raised when no recipient is supplied or configured."""


class MissingAttachmentError(EmpireMailError):
    """Raised when an attachment path cannot be found."""


class MailSendError(EmpireMailError):
    """Raised when SMTP delivery fails."""
