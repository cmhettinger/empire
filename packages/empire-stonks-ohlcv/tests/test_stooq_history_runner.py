from __future__ import annotations

import io
import json
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

import empire_stonks_ohlcv.stooq_history_runner as stooq_runner
import empire_stonks_ohlcv.stooq_history_writer as stooq_writer
from empire_core import ObjectStore, RunContext, RunService, StorageRoot, StoredObject
from empire_stonks_ohlcv import (
    OHLCVConfig,
    OHLCVWorkflowError,
    PersistenceCounts,
    ProviderListingWriteResult,
    ResolvedProviderListing,
    SourceSnapshotRegistration,
    StooqHistoryScope,
    run_stooq_history_backfill,
)


EFFECTIVE_DATE = date(2026, 7, 18)
HEADER = (
    "<TICKER>,<PER>,<DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,"
    "<VOL>,<OPENINT>\n"
)


class FakeRunRepository:
    def __init__(self) -> None:
        self.runs: dict[UUID, RunContext] = {}
        self.runner_refs: dict[UUID, dict[str, object]] = {}
        self.failure_messages: dict[UUID, str] = {}
        self.heartbeat_count = 0

    def start_run(self, **values: object) -> RunContext:
        context = RunContext(
            run_id=uuid4(),
            domain=values["domain"],  # type: ignore[arg-type]
            job_name=values["job_name"],  # type: ignore[arg-type]
            subject_key=values["subject_key"],  # type: ignore[arg-type]
            effective_date=values["effective_date"],  # type: ignore[arg-type]
            run_type=values["run_type"],  # type: ignore[arg-type]
            status="started",
            runner=values["runner"],  # type: ignore[arg-type]
            params=values["params"],  # type: ignore[arg-type]
            heartbeat_timeout_seconds=values[  # type: ignore[arg-type]
                "heartbeat_timeout_seconds"
            ],
            started_at=datetime.now(UTC),
        )
        self.runs[context.run_id] = context
        self.runner_refs[context.run_id] = values[  # type: ignore[assignment]
            "runner_ref"
        ]
        return context

    def complete_run(
        self,
        run_id: UUID,
        summary: dict[str, object] | None,
    ) -> RunContext:
        context = replace(
            self.runs[run_id],
            status="succeeded",
            summary=summary or {},
            completed_at=datetime.now(UTC),
        )
        self.runs[run_id] = context
        return context

    def fail_run(
        self,
        run_id: UUID,
        error_message: str,
        summary: dict[str, object] | None,
    ) -> RunContext:
        context = replace(
            self.runs[run_id],
            status="failed",
            summary=summary or {},
            completed_at=datetime.now(UTC),
        )
        self.runs[run_id] = context
        self.failure_messages[run_id] = error_message
        return context

    def heartbeat(self, run_id: UUID) -> RunContext:
        self.heartbeat_count += 1
        return self.runs[run_id]


class FakeObjectRepository:
    def __init__(self, root: Path) -> None:
        self.root = StorageRoot(1, "global", "filesystem", str(root))
        self.objects: dict[UUID, StoredObject] = {}

    def get_storage_root(self, root_name: str) -> StorageRoot | None:
        return self.root if root_name == "global" else None

    def insert_object(self, **values: object) -> StoredObject:
        stored = StoredObject(
            object_id=uuid4(),
            run_id=values["run_id"],  # type: ignore[arg-type]
            storage_root_id=1,
            storage_root_name="global",
            base_uri=self.root.base_uri,
            object_key=values["object_key"],  # type: ignore[arg-type]
            filename=values["filename"],  # type: ignore[arg-type]
            object_scope=values["object_scope"],  # type: ignore[arg-type]
            domain=values["domain"],  # type: ignore[arg-type]
            logical_name=values["logical_name"],  # type: ignore[arg-type]
            content_type=values["content_type"],  # type: ignore[arg-type]
            object_kind=values["object_kind"],  # type: ignore[arg-type]
            size_bytes=values["size_bytes"],  # type: ignore[arg-type]
            checksum_sha256=values["checksum_sha256"],  # type: ignore[arg-type]
            expires_at=values["expires_at"],  # type: ignore[arg-type]
            deleted_at=None,
            purge_after=None,
            metadata=values["metadata"],  # type: ignore[arg-type]
        )
        self.objects[stored.object_id] = stored
        return stored

    def get_object(self, object_id: UUID) -> StoredObject | None:
        return self.objects.get(object_id)


class FakeCursor:
    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class FakeConnection:
    def __init__(self) -> None:
        self.commit_calls = 0
        self.rollback_calls = 0

    def cursor(self) -> FakeCursor:
        return FakeCursor()

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1


def _archive(tmp_path: Path) -> Path:
    output = io.BytesIO()
    members = {
        "data/daily/us/nasdaq stocks/1/aaa.us.txt": (
            HEADER
            + "AAA.US,D,20260102,000000,10,11,9,10.5,100,0\n"
            + "AAA.US,D,20260105,000000,11,12,10,11.5,110,0\n"
        ),
        "data/daily/us/nyse stocks/2/bbb.us.txt": (
            HEADER + "BBB.US,D,20260102,000000,20,21,19,20.5,200,0\n"
        ),
        "data/daily/us/nysemkt stocks/ccc.us.txt": (
            HEADER + "CCC.US,D,20260102,000000,30,31,29,30.5,300,0\n"
        ),
    }
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for member_path, content in members.items():
            archive.writestr(member_path, content)
    path = tmp_path / "d_us_txt.zip"
    path.write_bytes(output.getvalue())
    return path


def _install_persistence(
    monkeypatch: pytest.MonkeyPatch,
    *,
    fail_bar_call: int | None = None,
) -> None:
    def register(**values: object) -> SourceSnapshotRegistration:
        acquired = values["acquired_object"]
        return SourceSnapshotRegistration(
            source_snapshot_id=UUID(int=500),
            object_id=acquired.object_id,  # type: ignore[union-attr]
            provider_code="STOOQ",
            source_code="stooq_history",
            content_sha256=acquired.checksum_sha256,  # type: ignore[union-attr]
            snapshot_inserted=True,
            object_link_inserted=True,
        )

    def listings(**values: object) -> ProviderListingWriteResult:
        prepared = tuple(values["listings"])  # type: ignore[arg-type]
        return ProviderListingWriteResult(
            resolved=tuple(
                ResolvedProviderListing(
                    listing=listing,
                    provider_listing_id=UUID(int=index + 1),
                    outcome="inserted",
                )
                for index, listing in enumerate(prepared)
            )
        )

    bar_calls = 0

    def bars(**values: object) -> PersistenceCounts:
        nonlocal bar_calls
        bar_calls += 1
        if bar_calls == fail_bar_call:
            raise RuntimeError("forced persistence detail")
        prepared = tuple(values["bars"])  # type: ignore[arg-type]
        return PersistenceCounts(inserted=len(prepared))

    monkeypatch.setattr(stooq_runner, "upsert_provider_source_snapshot", register)
    monkeypatch.setattr(stooq_writer, "upsert_provider_listings", listings)
    monkeypatch.setattr(stooq_writer, "upsert_daily_bars", bars)


def _services(tmp_path: Path) -> tuple[
    FakeRunRepository,
    RunService,
    FakeObjectRepository,
    ObjectStore,
]:
    run_repository = FakeRunRepository()
    object_repository = FakeObjectRepository(tmp_path / "objects")
    return (
        run_repository,
        RunService(run_repository),
        object_repository,
        ObjectStore(object_repository),
    )


def test_runner_tracks_stored_archive_snapshot_chunks_and_safe_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_persistence(monkeypatch)
    run_repo, run_service, object_repo, object_store = _services(tmp_path)
    connection = FakeConnection()
    input_path = _archive(tmp_path)
    progress: list[dict[str, object]] = []

    result = run_stooq_history_backfill(
        run_service=run_service,
        connection=connection,
        object_store=object_store,
        config=OHLCVConfig(raw_retention_days=5),
        input_path=input_path,
        scope=StooqHistoryScope(effective_date=EFFECTIVE_DATE),
        chunk_size=2,
        run_type="cli",
        runner="pytest",
        runner_ref={"command": "test"},
        progress_sink=progress.append,
    )

    assert input_path.exists()
    stored = object_repo.objects[result.acquired_object.object_id]
    assert stored.filename == "raw.zip"
    assert object_store.get_path(stored.object_id).is_file()
    assert object_store.get_path(stored.object_id) != input_path
    assert stored.metadata["request_scope"] == "us_stocks"
    assert connection.commit_calls == 3
    assert connection.rollback_calls == 0
    assert result.status == "succeeded"
    assert result.parse_summary.files_completed == 3
    assert result.parse_summary.accepted_records == 4
    assert result.write_summary.chunks_completed == 2
    assert result.write_summary.bar_counts.inserted == 4
    assert [item["stage"] for item in progress] == [
        "acquisition",
        "parsing",
        "persistence",
        "persistence",
    ]
    assert run_repo.heartbeat_count == 4

    run = run_repo.runs[result.run_id]
    assert run.job_name == "stonks_ohlcv_stooq_backfill"
    assert run.subject_key == "us_stocks"
    assert run.heartbeat_timeout_seconds == 900
    assert run.params["scope"] == {
        "effective_date": "2026-07-18",
        "start_date": None,
        "end_date": None,
        "markets": ["nasdaq", "nyse", "nysemkt"],
        "tickers": [],
    }
    assert "input_path" not in run.params
    assert run.summary["acquired_object"]["checksum_sha256"] == (
        result.acquired_object.checksum_sha256
    )
    json.dumps(result.to_dict())
    json.dumps(run.summary)


def test_failure_summary_preserves_exact_rerun_scope_and_committed_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_persistence(monkeypatch, fail_bar_call=2)
    run_repo, run_service, _object_repo, object_store = _services(tmp_path)
    connection = FakeConnection()
    scope = StooqHistoryScope(
        effective_date=EFFECTIVE_DATE,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        markets=("nasdaq", "nyse"),
        tickers=("AAA.US", "BBB.US"),
    )

    with pytest.raises(OHLCVWorkflowError) as raised:
        run_stooq_history_backfill(
            run_service=run_service,
            connection=connection,
            object_store=object_store,
            config=OHLCVConfig(),
            input_path=_archive(tmp_path),
            scope=scope,
            chunk_size=2,
            run_type="cli",
            runner="pytest",
        )

    run = next(iter(run_repo.runs.values()))
    assert run.status == "failed"
    assert run_repo.failure_messages[run.run_id] == "OHLCV provider run failed."
    assert str(raised.value) == "OHLCV provider workflow failed during persistence."
    assert run.summary["failed_stage"] == "persistence"
    assert run.summary["scope"] == scope.to_dict()
    assert run.summary["chunk_size"] == 2
    assert run.summary["acquired_object"]["checksum_sha256"]
    assert run.summary["source_snapshot"]["source_snapshot_id"] == str(UUID(int=500))
    assert run.summary["write_summary"]["chunks_completed"] == 1
    assert run.summary["write_summary"]["chunks_failed"] == 1
    assert run.summary["write_summary"]["last_completed_chunk"] == 1
    assert connection.commit_calls == 2
    assert connection.rollback_calls >= 2
    assert "forced persistence detail" not in repr(run.summary)


def test_invalid_input_does_not_start_core_run(tmp_path: Path) -> None:
    run_repo, run_service, _object_repo, object_store = _services(tmp_path)

    with pytest.raises(Exception, match="existing regular file"):
        run_stooq_history_backfill(
            run_service=run_service,
            connection=FakeConnection(),
            object_store=object_store,
            config=OHLCVConfig(),
            input_path=tmp_path / "d_us_txt.zip",
            scope=StooqHistoryScope(effective_date=EFFECTIVE_DATE),
            chunk_size=100,
            run_type="cli",
            runner="pytest",
        )

    assert run_repo.runs == {}
