from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from uuid import UUID

import pytest

import empire_stonks_ohlcv.eoddata_import as eoddata_import
from empire_stonks_ohlcv import (
    AcquiredObject,
    EODDATA_DAILY_SOURCE,
    EODDATA_SYMBOL_LIST_SOURCE,
    OHLCVWorkflowError,
    PersistenceCounts,
    ProviderListingWriteResult,
    ResolvedProviderListing,
    SourceSnapshotRegistration,
    import_eoddata_daily,
    parse_eoddata_quote_list,
    parse_eoddata_symbol_list,
)


EFFECTIVE_DATE = date(2026, 7, 15)
MARKETS = ("NYSE", "NASDAQ", "AMEX")
FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "eoddata"


class FakeCursor:
    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class FakeConnection:
    def __init__(self) -> None:
        self.cursor_calls = 0
        self.commit_calls = 0
        self.rollback_calls = 0
        self.cursor_value = FakeCursor()

    def cursor(self) -> FakeCursor:
        self.cursor_calls += 1
        return self.cursor_value

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1


def _acquired_objects() -> tuple[AcquiredObject, ...]:
    values = []
    object_number = 1
    for source in (EODDATA_SYMBOL_LIST_SOURCE, EODDATA_DAILY_SOURCE):
        for market in MARKETS:
            values.append(
                AcquiredObject(
                    source_code=source.source_code,
                    object_id=UUID(int=object_number),
                    object_key=f"test/{source.source_code}/{market.lower()}",
                    filename=f"raw-{market.lower()}.json",
                    size_bytes=100 + object_number,
                    checksum_sha256=f"{object_number:064x}",
                )
            )
            object_number += 1
    return tuple(reversed(values))


def _quote_payload(exchange: str, ticker: str, close: float = 10.5) -> bytes:
    return json.dumps(
        [
            {
                "exchangeCode": exchange,
                "symbolCode": ticker,
                "interval": "d",
                "dateStamp": EFFECTIVE_DATE.isoformat(),
                "open": 10,
                "high": 11,
                "low": 9,
                "close": close,
                "volume": 1000,
            }
        ]
    ).encode("utf-8")


def _validation_result(market: str, *, close: float = 10.5):
    ticker = f"{market}.ONE"
    symbols = parse_eoddata_symbol_list(
        json.dumps(
            [
                {
                    "code": ticker,
                    "name": f"{market} Company",
                    "type": "Equity",
                    "currency": "USD",
                }
            ]
        ).encode("utf-8"),
        exchange=market,
    )
    quotes = parse_eoddata_quote_list(
        _quote_payload(market, ticker, close),
        exchange=market,
        effective_date=EFFECTIVE_DATE,
        symbol_list=symbols,
    )
    return quotes.to_validation_result(symbol_list=symbols)


def _validation_results():
    return tuple(_validation_result(market) for market in reversed(MARKETS))


def _registration(acquired_object: AcquiredObject) -> SourceSnapshotRegistration:
    return SourceSnapshotRegistration(
        source_snapshot_id=UUID(int=100 + acquired_object.object_id.int),
        object_id=acquired_object.object_id,
        provider_code="EODDATA",
        source_code=acquired_object.source_code,
        content_sha256=acquired_object.checksum_sha256,
        snapshot_inserted=True,
        object_link_inserted=True,
    )


def _listing_result(
    listings: tuple[object, ...],
    *,
    inactive_market: str | None = None,
    outcome: str = "inserted",
) -> ProviderListingWriteResult:
    return ProviderListingWriteResult(
        resolved=tuple(
            ResolvedProviderListing(
                listing=listing,  # type: ignore[arg-type]
                provider_listing_id=UUID(
                    int=1000 + sum(ord(char) for char in listing.market)
                ),
                outcome=outcome,  # type: ignore[arg-type]
                status=(
                    "INACTIVE"
                    if listing.market == inactive_market
                    else "ACTIVE"
                ),
            )
            for listing in listings
        )
    )


def _install_success_writers(
    monkeypatch: pytest.MonkeyPatch,
    *,
    events: list[str],
    inactive_market: str | None = None,
    outcome: str = "inserted",
) -> None:
    def register(**values: object) -> SourceSnapshotRegistration:
        acquired = values["acquired_object"]
        assert isinstance(acquired, AcquiredObject)
        events.append(f"snapshot:{acquired.source_code}:{acquired.filename}")
        return _registration(acquired)

    def write_listings(**values: object) -> ProviderListingWriteResult:
        listings = tuple(values["listings"])  # type: ignore[arg-type]
        market = listings[0].market
        events.append(f"listings:{market}")
        return _listing_result(
            listings,
            inactive_market=inactive_market,
            outcome=outcome,
        )

    def write_bars(**values: object) -> PersistenceCounts:
        bars = tuple(values["bars"])  # type: ignore[arg-type]
        market = (
            next(
                market
                for market in MARKETS
                if UUID(int=1000 + sum(ord(char) for char in market))
                == bars[0].provider_listing_id
            )
            if bars
            else inactive_market
        )
        events.append(f"bars:{market}")
        return PersistenceCounts(inserted=len(bars))

    monkeypatch.setattr(
        eoddata_import,
        "upsert_provider_source_snapshot",
        register,
    )
    monkeypatch.setattr(eoddata_import, "upsert_provider_listings", write_listings)
    monkeypatch.setattr(eoddata_import, "upsert_daily_bars", write_bars)


def test_atomic_service_registers_all_sources_then_writes_listings_and_bars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection()
    events: list[str] = []
    _install_success_writers(monkeypatch, events=events)

    result = import_eoddata_daily(
        connection=connection,
        effective_date=EFFECTIVE_DATE,
        acquired_objects=_acquired_objects(),
        validation_results=_validation_results(),
    )

    assert events[:6] == [
        f"snapshot:{source.source_code}:raw-{market.lower()}.json"
        for source in (EODDATA_SYMBOL_LIST_SOURCE, EODDATA_DAILY_SOURCE)
        for market in MARKETS
    ]
    assert events[6:] == [
        "listings:NYSE",
        "bars:NYSE",
        "listings:NASDAQ",
        "bars:NASDAQ",
        "listings:AMEX",
        "bars:AMEX",
    ]
    assert connection.cursor_calls == 1
    assert connection.commit_calls == 1
    assert connection.rollback_calls == 0
    assert result.listing_counts == PersistenceCounts(inserted=3)
    assert result.bar_counts == PersistenceCounts(inserted=3)
    assert result.skipped_inactive_bars == 0
    assert result.failures.total_count == 0
    assert len(result.source_snapshots) == 6
    assert tuple((item.source_code, item.market) for item in result.feed_counts) == (
        ("eoddata_symbol_list", "NYSE"),
        ("eoddata_symbol_list", "NASDAQ"),
        ("eoddata_symbol_list", "AMEX"),
        ("eoddata_daily", "NYSE"),
        ("eoddata_daily", "NASDAQ"),
        ("eoddata_daily", "AMEX"),
    )
    json.dumps(result.to_dict())


def test_inactive_listing_is_upserted_but_its_bar_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection()
    events: list[str] = []
    _install_success_writers(
        monkeypatch,
        events=events,
        inactive_market="NYSE",
        outcome="unchanged",
    )

    result = import_eoddata_daily(
        connection=connection,
        effective_date=EFFECTIVE_DATE,
        acquired_objects=_acquired_objects(),
        validation_results=_validation_results(),
    )

    nyse_listing = next(
        item
        for item in result.write_counts
        if item.market == "NYSE" and item.record_kind == "listing"
    )
    nyse_bars = next(
        item
        for item in result.write_counts
        if item.market == "NYSE" and item.record_kind == "bar"
    )
    assert nyse_listing.counts.unchanged == 1
    assert nyse_bars.counts.input_count == 0
    assert nyse_bars.skipped_inactive == 1
    assert result.skipped_inactive_bars == 1
    assert result.failures.total_count == 0


@pytest.mark.parametrize("failure_stage", ("snapshot", "listing", "bar"))
def test_any_persistence_failure_rolls_back_the_entire_service(
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
) -> None:
    connection = FakeConnection()
    events: list[str] = []
    _install_success_writers(monkeypatch, events=events)

    if failure_stage == "snapshot":
        monkeypatch.setattr(
            eoddata_import,
            "upsert_provider_source_snapshot",
            lambda **_values: (_ for _ in ()).throw(RuntimeError("secret")),
        )
    elif failure_stage == "listing":
        monkeypatch.setattr(
            eoddata_import,
            "upsert_provider_listings",
            lambda **_values: (_ for _ in ()).throw(RuntimeError("secret")),
        )
    else:
        monkeypatch.setattr(
            eoddata_import,
            "upsert_daily_bars",
            lambda **_values: (_ for _ in ()).throw(RuntimeError("secret")),
        )

    with pytest.raises(OHLCVWorkflowError) as error:
        import_eoddata_daily(
            connection=connection,
            effective_date=EFFECTIVE_DATE,
            acquired_objects=_acquired_objects(),
            validation_results=_validation_results(),
        )

    assert error.value.stage == "persistence"
    assert "secret" not in str(error.value)
    assert connection.commit_calls == 0
    assert connection.rollback_calls == 1


def test_duplicate_policy_outcomes_are_carried_without_writing_rejected_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    symbols = parse_eoddata_symbol_list(
        json.dumps(
            [
                {"code": "EMP.A"},
                {"code": "CLASH"},
            ]
        ).encode("utf-8"),
        exchange="NYSE",
    )
    quotes = parse_eoddata_quote_list(
        (
            FIXTURE_DIRECTORY
            / "eoddata_daily"
            / "nyse_daily_duplicates.json"
        ).read_bytes(),
        exchange="NYSE",
        effective_date=EFFECTIVE_DATE,
        symbol_list=symbols,
    )
    validations = (
        quotes.to_validation_result(symbol_list=symbols),
        _validation_result("NASDAQ"),
        _validation_result("AMEX"),
    )
    connection = FakeConnection()
    events: list[str] = []
    written_tickers: list[str] = []
    _install_success_writers(monkeypatch, events=events)
    original_listing_writer = eoddata_import.upsert_provider_listings

    def capture_listings(**values: object) -> ProviderListingWriteResult:
        listings = tuple(values["listings"])  # type: ignore[arg-type]
        written_tickers.extend(listing.ticker for listing in listings)
        return original_listing_writer(
            cursor=values["cursor"],
            listings=listings,
        )

    monkeypatch.setattr(
        eoddata_import,
        "upsert_provider_listings",
        capture_listings,
    )

    result = import_eoddata_daily(
        connection=connection,
        effective_date=EFFECTIVE_DATE,
        acquired_objects=_acquired_objects(),
        validation_results=validations,
    )

    assert "GHOST" not in written_tickers
    assert set(written_tickers[:2]) == {"CLASH", "EMP.A"}
    assert result.failures.total_count == 2
    assert result.warnings.total_count == 1
    assert tuple(issue.record_reference for issue in result.failures.samples) == (
        "NYSE:CLASH",
        "NYSE:GHOST",
    )
    nyse_daily = next(
        item
        for item in result.feed_counts
        if item.source_code == "eoddata_daily" and item.market == "NYSE"
    )
    assert nyse_daily.accepted_records == 1
    assert nyse_daily.rejected_records == 2
    assert nyse_daily.duplicate_rows_collapsed == 1


@pytest.mark.parametrize(
    "mutation",
    ("missing_object", "missing_market", "wrong_date", "duplicate_listing"),
)
def test_invalid_complete_run_shape_fails_before_opening_transaction(
    mutation: str,
) -> None:
    connection = FakeConnection()
    objects = _acquired_objects()
    validations = _validation_results()
    effective_date = EFFECTIVE_DATE
    if mutation == "missing_object":
        objects = objects[:-1]
    elif mutation == "missing_market":
        validations = validations[:-1]
    elif mutation == "wrong_date":
        effective_date = date(2026, 7, 16)
    else:
        validations = (validations[0], validations[0], validations[1])

    with pytest.raises((TypeError, ValueError)):
        import_eoddata_daily(
            connection=connection,
            effective_date=effective_date,
            acquired_objects=objects,
            validation_results=validations,
        )

    assert connection.cursor_calls == 0
    assert connection.commit_calls == 0
    assert connection.rollback_calls == 0
