from __future__ import annotations

import json
from datetime import date
from uuid import UUID

import pytest

import empire_stonks_tech_indicators as public_api
from empire_stonks_tech_indicators import (
    EligibleListing,
    TechIndicatorsScope,
    select_eligible_listings,
)
from empire_stonks_tech_indicators import queries as queries_module


ACTIVE_ID = UUID("00000000-0000-4000-8000-000000000001")
INACTIVE_ID = UUID("00000000-0000-4000-8000-000000000002")


class FakeCursor:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.rows = rows
        self.sql = ""
        self.parameters: tuple[object, ...] = ()

    def execute(self, sql: str, parameters: tuple[object, ...]) -> None:
        self.sql = sql
        self.parameters = parameters

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.rows


def _row(**overrides: object) -> tuple[object, ...]:
    values: list[object] = [
        ACTIVE_ID,
        "EODDATA",
        "NASDAQ",
        "TEST",
        "UNKNOWN",
        "ACTIVE",
        date(2026, 8, 1),
        date(2026, 8, 2),
        2,
    ]
    positions = {
        "provider_listing_id": 0,
        "provider_code": 1,
        "market": 2,
        "ticker": 3,
        "instrument_type_code": 4,
        "status": 5,
        "first_trading_date": 6,
        "last_trading_date": 7,
        "source_observation_count": 8,
    }
    for name, value in overrides.items():
        values[positions[name]] = value
    return tuple(values)


def test_query_api_is_explicitly_exported() -> None:
    assert queries_module.__all__ == [
        "EligibleListing",
        "select_eligible_listings",
    ]
    assert public_api.EligibleListing is EligibleListing
    assert public_api.select_eligible_listings is select_eligible_listings


def test_eligible_listing_exposes_scoped_history_sufficiency() -> None:
    listing = EligibleListing(*_row())

    assert listing.has_minimum_history(2) is True
    assert listing.has_minimum_history(3) is False
    assert listing.to_dict() == {
        "provider_listing_id": str(ACTIVE_ID),
        "provider_code": "EODDATA",
        "market": "NASDAQ",
        "ticker": "TEST",
        "instrument_type_code": "UNKNOWN",
        "status": "ACTIVE",
        "first_trading_date": "2026-08-01",
        "last_trading_date": "2026-08-02",
        "source_observation_count": 2,
    }
    json.dumps(listing.to_dict())


def test_eligible_listing_preserves_zero_history() -> None:
    listing = EligibleListing(
        *_row(
            first_trading_date=None,
            last_trading_date=None,
            source_observation_count=0,
        )
    )

    assert listing.has_minimum_history(1) is False
    assert listing.first_trading_date is None


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (_row(provider_listing_id="bad"), "UUID"),
        (_row(status="DISABLED"), "ACTIVE or INACTIVE"),
        (_row(source_observation_count=-1), "non-negative"),
        (
            _row(first_trading_date=None, last_trading_date=None),
            "exactly when observation count is zero",
        ),
    ],
)
def test_eligible_listing_rejects_invalid_contract_rows(
    row: tuple[object, ...],
    message: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        EligibleListing(*row)  # type: ignore[arg-type]


def test_minimum_history_requires_a_positive_integer() -> None:
    listing = EligibleListing(*_row())

    with pytest.raises(TypeError, match="integer"):
        listing.has_minimum_history(True)
    with pytest.raises(ValueError, match="positive"):
        listing.has_minimum_history(0)


def test_select_eligible_listings_applies_exact_p06_and_active_scope() -> None:
    cursor = FakeCursor([_row()])
    scope = TechIndicatorsScope(
        provider_codes=("EODDATA",),
        markets=("NASDAQ",),
        provider_listing_ids=(ACTIVE_ID,),
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 2),
    )

    listings = select_eligible_listings(cursor=cursor, scope=scope)

    assert listings == (EligibleListing(*_row()),)
    assert "daily.trading_date BETWEEN %s AND %s" in cursor.sql
    assert "listing.status = 'ACTIVE'" in cursor.sql
    assert "listing.provider_code = 'EODDATA'" in cursor.sql
    assert "upper(btrim(listing.metadata ->> 'type')) = 'EQUITY'" in cursor.sql
    assert "listing.market IN ('nasdaq', 'nyse', 'nysemkt')" in cursor.sql
    assert "listing.ticker = 'SPX'" in cursor.sql
    assert "listing.metadata ->> 'YahooTicker' = '^GSPC'" in cursor.sql
    assert cursor.parameters == (
        date(2026, 8, 1),
        date(2026, 8, 2),
        ["EODDATA"],
        ["NASDAQ"],
        [ACTIVE_ID],
    )


def test_select_eligible_listings_allows_only_explicit_inactive_opt_in() -> None:
    cursor = FakeCursor(
        [
            _row(
                provider_listing_id=INACTIVE_ID,
                status="INACTIVE",
                first_trading_date=None,
                last_trading_date=None,
                source_observation_count=0,
            )
        ]
    )
    scope = TechIndicatorsScope(
        provider_listing_ids=(INACTIVE_ID,),
        include_inactive=True,
    )

    listings = select_eligible_listings(cursor=cursor, scope=scope)

    assert listings[0].status == "INACTIVE"
    assert "listing.status IN ('ACTIVE', 'INACTIVE')" in cursor.sql
    assert "listing.provider_code = ANY" not in cursor.sql
    assert cursor.parameters == ([INACTIVE_ID],)


def test_select_eligible_listings_rejects_invalid_boundary_data() -> None:
    with pytest.raises(TypeError, match="cursor"):
        select_eligible_listings(cursor=object(), scope=TechIndicatorsScope())
    with pytest.raises(TypeError, match="TechIndicatorsScope"):
        select_eligible_listings(
            cursor=FakeCursor([]),
            scope=object(),  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="invalid row"):
        select_eligible_listings(
            cursor=FakeCursor([(ACTIVE_ID,)]),
            scope=TechIndicatorsScope(),
        )
