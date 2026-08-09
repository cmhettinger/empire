import json
from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest

import empire_stonks_tech_indicators as public_api
from empire_stonks_tech_indicators import (
    FeatureCounts,
    FeatureRow,
    ReasonCount,
    ResolvedBenchmark,
    SourceBar,
    TechIndicatorsIssue,
    TechIndicatorsRunResult,
    TechIndicatorsScope,
    TechIndicatorsSummary,
)
from empire_stonks_tech_indicators import models as models_module
from empire_stonks_tech_indicators.models import PYTHON_FEATURE_FIELDS


LISTING_ID = UUID("00000000-0000-4000-8000-000000000001")
OTHER_LISTING_ID = UUID("00000000-0000-4000-8000-000000000002")
BENCHMARK_ID = UUID("00000000-0000-4000-8000-000000000003")
RUN_ID = UUID("00000000-0000-4000-8000-000000000004")
CALCULATED_AT = datetime(2026, 8, 9, 12, 30, tzinfo=UTC)


def _source_bar(**overrides: object) -> SourceBar:
    values: dict[str, object] = {
        "provider_listing_id": LISTING_ID,
        "trading_date": date(2026, 8, 8),
        "open": Decimal("-10.25"),
        "high": Decimal("12.50"),
        "low": Decimal("-11.00"),
        "close": Decimal("12.00"),
        "volume": None,
    }
    values.update(overrides)
    return SourceBar(**values)  # type: ignore[arg-type]


def _feature_row(**overrides: object) -> FeatureRow:
    values: dict[str, object] = {
        "source": _source_bar(),
        "history_observation_count": 1,
        "calculation_version": "TECH_INDICATORS_V1",
        "calculated_at": CALCULATED_AT,
    }
    values.update(overrides)
    return FeatureRow(**values)  # type: ignore[arg-type]


def _issue(**overrides: object) -> TechIndicatorsIssue:
    values: dict[str, object] = {
        "code": "ALIGNED_WARMUP",
        "severity": "WARNING",
        "message": "Insufficient aligned history.",
    }
    values.update(overrides)
    return TechIndicatorsIssue(**values)  # type: ignore[arg-type]


def test_models_are_explicitly_exported() -> None:
    expected = [
        "FeatureCounts",
        "FeatureRow",
        "ReasonCount",
        "ResolvedBenchmark",
        "SourceBar",
        "TechIndicatorsIssue",
        "TechIndicatorsRunResult",
        "TechIndicatorsScope",
        "TechIndicatorsSummary",
    ]

    assert models_module.__all__ == expected
    assert all(
        getattr(public_api, name) is getattr(models_module, name)
        for name in expected
    )
    assert public_api.__all__[-len(expected) :] == expected


def test_source_bar_preserves_provider_values_as_json_strings() -> None:
    bar = _source_bar()

    assert bar.to_dict() == {
        "provider_listing_id": str(LISTING_ID),
        "trading_date": "2026-08-08",
        "open": "-10.25",
        "high": "12.50",
        "low": "-11.00",
        "close": "12.00",
        "volume": None,
    }
    json.dumps(bar.to_dict(), allow_nan=False)


@pytest.mark.parametrize(
    ("overrides", "error", "message"),
    [
        ({"provider_listing_id": "not-a-uuid"}, TypeError, "UUID"),
        ({"trading_date": datetime.now(UTC)}, TypeError, "date"),
        ({"open": 1.0}, TypeError, "Decimal"),
        ({"close": Decimal("NaN")}, ValueError, "finite"),
        ({"high": Decimal("-12")}, ValueError, "high"),
        ({"low": Decimal("13")}, ValueError, "low"),
        ({"volume": Decimal("-1")}, ValueError, "non-negative"),
    ],
)
def test_source_bar_rejects_invalid_values(
    overrides: dict[str, object],
    error: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error, match=message):
        _source_bar(**overrides)


def test_feature_row_is_exact_package_write_shape() -> None:
    row = _feature_row()
    payload = row.to_dict()

    assert len(PYTHON_FEATURE_FIELDS) == 53
    assert len(payload) == 65
    assert payload["provider_listing_id"] == str(LISTING_ID)
    assert payload["history_observation_count"] == 1
    assert payload["calculation_version"] == "TECH_INDICATORS_V1"
    assert payload["calculated_at"] == "2026-08-09T12:30:00+00:00"
    assert payload["consecutive_up_days"] == 0
    assert payload["consecutive_down_days"] == 0
    assert payload["relative_strength_benchmark_provider_listing_id"] is None
    assert all(
        payload[name] is None
        for name in PYTHON_FEATURE_FIELDS
        if "consecutive" not in name
    )
    assert "created_at" not in payload
    assert "updated_at" not in payload
    assert "dollar_volume" not in payload
    json.dumps(payload, allow_nan=False)


def test_feature_row_accepts_finite_features_and_resolved_benchmark() -> None:
    row = _feature_row(
        relative_strength_benchmark_provider_listing_id=BENCHMARK_ID,
        run_id=RUN_ID,
        return_1d_pct=0.05,
        consecutive_up_days=2,
        rel_spx=1.25,
        spx_correlation_60d=-1.0,
    )

    assert row.to_dict()["run_id"] == str(RUN_ID)
    assert row.to_dict()["rel_spx"] == 1.25


@pytest.mark.parametrize(
    ("overrides", "error", "message"),
    [
        ({"source": object()}, TypeError, "SourceBar"),
        ({"history_observation_count": 0}, ValueError, "positive"),
        ({"calculation_version": "TECH_INDICATORS_V2"}, ValueError, "V1"),
        ({"calculated_at": datetime(2026, 8, 9)}, ValueError, "timezone-aware"),
        ({"return_1d_pct": 1}, TypeError, "float or None"),
        ({"return_1d_pct": float("inf")}, ValueError, "finite"),
        ({"consecutive_up_days": -1}, ValueError, "non-negative"),
        ({"consecutive_down_days": True}, TypeError, "integer"),
        ({"rel_spx": 1.0}, ValueError, "resolved benchmark"),
    ],
)
def test_feature_row_rejects_invalid_shape(
    overrides: dict[str, object],
    error: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error, match=message):
        _feature_row(**overrides)


def test_scope_normalizes_selectors_and_dates() -> None:
    scope = TechIndicatorsScope(
        provider_codes=("STOOQ", "EODDATA", "STOOQ"),
        markets=("nyse", "NASDAQ", "nyse"),
        provider_listing_ids=(OTHER_LISTING_ID, LISTING_ID, OTHER_LISTING_ID),
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 9),
    )

    assert scope.to_dict() == {
        "provider_codes": ["EODDATA", "STOOQ"],
        "markets": ["NASDAQ", "nyse"],
        "provider_listing_ids": [str(LISTING_ID), str(OTHER_LISTING_ID)],
        "start_date": "2026-08-01",
        "end_date": "2026-08-09",
        "include_inactive": False,
    }


@pytest.mark.parametrize(
    ("kwargs", "error", "message"),
    [
        ({"provider_codes": ["STOOQ"]}, TypeError, "tuple"),
        ({"provider_codes": ("stooq",)}, ValueError, "uppercase"),
        ({"start_date": date(2026, 8, 1)}, ValueError, "provided together"),
        (
            {"start_date": date(2026, 8, 2), "end_date": date(2026, 8, 1)},
            ValueError,
            "must not be after",
        ),
        ({"include_inactive": 1}, TypeError, "bool"),
        ({"include_inactive": True}, ValueError, "explicit listing-only"),
        (
            {
                "include_inactive": True,
                "provider_listing_ids": (LISTING_ID,),
                "provider_codes": ("STOOQ",),
            },
            ValueError,
            "listing-only",
        ),
    ],
)
def test_scope_rejects_ambiguous_or_unsafe_selection(
    kwargs: dict[str, object],
    error: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error, match=message):
        TechIndicatorsScope(**kwargs)  # type: ignore[arg-type]


def test_scope_allows_explicit_inactive_listing_opt_in() -> None:
    scope = TechIndicatorsScope(
        provider_listing_ids=(LISTING_ID,),
        include_inactive=True,
    )

    assert scope.include_inactive is True


def test_resolved_benchmark_requires_every_frozen_fact() -> None:
    benchmark = ResolvedBenchmark(provider_listing_id=BENCHMARK_ID)

    assert benchmark.to_dict() == {
        "provider_listing_id": str(BENCHMARK_ID),
        "provider_code": "YAHOO",
        "market": "XIDX",
        "ticker": "SPX",
        "instrument_type_code": "EQUITY_INDEX",
        "status": "ACTIVE",
        "yahoo_ticker": "^GSPC",
    }


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("provider_code", "STOOQ"),
        ("market", "xidx"),
        ("ticker", "^GSPC"),
        ("instrument_type_code", "UNKNOWN"),
        ("status", "INACTIVE"),
        ("yahoo_ticker", "SPX"),
    ],
)
def test_resolved_benchmark_rejects_identity_drift(
    field_name: str,
    value: str,
) -> None:
    with pytest.raises(ValueError, match=field_name):
        ResolvedBenchmark(
            provider_listing_id=BENCHMARK_ID,
            **{field_name: value},
        )


def test_issue_is_bounded_and_json_ready() -> None:
    issue = _issue(
        provider_listing_id=LISTING_ID,
        trading_date=date(2026, 8, 8),
        field_name="rel_spx",
    )

    assert issue.to_dict() == {
        "code": "ALIGNED_WARMUP",
        "severity": "WARNING",
        "message": "Insufficient aligned history.",
        "provider_listing_id": str(LISTING_ID),
        "trading_date": "2026-08-08",
        "field_name": "rel_spx",
    }


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"code": "lowercase"}, "uppercase identifier"),
        ({"severity": "INFO"}, "WARNING or ERROR"),
        ({"message": "x" * 501}, "at most 500"),
        ({"field_name": "RelSPX"}, "lowercase identifier"),
    ],
)
def test_issue_rejects_unbounded_or_unsafe_values(
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _issue(**overrides)


def test_counts_expose_evaluated_compared_and_changed_ledgers() -> None:
    counts = FeatureCounts(
        selected_listings=2,
        excluded_listings=1,
        evaluated_rows=10,
        inserted_rows=2,
        updated_rows=3,
        unchanged_rows=4,
        deleted_rows=1,
    )

    assert counts.compared_rows == 9
    assert counts.changed_rows == 6
    assert counts.to_dict()["evaluated_rows"] == 10


def test_counts_reject_invalid_or_inconsistent_values() -> None:
    with pytest.raises(TypeError, match="integer"):
        FeatureCounts(evaluated_rows=True)
    with pytest.raises(ValueError, match="cannot exceed"):
        FeatureCounts(evaluated_rows=1, inserted_rows=2)


def test_summary_sorts_reasons_and_bounds_issue_samples() -> None:
    summary = TechIndicatorsSummary(
        counts=FeatureCounts(evaluated_rows=1, unchanged_rows=1),
        reason_counts=(
            ReasonCount("VERSION_DRIFT", 1),
            ReasonCount("TAIL_APPEND", 2),
        ),
        total_issue_count=3,
        issues=(_issue(),),
    )
    payload = summary.to_dict()

    assert [item["code"] for item in payload["reason_counts"]] == [
        "TAIL_APPEND",
        "VERSION_DRIFT",
    ]
    assert payload["issue_sample_count"] == 1
    assert payload["issues_truncated"] is True
    json.dumps(payload, allow_nan=False)


def test_summary_rejects_duplicate_reasons_and_unbounded_samples() -> None:
    with pytest.raises(ValueError, match="unique"):
        TechIndicatorsSummary(
            reason_counts=(ReasonCount("TAIL_APPEND", 1), ReasonCount("TAIL_APPEND", 2))
        )
    with pytest.raises(ValueError, match="100-sample"):
        TechIndicatorsSummary(
            total_issue_count=101,
            issues=tuple(_issue() for _ in range(101)),
        )


def test_run_result_is_compact_and_json_ready() -> None:
    result = TechIndicatorsRunResult(
        run_id=RUN_ID,
        status="succeeded",
        calculation_version="TECH_INDICATORS_V1",
        scope=TechIndicatorsScope(provider_listing_ids=(LISTING_ID,)),
        benchmark=ResolvedBenchmark(provider_listing_id=BENCHMARK_ID),
        summary=TechIndicatorsSummary(),
    )
    payload = result.to_dict()

    assert payload["run_id"] == str(RUN_ID)
    assert payload["benchmark"]["ticker"] == "SPX"
    assert "source_rows" not in payload
    assert "feature_rows" not in payload
    json.dumps(payload, allow_nan=False)


def test_run_result_rejects_invalid_status_and_component_types() -> None:
    with pytest.raises(ValueError, match="succeeded or failed"):
        TechIndicatorsRunResult(
            run_id=RUN_ID,
            status="running",
            calculation_version="TECH_INDICATORS_V1",
            scope=TechIndicatorsScope(),
            summary=TechIndicatorsSummary(),
        )
    with pytest.raises(TypeError, match="TechIndicatorsSummary"):
        TechIndicatorsRunResult(
            run_id=RUN_ID,
            status="succeeded",
            calculation_version="TECH_INDICATORS_V1",
            scope=TechIndicatorsScope(),
            summary=object(),  # type: ignore[arg-type]
        )


def test_models_are_immutable() -> None:
    row = _feature_row()

    with pytest.raises(FrozenInstanceError):
        row.history_observation_count = 2  # type: ignore[misc]
