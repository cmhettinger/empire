from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import numpy as np
import pytest

import empire_stonks_tech_indicators as public_api
from empire_stonks_tech_indicators import (
    ReturnArrays,
    SourceBar,
    TechIndicatorsCalculationError,
    calculate_returns,
    normalize_source_bars,
)
from empire_stonks_tech_indicators import returns as returns_module


LISTING_ID = UUID("00000000-0000-4000-8000-000000000001")


def _bar(index: int, close: Decimal, *, gap_days: int = 0) -> SourceBar:
    return SourceBar(
        provider_listing_id=LISTING_ID,
        trading_date=date(2020, 1, 1) + timedelta(days=index + gap_days),
        open=close,
        high=close + Decimal("1"),
        low=close - Decimal("1"),
        close=close,
        volume=Decimal("100"),
    )


def _calculate(closes: list[str], *, gap_after: int | None = None) -> ReturnArrays:
    bars = tuple(
        _bar(
            index,
            Decimal(close),
            gap_days=3 if gap_after is not None and index > gap_after else 0,
        )
        for index, close in enumerate(closes)
    )
    return calculate_returns(normalize_source_bars(bars))


def test_return_api_is_explicitly_exported() -> None:
    assert returns_module.__all__ == [
        "RETURN_FIELDS",
        "RETURN_PERIODS",
        "ReturnArrays",
        "calculate_returns",
    ]
    assert public_api.ReturnArrays is ReturnArrays
    assert public_api.calculate_returns is calculate_returns


@pytest.mark.parametrize(
    ("field_name", "period"),
    returns_module.RETURN_FIELDS,
)
def test_each_return_warms_up_then_uses_exact_observation_lag(
    field_name: str,
    period: int,
) -> None:
    closes = [str(index + 1) for index in range(253)]
    returns = _calculate(closes, gap_after=100)
    series = getattr(returns, field_name)

    assert series.null_mask[:period].all()
    assert np.isnan(series.values[:period]).all()
    assert series.value_at(period - 1) is None
    assert series.value_at(period) == pytest.approx(
        float(Decimal(period + 1) / Decimal(1) - Decimal(1))
    )
    assert not series.null_mask[period:].any()


def test_zero_negative_tiny_and_unchanged_denominators() -> None:
    returns = _calculate(["0", "2", "0", "-2", "-1", "-1", "1e-300", "1"])
    one_day = returns.return_1d_pct

    assert one_day.value_at(0) is None
    assert one_day.value_at(1) is None
    assert one_day.value_at(2) == -1.0
    assert one_day.value_at(3) is None
    assert one_day.value_at(4) == -0.5
    assert one_day.value_at(5) == 0.0
    assert one_day.value_at(6) == pytest.approx(-1.0)
    assert one_day.value_at(7) == pytest.approx(1e300 - 1.0)


def test_zero_denominator_does_not_poison_later_eligible_returns() -> None:
    returns = _calculate(["1", "0", "3", "6"])

    assert returns.return_1d_pct.null_mask.tolist() == [True, False, True, False]
    assert returns.return_1d_pct.value_at(1) == -1.0
    assert returns.return_1d_pct.value_at(3) == 1.0
    assert returns.return_2d_pct.null_mask.tolist() == [True, True, False, True]
    assert returns.return_2d_pct.value_at(2) == 2.0


def test_calendar_gap_remains_one_observation_lag() -> None:
    returns = _calculate(["10", "15"], gap_after=0)

    assert returns.observation_count == 2
    assert returns.return_1d_pct.value_at(1) == 0.5


def test_return_arrays_are_read_only_contiguous_float64_with_boolean_masks() -> None:
    returns = _calculate(["1", "2", "4"])

    assert returns.observation_count == 3
    assert tuple(bar.close for bar in returns.source_bars) == (
        Decimal("1"),
        Decimal("2"),
        Decimal("4"),
    )
    for field_name, _ in returns_module.RETURN_FIELDS:
        series = getattr(returns, field_name)
        assert series.values.dtype == np.dtype("float64")
        assert series.values.flags.c_contiguous
        assert not series.values.flags.writeable
        assert series.null_mask.dtype == np.dtype("bool")
        assert series.null_mask.flags.c_contiguous
        assert not series.null_mask.flags.writeable
        with pytest.raises(ValueError, match="read-only"):
            series.values[0] = 0.0


def test_prefix_results_are_independent_of_future_observations() -> None:
    closes = [str(index * index + 1) for index in range(80)]
    full = _calculate(closes)
    prefix = _calculate(closes[:40])

    for field_name, _ in returns_module.RETURN_FIELDS:
        full_series = getattr(full, field_name)
        prefix_series = getattr(prefix, field_name)
        np.testing.assert_array_equal(
            prefix_series.values,
            full_series.values[:40],
        )
        np.testing.assert_array_equal(
            prefix_series.null_mask,
            full_series.null_mask[:40],
        )


def test_nonfinite_finite_input_result_fails_calculation() -> None:
    calculation_arrays = normalize_source_bars(
        (_bar(0, Decimal("1e-320")), _bar(1, Decimal("1")))
    )

    with pytest.raises(
        TechIndicatorsCalculationError,
        match="return_1d_pct.*observation 1",
    ):
        calculate_returns(calculation_arrays)


def test_calculate_returns_rejects_wrong_input_type() -> None:
    with pytest.raises(TypeError, match="CalculationArrays"):
        calculate_returns(object())  # type: ignore[arg-type]
