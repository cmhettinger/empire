"""Build and store reports for complete or partial Stooq history runs."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from empire_core import ObjectStore, RunContext, StoredObject

from empire_stonks_ohlcv.config import OHLCVConfig
from empire_stonks_ohlcv.object_store import DEFAULT_STORAGE_ROOT
from empire_stonks_ohlcv.reporting import (
    PDF_REPORT_CONTENT_TYPE,
    PDF_REPORT_OBJECT_KIND,
    REPORT_CONTENT_TYPE,
    REPORT_OBJECT_KIND,
    REPORT_SCHEMA_VERSION,
    build_report_object_key,
)
from empire_stonks_ohlcv.reports.stooq_history_pdf import (
    STOOQ_HISTORY_PDF_REPORT_ID,
    render_stooq_history_pdf,
)
from empire_stonks_ohlcv.results import AcquiredObject
from empire_stonks_ohlcv.source_conventions import STOOQ_HISTORY_SOURCE
from empire_stonks_ohlcv.source_snapshots import SourceSnapshotRegistration
from empire_stonks_ohlcv.stooq_history import (
    STOOQ_HISTORY_ARCHIVE_NAME,
    STOOQ_HISTORY_CORE_ARCHIVE_NAME,
    STOOQ_HISTORY_MARKETS,
    STOOQ_HISTORY_PROVIDER_CODE,
    StooqHistoryParseProgress,
    StooqHistoryParseSummary,
    StooqHistoryScope,
)
from empire_stonks_ohlcv.stooq_history_writer import StooqHistoryWriteSummary
from empire_stonks_ohlcv.validation import MAX_ISSUE_SAMPLES


STOOQ_HISTORY_REPORT_TYPE = "stooq_history_backfill"
STOOQ_HISTORY_REPORT_LOGICAL_NAME = "stooq_history_report"
STOOQ_HISTORY_REPORT_FILENAME = "report.json"
STOOQ_HISTORY_PDF_REPORT_LOGICAL_NAME = "stooq_history_pdf_report"
STOOQ_HISTORY_PDF_REPORT_FILENAME = "report.pdf"

StooqHistoryReportStatus = Literal["complete", "partial"]


@dataclass(frozen=True)
class StooqHistoryMarketCoverage:
    """Persisted listing and bar coverage for one selected Stooq market."""

    market: str
    listing_count: int = 0
    active_listing_count: int = 0
    inactive_listing_count: int = 0
    listings_with_scoped_bars: int = 0
    persisted_bar_count: int = 0
    scoped_bar_count: int = 0
    first_persisted_trading_date: date | None = None
    last_persisted_trading_date: date | None = None
    first_scoped_trading_date: date | None = None
    last_scoped_trading_date: date | None = None

    def __post_init__(self) -> None:
        if self.market not in STOOQ_HISTORY_MARKETS:
            raise ValueError("market is not supported.")
        for field_name in (
            "listing_count",
            "active_listing_count",
            "inactive_listing_count",
            "listings_with_scoped_bars",
            "persisted_bar_count",
            "scoped_bar_count",
        ):
            _nonnegative_int(field_name, getattr(self, field_name))
        if self.active_listing_count + self.inactive_listing_count != (
            self.listing_count
        ):
            raise ValueError("active and inactive listings must match total listings.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "listing_count": self.listing_count,
            "active_listing_count": self.active_listing_count,
            "inactive_listing_count": self.inactive_listing_count,
            "listings_with_scoped_bars": self.listings_with_scoped_bars,
            "persisted_bar_count": self.persisted_bar_count,
            "scoped_bar_count": self.scoped_bar_count,
            "first_persisted_trading_date": _date_text(
                self.first_persisted_trading_date
            ),
            "last_persisted_trading_date": _date_text(
                self.last_persisted_trading_date
            ),
            "first_scoped_trading_date": _date_text(
                self.first_scoped_trading_date
            ),
            "last_scoped_trading_date": _date_text(
                self.last_scoped_trading_date
            ),
        }


@dataclass(frozen=True)
class StooqHistorySeriesCoverage:
    """One bounded provider-series coverage sample."""

    provider_listing_id: UUID
    market: str
    ticker: str
    status: str
    persisted_bar_count: int
    scoped_bar_count: int
    first_persisted_trading_date: date | None
    last_persisted_trading_date: date | None
    first_scoped_trading_date: date | None
    last_scoped_trading_date: date | None

    def __post_init__(self) -> None:
        if not isinstance(self.provider_listing_id, UUID):
            raise TypeError("provider_listing_id must be a UUID.")
        if self.market not in STOOQ_HISTORY_MARKETS:
            raise ValueError("market is not supported.")
        if not isinstance(self.ticker, str) or not self.ticker:
            raise ValueError("ticker is required.")
        if self.status not in {"ACTIVE", "INACTIVE"}:
            raise ValueError("status is invalid.")
        _nonnegative_int("persisted_bar_count", self.persisted_bar_count)
        _nonnegative_int("scoped_bar_count", self.scoped_bar_count)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_listing_id": str(self.provider_listing_id),
            "market": self.market,
            "ticker": self.ticker,
            "status": self.status,
            "persisted_bar_count": self.persisted_bar_count,
            "scoped_bar_count": self.scoped_bar_count,
            "first_persisted_trading_date": _date_text(
                self.first_persisted_trading_date
            ),
            "last_persisted_trading_date": _date_text(
                self.last_persisted_trading_date
            ),
            "first_scoped_trading_date": _date_text(
                self.first_scoped_trading_date
            ),
            "last_scoped_trading_date": _date_text(
                self.last_scoped_trading_date
            ),
        }


@dataclass(frozen=True)
class StooqHistoryCoverage:
    """Bounded coverage query result for the exact backfill identity scope."""

    markets: tuple[StooqHistoryMarketCoverage, ...]
    series_samples: tuple[StooqHistorySeriesCoverage, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.markets, tuple) or any(
            not isinstance(item, StooqHistoryMarketCoverage)
            for item in self.markets
        ):
            raise TypeError("markets must contain StooqHistoryMarketCoverage.")
        if not isinstance(self.series_samples, tuple) or any(
            not isinstance(item, StooqHistorySeriesCoverage)
            for item in self.series_samples
        ):
            raise TypeError(
                "series_samples must contain StooqHistorySeriesCoverage."
            )
        if len(self.series_samples) > MAX_ISSUE_SAMPLES:
            raise ValueError("series_samples exceeds the shared sample limit.")

    @property
    def series_count(self) -> int:
        return sum(item.listing_count for item in self.markets)

    def to_dict(self) -> dict[str, Any]:
        return {
            "series_count": self.series_count,
            "sample_count": len(self.series_samples),
            "truncated": len(self.series_samples) < self.series_count,
            "markets": [item.to_dict() for item in self.markets],
            "series_samples": [
                item.to_dict() for item in self.series_samples
            ],
        }


def select_stooq_history_coverage(
    *,
    cursor: Any,
    scope: StooqHistoryScope,
) -> StooqHistoryCoverage:
    """Select persisted total and requested-date coverage for one run scope."""

    if not isinstance(scope, StooqHistoryScope):
        raise TypeError("scope must be a StooqHistoryScope.")
    tickers = list(scope.tickers) if scope.tickers else None
    markets = list(scope.markets)
    date_values = (
        scope.start_date,
        scope.start_date,
        scope.end_date,
        scope.end_date,
    )
    identity_values = (
        STOOQ_HISTORY_PROVIDER_CODE,
        markets,
        tickers,
        tickers,
    )
    cursor.execute(
        _MARKET_COVERAGE_SQL,
        (*date_values, *date_values, *date_values, *date_values, *identity_values),
    )
    by_market = {
        row[0]: StooqHistoryMarketCoverage(*row) for row in cursor.fetchall()
    }
    market_results = tuple(
        by_market.get(market, StooqHistoryMarketCoverage(market=market))
        for market in scope.markets
    )

    cursor.execute(
        _SERIES_COVERAGE_SQL,
        (
            *identity_values,
            MAX_ISSUE_SAMPLES,
            *date_values,
            *date_values,
            *date_values,
        ),
    )
    samples = tuple(
        StooqHistorySeriesCoverage(*row) for row in cursor.fetchall()
    )
    return StooqHistoryCoverage(
        markets=market_results,
        series_samples=samples,
    )


def build_stooq_history_report(
    *,
    cursor: Any,
    scope: StooqHistoryScope,
    chunk_size: int,
    acquired_object: AcquiredObject | None,
    source_snapshot: SourceSnapshotRegistration | None,
    parse_summary: StooqHistoryParseSummary | None,
    parse_progress: StooqHistoryParseProgress,
    write_summary: StooqHistoryWriteSummary,
    run_status: StooqHistoryReportStatus,
    failed_stage: str | None = None,
    elapsed_seconds: float = 0.0,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a complete or partial historical report from durable state."""

    _validate_report_inputs(
        scope=scope,
        chunk_size=chunk_size,
        acquired_object=acquired_object,
        source_snapshot=source_snapshot,
        parse_summary=parse_summary,
        parse_progress=parse_progress,
        write_summary=write_summary,
        run_status=run_status,
        failed_stage=failed_stage,
        elapsed_seconds=elapsed_seconds,
    )
    coverage = select_stooq_history_coverage(cursor=cursor, scope=scope)
    parse_by_market = (
        {item.market: item.to_dict() for item in parse_summary.market_counts}
        if parse_summary is not None
        else {}
    )
    warnings = _warnings(
        parse_summary=parse_summary,
        parse_progress=parse_progress,
        write_summary=write_summary,
    )
    failure_count = 1 if run_status == "partial" else 0
    outcome = (
        "FAIL"
        if failure_count
        else "WARN"
        if warnings["total_count"]
        else "PASS"
    )
    generated = _generated_at(generated_at)
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "report_type": STOOQ_HISTORY_REPORT_TYPE,
        "provider_code": STOOQ_HISTORY_PROVIDER_CODE,
        "source_code": STOOQ_HISTORY_SOURCE.source_code,
        "effective_date": scope.effective_date.isoformat(),
        "generated_at": generated.isoformat(),
        "outcome": outcome,
        "run_status": run_status,
        "input": {
            "scope": scope.to_dict(),
            "chunk_size": chunk_size,
            "manual_acquisition": True,
            "operator_filename": STOOQ_HISTORY_ARCHIVE_NAME,
            "archive": (
                acquired_object.to_dict()
                if acquired_object is not None
                else None
            ),
            "source_snapshot": (
                source_snapshot.to_dict()
                if source_snapshot is not None
                else None
            ),
        },
        "progress": {
            "elapsed_seconds": elapsed_seconds,
            "parse": (
                parse_summary.to_dict()
                if parse_summary is not None
                else parse_progress.to_dict()
            ),
            "write": write_summary.to_dict(),
        },
        "markets": [
            {
                "market": market.market,
                "parse_counts": parse_by_market.get(market.market),
                "coverage": market.to_dict(),
            }
            for market in coverage.markets
        ],
        "coverage": coverage.to_dict(),
        "hard_failures": {
            "total_count": failure_count,
            "failed_stage": failed_stage,
            "message": (
                "Stooq history run did not complete."
                if failure_count
                else None
            ),
        },
        "warnings": warnings,
        "native_value_semantics": {
            "interval": "daily",
            "adjustment_basis": "unspecified_by_stooq_history_bundle",
            "adjusted_close_present": False,
            "volume_basis": "provider_supplied_unspecified_fractional_allowed",
            "currency": "unspecified",
            "corporate_action_interpretation": "unspecified",
            "correction_behavior": "overwrite_same_provider_series_date",
            "canonical_identity_mutation": False,
        },
    }


def stooq_history_report_to_json(report: dict[str, Any]) -> str:
    """Serialize one validated Stooq history report deterministically."""

    _validate_report(report)
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def store_stooq_history_report(
    *,
    object_store: ObjectStore,
    run_context: RunContext,
    config: OHLCVConfig,
    report: dict[str, Any],
    storage_root: str = DEFAULT_STORAGE_ROOT,
) -> StoredObject:
    """Store one durable Stooq history JSON report under its active run."""

    if not isinstance(object_store, ObjectStore):
        raise TypeError("object_store must be a Core ObjectStore.")
    if not isinstance(config, OHLCVConfig):
        raise TypeError("config must be an OHLCVConfig.")
    _validate_run_context(run_context)
    _validate_report(report)
    if report["effective_date"] != run_context.effective_date.isoformat():
        raise ValueError("report effective_date must match the Core run.")
    return object_store.put_bytes(
        run_context=run_context,
        object_scope="run",
        domain="stonks",
        logical_name=STOOQ_HISTORY_REPORT_LOGICAL_NAME,
        storage_root=storage_root,
        object_key=build_report_object_key(
            storage_key=config.storage_key,
            run_context=run_context,
            provider_code=STOOQ_HISTORY_PROVIDER_CODE,
        ),
        filename=STOOQ_HISTORY_REPORT_FILENAME,
        data=stooq_history_report_to_json(report).encode("utf-8"),
        content_type=REPORT_CONTENT_TYPE,
        object_kind=REPORT_OBJECT_KIND,
        metadata={
            "schema_version": REPORT_SCHEMA_VERSION,
            "report_type": STOOQ_HISTORY_REPORT_TYPE,
            "provider_code": STOOQ_HISTORY_PROVIDER_CODE,
            "source_code": STOOQ_HISTORY_SOURCE.source_code,
            "effective_date": report["effective_date"],
            "generated_at": report["generated_at"],
            "outcome": report["outcome"],
            "run_status": report["run_status"],
        },
    )


def store_stooq_history_pdf_report(
    *,
    object_store: ObjectStore,
    run_context: RunContext,
    config: OHLCVConfig,
    report: dict[str, Any],
    storage_root: str = DEFAULT_STORAGE_ROOT,
    output_dir: str | Path | None = None,
) -> StoredObject:
    """Render and store the human-readable companion to a Stooq report."""

    if not isinstance(object_store, ObjectStore):
        raise TypeError("object_store must be a Core ObjectStore.")
    if not isinstance(config, OHLCVConfig):
        raise TypeError("config must be an OHLCVConfig.")
    _validate_run_context(run_context)
    _validate_report(report)
    if report["provider_code"] != STOOQ_HISTORY_PROVIDER_CODE:
        raise ValueError("report provider_code must be STOOQ.")
    if report["effective_date"] != run_context.effective_date.isoformat():
        raise ValueError("report effective_date must match the Core run.")

    render_root = Path(output_dir or os.environ.get("EMPIRE_TEMP_DIR", "/tmp"))
    render_dir = (
        render_root
        / "empire"
        / "stonks-ohlcv"
        / str(run_context.run_id)
        / "reports"
    )
    result = render_stooq_history_pdf(
        report=report,
        output_dir=render_dir,
        filename=STOOQ_HISTORY_PDF_REPORT_FILENAME,
    )
    return object_store.put_file(
        run_context=run_context,
        object_scope="run",
        domain="stonks",
        logical_name=STOOQ_HISTORY_PDF_REPORT_LOGICAL_NAME,
        storage_root=storage_root,
        object_key=build_report_object_key(
            storage_key=config.storage_key,
            run_context=run_context,
            provider_code=STOOQ_HISTORY_PROVIDER_CODE,
        ),
        filename=STOOQ_HISTORY_PDF_REPORT_FILENAME,
        source_path=result.primary_artifact.path,
        move=False,
        content_type=PDF_REPORT_CONTENT_TYPE,
        object_kind=PDF_REPORT_OBJECT_KIND,
        metadata={
            "schema_version": REPORT_SCHEMA_VERSION,
            "report_id": STOOQ_HISTORY_PDF_REPORT_ID,
            "report_type": STOOQ_HISTORY_REPORT_TYPE,
            "provider_code": STOOQ_HISTORY_PROVIDER_CODE,
            "source_code": STOOQ_HISTORY_SOURCE.source_code,
            "effective_date": report["effective_date"],
            "generated_at": report["generated_at"],
            "outcome": report["outcome"],
            "run_status": report["run_status"],
        },
    )


def _warnings(
    *,
    parse_summary: StooqHistoryParseSummary | None,
    parse_progress: StooqHistoryParseProgress,
    write_summary: StooqHistoryWriteSummary,
) -> dict[str, Any]:
    rejected = (
        parse_summary.rejected_records
        if parse_summary is not None
        else parse_progress.rejected_records
    )
    duplicates = (
        parse_summary.duplicate_rows_collapsed
        if parse_summary is not None
        else parse_progress.duplicate_rows_collapsed
    )
    inactive = write_summary.skipped_inactive_bars
    empty_files = (
        parse_summary.empty_files_skipped
        if parse_summary is not None
        else parse_progress.empty_files_skipped
    )
    samples = (
        [item.to_dict() for item in parse_summary.issue_samples]
        if parse_summary is not None
        else []
    )
    return {
        "total_count": rejected + duplicates + inactive + empty_files,
        "rejected_records": rejected,
        "duplicate_rows_collapsed": duplicates,
        "skipped_inactive_bars": inactive,
        "empty_files_skipped": empty_files,
        "sample_count": len(samples),
        "samples": samples,
    }


def _validate_report_inputs(
    *,
    scope: StooqHistoryScope,
    chunk_size: int,
    acquired_object: AcquiredObject | None,
    source_snapshot: SourceSnapshotRegistration | None,
    parse_summary: StooqHistoryParseSummary | None,
    parse_progress: StooqHistoryParseProgress,
    write_summary: StooqHistoryWriteSummary,
    run_status: object,
    failed_stage: str | None,
    elapsed_seconds: float,
) -> None:
    if not isinstance(scope, StooqHistoryScope):
        raise TypeError("scope must be a StooqHistoryScope.")
    if isinstance(chunk_size, bool) or not isinstance(chunk_size, int):
        raise TypeError("chunk_size must be an integer.")
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero.")
    if acquired_object is not None and not isinstance(acquired_object, AcquiredObject):
        raise TypeError("acquired_object must be an AcquiredObject or None.")
    if source_snapshot is not None and not isinstance(
        source_snapshot,
        SourceSnapshotRegistration,
    ):
        raise TypeError("source_snapshot must be a registration or None.")
    if parse_summary is not None and not isinstance(
        parse_summary,
        StooqHistoryParseSummary,
    ):
        raise TypeError("parse_summary must be a summary or None.")
    if not isinstance(parse_progress, StooqHistoryParseProgress):
        raise TypeError("parse_progress must be StooqHistoryParseProgress.")
    if not isinstance(write_summary, StooqHistoryWriteSummary):
        raise TypeError("write_summary must be StooqHistoryWriteSummary.")
    if run_status not in {"complete", "partial"}:
        raise ValueError("run_status must be complete or partial.")
    if run_status == "complete" and (
        acquired_object is None
        or source_snapshot is None
        or parse_summary is None
        or failed_stage is not None
    ):
        raise ValueError("complete reports require complete successful inputs.")
    if acquired_object is not None and (
        acquired_object.source_code != STOOQ_HISTORY_SOURCE.source_code
        or acquired_object.filename != STOOQ_HISTORY_CORE_ARCHIVE_NAME
    ):
        raise ValueError("acquired_object must be the Core Stooq history archive.")
    if source_snapshot is not None and (
        acquired_object is None
        or source_snapshot.object_id != acquired_object.object_id
        or source_snapshot.provider_code != STOOQ_HISTORY_PROVIDER_CODE
        or source_snapshot.source_code != STOOQ_HISTORY_SOURCE.source_code
    ):
        raise ValueError("source_snapshot must match the acquired Stooq archive.")
    if parse_summary is not None and (
        parse_summary.chunks_emitted != write_summary.chunks_completed
        or parse_summary.accepted_records
        != write_summary.bar_counts.input_count
        + write_summary.skipped_inactive_bars
    ):
        raise ValueError("complete parser and writer counts must reconcile.")
    if write_summary.chunks_attempted > parse_progress.chunks_emitted:
        raise ValueError("writer attempts must not exceed emitted parser chunks.")
    if run_status == "partial" and failed_stage not in {
        "acquisition",
        "parsing",
        "persistence",
        "reporting",
    }:
        raise ValueError("partial reports require a valid failed_stage.")
    if isinstance(elapsed_seconds, bool) or not isinstance(
        elapsed_seconds,
        (int, float),
    ):
        raise TypeError("elapsed_seconds must be a number.")
    if elapsed_seconds < 0:
        raise ValueError("elapsed_seconds must be non-negative.")


def _validate_report(report: object) -> None:
    if not isinstance(report, dict):
        raise TypeError("report must be a dictionary.")
    required = {
        "schema_version",
        "report_type",
        "provider_code",
        "source_code",
        "effective_date",
        "generated_at",
        "outcome",
        "run_status",
        "input",
        "progress",
        "markets",
        "coverage",
        "hard_failures",
        "warnings",
        "native_value_semantics",
    }
    if set(report) != required:
        raise ValueError("report does not match the Stooq history schema.")
    if report["schema_version"] != REPORT_SCHEMA_VERSION:
        raise ValueError("report schema_version is invalid.")
    if report["report_type"] != STOOQ_HISTORY_REPORT_TYPE:
        raise ValueError("report_type is invalid.")
    if report["provider_code"] != STOOQ_HISTORY_PROVIDER_CODE:
        raise ValueError("report provider_code must be STOOQ.")
    if report["source_code"] != STOOQ_HISTORY_SOURCE.source_code:
        raise ValueError("report source_code must be stooq_history.")
    if report["outcome"] not in {"PASS", "WARN", "FAIL"}:
        raise ValueError("report outcome is invalid.")
    if report["run_status"] not in {"complete", "partial"}:
        raise ValueError("report run_status is invalid.")


def _validate_run_context(run_context: RunContext) -> None:
    if not isinstance(run_context, RunContext):
        raise TypeError("run_context must be a Core RunContext.")
    if run_context.domain != "stonks" or run_context.status != "started":
        raise ValueError("run_context must be an active stonks run.")
    if run_context.effective_date is None:
        raise ValueError("run_context effective_date is required.")


def _generated_at(value: datetime | None) -> datetime:
    generated = value or datetime.now(UTC)
    if not isinstance(generated, datetime) or generated.tzinfo is None:
        raise ValueError("generated_at must be timezone-aware.")
    return generated.astimezone(UTC)


def _date_text(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def _nonnegative_int(field_name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer.")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative.")


_MARKET_COVERAGE_SQL = """
    SELECT
        listing.market,
        count(DISTINCT listing.provider_listing_id),
        count(DISTINCT listing.provider_listing_id)
            FILTER (WHERE listing.status = 'ACTIVE'),
        count(DISTINCT listing.provider_listing_id)
            FILTER (WHERE listing.status = 'INACTIVE'),
        count(DISTINCT listing.provider_listing_id)
            FILTER (
                WHERE daily.trading_date IS NOT NULL
                  AND (%s::date IS NULL OR daily.trading_date >= %s::date)
                  AND (%s::date IS NULL OR daily.trading_date <= %s::date)
            ),
        count(daily.trading_date),
        count(daily.trading_date)
            FILTER (
                WHERE (%s::date IS NULL OR daily.trading_date >= %s::date)
                  AND (%s::date IS NULL OR daily.trading_date <= %s::date)
            ),
        min(daily.trading_date),
        max(daily.trading_date),
        min(daily.trading_date)
            FILTER (
                WHERE (%s::date IS NULL OR daily.trading_date >= %s::date)
                  AND (%s::date IS NULL OR daily.trading_date <= %s::date)
            ),
        max(daily.trading_date)
            FILTER (
                WHERE (%s::date IS NULL OR daily.trading_date >= %s::date)
                  AND (%s::date IS NULL OR daily.trading_date <= %s::date)
            )
    FROM stonks.provider_listing AS listing
    LEFT JOIN stonks.ohlcv_daily AS daily
      USING (provider_listing_id)
    WHERE listing.provider_code = %s
      AND listing.market = ANY(%s)
      AND (%s::text[] IS NULL OR listing.ticker = ANY(%s))
    GROUP BY listing.market
    ORDER BY listing.market
"""


_SERIES_COVERAGE_SQL = """
    WITH sampled_listing AS (
        SELECT
            provider_listing_id,
            market,
            ticker,
            status
        FROM stonks.provider_listing
        WHERE provider_code = %s
          AND market = ANY(%s)
          AND (%s::text[] IS NULL OR ticker = ANY(%s))
        ORDER BY market, ticker, provider_listing_id
        LIMIT %s
    )
    SELECT
        listing.provider_listing_id,
        listing.market,
        listing.ticker,
        listing.status,
        count(daily.trading_date),
        count(daily.trading_date)
            FILTER (
                WHERE (%s::date IS NULL OR daily.trading_date >= %s::date)
                  AND (%s::date IS NULL OR daily.trading_date <= %s::date)
            ),
        min(daily.trading_date),
        max(daily.trading_date),
        min(daily.trading_date)
            FILTER (
                WHERE (%s::date IS NULL OR daily.trading_date >= %s::date)
                  AND (%s::date IS NULL OR daily.trading_date <= %s::date)
            ),
        max(daily.trading_date)
            FILTER (
                WHERE (%s::date IS NULL OR daily.trading_date >= %s::date)
                  AND (%s::date IS NULL OR daily.trading_date <= %s::date)
            )
    FROM sampled_listing AS listing
    LEFT JOIN stonks.ohlcv_daily AS daily
      USING (provider_listing_id)
    GROUP BY
        listing.provider_listing_id,
        listing.market,
        listing.ticker,
        listing.status
    ORDER BY listing.market, listing.ticker, listing.provider_listing_id
"""
