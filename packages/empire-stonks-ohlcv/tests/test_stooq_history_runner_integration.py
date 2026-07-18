from __future__ import annotations

import io
import json
import os
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from uuid import UUID, uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

import empire_stonks_ohlcv.stooq_history_writer as stooq_writer
from empire_core import EmpireDatabase, ObjectStore, RunService
from empire_stonks_ohlcv import (
    OHLCVConfig,
    OHLCVWorkflowError,
    StooqHistoryScope,
    run_stooq_history_backfill,
)


DATABASE_ENVIRONMENT = (
    "EMPIRE_DB_HOST",
    "EMPIRE_DB_NAME",
    "EMPIRE_DB_USER",
    "EMPIRE_DB_PASSWORD",
)
EFFECTIVE_DATE = date(2026, 7, 18)
HEADER = (
    "<TICKER>,<PER>,<DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,"
    "<VOL>,<OPENINT>\n"
)


@pytest.fixture
def database_connection() -> Iterator[object]:
    if any(not os.environ.get(name) for name in DATABASE_ENVIRONMENT):
        pytest.skip("Empire database environment is not configured.")

    connection = EmpireDatabase.connect_from_env()
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


def _archive(tmp_path: Path, marker: str) -> tuple[Path, tuple[str, ...]]:
    tickers = tuple(f"H74{market[0].upper()}{marker}.US" for market in (
        "nasdaq",
        "nyse",
        "nysemkt",
    ))
    output = io.BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for index, (market, ticker) in enumerate(
            zip(("nasdaq", "nyse", "nysemkt"), tickers, strict=True),
            start=1,
        ):
            archive.writestr(
                f"data/daily/us/{market} stocks/{ticker.lower()}.txt",
                HEADER
                + (
                    f"{ticker},D,2026010{index + 1},000000,"
                    f"{index}0,{index}1,{index}0,{index}0.5,100,0\n"
                ),
            )
    path = tmp_path / "d_us_txt.zip"
    path.write_bytes(output.getvalue())
    return path, tickers


def _cleanup(
    *,
    connection: object,
    object_store: ObjectStore,
    run_id: UUID | None,
    runner: str,
    tickers: tuple[str, ...],
    checksum: str | None,
) -> None:
    connection.rollback()  # type: ignore[union-attr]
    if run_id is None:
        with connection.cursor() as cursor:  # type: ignore[union-attr]
            cursor.execute(
                "SELECT run_id FROM core.core_run WHERE runner = %s",
                (runner,),
            )
            row = cursor.fetchone()
            run_id = row[0] if row is not None else None
    if run_id is not None and checksum is None:
        with connection.cursor() as cursor:  # type: ignore[union-attr]
            cursor.execute(
                """
                SELECT checksum_sha256
                FROM core.stored_object
                WHERE run_id = %s
                  AND object_kind = 'stonks_ohlcv_raw_source'
                """,
                (run_id,),
            )
            row = cursor.fetchone()
            checksum = row[0] if row is not None else None
    if run_id is not None:
        object_store.delete_objects_by_run_id(run_id)
        object_store.purge_deleted_objects_by_run_id(
            run_id,
            ignore_purge_after=True,
        )
    with connection.cursor() as cursor:  # type: ignore[union-attr]
        cursor.execute(
            """
            DELETE FROM stonks.ohlcv_daily
            WHERE provider_listing_id IN (
                SELECT provider_listing_id
                FROM stonks.provider_listing
                WHERE provider_code = 'STOOQ'
                  AND ticker = ANY(%s)
            )
            """,
            (list(tickers),),
        )
        cursor.execute(
            """
            DELETE FROM stonks.provider_listing
            WHERE provider_code = 'STOOQ'
              AND ticker = ANY(%s)
            """,
            (list(tickers),),
        )
        if checksum is not None:
            cursor.execute(
                """
                DELETE FROM stonks.provider_source_snapshot
                WHERE provider_code = 'STOOQ'
                  AND source_code = 'stooq_history'
                  AND content_sha256 = %s
                """,
                (checksum,),
            )
        if run_id is not None:
            cursor.execute("DELETE FROM core.core_run WHERE run_id = %s", (run_id,))
    connection.commit()  # type: ignore[union-attr]


def test_tracked_backfill_persists_core_lineage_and_safe_summary(
    database_connection: object,
    tmp_path: Path,
) -> None:
    connection = database_connection
    marker = uuid4().hex[:8].upper()
    runner = f"pytest:h74:{marker}"
    input_path, tickers = _archive(tmp_path, marker)
    object_store = ObjectStore.from_connection(connection)
    run_id: UUID | None = None
    checksum: str | None = None

    try:
        result = run_stooq_history_backfill(
            run_service=RunService.from_connection(connection),
            connection=connection,
            object_store=object_store,
            config=OHLCVConfig(
                storage_key=f"stonks/ohlcv/h74/{marker.lower()}",
                raw_retention_days=3,
            ),
            input_path=input_path,
            scope=StooqHistoryScope(effective_date=EFFECTIVE_DATE),
            chunk_size=2,
            run_type="manual",
            runner=runner,
        )
        run_id = result.run_id
        checksum = result.acquired_object.checksum_sha256

        assert input_path.is_file()
        assert result.status == "succeeded"
        assert result.parse_summary.files_completed == 3
        assert result.write_summary.chunks_completed == 2
        assert result.write_summary.bar_counts.inserted == 3
        assert result.report_outcome == "PASS"
        assert object_store.get_path(result.acquired_object.object_id).is_file()
        report = json.loads(object_store.get_bytes(result.report_object_id))
        assert report["run_status"] == "complete"
        assert report["coverage"]["series_count"] == 3
        assert report["warnings"]["total_count"] == 0
        assert report["native_value_semantics"]["currency"] == "unspecified"

        with connection.cursor() as cursor:  # type: ignore[union-attr]
            cursor.execute(
                """
                SELECT status, subject_key, params, summary, error_message,
                       last_heartbeat_at IS NOT NULL
                FROM core.core_run
                WHERE run_id = %s
                """,
                (run_id,),
            )
            status, subject_key, params, summary, error, heartbeat = cursor.fetchone()
            assert status == "succeeded"
            assert subject_key == "us_stocks"
            assert params["scope"] == result.scope.to_dict()
            assert params["chunk_size"] == 2
            assert "input_path" not in params
            assert summary["acquired_object"]["checksum_sha256"] == checksum
            assert summary["write_summary"]["last_completed_chunk"] == 2
            assert summary["report_object_id"] == str(result.report_object_id)
            assert summary["report_outcome"] == "PASS"
            assert error is None
            assert heartbeat is True

            cursor.execute(
                """
                SELECT count(*)
                FROM stonks.provider_source_snapshot_object
                WHERE object_id = %s
                  AND source_snapshot_id = %s
                """,
                (
                    result.acquired_object.object_id,
                    result.source_snapshot.source_snapshot_id,
                ),
            )
            assert cursor.fetchone()[0] == 1
            cursor.execute(
                """
                SELECT count(*)
                FROM stonks.ohlcv_daily AS bar
                JOIN stonks.provider_listing AS listing
                  USING (provider_listing_id)
                WHERE listing.provider_code = 'STOOQ'
                  AND listing.ticker = ANY(%s)
                """,
                (list(tickers),),
            )
            assert cursor.fetchone()[0] == 3
    finally:
        _cleanup(
            connection=connection,
            object_store=object_store,
            run_id=run_id,
            runner=runner,
            tickers=tickers,
            checksum=checksum,
        )


def test_failed_chunk_stores_partial_report_with_durable_progress(
    database_connection: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = database_connection
    marker = uuid4().hex[:8].upper()
    runner = f"pytest:h75-partial:{marker}"
    input_path, tickers = _archive(tmp_path, marker)
    object_store = ObjectStore.from_connection(connection)
    run_id: UUID | None = None
    checksum: str | None = None
    original_bar_writer = stooq_writer.upsert_daily_bars
    bar_calls = 0

    def fail_second_chunk(**values: object):
        nonlocal bar_calls
        bar_calls += 1
        if bar_calls == 2:
            raise RuntimeError("forced partial report integration failure")
        return original_bar_writer(**values)

    monkeypatch.setattr(stooq_writer, "upsert_daily_bars", fail_second_chunk)
    try:
        with pytest.raises(OHLCVWorkflowError):
            run_stooq_history_backfill(
                run_service=RunService.from_connection(connection),
                connection=connection,
                object_store=object_store,
                config=OHLCVConfig(
                    storage_key=f"stonks/ohlcv/h75/{marker.lower()}",
                    raw_retention_days=3,
                ),
                input_path=input_path,
                scope=StooqHistoryScope(effective_date=EFFECTIVE_DATE),
                chunk_size=2,
                run_type="manual",
                runner=runner,
            )

        with connection.cursor() as cursor:  # type: ignore[union-attr]
            cursor.execute(
                """
                SELECT run_id, status, summary, error_message
                FROM core.core_run
                WHERE runner = %s
                """,
                (runner,),
            )
            run_id, status, summary, error_message = cursor.fetchone()
        assert status == "failed"
        assert summary["failed_stage"] == "persistence"
        assert summary["write_summary"]["last_completed_chunk"] == 1
        assert summary["report_outcome"] == "FAIL"
        assert error_message == "OHLCV provider run failed."

        report_id = UUID(summary["report_object_id"])
        report = json.loads(object_store.get_bytes(report_id))
        checksum = report["input"]["archive"]["checksum_sha256"]
        assert report["run_status"] == "partial"
        assert report["outcome"] == "FAIL"
        assert report["hard_failures"]["failed_stage"] == "persistence"
        assert report["progress"]["write"]["chunks_completed"] == 1
        assert report["progress"]["write"]["chunks_failed"] == 1
        assert report["coverage"]["series_count"] == 2
        assert "forced partial report" not in repr(report)
    finally:
        _cleanup(
            connection=connection,
            object_store=object_store,
            run_id=run_id,
            runner=runner,
            tickers=tickers,
            checksum=checksum,
        )
