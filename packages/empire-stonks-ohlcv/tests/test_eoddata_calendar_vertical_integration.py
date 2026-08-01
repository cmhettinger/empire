from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from empire_core import EmpireDatabase, ObjectStore, RunService
from empire_stonks_ohlcv import (
    CalendarSchedule,
    EODDataCredentials,
    EODDataHTTPResponse,
    MarketSessionService,
    OHLCVConfig,
    PandasMarketCalendarProvider,
    run_eoddata_daily,
)


DATABASE_ENVIRONMENT = (
    "EMPIRE_DB_HOST",
    "EMPIRE_DB_NAME",
    "EMPIRE_DB_USER",
    "EMPIRE_DB_PASSWORD",
)
MARKETS = ("NYSE", "NASDAQ", "AMEX")
HOLIDAY_DATE = date(2035, 7, 4)
SESSION_DATE = date(2035, 7, 6)
WEEKEND_DATE = date(2035, 7, 7)
ELIGIBLE_AT = datetime(2035, 7, 7, 0, 15, tzinfo=UTC)
HISTORICAL_AT = datetime(2035, 9, 5, 2, tzinfo=UTC)


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


class RecordingCalendarProvider:
    def __init__(self) -> None:
        self.delegate = PandasMarketCalendarProvider()
        self.calls: list[tuple[str, date, date]] = []

    def schedule(
        self,
        *,
        calendar_name: str,
        start_date: date,
        end_date: date,
    ) -> CalendarSchedule:
        self.calls.append((calendar_name, start_date, end_date))
        return self.delegate.schedule(
            calendar_name=calendar_name,
            start_date=start_date,
            end_date=end_date,
        )


def _payloads(
    marker: str,
    *,
    nyse_close: int,
    include_amex_bar: bool,
) -> dict[tuple[str, str], bytes]:
    symbols = {
        market: json.dumps(
            [
                {
                    "code": marker,
                    "name": f"C9.6 {market} calendar fixture",
                    "type": "Equity",
                    "currency": "USD",
                }
            ]
        ).encode("utf-8")
        for market in MARKETS
    }
    closes = {"NYSE": nyse_close, "NASDAQ": 20, "AMEX": 30}
    quotes: dict[str, bytes] = {}
    for market in MARKETS:
        rows = []
        if market != "AMEX" or include_amex_bar:
            close = closes[market]
            rows.append(
                {
                    "exchangeCode": market,
                    "symbolCode": marker,
                    "interval": "d",
                    "dateStamp": SESSION_DATE.isoformat(),
                    "open": close - 1,
                    "high": close + 1,
                    "low": close - 2,
                    "close": close,
                    "volume": 1000,
                }
            )
        quotes[market] = json.dumps(rows).encode("utf-8")
    return {
        **{("Symbol", market): body for market, body in symbols.items()},
        **{("Quote", market): body for market, body in quotes.items()},
    }


def _transport(
    payloads: Mapping[tuple[str, str], bytes],
    calls: list[tuple[str, str]],
):
    def transport(**request: object) -> EODDataHTTPResponse:
        url = request["url"]
        query = request["query"]
        assert isinstance(url, str)
        assert isinstance(query, Mapping)
        endpoint, _, market = url.rsplit("/", 2)
        source = endpoint.rsplit("/", 1)[-1]
        key = (source, market)
        calls.append(key)
        assert query["apiKey"] == "fixture-secret"
        if source == "Quote":
            assert query["DateStamp"] == SESSION_DATE.isoformat()
        return EODDataHTTPResponse(
            status_code=200,
            body=payloads[key],
            headers={"content-type": "application/json"},
        )

    return transport


def _unexpected_transport(**_request: object) -> EODDataHTTPResponse:
    raise AssertionError("a planner no-op must not call EODData")


def _request_order() -> list[tuple[str, str]]:
    return [
        (source, market)
        for source in ("Symbol", "Quote")
        for market in MARKETS
    ]


def _insert_yahoo_fixture(connection: object, marker: str) -> None:
    with connection.cursor() as cursor:  # type: ignore[union-attr]
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
                'C9.6 Yahoo policy isolation fixture',
                'EQUITY_INDEX',
                'ACTIVE',
                jsonb_build_object('YahooTicker', %s::text),
                'YH_XNYS_CLOSE_90M'
            )
            """,
            (marker, f"^{marker}"),
        )
    connection.commit()  # type: ignore[union-attr]


def _cleanup(
    *,
    connection: object,
    object_store: ObjectStore,
    runner: str,
    marker: str,
    checksums: tuple[str, ...],
) -> None:
    connection.rollback()  # type: ignore[union-attr]
    with connection.cursor() as cursor:  # type: ignore[union-attr]
        cursor.execute("SELECT run_id FROM core.core_run WHERE runner = %s", (runner,))
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
            WHERE (provider_code = 'EODDATA' AND ticker = %s)
               OR (provider_code = 'YAHOO' AND ticker = %s)
            """,
            (marker, marker),
        )
        cursor.execute(
            """
            DELETE FROM stonks.provider_source_snapshot
            WHERE provider_code = 'EODDATA'
              AND content_sha256 = ANY(%s)
            """,
            (list(checksums),),
        )
        cursor.execute("DELETE FROM core.core_run WHERE runner = %s", (runner,))
    connection.commit()  # type: ignore[union-attr]


def test_calendar_aware_eoddata_vertical_converges_without_policy_leakage(
    database_connection: object,
) -> None:
    connection = database_connection
    marker = f"C96{uuid4().hex[:12].upper()}"
    runner = f"pytest:c96:{marker}"
    first_payloads = _payloads(
        marker,
        nyse_close=10,
        include_amex_bar=False,
    )
    corrected_payloads = _payloads(
        marker,
        nyse_close=11,
        include_amex_bar=True,
    )
    checksums = tuple(
        sorted(
            {
                hashlib.sha256(body).hexdigest()
                for body in (*first_payloads.values(), *corrected_payloads.values())
            }
        )
    )
    object_store = ObjectStore.from_connection(connection)
    run_service = RunService.from_connection(connection)
    calendar_provider = RecordingCalendarProvider()
    session_service = MarketSessionService(calendar_provider)
    config = OHLCVConfig(
        storage_key=f"stonks/ohlcv/c96/{marker.lower()}",
        max_retries=0,
        eoddata_request_delay_seconds=0,
        eoddata_reconciliation_sessions=2,
        eoddata_credentials=EODDataCredentials(api_key="fixture-secret"),
    )

    try:
        _insert_yahoo_fixture(connection, marker)

        holiday = run_eoddata_daily(
            run_service=run_service,
            connection=connection,
            object_store=object_store,
            config=config,
            effective_date=HOLIDAY_DATE,
            run_type="manual",
            runner=runner,
            transport=_unexpected_transport,
            clock=lambda: datetime(2035, 7, 5, 2, tzinfo=UTC),
        )
        weekend = run_eoddata_daily(
            run_service=run_service,
            connection=connection,
            object_store=object_store,
            config=config,
            effective_date=WEEKEND_DATE,
            run_type="manual",
            runner=runner,
            transport=_unexpected_transport,
            clock=lambda: datetime(2035, 7, 8, 2, tzinfo=UTC),
        )
        assert holiday.expected_session_count == 0
        assert holiday.planned_exchange_count == 0
        assert weekend.expected_session_count == 0
        assert weekend.planned_exchange_count == 0

        initial_calls: list[tuple[str, str]] = []
        initial = run_eoddata_daily(
            run_service=run_service,
            connection=connection,
            object_store=object_store,
            config=config,
            effective_date=SESSION_DATE,
            run_type="manual",
            runner=runner,
            transport=_transport(first_payloads, initial_calls),
            sleep=lambda _delay: None,
            clock=lambda: ELIGIBLE_AT,
            session_service=session_service,
        )
        assert initial_calls == _request_order()
        assert initial.bar_counts.inserted == 2
        assert initial.expected_session_count == 3
        assert initial.eligible_session_count == 3
        assert initial.missing_session_count == 1
        assert initial.planned_exchange_count == 3

        retry_calls: list[tuple[str, str]] = []
        retry = run_eoddata_daily(
            run_service=run_service,
            connection=connection,
            object_store=object_store,
            config=config,
            effective_date=SESSION_DATE,
            run_type="manual",
            runner=runner,
            transport=_transport(corrected_payloads, retry_calls),
            sleep=lambda _delay: None,
            clock=lambda: ELIGIBLE_AT,
            session_service=session_service,
        )
        assert retry_calls == _request_order()
        assert retry.bar_counts.inserted == 1
        assert retry.bar_counts.updated == 1
        assert retry.bar_counts.unchanged == 1
        assert retry.missing_session_count == 0
        assert retry.corrected_current_rows == 1

        converged_calls: list[tuple[str, str]] = []
        converged = run_eoddata_daily(
            run_service=run_service,
            connection=connection,
            object_store=object_store,
            config=config,
            effective_date=SESSION_DATE,
            run_type="manual",
            runner=runner,
            transport=_transport(corrected_payloads, converged_calls),
            sleep=lambda _delay: None,
            clock=lambda: ELIGIBLE_AT,
            session_service=session_service,
        )
        assert converged_calls == _request_order()
        assert converged.bar_counts.unchanged == 3
        assert converged.corrected_current_rows == 0
        assert converged.missing_session_count == 0

        completed = run_eoddata_daily(
            run_service=run_service,
            connection=connection,
            object_store=object_store,
            config=config,
            effective_date=SESSION_DATE,
            run_type="manual",
            runner=runner,
            transport=_unexpected_transport,
            clock=lambda: HISTORICAL_AT,
            session_service=session_service,
        )
        assert completed.expected_session_count == 3
        assert completed.eligible_session_count == 3
        assert completed.missing_session_count == 0
        assert completed.planned_exchange_count == 0
        assert completed.bar_counts.input_count == 0
        assert completed.bar_counts.derived_updated == 0

        assert {item[0] for item in calendar_provider.calls} == {
            "NASDAQ",
            "XNYS",
        }

        with connection.cursor() as cursor:  # type: ignore[union-attr]
            cursor.execute(
                """
                SELECT
                    listing.provider_code,
                    listing.market,
                    listing.session_policy_code,
                    listing.metadata ->> 'YahooTicker'
                FROM stonks.provider_listing AS listing
                WHERE listing.ticker = %s
                  AND listing.provider_code IN ('EODDATA', 'YAHOO')
                ORDER BY listing.provider_code, listing.market
                """,
                (marker,),
            )
            policy_rows = cursor.fetchall()
            cursor.execute(
                """
                SELECT listing.market, daily.trading_date, daily.close
                FROM stonks.provider_listing AS listing
                JOIN stonks.ohlcv_daily AS daily
                  ON daily.provider_listing_id = listing.provider_listing_id
                WHERE listing.provider_code = 'EODDATA'
                  AND listing.ticker = %s
                ORDER BY listing.market, daily.trading_date
                """,
                (marker,),
            )
            bar_rows = cursor.fetchall()

        assert policy_rows == [
            ("EODDATA", "AMEX", "ED_XNYS_1900_60M", None),
            ("EODDATA", "NASDAQ", "ED_XNAS_1900_60M", None),
            ("EODDATA", "NYSE", "ED_XNYS_1900_60M", None),
            ("YAHOO", "XIDX", "YH_XNYS_CLOSE_90M", f"^{marker}"),
        ]
        assert [(row[0], row[1], str(row[2])) for row in bar_rows] == [
            ("AMEX", SESSION_DATE, "30.0000000000"),
            ("NASDAQ", SESSION_DATE, "20.0000000000"),
            ("NYSE", SESSION_DATE, "11.0000000000"),
        ]

        initial_report = json.loads(object_store.get_bytes(initial.report_object_id))
        retry_report = json.loads(object_store.get_bytes(retry.report_object_id))
        completed_report = json.loads(
            object_store.get_bytes(completed.report_object_id)
        )
        assert [
            item["session_coverage"]["policy_code"]
            for item in retry_report["markets"]
        ] == [
            "ED_XNYS_1900_60M",
            "ED_XNAS_1900_60M",
            "ED_XNYS_1900_60M",
        ]
        assert initial_report["session_planning"][
            "missing_eligible_session_count"
        ] == 1
        assert retry_report["session_planning"][
            "missing_eligible_session_count"
        ] == 0
        assert retry_report["execution"]["corrected_current_rows"] == 1
        assert [
            item["execution"]["work_reasons"]
            for item in retry_report["markets"]
        ] == [
            ["recent_reconciliation"],
            ["recent_reconciliation"],
            ["eligible_missing_session"],
        ]
        assert completed_report["execution"]["requested_exchange_count"] == 0
        assert all(
            report["provider_code"] == "EODDATA"
            for report in (initial_report, retry_report, completed_report)
        )

        for result, raw_count in (
            (holiday, 0),
            (weekend, 0),
            (initial, 6),
            (retry, 6),
            (converged, 6),
            (completed, 0),
        ):
            objects = object_store.find_objects_by_run_id(result.run_id)
            assert len(objects) == raw_count + 3
            assert sum(
                item.object_kind == "stonks_ohlcv_raw_source"
                for item in objects
            ) == raw_count
            with connection.cursor() as cursor:  # type: ignore[union-attr]
                cursor.execute(
                    """
                    SELECT count(*)
                    FROM stonks.provider_source_snapshot_object AS membership
                    JOIN core.stored_object AS object
                      ON object.object_id = membership.object_id
                    WHERE object.run_id = %s
                    """,
                    (result.run_id,),
                )
                assert cursor.fetchone()[0] == raw_count
    finally:
        _cleanup(
            connection=connection,
            object_store=object_store,
            runner=runner,
            marker=marker,
            checksums=checksums,
        )
