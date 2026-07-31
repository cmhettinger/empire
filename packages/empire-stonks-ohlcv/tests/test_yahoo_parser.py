from __future__ import annotations

import json
from datetime import date, time
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from empire_stonks_ohlcv import (
    DailyBar,
    EligibilityRule,
    OHLCVParseError,
    ParsedListingBatch,
    ParsedProviderOutput,
    ProviderListing,
    SessionDateRule,
    SessionPolicy,
    YAHOO_DAILY_SOURCE,
)
from parser_contract import InvalidParserCase, ValidParserCase, assert_parser_contract
from empire_stonks_ohlcv.yahoo import (
    YahooAcquisitionRequest,
    YahooListingTarget,
    YahooRequestMode,
)
from empire_stonks_ohlcv.yahoo_parser import parse_yahoo_chart


FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "yahoo"
    / "yahoo_daily"
    / "spx_chart_daily.json"
)
LISTING_ID = UUID("11111111-2222-4333-8444-555555555555")


def _listing(
    *,
    ticker: str = "SPX",
    yahoo_ticker: str = "^GSPC",
    metadata: dict[str, object] | None = None,
) -> ProviderListing:
    return ProviderListing(
        provider_code="YAHOO",
        market="XIDX",
        ticker=ticker,
        name="S&P 500 Index",
        instrument_type_code="EQUITY_INDEX",
        metadata=(
            {"YahooTicker": yahoo_ticker, "reviewed": True}
            if metadata is None
            else metadata
        ),
    )


def _request(
    *,
    ticker: str = "SPX",
    yahoo_ticker: str = "^GSPC",
    start_date: date = date(2026, 7, 1),
    end_date_exclusive: date = date(2026, 7, 5),
    mode: YahooRequestMode = YahooRequestMode.DAILY,
) -> YahooAcquisitionRequest:
    return YahooAcquisitionRequest(
        listing=YahooListingTarget(
            provider_listing_id=LISTING_ID,
            ticker=ticker,
            yahoo_ticker=yahoo_ticker,
        ),
        start_date=start_date,
        end_date_exclusive=end_date_exclusive,
        mode=mode,
    )


def _calendar_policy() -> SessionPolicy:
    return SessionPolicy(
        code="YAHOO_US_CASH",
        calendar_name="XNYS",
        timezone_name="America/New_York",
        eligibility_rule=EligibilityRule.SESSION_CLOSE,
        cutoff_local_time=None,
        availability_delay_minutes=90,
        session_date_rule=SessionDateRule.CALENDAR_SESSION,
    )


def _observed_policy(
    *,
    code: str = "YAHOO_OBSERVED",
    date_rule: SessionDateRule = SessionDateRule.PROVIDER_LOCAL_DATE,
) -> SessionPolicy:
    return SessionPolicy(
        code=code,
        calendar_name=None,
        timezone_name="America/New_York",
        eligibility_rule=EligibilityRule.LOCAL_CUTOFF,
        cutoff_local_time=time(22),
        availability_delay_minutes=0,
        session_date_rule=date_rule,
    )


def _chart_payload(
    *,
    symbol: str = "^GSPC",
    timezone_name: str = "America/New_York",
    timestamps: list[object] | None = None,
    quote: dict[str, list[object]] | None = None,
    adjusted: list[object] | None | object = (),
    exchange_name: object = "SNP",
) -> bytes:
    timestamp_values = (
        [1782912600] if timestamps is None else timestamps
    )
    quote_values = quote or {
        "open": [10.1250],
        "high": [11.5000],
        "low": [9.7500],
        "close": [11.2500],
        "volume": [None],
    }
    indicators: dict[str, object] = {"quote": [quote_values]}
    if adjusted != ():
        indicators["adjclose"] = [{"adjclose": adjusted}]
    payload = {
        "chart": {
            "result": [
                {
                    "meta": {
                        "symbol": symbol,
                        "exchangeName": exchange_name,
                        "exchangeTimezoneName": timezone_name,
                    },
                    "timestamp": timestamp_values,
                    "indicators": indicators,
                }
            ],
            "error": None,
        }
    }
    return json.dumps(payload, separators=(",", ":")).encode()


def test_fixture_preserves_native_values_filters_plan_and_ignores_events() -> None:
    listing = _listing()

    result = parse_yahoo_chart(
        FIXTURE_PATH.read_bytes(),
        request=_request(),
        listing=listing,
        policy=_calendar_policy(),
        planned_session_dates=(date(2026, 7, 1), date(2026, 7, 2)),
    )

    assert result.response_timezone_name == "America/New_York"
    assert result.exchange_name == "SNP"
    assert result.input_rows == 3
    assert result.accepted_rows == 2
    assert result.unplanned_rows == 1
    assert result.rejected_rows == 1
    assert result.batch.listing is listing
    assert result.batch.bars[0].to_dict() == {
        "trading_date": "2026-07-01",
        "open": "6200.1250",
        "high": "6220.5000",
        "low": "6190.2500",
        "close": "6210.7500",
        "volume": None,
    }
    assert result.batch.bars[1].to_dict() == {
        "trading_date": "2026-07-02",
        "open": "6210.7500",
        "high": "6235.0000",
        "low": "6205.0000",
        "close": "6230.0000",
        "volume": "0",
    }
    assert result.adjusted_close_present
    assert [item.to_dict() for item in result.adjusted_closes] == [
        {
            "trading_date": "2026-07-01",
            "adjusted_close": "6209.5000",
        },
        {
            "trading_date": "2026-07-02",
            "adjusted_close": "6229.2500",
        },
    ]
    assert [item.code for item in result.issues] == [
        "yahoo_unplanned_session"
    ]

    output = result.to_parsed_provider_output()
    assert output.sources == (YAHOO_DAILY_SOURCE,)
    assert output.batches == (result.batch,)
    assert output.bar_count == 2
    assert output.batches[0].bars[0].close == Decimal("6210.7500")
    assert all(
        "adjusted" not in bar.to_dict() for bar in output.batches[0].bars
    )


def test_yahoo_fixture_satisfies_shared_parser_contract() -> None:
    listing = _listing()

    def parse(payload: bytes) -> ParsedProviderOutput:
        return parse_yahoo_chart(
            payload,
            request=_request(),
            listing=listing,
            policy=_calendar_policy(),
            planned_session_dates=(date(2026, 7, 1), date(2026, 7, 2)),
        ).to_parsed_provider_output()

    assert_parser_contract(
        parse=parse,
        provider_code="YAHOO",
        volume_is_optional=True,
        valid_cases=(
            ValidParserCase(
                name="manifested Yahoo Chart daily response",
                payload=FIXTURE_PATH.read_bytes(),
                expected=ParsedProviderOutput(
                    sources=(YAHOO_DAILY_SOURCE,),
                    batches=(
                        ParsedListingBatch(
                            listing=listing,
                            bars=(
                                DailyBar(
                                    trading_date=date(2026, 7, 1),
                                    open=Decimal("6200.1250"),
                                    high=Decimal("6220.5000"),
                                    low=Decimal("6190.2500"),
                                    close=Decimal("6210.7500"),
                                    volume=None,
                                ),
                                DailyBar(
                                    trading_date=date(2026, 7, 2),
                                    open=Decimal("6210.7500"),
                                    high=Decimal("6235.0000"),
                                    low=Decimal("6205.0000"),
                                    close=Decimal("6230.0000"),
                                    volume=Decimal("0"),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
        invalid_cases=(
            InvalidParserCase(
                name="malformed Yahoo Chart response",
                payload=b'{"chart":{"result":[],"error":null}}',
            ),
        ),
    )


def test_futures_provider_date_uses_local_settlement_not_utc_date() -> None:
    request = _request(
        ticker="ES",
        yahoo_ticker="ES=F",
        start_date=date(2026, 7, 6),
        end_date_exclusive=date(2026, 7, 7),
    )
    listing = _listing(ticker="ES", yahoo_ticker="ES=F")
    policy = SessionPolicy(
        code="YAHOO_FUTURES",
        calendar_name="CME_Equity",
        timezone_name="America/New_York",
        eligibility_rule=EligibilityRule.LOCAL_CUTOFF,
        cutoff_local_time=time(22),
        availability_delay_minutes=0,
        session_date_rule=SessionDateRule.PROVIDER_DAILY_SETTLEMENT,
    )

    result = parse_yahoo_chart(
        _chart_payload(
            symbol="ES=F",
            timestamps=[1783389600],
        ),
        request=request,
        listing=listing,
        policy=policy,
        planned_session_dates=(date(2026, 7, 6),),
    )

    assert result.accepted_rows == 1
    assert result.batch.bars[0].trading_date == date(2026, 7, 6)


def test_observed_only_provider_accepts_only_dates_inside_request_window() -> None:
    result = parse_yahoo_chart(
        _chart_payload(
            timestamps=[1782912600, 1783171800],
            quote={
                "open": [10, 20],
                "high": [12, 22],
                "low": [9, 19],
                "close": [11, 21],
                "volume": [None, None],
            },
        ),
        request=_request(
            start_date=date(2026, 7, 1),
            end_date_exclusive=date(2026, 7, 3),
        ),
        listing=_listing(),
        policy=_observed_policy(),
        planned_session_dates=None,
    )

    assert [bar.trading_date for bar in result.batch.bars] == [
        date(2026, 7, 1)
    ]
    assert result.unplanned_rows == 1


def test_equal_duplicates_collapse_and_conflicts_reject_independent_of_order() -> None:
    timestamps = [
        1782912600,
        1782912600,
        1782999000,
        1782999000,
    ]
    quote = {
        "open": [10, 10, 20, 20],
        "high": [12, 12, 22, 23],
        "low": [9, 9, 19, 19],
        "close": [11, 11, 21, 21],
        "volume": [None, None, 0, 0],
    }
    adjusted = [10.5, 10.5, 20.5, 20.5]

    first = parse_yahoo_chart(
        _chart_payload(
            timestamps=timestamps,
            quote=quote,
            adjusted=adjusted,
        ),
        request=_request(),
        listing=_listing(),
        policy=_calendar_policy(),
        planned_session_dates=(date(2026, 7, 1), date(2026, 7, 2)),
    )
    second = parse_yahoo_chart(
        _chart_payload(
            timestamps=list(reversed(timestamps)),
            quote={
                key: list(reversed(values)) for key, values in quote.items()
            },
            adjusted=list(reversed(adjusted)),
        ),
        request=_request(),
        listing=_listing(),
        policy=_calendar_policy(),
        planned_session_dates=(date(2026, 7, 1), date(2026, 7, 2)),
    )

    assert first.batch.bars == second.batch.bars
    assert [bar.trading_date for bar in first.batch.bars] == [
        date(2026, 7, 1)
    ]
    assert first.compatible_duplicate_groups == 1
    assert first.collapsed_duplicate_rows == 1
    assert first.conflicting_duplicate_groups == 1
    assert first.conflicting_duplicate_rows == 2
    assert [item.code for item in first.issues] == [
        "yahoo_duplicate_collapsed",
        "yahoo_duplicate_conflict",
    ]
    assert first.to_dict() == second.to_dict()


def test_invalid_ohlcv_rows_are_rejected_without_zero_filling() -> None:
    result = parse_yahoo_chart(
        _chart_payload(
            timestamps=[1782912600, 1782999000, 1783085400],
            quote={
                "open": [10, 20, 30],
                "high": [12, 22, 29],
                "low": [9, 19, 31],
                "close": [None, 21, 30],
                "volume": [100, -1, 10],
            },
        ),
        request=_request(),
        listing=_listing(),
        policy=_calendar_policy(),
        planned_session_dates=(
            date(2026, 7, 1),
            date(2026, 7, 2),
            date(2026, 7, 3),
        ),
    )

    assert result.accepted_rows == 0
    assert result.invalid_rows == 3
    assert result.rejected_rows == 3
    assert [item.code for item in result.issues] == [
        "yahoo_invalid_ohlcv",
        "yahoo_invalid_ohlcv",
        "yahoo_invalid_ohlcv",
    ]


def test_invalid_adjusted_close_is_warned_but_native_close_is_accepted() -> None:
    result = parse_yahoo_chart(
        _chart_payload(adjusted=["not-a-number"]),
        request=_request(),
        listing=_listing(),
        policy=_calendar_policy(),
        planned_session_dates=(date(2026, 7, 1),),
    )

    assert result.accepted_rows == 1
    assert result.batch.bars[0].close == Decimal("11.25")
    assert result.adjusted_closes[0].adjusted_close is None
    assert result.invalid_adjusted_close_rows == 1
    assert result.issues[0].code == "yahoo_invalid_adjusted_close"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"not-json", "invalid JSON"),
        (b"[]", "must be a JSON object"),
        (b'{"wrong":{}}', "invalid response shape"),
        (
            b'{"chart":{"result":null,"error":null}}',
            "invalid response shape",
        ),
        (
            b'{"chart":{"result":[],"error":{"code":"Denied"}}}',
            "invalid response shape",
        ),
        (
            _chart_payload(symbol="^WRONG"),
            "symbol does not match",
        ),
        (
            _chart_payload(timestamps=[]),
            "invalid response shape",
        ),
    ],
)
def test_structural_payload_failures_are_safe(
    payload: bytes,
    message: str,
) -> None:
    with pytest.raises(OHLCVParseError, match=message):
        parse_yahoo_chart(
            payload,
            request=_request(),
            listing=_listing(),
            policy=_calendar_policy(),
            planned_session_dates=(date(2026, 7, 1),),
        )


def test_required_quote_and_adjusted_arrays_must_align() -> None:
    with pytest.raises(OHLCVParseError, match="quote arrays"):
        parse_yahoo_chart(
            _chart_payload(
                timestamps=[1782912600, 1782999000],
                quote={
                    "open": [10],
                    "high": [12, 13],
                    "low": [9, 10],
                    "close": [11, 12],
                    "volume": [None, None],
                },
            ),
            request=_request(),
            listing=_listing(),
            policy=_calendar_policy(),
            planned_session_dates=(date(2026, 7, 1), date(2026, 7, 2)),
        )

    with pytest.raises(OHLCVParseError, match="adjusted-close"):
        parse_yahoo_chart(
            _chart_payload(
                timestamps=[1782912600, 1782999000],
                quote={
                    "open": [10, 11],
                    "high": [12, 13],
                    "low": [9, 10],
                    "close": [11, 12],
                    "volume": [None, None],
                },
                adjusted=[10.5],
            ),
            request=_request(),
            listing=_listing(),
            policy=_calendar_policy(),
            planned_session_dates=(date(2026, 7, 1), date(2026, 7, 2)),
        )


@pytest.mark.parametrize(
    ("timezone_name", "message"),
    [
        ("Europe/London", "does not match"),
        ("Mars/Olympus", "unknown exchange timezone"),
    ],
)
def test_response_timezone_must_match_policy(
    timezone_name: str,
    message: str,
) -> None:
    with pytest.raises(OHLCVParseError, match=message):
        parse_yahoo_chart(
            _chart_payload(timezone_name=timezone_name),
            request=_request(),
            listing=_listing(),
            policy=_calendar_policy(),
            planned_session_dates=(date(2026, 7, 1),),
        )


def test_invalid_timestamp_is_a_bounded_row_rejection() -> None:
    result = parse_yahoo_chart(
        _chart_payload(timestamps=["1782912600"]),
        request=_request(),
        listing=_listing(),
        policy=_calendar_policy(),
        planned_session_dates=(date(2026, 7, 1),),
    )

    assert result.accepted_rows == 0
    assert result.invalid_rows == 1
    assert result.issues[0].code == "yahoo_invalid_timestamp"


def test_seed_identity_and_calendar_plan_are_required() -> None:
    with pytest.raises(ValueError, match="metadata.YahooTicker"):
        parse_yahoo_chart(
            _chart_payload(),
            request=_request(),
            listing=_listing(metadata={"YahooTicker": "^WRONG"}),
            policy=_calendar_policy(),
            planned_session_dates=(date(2026, 7, 1),),
        )
    with pytest.raises(ValueError, match="requires planned_session_dates"):
        parse_yahoo_chart(
            _chart_payload(),
            request=_request(),
            listing=_listing(),
            policy=_calendar_policy(),
            planned_session_dates=None,
        )
    with pytest.raises(ValueError, match="inside the acquisition range"):
        parse_yahoo_chart(
            _chart_payload(),
            request=_request(),
            listing=_listing(),
            policy=_calendar_policy(),
            planned_session_dates=(date(2026, 6, 30),),
        )


def test_nonstandard_json_numeric_constants_are_rejected() -> None:
    payload = _chart_payload().replace(b"11.25", b"NaN")

    with pytest.raises(OHLCVParseError, match="invalid JSON"):
        parse_yahoo_chart(
            payload,
            request=_request(),
            listing=_listing(),
            policy=_calendar_policy(),
            planned_session_dates=(date(2026, 7, 1),),
        )
