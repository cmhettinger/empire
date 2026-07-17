from __future__ import annotations

import hashlib
import json
import os
from datetime import date
from typing import Iterator
from uuid import UUID, uuid4

import pytest

import empire_stonks_ohlcv.eoddata_import as eoddata_import
from empire_core.db.connection import EmpireDatabase
from empire_stonks_ohlcv import (
    AcquiredObject,
    EODDATA_DAILY_SOURCE,
    EODDATA_SYMBOL_LIST_SOURCE,
    OHLCVWorkflowError,
    RAW_SOURCE_OBJECT_KIND,
    import_eoddata_daily,
    parse_eoddata_quote_list,
    parse_eoddata_symbol_list,
)


DATABASE_ENVIRONMENT = (
    "EMPIRE_DB_HOST",
    "EMPIRE_DB_NAME",
    "EMPIRE_DB_USER",
    "EMPIRE_DB_PASSWORD",
)
EFFECTIVE_DATE = date(2026, 7, 15)
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


def _validation_results(*, ticker: str, close: float):
    results = []
    for market in MARKETS:
        symbols = parse_eoddata_symbol_list(
            json.dumps(
                [
                    {
                        "code": ticker,
                        "name": "E6.6 Integration Company",
                        "type": "Equity",
                        "currency": "USD",
                    }
                ]
            ).encode("utf-8"),
            exchange=market,
        )
        quotes = parse_eoddata_quote_list(
            json.dumps(
                [
                    {
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
                ]
            ).encode("utf-8"),
            exchange=market,
            effective_date=EFFECTIVE_DATE,
            symbol_list=symbols,
        )
        results.append(quotes.to_validation_result(symbol_list=symbols))
    return tuple(results)


def _insert_raw_objects(
    *,
    cursor: object,
    run_id: UUID,
    storage_root_id: int,
    marker: str,
) -> tuple[AcquiredObject, ...]:
    acquired: list[AcquiredObject] = []
    for source in (EODDATA_SYMBOL_LIST_SOURCE, EODDATA_DAILY_SOURCE):
        for market in MARKETS:
            content = f"{marker}:{source.source_code}:{market}".encode()
            checksum = hashlib.sha256(content).hexdigest()
            filename = f"raw-{market.lower()}.json"
            object_key = (
                f"stonks/ohlcv/eoddata/e66/{marker}/"
                f"{source.source_code}/{market.lower()}"
            )
            cursor.execute(  # type: ignore[union-attr]
                """
                INSERT INTO core.stored_object (
                    run_id,
                    storage_root_id,
                    object_key,
                    filename,
                    object_scope,
                    domain,
                    logical_name,
                    content_type,
                    object_kind,
                    size_bytes,
                    checksum_sha256,
                    metadata
                )
                VALUES (%s, %s, %s, %s, 'run', 'stonks', %s,
                        'application/json', %s, %s, %s, '{}'::jsonb)
                RETURNING object_id
                """,
                (
                    run_id,
                    storage_root_id,
                    object_key,
                    filename,
                    source.source_code,
                    RAW_SOURCE_OBJECT_KIND,
                    len(content),
                    checksum,
                ),
            )
            object_id = cursor.fetchone()[0]  # type: ignore[union-attr]
            acquired.append(
                AcquiredObject(
                    source_code=source.source_code,
                    object_id=object_id,
                    object_key=object_key,
                    filename=filename,
                    size_bytes=len(content),
                    checksum_sha256=checksum,
                )
            )
    return tuple(acquired)


def test_eoddata_import_rolls_back_then_reruns_corrects_and_skips_inactive(
    database_connection: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = database_connection
    marker = str(uuid4())
    ticker = f"E66.{marker[:8]}"
    object_ids: list[UUID] = []
    run_id: UUID | None = None
    checksums: list[str] = []

    try:
        with connection.cursor() as cursor:  # type: ignore[union-attr]
            cursor.execute(
                """
                INSERT INTO core.core_run (
                    domain,
                    job_name,
                    subject_key,
                    effective_date,
                    run_type,
                    status,
                    runner
                )
                VALUES ('stonks', 'stonks_ohlcv_eoddata_daily', %s, %s,
                        'cli', 'started', 'pytest')
                RETURNING run_id
                """,
                (f"e66:{marker}", EFFECTIVE_DATE),
            )
            run_id = cursor.fetchone()[0]
            cursor.execute(
                """
                SELECT storage_root_id
                FROM core.storage_root
                WHERE root_name = 'global'
                  AND is_active
                """
            )
            storage_root_id = cursor.fetchone()[0]
            acquired = _insert_raw_objects(
                cursor=cursor,
                run_id=run_id,
                storage_root_id=storage_root_id,
                marker=marker,
            )
            object_ids.extend(item.object_id for item in acquired)
            checksums.extend(item.checksum_sha256 for item in acquired)
        connection.commit()  # type: ignore[union-attr]

        validations = _validation_results(ticker=ticker, close=10.5)
        original_bar_writer = eoddata_import.upsert_daily_bars
        bar_calls = 0

        def fail_after_one_market(**values: object):
            nonlocal bar_calls
            bar_calls += 1
            if bar_calls == 2:
                raise RuntimeError("forced persistence failure")
            return original_bar_writer(**values)

        monkeypatch.setattr(
            eoddata_import,
            "upsert_daily_bars",
            fail_after_one_market,
        )
        with pytest.raises(OHLCVWorkflowError):
            import_eoddata_daily(
                connection=connection,
                effective_date=EFFECTIVE_DATE,
                acquired_objects=acquired,
                validation_results=validations,
            )

        with connection.cursor() as cursor:  # type: ignore[union-attr]
            cursor.execute(
                """
                SELECT count(*)
                FROM stonks.provider_source_snapshot_object
                WHERE object_id = ANY(%s)
                """,
                (object_ids,),
            )
            assert cursor.fetchone()[0] == 0
            cursor.execute(
                """
                SELECT count(*)
                FROM stonks.provider_listing
                WHERE provider_code = 'EODDATA'
                  AND ticker = %s
                """,
                (ticker,),
            )
            assert cursor.fetchone()[0] == 0

        monkeypatch.setattr(
            eoddata_import,
            "upsert_daily_bars",
            original_bar_writer,
        )
        first = import_eoddata_daily(
            connection=connection,
            effective_date=EFFECTIVE_DATE,
            acquired_objects=acquired,
            validation_results=validations,
        )
        rerun = import_eoddata_daily(
            connection=connection,
            effective_date=EFFECTIVE_DATE,
            acquired_objects=acquired,
            validation_results=validations,
        )
        assert first.listing_counts.inserted == 3
        assert first.bar_counts.inserted == 3
        assert rerun.listing_counts.unchanged == 3
        assert rerun.bar_counts.unchanged == 3

        with connection.cursor() as cursor:  # type: ignore[union-attr]
            cursor.execute(
                """
                UPDATE stonks.provider_listing
                SET status = 'INACTIVE'
                WHERE provider_code = 'EODDATA'
                  AND market = 'NYSE'
                  AND ticker = %s
                """,
                (ticker,),
            )
        connection.commit()  # type: ignore[union-attr]

        corrected = import_eoddata_daily(
            connection=connection,
            effective_date=EFFECTIVE_DATE,
            acquired_objects=acquired,
            validation_results=_validation_results(ticker=ticker, close=10.75),
        )
        assert corrected.listing_counts.unchanged == 3
        assert corrected.bar_counts.updated == 2
        assert corrected.skipped_inactive_bars == 1

        with connection.cursor() as cursor:  # type: ignore[union-attr]
            cursor.execute(
                """
                SELECT listing.market, daily.close, listing.status
                FROM stonks.provider_listing AS listing
                JOIN stonks.ohlcv_daily AS daily
                  ON daily.provider_listing_id = listing.provider_listing_id
                WHERE listing.provider_code = 'EODDATA'
                  AND listing.ticker = %s
                ORDER BY listing.market
                """,
                (ticker,),
            )
            rows = cursor.fetchall()
        assert [(row[0], str(row[1]), row[2]) for row in rows] == [
            ("AMEX", "10.7500000000", "ACTIVE"),
            ("NASDAQ", "10.7500000000", "ACTIVE"),
            ("NYSE", "10.5000000000", "INACTIVE"),
        ]
    finally:
        connection.rollback()  # type: ignore[union-attr]
        with connection.cursor() as cursor:  # type: ignore[union-attr]
            cursor.execute(
                """
                DELETE FROM stonks.provider_listing
                WHERE provider_code = 'EODDATA'
                  AND ticker = %s
                """,
                (ticker,),
            )
            if object_ids:
                cursor.execute(
                    """
                    DELETE FROM stonks.provider_source_snapshot_object
                    WHERE object_id = ANY(%s)
                    """,
                    (object_ids,),
                )
            if checksums:
                cursor.execute(
                    """
                    DELETE FROM stonks.provider_source_snapshot
                    WHERE provider_code = 'EODDATA'
                      AND content_sha256 = ANY(%s)
                    """,
                    (checksums,),
                )
            if object_ids:
                cursor.execute(
                    """
                    DELETE FROM core.stored_object
                    WHERE object_id = ANY(%s)
                    """,
                    (object_ids,),
                )
            if run_id is not None:
                cursor.execute(
                    """
                    DELETE FROM core.core_run
                    WHERE run_id = %s
                    """,
                    (run_id,),
                )
        connection.commit()  # type: ignore[union-attr]
