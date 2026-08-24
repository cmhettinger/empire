"""Package-owned resumable staged backfill workflow."""

from __future__ import annotations

import math
import platform
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from importlib.metadata import PackageNotFoundError, version
from typing import Any
from uuid import UUID

from empire_core import ObjectStore, RunService

from empire_stonks_tech_indicators.arrays import normalize_source_bars
from empire_stonks_tech_indicators.assembly import assemble_feature_rows
from empire_stonks_tech_indicators.backfill_publication import (
    BackfillPublicationProgress,
    complete_backfill_listing,
    create_or_resume_backfill_candidate,
    delete_stale_backfill_rows,
    prepare_backfill_candidate,
    record_backfill_batch,
)
from empire_stonks_tech_indicators.backfill_scope import (
    ResolvedTechIndicatorsBackfillScope,
    TechIndicatorsBackfillCursor,
    TechIndicatorsBackfillScope,
    resolve_tech_indicators_backfill_scope,
)
from empire_stonks_tech_indicators.config import (
    HARD_MAX_TRANSACTION_ROWS,
    TechIndicatorsConfig,
)
from empire_stonks_tech_indicators.core_lifecycle import TechIndicatorsCoreRun
from empire_stonks_tech_indicators.exceptions import TechIndicatorsWorkflowError
from empire_stonks_tech_indicators.models import (
    FeatureCounts,
    TechIndicatorsScope,
    TechIndicatorsSummary,
)
from empire_stonks_tech_indicators.persistence import (
    FeatureRowKey,
    copy_feature_rows_between_slots,
    upsert_feature_rows,
)
from empire_stonks_tech_indicators.publication import (
    PublicationSlotSelection,
    finalize_publication,
    select_inactive_payload_slots,
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
from empire_stonks_tech_indicators.report_storage import (
    store_tech_indicators_json_report,
    store_tech_indicators_pdf_report,
)
from empire_stonks_tech_indicators.reports import (
    BACKFILL_CORE_JOB_NAME,
    BACKFILL_REPORT_ID,
    BENCHMARK_CONTRACT_VERSION,
    PublicationMethod,
    PublicationReadiness,
    PublicationReportPhase,
    ReportBackfill,
    ReportCounts,
    ReportCoverage,
    ReportDatabasePerformance,
    ReportIdentity,
    ReportIssueAggregate,
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
class TechIndicatorsBackfillRunResult:
    status: str
    effective_date: date
    run_id: UUID | None = None
    publication_id: UUID | None = None
    json_report_object_id: UUID | None = None
    pdf_report_object_id: UUID | None = None
    outcome: ReportOutcome | None = None
    resume_cursor: TechIndicatorsBackfillCursor | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"succeeded", "partial", "contended"}:
            raise ValueError("invalid backfill result status.")
        if self.status == "contended" and self.message != (
            TECH_INDICATORS_LOCK_CONTENDED_MESSAGE
        ):
            raise ValueError("contended result requires the stable lock message.")
        if self.status == "contended" and any(
            value is not None
            for value in (
                self.run_id,
                self.publication_id,
                self.json_report_object_id,
                self.pdf_report_object_id,
                self.outcome,
                self.resume_cursor,
            )
        ):
            raise ValueError("contended result cannot contain workflow state.")
        if self.status in {"succeeded", "partial"} and (
            not isinstance(self.run_id, UUID)
            or not isinstance(self.json_report_object_id, UUID)
            or not isinstance(self.pdf_report_object_id, UUID)
            or self.message is not None
        ):
            raise ValueError("completed backfill result is incomplete.")
        if self.status == "partial" and (
            not isinstance(self.publication_id, UUID)
            or self.outcome is not ReportOutcome.PARTIAL
            or not isinstance(self.resume_cursor, TechIndicatorsBackfillCursor)
        ):
            raise ValueError("partial backfill result is incomplete.")
        if self.status == "succeeded" and (
            self.outcome is not ReportOutcome.PASS
            or self.resume_cursor is not None
        ):
            raise ValueError("successful backfill result is inconsistent.")

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
            "resume_cursor": (
                None
                if self.resume_cursor is None
                else self.resume_cursor.to_dict()
            ),
            "message": self.message,
        }


def run_tech_indicators_backfill(
    *,
    run_service: RunService,
    connection: Any,
    lock_connection_factory: Callable[[], Any],
    object_store: ObjectStore,
    config: TechIndicatorsConfig,
    scope: TechIndicatorsBackfillScope,
    run_type: str,
    runner: str,
    batch_limit: int | None = None,
    clock: Clock = _utc_now,
) -> TechIndicatorsBackfillRunResult:
    """Stage complete listing images in committed batches and publish once."""

    if batch_limit is not None and (type(batch_limit) is not int or batch_limit < 1):
        raise ValueError("batch_limit must be a positive integer or None.")
    if scope.dry_run and (scope.resume_cursor is not None or batch_limit is not None):
        raise ValueError("dry-run cannot resume or stop with partial progress.")
    acquired = acquire_tech_indicators_writer_lock(
        connection_factory=lock_connection_factory
    )
    if acquired.outcome is WriterLockOutcome.CONTENDED:
        return TechIndicatorsBackfillRunResult(
            "contended", scope.effective_date, message=acquired.message
        )
    lock = acquired.lock
    assert lock is not None
    core_run: TechIndicatorsCoreRun | None = None
    progress: BackfillPublicationProgress | None = None
    summary = TechIndicatorsSummary()
    try:
        with lock:
            resolved = _resolve(connection, scope)
            core_run = TechIndicatorsCoreRun.start(
                run_service=run_service,
                workflow_kind=WorkflowKind.BACKFILL,
                effective_date=scope.effective_date,
                run_type=run_type,
                runner=runner,
                subject_key=resolved.subject_key,
                calculation_version=config.calculation_version,
            )
            started_at = _aware(clock())
            listings = _full_listings(connection, resolved)
            benchmark = _benchmark(connection, listings, config)
            if (
                benchmark is not None
                and benchmark.bar_on(scope.effective_date) is None
            ):
                raise TechIndicatorsWorkflowError(
                    "The SPX benchmark lacks the backfill effective-date bar."
                )
            slots = _slots(connection, listings)
            planned_batch_count = _planned_batches(
                connection=connection,
                listings=listings,
                slots=slots,
                resolved=resolved,
            )
            with connection.cursor() as cursor:
                progress = create_or_resume_backfill_candidate(
                    cursor=cursor,
                    resolved=resolved,
                    run_id=core_run.run_context.run_id,
                    benchmark=benchmark,
                )
            if not scope.dry_run:
                connection.commit()
            _validate_resume_prefix(
                connection=connection,
                listings=listings,
                slots=slots,
                progress=progress,
                calculation_version=config.calculation_version,
            )
            evaluated = {
                item.provider_listing_id: 0 for item in listings
            }
            committed_this_run = 0
            read_pages = 0
            largest_read = 0
            for listing in listings:
                rows, pages, largest = _calculate_listing(
                    connection=connection,
                    listing=listing,
                    benchmark=benchmark,
                    run_id=core_run.run_context.run_id,
                    config=config,
                    calculated_at=_aware(clock()),
                    include_inactive=scope.include_inactive,
                )
                read_pages += pages
                largest_read = max(largest_read, largest)
                start = _resume_index(progress, listing, rows, listings)
                if not rows:
                    with connection.cursor() as cursor:
                        complete_backfill_listing(
                            cursor=cursor,
                            publication_id=progress.publication_id,
                            listing=listing,
                            target_slot=(
                                slots[listing.provider_listing_id].target_slot
                            ),
                            calculation_version=config.calculation_version,
                            benchmark_provider_listing_id=None,
                        )
                    if not scope.dry_run:
                        connection.commit()
                    continue
                if start == len(rows):
                    evaluated[listing.provider_listing_id] = sum(
                        _requires_calculation(
                            row.source.trading_date,
                            selection=slots[listing.provider_listing_id],
                            resolved=resolved,
                        )
                        for row in rows
                    )
                    continue
                with connection.cursor() as cursor:
                    progress = delete_stale_backfill_rows(
                        cursor=cursor,
                        progress=progress,
                        provider_listing_id=listing.provider_listing_id,
                        target_slot=(
                            slots[listing.provider_listing_id].target_slot
                        ),
                        maximum_rows=HARD_MAX_TRANSACTION_ROWS,
                    )
                if not scope.dry_run:
                    connection.commit()
                evaluated[listing.provider_listing_id] = sum(
                    _requires_calculation(
                        row.source.trading_date,
                        selection=slots[listing.provider_listing_id],
                        resolved=resolved,
                    )
                    for row in rows[:start]
                )
                offset = start
                while offset < len(rows):
                    selection = slots[listing.provider_listing_id]
                    calculate = _requires_calculation(
                        rows[offset].source.trading_date,
                        selection=selection,
                        resolved=resolved,
                    )
                    segment_end = offset + 1
                    while segment_end < len(rows) and (
                        _requires_calculation(
                            rows[segment_end].source.trading_date,
                            selection=selection,
                            resolved=resolved,
                        )
                        == calculate
                    ):
                        segment_end += 1
                    batch_end = min(
                        offset + scope.batch_size,
                        segment_end,
                    )
                    batch = rows[offset:batch_end]
                    with connection.cursor() as cursor:
                        if calculate:
                            writes = upsert_feature_rows(
                                cursor=cursor,
                                slot=selection.target_slot,
                                rows=batch,
                                batch_size=scope.batch_size,
                            )
                        else:
                            assert selection.active_slot is not None
                            writes = copy_feature_rows_between_slots(
                                cursor=cursor,
                                source_slot=selection.active_slot,
                                target_slot=selection.target_slot,
                                keys=tuple(
                                    FeatureRowKey(
                                        row.source.provider_listing_id,
                                        row.source.trading_date,
                                    )
                                    for row in batch
                                ),
                                batch_size=scope.batch_size,
                            )
                        progress = record_backfill_batch(
                            cursor=cursor,
                            progress=progress,
                            provider_listing_id=listing.provider_listing_id,
                            trading_date=batch[-1].source.trading_date,
                            row_count=len(batch),
                            writes=writes,
                        )
                        if batch_end == len(rows):
                            complete_backfill_listing(
                                cursor=cursor,
                                publication_id=progress.publication_id,
                                listing=listing,
                                target_slot=selection.target_slot,
                                calculation_version=config.calculation_version,
                                benchmark_provider_listing_id=(
                                    benchmark.benchmark.provider_listing_id
                                    if benchmark is not None
                                    and is_spx_supported_subject(listing)
                                    else None
                                ),
                            )
                    if calculate:
                        evaluated[listing.provider_listing_id] += len(batch)
                    offset = batch_end
                    committed_this_run += 1
                    if not scope.dry_run:
                        connection.commit()
                    lock.heartbeat()
                    core_run.heartbeat()
                    if batch_limit == committed_this_run:
                        return _finish(
                            connection=connection,
                            lock=lock,
                            object_store=object_store,
                            config=config,
                            resolved=resolved,
                            listings=listings,
                            benchmark=benchmark,
                            core_run=core_run,
                            progress=progress,
                            evaluated=evaluated,
                            started_at=started_at,
                            clock=clock,
                            read_pages=read_pages,
                            largest_read=largest_read,
                            complete=False,
                            planned_batch_count=planned_batch_count,
                        )
            return _finish(
                connection=connection,
                lock=lock,
                object_store=object_store,
                config=config,
                resolved=resolved,
                listings=listings,
                benchmark=benchmark,
                core_run=core_run,
                progress=progress,
                evaluated=evaluated,
                started_at=started_at,
                clock=clock,
                read_pages=read_pages,
                largest_read=largest_read,
                complete=True,
                planned_batch_count=planned_batch_count,
            )
    except BaseException:
        _rollback(connection)
        if core_run is not None and core_run.run_context.status == "started":
            try:
                core_run.fail(outcome=ReportOutcome.FAIL, summary=summary)
            except Exception:
                pass
        raise


def _finish(
    *, connection: Any, lock: Any, object_store: ObjectStore,
    config: TechIndicatorsConfig, resolved: ResolvedTechIndicatorsBackfillScope,
    listings: tuple[EligibleListing, ...], benchmark: BenchmarkHistory | None,
    core_run: TechIndicatorsCoreRun, progress: BackfillPublicationProgress,
    evaluated: dict[UUID, int], started_at: datetime, clock: Clock,
    read_pages: int, largest_read: int, complete: bool,
    planned_batch_count: int,
) -> TechIndicatorsBackfillRunResult:
    report_scope = TechIndicatorsScope(
        provider_listing_ids=tuple(item.provider_listing_id for item in listings),
        include_inactive=resolved.request.include_inactive,
    )
    with connection.cursor() as cursor:
        database = select_report_database_summary(
            cursor=cursor,
            scope=report_scope,
            publication_id=progress.publication_id,
        )
        cursor.execute(
            """
            SELECT count(*)
            FROM stonks.tech_indicators_publication_listing
            WHERE publication_id = %s
            """,
            (progress.publication_id,),
        )
        completed_listing_count = cursor.fetchone()[0]
    if not resolved.request.dry_run:
        connection.rollback()
    report = _build_report(
        resolved=resolved, listings=listings, benchmark=benchmark,
        core_run=core_run, progress=progress, database=database,
        evaluated=evaluated, started_at=started_at, finished_at=_aware(clock()),
        generated_at=_aware(clock()), lock_facts=lock.report_facts(),
        read_pages=read_pages, largest_read=largest_read, complete=complete,
        completed_listing_count=completed_listing_count,
        planned_batch_count=planned_batch_count,
    )
    json_object = store_tech_indicators_json_report(
        object_store=object_store, run_context=core_run.run_context,
        config=config, report=report,
    )
    pdf_object = store_tech_indicators_pdf_report(
        object_store=object_store, run_context=core_run.run_context,
        config=config, report=report,
    )
    core_summary = TechIndicatorsSummary(
        counts=FeatureCounts(
            selected_listings=len(listings),
            evaluated_rows=sum(evaluated.values()),
            inserted_rows=progress.inserted_row_count,
            updated_rows=progress.updated_row_count,
            unchanged_rows=(
                progress.equivalent_row_count
                - (progress.staged_payload_row_count - sum(evaluated.values()))
            ),
            deleted_rows=progress.deleted_row_count,
        )
    )
    if not complete:
        core_run.fail(
            outcome=ReportOutcome.PARTIAL, summary=core_summary,
            json_report_object_id=json_object.object_id,
            pdf_report_object_id=pdf_object.object_id,
            publication_id=progress.publication_id,
        )
        lock.commit()
        return TechIndicatorsBackfillRunResult(
            "partial", resolved.request.effective_date,
            core_run.run_context.run_id, progress.publication_id,
            json_object.object_id, pdf_object.object_id, ReportOutcome.PARTIAL,
            progress.cursor,
        )
    if resolved.request.dry_run:
        core_run.succeed(
            outcome=ReportOutcome.PASS, summary=core_summary,
            json_report_object_id=json_object.object_id,
            pdf_report_object_id=pdf_object.object_id,
        )
        connection.rollback()
        lock.rollback()
        publication_id = None
    else:
        with connection.cursor() as cursor:
            prepare_backfill_candidate(
                cursor=cursor, progress=progress,
                expected_listing_count=len(listings),
                expected_source_row_count=sum(
                    item.source_observation_count for item in listings
                ),
                json_report_object_id=json_object.object_id,
                pdf_report_object_id=pdf_object.object_id,
            )
        connection.commit()
        core_run.succeed(
            outcome=ReportOutcome.PASS, summary=core_summary,
            json_report_object_id=json_object.object_id,
            pdf_report_object_id=pdf_object.object_id,
            publication_id=progress.publication_id,
        )
        lock.commit_terminal(lambda cursor: finalize_publication(
            cursor=cursor, publication_id=progress.publication_id,
            scope_hash=resolved.scope_hash,
            calculation_version=config.calculation_version,
            provider_listing_ids=tuple(
                item.provider_listing_id for item in listings
            ),
        ))
        publication_id = progress.publication_id
    return TechIndicatorsBackfillRunResult(
        "succeeded", resolved.request.effective_date,
        core_run.run_context.run_id, publication_id,
        json_object.object_id, pdf_object.object_id, ReportOutcome.PASS,
    )


def _build_report(
    *, resolved: ResolvedTechIndicatorsBackfillScope,
    listings: tuple[EligibleListing, ...], benchmark: BenchmarkHistory | None,
    core_run: TechIndicatorsCoreRun, progress: BackfillPublicationProgress,
    database: ReportDatabaseSummary, evaluated: dict[UUID, int],
    started_at: datetime, finished_at: datetime, generated_at: datetime,
    lock_facts: Any, read_pages: int, largest_read: int, complete: bool,
    completed_listing_count: int,
    planned_batch_count: int,
) -> TechIndicatorsReport:
    by_id = {item.provider_listing_id: item for item in listings}
    provider_rows: Counter[str] = Counter()
    market_rows: Counter[str] = Counter()
    instrument_rows: Counter[str] = Counter()
    for key, count in evaluated.items():
        provider_rows[by_id[key].provider_code] += count
        market_rows[by_id[key].market] += count
        instrument_rows[by_id[key].instrument_type_code] += count
    counts = ReportCounts.from_database_summary(
        database, eligible_listing_count=len(listings),
        evaluated_row_count=sum(evaluated.values()),
        evaluated_provider_rows={
            item.code: provider_rows[item.code] for item in database.providers
        },
        evaluated_market_rows={
            item.code: market_rows[item.code] for item in database.markets
        },
        evaluated_instrument_type_rows={
            item.code: instrument_rows[item.code]
            for item in database.instrument_types
        },
    )
    remaining_rows = (
        sum(item.source_observation_count for item in listings)
        - progress.staged_payload_row_count
    )
    remaining_listings = len(listings) - completed_listing_count
    elapsed = (finished_at - started_at).total_seconds()
    copied_rows = progress.staged_payload_row_count - sum(evaluated.values())
    publication_id = None if resolved.request.dry_run else progress.publication_id
    supported = any(is_spx_supported_subject(item) for item in listings)
    evidence = tuple(ReportProviderEvidence(
        provider_code=item.code,
        evidence_kind="COVERAGE_ONLY" if item.code == "STOOQ" else "CORE_AND_COVERAGE",
        required=False, ready=True, successful_run_count=0,
        latest_successful_run_id=None, source_listing_count=item.listing_count,
        source_row_count=item.source_row_count, effective_date_row_count=0,
    ) for item in database.providers)
    return TechIndicatorsReport(
        report_id=BACKFILL_REPORT_ID, workflow_kind=WorkflowKind.BACKFILL,
        outcome=ReportOutcome.PASS if complete else ReportOutcome.PARTIAL,
        generated_at=max(generated_at, finished_at),
        identity=ReportIdentity(
            run_id=core_run.run_context.run_id, core_subject_key=resolved.subject_key,
            effective_date=resolved.request.effective_date,
            publication_id=publication_id, core_job_name=BACKFILL_CORE_JOB_NAME,
        ),
        scope=resolved.to_report_scope(), versions=ReportVersions(
            package_version=_package_version(),
            python_version=platform.python_version(),
            postgresql_version=None,
        ), lock=lock_facts,
        source_readiness=ReportSourceReadiness(
            SourceReadinessStatus.READY, None, (), evidence,
            ReportSourceBenchmark(
                required=supported, ready=supported,
                provider_listing_id=(
                    None
                    if benchmark is None
                    else benchmark.benchmark.provider_listing_id
                ),
                effective_date_bar_present=(
                    False
                    if benchmark is None
                    else benchmark.bar_on(resolved.request.effective_date) is not None
                ),
            ),
        ),
        publication=ReportPublication(
            method=(
                PublicationMethod.NONE
                if resolved.request.dry_run
                else PublicationMethod.STAGED
            ),
            report_phase=(
                PublicationReportPhase.DRY_RUN
                if resolved.request.dry_run
                else PublicationReportPhase.PREPARED_CANDIDATE
                if complete
                else PublicationReportPhase.UNPUBLISHED_PARTIAL
            ),
            candidate_status=(
                None
                if resolved.request.dry_run
                else "PREPARED" if complete else "BUILDING"
            ),
            readiness_at_report=PublicationReadiness.NOT_READY,
            readiness_reason_counts=(ReportReasonCount("PUBLICATION_NOT_READY", 1),),
            publication_listing_count=counts.selected_listing_count,
            publication_source_row_count=counts.source_row_count,
            publication_payload_row_count=counts.payload_row_count,
            benchmark_provider_listing_id=(
                None
                if benchmark is None
                else benchmark.benchmark.provider_listing_id
            ),
            benchmark_contract_version=(
                None if benchmark is None else BENCHMARK_CONTRACT_VERSION
            ),
            resume_cursor=None if complete else progress.cursor.to_report_cursor(),
        ),
        counts=counts,
        writes=ReportWrites(
            inserted=progress.inserted_row_count, updated=progress.updated_row_count,
            deleted=progress.deleted_row_count,
            equivalent=progress.equivalent_row_count - copied_rows,
            copied_equivalent=copied_rows,
            batch_count=progress.completed_batch_count,
            committed_batch_count=(
                0
                if resolved.request.dry_run
                else progress.completed_batch_count
            ),
            rolled_back_batch_count=(
                progress.completed_batch_count
                if resolved.request.dry_run
                else 0
            ),
        ), coverage=ReportCoverage.from_database_summary(database),
        backfill=ReportBackfill(
            True,
            resolved.request.batch_size,
            planned_batch_count or None,
            progress.completed_batch_count,
            None if progress.cursor is None else progress.cursor.to_report_cursor(),
            resolved.resumed_from_cursor, remaining_listings, remaining_rows,
        ),
        performance=ReportPerformance(
            started_at, finished_at, elapsed, None, (),
            ReportThroughput(
                sum(evaluated.values()),
                progress.inserted_row_count + progress.updated_row_count,
                elapsed,
                None
                if elapsed == 0
                else sum(evaluated.values()) / elapsed,
                None
                if elapsed == 0
                else (
                    progress.inserted_row_count + progress.updated_row_count
                )
                / elapsed,
            ),
            ReportDatabasePerformance(
                read_pages, progress.completed_batch_count, largest_read,
                min(
                    resolved.request.batch_size,
                    progress.staged_payload_row_count,
                ),
                None,
            ),
        ),
        warnings=(
            ()
            if complete
            else (ReportIssueAggregate("BACKFILL_INCOMPLETE", 1),)
        ),
        failures=(), diagnostic_samples=(),
        native_value_semantics=ReportNativeValueSemantics.for_providers(
            tuple(item.code for item in counts.providers),
            analytical_rows_present=counts.payload_row_count > 0,
        ),
    )


def _resolve(
    connection: Any,
    scope: TechIndicatorsBackfillScope,
) -> ResolvedTechIndicatorsBackfillScope:
    try:
        with connection.cursor() as cursor:
            return resolve_tech_indicators_backfill_scope(cursor=cursor, scope=scope)
    finally:
        connection.rollback()


def _full_listings(
    connection: Any,
    resolved: ResolvedTechIndicatorsBackfillScope,
) -> tuple[EligibleListing, ...]:
    scope = TechIndicatorsScope(
        provider_listing_ids=tuple(
            item.provider_listing_id for item in resolved.listings
        ),
        include_inactive=resolved.request.include_inactive,
    )
    with connection.cursor() as cursor:
        listings = select_eligible_listings(cursor=cursor, scope=scope)
    connection.rollback()
    if tuple(item.provider_listing_id for item in listings) != tuple(
        item.provider_listing_id for item in resolved.listings
    ):
        raise TechIndicatorsWorkflowError("Resolved backfill listing identity changed.")
    return listings


def _benchmark(
    connection: Any,
    listings: tuple[EligibleListing, ...],
    config: TechIndicatorsConfig,
) -> BenchmarkHistory | None:
    if not any(is_spx_supported_subject(item) for item in listings):
        return None
    with connection.cursor() as cursor:
        result = load_spx_benchmark_history(
            cursor=cursor,
            config=config.benchmark,
            page_size=config.source_read_page_size,
        )
    connection.rollback()
    return result


def _slots(
    connection: Any,
    listings: tuple[EligibleListing, ...],
) -> dict[UUID, PublicationSlotSelection]:
    with connection.cursor() as cursor:
        selected = select_inactive_payload_slots(
            cursor=cursor,
            provider_listing_ids=tuple(
                item.provider_listing_id for item in listings
            ),
        )
    connection.rollback()
    return {item.provider_listing_id: item for item in selected}


def _requires_calculation(
    trading_date: date,
    *,
    selection: PublicationSlotSelection,
    resolved: ResolvedTechIndicatorsBackfillScope,
) -> bool:
    return (
        selection.active_slot is None
        or resolved.request.rebuild
        or resolved.request.start_date
        <= trading_date
        <= resolved.request.end_date
    )


def _planned_batches(
    *,
    connection: Any,
    listings: tuple[EligibleListing, ...],
    slots: dict[UUID, PublicationSlotSelection],
    resolved: ResolvedTechIndicatorsBackfillScope,
) -> int:
    identifiers = [item.provider_listing_id for item in listings]
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT provider_listing_id,
                   count(*) FILTER (WHERE trading_date < %s),
                   count(*) FILTER (WHERE trading_date BETWEEN %s AND %s),
                   count(*) FILTER (WHERE trading_date > %s)
            FROM stonks.ohlcv_daily
            WHERE provider_listing_id = ANY(%s::uuid[])
            GROUP BY provider_listing_id
            """,
            (
                resolved.request.start_date,
                resolved.request.start_date,
                resolved.request.end_date,
                resolved.request.end_date,
                identifiers,
            ),
        )
        counts = {row[0]: row[1:] for row in cursor.fetchall()}
    connection.rollback()
    batches = 0
    for listing in listings:
        before, selected, after = counts.get(
            listing.provider_listing_id,
            (0, 0, 0),
        )
        selection = slots[listing.provider_listing_id]
        segments = (
            (before, selected, after)
            if selection.active_slot is not None and not resolved.request.rebuild
            else (before + selected + after,)
        )
        batches += sum(
            math.ceil(count / resolved.request.batch_size)
            for count in segments
        )
    return batches


def _calculate_listing(
    *,
    connection: Any,
    listing: EligibleListing,
    benchmark: BenchmarkHistory | None,
    run_id: UUID,
    config: TechIndicatorsConfig,
    calculated_at: datetime,
    include_inactive: bool,
) -> tuple[tuple[Any, ...], int, int]:
    scope = TechIndicatorsScope(
        provider_listing_ids=(listing.provider_listing_id,),
        include_inactive=include_inactive,
    )
    with connection.cursor() as cursor:
        pages = tuple(
            iter_source_bar_pages(
                cursor=cursor,
                scope=scope,
                page_size=config.source_read_page_size,
            )
        )
    connection.rollback()
    bars = tuple(bar for page in pages for bar in page)
    arrays = normalize_source_bars(bars)
    subject_benchmark = benchmark if is_spx_supported_subject(listing) else None
    rows = assemble_feature_rows(
        arrays,
        subject=listing,
        calculated_at=calculated_at,
        calculation_version=config.calculation_version,
        benchmark_history=subject_benchmark,
        run_id=run_id,
    )
    validate_feature_rows(
        rows,
        calculation_arrays=arrays,
        subject=listing,
        benchmark_history=subject_benchmark,
    )
    return rows, len(pages), max((len(page) for page in pages), default=0)


def _resume_index(
    progress: BackfillPublicationProgress,
    listing: EligibleListing,
    rows: tuple[Any, ...],
    listings: tuple[EligibleListing, ...],
) -> int:
    if progress.cursor is None:
        return 0
    order = {item.provider_listing_id: index for index, item in enumerate(listings)}
    current = order[listing.provider_listing_id]
    boundary = order[progress.cursor.provider_listing_id]
    if current < boundary:
        return len(rows)
    if current > boundary:
        return 0
    dates = tuple(row.source.trading_date for row in rows)
    try:
        return dates.index(progress.cursor.trading_date) + 1
    except ValueError as exc:
        raise TechIndicatorsWorkflowError("Durable resume source key changed.") from exc


def _validate_resume_prefix(
    *,
    connection: Any,
    listings: tuple[EligibleListing, ...],
    slots: dict[UUID, PublicationSlotSelection],
    progress: BackfillPublicationProgress,
    calculation_version: str,
) -> None:
    """Fail closed unless the durable cursor's staged prefix is still exact."""

    if progress.cursor is None:
        return
    order = {item.provider_listing_id: index for index, item in enumerate(listings)}
    boundary = order[progress.cursor.provider_listing_id]
    prior = listings[:boundary]
    expected_prior_rows = sum(item.source_observation_count for item in prior)
    expected_prefix = progress.staged_payload_row_count - expected_prior_rows
    if expected_prefix < 1:
        raise TechIndicatorsWorkflowError("Durable backfill row count is inconsistent.")
    with connection.cursor() as cursor:
        if prior:
            cursor.execute(
                """
                SELECT count(*)
                FROM stonks.tech_indicators_publication_listing
                WHERE publication_id = %s
                  AND provider_listing_id = ANY(%s::uuid[])
                """,
                (
                    progress.publication_id,
                    [item.provider_listing_id for item in prior],
                ),
            )
            if cursor.fetchone()[0] != len(prior):
                raise TechIndicatorsWorkflowError(
                    "Completed backfill memberships do not match the resume cursor."
                )
        table = slots[
            progress.cursor.provider_listing_id
        ].target_slot.table_name
        cursor.execute(
            f"""
            SELECT count(*), count(*) FILTER (
                WHERE payload.calculation_version = %s
                  AND payload.open IS NOT DISTINCT FROM source.open
                  AND payload.high IS NOT DISTINCT FROM source.high
                  AND payload.low IS NOT DISTINCT FROM source.low
                  AND payload.close IS NOT DISTINCT FROM source.close
                  AND payload.volume IS NOT DISTINCT FROM source.volume
            )
            FROM {table} AS payload
            INNER JOIN stonks.ohlcv_daily AS source
              USING (provider_listing_id, trading_date)
            WHERE payload.provider_listing_id = %s
              AND payload.trading_date <= %s
            """,
            (
                calculation_version,
                progress.cursor.provider_listing_id,
                progress.cursor.trading_date,
            ),
        )
        total, exact = cursor.fetchone()
    connection.rollback()
    if (total, exact) != (expected_prefix, expected_prefix):
        raise TechIndicatorsWorkflowError(
            "Durable staged prefix no longer matches current source state."
        )


def _aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime.")
    return value.astimezone(UTC)


def _rollback(connection: Any) -> None:
    try:
        connection.rollback()
    except Exception:
        pass


def _package_version() -> str:
    try:
        return version("empire-stonks-tech-indicators")
    except PackageNotFoundError:
        return "0.1.0"


__all__ = ["TechIndicatorsBackfillRunResult", "run_tech_indicators_backfill"]
