from __future__ import annotations

import hashlib
import io
import json
import os
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

import empire_stonks_ohlcv.stooq_history_writer as stooq_writer
from empire_core import EmpireDatabase, ObjectStore, RunService
from empire_stonks_ohlcv import (
    OHLCVConfig,
    StooqHistoryScope,
    run_stooq_history_backfill,
)


DATABASE_ENVIRONMENT = (
    "EMPIRE_DB_HOST",
    "EMPIRE_DB_NAME",
    "EMPIRE_DB_USER",
    "EMPIRE_DB_PASSWORD",
)
FIXTURE_ROOT = (
    Path(__file__).parent / "fixtures" / "stooq" / "stooq_history"
)
EFFECTIVE_DATE = date(2026, 7, 18)
START_DATE = date(2026, 1, 2)
END_DATE = date(2026, 1, 6)
CHUNK_SIZE = 2
MARKETS = ("nasdaq", "nyse", "nysemkt")
FIXTURE_MEMBERS = (
    ("nasdaq", "AAA.US", "nasdaq_stocks_valid.txt"),
    ("nyse", "BBB.US", "nyse_stocks_valid.txt"),
    ("nysemkt", "CCC.US", "nysemkt_stocks_valid.txt"),
)


@pytest.fixture
def database_connection() -> Iterator[Any]:
    if any(not os.environ.get(name) for name in DATABASE_ENVIRONMENT):
        pytest.skip("Empire database environment is not configured.")

    connection = EmpireDatabase.connect_from_env()
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


class CommitCountingConnection:
    """Delegate a real connection while observing runner-owned boundaries."""

    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self.commit_calls = 0
        self.rollback_calls = 0

    def cursor(self) -> Any:
        return self.connection.cursor()

    def commit(self) -> None:
        self.commit_calls += 1
        self.connection.commit()

    def rollback(self) -> None:
        self.rollback_calls += 1
        self.connection.rollback()


def _archive(tmp_path: Path, marker: str) -> tuple[Path, tuple[str, ...]]:
    output = io.BytesIO()
    tickers: list[str] = []
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for market, fixture_ticker, fixture_name in FIXTURE_MEMBERS:
            ticker = f"H77{fixture_ticker[0]}{marker}.US"
            tickers.append(ticker)
            payload = (FIXTURE_ROOT / fixture_name).read_text(encoding="utf-8")
            payload = payload.replace(fixture_ticker, ticker)
            archive.writestr(
                f"data/daily/us/{market} stocks/{ticker.lower()}.txt",
                payload,
            )
    path = tmp_path / "d_us_txt.zip"
    path.write_bytes(output.getvalue())
    return path, tuple(tickers)


def _series_rows(
    connection: Any,
    tickers: tuple[str, ...],
) -> tuple[tuple[Any, ...], ...]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                listing.market,
                listing.ticker,
                listing.provider_listing_id,
                count(daily.trading_date),
                min(daily.trading_date),
                max(daily.trading_date)
            FROM stonks.provider_listing AS listing
            LEFT JOIN stonks.ohlcv_daily AS daily
              USING (provider_listing_id)
            WHERE listing.provider_code = 'STOOQ'
              AND listing.ticker = ANY(%s)
            GROUP BY
                listing.provider_listing_id,
                listing.market,
                listing.ticker
            ORDER BY listing.market, listing.ticker
            """,
            (list(tickers),),
        )
        return tuple(cursor.fetchall())


def _cleanup(
    *,
    connection: Any,
    object_store: ObjectStore,
    runner: str,
    tickers: tuple[str, ...],
    checksum: str,
) -> None:
    connection.rollback()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT run_id FROM core.core_run WHERE runner = %s",
            (runner,),
        )
        run_ids = tuple(row[0] for row in cursor.fetchall())
    for run_id in run_ids:
        object_store.delete_objects_by_run_id(run_id)
        object_store.purge_deleted_objects_by_run_id(
            run_id,
            ignore_purge_after=True,
        )
    with connection.cursor() as cursor:
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
        cursor.execute(
            """
            DELETE FROM stonks.provider_source_snapshot
            WHERE provider_code = 'STOOQ'
              AND source_code = 'stooq_history'
              AND content_sha256 = %s
            """,
            (checksum,),
        )
        cursor.execute(
            "DELETE FROM core.core_run WHERE runner = %s",
            (runner,),
        )
    connection.commit()


def test_stooq_history_fixture_vertical_is_stable_and_bounded(
    database_connection: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    connection = database_connection
    marker = uuid4().hex[:10].upper()
    runner = f"pytest:h77:{marker}"
    input_path, tickers = _archive(tmp_path, marker)
    checksum = hashlib.sha256(input_path.read_bytes()).hexdigest()
    object_store = ObjectStore.from_connection(connection)
    run_service = RunService.from_connection(connection)
    observed_connection = CommitCountingConnection(connection)
    config = OHLCVConfig(
        storage_key=f"stonks/ohlcv/h77/{marker.lower()}",
        raw_retention_days=3,
    )
    scope = StooqHistoryScope(
        effective_date=EFFECTIVE_DATE,
        start_date=START_DATE,
        end_date=END_DATE,
        markets=MARKETS,
        tickers=tickers,
    )
    bar_batch_sizes: list[int] = []
    original_bar_writer = stooq_writer.upsert_daily_bars

    def observe_bar_batch(**values: object):
        bars = tuple(values["bars"])  # type: ignore[arg-type]
        bar_batch_sizes.append(len(bars))
        return original_bar_writer(cursor=values["cursor"], bars=bars)

    monkeypatch.setattr(stooq_writer, "upsert_daily_bars", observe_bar_batch)

    try:
        first = run_stooq_history_backfill(
            run_service=run_service,
            connection=observed_connection,
            object_store=object_store,
            config=config,
            input_path=input_path,
            scope=scope,
            chunk_size=CHUNK_SIZE,
            run_type="manual",
            runner=runner,
        )
        first_rows = _series_rows(connection, tickers)
        first_commit_calls = observed_connection.commit_calls

        second = run_stooq_history_backfill(
            run_service=run_service,
            connection=observed_connection,
            object_store=object_store,
            config=config,
            input_path=input_path,
            scope=scope,
            chunk_size=CHUNK_SIZE,
            run_type="manual",
            runner=runner,
        )
        second_rows = _series_rows(connection, tickers)

        assert first.status == second.status == "succeeded"
        assert first.run_id != second.run_id
        assert first.acquired_object.object_id != second.acquired_object.object_id
        assert first.report_object_id != second.report_object_id
        assert first.source_snapshot.source_snapshot_id == (
            second.source_snapshot.source_snapshot_id
        )
        assert first.source_snapshot.snapshot_inserted is True
        assert second.source_snapshot.snapshot_inserted is False
        assert first.source_snapshot.object_link_inserted is True
        assert second.source_snapshot.object_link_inserted is True
        assert first.acquired_object.checksum_sha256 == checksum
        assert second.acquired_object.checksum_sha256 == checksum

        assert first.parse_summary.files_completed == 3
        assert first.parse_summary.input_rows == 8
        assert first.parse_summary.date_filtered_rows == 2
        assert first.parse_summary.accepted_records == 6
        assert first.write_summary.chunks_completed == 3
        assert first.write_summary.listing_counts.inserted == 3
        assert first.write_summary.bar_counts.inserted == 6
        assert first.write_summary.bar_counts.unchanged == 0

        assert second.parse_summary.to_dict() == first.parse_summary.to_dict()
        assert second.write_summary.chunks_completed == 3
        assert second.write_summary.listing_counts.inserted == 0
        assert second.write_summary.listing_counts.updated == 0
        assert second.write_summary.listing_counts.unchanged == 3
        assert second.write_summary.bar_counts.inserted == 0
        assert second.write_summary.bar_counts.updated == 0
        assert second.write_summary.bar_counts.derived_updated == 0
        assert second.write_summary.bar_counts.unchanged == 6

        assert len(first_rows) == 3
        assert second_rows == first_rows
        first_ids = tuple(row[2] for row in first_rows)
        assert len(set(first_ids)) == 3
        assert [row[0] for row in first_rows] == list(MARKETS)
        assert [(row[3], row[4], row[5]) for row in first_rows] == [
            (2, date(2026, 1, 2), date(2026, 1, 5)),
            (2, date(2026, 1, 2), date(2026, 1, 6)),
            (2, date(2026, 1, 5), date(2026, 1, 6)),
        ]

        assert bar_batch_sizes == [CHUNK_SIZE] * 6
        assert first_commit_calls == 4
        assert observed_connection.commit_calls == 8
        assert observed_connection.rollback_calls == 0

        for result, expected_counts in (
            (first, (3, 6, 0)),
            (second, (0, 0, 6)),
        ):
            objects = object_store.find_objects_by_run_id(result.run_id)
            assert len(objects) == 2
            assert {item.object_kind for item in objects} == {
                "stonks_ohlcv_raw_source",
                "stonks_ohlcv_provider_report",
            }
            report = json.loads(object_store.get_bytes(result.report_object_id))
            inserted_listings, inserted_bars, unchanged_bars = expected_counts
            assert report["run_status"] == "complete"
            assert report["outcome"] == "PASS"
            assert report["input"]["scope"] == scope.to_dict()
            assert report["input"]["chunk_size"] == CHUNK_SIZE
            assert report["progress"]["write"]["listing_counts"][
                "inserted"
            ] == inserted_listings
            assert report["progress"]["write"]["bar_counts"][
                "inserted"
            ] == inserted_bars
            assert report["progress"]["write"]["bar_counts"][
                "unchanged"
            ] == unchanged_bars
            assert report["coverage"]["series_count"] == 3
            market_coverage = report["coverage"]["markets"]
            assert sum(
                item["persisted_bar_count"] for item in market_coverage
            ) == 6
            assert sum(
                item["scoped_bar_count"] for item in market_coverage
            ) == 6
            assert [
                (
                    item["first_scoped_trading_date"],
                    item["last_scoped_trading_date"],
                )
                for item in market_coverage
            ] == [
                ("2026-01-02", "2026-01-05"),
                ("2026-01-02", "2026-01-06"),
                ("2026-01-05", "2026-01-06"),
            ]

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM core.core_run WHERE runner = %s",
                (runner,),
            )
            assert cursor.fetchone()[0] == 2
            cursor.execute(
                """
                SELECT count(*), count(DISTINCT source_snapshot_id)
                FROM stonks.provider_source_snapshot_object
                WHERE object_id = ANY(%s)
                """,
                (
                    [
                        first.acquired_object.object_id,
                        second.acquired_object.object_id,
                    ],
                ),
            )
            assert cursor.fetchone() == (2, 1)
    finally:
        _cleanup(
            connection=connection,
            object_store=object_store,
            runner=runner,
            tickers=tickers,
            checksum=checksum,
        )
