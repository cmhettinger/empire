from __future__ import annotations

import json
from pathlib import Path

import pytest

from empire_stonks_ohlcv import (
    EODDATA_SYMBOL_LIST_SOURCE,
    EODDataSymbolListParseResult,
    OHLCVParseError,
    ParsedListingBatch,
    ParsedProviderOutput,
    ProviderListing,
    parse_eoddata_symbol_list,
)
from parser_contract import (
    InvalidParserCase,
    ValidParserCase,
    assert_parser_contract,
)


FIXTURE_DIRECTORY = (
    Path(__file__).parent / "fixtures" / "eoddata" / "eoddata_symbol_list"
)
EXPECTED_ISSUE_SAMPLE_LIMIT = 100


def _fixture(name: str) -> bytes:
    return (FIXTURE_DIRECTORY / name).read_bytes()


def _shared_output(*listings: ProviderListing) -> ParsedProviderOutput:
    return ParsedProviderOutput(
        sources=(EODDATA_SYMBOL_LIST_SOURCE,),
        batches=tuple(
            ParsedListingBatch(listing=listing, bars=()) for listing in listings
        ),
    )


def test_parses_nyse_listing_and_ignores_quote_like_fields() -> None:
    result = parse_eoddata_symbol_list(
        _fixture("nyse_symbols_valid.json"),
        exchange="NYSE",
    )

    assert isinstance(result, EODDataSymbolListParseResult)
    assert result.row_count == 1
    assert result.listings == (
        ProviderListing(
            provider_code="EODDATA",
            market="NYSE",
            ticker="EMP.A",
            name="Empire Alpha",
            instrument_type_code="UNKNOWN",
            metadata={"type": "Equity", "currency": "USD"},
        ),
    )
    assert result.to_parsed_provider_output().bar_count == 0
    assert result.issues == ()


def test_collapses_compatible_and_rejects_conflicting_duplicates() -> None:
    result = parse_eoddata_symbol_list(
        _fixture("nasdaq_symbols_duplicates.json"),
        exchange="NASDAQ",
    )

    assert tuple(listing.ticker for listing in result.listings) == (
        "COMP",
        "MIN.I",
    )
    assert result.listings[0].name == "Compatible Systems"
    assert result.listings[0].metadata == {
        "type": "Equity",
        "currency": "USD",
    }
    assert result.listings[1].name is None
    assert result.listings[1].metadata is None
    assert result.compatible_duplicate_groups == 1
    assert result.collapsed_duplicate_rows == 1
    assert result.conflicting_duplicate_groups == 1
    assert result.rejected_rows == 2
    assert result.issue_count == 1
    assert result.issues[0].to_dict() == {
        "code": "eoddata_symbol_duplicate_conflict",
        "message": (
            "Conflicting duplicate Symbol List fields were rejected: "
            "name,currency."
        ),
        "source_code": "eoddata_symbol_list",
        "record_reference": "NASDAQ:CLASH",
    }


def test_duplicate_resolution_is_independent_of_row_order() -> None:
    rows = json.loads(_fixture("nasdaq_symbols_duplicates.json"))

    forward = parse_eoddata_symbol_list(
        json.dumps(rows).encode("utf-8"),
        exchange="NASDAQ",
    )
    reversed_order = parse_eoddata_symbol_list(
        json.dumps(list(reversed(rows))).encode("utf-8"),
        exchange="NASDAQ",
    )

    assert reversed_order == forward


def test_amex_preserves_identity_and_omits_missing_optional_values() -> None:
    result = parse_eoddata_symbol_list(
        _fixture("amex_symbols_valid.json"),
        exchange="AMEX",
    )

    assert result.listings == (
        ProviderListing(
            provider_code="EODDATA",
            market="AMEX",
            ticker="Same.X",
            metadata={"type": "Fund"},
        ),
    )


def test_same_exact_ticker_remains_distinct_across_exchange_partitions() -> None:
    payload = b'[{"code":"OVERLAP"}]'

    listings = tuple(
        parse_eoddata_symbol_list(payload, exchange=exchange).listings[0]
        for exchange in ("NYSE", "NASDAQ", "AMEX")
    )

    assert tuple(listing.market for listing in listings) == (
        "NYSE",
        "NASDAQ",
        "AMEX",
    )
    assert len(set(listings)) == 3


@pytest.mark.parametrize(
    ("payload", "message"),
    (
        (b"not-json", "payload is invalid JSON"),
        (b"{}", "payload must be a JSON array"),
        (b"[]", "payload must not be empty"),
        (b"[1]", "row 1 must be an object"),
        (b'[{}]', "row 1 has an invalid code"),
        (b'[{"code":" BAD"}]', "row 1 has an invalid code"),
        (b'[{"code":7}]', "row 1 has an invalid code"),
    ),
)
def test_rejects_structurally_invalid_payloads(
    payload: bytes,
    message: str,
) -> None:
    with pytest.raises(OHLCVParseError, match=message):
        parse_eoddata_symbol_list(payload, exchange="NYSE")


def test_rejects_unsupported_exchange_before_parsing() -> None:
    with pytest.raises(ValueError, match="NYSE, NASDAQ, or AMEX"):
        parse_eoddata_symbol_list(b"[]", exchange="OTC")


def test_conflict_issue_samples_are_bounded_and_deterministic() -> None:
    rows = [
        {"code": f"C{group:03d}", "name": name}
        for group in range(EXPECTED_ISSUE_SAMPLE_LIMIT + 1)
        for name in ("One", "Two")
    ]
    payload = json.dumps(rows, sort_keys=True).encode("utf-8")

    first = parse_eoddata_symbol_list(payload, exchange="NYSE")
    second = parse_eoddata_symbol_list(payload, exchange="NYSE")

    assert first == second
    assert first.listings == ()
    assert first.issue_count == EXPECTED_ISSUE_SAMPLE_LIMIT + 1
    assert len(first.issues) == EXPECTED_ISSUE_SAMPLE_LIMIT
    assert first.issues[0].record_reference == "NYSE:C000"
    assert first.issues[-1].record_reference == "NYSE:C099"


def test_symbol_list_parser_passes_shared_contract_for_all_exchanges() -> None:
    cases = (
        (
            "NYSE",
            "nyse_symbols_valid.json",
            _shared_output(
                ProviderListing(
                    provider_code="EODDATA",
                    market="NYSE",
                    ticker="EMP.A",
                    name="Empire Alpha",
                    metadata={"type": "Equity", "currency": "USD"},
                )
            ),
        ),
        (
            "NASDAQ",
            "nasdaq_symbols_duplicates.json",
            _shared_output(
                ProviderListing(
                    provider_code="EODDATA",
                    market="NASDAQ",
                    ticker="COMP",
                    name="Compatible Systems",
                    metadata={"type": "Equity", "currency": "USD"},
                ),
                ProviderListing(
                    provider_code="EODDATA",
                    market="NASDAQ",
                    ticker="MIN.I",
                ),
            ),
        ),
        (
            "AMEX",
            "amex_symbols_valid.json",
            _shared_output(
                ProviderListing(
                    provider_code="EODDATA",
                    market="AMEX",
                    ticker="Same.X",
                    metadata={"type": "Fund"},
                )
            ),
        ),
    )

    for exchange, fixture_name, expected in cases:
        assert_parser_contract(
            parse=lambda payload, exchange=exchange: parse_eoddata_symbol_list(
                payload,
                exchange=exchange,
            ).to_parsed_provider_output(),
            provider_code="EODDATA",
            volume_is_optional=None,
            has_bars=False,
            valid_cases=(
                ValidParserCase(
                    name=f"{exchange} Symbol List",
                    payload=_fixture(fixture_name),
                    expected=expected,
                ),
            ),
            invalid_cases=(
                InvalidParserCase(
                    name=f"{exchange} invalid code",
                    payload=b'[{"code":" BAD"}]',
                ),
            ),
        )
