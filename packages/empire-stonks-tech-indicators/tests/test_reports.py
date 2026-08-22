from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest

from empire_stonks_tech_indicators.reporting_queries import (
    REPORT_FEATURE_FIELDS,
    ReportBenchmarkCoverage,
    ReportDatabaseSummary,
    ReportDateCoverage,
    ReportDimensionCoverage,
    ReportFeatureCoverage,
    ReportVersionCoverage,
)
from empire_stonks_tech_indicators.reports import (
    BACKFILL_CORE_JOB_NAME,
    BACKFILL_REPORT_ID,
    DAILY_CORE_JOB_NAME,
    DAILY_REPORT_ID,
    REPORT_DIAGNOSTIC_MESSAGE_CATALOG,
    REPORT_MAXIMUM_BYTES,
    REPORT_MESSAGE_CATALOG,
    LockOutcome,
    PublicationMethod,
    PublicationReadiness,
    PublicationReportPhase,
    ReportBackfill,
    ReportCounts,
    ReportCoverage,
    ReportCursor,
    ReportDatabasePerformance,
    ReportDiagnosticSample,
    ReportDimensionCount,
    ReportIdentity,
    ReportIssueAggregate,
    ReportLock,
    ReportNativeValueSemantics,
    ReportOutcome,
    ReportPerformance,
    ReportPhaseTiming,
    ReportProviderEvidence,
    ReportPublication,
    ReportReasonCount,
    ReportScope,
    ReportSourceBenchmark,
    ReportSourceReadiness,
    ReportThroughput,
    ReportVersions,
    ReportWrites,
    SourceReadinessStatus,
    TechIndicatorsReport,
    WorkflowKind,
    make_report_diagnostic_samples,
    render_tech_indicators_report_json,
)


RUN_ID = UUID("81111111-1111-4111-8111-111111111111")
PUBLICATION_ID = UUID("82222222-2222-4222-8222-222222222222")
LISTING_ID = UUID("83333333-3333-4333-8333-333333333333")
BENCHMARK_ID = UUID("84444444-4444-4444-8444-444444444444")
SOURCE_RUN_ID = UUID("85555555-5555-4555-8555-555555555555")
EFFECTIVE_DATE = date(2026, 8, 21)
STARTED_AT = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
FINISHED_AT = STARTED_AT + timedelta(seconds=10)
GENERATED_AT = FINISHED_AT + timedelta(microseconds=1)


def _features(row_count: int) -> tuple[ReportFeatureCoverage, ...]:
    return tuple(
        ReportFeatureCoverage(
            feature_name=field,
            eligible_row_count=row_count,
            populated_count=row_count,
            null_count=0,
            warmup_null_count=0,
            dependency_null_count=0,
            unsupported_null_count=0,
            unexpected_null_count=0,
        )
        for field in REPORT_FEATURE_FIELDS
    )


def _dimension(
    code: str,
    *,
    evaluated: int,
    published: int,
) -> ReportDimensionCount:
    return ReportDimensionCount(
        code=code,
        listing_count=1,
        source_row_count=2,
        evaluated_row_count=evaluated,
        payload_row_count=2,
        published_row_count=published,
    )


def _counts(*, evaluated: int, published: int) -> ReportCounts:
    return ReportCounts(
        eligible_listing_count=1,
        selected_listing_count=1,
        source_listing_count=1,
        source_row_count=2,
        evaluated_row_count=evaluated,
        payload_row_count=2,
        published_listing_count=int(published > 0),
        published_row_count=published,
        providers=(_dimension("EODDATA", evaluated=evaluated, published=published),),
        markets=(_dimension("NYSE", evaluated=evaluated, published=published),),
        instrument_types=(
            _dimension("UNKNOWN", evaluated=evaluated, published=published),
        ),
    )


def _coverage() -> ReportCoverage:
    return ReportCoverage(
        date=ReportDateCoverage(
            source_first_date=date(2026, 8, 20),
            source_last_date=EFFECTIVE_DATE,
            payload_first_date=date(2026, 8, 20),
            payload_last_date=EFFECTIVE_DATE,
            effective_date_source_rows=1,
            effective_date_payload_rows=1,
            effective_date_published_rows=0,
        ),
        versions=(ReportVersionCoverage("TECH_INDICATORS_V1", 1, 2),),
        features=_features(2),
        benchmark=ReportBenchmarkCoverage(
            supported_listing_count=1,
            unsupported_listing_count=0,
            benchmark_linked_row_count=2,
            benchmark_unlinked_row_count=0,
            aligned_row_count=2,
            effective_date_aligned_count=1,
            complete_20_count=2,
            complete_50_count=2,
            complete_60_count=2,
            complete_63_count=2,
            complete_126_count=2,
            complete_252_count=2,
        ),
    )


def _source_readiness() -> ReportSourceReadiness:
    return ReportSourceReadiness(
        decision=SourceReadinessStatus.READY,
        effective_date=EFFECTIVE_DATE,
        reason_counts=(),
        provider_evidence=(
            ReportProviderEvidence(
                provider_code="EODDATA",
                evidence_kind="CORE_AND_COVERAGE",
                required=True,
                ready=True,
                successful_run_count=1,
                latest_successful_run_id=SOURCE_RUN_ID,
                source_listing_count=1,
                source_row_count=2,
                effective_date_row_count=1,
            ),
        ),
        benchmark=ReportSourceBenchmark(
            required=True,
            ready=True,
            provider_listing_id=BENCHMARK_ID,
            effective_date_bar_present=True,
        ),
    )


def _performance(*, evaluated: int, persisted: int, batches: int) -> ReportPerformance:
    return ReportPerformance(
        started_at=STARTED_AT,
        finished_at=FINISHED_AT,
        elapsed_seconds=10.0,
        peak_rss_bytes=128 * 1024 * 1024,
        phases=(
            ReportPhaseTiming("LOCK", 0.1),
            ReportPhaseTiming("CALCULATION", 3.0),
            ReportPhaseTiming("REPORT_FACTS", 0.2),
        ),
        throughput=ReportThroughput(
            evaluated_rows=evaluated,
            persisted_rows=persisted,
            elapsed_seconds=5.0,
            evaluated_rows_per_second=evaluated / 5.0,
            persisted_rows_per_second=persisted / 5.0,
        ),
        database=ReportDatabasePerformance(
            read_page_count=1,
            write_batch_count=batches,
            largest_read_page_rows=2,
            largest_write_batch_rows=persisted,
            longest_write_transaction_seconds=(0.1 if batches else None),
        ),
    )


def _prepared_publication() -> ReportPublication:
    return ReportPublication(
        method=PublicationMethod.IN_PLACE,
        report_phase=PublicationReportPhase.PREPARED_CANDIDATE,
        candidate_status="PREPARED",
        readiness_at_report=PublicationReadiness.NOT_READY,
        readiness_reason_counts=(
            ReportReasonCount("PUBLICATION_NOT_READY", 1),
        ),
        publication_listing_count=1,
        publication_source_row_count=2,
        publication_payload_row_count=2,
        benchmark_provider_listing_id=BENCHMARK_ID,
        benchmark_contract_version="TECH_INDICATORS_SPX_V1",
        resume_cursor=None,
    )


def _daily_pass() -> TechIndicatorsReport:
    return TechIndicatorsReport(
        report_id=DAILY_REPORT_ID,
        workflow_kind=WorkflowKind.DAILY,
        outcome=ReportOutcome.PASS,
        generated_at=GENERATED_AT,
        identity=ReportIdentity(
            run_id=RUN_ID,
            core_subject_key="all_series",
            effective_date=EFFECTIVE_DATE,
            publication_id=PUBLICATION_ID,
            core_job_name=DAILY_CORE_JOB_NAME,
        ),
        scope=ReportScope(
            scope_hash="a" * 64,
            effective_date=EFFECTIVE_DATE,
            start_date=None,
            end_date=None,
            provider_codes=("EODDATA",),
            requested_listing_count=1,
            resolved_listing_count=1,
        ),
        versions=ReportVersions("0.1.0", "3.14.6", "PostgreSQL 18.4"),
        lock=ReportLock(LockOutcome.ACQUIRED, 1, 0),
        source_readiness=_source_readiness(),
        publication=_prepared_publication(),
        counts=_counts(evaluated=2, published=0),
        writes=ReportWrites(
            inserted=2,
            batch_count=1,
            committed_batch_count=1,
        ),
        coverage=_coverage(),
        backfill=ReportBackfill(False, None, None, 0, None, None, 0, 0),
        performance=_performance(evaluated=2, persisted=2, batches=1),
        warnings=(),
        failures=(),
        diagnostic_samples=(),
        native_value_semantics=ReportNativeValueSemantics.for_providers(
            ("EODDATA",),
            analytical_rows_present=True,
        ),
    )


def _no_op() -> TechIndicatorsReport:
    base = _daily_pass()
    publication = ReportPublication(
        method=PublicationMethod.NONE,
        report_phase=PublicationReportPhase.EXISTING_PUBLICATION,
        candidate_status=None,
        readiness_at_report=PublicationReadiness.READY,
        readiness_reason_counts=(),
        publication_listing_count=1,
        publication_source_row_count=2,
        publication_payload_row_count=2,
        benchmark_provider_listing_id=BENCHMARK_ID,
        benchmark_contract_version="TECH_INDICATORS_SPX_V1",
        resume_cursor=None,
    )
    coverage = replace(
        base.coverage,
        date=replace(base.coverage.date, effective_date_published_rows=1),
    )
    return replace(
        base,
        outcome=ReportOutcome.NO_OP,
        identity=replace(
            base.identity,
            publication_id=None,
            existing_readiness_token="b" * 64,
        ),
        publication=publication,
        counts=_counts(evaluated=0, published=2),
        writes=ReportWrites(),
        coverage=coverage,
        performance=_performance(evaluated=0, persisted=0, batches=0),
    )


def _partial() -> TechIndicatorsReport:
    base = _daily_pass()
    resumed_cursor = ReportCursor(LISTING_ID, date(2026, 8, 20), 1)
    cursor = ReportCursor(LISTING_ID, EFFECTIVE_DATE, 2)
    return replace(
        base,
        report_id=BACKFILL_REPORT_ID,
        workflow_kind=WorkflowKind.BACKFILL,
        outcome=ReportOutcome.PARTIAL,
        identity=replace(base.identity, core_job_name=BACKFILL_CORE_JOB_NAME),
        scope=replace(
            base.scope,
            effective_date=None,
            start_date=date(2026, 8, 20),
            end_date=EFFECTIVE_DATE,
        ),
        publication=ReportPublication(
            method=PublicationMethod.STAGED,
            report_phase=PublicationReportPhase.UNPUBLISHED_PARTIAL,
            candidate_status="BUILDING",
            readiness_at_report=PublicationReadiness.NOT_READY,
            readiness_reason_counts=(
                ReportReasonCount("PUBLICATION_NOT_READY", 1),
            ),
            publication_listing_count=1,
            publication_source_row_count=2,
            publication_payload_row_count=2,
            benchmark_provider_listing_id=BENCHMARK_ID,
            benchmark_contract_version="TECH_INDICATORS_SPX_V1",
            resume_cursor=cursor,
        ),
        counts=_counts(evaluated=1, published=0),
        writes=ReportWrites(
            inserted=1,
            batch_count=1,
            committed_batch_count=1,
        ),
        backfill=ReportBackfill(
            True,
            1,
            3,
            2,
            cursor,
            resumed_cursor,
            1,
            1,
        ),
        performance=_performance(evaluated=1, persisted=1, batches=1),
        warnings=(ReportIssueAggregate("BACKFILL_INCOMPLETE", 1),),
    )


def _failure() -> TechIndicatorsReport:
    base = _daily_pass()
    return replace(
        base,
        outcome=ReportOutcome.FAIL,
        publication=replace(
            base.publication,
            report_phase=PublicationReportPhase.FAILED,
            candidate_status="FAILED",
        ),
        failures=(ReportIssueAggregate("CALCULATION_FAILED", 1),),
    )


@pytest.mark.parametrize(
    ("report", "outcome"),
    (
        (_daily_pass(), "PASS"),
        (
            replace(
                _daily_pass(),
                outcome=ReportOutcome.WARN,
                warnings=(ReportIssueAggregate("SOURCE_COVERAGE_WARNING", 1),),
            ),
            "WARN",
        ),
        (_no_op(), "NO_OP"),
        (_partial(), "PARTIAL"),
        (_failure(), "FAIL"),
    ),
)
def test_all_report_outcomes_render_deterministically(
    report: TechIndicatorsReport,
    outcome: str,
) -> None:
    first = render_tech_indicators_report_json(report)
    second = render_tech_indicators_report_json(report)
    payload = json.loads(first)

    assert first == second
    assert first.endswith(b"\n")
    assert b"\n" not in first[:-1]
    assert len(first) < REPORT_MAXIMUM_BYTES
    assert payload["schema_version"] == 1
    assert payload["outcome"] == outcome
    assert payload["generated_at"].endswith("Z")
    assert payload["identity"]["json_object_id"] is None
    assert payload["identity"]["pdf_object_id"] is None
    assert len(payload["coverage"]["features"]) == 76
    if outcome == "PARTIAL":
        assert payload["backfill"]["resumed_from_cursor"]["batch_number"] == 1
        assert payload["publication"]["resume_cursor"]["batch_number"] == 2
    assert set(payload) == {
        "schema_version",
        "report_id",
        "workflow_kind",
        "outcome",
        "generated_at",
        "identity",
        "scope",
        "versions",
        "lock",
        "source_readiness",
        "publication",
        "counts",
        "writes",
        "coverage",
        "backfill",
        "performance",
        "warnings",
        "failures",
        "diagnostic_samples",
        "native_value_semantics",
    }


def test_issue_messages_are_fixed_and_samples_receive_stable_ids() -> None:
    message = REPORT_DIAGNOSTIC_MESSAGE_CATALOG["UNEXPECTED_NULL"]
    unordered = (
        ReportDiagnosticSample("S999", "UNEXPECTED_NULL", message, ticker="ZZZ"),
        ReportDiagnosticSample("S998", "UNEXPECTED_NULL", message, ticker="AAA"),
    )

    samples = make_report_diagnostic_samples(unordered)

    assert tuple(item.sample_id for item in samples) == ("S001", "S002")
    assert tuple(item.ticker for item in samples) == ("AAA", "ZZZ")
    with pytest.raises(ValueError, match="fixed code"):
        ReportDiagnosticSample("S001", "UNEXPECTED_NULL", "raw exception")


def test_unknown_input_nonfinite_and_cross_section_drift_fail_closed() -> None:
    report = _daily_pass()

    with pytest.raises(TypeError, match="TechIndicatorsReport"):
        render_tech_indicators_report_json(  # type: ignore[arg-type]
            {**report.to_dict(), "unknown": True}
        )
    with pytest.raises(ValueError, match="finite"):
        ReportPhaseTiming("LOCK", float("nan"))
    with pytest.raises(ValueError, match="resolved scope"):
        replace(report, scope=replace(report.scope, resolved_listing_count=0))
    with pytest.raises(ValueError, match="FAIL"):
        replace(
            report,
            writes=replace(report.writes, inserted=1, failed=1),
            performance=_performance(evaluated=2, persisted=1, batches=1),
        )


def test_diagnostic_ceiling_and_unreferenced_samples_are_rejected() -> None:
    message = REPORT_DIAGNOSTIC_MESSAGE_CATALOG["CALCULATION_FAILED"]
    sample = ReportDiagnosticSample(
        "S001",
        "CALCULATION_FAILED",
        message,
    )

    with pytest.raises(ValueError, match="not referenced"):
        replace(_failure(), diagnostic_samples=(sample,))
    with pytest.raises(ValueError, match="100-sample"):
        make_report_diagnostic_samples(tuple(sample for _index in range(101)))


def test_native_disclosures_are_provider_aware_and_ordered() -> None:
    semantics = ReportNativeValueSemantics.for_providers(
        ("EODDATA", "STOOQ", "YAHOO"),
        analytical_rows_present=True,
    )

    assert len(semantics.notes) == 13
    assert semantics.notes[0] == "EODDATA_OHLC_ADJUSTMENT_UNSPECIFIED"
    assert semantics.notes[-1] == "CROSS_PROVIDER_VALUES_NOT_NORMALIZED"

    with pytest.raises(TypeError):
        REPORT_MESSAGE_CATALOG["NEW_CODE"] = "mutable"  # type: ignore[index]


def test_database_summary_factories_add_only_runner_evaluation_counts() -> None:
    database_dimension = ReportDimensionCoverage(
        code="EODDATA",
        listing_count=1,
        source_row_count=2,
        payload_row_count=2,
        published_row_count=0,
    )
    summary = ReportDatabaseSummary(
        selected_listing_count=1,
        source_listing_count=1,
        source_row_count=2,
        payload_listing_count=1,
        payload_row_count=2,
        published_listing_count=0,
        published_row_count=0,
        providers=(database_dimension,),
        markets=(replace(database_dimension, code="NYSE"),),
        instrument_types=(replace(database_dimension, code="UNKNOWN"),),
        dates=_coverage().date,
        versions=_coverage().versions,
        features=_coverage().features,
        benchmark=_coverage().benchmark,
    )

    counts = ReportCounts.from_database_summary(
        summary,
        eligible_listing_count=1,
        evaluated_row_count=2,
        evaluated_provider_rows={"EODDATA": 2},
        evaluated_market_rows={"NYSE": 2},
        evaluated_instrument_type_rows={"UNKNOWN": 2},
    )

    assert counts.providers == (_dimension("EODDATA", evaluated=2, published=0),)
    assert ReportCoverage.from_database_summary(summary) == _coverage()


def test_report_with_global_maximum_diagnostic_samples_stays_bounded() -> None:
    message = REPORT_DIAGNOSTIC_MESSAGE_CATALOG["CALCULATION_FAILED"]
    samples = tuple(
        ReportDiagnosticSample(
            sample_id=f"S{index:03d}",
            code="CALCULATION_FAILED",
            message=message,
            ticker=f"T{index:03d}",
        )
        for index in range(1, 101)
    )
    sample_ids = tuple(sample.sample_id for sample in samples)
    report = replace(
        _failure(),
        failures=(
            ReportIssueAggregate(
                "CALCULATION_FAILED",
                len(samples),
                sample_ids,
            ),
        ),
        diagnostic_samples=samples,
    )

    rendered = render_tech_indicators_report_json(report)

    assert len(rendered) < REPORT_MAXIMUM_BYTES
    assert len(json.loads(rendered)["diagnostic_samples"]) == 100
