"""Attachment helpers for email messages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from empire_mail.exceptions import MissingAttachmentError


@dataclass(frozen=True)
class MailAttachment:
    """A file attachment loaded from disk."""

    path: Path
    filename: str
    content: bytes
    maintype: str
    subtype: str


def load_attachment(path: str | Path) -> MailAttachment:
    """Load an attachment from a local file path."""

    attachment_path = Path(path)
    if not attachment_path.is_file():
        raise MissingAttachmentError(f"Attachment not found: {attachment_path}")

    return MailAttachment(
        path=attachment_path,
        filename=attachment_path.name,
        content=attachment_path.read_bytes(),
        maintype="application",
        subtype="octet-stream",
    )
