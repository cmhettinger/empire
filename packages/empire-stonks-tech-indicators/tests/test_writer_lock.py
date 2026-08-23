from __future__ import annotations

import copy
import hashlib
import inspect

import pytest

import empire_stonks_tech_indicators as public_api
from empire_stonks_tech_indicators import (
    TECH_INDICATORS_LOCK_CONTENDED_MESSAGE,
    TECH_INDICATORS_LOCK_FAILURE_MESSAGE,
    TECH_INDICATORS_LOCK_LOST_MESSAGE,
    TECH_INDICATORS_TEMPORARY_FAILURE_EXIT_CODE,
    TECH_INDICATORS_WRITER_LOCK_KEY,
    TECH_INDICATORS_WRITER_LOCK_SEED,
    LockOutcome,
    TechIndicatorsWorkflowError,
    TechIndicatorsWriterLock,
    TechIndicatorsWriterLockLostError,
    WriterLockAcquisition,
    WriterLockOutcome,
    acquire_tech_indicators_writer_lock,
)
from empire_stonks_tech_indicators import writer_lock as writer_lock_module


SENSITIVE_TEXT = "postgresql://secret:password@private.example/empire"


class FakeCursor:
    def __init__(self, *, acquired: bool = True) -> None:
        self.acquired = acquired
        self.executions: list[tuple[str, tuple[object, ...] | None]] = []
        self.closed = False
        self.heartbeat_fails = False
        self.invalid_acquisition = False

    def execute(
        self,
        sql: str,
        parameters: tuple[object, ...] | None = None,
    ) -> None:
        if sql == "SELECT 1" and self.heartbeat_fails:
            raise RuntimeError(SENSITIVE_TEXT)
        self.executions.append((sql, parameters))

    def fetchone(self) -> tuple[object, ...]:
        if self.executions[-1][0] == "SELECT 1":
            return (1,)
        if self.invalid_acquisition:
            return ("yes",)
        return (self.acquired,)

    def close(self) -> None:
        self.closed = True


class FakeConnection:
    def __init__(self, *, acquired: bool = True) -> None:
        self.lock_cursor = FakeCursor(acquired=acquired)
        self.commit_count = 0
        self.rollback_count = 0
        self.close_count = 0
        self.commit_fails = False
        self.rollback_fails = False

    def cursor(self) -> FakeCursor:
        return self.lock_cursor

    def commit(self) -> None:
        self.commit_count += 1
        if self.commit_fails:
            raise RuntimeError(SENSITIVE_TEXT)

    def rollback(self) -> None:
        self.rollback_count += 1
        if self.rollback_fails:
            raise RuntimeError(SENSITIVE_TEXT)

    def close(self) -> None:
        self.close_count += 1


def _acquire(
    connection: FakeConnection,
) -> WriterLockAcquisition:
    return acquire_tech_indicators_writer_lock(
        connection_factory=lambda: connection
    )


def _lock(connection: FakeConnection) -> TechIndicatorsWriterLock:
    acquisition = _acquire(connection)
    assert acquisition.lock is not None
    return acquisition.lock


def test_writer_lock_api_is_explicitly_exported() -> None:
    assert writer_lock_module.__all__ == [
        "TECH_INDICATORS_LOCK_CONTENDED_MESSAGE",
        "TECH_INDICATORS_LOCK_FAILURE_MESSAGE",
        "TECH_INDICATORS_LOCK_LOST_MESSAGE",
        "TECH_INDICATORS_TEMPORARY_FAILURE_EXIT_CODE",
        "TechIndicatorsWriterLock",
        "WriterLockAcquisition",
        "WriterLockOutcome",
        "acquire_tech_indicators_writer_lock",
    ]
    assert public_api.TechIndicatorsWriterLock is TechIndicatorsWriterLock
    assert public_api.WriterLockAcquisition is WriterLockAcquisition
    assert public_api.WriterLockOutcome is WriterLockOutcome
    assert public_api.acquire_tech_indicators_writer_lock is (
        acquire_tech_indicators_writer_lock
    )


def test_frozen_key_is_first_eight_sha256_bytes_as_signed_big_endian() -> None:
    derived = int.from_bytes(
        hashlib.sha256(
            TECH_INDICATORS_WRITER_LOCK_SEED.encode("utf-8")
        ).digest()[:8],
        byteorder="big",
        signed=True,
    )

    assert derived == 7681980501239933110
    assert TECH_INDICATORS_WRITER_LOCK_KEY == derived
    assert "hash" not in writer_lock_module._ACQUIRE_SQL.lower()
    source = inspect.getsource(writer_lock_module)
    assert "pg_advisory_unlock" not in source
    assert "hashtext" not in source
    assert "sleep(" not in source


def test_acquisition_explicitly_begins_read_committed_and_uses_frozen_key() -> None:
    connection = FakeConnection()

    acquisition = _acquire(connection)

    assert acquisition.acquired is True
    assert acquisition.outcome is WriterLockOutcome.ACQUIRED
    assert acquisition.message is None
    assert acquisition.to_dict() == {
        "outcome": "ACQUIRED",
        "name": TECH_INDICATORS_WRITER_LOCK_SEED,
        "key": TECH_INDICATORS_WRITER_LOCK_KEY,
        "message": None,
    }
    assert connection.lock_cursor.executions == [
        ("BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED", None),
        (
            "SELECT pg_try_advisory_xact_lock(%s::bigint)",
            (TECH_INDICATORS_WRITER_LOCK_KEY,),
        ),
    ]


def test_contention_returns_immediately_and_closes_without_a_handle() -> None:
    connection = FakeConnection(acquired=False)

    acquisition = _acquire(connection)

    assert acquisition.acquired is False
    assert acquisition.outcome is WriterLockOutcome.CONTENDED
    assert acquisition.lock is None
    assert acquisition.message == TECH_INDICATORS_LOCK_CONTENDED_MESSAGE
    assert TECH_INDICATORS_TEMPORARY_FAILURE_EXIT_CODE == 75
    assert connection.rollback_count == 1
    assert connection.lock_cursor.closed is True
    assert connection.close_count == 1
    assert SENSITIVE_TEXT not in repr(acquisition)


def test_heartbeat_report_and_terminal_commit_use_the_owned_cursor() -> None:
    connection = FakeConnection()
    lock = _lock(connection)
    observed_cursor: list[FakeCursor] = []

    assert lock.heartbeat() == 1
    assert lock.heartbeat_count == 1
    assert lock.report_facts().outcome is LockOutcome.ACQUIRED
    assert lock.report_facts().heartbeat_count == 1

    result = lock.commit_terminal(
        lambda cursor: observed_cursor.append(cursor) or "published"
    )

    assert result == "published"
    assert observed_cursor == [connection.lock_cursor]
    assert connection.commit_count == 1
    assert connection.rollback_count == 0
    assert connection.lock_cursor.closed is True
    assert connection.close_count == 1
    assert lock.is_held is False
    with pytest.raises(RuntimeError, match="released"):
        lock.heartbeat()


def test_healthy_noop_commit_and_dry_run_rollback_are_single_use() -> None:
    committed_connection = FakeConnection()
    committed = _lock(committed_connection)
    committed.commit()
    assert committed_connection.commit_count == 1
    with pytest.raises(RuntimeError, match="released"):
        committed.commit()

    rolled_back_connection = FakeConnection()
    rolled_back = _lock(rolled_back_connection)
    rolled_back.rollback()
    assert rolled_back_connection.rollback_count == 1
    with pytest.raises(RuntimeError, match="released"):
        rolled_back.rollback()


def test_context_exit_and_terminal_error_roll_back_without_masking() -> None:
    class Cancellation(BaseException):
        pass

    context_connection = FakeConnection()
    with pytest.raises(Cancellation):
        with _lock(context_connection):
            raise Cancellation("cancelled")
    assert context_connection.rollback_count == 1
    assert context_connection.close_count == 1

    terminal_connection = FakeConnection()
    terminal_lock = _lock(terminal_connection)
    with pytest.raises(ValueError, match="validation"):
        terminal_lock.commit_terminal(
            lambda _cursor: (_ for _ in ()).throw(
                ValueError("validation failed")
            )
        )
    assert terminal_connection.rollback_count == 1
    assert terminal_connection.commit_count == 0
    assert terminal_connection.close_count == 1


def test_heartbeat_failure_marks_lost_closes_and_never_reacquires() -> None:
    connection = FakeConnection()
    lock = _lock(connection)
    connection.lock_cursor.heartbeat_fails = True

    with pytest.raises(
        TechIndicatorsWriterLockLostError,
        match=TECH_INDICATORS_LOCK_LOST_MESSAGE,
    ) as raised:
        lock.heartbeat()

    assert SENSITIVE_TEXT not in str(raised.value)
    assert lock.outcome is WriterLockOutcome.LOST
    assert lock.is_held is False
    assert lock.heartbeat_failure_count == 1
    report = lock.report_facts()
    assert report.outcome is LockOutcome.LOST
    assert report.heartbeat_failure_count == 1
    assert len(connection.lock_cursor.executions) == 2
    with pytest.raises(TechIndicatorsWriterLockLostError):
        lock.heartbeat()
    assert len(connection.lock_cursor.executions) == 2


def test_commit_failure_is_safe_lock_loss_and_closes() -> None:
    connection = FakeConnection()
    connection.commit_fails = True
    lock = _lock(connection)

    with pytest.raises(
        TechIndicatorsWriterLockLostError,
        match=TECH_INDICATORS_LOCK_LOST_MESSAGE,
    ) as raised:
        lock.commit()

    assert SENSITIVE_TEXT not in str(raised.value)
    assert lock.outcome is WriterLockOutcome.LOST
    assert connection.rollback_count == 1
    assert connection.close_count == 1


def test_handle_cannot_be_copied_or_expose_a_connection_property() -> None:
    connection = FakeConnection()
    lock = _lock(connection)

    with pytest.raises(TypeError, match="cannot be copied"):
        copy.copy(lock)
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.deepcopy(lock)
    assert "connection" not in inspect.signature(
        lock.commit_terminal
    ).parameters
    assert not hasattr(lock, "connection")
    lock.rollback()


def test_acquisition_failure_is_fixed_safe_error_and_closes() -> None:
    connection = FakeConnection()
    connection.lock_cursor.invalid_acquisition = True

    with pytest.raises(
        TechIndicatorsWorkflowError,
        match=TECH_INDICATORS_LOCK_FAILURE_MESSAGE,
    ) as raised:
        _acquire(connection)

    assert SENSITIVE_TEXT not in str(raised.value)
    assert connection.rollback_count == 1
    assert connection.close_count == 1


def test_connection_factory_failure_does_not_chain_sensitive_details() -> None:
    def fail() -> object:
        raise RuntimeError(SENSITIVE_TEXT)

    with pytest.raises(
        TechIndicatorsWorkflowError,
        match=TECH_INDICATORS_LOCK_FAILURE_MESSAGE,
    ) as raised:
        acquire_tech_indicators_writer_lock(connection_factory=fail)

    assert SENSITIVE_TEXT not in str(raised.value)
    assert raised.value.__cause__ is None


@pytest.mark.parametrize(
    "workload",
    [
        "daily",
        "backfill",
        "version-rebuild",
        "disjoint-listing",
        "correction",
        "cleanup",
        "resume",
        "no-op",
        "dry-run",
    ],
)
def test_every_mutating_workload_uses_the_same_scope_free_acquisition(
    workload: str,
) -> None:
    assert workload
    assert tuple(
        inspect.signature(acquire_tech_indicators_writer_lock).parameters
    ) == ("connection_factory",)
