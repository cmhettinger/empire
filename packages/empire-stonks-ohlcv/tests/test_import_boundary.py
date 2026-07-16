from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest

from empire_core import RunContext
from empire_stonks_ohlcv import (
    AcquiredObject,
    DailyBar,
    OHLCVWorkflowError,
    ParsedListingBatch,
    ParsedProviderOutput,
    PersistenceCounts,
    ProviderListing,
    ProviderSourceMetadata,
    execute_import_boundary,
)
from empire_stonks_ohlcv import import_boundary


class FakeCursor:
    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None


class FakeConnection:
    def __init__(self, *, commit_error: Exception | None = None) -> None:
        self.cursor_calls = 0
        self.commit_calls = 0
        self.rollback_calls = 0
        self.commit_error = commit_error

    def cursor(self) -> FakeCursor:
        self.cursor_calls += 1
        return FakeCursor()

    def commit(self) -> None:
        self.commit_calls += 1
        if self.commit_error is not None:
            raise self.commit_error

    def rollback(self) -> None:
        self.rollback_calls += 1


def run_context() -> RunContext:
    return RunContext(
        run_id=UUID("10000000-0000-4000-8000-000000000001"),
        domain="stonks",
        job_name="stonks_ohlcv_eoddata_daily",
        subject_key="all_series",
        effective_date=date(2026, 7, 16),
        run_type="pytest",
        status="started",
        runner="pytest",
        params={},
        started_at=datetime.now(UTC),
    )


def acquired_object() -> AcquiredObject:
    return AcquiredObject(
        source_code="eoddata_daily",
        object_id=UUID("20000000-0000-4000-8000-000000000002"),
        object_key="stonks/ohlcv/eoddata/2026-07-16/run/raw.csv",
        filename="raw.csv",
        size_bytes=42,
        checksum_sha256="ab" * 32,
    )


def parsed_batch() -> ParsedListingBatch:
    return ParsedListingBatch(
        listing=ProviderListing(
            provider_code="EODDATA",
            market="NYSE",
            ticker="ABC",
        ),
        bars=(
            DailyBar(
                trading_date=date(2026, 7, 15),
                open=Decimal("10"),
                high=Decimal("12"),
                low=Decimal("9"),
                close=Decimal("11"),
                volume=Decimal("1000"),
            ),
        ),
    )


def parsed_output(*batches: ParsedListingBatch) -> ParsedProviderOutput:
    return ParsedProviderOutput(
        sources=(
            ProviderSourceMetadata(
                source_code="eoddata_daily",
                parser_version="2026.07",
            ),
        ),
        batches=tuple(batches),
    )


def test_success_persists_all_ohlcv_records_in_one_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection()
    acquired = acquired_object()
    batch = parsed_batch()
    events: list[str] = []

    def register(**values: object) -> None:
        assert values["acquired_object"] == acquired
        assert values["parser_version"] == "2026.07"
        events.append("snapshot")

    listing_result = SimpleNamespace(
        counts=PersistenceCounts(inserted=1),
        provider_listing_id_for=lambda listing: UUID(
            "30000000-0000-4000-8000-000000000003"
        ),
    )

    def write_listings(**values: object) -> object:
        assert tuple(values["listings"]) == (batch.listing,)
        events.append("listings")
        return listing_result

    def write_bars(**values: object) -> PersistenceCounts:
        bars = tuple(values["bars"])
        assert len(bars) == 1
        assert bars[0].bar == batch.bars[0]
        events.append("bars")
        return PersistenceCounts(inserted=1)

    monkeypatch.setattr(import_boundary, "upsert_provider_source_snapshot", register)
    monkeypatch.setattr(import_boundary, "upsert_provider_listings", write_listings)
    monkeypatch.setattr(import_boundary, "upsert_daily_bars", write_bars)

    result = execute_import_boundary(
        connection=connection,
        run_context=run_context(),
        provider_code="EODDATA",
        acquire=lambda _context: (acquired,),
        parse=lambda _objects: parsed_output(batch),
    )

    assert events == ["snapshot", "listings", "bars"]
    assert connection.cursor_calls == 1
    assert connection.commit_calls == 1
    assert connection.rollback_calls == 0
    assert result.acquired_objects == (acquired,)
    assert result.listing_counts == PersistenceCounts(inserted=1)
    assert result.bar_counts == PersistenceCounts(inserted=1)


@pytest.mark.parametrize(
    ("failure_stage", "expected_cursor_calls", "expected_rollbacks"),
    [
        ("acquisition", 0, 0),
        ("parsing", 0, 0),
        ("persistence", 1, 1),
    ],
)
def test_failure_is_stage_safe_and_never_partially_commits(
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
    expected_cursor_calls: int,
    expected_rollbacks: int,
) -> None:
    connection = FakeConnection()
    acquired = acquired_object()
    batch = parsed_batch()

    def acquire(_context: RunContext) -> tuple[AcquiredObject, ...]:
        if failure_stage == "acquisition":
            raise RuntimeError("secret acquisition detail")
        return (acquired,)

    def parse(_objects: tuple[AcquiredObject, ...]) -> ParsedProviderOutput:
        if failure_stage == "parsing":
            raise RuntimeError("secret parser detail")
        return parsed_output(batch)

    def register(**_values: object) -> None:
        if failure_stage == "persistence":
            raise RuntimeError("secret database detail")

    monkeypatch.setattr(import_boundary, "upsert_provider_source_snapshot", register)
    monkeypatch.setattr(
        import_boundary,
        "upsert_provider_listings",
        lambda **_values: pytest.fail("listings must not be written"),
    )

    with pytest.raises(OHLCVWorkflowError) as error:
        execute_import_boundary(
            connection=connection,
            run_context=run_context(),
            provider_code="EODDATA",
            acquire=acquire,
            parse=parse,
        )

    assert error.value.stage == failure_stage
    assert str(error.value) == (
        f"OHLCV provider workflow failed during {failure_stage}."
    )
    assert "secret" not in str(error.value)
    assert connection.cursor_calls == expected_cursor_calls
    assert connection.commit_calls == 0
    assert connection.rollback_calls == expected_rollbacks


@pytest.mark.parametrize("mismatch", ["source", "provider", "return_type"])
def test_parser_output_contract_mismatches_fail_before_persistence(
    mismatch: str,
) -> None:
    connection = FakeConnection()

    def parse(_objects: tuple[AcquiredObject, ...]) -> object:
        if mismatch == "return_type":
            return (parsed_batch(),)
        if mismatch == "source":
            return ParsedProviderOutput(
                sources=(ProviderSourceMetadata("eoddata_other", "v1"),),
                batches=(parsed_batch(),),
            )
        wrong_provider_batch = ParsedListingBatch(
            listing=ProviderListing(
                provider_code="STOOQ",
                market="NYSE",
                ticker="ABC",
            ),
            bars=(),
        )
        return parsed_output(wrong_provider_batch)

    with pytest.raises(OHLCVWorkflowError) as error:
        execute_import_boundary(
            connection=connection,
            run_context=run_context(),
            provider_code="EODDATA",
            acquire=lambda _context: (acquired_object(),),
            parse=parse,  # type: ignore[arg-type]
        )

    assert error.value.stage == "parsing"
    assert connection.cursor_calls == 0
    assert connection.commit_calls == 0
    assert connection.rollback_calls == 0


def test_commit_failure_is_reported_as_persistence_and_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection(commit_error=RuntimeError("secret commit detail"))
    listing_result = SimpleNamespace(
        counts=PersistenceCounts(),
        provider_listing_id_for=lambda listing: pytest.fail(
            "empty parse output must not resolve listings"
        ),
    )
    monkeypatch.setattr(
        import_boundary,
        "upsert_provider_source_snapshot",
        lambda **_values: None,
    )
    monkeypatch.setattr(
        import_boundary,
        "upsert_provider_listings",
        lambda **_values: listing_result,
    )
    monkeypatch.setattr(
        import_boundary,
        "upsert_daily_bars",
        lambda **_values: PersistenceCounts(),
    )

    with pytest.raises(OHLCVWorkflowError) as error:
        execute_import_boundary(
            connection=connection,
            run_context=run_context(),
            provider_code="EODDATA",
            acquire=lambda _context: (acquired_object(),),
            parse=lambda _objects: parsed_output(),
        )

    assert error.value.stage == "persistence"
    assert "secret" not in str(error.value)
    assert connection.commit_calls == 1
    assert connection.rollback_calls == 1
