"""Build and store provider-scoped OHLCV run reports."""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

from empire_core import ObjectStore, RunContext, StoredObject

from empire_stonks_ohlcv.config import DEFAULT_EODDATA_EXCHANGES, OHLCVConfig
from empire_stonks_ohlcv.eoddata import EODDATA_PROVIDER_CODE
from empire_stonks_ohlcv.eoddata_import import EODDataImportResult
from empire_stonks_ohlcv.health import (
    ProviderMarketHealth,
    ProviderSeriesHealth,
    select_provider_market_health,
    select_provider_series_health,
    select_provider_weekday_gaps,
)
from empire_stonks_ohlcv.object_store import DEFAULT_STORAGE_ROOT
from empire_stonks_ohlcv.results import ImportIssue
from empire_stonks_ohlcv.source_conventions import (
    EODDATA_DAILY_SOURCE,
    EODDATA_SYMBOL_LIST_SOURCE,
)
from empire_stonks_ohlcv.validation import MAX_ISSUE_SAMPLES, BoundedIssueSummary


REPORT_SCHEMA_VERSION = 1
REPORT_OBJECT_KIND = "stonks_ohlcv_provider_report"
REPORT_CONTENT_TYPE = "application/json"
_REPORT_FILENAME = "report.json"
_SOURCES = (EODDATA_SYMBOL_LIST_SOURCE, EODDATA_DAILY_SOURCE)
_PATH_TOKEN_PATTERN = re.compile(r"^[a-z0-9]+(?:[_-][a-z0-9]+)*$")


def build_eoddata_report(
    *,
    cursor: Any,
    import_result: EODDataImportResult,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build the schema-version-1 EODData report from persisted state."""

    if not isinstance(import_result, EODDataImportResult):
        raise TypeError("import_result must be an EODDataImportResult.")
    _validate_import_scope(import_result)
    generated = _generated_at(generated_at)
    as_of_date = import_result.effective_date
    market_health = {
        item.market: item
        for item in select_provider_market_health(
            cursor=cursor,
            provider_code=EODDATA_PROVIDER_CODE,
        )
    }
    series = select_provider_series_health(
        cursor=cursor,
        provider_code=EODDATA_PROVIDER_CODE,
    )
    _validate_health_scope(market_health, series)

    feed_counts = {
        (item.source_code, item.market): item
        for item in import_result.feed_counts
    }
    write_counts = {
        (item.source_code, item.market): item
        for item in import_result.write_counts
    }
    cross_feed_counts = {
        item.market: item for item in import_result.cross_feed_counts
    }
    series_by_market = {
        market: tuple(item for item in series if item.market == market)
        for market in DEFAULT_EODDATA_EXCHANGES
    }

    future_issues: list[ImportIssue] = []
    market_sections: list[dict[str, Any]] = []
    health_warning_count = 0
    for market in DEFAULT_EODDATA_EXCHANGES:
        health = market_health[market]
        market_series = series_by_market[market]
        active_series = tuple(item for item in market_series if item.is_active)
        stale = tuple(
            _series_candidate(item, as_of_date)
            for item in active_series
            if item.last_trading_date is not None
            and item.last_trading_date <= as_of_date
            and _weekday_age(item.last_trading_date, as_of_date) >= 2
        )
        no_data = tuple(
            _series_candidate(item, as_of_date)
            for item in active_series
            if item.last_trading_date is None
        )
        future = tuple(
            item
            for item in active_series
            if item.last_trading_date is not None
            and item.last_trading_date > as_of_date
        )
        for item in future:
            future_issues.append(
                ImportIssue(
                    code="future_last_trading_date",
                    message="Stored last trading date is after the report date.",
                    source_code=EODDATA_DAILY_SOURCE.source_code,
                    record_reference=f"{market}:{item.ticker}",
                )
            )
        gaps = select_provider_weekday_gaps(
            cursor=cursor,
            provider_code=EODDATA_PROVIDER_CODE,
            market=market,
        )
        health_warning_count += len(stale) + len(no_data) + gaps.total_count
        market_sections.append(
            {
                "market": market,
                "listing_feed": feed_counts[
                    (EODDATA_SYMBOL_LIST_SOURCE.source_code, market)
                ].to_dict(),
                "quote_or_bar_feed": feed_counts[
                    (EODDATA_DAILY_SOURCE.source_code, market)
                ].to_dict(),
                "listing_write": write_counts[
                    (EODDATA_SYMBOL_LIST_SOURCE.source_code, market)
                ].to_dict(),
                "bar_write": write_counts[
                    (EODDATA_DAILY_SOURCE.source_code, market)
                ].to_dict(),
                "duplicate_outcomes": {
                    "listing_rows_collapsed": feed_counts[
                        (EODDATA_SYMBOL_LIST_SOURCE.source_code, market)
                    ].duplicate_rows_collapsed,
                    "bar_rows_collapsed": feed_counts[
                        (EODDATA_DAILY_SOURCE.source_code, market)
                    ].duplicate_rows_collapsed,
                },
                "cross_feed_outcomes": cross_feed_counts[market].to_dict(),
                "coverage": _coverage(health),
                "freshness": _freshness(health, as_of_date),
                "stale_candidates": _bounded_candidates(stale),
                "no_data_candidates": _bounded_candidates(no_data),
                "weekday_gap_warnings": gaps.to_dict(),
            }
        )

    failures = _combine_issues(import_result.failures, tuple(future_issues))
    outcome = _outcome(
        failure_count=failures.total_count,
        warning_count=import_result.warnings.total_count + health_warning_count,
    )
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "provider_code": EODDATA_PROVIDER_CODE,
        "effective_date": as_of_date.isoformat(),
        "generated_at": generated.isoformat(),
        "outcome": outcome,
        "sources": _source_sections(import_result),
        "markets": market_sections,
        "inactive_series": _inactive_series(market_health),
        "failures": failures.to_dict(),
        "warnings": import_result.warnings.to_dict(),
        "native_value_semantics": {
            "interval": "daily",
            "adjustment_basis": "unspecified_by_eoddata_quote_list",
            "adjusted_close_present": False,
            "volume_basis": "provider_supplied_unspecified",
            "correction_behavior": "overwrite_same_provider_series_date",
            "currency": "best_effort_listing_metadata_only",
        },
    }


def eoddata_report_to_json(report: dict[str, Any]) -> str:
    """Serialize one report deterministically for Core object storage."""

    _validate_report(report)
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def build_report_object_key(
    *,
    storage_key: str,
    run_context: RunContext,
    provider_code: str,
) -> str:
    """Build the stable Core run path for one provider report."""

    _validate_run_context(run_context)
    if not isinstance(provider_code, str) or provider_code != provider_code.upper():
        raise ValueError("provider_code must be uppercase.")
    provider_path = provider_code.lower()
    if not _PATH_TOKEN_PATTERN.fullmatch(provider_path):
        raise ValueError("provider_code must be path-safe.")
    prefix = storage_key.strip("/")
    if not prefix or any(
        not _PATH_TOKEN_PATTERN.fullmatch(part) for part in prefix.split("/")
    ):
        raise ValueError("storage_key must contain path-safe segments.")
    effective_date = run_context.effective_date
    assert effective_date is not None
    return "/".join(
        (
            prefix,
            provider_path,
            "runs",
            f"{effective_date:%Y}",
            f"{effective_date:%m}",
            f"{effective_date:%d}",
            str(run_context.run_id),
            "reports",
        )
    )


def store_eoddata_report(
    *,
    object_store: ObjectStore,
    run_context: RunContext,
    config: OHLCVConfig,
    report: dict[str, Any],
    storage_root: str = DEFAULT_STORAGE_ROOT,
) -> StoredObject:
    """Store one durable EODData report under its active Core run."""

    if not isinstance(object_store, ObjectStore):
        raise TypeError("object_store must be a Core ObjectStore.")
    if not isinstance(config, OHLCVConfig):
        raise TypeError("config must be an OHLCVConfig.")
    _validate_run_context(run_context)
    _validate_report(report)
    if report["provider_code"] != EODDATA_PROVIDER_CODE:
        raise ValueError("report provider_code must be EODDATA.")
    if report["effective_date"] != run_context.effective_date.isoformat():
        raise ValueError("report effective_date must match the Core run.")
    return object_store.put_bytes(
        run_context=run_context,
        object_scope="run",
        domain="stonks",
        logical_name="eoddata_daily_report",
        storage_root=storage_root,
        object_key=build_report_object_key(
            storage_key=config.storage_key,
            run_context=run_context,
            provider_code=EODDATA_PROVIDER_CODE,
        ),
        filename=_REPORT_FILENAME,
        data=eoddata_report_to_json(report).encode("utf-8"),
        content_type=REPORT_CONTENT_TYPE,
        object_kind=REPORT_OBJECT_KIND,
        metadata={
            "schema_version": REPORT_SCHEMA_VERSION,
            "provider_code": EODDATA_PROVIDER_CODE,
            "effective_date": report["effective_date"],
            "generated_at": report["generated_at"],
            "outcome": report["outcome"],
        },
    )


def _source_sections(import_result: EODDataImportResult) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for source in _SOURCES:
        objects = []
        for market in DEFAULT_EODDATA_EXCHANGES:
            acquired = next(
                item
                for item in import_result.acquired_objects
                if item.source_code == source.source_code
                and item.filename == f"raw-{market.lower()}.json"
            )
            objects.append({"market": market, **acquired.to_dict()})
        sections.append(
            {
                "source_code": source.source_code,
                "parser_version": source.parser_version,
                "acquired_object_count": len(objects),
                "acquired_objects": objects,
            }
        )
    return sections


def _coverage(health: ProviderMarketHealth) -> dict[str, Any]:
    return {
        "listing_count": health.active_listing_count,
        "listings_with_bars": health.active_listings_with_bars,
        "listings_without_bars": health.active_listings_without_bars,
        "bar_count": health.active_bar_count,
        "first_trading_date": (
            None
            if health.first_trading_date is None
            else health.first_trading_date.isoformat()
        ),
        "last_trading_date": (
            None
            if health.last_trading_date is None
            else health.last_trading_date.isoformat()
        ),
    }


def _freshness(health: ProviderMarketHealth, as_of_date: date) -> dict[str, Any]:
    last_date = health.last_trading_date
    if last_date is None:
        return {
            "as_of_date": as_of_date.isoformat(),
            "latest_bar_calendar_age_days": None,
            "latest_bar_weekday_age": None,
            "status": "no_data",
        }
    calendar_age = (as_of_date - last_date).days
    if calendar_age < 0:
        return {
            "as_of_date": as_of_date.isoformat(),
            "latest_bar_calendar_age_days": calendar_age,
            "latest_bar_weekday_age": None,
            "status": "invalid_future_date",
        }
    weekday_age = _weekday_age(last_date, as_of_date)
    return {
        "as_of_date": as_of_date.isoformat(),
        "latest_bar_calendar_age_days": calendar_age,
        "latest_bar_weekday_age": weekday_age,
        "status": (
            "current"
            if weekday_age == 0
            else "delayed" if weekday_age == 1 else "stale_candidate"
        ),
    }


def _series_candidate(
    series: ProviderSeriesHealth,
    as_of_date: date,
) -> dict[str, Any]:
    last_date = series.last_trading_date
    return {
        "provider_listing_id": str(series.provider_listing_id),
        "market": series.market,
        "ticker": series.ticker,
        "last_trading_date": None if last_date is None else last_date.isoformat(),
        "latest_bar_calendar_age_days": (
            None if last_date is None else (as_of_date - last_date).days
        ),
        "latest_bar_weekday_age": (
            None if last_date is None else _weekday_age(last_date, as_of_date)
        ),
    }


def _bounded_candidates(candidates: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    samples = candidates[:MAX_ISSUE_SAMPLES]
    return {
        "total_count": len(candidates),
        "sample_count": len(samples),
        "truncated": len(samples) < len(candidates),
        "samples": list(samples),
    }


def _inactive_series(
    market_health: dict[str, ProviderMarketHealth],
) -> dict[str, Any]:
    markets = [
        {
            "market": market,
            "listing_count": market_health[market].inactive_listing_count,
            "listings_with_bars": (
                market_health[market].inactive_listings_with_bars
            ),
            "listings_without_bars": (
                market_health[market].inactive_listings_without_bars
            ),
            "bar_count": market_health[market].inactive_bar_count,
        }
        for market in DEFAULT_EODDATA_EXCHANGES
    ]
    return {
        "total_count": sum(item["listing_count"] for item in markets),
        "markets": markets,
    }


def _weekday_age(last_date: date, as_of_date: date) -> int:
    if last_date > as_of_date:
        raise ValueError("last_date must not be after as_of_date.")
    total_days = (as_of_date - last_date).days
    full_weeks, remainder = divmod(total_days, 7)
    weekdays = full_weeks * 5
    for offset in range(1, remainder + 1):
        if (last_date + timedelta(days=offset)).weekday() < 5:
            weekdays += 1
    return weekdays


def _combine_issues(
    existing: BoundedIssueSummary,
    additions: tuple[ImportIssue, ...],
) -> BoundedIssueSummary:
    samples = (existing.samples + additions)[:MAX_ISSUE_SAMPLES]
    return BoundedIssueSummary(
        total_count=existing.total_count + len(additions),
        samples=samples,
    )


def _outcome(*, failure_count: int, warning_count: int) -> str:
    if failure_count:
        return "FAIL"
    if warning_count:
        return "WARN"
    return "PASS"


def _validate_health_scope(
    market_health: dict[str, ProviderMarketHealth],
    series: tuple[ProviderSeriesHealth, ...],
) -> None:
    expected = set(DEFAULT_EODDATA_EXCHANGES)
    if set(market_health) != expected:
        raise ValueError("EODData market health must cover NYSE, NASDAQ, and AMEX.")
    if any(item.market not in expected for item in series):
        raise ValueError("EODData series health contains an unsupported market.")


def _validate_import_scope(import_result: EODDataImportResult) -> None:
    expected_feed_keys = {
        (source.source_code, market)
        for source in _SOURCES
        for market in DEFAULT_EODDATA_EXCHANGES
    }
    if {
        (item.source_code, item.market) for item in import_result.feed_counts
    } != expected_feed_keys:
        raise ValueError("EODData report feed counts have an invalid scope.")
    if {
        (item.source_code, item.market) for item in import_result.write_counts
    } != expected_feed_keys:
        raise ValueError("EODData report write counts have an invalid scope.")
    expected_objects = {
        (source.source_code, f"raw-{market.lower()}.json")
        for source in _SOURCES
        for market in DEFAULT_EODDATA_EXCHANGES
    }
    if {
        (item.source_code, item.filename)
        for item in import_result.acquired_objects
    } != expected_objects:
        raise ValueError("EODData report acquired objects have an invalid scope.")


def _generated_at(value: datetime | None) -> datetime:
    generated = value or datetime.now(UTC)
    if not isinstance(generated, datetime) or generated.tzinfo is None:
        raise ValueError("generated_at must be a timezone-aware datetime.")
    return generated.astimezone(UTC)


def _validate_run_context(run_context: RunContext) -> None:
    if not isinstance(run_context, RunContext):
        raise TypeError("run_context must be a Core RunContext.")
    if run_context.domain != "stonks" or run_context.status != "started":
        raise ValueError("run_context must be an active stonks run.")
    if run_context.effective_date is None:
        raise ValueError("run_context effective_date is required.")


def _validate_report(report: object) -> None:
    if not isinstance(report, dict):
        raise TypeError("report must be a dictionary.")
    required = {
        "schema_version",
        "provider_code",
        "effective_date",
        "generated_at",
        "outcome",
        "sources",
        "markets",
        "inactive_series",
        "failures",
        "warnings",
        "native_value_semantics",
    }
    if set(report) != required:
        raise ValueError("report does not match schema version 1.")
    if report["schema_version"] != REPORT_SCHEMA_VERSION:
        raise ValueError("report schema_version must be 1.")
    if report["outcome"] not in {"PASS", "WARN", "FAIL"}:
        raise ValueError("report outcome is invalid.")
