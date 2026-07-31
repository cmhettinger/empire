from __future__ import annotations

import hashlib
import json
import os
from datetime import date
from typing import Iterator
from urllib.parse import unquote
from uuid import UUID, uuid4

import pytest

from empire_core import EmpireDatabase, ObjectStore, RunService
from empire_stonks_ohlcv import (
    OHLCVConfig,
    YahooBackfillScope,
    YahooHTTPResponse,
    run_yahoo_backfill,
)


DATABASE_ENVIRONMENT = (
    "EMPIRE_DB_HOST",
    "EMPIRE_DB_NAME",
    "EMPIRE_DB_USER",
    "EMPIRE_DB_PASSWORD",
)
EFFECTIVE_DATE = date(2026, 7, 30)
START_DATE = date(2026, 7, 1)
END_DATE_EXCLUSIVE = date(2026, 7, 2)
POLICY_CODE = "YH_XNYS_CLOSE_90M"


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


def _payload(*, yahoo_ticker: str, close: float) -> bytes:
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
                        "timestamp": [1782912600],
                        "indicators": {
                            "quote": [
                                {
                                    "open": [10],
                                    "high": [13],
                                    "low": [9],
                                    "close": [close],
                                    "volume": [None],
                                }
                            ]
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


def test_backfill_rerun_correction_partial_failure_and_resume(
    database_connection: object,
) -> None:
    connection = database_connection
    object_store = ObjectStore.from_connection(connection)
    marker = uuid4().hex[:8].upper()
    tickers = (f"Y89A{marker}", f"Y89B{marker}")
    yahoo_tickers = {
        tickers[0]: f"^{tickers[0]}",
        tickers[1]: f"^{tickers[1]}",
    }
    runner = f"pytest:y89:{marker}"
    closes = {
        yahoo_tickers[tickers[0]]: 11.25,
        yahoo_tickers[tickers[1]]: 12.00,
    }
    failing: set[str] = set()
    checksums: set[str] = set()

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
                        'YAHOO',
                        'XIDX',
                        %s,
                        %s,
                        'EQUITY_INDEX',
                        'ACTIVE',
                        %s::jsonb,
                        %s
                    )
                    """,
                    (
                        ticker,
                        f"{ticker} Integration Index",
                        json.dumps(
                            {"YahooTicker": yahoo_tickers[ticker]}
                        ),
                        POLICY_CODE,
                    ),
                )
        connection.commit()  # type: ignore[union-attr]

        def transport(**values: object) -> YahooHTTPResponse:
            url = values["url"]
            assert isinstance(url, str)
            yahoo_ticker = unquote(url.rsplit("/", 1)[-1])
            if yahoo_ticker in failing:
                return YahooHTTPResponse(
                    status_code=503,
                    body=b"temporary provider failure",
                    headers={"content-type": "text/plain"},
                )
            body = _payload(
                yahoo_ticker=yahoo_ticker,
                close=closes[yahoo_ticker],
            )
            checksums.add(hashlib.sha256(body).hexdigest())
            return YahooHTTPResponse(
                status_code=200,
                body=body,
                headers={"content-type": "application/json"},
            )

        config = OHLCVConfig(
            storage_key=f"stonks/ohlcv/y89/{marker.lower()}",
            max_retries=0,
            yahoo_request_delay_seconds=0,
            yahoo_request_jitter_min_seconds=0,
            yahoo_request_jitter_max_seconds=0,
            yahoo_failure_cooldown_min_seconds=0,
            yahoo_failure_cooldown_max_seconds=0,
        )

        def run(
            *,
            selected_tickers: tuple[str, ...] = tickers,
            resume_from: str | None = None,
        ):
            return run_yahoo_backfill(
                run_service=RunService.from_connection(connection),
                connection=connection,
                object_store=object_store,
                config=config,
                scope=YahooBackfillScope(
                    effective_date=EFFECTIVE_DATE,
                    start_date=START_DATE,
                    end_date_exclusive=END_DATE_EXCLUSIVE,
                    tickers=selected_tickers,
                    resume_from_ticker=resume_from,
                ),
                run_type="manual",
                runner=runner,
                transport=transport,
                sleep=lambda _: None,
                random_uniform=lambda minimum, _maximum: minimum,
            )

        first = run()
        rerun = run()
        assert first.bar_counts.inserted == 2
        assert rerun.bar_counts.unchanged == 2
        assert first.report_outcome == "PASS"
        assert rerun.report_outcome == "PASS"

        closes[yahoo_tickers[tickers[0]]] = 11.50
        corrected = run(selected_tickers=(tickers[0],))
        assert corrected.bar_counts.updated == 1
        assert corrected.report_outcome == "PASS"

        failing.add(yahoo_tickers[tickers[1]])
        partial = run()
        assert partial.import_result.imported_chunks == 1
        assert partial.import_result.failed_chunks == 1
        assert partial.bar_counts.unchanged == 1
        assert partial.report_outcome == "WARN"

        failing.clear()
        resumed = run(resume_from=tickers[1])
        assert resumed.selected_listing_count == 1
        assert resumed.bar_counts.unchanged == 1
        assert resumed.report_outcome == "PASS"

        with connection.cursor() as cursor:  # type: ignore[union-attr]
            cursor.execute(
                """
                SELECT listing.ticker, daily.close
                FROM stonks.provider_listing AS listing
                JOIN stonks.ohlcv_daily AS daily
                  ON daily.provider_listing_id = listing.provider_listing_id
                WHERE listing.provider_code = 'YAHOO'
                  AND listing.ticker = ANY(%s)
                  AND daily.trading_date = %s
                ORDER BY listing.ticker
                """,
                (list(tickers), START_DATE),
            )
            rows = cursor.fetchall()
            cursor.execute(
                """
                SELECT count(*)
                FROM core.core_run
                WHERE runner = %s
                  AND status = 'succeeded'
                """,
                (runner,),
            )
            succeeded_runs = cursor.fetchone()[0]
        assert rows == [
            (tickers[0], 11.5000000000),
            (tickers[1], 12.0000000000),
        ]
        assert succeeded_runs == 5

        report = json.loads(
            object_store.get_bytes(partial.report_object_id)
        )
        assert report["outcome"] == "WARN"
        assert report["acquisition"]["failed"] == 1
        assert report["import"]["failed_chunks"] == 1
        assert report["native_value_semantics"]["seeded_listing_writes"] == 0
        assert "temporary provider failure" not in repr(report)
    finally:
        _cleanup(
            connection=connection,
            object_store=object_store,
            runner=runner,
            tickers=tickers,
            checksums=checksums,
        )
