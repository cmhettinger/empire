from __future__ import annotations

from uuid import UUID

import pytest

from empire_stonks_ohlcv import (
    AcquiredObject,
    OHLCVPersistenceError,
    RAW_SOURCE_OBJECT_KIND,
    upsert_provider_source_snapshot,
)


OBJECT_ID = UUID("10000000-0000-4000-8000-000000000001")
SECOND_OBJECT_ID = UUID("10000000-0000-4000-8000-000000000002")
RUN_ID = UUID("20000000-0000-4000-8000-000000000001")
CHECKSUM = "ab" * 32


class FakeSourceSnapshotCursor:
    """Focused in-memory cursor for source-snapshot SQL behavior."""

    def __init__(self) -> None:
        self.objects: dict[UUID, tuple[object, ...]] = {}
        self.snapshots: dict[tuple[str, str, str], UUID] = {}
        self.links: dict[UUID, UUID] = {}
        self.snapshot_inserts = 0
        self.link_inserts = 0
        self._next_snapshot_id = 1
        self._result: tuple[object, ...] | None = None

    def add_object(
        self,
        acquired: AcquiredObject,
        *,
        checksum: str | None = None,
    ) -> None:
        self.objects[acquired.object_id] = (
            RUN_ID,
            acquired.object_key,
            acquired.filename,
            "stonks",
            acquired.source_code,
            RAW_SOURCE_OBJECT_KIND,
            acquired.size_bytes,
            checksum or acquired.checksum_sha256,
        )

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        if "FROM core.stored_object" in query:
            self._result = self.objects.get(params[0])  # type: ignore[arg-type]
            return
        if "INSERT INTO stonks.provider_source_snapshot_object" in query:
            source_snapshot_id, object_id = params
            if object_id in self.links:
                self._result = None
            else:
                assert isinstance(object_id, UUID)
                assert isinstance(source_snapshot_id, UUID)
                self.links[object_id] = source_snapshot_id
                self.link_inserts += 1
                self._result = (UUID(int=self.link_inserts),)
            return
        if "INSERT INTO stonks.provider_source_snapshot" in query:
            key = (str(params[0]), str(params[1]), str(params[2]))
            if key in self.snapshots:
                self._result = None
            else:
                source_snapshot_id = UUID(int=self._next_snapshot_id)
                self._next_snapshot_id += 1
                self.snapshots[key] = source_snapshot_id
                self.snapshot_inserts += 1
                self._result = (source_snapshot_id,)
            return
        if "FROM stonks.provider_source_snapshot_object" in query:
            source_snapshot_id = self.links.get(params[0])  # type: ignore[arg-type]
            self._result = (
                None if source_snapshot_id is None else (source_snapshot_id,)
            )
            return
        if "FROM stonks.provider_source_snapshot" in query:
            key = (str(params[0]), str(params[1]), str(params[2]))
            source_snapshot_id = self.snapshots.get(key)
            self._result = (
                None if source_snapshot_id is None else (source_snapshot_id,)
            )
            return
        raise AssertionError(f"Unexpected SQL: {query}")

    def fetchone(self) -> tuple[object, ...] | None:
        return self._result


def acquired_object(
    *,
    object_id: UUID = OBJECT_ID,
    checksum: str = CHECKSUM,
) -> AcquiredObject:
    return AcquiredObject(
        source_code="eoddata_daily",
        object_id=object_id,
        object_key=f"stonks/ohlcv/eoddata/runs/2026/07/16/run/{object_id}",
        filename="raw.csv",
        size_bytes=42,
        checksum_sha256=checksum,
    )


def test_inserts_snapshot_and_current_object_link() -> None:
    cursor = FakeSourceSnapshotCursor()
    acquired = acquired_object()
    cursor.add_object(acquired)

    result = upsert_provider_source_snapshot(
        cursor=cursor,
        provider_code="EODDATA",
        acquired_object=acquired,
        parser_version="1.0.0",
    )

    assert result.snapshot_inserted is True
    assert result.object_link_inserted is True
    assert result.content_sha256 == CHECKSUM
    assert result.to_dict() == {
        "source_snapshot_id": str(result.source_snapshot_id),
        "object_id": str(OBJECT_ID),
        "provider_code": "EODDATA",
        "source_code": "eoddata_daily",
        "content_sha256": CHECKSUM,
        "snapshot_inserted": True,
        "object_link_inserted": True,
    }
    assert cursor.snapshot_inserts == 1
    assert cursor.link_inserts == 1


def test_rerun_reuses_snapshot_and_link() -> None:
    cursor = FakeSourceSnapshotCursor()
    acquired = acquired_object()
    cursor.add_object(acquired)
    first = upsert_provider_source_snapshot(
        cursor=cursor,
        provider_code="EODDATA",
        acquired_object=acquired,
    )

    rerun = upsert_provider_source_snapshot(
        cursor=cursor,
        provider_code="EODDATA",
        acquired_object=acquired,
    )

    assert rerun.source_snapshot_id == first.source_snapshot_id
    assert rerun.snapshot_inserted is False
    assert rerun.object_link_inserted is False
    assert cursor.snapshot_inserts == 1
    assert cursor.link_inserts == 1


def test_same_content_from_new_object_adds_membership_to_same_snapshot() -> None:
    cursor = FakeSourceSnapshotCursor()
    first_object = acquired_object()
    second_object = acquired_object(object_id=SECOND_OBJECT_ID)
    cursor.add_object(first_object)
    cursor.add_object(second_object)
    first = upsert_provider_source_snapshot(
        cursor=cursor,
        provider_code="EODDATA",
        acquired_object=first_object,
    )

    second = upsert_provider_source_snapshot(
        cursor=cursor,
        provider_code="EODDATA",
        acquired_object=second_object,
    )

    assert second.source_snapshot_id == first.source_snapshot_id
    assert second.snapshot_inserted is False
    assert second.object_link_inserted is True
    assert cursor.snapshot_inserts == 1
    assert cursor.link_inserts == 2


def test_rejects_object_already_linked_to_different_snapshot() -> None:
    cursor = FakeSourceSnapshotCursor()
    acquired = acquired_object()
    cursor.add_object(acquired)
    cursor.links[OBJECT_ID] = UUID(int=999)

    with pytest.raises(OHLCVPersistenceError, match="different source snapshot"):
        upsert_provider_source_snapshot(
            cursor=cursor,
            provider_code="EODDATA",
            acquired_object=acquired,
        )


@pytest.mark.parametrize(
    ("provider_code", "acquired", "message"),
    [
        ("eoddata", acquired_object(), "uppercase"),
        ("YAHOO", acquired_object(), "prefixed"),
        ("EODDATA", acquired_object(checksum="not-a-checksum"), "64 hex"),
    ],
)
def test_rejects_invalid_identity_before_sql(
    provider_code: str,
    acquired: AcquiredObject,
    message: str,
) -> None:
    cursor = FakeSourceSnapshotCursor()

    with pytest.raises(OHLCVPersistenceError, match=message):
        upsert_provider_source_snapshot(
            cursor=cursor,
            provider_code=provider_code,
            acquired_object=acquired,
        )

    assert cursor.snapshot_inserts == 0


def test_rejects_missing_or_mismatched_core_object() -> None:
    cursor = FakeSourceSnapshotCursor()
    acquired = acquired_object()

    with pytest.raises(OHLCVPersistenceError, match="does not exist"):
        upsert_provider_source_snapshot(
            cursor=cursor,
            provider_code="EODDATA",
            acquired_object=acquired,
        )

    cursor.add_object(acquired, checksum="cd" * 32)
    with pytest.raises(OHLCVPersistenceError, match="checksum"):
        upsert_provider_source_snapshot(
            cursor=cursor,
            provider_code="EODDATA",
            acquired_object=acquired,
        )
