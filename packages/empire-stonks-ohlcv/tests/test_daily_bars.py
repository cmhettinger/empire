from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from empire_stonks_ohlcv import DailyBar, DailyBarWriteInput, OHLCVPersistenceError
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
