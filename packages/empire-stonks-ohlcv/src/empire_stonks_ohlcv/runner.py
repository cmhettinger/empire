"""Core run lifecycle wrapper for OHLCV provider work."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Any, TypeAlias

from empire_core import RunContext, RunService

from empire_stonks_ohlcv.config import OHLCVConfig
from empire_stonks_ohlcv.exceptions import OHLCVConfigError, OHLCVWorkflowError
from empire_stonks_ohlcv.import_boundary import execute_import_boundary
from empire_stonks_ohlcv.provider_contract import (
    AcquireProviderObjects,
    ParseProviderObjects,
)
from empire_stonks_ohlcv.results import ProviderImportResult


DEFAULT_DOMAIN = "stonks"
DEFAULT_SUBJECT_KEY = "all_series"
SAFE_FAILURE_MESSAGE = "OHLCV provider run failed."

JOB_PROVIDER_CODES = MappingProxyType(
    {
        "stonks_ohlcv_eoddata_daily": "EODDATA",
        "stonks_ohlcv_stooq_daily": "STOOQ",
        "stonks_ohlcv_yahoo_daily": "YAHOO",
        "stonks_ohlcv_stooq_backfill": "STOOQ",
    }
)

ProviderRunWork: TypeAlias = Callable[[RunContext], ProviderImportResult]


@dataclass(frozen=True)
class OHLCVRunResult:
    """Completed Core run context and its provider import result."""

    run_context: RunContext
    import_result: ProviderImportResult

    @property
    def summary(self) -> dict[str, Any]:
        return build_run_summary(self.import_result)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": str(self.run_context.run_id),
            "status": self.run_context.status,
            "summary": self.summary,
        }


def run_provider_import(
    *,
    run_service: RunService,
    config: OHLCVConfig,
    provider_code: str,
    job_name: str,
    effective_date: date,
    run_type: str,
    runner: str,
    work: ProviderRunWork,
    subject_key: str = DEFAULT_SUBJECT_KEY,
    runner_ref: dict[str, Any] | None = None,
) -> OHLCVRunResult:
    """Track one provider operation through the Core run lifecycle."""

    _validate_run_inputs(
        config=config,
        provider_code=provider_code,
        job_name=job_name,
        effective_date=effective_date,
        subject_key=subject_key,
        work=work,
    )
    run_context = run_service.start_run(
        domain=DEFAULT_DOMAIN,
        job_name=job_name,
        subject_key=subject_key,
        effective_date=effective_date,
        run_type=run_type,
        runner=runner,
        runner_ref=runner_ref or {},
        params={
            "provider_code": provider_code,
            "configuration": config.to_safe_dict(),
        },
    )
    try:
        import_result = work(run_context)
        if not isinstance(import_result, ProviderImportResult):
            raise TypeError("work must return a ProviderImportResult.")
        if import_result.provider_code != provider_code:
            raise ValueError("work returned a result for a different provider.")
        summary = build_run_summary(import_result)
        completed_context = run_service.complete_run(
            run_context.run_id,
            summary=summary,
        )
        return OHLCVRunResult(
            run_context=completed_context,
            import_result=import_result,
        )
    except Exception as exc:
        failed_stage = exc.stage if isinstance(exc, OHLCVWorkflowError) else None
        run_service.fail_run(
            run_context.run_id,
            SAFE_FAILURE_MESSAGE,
            summary=build_failure_summary(
                provider_code,
                failed_stage=failed_stage,
            ),
        )
        raise


def run_provider_pipeline(
    *,
    run_service: RunService,
    connection: Any,
    config: OHLCVConfig,
    provider_code: str,
    job_name: str,
    effective_date: date,
    run_type: str,
    runner: str,
    acquire: AcquireProviderObjects,
    parse: ParseProviderObjects,
    subject_key: str = DEFAULT_SUBJECT_KEY,
    runner_ref: dict[str, Any] | None = None,
) -> OHLCVRunResult:
    """Run injected provider acquisition and parsing through shared boundaries.

    The caller owns ``connection``. This seam neither creates nor closes it, so
    CLIs, Airflow, and tests can supply their normal runtime connection scope.
    """

    _validate_pipeline_collaborators(
        connection=connection,
        acquire=acquire,
        parse=parse,
    )

    def work(run_context: RunContext) -> ProviderImportResult:
        return execute_import_boundary(
            connection=connection,
            run_context=run_context,
            provider_code=provider_code,
            acquire=acquire,
            parse=parse,
        )

    return run_provider_import(
        run_service=run_service,
        config=config,
        provider_code=provider_code,
        job_name=job_name,
        effective_date=effective_date,
        run_type=run_type,
        runner=runner,
        work=work,
        subject_key=subject_key,
        runner_ref=runner_ref,
    )


def build_run_summary(import_result: ProviderImportResult) -> dict[str, Any]:
    """Build the compact secret-safe Core summary for a successful run."""

    if not isinstance(import_result, ProviderImportResult):
        raise TypeError("import_result must be a ProviderImportResult.")
    return {
        "provider_code": import_result.provider_code,
        "acquired_object_count": len(import_result.acquired_objects),
        "listing_counts": import_result.listing_counts.to_dict(),
        "bar_counts": import_result.bar_counts.to_dict(),
        "accepted": import_result.accepted,
        "rejected": import_result.rejected,
        "failure_count": len(import_result.failures),
        "warning_count": len(import_result.warnings),
    }


def build_failure_summary(
    provider_code: str,
    *,
    failed_stage: str | None = None,
) -> dict[str, str]:
    """Build a detail-free Core summary for a failed provider run."""

    summary = {
        "provider_code": provider_code,
        "outcome": "failed",
    }
    if failed_stage is not None:
        summary["failed_stage"] = failed_stage
    return summary


def _validate_run_inputs(
    *,
    config: OHLCVConfig,
    provider_code: str,
    job_name: str,
    effective_date: date,
    subject_key: str,
    work: ProviderRunWork,
) -> None:
    if not isinstance(config, OHLCVConfig):
        raise OHLCVConfigError("config must be an OHLCVConfig.")
    expected_provider = JOB_PROVIDER_CODES.get(job_name)
    if expected_provider is None:
        raise OHLCVConfigError("job_name is not a supported OHLCV job.")
    if provider_code != expected_provider:
        raise OHLCVConfigError("provider_code does not match job_name.")
    if not isinstance(effective_date, date):
        raise OHLCVConfigError("effective_date must be a date.")
    if (
        not isinstance(subject_key, str)
        or not subject_key.strip()
        or subject_key != subject_key.strip()
    ):
        raise OHLCVConfigError("subject_key must be non-blank and trimmed.")
    if not callable(work):
        raise TypeError("work must be callable.")


def _validate_pipeline_collaborators(
    *,
    connection: Any,
    acquire: AcquireProviderObjects,
    parse: ParseProviderObjects,
) -> None:
    for method_name in ("cursor", "commit", "rollback"):
        if not callable(getattr(connection, method_name, None)):
            raise TypeError(
                "connection must provide cursor, commit, and rollback methods."
            )
    if not callable(acquire):
        raise TypeError("acquire must be callable.")
    if not callable(parse):
        raise TypeError("parse must be callable.")
