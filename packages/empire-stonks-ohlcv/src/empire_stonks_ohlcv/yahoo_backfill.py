"""Package-owned Yahoo historical backfill orchestration and reporting."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from empire_core import ObjectStore, RunContext, RunService, StoredObject

from empire_stonks_ohlcv.config import OHLCVConfig
from empire_stonks_ohlcv.exceptions import (
    OHLCVConfigError,
    OHLCVWorkflowError,
)
from empire_stonks_ohlcv.market_sessions import MarketSessionService
from empire_stonks_ohlcv.object_store import Clock
from empire_stonks_ohlcv.reporting import REPORT_SCHEMA_VERSION
from empire_stonks_ohlcv.results import PersistenceCounts
from empire_stonks_ohlcv.runner import DEFAULT_DOMAIN, SAFE_FAILURE_MESSAGE
from empire_stonks_ohlcv.source_conventions import YAHOO_DAILY_SOURCE
from empire_stonks_ohlcv.yahoo import (
    YAHOO_PROVIDER_CODE,
    RandomUniform,
    Sleep,
    YahooAcquisitionOutcome,
    YahooAcquisitionRequest,
    YahooAcquisitionResult,
    YahooAcquisitionStatus,
    YahooHTTPTransport,
    YahooRequestMode,
    acquire_yahoo_objects,
)
from empire_stonks_ohlcv.yahoo_import import (
    YahooChunkImportResult,
    YahooImportInput,
    YahooImportResult,
    YahooListingImportSummary,
    import_yahoo_ranges,
)
from empire_stonks_ohlcv.yahoo_listings import (
    SeededYahooListing,
    select_active_yahoo_listings,
)
from empire_stonks_ohlcv.yahoo_parser import parse_yahoo_chart
from empire_stonks_ohlcv.yahoo_reporting import (
    YAHOO_BACKFILL_REPORT_FILENAME,
    YAHOO_BACKFILL_REPORT_LOGICAL_NAME,
    YAHOO_BACKFILL_REPORT_TYPE,
    YahooReportPhase,
    YahooReportPhaseResult,
    build_yahoo_backfill_report,
    store_yahoo_report,
)


YAHOO_BACKFILL_JOB_NAME = "stonks_ohlcv_yahoo_backfill"
YAHOO_BACKFILL_SUBJECT_KEY = "seeded_universe"
YAHOO_BACKFILL_REPORT_SCHEMA_VERSION = REPORT_SCHEMA_VERSION

ProgressSink = Callable[[dict[str, Any]], None]

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class YahooBackfillScope:
    """Explicit date and seeded-listing selection for one backfill run."""

    effective_date: date
    start_date: date
    end_date_exclusive: date
    tickers: tuple[str, ...] = ()
    resume_from_ticker: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "effective_date",
            "start_date",
            "end_date_exclusive",
        ):
            if type(getattr(self, field_name)) is not date:
                raise TypeError(f"{field_name} must be a date.")
        if self.end_date_exclusive <= self.start_date:
            raise ValueError("end_date_exclusive must be after start_date.")
        if self.end_date_exclusive > self.effective_date + timedelta(days=1):
            raise ValueError(
                "end_date_exclusive cannot be after effective_date + 1 day."
            )
        if not isinstance(self.tickers, tuple):
            raise TypeError("tickers must be a tuple.")
        for ticker in self.tickers:
            _required_ticker("ticker", ticker)
        if len(self.tickers) != len(set(self.tickers)):
            raise ValueError("tickers must be unique.")
        object.__setattr__(self, "tickers", tuple(sorted(self.tickers)))
        if self.resume_from_ticker is not None:
            _required_ticker(
                "resume_from_ticker",
                self.resume_from_ticker,
            )
            if (
                self.tickers
                and self.resume_from_ticker not in self.tickers
            ):
                raise ValueError(
                    "resume_from_ticker must be included in tickers."
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "effective_date": self.effective_date.isoformat(),
            "start_date": self.start_date.isoformat(),
            "end_date_exclusive": self.end_date_exclusive.isoformat(),
            "tickers": list(self.tickers),
            "resume_from_ticker": self.resume_from_ticker,
        }


@dataclass(frozen=True)
class YahooBackfillRunResult:
    """Compact secret-safe result for one completed Yahoo backfill."""

    run_id: UUID
    status: str
    scope: YahooBackfillScope
    enumerated_listing_count: int
    selected_listing_count: int
    request_chunk_count: int
    acquisition_stored_count: int
    acquisition_missing_count: int
    acquisition_failed_count: int
    parse_failed_count: int
    import_result: YahooImportResult
    report_object_id: UUID
    report_outcome: str

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, UUID):
            raise TypeError("run_id must be a UUID.")
        if self.status != "succeeded":
            raise ValueError("status must be succeeded.")
        if not isinstance(self.scope, YahooBackfillScope):
            raise TypeError("scope must be a YahooBackfillScope.")
        for field_name in (
            "enumerated_listing_count",
            "selected_listing_count",
            "request_chunk_count",
            "acquisition_stored_count",
            "acquisition_missing_count",
            "acquisition_failed_count",
            "parse_failed_count",
        ):
            _nonnegative_int(field_name, getattr(self, field_name))
        if self.selected_listing_count > self.enumerated_listing_count:
            raise ValueError(
                "selected_listing_count cannot exceed enumerated listings."
            )
        if not isinstance(self.import_result, YahooImportResult):
            raise TypeError("import_result must be a YahooImportResult.")
        if self.import_result.chunk_count != self.request_chunk_count:
            raise ValueError(
                "import_result must cover every acquisition request chunk."
            )
        if not isinstance(self.report_object_id, UUID):
            raise TypeError("report_object_id must be a UUID.")
        if self.report_outcome not in {"PASS", "WARN"}:
            raise ValueError("report_outcome must be PASS or WARN.")

    @property
    def bar_counts(self) -> PersistenceCounts:
        return self.import_result.bar_counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": str(self.run_id),
            "status": self.status,
            "provider_code": YAHOO_PROVIDER_CODE,
            "source_code": YAHOO_DAILY_SOURCE.source_code,
            "scope": self.scope.to_dict(),
            "enumerated_listing_count": self.enumerated_listing_count,
            "selected_listing_count": self.selected_listing_count,
            "request_chunk_count": self.request_chunk_count,
            "acquisition": {
                "stored": self.acquisition_stored_count,
                "missing": self.acquisition_missing_count,
                "failed": self.acquisition_failed_count,
            },
            "parse_failed_count": self.parse_failed_count,
            "imported_chunks": self.import_result.imported_chunks,
            "missing_chunks": self.import_result.missing_chunks,
            "failed_chunks": self.import_result.failed_chunks,
            "source_snapshot_count": (
                self.import_result.source_snapshot_count
            ),
            "bar_counts": self.bar_counts.to_dict(),
            "report_object_id": str(self.report_object_id),
            "report_outcome": self.report_outcome,
        }


def run_yahoo_backfill(
    *,
    run_service: RunService,
    connection: Any,
    object_store: ObjectStore,
    config: OHLCVConfig,
    scope: YahooBackfillScope,
    run_type: str,
    runner: str,
    runner_ref: dict[str, Any] | None = None,
    transport: YahooHTTPTransport | None = None,
    sleep: Sleep = time.sleep,
    random_uniform: RandomUniform = random.uniform,
    clock: Clock = _utc_now,
    session_service: MarketSessionService | None = None,
    progress_sink: ProgressSink | None = None,
) -> YahooBackfillRunResult:
    """Enumerate, acquire, parse, and import a bounded Yahoo seed backfill."""

    _validate_runner_inputs(
        run_service=run_service,
        connection=connection,
        object_store=object_store,
        config=config,
        scope=scope,
        runner=runner,
        sleep=sleep,
        random_uniform=random_uniform,
        clock=clock,
        session_service=session_service,
        progress_sink=progress_sink,
    )
    run_context = run_service.start_run(
        domain=DEFAULT_DOMAIN,
        job_name=YAHOO_BACKFILL_JOB_NAME,
        subject_key=YAHOO_BACKFILL_SUBJECT_KEY,
        effective_date=scope.effective_date,
        run_type=run_type,
        runner=runner,
        runner_ref=runner_ref or {},
        params={
            "provider_code": YAHOO_PROVIDER_CODE,
            "source_code": YAHOO_DAILY_SOURCE.source_code,
            "scope": scope.to_dict(),
            "configuration": config.to_safe_dict(),
        },
    )
    stage = "enumeration"
    try:
        with connection.cursor() as cursor:
            enumerated = select_active_yahoo_listings(cursor=cursor)
        selected = _select_scope(enumerated=enumerated, scope=scope)
        requests = tuple(
            YahooAcquisitionRequest(
                listing=item.target,
                start_date=scope.start_date,
                end_date_exclusive=scope.end_date_exclusive,
                mode=YahooRequestMode.BACKFILL,
            )
            for item in selected
        )
        acquired_chunks = 0

        def acquired(outcome: YahooAcquisitionOutcome) -> None:
            nonlocal acquired_chunks
            acquired_chunks += 1
            run_service.heartbeat(run_context.run_id)
            _emit_progress(
                progress_sink,
                {
                    "run_id": str(run_context.run_id),
                    "stage": "acquisition",
                    "completed_chunks": acquired_chunks,
                    "ticker": outcome.request.listing.ticker,
                    "status": outcome.status.value,
                },
            )

        stage = "acquisition"
        acquisition = acquire_yahoo_objects(
            object_store=object_store,
            run_context=run_context,
            config=config,
            requests=requests,
            transport=transport,
            sleep=sleep,
            random_uniform=random_uniform,
            clock=clock,
            outcome_sink=acquired,
        )
        stage = "parsing_persistence"
        import_result, parse_failed_count = _parse_and_import(
            run_service=run_service,
            run_context=run_context,
            connection=connection,
            object_store=object_store,
            acquisition=acquisition,
            listings=selected,
            session_service=session_service or MarketSessionService(),
            progress_sink=progress_sink,
        )
        with connection.cursor() as cursor:
            report = build_yahoo_backfill_report(
                cursor=cursor,
                run_context=run_context,
                scope=scope.to_dict(),
                listings=tuple(item.target for item in selected),
                enumerated_listing_count=len(enumerated),
                result=YahooReportPhaseResult(
                    phase=YahooReportPhase.INITIAL_INGESTION,
                    acquisition=acquisition,
                    import_result=import_result,
                    parse_failed_count=parse_failed_count,
                ),
                generated_at=clock(),
            )
        stage = "reporting"
        stored_report = store_yahoo_report(
            object_store=object_store,
            run_context=run_context,
            config=config,
            report=report,
        )
        summary = _success_summary(
            scope=scope,
            enumerated_listing_count=len(enumerated),
            selected_listing_count=len(selected),
            acquisition=acquisition,
            parse_failed_count=parse_failed_count,
            import_result=import_result,
            stored_report=stored_report,
            report_outcome=report["outcome"],
        )
        completed = run_service.complete_run(
            run_context.run_id,
            summary=summary,
        )
        return YahooBackfillRunResult(
            run_id=completed.run_id,
            status=completed.status,
            scope=scope,
            enumerated_listing_count=len(enumerated),
            selected_listing_count=len(selected),
            request_chunk_count=len(acquisition.outcomes),
            acquisition_stored_count=acquisition.stored_count,
            acquisition_missing_count=acquisition.missing_count,
            acquisition_failed_count=acquisition.failed_count,
            parse_failed_count=parse_failed_count,
            import_result=import_result,
            report_object_id=stored_report.object_id,
            report_outcome=report["outcome"],
        )
    except Exception as exc:
        _rollback_quietly(connection)
        run_service.fail_run(
            run_context.run_id,
            SAFE_FAILURE_MESSAGE,
            summary={
                "provider_code": YAHOO_PROVIDER_CODE,
                "source_code": YAHOO_DAILY_SOURCE.source_code,
                "outcome": "failed",
                "failed_stage": stage,
                "scope": scope.to_dict(),
            },
        )
        if isinstance(exc, OHLCVWorkflowError):
            raise
        raise OHLCVWorkflowError(
            _workflow_stage(stage),
            source_code=YAHOO_DAILY_SOURCE.source_code,
        ) from exc


def _parse_and_import(
    *,
    run_service: RunService,
    run_context: RunContext,
    connection: Any,
    object_store: ObjectStore,
    acquisition: YahooAcquisitionResult,
    listings: tuple[SeededYahooListing, ...],
    session_service: MarketSessionService,
    progress_sink: ProgressSink | None,
) -> tuple[YahooImportResult, int]:
    by_id = {
        item.target.provider_listing_id: item for item in listings
    }
    planned_cache: dict[
        tuple[str, date, date],
        tuple[date, ...] | None,
    ] = {}
    chunk_results: list[YahooChunkImportResult] = []
    parse_failed_count = 0
    for index, outcome in enumerate(acquisition.outcomes, start=1):
        parsed = None
        if outcome.status is YahooAcquisitionStatus.STORED:
            seeded = by_id[outcome.request.listing.provider_listing_id]
            try:
                planned = _planned_dates(
                    seeded=seeded,
                    request=outcome.request,
                    session_service=session_service,
                    cache=planned_cache,
                )
                assert outcome.acquired_object is not None
                parsed = parse_yahoo_chart(
                    object_store.get_bytes(
                        outcome.acquired_object.object_id
                    ),
                    request=outcome.request,
                    listing=seeded.listing,
                    policy=seeded.policy,
                    planned_session_dates=planned,
                    session_service=session_service,
                )
            except Exception:
                parse_failed_count += 1
        imported = import_yahoo_ranges(
            connection=connection,
            inputs=(
                YahooImportInput(
                    acquisition=outcome,
                    parse_result=parsed,
                ),
            ),
        )
        chunk_results.extend(
            chunk
            for listing in imported.listings
            for chunk in listing.chunks
        )
        run_service.heartbeat(run_context.run_id)
        _emit_progress(
            progress_sink,
            {
                "run_id": str(run_context.run_id),
                "stage": "persistence",
                "completed_chunks": index,
                "total_chunks": len(acquisition.outcomes),
                "ticker": outcome.request.listing.ticker,
                "status": chunk_results[-1].status.value,
            },
        )
    return _import_result(tuple(chunk_results)), parse_failed_count


def _planned_dates(
    *,
    seeded: SeededYahooListing,
    request: YahooAcquisitionRequest,
    session_service: MarketSessionService,
    cache: dict[tuple[str, date, date], tuple[date, ...] | None],
) -> tuple[date, ...] | None:
    if seeded.policy.calendar_name is None:
        return None
    key = (
        seeded.policy.code,
        request.start_date,
        request.end_date_exclusive,
    )
    if key not in cache:
        cache[key] = tuple(
            item.session_date
            for item in session_service.expected_sessions(
                policy=seeded.policy,
                start_date=request.start_date,
                end_date=request.end_date_exclusive - timedelta(days=1),
            )
        )
    return cache[key]


def _import_result(
    chunks: tuple[YahooChunkImportResult, ...],
) -> YahooImportResult:
    grouped: dict[
        tuple[UUID, str],
        list[YahooChunkImportResult],
    ] = {}
    for chunk in chunks:
        key = (chunk.provider_listing_id, chunk.ticker)
        grouped.setdefault(key, []).append(chunk)
    return YahooImportResult(
        listings=tuple(
            YahooListingImportSummary(
                provider_listing_id=provider_listing_id,
                ticker=ticker,
                chunks=tuple(grouped[(provider_listing_id, ticker)]),
            )
            for provider_listing_id, ticker in sorted(
                grouped,
                key=lambda item: (item[1], str(item[0])),
            )
        )
    )


def _select_scope(
    *,
    enumerated: tuple[SeededYahooListing, ...],
    scope: YahooBackfillScope,
) -> tuple[SeededYahooListing, ...]:
    if not enumerated:
        raise OHLCVConfigError("No active seeded Yahoo listings were found.")
    by_ticker = {item.target.ticker: item for item in enumerated}
    unknown = sorted(set(scope.tickers) - set(by_ticker))
    if unknown:
        raise OHLCVConfigError(
            "Requested Yahoo ticker is not an active seed."
        )
    if (
        scope.resume_from_ticker is not None
        and scope.resume_from_ticker not in by_ticker
    ):
        raise OHLCVConfigError(
            "resume_from_ticker is not an active Yahoo seed."
        )
    selected = tuple(
        item
        for item in enumerated
        if not scope.tickers or item.target.ticker in scope.tickers
    )
    if scope.resume_from_ticker is not None:
        selected = tuple(
            item
            for item in selected
            if item.target.ticker >= scope.resume_from_ticker
        )
    if not selected:
        raise OHLCVConfigError("Yahoo backfill scope selected no listings.")
    return selected


def _success_summary(
    *,
    scope: YahooBackfillScope,
    enumerated_listing_count: int,
    selected_listing_count: int,
    acquisition: YahooAcquisitionResult,
    parse_failed_count: int,
    import_result: YahooImportResult,
    stored_report: StoredObject,
    report_outcome: str,
) -> dict[str, Any]:
    return {
        "provider_code": YAHOO_PROVIDER_CODE,
        "source_code": YAHOO_DAILY_SOURCE.source_code,
        "outcome": "succeeded",
        "scope": scope.to_dict(),
        "enumerated_listing_count": enumerated_listing_count,
        "selected_listing_count": selected_listing_count,
        "request_chunk_count": len(acquisition.outcomes),
        "acquisition": {
            "stored": acquisition.stored_count,
            "missing": acquisition.missing_count,
            "failed": acquisition.failed_count,
        },
        "parse_failed_count": parse_failed_count,
        "imported_chunks": import_result.imported_chunks,
        "missing_chunks": import_result.missing_chunks,
        "failed_chunks": import_result.failed_chunks,
        "source_snapshot_count": import_result.source_snapshot_count,
        "bar_counts": import_result.bar_counts.to_dict(),
        "report_object_id": str(stored_report.object_id),
        "report_outcome": report_outcome,
    }


def _emit_progress(
    sink: ProgressSink | None,
    payload: dict[str, Any],
) -> None:
    if sink is None:
        return
    try:
        sink(payload)
    except Exception:
        logger.warning("Yahoo backfill progress sink failed; continuing run.")


def _validate_runner_inputs(
    *,
    run_service: RunService,
    connection: Any,
    object_store: ObjectStore,
    config: OHLCVConfig,
    scope: YahooBackfillScope,
    runner: str,
    sleep: Sleep,
    random_uniform: RandomUniform,
    clock: Clock,
    session_service: MarketSessionService | None,
    progress_sink: ProgressSink | None,
) -> None:
    if not isinstance(run_service, RunService):
        raise TypeError("run_service must be a Core RunService.")
    for method_name in ("cursor", "commit", "rollback"):
        if not callable(getattr(connection, method_name, None)):
            raise TypeError(
                "connection must provide cursor, commit, and rollback methods."
            )
    if not isinstance(object_store, ObjectStore):
        raise TypeError("object_store must be a Core ObjectStore.")
    if not isinstance(config, OHLCVConfig):
        raise TypeError("config must be an OHLCVConfig.")
    if not isinstance(scope, YahooBackfillScope):
        raise TypeError("scope must be a YahooBackfillScope.")
    if not isinstance(runner, str) or not runner.strip():
        raise OHLCVConfigError("runner is required.")
    for field_name, value in (
        ("sleep", sleep),
        ("random_uniform", random_uniform),
        ("clock", clock),
    ):
        if not callable(value):
            raise TypeError(f"{field_name} must be callable.")
    if session_service is not None and not isinstance(
        session_service,
        MarketSessionService,
    ):
        raise TypeError(
            "session_service must be a MarketSessionService or None."
        )
    if progress_sink is not None and not callable(progress_sink):
        raise TypeError("progress_sink must be callable or None.")


def _aware_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("clock must return an aware datetime.")
    return value.astimezone(UTC)


def _rollback_quietly(connection: Any) -> None:
    try:
        connection.rollback()
    except Exception:
        pass


def _workflow_stage(stage: str) -> str:
    if stage == "enumeration":
        return "persistence"
    if stage == "parsing_persistence":
        return "parsing"
    return stage


def _required_ticker(field_name: str, value: object) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    if not value or value != value.strip() or value != value.upper():
        raise ValueError(
            f"{field_name} must be a non-empty trimmed uppercase ticker."
        )


def _nonnegative_int(field_name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer.")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative.")
