from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from empire_core import ObjectStore, RunContext, StorageRoot, StoredObject
from empire_stonks_ohlcv import (
    OHLCVAcquisitionError,
    OHLCVConfig,
    RAW_SOURCE_OBJECT_KIND,
    build_raw_filename,
    build_raw_object_key,
    store_raw_bytes,
    store_raw_file,
)


RUN_ID = UUID("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee")
STORED_AT = datetime(2026, 7, 16, 14, 30, tzinfo=UTC)


class FakeObjectRepository:
    def __init__(self, base_uri: Path) -> None:
        self.root = StorageRoot(
            storage_root_id=1,
            root_name="global",
            backend_type="filesystem",
            base_uri=str(base_uri),
        )
        self.objects: dict[UUID, StoredObject] = {}

    def get_storage_root(self, root_name: str) -> StorageRoot | None:
        return self.root if root_name == self.root.root_name else None

    def insert_object(self, **values: object) -> StoredObject:
        stored = StoredObject(
            object_id=uuid4(),
            run_id=values["run_id"],
            storage_root_id=values["storage_root_id"],
            storage_root_name=self.root.root_name,
            base_uri=self.root.base_uri,
            object_key=values["object_key"],
            filename=values["filename"],
            object_scope=values["object_scope"],
            domain=values["domain"],
            logical_name=values["logical_name"],
            content_type=values["content_type"],
            object_kind=values["object_kind"],
            size_bytes=values["size_bytes"],
            checksum_sha256=values["checksum_sha256"],
            expires_at=values["expires_at"],
            deleted_at=None,
            purge_after=None,
            metadata=values["metadata"],
            created_at=STORED_AT,
            updated_at=STORED_AT,
        )
        self.objects[stored.object_id] = stored
        return stored

    def get_object(self, object_id: UUID) -> StoredObject | None:
        return self.objects.get(object_id)


def _run_context(**overrides: object) -> RunContext:
    values = {
        "run_id": RUN_ID,
        "domain": "stonks",
        "job_name": "stonks_ohlcv_eoddata_daily",
        "subject_key": "all_series",
        "effective_date": date(2026, 7, 15),
        "run_type": "cli",
        "status": "started",
        "runner": "pytest",
    }
    values.update(overrides)
    return RunContext(**values)


def _store(tmp_path: Path) -> tuple[ObjectStore, FakeObjectRepository]:
    repository = FakeObjectRepository(tmp_path)
    return ObjectStore(repository), repository


def test_builds_contract_key_and_raw_filenames() -> None:
    run_context = _run_context()

    assert build_raw_object_key(
        storage_key="/stonks/ohlcv/",
        provider_code="EODDATA",
        run_context=run_context,
        source_code="eoddata_daily",
    ) == (
        "stonks/ohlcv/eoddata/runs/2026/07/15/"
        "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee/eoddata_daily"
    )
    assert build_raw_filename(format_suffix="json") == "raw.json"
    assert build_raw_filename(
        format_suffix="csv.gz",
        part_key="2026-q1",
    ) == "raw-2026-q1.csv.gz"


def test_stores_bytes_with_core_checksum_metadata_and_expiration(
    tmp_path: Path,
) -> None:
    object_store, repository = _store(tmp_path)
    payload = b"date,open,high,low,close\n2026-07-15,1,2,1,2\n"

    acquired = store_raw_bytes(
        object_store=object_store,
        run_context=_run_context(),
        config=OHLCVConfig(raw_retention_days=7),
        provider_code="EODDATA",
        source_code="eoddata_daily",
        format_suffix="csv",
        data=payload,
        content_type="text/csv",
        parser_version="1.0.0",
        provider_metadata={
            "etag": '"source-etag"',
            "http_status": 200,
        },
        clock=lambda: STORED_AT,
    )

    stored = repository.objects[acquired.object_id]
    assert acquired.object_key.endswith("/eoddata_daily")
    assert acquired.filename == "raw.csv"
    assert acquired.size_bytes == len(payload)
    assert acquired.checksum_sha256 == hashlib.sha256(payload).hexdigest()
    assert object_store.get_bytes(acquired.object_id) == payload
    assert stored.run_id == RUN_ID
    assert stored.object_scope == "run"
    assert stored.domain == "stonks"
    assert stored.logical_name == "eoddata_daily"
    assert stored.object_kind == RAW_SOURCE_OBJECT_KIND
    assert stored.content_type == "text/csv"
    assert stored.expires_at == STORED_AT + timedelta(days=7)
    assert stored.metadata == {
        "schema_version": 1,
        "provider_code": "EODDATA",
        "source_code": "eoddata_daily",
        "effective_date": "2026-07-15",
        "acquired_at": "2026-07-16T14:30:00+00:00",
        "retention_days": 7,
        "parser_version": "1.0.0",
        "etag": '"source-etag"',
        "http_status": 200,
    }
    assert len(repository.objects) == 1


def test_stores_file_without_loading_it_and_moves_by_default(tmp_path: Path) -> None:
    object_store, repository = _store(tmp_path / "objects")
    source_path = tmp_path / "download" / "provider.zip"
    source_path.parent.mkdir()
    source_path.write_bytes(b"provider archive")

    acquired = store_raw_file(
        object_store=object_store,
        run_context=_run_context(),
        config=OHLCVConfig(raw_retention_days=3),
        provider_code="STOOQ",
        source_code="stooq_history",
        format_suffix="zip",
        part_key="2026-q1",
        source_path=source_path,
        content_type="application/zip",
        clock=lambda: STORED_AT,
    )

    stored = repository.objects[acquired.object_id]
    assert not source_path.exists()
    assert acquired.filename == "raw-2026-q1.zip"
    assert acquired.checksum_sha256 == hashlib.sha256(b"provider archive").hexdigest()
    assert stored.expires_at == STORED_AT + timedelta(days=3)
    assert object_store.get_bytes(acquired.object_id) == b"provider archive"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"provider_code": "eoddata"}, "provider_code must be uppercase"),
        ({"source_code": "daily"}, "prefixed"),
        ({"source_code": "eoddata/daily"}, "path-safe"),
        ({"run_context": _run_context(domain="weather")}, "domain"),
        ({"run_context": _run_context(status="succeeded")}, "active"),
        ({"run_context": _run_context(effective_date=None)}, "effective_date"),
    ],
)
def test_rejects_invalid_identity_or_run_context(
    tmp_path: Path,
    kwargs: dict[str, object],
    message: str,
) -> None:
    values = {
        "object_store": _store(tmp_path)[0],
        "run_context": _run_context(),
        "config": OHLCVConfig(),
        "provider_code": "EODDATA",
        "source_code": "eoddata_daily",
        "format_suffix": "json",
        "data": b"{}",
        "content_type": "application/json",
        "clock": lambda: STORED_AT,
    }
    values.update(kwargs)

    with pytest.raises(OHLCVAcquisitionError, match=message):
        store_raw_bytes(**values)


def test_rejects_unsafe_filename_storage_key_clock_and_metadata(
    tmp_path: Path,
) -> None:
    object_store, _ = _store(tmp_path)
    common = {
        "object_store": object_store,
        "run_context": _run_context(),
        "provider_code": "EODDATA",
        "source_code": "eoddata_daily",
        "format_suffix": "json",
        "data": b"{}",
        "content_type": "application/json",
        "clock": lambda: STORED_AT,
    }

    with pytest.raises(OHLCVAcquisitionError, match="storage_key"):
        store_raw_bytes(config=OHLCVConfig(storage_key="stonks//ohlcv"), **common)
    with pytest.raises(OHLCVAcquisitionError, match="format_suffix"):
        store_raw_bytes(
            config=OHLCVConfig(),
            **{**common, "format_suffix": "../../json"},
        )
    with pytest.raises(OHLCVAcquisitionError, match="timezone-aware"):
        store_raw_bytes(
            config=OHLCVConfig(),
            **{**common, "clock": lambda: datetime(2026, 7, 16)},
        )
    with pytest.raises(OHLCVAcquisitionError, match="unsupported keys") as error:
        store_raw_bytes(
            config=OHLCVConfig(),
            provider_metadata={"api_key": "do-not-print-this-secret"},
            **common,
        )
    assert "do-not-print-this-secret" not in str(error.value)
