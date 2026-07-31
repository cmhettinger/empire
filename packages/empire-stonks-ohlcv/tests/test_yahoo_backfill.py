from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

import empire_stonks_ohlcv.yahoo_backfill as yahoo_backfill
from empire_core import (
    ObjectStore,
    RunContext,
    RunService,
    StorageRoot,
    StoredObject,
)
from empire_stonks_ohlcv import (
    AcquiredObject,
    EligibilityRule,
    OHLCVConfig,
    PersistenceCounts,
    ProviderListing,
    SeededYahooListing,
    SessionDateRule,
    SessionPolicy,
    YahooAcquisitionOutcome,
    YahooAcquisitionResult,
    YahooAcquisitionStatus,
    YahooBackfillScope,
    YahooChunkImportResult,
    YahooFailureReason,
    YahooImportFailureCode,
    YahooImportResult,
    YahooImportStatus,
    YahooListingImportSummary,
    YahooListingTarget,
    run_yahoo_backfill,
)


EFFECTIVE_DATE = date(2026, 7, 30)
START_DATE = date(2026, 7, 1)
END_DATE = date(2026, 7, 3)


class FakeRunRepository:
    def __init__(self) -> None:
        self.runs: dict[UUID, RunContext] = {}
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
            started_at=datetime.now(UTC),
        )
        self.runs[context.run_id] = context
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
        return failed

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
    def execute(self, *_args: object) -> None:
        return None

    def fetchall(self) -> list[object]:
        return []

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


def _seed(index: int, ticker: str) -> SeededYahooListing:
    yahoo_ticker = f"^{ticker}"
    return SeededYahooListing(
        target=YahooListingTarget(
            provider_listing_id=UUID(int=index),
            ticker=ticker,
            yahoo_ticker=yahoo_ticker,
        ),
        listing=ProviderListing(
            provider_code="YAHOO",
            market="XIDX",
            ticker=ticker,
            name=f"{ticker} Test",
            instrument_type_code="EQUITY_INDEX",
            metadata={"YahooTicker": yahoo_ticker},
        ),
        policy=SessionPolicy(
            code="YH_XNYS_CLOSE_90M",
            calendar_name="XNYS",
            timezone_name="America/New_York",
            eligibility_rule=EligibilityRule.SESSION_CLOSE,
            cutoff_local_time=None,
            availability_delay_minutes=90,
            session_date_rule=SessionDateRule.CALENDAR_SESSION,
        ),
    )


def _acquired(index: int) -> AcquiredObject:
    return AcquiredObject(
        source_code="yahoo_daily",
        object_id=UUID(int=100 + index),
        object_key=f"raw/{index}",
        filename=f"raw-{index}.json",
        size_bytes=100,
        checksum_sha256=f"{index:064x}",
    )


def _results(
    requests: tuple[object, ...],
) -> tuple[YahooAcquisitionResult, YahooImportResult]:
    stored_request, failed_request = requests
    stored = YahooAcquisitionOutcome(
        request=stored_request,  # type: ignore[arg-type]
        status=YahooAcquisitionStatus.STORED,
        attempts=1,
        http_status=200,
        acquired_object=_acquired(1),
    )
    failed = YahooAcquisitionOutcome(
        request=failed_request,  # type: ignore[arg-type]
        status=YahooAcquisitionStatus.FAILED,
        attempts=2,
        http_status=503,
        failure_reason=YahooFailureReason.HTTP,
    )
    chunks = (
        YahooChunkImportResult(
            acquisition=stored,
            status=YahooImportStatus.IMPORTED,
            source_snapshot=None,
            bar_counts=PersistenceCounts(inserted=1),
            accepted_rows=1,
            rejected_rows=0,
            parse_issue_count=0,
            parse_issues=(),
        ),
        YahooChunkImportResult(
            acquisition=failed,
            status=YahooImportStatus.FAILED,
            source_snapshot=None,
            bar_counts=PersistenceCounts(),
            accepted_rows=0,
            rejected_rows=0,
            parse_issue_count=0,
            parse_issues=(),
            failure_code=YahooImportFailureCode.ACQUISITION_FAILED,
        ),
    )
    imported = YahooImportResult(
        listings=tuple(
            YahooListingImportSummary(
                provider_listing_id=chunk.provider_listing_id,
                ticker=chunk.ticker,
                chunks=(chunk,),
            )
            for chunk in chunks
        )
    )
    return YahooAcquisitionResult((stored, failed)), imported


def test_full_enumeration_completes_warn_and_stores_safe_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seeds = (_seed(1, "DOW"), _seed(2, "SPX"))
    repository = FakeRunRepository()
    run_service = RunService(repository)
    object_repository = FakeObjectRepository(tmp_path)
    object_store = ObjectStore(object_repository)
    connection = FakeConnection()
    captured_requests: tuple[object, ...] = ()
    imported_result: YahooImportResult | None = None

    monkeypatch.setattr(
        yahoo_backfill,
        "select_active_yahoo_listings",
        lambda **_: seeds,
    )

    def acquire(**values: object) -> YahooAcquisitionResult:
        nonlocal captured_requests, imported_result
        captured_requests = tuple(values["requests"])  # type: ignore[arg-type]
        acquisition, imported_result = _results(captured_requests)
        sink = values["outcome_sink"]
        for outcome in acquisition.outcomes:
            sink(outcome)  # type: ignore[operator]
        return acquisition

    monkeypatch.setattr(yahoo_backfill, "acquire_yahoo_objects", acquire)

    def parse_import(**_: object) -> tuple[YahooImportResult, int]:
        assert imported_result is not None
        return imported_result, 0

    monkeypatch.setattr(yahoo_backfill, "_parse_and_import", parse_import)
    progress: list[dict[str, object]] = []

    result = run_yahoo_backfill(
        run_service=run_service,
        connection=connection,
        object_store=object_store,
        config=OHLCVConfig(),
        scope=YahooBackfillScope(
            effective_date=EFFECTIVE_DATE,
            start_date=START_DATE,
            end_date_exclusive=END_DATE,
        ),
        run_type="cli",
        runner="pytest",
        sleep=lambda _: None,
        random_uniform=lambda minimum, _maximum: minimum,
        clock=lambda: datetime(2026, 7, 30, 12, tzinfo=UTC),
        progress_sink=progress.append,
    )

    assert [item.listing.ticker for item in captured_requests] == [
        "DOW",
        "SPX",
    ]
    assert result.enumerated_listing_count == 2
    assert result.selected_listing_count == 2
    assert result.request_chunk_count == 2
    assert result.acquisition_stored_count == 1
    assert result.acquisition_failed_count == 1
    assert result.import_result.bar_counts.inserted == 1
    assert result.report_outcome == "WARN"
    assert repository.heartbeat_count == 2
    assert len(progress) == 2

    report = json.loads(object_store.get_bytes(result.report_object_id))
    assert report["scope"]["tickers"] == []
    assert report["enumerated_listing_count"] == 2
    assert report["selected_listing_count"] == 2
    assert report["outcome"] == "WARN"
    assert report["native_value_semantics"]["seeded_listing_writes"] == 0
    assert "secret" not in json.dumps(report)
    completed = repository.runs[result.run_id]
    assert completed.summary["report_object_id"] == str(
        result.report_object_id
    )


def test_resume_from_is_inclusive_within_explicit_tickers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seeds = (
        _seed(1, "DOW"),
        _seed(2, "DXY"),
        _seed(3, "SPX"),
    )
    repository = FakeRunRepository()
    run_service = RunService(repository)
    object_store = ObjectStore(FakeObjectRepository(tmp_path))
    captured: list[str] = []

    monkeypatch.setattr(
        yahoo_backfill,
        "select_active_yahoo_listings",
        lambda **_: seeds,
    )

    def acquire(**values: object) -> YahooAcquisitionResult:
        requests = tuple(values["requests"])  # type: ignore[arg-type]
        captured.extend(item.listing.ticker for item in requests)
        outcome = YahooAcquisitionOutcome(
            request=requests[0],
            status=YahooAcquisitionStatus.FAILED,
            attempts=1,
            failure_reason=YahooFailureReason.TRANSPORT,
        )
        return YahooAcquisitionResult((outcome,))

    monkeypatch.setattr(yahoo_backfill, "acquire_yahoo_objects", acquire)

    def parse_import(**values: object) -> tuple[YahooImportResult, int]:
        acquisition = values["acquisition"]
        outcome = acquisition.outcomes[0]  # type: ignore[union-attr]
        chunk = YahooChunkImportResult(
            acquisition=outcome,
            status=YahooImportStatus.FAILED,
            source_snapshot=None,
            bar_counts=PersistenceCounts(),
            accepted_rows=0,
            rejected_rows=0,
            parse_issue_count=0,
            parse_issues=(),
            failure_code=YahooImportFailureCode.ACQUISITION_FAILED,
        )
        return (
            YahooImportResult(
                listings=(
                    YahooListingImportSummary(
                        provider_listing_id=chunk.provider_listing_id,
                        ticker=chunk.ticker,
                        chunks=(chunk,),
                    ),
                )
            ),
            0,
        )

    monkeypatch.setattr(yahoo_backfill, "_parse_and_import", parse_import)

    result = run_yahoo_backfill(
        run_service=run_service,
        connection=FakeConnection(),
        object_store=object_store,
        config=OHLCVConfig(),
        scope=YahooBackfillScope(
            effective_date=EFFECTIVE_DATE,
            start_date=START_DATE,
            end_date_exclusive=END_DATE,
            tickers=("DOW", "SPX"),
            resume_from_ticker="SPX",
        ),
        run_type="cli",
        runner="pytest",
        sleep=lambda _: None,
        clock=lambda: datetime(2026, 7, 30, 12, tzinfo=UTC),
    )

    assert captured == ["SPX"]
    assert result.enumerated_listing_count == 3
    assert result.selected_listing_count == 1


def test_enumeration_failure_records_safe_failed_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = FakeRunRepository()
    monkeypatch.setattr(
        yahoo_backfill,
        "select_active_yahoo_listings",
        lambda **_: (_ for _ in ()).throw(
            RuntimeError("database-secret-detail")
        ),
    )

    with pytest.raises(Exception, match="persistence"):
        run_yahoo_backfill(
            run_service=RunService(repository),
            connection=FakeConnection(),
            object_store=ObjectStore(FakeObjectRepository(tmp_path)),
            config=OHLCVConfig(),
            scope=YahooBackfillScope(
                effective_date=EFFECTIVE_DATE,
                start_date=START_DATE,
                end_date_exclusive=END_DATE,
            ),
            run_type="cli",
            runner="pytest",
            sleep=lambda _: None,
        )

    failed = next(iter(repository.runs.values()))
    assert failed.status == "failed"
    assert failed.summary["failed_stage"] == "enumeration"
    assert repository.failure_messages[failed.run_id] == (
        "OHLCV provider run failed."
    )
    assert "secret" not in repr(failed.summary)


def test_scope_rejects_future_and_duplicate_or_nonuppercase_tickers() -> None:
    with pytest.raises(ValueError, match="effective_date"):
        YahooBackfillScope(
            effective_date=EFFECTIVE_DATE,
            start_date=START_DATE,
            end_date_exclusive=date(2026, 8, 2),
        )
    with pytest.raises(ValueError, match="unique"):
        YahooBackfillScope(
            effective_date=EFFECTIVE_DATE,
            start_date=START_DATE,
            end_date_exclusive=END_DATE,
            tickers=("SPX", "SPX"),
        )
    with pytest.raises(ValueError, match="uppercase"):
        YahooBackfillScope(
            effective_date=EFFECTIVE_DATE,
            start_date=START_DATE,
            end_date_exclusive=END_DATE,
            resume_from_ticker="spx",
        )
