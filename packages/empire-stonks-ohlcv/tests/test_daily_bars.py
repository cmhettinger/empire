from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from empire_stonks_ohlcv import (
    DailyBar,
    DailyBarComparisonStatus,
    DailyBarWriteInput,
    OHLCVPersistenceError,
    compare_daily_bar_sources,
    upsert_daily_bars,
)
from empire_stonks_ohlcv.daily_bars import _to_database_scale


def test_daily_bar_write_input_requires_resolved_uuid_and_daily_bar() -> None:
    bar = DailyBar(
        trading_date=date(2026, 7, 15),
        open=Decimal("10"),
        high=Decimal("12"),
        low=Decimal("9"),
        close=Decimal("11"),
    )
    item = DailyBarWriteInput(provider_listing_id=uuid4(), bar=bar)

    assert item.bar is bar
    with pytest.raises(TypeError, match="provider_listing_id"):
        DailyBarWriteInput(  # type: ignore[arg-type]
            provider_listing_id="not-a-uuid",
            bar=bar,
        )
    with pytest.raises(TypeError, match="bar must be a DailyBar"):
        DailyBarWriteInput(  # type: ignore[arg-type]
            provider_listing_id=uuid4(),
            bar=object(),
        )


def test_database_scale_rounding_and_precision_boundary() -> None:
    assert _to_database_scale(
        Decimal("1.23456789005"),
        scale=Decimal("0.0000000001"),
        integer_digits=20,
    ) == Decimal("1.2345678901")

    with pytest.raises(OHLCVPersistenceError, match="numeric precision"):
        _to_database_scale(
            Decimal("1" + "0" * 20),
            scale=Decimal("0.0000000001"),
            integer_digits=20,
        )


class InactiveListingCursor:
    def __init__(self, provider_listing_id: UUID) -> None:
        self.provider_listing_id = provider_listing_id

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        assert "FROM stonks.provider_listing" in query
        assert params == (self.provider_listing_id,)

    def fetchone(self) -> tuple[UUID, None, None, str]:
        return (self.provider_listing_id, None, None, "INACTIVE")


def test_daily_bar_writer_rejects_direct_writes_to_inactive_listing() -> None:
    provider_listing_id = uuid4()
    cursor = InactiveListingCursor(provider_listing_id)
    daily_bar = DailyBar(
        trading_date=date(2026, 7, 15),
        open=Decimal("10"),
        high=Decimal("12"),
        low=Decimal("9"),
        close=Decimal("11"),
    )

    with pytest.raises(OHLCVPersistenceError, match="listing is inactive"):
        upsert_daily_bars(
            cursor=cursor,
            bars=(
                DailyBarWriteInput(
                    provider_listing_id=provider_listing_id,
                    bar=daily_bar,
                ),
            ),
        )


class ComparisonCursor:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.calls.append((query, params))

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.rows


def test_daily_bar_comparison_normalizes_and_reports_field_differences() -> None:
    provider_listing_id = UUID(int=1)
    cursor = ComparisonCursor(
        [
            (
                date(2026, 7, 1),
                Decimal("10.0000000000"),
                Decimal("12.0000000000"),
                Decimal("9.0000000000"),
                Decimal("11.0000000000"),
                Decimal("100.00000000"),
            ),
            (
                date(2026, 7, 2),
                Decimal("10.0000000000"),
                Decimal("12.0000000000"),
                Decimal("9.0000000000"),
                Decimal("11.0000000000"),
                Decimal("100.00000000"),
            ),
        ]
    )
    bars = (
        DailyBarWriteInput(
            provider_listing_id,
            DailyBar(
                date(2026, 7, 1),
                Decimal("10"),
                Decimal("12"),
                Decimal("9"),
                Decimal("11.00000000001"),
                Decimal("100"),
            ),
        ),
        DailyBarWriteInput(
            provider_listing_id,
            DailyBar(
                date(2026, 7, 2),
                Decimal("10"),
                Decimal("12.5"),
                Decimal("9"),
                Decimal("11.5"),
                None,
            ),
        ),
        DailyBarWriteInput(
            provider_listing_id,
            DailyBar(
                date(2026, 7, 3),
                Decimal("11"),
                Decimal("13"),
                Decimal("10"),
                Decimal("12"),
                Decimal("200"),
            ),
        ),
    )

    comparisons = compare_daily_bar_sources(cursor=cursor, bars=bars)

    assert [item.status for item in comparisons] == [
        DailyBarComparisonStatus.UNCHANGED,
        DailyBarComparisonStatus.CORRECTED,
        DailyBarComparisonStatus.INSERTED,
    ]
    assert [item.field_name for item in comparisons[1].differences] == [
        "high",
        "close",
        "volume",
    ]
    assert comparisons[1].differences[-1].to_dict() == {
        "field_name": "volume",
        "stored_value": "100.00000000",
        "incoming_value": None,
    }
    assert comparisons[2].differences == ()
    assert "trading_date = ANY" in cursor.calls[0][0]
