from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, date, datetime
from typing import Iterator
from urllib.parse import unquote
from uuid import UUID, uuid4

import pytest

from empire_core import EmpireDatabase, ObjectStore, RunService
from empire_stonks_ohlcv import (
    OHLCVConfig,
    YahooDailyScope,
    YahooHTTPResponse,
    run_yahoo_daily,
)


DATABASE_ENVIRONMENT = (
    "EMPIRE_DB_HOST",
    "EMPIRE_DB_NAME",
    "EMPIRE_DB_USER",
    "EMPIRE_DB_PASSWORD",
)
POLICY_CODE = "YH_XNYS_CLOSE_90M"
START_DATE = date(2026, 7, 1)
END_DATE = date(2026, 7, 2)


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


def _payload(
    *,
    yahoo_ticker: str,
    first_close: float,
) -> bytes:
    return json.dumps(
        {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "symbol": yahoo_ticker,
                            "exchangeName": "SNP",
                            "exchangeTimezoneName": "America/New_York",
                        },
                        "timestamp": [1782912600, 1782999000],
                        "indicators": {
                            "quote": [
                                {
                                    "open": [10, 11],
                                    "high": [13, 14],
                                    "low": [9, 10],
                                    "close": [first_close, 13],
                                    "volume": [None, 200],
                                }
                            ],
                            "adjclose": [
                                {"adjclose": [first_close - 0.1, 12.9]}
                            ],
                        },
                    }
                ],
                "error": None,
            }
        },
        separators=(",", ":"),
    ).encode()


def _cleanup(
    *,
    connection: object,
    object_store: ObjectStore,
    runner: str,
    tickers: tuple[str, ...],
    checksums: set[str],
) -> None:
    connection.rollback()  # type: ignore[union-attr]
    with connection.cursor() as cursor:  # type: ignore[union-attr]
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
    with connection.cursor() as cursor:  # type: ignore[union-attr]
        cursor.execute(
            """
            DELETE FROM stonks.provider_listing
            WHERE provider_code = 'YAHOO'
              AND ticker = ANY(%s)
            """,
            (list(tickers),),
        )
        if checksums:
            cursor.execute(
                """
                DELETE FROM stonks.provider_source_snapshot
                WHERE provider_code = 'YAHOO'
                  AND source_code = 'yahoo_daily'
                  AND content_sha256 = ANY(%s)
                """,
                (list(checksums),),
            )
        cursor.execute(
            "DELETE FROM core.core_run WHERE runner = %s",
            (runner,),
        )
    connection.commit()  # type: ignore[union-attr]


def test_daily_runner_partial_retry_rerun_correction_and_noop(
    database_connection: object,
) -> None:
    connection = database_connection
    object_store = ObjectStore.from_connection(connection)
    marker = uuid4().hex[:8].upper()
    tickers = (f"Y813A{marker}", f"Y813B{marker}")
    yahoo_tickers = {ticker: f"^{ticker}" for ticker in tickers}
    runner = f"pytest:y813:{marker}"
    first_closes = {
        yahoo_tickers[tickers[0]]: 11.0,
        yahoo_tickers[tickers[1]]: 12.0,
    }
    failing = {yahoo_tickers[tickers[1]]}
    checksums: set[str] = set()
    transport_calls: list[str] = []
    listing_ids: dict[str, UUID] = {}

    try:
        with connection.cursor() as cursor:  # type: ignore[union-attr]
            for ticker in tickers:
                cursor.execute(
                    """
                    INSERT INTO stonks.provider_listing (
                        provider_code,
                        market,
                        ticker,
                        name,
                        instrument_type_code,
                        status,
                        metadata,
                        session_policy_code
                    )
                    VALUES (
                        'YAHOO', 'XIDX', %s, %s, 'EQUITY_INDEX', 'ACTIVE',
                        %s::jsonb, %s
                    )
                    RETURNING provider_listing_id
                    """,
                    (
                        ticker,
                        f"{ticker} Daily Runner Test",
                        json.dumps({"YahooTicker": yahoo_tickers[ticker]}),
                        POLICY_CODE,
                    ),
                )
                listing_ids[ticker] = cursor.fetchone()[0]
        connection.commit()  # type: ignore[union-attr]

        def transport(**values: object) -> YahooHTTPResponse:
            url = values["url"]
            assert isinstance(url, str)
            yahoo_ticker = unquote(url.rsplit("/", 1)[-1])
            transport_calls.append(yahoo_ticker)
            if yahoo_ticker in failing:
                return YahooHTTPResponse(
                    status_code=503,
                    body=b"temporary provider failure",
                    headers={"content-type": "text/plain"},
                )
            body = _payload(
                yahoo_ticker=yahoo_ticker,
                first_close=first_closes[yahoo_ticker],
            )
            checksums.add(hashlib.sha256(body).hexdigest())
            return YahooHTTPResponse(
                status_code=200,
                body=body,
                headers={"content-type": "application/json"},
            )

        config = OHLCVConfig(
            storage_key=f"stonks/ohlcv/y813/{marker.lower()}",
            max_retries=0,
            yahoo_request_delay_seconds=0,
            yahoo_request_jitter_min_seconds=0,
            yahoo_request_jitter_max_seconds=0,
            yahoo_failure_cooldown_min_seconds=0,
            yahoo_failure_cooldown_max_seconds=0,
            yahoo_daily_request_max_days=10,
            yahoo_reconciliation_sessions=2,
        )

        def run(
            *,
            selected_tickers: tuple[str, ...] = tickers,
            start_date: date = START_DATE,
            end_date: date = END_DATE,
            now: datetime = datetime(2026, 7, 3, 12, tzinfo=UTC),
        ):
            return run_yahoo_daily(
                run_service=RunService.from_connection(connection),
                connection=connection,
                object_store=object_store,
                config=config,
                scope=YahooDailyScope(
                    effective_date=end_date,
                    start_date=start_date,
                    end_date=end_date,
                    tickers=selected_tickers,
                ),
                run_type="manual",
                runner=runner,
                transport=transport,
                sleep=lambda _: None,
                random_uniform=lambda minimum, _maximum: minimum,
                clock=lambda: now,
            )

        partial = run()
        assert partial.status == "succeeded"
        assert partial.ingestion.acquisition.failed_count == 1
        assert partial.reconciliation.acquisition.failed_count == 1
        assert partial.bar_counts.inserted == 2
        assert partial.bar_counts.unchanged == 0
        assert partial.report_outcome == "WARN"

        failing.clear()
        retry = run(selected_tickers=(tickers[1],))
        assert retry.ingestion.import_result.bar_counts.inserted == 2
        assert not retry.reconciliation.acquisition.outcomes
        assert retry.report_outcome == "PASS"

        rerun = run()
        assert not rerun.ingestion.acquisition.outcomes
        assert rerun.reconciliation.import_result.bar_counts.unchanged == 4
        assert rerun.report_outcome == "PASS"

        first_closes[yahoo_tickers[tickers[0]]] = 11.5
        corrected = run(selected_tickers=(tickers[0],))
        assert not corrected.ingestion.acquisition.outcomes
        assert corrected.reconciliation.import_result.bar_counts.updated == 1
        assert corrected.corrected_reconciliation_bars == 1
        assert corrected.report_outcome == "WARN"

        before_noop = len(transport_calls)
        no_op = run(
            start_date=date(2026, 7, 4),
            end_date=date(2026, 7, 4),
            now=datetime(2026, 7, 4, 12, tzinfo=UTC),
        )
        assert len(transport_calls) == before_noop
        assert not no_op.ingestion.acquisition.outcomes
        assert not no_op.reconciliation.acquisition.outcomes
        assert no_op.report_outcome == "PASS"

        with connection.cursor() as cursor:  # type: ignore[union-attr]
            cursor.execute(
                """
                SELECT listing.ticker, daily.trading_date, daily.close
                FROM stonks.provider_listing AS listing
                JOIN stonks.ohlcv_daily AS daily
                  ON daily.provider_listing_id = listing.provider_listing_id
                WHERE listing.provider_code = 'YAHOO'
                  AND listing.ticker = ANY(%s)
                ORDER BY listing.ticker, daily.trading_date
                """,
                (list(tickers),),
            )
            rows = cursor.fetchall()
        assert rows == [
            (tickers[0], START_DATE, 11.5000000000),
            (tickers[0], END_DATE, 13.0000000000),
            (tickers[1], START_DATE, 12.0000000000),
            (tickers[1], END_DATE, 13.0000000000),
        ]

        report = json.loads(object_store.get_bytes(corrected.report_object_id))
        assert report["workflow"] == "daily_ingestion_and_reconciliation"
        assert report["phase_results"][0]["phase"] == "daily_ingestion"
        assert report["phase_results"][1]["phase"] == "reconciliation"
        assert report["phase_results"][1]["reconciliation"][
            "corrected_bar_count"
        ] == 1
        assert "temporary provider failure" not in repr(report)
    finally:
        _cleanup(
            connection=connection,
            object_store=object_store,
            runner=runner,
            tickers=tickers,
            checksums=checksums,
        )
