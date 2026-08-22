from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from uuid import UUID

import pytest

from empire_stonks_tech_indicators.affected_ranges import (
    AffectedRange,
    AffectedRangePlan,
    AffectedRangeReason,
    plan_affected_ranges,
)
from empire_stonks_tech_indicators.queries import EligibleListing
from empire_stonks_tech_indicators.state import ListingStateComparison


LISTING_ID = UUID("10000000-0000-4000-8000-000000000001")
SECOND_ID = UUID("10000000-0000-4000-8000-000000000002")
FIRST_DATE = date(2026, 1, 1)
LAST_DATE = date(2026, 1, 10)


def _listing(
    provider_listing_id: UUID = LISTING_ID,
    *,
    provider_code: str = "EODDATA",
    market: str = "NYSE",
    ticker: str = "AAA",
    status: str = "ACTIVE",
) -> EligibleListing:
    return EligibleListing(
        provider_listing_id=provider_listing_id,
        provider_code=provider_code,
        market=market,
        ticker=ticker,
        instrument_type_code="UNKNOWN",
        status=status,
        first_trading_date=FIRST_DATE,
        last_trading_date=LAST_DATE,
        source_observation_count=10,
    )


def _comparison(
    provider_listing_id: UUID = LISTING_ID,
    **overrides: object,
) -> ListingStateComparison:
    values: dict[str, object] = {
        "provider_listing_id": provider_listing_id,
        "provider_code": "EODDATA",
        "market": "NYSE",
        "ticker": "AAA",
        "first_source_date": FIRST_DATE,
        "last_source_date": LAST_DATE,
        "source_observation_count": 10,
        "last_technical_date": date(2026, 1, 8),
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


def _plan(
    comparison: ListingStateComparison,
    *,
    listing: EligibleListing | None = None,
    requested_end_date: date = LAST_DATE,
    requested_start_date: date | None = None,
    benchmark_drift_start_date: date | None = None,
    explicit_rebuild_listing_ids: tuple[UUID, ...] = (),
) -> AffectedRangePlan:
    return plan_affected_ranges(
        listings=(_listing() if listing is None else listing,),
        comparisons=(comparison,),
        requested_start_date=requested_start_date,
        requested_end_date=requested_end_date,
        benchmark_drift_start_date=benchmark_drift_start_date,
        explicit_rebuild_listing_ids=explicit_rebuild_listing_ids,
    )


def test_equivalent_listing_produces_bounded_noop_summary() -> None:
    plan = _plan(_comparison())

    assert plan.is_noop is True
    assert plan.ranges == ()
    assert plan.reason_counts == ()
    assert plan.to_summary_dict() == {
        "requested_start_date": None,
        "requested_end_date": "2026-01-10",
        "benchmark_drift_start_date": None,
        "selected_listing_count": 1,
        "work_range_count": 0,
        "expanded_range_count": 0,
        "is_noop": True,
        "reason_counts": [],
    }
    json.dumps(plan.to_summary_dict())


def test_public_planner_access_remains_calculation_runtime_lazy() -> None:
    code = """
import json
import sys
import empire_stonks_tech_indicators as package

planner = package.plan_affected_ranges
print(json.dumps({
    "callable": callable(planner),
    "calculation_modules": [
        name for name in ("numpy", "talib") if name in sys.modules
    ],
}))
"""
    completed = subprocess.run(
        [sys.executable, "-I", "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == {
        "callable": True,
        "calculation_modules": [],
    }


def test_tail_append_calculates_full_prefix_and_writes_only_new_suffix() -> None:
    plan = _plan(
        _comparison(
            tail_append_count=2,
            earliest_tail_append_date=date(2026, 1, 9),
        )
    )

    assert plan.ranges == (
        AffectedRange(
            provider_listing_id=LISTING_ID,
            provider_code="EODDATA",
            market="NYSE",
            ticker="AAA",
            status="ACTIVE",
            calculation_start_date=FIRST_DATE,
            write_start_date=date(2026, 1, 9),
            write_end_date=LAST_DATE,
            requested_end_date=LAST_DATE,
            reasons=(AffectedRangeReason.TAIL_APPEND,),
        ),
    )


def test_overlapping_local_reasons_collapse_and_expand_stale_tail() -> None:
    plan = _plan(
        _comparison(
            last_technical_date=LAST_DATE,
            missing_tech_row_count=1,
            earliest_missing_tech_date=date(2026, 1, 4),
            source_copy_drift_count=2,
            earliest_source_copy_drift_date=date(2026, 1, 3),
            history_count_drift_count=1,
            earliest_history_count_drift_date=date(2026, 1, 5),
        ),
        requested_end_date=date(2026, 1, 6),
    )

    affected = plan.ranges[0]
    assert affected.calculation_start_date == FIRST_DATE
    assert affected.write_start_date == date(2026, 1, 3)
    assert affected.write_end_date == LAST_DATE
    assert affected.expanded_beyond_requested_horizon is True
    assert affected.reasons == (
        AffectedRangeReason.MISSING_TECH_ROW,
        AffectedRangeReason.SOURCE_COPY_DRIFT,
        AffectedRangeReason.HISTORY_COUNT_DRIFT,
    )
    assert plan.expanded_range_count == 1


def test_version_drift_forces_first_source_row() -> None:
    plan = _plan(
        _comparison(
            last_technical_date=LAST_DATE,
            version_drift_count=1,
            earliest_version_drift_date=date(2026, 1, 5),
        ),
        requested_end_date=date(2026, 1, 6),
    )

    affected = plan.ranges[0]
    assert affected.write_start_date == FIRST_DATE
    assert affected.write_end_date == LAST_DATE
    assert affected.reasons == (AffectedRangeReason.VERSION_DRIFT,)


def test_version_drift_after_requested_horizon_still_prevents_mixed_state() -> None:
    plan = _plan(
        _comparison(
            last_technical_date=LAST_DATE,
            version_drift_count=1,
            earliest_version_drift_date=date(2026, 1, 9),
        ),
        requested_end_date=date(2026, 1, 6),
    )

    affected = plan.ranges[0]
    assert affected.write_start_date == FIRST_DATE
    assert affected.write_end_date == LAST_DATE


def test_supported_benchmark_drift_propagates_conservative_suffix() -> None:
    plan = _plan(
        _comparison(last_technical_date=LAST_DATE),
        requested_end_date=date(2026, 1, 7),
        benchmark_drift_start_date=date(2026, 1, 5),
    )

    affected = plan.ranges[0]
    assert affected.write_start_date == date(2026, 1, 5)
    assert affected.write_end_date == LAST_DATE
    assert affected.reasons == (AffectedRangeReason.BENCHMARK_DRIFT,)
    assert plan.reason_counts[0].to_dict() == {
        "code": "BENCHMARK_DRIFT",
        "count": 1,
    }


@pytest.mark.parametrize(
    ("provider_code", "market"),
    [("YAHOO", "XIDX"), ("EODDATA", "LSE"), ("STOOQ", "wig20")],
)
def test_benchmark_drift_skips_unsupported_subjects(
    provider_code: str,
    market: str,
) -> None:
    listing = _listing(provider_code=provider_code, market=market)
    comparison = _comparison(provider_code=provider_code, market=market)

    plan = _plan(
        comparison,
        listing=listing,
        benchmark_drift_start_date=date(2026, 1, 5),
    )

    assert plan.is_noop is True


def test_benchmark_drift_skips_nonoverlapping_subject_coverage() -> None:
    plan = _plan(
        _comparison(),
        benchmark_drift_start_date=date(2026, 1, 11),
    )

    assert plan.is_noop is True


def test_benchmark_drift_before_subject_coverage_is_unrelated() -> None:
    comparison = _comparison(
        first_source_date=date(2026, 1, 5),
        source_observation_count=6,
    )

    plan = _plan(
        comparison,
        benchmark_drift_start_date=date(2026, 1, 4),
    )

    assert plan.is_noop is True


def test_benchmark_only_inactive_maintenance_cannot_extend_coverage() -> None:
    listing = _listing(status="INACTIVE")
    comparison = _comparison(last_technical_date=date(2026, 1, 7))

    plan = _plan(
        comparison,
        listing=listing,
        benchmark_drift_start_date=date(2026, 1, 5),
    )

    assert plan.ranges[0].write_end_date == date(2026, 1, 7)
    assert plan.ranges[0].status == "INACTIVE"


def test_benchmark_only_inactive_listing_without_payload_is_ignored() -> None:
    listing = _listing(status="INACTIVE")

    plan = _plan(
        _comparison(last_technical_date=None),
        listing=listing,
        benchmark_drift_start_date=date(2026, 1, 5),
    )

    assert plan.is_noop is True


def test_explicit_rebuild_respects_start_and_expands_existing_tail() -> None:
    plan = _plan(
        _comparison(last_technical_date=LAST_DATE),
        requested_start_date=date(2026, 1, 4),
        requested_end_date=date(2026, 1, 6),
        explicit_rebuild_listing_ids=(LISTING_ID,),
    )

    affected = plan.ranges[0]
    assert affected.calculation_start_date == FIRST_DATE
    assert affected.write_start_date == date(2026, 1, 4)
    assert affected.write_end_date == LAST_DATE
    assert affected.reasons == (AffectedRangeReason.EXPLICIT_REBUILD,)


def test_dates_after_requested_horizon_do_not_create_work() -> None:
    plan = _plan(
        _comparison(
            tail_append_count=1,
            earliest_tail_append_date=date(2026, 1, 9),
        ),
        requested_end_date=date(2026, 1, 8),
    )

    assert plan.is_noop is True


def test_end_date_never_reads_beyond_available_source() -> None:
    plan = _plan(
        _comparison(
            tail_append_count=1,
            earliest_tail_append_date=date(2026, 1, 9),
        ),
        requested_end_date=date(2026, 1, 20),
    )

    assert plan.ranges[0].write_end_date == LAST_DATE


def test_local_and_benchmark_reasons_use_contract_order() -> None:
    plan = _plan(
        _comparison(
            source_copy_drift_count=1,
            earliest_source_copy_drift_date=date(2026, 1, 6),
        ),
        benchmark_drift_start_date=date(2026, 1, 4),
    )

    assert plan.ranges[0].write_start_date == date(2026, 1, 4)
    assert plan.ranges[0].reasons == (
        AffectedRangeReason.SOURCE_COPY_DRIFT,
        AffectedRangeReason.BENCHMARK_DRIFT,
    )


def test_ranges_are_sorted_by_provider_identity_not_input_order() -> None:
    second_listing = _listing(
        SECOND_ID,
        provider_code="STOOQ",
        market="nyse",
        ticker="BBB",
    )
    second_comparison = _comparison(
        SECOND_ID,
        provider_code="STOOQ",
        market="nyse",
        ticker="BBB",
        tail_append_count=1,
        earliest_tail_append_date=date(2026, 1, 9),
    )
    first_comparison = _comparison(
        source_copy_drift_count=1,
        earliest_source_copy_drift_date=date(2026, 1, 4),
    )

    plan = plan_affected_ranges(
        listings=(second_listing, _listing()),
        comparisons=(second_comparison, first_comparison),
        requested_end_date=LAST_DATE,
    )

    assert [item.provider_listing_id for item in plan.ranges] == [
        LISTING_ID,
        SECOND_ID,
    ]


def test_empty_source_never_creates_calculation_work() -> None:
    listing = EligibleListing(
        provider_listing_id=LISTING_ID,
        provider_code="EODDATA",
        market="NYSE",
        ticker="AAA",
        instrument_type_code="UNKNOWN",
        status="ACTIVE",
        first_trading_date=None,
        last_trading_date=None,
        source_observation_count=0,
    )
    comparison = _comparison(
        first_source_date=None,
        last_source_date=None,
        source_observation_count=0,
        last_technical_date=None,
    )

    plan = _plan(
        comparison,
        listing=listing,
        benchmark_drift_start_date=FIRST_DATE,
        explicit_rebuild_listing_ids=(LISTING_ID,),
    )

    assert plan.is_noop is True


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {"comparisons": ()},
            "same IDs",
        ),
        (
            {"explicit_rebuild_listing_ids": (SECOND_ID,)},
            "selected listings",
        ),
        (
            {"explicit_rebuild_listing_ids": [LISTING_ID]},
            "must be a tuple",
        ),
    ],
)
def test_planner_rejects_incomplete_or_invalid_identity_inputs(
    kwargs: dict[str, object],
    message: str,
) -> None:
    arguments: dict[str, object] = {
        "listings": (_listing(),),
        "comparisons": (_comparison(),),
        "requested_end_date": LAST_DATE,
    }
    arguments.update(kwargs)

    with pytest.raises((TypeError, ValueError), match=message):
        plan_affected_ranges(**arguments)  # type: ignore[arg-type]


def test_planner_rejects_identity_drift_and_inverted_request() -> None:
    with pytest.raises(ValueError, match="identity facts"):
        _plan(_comparison(ticker="DRIFT"))

    with pytest.raises(ValueError, match="must not follow"):
        _plan(
            _comparison(),
            requested_start_date=LAST_DATE,
            requested_end_date=FIRST_DATE,
        )
