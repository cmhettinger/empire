from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator, Mapping
from datetime import date
from uuid import UUID, uuid4

import pytest

import empire_stonks_ohlcv.eoddata_import as eoddata_import
from empire_core import EmpireDatabase, ObjectStore, RunService
from empire_stonks_ohlcv import (
    EODDataCredentials,
    EODDataHTTPResponse,
    OHLCVConfig,
    run_eoddata_daily,
)


DATABASE_ENVIRONMENT = (
    "EMPIRE_DB_HOST",
    "EMPIRE_DB_NAME",
    "EMPIRE_DB_USER",
    "EMPIRE_DB_PASSWORD",
)
EFFECTIVE_DATE = date(2026, 1, 5)
MARKETS = ("NYSE", "NASDAQ", "AMEX")


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


def _payloads(marker: str) -> dict[tuple[str, str], bytes]:
    shared = f"{marker}.SHARED"
    no_quote = f"{marker}.NOQUOTE"
    duplicate = f"{marker}.DUP"
    conflict = f"{marker}.CONFLICT"
    ghost = f"{marker}.GHOST"

    symbols = {
        "NYSE": [
            {
                "code": shared,
                "name": "E6.13 NYSE Shared",
                "type": "Equity",
                "currency": "USD",
            },
            {"code": no_quote, "name": "E6.13 No Quote"},
        ],
        "NASDAQ": [
            {
                "code": shared,
                "name": "E6.13 NASDAQ Shared",
                "type": "Equity",
                "currency": "USD",
            },
            {
                "code": shared,
                "name": "E6.13 NASDAQ Shared",
                "type": "Equity",
                "currency": "USD",
            },
            {"code": duplicate, "name": "E6.13 Duplicate Quote"},
            {"code": conflict, "name": "Conflict One"},
            {"code": conflict, "name": "Conflict Two"},
        ],
        "AMEX": [
            {
                "code": shared,
                "name": "E6.13 AMEX Shared",
                "type": "Fund",
                "currency": "USD",
            }
        ],
    }

    def quote(market: str, ticker: str, close: float) -> dict[str, object]:
        return {
            "exchangeCode": market,
            "symbolCode": ticker,
            "interval": "d",
            "dateStamp": EFFECTIVE_DATE.isoformat(),
            "open": 10,
            "high": 12,
            "low": 9,
            "close": close,
            "volume": 1000,
        }

    quotes = {
        "NYSE": [
            quote("NYSE", shared, 10.5),
            quote("NYSE", shared, 10.5),
            quote("NYSE", ghost, 11),
        ],
        "NASDAQ": [
            quote("NASDAQ", shared, 10.75),
            quote("NASDAQ", duplicate, 10.5),
            quote("NASDAQ", duplicate, 10.75),
            quote("NASDAQ", conflict, 11),
        ],
        "AMEX": [quote("AMEX", shared, 10.25)],
    }
    return {
        **{
            ("Symbol", market): json.dumps(rows).encode("utf-8")
            for market, rows in symbols.items()
        },
        **{
            ("Quote", market): json.dumps(rows).encode("utf-8")
            for market, rows in quotes.items()
        },
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
            assert query["DateStamp"] == EFFECTIVE_DATE.isoformat()
        return EODDataHTTPResponse(
            status_code=200,
            body=payloads[key],
            headers={"content-type": "application/json"},
        )

    return transport


def _cleanup(
    *,
    connection: object,
    object_store: ObjectStore,
    runner: str,
    marker: str,
    snapshot_checksums: tuple[str, ...],
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
            WHERE provider_code = 'EODDATA'
              AND ticker LIKE %s
            """,
            (marker + ".%",),
        )
        cursor.execute(
            """
            DELETE FROM stonks.provider_source_snapshot
            WHERE provider_code = 'EODDATA'
              AND content_sha256 = ANY(%s)
            """,
            (list(snapshot_checksums),),
        )
        cursor.execute("DELETE FROM core.core_run WHERE runner = %s", (runner,))
    connection.commit()  # type: ignore[union-attr]


def test_eoddata_six_object_fixture_vertical_and_unchanged_rerun(
    database_connection: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = database_connection
    marker = f"E613{uuid4().hex[:10].upper()}"
    runner = f"pytest:e613:{marker}"
    payloads = _payloads(marker)
    checksums = tuple(
        sorted(hashlib.sha256(payload).hexdigest() for payload in payloads.values())
    )
    calls: list[tuple[str, str]] = []
    write_events: list[str] = []
    object_store = ObjectStore.from_connection(connection)
    run_service = RunService.from_connection(connection)
    config = OHLCVConfig(
        storage_key=f"stonks/ohlcv/e613/{marker.lower()}",
        max_retries=0,
        eoddata_request_delay_seconds=0,
        eoddata_credentials=EODDataCredentials(api_key="fixture-secret"),
    )
    original_listing_writer = eoddata_import.upsert_provider_listings
    original_bar_writer = eoddata_import.upsert_daily_bars

    def write_listings(**values: object):
        listings = tuple(values["listings"])  # type: ignore[arg-type]
        write_events.append(f"listings:{listings[0].market}")
        return original_listing_writer(
            cursor=values["cursor"],
            listings=listings,
        )

    def write_bars(**values: object):
        write_events.append("bars")
        return original_bar_writer(**values)

    monkeypatch.setattr(eoddata_import, "upsert_provider_listings", write_listings)
    monkeypatch.setattr(eoddata_import, "upsert_daily_bars", write_bars)

    run_ids: tuple[UUID, ...] = ()
    try:
        first = run_eoddata_daily(
            run_service=run_service,
            connection=connection,
            object_store=object_store,
            config=config,
            effective_date=EFFECTIVE_DATE,
            run_type="manual",
            runner=runner,
            transport=_transport(payloads, calls),
            sleep=lambda _delay: None,
        )
        second = run_eoddata_daily(
            run_service=run_service,
            connection=connection,
            object_store=object_store,
            config=config,
            effective_date=EFFECTIVE_DATE,
            run_type="manual",
            runner=runner,
            transport=_transport(payloads, calls),
            sleep=lambda _delay: None,
        )
        run_ids = (first.run_id, second.run_id)

        assert first.listing_counts.inserted == 5
        assert first.bar_counts.inserted == 3
        assert first.row_rejection_count == 4
        assert first.row_rejection_row_count == 6
        assert first.failure_count == 0
        assert first.status == "succeeded"
        assert first.report_outcome == "WARN"
        assert second.listing_counts.unchanged == 5
        assert second.bar_counts.unchanged == 3
        assert second.listing_counts.inserted == 0
        assert second.bar_counts.inserted == 0
        assert second.bar_counts.derived_updated == 0
        assert second.status == "succeeded"
        assert second.report_outcome == "WARN"
        assert first.run_id != second.run_id

        request_order = [
            (source, market)
            for source in ("Symbol", "Quote")
            for market in MARKETS
        ]
        assert calls == request_order * 2
        write_order = [
            item
            for market in MARKETS
            for item in (f"listings:{market}", "bars")
        ]
        assert write_events == write_order * 2

        for run_id in run_ids:
            objects = object_store.find_objects_by_run_id(run_id)
            assert len(objects) == 7
            raw_objects = tuple(
                item
                for item in objects
                if item.object_kind == "stonks_ohlcv_raw_source"
            )
            assert len(raw_objects) == 6
            assert sorted(item.metadata["market"] for item in raw_objects) == [
                "AMEX",
                "AMEX",
                "NASDAQ",
                "NASDAQ",
                "NYSE",
                "NYSE",
            ]
            assert sum(
                item.object_kind == "stonks_ohlcv_provider_report" for item in objects
            ) == 1

        with connection.cursor() as cursor:  # type: ignore[union-attr]
            cursor.execute(
                "SELECT count(*) FROM core.core_run WHERE runner = %s",
                (runner,),
            )
            assert cursor.fetchone()[0] == 2
            cursor.execute(
                """
                SELECT count(*), count(DISTINCT membership.source_snapshot_id)
                FROM stonks.provider_source_snapshot_object AS membership
                JOIN core.stored_object AS object
                  ON object.object_id = membership.object_id
                WHERE object.run_id = ANY(%s)
                """,
                (list(run_ids),),
            )
            assert cursor.fetchone() == (12, 6)
            cursor.execute(
                """
                SELECT snapshot.source_code, count(*)
                FROM stonks.provider_source_snapshot_object AS membership
                JOIN core.stored_object AS object
                  ON object.object_id = membership.object_id
                JOIN stonks.provider_source_snapshot AS snapshot
                  ON snapshot.source_snapshot_id = membership.source_snapshot_id
                WHERE object.run_id = ANY(%s)
                  AND object.object_kind = 'stonks_ohlcv_raw_source'
                  AND snapshot.provider_code = 'EODDATA'
                GROUP BY snapshot.source_code
                ORDER BY snapshot.source_code
                """,
                (list(run_ids),),
            )
            assert cursor.fetchall() == [
                ("eoddata_daily", 6),
                ("eoddata_symbol_list", 6),
            ]
            cursor.execute(
                """
                SELECT listing.market, listing.ticker,
                       count(daily.trading_date) AS bar_count
                FROM stonks.provider_listing AS listing
                LEFT JOIN stonks.ohlcv_daily AS daily
                  ON daily.provider_listing_id = listing.provider_listing_id
                WHERE listing.provider_code = 'EODDATA'
                  AND listing.ticker LIKE %s
                GROUP BY listing.provider_listing_id,
                         listing.market,
                         listing.ticker
                ORDER BY listing.market, listing.ticker
                """,
                (marker + ".%",),
            )
            listing_rows = cursor.fetchall()
        assert len(listing_rows) == 5
        shared = [row for row in listing_rows if row[1] == f"{marker}.SHARED"]
        assert [(row[0], row[2]) for row in shared] == [
            ("AMEX", 1),
            ("NASDAQ", 1),
            ("NYSE", 1),
        ]
        assert not any(row[1] == f"{marker}.CONFLICT" for row in listing_rows)

        report = json.loads(object_store.get_bytes(second.report_object_id))
        assert report["row_rejections"]["rejected_records"] == 4
        assert report["row_rejections"]["rejected_rows"] == 6
        assert report["warnings"]["total_count"] == 2
        assert {
            (item["market"], item["code"], item["rejected_rows"])
            for item in report["row_rejections"]["reasons"]
        } == {
            ("NYSE", "eoddata_quote_without_listing", 1),
            ("NASDAQ", "eoddata_symbol_duplicate_conflict", 2),
            ("NASDAQ", "eoddata_quote_duplicate_conflict", 2),
            ("NASDAQ", "eoddata_quote_without_listing", 1),
        }
        assert [item["market"] for item in report["markets"]] == list(MARKETS)
        assert [item["listing_write"]["counts"] for item in report["markets"]] == [
            {"derived_updated": 0, "inserted": 0, "unchanged": 2, "updated": 0},
            {"derived_updated": 0, "inserted": 0, "unchanged": 2, "updated": 0},
            {"derived_updated": 0, "inserted": 0, "unchanged": 1, "updated": 0},
        ]
        assert [item["bar_write"]["counts"] for item in report["markets"]] == [
            {"derived_updated": 0, "inserted": 0, "unchanged": 1, "updated": 0},
            {"derived_updated": 0, "inserted": 0, "unchanged": 1, "updated": 0},
            {"derived_updated": 0, "inserted": 0, "unchanged": 1, "updated": 0},
        ]
        assert report["sources"][0]["acquired_object_count"] == 3
        assert report["sources"][1]["acquired_object_count"] == 3
    finally:
        _cleanup(
            connection=connection,
            object_store=object_store,
            runner=runner,
            marker=marker,
            snapshot_checksums=checksums,
        )
