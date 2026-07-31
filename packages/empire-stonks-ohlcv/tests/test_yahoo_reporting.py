from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from empire_core import ObjectStore, RunContext, StorageRoot, StoredObject
from empire_stonks_ohlcv import (
    AcquiredObject,
    DailyBarComparison,
    DailyBarComparisonStatus,
    DailyBarFieldDifference,
    ExpectedSession,
    OHLCVConfig,
    ObservedPollCandidate,
    PersistenceCounts,
    YahooAcquisitionOutcome,
    YahooCompletenessStatus,
    YahooAcquisitionRequest,
    YahooAcquisitionResult,
    YahooAcquisitionStatus,
    YahooAdjustedCloseComparison,
    YahooChunkImportResult,
    YahooDailyCompletenessPlan,
    YahooDailyPull,
    YahooFailureReason,
    YahooImportFailureCode,
    YahooImportPurpose,
    YahooImportResult,
    YahooImportStatus,
    YahooListingCompletenessPlan,
    YahooListingImportSummary,
    YahooListingTarget,
    YahooPlanningFailureReason,
    YahooPullReason,
    YahooRequestMode,
    YahooReconciliationSummary,
    build_yahoo_recent_reconciliation_plan,
)
from empire_stonks_ohlcv.reporting import (
    REPORT_OBJECT_KIND,
    REPORT_SCHEMA_VERSION,
)
from empire_stonks_ohlcv.yahoo_reporting import (
    YAHOO_DAILY_REPORT_LOGICAL_NAME,
    YAHOO_DAILY_REPORT_TYPE,
    YahooReportPhase,
    YahooReportPhaseResult,
    build_yahoo_daily_report,
    empty_yahoo_report_phase,
    store_yahoo_report,
    yahoo_report_to_json,
)


class _StoredDateCursor:
    def __init__(self, rows: list[tuple[UUID, date]]) -> None:
        self.rows = rows
        self.params: tuple[object, ...] = ()

    def execute(self, _query: str, params: tuple[object, ...]) -> None:
        self.params = params

    def fetchall(self) -> list[tuple[UUID, date]]:
        return self.rows


class _ObjectRepository:
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


def _target(index: int, ticker: str) -> YahooListingTarget:
    return YahooListingTarget(
        provider_listing_id=UUID(int=index),
        ticker=ticker,
        yahoo_ticker=f"^{ticker}",
    )


def _expected(day: int, eligible_hour: int) -> ExpectedSession:
    return ExpectedSession(
        session_date=date(2026, 7, day),
        eligible_at=datetime(2026, 7, day, eligible_hour, tzinfo=UTC),
    )


def _pull(
    target: YahooListingTarget,
    day: int,
    reason: YahooPullReason,
) -> YahooDailyPull:
    return YahooDailyPull(
        request=YahooAcquisitionRequest(
            listing=target,
            start_date=date(2026, 7, day),
            end_date_exclusive=date(2026, 7, day + 1),
            mode=YahooRequestMode.DAILY,
        ),
        reason=reason,
        planned_dates=(date(2026, 7, day),),
    )


def _plan() -> YahooDailyCompletenessPlan:
    dxy = _target(1, "DXY")
    spx = _target(2, "SPX")
    expected = tuple(_expected(day, 21) for day in range(1, 5))
    return YahooDailyCompletenessPlan(
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 4),
        planned_at=datetime(2026, 7, 4, 20, tzinfo=UTC),
        enumerated_listing_count=93,
        listings=(
            YahooListingCompletenessPlan(
                listing=dxy,
                policy_code="YH_DXY_CUTOFF_120M",
                status=YahooCompletenessStatus.PLANNED,
                observed_only=True,
                stored_session_dates=(
                    date(2026, 7, 1),
                    date(2026, 7, 2),
                    date(2026, 7, 3),
                ),
                observed_poll_candidates=(
                    ObservedPollCandidate(
                        candidate_date=date(2026, 7, 4),
                        poll_at=datetime(2026, 7, 4, 18, tzinfo=UTC),
                    ),
                ),
                pulls=(
                    _pull(dxy, 4, YahooPullReason.DUE_OBSERVED_POLL),
                ),
            ),
            YahooListingCompletenessPlan(
                listing=spx,
                policy_code="YH_XNYS_CLOSE_90M",
                status=YahooCompletenessStatus.PLANNED,
                observed_only=False,
                stored_session_dates=(date(2026, 7, 1), date(2026, 7, 2)),
                expected_sessions=expected,
                eligible_sessions=expected[:3],
                missing_sessions=(expected[2],),
                pulls=(
                    _pull(
                        spx,
                        3,
                        YahooPullReason.ELIGIBLE_MISSING_SESSION,
                    ),
                ),
            ),
        ),
    )


def _run_context() -> RunContext:
    return RunContext(
        run_id=UUID(int=100),
        domain="stonks",
        job_name="stonks_ohlcv_yahoo_daily",
        subject_key="seeded_universe",
        effective_date=date(2026, 7, 4),
        run_type="pytest",
        status="started",
        runner="pytest:y812",
        params={},
        started_at=datetime(2026, 7, 4, 20, tzinfo=UTC),
    )


def test_daily_report_distinguishes_calendar_coverage_and_observed_polls() -> None:
    plan = _plan()
    reconciliation = build_yahoo_recent_reconciliation_plan(
        completeness_plan=plan,
        session_count=2,
        max_request_days=10,
    )
    cursor = _StoredDateCursor(
        [
            (UUID(int=1), date(2026, 7, 1)),
            (UUID(int=1), date(2026, 7, 2)),
            (UUID(int=1), date(2026, 7, 3)),
            (UUID(int=2), date(2026, 7, 1)),
            (UUID(int=2), date(2026, 7, 2)),
        ]
    )

    report = build_yahoo_daily_report(
        cursor=cursor,
        run_context=_run_context(),
        completeness_plan=plan,
        reconciliation_plan=reconciliation,
        ingestion_result=empty_yahoo_report_phase(
            YahooReportPhase.DAILY_INGESTION
        ),
        reconciliation_result=empty_yahoo_report_phase(
            YahooReportPhase.RECONCILIATION
        ),
        generated_at=datetime(2026, 7, 4, 20, 1, tzinfo=UTC),
    )

    assert report["schema_version"] == REPORT_SCHEMA_VERSION
    assert report["report_type"] == YAHOO_DAILY_REPORT_TYPE
    assert report["workflow"] == "daily_ingestion_and_reconciliation"
    assert report["coverage"]["eligible_session_count"] == 3
    assert report["coverage"]["ineligible_session_count"] == 1
    assert report["coverage"]["missing_eligible_session_count"] == 1
    assert report["coverage"]["unresolved_observed_poll_count"] == 1
    assert report["coverage"]["coverage_percent"] == 66.67
    assert report["health"]["stale_listing_count"] == 1
    assert report["outcome"] == "WARN"
    dxy, spx = report["coverage"]["listings"]
    assert dxy["coverage_basis"] == "observed_only"
    assert dxy["coverage_percent"] is None
    assert not dxy["stale"]
    assert spx["missing_eligible_dates"] == ["2026-07-03"]
    assert spx["stale"]


def test_stored_report_is_durable_and_secret_safe(tmp_path: Path) -> None:
    plan = _plan()
    report = build_yahoo_daily_report(
        cursor=_StoredDateCursor(
            [
                (UUID(int=1), date(2026, 7, day))
                for day in range(1, 5)
            ]
            + [
                (UUID(int=2), date(2026, 7, day))
                for day in range(1, 4)
            ]
        ),
        run_context=_run_context(),
        completeness_plan=plan,
        reconciliation_plan=build_yahoo_recent_reconciliation_plan(
            completeness_plan=plan,
            session_count=2,
            max_request_days=10,
        ),
        ingestion_result=empty_yahoo_report_phase(
            YahooReportPhase.DAILY_INGESTION
        ),
        reconciliation_result=empty_yahoo_report_phase(
            YahooReportPhase.RECONCILIATION
        ),
        generated_at=datetime(2026, 7, 4, 20, 1, tzinfo=UTC),
    )
    object_store = ObjectStore(_ObjectRepository(tmp_path))

    stored = store_yahoo_report(
        object_store=object_store,
        run_context=_run_context(),
        config=OHLCVConfig(storage_key="stonks/ohlcv/test"),
        report=report,
    )

    assert stored.logical_name == YAHOO_DAILY_REPORT_LOGICAL_NAME
    assert stored.object_kind == REPORT_OBJECT_KIND
    assert stored.expires_at is None
    assert stored.metadata["report_type"] == YAHOO_DAILY_REPORT_TYPE
    loaded = json.loads(object_store.get_bytes(stored.object_id))
    assert loaded == json.loads(yahoo_report_to_json(report))
    assert "YahooTicker" not in repr(loaded)
    assert "secret" not in repr(loaded).lower()


def test_report_surfaces_retries_failures_corrections_and_adjustments() -> None:
    plan = _plan()
    target = plan.listings[1].listing
    request = YahooAcquisitionRequest(
        listing=target,
        start_date=date(2026, 7, 3),
        end_date_exclusive=date(2026, 7, 4),
        mode=YahooRequestMode.DAILY,
    )
    failed = YahooAcquisitionOutcome(
        request=request,
        status=YahooAcquisitionStatus.FAILED,
        attempts=3,
        http_status=503,
        failure_reason=YahooFailureReason.HTTP,
    )
    failed_chunk = YahooChunkImportResult(
        acquisition=failed,
        status=YahooImportStatus.FAILED,
        source_snapshot=None,
        bar_counts=PersistenceCounts(),
        accepted_rows=0,
        rejected_rows=0,
        parse_issue_count=0,
        parse_issues=(),
        failure_code=YahooImportFailureCode.ACQUISITION_FAILED,
    )
    ingestion = YahooReportPhaseResult(
        phase=YahooReportPhase.DAILY_INGESTION,
        acquisition=YahooAcquisitionResult((failed,)),
        import_result=YahooImportResult(
            (
                YahooListingImportSummary(
                    provider_listing_id=target.provider_listing_id,
                    ticker=target.ticker,
                    chunks=(failed_chunk,),
                ),
            )
        ),
    )

    acquired = YahooAcquisitionOutcome(
        request=request,
        status=YahooAcquisitionStatus.STORED,
        attempts=1,
        http_status=200,
        acquired_object=AcquiredObject(
            source_code="yahoo_daily",
            object_id=UUID(int=300),
            object_key="raw/test",
            filename="raw.json",
            size_bytes=100,
            checksum_sha256="a" * 64,
        ),
    )
    summary = YahooReconciliationSummary(
        comparisons=(
            DailyBarComparison(
                provider_listing_id=target.provider_listing_id,
                trading_date=date(2026, 7, 3),
                status=DailyBarComparisonStatus.CORRECTED,
                differences=(
                    DailyBarFieldDifference(
                        field_name="close",
                        stored_value=Decimal("10"),
                        incoming_value=Decimal("11"),
                    ),
                ),
            ),
        ),
        adjusted_close_present=True,
        adjusted_close_comparisons=(
            YahooAdjustedCloseComparison(
                trading_date=date(2026, 7, 3),
                native_close=Decimal("11"),
                adjusted_close=Decimal("10.5"),
            ),
        ),
        invalid_adjusted_close_rows=0,
    )
    corrected_chunk = YahooChunkImportResult(
        acquisition=acquired,
        status=YahooImportStatus.IMPORTED,
        source_snapshot=None,
        bar_counts=PersistenceCounts(updated=1),
        accepted_rows=1,
        rejected_rows=0,
        parse_issue_count=0,
        parse_issues=(),
        purpose=YahooImportPurpose.RECONCILIATION,
        reconciliation=summary,
    )
    reconciliation = YahooReportPhaseResult(
        phase=YahooReportPhase.RECONCILIATION,
        acquisition=YahooAcquisitionResult((acquired,)),
        import_result=YahooImportResult(
            (
                YahooListingImportSummary(
                    provider_listing_id=target.provider_listing_id,
                    ticker=target.ticker,
                    chunks=(corrected_chunk,),
                ),
            )
        ),
    )
    rows = [
        (UUID(int=index), date(2026, 7, day))
        for index in (1, 2)
        for day in range(1, 5)
    ]

    report = build_yahoo_daily_report(
        cursor=_StoredDateCursor(rows),
        run_context=_run_context(),
        completeness_plan=plan,
        reconciliation_plan=build_yahoo_recent_reconciliation_plan(
            completeness_plan=plan,
            session_count=2,
            max_request_days=10,
        ),
        ingestion_result=ingestion,
        reconciliation_result=reconciliation,
    )

    ingestion_section, reconciliation_section = report["phase_results"]
    assert ingestion_section["retry_count"] == 2
    assert ingestion_section["retried_request_count"] == 1
    assert ingestion_section["acquisition"]["failed"] == 1
    details = reconciliation_section["reconciliation"]
    assert details["corrected_bar_count"] == 1
    assert details["field_difference_counts"]["close"] == 1
    assert details["adjusted_close_difference_count"] == 1
    assert report["outcome"] == "WARN"


def test_daily_report_bounds_calendar_policy_errors() -> None:
    target = _target(9, "VIX")
    plan = YahooDailyCompletenessPlan(
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 4),
        planned_at=datetime(2026, 7, 4, 20, tzinfo=UTC),
        enumerated_listing_count=93,
        listings=(
            YahooListingCompletenessPlan(
                listing=target,
                policy_code="YH_BAD_CALENDAR",
                status=YahooCompletenessStatus.FAILED,
                observed_only=False,
                stored_session_dates=(),
                failure_reason=YahooPlanningFailureReason.CALENDAR_POLICY,
            ),
        ),
    )

    report = build_yahoo_daily_report(
        cursor=_StoredDateCursor([]),
        run_context=_run_context(),
        completeness_plan=plan,
        reconciliation_plan=build_yahoo_recent_reconciliation_plan(
            completeness_plan=plan,
            session_count=2,
            max_request_days=10,
        ),
        ingestion_result=empty_yahoo_report_phase(
            YahooReportPhase.DAILY_INGESTION
        ),
        reconciliation_result=empty_yahoo_report_phase(
            YahooReportPhase.RECONCILIATION
        ),
    )

    assert report["health"]["calendar_policy_error_count"] == 1
    errors = report["health"]["calendar_policy_errors"]
    assert errors["total_count"] == 1
    assert errors["samples"][0]["ticker"] == "VIX"
    assert errors["samples"][0]["failure_reason"] == "calendar_policy"
    assert report["outcome"] == "WARN"
