from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from empire_stonks_ohlcv import (
    DailyBar,
    DailyBarWriteInput,
    OHLCVPersistenceError,
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
