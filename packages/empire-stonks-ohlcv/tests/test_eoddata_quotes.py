from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from empire_stonks_ohlcv import (
    DailyBar,
    EODDATA_DAILY_SOURCE,
    EODDATA_SYMBOL_LIST_SOURCE,
    EODDataQuoteListParseResult,
    OHLCVParseError,
    ParsedListingBatch,
    ParsedProviderOutput,
    ProviderListing,
    parse_eoddata_quote_list,
    parse_eoddata_symbol_list,
)
from parser_contract import (
    InvalidParserCase,
    ValidParserCase,
    assert_parser_contract,
)


FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "eoddata"
EFFECTIVE_DATE = date(2026, 7, 15)
EXPECTED_ISSUE_SAMPLE_LIMIT = 100


def _daily_fixture(name: str) -> bytes:
    return (FIXTURE_DIRECTORY / "eoddata_daily" / name).read_bytes()


def _symbols(exchange: str, *rows: dict[str, object]):
    return parse_eoddata_symbol_list(
        json.dumps(rows, sort_keys=True).encode("utf-8"),
        exchange=exchange,
    )


def _bar(
    open_value: str,
    high: str,
    low: str,
    close: str,
    volume: str,
) -> DailyBar:
    return DailyBar(
        trading_date=EFFECTIVE_DATE,
        open=Decimal(open_value),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal(volume),
    )


def _output(*batches: ParsedListingBatch) -> ParsedProviderOutput:
    return ParsedProviderOutput(
        sources=(EODDATA_SYMBOL_LIST_SOURCE, EODDATA_DAILY_SOURCE),
        batches=batches,
    )


def _quote_row(
    *,
    exchange: str = "NYSE",
    ticker: str = "EMP.A",
    interval: str = "d",
    date_stamp: str = "2026-07-15",
    **values: object,
) -> dict[str, object]:
    return {
        "exchangeCode": exchange,
        "symbolCode": ticker,
        "interval": interval,
        "dateStamp": date_stamp,
        "open": values.get("open", 10),
        "high": values.get("high", 11),
        "low": values.get("low", 9),
        "close": values.get("close", 10.5),
        "volume": values.get("volume", 1000),
    }


def test_reconciles_quotes_and_preserves_symbol_list_metadata() -> None:
    symbol_list = _symbols(
        "NASDAQ",
        {
            "code": "EMPA",
            "name": "Empire Alpha",
            "type": "Equity",
            "currency": "USD",
        },
        {"code": "emp.B", "name": "Empire Beta", "type": "Fund"},
        {"code": "NOQUOTE", "name": "No Quote Company"},
    )

    result = parse_eoddata_quote_list(
        _daily_fixture("nasdaq_daily_valid.json"),
        exchange="NASDAQ",
        effective_date=EFFECTIVE_DATE,
        symbol_list=symbol_list,
    )

    assert isinstance(result, EODDataQuoteListParseResult)
    assert tuple(batch.listing.ticker for batch in result.batches) == (
        "EMPA",
        "NOQUOTE",
        "emp.B",
    )
    assert result.batches[0].listing.metadata == {
        "type": "Equity",
        "currency": "USD",
    }
    assert result.batches[0].bars == (
        _bar("10.2500", "10.8750", "10.1250", "10.7500", "125000"),
    )
    assert result.batches[1].bars == ()
    assert result.batches[2].listing.metadata == {"type": "Fund"}
    assert result.batches[2].bars == (
        _bar("27.7900", "27.7900", "27.5900", "27.7096", "0"),
    )
    assert result.symbols_without_quotes == 1
    assert result.bar_count == 2
    assert result.issues == ()


def test_duplicate_and_unmatched_quotes_have_deterministic_outcomes() -> None:
    symbol_list = _symbols(
        "NYSE",
        {"code": "EMP.A", "name": "Empire Alpha"},
        {"code": "CLASH", "name": "Conflicting Quote"},
    )

    result = parse_eoddata_quote_list(
        _daily_fixture("nyse_daily_duplicates.json"),
        exchange="NYSE",
        effective_date=EFFECTIVE_DATE,
        symbol_list=symbol_list,
    )

    assert tuple(batch.listing.ticker for batch in result.batches) == (
        "CLASH",
        "EMP.A",
    )
    assert result.batches[0].bars == ()
    assert result.batches[1].bars == (
        _bar("10.00", "11.00", "9.50", "10.50", "1000"),
    )
    assert result.compatible_duplicate_groups == 1
    assert result.collapsed_duplicate_rows == 1
    assert result.conflicting_duplicate_groups == 1
    assert result.conflicting_duplicate_rows == 2
    assert result.unmatched_quote_groups == 1
    assert result.unmatched_quote_rows == 1
    assert result.symbols_without_quotes == 0
    assert result.rejected_rows == 3
    assert tuple(issue.to_dict() for issue in result.issues) == (
        {
            "code": "eoddata_quote_duplicate_conflict",
            "message": (
                "Conflicting duplicate Quote List fields were rejected: close."
            ),
            "source_code": "eoddata_daily",
            "record_reference": "NYSE:CLASH",
        },
        {
            "code": "eoddata_quote_without_listing",
            "message": (
                "Quote List identity has no accepted same-exchange Symbol "
                "List identity."
            ),
            "source_code": "eoddata_daily",
            "record_reference": "NYSE:GHOST",
        },
    )


def test_duplicate_resolution_is_independent_of_row_order() -> None:
    rows = json.loads(_daily_fixture("nyse_daily_duplicates.json"))
    symbol_list = _symbols(
        "NYSE",
        {"code": "EMP.A"},
        {"code": "CLASH"},
    )

    forward = parse_eoddata_quote_list(
        json.dumps(rows).encode("utf-8"),
        exchange="NYSE",
        effective_date=EFFECTIVE_DATE,
        symbol_list=symbol_list,
    )
    reversed_order = parse_eoddata_quote_list(
        json.dumps(list(reversed(rows))).encode("utf-8"),
        exchange="NYSE",
        effective_date=EFFECTIVE_DATE,
        symbol_list=symbol_list,
    )

    assert reversed_order == forward


def test_empty_quote_list_retains_symbols_without_bars() -> None:
    symbol_list = _symbols("NYSE", {"code": "EMP.A"}, {"code": "QUIET"})

    result = parse_eoddata_quote_list(
        b"[]",
        exchange="NYSE",
        effective_date=EFFECTIVE_DATE,
        symbol_list=symbol_list,
    )

    assert result.empty_quote_list is True
    assert result.row_count == 0
    assert result.listing_count == 2
    assert result.bar_count == 0
    assert result.symbols_without_quotes == 2
    assert result.issues == ()


@pytest.mark.parametrize(
    ("row", "message"),
    (
        (_quote_row(exchange="NASDAQ"), "exchange mismatch"),
        (_quote_row(interval="h"), "interval mismatch"),
        (_quote_row(date_stamp="2026-07-14"), "date mismatch"),
        (_quote_row(ticker=" BAD"), "invalid symbolCode"),
    ),
)
def test_rejects_request_scope_and_identity_mismatches(
    row: dict[str, object],
    message: str,
) -> None:
    symbol_list = _symbols("NYSE", {"code": "EMP.A"})

    with pytest.raises(OHLCVParseError, match=message):
        parse_eoddata_quote_list(
            json.dumps([row]).encode("utf-8"),
            exchange="NYSE",
            effective_date=EFFECTIVE_DATE,
            symbol_list=symbol_list,
        )


@pytest.mark.parametrize(
    ("payload", "message"),
    (
        (b"not-json", "payload is invalid JSON"),
        (b"{}", "payload must be a JSON array"),
        (b"[1]", "row 1 must be an object"),
        (b"[NaN]", "payload is invalid JSON"),
    ),
)
def test_rejects_structurally_invalid_payloads(
    payload: bytes,
    message: str,
) -> None:
    symbol_list = _symbols("NYSE", {"code": "EMP.A"})

    with pytest.raises(OHLCVParseError, match=message):
        parse_eoddata_quote_list(
            payload,
            exchange="NYSE",
            effective_date=EFFECTIVE_DATE,
            symbol_list=symbol_list,
        )


def test_invalid_ohlcv_group_is_rejected_without_losing_listing() -> None:
    symbol_list = _symbols("NYSE", {"code": "EMP.A"})
    invalid = _quote_row(high=9)

    result = parse_eoddata_quote_list(
        json.dumps([invalid]).encode("utf-8"),
        exchange="NYSE",
        effective_date=EFFECTIVE_DATE,
        symbol_list=symbol_list,
    )

    assert result.batches[0].bars == ()
    assert result.invalid_quote_groups == 1
    assert result.invalid_quote_rows == 1
    assert result.rejected_rows == 1
    assert result.issues[0].code == "eoddata_quote_invalid_ohlcv"


def test_input_scope_must_match_symbol_list_scope() -> None:
    symbol_list = _symbols("NASDAQ", {"code": "EMPA"})

    with pytest.raises(ValueError, match="symbol_list exchange must match"):
        parse_eoddata_quote_list(
            b"[]",
            exchange="NYSE",
            effective_date=EFFECTIVE_DATE,
            symbol_list=symbol_list,
        )


def test_issue_samples_are_bounded_and_count_all_unmatched_quotes() -> None:
    rows = [
        _quote_row(ticker=f"G{index:03d}")
        for index in range(EXPECTED_ISSUE_SAMPLE_LIMIT + 1)
    ]
    symbol_list = _symbols("NYSE", {"code": "KNOWN"})

    result = parse_eoddata_quote_list(
        json.dumps(rows).encode("utf-8"),
        exchange="NYSE",
        effective_date=EFFECTIVE_DATE,
        symbol_list=symbol_list,
    )

    assert result.issue_count == EXPECTED_ISSUE_SAMPLE_LIMIT + 1
    assert len(result.issues) == EXPECTED_ISSUE_SAMPLE_LIMIT
    assert result.issues[0].record_reference == "NYSE:G000"
    assert result.issues[-1].record_reference == "NYSE:G099"


def test_same_ticker_is_isolated_across_all_exchange_partitions() -> None:
    results = []
    for exchange in ("NYSE", "NASDAQ", "AMEX"):
        symbol_list = _symbols(exchange, {"code": "OVERLAP"})
        payload = json.dumps(
            [_quote_row(exchange=exchange, ticker="OVERLAP")]
        ).encode("utf-8")
        results.append(
            parse_eoddata_quote_list(
                payload,
                exchange=exchange,
                effective_date=EFFECTIVE_DATE,
                symbol_list=symbol_list,
            )
        )

    assert tuple(result.batches[0].listing.market for result in results) == (
        "NYSE",
        "NASDAQ",
        "AMEX",
    )
    assert all(result.bar_count == 1 for result in results)


def test_reconciled_result_builds_shared_validation_counts_and_issues() -> None:
    symbol_list = _symbols(
        "NYSE",
        {"code": "DUP", "name": "Compatible"},
        {"code": "DUP", "name": "Compatible"},
        {"code": "BAD", "name": "First"},
        {"code": "BAD", "name": "Second"},
    )
    quote_result = parse_eoddata_quote_list(
        b"[]",
        exchange="NYSE",
        effective_date=EFFECTIVE_DATE,
        symbol_list=symbol_list,
    )

    result = quote_result.to_validation_result(symbol_list=symbol_list)

    assert tuple(item.to_dict() for item in result.feed_counts) == (
        {
            "source_code": "eoddata_symbol_list",
            "market": "NYSE",
            "input_rows": 4,
            "accepted_records": 1,
            "rejected_records": 1,
            "duplicate_rows_collapsed": 1,
            "warning_count": 1,
        },
        {
            "source_code": "eoddata_daily",
            "market": "NYSE",
            "input_rows": 0,
            "accepted_records": 0,
            "rejected_records": 0,
            "duplicate_rows_collapsed": 0,
            "warning_count": 1,
        },
    )
    assert result.output.listing_count == 1
    assert result.output.bar_count == 0
    assert result.failures.total_count == 0
    assert len(result.row_rejections) == 1
    rejection = result.row_rejections[0]
    assert rejection.market == "NYSE"
    assert rejection.code == "eoddata_symbol_duplicate_conflict"
    assert rejection.rejected_records == 1
    assert rejection.rejected_rows == 2
    assert rejection.samples[0].record_reference == "NYSE:BAD"
    assert result.warnings.total_count == 2
    assert result.cross_feed_counts is not None
    assert result.cross_feed_counts.to_dict() == {
        "market": "NYSE",
        "listings_without_bars": 1,
        "bars_without_listings": 0,
    }
    assert tuple(issue.code for issue in result.warnings.samples) == (
        "eoddata_symbol_duplicates_collapsed",
        "eoddata_quote_list_empty",
    )


def test_quote_parser_passes_shared_contract_for_all_exchanges() -> None:
    nasdaq_symbols = _symbols(
        "NASDAQ",
        {"code": "EMPA", "name": "Empire Alpha"},
        {"code": "emp.B", "name": "Empire Beta"},
    )
    nyse_symbols = _symbols(
        "NYSE",
        {"code": "EMP.A"},
        {"code": "CLASH"},
    )
    amex_symbols = _symbols("AMEX", {"code": "OVERLAP"})
    cases = (
        (
            "NYSE",
            "nyse_daily_duplicates.json",
            nyse_symbols,
            _output(
                ParsedListingBatch(
                    listing=ProviderListing(
                        provider_code="EODDATA",
                        market="NYSE",
                        ticker="CLASH",
                    ),
                    bars=(),
                ),
                ParsedListingBatch(
                    listing=ProviderListing(
                        provider_code="EODDATA",
                        market="NYSE",
                        ticker="EMP.A",
                    ),
                    bars=(
                        _bar("10.00", "11.00", "9.50", "10.50", "1000"),
                    ),
                ),
            ),
        ),
        (
            "NASDAQ",
            "nasdaq_daily_valid.json",
            nasdaq_symbols,
            _output(
                ParsedListingBatch(
                    listing=ProviderListing(
                        provider_code="EODDATA",
                        market="NASDAQ",
                        ticker="EMPA",
                        name="Empire Alpha",
                    ),
                    bars=(
                        _bar(
                            "10.2500",
                            "10.8750",
                            "10.1250",
                            "10.7500",
                            "125000",
                        ),
                    ),
                ),
                ParsedListingBatch(
                    listing=ProviderListing(
                        provider_code="EODDATA",
                        market="NASDAQ",
                        ticker="emp.B",
                        name="Empire Beta",
                    ),
                    bars=(
                        _bar("27.7900", "27.7900", "27.5900", "27.7096", "0"),
                    ),
                ),
            ),
        ),
        (
            "AMEX",
            "amex_daily_overlap.json",
            amex_symbols,
            _output(
                ParsedListingBatch(
                    listing=ProviderListing(
                        provider_code="EODDATA",
                        market="AMEX",
                        ticker="OVERLAP",
                    ),
                    bars=(
                        _bar("30.00", "31.00", "29.50", "30.50", "3000"),
                    ),
                ),
            ),
        ),
    )

    for exchange, fixture_name, symbol_list, expected in cases:
        assert_parser_contract(
            parse=lambda payload, exchange=exchange, symbol_list=symbol_list: (
                parse_eoddata_quote_list(
                    payload,
                    exchange=exchange,
                    effective_date=EFFECTIVE_DATE,
                    symbol_list=symbol_list,
                ).to_parsed_provider_output()
            ),
            provider_code="EODDATA",
            volume_is_optional=False,
            valid_cases=(
                ValidParserCase(
                    name=f"{exchange} Quote List",
                    payload=_daily_fixture(fixture_name),
                    expected=expected,
                ),
            ),
            invalid_cases=(
                InvalidParserCase(
                    name=f"{exchange} exchange mismatch",
                    payload=json.dumps(
                        [_quote_row(exchange="WRONG")]
                    ).encode("utf-8"),
                ),
            ),
        )
