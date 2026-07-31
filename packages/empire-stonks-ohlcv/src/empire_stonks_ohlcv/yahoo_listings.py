"""Seeded Yahoo listing and session-policy resolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from empire_stonks_ohlcv.market_sessions import (
    EligibilityRule,
    SessionDateRule,
    SessionPolicy,
)
from empire_stonks_ohlcv.models import ProviderListing
from empire_stonks_ohlcv.yahoo import (
    YAHOO_MARKET,
    YAHOO_PROVIDER_CODE,
    YahooListingTarget,
)


@dataclass(frozen=True)
class SeededYahooListing:
    """One active seed row with its exact acquisition and session contracts."""

    target: YahooListingTarget
    listing: ProviderListing
    policy: SessionPolicy

    def __post_init__(self) -> None:
        if not isinstance(self.target, YahooListingTarget):
            raise TypeError("target must be a YahooListingTarget.")
        if not isinstance(self.listing, ProviderListing):
            raise TypeError("listing must be a ProviderListing.")
        if not isinstance(self.policy, SessionPolicy):
            raise TypeError("policy must be a SessionPolicy.")
        metadata = self.listing.metadata
        if (
            self.listing.provider_code != YAHOO_PROVIDER_CODE
            or self.listing.market != YAHOO_MARKET
            or self.listing.ticker != self.target.ticker
            or not isinstance(metadata, dict)
            or metadata.get("YahooTicker") != self.target.yahoo_ticker
        ):
            raise ValueError(
                "listing must match the exact seeded Yahoo target identity."
            )


def select_active_yahoo_listings(
    *,
    cursor: Any,
) -> tuple[SeededYahooListing, ...]:
    """Return every active seeded Yahoo listing in Empire ticker order."""

    if not callable(getattr(cursor, "execute", None)) or not callable(
        getattr(cursor, "fetchall", None)
    ):
        raise TypeError("cursor must provide execute and fetchall methods.")
    cursor.execute(
        """
        SELECT
            listing.provider_listing_id,
            listing.ticker,
            listing.name,
            listing.instrument_type_code,
            listing.metadata,
            policy.session_policy_code,
            policy.calendar_name,
            policy.timezone_name,
            policy.eligibility_rule,
            policy.cutoff_local_time,
            policy.availability_delay_minutes,
            policy.session_date_rule
        FROM stonks.provider_listing AS listing
        JOIN stonks.ohlcv_session_policy AS policy
          ON policy.session_policy_code = listing.session_policy_code
        WHERE listing.provider_code = %s
          AND listing.market = %s
          AND listing.status = 'ACTIVE'
        ORDER BY listing.ticker, listing.provider_listing_id
        """,
        (YAHOO_PROVIDER_CODE, YAHOO_MARKET),
    )
    rows = cursor.fetchall()
    listings = tuple(_seeded_listing(row) for row in rows)
    tickers = tuple(item.target.ticker for item in listings)
    listing_ids = tuple(
        item.target.provider_listing_id for item in listings
    )
    yahoo_tickers = tuple(item.target.yahoo_ticker for item in listings)
    if tickers != tuple(sorted(tickers)):
        raise ValueError("Yahoo seed query returned unordered tickers.")
    if (
        len(tickers) != len(set(tickers))
        or len(listing_ids) != len(set(listing_ids))
        or len(yahoo_tickers) != len(set(yahoo_tickers))
    ):
        raise ValueError("Active Yahoo seed identities must be unique.")
    return listings


def _seeded_listing(row: object) -> SeededYahooListing:
    if not isinstance(row, (tuple, list)) or len(row) != 12:
        raise ValueError("Yahoo seed query returned an invalid row.")
    (
        provider_listing_id,
        ticker,
        name,
        instrument_type_code,
        metadata,
        policy_code,
        calendar_name,
        timezone_name,
        eligibility_rule,
        cutoff_local_time,
        availability_delay_minutes,
        session_date_rule,
    ) = row
    if not isinstance(metadata, dict):
        raise ValueError("Yahoo seed metadata must be a JSON object.")
    yahoo_ticker = metadata.get("YahooTicker")
    if not isinstance(yahoo_ticker, str):
        raise ValueError("Yahoo seed metadata.YahooTicker must be a string.")
    try:
        policy = SessionPolicy(
            code=policy_code,
            calendar_name=calendar_name,
            timezone_name=timezone_name,
            eligibility_rule=EligibilityRule(eligibility_rule),
            cutoff_local_time=cutoff_local_time,
            availability_delay_minutes=availability_delay_minutes,
            session_date_rule=SessionDateRule(session_date_rule),
        )
        target = YahooListingTarget(
            provider_listing_id=provider_listing_id,
            ticker=ticker,
            yahoo_ticker=yahoo_ticker,
        )
        listing = ProviderListing(
            provider_code=YAHOO_PROVIDER_CODE,
            market=YAHOO_MARKET,
            ticker=ticker,
            name=name,
            instrument_type_code=instrument_type_code,
            metadata=metadata,
        )
        return SeededYahooListing(
            target=target,
            listing=listing,
            policy=policy,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Yahoo seed query returned invalid contract data.") from exc
