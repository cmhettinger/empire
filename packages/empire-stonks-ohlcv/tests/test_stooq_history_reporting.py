from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

from empire_core import ObjectStore, RunContext, StorageRoot, StoredObject
from empire_stonks_ohlcv import (
    AcquiredObject,
    ImportIssue,
    OHLCVConfig,
    PDF_REPORT_OBJECT_KIND,
    PersistenceCounts,
    STOOQ_HISTORY_PDF_REPORT_ID,
    SourceSnapshotRegistration,
    StooqHistoryMarketParseCounts,
    StooqHistoryParseProgress,
    StooqHistoryParseSummary,
    StooqHistoryScope,
    StooqHistoryWriteSummary,
    build_stooq_history_report,
    render_stooq_history_pdf,
    stooq_history_report_to_json,
    store_stooq_history_pdf_report,
    store_stooq_history_report,
)


EFFECTIVE_DATE = date(2026, 7, 18)
GENERATED_AT = datetime(2026, 7, 18, 20, 30, tzinfo=UTC)
RUN_ID = UUID("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee")


class FakeCursor:
    def __init__(
        self,
        market_rows: list[tuple[object, ...]],
        series_rows: list[tuple[object, ...]],
    ) -> None:
        self.results = [market_rows, series_rows]
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.calls.append((sql, params))

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.results[len(self.calls) - 1]


class FakeObjectRepository:
    def __init__(self, root: Path) -> None:
        self.root = StorageRoot(1, "global", "filesystem", str(root))
        self.objects: dict[UUID, StoredObject] = {}

    def get_storage_root(self, root_name: str) -> StorageRoot | None:
        return self.root if root_name == "global" else None

    def insert_object(self, **values: object) -> StoredObject:
        stored = StoredObject(
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
            expires_at=values["expires_at"],  # type: ignore[arg-type]
            deleted_at=None,
            purge_after=None,
            metadata=values["metadata"],  # type: ignore[arg-type]
        )
        self.objects[stored.object_id] = stored
        return stored

    def get_object(self, object_id: UUID) -> StoredObject | None:
        return self.objects.get(object_id)


def _scope() -> StooqHistoryScope:
    return StooqHistoryScope(
        effective_date=EFFECTIVE_DATE,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        markets=("nasdaq", "nyse"),
        tickers=("AAA.US", "BBB.US"),
    )


def _acquired() -> AcquiredObject:
    return AcquiredObject(
        source_code="stooq_history",
        object_id=UUID(int=1),
        object_key="stonks/ohlcv/stooq/run/stooq_history",
        filename="raw.zip",
        size_bytes=1234,
        checksum_sha256="ab" * 32,
    )


def _snapshot() -> SourceSnapshotRegistration:
    return SourceSnapshotRegistration(
        source_snapshot_id=UUID(int=2),
        object_id=UUID(int=1),
        provider_code="STOOQ",
        source_code="stooq_history",
        content_sha256="ab" * 32,
        snapshot_inserted=True,
        object_link_inserted=True,
    )


def _run_context() -> RunContext:
    return RunContext(
        run_id=RUN_ID,
        domain="stonks",
        job_name="stonks_ohlcv_stooq_backfill",
        subject_key="us_stocks",
        effective_date=EFFECTIVE_DATE,
        run_type="cli",
        status="started",
        runner="pytest",
    )


def _parse_summary() -> StooqHistoryParseSummary:
    return StooqHistoryParseSummary(
        files_discovered=2,
        chunks_emitted=2,
        market_counts=(
            StooqHistoryMarketParseCounts(
                market="nasdaq",
                files_completed=1,
                input_rows=5,
                accepted_records=3,
                rejected_records=1,
                rejected_rows=1,
                duplicate_rows_collapsed=1,
            ),
            StooqHistoryMarketParseCounts(
                market="nyse",
                files_completed=1,
                input_rows=1,
                accepted_records=1,
            ),
        ),
        issue_samples=(
            ImportIssue(
                code="stooq_history_invalid_row",
                message="Invalid Stooq history row was rejected.",
                source_code="stooq_history",
                record_reference="nasdaq:AAA.US:3",
            ),
        ),
    )


def _progress() -> StooqHistoryParseProgress:
    return StooqHistoryParseProgress(
        files_discovered=2,
        files_completed=2,
        chunks_emitted=2,
        input_rows=6,
        accepted_records=4,
        rejected_records=1,
        rejected_rows=1,
        duplicate_rows_collapsed=1,
        current_member="data/daily/us/nyse stocks/bbb.us.txt",
    )


def _write_summary() -> StooqHistoryWriteSummary:
    return StooqHistoryWriteSummary(
        chunks_completed=2,
        listing_counts=PersistenceCounts(inserted=2),
        bar_counts=PersistenceCounts(inserted=3, derived_updated=1),
        skipped_inactive_bars=1,
    )


def _coverage_cursor() -> FakeCursor:
    return FakeCursor(
        market_rows=[
            (
                "nasdaq",
                1,
                1,
                0,
                1,
                10,
                3,
                date(2025, 1, 2),
                date(2026, 1, 5),
                date(2026, 1, 2),
                date(2026, 1, 5),
            ),
            (
                "nyse",
                1,
                1,
                0,
                1,
                20,
                1,
                date(2024, 1, 2),
                date(2026, 1, 2),
                date(2026, 1, 2),
                date(2026, 1, 2),
            ),
        ],
        series_rows=[
            (
                UUID(int=10),
                "nasdaq",
                "AAA.US",
                "ACTIVE",
                10,
                3,
                date(2025, 1, 2),
                date(2026, 1, 5),
                date(2026, 1, 2),
                date(2026, 1, 5),
            ),
            (
                UUID(int=11),
                "nyse",
                "BBB.US",
                "ACTIVE",
                20,
                1,
                date(2024, 1, 2),
                date(2026, 1, 2),
                date(2026, 1, 2),
                date(2026, 1, 2),
            ),
        ],
    )


def _complete_report(cursor: FakeCursor) -> dict[str, object]:
    return build_stooq_history_report(
        cursor=cursor,
        scope=_scope(),
        chunk_size=2,
        acquired_object=_acquired(),
        source_snapshot=_snapshot(),
        parse_summary=_parse_summary(),
        parse_progress=_progress(),
        write_summary=_write_summary(),
        run_status="complete",
        elapsed_seconds=12.5,
        generated_at=GENERATED_AT,
    )


def test_builds_complete_report_with_scoped_coverage_and_native_notes() -> None:
    cursor = _coverage_cursor()

    report = _complete_report(cursor)

    assert report["schema_version"] == 2
    assert report["report_type"] == "stooq_history_backfill"
    assert report["provider_code"] == "STOOQ"
    assert report["outcome"] == "WARN"
    assert report["run_status"] == "complete"
    assert report["input"]["scope"] == _scope().to_dict()
    assert report["progress"]["write"]["bar_counts"] == {
        "inserted": 3,
        "updated": 0,
        "unchanged": 0,
        "derived_updated": 1,
    }
    assert report["coverage"]["series_count"] == 2
    assert report["coverage"]["truncated"] is False
    assert report["markets"][0]["coverage"]["scoped_bar_count"] == 3
    assert report["markets"][1]["coverage"]["persisted_bar_count"] == 20
    assert report["warnings"]["total_count"] == 3
    assert report["warnings"]["sample_count"] == 1
    assert report["hard_failures"]["total_count"] == 0
    semantics = report["native_value_semantics"]
    assert semantics["adjustment_basis"] == (
        "unspecified_by_stooq_history_bundle"
    )
    assert semantics["currency"] == "unspecified"
    assert len(cursor.calls[0][1]) == 20
    assert len(cursor.calls[1][1]) == 17
    assert cursor.calls[0][1][-4:] == (
        "STOOQ",
        ["nasdaq", "nyse"],
        ["AAA.US", "BBB.US"],
        ["AAA.US", "BBB.US"],
    )
    assert cursor.calls[1][1][:5] == (
        "STOOQ",
        ["nasdaq", "nyse"],
        ["AAA.US", "BBB.US"],
        ["AAA.US", "BBB.US"],
        100,
    )
    assert json.loads(stooq_history_report_to_json(report)) == report


def test_builds_partial_failure_report_from_current_progress() -> None:
    cursor = FakeCursor(market_rows=[], series_rows=[])
    progress = StooqHistoryParseProgress(
        files_discovered=20,
        files_completed=8,
        chunks_emitted=3,
        input_rows=100,
        accepted_records=90,
        rejected_records=2,
        rejected_rows=2,
        duplicate_rows_collapsed=8,
        current_member="data/daily/us/nasdaq stocks/aaa.us.txt",
    )
    writes = StooqHistoryWriteSummary(
        chunks_completed=2,
        chunks_failed=1,
        bar_counts=PersistenceCounts(inserted=60),
    )

    report = build_stooq_history_report(
        cursor=cursor,
        scope=_scope(),
        chunk_size=30,
        acquired_object=_acquired(),
        source_snapshot=_snapshot(),
        parse_summary=None,
        parse_progress=progress,
        write_summary=writes,
        run_status="partial",
        failed_stage="persistence",
        elapsed_seconds=30,
        generated_at=GENERATED_AT,
    )

    assert report["outcome"] == "FAIL"
    assert report["run_status"] == "partial"
    assert report["progress"]["parse"]["files_completed"] == 8
    assert report["progress"]["write"]["last_completed_chunk"] == 2
    assert report["hard_failures"] == {
        "total_count": 1,
        "failed_stage": "persistence",
        "message": "Stooq history run did not complete.",
    }
    assert report["warnings"]["total_count"] == 10
    assert all(item["parse_counts"] is None for item in report["markets"])


def test_stores_report_as_durable_core_provider_report(tmp_path: Path) -> None:
    report = _complete_report(_coverage_cursor())
    repository = FakeObjectRepository(tmp_path)
    object_store = ObjectStore(repository)
    run_context = _run_context()

    stored = store_stooq_history_report(
        object_store=object_store,
        run_context=run_context,
        config=OHLCVConfig(),
        report=report,
    )

    assert stored.object_key.endswith(f"/{RUN_ID}/reports")
    assert stored.filename == "report.json"
    assert stored.logical_name == "stooq_history_report"
    assert stored.object_kind == "stonks_ohlcv_provider_report"
    assert stored.expires_at is None
    assert stored.metadata == {
        "schema_version": 2,
        "report_type": "stooq_history_backfill",
        "provider_code": "STOOQ",
        "source_code": "stooq_history",
        "effective_date": "2026-07-18",
        "generated_at": "2026-07-18T20:30:00+00:00",
        "outcome": "WARN",
        "run_status": "complete",
    }
    assert json.loads(object_store.get_bytes(stored.object_id)) == report


def test_renders_human_readable_stooq_pdf(tmp_path: Path) -> None:
    report = _complete_report(_coverage_cursor())

    result = render_stooq_history_pdf(
        report=report,
        output_dir=tmp_path,
    )

    pdf_path = result.primary_artifact.path
    assert result.report.report_id == STOOQ_HISTORY_PDF_REPORT_ID
    assert pdf_path.name == "report.pdf"
    assert pdf_path.read_bytes().startswith(b"%PDF-")
    assert pdf_path.stat().st_size > 10_000


def test_stores_stooq_pdf_beside_json_report(tmp_path: Path) -> None:
    report = _complete_report(_coverage_cursor())
    repository = FakeObjectRepository(tmp_path / "objects")
    object_store = ObjectStore(repository)

    stored = store_stooq_history_pdf_report(
        object_store=object_store,
        run_context=_run_context(),
        config=OHLCVConfig(),
        report=report,
        output_dir=tmp_path / "render",
    )

    assert stored.filename == "report.pdf"
    assert stored.logical_name == "stooq_history_pdf_report"
    assert stored.object_kind == PDF_REPORT_OBJECT_KIND
    assert stored.content_type == "application/pdf"
    assert stored.object_key.endswith(f"/{RUN_ID}/reports")
    assert stored.metadata == {
        "schema_version": 2,
        "report_id": STOOQ_HISTORY_PDF_REPORT_ID,
        "report_type": "stooq_history_backfill",
        "provider_code": "STOOQ",
        "source_code": "stooq_history",
        "effective_date": "2026-07-18",
        "generated_at": "2026-07-18T20:30:00+00:00",
        "outcome": "WARN",
        "run_status": "complete",
    }
    assert object_store.get_bytes(stored.object_id).startswith(b"%PDF-")
