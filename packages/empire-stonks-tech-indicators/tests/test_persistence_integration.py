from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterator
from uuid import UUID, uuid4

import pytest

from empire_stonks_tech_indicators import (
    FeatureRow,
    FeatureRowKey,
    SlotWriteCounts,
    SourceBar,
    TechIndicatorsPayloadSlot,
    copy_feature_rows_between_slots,
    upsert_feature_rows,
)


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


def _insert_source_bar(cursor: object) -> tuple[UUID, date]:
    ticker = f"W73{uuid4().hex[:12].upper()}"
    cursor.execute(  # type: ignore[union-attr]
        """
        INSERT INTO stonks.provider_listing (
            provider_code,
            market,
            ticker,
            status
        )
        VALUES ('EODDATA', 'US', %s, 'ACTIVE')
        RETURNING provider_listing_id
        """,
        (ticker,),
    )
    provider_listing_id = cursor.fetchone()[0]  # type: ignore[union-attr]
    trading_date = date(2026, 8, 21)
    cursor.execute(  # type: ignore[union-attr]
        """
        INSERT INTO stonks.ohlcv_daily (
            provider_listing_id,
            trading_date,
            open,
            high,
            low,
            close,
            volume,
            change,
            changepct,
            typ,
            hl_range,
            oc_range
        )
        VALUES (%s, %s, 10, 12, 9, 11, 100, NULL, NULL, 10.66666667, 3, 1)
        """,
        (provider_listing_id, trading_date),
    )
    return provider_listing_id, trading_date


def _row(
    *,
    provider_listing_id: UUID,
    trading_date: date,
    calculated_at: datetime,
    return_1d_pct: float | None,
) -> FeatureRow:
    return FeatureRow(
        source=SourceBar(
            provider_listing_id=provider_listing_id,
            trading_date=trading_date,
            open=Decimal("10"),
            high=Decimal("12"),
            low=Decimal("9"),
            close=Decimal("11"),
            volume=Decimal("100"),
        ),
        history_observation_count=1,
        calculation_version="TECH_INDICATORS_V1",
        calculated_at=calculated_at,
        return_1d_pct=return_1d_pct,
    )


def test_slot_upsert_and_exact_copy_against_postgresql(
    database_connection: object,
) -> None:
    cursor = database_connection.cursor()  # type: ignore[union-attr]
    provider_listing_id, trading_date = _insert_source_bar(cursor)
    first_calculated_at = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
    first = _row(
        provider_listing_id=provider_listing_id,
        trading_date=trading_date,
        calculated_at=first_calculated_at,
        return_1d_pct=0.25,
    )

    assert upsert_feature_rows(
        cursor=cursor,
        slot=TechIndicatorsPayloadSlot.A,
        rows=(first,),
    ) == SlotWriteCounts(inserted_rows=1)
    cursor.execute(  # type: ignore[union-attr]
        """
        SELECT calculated_at, created_at, updated_at, intraday_return_1d_pct
        FROM stonks.ohlcv_daily_tech_indicators_a
        WHERE provider_listing_id = %s AND trading_date = %s
        """,
        (provider_listing_id, trading_date),
    )
    stored_calculated_at, created_at, inserted_updated_at, intraday_return = (
        cursor.fetchone()  # type: ignore[union-attr]
    )
    assert stored_calculated_at == first_calculated_at
    assert intraday_return == pytest.approx(0.1)

    equivalent = _row(
        provider_listing_id=provider_listing_id,
        trading_date=trading_date,
        calculated_at=first_calculated_at + timedelta(hours=1),
        return_1d_pct=0.25 + 5e-13,
    )
    assert upsert_feature_rows(
        cursor=cursor,
        slot=TechIndicatorsPayloadSlot.A,
        rows=(equivalent,),
    ) == SlotWriteCounts(unchanged_rows=1)
    cursor.execute(  # type: ignore[union-attr]
        """
        SELECT calculated_at, created_at, updated_at, return_1d_pct
        FROM stonks.ohlcv_daily_tech_indicators_a
        WHERE provider_listing_id = %s AND trading_date = %s
        """,
        (provider_listing_id, trading_date),
    )
    assert cursor.fetchone() == (  # type: ignore[union-attr]
        stored_calculated_at,
        created_at,
        inserted_updated_at,
        0.25,
    )

    changed_calculated_at = first_calculated_at + timedelta(hours=2)
    changed = _row(
        provider_listing_id=provider_listing_id,
        trading_date=trading_date,
        calculated_at=changed_calculated_at,
        return_1d_pct=0.5,
    )
    assert upsert_feature_rows(
        cursor=cursor,
        slot=TechIndicatorsPayloadSlot.A,
        rows=(changed,),
    ) == SlotWriteCounts(updated_rows=1)
    cursor.execute(  # type: ignore[union-attr]
        """
        SELECT calculated_at, created_at, updated_at, return_1d_pct
        FROM stonks.ohlcv_daily_tech_indicators_a
        WHERE provider_listing_id = %s AND trading_date = %s
        """,
        (provider_listing_id, trading_date),
    )
    assert cursor.fetchone() == (  # type: ignore[union-attr]
        changed_calculated_at,
        created_at,
        changed_calculated_at,
        0.5,
    )

    key = FeatureRowKey(provider_listing_id, trading_date)
    assert copy_feature_rows_between_slots(
        cursor=cursor,
        source_slot=TechIndicatorsPayloadSlot.A,
        target_slot=TechIndicatorsPayloadSlot.B,
        keys=(key,),
    ) == SlotWriteCounts(unchanged_rows=1)
    cursor.execute(  # type: ignore[union-attr]
        """
        SELECT calculated_at, created_at, updated_at, return_1d_pct
        FROM stonks.ohlcv_daily_tech_indicators_b
        WHERE provider_listing_id = %s AND trading_date = %s
        """,
        (provider_listing_id, trading_date),
    )
    assert cursor.fetchone() == (  # type: ignore[union-attr]
        changed_calculated_at,
        created_at,
        changed_calculated_at,
        0.5,
    )
    assert copy_feature_rows_between_slots(
        cursor=cursor,
        source_slot=TechIndicatorsPayloadSlot.A,
        target_slot=TechIndicatorsPayloadSlot.B,
        keys=(key,),
    ) == SlotWriteCounts(unchanged_rows=1)
