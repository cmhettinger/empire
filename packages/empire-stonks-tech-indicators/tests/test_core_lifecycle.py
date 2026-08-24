from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest

from empire_core import RunContext, RunService
from empire_stonks_tech_indicators import (
    FeatureCounts,
    ReasonCount,
    ReportOutcome,
    TECH_INDICATORS_CORE_DOMAIN,
    TECH_INDICATORS_DEFAULT_SUBJECT_KEY,
    TECH_INDICATORS_HEARTBEAT_TIMEOUT_SECONDS,
    TECH_INDICATORS_SAFE_FAILURE_MESSAGE,
    TechIndicatorsCoreRun,
    TechIndicatorsIssue,
    TechIndicatorsSummary,
    WorkflowKind,
    build_tech_indicators_core_summary,
)


EFFECTIVE_DATE = date(2026, 8, 22)
JSON_REPORT_ID = UUID("10000000-0000-4000-8000-000000000001")
PDF_REPORT_ID = UUID("10000000-0000-4000-8000-000000000002")
PUBLICATION_ID = UUID("10000000-0000-4000-8000-000000000003")
SENSITIVE_TEXT = "source close=123.45 feature rsi_14=70 password=hunter2"


class FakeRunRepository:
    def __init__(self) -> None:
        self.runs: dict[UUID, RunContext] = {}
        self.runner_refs: dict[UUID, dict[str, object]] = {}
        self.failure_messages: dict[UUID, str] = {}
        self.heartbeat_count = 0

    def start_run(self, **values: object) -> RunContext:
        context = RunContext(
            run_id=uuid4(),
            domain=values["domain"],  # type: ignore[arg-type]
            job_name=values["job_name"],  # type: ignore[arg-type]
            subject_key=values["subject_key"],  # type: ignore[arg-type]
            effective_date=values["effective_date"],  # type: ignore[arg-type]
            run_type=values["run_type"],  # type: ignore[arg-type]
            status="started",
            runner=values["runner"],  # type: ignore[arg-type]
            params=values["params"],  # type: ignore[arg-type]
            started_at=datetime.now(UTC),
            heartbeat_timeout_seconds=values[  # type: ignore[arg-type]
                "heartbeat_timeout_seconds"
            ],
            last_heartbeat_at=datetime.now(UTC),
        )
        self.runs[context.run_id] = context
        self.runner_refs[context.run_id] = values[  # type: ignore[assignment]
            "runner_ref"
        ]
        return context

    def complete_run(
        self,
        run_id: UUID,
        summary: dict[str, object] | None,
    ) -> RunContext:
        context = replace(
            self.runs[run_id],
            status="succeeded",
            summary=summary or {},
            completed_at=datetime.now(UTC),
        )
        self.runs[run_id] = context
        return context

    def fail_run(
        self,
        run_id: UUID,
        error_message: str,
        summary: dict[str, object] | None,
    ) -> RunContext:
        context = replace(
            self.runs[run_id],
            status="failed",
            summary=summary or {},
            completed_at=datetime.now(UTC),
        )
        self.runs[run_id] = context
        self.failure_messages[run_id] = error_message
        return context

    def heartbeat(self, run_id: UUID) -> RunContext:
        self.heartbeat_count += 1
        context = replace(
            self.runs[run_id],
            last_heartbeat_at=datetime.now(UTC),
        )
        self.runs[run_id] = context
        return context


def _summary() -> TechIndicatorsSummary:
    return TechIndicatorsSummary(
        counts=FeatureCounts(
            selected_listings=3,
            excluded_listings=1,
            evaluated_rows=12,
            inserted_rows=4,
            updated_rows=2,
            unchanged_rows=6,
            deleted_rows=1,
        ),
        reason_counts=(ReasonCount("SOURCE_NOT_READY", 2),),
        total_issue_count=2,
        issues=(
            TechIndicatorsIssue(
                code="SOURCE_NOT_READY",
                severity="ERROR",
                message=SENSITIVE_TEXT,
            ),
        ),
    )


def _start(
    repository: FakeRunRepository,
    *,
    workflow_kind: WorkflowKind = WorkflowKind.DAILY,
    subject_key: str = TECH_INDICATORS_DEFAULT_SUBJECT_KEY,
) -> TechIndicatorsCoreRun:
    return TechIndicatorsCoreRun.start(
        run_service=RunService(repository),
        workflow_kind=workflow_kind,
        effective_date=EFFECTIVE_DATE,
        run_type="cli",
        runner="pytest",
        subject_key=subject_key,
    )


def test_start_uses_frozen_identity_and_metadata_allowlist() -> None:
    repository = FakeRunRepository()

    lifecycle = _start(repository)
    context = lifecycle.run_context

    assert context.domain == TECH_INDICATORS_CORE_DOMAIN
    assert context.job_name == "stonks_tech_indicators_daily"
    assert context.subject_key == TECH_INDICATORS_DEFAULT_SUBJECT_KEY
    assert context.effective_date == EFFECTIVE_DATE
    assert context.status == "started"
    assert (
        context.heartbeat_timeout_seconds
        == TECH_INDICATORS_HEARTBEAT_TIMEOUT_SECONDS
    )
    assert context.params == {
        "workflow_kind": "DAILY",
        "calculation_version": "TECH_INDICATORS_V1",
    }
    assert repository.runner_refs[context.run_id] == {}


def test_heartbeat_and_success_preserve_identity_and_store_aggregates_only() -> None:
    repository = FakeRunRepository()
    lifecycle = _start(repository)
    started = lifecycle.run_context

    heartbeat = lifecycle.heartbeat()
    completed = lifecycle.succeed(
        outcome=ReportOutcome.WARN,
        summary=_summary(),
        json_report_object_id=JSON_REPORT_ID,
        pdf_report_object_id=PDF_REPORT_ID,
        publication_id=PUBLICATION_ID,
    )

    assert repository.heartbeat_count == 1
    assert heartbeat.run_id == started.run_id == completed.run_id
    assert completed.status == "succeeded"
    assert completed.summary == {
        "workflow_kind": "DAILY",
        "outcome": "WARN",
        "calculation_version": "TECH_INDICATORS_V1",
        "selected_listing_count": 3,
        "excluded_listing_count": 1,
        "evaluated_row_count": 12,
        "inserted_row_count": 4,
        "updated_row_count": 2,
        "unchanged_row_count": 6,
        "deleted_row_count": 1,
        "changed_row_count": 7,
        "reason_counts": [{"code": "SOURCE_NOT_READY", "count": 2}],
        "total_issue_count": 2,
        "issue_sample_count": 1,
        "issues_truncated": True,
        "heartbeat_count": 1,
        "json_report_object_id": str(JSON_REPORT_ID),
        "pdf_report_object_id": str(PDF_REPORT_ID),
        "publication_id": str(PUBLICATION_ID),
    }
    serialized_metadata = json.dumps(
        {
            "params": completed.params,
            "summary": completed.summary,
            "runner_ref": repository.runner_refs[completed.run_id],
        },
        sort_keys=True,
    )
    assert SENSITIVE_TEXT not in serialized_metadata
    assert "rsi_14" not in serialized_metadata
    assert "123.45" not in serialized_metadata


def test_failure_uses_fixed_message_and_discards_issue_details() -> None:
    repository = FakeRunRepository()
    lifecycle = _start(repository, workflow_kind=WorkflowKind.BACKFILL)

    failed = lifecycle.fail(
        outcome=ReportOutcome.PARTIAL,
        summary=_summary(),
        json_report_object_id=JSON_REPORT_ID,
    )

    assert failed.job_name == "stonks_tech_indicators_backfill"
    assert failed.status == "failed"
    assert failed.summary["outcome"] == "PARTIAL"
    assert repository.failure_messages[failed.run_id] == (
        TECH_INDICATORS_SAFE_FAILURE_MESSAGE
    )
    assert SENSITIVE_TEXT not in repr(failed.summary)
    assert SENSITIVE_TEXT not in repository.failure_messages[failed.run_id]


def test_publication_failure_corrects_premature_core_success_safely() -> None:
    repository = FakeRunRepository()
    lifecycle = _start(repository)
    lifecycle.succeed(
        outcome=ReportOutcome.PASS,
        summary=_summary(),
        json_report_object_id=JSON_REPORT_ID,
        pdf_report_object_id=PDF_REPORT_ID,
        publication_id=PUBLICATION_ID,
    )

    corrected = lifecycle.correct_succeeded_failure(
        summary=TechIndicatorsSummary(),
        publication_id=PUBLICATION_ID,
    )

    assert corrected.status == "failed"
    assert corrected.summary["outcome"] == "FAIL"
    assert corrected.summary["json_report_object_id"] is None
    assert corrected.summary["pdf_report_object_id"] is None
    assert corrected.summary["publication_id"] == str(PUBLICATION_ID)
    assert repository.failure_messages[corrected.run_id] == (
        TECH_INDICATORS_SAFE_FAILURE_MESSAGE
    )


def test_terminal_run_rejects_heartbeat_or_second_transition() -> None:
    repository = FakeRunRepository()
    lifecycle = _start(repository)
    lifecycle.succeed(outcome=ReportOutcome.PASS, summary=TechIndicatorsSummary())

    with pytest.raises(RuntimeError, match="already terminal"):
        lifecycle.heartbeat()
    with pytest.raises(RuntimeError, match="already terminal"):
        lifecycle.fail(
            outcome=ReportOutcome.FAIL,
            summary=TechIndicatorsSummary(),
        )


def test_lifecycle_identity_is_immutable() -> None:
    lifecycle = _start(FakeRunRepository())

    with pytest.raises(FrozenInstanceError):
        lifecycle.workflow_kind = WorkflowKind.BACKFILL


def test_lifecycle_accepts_canonical_scoped_subject() -> None:
    repository = FakeRunRepository()
    subject_key = f"scope:{'a' * 64}"

    lifecycle = _start(repository, subject_key=subject_key)

    assert lifecycle.run_context.subject_key == subject_key


@pytest.mark.parametrize(
    ("kwargs", "error", "message"),
    [
        ({"workflow_kind": "DAILY"}, TypeError, "WorkflowKind"),
        ({"effective_date": datetime.now(UTC)}, TypeError, "date"),
        ({"run_type": "cron"}, ValueError, "run_type"),
        ({"runner": "  "}, ValueError, "runner"),
        ({"subject_key": " all_series"}, ValueError, "subject_key"),
        ({"subject_key": "scope:not-a-hash"}, ValueError, "subject_key"),
        ({"calculation_version": "TECH_INDICATORS_V2"}, ValueError, "V1"),
    ],
)
def test_invalid_identity_does_not_start_core_run(
    kwargs: dict[str, object],
    error: type[Exception],
    message: str,
) -> None:
    repository = FakeRunRepository()
    values: dict[str, object] = {
        "run_service": RunService(repository),
        "workflow_kind": WorkflowKind.DAILY,
        "effective_date": EFFECTIVE_DATE,
        "run_type": "cli",
        "runner": "pytest",
    }
    values.update(kwargs)

    with pytest.raises(error, match=message):
        TechIndicatorsCoreRun.start(**values)  # type: ignore[arg-type]

    assert repository.runs == {}


def test_transition_outcomes_must_match_core_status() -> None:
    repository = FakeRunRepository()
    lifecycle = _start(repository)

    with pytest.raises(ValueError, match="PASS, WARN, or NO_OP"):
        lifecycle.succeed(
            outcome=ReportOutcome.FAIL,
            summary=TechIndicatorsSummary(),
        )
    with pytest.raises(ValueError, match="FAIL or PARTIAL"):
        lifecycle.fail(
            outcome=ReportOutcome.WARN,
            summary=TechIndicatorsSummary(),
        )
    with pytest.raises(ValueError, match="backfill"):
        lifecycle.fail(
            outcome=ReportOutcome.PARTIAL,
            summary=TechIndicatorsSummary(),
        )


def test_summary_builder_rejects_payload_like_untyped_inputs() -> None:
    with pytest.raises(TypeError, match="TechIndicatorsSummary"):
        build_tech_indicators_core_summary(
            workflow_kind=WorkflowKind.DAILY,
            outcome=ReportOutcome.PASS,
            calculation_version="TECH_INDICATORS_V1",
            summary={"source_bars": [SENSITIVE_TEXT]},  # type: ignore[arg-type]
        )
