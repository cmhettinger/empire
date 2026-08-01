"""Package-owned daily EODData run sequencing."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from empire_core import ObjectStore, RunContext, RunService, StoredObject

from empire_stonks_ohlcv.config import OHLCVConfig
from empire_stonks_ohlcv.daily_market_reporting import (
    build_eoddata_daily_market_report,
)
from empire_stonks_ohlcv.eoddata import (
    EODDATA_PROVIDER_CODE,
    EODDataHTTPTransport,
    EODDataRetryEvent,
    Sleep,
    acquire_eoddata_objects,
)
from empire_stonks_ohlcv.eoddata_import import (
    EODDataImportResult,
    import_eoddata_daily,
)
from empire_stonks_ohlcv.eoddata_quotes import parse_eoddata_quote_list
from empire_stonks_ohlcv.eoddata_symbols import parse_eoddata_symbol_list
from empire_stonks_ohlcv.eoddata_planning import (
    EODDataDailyPlan,
    EODDataExchangeWorkReason,
    plan_eoddata_exchange_work,
)
from empire_stonks_ohlcv.exceptions import (
    OHLCVAcquisitionError,
    OHLCVConfigError,
    OHLCVWorkflowError,
)
from empire_stonks_ohlcv.reporting import (
    build_eoddata_report,
    store_eoddata_daily_market_pdf_report,
    store_eoddata_pdf_report,
    store_eoddata_report,
)
from empire_stonks_ohlcv.results import AcquiredObject, PersistenceCounts
from empire_stonks_ohlcv.market_sessions import MarketSessionService
from empire_stonks_ohlcv.object_store import Clock
from empire_stonks_ohlcv.runner import (
    DEFAULT_DOMAIN,
    DEFAULT_SUBJECT_KEY,
    SAFE_FAILURE_MESSAGE,
    build_failure_summary,
)
from empire_stonks_ohlcv.source_conventions import (
    EODDATA_DAILY_SOURCE,
    EODDATA_SYMBOL_LIST_SOURCE,
)
from empire_stonks_ohlcv.validation import ProviderValidationResult


EODDATA_DAILY_JOB_NAME = "stonks_ohlcv_eoddata_daily"


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class EODDataDailyRunResult:
    """Compact secret-safe result for one completed EODData daily run."""

    run_id: UUID
    status: str
    effective_date: date
    report_object_id: UUID
    pdf_report_object_id: UUID
    market_pdf_report_object_id: UUID
    report_outcome: str
    listing_counts: PersistenceCounts
    bar_counts: PersistenceCounts
    skipped_inactive_bars: int
    row_rejection_count: int
    row_rejection_row_count: int
    failure_count: int
    warning_count: int
    expected_session_count: int
    eligible_session_count: int
    missing_session_count: int
    ineligible_exchange_count: int
    planned_exchange_count: int
    retry_count: int
    corrected_current_rows: int

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, UUID):
            raise TypeError("run_id must be a UUID.")
        if self.status != "succeeded":
            raise ValueError("status must be succeeded.")
        if type(self.effective_date) is not date:
            raise TypeError("effective_date must be a date.")
        if not isinstance(self.report_object_id, UUID):
            raise TypeError("report_object_id must be a UUID.")
        if not isinstance(self.pdf_report_object_id, UUID):
            raise TypeError("pdf_report_object_id must be a UUID.")
        if not isinstance(self.market_pdf_report_object_id, UUID):
            raise TypeError("market_pdf_report_object_id must be a UUID.")
        if self.report_outcome not in {"PASS", "WARN", "FAIL"}:
            raise ValueError("report_outcome is invalid.")
        if not isinstance(self.listing_counts, PersistenceCounts):
            raise TypeError("listing_counts must be PersistenceCounts.")
        if not isinstance(self.bar_counts, PersistenceCounts):
            raise TypeError("bar_counts must be PersistenceCounts.")
        for field_name in (
            "skipped_inactive_bars",
            "row_rejection_count",
            "row_rejection_row_count",
            "failure_count",
            "warning_count",
            "expected_session_count",
            "eligible_session_count",
            "missing_session_count",
            "ineligible_exchange_count",
            "planned_exchange_count",
            "retry_count",
            "corrected_current_rows",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field_name} must be an integer.")
            if value < 0:
                raise ValueError(f"{field_name} must be non-negative.")
        if self.eligible_session_count > self.expected_session_count:
            raise ValueError("eligible sessions cannot exceed expected sessions.")
        if self.missing_session_count > self.eligible_session_count:
            raise ValueError("missing sessions cannot exceed eligible sessions.")
        if self.ineligible_exchange_count > 3:
            raise ValueError("ineligible_exchange_count cannot exceed three.")
        if self.planned_exchange_count > 3:
            raise ValueError("planned_exchange_count cannot exceed three.")
        if self.corrected_current_rows > self.bar_counts.updated:
            raise ValueError("corrected rows cannot exceed updated bars.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": str(self.run_id),
            "status": self.status,
            "provider_code": EODDATA_PROVIDER_CODE,
            "effective_date": self.effective_date.isoformat(),
            "report_object_id": str(self.report_object_id),
            "pdf_report_object_id": str(self.pdf_report_object_id),
            "market_pdf_report_object_id": str(
                self.market_pdf_report_object_id
            ),
            "report_outcome": self.report_outcome,
            "listing_counts": self.listing_counts.to_dict(),
            "bar_counts": self.bar_counts.to_dict(),
            "skipped_inactive_bars": self.skipped_inactive_bars,
            "row_rejection_count": self.row_rejection_count,
            "row_rejection_row_count": self.row_rejection_row_count,
            "failure_count": self.failure_count,
            "warning_count": self.warning_count,
            "expected_session_count": self.expected_session_count,
            "eligible_session_count": self.eligible_session_count,
            "missing_session_count": self.missing_session_count,
            "ineligible_exchange_count": self.ineligible_exchange_count,
            "planned_exchange_count": self.planned_exchange_count,
            "retry_count": self.retry_count,
            "corrected_current_rows": self.corrected_current_rows,
        }


def run_eoddata_daily(
    *,
    run_service: RunService,
    connection: Any,
    object_store: ObjectStore,
    config: OHLCVConfig,
    effective_date: date,
    run_type: str,
    runner: str,
    runner_ref: dict[str, Any] | None = None,
    transport: EODDataHTTPTransport | None = None,
    sleep: Sleep = time.sleep,
    clock: Clock = _utc_now,
    session_service: MarketSessionService | None = None,
) -> EODDataDailyRunResult:
    """Run acquisition through report storage under one Core lifecycle."""

    _validate_inputs(
        run_service=run_service,
        connection=connection,
        object_store=object_store,
        config=config,
        effective_date=effective_date,
        runner=runner,
        sleep=sleep,
        clock=clock,
        session_service=session_service,
    )
    current = _aware_utc(clock())
    run_context = run_service.start_run(
        domain=DEFAULT_DOMAIN,
        job_name=EODDATA_DAILY_JOB_NAME,
        subject_key=DEFAULT_SUBJECT_KEY,
        effective_date=effective_date,
        run_type=run_type,
        runner=runner,
        runner_ref=runner_ref or {},
        params={
            "provider_code": EODDATA_PROVIDER_CODE,
            "configuration": config.to_safe_dict(),
        },
    )
    stage = "planning"
    try:
        service = session_service or MarketSessionService()
        plan = _plan(
            connection=connection,
            effective_date=effective_date,
            now=current,
            reconciliation_sessions=config.eoddata_reconciliation_sessions,
            session_service=service,
        )
        planned_exchanges = _planned_exchanges(plan)
        retry_events: list[EODDataRetryEvent] = []
        import_result: EODDataImportResult | None = None
        if planned_exchanges:
            stage = "acquisition"
            acquired_objects = _acquire(
                object_store=object_store,
                run_context=run_context,
                config=config,
                transport=transport,
                sleep=sleep,
                exchanges=planned_exchanges,
                retry_events=retry_events,
            )
            validation_results = _parse(
                object_store=object_store,
                acquired_objects=acquired_objects,
                effective_date=effective_date,
                markets=planned_exchanges,
            )
            stage = "persistence"
            import_result = _persist(
                connection=connection,
                effective_date=effective_date,
                acquired_objects=acquired_objects,
                validation_results=validation_results,
                exchanges=planned_exchanges,
            )
            stage = "planning"
            post_import_plan = _plan(
                connection=connection,
                effective_date=effective_date,
                now=current,
                reconciliation_sessions=(
                    config.eoddata_reconciliation_sessions
                ),
                session_service=service,
            )
        else:
            post_import_plan = plan
        stage = "reporting"
        (
            report,
            stored_report,
            stored_pdf_report,
            stored_market_pdf_report,
        ) = _report(
            connection=connection,
            object_store=object_store,
            run_context=run_context,
            config=config,
            import_result=import_result,
            plan=plan,
            post_import_plan=post_import_plan,
            retry_events=tuple(retry_events),
        )
        summary = _success_summary(
            import_result=import_result,
            plan=plan,
            post_import_plan=post_import_plan,
            retry_events=tuple(retry_events),
            report=report,
            stored_report=stored_report,
            stored_pdf_report=stored_pdf_report,
            stored_market_pdf_report=stored_market_pdf_report,
        )
        completed = run_service.complete_run(run_context.run_id, summary=summary)
        return EODDataDailyRunResult(
            run_id=completed.run_id,
            status=completed.status,
            effective_date=effective_date,
            report_object_id=stored_report.object_id,
            pdf_report_object_id=stored_pdf_report.object_id,
            market_pdf_report_object_id=stored_market_pdf_report.object_id,
            report_outcome=report["outcome"],
            listing_counts=_listing_counts(import_result),
            bar_counts=_bar_counts(import_result),
            skipped_inactive_bars=_skipped_inactive_bars(import_result),
            row_rejection_count=_row_rejection_count(import_result),
            row_rejection_row_count=_row_rejection_row_count(import_result),
            failure_count=report["hard_failures"]["total_count"],
            warning_count=_warning_count(import_result),
            expected_session_count=_expected_session_count(post_import_plan),
            eligible_session_count=_eligible_session_count(post_import_plan),
            missing_session_count=_missing_session_count(post_import_plan),
            ineligible_exchange_count=_ineligible_exchange_count(
                post_import_plan
            ),
            planned_exchange_count=len(planned_exchanges),
            retry_count=len(retry_events),
            corrected_current_rows=_corrected_current_rows(
                plan,
                import_result,
            ),
        )
    except Exception as exc:
        _rollback_quietly(connection)
        failed_stage = (
            exc.stage if isinstance(exc, OHLCVWorkflowError) else stage
        )
        run_service.fail_run(
            run_context.run_id,
            SAFE_FAILURE_MESSAGE,
            summary=build_failure_summary(
                EODDATA_PROVIDER_CODE,
                failed_stage=failed_stage,
                market=(
                    exc.market if isinstance(exc, OHLCVWorkflowError) else None
                ),
                source_code=(
                    exc.source_code
                    if isinstance(exc, OHLCVWorkflowError)
                    else None
                ),
            ),
        )
        raise


def _acquire(
    *,
    object_store: ObjectStore,
    run_context: RunContext,
    config: OHLCVConfig,
    transport: EODDataHTTPTransport | None,
    sleep: Sleep,
    exchanges: tuple[str, ...],
    retry_events: list[EODDataRetryEvent],
) -> tuple[AcquiredObject, ...]:
    try:
        acquired = acquire_eoddata_objects(
            object_store=object_store,
            run_context=run_context,
            config=config,
            transport=transport,
            sleep=sleep,
            exchanges=exchanges,
            retry_sink=retry_events.append,
        )
        _objects_by_source_market(
            acquired,
            markets=exchanges,
        )
        return acquired
    except Exception as exc:
        raise OHLCVWorkflowError(
            "acquisition",
            market=(
                exc.market if isinstance(exc, OHLCVAcquisitionError) else None
            ),
            source_code=(
                exc.source_code
                if isinstance(exc, OHLCVAcquisitionError)
                else None
            ),
        ) from exc


def _parse(
    *,
    object_store: ObjectStore,
    acquired_objects: tuple[AcquiredObject, ...],
    effective_date: date,
    markets: tuple[str, ...],
) -> tuple[ProviderValidationResult, ...]:
    try:
        objects = _objects_by_source_market(acquired_objects, markets=markets)
        results: list[ProviderValidationResult] = []
        for market in markets:
            try:
                symbols = parse_eoddata_symbol_list(
                    object_store.get_bytes(
                        objects[
                            (EODDATA_SYMBOL_LIST_SOURCE.source_code, market)
                        ].object_id
                    ),
                    exchange=market,
                )
            except Exception as exc:
                raise OHLCVWorkflowError(
                    "parsing",
                    market=market,
                    source_code=EODDATA_SYMBOL_LIST_SOURCE.source_code,
                ) from exc
            try:
                quotes = parse_eoddata_quote_list(
                    object_store.get_bytes(
                        objects[(EODDATA_DAILY_SOURCE.source_code, market)].object_id
                    ),
                    exchange=market,
                    effective_date=effective_date,
                    symbol_list=symbols,
                )
            except Exception as exc:
                raise OHLCVWorkflowError(
                    "parsing",
                    market=market,
                    source_code=EODDATA_DAILY_SOURCE.source_code,
                ) from exc
            results.append(quotes.to_validation_result(symbol_list=symbols))
        return tuple(results)
    except OHLCVWorkflowError:
        raise
    except Exception as exc:
        raise OHLCVWorkflowError("parsing") from exc


def _persist(
    *,
    connection: Any,
    effective_date: date,
    acquired_objects: tuple[AcquiredObject, ...],
    validation_results: tuple[ProviderValidationResult, ...],
    exchanges: tuple[str, ...],
) -> EODDataImportResult:
    try:
        result = import_eoddata_daily(
            connection=connection,
            effective_date=effective_date,
            acquired_objects=acquired_objects,
            validation_results=validation_results,
            exchanges=exchanges,
        )
        if not isinstance(result, EODDataImportResult):
            raise TypeError("EODData import returned an invalid result.")
        return result
    except OHLCVWorkflowError as exc:
        if exc.stage == "persistence":
            raise
        raise OHLCVWorkflowError("persistence") from exc
    except Exception as exc:
        raise OHLCVWorkflowError("persistence") from exc


def _report(
    *,
    connection: Any,
    object_store: ObjectStore,
    run_context: RunContext,
    config: OHLCVConfig,
    import_result: EODDataImportResult | None,
    plan: EODDataDailyPlan,
    post_import_plan: EODDataDailyPlan,
    retry_events: tuple[EODDataRetryEvent, ...],
) -> tuple[dict[str, Any], StoredObject, StoredObject, StoredObject]:
    try:
        with connection.cursor() as cursor:
            report = build_eoddata_report(
                cursor=cursor,
                import_result=import_result,
                plan=plan,
                post_import_plan=post_import_plan,
                retry_events=retry_events,
            )
            market_report = build_eoddata_daily_market_report(
                cursor=cursor,
                trading_date=plan.end_date,
            )
        stored = store_eoddata_report(
            object_store=object_store,
            run_context=run_context,
            config=config,
            report=report,
        )
        stored_pdf = store_eoddata_pdf_report(
            object_store=object_store,
            run_context=run_context,
            config=config,
            report=report,
        )
        stored_market_pdf = store_eoddata_daily_market_pdf_report(
            object_store=object_store,
            run_context=run_context,
            config=config,
            report=market_report,
        )
        if (
            not isinstance(stored, StoredObject)
            or stored.run_id != run_context.run_id
            or not isinstance(stored_pdf, StoredObject)
            or stored_pdf.run_id != run_context.run_id
            or not isinstance(stored_market_pdf, StoredObject)
            or stored_market_pdf.run_id != run_context.run_id
        ):
            raise TypeError("EODData report storage returned an invalid Core object.")
        return report, stored, stored_pdf, stored_market_pdf
    except Exception as exc:
        raise OHLCVWorkflowError("reporting") from exc


def _objects_by_source_market(
    acquired_objects: object,
    *,
    markets: tuple[str, ...],
) -> dict[tuple[str, str], AcquiredObject]:
    if not isinstance(acquired_objects, tuple) or any(
        not isinstance(item, AcquiredObject) for item in acquired_objects
    ):
        raise TypeError("EODData acquisition must return AcquiredObject records.")
    objects: dict[tuple[str, str], AcquiredObject] = {}
    for item in acquired_objects:
        market = next(
            (
                candidate
                for candidate in markets
                if item.filename == f"raw-{candidate.lower()}.json"
            ),
            None,
        )
        if market is None:
            raise ValueError("EODData acquired object has an invalid filename.")
        key = (item.source_code, market)
        if key in objects:
            raise ValueError("EODData acquisition returned a duplicate partition.")
        objects[key] = item
    expected = {
        (source.source_code, market)
        for source in (EODDATA_SYMBOL_LIST_SOURCE, EODDATA_DAILY_SOURCE)
        for market in markets
    }
    if set(objects) != expected:
        raise ValueError(
            "EODData acquisition must return both scoped source partitions."
        )
    return objects


def _success_summary(
    *,
    import_result: EODDataImportResult | None,
    plan: EODDataDailyPlan,
    post_import_plan: EODDataDailyPlan,
    retry_events: tuple[EODDataRetryEvent, ...],
    report: dict[str, Any],
    stored_report: StoredObject,
    stored_pdf_report: StoredObject,
    stored_market_pdf_report: StoredObject,
) -> dict[str, Any]:
    return {
        "provider_code": EODDATA_PROVIDER_CODE,
        "effective_date": plan.end_date.isoformat(),
        "planned_exchange_count": len(_planned_exchanges(plan)),
        "expected_session_count": _expected_session_count(post_import_plan),
        "eligible_session_count": _eligible_session_count(post_import_plan),
        "missing_session_count": _missing_session_count(post_import_plan),
        "ineligible_exchange_count": _ineligible_exchange_count(
            post_import_plan
        ),
        "retry_count": len(retry_events),
        "corrected_current_rows": _corrected_current_rows(
            plan,
            import_result,
        ),
        "acquired_object_count": (
            0 if import_result is None else len(import_result.acquired_objects)
        ),
        "source_snapshot_count": (
            0 if import_result is None else len(import_result.source_snapshots)
        ),
        "listing_counts": _listing_counts(import_result).to_dict(),
        "bar_counts": _bar_counts(import_result).to_dict(),
        "skipped_inactive_bars": _skipped_inactive_bars(import_result),
        "row_rejection_count": _row_rejection_count(import_result),
        "row_rejection_row_count": _row_rejection_row_count(import_result),
        "failure_count": report["hard_failures"]["total_count"],
        "warning_count": _warning_count(import_result),
        "report_object_id": str(stored_report.object_id),
        "pdf_report_object_id": str(stored_pdf_report.object_id),
        "market_pdf_report_object_id": str(
            stored_market_pdf_report.object_id
        ),
        "report_outcome": report["outcome"],
    }


def _validate_inputs(
    *,
    run_service: RunService,
    connection: Any,
    object_store: ObjectStore,
    config: OHLCVConfig,
    effective_date: date,
    runner: str,
    sleep: Sleep,
    clock: Clock,
    session_service: MarketSessionService | None,
) -> None:
    if not isinstance(run_service, RunService):
        raise TypeError("run_service must be a Core RunService.")
    if not isinstance(object_store, ObjectStore):
        raise TypeError("object_store must be a Core ObjectStore.")
    if not isinstance(config, OHLCVConfig):
        raise OHLCVConfigError("config must be an OHLCVConfig.")
    config.require_eoddata_credentials()
    if type(effective_date) is not date:
        raise OHLCVConfigError("effective_date must be a date.")
    if not isinstance(runner, str) or not runner.strip() or runner != runner.strip():
        raise OHLCVConfigError("runner must be non-blank and trimmed.")
    for method_name in ("cursor", "commit", "rollback"):
        if not callable(getattr(connection, method_name, None)):
            raise TypeError(
                "connection must provide cursor, commit, and rollback methods."
            )
    if not callable(sleep):
        raise TypeError("sleep must be callable.")
    if not callable(clock):
        raise TypeError("clock must be callable.")
    if session_service is not None and not isinstance(
        session_service,
        MarketSessionService,
    ):
        raise TypeError("session_service must be a MarketSessionService.")


def _plan(
    *,
    connection: Any,
    effective_date: date,
    now: datetime,
    reconciliation_sessions: int,
    session_service: MarketSessionService,
) -> EODDataDailyPlan:
    with connection.cursor() as cursor:
        return plan_eoddata_exchange_work(
            cursor=cursor,
            start_date=effective_date,
            end_date=effective_date,
            now=now,
            reconciliation_sessions=reconciliation_sessions,
            session_service=session_service,
        )


def _planned_exchanges(plan: EODDataDailyPlan) -> tuple[str, ...]:
    return tuple(
        exchange.exchange for exchange in plan.exchanges if exchange.work
    )


def _listing_counts(
    import_result: EODDataImportResult | None,
) -> PersistenceCounts:
    return (
        PersistenceCounts()
        if import_result is None
        else import_result.listing_counts
    )


def _bar_counts(
    import_result: EODDataImportResult | None,
) -> PersistenceCounts:
    return (
        PersistenceCounts()
        if import_result is None
        else import_result.bar_counts
    )


def _skipped_inactive_bars(
    import_result: EODDataImportResult | None,
) -> int:
    return 0 if import_result is None else import_result.skipped_inactive_bars


def _row_rejection_count(
    import_result: EODDataImportResult | None,
) -> int:
    if import_result is None:
        return 0
    return sum(item.rejected_records for item in import_result.row_rejections)


def _row_rejection_row_count(
    import_result: EODDataImportResult | None,
) -> int:
    if import_result is None:
        return 0
    return sum(item.rejected_rows for item in import_result.row_rejections)


def _warning_count(import_result: EODDataImportResult | None) -> int:
    return 0 if import_result is None else import_result.warnings.total_count


def _expected_session_count(plan: EODDataDailyPlan) -> int:
    return sum(len(item.expected_sessions) for item in plan.exchanges)


def _eligible_session_count(plan: EODDataDailyPlan) -> int:
    return sum(len(item.eligible_sessions) for item in plan.exchanges)


def _missing_session_count(plan: EODDataDailyPlan) -> int:
    return sum(len(item.missing_sessions) for item in plan.exchanges)


def _ineligible_exchange_count(plan: EODDataDailyPlan) -> int:
    return sum(
        item.status.value == "planned" and not item.eligible_sessions
        for item in plan.exchanges
    )


def _corrected_current_rows(
    plan: EODDataDailyPlan,
    import_result: EODDataImportResult | None,
) -> int:
    if import_result is None:
        return 0
    reconciliation_exchanges = {
        item.exchange
        for item in plan.work
        if item.reason is EODDataExchangeWorkReason.RECENT_RECONCILIATION
    }
    return sum(
        item.counts.updated
        for item in import_result.write_counts
        if item.record_kind == "bar"
        and item.market in reconciliation_exchanges
    )


def _aware_utc(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("clock must return a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime.")
    return value.astimezone(UTC)


def _rollback_quietly(connection: Any) -> None:
    try:
        connection.rollback()
    except Exception:
        pass
