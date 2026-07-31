from __future__ import annotations

import hashlib
import json
import os
from datetime import date
from typing import Iterator
from uuid import UUID, uuid4

import pytest

from empire_core.db.connection import EmpireDatabase
from empire_stonks_ohlcv import (
    AcquiredObject,
    EligibilityRule,
    ProviderListing,
    RAW_SOURCE_OBJECT_KIND,
    SessionDateRule,
    SessionPolicy,
    YahooAcquisitionOutcome,
    YahooAcquisitionRequest,
    YahooAcquisitionStatus,
    YahooImportFailureCode,
    YahooImportInput,
    YahooListingTarget,
    YahooRequestMode,
    import_yahoo_ranges,
    parse_yahoo_chart,
)


DATABASE_ENVIRONMENT = (
    "EMPIRE_DB_HOST",
    "EMPIRE_DB_NAME",
    "EMPIRE_DB_USER",
    "EMPIRE_DB_PASSWORD",
)
TRADE_DATE = date(2026, 7, 1)
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
                                    "high": [12],
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
        }
    ).encode()


def _insert_raw_object(
    *,
    cursor: object,
    run_id: UUID,
    storage_root_id: int,
    marker: str,
    sequence: int,
    content: bytes,
) -> AcquiredObject:
    checksum = hashlib.sha256(content).hexdigest()
    object_key = f"stonks/ohlcv/yahoo/y88/{marker}/raw-{sequence}.json"
    filename = f"raw-{sequence}.json"
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
        VALUES (%s, %s, %s, %s, 'run', 'stonks', 'yahoo_daily',
                'application/json', %s, %s, %s, '{}'::jsonb)
        RETURNING object_id
        """,
        (
            run_id,
            storage_root_id,
            object_key,
            filename,
            RAW_SOURCE_OBJECT_KIND,
            len(content),
            checksum,
        ),
    )
    object_id = cursor.fetchone()[0]  # type: ignore[union-attr]
    return AcquiredObject(
        source_code="yahoo_daily",
        object_id=object_id,
        object_key=object_key,
        filename=filename,
        size_bytes=len(content),
        checksum_sha256=checksum,
    )


def _import_input(
    *,
    provider_listing_id: UUID,
    ticker: str,
    yahoo_ticker: str,
    name: str,
    acquired_object: AcquiredObject,
    payload: bytes,
) -> YahooImportInput:
    request = YahooAcquisitionRequest(
        listing=YahooListingTarget(
            provider_listing_id=provider_listing_id,
            ticker=ticker,
            yahoo_ticker=yahoo_ticker,
        ),
        start_date=TRADE_DATE,
        end_date_exclusive=END_DATE_EXCLUSIVE,
        mode=YahooRequestMode.DAILY,
    )
    acquisition = YahooAcquisitionOutcome(
        request=request,
        status=YahooAcquisitionStatus.STORED,
        attempts=1,
        http_status=200,
        acquired_object=acquired_object,
    )
    parsed = parse_yahoo_chart(
        payload,
        request=request,
        listing=ProviderListing(
            provider_code="YAHOO",
            market="XIDX",
            ticker=ticker,
            name=name,
            instrument_type_code="EQUITY_INDEX",
            metadata={"YahooTicker": yahoo_ticker},
        ),
        policy=SessionPolicy(
            code=POLICY_CODE,
            calendar_name="XNYS",
            timezone_name="America/New_York",
            eligibility_rule=EligibilityRule.SESSION_CLOSE,
            cutoff_local_time=None,
            availability_delay_minutes=90,
            session_date_rule=SessionDateRule.CALENDAR_SESSION,
        ),
        planned_session_dates=(TRADE_DATE,),
    )
    return YahooImportInput(
        acquisition=acquisition,
        parse_result=parsed,
    )


def test_yahoo_import_is_seed_only_idempotent_correctable_and_isolated(
    database_connection: object,
) -> None:
    connection = database_connection
    marker = uuid4().hex
    ticker = f"Y88{marker[:8].upper()}"
    yahoo_ticker = f"^{ticker}"
    name = f"{ticker} Integration Index"
    run_id: UUID | None = None
    provider_listing_id: UUID | None = None
    acquired_objects: tuple[AcquiredObject, ...] = ()

    payloads = (
        _payload(yahoo_ticker=yahoo_ticker, close=11.25),
        _payload(yahoo_ticker=yahoo_ticker, close=11.50),
        _payload(yahoo_ticker=yahoo_ticker, close=11.75),
        _payload(yahoo_ticker=f"^{ticker}UNSEEDED", close=11.60),
    )

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
                VALUES ('stonks', 'stonks_ohlcv_yahoo_y88_test', %s, %s,
                        'cli', 'started', 'pytest')
                RETURNING run_id
                """,
                (f"y88:{marker}", TRADE_DATE),
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
            acquired_objects = tuple(
                _insert_raw_object(
                    cursor=cursor,
                    run_id=run_id,
                    storage_root_id=storage_root_id,
                    marker=marker,
                    sequence=index,
                    content=payload,
                )
                for index, payload in enumerate(payloads, start=1)
            )
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
                RETURNING provider_listing_id
                """,
                (
                    ticker,
                    name,
                    json.dumps({"YahooTicker": yahoo_ticker}),
                    POLICY_CODE,
                ),
            )
            provider_listing_id = cursor.fetchone()[0]
        connection.commit()  # type: ignore[union-attr]

        first_input = _import_input(
            provider_listing_id=provider_listing_id,
            ticker=ticker,
            yahoo_ticker=yahoo_ticker,
            name=name,
            acquired_object=acquired_objects[0],
            payload=payloads[0],
        )
        first = import_yahoo_ranges(
            connection=connection,
            inputs=(first_input,),
        )
        rerun = import_yahoo_ranges(
            connection=connection,
            inputs=(first_input,),
        )
        assert first.bar_counts.inserted == 1
        assert rerun.bar_counts.unchanged == 1

        correction_input = _import_input(
            provider_listing_id=provider_listing_id,
            ticker=ticker,
            yahoo_ticker=yahoo_ticker,
            name=name,
            acquired_object=acquired_objects[1],
            payload=payloads[1],
        )
        unseeded_input = _import_input(
            provider_listing_id=uuid4(),
            ticker=f"{ticker}UNSEEDED",
            yahoo_ticker=f"^{ticker}UNSEEDED",
            name=f"{ticker} Unseeded Index",
            acquired_object=acquired_objects[3],
            payload=payloads[3],
        )
        mixed = import_yahoo_ranges(
            connection=connection,
            inputs=(unseeded_input, correction_input),
        )
        assert mixed.bar_counts.updated == 1
        assert mixed.imported_chunks == 1
        assert mixed.failed_chunks == 1
        assert {
            chunk.failure_code
            for listing in mixed.listings
            for chunk in listing.chunks
            if chunk.failure_code is not None
        } == {YahooImportFailureCode.UNSEEDED_LISTING}

        with connection.cursor() as cursor:  # type: ignore[union-attr]
            cursor.execute(
                """
                SELECT count(*)
                FROM stonks.provider_listing
                WHERE provider_code = 'YAHOO'
                  AND ticker = %s
                """,
                (f"{ticker}UNSEEDED",),
            )
            assert cursor.fetchone()[0] == 0
            cursor.execute(
                """
                UPDATE stonks.provider_listing
                SET status = 'INACTIVE'
                WHERE provider_listing_id = %s
                """,
                (provider_listing_id,),
            )
        connection.commit()  # type: ignore[union-attr]

        inactive_input = _import_input(
            provider_listing_id=provider_listing_id,
            ticker=ticker,
            yahoo_ticker=yahoo_ticker,
            name=name,
            acquired_object=acquired_objects[2],
            payload=payloads[2],
        )
        inactive = import_yahoo_ranges(
            connection=connection,
            inputs=(inactive_input,),
        )
        assert inactive.failed_chunks == 1
        assert inactive.listings[0].chunks[0].failure_code is (
            YahooImportFailureCode.INACTIVE_LISTING
        )

        with connection.cursor() as cursor:  # type: ignore[union-attr]
            cursor.execute(
                """
                SELECT daily.close, listing.status
                FROM stonks.provider_listing AS listing
                JOIN stonks.ohlcv_daily AS daily
                  ON daily.provider_listing_id = listing.provider_listing_id
                WHERE listing.provider_listing_id = %s
                  AND daily.trading_date = %s
                """,
                (provider_listing_id, TRADE_DATE),
            )
            close, status = cursor.fetchone()
        assert str(close) == "11.5000000000"
        assert status == "INACTIVE"
    finally:
        connection.rollback()  # type: ignore[union-attr]
        object_ids = [item.object_id for item in acquired_objects]
        checksums = [item.checksum_sha256 for item in acquired_objects]
        with connection.cursor() as cursor:  # type: ignore[union-attr]
            if provider_listing_id is not None:
                cursor.execute(
                    """
                    DELETE FROM stonks.provider_listing
                    WHERE provider_listing_id = %s
                    """,
                    (provider_listing_id,),
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
                    WHERE provider_code = 'YAHOO'
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
