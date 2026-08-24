"""Secret-safe Empire Core lifecycle for technical-indicator workflows."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Final
from uuid import UUID

from empire_core import RunContext, RunService

from empire_stonks_tech_indicators.config import DEFAULT_CALCULATION_VERSION
from empire_stonks_tech_indicators.models import TechIndicatorsSummary
from empire_stonks_tech_indicators.reports import (
    BACKFILL_CORE_JOB_NAME,
    DAILY_CORE_JOB_NAME,
    ReportOutcome,
    WorkflowKind,
)


TECH_INDICATORS_CORE_DOMAIN: Final = "stonks"
TECH_INDICATORS_DEFAULT_SUBJECT_KEY: Final = "all_series"
TECH_INDICATORS_HEARTBEAT_TIMEOUT_SECONDS: Final = 90
TECH_INDICATORS_SAFE_FAILURE_MESSAGE: Final = (
    "Technical-indicator workflow failed safely."
)

_CORE_RUN_TYPES = frozenset({"airflow", "cli", "api", "manual", "agent"})
_CORE_REASON_COUNT_LIMIT = 100
_RUNNER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")
_SUBJECT_KEY_PATTERN = re.compile(r"^(?:all_series|scope:[0-9a-f]{64})$")
_SUCCESS_OUTCOMES = frozenset(
    {ReportOutcome.PASS, ReportOutcome.WARN, ReportOutcome.NO_OP}
)
_FAILURE_OUTCOMES = frozenset({ReportOutcome.FAIL, ReportOutcome.PARTIAL})
_JOB_NAMES = {
    WorkflowKind.DAILY: DAILY_CORE_JOB_NAME,
    WorkflowKind.BACKFILL: BACKFILL_CORE_JOB_NAME,
}


def build_tech_indicators_core_summary(
    *,
    workflow_kind: WorkflowKind,
    outcome: ReportOutcome,
    calculation_version: str,
    summary: TechIndicatorsSummary,
    heartbeat_count: int = 0,
    json_report_object_id: UUID | None = None,
    pdf_report_object_id: UUID | None = None,
    publication_id: UUID | None = None,
) -> dict[str, object]:
    """Return the exact aggregate-only Core terminal summary.

    Diagnostic samples are deliberately omitted. Core receives counts and
    durable artifact identities, never source bars, feature rows, selectors,
    exception text, or complete listing-ID collections.
    """

    _validate_workflow_kind(workflow_kind)
    _validate_outcome(outcome)
    _validate_calculation_version(calculation_version)
    if not isinstance(summary, TechIndicatorsSummary):
        raise TypeError("summary must be a TechIndicatorsSummary.")
    if len(summary.reason_counts) > _CORE_REASON_COUNT_LIMIT:
        raise ValueError("Core summary reason counts cannot exceed 100 entries.")
    if type(heartbeat_count) is not int or heartbeat_count < 0:
        raise ValueError("heartbeat_count must be a non-negative integer.")
    for field_name, value in (
        ("json_report_object_id", json_report_object_id),
        ("pdf_report_object_id", pdf_report_object_id),
        ("publication_id", publication_id),
    ):
        _validate_optional_uuid(field_name, value)

    counts = summary.counts
    return {
        "workflow_kind": workflow_kind.value,
        "outcome": outcome.value,
        "calculation_version": calculation_version,
        "selected_listing_count": counts.selected_listings,
        "excluded_listing_count": counts.excluded_listings,
        "evaluated_row_count": counts.evaluated_rows,
        "inserted_row_count": counts.inserted_rows,
        "updated_row_count": counts.updated_rows,
        "unchanged_row_count": counts.unchanged_rows,
        "deleted_row_count": counts.deleted_rows,
        "changed_row_count": counts.changed_rows,
        "reason_counts": [item.to_dict() for item in summary.reason_counts],
        "total_issue_count": summary.total_issue_count,
        "issue_sample_count": summary.issue_sample_count,
        "issues_truncated": summary.issues_truncated,
        "heartbeat_count": heartbeat_count,
        "json_report_object_id": (
            None if json_report_object_id is None else str(json_report_object_id)
        ),
        "pdf_report_object_id": (
            None if pdf_report_object_id is None else str(pdf_report_object_id)
        ),
        "publication_id": None if publication_id is None else str(publication_id),
    }


@dataclass(frozen=True)
class TechIndicatorsCoreRun:
    """One started Core run with explicit, validated terminal transitions."""

    run_service: RunService = field(repr=False)
    run_context: RunContext
    workflow_kind: WorkflowKind
    calculation_version: str = DEFAULT_CALCULATION_VERSION
    heartbeat_count: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.run_service, RunService):
            raise TypeError("run_service must be a RunService.")
        _validate_workflow_kind(self.workflow_kind)
        _validate_calculation_version(self.calculation_version)
        self._validate_context(self.run_context, expected_status="started")

    @classmethod
    def start(
        cls,
        *,
        run_service: RunService,
        workflow_kind: WorkflowKind,
        effective_date: date,
        run_type: str,
        runner: str,
        subject_key: str = TECH_INDICATORS_DEFAULT_SUBJECT_KEY,
        calculation_version: str = DEFAULT_CALCULATION_VERSION,
    ) -> TechIndicatorsCoreRun:
        """Validate stable identity and start one heartbeat-enabled Core run."""

        if not isinstance(run_service, RunService):
            raise TypeError("run_service must be a RunService.")
        _validate_workflow_kind(workflow_kind)
        if type(effective_date) is not date:
            raise TypeError("effective_date must be a date.")
        if run_type not in _CORE_RUN_TYPES:
            raise ValueError("run_type is not supported by Empire Core.")
        _validate_safe_text("runner", runner)
        _validate_safe_text("subject_key", subject_key)
        _validate_calculation_version(calculation_version)

        context = run_service.start_run(
            domain=TECH_INDICATORS_CORE_DOMAIN,
            job_name=_JOB_NAMES[workflow_kind],
            subject_key=subject_key,
            effective_date=effective_date,
            run_type=run_type,
            runner=runner,
            runner_ref={},
            params={
                "workflow_kind": workflow_kind.value,
                "calculation_version": calculation_version,
            },
            heartbeat_timeout_seconds=(
                TECH_INDICATORS_HEARTBEAT_TIMEOUT_SECONDS
            ),
        )
        expected_started_identity = {
            "domain": TECH_INDICATORS_CORE_DOMAIN,
            "job_name": _JOB_NAMES[workflow_kind],
            "subject_key": subject_key,
            "effective_date": effective_date,
            "run_type": run_type,
            "runner": runner,
        }
        if not isinstance(context, RunContext) or any(
            getattr(context, field_name) != expected_value
            for field_name, expected_value in expected_started_identity.items()
        ):
            raise RuntimeError("Core lifecycle changed the stable run identity.")
        return cls(
            run_service=run_service,
            run_context=context,
            workflow_kind=workflow_kind,
            calculation_version=calculation_version,
        )

    def heartbeat(self) -> RunContext:
        """Record one Core heartbeat while preserving the started identity."""

        self._require_active()
        context = self.run_service.heartbeat(self.run_context.run_id)
        self._validate_context(context, expected_status="started")
        object.__setattr__(self, "run_context", context)
        object.__setattr__(self, "heartbeat_count", self.heartbeat_count + 1)
        return context

    def succeed(
        self,
        *,
        outcome: ReportOutcome,
        summary: TechIndicatorsSummary,
        json_report_object_id: UUID | None = None,
        pdf_report_object_id: UUID | None = None,
        publication_id: UUID | None = None,
    ) -> RunContext:
        """Complete the active Core run with a successful aggregate summary."""

        self._require_active()
        if outcome not in _SUCCESS_OUTCOMES:
            raise ValueError("succeed requires PASS, WARN, or NO_OP outcome.")
        core_summary = build_tech_indicators_core_summary(
            workflow_kind=self.workflow_kind,
            outcome=outcome,
            calculation_version=self.calculation_version,
            summary=summary,
            heartbeat_count=self.heartbeat_count,
            json_report_object_id=json_report_object_id,
            pdf_report_object_id=pdf_report_object_id,
            publication_id=publication_id,
        )
        context = self.run_service.complete_run(
            self.run_context.run_id,
            summary=core_summary,
        )
        self._validate_context(context, expected_status="succeeded")
        object.__setattr__(self, "run_context", context)
        return context

    def fail(
        self,
        *,
        outcome: ReportOutcome,
        summary: TechIndicatorsSummary,
        json_report_object_id: UUID | None = None,
        pdf_report_object_id: UUID | None = None,
        publication_id: UUID | None = None,
    ) -> RunContext:
        """Fail the active Core run without retaining exception details."""

        self._require_active()
        if outcome not in _FAILURE_OUTCOMES:
            raise ValueError("fail requires FAIL or PARTIAL outcome.")
        if outcome is ReportOutcome.PARTIAL and (
            self.workflow_kind is not WorkflowKind.BACKFILL
        ):
            raise ValueError("PARTIAL is valid only for a backfill workflow.")
        core_summary = build_tech_indicators_core_summary(
            workflow_kind=self.workflow_kind,
            outcome=outcome,
            calculation_version=self.calculation_version,
            summary=summary,
            heartbeat_count=self.heartbeat_count,
            json_report_object_id=json_report_object_id,
            pdf_report_object_id=pdf_report_object_id,
            publication_id=publication_id,
        )
        context = self.run_service.fail_run(
            self.run_context.run_id,
            TECH_INDICATORS_SAFE_FAILURE_MESSAGE,
            summary=core_summary,
        )
        self._validate_context(context, expected_status="failed")
        object.__setattr__(self, "run_context", context)
        return context

    def correct_succeeded_failure(
        self,
        *,
        summary: TechIndicatorsSummary,
        json_report_object_id: UUID | None = None,
        pdf_report_object_id: UUID | None = None,
        publication_id: UUID | None = None,
    ) -> RunContext:
        """Correct Core when publication fails after success was recorded.

        Publication is the final authority for a mutating workflow.  The
        runner records Core success immediately before the atomic publication
        transaction, so a failure in that transaction must replace the
        premature success with the fixed secret-safe failure terminal state.
        """

        if self.run_context.status != "succeeded":
            raise RuntimeError("Core failure correction requires succeeded status.")
        core_summary = build_tech_indicators_core_summary(
            workflow_kind=self.workflow_kind,
            outcome=ReportOutcome.FAIL,
            calculation_version=self.calculation_version,
            summary=summary,
            heartbeat_count=self.heartbeat_count,
            json_report_object_id=json_report_object_id,
            pdf_report_object_id=pdf_report_object_id,
            publication_id=publication_id,
        )
        context = self.run_service.fail_run(
            self.run_context.run_id,
            TECH_INDICATORS_SAFE_FAILURE_MESSAGE,
            summary=core_summary,
        )
        self._validate_context(context, expected_status="failed")
        object.__setattr__(self, "run_context", context)
        return context

    def _require_active(self) -> None:
        if self.run_context.status != "started":
            raise RuntimeError("Core run is already terminal.")

    def _validate_context(
        self,
        context: RunContext,
        *,
        expected_status: str,
    ) -> None:
        if not isinstance(context, RunContext):
            raise TypeError("Core lifecycle operation must return a RunContext.")
        expected_params = {
            "workflow_kind": self.workflow_kind.value,
            "calculation_version": self.calculation_version,
        }
        if context.params != expected_params:
            raise RuntimeError("Core lifecycle changed the safe run parameters.")
        expected = {
            "run_id": self.run_context.run_id,
            "domain": TECH_INDICATORS_CORE_DOMAIN,
            "job_name": _JOB_NAMES[self.workflow_kind],
            "subject_key": self.run_context.subject_key,
            "effective_date": self.run_context.effective_date,
            "run_type": self.run_context.run_type,
            "runner": self.run_context.runner,
            "heartbeat_timeout_seconds": (
                TECH_INDICATORS_HEARTBEAT_TIMEOUT_SECONDS
            ),
        }
        if context.status != expected_status:
            raise RuntimeError("Core lifecycle returned an unexpected status.")
        for field_name, expected_value in expected.items():
            if getattr(context, field_name) != expected_value:
                raise RuntimeError("Core lifecycle changed the stable run identity.")


def _validate_workflow_kind(value: object) -> None:
    if not isinstance(value, WorkflowKind):
        raise TypeError("workflow_kind must be a WorkflowKind.")


def _validate_outcome(value: object) -> None:
    if not isinstance(value, ReportOutcome):
        raise TypeError("outcome must be a ReportOutcome.")


def _validate_calculation_version(value: object) -> None:
    if value != DEFAULT_CALCULATION_VERSION:
        raise ValueError(
            f"calculation_version must be {DEFAULT_CALCULATION_VERSION}."
        )


def _validate_optional_uuid(field_name: str, value: object) -> None:
    if value is not None and not isinstance(value, UUID):
        raise TypeError(f"{field_name} must be a UUID or None.")


def _validate_safe_text(field_name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 200
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError(
            f"{field_name} must be non-empty, trimmed, and at most 200 characters."
        )

    if field_name == "subject_key" and not _SUBJECT_KEY_PATTERN.fullmatch(value):
        raise ValueError(
            "subject_key must be all_series or scope:<lowercase SHA-256>."
        )
    if field_name == "runner" and not _RUNNER_PATTERN.fullmatch(value):
        raise ValueError("runner must be a safe runtime identifier.")


__all__ = [
    "TECH_INDICATORS_CORE_DOMAIN",
    "TECH_INDICATORS_DEFAULT_SUBJECT_KEY",
    "TECH_INDICATORS_HEARTBEAT_TIMEOUT_SECONDS",
    "TECH_INDICATORS_SAFE_FAILURE_MESSAGE",
    "TechIndicatorsCoreRun",
    "build_tech_indicators_core_summary",
]
