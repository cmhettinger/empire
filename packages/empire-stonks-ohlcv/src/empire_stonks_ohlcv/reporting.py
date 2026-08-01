"""Build and store provider-scoped OHLCV run reports."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from empire_core import ObjectStore, RunContext, StoredObject

from empire_stonks_ohlcv.config import DEFAULT_EODDATA_EXCHANGES, OHLCVConfig
from empire_stonks_ohlcv.daily_market_reporting import EODDataDailyMarketReport
from empire_stonks_ohlcv.eoddata import (
    EODDATA_PROVIDER_CODE,
    EODDataRetryEvent,
)
from empire_stonks_ohlcv.eoddata_import import EODDataImportResult
from empire_stonks_ohlcv.eoddata_planning import (
    EODDataDailyPlan,
    EODDataExchangeDailyPlan,
    EODDataExchangeWorkReason,
)
from empire_stonks_ohlcv.health import (
    ProviderMarketHealth,
    ProviderSeriesHealth,
    select_provider_market_health,
    select_provider_series_health,
    select_provider_weekday_gaps,
)
from empire_stonks_ohlcv.object_store import DEFAULT_STORAGE_ROOT
from empire_stonks_ohlcv.results import PersistenceCounts
from empire_stonks_ohlcv.reports.eoddata_daily_pdf import (
    EODDATA_DAILY_PDF_REPORT_ID,
    render_eoddata_daily_pdf,
)
from empire_stonks_ohlcv.reports.eoddata_daily_market_pdf import (
    EODDATA_DAILY_MARKET_PDF_REPORT_ID,
    render_eoddata_daily_market_pdf,
)
from empire_stonks_ohlcv.source_conventions import (
    EODDATA_DAILY_SOURCE,
    EODDATA_SYMBOL_LIST_SOURCE,
)
from empire_stonks_ohlcv.validation import (
    MAX_ISSUE_SAMPLES,
    BoundedIssueSummary,
    CrossFeedOutcomeCounts,
    FeedOutcomeCounts,
    SourceMarketWriteCounts,
)


REPORT_SCHEMA_VERSION = 2
REPORT_OBJECT_KIND = "stonks_ohlcv_provider_report"
REPORT_CONTENT_TYPE = "application/json"
PDF_REPORT_OBJECT_KIND = "stonks_ohlcv_provider_pdf_report"
PDF_REPORT_CONTENT_TYPE = "application/pdf"
MARKET_PDF_REPORT_OBJECT_KIND = "stonks_ohlcv_market_pdf_report"
_REPORT_FILENAME = "report.json"
_PDF_REPORT_FILENAME = "report.pdf"
_MARKET_PDF_REPORT_FILENAME = "daily-market-report.pdf"
_SOURCES = (EODDATA_SYMBOL_LIST_SOURCE, EODDATA_DAILY_SOURCE)
_PATH_TOKEN_PATTERN = re.compile(r"^[a-z0-9]+(?:[_-][a-z0-9]+)*$")


def build_eoddata_report(
    *,
    cursor: Any,
    import_result: EODDataImportResult | None,
    plan: EODDataDailyPlan,
    post_import_plan: EODDataDailyPlan,
    retry_events: tuple[EODDataRetryEvent, ...] = (),
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build the schema-version-2 EODData report from persisted state."""

    if import_result is not None and not isinstance(
        import_result,
        EODDataImportResult,
    ):
        raise TypeError("import_result must be an EODDataImportResult or None.")
    _validate_plans(plan, post_import_plan)
    _validate_retry_events(retry_events)
    if import_result is not None:
        _validate_import_scope(import_result)
        if import_result.effective_date != plan.end_date:
            raise ValueError("import_result must match the planning date.")
    generated = _generated_at(generated_at)
    as_of_date = plan.end_date
    market_health = {
        item.market: item
        for item in select_provider_market_health(
            cursor=cursor,
            provider_code=EODDATA_PROVIDER_CODE,
            as_of_date=as_of_date,
        )
    }
    series = select_provider_series_health(
        cursor=cursor,
        provider_code=EODDATA_PROVIDER_CODE,
        as_of_date=as_of_date,
    )
    _validate_health_scope(market_health, series)

    feed_counts: dict[tuple[str, str], FeedOutcomeCounts] = {
        (item.source_code, item.market): item
        for item in (() if import_result is None else import_result.feed_counts)
    }
    write_counts: dict[tuple[str, str], SourceMarketWriteCounts] = {
        (item.source_code, item.market): item
        for item in (() if import_result is None else import_result.write_counts)
    }
    cross_feed_counts: dict[str, CrossFeedOutcomeCounts] = {
        item.market: item
        for item in (
            () if import_result is None else import_result.cross_feed_counts
        )
    }
    series_by_market = {
        market: tuple(item for item in series if item.market == market)
        for market in DEFAULT_EODDATA_EXCHANGES
    }

    market_sections: list[dict[str, Any]] = []
    health_warning_count = 0
    for market in DEFAULT_EODDATA_EXCHANGES:
        initial_exchange_plan = _exchange_plan(plan, market)
        final_exchange_plan = _exchange_plan(post_import_plan, market)
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
        gaps = select_provider_weekday_gaps(
            cursor=cursor,
            provider_code=EODDATA_PROVIDER_CODE,
            market=market,
            as_of_date=as_of_date,
        )
        health_warning_count += len(stale) + len(no_data) + gaps.total_count
        market_sections.append(
            {
                "market": market,
                "row_rejections": _row_rejections(
                    import_result,
                    market=market,
                ),
                "listing_feed": _feed_count(
                    feed_counts,
                    source_code=EODDATA_SYMBOL_LIST_SOURCE.source_code,
                    market=market,
                ).to_dict(),
                "quote_or_bar_feed": _feed_count(
                    feed_counts,
                    source_code=EODDATA_DAILY_SOURCE.source_code,
                    market=market,
                ).to_dict(),
                "listing_write": _write_count(
                    write_counts,
                    source_code=EODDATA_SYMBOL_LIST_SOURCE.source_code,
                    market=market,
                    record_kind="listing",
                ).to_dict(),
                "bar_write": _write_count(
                    write_counts,
                    source_code=EODDATA_DAILY_SOURCE.source_code,
                    market=market,
                    record_kind="bar",
                ).to_dict(),
                "duplicate_outcomes": {
                    "listing_rows_collapsed": _feed_count(
                        feed_counts,
                        source_code=EODDATA_SYMBOL_LIST_SOURCE.source_code,
                        market=market,
                    ).duplicate_rows_collapsed,
                    "bar_rows_collapsed": _feed_count(
                        feed_counts,
                        source_code=EODDATA_DAILY_SOURCE.source_code,
                        market=market,
                    ).duplicate_rows_collapsed,
                },
                "cross_feed_outcomes": cross_feed_counts.get(
                    market,
                    CrossFeedOutcomeCounts(market=market),
                ).to_dict(),
                "session_coverage": _session_coverage(final_exchange_plan),
                "execution": _market_execution(
                    initial_exchange_plan,
                    retry_events=retry_events,
                    write_counts=write_counts,
                ),
                "coverage": _coverage(health),
                "freshness": _freshness(health, as_of_date),
                "stale_candidates": _bounded_candidates(stale),
                "no_data_candidates": _bounded_candidates(no_data),
                "weekday_gap_warnings": gaps.to_dict(),
            }
        )

    if import_result is not None and import_result.failures.total_count:
        raise ValueError(
            "EODData import hard failures must abort before report generation."
        )
    hard_failures = _empty_market_issue_summary()
    row_rejections = _row_rejections(import_result)
    outcome = _outcome(
        failure_count=hard_failures["total_count"],
        warning_count=(
            (0 if import_result is None else import_result.warnings.total_count)
            + health_warning_count
            + row_rejections["rejected_records"]
            + post_import_plan.failed_exchange_count
            + _missing_session_count(post_import_plan)
        ),
    )
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "provider_code": EODDATA_PROVIDER_CODE,
        "effective_date": as_of_date.isoformat(),
        "generated_at": generated.isoformat(),
        "outcome": outcome,
        "session_planning": _session_planning(plan, post_import_plan),
        "execution": _execution(
            plan,
            import_result=import_result,
            retry_events=retry_events,
        ),
        "sources": _source_sections(import_result),
        "markets": market_sections,
        "inactive_series": _inactive_series(market_health),
        "hard_failures": hard_failures,
        "row_rejections": row_rejections,
        "warnings": (
            BoundedIssueSummary().to_dict()
            if import_result is None
            else import_result.warnings.to_dict()
        ),
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


def store_eoddata_pdf_report(
    *,
    object_store: ObjectStore,
    run_context: RunContext,
    config: OHLCVConfig,
    report: dict[str, Any],
    storage_root: str = DEFAULT_STORAGE_ROOT,
    output_dir: str | Path | None = None,
) -> StoredObject:
    """Render and store the human-readable companion to an EODData report."""

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

    render_root = Path(
        output_dir or os.environ.get("EMPIRE_TEMP_DIR", "/tmp")
    )
    render_dir = (
        render_root
        / "empire"
        / "stonks-ohlcv"
        / str(run_context.run_id)
        / "reports"
    )
    result = render_eoddata_daily_pdf(
        report=report,
        output_dir=render_dir,
        filename=_PDF_REPORT_FILENAME,
    )
    return object_store.put_file(
        run_context=run_context,
        object_scope="run",
        domain="stonks",
        logical_name="eoddata_daily_pdf_report",
        storage_root=storage_root,
        object_key=build_report_object_key(
            storage_key=config.storage_key,
            run_context=run_context,
            provider_code=EODDATA_PROVIDER_CODE,
        ),
        filename=_PDF_REPORT_FILENAME,
        source_path=result.primary_artifact.path,
        move=False,
        content_type=PDF_REPORT_CONTENT_TYPE,
        object_kind=PDF_REPORT_OBJECT_KIND,
        metadata={
            "schema_version": REPORT_SCHEMA_VERSION,
            "report_id": EODDATA_DAILY_PDF_REPORT_ID,
            "provider_code": EODDATA_PROVIDER_CODE,
            "effective_date": report["effective_date"],
            "generated_at": report["generated_at"],
            "outcome": report["outcome"],
        },
    )


def store_eoddata_daily_market_pdf_report(
    *,
    object_store: ObjectStore,
    run_context: RunContext,
    config: OHLCVConfig,
    report: EODDataDailyMarketReport,
    storage_root: str = DEFAULT_STORAGE_ROOT,
    output_dir: str | Path | None = None,
) -> StoredObject:
    """Render and store the date-scoped EODData equity market report."""

    if not isinstance(object_store, ObjectStore):
        raise TypeError("object_store must be a Core ObjectStore.")
    if not isinstance(config, OHLCVConfig):
        raise TypeError("config must be an OHLCVConfig.")
    if not isinstance(report, EODDataDailyMarketReport):
        raise TypeError("report must be an EODDataDailyMarketReport.")
    _validate_run_context(run_context)
    if report.trading_date != run_context.effective_date:
        raise ValueError("report trading_date must match the Core run.")

    render_root = Path(output_dir or os.environ.get("EMPIRE_TEMP_DIR", "/tmp"))
    render_dir = (
        render_root
        / "empire"
        / "stonks-ohlcv"
        / str(run_context.run_id)
        / "reports"
    )
    result = render_eoddata_daily_market_pdf(
        report=report,
        output_dir=render_dir,
        filename=_MARKET_PDF_REPORT_FILENAME,
    )
    return object_store.put_file(
        run_context=run_context,
        object_scope="run",
        domain="stonks",
        logical_name="eoddata_daily_market_pdf_report",
        storage_root=storage_root,
        object_key=build_report_object_key(
            storage_key=config.storage_key,
            run_context=run_context,
            provider_code=EODDATA_PROVIDER_CODE,
        ),
        filename=_MARKET_PDF_REPORT_FILENAME,
        source_path=result.primary_artifact.path,
        move=False,
        content_type=PDF_REPORT_CONTENT_TYPE,
        object_kind=MARKET_PDF_REPORT_OBJECT_KIND,
        metadata={
            "report_id": EODDATA_DAILY_MARKET_PDF_REPORT_ID,
            "provider_code": EODDATA_PROVIDER_CODE,
            "trading_date": report.trading_date.isoformat(),
            "generated_at": report.generated_at.isoformat(),
            "source_bar_count": report.universe.source_bar_count,
            "equity_bar_count": report.universe.equity_bar_count,
        },
    )


def _source_sections(
    import_result: EODDataImportResult | None,
) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for source in _SOURCES:
        objects = [
            {"market": market, **acquired.to_dict()}
            for market in DEFAULT_EODDATA_EXCHANGES
            for acquired in (
                ()
                if import_result is None
                else import_result.acquired_objects
            )
            if acquired.source_code == source.source_code
            and acquired.filename == f"raw-{market.lower()}.json"
        ]
        sections.append(
            {
                "source_code": source.source_code,
                "parser_version": source.parser_version,
                "acquired_object_count": len(objects),
                "acquired_objects": objects,
            }
        )
    return sections


def _feed_count(
    counts: dict[tuple[str, str], FeedOutcomeCounts],
    *,
    source_code: str,
    market: str,
) -> FeedOutcomeCounts:
    return counts.get(
        (source_code, market),
        FeedOutcomeCounts(source_code=source_code, market=market),
    )


def _write_count(
    counts: dict[tuple[str, str], SourceMarketWriteCounts],
    *,
    source_code: str,
    market: str,
    record_kind: str,
) -> SourceMarketWriteCounts:
    return counts.get(
        (source_code, market),
        SourceMarketWriteCounts(
            source_code=source_code,
            market=market,
            record_kind=record_kind,
            counts=PersistenceCounts(),
        ),
    )


def _exchange_plan(
    plan: EODDataDailyPlan,
    market: str,
) -> EODDataExchangeDailyPlan:
    return next(item for item in plan.exchanges if item.exchange == market)


def _session_coverage(
    plan: EODDataExchangeDailyPlan,
) -> dict[str, Any]:
    return {
        "status": plan.status.value,
        "policy_code": plan.policy_code,
        "expected_session_count": len(plan.expected_sessions),
        "eligible_session_count": len(plan.eligible_sessions),
        "ineligible_session_count": plan.ineligible_session_count,
        "missing_eligible_session_count": len(plan.missing_sessions),
        "missing_eligible_dates": [
            item.session_date.isoformat() for item in plan.missing_sessions
        ],
        "latest_expected_session": (
            None
            if plan.latest_expected_session is None
            else plan.latest_expected_session.session_date.isoformat()
        ),
        "latest_expected_is_eligible": plan.latest_expected_is_eligible,
        "latest_expected_is_complete": plan.latest_expected_is_complete,
        "failure_reason": (
            None
            if plan.failure_reason is None
            else plan.failure_reason.value
        ),
    }


def _market_execution(
    plan: EODDataExchangeDailyPlan,
    *,
    retry_events: tuple[EODDataRetryEvent, ...],
    write_counts: dict[tuple[str, str], SourceMarketWriteCounts],
) -> dict[str, Any]:
    bar_write = _write_count(
        write_counts,
        source_code=EODDATA_DAILY_SOURCE.source_code,
        market=plan.exchange,
        record_kind="bar",
    )
    reconciliation = any(
        item.reason is EODDataExchangeWorkReason.RECENT_RECONCILIATION
        for item in plan.work
    )
    return {
        "requested": bool(plan.work),
        "work_reasons": [item.reason.value for item in plan.work],
        "retry_count": sum(
            item.exchange == plan.exchange for item in retry_events
        ),
        "corrected_current_rows": (
            bar_write.counts.updated if reconciliation else 0
        ),
    }


def _session_planning(
    plan: EODDataDailyPlan,
    post_import_plan: EODDataDailyPlan,
) -> dict[str, Any]:
    return {
        "planned_at": plan.planned_at.isoformat(),
        "reconciliation_sessions": plan.reconciliation_sessions,
        "expected_session_count": sum(
            len(item.expected_sessions) for item in post_import_plan.exchanges
        ),
        "eligible_session_count": sum(
            len(item.eligible_sessions) for item in post_import_plan.exchanges
        ),
        "ineligible_exchange_count": sum(
            item.status.value == "planned" and not item.eligible_sessions
            for item in post_import_plan.exchanges
        ),
        "missing_eligible_session_count": _missing_session_count(
            post_import_plan
        ),
        "failed_exchange_count": post_import_plan.failed_exchange_count,
        "inactive_exchange_count": post_import_plan.inactive_exchange_count,
        "planned_exchange_count": sum(bool(item.work) for item in plan.exchanges),
    }


def _execution(
    plan: EODDataDailyPlan,
    *,
    import_result: EODDataImportResult | None,
    retry_events: tuple[EODDataRetryEvent, ...],
) -> dict[str, Any]:
    return {
        "requested_exchange_count": sum(
            bool(item.work) for item in plan.exchanges
        ),
        "acquired_object_count": (
            0 if import_result is None else len(import_result.acquired_objects)
        ),
        "source_snapshot_count": (
            0 if import_result is None else len(import_result.source_snapshots)
        ),
        "retry_count": len(retry_events),
        "corrected_current_rows": _corrected_current_rows(
            plan,
            import_result,
        ),
    }


def _corrected_current_rows(
    plan: EODDataDailyPlan,
    import_result: EODDataImportResult | None,
) -> int:
    if import_result is None:
        return 0
    reconciliation_exchanges = {
        item.exchange
        for item in plan.work
        if item.reason is EODDataExchangeWorkReason.RECENT_RECONCILIATION
    }
    return sum(
        item.counts.updated
        for item in import_result.write_counts
        if item.record_kind == "bar"
        and item.market in reconciliation_exchanges
    )


def _missing_session_count(plan: EODDataDailyPlan) -> int:
    return sum(len(item.missing_sessions) for item in plan.exchanges)


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


def _row_rejections(
    import_result: EODDataImportResult | None,
    *,
    market: str | None = None,
) -> dict[str, Any]:
    reasons = tuple(
        item
        for item in (() if import_result is None else import_result.row_rejections)
        if market is None or item.market == market
    )
    return {
        "rejected_records": sum(item.rejected_records for item in reasons),
        "rejected_rows": sum(item.rejected_rows for item in reasons),
        "reasons": [item.to_dict() for item in reasons],
    }


def _empty_market_issue_summary() -> dict[str, Any]:
    return {
        "total_count": 0,
        "markets": [
            {
                "market": market,
                **BoundedIssueSummary().to_dict(),
                "reasons": [],
            }
            for market in DEFAULT_EODDATA_EXCHANGES
        ],
    }


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
        for market in import_result.exchanges
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
        for market in import_result.exchanges
    }
    if {
        (item.source_code, item.filename)
        for item in import_result.acquired_objects
    } != expected_objects:
        raise ValueError("EODData report acquired objects have an invalid scope.")


def _validate_plans(
    plan: object,
    post_import_plan: object,
) -> None:
    if not isinstance(plan, EODDataDailyPlan):
        raise TypeError("plan must be an EODDataDailyPlan.")
    if not isinstance(post_import_plan, EODDataDailyPlan):
        raise TypeError("post_import_plan must be an EODDataDailyPlan.")
    if (
        plan.start_date != plan.end_date
        or post_import_plan.start_date != plan.start_date
        or post_import_plan.end_date != plan.end_date
        or post_import_plan.planned_at != plan.planned_at
        or post_import_plan.reconciliation_sessions
        != plan.reconciliation_sessions
    ):
        raise ValueError("EODData report plans must share one daily scope.")


def _validate_retry_events(events: object) -> None:
    if not isinstance(events, tuple) or any(
        not isinstance(item, EODDataRetryEvent) for item in events
    ):
        raise TypeError("retry_events must contain EODDataRetryEvent records.")


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
        "session_planning",
        "execution",
        "sources",
        "markets",
        "inactive_series",
        "hard_failures",
        "row_rejections",
        "warnings",
        "native_value_semantics",
    }
    if set(report) != required:
        raise ValueError("report does not match schema version 2.")
    if report["schema_version"] != REPORT_SCHEMA_VERSION:
        raise ValueError("report schema_version must be 2.")
    if report["outcome"] not in {"PASS", "WARN", "FAIL"}:
        raise ValueError("report outcome is invalid.")
