from __future__ import annotations

import pytest

from empire_stonks_securities.symbols import (
    NormalizedSymbol,
    normalize_display_symbol,
    normalize_eoddata_symbol,
    normalize_sec_ticker,
    normalize_stooq_symbol,
    normalize_yahoo_symbol,
)


@pytest.mark.parametrize(
    ("raw_symbol", "expected"),
    [
        (" aapl ", "AAPL"),
        ("brk-b", "BRK-B"),
        ("brk.b", "BRK.B"),
        ("bf/b", "BF/B"),
    ],
)
def test_normalize_sec_ticker_preserves_separator_semantics(raw_symbol, expected):
    result = normalize_sec_ticker(raw_symbol)

    assert isinstance(result, NormalizedSymbol)
    assert result.provider_code == "SEC"
    assert result.normalized_symbol == expected
    assert result.display_symbol == expected
    assert result.canonical_symbol == expected
    assert result.provider_symbol == expected
    assert result.warnings == ()


@pytest.mark.parametrize("raw_symbol", ["", "   ", None])
def test_normalize_sec_ticker_handles_empty_input(raw_symbol):
    result = normalize_sec_ticker(raw_symbol)

    assert result.provider_code == "SEC"
    assert result.normalized_symbol is None
    assert result.display_symbol is None
    assert result.canonical_symbol is None
    assert result.provider_symbol is None
    assert result.warnings


@pytest.mark.parametrize(
    "normalizer",
    [
        normalize_yahoo_symbol,
        normalize_stooq_symbol,
        normalize_eoddata_symbol,
        normalize_display_symbol,
    ],
)
def test_future_provider_symbol_normalizers_are_explicitly_deferred(normalizer):
    with pytest.raises(NotImplementedError):
        normalizer("BRK-B")
