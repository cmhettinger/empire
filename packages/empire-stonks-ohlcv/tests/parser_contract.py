"""Reusable assertions for provider parser implementations."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from empire_stonks_ohlcv import (
    DailyBar,
    OHLCVParseError,
    ParsedListingBatch,
    ParsedProviderOutput,
    ProviderListing,
)


ParseFixture = Callable[[bytes], ParsedProviderOutput]


@dataclass(frozen=True)
class ValidParserCase:
    """One fixture payload and its exact shared-record output."""

    name: str
    payload: bytes
    expected: ParsedProviderOutput


@dataclass(frozen=True)
class InvalidParserCase:
    """One structurally invalid payload that must fail parsing."""

    name: str
    payload: bytes


def assert_parser_contract(
    *,
    parse: ParseFixture,
    provider_code: str,
    volume_is_optional: bool | None,
    valid_cases: tuple[ValidParserCase, ...],
    invalid_cases: tuple[InvalidParserCase, ...],
    has_bars: bool = True,
) -> None:
    """Assert the shared provider parser behavior for supplied cases."""

    assert type(has_bars) is bool
    if has_bars:
        assert type(volume_is_optional) is bool
    else:
        assert volume_is_optional is None
    assert valid_cases, "parser contract requires at least one valid case"
    assert invalid_cases, "parser contract requires at least one invalid case"

    volumes: list[Decimal | None] = []
    for case in valid_cases:
        first = parse(case.payload)
        second = parse(case.payload)

        assert isinstance(first, ParsedProviderOutput), case.name
        assert first == case.expected, case.name
        assert second == first, f"{case.name}: output is not deterministic"
        assert json.dumps(second.to_dict(), sort_keys=True) == json.dumps(
            first.to_dict(),
            sort_keys=True,
        )
        _assert_shared_types(first, provider_code=provider_code, case_name=case.name)
        volumes.extend(
            bar.volume
            for batch in first.batches
            for bar in batch.bars
        )

    if not has_bars:
        assert not volumes, "listing-only parser unexpectedly returned bars"
    elif volume_is_optional:
        assert any(volume is not None for volume in volumes), (
            "parser contract requires a populated-volume case"
        )
        assert any(volume is None for volume in volumes), (
            "optional-volume source requires a volume=None case"
        )
    else:
        assert any(volume is not None for volume in volumes), (
            "parser contract requires a populated-volume case"
        )
        assert all(volume is not None for volume in volumes), (
            "required-volume source returned volume=None"
        )

    for case in invalid_cases:
        messages: list[str] = []
        for _attempt in range(2):
            with pytest.raises(OHLCVParseError) as error:
                parse(case.payload)
            messages.append(str(error.value))
        assert messages[0], f"{case.name}: parse error must have a safe message"
        assert messages[1] == messages[0], (
            f"{case.name}: rejection is not deterministic"
        )


def _assert_shared_types(
    output: ParsedProviderOutput,
    *,
    provider_code: str,
    case_name: str,
) -> None:
    assert output.batches, f"{case_name}: expected at least one listing batch"
    for batch in output.batches:
        assert isinstance(batch, ParsedListingBatch), case_name
        assert isinstance(batch.listing, ProviderListing), case_name
        assert batch.listing.provider_code == provider_code, case_name
        assert batch.listing.market == batch.listing.market.strip(), case_name
        assert batch.listing.ticker == batch.listing.ticker.strip(), case_name
        for bar in batch.bars:
            assert isinstance(bar, DailyBar), case_name
            assert type(bar.trading_date) is date, case_name
            assert type(bar.open) is Decimal, case_name
            assert type(bar.high) is Decimal, case_name
            assert type(bar.low) is Decimal, case_name
            assert type(bar.close) is Decimal, case_name
            assert bar.volume is None or type(bar.volume) is Decimal, case_name
