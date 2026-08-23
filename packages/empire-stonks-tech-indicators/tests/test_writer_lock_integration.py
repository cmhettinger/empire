from __future__ import annotations

import os

import pytest

from empire_stonks_tech_indicators import (
    TechIndicatorsWriterLockLostError,
    WriterLockOutcome,
    acquire_tech_indicators_writer_lock,
)
from empire_stonks_tech_indicators import publication as publication_module


EmpireDatabase = pytest.importorskip(
    "empire_core.db.connection",
    reason="Empire Core database runtime is not installed.",
).EmpireDatabase


DATABASE_ENVIRONMENT = (
    "EMPIRE_DB_HOST",
    "EMPIRE_DB_NAME",
    "EMPIRE_DB_USER",
    "EMPIRE_DB_PASSWORD",
)


def _require_database() -> None:
    if any(not os.environ.get(name) for name in DATABASE_ENVIRONMENT):
        pytest.skip("Empire database environment is not configured.")


def _counts(connection: object) -> tuple[int, int, int]:
    with connection.cursor() as cursor:  # type: ignore[union-attr]
        cursor.execute(
            """
            SELECT
                (SELECT count(*) FROM core.core_run),
                (SELECT count(*) FROM core.stored_object),
                (
                    SELECT count(*)
                    FROM stonks.tech_indicators_publication
                )
            """
        )
        return cursor.fetchone()  # type: ignore[no-any-return]


def test_global_lock_contends_without_state_and_survives_other_commits() -> None:
    _require_database()
    owner_connection = EmpireDatabase.connect_from_env()
    observer = EmpireDatabase.connect_from_env()
    work = EmpireDatabase.connect_from_env()
    contender_connections: list[object] = []
    try:
        before = _counts(observer)
        observer.rollback()
        owner_result = acquire_tech_indicators_writer_lock(
            connection_factory=lambda: owner_connection
        )
        assert owner_result.lock is not None
        owner = owner_result.lock

        with work.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM stonks.provider_listing")
            assert cursor.fetchone()[0] >= 0
        work.commit()

        first_contender = EmpireDatabase.connect_from_env()
        contender_connections.append(first_contender)
        contended = acquire_tech_indicators_writer_lock(
            connection_factory=lambda: first_contender
        )
        assert contended.outcome is WriterLockOutcome.CONTENDED
        assert contended.lock is None
        assert first_contender.closed

        assert owner.heartbeat() == 1
        after_contention = _counts(observer)
        observer.rollback()
        assert after_contention == before

        second_contender = EmpireDatabase.connect_from_env()
        contender_connections.append(second_contender)
        still_contended = acquire_tech_indicators_writer_lock(
            connection_factory=lambda: second_contender
        )
        assert still_contended.outcome is WriterLockOutcome.CONTENDED

        owner.rollback()
        replacement_connection = EmpireDatabase.connect_from_env()
        contender_connections.append(replacement_connection)
        replacement_result = acquire_tech_indicators_writer_lock(
            connection_factory=lambda: replacement_connection
        )
        assert replacement_result.outcome is WriterLockOutcome.ACQUIRED
        assert replacement_result.lock is not None
        replacement_result.lock.rollback()
    finally:
        for connection in (observer, work, *contender_connections):
            try:
                if not connection.closed:  # type: ignore[union-attr]
                    connection.rollback()  # type: ignore[union-attr]
            finally:
                if not connection.closed:  # type: ignore[union-attr]
                    connection.close()  # type: ignore[union-attr]
        if not owner_connection.closed:
            owner_connection.rollback()
            owner_connection.close()


def test_terminal_callback_owns_publication_lock_and_commit_releases_it() -> None:
    _require_database()
    owner_connection = EmpireDatabase.connect_from_env()
    replacement_connection = None
    try:
        result = acquire_tech_indicators_writer_lock(
            connection_factory=lambda: owner_connection
        )
        assert result.lock is not None

        terminal_result = result.lock.commit_terminal(
            lambda cursor: (
                publication_module._require_writer_lock(cursor),
                "terminal-ready",
            )[1]
        )

        assert terminal_result == "terminal-ready"
        assert owner_connection.closed
        replacement_connection = EmpireDatabase.connect_from_env()
        replacement = acquire_tech_indicators_writer_lock(
            connection_factory=lambda: replacement_connection
        )
        assert replacement.lock is not None
        replacement.lock.rollback()
    finally:
        for connection in (owner_connection, replacement_connection):
            if connection is not None and not connection.closed:
                connection.rollback()
                connection.close()


def test_connection_loss_fails_closed_and_fresh_run_can_reacquire() -> None:
    _require_database()
    owner_connection = EmpireDatabase.connect_from_env()
    replacement_connection = None
    try:
        result = acquire_tech_indicators_writer_lock(
            connection_factory=lambda: owner_connection
        )
        assert result.lock is not None
        owner_connection.close()

        with pytest.raises(TechIndicatorsWriterLockLostError):
            result.lock.heartbeat()
        assert result.lock.outcome is WriterLockOutcome.LOST

        replacement_connection = EmpireDatabase.connect_from_env()
        replacement = acquire_tech_indicators_writer_lock(
            connection_factory=lambda: replacement_connection
        )
        assert replacement.lock is not None
        replacement.lock.rollback()
    finally:
        for connection in (owner_connection, replacement_connection):
            if connection is not None and not connection.closed:
                connection.rollback()
                connection.close()
