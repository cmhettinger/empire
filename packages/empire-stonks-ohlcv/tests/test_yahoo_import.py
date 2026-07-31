from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

import empire_stonks_ohlcv.yahoo_import as yahoo_import
from empire_stonks_ohlcv import (
    AcquiredObject,
    EligibilityRule,
    PersistenceCounts,
    ProviderListing,
    SessionDateRule,
    SessionPolicy,
    SourceSnapshotRegistration,
)
from empire_stonks_ohlcv.yahoo import (
    YahooAcquisitionOutcome,
    YahooAcquisitionRequest,
    YahooAcquisitionStatus,
    YahooFailureReason,
    YahooListingTarget,
    YahooRequestMode,
)
from empire_stonks_ohlcv.yahoo_import import (
    YahooImportFailureCode,
    YahooImportInput,
    YahooImportStatus,
    import_yahoo_ranges,
)
from empire_stonks_ohlcv.yahoo_parser import parse_yahoo_chart


TRADE_DATE = date(2026, 7, 1)
POLICY_CODE = "YH_XNYS_CLOSE_90M"


class FakeCursor:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.provider_listing_id: UUID | None = None

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, _query: str, params: tuple[object, ...]) -> None:
        self.provider_listing_id = params[0]  # type: ignore[assignment]

    def fetchone(self) -> tuple[object, ...] | None:
        assert self.provider_listing_id is not None
        return self.connection.rows.get(self.provider_listing_id)


class FakeConnection:
    def __init__(
        self,
        rows: dict[UUID, tuple[object, ...] | None],
    ) -> None:
        self.rows = rows
        self.cursor_calls = 0
        self.commit_calls = 0
        self.rollback_calls = 0

    def cursor(self) -> FakeCursor:
        self.cursor_calls += 1
        return FakeCursor(self)

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1


def _identity(index: int) -> tuple[UUID, str, str]:
    return (
        UUID(int=index),
        f"Y8{index}",
        f"^Y8{index}",
    )


def _listing(ticker: str, yahoo_ticker: str) -> ProviderListing:
    return ProviderListing(
        provider_code="YAHOO",
        market="XIDX",
        ticker=ticker,
        name=f"{ticker} Test Index",
        instrument_type_code="EQUITY_INDEX",
        metadata={"YahooTicker": yahoo_ticker},
    )


def _request(
    index: int,
    *,
    start_date: date = TRADE_DATE,
    end_date_exclusive: date = date(2026, 7, 2),
) -> YahooAcquisitionRequest:
    provider_listing_id, ticker, yahoo_ticker = _identity(index)
    return YahooAcquisitionRequest(
        listing=YahooListingTarget(
            provider_listing_id=provider_listing_id,
            ticker=ticker,
            yahoo_ticker=yahoo_ticker,
        ),
        start_date=start_date,
        end_date_exclusive=end_date_exclusive,
        mode=YahooRequestMode.DAILY,
    )


def _acquired(index: int) -> AcquiredObject:
    return AcquiredObject(
        source_code="yahoo_daily",
        object_id=UUID(int=10_000 + index),
        object_key=f"test/yahoo/{index}",
        filename=f"raw-{index}.json",
        size_bytes=100 + index,
        checksum_sha256=f"{index:064x}",
    )


def _outcome(
    index: int,
    *,
    status: YahooAcquisitionStatus = YahooAcquisitionStatus.STORED,
    acquired: bool = True,
) -> YahooAcquisitionOutcome:
    return YahooAcquisitionOutcome(
        request=_request(index),
        status=status,
        attempts=1,
        http_status=200 if acquired else 404,
        acquired_object=_acquired(index) if acquired else None,
        failure_reason=(
            YahooFailureReason.HTTP
            if status is YahooAcquisitionStatus.FAILED
            else None
        ),
    )


def _policy() -> SessionPolicy:
    return SessionPolicy(
        code=POLICY_CODE,
        calendar_name="XNYS",
        timezone_name="America/New_York",
        eligibility_rule=EligibilityRule.SESSION_CLOSE,
        cutoff_local_time=None,
        availability_delay_minutes=90,
        session_date_rule=SessionDateRule.CALENDAR_SESSION,
    )


def _parse_result(index: int, *, close: str = "11.25"):
    _, ticker, yahoo_ticker = _identity(index)
    payload = json.dumps(
        {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "symbol": yahoo_ticker,
                            "exchangeName": "SNP",
                            "exchangeTimezoneName": "America/New_York",
                        },
                        "timestamp": [1782912600],
                        "indicators": {
                            "quote": [
                                {
                                    "open": [10],
                                    "high": [12],
                                    "low": [9],
                                    "close": [float(close)],
                                    "volume": [None],
                                }
                            ]
                        },
                    }
                ],
                "error": None,
            }
        }
    ).encode()
    return parse_yahoo_chart(
        payload,
        request=_request(index),
        listing=_listing(ticker, yahoo_ticker),
        policy=_policy(),
        planned_session_dates=(TRADE_DATE,),
    )


def _input(
    index: int,
    *,
    status: YahooAcquisitionStatus = YahooAcquisitionStatus.STORED,
    acquired: bool = True,
    parsed: bool = True,
    close: str = "11.25",
) -> YahooImportInput:
    return YahooImportInput(
        acquisition=_outcome(
            index,
            status=status,
            acquired=acquired,
        ),
        parse_result=(
            _parse_result(index, close=close)
            if parsed and status is YahooAcquisitionStatus.STORED
            else None
        ),
    )


def _seed_row(
    index: int,
    *,
    status: str = "ACTIVE",
    policy_code: str = POLICY_CODE,
    metadata: dict[str, object] | None = None,
) -> tuple[object, ...]:
    _, ticker, yahoo_ticker = _identity(index)
    listing = _listing(ticker, yahoo_ticker)
    return (
        listing.provider_code,
        listing.market,
        listing.ticker,
        listing.name,
        listing.instrument_type_code,
        listing.metadata if metadata is None else metadata,
        status,
        policy_code,
    )


def _registration(index: int) -> SourceSnapshotRegistration:
    acquired = _acquired(index)
    return SourceSnapshotRegistration(
        source_snapshot_id=UUID(int=20_000 + index),
        object_id=acquired.object_id,
        provider_code="YAHOO",
        source_code="yahoo_daily",
        content_sha256=acquired.checksum_sha256,
        snapshot_inserted=True,
        object_link_inserted=True,
    )


def _install_writers(
    monkeypatch: pytest.MonkeyPatch,
    *,
    events: list[str],
) -> None:
    def register(**values: object) -> SourceSnapshotRegistration:
        acquired = values["acquired_object"]
        assert isinstance(acquired, AcquiredObject)
        index = acquired.object_id.int - 10_000
        events.append(f"snapshot:{index}")
        return _registration(index)

    def write_bars(**values: object) -> PersistenceCounts:
        bars = tuple(values["bars"])  # type: ignore[arg-type]
        index = bars[0].provider_listing_id.int if bars else 0
        events.append(f"bars:{index}")
        return PersistenceCounts(inserted=len(bars))

    monkeypatch.setattr(
        yahoo_import,
        "upsert_provider_source_snapshot",
        register,
    )
    monkeypatch.setattr(yahoo_import, "upsert_daily_bars", write_bars)


def test_imports_stored_registers_missing_and_carries_acquisition_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection(
        {
            UUID(int=1): _seed_row(1),
            UUID(int=2): _seed_row(2),
        }
    )
    events: list[str] = []
    _install_writers(monkeypatch, events=events)

    result = import_yahoo_ranges(
        connection=connection,
        inputs=(
            _input(
                3,
                status=YahooAcquisitionStatus.FAILED,
                acquired=False,
                parsed=False,
            ),
            _input(
                2,
                status=YahooAcquisitionStatus.MISSING,
                parsed=False,
            ),
            _input(1),
        ),
    )

    assert events == ["snapshot:1", "bars:1", "snapshot:2"]
    assert connection.cursor_calls == 2
    assert connection.commit_calls == 2
    assert connection.rollback_calls == 0
    assert result.chunk_count == 3
    assert result.imported_chunks == 1
    assert result.missing_chunks == 1
    assert result.failed_chunks == 1
    assert result.source_snapshot_count == 2
    assert result.bar_counts == PersistenceCounts(inserted=1)
    assert [item.ticker for item in result.listings] == ["Y81", "Y82", "Y83"]
    assert result.listings[2].chunks[0].failure_code is (
        YahooImportFailureCode.ACQUISITION_FAILED
    )
    assert result.to_dict()["seeded_listing_writes"] == 0
    json.dumps(result.to_dict())


def test_multiple_chunks_are_grouped_under_one_listing_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection({UUID(int=1): _seed_row(1)})
    events: list[str] = []
    _install_writers(monkeypatch, events=events)
    missing_request = _request(
        1,
        start_date=date(2026, 7, 2),
        end_date_exclusive=date(2026, 7, 3),
    )
    missing = YahooImportInput(
        acquisition=YahooAcquisitionOutcome(
            request=missing_request,
            status=YahooAcquisitionStatus.MISSING,
            attempts=1,
            http_status=200,
            acquired_object=_acquired(101),
        )
    )

    result = import_yahoo_ranges(
        connection=connection,
        inputs=(missing, _input(1)),
    )

    assert events == ["snapshot:1", "bars:1", "snapshot:101"]
    assert len(result.listings) == 1
    assert result.listings[0].imported_chunks == 1
    assert result.listings[0].missing_chunks == 1
    assert result.listings[0].source_snapshot_count == 2
    assert result.listings[0].bar_counts == PersistenceCounts(inserted=1)


def test_persistence_failure_rolls_back_only_its_chunk_and_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection(
        {UUID(int=index): _seed_row(index) for index in (1, 2, 3)}
    )
    events: list[str] = []

    def register(**values: object) -> SourceSnapshotRegistration:
        acquired = values["acquired_object"]
        assert isinstance(acquired, AcquiredObject)
        index = acquired.object_id.int - 10_000
        events.append(f"snapshot:{index}")
        return _registration(index)

    def write_bars(**values: object) -> PersistenceCounts:
        bars = tuple(values["bars"])  # type: ignore[arg-type]
        index = bars[0].provider_listing_id.int
        events.append(f"bars:{index}")
        if index == 2:
            raise RuntimeError("provider body secret")
        return PersistenceCounts(inserted=1)

    monkeypatch.setattr(
        yahoo_import,
        "upsert_provider_source_snapshot",
        register,
    )
    monkeypatch.setattr(yahoo_import, "upsert_daily_bars", write_bars)

    result = import_yahoo_ranges(
        connection=connection,
        inputs=(_input(3), _input(2), _input(1)),
    )

    assert events == [
        "snapshot:1",
        "bars:1",
        "snapshot:2",
        "bars:2",
        "snapshot:3",
        "bars:3",
    ]
    assert connection.commit_calls == 2
    assert connection.rollback_calls == 1
    assert result.imported_chunks == 2
    assert result.failed_chunks == 1
    failed = result.listings[1].chunks[0]
    assert failed.failure_code is YahooImportFailureCode.PERSISTENCE_FAILED
    assert failed.source_snapshot is None
    assert "secret" not in repr(result.to_dict())


def test_unseeded_inactive_and_mismatched_rows_fail_before_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection(
        {
            UUID(int=1): None,
            UUID(int=2): _seed_row(2, status="INACTIVE"),
            UUID(int=3): _seed_row(
                3,
                metadata={"YahooTicker": "^WRONG"},
            ),
        }
    )
    events: list[str] = []
    _install_writers(monkeypatch, events=events)

    result = import_yahoo_ranges(
        connection=connection,
        inputs=(_input(1), _input(2), _input(3)),
    )

    assert events == []
    assert connection.commit_calls == 0
    assert connection.rollback_calls == 3
    assert [item.chunks[0].failure_code for item in result.listings] == [
        YahooImportFailureCode.UNSEEDED_LISTING,
        YahooImportFailureCode.INACTIVE_LISTING,
        YahooImportFailureCode.LISTING_IDENTITY_MISMATCH,
    ]


def test_stored_parse_failure_and_stored_acquisition_failure_keep_lineage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection(
        {
            UUID(int=1): _seed_row(1),
            UUID(int=2): _seed_row(2),
        }
    )
    events: list[str] = []
    _install_writers(monkeypatch, events=events)

    result = import_yahoo_ranges(
        connection=connection,
        inputs=(
            _input(1, parsed=False),
            _input(
                2,
                status=YahooAcquisitionStatus.FAILED,
                parsed=False,
            ),
        ),
    )

    assert events == ["snapshot:1", "snapshot:2"]
    assert connection.commit_calls == 2
    assert result.source_snapshot_count == 2
    assert result.failed_chunks == 2
    assert [item.chunks[0].failure_code for item in result.listings] == [
        YahooImportFailureCode.PARSE_UNAVAILABLE,
        YahooImportFailureCode.ACQUISITION_FAILED,
    ]


def test_writer_outcomes_prove_insert_unchanged_and_correction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection({UUID(int=1): _seed_row(1)})
    stored_close: Decimal | None = None

    monkeypatch.setattr(
        yahoo_import,
        "upsert_provider_source_snapshot",
        lambda **_: _registration(1),
    )

    def write_bars(**values: object) -> PersistenceCounts:
        nonlocal stored_close
        bars = tuple(values["bars"])  # type: ignore[arg-type]
        close = bars[0].bar.close
        if stored_close is None:
            stored_close = close
            return PersistenceCounts(inserted=1)
        if stored_close == close:
            return PersistenceCounts(unchanged=1)
        stored_close = close
        return PersistenceCounts(updated=1)

    monkeypatch.setattr(yahoo_import, "upsert_daily_bars", write_bars)

    first = import_yahoo_ranges(
        connection=connection,
        inputs=(_input(1, close="11.25"),),
    )
    rerun = import_yahoo_ranges(
        connection=connection,
        inputs=(_input(1, close="11.25"),),
    )
    corrected = import_yahoo_ranges(
        connection=connection,
        inputs=(_input(1, close="11.50"),),
    )

    assert first.bar_counts == PersistenceCounts(inserted=1)
    assert rerun.bar_counts == PersistenceCounts(unchanged=1)
    assert corrected.bar_counts == PersistenceCounts(updated=1)
    assert connection.commit_calls == 3
    assert connection.rollback_calls == 0


def test_policy_or_seeded_listing_detail_drift_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection(
        {
            UUID(int=1): _seed_row(1, policy_code="OTHER_POLICY"),
            UUID(int=2): (
                *_seed_row(2)[:3],
                "Different Name",
                *_seed_row(2)[4:],
            ),
        }
    )
    events: list[str] = []
    _install_writers(monkeypatch, events=events)

    result = import_yahoo_ranges(
        connection=connection,
        inputs=(_input(1), _input(2)),
    )

    assert events == []
    assert result.failed_chunks == 2
    assert all(
        item.chunks[0].failure_code
        is YahooImportFailureCode.LISTING_IDENTITY_MISMATCH
        for item in result.listings
    )


def test_duplicate_chunk_or_object_fails_before_transaction() -> None:
    connection = FakeConnection({})
    item = _input(
        1,
        status=YahooAcquisitionStatus.FAILED,
        acquired=False,
        parsed=False,
    )

    with pytest.raises(ValueError, match="duplicate Yahoo request"):
        import_yahoo_ranges(connection=connection, inputs=(item, item))

    assert connection.cursor_calls == 0
    assert connection.commit_calls == 0
    assert connection.rollback_calls == 0


def test_input_rejects_parse_result_for_nonstored_acquisition() -> None:
    with pytest.raises(ValueError, match="requires a STORED"):
        YahooImportInput(
            acquisition=_outcome(
                1,
                status=YahooAcquisitionStatus.MISSING,
            ),
            parse_result=_parse_result(1),
        )
