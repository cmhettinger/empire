from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

import empire_stonks_tech_indicators as public_api
from empire_stonks_tech_indicators import (
    BenchmarkConfig,
    BenchmarkHistory,
    EligibleListing,
    ListingStateComparison,
    ResolvedBenchmark,
    SourceBar,
    TechIndicatorsScope,
    TechIndicatorsValidationError,
    iter_source_bar_pages,
    iter_state_comparison_pages,
    load_spx_benchmark_history,
    resolve_spx_benchmark,
    select_eligible_listings,
)
from empire_stonks_tech_indicators import queries as queries_module
from empire_stonks_tech_indicators import state as state_module


ACTIVE_ID = UUID("00000000-0000-4000-8000-000000000001")
INACTIVE_ID = UUID("00000000-0000-4000-8000-000000000002")
BENCHMARK_ID = UUID("00000000-0000-4000-8000-000000000003")


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

    def fetchmany(self, size: int) -> list[tuple[object, ...]]:
        rows = self.rows[:size]
        self.rows = self.rows[size:]
        return rows


class SequencedCursor:
    def __init__(self, responses: list[list[tuple[object, ...]]]) -> None:
        self.responses = responses
        self.executions: list[tuple[str, tuple[object, ...]]] = []
        self.fetch_sizes: list[int] = []

    def execute(self, sql: str, parameters: tuple[object, ...]) -> None:
        self.executions.append((sql, parameters))

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.responses.pop(0)

    def fetchmany(self, size: int) -> list[tuple[object, ...]]:
        self.fetch_sizes.append(size)
        rows = self.responses[0][:size]
        self.responses[0] = self.responses[0][size:]
        return rows


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


def _benchmark_row(**overrides: object) -> tuple[object, ...]:
    values: list[object] = [
        BENCHMARK_ID,
        "YAHOO",
        "XIDX",
        "SPX",
        "EQUITY_INDEX",
        "ACTIVE",
        {"YahooTicker": "^GSPC", "ReviewedFact": "allowed"},
    ]
    positions = {
        "provider_listing_id": 0,
        "provider_code": 1,
        "market": 2,
        "ticker": 3,
        "instrument_type_code": 4,
        "status": 5,
        "metadata": 6,
    }
    for name, value in overrides.items():
        values[positions[name]] = value
    return tuple(values)


def _resolved_benchmark() -> ResolvedBenchmark:
    return ResolvedBenchmark(
        provider_listing_id=BENCHMARK_ID,
        provider_code="YAHOO",
        market="XIDX",
        ticker="SPX",
        instrument_type_code="EQUITY_INDEX",
        status="ACTIVE",
        yahoo_ticker="^GSPC",
    )


def _benchmark_bar(
    trading_date: date,
    close: str,
    *,
    provider_listing_id: UUID = BENCHMARK_ID,
) -> SourceBar:
    close_value = Decimal(close)
    return SourceBar(
        provider_listing_id=provider_listing_id,
        trading_date=trading_date,
        open=close_value - 1,
        high=close_value + 1,
        low=close_value - 2,
        close=close_value,
        volume=Decimal("100"),
    )


def _benchmark_listing_row(
    *,
    first_trading_date: date | None,
    last_trading_date: date | None,
    source_observation_count: int,
) -> tuple[object, ...]:
    return (
        BENCHMARK_ID,
        "YAHOO",
        "XIDX",
        "SPX",
        "EQUITY_INDEX",
        "ACTIVE",
        first_trading_date,
        last_trading_date,
        source_observation_count,
    )


def _benchmark_bar_row(trading_date: date, close: str) -> tuple[object, ...]:
    bar = _benchmark_bar(trading_date, close)
    return (
        "YAHOO",
        "XIDX",
        "SPX",
        bar.provider_listing_id,
        bar.trading_date,
        bar.open,
        bar.high,
        bar.low,
        bar.close,
        bar.volume,
    )


def _state_row(**overrides: object) -> tuple[object, ...]:
    values: list[object] = [
        ACTIVE_ID,
        "EODDATA",
        "NASDAQ",
        "TEST",
        date(2026, 1, 2),
        date(2026, 1, 8),
        5,
        date(2026, 1, 7),
        1,
        1,
        1,
        1,
        1,
        date(2026, 1, 8),
        date(2026, 1, 3),
        date(2026, 1, 5),
        date(2026, 1, 6),
        date(2026, 1, 7),
    ]
    positions = {
        "provider_listing_id": 0,
        "provider_code": 1,
        "market": 2,
        "ticker": 3,
        "first_source_date": 4,
        "last_source_date": 5,
        "source_observation_count": 6,
        "last_technical_date": 7,
        "tail_append_count": 8,
        "missing_tech_row_count": 9,
        "source_copy_drift_count": 10,
        "history_count_drift_count": 11,
        "version_drift_count": 12,
        "earliest_tail_append_date": 13,
        "earliest_missing_tech_date": 14,
        "earliest_source_copy_drift_date": 15,
        "earliest_history_count_drift_date": 16,
        "earliest_version_drift_date": 17,
    }
    for name, value in overrides.items():
        values[positions[name]] = value
    return tuple(values)


def test_query_api_is_explicitly_exported() -> None:
    assert queries_module.__all__ == [
        "BenchmarkHistory",
        "EligibleListing",
        "iter_source_bar_pages",
        "load_spx_benchmark_history",
        "resolve_spx_benchmark",
        "select_eligible_listings",
    ]
    assert state_module.__all__ == [
        "ListingStateComparison",
        "iter_state_comparison_pages",
    ]
    assert public_api.BenchmarkHistory is BenchmarkHistory
    assert public_api.EligibleListing is EligibleListing
    assert public_api.ListingStateComparison is ListingStateComparison
    assert public_api.iter_source_bar_pages is iter_source_bar_pages
    assert public_api.iter_state_comparison_pages is iter_state_comparison_pages
    assert public_api.load_spx_benchmark_history is load_spx_benchmark_history
    assert public_api.resolve_spx_benchmark is resolve_spx_benchmark
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


def test_resolve_spx_benchmark_returns_exact_reviewed_identity() -> None:
    cursor = FakeCursor([_benchmark_row()])

    benchmark = resolve_spx_benchmark(
        cursor=cursor,
        config=BenchmarkConfig(),
    )

    assert benchmark.to_dict() == {
        "provider_listing_id": str(BENCHMARK_ID),
        "provider_code": "YAHOO",
        "market": "XIDX",
        "ticker": "SPX",
        "instrument_type_code": "EQUITY_INDEX",
        "status": "ACTIVE",
        "yahoo_ticker": "^GSPC",
    }
    assert "status =" not in cursor.sql
    assert "instrument_type_code =" not in cursor.sql
    assert "metadata" in cursor.sql
    assert "LIMIT 2" in cursor.sql
    assert cursor.parameters == ("YAHOO", "XIDX", "SPX")


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([], "missing"),
        ([_benchmark_row(), _benchmark_row()], "duplicated"),
        ([_benchmark_row(status="INACTIVE")], "ACTIVE"),
        (
            [_benchmark_row(instrument_type_code="UNKNOWN")],
            "instrument type has drifted",
        ),
        ([_benchmark_row(metadata=None)], "YahooTicker metadata has drifted"),
        (
            [_benchmark_row(metadata={"YahooTicker": 1})],
            "YahooTicker metadata has drifted",
        ),
        (
            [_benchmark_row(metadata={"YahooTicker": "SPX"})],
            "YahooTicker metadata has drifted",
        ),
        (
            [_benchmark_row(provider_listing_id="bad")],
            "invalid contract data",
        ),
    ],
)
def test_resolve_spx_benchmark_fails_closed(
    rows: list[tuple[object, ...]],
    message: str,
) -> None:
    with pytest.raises(TechIndicatorsValidationError, match=message):
        resolve_spx_benchmark(
            cursor=FakeCursor(rows),
            config=BenchmarkConfig(),
        )


def test_resolve_spx_benchmark_rejects_invalid_boundary_types() -> None:
    with pytest.raises(TypeError, match="cursor"):
        resolve_spx_benchmark(cursor=object(), config=BenchmarkConfig())
    with pytest.raises(TypeError, match="BenchmarkConfig"):
        resolve_spx_benchmark(
            cursor=FakeCursor([]),
            config=object(),  # type: ignore[arg-type]
        )


def test_benchmark_history_preserves_exact_dates_without_filling_gaps() -> None:
    first_date = date(2026, 1, 2)
    last_date = date(2026, 1, 5)
    first_bar = _benchmark_bar(first_date, "10")
    last_bar = _benchmark_bar(last_date, "12")
    history = BenchmarkHistory(
        benchmark=_resolved_benchmark(),
        bars=(first_bar, last_bar),
    )

    assert history.observation_count == 2
    assert history.first_trading_date == first_date
    assert history.last_trading_date == last_date
    assert history.bar_on(first_date) is first_bar
    assert history.bar_on(date(2026, 1, 3)) is None
    assert history.close_by_date() == {
        first_date: Decimal("10"),
        last_date: Decimal("12"),
    }
    assert history.to_dict() == {
        "benchmark": _resolved_benchmark().to_dict(),
        "observation_count": 2,
        "first_trading_date": "2026-01-02",
        "last_trading_date": "2026-01-05",
    }
    json.dumps(history.to_dict())


def test_benchmark_history_rejects_mixed_or_unordered_bars() -> None:
    other_id = UUID("00000000-0000-4000-8000-000000000004")
    with pytest.raises(ValueError, match="resolved listing ID"):
        BenchmarkHistory(
            benchmark=_resolved_benchmark(),
            bars=(
                _benchmark_bar(
                    date(2026, 1, 2),
                    "10",
                    provider_listing_id=other_id,
                ),
            ),
        )
    with pytest.raises(ValueError, match="strictly chronological"):
        BenchmarkHistory(
            benchmark=_resolved_benchmark(),
            bars=(
                _benchmark_bar(date(2026, 1, 5), "12"),
                _benchmark_bar(date(2026, 1, 2), "10"),
            ),
        )
    with pytest.raises(TypeError, match="bars"):
        BenchmarkHistory(
            benchmark=_resolved_benchmark(),
            bars=[],  # type: ignore[arg-type]
        )


def test_benchmark_history_requires_exact_date_lookup() -> None:
    history = BenchmarkHistory(benchmark=_resolved_benchmark(), bars=())

    with pytest.raises(TypeError, match="trading_date"):
        history.bar_on("2026-01-02")  # type: ignore[arg-type]


def test_benchmark_history_loader_resolves_and_reads_bounded_exact_bars() -> None:
    first_date = date(2026, 1, 2)
    last_date = date(2026, 1, 5)
    cursor = SequencedCursor(
        [
            [_benchmark_row()],
            [
                _benchmark_listing_row(
                    first_trading_date=first_date,
                    last_trading_date=last_date,
                    source_observation_count=2,
                )
            ],
            [
                _benchmark_bar_row(first_date, "10"),
                _benchmark_bar_row(last_date, "12"),
            ],
        ]
    )

    history = load_spx_benchmark_history(
        cursor=cursor,
        config=BenchmarkConfig(),
        start_date=first_date,
        end_date=last_date,
        page_size=1000,
    )

    assert history.benchmark == _resolved_benchmark()
    assert [bar.trading_date for bar in history.bars] == [first_date, last_date]
    assert history.bar_on(date(2026, 1, 3)) is None
    assert len(cursor.executions) == 3
    assert cursor.executions[0][1] == ("YAHOO", "XIDX", "SPX")
    assert cursor.executions[1][1] == (
        first_date,
        last_date,
        [BENCHMARK_ID],
    )
    assert cursor.executions[2][1] == (
        [BENCHMARK_ID],
        first_date,
        last_date,
        1000,
    )


def test_benchmark_history_loader_preserves_empty_exact_history() -> None:
    cursor = SequencedCursor(
        [
            [_benchmark_row()],
            [
                _benchmark_listing_row(
                    first_trading_date=None,
                    last_trading_date=None,
                    source_observation_count=0,
                )
            ],
            [],
        ]
    )

    history = load_spx_benchmark_history(
        cursor=cursor,
        config=BenchmarkConfig(),
    )

    assert history.bars == ()
    assert history.first_trading_date is None
    assert history.close_by_date() == {}


@pytest.mark.parametrize(
    ("start_date", "end_date", "exception", "message"),
    [
        (date(2026, 1, 2), None, ValueError, "provided together"),
        ("2026-01-02", "2026-01-05", TypeError, "must be dates"),
        (date(2026, 1, 5), date(2026, 1, 2), ValueError, "must not be after"),
    ],
)
def test_benchmark_history_loader_rejects_invalid_date_ranges(
    start_date: object,
    end_date: object,
    exception: type[Exception],
    message: str,
) -> None:
    cursor = FakeCursor([])

    with pytest.raises(exception, match=message):
        load_spx_benchmark_history(
            cursor=cursor,
            config=BenchmarkConfig(),
            start_date=start_date,  # type: ignore[arg-type]
            end_date=end_date,  # type: ignore[arg-type]
        )
    assert cursor.sql == ""


def test_listing_state_comparison_exposes_reasons_and_version_restart() -> None:
    comparison = ListingStateComparison(*_state_row())

    assert comparison.missing_row_count == 2
    assert comparison.reasons == (
        "TAIL_APPEND",
        "MISSING_TECH_ROW",
        "SOURCE_COPY_DRIFT",
        "HISTORY_COUNT_DRIFT",
        "VERSION_DRIFT",
    )
    assert comparison.earliest_recalculation_date == date(2026, 1, 2)
    assert comparison.is_equivalent is False
    assert comparison.to_dict()["earliest_recalculation_date"] == "2026-01-02"
    json.dumps(comparison.to_dict())


def test_listing_state_comparison_uses_earliest_non_version_uncertainty() -> None:
    comparison = ListingStateComparison(
        *_state_row(
            version_drift_count=0,
            earliest_version_drift_date=None,
        )
    )

    assert comparison.earliest_recalculation_date == date(2026, 1, 3)


def test_listing_state_comparison_preserves_equivalent_empty_source() -> None:
    comparison = ListingStateComparison(
        *_state_row(
            first_source_date=None,
            last_source_date=None,
            source_observation_count=0,
            last_technical_date=None,
            tail_append_count=0,
            missing_tech_row_count=0,
            source_copy_drift_count=0,
            history_count_drift_count=0,
            version_drift_count=0,
            earliest_tail_append_date=None,
            earliest_missing_tech_date=None,
            earliest_source_copy_drift_date=None,
            earliest_history_count_drift_date=None,
            earliest_version_drift_date=None,
        )
    )

    assert comparison.is_equivalent is True
    assert comparison.reasons == ()
    assert comparison.earliest_recalculation_date is None


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (_state_row(source_observation_count=-1), "non-negative"),
        (_state_row(earliest_tail_append_date=None), "exactly when"),
        (
            _state_row(first_source_date=None, last_source_date=None),
            "exactly when source count is zero",
        ),
    ],
)
def test_listing_state_comparison_rejects_invalid_rows(
    row: tuple[object, ...],
    message: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        ListingStateComparison(*row)  # type: ignore[arg-type]


def test_state_comparison_query_is_set_based_paged_and_scope_safe() -> None:
    cursor = SequencedCursor(
        [
            [_row()],
            [_state_row()],
        ]
    )
    scope = TechIndicatorsScope(
        provider_listing_ids=(ACTIVE_ID,),
        start_date=date(2026, 1, 3),
        end_date=date(2026, 1, 8),
    )

    pages = list(
        iter_state_comparison_pages(
            cursor=cursor,
            scope=scope,
            calculation_version="TECH_INDICATORS_V1",
            page_size=1000,
        )
    )

    assert pages == [(ListingStateComparison(*_state_row()),)]
    assert cursor.fetch_sizes == [1000, 1000]
    assert len(cursor.executions) == 2
    sql, parameters = cursor.executions[1]
    assert "row_number() OVER" in sql
    assert "stonks.ohlcv_daily_tech_indicators AS technical" in sql
    assert "ROW(" in sql
    assert "IS DISTINCT FROM ROW(" in sql
    assert "technical.history_observation_count" in sql
    assert "source_state.trading_date BETWEEN %s AND %s" in sql
    assert parameters == (
        [ACTIVE_ID],
        "TECH_INDICATORS_V1",
        date(2026, 1, 3),
        date(2026, 1, 8),
    )


def test_state_comparison_query_handles_empty_selection() -> None:
    cursor = SequencedCursor([[]])

    assert list(
        iter_state_comparison_pages(
            cursor=cursor,
            scope=TechIndicatorsScope(),
            calculation_version="TECH_INDICATORS_V1",
        )
    ) == []
    assert len(cursor.executions) == 1
    assert cursor.fetch_sizes == []


@pytest.mark.parametrize(
    ("version", "exception"),
    [
        (1, TypeError),
        ("tech_indicators_v1", ValueError),
        ("TECH-INDICATORS-V1", ValueError),
        ("A" * 65, ValueError),
    ],
)
def test_state_comparison_query_rejects_invalid_versions(
    version: object,
    exception: type[Exception],
) -> None:
    with pytest.raises(exception, match="calculation_version"):
        list(
            iter_state_comparison_pages(
                cursor=SequencedCursor([[]]),
                scope=TechIndicatorsScope(),
                calculation_version=version,  # type: ignore[arg-type]
            )
        )


def test_state_comparison_query_requires_fetchmany_and_ordered_identity() -> None:
    class FetchAllOnlyCursor:
        def execute(self, sql: str, parameters: tuple[object, ...]) -> None:
            pass

        def fetchall(self) -> list[tuple[object, ...]]:
            return []

    with pytest.raises(TypeError, match="fetchmany"):
        list(
            iter_state_comparison_pages(
                cursor=FetchAllOnlyCursor(),
                scope=TechIndicatorsScope(),
                calculation_version="TECH_INDICATORS_V1",
            )
        )

    cursor = SequencedCursor(
        [
            [_row()],
            [_state_row(ticker="DRIFT")],
        ]
    )
    with pytest.raises(ValueError, match="identity drift"):
        list(
            iter_state_comparison_pages(
                cursor=cursor,
                scope=TechIndicatorsScope(
                    provider_listing_ids=(ACTIVE_ID,),
                ),
                calculation_version="TECH_INDICATORS_V1",
            )
        )
