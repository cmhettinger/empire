from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

import empire_stonks_tech_indicators as public_api
from empire_stonks_tech_indicators import (
    EligibleListing,
    TechIndicatorsScope,
    iter_source_bar_pages,
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


class SequencedCursor:
    def __init__(self, responses: list[list[tuple[object, ...]]]) -> None:
        self.responses = responses
        self.executions: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql: str, parameters: tuple[object, ...]) -> None:
        self.executions.append((sql, parameters))

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.responses.pop(0)


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


def _bar_row(index: int) -> tuple[object, ...]:
    trading_date = date(2020, 1, 1) + timedelta(days=index + (index > 500))
    if index == 0:
        values = (
            Decimal("-3.0000000000"),
            Decimal("-1.0000000000"),
            Decimal("-4.0000000000"),
            Decimal("-2.0000000000"),
            None,
        )
    else:
        values = (
            Decimal("10.0000000000"),
            Decimal("12.0000000000"),
            Decimal("9.0000000000"),
            Decimal("11.0000000000"),
            Decimal("100.00000000"),
        )
    return (
        "EODDATA",
        "NASDAQ",
        "TEST",
        ACTIVE_ID,
        trading_date,
        *values,
    )


def test_query_api_is_explicitly_exported() -> None:
    assert queries_module.__all__ == [
        "EligibleListing",
        "iter_source_bar_pages",
        "select_eligible_listings",
    ]
    assert public_api.EligibleListing is EligibleListing
    assert public_api.iter_source_bar_pages is iter_source_bar_pages
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


def test_source_bar_reader_uses_bounded_keyset_pages_and_exact_values() -> None:
    listing_row = _row(
        first_trading_date=date(2020, 1, 1),
        last_trading_date=date(2022, 9, 29),
        source_observation_count=1002,
    )
    source_rows = [_bar_row(index) for index in range(1002)]
    cursor = SequencedCursor(
        [
            [listing_row],
            source_rows[:1000],
            source_rows[1000:],
        ]
    )
    scope = TechIndicatorsScope(
        provider_listing_ids=(ACTIVE_ID,),
        start_date=date(2020, 1, 1),
        end_date=date(2022, 9, 29),
    )

    pages = list(
        iter_source_bar_pages(
            cursor=cursor,
            scope=scope,
            page_size=1000,
        )
    )

    assert [len(page) for page in pages] == [1000, 2]
    assert pages[0][0].to_dict() == {
        "provider_listing_id": str(ACTIVE_ID),
        "trading_date": "2020-01-01",
        "open": "-3.0000000000",
        "high": "-1.0000000000",
        "low": "-4.0000000000",
        "close": "-2.0000000000",
        "volume": None,
    }
    assert pages[0][500].trading_date == date(2021, 5, 15)
    assert pages[0][501].trading_date == date(2021, 5, 17)
    assert pages[1][-1].trading_date == source_rows[-1][4]
    assert len(cursor.executions) == 3
    first_page_sql, first_page_parameters = cursor.executions[1]
    assert "daily.provider_listing_id = ANY(%s::uuid[])" in first_page_sql
    assert "daily.trading_date BETWEEN %s AND %s" in first_page_sql
    assert ") > ROW(%s, %s, %s, %s, %s)" not in first_page_sql
    assert "LIMIT %s" in first_page_sql
    assert first_page_parameters == (
        [ACTIVE_ID],
        date(2020, 1, 1),
        date(2022, 9, 29),
        1000,
    )
    second_page_sql, second_page_parameters = cursor.executions[2]
    assert ") > ROW(%s, %s, %s, %s, %s)" in second_page_sql
    assert second_page_parameters[-6:] == (
        "EODDATA",
        "NASDAQ",
        "TEST",
        ACTIVE_ID,
        source_rows[999][4],
        1000,
    )


def test_source_bar_reader_handles_empty_selection_without_bar_query() -> None:
    cursor = SequencedCursor([[]])

    assert list(
        iter_source_bar_pages(
            cursor=cursor,
            scope=TechIndicatorsScope(),
        )
    ) == []
    assert len(cursor.executions) == 1


@pytest.mark.parametrize("page_size", [True, 999, 50_001])
def test_source_bar_reader_rejects_invalid_page_size(page_size: object) -> None:
    with pytest.raises((TypeError, ValueError), match="page_size"):
        list(
            iter_source_bar_pages(
                cursor=FakeCursor([]),
                scope=TechIndicatorsScope(),
                page_size=page_size,  # type: ignore[arg-type]
            )
        )


def test_source_bar_reader_rejects_unordered_or_drifted_rows() -> None:
    listing_row = _row()
    later = _bar_row(2)
    earlier = _bar_row(1)
    unordered = SequencedCursor([[listing_row], [later, earlier]])
    with pytest.raises(ValueError, match="unordered"):
        list(
            iter_source_bar_pages(
                cursor=unordered,
                scope=TechIndicatorsScope(provider_listing_ids=(ACTIVE_ID,)),
                page_size=1000,
            )
        )

    drifted_row = list(_bar_row(0))
    drifted_row[2] = "OTHER"
    drifted = SequencedCursor([[listing_row], [tuple(drifted_row)]])
    with pytest.raises(ValueError, match="identity drift"):
        list(
            iter_source_bar_pages(
                cursor=drifted,
                scope=TechIndicatorsScope(provider_listing_ids=(ACTIVE_ID,)),
                page_size=1000,
            )
        )
