from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from math import isclose
from uuid import UUID

import pytest

from empire_stonks_tech_indicators import (
    BenchmarkHistory,
    EligibleListing,
    FeatureRow,
    ListingStateComparison,
    ResolvedBenchmark,
    SourceBar,
    assemble_feature_rows,
    normalize_source_bars,
)
from empire_stonks_tech_indicators.affected_ranges import (
    AffectedRange,
    AffectedRangeReason,
    plan_affected_ranges,
)
from empire_stonks_tech_indicators.models import PYTHON_FEATURE_FIELDS
from empire_stonks_tech_indicators.validation import (
    ABSOLUTE_TOLERANCE,
    RELATIVE_TOLERANCE,
)


SUBJECT_ID = UUID("71111111-1111-4111-8111-111111111111")
BENCHMARK_ID = UUID("72222222-2222-4222-8222-222222222222")
OLD_RUN_ID = UUID("73333333-3333-4333-8333-333333333333")
NEW_RUN_ID = UUID("74444444-4444-4444-8444-444444444444")
CORRECTION_RUN_ID = UUID("75555555-5555-4555-8555-555555555555")
OLD_CALCULATED_AT = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
NEW_CALCULATED_AT = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
CORRECTION_CALCULATED_AT = datetime(2026, 8, 22, 13, 0, tzinfo=UTC)
STALE_VERSION = "TECH_INDICATORS_PRIOR"
CURRENT_VERSION = "TECH_INDICATORS_V1"
ROW_COUNT = 300
APPEND_START_INDEX = 280
SOURCE_CORRECTION_INDEX = 137
BENCHMARK_CORRECTION_INDEX = 145
LIFECYCLE_FIELDS = frozenset({"run_id", "calculated_at"})
EXACT_FEATURE_FIELDS = frozenset(
    {"consecutive_up_days", "consecutive_down_days"}
)


Payload = dict[str, object]
Image = dict[str, Payload]


@dataclass(frozen=True)
class RebuildFixture:
    bars: tuple[SourceBar, ...]
    subject: EligibleListing
    benchmark: BenchmarkHistory
    current_rows: tuple[FeatureRow, ...]
    appended_rows: tuple[FeatureRow, ...]
    source_corrected_rows: tuple[FeatureRow, ...]
    benchmark_corrected_rows: tuple[FeatureRow, ...]


def _bars(
    listing_id: UUID,
    count: int,
    *,
    base: Decimal,
    step: Decimal,
) -> tuple[SourceBar, ...]:
    start = date(2025, 1, 1)
    return tuple(
        SourceBar(
            provider_listing_id=listing_id,
            trading_date=start + timedelta(days=index),
            open=close - Decimal("0.25"),
            high=close + Decimal("1.50"),
            low=close - Decimal("1.25"),
            close=close,
            volume=Decimal(10_000 + index * 3),
        )
        for index in range(count)
        for close in (
            base + step * index + Decimal(index % 11) / Decimal("100"),
        )
    )


def _subject(bars: tuple[SourceBar, ...]) -> EligibleListing:
    return EligibleListing(
        provider_listing_id=SUBJECT_ID,
        provider_code="EODDATA",
        market="NYSE",
        ticker="EQUIV",
        instrument_type_code="UNKNOWN",
        status="ACTIVE",
        first_trading_date=bars[0].trading_date,
        last_trading_date=bars[-1].trading_date,
        source_observation_count=len(bars),
    )


def _benchmark(bars: tuple[SourceBar, ...]) -> BenchmarkHistory:
    return BenchmarkHistory(
        benchmark=ResolvedBenchmark(provider_listing_id=BENCHMARK_ID),
        bars=bars,
    )


def _assemble(
    bars: tuple[SourceBar, ...],
    benchmark: BenchmarkHistory,
    *,
    calculated_at: datetime,
    run_id: UUID,
) -> tuple[FeatureRow, ...]:
    return assemble_feature_rows(
        normalize_source_bars(bars),
        subject=_subject(bars),
        benchmark_history=benchmark,
        calculated_at=calculated_at,
        run_id=run_id,
    )


@pytest.fixture(scope="module")
def rebuild_fixture() -> RebuildFixture:
    bars = _bars(
        SUBJECT_ID,
        ROW_COUNT,
        base=Decimal("100"),
        step=Decimal("0.17"),
    )
    benchmark_bars = _bars(
        BENCHMARK_ID,
        ROW_COUNT,
        base=Decimal("4200"),
        step=Decimal("0.41"),
    )
    benchmark = _benchmark(benchmark_bars)
    current_rows = _assemble(
        bars,
        benchmark,
        calculated_at=NEW_CALCULATED_AT,
        run_id=NEW_RUN_ID,
    )
    appended_rows = _assemble(
        bars[:APPEND_START_INDEX],
        _benchmark(benchmark_bars[:APPEND_START_INDEX]),
        calculated_at=OLD_CALCULATED_AT,
        run_id=OLD_RUN_ID,
    )

    corrected_source = list(bars)
    changed_source = corrected_source[SOURCE_CORRECTION_INDEX]
    corrected_source[SOURCE_CORRECTION_INDEX] = replace(
        changed_source,
        open=changed_source.open + Decimal("7"),
        high=changed_source.high + Decimal("7"),
        low=changed_source.low + Decimal("7"),
        close=changed_source.close + Decimal("7"),
        volume=changed_source.volume + Decimal("100"),
    )
    source_corrected_rows = _assemble(
        tuple(corrected_source),
        benchmark,
        calculated_at=CORRECTION_CALCULATED_AT,
        run_id=CORRECTION_RUN_ID,
    )

    corrected_benchmark = list(benchmark_bars)
    changed_benchmark = corrected_benchmark[BENCHMARK_CORRECTION_INDEX]
    corrected_benchmark[BENCHMARK_CORRECTION_INDEX] = replace(
        changed_benchmark,
        open=changed_benchmark.open + Decimal("15"),
        high=changed_benchmark.high + Decimal("15"),
        low=changed_benchmark.low + Decimal("15"),
        close=changed_benchmark.close + Decimal("15"),
    )
    benchmark_corrected_rows = _assemble(
        bars,
        _benchmark(tuple(corrected_benchmark)),
        calculated_at=CORRECTION_CALCULATED_AT,
        run_id=CORRECTION_RUN_ID,
    )
    return RebuildFixture(
        bars=bars,
        subject=_subject(bars),
        benchmark=benchmark,
        current_rows=current_rows,
        appended_rows=appended_rows,
        source_corrected_rows=source_corrected_rows,
        benchmark_corrected_rows=benchmark_corrected_rows,
    )


def _comparison(
    bars: tuple[SourceBar, ...],
    *,
    last_technical_date: date | None,
    **overrides: object,
) -> ListingStateComparison:
    values: dict[str, object] = {
        "provider_listing_id": SUBJECT_ID,
        "provider_code": "EODDATA",
        "market": "NYSE",
        "ticker": "EQUIV",
        "first_source_date": bars[0].trading_date,
        "last_source_date": bars[-1].trading_date,
        "source_observation_count": len(bars),
        "last_technical_date": last_technical_date,
        "tail_append_count": 0,
        "missing_tech_row_count": 0,
        "source_copy_drift_count": 0,
        "history_count_drift_count": 0,
        "version_drift_count": 0,
        "earliest_tail_append_date": None,
        "earliest_missing_tech_date": None,
        "earliest_source_copy_drift_date": None,
        "earliest_history_count_drift_date": None,
        "earliest_version_drift_date": None,
    }
    values.update(overrides)
    return ListingStateComparison(**values)  # type: ignore[arg-type]


def _range(
    fixture: RebuildFixture,
    comparison: ListingStateComparison,
    *,
    benchmark_drift_start_date: date | None = None,
    explicit_rebuild: bool = False,
) -> AffectedRange:
    plan = plan_affected_ranges(
        listings=(fixture.subject,),
        comparisons=(comparison,),
        requested_end_date=fixture.bars[-1].trading_date,
        benchmark_drift_start_date=benchmark_drift_start_date,
        explicit_rebuild_listing_ids=(SUBJECT_ID,) if explicit_rebuild else (),
    )
    assert len(plan.ranges) == 1
    return plan.ranges[0]


def _image(rows: tuple[FeatureRow, ...]) -> Image:
    return {row.source.trading_date.isoformat(): row.to_dict() for row in rows}


def _old_image(rows: tuple[FeatureRow, ...]) -> Image:
    image = _image(rows)
    for payload in image.values():
        payload["run_id"] = str(OLD_RUN_ID)
        payload["calculated_at"] = OLD_CALCULATED_AT.isoformat()
    return image


def _payloads_equivalent(actual: Payload, expected: Payload) -> bool:
    if actual.keys() != expected.keys():
        return False
    for field_name in actual.keys() - LIFECYCLE_FIELDS:
        actual_value = actual[field_name]
        expected_value = expected[field_name]
        if field_name not in PYTHON_FEATURE_FIELDS:
            if actual_value != expected_value:
                return False
            continue
        if (actual_value is None) != (expected_value is None):
            return False
        if actual_value is None:
            continue
        if field_name in EXACT_FEATURE_FIELDS:
            if actual_value != expected_value:
                return False
            continue
        if not isclose(
            float(actual_value),
            float(expected_value),
            rel_tol=RELATIVE_TOLERANCE,
            abs_tol=ABSOLUTE_TOLERANCE,
        ):
            return False
    return True


def _publish_suffix(
    existing: Image,
    calculated_rows: tuple[FeatureRow, ...],
    *,
    write_start_date: date,
    write_end_date: date,
) -> Image:
    published = dict(existing)
    for row in calculated_rows:
        trading_date = row.source.trading_date
        if not write_start_date <= trading_date <= write_end_date:
            continue
        key = trading_date.isoformat()
        candidate = row.to_dict()
        current = published.get(key)
        if current is None or not _payloads_equivalent(current, candidate):
            published[key] = candidate
    return published


def _publish_range(
    existing: Image,
    calculated_rows: tuple[FeatureRow, ...],
    affected: AffectedRange,
) -> Image:
    return _publish_suffix(
        existing,
        calculated_rows,
        write_start_date=affected.write_start_date,
        write_end_date=affected.write_end_date,
    )


def _assert_images_equivalent(actual: Image, expected: Image) -> None:
    assert actual.keys() == expected.keys()
    for key in actual:
        assert _payloads_equivalent(actual[key], expected[key]), key


def _assert_prefix_preserved(before: Image, after: Image, cutoff: date) -> None:
    for key, payload in before.items():
        if date.fromisoformat(key) < cutoff:
            assert after[key] is payload


def test_full_rebuild_matches_complete_reference_image(
    rebuild_fixture: RebuildFixture,
) -> None:
    comparison = _comparison(
        rebuild_fixture.bars,
        last_technical_date=None,
    )
    affected = _range(
        rebuild_fixture,
        comparison,
        explicit_rebuild=True,
    )

    published = _publish_range({}, rebuild_fixture.current_rows, affected)

    assert affected.write_start_date == rebuild_fixture.bars[0].trading_date
    assert affected.reasons == (AffectedRangeReason.EXPLICIT_REBUILD,)
    assert len(published) == ROW_COUNT
    _assert_images_equivalent(published, _image(rebuild_fixture.current_rows))


def test_append_matches_full_rebuild_and_preserves_existing_prefix(
    rebuild_fixture: RebuildFixture,
) -> None:
    append_date = rebuild_fixture.bars[APPEND_START_INDEX].trading_date
    existing = _image(rebuild_fixture.appended_rows)
    comparison = _comparison(
        rebuild_fixture.bars,
        last_technical_date=rebuild_fixture.bars[APPEND_START_INDEX - 1].trading_date,
        tail_append_count=ROW_COUNT - APPEND_START_INDEX,
        earliest_tail_append_date=append_date,
    )
    affected = _range(rebuild_fixture, comparison)

    published = _publish_range(
        existing,
        rebuild_fixture.current_rows,
        affected,
    )

    assert affected.write_start_date == append_date
    assert affected.reasons == (AffectedRangeReason.TAIL_APPEND,)
    _assert_prefix_preserved(existing, published, append_date)
    _assert_images_equivalent(published, _image(rebuild_fixture.current_rows))


def test_resumed_append_matches_full_rebuild_without_duplicate_or_drift(
    rebuild_fixture: RebuildFixture,
) -> None:
    append_date = rebuild_fixture.bars[APPEND_START_INDEX].trading_date
    resume_date = rebuild_fixture.bars[APPEND_START_INDEX + 7].trading_date
    existing = _image(rebuild_fixture.appended_rows)
    comparison = _comparison(
        rebuild_fixture.bars,
        last_technical_date=rebuild_fixture.bars[APPEND_START_INDEX - 1].trading_date,
        tail_append_count=ROW_COUNT - APPEND_START_INDEX,
        earliest_tail_append_date=append_date,
    )
    affected = _range(rebuild_fixture, comparison)
    first_batch = _publish_suffix(
        existing,
        rebuild_fixture.current_rows,
        write_start_date=affected.write_start_date,
        write_end_date=resume_date - timedelta(days=1),
    )

    replayed_batch = _publish_suffix(
        first_batch,
        rebuild_fixture.current_rows,
        write_start_date=append_date,
        write_end_date=resume_date - timedelta(days=1),
    )
    published = _publish_suffix(
        replayed_batch,
        rebuild_fixture.current_rows,
        write_start_date=resume_date,
        write_end_date=affected.write_end_date,
    )

    assert affected.reasons == (AffectedRangeReason.TAIL_APPEND,)
    assert all(replayed_batch[key] is payload for key, payload in first_batch.items())
    assert len(published) == len(set(published)) == ROW_COUNT
    _assert_prefix_preserved(existing, published, append_date)
    _assert_images_equivalent(published, _image(rebuild_fixture.current_rows))


def test_source_correction_suffix_matches_full_corrected_rebuild(
    rebuild_fixture: RebuildFixture,
) -> None:
    correction_date = rebuild_fixture.bars[SOURCE_CORRECTION_INDEX].trading_date
    existing = _old_image(rebuild_fixture.current_rows)
    comparison = _comparison(
        rebuild_fixture.bars,
        last_technical_date=rebuild_fixture.bars[-1].trading_date,
        source_copy_drift_count=1,
        earliest_source_copy_drift_date=correction_date,
    )
    affected = _range(rebuild_fixture, comparison)

    published = _publish_range(
        existing,
        rebuild_fixture.source_corrected_rows,
        affected,
    )

    assert affected.write_start_date == correction_date
    assert affected.reasons == (AffectedRangeReason.SOURCE_COPY_DRIFT,)
    _assert_prefix_preserved(existing, published, correction_date)
    _assert_images_equivalent(
        published,
        _image(rebuild_fixture.source_corrected_rows),
    )


def test_spx_correction_suffix_matches_full_corrected_rebuild(
    rebuild_fixture: RebuildFixture,
) -> None:
    correction_date = rebuild_fixture.bars[BENCHMARK_CORRECTION_INDEX].trading_date
    existing = _old_image(rebuild_fixture.current_rows)
    comparison = _comparison(
        rebuild_fixture.bars,
        last_technical_date=rebuild_fixture.bars[-1].trading_date,
    )
    affected = _range(
        rebuild_fixture,
        comparison,
        benchmark_drift_start_date=correction_date,
    )

    published = _publish_range(
        existing,
        rebuild_fixture.benchmark_corrected_rows,
        affected,
    )

    assert affected.write_start_date == correction_date
    assert affected.reasons == (AffectedRangeReason.BENCHMARK_DRIFT,)
    _assert_prefix_preserved(existing, published, correction_date)
    _assert_images_equivalent(
        published,
        _image(rebuild_fixture.benchmark_corrected_rows),
    )


def test_version_rebuild_replaces_complete_image_without_mixed_versions(
    rebuild_fixture: RebuildFixture,
) -> None:
    existing = _old_image(rebuild_fixture.current_rows)
    for payload in existing.values():
        payload["calculation_version"] = STALE_VERSION
    drift_date = rebuild_fixture.bars[173].trading_date
    comparison = _comparison(
        rebuild_fixture.bars,
        last_technical_date=rebuild_fixture.bars[-1].trading_date,
        version_drift_count=1,
        earliest_version_drift_date=drift_date,
    )
    affected = _range(rebuild_fixture, comparison)

    published = _publish_range(
        existing,
        rebuild_fixture.current_rows,
        affected,
    )

    assert affected.write_start_date == rebuild_fixture.bars[0].trading_date
    assert affected.reasons == (AffectedRangeReason.VERSION_DRIFT,)
    assert {row["calculation_version"] for row in published.values()} == {
        CURRENT_VERSION
    }
    assert {row["run_id"] for row in published.values()} == {str(NEW_RUN_ID)}
    _assert_images_equivalent(published, _image(rebuild_fixture.current_rows))
