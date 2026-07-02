"""Package-owned stage wrappers for the SEC daily refresh workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from empire_core import ObjectStore, RunContext as CoreRunContext, RunService

from empire_stonks_securities.acquisition import SecDownloader
from empire_stonks_securities.config import StonksSecuritiesConfig
from empire_stonks_securities.conflicts import (
    ConflictRunContext,
    generate_phase_2a_conflict_report,
    write_conflict_report_to_object_store,
)
from empire_stonks_securities.daily_summary import (
    DailySummaryRunContext,
    generate_daily_refresh_summary_report,
    write_daily_summary_pdf_to_object_store,
    write_daily_summary_report_to_object_store,
)
from empire_stonks_securities.issuers import upsert_sec_issuers_from_provider_observations
from empire_stonks_securities.listings import upsert_sec_listings_from_provider_observations
from empire_stonks_securities.observations import run_stonks_securities_daily_observation_writer
from empire_stonks_securities.runner import (
    DEFAULT_DAILY_SOURCE_KEYS,
    StonksSecuritiesAcquisitionRunResult,
    run_stonks_securities_daily_to_object_store,
)
from empire_stonks_securities.securities import upsert_sec_securities_from_provider_observations
from empire_stonks_securities.validation import (
    ValidationRunContext,
    generate_phase_2a_validation_report,
    write_validation_report_to_object_store,
)
from empire_stonks_securities.verification import (
    VerifyRunContext,
    generate_verify_report,
    verify_stonks_securities_daily_sources,
    write_verify_report_to_object_store,
)


DEFAULT_DAILY_REFRESH_DAG_ID = "stonks_securities_sec_daily_scrape"


@dataclass(frozen=True)
class DailyRefreshRunContext:
    """Explicit workflow context shared by SEC daily refresh stages."""

    workflow_id: str | None = DEFAULT_DAILY_REFRESH_DAG_ID
    run_id: str | None = None
    source_run_id: str | None = None
    logical_date: str | None = None
    environment: str | None = None

    def for_source_run(self, source_run_id: str | UUID) -> "DailyRefreshRunContext":
        return DailyRefreshRunContext(
            workflow_id=self.workflow_id,
            run_id=self.run_id,
            source_run_id=str(source_run_id),
            logical_date=self.logical_date,
            environment=self.environment,
        )

    def to_report_context(self, context_type: type[Any]) -> Any:
        return context_type(
            dag_id=self.workflow_id,
            run_id=self.run_id,
            source_run_id=self.source_run_id,
            logical_date=self.logical_date,
            environment=self.environment,
        )


@dataclass(frozen=True)
class DailyRefreshReportRef:
    """Stored report reference passed between daily refresh stages."""

    object_key: str
    filename: str
    object_id: str

    @classmethod
    def from_stored_object(cls, stored: Any) -> "DailyRefreshReportRef":
        return cls(
            object_key=stored.object_key,
            filename=stored.filename,
            object_id=str(stored.object_id),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "object_key": self.object_key,
            "filename": self.filename,
            "object_id": self.object_id,
        }


@dataclass(frozen=True)
class DailyRefreshStageResult:
    """Serializable result for one SEC daily refresh stage."""

    stage: str
    source_run_id: str
    payload: dict[str, Any]
    report: DailyRefreshReportRef | None = None
    pdf_report: DailyRefreshReportRef | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "stage": self.stage,
            "source_run_id": self.source_run_id,
            **self.payload,
        }
        if self.report is not None:
            result.update(self.report.to_dict())
        if self.pdf_report is not None:
            result.update(
                {
                    "pdf_object_key": self.pdf_report.object_key,
                    "pdf_filename": self.pdf_report.filename,
                    "pdf_object_id": self.pdf_report.object_id,
                }
            )
        return result


def collect_sec_sources_stage(
    *,
    config: StonksSecuritiesConfig,
    downloader: SecDownloader,
    run_service: RunService,
    object_store: ObjectStore,
    run_type: str,
    runner: str,
    runner_ref: dict | None = None,
    source_keys: tuple[str, ...] = DEFAULT_DAILY_SOURCE_KEYS,
    **kwargs: Any,
) -> DailyRefreshStageResult:
    result = run_stonks_securities_daily_to_object_store(
        config=config,
        downloader=downloader,
        run_service=run_service,
        object_store=object_store,
        run_type=run_type,
        runner=runner,
        runner_ref=runner_ref,
        source_keys=source_keys,
        **kwargs,
    )
    return _acquisition_result_to_stage(result)


def verify_sec_sources_stage(
    *,
    object_store: ObjectStore,
    run_service: RunService,
    source_run_id: str | UUID,
    run_context: DailyRefreshRunContext,
    generated_at: datetime | None = None,
) -> DailyRefreshStageResult:
    generated_at = generated_at or datetime.now(UTC)
    stage_context = run_context.for_source_run(source_run_id)
    storage_run_context = _require_run_context(run_service, source_run_id)
    result = verify_stonks_securities_daily_sources(
        object_store=object_store,
        input_run_id=source_run_id,
    )
    report = generate_verify_report(
        result=result,
        run_context=stage_context.to_report_context(VerifyRunContext),
        generated_at=generated_at,
    )
    stored = write_verify_report_to_object_store(
        report=report,
        object_store=object_store,
        generated_at=generated_at,
        logical_date=stage_context.logical_date,
        storage_run_context=storage_run_context,
    )
    return DailyRefreshStageResult(
        stage="verify",
        source_run_id=str(source_run_id),
        payload={**result.to_dict(), "summary": report["summary"]},
        report=DailyRefreshReportRef.from_stored_object(stored),
    )


def write_sec_observations_stage(
    *,
    connection: Any,
    object_store: ObjectStore,
    source_run_id: str | UUID,
) -> DailyRefreshStageResult:
    result = run_stonks_securities_daily_observation_writer(
        connection=connection,
        object_store=object_store,
        input_run_id=source_run_id,
    )
    return DailyRefreshStageResult(
        stage="observations",
        source_run_id=str(source_run_id),
        payload=result.to_dict(),
    )


def upsert_sec_issuers_stage(
    *,
    connection: Any,
    source_run_id: str | UUID,
) -> DailyRefreshStageResult:
    result = upsert_sec_issuers_from_provider_observations(
        connection=connection,
        source_run_id=source_run_id,
    )
    return DailyRefreshStageResult(
        stage="issuers",
        source_run_id=str(source_run_id),
        payload=result.to_dict(),
    )


def upsert_sec_securities_stage(
    *,
    connection: Any,
    source_run_id: str | UUID,
) -> DailyRefreshStageResult:
    result = upsert_sec_securities_from_provider_observations(
        connection=connection,
        source_run_id=source_run_id,
    )
    return DailyRefreshStageResult(
        stage="securities",
        source_run_id=str(source_run_id),
        payload=result.to_dict(),
    )


def upsert_sec_listings_stage(
    *,
    connection: Any,
    source_run_id: str | UUID,
) -> DailyRefreshStageResult:
    result = upsert_sec_listings_from_provider_observations(
        connection=connection,
        source_run_id=source_run_id,
    )
    return DailyRefreshStageResult(
        stage="listings",
        source_run_id=str(source_run_id),
        payload=result.to_dict(),
    )


def generate_validation_report_stage(
    *,
    connection: Any,
    object_store: ObjectStore,
    run_service: RunService,
    source_run_id: str | UUID,
    run_context: DailyRefreshRunContext,
    generated_at: datetime | None = None,
) -> DailyRefreshStageResult:
    generated_at = generated_at or datetime.now(UTC)
    stage_context = run_context.for_source_run(source_run_id)
    storage_run_context = _require_run_context(run_service, source_run_id)
    report = generate_phase_2a_validation_report(
        connection=connection,
        run_context=stage_context.to_report_context(ValidationRunContext),
        source_run_id=str(source_run_id),
        generated_at=generated_at,
    )
    stored = write_validation_report_to_object_store(
        report=report,
        object_store=object_store,
        generated_at=generated_at,
        logical_date=stage_context.logical_date,
        storage_run_context=storage_run_context,
    )
    return DailyRefreshStageResult(
        stage="validation",
        source_run_id=str(source_run_id),
        payload={"summary": report["summary"]},
        report=DailyRefreshReportRef.from_stored_object(stored),
    )


def generate_conflict_report_stage(
    *,
    connection: Any,
    object_store: ObjectStore,
    run_service: RunService,
    source_run_id: str | UUID,
    run_context: DailyRefreshRunContext,
    generated_at: datetime | None = None,
) -> DailyRefreshStageResult:
    generated_at = generated_at or datetime.now(UTC)
    stage_context = run_context.for_source_run(source_run_id)
    storage_run_context = _require_run_context(run_service, source_run_id)
    report = generate_phase_2a_conflict_report(
        connection=connection,
        run_context=stage_context.to_report_context(ConflictRunContext),
        source_run_id=str(source_run_id),
        generated_at=generated_at,
    )
    stored = write_conflict_report_to_object_store(
        report=report,
        object_store=object_store,
        generated_at=generated_at,
        logical_date=stage_context.logical_date,
        storage_run_context=storage_run_context,
    )
    return DailyRefreshStageResult(
        stage="conflicts",
        source_run_id=str(source_run_id),
        payload={"summary": report["summary"]},
        report=DailyRefreshReportRef.from_stored_object(stored),
    )


def generate_daily_refresh_summary_stage(
    *,
    connection: Any,
    object_store: ObjectStore,
    run_service: RunService,
    source_run_id: str | UUID,
    run_context: DailyRefreshRunContext,
    verify_report_object_id: str | UUID | None = None,
    validation_report_object_id: str | UUID | None = None,
    conflict_report_object_id: str | UUID | None = None,
    generated_at: datetime | None = None,
) -> DailyRefreshStageResult:
    generated_at = generated_at or datetime.now(UTC)
    stage_context = run_context.for_source_run(source_run_id)
    storage_run_context = _require_run_context(run_service, source_run_id)
    report = generate_daily_refresh_summary_report(
        connection=connection,
        object_store=object_store,
        run_context=stage_context.to_report_context(DailySummaryRunContext),
        source_run_id=str(source_run_id),
        verify_report_object_id=verify_report_object_id,
        validation_report_object_id=validation_report_object_id,
        conflict_report_object_id=conflict_report_object_id,
        generated_at=generated_at,
    )
    stored = write_daily_summary_report_to_object_store(
        report=report,
        object_store=object_store,
        generated_at=generated_at,
        logical_date=stage_context.logical_date,
        storage_run_context=storage_run_context,
    )
    stored_pdf = write_daily_summary_pdf_to_object_store(
        report=report,
        object_store=object_store,
        generated_at=generated_at,
        logical_date=stage_context.logical_date,
        storage_run_context=storage_run_context,
    )
    return DailyRefreshStageResult(
        stage="summary",
        source_run_id=str(source_run_id),
        payload={"summary": report["summary"]},
        report=DailyRefreshReportRef.from_stored_object(stored),
        pdf_report=DailyRefreshReportRef.from_stored_object(stored_pdf),
    )


def _acquisition_result_to_stage(
    result: StonksSecuritiesAcquisitionRunResult,
) -> DailyRefreshStageResult:
    return DailyRefreshStageResult(
        stage="scrape",
        source_run_id=str(result.run_context.run_id),
        payload={
            "run_id": str(result.run_context.run_id),
            "downloaded_count": result.downloaded_count,
            "skipped_count": result.skipped_count,
            "source_count": len(result.results),
            "sources": [
                {
                    "source_code": item.source_code,
                    "status": item.status,
                    "object_key": item.object_key,
                    "filename": item.filename,
                    "metadata_filename": item.metadata_filename,
                    "object_id": item.object_id,
                    "metadata_object_id": item.metadata_object_id,
                }
                for item in result.results
            ],
        },
    )


def _require_run_context(
    run_service: RunService,
    source_run_id: str | UUID,
) -> CoreRunContext:
    parsed_source_run_id = (
        source_run_id if isinstance(source_run_id, UUID) else UUID(str(source_run_id))
    )
    run_context = run_service.get_run_context(parsed_source_run_id)
    if run_context is None:
        raise RuntimeError(f"Run context not found for source_run_id={source_run_id}")
    return run_context
