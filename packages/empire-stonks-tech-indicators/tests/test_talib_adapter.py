from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import numpy as np
import pytest
import talib

import empire_stonks_tech_indicators as public_api
from empire_stonks_tech_indicators import (
    CalculationArrays,
    MaskedFloatArray,
    SourceBar,
    TALibAdapter,
    TALibRuntimeInfo,
    TechIndicatorsCalculationError,
    normalize_source_bars,
)
from empire_stonks_tech_indicators import talib_adapter as adapter_module


LISTING_ID = UUID("00000000-0000-4000-8000-000000000001")


def _arrays(observation_count: int = 80) -> CalculationArrays:
    first_date = date(2026, 1, 1)
    bars = []
    for index in range(observation_count):
        close = Decimal("100") + Decimal(index) + Decimal(index % 7) / 10
        bars.append(
            SourceBar(
                provider_listing_id=LISTING_ID,
                trading_date=first_date + timedelta(days=index),
                open=close - Decimal("0.25"),
                high=close + Decimal("1.25"),
                low=close - Decimal("1.50"),
                close=close,
                volume=Decimal("1000") + index,
            )
        )
    return normalize_source_bars(bars)


def test_adapter_api_is_explicit_and_records_exact_runtime() -> None:
    adapter = TALibAdapter(_arrays())

    assert adapter_module.__all__ == ["TALibAdapter", "TALibRuntimeInfo"]
    assert public_api.TALibAdapter is TALibAdapter
    assert public_api.TALibRuntimeInfo is TALibRuntimeInfo
    assert adapter.runtime == TALibRuntimeInfo(
        library_name="TA-Lib",
        python_wrapper_version="0.7.1",
        c_library_version="0.7.1",
        numpy_version="2.4.6",
        compatibility="DEFAULT",
        unstable_period=0,
    )
    assert adapter.runtime.as_dict() == {
        "library_name": "TA-Lib",
        "python_wrapper_version": "0.7.1",
        "c_library_version": "0.7.1",
        "numpy_version": "2.4.6",
        "compatibility": "DEFAULT",
        "unstable_period": 0,
    }


@pytest.mark.parametrize(
    ("calculate", "first_valid_index"),
    [
        (lambda adapter: adapter.sma(timeperiod=20), 19),
        (lambda adapter: adapter.ema(timeperiod=20), 19),
        (lambda adapter: adapter.rsi(timeperiod=14), 14),
        (lambda adapter: adapter.atr(timeperiod=14), 14),
        (lambda adapter: adapter.stddev(timeperiod=20, nbdev=1.0), 19),
        (lambda adapter: adapter.plus_di(timeperiod=14), 14),
        (lambda adapter: adapter.minus_di(timeperiod=14), 14),
        (lambda adapter: adapter.adx(timeperiod=14), 27),
    ],
)
def test_single_output_calls_return_empire_masks(
    calculate,
    first_valid_index: int,
) -> None:
    result = calculate(TALibAdapter(_arrays()))

    assert type(result) is MaskedFloatArray
    np.testing.assert_array_equal(
        result.null_mask,
        np.arange(80) < first_valid_index,
    )
    assert np.isnan(result.values[:first_valid_index]).all()
    assert np.isfinite(result.values[first_valid_index:]).all()
    assert result.values.flags.c_contiguous
    assert not result.values.flags.writeable
    assert not result.null_mask.flags.writeable


def test_macd_returns_three_empire_arrays_with_one_documented_prefix() -> None:
    results = TALibAdapter(_arrays()).macd(
        fastperiod=12,
        slowperiod=26,
        signalperiod=9,
    )

    assert type(results) is tuple
    assert len(results) == 3
    for result in results:
        assert type(result) is MaskedFloatArray
        np.testing.assert_array_equal(result.null_mask, np.arange(80) < 33)
        assert np.isfinite(result.values[33:]).all()


def test_short_history_is_an_all_null_documented_warmup() -> None:
    result = TALibAdapter(_arrays(10)).sma(timeperiod=20)

    assert result.null_mask.all()
    assert np.isnan(result.values).all()


def test_nonfinite_warmup_values_are_normalized_without_exposing_library_array(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    library_output = np.arange(8, dtype=np.float64)
    library_output[:3] = [np.nan, np.inf, -np.inf]
    monkeypatch.setattr(
        adapter_module._talib,
        "SMA",
        lambda *_args, **_kwargs: library_output,
    )

    result = TALibAdapter(_arrays(8)).sma(timeperiod=4)

    np.testing.assert_array_equal(
        result.null_mask,
        [True, True, True, False, False, False, False, False],
    )
    assert np.isnan(result.values[:3]).all()
    assert result.values is not library_output
    assert library_output[1] == np.inf


def test_finite_warmup_or_nonfinite_populated_output_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    finite_prefix = np.arange(8, dtype=np.float64)
    monkeypatch.setattr(
        adapter_module._talib,
        "SMA",
        lambda *_args, **_kwargs: finite_prefix,
    )
    with pytest.raises(TechIndicatorsCalculationError, match="warm-up prefix"):
        TALibAdapter(_arrays(8)).sma(timeperiod=4)

    invalid_populated = np.arange(8, dtype=np.float64)
    invalid_populated[:3] = np.nan
    invalid_populated[5] = np.inf
    monkeypatch.setattr(
        adapter_module._talib,
        "SMA",
        lambda *_args, **_kwargs: invalid_populated,
    )
    with pytest.raises(
        TechIndicatorsCalculationError,
        match="non-finite value at observation 5",
    ):
        TALibAdapter(_arrays(8)).sma(timeperiod=4)


def test_library_failures_are_hidden_behind_package_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args, **_kwargs):
        raise RuntimeError("library detail")

    monkeypatch.setattr(adapter_module._talib, "SMA", fail)

    with pytest.raises(TechIndicatorsCalculationError) as raised:
        TALibAdapter(_arrays()).sma(timeperiod=20)

    assert str(raised.value) == "TA-Lib SMA calculation failed."
    assert raised.value.__cause__ is None
    assert "library detail" not in str(raised.value)


def test_adapter_rejects_changed_process_global_settings() -> None:
    adapter = TALibAdapter(_arrays())
    try:
        talib.set_compatibility(1)
        with pytest.raises(TechIndicatorsCalculationError, match="DEFAULT"):
            adapter.sma(timeperiod=20)
    finally:
        talib.set_compatibility(0)

    try:
        talib.set_unstable_period("EMA", 2)
        with pytest.raises(
            TechIndicatorsCalculationError,
            match="unstable periods",
        ):
            adapter.ema(timeperiod=20)
    finally:
        talib.set_unstable_period("EMA", 0)


@pytest.mark.parametrize("timeperiod", [True, 1, 1.5])
def test_invalid_parameters_fail_before_the_library(timeperiod: object) -> None:
    with pytest.raises(ValueError, match="timeperiod"):
        TALibAdapter(_arrays()).sma(timeperiod=timeperiod)  # type: ignore[arg-type]


def test_adapter_accepts_only_normalized_arrays_and_hides_talib_objects() -> None:
    with pytest.raises(TypeError, match="CalculationArrays"):
        TALibAdapter(object())  # type: ignore[arg-type]

    adapter = TALibAdapter(_arrays())
    assert all(
        not type(value).__module__.startswith("talib")
        for value in vars(adapter).values()
    )
