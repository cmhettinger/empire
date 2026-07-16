"""Transactional persistence for durable OHLCV source-content identity."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from empire_stonks_ohlcv.exceptions import OHLCVPersistenceError
from empire_stonks_ohlcv.object_store import RAW_SOURCE_OBJECT_KIND
from empire_stonks_ohlcv.results import AcquiredObject


_SOURCE_CODE_PATTERN = re.compile(r"^[a-z0-9]+(?:[_-][a-z0-9]+)*$")
_CHECKSUM_PATTERN = re.compile(r"^[a-fA-F0-9]{64}$")
_PARSER_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class SourceSnapshotRegistration:
    """Result of registering one current Core raw object as source content."""

    source_snapshot_id: UUID
    object_id: UUID
    provider_code: str
    source_code: str
    content_sha256: str
    snapshot_inserted: bool
    object_link_inserted: bool

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "source_snapshot_id": str(self.source_snapshot_id),
            "object_id": str(self.object_id),
            "provider_code": self.provider_code,
            "source_code": self.source_code,
            "content_sha256": self.content_sha256,
            "snapshot_inserted": self.snapshot_inserted,
            "object_link_inserted": self.object_link_inserted,
        }


def upsert_provider_source_snapshot(
    *,
    cursor: Any,
    provider_code: str,
    acquired_object: AcquiredObject,
    parser_version: str | None = None,
) -> SourceSnapshotRegistration:
    """Upsert source identity and link its current Core object.

    The caller owns the transaction. This helper neither commits nor creates
    Core objects, runs, or duplicate source-snapshot tables.
    """

    content_sha256 = _validate_input(
        provider_code=provider_code,
        acquired_object=acquired_object,
        parser_version=parser_version,
    )
    run_id = _validate_stored_object(
        cursor=cursor,
        acquired_object=acquired_object,
        content_sha256=content_sha256,
    )
    cursor.execute(
        """
        INSERT INTO stonks.provider_source_snapshot (
            provider_code,
            source_code,
            content_sha256,
            first_seen_object_id,
            first_seen_run_id,
            parser_version
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT ON CONSTRAINT uq_provider_source_snapshot_identity
        DO NOTHING
        RETURNING source_snapshot_id
        """,
        (
            provider_code,
            acquired_object.source_code,
            content_sha256,
            acquired_object.object_id,
            run_id,
            parser_version,
        ),
    )
    inserted_row = cursor.fetchone()
    snapshot_inserted = inserted_row is not None
    if inserted_row is None:
        cursor.execute(
            """
            SELECT source_snapshot_id
            FROM stonks.provider_source_snapshot
            WHERE provider_code = %s
              AND source_code = %s
              AND content_sha256 = %s
            """,
            (
                provider_code,
                acquired_object.source_code,
                content_sha256,
            ),
        )
        snapshot_row = cursor.fetchone()
        if snapshot_row is None:
            raise OHLCVPersistenceError(
                "Source-snapshot conflict did not return an existing identity."
            )
        source_snapshot_id = snapshot_row[0]
    else:
        source_snapshot_id = inserted_row[0]

    cursor.execute(
        """
        INSERT INTO stonks.provider_source_snapshot_object (
            source_snapshot_id,
            object_id
        )
        VALUES (%s, %s)
        ON CONFLICT ON CONSTRAINT uq_provider_source_snapshot_object_object
        DO NOTHING
        RETURNING source_snapshot_object_id
        """,
        (source_snapshot_id, acquired_object.object_id),
    )
    object_link_inserted = cursor.fetchone() is not None
    if not object_link_inserted:
        _validate_existing_object_link(
            cursor=cursor,
            object_id=acquired_object.object_id,
            source_snapshot_id=source_snapshot_id,
        )

    return SourceSnapshotRegistration(
        source_snapshot_id=source_snapshot_id,
        object_id=acquired_object.object_id,
        provider_code=provider_code,
        source_code=acquired_object.source_code,
        content_sha256=content_sha256,
        snapshot_inserted=snapshot_inserted,
        object_link_inserted=object_link_inserted,
    )


def _validate_input(
    *,
    provider_code: str,
    acquired_object: AcquiredObject,
    parser_version: str | None,
) -> str:
    if not isinstance(provider_code, str) or provider_code != provider_code.upper():
        raise OHLCVPersistenceError("provider_code must be uppercase.")
    if not provider_code or len(provider_code) > 32:
        raise OHLCVPersistenceError("provider_code must contain at most 32 characters.")
    if not isinstance(acquired_object, AcquiredObject):
        raise TypeError("acquired_object must be an AcquiredObject.")
    source_code = acquired_object.source_code
    if len(source_code) > 64 or not _SOURCE_CODE_PATTERN.fullmatch(source_code):
        raise OHLCVPersistenceError("source_code is invalid.")
    if not source_code.startswith(f"{provider_code.lower()}_"):
        raise OHLCVPersistenceError(
            "source_code must be prefixed by the lowercase provider code."
        )
    if not _CHECKSUM_PATTERN.fullmatch(acquired_object.checksum_sha256):
        raise OHLCVPersistenceError("checksum_sha256 must contain 64 hex characters.")
    if parser_version is not None and (
        len(parser_version) > 64
        or not _PARSER_VERSION_PATTERN.fullmatch(parser_version)
    ):
        raise OHLCVPersistenceError("parser_version is invalid.")
    return acquired_object.checksum_sha256.lower()


def _validate_stored_object(
    *,
    cursor: Any,
    acquired_object: AcquiredObject,
    content_sha256: str,
) -> UUID:
    cursor.execute(
        """
        SELECT
            run_id,
            object_key,
            filename,
            domain,
            logical_name,
            object_kind,
            size_bytes,
            checksum_sha256
        FROM core.stored_object
        WHERE object_id = %s
          AND deleted_at IS NULL
        FOR SHARE
        """,
        (acquired_object.object_id,),
    )
    row = cursor.fetchone()
    if row is None:
        raise OHLCVPersistenceError("Current Core raw object does not exist.")
    (
        run_id,
        object_key,
        filename,
        domain,
        logical_name,
        object_kind,
        size_bytes,
        stored_checksum,
    ) = row
    if (
        not isinstance(run_id, UUID)
        or domain != "stonks"
        or object_kind != RAW_SOURCE_OBJECT_KIND
    ):
        raise OHLCVPersistenceError("Core object is not an OHLCV run raw object.")
    if logical_name != acquired_object.source_code:
        raise OHLCVPersistenceError("Core object source code does not match.")
    if (
        object_key != acquired_object.object_key
        or filename != acquired_object.filename
        or size_bytes != acquired_object.size_bytes
    ):
        raise OHLCVPersistenceError("Core object attributes do not match acquisition.")
    if stored_checksum is None or stored_checksum.lower() != content_sha256:
        raise OHLCVPersistenceError("Core object checksum does not match acquisition.")
    return run_id


def _validate_existing_object_link(
    *,
    cursor: Any,
    object_id: UUID,
    source_snapshot_id: UUID,
) -> None:
    cursor.execute(
        """
        SELECT source_snapshot_id
        FROM stonks.provider_source_snapshot_object
        WHERE object_id = %s
        """,
        (object_id,),
    )
    row = cursor.fetchone()
    if row is None:
        raise OHLCVPersistenceError(
            "Source-snapshot object conflict did not return an existing link."
        )
    if row[0] != source_snapshot_id:
        raise OHLCVPersistenceError(
            "Core object is already linked to a different source snapshot."
        )
