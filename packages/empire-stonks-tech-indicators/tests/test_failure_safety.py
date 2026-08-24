from __future__ import annotations

from asyncio import CancelledError
from uuid import uuid4

import pytest

import empire_stonks_tech_indicators.failure_safety as failure_safety
from empire_stonks_tech_indicators.core_lifecycle import (
    TECH_INDICATORS_SAFE_FAILURE_MESSAGE,
)
from empire_stonks_tech_indicators.exceptions import TechIndicatorsWorkflowError
from empire_stonks_tech_indicators.writer_lock import WriterLockOutcome


class FakeLock:
    def __init__(self, *, held: bool) -> None:
        self.is_held = held
        self.committed = False

    def __enter__(self) -> FakeLock:
        return self

    def __exit__(self, *_values: object) -> bool:
        return False

    def commit_terminal(self, operation: object) -> None:
        operation("cursor")  # type: ignore[operator]
        self.is_held = False
        self.committed = True


def test_cancellation_detection_is_narrow_and_preserves_runtime_types() -> None:
    assert failure_safety.is_workflow_cancellation(CancelledError())
    assert failure_safety.is_workflow_cancellation(KeyboardInterrupt())
    assert failure_safety.is_workflow_cancellation(SystemExit())
    assert not failure_safety.is_workflow_cancellation(RuntimeError())


def test_safe_workflow_error_never_exposes_root_details() -> None:
    error = failure_safety.safe_workflow_error(
        RuntimeError("password=should-not-escape")
    )

    assert str(error) == TECH_INDICATORS_SAFE_FAILURE_MESSAGE
    assert "password" not in repr(error)


@pytest.mark.parametrize("abandoned", (False, True))
def test_terminal_cleanup_uses_held_lock(
    monkeypatch: pytest.MonkeyPatch,
    abandoned: bool,
) -> None:
    publication_id = uuid4()
    calls: list[tuple[object, object, bool]] = []
    lock = FakeLock(held=True)
    monkeypatch.setattr(
        failure_safety,
        "fail_unpublished_publication",
        lambda *, cursor, publication_id, abandoned: calls.append(
            (cursor, publication_id, abandoned)
        ),
    )

    failure_safety.terminalize_unpublished_candidate(
        publication_id=publication_id,
        lock=lock,
        lock_connection_factory=lambda: None,
        abandoned=abandoned,
    )

    assert calls == [("cursor", publication_id, abandoned)]
    assert lock.committed


def test_terminal_cleanup_reacquires_after_finalization_released_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publication_id = uuid4()
    released = FakeLock(held=False)
    recovery = FakeLock(held=True)
    calls: list[object] = []
    monkeypatch.setattr(
        failure_safety,
        "fail_unpublished_publication",
        lambda **values: calls.append(values["publication_id"]),
    )
    monkeypatch.setattr(
        failure_safety,
        "acquire_tech_indicators_writer_lock",
        lambda **_values: type(
            "Acquisition",
            (),
            {"outcome": WriterLockOutcome.ACQUIRED, "lock": recovery},
        )(),
    )

    failure_safety.terminalize_unpublished_candidate(
        publication_id=publication_id,
        lock=released,
        lock_connection_factory=lambda: None,
        abandoned=False,
    )

    assert calls == [publication_id]
    assert recovery.committed


def test_terminal_cleanup_observes_commit_that_succeeded_before_caller_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class PublishedCursor:
        def execute(self, _sql: str, _params: object) -> None:
            pass

        def fetchone(self) -> tuple[str]:
            return ("PUBLISHED",)

    def reject_terminalization(**_values: object) -> None:
        raise TechIndicatorsWorkflowError("already terminal")

    monkeypatch.setattr(
        failure_safety,
        "fail_unpublished_publication",
        reject_terminalization,
    )

    published = failure_safety._fail_or_observe_published(
        cursor=PublishedCursor(),
        publication_id=uuid4(),
        abandoned=False,
    )

    assert published
