from __future__ import annotations

import json

import pytest

from empire_stonks_ohlcv import (
    MAX_ISSUE_SAMPLES,
    BoundedIssueSummary,
    CrossFeedOutcomeCounts,
    EODDATA_DAILY_SOURCE,
    FeedOutcomeCounts,
    ImportIssue,
    ParsedProviderOutput,
    PersistenceCounts,
    ProviderValidationResult,
    RowRejectionSummary,
    SourceMarketWriteCounts,
)


def _issue(index: int = 1) -> ImportIssue:
    return ImportIssue(
        code="invalid_row",
        message="A provider row was rejected.",
        source_code="eoddata_daily",
        record_reference=f"NYSE:ROW{index}",
    )


def _feed_counts(
    *,
    source_code: str = "eoddata_daily",
    market: str = "NYSE",
) -> FeedOutcomeCounts:
    return FeedOutcomeCounts(
        source_code=source_code,
        market=market,
        input_rows=12,
        accepted_records=9,
        rejected_records=2,
        duplicate_rows_collapsed=1,
        warning_count=1,
    )


def test_bounded_issue_summary_preserves_totals_and_safe_samples() -> None:
    summary = BoundedIssueSummary(total_count=125, samples=(_issue(1), _issue(2)))

    assert summary.sample_count == 2
    assert summary.truncated is True
    assert json.loads(json.dumps(summary.to_dict())) == {
        "total_count": 125,
        "sample_count": 2,
        "truncated": True,
        "samples": [_issue(1).to_dict(), _issue(2).to_dict()],
    }


def test_empty_issue_summary_is_not_truncated() -> None:
    assert BoundedIssueSummary().to_dict() == {
        "total_count": 0,
        "sample_count": 0,
        "truncated": False,
        "samples": [],
    }


@pytest.mark.parametrize(
    ("values", "message"),
    (
        ({"total_count": -1}, "total_count"),
        ({"total_count": 0, "samples": (_issue(),)}, "total_count"),
        ({"total_count": 1, "samples": [_issue()]}, "samples"),
        (
            {
                "total_count": MAX_ISSUE_SAMPLES + 1,
                "samples": tuple(
                    _issue(index) for index in range(MAX_ISSUE_SAMPLES + 1)
                ),
            },
            "at most",
        ),
    ),
)
def test_bounded_issue_summary_rejects_invalid_members(
    values: dict[str, object],
    message: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        BoundedIssueSummary(**values)  # type: ignore[arg-type]


def test_feed_outcome_counts_are_json_ready_and_keep_grains_separate() -> None:
    counts = _feed_counts()

    assert counts.to_dict() == {
        "source_code": "eoddata_daily",
        "market": "NYSE",
        "input_rows": 12,
        "accepted_records": 9,
        "rejected_records": 2,
        "duplicate_rows_collapsed": 1,
        "warning_count": 1,
    }


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    (
        ("source_code", "EODDATA", "path-safe"),
        ("market", " NYSE", "trimmed"),
        ("input_rows", True, "integer"),
        ("accepted_records", -1, "non-negative"),
        ("rejected_records", 13, "cannot exceed"),
        ("duplicate_rows_collapsed", 13, "cannot exceed"),
    ),
)
def test_feed_outcome_counts_reject_invalid_values(
    field_name: str,
    value: object,
    message: str,
) -> None:
    values: dict[str, object] = {
        "source_code": "eoddata_daily",
        "market": "NYSE",
        "input_rows": 12,
        "accepted_records": 9,
        "rejected_records": 2,
        "duplicate_rows_collapsed": 1,
        "warning_count": 1,
    }
    values[field_name] = value

    with pytest.raises((TypeError, ValueError), match=message):
        FeedOutcomeCounts(**values)  # type: ignore[arg-type]


def test_source_market_write_counts_preserve_record_kind() -> None:
    result = SourceMarketWriteCounts(
        source_code="eoddata_daily",
        market="NASDAQ",
        record_kind="bar",
        counts=PersistenceCounts(inserted=3, unchanged=2, derived_updated=1),
    )

    assert result.to_dict() == {
        "source_code": "eoddata_daily",
        "market": "NASDAQ",
        "record_kind": "bar",
        "counts": {
            "inserted": 3,
            "updated": 0,
            "unchanged": 2,
            "derived_updated": 1,
        },
        "skipped_inactive": 0,
    }


@pytest.mark.parametrize("record_kind", ("bars", "quote", ""))
def test_source_market_write_counts_reject_unknown_record_kind(
    record_kind: str,
) -> None:
    with pytest.raises(ValueError, match="listing or bar"):
        SourceMarketWriteCounts(
            source_code="eoddata_daily",
            market="NYSE",
            record_kind=record_kind,
            counts=PersistenceCounts(),
        )


def test_provider_validation_result_carries_output_counts_and_issues() -> None:
    output = ParsedProviderOutput(sources=(EODDATA_DAILY_SOURCE,), batches=())
    result = ProviderValidationResult(
        output=output,
        feed_counts=(_feed_counts(),),
        row_rejections=(
            RowRejectionSummary(
                source_code="eoddata_daily",
                market="NYSE",
                code="invalid_row",
                rejected_records=2,
                rejected_rows=3,
                samples=(_issue(),),
            ),
        ),
        warnings=BoundedIssueSummary(total_count=1),
    )

    assert result.to_dict() == {
        "sources": [EODDATA_DAILY_SOURCE.to_dict()],
        "listing_count": 0,
        "bar_count": 0,
        "feed_counts": [_feed_counts().to_dict()],
        "row_rejections": [result.row_rejections[0].to_dict()],
        "failures": BoundedIssueSummary().to_dict(),
        "warnings": BoundedIssueSummary(total_count=1).to_dict(),
        "cross_feed_counts": None,
    }


def test_cross_feed_counts_are_typed_scoped_and_json_ready() -> None:
    counts = CrossFeedOutcomeCounts(
        market="NYSE",
        listings_without_bars=3,
        bars_without_listings=2,
    )

    assert counts.to_dict() == {
        "market": "NYSE",
        "listings_without_bars": 3,
        "bars_without_listings": 2,
    }


def test_provider_validation_result_requires_exact_unique_source_counts() -> None:
    output = ParsedProviderOutput(sources=(EODDATA_DAILY_SOURCE,), batches=())

    with pytest.raises(ValueError, match="unique source/market"):
        ProviderValidationResult(
            output=output,
            feed_counts=(_feed_counts(), _feed_counts()),
        )
    with pytest.raises(ValueError, match="exactly match"):
        ProviderValidationResult(
            output=output,
            feed_counts=(_feed_counts(source_code="other_daily"),),
        )
