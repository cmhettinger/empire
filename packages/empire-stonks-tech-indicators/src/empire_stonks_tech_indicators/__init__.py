"""Reusable technical-indicator utilities for Empire stonks."""

from typing import TYPE_CHECKING

from empire_stonks_tech_indicators.config import (
    BenchmarkConfig,
    TechIndicatorsConfig,
)
from empire_stonks_tech_indicators.exceptions import (
    EmpireStonksTechIndicatorsError,
    TechIndicatorsCalculationError,
    TechIndicatorsConfigError,
    TechIndicatorsPersistenceError,
    TechIndicatorsValidationError,
    TechIndicatorsWorkflowError,
)
from empire_stonks_tech_indicators.models import (
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
from empire_stonks_tech_indicators.persistence import (
    FeatureRowKey,
    SlotWriteCounts,
    TechIndicatorsPayloadSlot,
    copy_feature_rows_between_slots,
    upsert_feature_rows,
)
from empire_stonks_tech_indicators.publication import (
    TECH_INDICATORS_WRITER_LOCK_KEY,
    TECH_INDICATORS_WRITER_LOCK_SEED,
    InPlaceSlotChanges,
    PublicationFinalizationResult,
    PublicationRecoveryAction,
    PublicationRecoveryDecision,
    PublicationSlotSelection,
    fail_unpublished_publication,
    finalize_publication,
    inspect_publication_recovery,
    select_inactive_payload_slots,
)
from empire_stonks_tech_indicators.published_queries import (
    PUBLISHED_MODEL_INPUT_FIELDS,
    PUBLISHED_RANKING_FIELDS,
    PublishedFeatureCoverage,
    PublishedFeatureFreshness,
    PublishedFeatureRankingRow,
    PublishedModelInputRow,
    PublishedModelInputSnapshot,
    PublishedReadinessToken,
    read_published_model_inputs,
    select_published_feature_coverage,
    select_published_feature_freshness,
    select_published_feature_ranking,
)
from empire_stonks_tech_indicators.queries import (
    BenchmarkHistory,
    EligibleListing,
    iter_source_bar_pages,
    load_spx_benchmark_history,
    resolve_spx_benchmark,
    select_eligible_listings,
)
from empire_stonks_tech_indicators.reporting_queries import (
    REPORT_FEATURE_FIELDS,
    ReportBenchmarkCoverage,
    ReportDatabaseSummary,
    ReportDateCoverage,
    ReportDimensionCoverage,
    ReportFeatureCoverage,
    ReportVersionCoverage,
    select_report_database_summary,
)
from empire_stonks_tech_indicators.reports import (
    BACKFILL_CORE_JOB_NAME,
    BACKFILL_REPORT_ID,
    BENCHMARK_CONTRACT_VERSION,
    DAILY_CORE_JOB_NAME,
    DAILY_REPORT_ID,
    NATIVE_VALUE_NOTE_MESSAGES,
    NATIVE_VALUE_NOTE_ORDER,
    PUBLICATION_READINESS_REASON_CODES,
    REPORT_DIAGNOSTIC_MESSAGE_CATALOG,
    REPORT_DIAGNOSTIC_SAMPLE_LIMIT,
    REPORT_MAXIMUM_BYTES,
    REPORT_MESSAGE_CATALOG,
    REPORT_PHASE_ORDER,
    REPORT_SCHEMA_VERSION,
    SOURCE_READINESS_REASON_CODES,
    LockOutcome,
    PublicationMethod,
    PublicationReadiness,
    PublicationReportPhase,
    ReportBackfill,
    ReportCounts,
    ReportCoverage,
    ReportCursor,
    ReportDatabasePerformance,
    ReportDiagnosticSample,
    ReportDimensionCount,
    ReportIdentity,
    ReportIssueAggregate,
    ReportLock,
    ReportNativeValueSemantics,
    ReportOutcome,
    ReportPerformance,
    ReportPhaseTiming,
    ReportProviderEvidence,
    ReportPublication,
    ReportReasonCount,
    ReportScope,
    ReportSourceBenchmark,
    ReportSourceReadiness,
    ReportThroughput,
    ReportVersions,
    ReportWrites,
    SourceReadinessStatus,
    TechIndicatorsReport,
    WorkflowKind,
    make_report_diagnostic_samples,
    render_tech_indicators_report_json,
)
from empire_stonks_tech_indicators.report_storage import (
    BACKFILL_PDF_REPORT_LOGICAL_NAME,
    BACKFILL_JSON_REPORT_LOGICAL_NAME,
    DAILY_PDF_REPORT_LOGICAL_NAME,
    DAILY_JSON_REPORT_LOGICAL_NAME,
    DEFAULT_REPORT_STORAGE_ROOT,
    JSON_REPORT_CONTENT_TYPE,
    JSON_REPORT_FILENAME,
    JSON_REPORT_LOGICAL_NAMES,
    JSON_REPORT_OBJECT_KIND,
    PDF_REPORT_CONTENT_TYPE,
    PDF_REPORT_FILENAME,
    PDF_REPORT_LOGICAL_NAMES,
    PDF_REPORT_OBJECT_KIND,
    build_tech_indicators_report_object_key,
    store_tech_indicators_json_report,
    store_tech_indicators_pdf_report,
    tech_indicators_report_metadata,
)
from empire_stonks_tech_indicators.report_pdf import (
    PDF_DIAGNOSTIC_SAMPLE_LIMIT,
    PDF_FEATURE_EXCEPTION_LIMIT,
    PDF_LISTING_SAMPLE_LIMIT,
    PDF_MAXIMUM_BYTES,
    PDF_MAXIMUM_PAGES,
    PdfFeatureFamilyCoverage,
    TECH_INDICATORS_PDF_FEATURE_FAMILIES,
    render_tech_indicators_report_pdf,
    roll_up_pdf_feature_coverage,
)
from empire_stonks_tech_indicators.readiness import (
    EODDATA_DAILY_JOB_NAME,
    SourceReadinessDecision,
    YAHOO_DAILY_JOB_NAME,
    decide_source_readiness,
)
from empire_stonks_tech_indicators.state import (
    ListingStateComparison,
    iter_state_comparison_pages,
)

if TYPE_CHECKING:
    from empire_stonks_tech_indicators.affected_ranges import (
        AffectedRange,
        AffectedRangePlan,
        AffectedRangeReason,
        plan_affected_ranges,
    )
    from empire_stonks_tech_indicators.assembly import assemble_feature_rows
    from empire_stonks_tech_indicators.arrays import (
        CalculationArrays,
        MaskedFloatArray,
        normalize_source_bars,
    )
    from empire_stonks_tech_indicators.returns import (
        ReturnArrays,
        calculate_returns,
    )
    from empire_stonks_tech_indicators.spx_alignment import (
        AlignedReturnArrays,
        calculate_aligned_returns,
    )
    from empire_stonks_tech_indicators.spx_beta import (
        SpxBetaArrays,
        calculate_spx_beta,
    )
    from empire_stonks_tech_indicators.spx_correlation import (
        SpxCorrelationArrays,
        calculate_spx_correlation,
    )
    from empire_stonks_tech_indicators.spx_features import (
        SpxFeatureArrays,
        calculate_spx_features,
        is_spx_supported_subject,
    )
    from empire_stonks_tech_indicators.spx_price_ratio import (
        SpxPriceRatioArrays,
        calculate_spx_price_ratios,
    )
    from empire_stonks_tech_indicators.spx_relative_returns import (
        SpxRelativeReturnArrays,
        calculate_spx_relative_returns,
    )
    from empire_stonks_tech_indicators.return_statistics import (
        ReturnStatisticArrays,
        calculate_return_statistics,
    )
    from empire_stonks_tech_indicators.rsi_atr import (
        RsiAtrArrays,
        calculate_rsi_atr,
    )
    from empire_stonks_tech_indicators.bar_structure import (
        BarStructureArrays,
        calculate_bar_structure,
    )
    from empire_stonks_tech_indicators.bollinger import (
        BollingerStateArrays,
        calculate_bollinger_state,
    )
    from empire_stonks_tech_indicators.range_relationships import (
        RangeRelationshipArrays,
        calculate_range_relationships,
    )
    from empire_stonks_tech_indicators.directional_movement import (
        DirectionalMovementArrays,
        calculate_directional_movement,
    )
    from empire_stonks_tech_indicators.volume_liquidity import (
        VolumeLiquidityArrays,
        calculate_volume_liquidity,
    )
    from empire_stonks_tech_indicators.streaks import (
        StreakArrays,
        calculate_streaks,
    )
    from empire_stonks_tech_indicators.moving_averages import (
        MovingAverageArrays,
        calculate_moving_averages,
    )
    from empire_stonks_tech_indicators.moving_average_trends import (
        MovingAverageTrendArrays,
        calculate_moving_average_trends,
    )
    from empire_stonks_tech_indicators.macd import (
        MacdArrays,
        calculate_macd,
    )
    from empire_stonks_tech_indicators.talib_adapter import (
        TALibAdapter,
        TALibRuntimeInfo,
    )
    from empire_stonks_tech_indicators.validation import validate_feature_rows


def __getattr__(name: str) -> object:
    if name in {
        "AffectedRange",
        "AffectedRangePlan",
        "AffectedRangeReason",
        "plan_affected_ranges",
    }:
        from empire_stonks_tech_indicators.affected_ranges import (
            AffectedRange,
            AffectedRangePlan,
            AffectedRangeReason,
            plan_affected_ranges,
        )

        exports = {
            "AffectedRange": AffectedRange,
            "AffectedRangePlan": AffectedRangePlan,
            "AffectedRangeReason": AffectedRangeReason,
            "plan_affected_ranges": plan_affected_ranges,
        }
        globals().update(exports)
        return exports[name]
    if name == "assemble_feature_rows":
        from empire_stonks_tech_indicators.assembly import assemble_feature_rows

        globals()[name] = assemble_feature_rows
        return assemble_feature_rows
    if name in {
        "CalculationArrays",
        "MaskedFloatArray",
        "normalize_source_bars",
    }:
        from empire_stonks_tech_indicators.arrays import (
            CalculationArrays,
            MaskedFloatArray,
            normalize_source_bars,
        )

        exports = {
            "CalculationArrays": CalculationArrays,
            "MaskedFloatArray": MaskedFloatArray,
            "normalize_source_bars": normalize_source_bars,
        }
        globals().update(exports)
        return exports[name]
    if name in {"ReturnArrays", "calculate_returns"}:
        from empire_stonks_tech_indicators.returns import (
            ReturnArrays,
            calculate_returns,
        )

        exports = {
            "ReturnArrays": ReturnArrays,
            "calculate_returns": calculate_returns,
        }
        globals().update(exports)
        return exports[name]
    if name in {"AlignedReturnArrays", "calculate_aligned_returns"}:
        from empire_stonks_tech_indicators.spx_alignment import (
            AlignedReturnArrays,
            calculate_aligned_returns,
        )

        exports = {
            "AlignedReturnArrays": AlignedReturnArrays,
            "calculate_aligned_returns": calculate_aligned_returns,
        }
        globals().update(exports)
        return exports[name]
    if name in {"SpxBetaArrays", "calculate_spx_beta"}:
        from empire_stonks_tech_indicators.spx_beta import (
            SpxBetaArrays,
            calculate_spx_beta,
        )

        exports = {
            "SpxBetaArrays": SpxBetaArrays,
            "calculate_spx_beta": calculate_spx_beta,
        }
        globals().update(exports)
        return exports[name]
    if name in {"SpxCorrelationArrays", "calculate_spx_correlation"}:
        from empire_stonks_tech_indicators.spx_correlation import (
            SpxCorrelationArrays,
            calculate_spx_correlation,
        )

        exports = {
            "SpxCorrelationArrays": SpxCorrelationArrays,
            "calculate_spx_correlation": calculate_spx_correlation,
        }
        globals().update(exports)
        return exports[name]
    if name in {
        "SpxFeatureArrays",
        "calculate_spx_features",
        "is_spx_supported_subject",
    }:
        from empire_stonks_tech_indicators.spx_features import (
            SpxFeatureArrays,
            calculate_spx_features,
            is_spx_supported_subject,
        )

        exports = {
            "SpxFeatureArrays": SpxFeatureArrays,
            "calculate_spx_features": calculate_spx_features,
            "is_spx_supported_subject": is_spx_supported_subject,
        }
        globals().update(exports)
        return exports[name]
    if name in {"SpxPriceRatioArrays", "calculate_spx_price_ratios"}:
        from empire_stonks_tech_indicators.spx_price_ratio import (
            SpxPriceRatioArrays,
            calculate_spx_price_ratios,
        )

        exports = {
            "SpxPriceRatioArrays": SpxPriceRatioArrays,
            "calculate_spx_price_ratios": calculate_spx_price_ratios,
        }
        globals().update(exports)
        return exports[name]
    if name in {"SpxRelativeReturnArrays", "calculate_spx_relative_returns"}:
        from empire_stonks_tech_indicators.spx_relative_returns import (
            SpxRelativeReturnArrays,
            calculate_spx_relative_returns,
        )

        exports = {
            "SpxRelativeReturnArrays": SpxRelativeReturnArrays,
            "calculate_spx_relative_returns": calculate_spx_relative_returns,
        }
        globals().update(exports)
        return exports[name]
    if name in {"ReturnStatisticArrays", "calculate_return_statistics"}:
        from empire_stonks_tech_indicators.return_statistics import (
            ReturnStatisticArrays,
            calculate_return_statistics,
        )

        exports = {
            "ReturnStatisticArrays": ReturnStatisticArrays,
            "calculate_return_statistics": calculate_return_statistics,
        }
        globals().update(exports)
        return exports[name]
    if name in {"RsiAtrArrays", "calculate_rsi_atr"}:
        from empire_stonks_tech_indicators.rsi_atr import (
            RsiAtrArrays,
            calculate_rsi_atr,
        )

        exports = {
            "RsiAtrArrays": RsiAtrArrays,
            "calculate_rsi_atr": calculate_rsi_atr,
        }
        globals().update(exports)
        return exports[name]
    if name in {"BarStructureArrays", "calculate_bar_structure"}:
        from empire_stonks_tech_indicators.bar_structure import (
            BarStructureArrays,
            calculate_bar_structure,
        )

        exports = {
            "BarStructureArrays": BarStructureArrays,
            "calculate_bar_structure": calculate_bar_structure,
        }
        globals().update(exports)
        return exports[name]
    if name in {"BollingerStateArrays", "calculate_bollinger_state"}:
        from empire_stonks_tech_indicators.bollinger import (
            BollingerStateArrays,
            calculate_bollinger_state,
        )

        exports = {
            "BollingerStateArrays": BollingerStateArrays,
            "calculate_bollinger_state": calculate_bollinger_state,
        }
        globals().update(exports)
        return exports[name]
    if name in {"RangeRelationshipArrays", "calculate_range_relationships"}:
        from empire_stonks_tech_indicators.range_relationships import (
            RangeRelationshipArrays,
            calculate_range_relationships,
        )

        exports = {
            "RangeRelationshipArrays": RangeRelationshipArrays,
            "calculate_range_relationships": calculate_range_relationships,
        }
        globals().update(exports)
        return exports[name]
    if name in {"DirectionalMovementArrays", "calculate_directional_movement"}:
        from empire_stonks_tech_indicators.directional_movement import (
            DirectionalMovementArrays,
            calculate_directional_movement,
        )

        exports = {
            "DirectionalMovementArrays": DirectionalMovementArrays,
            "calculate_directional_movement": calculate_directional_movement,
        }
        globals().update(exports)
        return exports[name]
    if name in {"VolumeLiquidityArrays", "calculate_volume_liquidity"}:
        from empire_stonks_tech_indicators.volume_liquidity import (
            VolumeLiquidityArrays,
            calculate_volume_liquidity,
        )

        exports = {
            "VolumeLiquidityArrays": VolumeLiquidityArrays,
            "calculate_volume_liquidity": calculate_volume_liquidity,
        }
        globals().update(exports)
        return exports[name]
    if name in {"StreakArrays", "calculate_streaks"}:
        from empire_stonks_tech_indicators.streaks import (
            StreakArrays,
            calculate_streaks,
        )

        exports = {
            "StreakArrays": StreakArrays,
            "calculate_streaks": calculate_streaks,
        }
        globals().update(exports)
        return exports[name]
    if name in {"MovingAverageArrays", "calculate_moving_averages"}:
        from empire_stonks_tech_indicators.moving_averages import (
            MovingAverageArrays,
            calculate_moving_averages,
        )

        exports = {
            "MovingAverageArrays": MovingAverageArrays,
            "calculate_moving_averages": calculate_moving_averages,
        }
        globals().update(exports)
        return exports[name]
    if name in {"MovingAverageTrendArrays", "calculate_moving_average_trends"}:
        from empire_stonks_tech_indicators.moving_average_trends import (
            MovingAverageTrendArrays,
            calculate_moving_average_trends,
        )

        exports = {
            "MovingAverageTrendArrays": MovingAverageTrendArrays,
            "calculate_moving_average_trends": calculate_moving_average_trends,
        }
        globals().update(exports)
        return exports[name]
    if name in {"MacdArrays", "calculate_macd"}:
        from empire_stonks_tech_indicators.macd import (
            MacdArrays,
            calculate_macd,
        )

        exports = {
            "MacdArrays": MacdArrays,
            "calculate_macd": calculate_macd,
        }
        globals().update(exports)
        return exports[name]
    if name in {"TALibAdapter", "TALibRuntimeInfo"}:
        from empire_stonks_tech_indicators.talib_adapter import (
            TALibAdapter,
            TALibRuntimeInfo,
        )

        exports = {
            "TALibAdapter": TALibAdapter,
            "TALibRuntimeInfo": TALibRuntimeInfo,
        }
        globals().update(exports)
        return exports[name]
    if name == "validate_feature_rows":
        from empire_stonks_tech_indicators.validation import validate_feature_rows

        globals()[name] = validate_feature_rows
        return validate_feature_rows
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "EmpireStonksTechIndicatorsError",
    "TechIndicatorsCalculationError",
    "TechIndicatorsConfigError",
    "TechIndicatorsPersistenceError",
    "TechIndicatorsValidationError",
    "TechIndicatorsWorkflowError",
    "BenchmarkConfig",
    "TechIndicatorsConfig",
    "AlignedReturnArrays",
    "BarStructureArrays",
    "BollingerStateArrays",
    "CalculationArrays",
    "DirectionalMovementArrays",
    "MaskedFloatArray",
    "RangeRelationshipArrays",
    "ReturnArrays",
    "ReturnStatisticArrays",
    "RsiAtrArrays",
    "BenchmarkHistory",
    "EligibleListing",
    "EODDATA_DAILY_JOB_NAME",
    "ListingStateComparison",
    "MacdArrays",
    "MovingAverageArrays",
    "MovingAverageTrendArrays",
    "SourceReadinessDecision",
    "SpxBetaArrays",
    "SpxCorrelationArrays",
    "SpxFeatureArrays",
    "SpxPriceRatioArrays",
    "SpxRelativeReturnArrays",
    "StreakArrays",
    "TALibAdapter",
    "TALibRuntimeInfo",
    "VolumeLiquidityArrays",
    "YAHOO_DAILY_JOB_NAME",
    "AffectedRange",
    "AffectedRangePlan",
    "AffectedRangeReason",
    "PUBLISHED_MODEL_INPUT_FIELDS",
    "PUBLISHED_RANKING_FIELDS",
    "PublishedFeatureCoverage",
    "PublishedFeatureFreshness",
    "PublishedFeatureRankingRow",
    "PublishedModelInputRow",
    "PublishedModelInputSnapshot",
    "PublishedReadinessToken",
    "REPORT_FEATURE_FIELDS",
    "ReportBenchmarkCoverage",
    "ReportDatabaseSummary",
    "ReportDateCoverage",
    "ReportDimensionCoverage",
    "ReportFeatureCoverage",
    "ReportVersionCoverage",
    "BACKFILL_JSON_REPORT_LOGICAL_NAME",
    "BACKFILL_PDF_REPORT_LOGICAL_NAME",
    "DAILY_JSON_REPORT_LOGICAL_NAME",
    "DAILY_PDF_REPORT_LOGICAL_NAME",
    "DEFAULT_REPORT_STORAGE_ROOT",
    "JSON_REPORT_CONTENT_TYPE",
    "JSON_REPORT_FILENAME",
    "JSON_REPORT_LOGICAL_NAMES",
    "JSON_REPORT_OBJECT_KIND",
    "PDF_REPORT_CONTENT_TYPE",
    "PDF_REPORT_FILENAME",
    "PDF_REPORT_LOGICAL_NAMES",
    "PDF_REPORT_OBJECT_KIND",
    "build_tech_indicators_report_object_key",
    "store_tech_indicators_json_report",
    "store_tech_indicators_pdf_report",
    "tech_indicators_report_metadata",
    "PDF_DIAGNOSTIC_SAMPLE_LIMIT",
    "PDF_FEATURE_EXCEPTION_LIMIT",
    "PDF_LISTING_SAMPLE_LIMIT",
    "PDF_MAXIMUM_BYTES",
    "PDF_MAXIMUM_PAGES",
    "PdfFeatureFamilyCoverage",
    "TECH_INDICATORS_PDF_FEATURE_FAMILIES",
    "render_tech_indicators_report_pdf",
    "roll_up_pdf_feature_coverage",
    "BACKFILL_CORE_JOB_NAME",
    "BACKFILL_REPORT_ID",
    "BENCHMARK_CONTRACT_VERSION",
    "DAILY_CORE_JOB_NAME",
    "DAILY_REPORT_ID",
    "NATIVE_VALUE_NOTE_MESSAGES",
    "NATIVE_VALUE_NOTE_ORDER",
    "PUBLICATION_READINESS_REASON_CODES",
    "REPORT_DIAGNOSTIC_MESSAGE_CATALOG",
    "REPORT_DIAGNOSTIC_SAMPLE_LIMIT",
    "REPORT_MAXIMUM_BYTES",
    "REPORT_MESSAGE_CATALOG",
    "REPORT_PHASE_ORDER",
    "REPORT_SCHEMA_VERSION",
    "SOURCE_READINESS_REASON_CODES",
    "LockOutcome",
    "PublicationMethod",
    "PublicationReadiness",
    "PublicationReportPhase",
    "ReportBackfill",
    "ReportCounts",
    "ReportCoverage",
    "ReportCursor",
    "ReportDatabasePerformance",
    "ReportDiagnosticSample",
    "ReportDimensionCount",
    "ReportIdentity",
    "ReportIssueAggregate",
    "ReportLock",
    "ReportNativeValueSemantics",
    "ReportOutcome",
    "ReportPerformance",
    "ReportPhaseTiming",
    "ReportProviderEvidence",
    "ReportPublication",
    "ReportReasonCount",
    "ReportScope",
    "ReportSourceBenchmark",
    "ReportSourceReadiness",
    "ReportThroughput",
    "ReportVersions",
    "ReportWrites",
    "SourceReadinessStatus",
    "TechIndicatorsReport",
    "WorkflowKind",
    "make_report_diagnostic_samples",
    "render_tech_indicators_report_json",
    "assemble_feature_rows",
    "calculate_aligned_returns",
    "calculate_spx_beta",
    "calculate_spx_correlation",
    "calculate_spx_features",
    "calculate_spx_price_ratios",
    "calculate_spx_relative_returns",
    "calculate_bar_structure",
    "calculate_bollinger_state",
    "calculate_directional_movement",
    "calculate_macd",
    "calculate_moving_averages",
    "calculate_moving_average_trends",
    "calculate_range_relationships",
    "calculate_return_statistics",
    "calculate_returns",
    "calculate_rsi_atr",
    "calculate_streaks",
    "calculate_volume_liquidity",
    "decide_source_readiness",
    "iter_source_bar_pages",
    "is_spx_supported_subject",
    "iter_state_comparison_pages",
    "load_spx_benchmark_history",
    "normalize_source_bars",
    "plan_affected_ranges",
    "resolve_spx_benchmark",
    "read_published_model_inputs",
    "select_published_feature_coverage",
    "select_published_feature_freshness",
    "select_published_feature_ranking",
    "select_report_database_summary",
    "select_eligible_listings",
    "validate_feature_rows",
    "FeatureRowKey",
    "SlotWriteCounts",
    "InPlaceSlotChanges",
    "PublicationFinalizationResult",
    "PublicationRecoveryAction",
    "PublicationRecoveryDecision",
    "PublicationSlotSelection",
    "TECH_INDICATORS_WRITER_LOCK_KEY",
    "TECH_INDICATORS_WRITER_LOCK_SEED",
    "TechIndicatorsPayloadSlot",
    "copy_feature_rows_between_slots",
    "fail_unpublished_publication",
    "finalize_publication",
    "inspect_publication_recovery",
    "select_inactive_payload_slots",
    "upsert_feature_rows",
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
