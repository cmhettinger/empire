"""Shared fail-closed cleanup for technical-indicator workflow runners."""

from __future__ import annotations

from asyncio import CancelledError
from collections.abc import Callable
from typing import Any
from uuid import UUID

from empire_stonks_tech_indicators.core_lifecycle import (
    TECH_INDICATORS_SAFE_FAILURE_MESSAGE,
    TechIndicatorsCoreRun,
)
from empire_stonks_tech_indicators.exceptions import TechIndicatorsWorkflowError
from empire_stonks_tech_indicators.models import TechIndicatorsSummary
from empire_stonks_tech_indicators.publication import fail_unpublished_publication
from empire_stonks_tech_indicators.reports import ReportOutcome
from empire_stonks_tech_indicators.writer_lock import (
    WriterLockOutcome,
    acquire_tech_indicators_writer_lock,
)


_CANCELLATION_TYPES = (CancelledError, KeyboardInterrupt, SystemExit)


def is_workflow_cancellation(error: BaseException) -> bool:
    """Return whether runtime cancellation semantics must be preserved."""

    return isinstance(error, _CANCELLATION_TYPES)


def close_core_after_failure(
    *,
    core_run: TechIndicatorsCoreRun | None,
    summary: TechIndicatorsSummary,
    publication_id: UUID | None,
    publication_was_published: bool,
    json_report_object_id: UUID | None = None,
    pdf_report_object_id: UUID | None = None,
) -> None:
    """Best-effort fail or correct Core without masking the root failure."""

    if core_run is None or publication_was_published:
        return
    try:
        if core_run.run_context.status == "started":
            core_run.fail(
                outcome=ReportOutcome.FAIL,
                summary=summary,
                json_report_object_id=json_report_object_id,
                pdf_report_object_id=pdf_report_object_id,
                publication_id=publication_id,
            )
        elif core_run.run_context.status == "succeeded":
            core_run.correct_succeeded_failure(
                summary=summary,
                json_report_object_id=json_report_object_id,
                pdf_report_object_id=pdf_report_object_id,
                publication_id=publication_id,
            )
    except Exception:
        pass


def terminalize_unpublished_candidate(
    *,
    publication_id: UUID | None,
    lock: Any,
    lock_connection_factory: Callable[[], Any],
    abandoned: bool,
) -> bool:
    """Terminalize a candidate and report an already-published commit."""

    if publication_id is None:
        return False
    if lock.is_held:
        try:
            return lock.commit_terminal(
                lambda cursor: _fail_or_observe_published(
                    cursor=cursor,
                    publication_id=publication_id,
                    abandoned=abandoned,
                )
            )
        except Exception:
            pass
    try:
        acquired = acquire_tech_indicators_writer_lock(
            connection_factory=lock_connection_factory
        )
        if acquired.outcome is not WriterLockOutcome.ACQUIRED:
            return False
        recovery_lock = acquired.lock
        assert recovery_lock is not None
        with recovery_lock:
            return recovery_lock.commit_terminal(
                lambda cursor: _fail_or_observe_published(
                    cursor=cursor,
                    publication_id=publication_id,
                    abandoned=abandoned,
                )
            )
    except Exception:
        return False


def _fail_or_observe_published(
    *, cursor: Any, publication_id: UUID, abandoned: bool
) -> bool:
    """Resolve commit ambiguity without replaying an already-published unit."""

    try:
        fail_unpublished_publication(
            cursor=cursor,
            publication_id=publication_id,
            abandoned=abandoned,
        )
        return False
    except TechIndicatorsWorkflowError:
        cursor.execute(
            "SELECT status FROM stonks.tech_indicators_publication "
            "WHERE publication_id = %s",
            (publication_id,),
        )
        row = cursor.fetchone()
        if row == ("PUBLISHED",):
            return True
        raise


def safe_workflow_error(_error: BaseException) -> TechIndicatorsWorkflowError:
    """Return the fixed outward error while callers retain the root cause."""

    return TechIndicatorsWorkflowError(TECH_INDICATORS_SAFE_FAILURE_MESSAGE)


__all__ = [
    "close_core_after_failure",
    "is_workflow_cancellation",
    "safe_workflow_error",
    "terminalize_unpublished_candidate",
]
