"""Transactional persistence for provider-native listing series."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal
from uuid import UUID

from empire_stonks_ohlcv.exceptions import OHLCVPersistenceError
from empire_stonks_ohlcv.models import (
    UNKNOWN_INSTRUMENT_TYPE_CODE,
    ProviderListing,
)
from empire_stonks_ohlcv.results import PersistenceCounts


ProviderListingOutcome = Literal["inserted", "updated", "unchanged"]
ProviderListingIdentity = tuple[str, str, str]


@dataclass(frozen=True)
class ResolvedProviderListing:
    """One input provider series and its durable database identifier."""

    listing: ProviderListing
    provider_listing_id: UUID
    outcome: ProviderListingOutcome

    def to_dict(self) -> dict[str, Any]:
        return {
            "listing": self.listing.to_dict(),
            "provider_listing_id": str(self.provider_listing_id),
            "outcome": self.outcome,
        }


@dataclass(frozen=True)
class ProviderListingWriteResult:
    """Provider-listing resolution results for one caller-owned transaction."""

    resolved: tuple[ResolvedProviderListing, ...]

    @property
    def inserted(self) -> int:
        return sum(item.outcome == "inserted" for item in self.resolved)

    @property
    def updated(self) -> int:
        return sum(item.outcome == "updated" for item in self.resolved)

    @property
    def unchanged(self) -> int:
        return sum(item.outcome == "unchanged" for item in self.resolved)

    @property
    def counts(self) -> PersistenceCounts:
        """Return listing outcomes; derived maintenance never applies here."""

        return PersistenceCounts(
            inserted=self.inserted,
            updated=self.updated,
            unchanged=self.unchanged,
        )

    def provider_listing_id_for(self, listing: ProviderListing) -> UUID:
        """Return the resolved ID for one input's exact native identity."""

        target = _identity(listing)
        for item in self.resolved:
            if _identity(item.listing) == target:
                return item.provider_listing_id
        raise KeyError(target)

    def to_dict(self) -> dict[str, Any]:
        return {
            "counts": self.counts.to_dict(),
            "resolved": [item.to_dict() for item in self.resolved],
        }


def upsert_provider_listings(
    *,
    cursor: Any,
    listings: Iterable[ProviderListing],
) -> ProviderListingWriteResult:
    """Resolve provider series with idempotent, update-only-when-distinct SQL.

    The caller owns the transaction and must roll it back if this helper raises.
    This helper neither commits nor mutates canonical Stonks tables.
    """

    prepared = tuple(listings)
    _validate_inputs(prepared)
    ordered = tuple(sorted(prepared, key=_identity))
    inserted_ids: dict[ProviderListingIdentity, UUID] = {}
    resolved_ids: dict[ProviderListingIdentity, UUID] = {}

    for listing in ordered:
        identity = _identity(listing)
        cursor.execute(
            """
            INSERT INTO stonks.provider_listing (
                provider_code,
                market,
                ticker,
                name,
                instrument_type_code
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT ON CONSTRAINT uq_provider_listing_identity DO NOTHING
            RETURNING provider_listing_id
            """,
            (
                listing.provider_code,
                listing.market,
                listing.ticker,
                listing.name,
                listing.instrument_type_code,
            ),
        )
        row = cursor.fetchone()
        if row is not None:
            provider_listing_id = row[0]
            inserted_ids[identity] = provider_listing_id
        else:
            cursor.execute(
                """
                SELECT provider_listing_id
                FROM stonks.provider_listing
                WHERE provider_code = %s
                  AND market = %s
                  AND ticker = %s
                """,
                identity,
            )
            existing = cursor.fetchone()
            if existing is None:
                raise OHLCVPersistenceError(
                    "Provider-listing conflict did not return an existing series."
                )
            provider_listing_id = existing[0]
        resolved_ids[identity] = provider_listing_id

    locked_rows = _lock_resolved_listings(
        cursor=cursor,
        provider_listing_ids=resolved_ids.values(),
    )
    resolved: list[ResolvedProviderListing] = []
    for listing in ordered:
        identity = _identity(listing)
        provider_listing_id = resolved_ids[identity]
        stored_name, stored_instrument_type = locked_rows[provider_listing_id]
        if identity in inserted_ids:
            outcome: ProviderListingOutcome = "inserted"
        else:
            new_name = listing.name if listing.name is not None else stored_name
            new_instrument_type = (
                listing.instrument_type_code
                if listing.instrument_type_code != UNKNOWN_INSTRUMENT_TYPE_CODE
                else stored_instrument_type
            )
            if (
                new_name == stored_name
                and new_instrument_type == stored_instrument_type
            ):
                outcome = "unchanged"
            else:
                cursor.execute(
                    """
                    UPDATE stonks.provider_listing
                    SET
                        name = %s,
                        instrument_type_code = %s,
                        updated_at = now()
                    WHERE provider_listing_id = %s
                    """,
                    (new_name, new_instrument_type, provider_listing_id),
                )
                outcome = "updated"
        resolved.append(
            ResolvedProviderListing(
                listing=listing,
                provider_listing_id=provider_listing_id,
                outcome=outcome,
            )
        )

    return ProviderListingWriteResult(resolved=tuple(resolved))


def _lock_resolved_listings(
    *,
    cursor: Any,
    provider_listing_ids: Iterable[UUID],
) -> dict[UUID, tuple[str | None, str]]:
    locked: dict[UUID, tuple[str | None, str]] = {}
    for provider_listing_id in sorted(set(provider_listing_ids), key=str):
        cursor.execute(
            """
            SELECT provider_listing_id, name, instrument_type_code
            FROM stonks.provider_listing
            WHERE provider_listing_id = %s
            FOR UPDATE
            """,
            (provider_listing_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise OHLCVPersistenceError(
                "Resolved provider listing disappeared before it could be locked."
            )
        locked[row[0]] = (row[1], row[2])
    return locked


def _validate_inputs(listings: tuple[ProviderListing, ...]) -> None:
    seen: set[ProviderListingIdentity] = set()
    for listing in listings:
        if not isinstance(listing, ProviderListing):
            raise TypeError("listings must contain only ProviderListing records.")
        identity = _identity(listing)
        if identity in seen:
            raise OHLCVPersistenceError(
                "Duplicate provider-listing identity in one writer call: "
                f"{identity!r}."
            )
        seen.add(identity)


def _identity(listing: ProviderListing) -> ProviderListingIdentity:
    return (listing.provider_code, listing.market, listing.ticker)
