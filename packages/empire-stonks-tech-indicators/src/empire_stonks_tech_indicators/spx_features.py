"""SPX subject eligibility and composed V1 feature calculations."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import numpy as np

from empire_stonks_tech_indicators.arrays import (
    CalculationArrays,
    MaskedFloatArray,
)
from empire_stonks_tech_indicators.exceptions import (
    TechIndicatorsValidationError,
)
from empire_stonks_tech_indicators.models import ReasonCount, SourceBar
from empire_stonks_tech_indicators.queries import BenchmarkHistory, EligibleListing
from empire_stonks_tech_indicators.spx_alignment import calculate_aligned_returns
from empire_stonks_tech_indicators.spx_beta import (
    SPX_BETA_FIELDS,
    calculate_spx_beta,
)
from empire_stonks_tech_indicators.spx_correlation import (
    SPX_CORRELATION_FIELDS,
    calculate_spx_correlation,
)
from empire_stonks_tech_indicators.spx_price_ratio import (
    SPX_PRICE_RATIO_FIELDS,
    calculate_spx_price_ratios,
)
from empire_stonks_tech_indicators.spx_relative_returns import (
    SPX_RELATIVE_RETURN_FIELDS,
    calculate_spx_relative_returns,
)
from empire_stonks_tech_indicators.subject_policy import (
    SPX_SUPPORTED_SUBJECT_MARKETS,
    is_spx_supported_subject,
)


SPX_FEATURE_FIELDS = (
    *SPX_PRICE_RATIO_FIELDS,
    *(field_name for field_name, _ in SPX_RELATIVE_RETURN_FIELDS),
    *(field_name for field_name, _ in SPX_BETA_FIELDS),
    *(field_name for field_name, _ in SPX_CORRELATION_FIELDS),
)
SUBJECT_UNSUPPORTED_REASON = "SUBJECT_UNSUPPORTED"


def _null_series(observation_count: int) -> MaskedFloatArray:
    values = np.full(observation_count, np.nan, dtype=np.float64)
    null_mask = np.ones(observation_count, dtype=np.bool_)
    values.setflags(write=False)
    null_mask.setflags(write=False)
    return MaskedFloatArray(values=values, null_mask=null_mask)


@dataclass(frozen=True, eq=False)
class SpxFeatureArrays:
    """All 11 persisted V1 SPX fields after subject eligibility enforcement."""

    subject: EligibleListing
    source_bars: tuple[SourceBar, ...]
    benchmark_provider_listing_id: UUID | None
    reason_counts: tuple[ReasonCount, ...]
    rel_spx: MaskedFloatArray
    pct_rel_spx_20: MaskedFloatArray
    pct_rel_spx_50: MaskedFloatArray
    relative_return_spx_20d_pct: MaskedFloatArray
    relative_return_spx_63d_pct: MaskedFloatArray
    relative_return_spx_126d_pct: MaskedFloatArray
    relative_return_spx_252d_pct: MaskedFloatArray
    spx_beta_60d: MaskedFloatArray
    spx_beta_252d: MaskedFloatArray
    spx_correlation_60d: MaskedFloatArray
    spx_correlation_252d: MaskedFloatArray

    def __post_init__(self) -> None:
        if not isinstance(self.subject, EligibleListing):
            raise TypeError("subject must be an EligibleListing.")
        if not isinstance(self.source_bars, tuple) or not self.source_bars:
            raise ValueError("source_bars must be a non-empty tuple.")
        if any(not isinstance(bar, SourceBar) for bar in self.source_bars):
            raise TypeError("source_bars must contain only SourceBar records.")
        if any(
            bar.provider_listing_id != self.subject.provider_listing_id
            for bar in self.source_bars
        ):
            raise ValueError("source_bars must belong to the subject listing.")
        if self.benchmark_provider_listing_id is not None and not isinstance(
            self.benchmark_provider_listing_id,
            UUID,
        ):
            raise TypeError("benchmark_provider_listing_id must be a UUID or None.")
        if not isinstance(self.reason_counts, tuple) or any(
            not isinstance(reason, ReasonCount) for reason in self.reason_counts
        ):
            raise TypeError("reason_counts must contain only ReasonCount records.")
        expected_supported = is_spx_supported_subject(self.subject)
        expected_reasons = (
            ()
            if expected_supported
            else (
                ReasonCount(
                    code=SUBJECT_UNSUPPORTED_REASON,
                    count=len(self.source_bars),
                ),
            )
        )
        if self.reason_counts != expected_reasons:
            raise ValueError("reason_counts do not match subject eligibility.")
        if expected_supported != (self.benchmark_provider_listing_id is not None):
            raise ValueError(
                "benchmark identity presence must match subject eligibility."
            )
        for field_name in SPX_FEATURE_FIELDS:
            series = getattr(self, field_name)
            if not isinstance(series, MaskedFloatArray):
                raise TypeError(f"{field_name} must be a MaskedFloatArray.")
            if len(series.values) != len(self.source_bars):
                raise ValueError(
                    "SPX feature arrays must match the subject observation count."
                )
            if not expected_supported and not series.null_mask.all():
                raise ValueError("unsupported subjects require null SPX fields.")

    @property
    def supported_subject(self) -> bool:
        return self.benchmark_provider_listing_id is not None

    @property
    def observation_count(self) -> int:
        return len(self.source_bars)


def calculate_spx_features(
    calculation_arrays: CalculationArrays,
    *,
    subject: EligibleListing,
    benchmark_history: BenchmarkHistory | None = None,
) -> SpxFeatureArrays:
    """Enforce subject support and calculate or null all 11 SPX fields."""

    if not isinstance(calculation_arrays, CalculationArrays):
        raise TypeError("calculation_arrays must be CalculationArrays.")
    if not isinstance(subject, EligibleListing):
        raise TypeError("subject must be an EligibleListing.")
    if benchmark_history is not None and not isinstance(
        benchmark_history,
        BenchmarkHistory,
    ):
        raise TypeError("benchmark_history must be a BenchmarkHistory or None.")
    if calculation_arrays.provider_listing_id != subject.provider_listing_id:
        raise ValueError("calculation arrays must belong to the subject listing.")

    if not is_spx_supported_subject(subject):
        return SpxFeatureArrays(
            subject=subject,
            source_bars=calculation_arrays.source_bars,
            benchmark_provider_listing_id=None,
            reason_counts=(
                ReasonCount(
                    code=SUBJECT_UNSUPPORTED_REASON,
                    count=calculation_arrays.observation_count,
                ),
            ),
            **{
                field_name: _null_series(calculation_arrays.observation_count)
                for field_name in SPX_FEATURE_FIELDS
            },
        )

    if benchmark_history is None:
        raise TechIndicatorsValidationError(
            "SPX benchmark history is required for a supported subject."
        )
    aligned_returns = calculate_aligned_returns(
        calculation_arrays,
        benchmark_history,
    )
    families = (
        calculate_spx_price_ratios(aligned_returns),
        calculate_spx_relative_returns(aligned_returns),
        calculate_spx_beta(aligned_returns),
        calculate_spx_correlation(aligned_returns),
    )
    fields = {
        field_name: getattr(family, field_name)
        for family in families
        for field_name in SPX_FEATURE_FIELDS
        if hasattr(family, field_name)
    }
    return SpxFeatureArrays(
        subject=subject,
        source_bars=calculation_arrays.source_bars,
        benchmark_provider_listing_id=(
            benchmark_history.benchmark.provider_listing_id
        ),
        reason_counts=(),
        **fields,
    )


__all__ = [
    "SPX_FEATURE_FIELDS",
    "SPX_SUPPORTED_SUBJECT_MARKETS",
    "SUBJECT_UNSUPPORTED_REASON",
    "SpxFeatureArrays",
    "calculate_spx_features",
    "is_spx_supported_subject",
]
