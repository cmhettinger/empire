from __future__ import annotations

import json
from uuid import UUID

import pytest

from empire_stonks_ohlcv import (
    OHLCVPersistenceError,
    ProviderListing,
    upsert_provider_listings,
)


class FakeProviderListingCursor:
    """Focused in-memory cursor for provider-listing writer SQL behavior."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str, str], dict[str, object]] = {}
        self._next_id = 1
        self._result: tuple[object, ...] | None = None
        self.insert_identities: list[tuple[str, str, str]] = []
        self.locked_ids: list[UUID] = []
        self.update_count = 0

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        if "INSERT INTO stonks.provider_listing" in query:
            provider_code, market, ticker, name, instrument_type_code, metadata = params
            identity = (str(provider_code), str(market), str(ticker))
            self.insert_identities.append(identity)
            row = self.rows.get(identity)
            if row is None:
                provider_listing_id = UUID(int=self._next_id)
                self._next_id += 1
                row = {
                    "provider_listing_id": provider_listing_id,
                    "name": name,
                    "instrument_type_code": instrument_type_code,
                    "metadata": None if metadata is None else json.loads(str(metadata)),
                    "status": "ACTIVE",
                }
                self.rows[identity] = row
                self._result = (provider_listing_id,)
            else:
                self._result = None
            return

        if (
            "SELECT provider_listing_id\n                FROM stonks.provider_listing"
            in query
        ):
            identity = tuple(params)
            row = self.rows.get(identity)  # type: ignore[arg-type]
            self._result = None if row is None else (row["provider_listing_id"],)
            return

        if "SELECT provider_listing_id, name, instrument_type_code" in query:
            provider_listing_id = params[0]
            self.locked_ids.append(provider_listing_id)  # type: ignore[arg-type]
            row = next(
                (
                    candidate
                    for candidate in self.rows.values()
                    if candidate["provider_listing_id"] == provider_listing_id
                ),
                None,
            )
            self._result = (
                None
                if row is None
                else (
                    row["provider_listing_id"],
                    row["name"],
                    row["instrument_type_code"],
                    row["metadata"],
                    row["status"],
                )
            )
            return

        if "UPDATE stonks.provider_listing" in query:
            name, instrument_type_code, metadata, provider_listing_id = params
            row = next(
                candidate
                for candidate in self.rows.values()
                if candidate["provider_listing_id"] == provider_listing_id
            )
            row["name"] = name
            row["instrument_type_code"] = instrument_type_code
            row["metadata"] = (
                None if metadata is None else json.loads(str(metadata))
            )
            self.update_count += 1
            self._result = None
            return

        raise AssertionError(f"Unexpected SQL: {query}")

    def fetchone(self) -> tuple[object, ...] | None:
        return self._result


def listing(
    *,
    provider_code: str = "EODDATA",
    market: str = "NASDAQ",
    ticker: str = "AAPL",
    name: str | None = None,
    instrument_type_code: str = "UNKNOWN",
    metadata: dict[str, object] | None = None,
) -> ProviderListing:
    return ProviderListing(
        provider_code=provider_code,
        market=market,
        ticker=ticker,
        name=name,
        instrument_type_code=instrument_type_code,
        metadata=metadata,
    )


def test_inserts_sorted_exact_provider_series_and_returns_ids() -> None:
    cursor = FakeProviderListingCursor()
    inputs = (
        listing(provider_code="STOOQ", market="US", ticker="AAPL"),
        listing(provider_code="EODDATA", market="NYSE", ticker="AAPL"),
        listing(provider_code="EODDATA", market="NASDAQ", ticker="AAPL"),
    )

    result = upsert_provider_listings(cursor=cursor, listings=inputs)

    assert result.inserted == 3
    assert result.updated == 0
    assert result.unchanged == 0
    assert result.counts.to_dict() == {
        "inserted": 3,
        "updated": 0,
        "unchanged": 0,
        "derived_updated": 0,
    }
    assert cursor.insert_identities == [
        ("EODDATA", "NASDAQ", "AAPL"),
        ("EODDATA", "NYSE", "AAPL"),
        ("STOOQ", "US", "AAPL"),
    ]
    assert result.provider_listing_id_for(inputs[0]) != result.provider_listing_id_for(
        inputs[1]
    )
    assert len(cursor.rows) == 3


def test_rerun_is_unchanged_and_does_not_update_metadata() -> None:
    cursor = FakeProviderListingCursor()
    source = listing(name="Apple Inc.", instrument_type_code="COMMON_STOCK")
    first = upsert_provider_listings(cursor=cursor, listings=(source,))

    second = upsert_provider_listings(cursor=cursor, listings=(source,))

    assert first.inserted == 1
    assert second.unchanged == 1
    assert second.updated == 0
    assert cursor.update_count == 0
    assert second.provider_listing_id_for(source) == first.provider_listing_id_for(
        source
    )


def test_updates_non_null_provider_metadata_and_preserves_it_when_omitted() -> None:
    cursor = FakeProviderListingCursor()
    source = listing(metadata={"figi": "OLD"})
    upsert_provider_listings(cursor=cursor, listings=(source,))

    updated = listing(metadata={"figi": "BBG000B9XRY4"})
    update_result = upsert_provider_listings(cursor=cursor, listings=(updated,))
    preserved = upsert_provider_listings(cursor=cursor, listings=(listing(),))

    row = cursor.rows[("EODDATA", "NASDAQ", "AAPL")]
    assert update_result.updated == 1
    assert preserved.unchanged == 1
    assert row["metadata"] == {"figi": "BBG000B9XRY4"}


def test_stored_inactive_status_is_returned_and_never_overwritten() -> None:
    cursor = FakeProviderListingCursor()
    source = listing()
    upsert_provider_listings(cursor=cursor, listings=(source,))
    cursor.rows[("EODDATA", "NASDAQ", "AAPL")]["status"] = "INACTIVE"

    result = upsert_provider_listings(cursor=cursor, listings=(source,))

    assert result.provider_listing_is_active(source) is False
    assert result.resolved[0].status == "INACTIVE"
    assert result.resolved[0].to_dict()["status"] == "INACTIVE"


def test_updates_non_null_name_and_non_unknown_instrument_type_only() -> None:
    cursor = FakeProviderListingCursor()
    base = listing(name="Apple", instrument_type_code="UNKNOWN")
    upsert_provider_listings(cursor=cursor, listings=(base,))

    updated = listing(name="Apple Inc.", instrument_type_code="COMMON_STOCK")
    update_result = upsert_provider_listings(cursor=cursor, listings=(updated,))
    preserved = upsert_provider_listings(cursor=cursor, listings=(listing(),))

    row = cursor.rows[("EODDATA", "NASDAQ", "AAPL")]
    assert update_result.updated == 1
    assert preserved.unchanged == 1
    assert row["name"] == "Apple Inc."
    assert row["instrument_type_code"] == "COMMON_STOCK"
    assert cursor.update_count == 1


def test_case_and_provider_market_variants_remain_distinct() -> None:
    cursor = FakeProviderListingCursor()
    inputs = (
        listing(provider_code="EODDATA", market="NASDAQ", ticker="AAPL"),
        listing(provider_code="EODDATA", market="NASDAQ", ticker="aapl"),
        listing(provider_code="EODDATA", market="nasdaq", ticker="AAPL"),
        listing(provider_code="YAHOO", market="NASDAQ", ticker="AAPL"),
    )

    result = upsert_provider_listings(cursor=cursor, listings=inputs)

    assert result.inserted == 4
    assert len(cursor.rows) == 4
    assert len({item.provider_listing_id for item in result.resolved}) == 4


def test_rejects_duplicate_native_identity_before_executing_sql() -> None:
    cursor = FakeProviderListingCursor()
    duplicate = listing(name="Apple Inc.")

    with pytest.raises(OHLCVPersistenceError, match="Duplicate provider-listing"):
        upsert_provider_listings(
            cursor=cursor,
            listings=(listing(), duplicate),
        )

    assert cursor.rows == {}
    assert cursor.insert_identities == []


def test_locks_resolved_rows_in_deterministic_id_order() -> None:
    cursor = FakeProviderListingCursor()
    inputs = (
        listing(provider_code="STOOQ", market="US", ticker="AAPL"),
        listing(provider_code="EODDATA", market="NYSE", ticker="AAPL"),
    )

    upsert_provider_listings(cursor=cursor, listings=inputs)

    assert cursor.locked_ids == sorted(cursor.locked_ids, key=str)
