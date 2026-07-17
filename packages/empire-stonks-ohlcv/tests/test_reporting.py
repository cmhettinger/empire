from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

import empire_stonks_ohlcv.reporting as reporting
from empire_core import ObjectStore, RunContext, StorageRoot, StoredObject
from empire_stonks_ohlcv import (
    AcquiredObject,
    BoundedIssueSummary,
    CrossFeedOutcomeCounts,
    EODDATA_DAILY_SOURCE,
    EODDATA_SYMBOL_LIST_SOURCE,
    EODDataCredentials,
    EODDataImportResult,
    FeedOutcomeCounts,
    OHLCVConfig,
    PersistenceCounts,
    ProviderMarketHealth,
    ProviderSeriesHealth,
    ProviderWeekdayGapResult,
    REPORT_OBJECT_KIND,
    SourceMarketWriteCounts,
    SourceSnapshotRegistration,
    WeekdayGapCandidate,
    build_eoddata_report,
    build_report_object_key,
    eoddata_report_to_json,
    store_eoddata_report,
)


EFFECTIVE_DATE = date(2026, 7, 15)
GENERATED_AT = datetime(2026, 7, 16, 2, 30, tzinfo=UTC)
RUN_ID = UUID("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee")
MARKETS = ("NYSE", "NASDAQ", "AMEX")
SECRET = "must-not-appear-in-report"


def _import_result() -> EODDataImportResult:
    acquired: list[AcquiredObject] = []
    snapshots: list[SourceSnapshotRegistration] = []
    feed_counts: list[FeedOutcomeCounts] = []
    write_counts: list[SourceMarketWriteCounts] = []
    object_number = 1
    for source in (EODDATA_SYMBOL_LIST_SOURCE, EODDATA_DAILY_SOURCE):
        for market in MARKETS:
            acquired_object = AcquiredObject(
                source_code=source.source_code,
                object_id=UUID(int=object_number),
                object_key=f"stonks/ohlcv/eoddata/{source.source_code}",
                filename=f"raw-{market.lower()}.json",
                size_bytes=100 + object_number,
                checksum_sha256=f"{object_number:064x}",
            )
            acquired.append(acquired_object)
            snapshots.append(
                SourceSnapshotRegistration(
                    source_snapshot_id=UUID(int=100 + object_number),
                    object_id=acquired_object.object_id,
                    provider_code="EODDATA",
                    source_code=source.source_code,
                    content_sha256=acquired_object.checksum_sha256,
                    snapshot_inserted=True,
                    object_link_inserted=True,
                )
            )
            is_listing = source == EODDATA_SYMBOL_LIST_SOURCE
            feed_counts.append(
                FeedOutcomeCounts(
                    source_code=source.source_code,
                    market=market,
                    input_rows=4,
                    accepted_records=3 if is_listing else 2,
                    rejected_records=0,
                    duplicate_rows_collapsed=1,
                    warning_count=1,
                )
            )
            write_counts.append(
                SourceMarketWriteCounts(
                    source_code=source.source_code,
                    market=market,
                    record_kind="listing" if is_listing else "bar",
                    counts=PersistenceCounts(inserted=3 if is_listing else 2),
                )
            )
            object_number += 1
    return EODDataImportResult(
        effective_date=EFFECTIVE_DATE,
        acquired_objects=tuple(acquired),
        source_snapshots=tuple(snapshots),
        feed_counts=tuple(feed_counts),
        write_counts=tuple(write_counts),
        failures=BoundedIssueSummary(),
        warnings=BoundedIssueSummary(),
        cross_feed_counts=tuple(
            CrossFeedOutcomeCounts(
                market=market,
                listings_without_bars=1,
                bars_without_listings=0,
            )
            for market in MARKETS
        ),
    )


def _market_health() -> tuple[ProviderMarketHealth, ...]:
    return tuple(
        ProviderMarketHealth(
            provider_code="EODDATA",
            market=market,
            active_listing_count=2,
            inactive_listing_count=1,
            active_listings_with_bars=1,
            active_listings_without_bars=1,
            inactive_listings_with_bars=1,
            inactive_listings_without_bars=0,
            active_bar_count=10,
            inactive_bar_count=3,
            first_trading_date=date(2026, 7, 1),
            last_trading_date=date(2026, 7, 13),
        )
        for market in MARKETS
    )


def _series_health() -> tuple[ProviderSeriesHealth, ...]:
    values: list[ProviderSeriesHealth] = []
    identity = 1000
    for market in MARKETS:
        for ticker, status, last_date, bar_count in (
            ("ACTIVE.STALE", "ACTIVE", date(2026, 7, 13), 10),
            ("ACTIVE.EMPTY", "ACTIVE", None, 0),
            ("INACTIVE.OLD", "INACTIVE", date(2026, 6, 1), 3),
        ):
            values.append(
                ProviderSeriesHealth(
                    provider_listing_id=UUID(int=identity),
                    provider_code="EODDATA",
                    market=market,
                    ticker=ticker,
                    status=status,  # type: ignore[arg-type]
                    first_seen=date(2026, 7, 1),
                    last_seen=EFFECTIVE_DATE,
                    first_trading_date=(
                        None if last_date is None else date(2026, 7, 1)
                    ),
                    last_trading_date=last_date,
                    bar_count=bar_count,
                )
            )
            identity += 1
    return tuple(values)


def _install_health(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, object]]:
    calls: list[tuple[str, object]] = []

    def market_health(**values: object) -> tuple[ProviderMarketHealth, ...]:
        calls.append(("markets", values["provider_code"]))
        return _market_health()

    def series_health(**values: object) -> tuple[ProviderSeriesHealth, ...]:
        calls.append(("series", values["provider_code"]))
        return _series_health()

    def gaps(**values: object) -> ProviderWeekdayGapResult:
        market = values["market"]
        calls.append(("gaps", market))
        return ProviderWeekdayGapResult(
            provider_code="EODDATA",
            market=market,  # type: ignore[arg-type]
            total_count=1,
            samples=(
                WeekdayGapCandidate(
                    provider_listing_id=UUID(int=2000),
                    market=market,  # type: ignore[arg-type]
                    ticker="ACTIVE.STALE",
                    previous_trading_date=date(2026, 7, 10),
                    missing_weekday=date(2026, 7, 13),
                    next_trading_date=date(2026, 7, 14),
                ),
            ),
        )

    monkeypatch.setattr(reporting, "select_provider_market_health", market_health)
    monkeypatch.setattr(reporting, "select_provider_series_health", series_health)
    monkeypatch.setattr(reporting, "select_provider_weekday_gaps", gaps)
    return calls


def _run_context() -> RunContext:
    return RunContext(
        run_id=RUN_ID,
        domain="stonks",
        job_name="stonks_ohlcv_eoddata_daily",
        subject_key="all_series",
        effective_date=EFFECTIVE_DATE,
        run_type="cli",
        status="started",
        runner="pytest",
    )


class FakeObjectRepository:
    def __init__(self, root: Path) -> None:
        self.root = StorageRoot(1, "global", "filesystem", str(root))
        self.stored: StoredObject | None = None

    def get_storage_root(self, root_name: str) -> StorageRoot | None:
        return self.root if root_name == "global" else None

    def insert_object(self, **values: object) -> StoredObject:
        self.stored = StoredObject(
            object_id=uuid4(),
            run_id=values["run_id"],  # type: ignore[arg-type]
            storage_root_id=1,
            storage_root_name="global",
            base_uri=self.root.base_uri,
            object_key=values["object_key"],  # type: ignore[arg-type]
            filename=values["filename"],  # type: ignore[arg-type]
            object_scope=values["object_scope"],  # type: ignore[arg-type]
            domain=values["domain"],  # type: ignore[arg-type]
            logical_name=values["logical_name"],  # type: ignore[arg-type]
            content_type=values["content_type"],  # type: ignore[arg-type]
            object_kind=values["object_kind"],  # type: ignore[arg-type]
            size_bytes=values["size_bytes"],  # type: ignore[arg-type]
            checksum_sha256=values["checksum_sha256"],  # type: ignore[arg-type]
            expires_at=None,
            deleted_at=None,
            purge_after=None,
            metadata=values["metadata"],  # type: ignore[arg-type]
        )
        return self.stored

    def get_object(self, object_id: UUID) -> StoredObject | None:
        if self.stored is not None and self.stored.object_id == object_id:
            return self.stored
        return None


def test_builds_complete_deterministic_scoped_eoddata_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_health(monkeypatch)

    report = build_eoddata_report(
        cursor=object(),
        import_result=_import_result(),
        generated_at=GENERATED_AT,
    )

    assert report["schema_version"] == 1
    assert report["provider_code"] == "EODDATA"
    assert report["effective_date"] == "2026-07-15"
    assert report["generated_at"] == "2026-07-16T02:30:00+00:00"
    assert report["outcome"] == "WARN"
    assert [item["market"] for item in report["markets"]] == list(MARKETS)
    assert [item["source_code"] for item in report["sources"]] == [
        "eoddata_symbol_list",
        "eoddata_daily",
    ]
    nyse = report["markets"][0]
    assert nyse["coverage"]["listing_count"] == 2
    assert nyse["freshness"]["latest_bar_weekday_age"] == 2
    assert nyse["stale_candidates"]["total_count"] == 1
    assert nyse["no_data_candidates"]["total_count"] == 1
    assert nyse["weekday_gap_warnings"]["total_count"] == 1
    assert nyse["cross_feed_outcomes"] == {
        "market": "NYSE",
        "listings_without_bars": 1,
        "bars_without_listings": 0,
    }
    assert report["inactive_series"]["total_count"] == 3
    assert calls == [
        ("markets", "EODDATA"),
        ("series", "EODDATA"),
        ("gaps", "NYSE"),
        ("gaps", "NASDAQ"),
        ("gaps", "AMEX"),
    ]
    assert json.loads(eoddata_report_to_json(report)) == report


def test_stores_secret_safe_report_under_active_core_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_health(monkeypatch)
    report = build_eoddata_report(
        cursor=object(),
        import_result=_import_result(),
        generated_at=GENERATED_AT,
    )
    repository = FakeObjectRepository(tmp_path)
    object_store = ObjectStore(repository)
    config = OHLCVConfig(
        eoddata_credentials=EODDataCredentials(api_key=SECRET),
    )

    stored = store_eoddata_report(
        object_store=object_store,
        run_context=_run_context(),
        config=config,
        report=report,
    )

    expected_key = (
        "stonks/ohlcv/eoddata/runs/2026/07/15/"
        "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee/reports"
    )
    assert stored.object_key == expected_key
    assert stored.filename == "report.json"
    assert stored.object_scope == "run"
    assert stored.run_id == RUN_ID
    assert stored.logical_name == "eoddata_daily_report"
    assert stored.object_kind == REPORT_OBJECT_KIND
    assert stored.content_type == "application/json"
    assert stored.expires_at is None
    assert stored.metadata == {
        "schema_version": 1,
        "provider_code": "EODDATA",
        "effective_date": "2026-07-15",
        "generated_at": "2026-07-16T02:30:00+00:00",
        "outcome": "WARN",
    }
    payload = object_store.get_bytes(stored.object_id)
    assert SECRET.encode() not in payload
    assert SECRET not in json.dumps(stored.metadata)
    assert json.loads(payload) == report


def test_report_path_requires_active_matching_run() -> None:
    assert build_report_object_key(
        storage_key="/stonks/ohlcv/",
        run_context=_run_context(),
        provider_code="EODDATA",
    ).endswith(f"/{RUN_ID}/reports")

    with pytest.raises(ValueError, match="active"):
        build_report_object_key(
            storage_key="stonks/ohlcv",
            run_context=RunContext(
                **{**_run_context().__dict__, "status": "succeeded"}
            ),
            provider_code="EODDATA",
        )
