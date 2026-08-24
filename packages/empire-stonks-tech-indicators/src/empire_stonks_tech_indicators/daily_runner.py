"""Package-owned daily technical-indicator workflow orchestration."""

from __future__ import annotations

import math
import platform
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from importlib.metadata import PackageNotFoundError, version
from typing import Any
from uuid import UUID

from empire_core import ObjectStore, RunService

from empire_stonks_tech_indicators.affected_ranges import (
    AffectedRangeReason,
    plan_affected_ranges,
)
from empire_stonks_tech_indicators.arrays import normalize_source_bars
from empire_stonks_tech_indicators.assembly import assemble_feature_rows
from empire_stonks_tech_indicators.config import (
    HARD_MAX_TRANSACTION_ROWS,
    TechIndicatorsConfig,
)
from empire_stonks_tech_indicators.core_lifecycle import TechIndicatorsCoreRun
from empire_stonks_tech_indicators.daily_publication import (
    DailyCandidateListing,
    create_daily_candidate,
    prepare_daily_candidate,
    select_daily_target_slots,
)
from empire_stonks_tech_indicators.daily_scope import (
    ResolvedTechIndicatorsDailyScope,
    TechIndicatorsDailyScope,
    resolve_tech_indicators_daily_scope,
)
from empire_stonks_tech_indicators.exceptions import TechIndicatorsWorkflowError
from empire_stonks_tech_indicators.failure_safety import (
    close_core_after_failure,
    is_workflow_cancellation,
    safe_workflow_error,
    terminalize_unpublished_candidate,
)
from empire_stonks_tech_indicators.models import (
    FeatureCounts,
    FeatureRow,
    ReasonCount,
    TechIndicatorsScope,
    TechIndicatorsSummary,
)
from empire_stonks_tech_indicators.persistence import (
    SlotWriteCounts,
    TechIndicatorsPayloadSlot,
    upsert_feature_rows,
)
from empire_stonks_tech_indicators.publication import (
    InPlaceSlotChanges,
    finalize_publication,
)
from empire_stonks_tech_indicators.published_queries import (
    PublishedModelInputSnapshot,
    PublishedReadinessToken,
    read_published_model_inputs,
)
from empire_stonks_tech_indicators.queries import (
    BenchmarkHistory,
    EligibleListing,
    iter_source_bar_pages,
    load_spx_benchmark_history,
    select_eligible_listings,
)
from empire_stonks_tech_indicators.reporting_queries import (
    ReportDatabaseSummary,
    select_report_database_summary,
)
from empire_stonks_tech_indicators.reports import (
    DAILY_CORE_JOB_NAME,
    DAILY_REPORT_ID,
    PublicationMethod,
    PublicationReadiness,
    PublicationReportPhase,
    ReportBackfill,
    ReportCounts,
    ReportCoverage,
    ReportDatabasePerformance,
    ReportIdentity,
    ReportLock,
    ReportNativeValueSemantics,
    ReportOutcome,
    ReportPerformance,
    ReportProviderEvidence,
    ReportPublication,
    ReportReasonCount,
    ReportSourceBenchmark,
    ReportSourceReadiness,
    ReportThroughput,
    ReportVersions,
    ReportWrites,
    SourceReadinessStatus,
    TechIndicatorsReport,
    WorkflowKind,
)
from empire_stonks_tech_indicators.report_storage import (
    store_tech_indicators_json_report,
    store_tech_indicators_pdf_report,
)
from empire_stonks_tech_indicators.state import (
    ListingStateComparison,
    iter_state_comparison_pages,
)
from empire_stonks_tech_indicators.subject_policy import is_spx_supported_subject
from empire_stonks_tech_indicators.validation import validate_feature_rows
from empire_stonks_tech_indicators.writer_lock import (
    TECH_INDICATORS_LOCK_CONTENDED_MESSAGE,
    WriterLockOutcome,
    acquire_tech_indicators_writer_lock,
)


Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class TechIndicatorsDailyRunResult:
    """Compact secret-safe result for a completed or contended daily run."""

    status: str
    effective_date: date
    run_id: UUID | None = None
    publication_id: UUID | None = None
    json_report_object_id: UUID | None = None
    pdf_report_object_id: UUID | None = None
    outcome: ReportOutcome | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"succeeded", "contended"}:
            raise ValueError("status must be succeeded or contended.")
        if type(self.effective_date) is not date:
            raise TypeError("effective_date must be a date.")
        if self.status == "contended":
            if any(
                value is not None
                for value in (
                    self.run_id,
                    self.publication_id,
                    self.json_report_object_id,
                    self.pdf_report_object_id,
                    self.outcome,
                )
            ) or self.message != TECH_INDICATORS_LOCK_CONTENDED_MESSAGE:
                raise ValueError("contended result must not contain workflow state.")
        elif (
            not isinstance(self.run_id, UUID)
            or not isinstance(self.json_report_object_id, UUID)
            or not isinstance(self.pdf_report_object_id, UUID)
            or self.outcome
            not in {ReportOutcome.PASS, ReportOutcome.WARN, ReportOutcome.NO_OP}
            or self.message is not None
        ):
            raise ValueError("succeeded result is incomplete.")
        if self.outcome is ReportOutcome.NO_OP and self.publication_id is not None:
            raise ValueError("NO_OP cannot create a publication.")

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "effective_date": self.effective_date.isoformat(),
            "run_id": None if self.run_id is None else str(self.run_id),
            "publication_id": (
                None if self.publication_id is None else str(self.publication_id)
            ),
            "json_report_object_id": (
                None
                if self.json_report_object_id is None
                else str(self.json_report_object_id)
            ),
            "pdf_report_object_id": (
                None
                if self.pdf_report_object_id is None
                else str(self.pdf_report_object_id)
            ),
            "outcome": None if self.outcome is None else self.outcome.value,
            "message": self.message,
        }


def run_tech_indicators_daily(
    *,
    run_service: RunService,
    connection: Any,
    lock_connection_factory: Callable[[], Any],
    object_store: ObjectStore,
    config: TechIndicatorsConfig,
    scope: TechIndicatorsDailyScope,
    run_type: str,
    runner: str,
    clock: Clock = _utc_now,
) -> TechIndicatorsDailyRunResult:
    """Run one daily scope through no-op, dry-run, or atomic publication."""

    _validate_inputs(
        run_service=run_service,
        connection=connection,
        lock_connection_factory=lock_connection_factory,
        object_store=object_store,
        config=config,
        scope=scope,
        clock=clock,
    )
    acquired = acquire_tech_indicators_writer_lock(
        connection_factory=lock_connection_factory
    )
    if acquired.outcome is WriterLockOutcome.CONTENDED:
        return TechIndicatorsDailyRunResult(
            status="contended",
            effective_date=scope.effective_date,
            message=acquired.message,
        )
    lock = acquired.lock
    assert lock is not None

    core_run: TechIndicatorsCoreRun | None = None
    publication_id: UUID | None = None
    publication_was_published = False
    json_report_object_id: UUID | None = None
    pdf_report_object_id: UUID | None = None
    summary = TechIndicatorsSummary()
    try:
        with lock:
            resolved = _resolve(connection, scope=scope, config=config)
            core_run = TechIndicatorsCoreRun.start(
                run_service=run_service,
                workflow_kind=WorkflowKind.DAILY,
                effective_date=scope.effective_date,
                run_type=run_type,
                runner=runner,
                subject_key=resolved.subject_key,
                calculation_version=config.calculation_version,
            )
            if not resolved.ready:
                raise TechIndicatorsWorkflowError(
                    "Technical-indicator source readiness is not satisfied."
                )
            started_at = _aware_utc(clock())
            plan, listings, comparisons = _plan(
                connection,
                resolved=resolved,
                config=config,
            )
            if plan.is_noop:
                return _complete_zero_work(
                    connection=connection,
                    object_store=object_store,
                    config=config,
                    resolved=resolved,
                    core_run=core_run,
                    lock=lock,
                    started_at=started_at,
                    clock=clock,
                )
            if any(
                AffectedRangeReason.VERSION_DRIFT in item.reasons
                for item in plan.ranges
            ):
                raise TechIndicatorsWorkflowError(
                    "Version rebuild requires the staged J9.6 workflow."
                )

            lock.heartbeat()
            core_run.heartbeat()
            benchmark = _benchmark_history(
                connection,
                resolved=resolved,
                listings=listings,
                config=config,
            )
            rows, read_page_count, largest_read_page_rows = _calculate(
                connection,
                plan=plan,
                listings=listings,
                benchmark=benchmark,
                run_id=core_run.run_context.run_id,
                config=config,
                calculated_at=_aware_utc(clock()),
            )
            if len(rows) > HARD_MAX_TRANSACTION_ROWS:
                raise TechIndicatorsWorkflowError(
                    "Daily work exceeds the 25,000-row in-place ceiling; "
                    "use the staged J9.6 workflow."
                )
            changes, memberships = _candidate_image(
                connection,
                rows=rows,
                listings=listings,
                comparisons=comparisons,
                benchmark=benchmark,
            )
            publication_kind = _publication_kind(plan.ranges)
            publication_id = _create_candidate(
                connection,
                resolved=resolved,
                core_run=core_run,
                memberships=memberships,
                benchmark=benchmark,
                publication_kind=publication_kind,
                dry_run=scope.dry_run,
            )
            preview_counts, database_summary, write_batch_count = _preview(
                connection,
                publication_id=publication_id,
                scope=_resolved_scope(resolved),
                effective_date=scope.effective_date,
                changes=changes,
                config=config,
            )
            report_publication_id = None if scope.dry_run else publication_id
            finished_at = _aware_utc(clock())
            report = _build_report(
                resolved=resolved,
                core_run=core_run,
                publication_id=report_publication_id,
                benchmark=benchmark,
                database_summary=database_summary,
                preview_counts=preview_counts,
                rows=rows,
                lock_facts=lock.report_facts(),
                started_at=started_at,
                finished_at=finished_at,
                generated_at=_aware_utc(clock()),
                read_page_count=read_page_count,
                largest_read_page_rows=largest_read_page_rows,
                write_batch_count=write_batch_count,
                config=config,
                readiness_token=None,
            )
            json_object = store_tech_indicators_json_report(
                object_store=object_store,
                run_context=core_run.run_context,
                config=config,
                report=report,
            )
            json_report_object_id = json_object.object_id
            pdf_object = store_tech_indicators_pdf_report(
                object_store=object_store,
                run_context=core_run.run_context,
                config=config,
                report=report,
            )
            pdf_report_object_id = pdf_object.object_id
            summary = _core_summary(
                resolved=resolved,
                preview_counts=preview_counts,
                evaluated_rows=len(rows),
                plan_reason_counts=plan.reason_counts,
            )
            if scope.dry_run:
                core_run.succeed(
                    outcome=report.outcome,
                    summary=summary,
                    json_report_object_id=json_object.object_id,
                    pdf_report_object_id=pdf_object.object_id,
                )
                lock.rollback()
                durable_publication_id = None
            else:
                _prepare_candidate(
                    connection,
                    publication_id=publication_id,
                    database_summary=database_summary,
                    counts=preview_counts,
                    json_report_object_id=json_object.object_id,
                    pdf_report_object_id=pdf_object.object_id,
                )
                core_run.succeed(
                    outcome=report.outcome,
                    summary=summary,
                    json_report_object_id=json_object.object_id,
                    pdf_report_object_id=pdf_object.object_id,
                    publication_id=publication_id,
                )
                lock.commit_terminal(
                    lambda cursor: finalize_publication(
                        cursor=cursor,
                        publication_id=publication_id,
                        scope_hash=resolved.scope_hash,
                        calculation_version=config.calculation_version,
                        provider_listing_ids=tuple(
                            item.provider_listing_id for item in listings
                        ),
                        in_place_changes=changes,
                    )
                )
                publication_was_published = True
                durable_publication_id = publication_id
            return TechIndicatorsDailyRunResult(
                status="succeeded",
                effective_date=scope.effective_date,
                run_id=core_run.run_context.run_id,
                publication_id=durable_publication_id,
                json_report_object_id=json_object.object_id,
                pdf_report_object_id=pdf_object.object_id,
                outcome=report.outcome,
            )
    except BaseException as error:
        _rollback_quietly(connection)
        cancelled = is_workflow_cancellation(error)
        if not scope.dry_run and not publication_was_published:
            publication_was_published = terminalize_unpublished_candidate(
                publication_id=publication_id,
                lock=lock,
                lock_connection_factory=lock_connection_factory,
                abandoned=cancelled,
            )
        close_core_after_failure(
            core_run=core_run,
            summary=summary,
            publication_id=publication_id,
            json_report_object_id=json_report_object_id,
            pdf_report_object_id=pdf_report_object_id,
            publication_was_published=publication_was_published,
        )
        if cancelled:
            raise
        raise safe_workflow_error(error) from error


def _complete_zero_work(
    *,
    connection: Any,
    object_store: ObjectStore,
    config: TechIndicatorsConfig,
    resolved: ResolvedTechIndicatorsDailyScope,
    core_run: TechIndicatorsCoreRun,
    lock: Any,
    started_at: datetime,
    clock: Clock,
) -> TechIndicatorsDailyRunResult:
    """Prove existing readiness and complete a write-free daily workflow."""

    lock.heartbeat()
    core_run.heartbeat()
    snapshot = _read_noop_snapshot(
        connection,
        resolved=resolved,
        config=config,
    )
    if not snapshot.ready or snapshot.token is None:
        raise TechIndicatorsWorkflowError(
            "Zero-work scope does not have a compatible ready publication."
        )
    database_summary = _published_summary(
        connection,
        resolved=resolved,
    )
    finished_at = _aware_utc(clock())
    report = _build_report(
        resolved=resolved,
        core_run=core_run,
        publication_id=None,
        benchmark=None,
        database_summary=database_summary,
        preview_counts=SlotWriteCounts(),
        rows=(),
        lock_facts=lock.report_facts(),
        started_at=started_at,
        finished_at=finished_at,
        generated_at=_aware_utc(clock()),
        read_page_count=0,
        largest_read_page_rows=0,
        write_batch_count=0,
        config=config,
        readiness_token=snapshot.token,
    )
    json_object = store_tech_indicators_json_report(
        object_store=object_store,
        run_context=core_run.run_context,
        config=config,
        report=report,
    )
    pdf_object = store_tech_indicators_pdf_report(
        object_store=object_store,
        run_context=core_run.run_context,
        config=config,
        report=report,
    )
    revalidated = _read_noop_snapshot(
        connection,
        resolved=resolved,
        config=config,
    )
    if (
        not revalidated.ready
        or revalidated.token is None
        or revalidated.token.value != snapshot.token.value
    ):
        raise TechIndicatorsWorkflowError(
            "Existing publication readiness changed while storing reports."
        )
    summary = TechIndicatorsSummary(
        counts=FeatureCounts(selected_listings=len(resolved.listings))
    )
    core_run.succeed(
        outcome=report.outcome,
        summary=summary,
        json_report_object_id=json_object.object_id,
        pdf_report_object_id=pdf_object.object_id,
    )
    if resolved.request.dry_run:
        lock.rollback()
    else:
        lock.commit()
    return TechIndicatorsDailyRunResult(
        status="succeeded",
        effective_date=resolved.request.effective_date,
        run_id=core_run.run_context.run_id,
        publication_id=None,
        json_report_object_id=json_object.object_id,
        pdf_report_object_id=pdf_object.object_id,
        outcome=report.outcome,
    )


def _resolve(
    connection: Any,
    *,
    scope: TechIndicatorsDailyScope,
    config: TechIndicatorsConfig,
) -> ResolvedTechIndicatorsDailyScope:
    try:
        with connection.cursor() as cursor:
            return resolve_tech_indicators_daily_scope(
                cursor=cursor,
                scope=scope,
                benchmark_config=config.benchmark,
            )
    finally:
        connection.rollback()


def _resolved_scope(resolved: ResolvedTechIndicatorsDailyScope) -> TechIndicatorsScope:
    return TechIndicatorsScope(
        provider_listing_ids=tuple(
            item.provider_listing_id for item in resolved.listings
        )
    )


def _read_noop_snapshot(
    connection: Any,
    *,
    resolved: ResolvedTechIndicatorsDailyScope,
    config: TechIndicatorsConfig,
) -> PublishedModelInputSnapshot:
    """Read the bounded ready token and one allowlisted field per model row."""

    return read_published_model_inputs(
        connection=connection,
        scope=resolved.request.selection_scope,
        effective_date=resolved.request.effective_date,
        calculation_version=config.calculation_version,
        benchmark_config=config.benchmark,
        feature_names=("close",),
        max_rows=HARD_MAX_TRANSACTION_ROWS,
    )


def _published_summary(
    connection: Any,
    *,
    resolved: ResolvedTechIndicatorsDailyScope,
) -> ReportDatabaseSummary:
    try:
        with connection.cursor() as cursor:
            return select_report_database_summary(
                cursor=cursor,
                scope=_resolved_scope(resolved),
                effective_date=resolved.request.effective_date,
            )
    finally:
        connection.rollback()


def _plan(
    connection: Any,
    *,
    resolved: ResolvedTechIndicatorsDailyScope,
    config: TechIndicatorsConfig,
) -> tuple[object, tuple[EligibleListing, ...], tuple[ListingStateComparison, ...]]:
    with connection.cursor() as cursor:
        full_scope = _resolved_scope(resolved)
        listings = select_eligible_listings(cursor=cursor, scope=full_scope)
        comparisons = tuple(
            item
            for page in iter_state_comparison_pages(
                cursor=cursor,
                scope=full_scope,
                calculation_version=config.calculation_version,
                page_size=config.source_read_page_size,
            )
            for item in page
        )
        benchmark_drift = None
        benchmark_id = resolved.readiness.benchmark_provider_listing_id
        if benchmark_id is not None:
            benchmark_scope = TechIndicatorsScope(
                provider_listing_ids=(benchmark_id,)
            )
            benchmark_comparisons = tuple(
                item
                for page in iter_state_comparison_pages(
                    cursor=cursor,
                    scope=benchmark_scope,
                    calculation_version=config.calculation_version,
                    page_size=config.source_read_page_size,
                )
                for item in page
            )
            if benchmark_comparisons:
                benchmark_drift = benchmark_comparisons[0].earliest_recalculation_date
        plan = plan_affected_ranges(
            listings=listings,
            comparisons=comparisons,
            requested_end_date=resolved.request.effective_date,
            benchmark_drift_start_date=benchmark_drift,
            explicit_rebuild_listing_ids=resolved.explicit_rebuild_listing_ids,
        )
    connection.rollback()
    return plan, listings, comparisons


def _benchmark_history(
    connection: Any,
    *,
    resolved: ResolvedTechIndicatorsDailyScope,
    listings: tuple[EligibleListing, ...],
    config: TechIndicatorsConfig,
) -> BenchmarkHistory | None:
    if not any(is_spx_supported_subject(item) for item in listings):
        return None
    with connection.cursor() as cursor:
        history = load_spx_benchmark_history(
            cursor=cursor,
            config=config.benchmark,
            page_size=config.source_read_page_size,
        )
    connection.rollback()
    return history


def _calculate(
    connection: Any,
    *,
    plan: Any,
    listings: tuple[EligibleListing, ...],
    benchmark: BenchmarkHistory | None,
    run_id: UUID,
    config: TechIndicatorsConfig,
    calculated_at: datetime,
) -> tuple[tuple[FeatureRow, ...], int, int]:
    by_id = {item.provider_listing_id: item for item in listings}
    output: list[FeatureRow] = []
    page_count = 0
    largest_page = 0
    with connection.cursor() as cursor:
        for affected in plan.ranges:
            source_scope = TechIndicatorsScope(
                provider_listing_ids=(affected.provider_listing_id,),
                start_date=affected.calculation_start_date,
                end_date=affected.write_end_date,
            )
            pages = tuple(
                iter_source_bar_pages(
                    cursor=cursor,
                    scope=source_scope,
                    page_size=config.source_read_page_size,
                )
            )
            page_count += len(pages)
            largest_page = max(largest_page, *(len(page) for page in pages))
            bars = tuple(bar for page in pages for bar in page)
            arrays = normalize_source_bars(bars)
            scoped_subjects = select_eligible_listings(
                cursor=cursor,
                scope=source_scope,
            )
            if len(scoped_subjects) != 1:
                raise TechIndicatorsWorkflowError(
                    "Calculated listing source coverage changed during the run."
                )
            subject = scoped_subjects[0]
            if subject.provider_listing_id not in by_id:
                raise TechIndicatorsWorkflowError(
                    "Calculated listing left the resolved daily scope."
                )
            rows = assemble_feature_rows(
                arrays,
                subject=subject,
                calculated_at=calculated_at,
                calculation_version=config.calculation_version,
                benchmark_history=(
                    benchmark if is_spx_supported_subject(subject) else None
                ),
                run_id=run_id,
            )
            validate_feature_rows(
                rows,
                calculation_arrays=arrays,
                subject=subject,
                benchmark_history=(
                    benchmark if is_spx_supported_subject(subject) else None
                ),
            )
            output.extend(
                row
                for row in rows
                if affected.write_start_date
                <= row.source.trading_date
                <= affected.write_end_date
            )
    connection.rollback()
    return tuple(output), page_count, largest_page


def _candidate_image(
    connection: Any,
    *,
    rows: tuple[FeatureRow, ...],
    listings: tuple[EligibleListing, ...],
    comparisons: tuple[ListingStateComparison, ...],
    benchmark: BenchmarkHistory | None,
) -> tuple[tuple[InPlaceSlotChanges, ...], tuple[DailyCandidateListing, ...]]:
    identifiers = tuple(item.provider_listing_id for item in listings)
    with connection.cursor() as cursor:
        slots = select_daily_target_slots(
            cursor=cursor,
            provider_listing_ids=identifiers,
        )
    connection.rollback()
    by_slot: dict[TechIndicatorsPayloadSlot, list[FeatureRow]] = defaultdict(list)
    for row in rows:
        by_slot[slots[row.source.provider_listing_id]].append(row)
    changes = tuple(
        InPlaceSlotChanges(slot=slot, rows=tuple(slot_rows))
        for slot, slot_rows in sorted(by_slot.items(), key=lambda item: item[0].value)
    )
    supported = {
        item.provider_listing_id
        for item in listings
        if is_spx_supported_subject(item)
    }
    comparison_by_id = {item.provider_listing_id: item for item in comparisons}
    memberships = tuple(
        DailyCandidateListing(
            provider_listing_id=item.provider_listing_id,
            target_slot=slots[item.provider_listing_id],
            source_coverage_start_date=(
                comparison_by_id[item.provider_listing_id].first_source_date
            ),
            source_coverage_end_date=(
                comparison_by_id[item.provider_listing_id].last_source_date
            ),
            source_row_count=(
                comparison_by_id[item.provider_listing_id].source_observation_count
            ),
            benchmark_provider_listing_id=(
                benchmark.benchmark.provider_listing_id
                if benchmark is not None and item.provider_listing_id in supported
                else None
            ),
        )
        for item in listings
    )
    return changes, memberships


def _create_candidate(
    connection: Any,
    *,
    resolved: ResolvedTechIndicatorsDailyScope,
    core_run: TechIndicatorsCoreRun,
    memberships: tuple[DailyCandidateListing, ...],
    benchmark: BenchmarkHistory | None,
    publication_kind: str,
    dry_run: bool,
) -> UUID:
    with connection.cursor() as cursor:
        publication_id = create_daily_candidate(
            cursor=cursor,
            publication_kind=publication_kind,
            effective_date=resolved.request.effective_date,
            run_id=core_run.run_context.run_id,
            scope_hash=resolved.scope_hash,
            memberships=memberships,
            benchmark_provider_listing_id=(
                None if benchmark is None else benchmark.benchmark.provider_listing_id
            ),
            benchmark_coverage_start_date=(
                None if benchmark is None else benchmark.first_trading_date
            ),
            benchmark_coverage_end_date=(
                None if benchmark is None else benchmark.last_trading_date
            ),
            benchmark_source_row_count=(
                None if benchmark is None else len(benchmark.bars)
            ),
        )
    if dry_run:
        return publication_id
    connection.commit()
    return publication_id


def _preview(
    connection: Any,
    *,
    publication_id: UUID,
    scope: TechIndicatorsScope,
    effective_date: date,
    changes: tuple[InPlaceSlotChanges, ...],
    config: TechIndicatorsConfig,
) -> tuple[SlotWriteCounts, ReportDatabaseSummary, int]:
    totals = SlotWriteCounts()
    batch_count = 0
    try:
        with connection.cursor() as cursor:
            for change in changes:
                observed = upsert_feature_rows(
                    cursor=cursor,
                    slot=change.slot,
                    rows=change.rows,
                    batch_size=config.write_batch_size,
                )
                totals = _add_write_counts(totals, observed)
                batch_count += math.ceil(len(change.rows) / config.write_batch_size)
            summary = select_report_database_summary(
                cursor=cursor,
                scope=scope,
                effective_date=effective_date,
                publication_id=publication_id,
            )
        return totals, summary, batch_count
    finally:
        connection.rollback()


def _prepare_candidate(
    connection: Any,
    *,
    publication_id: UUID,
    database_summary: ReportDatabaseSummary,
    counts: SlotWriteCounts,
    json_report_object_id: UUID,
    pdf_report_object_id: UUID,
) -> None:
    with connection.cursor() as cursor:
        prepare_daily_candidate(
            cursor=cursor,
            publication_id=publication_id,
            expected_listing_count=database_summary.selected_listing_count,
            expected_source_row_count=database_summary.source_row_count,
            expected_payload_row_count=database_summary.payload_row_count,
            inserted_row_count=counts.inserted_rows,
            updated_row_count=counts.updated_rows,
            deleted_row_count=0,
            equivalent_row_count=counts.unchanged_rows,
            warning_count=0,
            failure_count=0,
            json_report_object_id=json_report_object_id,
            pdf_report_object_id=pdf_report_object_id,
        )
    connection.commit()


def _build_report(
    *,
    resolved: ResolvedTechIndicatorsDailyScope,
    core_run: TechIndicatorsCoreRun,
    publication_id: UUID | None,
    benchmark: BenchmarkHistory | None,
    database_summary: ReportDatabaseSummary,
    preview_counts: SlotWriteCounts,
    rows: tuple[FeatureRow, ...],
    lock_facts: ReportLock,
    started_at: datetime,
    finished_at: datetime,
    generated_at: datetime,
    read_page_count: int,
    largest_read_page_rows: int,
    write_batch_count: int,
    config: TechIndicatorsConfig,
    readiness_token: PublishedReadinessToken | None,
) -> TechIndicatorsReport:
    evaluated = _evaluated_dimensions(rows, resolved.listings, database_summary)
    counts = ReportCounts.from_database_summary(
        database_summary,
        eligible_listing_count=database_summary.selected_listing_count,
        evaluated_row_count=len(rows),
        evaluated_provider_rows=evaluated[0],
        evaluated_market_rows=evaluated[1],
        evaluated_instrument_type_rows=evaluated[2],
    )
    dry_run = resolved.request.dry_run
    healthy_noop = readiness_token is not None and not dry_run
    report_writes = ReportWrites(
        inserted=preview_counts.inserted_rows,
        updated=preview_counts.updated_rows,
        equivalent=preview_counts.unchanged_rows,
        batch_count=write_batch_count,
        committed_batch_count=0 if dry_run else write_batch_count,
        rolled_back_batch_count=write_batch_count if dry_run else 0,
    )
    elapsed = (finished_at - started_at).total_seconds()
    throughput_elapsed = elapsed
    persisted = report_writes.persisted_rows
    readiness = resolved.readiness
    benchmark_provider_listing_id = (
        readiness_token.benchmark_provider_listing_id
        if readiness_token is not None
        else None if benchmark is None else benchmark.benchmark.provider_listing_id
    )
    if database_summary.benchmark.supported_listing_count == 0:
        benchmark_provider_listing_id = None
    return TechIndicatorsReport(
        report_id=DAILY_REPORT_ID,
        workflow_kind=WorkflowKind.DAILY,
        outcome=ReportOutcome.NO_OP if healthy_noop else ReportOutcome.PASS,
        generated_at=max(generated_at, finished_at),
        identity=ReportIdentity(
            run_id=core_run.run_context.run_id,
            core_subject_key=resolved.subject_key,
            effective_date=resolved.request.effective_date,
            publication_id=publication_id,
            existing_readiness_token=(
                readiness_token.value if healthy_noop else None
            ),
            core_job_name=DAILY_CORE_JOB_NAME,
        ),
        scope=resolved.to_report_scope(),
        versions=ReportVersions(
            package_version=_package_version(),
            python_version=platform.python_version(),
            postgresql_version=None,
        ),
        lock=lock_facts,
        source_readiness=_report_source_readiness(resolved, database_summary),
        publication=ReportPublication(
            method=(
                PublicationMethod.NONE
                if dry_run or healthy_noop
                else PublicationMethod.IN_PLACE
            ),
            report_phase=(
                PublicationReportPhase.DRY_RUN
                if dry_run
                else PublicationReportPhase.EXISTING_PUBLICATION
                if healthy_noop
                else PublicationReportPhase.PREPARED_CANDIDATE
            ),
            candidate_status=None if dry_run or healthy_noop else "PREPARED",
            readiness_at_report=(
                PublicationReadiness.READY
                if healthy_noop
                else PublicationReadiness.NOT_READY
            ),
            readiness_reason_counts=(
                ()
                if healthy_noop
                else (ReportReasonCount("PUBLICATION_NOT_READY", 1),)
            ),
            publication_listing_count=counts.selected_listing_count,
            publication_source_row_count=counts.source_row_count,
            publication_payload_row_count=counts.payload_row_count,
            benchmark_provider_listing_id=benchmark_provider_listing_id,
            benchmark_contract_version=(
                None
                if benchmark_provider_listing_id is None
                else "TECH_INDICATORS_SPX_V1"
            ),
            resume_cursor=None,
        ),
        counts=counts,
        writes=report_writes,
        coverage=ReportCoverage.from_database_summary(database_summary),
        backfill=ReportBackfill(False, None, None, 0, None, None, 0, 0),
        performance=ReportPerformance(
            started_at=started_at,
            finished_at=finished_at,
            elapsed_seconds=elapsed,
            peak_rss_bytes=None,
            phases=(),
            throughput=ReportThroughput(
                evaluated_rows=len(rows),
                persisted_rows=persisted,
                elapsed_seconds=throughput_elapsed,
                evaluated_rows_per_second=(
                    None if throughput_elapsed == 0 else len(rows) / throughput_elapsed
                ),
                persisted_rows_per_second=(
                    None if throughput_elapsed == 0 else persisted / throughput_elapsed
                ),
            ),
            database=ReportDatabasePerformance(
                read_page_count=read_page_count,
                write_batch_count=write_batch_count,
                largest_read_page_rows=largest_read_page_rows,
                largest_write_batch_rows=min(
                    config.write_batch_size,
                    len(rows),
                ),
                longest_write_transaction_seconds=None,
            ),
        ),
        warnings=(),
        failures=(),
        diagnostic_samples=(),
        native_value_semantics=ReportNativeValueSemantics.for_providers(
            tuple(item.code for item in counts.providers),
            analytical_rows_present=counts.payload_row_count > 0,
        ),
    )


def _report_source_readiness(
    resolved: ResolvedTechIndicatorsDailyScope,
    summary: ReportDatabaseSummary,
) -> ReportSourceReadiness:
    decision = resolved.readiness
    dimensions = {item.code: item for item in summary.providers}
    provider_counts = {
        "EODDATA": decision.eoddata_listing_count,
        "STOOQ": decision.stooq_listing_count,
        "YAHOO": decision.yahoo_listing_count,
    }
    run_ids = {
        "EODDATA": decision.eoddata_source_run_id,
        "STOOQ": None,
        "YAHOO": decision.yahoo_source_run_id,
    }
    required = {
        "EODDATA": decision.eoddata_evidence_required,
        "STOOQ": False,
        "YAHOO": decision.yahoo_evidence_required,
    }
    evidence = tuple(
        ReportProviderEvidence(
            provider_code=code,
            evidence_kind=(
                "COVERAGE_ONLY" if code == "STOOQ" else "CORE_AND_COVERAGE"
            ),
            required=required[code],
            ready=(not required[code] or run_ids[code] is not None),
            successful_run_count=int(run_ids[code] is not None),
            latest_successful_run_id=run_ids[code],
            source_listing_count=provider_counts[code],
            source_row_count=(
                0 if code not in dimensions else dimensions[code].source_row_count
            ),
            effective_date_row_count=sum(
                1
                for item in resolved.listings
                if item.provider_code == code and item.source_observation_count > 0
            ),
        )
        for code in sorted(code for code, count in provider_counts.items() if count)
    )
    return ReportSourceReadiness(
        decision=SourceReadinessStatus.READY,
        effective_date=decision.effective_date,
        reason_counts=(),
        provider_evidence=evidence,
        benchmark=ReportSourceBenchmark(
            required=decision.benchmark_identity_required,
            ready=(
                decision.benchmark_provider_listing_id is not None
                and (not decision.spx_bar_required or decision.benchmark_bar_present)
            ),
            provider_listing_id=decision.benchmark_provider_listing_id,
            effective_date_bar_present=decision.benchmark_bar_present,
        ),
    )


def _evaluated_dimensions(
    rows: tuple[FeatureRow, ...],
    listings: tuple[EligibleListing, ...],
    summary: ReportDatabaseSummary,
) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    by_id = {item.provider_listing_id: item for item in listings}
    providers = Counter(
        by_id[row.source.provider_listing_id].provider_code for row in rows
    )
    markets = Counter(by_id[row.source.provider_listing_id].market for row in rows)
    instruments = Counter(
        by_id[row.source.provider_listing_id].instrument_type_code for row in rows
    )
    return (
        {item.code: providers[item.code] for item in summary.providers},
        {item.code: markets[item.code] for item in summary.markets},
        {item.code: instruments[item.code] for item in summary.instrument_types},
    )


def _core_summary(
    *,
    resolved: ResolvedTechIndicatorsDailyScope,
    preview_counts: SlotWriteCounts,
    evaluated_rows: int,
    plan_reason_counts: tuple[ReasonCount, ...],
) -> TechIndicatorsSummary:
    return TechIndicatorsSummary(
        counts=FeatureCounts(
            selected_listings=len(resolved.listings),
            evaluated_rows=evaluated_rows,
            inserted_rows=preview_counts.inserted_rows,
            updated_rows=preview_counts.updated_rows,
            unchanged_rows=preview_counts.unchanged_rows,
        ),
        reason_counts=plan_reason_counts,
    )


def _publication_kind(ranges: tuple[Any, ...]) -> str:
    correction_reasons = {
        AffectedRangeReason.MISSING_TECH_ROW,
        AffectedRangeReason.SOURCE_COPY_DRIFT,
        AffectedRangeReason.HISTORY_COUNT_DRIFT,
        AffectedRangeReason.BENCHMARK_DRIFT,
        AffectedRangeReason.EXPLICIT_REBUILD,
    }
    return (
        "CORRECTION"
        if any(correction_reasons.intersection(item.reasons) for item in ranges)
        else "DAILY"
    )


def _add_write_counts(left: SlotWriteCounts, right: SlotWriteCounts) -> SlotWriteCounts:
    return SlotWriteCounts(
        inserted_rows=left.inserted_rows + right.inserted_rows,
        updated_rows=left.updated_rows + right.updated_rows,
        unchanged_rows=left.unchanged_rows + right.unchanged_rows,
    )


def _package_version() -> str:
    try:
        return version("empire-stonks-tech-indicators")
    except PackageNotFoundError:
        return "0.1.0"


def _aware_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("clock must return a timezone-aware datetime.")
    return value.astimezone(UTC)


def _rollback_quietly(connection: Any) -> None:
    try:
        connection.rollback()
    except Exception:
        pass


def _validate_inputs(
    *,
    run_service: RunService,
    connection: Any,
    lock_connection_factory: Callable[[], Any],
    object_store: ObjectStore,
    config: TechIndicatorsConfig,
    scope: TechIndicatorsDailyScope,
    clock: Clock,
) -> None:
    if not isinstance(run_service, RunService):
        raise TypeError("run_service must be a RunService.")
    if not hasattr(connection, "cursor") or not callable(connection.cursor):
        raise TypeError("connection must provide cursor().")
    if not callable(lock_connection_factory):
        raise TypeError("lock_connection_factory must be callable.")
    if not isinstance(object_store, ObjectStore):
        raise TypeError("object_store must be an ObjectStore.")
    if not isinstance(config, TechIndicatorsConfig):
        raise TypeError("config must be a TechIndicatorsConfig.")
    if not isinstance(scope, TechIndicatorsDailyScope):
        raise TypeError("scope must be a TechIndicatorsDailyScope.")
    if config.calculation_version != scope.calculation_version:
        raise ValueError("scope and configuration calculation versions differ.")
    if not callable(clock):
        raise TypeError("clock must be callable.")


__all__ = ["TechIndicatorsDailyRunResult", "run_tech_indicators_daily"]
