"""Ticker and provider symbol normalization helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


SEC_PROVIDER_CODE = "SEC"


@dataclass(frozen=True)
class NormalizedSymbol:
    """Normalized representation of one provider-observed symbol."""

    raw_symbol: str | None
    display_symbol: str | None
    canonical_symbol: str | None
    provider_symbol: str | None
    provider_code: str
    normalized_symbol: str | None
    notes: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def normalize_sec_ticker(raw_symbol: Any) -> NormalizedSymbol:
    """Normalize a SEC ticker without changing SEC separator semantics.

    Phase 2A SEC normalization is intentionally small and backward-compatible:
    trim surrounding whitespace, uppercase, and preserve internal punctuation.
    """

    if raw_symbol is None:
        return NormalizedSymbol(
            raw_symbol=None,
            display_symbol=None,
            canonical_symbol=None,
            provider_symbol=None,
            provider_code=SEC_PROVIDER_CODE,
            normalized_symbol=None,
            warnings=("SEC ticker is missing.",),
        )

    raw_text = str(raw_symbol)
    normalized = raw_text.strip().upper()
    if not normalized:
        return NormalizedSymbol(
            raw_symbol=raw_text,
            display_symbol=None,
            canonical_symbol=None,
            provider_symbol=None,
            provider_code=SEC_PROVIDER_CODE,
            normalized_symbol=None,
            warnings=("SEC ticker is blank after trimming.",),
        )

    return NormalizedSymbol(
        raw_symbol=raw_text,
        display_symbol=normalized,
        canonical_symbol=normalized,
        provider_symbol=normalized,
        provider_code=SEC_PROVIDER_CODE,
        normalized_symbol=normalized,
    )


def normalize_yahoo_symbol(raw_symbol: Any) -> NormalizedSymbol:
    """Normalize a Yahoo symbol.

    Provider-specific symbol mapping is intentionally deferred to the OHLCV
    provider-symbol reconciliation phase.
    """

    raise NotImplementedError("Yahoo symbol normalization is future provider-mapping work")


def normalize_stooq_symbol(raw_symbol: Any) -> NormalizedSymbol:
    """Normalize a Stooq symbol after provider mapping rules are designed."""

    raise NotImplementedError("Stooq symbol normalization is future provider-mapping work")


def normalize_eoddata_symbol(raw_symbol: Any) -> NormalizedSymbol:
    """Normalize an EODData symbol after provider mapping rules are designed."""

    raise NotImplementedError("EODData symbol normalization is future provider-mapping work")


def normalize_display_symbol(raw_symbol: Any) -> NormalizedSymbol:
    """Normalize a human display symbol after display rules are designed."""

    raise NotImplementedError("Display symbol normalization is future provider-mapping work")
