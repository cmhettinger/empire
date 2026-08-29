"""Package-owned Yahoo daily ingestion and reconciliation workflow."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from empire_core import ObjectStore, RunContext, RunService

from empire_stonks_ohlcv.config import OHLCVConfig
from empire_stonks_ohlcv.exceptions import (
    OHLCVConfigError,
    OHLCVWorkflowError,
)
from empire_stonks_ohlcv.market_sessions import MarketSessionService
from empire_stonks_ohlcv.object_store import Clock
from empire_stonks_ohlcv.results import PersistenceCounts
from empire_stonks_ohlcv.runner import DEFAULT_DOMAIN, SAFE_FAILURE_MESSAGE
from empire_stonks_ohlcv.source_conventions import YAHOO_DAILY_SOURCE
from empire_stonks_ohlcv.tech_indicators_completion import (
    TECH_INDICATORS_BENCHMARK_TICKER,
    TechIndicatorsSourceCompletionSignal,
)
from empire_stonks_ohlcv.yahoo import (
    YAHOO_PROVIDER_CODE,
    RandomUniform,
    Sleep,
    YahooAcquisitionOutcome,
    YahooAcquisitionStatus,
    YahooAcquisitionRequest,
    YahooHTTPTransport,
    YahooListingTarget,
    YahooRequestMode,
    acquire_yahoo_objects,
)
from empire_stonks_ohlcv.yahoo_benchmark_reporting import (
    build_yahoo_daily_benchmark_report,
)
from empire_stonks_ohlcv.yahoo_completeness import (
    YahooDailyCompletenessPlan,
    YahooDailyPull,
    YahooPullReason,
    plan_yahoo_daily_completeness,
)
from empire_stonks_ohlcv.yahoo_import import (
    YahooImportInput,
    YahooImportPurpose,
    import_yahoo_ranges,
)
from empire_stonks_ohlcv.yahoo_listings import (
    SeededYahooListing,
    select_active_yahoo_listings,
)
from empire_stonks_ohlcv.yahoo_parser import parse_yahoo_chart
from empire_stonks_ohlcv.yahoo_reconciliation import (
    YahooListingReconciliationPlan,
    YahooReconciliationPlan,
    build_yahoo_recent_reconciliation_plan,
)
from empire_stonks_ohlcv.yahoo_reporting import (
    YahooReportPhase,
    YahooReportPhaseResult,
    build_yahoo_daily_report,
    store_yahoo_daily_benchmark_pdf_report,
    store_yahoo_pdf_report,
    store_yahoo_report,
)


YAHOO_DAILY_JOB_NAME = "stonks_ohlcv_yahoo_daily"
YAHOO_DAILY_SUBJECT_KEY = "seeded_universe"

ProgressSink = Callable[[dict[str, Any]], None]

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class YahooDailyScope:
    """Explicit inclusive planning range and optional seed selection."""

    effective_date: date
    start_date: date
    end_date: date
    tickers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in ("effective_date", "start_date", "end_date"):
            if type(getattr(self, field_name)) is not date:
                raise TypeError(f"{field_name} must be a date.")
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date.")
        if self.end_date > self.effective_date:
            raise ValueError("end_date cannot be after effective_date.")
        if not isinstance(self.tickers, tuple):
            raise TypeError("tickers must be a tuple.")
        for ticker in self.tickers:
            _required_ticker(ticker)
        if len(self.tickers) != len(set(self.tickers)):
            raise ValueError("tickers must be unique.")
        object.__setattr__(self, "tickers", tuple(sorted(self.tickers)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "effective_date": self.effective_date.isoformat(),
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "tickers": list(self.tickers),
        }


@dataclass(frozen=True)
class YahooDailyRunResult:
    """Compact secret-safe result for one completed Yahoo daily run."""

    run_id: UUID
    status: str
    scope: YahooDailyScope
    enumerated_listing_count: int
    selected_listing_count: int
    calendar_policy_error_count: int
    ingestion: YahooReportPhaseResult
    reconciliation: YahooReportPhaseResult
    report_object_id: UUID
    pdf_report_object_id: UUID
    benchmark_pdf_report_object_id: UUID
    report_outcome: str

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, UUID):
            raise TypeError("run_id must be a UUID.")
        if self.status != "succeeded":
            raise ValueError("status must be succeeded.")
        if not isinstance(self.scope, YahooDailyScope):
            raise TypeError("scope must be a YahooDailyScope.")
        for field_name in (
            "enumerated_listing_count",
            "selected_listing_count",
            "calendar_policy_error_count",
        ):
            _nonnegative_int(field_name, getattr(self, field_name))
        if self.selected_listing_count > self.enumerated_listing_count:
            raise ValueError("Selected listings cannot exceed enumerated listings.")
        if self.calendar_policy_error_count > self.selected_listing_count:
            raise ValueError("Calendar errors cannot exceed selected listings.")
        if self.ingestion.phase is not YahooReportPhase.DAILY_INGESTION:
            raise ValueError("ingestion must be a daily_ingestion phase.")
        if self.reconciliation.phase is not YahooReportPhase.RECONCILIATION:
            raise ValueError("reconciliation must be a reconciliation phase.")
        if not isinstance(self.report_object_id, UUID):
            raise TypeError("report_object_id must be a UUID.")
        if not isinstance(self.pdf_report_object_id, UUID):
            raise TypeError("pdf_report_object_id must be a UUID.")
        if not isinstance(self.benchmark_pdf_report_object_id, UUID):
            raise TypeError("benchmark_pdf_report_object_id must be a UUID.")
        if self.report_outcome not in {"PASS", "WARN"}:
            raise ValueError("report_outcome must be PASS or WARN.")

    @property
    def bar_counts(self) -> PersistenceCounts:
        return _sum_counts(
            self.ingestion.import_result.bar_counts,
            self.reconciliation.import_result.bar_counts,
        )

    @property
    def corrected_reconciliation_bars(self) -> int:
        return self.reconciliation.import_result.corrected_reconciliation_bars

    @property
    def tech_indicators_completion_signal(
        self,
    ) -> TechIndicatorsSourceCompletionSignal | None:
        """Return a wake signal only when this run covered SPX readiness."""

        if self.scope.tickers and (
            TECH_INDICATORS_BENCHMARK_TICKER not in self.scope.tickers
        ):
            return None
        return TechIndicatorsSourceCompletionSignal(
            provider_code=YAHOO_PROVIDER_CODE,
            source_code=YAHOO_DAILY_SOURCE.source_code,
            job_name=YAHOO_DAILY_JOB_NAME,
            effective_date=self.scope.effective_date,
            source_run_id=self.run_id,
            report_outcome=self.report_outcome,
        )

    def to_dict(self) -> dict[str, Any]:
        completion_signal = self.tech_indicators_completion_signal
        return {
            "run_id": str(self.run_id),
            "status": self.status,
            "provider_code": YAHOO_PROVIDER_CODE,
            "source_code": YAHOO_DAILY_SOURCE.source_code,
            "scope": self.scope.to_dict(),
            "enumerated_listing_count": self.enumerated_listing_count,
            "selected_listing_count": self.selected_listing_count,
            "calendar_policy_error_count": self.calendar_policy_error_count,
            "ingestion": _phase_compact_dict(self.ingestion),
            "reconciliation": _phase_compact_dict(self.reconciliation),
            "bar_counts": self.bar_counts.to_dict(),
            "corrected_reconciliation_bars": (
                self.corrected_reconciliation_bars
            ),
            "report_object_id": str(self.report_object_id),
            "pdf_report_object_id": str(self.pdf_report_object_id),
            "benchmark_pdf_report_object_id": str(
                self.benchmark_pdf_report_object_id
            ),
            "report_outcome": self.report_outcome,
            "tech_indicators_completion_signal": (
                None
                if completion_signal is None
                else completion_signal.to_dict()
            ),
        }


def run_yahoo_daily(
    *,
    run_service: RunService,
    connection: Any,
    object_store: ObjectStore,
    config: OHLCVConfig,
    scope: YahooDailyScope,
    run_type: str,
    runner: str,
    runner_ref: dict[str, Any] | None = None,
    transport: YahooHTTPTransport | None = None,
    sleep: Sleep = time.sleep,
    random_uniform: RandomUniform = random.uniform,
    clock: Clock = _utc_now,
    session_service: MarketSessionService | None = None,
    progress_sink: ProgressSink | None = None,
) -> YahooDailyRunResult:
    """Plan and execute Yahoo missing-session and reconciliation phases."""

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
    current = _aware_utc(clock())
    run_context = run_service.start_run(
        domain=DEFAULT_DOMAIN,
        job_name=YAHOO_DAILY_JOB_NAME,
        subject_key=YAHOO_DAILY_SUBJECT_KEY,
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
    stage = "planning"
    try:
        service = session_service or MarketSessionService()
        with connection.cursor() as cursor:
            completeness = plan_yahoo_daily_completeness(
                cursor=cursor,
                start_date=scope.start_date,
                end_date=scope.end_date,
                now=current,
                max_request_days=config.yahoo_daily_request_max_days,
                tickers=scope.tickers,
                session_service=service,
            )
            enumerated = select_active_yahoo_listings(cursor=cursor)
        selected = _selected_seeds(
            seeds=enumerated,
            plan=completeness,
        )
        reconciliation_plan = build_yahoo_recent_reconciliation_plan(
            completeness_plan=completeness,
            session_count=config.yahoo_reconciliation_sessions,
            max_request_days=config.yahoo_daily_request_max_days,
        )

        stage = "acquisition"
        ingestion = _execute_phase(
            run_service=run_service,
            run_context=run_context,
            connection=connection,
            object_store=object_store,
            config=config,
            seeds=selected,
            pulls=completeness.pulls,
            phase=YahooReportPhase.DAILY_INGESTION,
            purpose=YahooImportPurpose.INGESTION,
            transport=transport,
            sleep=sleep,
            random_uniform=random_uniform,
            clock=clock,
            session_service=service,
            progress_sink=progress_sink,
        )
        reconciliation_plan = _exclude_fresh_ingestion_dates(
            plan=reconciliation_plan,
            ingestion=ingestion,
            ingestion_pulls=completeness.pulls,
            max_request_days=config.yahoo_daily_request_max_days,
        )
        reconciliation = _execute_phase(
            run_service=run_service,
            run_context=run_context,
            connection=connection,
            object_store=object_store,
            config=config,
            seeds=selected,
            pulls=reconciliation_plan.pulls,
            phase=YahooReportPhase.RECONCILIATION,
            purpose=YahooImportPurpose.RECONCILIATION,
            transport=transport,
            sleep=sleep,
            random_uniform=random_uniform,
            clock=clock,
            session_service=service,
            progress_sink=progress_sink,
        )

        stage = "reporting"
        with connection.cursor() as cursor:
            report = build_yahoo_daily_report(
                cursor=cursor,
                run_context=run_context,
                completeness_plan=completeness,
                reconciliation_plan=reconciliation_plan,
                ingestion_result=ingestion,
                reconciliation_result=reconciliation,
                generated_at=clock(),
            )
            benchmark_report = build_yahoo_daily_benchmark_report(
                cursor=cursor,
                trading_date=scope.effective_date,
                generated_at=clock(),
                session_service=service,
            )
        stored_report = store_yahoo_report(
            object_store=object_store,
            run_context=run_context,
            config=config,
            report=report,
        )
        stored_pdf_report = store_yahoo_pdf_report(
            object_store=object_store,
            run_context=run_context,
            config=config,
            report=report,
        )
        stored_benchmark_pdf_report = store_yahoo_daily_benchmark_pdf_report(
            object_store=object_store,
            run_context=run_context,
            config=config,
            report=benchmark_report,
        )
        summary = _success_summary(
            scope=scope,
            completeness=completeness,
            ingestion=ingestion,
            reconciliation=reconciliation,
            report=report,
            report_object_id=stored_report.object_id,
            pdf_report_object_id=stored_pdf_report.object_id,
            benchmark_pdf_report_object_id=(
                stored_benchmark_pdf_report.object_id
            ),
        )
        completed = run_service.complete_run(
            run_context.run_id,
            summary=summary,
        )
        return YahooDailyRunResult(
            run_id=completed.run_id,
            status=completed.status,
            scope=scope,
            enumerated_listing_count=completeness.enumerated_listing_count,
            selected_listing_count=len(completeness.listings),
            calendar_policy_error_count=completeness.failed_listing_count,
            ingestion=ingestion,
            reconciliation=reconciliation,
            report_object_id=stored_report.object_id,
            pdf_report_object_id=stored_pdf_report.object_id,
            benchmark_pdf_report_object_id=(
                stored_benchmark_pdf_report.object_id
            ),
            report_outcome=report["outcome"],
        )
    except Exception as exc:
        _rollback_quietly(connection)
        safe_stage = _workflow_stage(stage)
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
            safe_stage,
            source_code=YAHOO_DAILY_SOURCE.source_code,
        ) from exc


def _execute_phase(
    *,
    run_service: RunService,
    run_context: RunContext,
    connection: Any,
    object_store: ObjectStore,
    config: OHLCVConfig,
    seeds: tuple[SeededYahooListing, ...],
    pulls: tuple[YahooDailyPull, ...],
    phase: YahooReportPhase,
    purpose: YahooImportPurpose,
    transport: YahooHTTPTransport | None,
    sleep: Sleep,
    random_uniform: RandomUniform,
    clock: Clock,
    session_service: MarketSessionService,
    progress_sink: ProgressSink | None,
) -> YahooReportPhaseResult:
    completed = 0

    def acquired(outcome: YahooAcquisitionOutcome) -> None:
        nonlocal completed
        completed += 1
        run_service.heartbeat(run_context.run_id)
        _emit_progress(
            progress_sink,
            {
                "run_id": str(run_context.run_id),
                "stage": "acquisition",
                "phase": phase.value,
                "completed_chunks": completed,
                "ticker": outcome.request.listing.ticker,
                "status": outcome.status.value,
            },
        )

    acquisition = acquire_yahoo_objects(
        object_store=object_store,
        run_context=run_context,
        config=config,
        requests=tuple(item.request for item in pulls),
        transport=transport,
        sleep=sleep,
        random_uniform=random_uniform,
        clock=clock,
        outcome_sink=acquired,
    )
    by_id = {item.target.provider_listing_id: item for item in seeds}
    inputs: list[YahooImportInput] = []
    parse_failed_count = 0
    for outcome in acquisition.outcomes:
        parsed = None
        seeded = by_id.get(outcome.request.listing.provider_listing_id)
        if (
            outcome.status is YahooAcquisitionStatus.STORED
            and seeded is not None
        ):
            try:
                assert outcome.acquired_object is not None
                parsed = parse_yahoo_chart(
                    object_store.get_bytes(outcome.acquired_object.object_id),
                    request=outcome.request,
                    listing=seeded.listing,
                    policy=seeded.policy,
                    planned_session_dates=_planned_dates(
                        pulls=pulls,
                        outcome=outcome,
                    ),
                    session_service=session_service,
                )
            except Exception:
                parse_failed_count += 1
        inputs.append(
            YahooImportInput(
                acquisition=outcome,
                parse_result=parsed,
                purpose=purpose,
            )
        )
    imported = import_yahoo_ranges(connection=connection, inputs=tuple(inputs))
    if acquisition.outcomes:
        run_service.heartbeat(run_context.run_id)
    _emit_progress(
        progress_sink,
        {
            "run_id": str(run_context.run_id),
            "stage": "persistence",
            "phase": phase.value,
            "completed_chunks": imported.chunk_count,
            "status": "completed",
        },
    )
    return YahooReportPhaseResult(
        phase=phase,
        acquisition=acquisition,
        import_result=imported,
        parse_failed_count=parse_failed_count,
    )


def _planned_dates(
    *,
    pulls: tuple[YahooDailyPull, ...],
    outcome: YahooAcquisitionOutcome,
) -> tuple[date, ...]:
    request = outcome.request
    return tuple(
        item
        for pull in pulls
        if pull.request.listing.provider_listing_id
        == request.listing.provider_listing_id
        for item in pull.planned_dates
        if request.start_date <= item < request.end_date_exclusive
    )


def _exclude_fresh_ingestion_dates(
    *,
    plan: YahooReconciliationPlan,
    ingestion: YahooReportPhaseResult,
    ingestion_pulls: tuple[YahooDailyPull, ...],
    max_request_days: int,
) -> YahooReconciliationPlan:
    """Avoid reacquiring a range already stored during this Core run."""

    fresh: dict[UUID, set[date]] = {}
    for outcome in ingestion.acquisition.outcomes:
        if outcome.acquired_object is None:
            continue
        listing_id = outcome.request.listing.provider_listing_id
        dates = fresh.setdefault(listing_id, set())
        dates.update(
            item
            for pull in ingestion_pulls
            if pull.request.listing.provider_listing_id == listing_id
            for item in pull.planned_dates
            if outcome.request.start_date
            <= item
            < outcome.request.end_date_exclusive
        )
    listings = tuple(
        _filtered_reconciliation_listing(
            item=item,
            excluded=fresh.get(item.listing.provider_listing_id, set()),
            max_request_days=max_request_days,
        )
        for item in plan.listings
    )
    return YahooReconciliationPlan(
        completeness_plan=plan.completeness_plan,
        session_count=plan.session_count,
        listings=listings,
    )


def _filtered_reconciliation_listing(
    *,
    item: YahooListingReconciliationPlan,
    excluded: set[date],
    max_request_days: int,
) -> YahooListingReconciliationPlan:
    selected = tuple(value for value in item.selected_dates if value not in excluded)
    return YahooListingReconciliationPlan(
        listing=item.listing,
        policy_code=item.policy_code,
        status=item.status,
        selected_dates=selected,
        pulls=_reconciliation_pulls(
            listing=item.listing,
            selected_dates=selected,
            max_request_days=max_request_days,
        ),
        observed_only=item.observed_only,
        failure_reason=item.failure_reason,
    )


def _reconciliation_pulls(
    *,
    listing: YahooListingTarget,
    selected_dates: tuple[date, ...],
    max_request_days: int,
) -> tuple[YahooDailyPull, ...]:
    if not selected_dates:
        return ()
    groups: list[list[date]] = []
    current: list[date] = []
    for item in selected_dates:
        if current and (
            item + timedelta(days=1) - current[0]
        ).days > max_request_days:
            groups.append(current)
            current = []
        current.append(item)
    groups.append(current)
    return tuple(
        YahooDailyPull(
            request=YahooAcquisitionRequest(
                listing=listing,
                start_date=group[0],
                end_date_exclusive=group[-1] + timedelta(days=1),
                mode=YahooRequestMode.DAILY,
            ),
            reason=YahooPullReason.RECENT_RECONCILIATION,
            planned_dates=tuple(group),
        )
        for group in groups
    )


def _selected_seeds(
    *,
    seeds: tuple[SeededYahooListing, ...],
    plan: YahooDailyCompletenessPlan,
) -> tuple[SeededYahooListing, ...]:
    selected_ids = {
        item.listing.provider_listing_id for item in plan.listings
    }
    selected = tuple(
        item for item in seeds if item.target.provider_listing_id in selected_ids
    )
    if tuple(item.target for item in selected) != tuple(
        item.listing for item in plan.listings
    ):
        raise OHLCVConfigError(
            "Active Yahoo seeds changed during daily planning."
        )
    return selected


def _success_summary(
    *,
    scope: YahooDailyScope,
    completeness: YahooDailyCompletenessPlan,
    ingestion: YahooReportPhaseResult,
    reconciliation: YahooReportPhaseResult,
    report: dict[str, Any],
    report_object_id: UUID,
    pdf_report_object_id: UUID,
    benchmark_pdf_report_object_id: UUID,
) -> dict[str, Any]:
    counts = _sum_counts(
        ingestion.import_result.bar_counts,
        reconciliation.import_result.bar_counts,
    )
    return {
        "provider_code": YAHOO_PROVIDER_CODE,
        "source_code": YAHOO_DAILY_SOURCE.source_code,
        "outcome": "succeeded",
        "scope": scope.to_dict(),
        "enumerated_listing_count": completeness.enumerated_listing_count,
        "selected_listing_count": len(completeness.listings),
        "calendar_policy_error_count": completeness.failed_listing_count,
        "ingestion": _phase_compact_dict(ingestion),
        "reconciliation": _phase_compact_dict(reconciliation),
        "bar_counts": counts.to_dict(),
        "corrected_reconciliation_bars": (
            reconciliation.import_result.corrected_reconciliation_bars
        ),
        "report_object_id": str(report_object_id),
        "pdf_report_object_id": str(pdf_report_object_id),
        "benchmark_pdf_report_object_id": str(
            benchmark_pdf_report_object_id
        ),
        "report_outcome": report["outcome"],
    }


def _phase_compact_dict(result: YahooReportPhaseResult) -> dict[str, Any]:
    imported = result.import_result
    return {
        "request_count": len(result.acquisition.outcomes),
        "stored": result.acquisition.stored_count,
        "missing": result.acquisition.missing_count,
        "failed": result.acquisition.failed_count,
        "retry_count": result.retry_count,
        "parse_failed_count": result.parse_failed_count,
        "imported_chunks": imported.imported_chunks,
        "missing_chunks": imported.missing_chunks,
        "failed_chunks": imported.failed_chunks,
        "bar_counts": imported.bar_counts.to_dict(),
    }


def _sum_counts(
    first: PersistenceCounts,
    second: PersistenceCounts,
) -> PersistenceCounts:
    return PersistenceCounts(
        inserted=first.inserted + second.inserted,
        updated=first.updated + second.updated,
        unchanged=first.unchanged + second.unchanged,
        derived_updated=first.derived_updated + second.derived_updated,
    )


def _validate_runner_inputs(
    *,
    run_service: RunService,
    connection: Any,
    object_store: ObjectStore,
    config: OHLCVConfig,
    scope: YahooDailyScope,
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
    if not isinstance(scope, YahooDailyScope):
        raise TypeError("scope must be a YahooDailyScope.")
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


def _emit_progress(
    sink: ProgressSink | None,
    payload: dict[str, Any],
) -> None:
    if sink is None:
        return
    try:
        sink(payload)
    except Exception:
        logger.warning("Yahoo daily progress sink failed; continuing run.")


def _aware_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("clock must return an aware datetime.")
    return value.astimezone(UTC)


def _workflow_stage(stage: str) -> str:
    if stage == "reporting":
        return "reporting"
    if stage == "acquisition":
        return "acquisition"
    return "persistence"


def _rollback_quietly(connection: Any) -> None:
    try:
        connection.rollback()
    except Exception:
        pass


def _required_ticker(value: object) -> None:
    if not isinstance(value, str):
        raise TypeError("ticker must be a string.")
    if not value or value != value.strip() or value != value.upper():
        raise ValueError("ticker must be a non-empty trimmed uppercase value.")


def _nonnegative_int(field_name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer.")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative.")
