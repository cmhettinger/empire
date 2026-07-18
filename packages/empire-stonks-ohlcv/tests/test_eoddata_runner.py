from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

import empire_stonks_ohlcv.eoddata_runner as eoddata_runner
from empire_core import ObjectStore, RunContext, RunService, StorageRoot, StoredObject
from empire_stonks_ohlcv import (
    AcquiredObject,
    BoundedIssueSummary,
    CrossFeedOutcomeCounts,
    EODDATA_DAILY_SOURCE,
    EODDATA_SYMBOL_LIST_SOURCE,
    EODDataCredentials,
    EODDataImportResult,
    FeedOutcomeCounts,
    OHLCVConfig,
    OHLCVConfigError,
    OHLCVWorkflowError,
    PersistenceCounts,
    SAFE_FAILURE_MESSAGE,
    SourceMarketWriteCounts,
    SourceSnapshotRegistration,
    run_eoddata_daily,
)


EFFECTIVE_DATE = date(2026, 7, 15)
MARKETS = ("NYSE", "NASDAQ", "AMEX")
SECRET = "eoddata-runner-secret"


class FakeRunRepository:
    def __init__(self) -> None:
        self.runs: dict[UUID, RunContext] = {}
        self.runner_refs: dict[UUID, dict[str, object]] = {}
        self.failure_messages: dict[UUID, str] = {}
        self.events: list[str] = []

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
            started_at=datetime.now(UTC),
        )
        self.runs[context.run_id] = context
        self.runner_refs[context.run_id] = values[  # type: ignore[assignment]
            "runner_ref"
        ]
        self.events.append("start")
        return context

    def complete_run(
        self,
        run_id: UUID,
        summary: dict[str, object] | None,
    ) -> RunContext:
        completed = replace(
            self.runs[run_id],
            status="succeeded",
            summary=summary or {},
            completed_at=datetime.now(UTC),
        )
        self.runs[run_id] = completed
        self.events.append("complete")
        return completed

    def fail_run(
        self,
        run_id: UUID,
        error_message: str,
        summary: dict[str, object] | None,
    ) -> RunContext:
        failed = replace(
            self.runs[run_id],
            status="failed",
            summary=summary or {},
            completed_at=datetime.now(UTC),
        )
        self.runs[run_id] = failed
        self.failure_messages[run_id] = error_message
        self.events.append("fail")
        return failed


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
        self.rollback_calls = 0
        self.commit_calls = 0

    def cursor(self) -> FakeCursor:
        return FakeCursor()

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1


def _config() -> OHLCVConfig:
    return OHLCVConfig(
        eoddata_credentials=EODDataCredentials(api_key=SECRET),
    )


def _acquired_objects() -> tuple[AcquiredObject, ...]:
    objects = []
    number = 1
    for source in (EODDATA_SYMBOL_LIST_SOURCE, EODDATA_DAILY_SOURCE):
        for market in MARKETS:
            objects.append(
                AcquiredObject(
                    source_code=source.source_code,
                    object_id=UUID(int=number),
                    object_key=f"raw/{source.source_code}/{market.lower()}",
                    filename=f"raw-{market.lower()}.json",
                    size_bytes=number,
                    checksum_sha256=f"{number:064x}",
                )
            )
            number += 1
    return tuple(objects)


def _import_result() -> EODDataImportResult:
    acquired = _acquired_objects()
    snapshots = tuple(
        SourceSnapshotRegistration(
            source_snapshot_id=UUID(int=100 + index),
            object_id=item.object_id,
            provider_code="EODDATA",
            source_code=item.source_code,
            content_sha256=item.checksum_sha256,
            snapshot_inserted=True,
            object_link_inserted=True,
        )
        for index, item in enumerate(acquired, start=1)
    )
    feed_counts = tuple(
        FeedOutcomeCounts(
            source_code=source.source_code,
            market=market,
            input_rows=1,
            accepted_records=1,
        )
        for source in (EODDATA_SYMBOL_LIST_SOURCE, EODDATA_DAILY_SOURCE)
        for market in MARKETS
    )
    write_counts = tuple(
        SourceMarketWriteCounts(
            source_code=source.source_code,
            market=market,
            record_kind=(
                "listing" if source == EODDATA_SYMBOL_LIST_SOURCE else "bar"
            ),
            counts=PersistenceCounts(unchanged=1),
        )
        for source in (EODDATA_SYMBOL_LIST_SOURCE, EODDATA_DAILY_SOURCE)
        for market in MARKETS
    )
    return EODDataImportResult(
        effective_date=EFFECTIVE_DATE,
        acquired_objects=acquired,
        source_snapshots=snapshots,
        feed_counts=feed_counts,
        write_counts=write_counts,
        row_rejections=(),
        failures=BoundedIssueSummary(),
        warnings=BoundedIssueSummary(),
        cross_feed_counts=tuple(
            CrossFeedOutcomeCounts(market=market) for market in MARKETS
        ),
    )


def _stored_report(run_id: UUID | None = None) -> StoredObject:
    return StoredObject(
        object_id=uuid4(),
        run_id=run_id,
        storage_root_id=1,
        storage_root_name="global",
        base_uri="/tmp",
        object_key="stonks/ohlcv/eoddata/run/reports",
        filename="report.json",
        object_scope="run",
        domain="stonks",
        logical_name="eoddata_daily_report",
        content_type="application/json",
        object_kind="stonks_ohlcv_provider_report",
        size_bytes=100,
        checksum_sha256="ab" * 32,
        expires_at=None,
        deleted_at=None,
        purge_after=None,
    )


def _install_success(
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
) -> None:
    monkeypatch.setattr(
        eoddata_runner,
        "acquire_eoddata_objects",
        lambda **_values: events.append("acquire") or _acquired_objects(),
    )
    monkeypatch.setattr(
        eoddata_runner,
        "_parse",
        lambda **_values: events.append("parse") or (object(), object(), object()),
    )
    monkeypatch.setattr(
        eoddata_runner,
        "import_eoddata_daily",
        lambda **_values: events.append("persist") or _import_result(),
    )
    monkeypatch.setattr(
        eoddata_runner,
        "build_eoddata_report",
        lambda **_values: events.append("build_report")
        or {"outcome": "PASS", "hard_failures": {"total_count": 0}},
    )
    monkeypatch.setattr(
        eoddata_runner,
        "store_eoddata_report",
        lambda **values: events.append("store_report")
        or _stored_report(values["run_context"].run_id),
    )


def test_daily_runner_sequences_and_returns_only_compact_safe_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = FakeRunRepository()
    events: list[str] = []
    _install_success(monkeypatch, events)

    result = run_eoddata_daily(
        run_service=RunService(repository),
        connection=FakeConnection(),
        object_store=ObjectStore(FakeObjectRepository(tmp_path)),
        config=_config(),
        effective_date=EFFECTIVE_DATE,
        run_type="cli",
        runner="pytest",
        runner_ref={"command": "test"},
        sleep=lambda _delay: None,
    )

    assert events == [
        "acquire",
        "parse",
        "persist",
        "build_report",
        "store_report",
    ]
    assert repository.events == ["start", "complete"]
    assert result.status == "succeeded"
    assert result.report_outcome == "PASS"
    assert result.listing_counts == PersistenceCounts(unchanged=3)
    assert result.bar_counts == PersistenceCounts(unchanged=3)
    summary = repository.runs[result.run_id].summary
    assert summary["acquired_object_count"] == 6
    assert summary["source_snapshot_count"] == 6
    assert summary["report_object_id"] == str(result.report_object_id)
    assert result.to_dict()["provider_code"] == "EODDATA"
    serialized = repr(
        {
            "result": result.to_dict(),
            "params": repository.runs[result.run_id].params,
            "summary": summary,
            "runner_ref": repository.runner_refs[result.run_id],
        }
    )
    assert SECRET not in serialized


def test_invalid_configuration_does_not_start_core_run(tmp_path: Path) -> None:
    repository = FakeRunRepository()

    with pytest.raises(OHLCVConfigError, match="API_KEY"):
        run_eoddata_daily(
            run_service=RunService(repository),
            connection=FakeConnection(),
            object_store=ObjectStore(FakeObjectRepository(tmp_path)),
            config=OHLCVConfig(),
            effective_date=EFFECTIVE_DATE,
            run_type="cli",
            runner="pytest",
        )

    assert repository.runs == {}


@pytest.mark.parametrize(
    "stage",
    ("acquisition", "parsing", "persistence", "reporting"),
)
def test_daily_runner_records_safe_stage_for_each_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    repository = FakeRunRepository()
    events: list[str] = []
    _install_success(monkeypatch, events)

    if stage == "acquisition":
        monkeypatch.setattr(
            eoddata_runner,
            "acquire_eoddata_objects",
            lambda **_values: (_ for _ in ()).throw(RuntimeError(SECRET)),
        )
    elif stage == "parsing":
        monkeypatch.setattr(
            eoddata_runner,
            "_parse",
            lambda **_values: (_ for _ in ()).throw(
                OHLCVWorkflowError("parsing")
            ),
        )
    elif stage == "persistence":
        monkeypatch.setattr(
            eoddata_runner,
            "import_eoddata_daily",
            lambda **_values: (_ for _ in ()).throw(RuntimeError(SECRET)),
        )
    else:
        monkeypatch.setattr(
            eoddata_runner,
            "build_eoddata_report",
            lambda **_values: (_ for _ in ()).throw(RuntimeError(SECRET)),
        )

    with pytest.raises(OHLCVWorkflowError) as error:
        run_eoddata_daily(
            run_service=RunService(repository),
            connection=FakeConnection(),
            object_store=ObjectStore(FakeObjectRepository(tmp_path)),
            config=_config(),
            effective_date=EFFECTIVE_DATE,
            run_type="cli",
            runner="pytest",
            sleep=lambda _delay: None,
        )

    assert error.value.stage == stage
    failed = next(iter(repository.runs.values()))
    assert failed.status == "failed"
    assert failed.summary == {
        "provider_code": "EODDATA",
        "outcome": "failed",
        "failed_stage": stage,
    }
    assert repository.failure_messages[failed.run_id] == SAFE_FAILURE_MESSAGE
    assert SECRET not in repr(failed)


def test_acquisition_failure_keeps_partial_raw_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_repository = FakeRunRepository()
    object_repository = FakeObjectRepository(tmp_path)
    object_store = ObjectStore(object_repository)

    def partial_acquisition(**values: object) -> tuple[AcquiredObject, ...]:
        object_store.put_bytes(
            run_context=values["run_context"],  # type: ignore[arg-type]
            storage_root="global",
            object_key="stonks/ohlcv/eoddata/partial",
            filename="raw-nyse.json",
            data=b"[]",
            object_scope="run",
            domain="stonks",
            logical_name="eoddata_symbol_list",
            content_type="application/json",
            object_kind="stonks_ohlcv_raw_source",
        )
        raise RuntimeError(SECRET)

    monkeypatch.setattr(
        eoddata_runner,
        "acquire_eoddata_objects",
        partial_acquisition,
    )

    with pytest.raises(OHLCVWorkflowError, match="acquisition"):
        run_eoddata_daily(
            run_service=RunService(run_repository),
            connection=FakeConnection(),
            object_store=object_store,
            config=_config(),
            effective_date=EFFECTIVE_DATE,
            run_type="cli",
            runner="pytest",
            sleep=lambda _delay: None,
        )

    assert len(object_repository.objects) == 1
    stored = next(iter(object_repository.objects.values()))
    assert object_store.get_bytes(stored.object_id) == b"[]"
    assert stored.run_id == next(iter(run_repository.runs))


def test_daily_runner_records_safe_market_and_source_for_partition_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = FakeRunRepository()
    events: list[str] = []
    _install_success(monkeypatch, events)
    monkeypatch.setattr(
        eoddata_runner,
        "_parse",
        lambda **_values: (_ for _ in ()).throw(
            OHLCVWorkflowError(
                "parsing",
                market="AMEX",
                source_code="eoddata_daily",
            )
        ),
    )

    with pytest.raises(OHLCVWorkflowError):
        run_eoddata_daily(
            run_service=RunService(repository),
            connection=FakeConnection(),
            object_store=ObjectStore(FakeObjectRepository(tmp_path)),
            config=_config(),
            effective_date=EFFECTIVE_DATE,
            run_type="cli",
            runner="pytest",
            sleep=lambda _delay: None,
        )

    failed = next(iter(repository.runs.values()))
    assert failed.summary == {
        "provider_code": "EODDATA",
        "outcome": "failed",
        "failed_stage": "parsing",
        "market": "AMEX",
        "source_code": "eoddata_daily",
    }
def test_runner_rerun_uses_new_core_run_and_preserves_unchanged_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = FakeRunRepository()
    events: list[str] = []
    _install_success(monkeypatch, events)
    service = RunService(repository)
    object_store = ObjectStore(FakeObjectRepository(tmp_path))

    results = tuple(
        run_eoddata_daily(
            run_service=service,
            connection=FakeConnection(),
            object_store=object_store,
            config=_config(),
            effective_date=EFFECTIVE_DATE,
            run_type="cli",
            runner="pytest",
            sleep=lambda _delay: None,
        )
        for _ in range(2)
    )

    assert results[0].run_id != results[1].run_id
    assert all(result.status == "succeeded" for result in results)
    assert all(
        result.listing_counts == PersistenceCounts(unchanged=3)
        for result in results
    )
    assert len(repository.runs) == 2


def test_parse_stage_reads_six_objects_and_keeps_market_order(
    tmp_path: Path,
) -> None:
    repository = FakeObjectRepository(tmp_path)
    object_store = ObjectStore(repository)
    acquired: list[AcquiredObject] = []
    for source in (EODDATA_SYMBOL_LIST_SOURCE, EODDATA_DAILY_SOURCE):
        for market in MARKETS:
            ticker = f"{market}.ONE"
            payload = (
                json.dumps([{"code": ticker}]).encode()
                if source == EODDATA_SYMBOL_LIST_SOURCE
                else json.dumps(
                    [
                        {
                            "exchangeCode": market,
                            "symbolCode": ticker,
                            "interval": "d",
                            "dateStamp": EFFECTIVE_DATE.isoformat(),
                            "open": 10,
                            "high": 11,
                            "low": 9,
                            "close": 10,
                            "volume": 100,
                        }
                    ]
                ).encode()
            )
            stored = object_store.put_bytes(
                run_context=None,
                storage_root="global",
                object_key=f"test/{source.source_code}/{market.lower()}",
                filename=f"raw-{market.lower()}.json",
                data=payload,
                object_scope="manual",
                domain="stonks",
            )
            acquired.append(
                AcquiredObject(
                    source_code=source.source_code,
                    object_id=stored.object_id,
                    object_key=stored.object_key,
                    filename=stored.filename,
                    size_bytes=stored.size_bytes or 0,
                    checksum_sha256=stored.checksum_sha256 or "",
                )
            )

    results = eoddata_runner._parse(
        object_store=object_store,
        acquired_objects=tuple(reversed(acquired)),
        effective_date=EFFECTIVE_DATE,
        markets=MARKETS,
    )

    assert tuple(result.cross_feed_counts.market for result in results) == MARKETS
    assert all(result.output.listing_count == 1 for result in results)
    assert all(result.output.bar_count == 1 for result in results)
