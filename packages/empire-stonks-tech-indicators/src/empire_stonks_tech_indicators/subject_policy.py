"""Lightweight P0.5 SPX subject policy shared by planning and calculation."""

from __future__ import annotations

from empire_stonks_tech_indicators.queries import EligibleListing


SPX_SUPPORTED_SUBJECT_MARKETS = {
    "EODDATA": frozenset({"NYSE", "NASDAQ", "AMEX"}),
    "STOOQ": frozenset({"nasdaq", "nyse", "nysemkt"}),
}


def is_spx_supported_subject(subject: EligibleListing) -> bool:
    """Return the P0.5 subject decision for a P0.6-selected listing.

    ``EligibleListing`` is produced only after the P0.6 SQL predicate has
    validated EODData's metadata type. The remaining P0.5 decision is the
    exact provider and market pair; instrument type and ticker are not inferred.
    """

    if not isinstance(subject, EligibleListing):
        raise TypeError("subject must be an EligibleListing.")
    markets = SPX_SUPPORTED_SUBJECT_MARKETS.get(subject.provider_code)
    return markets is not None and subject.market in markets


__all__ = ["SPX_SUPPORTED_SUBJECT_MARKETS", "is_spx_supported_subject"]
