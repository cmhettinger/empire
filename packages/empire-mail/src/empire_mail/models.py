"""Public mail data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


AddressInput = str | list[str] | tuple[str, ...] | None
AttachmentInput = str | Path | list[str | Path] | tuple[str | Path, ...] | None


def normalize_addresses(addresses: AddressInput) -> list[str]:
    """Normalize a user-supplied address value to a clean list."""

    if addresses is None:
        return []
    if isinstance(addresses, str):
        return [addresses] if addresses.strip() else []
    return [address for address in addresses if address.strip()]


def normalize_attachments(attachments: AttachmentInput) -> list[Path]:
    """Normalize user-supplied attachment paths."""

    if attachments is None:
        return []
    if isinstance(attachments, (str, Path)):
        return [Path(attachments)]
    return [Path(attachment) for attachment in attachments]


@dataclass(frozen=True)
class MailMessage:
    """An email message before SMTP serialization."""

    to: AddressInput
    subject: str
    text: str
    html: str | None = None
    cc: AddressInput = None
    bcc: AddressInput = None
    attachments: AttachmentInput = None
    from_address: str | None = None
    normalized_to: list[str] = field(init=False, repr=False)
    normalized_cc: list[str] = field(init=False, repr=False)
    normalized_bcc: list[str] = field(init=False, repr=False)
    attachment_paths: list[Path] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "normalized_to", normalize_addresses(self.to))
        object.__setattr__(self, "normalized_cc", normalize_addresses(self.cc))
        object.__setattr__(self, "normalized_bcc", normalize_addresses(self.bcc))
        object.__setattr__(
            self, "attachment_paths", normalize_attachments(self.attachments)
        )

    @property
    def recipients(self) -> list[str]:
        """All SMTP envelope recipients, including Bcc."""

        return self.normalized_to + self.normalized_cc + self.normalized_bcc
