from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Iterator
from uuid import UUID, uuid4

import pytest

import empire_stonks_ohlcv.yahoo_import as yahoo_import
from empire_core import EmpireDatabase
from empire_stonks_ohlcv import (
    AcquiredObject,
    DailyBar,
    DailyBarComparisonStatus,
    DailyBarWriteInput,
    EligibilityRule,
    ProviderListing,
    SessionDateRule,
    SessionPolicy,
    SourceSnapshotRegistration,
    YahooAcquisitionOutcome,
    YahooAcquisitionRequest,
    YahooAcquisitionStatus,
    YahooImportInput,
    YahooImportPurpose,
    YahooListingTarget,
    YahooRequestMode,
    import_yahoo_ranges,
    parse_yahoo_chart,
    plan_yahoo_recent_reconciliation,
    upsert_daily_bars,
)


DATABASE_ENVIRONMENT = (
    "EMPIRE_DB_HOST",
    "EMPIRE_DB_NAME",
    "EMPIRE_DB_USER",
    "EMPIRE_DB_PASSWORD",
)
POLICY_CODE = "YH_XNYS_CLOSE_90M"
START_DATE = date(2026, 7, 1)
END_DATE_EXCLUSIVE = date(2026, 7, 3)


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


def _payload(yahoo_ticker: str) -> bytes:
    timestamps = [
        int(datetime(2026, 7, 1, 13, 30, tzinfo=UTC).timestamp()),
        int(datetime(2026, 7, 2, 13, 30, tzinfo=UTC).timestamp()),
    ]
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
                        "timestamp": timestamps,
                        "indicators": {
                            "quote": [
                                {
                                    "open": [10, 11.5],
                                    "high": [12.5, 13],
                                    "low": [9, 11],
                                    "close": [11.5, 12],
                                    "volume": [None, 200],
                                }
                            ],
                            "adjclose": [{"adjclose": [11.25, 11.9]}],
                        },
                    }
                ],
                "error": None,
            }
        },
        separators=(",", ":"),
    ).encode()


def test_reconciliation_handles_late_or_corrected_date_fields_and_noop(
    database_connection: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = database_connection
    marker = uuid4().hex[:8].upper()
    ticker = f"Y811{marker}"
    yahoo_ticker = f"^{ticker}"
    name = f"{ticker} Reconciliation Test"
    listing_id: UUID | None = None

    try:
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
                VALUES ('YAHOO', 'XIDX', %s, %s, 'EQUITY_INDEX', 'ACTIVE',
                        %s::jsonb, %s)
                RETURNING provider_listing_id
                """,
                (
                    ticker,
                    name,
                    json.dumps({"YahooTicker": yahoo_ticker}),
                    POLICY_CODE,
                ),
            )
            listing_id = cursor.fetchone()[0]
            initial_counts = upsert_daily_bars(
                cursor=cursor,
                bars=(
                    DailyBarWriteInput(
                        provider_listing_id=listing_id,
                        bar=DailyBar(
                            trading_date=START_DATE,
                            open=Decimal("10"),
                            high=Decimal("12"),
                            low=Decimal("9"),
                            close=Decimal("11"),
                            volume=Decimal("100"),
                        ),
                    ),
                ),
            )
        assert initial_counts.inserted == 1
        connection.commit()  # type: ignore[union-attr]

        with connection.cursor() as cursor:  # type: ignore[union-attr]
            reconciliation_plan = plan_yahoo_recent_reconciliation(
                cursor=cursor,
                start_date=START_DATE,
                end_date=date(2026, 7, 2),
                now=datetime(2026, 7, 3, tzinfo=UTC),
                session_count=2,
                max_request_days=10,
                tickers=(ticker,),
            )
        assert reconciliation_plan.listings[0].selected_dates == (
            START_DATE,
            date(2026, 7, 2),
        )

        request = YahooAcquisitionRequest(
            listing=YahooListingTarget(
                provider_listing_id=listing_id,
                ticker=ticker,
                yahoo_ticker=yahoo_ticker,
            ),
            start_date=START_DATE,
            end_date_exclusive=END_DATE_EXCLUSIVE,
            mode=YahooRequestMode.DAILY,
        )
        acquired = AcquiredObject(
            source_code="yahoo_daily",
            object_id=uuid4(),
            object_key=f"test/y811/{marker.lower()}",
            filename="raw.json",
            size_bytes=100,
            checksum_sha256="a" * 64,
        )
        outcome = YahooAcquisitionOutcome(
            request=request,
            status=YahooAcquisitionStatus.STORED,
            attempts=1,
            http_status=200,
            acquired_object=acquired,
        )
        parsed = parse_yahoo_chart(
            _payload(yahoo_ticker),
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
            planned_session_dates=(START_DATE, date(2026, 7, 2)),
        )
        registration = SourceSnapshotRegistration(
            source_snapshot_id=uuid4(),
            object_id=acquired.object_id,
            provider_code="YAHOO",
            source_code="yahoo_daily",
            content_sha256=acquired.checksum_sha256,
            snapshot_inserted=False,
            object_link_inserted=False,
        )
        monkeypatch.setattr(
            yahoo_import,
            "upsert_provider_source_snapshot",
            lambda **_: registration,
        )
        reconciliation_input = YahooImportInput(
            acquisition=outcome,
            parse_result=parsed,
            purpose=YahooImportPurpose.RECONCILIATION,
        )

        first = import_yahoo_ranges(
            connection=connection,
            inputs=(reconciliation_input,),
        )
        rerun = import_yahoo_ranges(
            connection=connection,
            inputs=(reconciliation_input,),
        )

        chunk = first.listings[0].chunks[0]
        assert first.bar_counts.updated == 1
        assert first.bar_counts.inserted == 1
        assert first.corrected_reconciliation_bars == 1
        assert first.inserted_reconciliation_bars == 1
        assert chunk.reconciliation is not None
        assert chunk.reconciliation.field_difference_counts == {
            "open": 0,
            "high": 1,
            "low": 0,
            "close": 1,
            "volume": 1,
        }
        assert [
            item.field_name
            for item in chunk.reconciliation.comparisons[0].differences
        ] == ["high", "close", "volume"]
        assert chunk.reconciliation.comparisons[1].status is (
            DailyBarComparisonStatus.INSERTED
        )
        assert chunk.reconciliation.comparisons[1].trading_date == date(
            2026, 7, 2
        )
        assert chunk.reconciliation.adjusted_close_present
        assert (
            chunk.reconciliation.adjusted_close_comparisons[0]
            .difference_from_native
            == Decimal("-0.25")
        )
        assert rerun.bar_counts.unchanged == 2
        assert rerun.unchanged_reconciliation_bars == 2
        assert rerun.corrected_reconciliation_bars == 0

        with connection.cursor() as cursor:  # type: ignore[union-attr]
            cursor.execute(
                """
                SELECT trading_date, close, volume
                FROM stonks.ohlcv_daily
                WHERE provider_listing_id = %s
                ORDER BY trading_date
                """,
                (listing_id,),
            )
            rows = cursor.fetchall()
        assert rows == [
            (START_DATE, Decimal("11.5000000000"), None),
            (
                date(2026, 7, 2),
                Decimal("12.0000000000"),
                Decimal("200.00000000"),
            ),
        ]
    finally:
        connection.rollback()  # type: ignore[union-attr]
        if listing_id is not None:
            with connection.cursor() as cursor:  # type: ignore[union-attr]
                cursor.execute(
                    """
                    DELETE FROM stonks.provider_listing
                    WHERE provider_listing_id = %s
                    """,
                    (listing_id,),
                )
            connection.commit()  # type: ignore[union-attr]
