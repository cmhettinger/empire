from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from statistics import mean, stdev
from uuid import UUID

import numpy as np
import pytest

import empire_stonks_tech_indicators as public_api
from empire_stonks_tech_indicators import (
    ReturnStatisticArrays,
    SourceBar,
    TechIndicatorsCalculationError,
    calculate_return_statistics,
    calculate_returns,
    normalize_source_bars,
)
from empire_stonks_tech_indicators.arrays import MaskedFloatArray
from empire_stonks_tech_indicators import return_statistics as statistics_module


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


def _inputs(
    closes: list[str],
    *,
    gap_after: int | None = None,
):
    bars = tuple(
        _bar(
            index,
            Decimal(close),
            gap_days=3 if gap_after is not None and index > gap_after else 0,
        )
        for index, close in enumerate(closes)
    )
    calculation_arrays = normalize_source_bars(bars)
    return calculation_arrays, calculate_returns(calculation_arrays)


def _calculate(closes: list[str], *, gap_after: int | None = None):
    calculation_arrays, returns = _inputs(closes, gap_after=gap_after)
    return returns, calculate_return_statistics(calculation_arrays, returns)


def _varied_closes(count: int) -> list[str]:
    return [str(100 + index * 2 + (index % 7) ** 2) for index in range(count)]


def test_return_statistics_api_is_explicitly_exported() -> None:
    assert statistics_module.__all__ == [
        "RETURN_STATISTIC_FIELDS",
        "ReturnStatisticArrays",
        "calculate_return_statistics",
    ]
    assert statistics_module.RETURN_STATISTIC_FIELDS == (
        "return_volatility_20d_pct",
        "return_volatility_60d_pct",
        "return_1d_zscore_20d",
        "return_3d_zscore_20d",
    )
    assert public_api.ReturnStatisticArrays is ReturnStatisticArrays
    assert public_api.calculate_return_statistics is calculate_return_statistics


@pytest.mark.parametrize(
    ("field_name", "period"),
    (
        ("return_volatility_20d_pct", 20),
        ("return_volatility_60d_pct", 60),
    ),
)
def test_volatility_is_complete_trailing_sample_stddev(
    field_name: str,
    period: int,
) -> None:
    returns, statistics = _calculate(_varied_closes(90), gap_after=30)
    source = returns.return_1d_pct
    actual = getattr(statistics, field_name)

    assert actual.null_mask[:period].all()
    assert actual.value_at(period) == pytest.approx(
        stdev(source.values[1 : period + 1].tolist())
    )
    for index in range(period, returns.observation_count):
        expected_window = source.values[index - period + 1 : index + 1]
        assert actual.value_at(index) == pytest.approx(
            stdev(expected_window.tolist())
        )


@pytest.mark.parametrize(
    ("return_field", "statistic_field", "first_eligible"),
    (
        ("return_1d_pct", "return_1d_zscore_20d", 21),
        ("return_3d_pct", "return_3d_zscore_20d", 23),
    ),
)
def test_zscore_uses_previous_twenty_returns_and_excludes_current(
    return_field: str,
    statistic_field: str,
    first_eligible: int,
) -> None:
    returns, statistics = _calculate(_varied_closes(90), gap_after=30)
    source = getattr(returns, return_field)
    actual = getattr(statistics, statistic_field)

    assert actual.null_mask[:first_eligible].all()
    for index in range(first_eligible, returns.observation_count):
        reference = source.values[index - 20 : index].tolist()
        expected = (source.values[index] - mean(reference)) / stdev(reference)
        assert actual.value_at(index) == pytest.approx(expected)


def test_constant_returns_populate_zero_volatility_but_null_zscores() -> None:
    closes = [str(2**index) for index in range(70)]
    _, statistics = _calculate(closes)

    assert statistics.return_volatility_20d_pct.value_at(20) == 0.0
    assert statistics.return_volatility_60d_pct.value_at(60) == 0.0
    assert statistics.return_1d_zscore_20d.null_mask.all()
    assert statistics.return_3d_zscore_20d.null_mask.all()


def test_null_return_invalidates_only_windows_that_contain_it() -> None:
    closes = _varied_closes(50)
    closes[10] = "0"
    _, statistics = _calculate(closes)

    assert statistics.return_volatility_20d_pct.null_mask[20:31].all()
    assert statistics.return_volatility_20d_pct.value_at(31) is not None
    assert statistics.return_1d_zscore_20d.null_mask[21:32].all()
    assert statistics.return_1d_zscore_20d.value_at(32) is not None
    assert statistics.return_3d_zscore_20d.null_mask[23:34].all()
    assert statistics.return_3d_zscore_20d.value_at(34) is not None


def test_results_are_read_only_contiguous_and_have_exact_masks() -> None:
    _, statistics = _calculate(_varied_closes(70))

    assert statistics.observation_count == 70
    for field_name in statistics_module.RETURN_STATISTIC_FIELDS:
        series = getattr(statistics, field_name)
        assert series.values.dtype == np.dtype("float64")
        assert series.values.flags.c_contiguous
        assert not series.values.flags.writeable
        assert series.null_mask.dtype == np.dtype("bool")
        assert series.null_mask.flags.c_contiguous
        assert not series.null_mask.flags.writeable
        assert np.isnan(series.values[series.null_mask]).all()


def test_prefix_results_do_not_depend_on_future_observations() -> None:
    closes = _varied_closes(90)
    _, full = _calculate(closes)
    _, prefix = _calculate(closes[:50])

    for field_name in statistics_module.RETURN_STATISTIC_FIELDS:
        full_series = getattr(full, field_name)
        prefix_series = getattr(prefix, field_name)
        np.testing.assert_array_equal(prefix_series.values, full_series.values[:50])
        np.testing.assert_array_equal(
            prefix_series.null_mask,
            full_series.null_mask[:50],
        )


def test_return_inputs_must_match_source_and_calculated_values() -> None:
    calculation_arrays, returns = _inputs(_varied_closes(30))
    other_calculation_arrays, other_returns = _inputs(_varied_closes(31))

    with pytest.raises(TechIndicatorsCalculationError, match="normalized source"):
        calculate_return_statistics(calculation_arrays, other_returns)

    values = returns.return_1d_pct.values.copy()
    values[5] += 0.25
    values.setflags(write=False)
    tampered = replace(
        returns,
        return_1d_pct=MaskedFloatArray(
            values=values,
            null_mask=returns.return_1d_pct.null_mask,
        ),
    )
    with pytest.raises(TechIndicatorsCalculationError, match="return_1d_pct"):
        calculate_return_statistics(calculation_arrays, tampered)

    assert other_calculation_arrays.observation_count == 31


def test_nonfinite_sample_statistic_fails_calculation() -> None:
    closes = ["1e-300" if index % 2 == 0 else "1" for index in range(22)]
    calculation_arrays, returns = _inputs(closes)

    with pytest.raises(
        TechIndicatorsCalculationError,
        match="return_volatility_20d_pct.*observation 20",
    ):
        calculate_return_statistics(calculation_arrays, returns)


def test_calculate_return_statistics_rejects_wrong_input_types() -> None:
    calculation_arrays, returns = _inputs(_varied_closes(30))

    with pytest.raises(TypeError, match="CalculationArrays"):
        calculate_return_statistics(object(), returns)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="ReturnArrays"):
        calculate_return_statistics(  # type: ignore[arg-type]
            calculation_arrays,
            object(),
        )
