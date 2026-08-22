"""Complete V1 feature-row assembly from aligned calculation families."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from empire_stonks_tech_indicators.arrays import CalculationArrays
from empire_stonks_tech_indicators.config import DEFAULT_CALCULATION_VERSION
from empire_stonks_tech_indicators.models import FeatureRow, PYTHON_FEATURE_FIELDS
from empire_stonks_tech_indicators.queries import BenchmarkHistory, EligibleListing
from empire_stonks_tech_indicators.validation import (
    _calculate_expected_feature_state,
    _validate_feature_rows_against_state,
    _validate_subject,
)


def _validate_metadata(
    *,
    calculation_version: object,
    calculated_at: object,
    run_id: object,
) -> None:
    if not isinstance(calculation_version, str):
        raise TypeError("calculation_version must be a string.")
    if calculation_version != DEFAULT_CALCULATION_VERSION:
        raise ValueError(
            f"calculation_version must be {DEFAULT_CALCULATION_VERSION}."
        )
    if not isinstance(calculated_at, datetime):
        raise TypeError("calculated_at must be a datetime.")
    if calculated_at.utcoffset() is None:
        raise ValueError("calculated_at must be timezone-aware.")
    if run_id is not None and not isinstance(run_id, UUID):
        raise TypeError("run_id must be a UUID or None.")


def assemble_feature_rows(
    calculation_arrays: CalculationArrays,
    *,
    subject: EligibleListing,
    calculated_at: datetime,
    calculation_version: str = DEFAULT_CALCULATION_VERSION,
    benchmark_history: BenchmarkHistory | None = None,
    run_id: UUID | None = None,
) -> tuple[FeatureRow, ...]:
    """Calculate, assemble, and validate one complete chronological V1 image.

    The returned rows preserve the exact source-prefix order and contain all
    65 package-written payload columns. PostgreSQL-owned lifecycle timestamps
    and generated columns are deliberately absent.
    """

    if not isinstance(calculation_arrays, CalculationArrays):
        raise TypeError("calculation_arrays must be CalculationArrays.")
    if not isinstance(subject, EligibleListing):
        raise TypeError("subject must be an EligibleListing.")
    if benchmark_history is not None and not isinstance(
        benchmark_history,
        BenchmarkHistory,
    ):
        raise TypeError("benchmark_history must be a BenchmarkHistory or None.")
    _validate_metadata(
        calculation_version=calculation_version,
        calculated_at=calculated_at,
        run_id=run_id,
    )
    _validate_subject(calculation_arrays, subject)

    expected_state = _calculate_expected_feature_state(
        calculation_arrays,
        subject=subject,
        benchmark_history=benchmark_history,
    )
    float_fields = tuple(expected_state.persisted)
    expected_float_fields = tuple(
        field_name
        for field_name in PYTHON_FEATURE_FIELDS
        if field_name not in {"consecutive_up_days", "consecutive_down_days"}
    )
    if float_fields != expected_float_fields:
        raise AssertionError("feature assembly field inventory drifted")

    rows = tuple(
        FeatureRow(
            source=source,
            relative_strength_benchmark_provider_listing_id=(
                expected_state.spx.benchmark_provider_listing_id
            ),
            history_observation_count=index + 1,
            calculation_version=calculation_version,
            run_id=run_id,
            calculated_at=calculated_at,
            consecutive_up_days=int(
                expected_state.streaks.consecutive_up_days[index]
            ),
            consecutive_down_days=int(
                expected_state.streaks.consecutive_down_days[index]
            ),
            **{
                field_name: expected_state.persisted[field_name].value_at(index)
                for field_name in expected_float_fields
            },
        )
        for index, source in enumerate(calculation_arrays.source_bars)
    )
    _validate_feature_rows_against_state(
        rows,
        calculation_arrays=calculation_arrays,
        subject=subject,
        expected_state=expected_state,
    )
    return rows


__all__ = ["assemble_feature_rows"]
