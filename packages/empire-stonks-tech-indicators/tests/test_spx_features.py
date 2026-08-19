from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import numpy as np
import pytest

import empire_stonks_tech_indicators as public_api
from empire_stonks_tech_indicators import (
    BenchmarkHistory,
    EligibleListing,
    ReasonCount,
    ResolvedBenchmark,
    SourceBar,
    SpxFeatureArrays,
    TechIndicatorsValidationError,
    calculate_spx_features,
    is_spx_supported_subject,
    normalize_source_bars,
)
from empire_stonks_tech_indicators import spx_features as features_module


SUBJECT_ID = UUID("00000000-0000-4000-8000-000000000001")
OTHER_ID = UUID("00000000-0000-4000-8000-000000000003")
SPX_ID = UUID("00000000-0000-4000-8000-000000000002")
START_DATE = date(2020, 1, 1)


def _bar(listing_id: UUID, index: int, close: Decimal) -> SourceBar:
    return SourceBar(
        provider_listing_id=listing_id,
        trading_date=START_DATE + timedelta(days=index),
        open=close,
        high=close + Decimal("1"),
        low=close - Decimal("1"),
        close=close,
        volume=Decimal("100"),
    )


def _listing(
    provider_code: str,
    market: str,
    *,
    instrument_type_code: str = "UNKNOWN",
    ticker: str = "TEST",
    listing_id: UUID = SUBJECT_ID,
    observation_count: int = 3,
) -> EligibleListing:
    return EligibleListing(
        provider_listing_id=listing_id,
        provider_code=provider_code,
        market=market,
        ticker=ticker,
        instrument_type_code=instrument_type_code,
        status="ACTIVE",
        first_trading_date=START_DATE,
        last_trading_date=START_DATE + timedelta(days=observation_count - 1),
        source_observation_count=observation_count,
    )


def _arrays(
    listing_id: UUID = SUBJECT_ID,
    *,
    observation_count: int = 3,
    multiplier: Decimal = Decimal("1"),
):
    return normalize_source_bars(
        _bar(
            listing_id,
            index,
            multiplier * Decimal(index * index + 100),
        )
        for index in range(observation_count)
    )


def _benchmark(observation_count: int = 3) -> BenchmarkHistory:
    benchmark = ResolvedBenchmark(provider_listing_id=SPX_ID)
    return BenchmarkHistory(
        benchmark=benchmark,
        bars=tuple(
            _bar(SPX_ID, index, Decimal(index * index + 100))
            for index in range(observation_count)
        ),
    )


def test_spx_feature_api_is_explicitly_exported() -> None:
    assert features_module.__all__ == [
        "SPX_FEATURE_FIELDS",
        "SPX_SUPPORTED_SUBJECT_MARKETS",
        "SUBJECT_UNSUPPORTED_REASON",
        "SpxFeatureArrays",
        "calculate_spx_features",
        "is_spx_supported_subject",
    ]
    assert len(features_module.SPX_FEATURE_FIELDS) == 11
    assert len(set(features_module.SPX_FEATURE_FIELDS)) == 11
    assert features_module.SUBJECT_UNSUPPORTED_REASON == "SUBJECT_UNSUPPORTED"
    assert public_api.SpxFeatureArrays is SpxFeatureArrays
    assert public_api.calculate_spx_features is calculate_spx_features
    assert public_api.is_spx_supported_subject is is_spx_supported_subject


@pytest.mark.parametrize(
    ("provider_code", "market"),
    [
        ("EODDATA", "NYSE"),
        ("EODDATA", "NASDAQ"),
        ("EODDATA", "AMEX"),
        ("STOOQ", "nasdaq"),
        ("STOOQ", "nyse"),
        ("STOOQ", "nysemkt"),
    ],
)
def test_exact_approved_cash_equity_cohorts_are_supported(
    provider_code: str,
    market: str,
) -> None:
    assert is_spx_supported_subject(_listing(provider_code, market)) is True


@pytest.mark.parametrize(
    ("provider_code", "market", "instrument_type_code", "ticker"),
    [
        ("YAHOO", "XIDX", "EQUITY_INDEX", "SPX"),
        ("YAHOO", "XIDX", "EQUITY_INDEX", "FTSE"),
        ("YAHOO", "XIDX", "CONTINUOUS_FUTURE_EQUITY", "ES"),
        ("YAHOO", "XIDX", "COMMODITY_INDEX", "GSCI"),
        ("YAHOO", "XIDX", "CURRENCY_INDEX", "DXY"),
        ("YAHOO", "XIDX", "CONTINUOUS_FUTURE_COMMODITY", "WTI"),
        ("EODDATA", "nyse", "UNKNOWN", "TEST"),
        ("STOOQ", "NYSE", "UNKNOWN", "TEST"),
        ("OTHER", "NYSE", "EQUITY", "TEST"),
    ],
)
def test_global_index_future_commodity_and_currency_subjects_are_unsupported(
    provider_code: str,
    market: str,
    instrument_type_code: str,
    ticker: str,
) -> None:
    listing = _listing(
        provider_code,
        market,
        instrument_type_code=instrument_type_code,
        ticker=ticker,
    )

    assert is_spx_supported_subject(listing) is False


def test_unsupported_subject_gets_exactly_11_null_fields_and_bounded_reason() -> None:
    listing = _listing(
        "YAHOO",
        "XIDX",
        instrument_type_code="EQUITY_INDEX",
        ticker="SPX",
    )
    result = calculate_spx_features(
        _arrays(),
        subject=listing,
        benchmark_history=_benchmark(),
    )

    assert result.supported_subject is False
    assert result.benchmark_provider_listing_id is None
    assert result.reason_counts == (
        ReasonCount(code="SUBJECT_UNSUPPORTED", count=3),
    )
    assert result.observation_count == 3
    for field_name in features_module.SPX_FEATURE_FIELDS:
        series = getattr(result, field_name)
        assert series.null_mask.all()
        assert np.isnan(series.values).all()
        assert not series.values.flags.writeable
        assert not series.null_mask.flags.writeable


@pytest.mark.parametrize(
    ("provider_code", "market"),
    [("EODDATA", "NYSE"), ("STOOQ", "nyse")],
)
def test_supported_subject_composes_all_11_feature_families(
    provider_code: str,
    market: str,
) -> None:
    observation_count = 260
    listing = _listing(
        provider_code,
        market,
        observation_count=observation_count,
    )
    result = calculate_spx_features(
        _arrays(
            observation_count=observation_count,
            multiplier=Decimal("2"),
        ),
        subject=listing,
        benchmark_history=_benchmark(observation_count),
    )

    assert result.supported_subject is True
    assert result.benchmark_provider_listing_id == SPX_ID
    assert result.reason_counts == ()
    for field_name in features_module.SPX_FEATURE_FIELDS:
        assert getattr(result, field_name).value_at(259) is not None
    assert result.rel_spx.value_at(0) == pytest.approx(2.0)
    assert result.pct_rel_spx_20.value_at(19) == pytest.approx(0.0)
    assert result.relative_return_spx_252d_pct.value_at(252) == pytest.approx(0.0)
    assert result.spx_beta_252d.value_at(252) == pytest.approx(1.0)
    assert result.spx_correlation_252d.value_at(252) == pytest.approx(1.0)


def test_supported_subject_requires_benchmark_history() -> None:
    with pytest.raises(
        TechIndicatorsValidationError,
        match="benchmark history is required",
    ):
        calculate_spx_features(
            _arrays(),
            subject=_listing("EODDATA", "NYSE"),
        )


def test_calculation_arrays_must_belong_to_subject() -> None:
    with pytest.raises(ValueError, match="belong to the subject"):
        calculate_spx_features(
            _arrays(OTHER_ID),
            subject=_listing("EODDATA", "NYSE"),
            benchmark_history=_benchmark(),
        )


def test_spx_feature_boundary_rejects_wrong_types() -> None:
    listing = _listing("EODDATA", "NYSE")
    arrays = _arrays()
    with pytest.raises(TypeError, match="CalculationArrays"):
        calculate_spx_features(  # type: ignore[arg-type]
            object(),
            subject=listing,
        )
    with pytest.raises(TypeError, match="EligibleListing"):
        calculate_spx_features(  # type: ignore[arg-type]
            arrays,
            subject=object(),
        )
    with pytest.raises(TypeError, match="BenchmarkHistory or None"):
        calculate_spx_features(
            arrays,
            subject=listing,
            benchmark_history=object(),  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="EligibleListing"):
        is_spx_supported_subject(object())  # type: ignore[arg-type]
