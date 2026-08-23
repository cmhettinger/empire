"""Package-owned P0.10 PostgreSQL writer-lock lifecycle."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final, TypeVar

from empire_stonks_tech_indicators.exceptions import (
    TechIndicatorsWorkflowError,
    TechIndicatorsWriterLockLostError,
)
from empire_stonks_tech_indicators.publication import (
    TECH_INDICATORS_WRITER_LOCK_KEY,
    TECH_INDICATORS_WRITER_LOCK_SEED,
)

if TYPE_CHECKING:
    from empire_stonks_tech_indicators.reports import ReportLock


TECH_INDICATORS_LOCK_CONTENDED_MESSAGE: Final = (
    "Technical-indicator writer lock is already held."
)
TECH_INDICATORS_LOCK_LOST_MESSAGE: Final = (
    "Technical-indicator writer lock was lost."
)
TECH_INDICATORS_LOCK_FAILURE_MESSAGE: Final = (
    "Technical-indicator writer lock operation failed safely."
)
TECH_INDICATORS_TEMPORARY_FAILURE_EXIT_CODE: Final = 75

_ACQUIRE_SQL = "SELECT pg_try_advisory_xact_lock(%s::bigint)"
_BEGIN_SQL = "BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED"
_HEARTBEAT_SQL = "SELECT 1"

_ResultT = TypeVar("_ResultT")


class WriterLockOutcome(StrEnum):
    """Frozen P0.10 outcomes, including pre-work contention and lock loss."""

    ACQUIRED = "ACQUIRED"
    CONTENDED = "CONTENDED"
    LOST = "LOST"


class _WriterLockState(StrEnum):
    HELD = "HELD"
    LOST = "LOST"
    COMMITTED = "COMMITTED"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass(frozen=True)
class WriterLockAcquisition:
    """Bounded acquisition result with an acquired handle or contention."""

    outcome: WriterLockOutcome
    lock: TechIndicatorsWriterLock | None
    message: str | None
    name: str = TECH_INDICATORS_WRITER_LOCK_SEED
    key: int = TECH_INDICATORS_WRITER_LOCK_KEY

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, WriterLockOutcome):
            raise TypeError("outcome must be a WriterLockOutcome.")
        if self.name != TECH_INDICATORS_WRITER_LOCK_SEED:
            raise ValueError("name must match the frozen writer-lock seed.")
        if self.key != TECH_INDICATORS_WRITER_LOCK_KEY:
            raise ValueError("key must match the frozen writer-lock key.")
        if self.outcome is WriterLockOutcome.ACQUIRED:
            if not isinstance(self.lock, TechIndicatorsWriterLock):
                raise TypeError("ACQUIRED requires a writer-lock handle.")
            if self.message is not None:
                raise ValueError("ACQUIRED must not include a message.")
        elif self.outcome is WriterLockOutcome.CONTENDED:
            if self.lock is not None:
                raise ValueError("CONTENDED cannot include a lock handle.")
            if self.message != TECH_INDICATORS_LOCK_CONTENDED_MESSAGE:
                raise ValueError("CONTENDED must use the fixed safe message.")
        else:
            raise ValueError("Acquisition cannot directly return LOST.")

    @property
    def acquired(self) -> bool:
        return self.outcome is WriterLockOutcome.ACQUIRED

    def to_dict(self) -> dict[str, object]:
        return {
            "outcome": self.outcome.value,
            "name": self.name,
            "key": self.key,
            "message": self.message,
        }


class TechIndicatorsWriterLock:
    """Single-use owner of one dedicated advisory-lock transaction.

    Instances are created only by :func:`acquire_tech_indicators_writer_lock`.
    The underlying connection is deliberately not public. Calculation and
    staged writes use other caller-owned connections; only a terminal callback
    receives this transaction's cursor immediately before the same handle
    commits publication and releases the lock.
    """

    __slots__ = (
        "_connection",
        "_cursor",
        "_heartbeat_count",
        "_heartbeat_failure_count",
        "_state",
    )

    def __init__(self, *, connection: Any, cursor: Any) -> None:
        self._connection = connection
        self._cursor = cursor
        self._state = _WriterLockState.HELD
        self._heartbeat_count = 0
        self._heartbeat_failure_count = 0

    def __copy__(self) -> None:
        raise TypeError("TechIndicatorsWriterLock cannot be copied.")

    def __deepcopy__(self, _memo: object) -> None:
        raise TypeError("TechIndicatorsWriterLock cannot be copied.")

    def __enter__(self) -> TechIndicatorsWriterLock:
        self._require_held()
        return self

    def __exit__(
        self,
        _error_type: object,
        _error: object,
        _traceback: object,
    ) -> bool:
        if self._state is _WriterLockState.HELD:
            self._rollback_and_close(suppress_errors=True)
        return False

    @property
    def outcome(self) -> WriterLockOutcome:
        if self._state is _WriterLockState.LOST:
            return WriterLockOutcome.LOST
        return WriterLockOutcome.ACQUIRED

    @property
    def is_held(self) -> bool:
        return self._state is _WriterLockState.HELD

    @property
    def heartbeat_count(self) -> int:
        return self._heartbeat_count

    @property
    def heartbeat_failure_count(self) -> int:
        return self._heartbeat_failure_count

    def heartbeat(self) -> int:
        """Prove the dedicated transaction remains usable without reacquiring."""

        self._require_held()
        try:
            self._cursor.execute(_HEARTBEAT_SQL)
            row = self._cursor.fetchone()
            if row != (1,):
                raise RuntimeError("invalid heartbeat result")
        except BaseException as exc:
            self._mark_lost()
            if not isinstance(exc, Exception):
                raise
            raise TechIndicatorsWriterLockLostError(
                TECH_INDICATORS_LOCK_LOST_MESSAGE
            ) from None
        self._heartbeat_count += 1
        return self._heartbeat_count

    def report_facts(self) -> ReportLock:
        """Return R8.1 facts while the report is still protected by this lock."""

        if self._state not in {_WriterLockState.HELD, _WriterLockState.LOST}:
            raise RuntimeError("writer lock is already released.")
        from empire_stonks_tech_indicators.reports import LockOutcome, ReportLock

        return ReportLock(
            outcome=(
                LockOutcome.LOST
                if self._state is _WriterLockState.LOST
                else LockOutcome.ACQUIRED
            ),
            heartbeat_count=self._heartbeat_count,
            heartbeat_failure_count=self._heartbeat_failure_count,
        )

    def commit_terminal(
        self,
        operation: Callable[[Any], _ResultT],
    ) -> _ResultT:
        """Run terminal publication on the lock cursor, commit, and close."""

        self._require_held()
        if not callable(operation):
            raise TypeError("operation must be callable.")
        try:
            result = operation(self._cursor)
        except BaseException:
            self._rollback_and_close(suppress_errors=True)
            raise
        try:
            self._connection.commit()
        except BaseException as exc:
            self._mark_lost()
            if not isinstance(exc, Exception):
                raise
            raise TechIndicatorsWriterLockLostError(
                TECH_INDICATORS_LOCK_LOST_MESSAGE
            ) from None
        self._state = _WriterLockState.COMMITTED
        self._close_resources()
        return result

    def commit(self) -> None:
        """Release a healthy no-op lock transaction by committing it."""

        self.commit_terminal(lambda _cursor: None)

    def rollback(self) -> None:
        """Release a dry-run, failure, or cancellation lock transaction."""

        self._require_held()
        try:
            self._connection.rollback()
        except BaseException as exc:
            self._state = _WriterLockState.LOST
            self._heartbeat_failure_count = 1
            self._close_resources()
            if not isinstance(exc, Exception):
                raise
            raise TechIndicatorsWriterLockLostError(
                TECH_INDICATORS_LOCK_LOST_MESSAGE
            ) from None
        self._state = _WriterLockState.ROLLED_BACK
        self._close_resources()

    def _require_held(self) -> None:
        if self._state is _WriterLockState.LOST:
            raise TechIndicatorsWriterLockLostError(
                TECH_INDICATORS_LOCK_LOST_MESSAGE
            )
        if self._state is not _WriterLockState.HELD:
            raise RuntimeError("writer lock is already released.")

    def _mark_lost(self) -> None:
        self._state = _WriterLockState.LOST
        self._heartbeat_failure_count = 1
        self._rollback_and_close(suppress_errors=True, retain_lost=True)

    def _rollback_and_close(
        self,
        *,
        suppress_errors: bool,
        retain_lost: bool = False,
    ) -> None:
        rollback_error: BaseException | None = None
        try:
            self._connection.rollback()
        except BaseException as exc:
            rollback_error = exc
        if not retain_lost:
            self._state = _WriterLockState.ROLLED_BACK
        self._close_resources()
        if rollback_error is not None and not suppress_errors:
            raise rollback_error

    def _close_resources(self) -> None:
        try:
            self._cursor.close()
        except BaseException:
            pass
        try:
            self._connection.close()
        except BaseException:
            pass


def acquire_tech_indicators_writer_lock(
    *,
    connection_factory: Callable[[], Any],
) -> WriterLockAcquisition:
    """Attempt the one global nonblocking lock before creating workflow state."""

    if not callable(connection_factory):
        raise TypeError("connection_factory must be callable.")
    connection: Any | None = None
    cursor: Any | None = None
    try:
        connection = connection_factory()
        _validate_connection(connection)
        cursor = connection.cursor()
        _validate_cursor(cursor)
        cursor.execute(_BEGIN_SQL)
        cursor.execute(
            _ACQUIRE_SQL,
            (TECH_INDICATORS_WRITER_LOCK_KEY,),
        )
        row = cursor.fetchone()
        if row not in {(True,), (False,)}:
            raise RuntimeError("invalid advisory-lock result")
        if row == (False,):
            _release_unacquired(connection=connection, cursor=cursor)
            return WriterLockAcquisition(
                outcome=WriterLockOutcome.CONTENDED,
                lock=None,
                message=TECH_INDICATORS_LOCK_CONTENDED_MESSAGE,
            )
        return WriterLockAcquisition(
            outcome=WriterLockOutcome.ACQUIRED,
            lock=TechIndicatorsWriterLock(
                connection=connection,
                cursor=cursor,
            ),
            message=None,
        )
    except BaseException as exc:
        _release_unacquired(connection=connection, cursor=cursor)
        if not isinstance(exc, Exception):
            raise
        raise TechIndicatorsWorkflowError(
            TECH_INDICATORS_LOCK_FAILURE_MESSAGE
        ) from None


def _validate_connection(connection: object) -> None:
    for method_name in ("cursor", "commit", "rollback", "close"):
        if not callable(getattr(connection, method_name, None)):
            raise TypeError(
                f"writer-lock connection must provide {method_name}()."
            )


def _validate_cursor(cursor: object) -> None:
    for method_name in ("execute", "fetchone", "close"):
        if not callable(getattr(cursor, method_name, None)):
            raise TypeError(f"writer-lock cursor must provide {method_name}().")


def _release_unacquired(*, connection: Any | None, cursor: Any | None) -> None:
    if connection is not None:
        try:
            connection.rollback()
        except BaseException:
            pass
    if cursor is not None:
        try:
            cursor.close()
        except BaseException:
            pass
    if connection is not None:
        try:
            connection.close()
        except BaseException:
            pass


__all__ = [
    "TECH_INDICATORS_LOCK_CONTENDED_MESSAGE",
    "TECH_INDICATORS_LOCK_FAILURE_MESSAGE",
    "TECH_INDICATORS_LOCK_LOST_MESSAGE",
    "TECH_INDICATORS_TEMPORARY_FAILURE_EXIT_CODE",
    "TechIndicatorsWriterLock",
    "WriterLockAcquisition",
    "WriterLockOutcome",
    "acquire_tech_indicators_writer_lock",
]
