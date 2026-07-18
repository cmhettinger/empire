"""Package-owned daily EODData run sequencing."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from empire_core import ObjectStore, RunContext, RunService, StoredObject

from empire_stonks_ohlcv.config import OHLCVConfig
from empire_stonks_ohlcv.eoddata import (
    EODDATA_PROVIDER_CODE,
    EODDataHTTPTransport,
    Sleep,
    acquire_eoddata_objects,
)
from empire_stonks_ohlcv.eoddata_import import (
    EODDataImportResult,
    import_eoddata_daily,
)
from empire_stonks_ohlcv.eoddata_quotes import parse_eoddata_quote_list
from empire_stonks_ohlcv.eoddata_symbols import parse_eoddata_symbol_list
from empire_stonks_ohlcv.exceptions import (
    OHLCVAcquisitionError,
    OHLCVConfigError,
    OHLCVWorkflowError,
)
from empire_stonks_ohlcv.reporting import (
    build_eoddata_report,
    store_eoddata_pdf_report,
    store_eoddata_report,
)
from empire_stonks_ohlcv.results import AcquiredObject, PersistenceCounts
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


@dataclass(frozen=True)
class EODDataDailyRunResult:
    """Compact secret-safe result for one completed EODData daily run."""

    run_id: UUID
    status: str
    effective_date: date
    report_object_id: UUID
    pdf_report_object_id: UUID
    report_outcome: str
    listing_counts: PersistenceCounts
    bar_counts: PersistenceCounts
    skipped_inactive_bars: int
    row_rejection_count: int
    row_rejection_row_count: int
    failure_count: int
    warning_count: int

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
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field_name} must be an integer.")
            if value < 0:
                raise ValueError(f"{field_name} must be non-negative.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": str(self.run_id),
            "status": self.status,
            "provider_code": EODDATA_PROVIDER_CODE,
            "effective_date": self.effective_date.isoformat(),
            "report_object_id": str(self.report_object_id),
            "pdf_report_object_id": str(self.pdf_report_object_id),
            "report_outcome": self.report_outcome,
            "listing_counts": self.listing_counts.to_dict(),
            "bar_counts": self.bar_counts.to_dict(),
            "skipped_inactive_bars": self.skipped_inactive_bars,
            "row_rejection_count": self.row_rejection_count,
            "row_rejection_row_count": self.row_rejection_row_count,
            "failure_count": self.failure_count,
            "warning_count": self.warning_count,
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
    )
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
    try:
        acquired_objects = _acquire(
            object_store=object_store,
            run_context=run_context,
            config=config,
            transport=transport,
            sleep=sleep,
        )
        validation_results = _parse(
            object_store=object_store,
            acquired_objects=acquired_objects,
            effective_date=effective_date,
            markets=config.eoddata_exchanges,
        )
        import_result = _persist(
            connection=connection,
            effective_date=effective_date,
            acquired_objects=acquired_objects,
            validation_results=validation_results,
        )
        report, stored_report, stored_pdf_report = _report(
            connection=connection,
            object_store=object_store,
            run_context=run_context,
            config=config,
            import_result=import_result,
        )
        summary = _success_summary(
            import_result=import_result,
            report=report,
            stored_report=stored_report,
            stored_pdf_report=stored_pdf_report,
        )
        completed = run_service.complete_run(run_context.run_id, summary=summary)
        return EODDataDailyRunResult(
            run_id=completed.run_id,
            status=completed.status,
            effective_date=effective_date,
            report_object_id=stored_report.object_id,
            pdf_report_object_id=stored_pdf_report.object_id,
            report_outcome=report["outcome"],
            listing_counts=import_result.listing_counts,
            bar_counts=import_result.bar_counts,
            skipped_inactive_bars=import_result.skipped_inactive_bars,
            row_rejection_count=sum(
                item.rejected_records for item in import_result.row_rejections
            ),
            row_rejection_row_count=sum(
                item.rejected_rows for item in import_result.row_rejections
            ),
            failure_count=report["hard_failures"]["total_count"],
            warning_count=import_result.warnings.total_count,
        )
    except Exception as exc:
        _rollback_quietly(connection)
        failed_stage = exc.stage if isinstance(exc, OHLCVWorkflowError) else None
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
) -> tuple[AcquiredObject, ...]:
    try:
        acquired = acquire_eoddata_objects(
            object_store=object_store,
            run_context=run_context,
            config=config,
            transport=transport,
            sleep=sleep,
        )
        _objects_by_source_market(
            acquired,
            markets=config.eoddata_exchanges,
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
) -> EODDataImportResult:
    try:
        result = import_eoddata_daily(
            connection=connection,
            effective_date=effective_date,
            acquired_objects=acquired_objects,
            validation_results=validation_results,
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
    import_result: EODDataImportResult,
) -> tuple[dict[str, Any], StoredObject, StoredObject]:
    try:
        with connection.cursor() as cursor:
            report = build_eoddata_report(
                cursor=cursor,
                import_result=import_result,
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
        if (
            not isinstance(stored, StoredObject)
            or stored.run_id != run_context.run_id
            or not isinstance(stored_pdf, StoredObject)
            or stored_pdf.run_id != run_context.run_id
        ):
            raise TypeError("EODData report storage returned an invalid Core object.")
        return report, stored, stored_pdf
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
        raise ValueError("EODData acquisition must return all six partitions.")
    return objects


def _success_summary(
    *,
    import_result: EODDataImportResult,
    report: dict[str, Any],
    stored_report: StoredObject,
    stored_pdf_report: StoredObject,
) -> dict[str, Any]:
    return {
        "provider_code": EODDATA_PROVIDER_CODE,
        "effective_date": import_result.effective_date.isoformat(),
        "acquired_object_count": len(import_result.acquired_objects),
        "source_snapshot_count": len(import_result.source_snapshots),
        "listing_counts": import_result.listing_counts.to_dict(),
        "bar_counts": import_result.bar_counts.to_dict(),
        "skipped_inactive_bars": import_result.skipped_inactive_bars,
        "row_rejection_count": sum(
            item.rejected_records for item in import_result.row_rejections
        ),
        "row_rejection_row_count": sum(
            item.rejected_rows for item in import_result.row_rejections
        ),
        "failure_count": report["hard_failures"]["total_count"],
        "warning_count": import_result.warnings.total_count,
        "report_object_id": str(stored_report.object_id),
        "pdf_report_object_id": str(stored_pdf_report.object_id),
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


def _rollback_quietly(connection: Any) -> None:
    try:
        connection.rollback()
    except Exception:
        pass
