from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import numpy as np
import pytest

from empire_stonks_tech_indicators import (
    BenchmarkHistory,
    EligibleListing,
    ResolvedBenchmark,
    SourceBar,
    SpxFeatureArrays,
    calculate_spx_features,
    normalize_source_bars,
)
from empire_stonks_tech_indicators.spx_features import SPX_FEATURE_FIELDS


SUBJECT_ID = UUID("00000000-0000-4000-8000-000000000001")
UNRELATED_ID = UUID("00000000-0000-4000-8000-000000000003")
UNSUPPORTED_ID = UUID("00000000-0000-4000-8000-000000000004")
SPX_ID = UUID("00000000-0000-4000-8000-000000000002")
START_DATE = date(2020, 1, 1)
OBSERVATION_COUNT = 300


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


def _subject_close(index: int) -> Decimal:
    return Decimal(index * index + 3 * index + 500)


def _spx_close(index: int) -> Decimal:
    return Decimal(index * index + index + 1000)


def _listing(
    listing_id: UUID = SUBJECT_ID,
    *,
    provider_code: str = "EODDATA",
    market: str = "NYSE",
    ticker: str = "TEST",
    start_index: int = 0,
    observation_count: int = OBSERVATION_COUNT,
    instrument_type_code: str = "UNKNOWN",
) -> EligibleListing:
    return EligibleListing(
        provider_listing_id=listing_id,
        provider_code=provider_code,
        market=market,
        ticker=ticker,
        instrument_type_code=instrument_type_code,
        status="ACTIVE",
        first_trading_date=START_DATE + timedelta(days=start_index),
        last_trading_date=(
            START_DATE + timedelta(days=start_index + observation_count - 1)
        ),
        source_observation_count=observation_count,
    )


def _subject_arrays(
    listing_id: UUID = SUBJECT_ID,
    *,
    start_index: int = 0,
    observation_count: int = OBSERVATION_COUNT,
):
    return normalize_source_bars(
        _bar(listing_id, index, _subject_close(index))
        for index in range(start_index, start_index + observation_count)
    )


def _benchmark(
    *,
    excluded_indices: frozenset[int] = frozenset(),
    changed_closes: dict[int, Decimal] | None = None,
) -> BenchmarkHistory:
    overrides = {} if changed_closes is None else changed_closes
    return BenchmarkHistory(
        benchmark=ResolvedBenchmark(provider_listing_id=SPX_ID),
        bars=tuple(
            _bar(SPX_ID, index, overrides.get(index, _spx_close(index)))
            for index in range(OBSERVATION_COUNT)
            if index not in excluded_indices
        ),
    )


def _calculate(
    benchmark: BenchmarkHistory,
    *,
    listing: EligibleListing | None = None,
    arrays=None,
) -> SpxFeatureArrays:
    resolved_listing = _listing() if listing is None else listing
    resolved_arrays = _subject_arrays() if arrays is None else arrays
    return calculate_spx_features(
        resolved_arrays,
        subject=resolved_listing,
        benchmark_history=benchmark,
    )


def _assert_prefix_unchanged(
    before: SpxFeatureArrays,
    after: SpxFeatureArrays,
    start_index: int,
) -> None:
    for field_name in SPX_FEATURE_FIELDS:
        before_series = getattr(before, field_name)
        after_series = getattr(after, field_name)
        np.testing.assert_array_equal(
            before_series.values[:start_index],
            after_series.values[:start_index],
        )
        np.testing.assert_array_equal(
            before_series.null_mask[:start_index],
            after_series.null_mask[:start_index],
        )


def _assert_suffix_replacement_matches_rebuild(
    before: SpxFeatureArrays,
    rebuilt: SpxFeatureArrays,
    start_index: int,
) -> None:
    for field_name in SPX_FEATURE_FIELDS:
        before_series = getattr(before, field_name)
        rebuilt_series = getattr(rebuilt, field_name)
        suffix_values = before_series.values.copy()
        suffix_mask = before_series.null_mask.copy()
        suffix_values[start_index:] = rebuilt_series.values[start_index:]
        suffix_mask[start_index:] = rebuilt_series.null_mask[start_index:]
        np.testing.assert_array_equal(suffix_values, rebuilt_series.values)
        np.testing.assert_array_equal(suffix_mask, rebuilt_series.null_mask)


def _assert_output_equal(left: SpxFeatureArrays, right: SpxFeatureArrays) -> None:
    assert left.benchmark_provider_listing_id == right.benchmark_provider_listing_id
    assert left.reason_counts == right.reason_counts
    for field_name in SPX_FEATURE_FIELDS:
        left_series = getattr(left, field_name)
        right_series = getattr(right, field_name)
        np.testing.assert_array_equal(left_series.values, right_series.values)
        np.testing.assert_array_equal(
            left_series.null_mask,
            right_series.null_mask,
        )


def _assert_correction_changes_output(
    before: SpxFeatureArrays,
    after: SpxFeatureArrays,
    start_index: int,
) -> None:
    changed = False
    for field_name in SPX_FEATURE_FIELDS:
        before_series = getattr(before, field_name)
        after_series = getattr(after, field_name)
        if not np.array_equal(
            before_series.null_mask[start_index:],
            after_series.null_mask[start_index:],
        ):
            changed = True
            break
        populated = ~before_series.null_mask[start_index:]
        if not np.array_equal(
            before_series.values[start_index:][populated],
            after_series.values[start_index:][populated],
        ):
            changed = True
            break
    assert changed, "benchmark correction fixture must change SPX output"


def test_inserted_spx_bar_rebuilds_from_inserted_subject_date() -> None:
    correction_index = 100
    missing = _calculate(
        _benchmark(excluded_indices=frozenset({correction_index}))
    )
    inserted = _calculate(_benchmark())

    _assert_prefix_unchanged(missing, inserted, correction_index)
    _assert_suffix_replacement_matches_rebuild(
        missing,
        inserted,
        correction_index,
    )
    _assert_correction_changes_output(missing, inserted, correction_index)
    assert missing.rel_spx.value_at(correction_index) is None
    assert inserted.rel_spx.value_at(correction_index) is not None


def test_changed_spx_close_rebuilds_from_correction_date() -> None:
    correction_index = 100
    before = _calculate(_benchmark())
    corrected = _calculate(
        _benchmark(
            changed_closes={
                correction_index: _spx_close(correction_index)
                * Decimal("1.125")
            }
        )
    )

    _assert_prefix_unchanged(before, corrected, correction_index)
    _assert_suffix_replacement_matches_rebuild(
        before,
        corrected,
        correction_index,
    )
    _assert_correction_changes_output(before, corrected, correction_index)
    assert before.source_bars == corrected.source_bars


@pytest.mark.parametrize("deletion_index", [0, 100, OBSERVATION_COUNT - 1])
def test_first_middle_and_final_spx_deletions_rebuild_required_suffix(
    deletion_index: int,
) -> None:
    before = _calculate(_benchmark())
    deleted = _calculate(
        _benchmark(excluded_indices=frozenset({deletion_index}))
    )

    _assert_prefix_unchanged(before, deleted, deletion_index)
    _assert_suffix_replacement_matches_rebuild(before, deleted, deletion_index)
    _assert_correction_changes_output(before, deleted, deletion_index)
    for field_name in SPX_FEATURE_FIELDS:
        assert getattr(deleted, field_name).value_at(deletion_index) is None


def test_missing_current_spx_date_nulls_all_fields_without_filling() -> None:
    missing_index = 150
    result = _calculate(
        _benchmark(excluded_indices=frozenset({missing_index}))
    )

    assert result.benchmark_provider_listing_id == SPX_ID
    for field_name in SPX_FEATURE_FIELDS:
        assert getattr(result, field_name).value_at(missing_index) is None
    assert result.rel_spx.value_at(missing_index - 1) is not None
    assert result.rel_spx.value_at(missing_index + 1) is not None


def test_benchmark_correction_does_not_mutate_unrelated_supported_coverage() -> None:
    correction_index = 100
    listing = _listing(
        UNRELATED_ID,
        ticker="LATE",
        start_index=200,
        observation_count=100,
    )
    arrays = _subject_arrays(
        UNRELATED_ID,
        start_index=200,
        observation_count=100,
    )
    before = _calculate(_benchmark(), listing=listing, arrays=arrays)
    corrected = _calculate(
        _benchmark(
            changed_closes={
                correction_index: _spx_close(correction_index)
                * Decimal("1.125")
            }
        ),
        listing=listing,
        arrays=arrays,
    )

    _assert_output_equal(before, corrected)
    assert before.source_bars == arrays.source_bars
    assert corrected.source_bars == arrays.source_bars


def test_benchmark_correction_does_not_touch_unsupported_subject() -> None:
    listing = _listing(
        UNSUPPORTED_ID,
        provider_code="YAHOO",
        market="XIDX",
        ticker="SPX",
        instrument_type_code="EQUITY_INDEX",
    )
    arrays = _subject_arrays(UNSUPPORTED_ID)
    before = _calculate(_benchmark(), listing=listing, arrays=arrays)
    corrected = _calculate(
        _benchmark(
            changed_closes={100: _spx_close(100) * Decimal("1.125")}
        ),
        listing=listing,
        arrays=arrays,
    )

    _assert_output_equal(before, corrected)
    assert before.benchmark_provider_listing_id is None
    assert before.reason_counts[0].code == "SUBJECT_UNSUPPORTED"
