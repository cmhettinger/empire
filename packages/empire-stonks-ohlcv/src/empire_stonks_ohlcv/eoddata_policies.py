"""Durable EODData exchange session-policy resolution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Any, Iterable

from empire_stonks_ohlcv.config import DEFAULT_EODDATA_EXCHANGES
from empire_stonks_ohlcv.eoddata import EODDATA_PROVIDER_CODE
from empire_stonks_ohlcv.exceptions import (
    OHLCVConfigError,
    OHLCVPersistenceError,
)
from empire_stonks_ohlcv.listings import (
    ProviderListingWriteResult,
    upsert_provider_listings,
)
from empire_stonks_ohlcv.market_sessions import (
    EligibilityRule,
    SessionDateRule,
    SessionPolicy,
)
from empire_stonks_ohlcv.models import ProviderListing


EODDATA_EXCHANGE_POLICY_CODES = (
    ("NYSE", "ED_XNYS_1900_60M"),
    ("NASDAQ", "ED_XNAS_1900_60M"),
    ("AMEX", "ED_XNYS_1900_60M"),
)

_POLICY_CODE_BY_EXCHANGE = dict(EODDATA_EXCHANGE_POLICY_CODES)
_EXPECTED_POLICIES = {
    "ED_XNYS_1900_60M": SessionPolicy(
        code="ED_XNYS_1900_60M",
        calendar_name="XNYS",
        timezone_name="America/New_York",
        eligibility_rule=EligibilityRule.LOCAL_CUTOFF,
        cutoff_local_time=time(19),
        availability_delay_minutes=60,
        session_date_rule=SessionDateRule.PROVIDER_LOCAL_DATE,
    ),
    "ED_XNAS_1900_60M": SessionPolicy(
        code="ED_XNAS_1900_60M",
        calendar_name="NASDAQ",
        timezone_name="America/New_York",
        eligibility_rule=EligibilityRule.LOCAL_CUTOFF,
        cutoff_local_time=time(19),
        availability_delay_minutes=60,
        session_date_rule=SessionDateRule.PROVIDER_LOCAL_DATE,
    ),
}


@dataclass(frozen=True)
class EODDataExchangeSessionPolicy:
    """One configured EODData exchange and its reviewed shared policy."""

    exchange: str
    policy: SessionPolicy

    def __post_init__(self) -> None:
        if self.exchange not in _POLICY_CODE_BY_EXCHANGE:
            raise ValueError("exchange must be a configured EODData exchange.")
        if not isinstance(self.policy, SessionPolicy):
            raise TypeError("policy must be a SessionPolicy.")
        if self.policy.code != _POLICY_CODE_BY_EXCHANGE[self.exchange]:
            raise ValueError("policy does not match the EODData exchange.")


def resolve_eoddata_exchange_policies(
    *,
    cursor: Any,
    exchanges: tuple[str, ...] = DEFAULT_EODDATA_EXCHANGES,
) -> tuple[EODDataExchangeSessionPolicy, ...]:
    """Resolve the exact reviewed policies in configured exchange order."""

    if not callable(getattr(cursor, "execute", None)) or not callable(
        getattr(cursor, "fetchall", None)
    ):
        raise TypeError("cursor must provide execute and fetchall methods.")
    _validate_exchanges(exchanges)
    policy_codes = tuple(
        dict.fromkeys(_POLICY_CODE_BY_EXCHANGE[item] for item in exchanges)
    )
    cursor.execute(
        """
        SELECT
            session_policy_code,
            calendar_name,
            timezone_name,
            eligibility_rule,
            cutoff_local_time,
            availability_delay_minutes,
            session_date_rule
        FROM stonks.ohlcv_session_policy
        WHERE session_policy_code = ANY(%s)
        ORDER BY session_policy_code
        """,
        (list(policy_codes),),
    )
    policies = _policies_by_code(cursor.fetchall())
    if set(policies) != set(policy_codes):
        raise OHLCVConfigError(
            "Configured EODData exchanges do not have complete session policies."
        )
    return tuple(
        EODDataExchangeSessionPolicy(
            exchange=exchange,
            policy=policies[_POLICY_CODE_BY_EXCHANGE[exchange]],
        )
        for exchange in exchanges
    )


def upsert_eoddata_provider_listings(
    *,
    cursor: Any,
    listings: Iterable[ProviderListing],
    exchange_policy: EODDataExchangeSessionPolicy,
) -> ProviderListingWriteResult:
    """Upsert one exchange's listings and bind first-seen rows to its policy."""

    if not isinstance(exchange_policy, EODDataExchangeSessionPolicy):
        raise TypeError(
            "exchange_policy must be an EODDataExchangeSessionPolicy."
        )
    prepared = tuple(listings)
    for listing in prepared:
        if not isinstance(listing, ProviderListing):
            raise TypeError("listings must contain ProviderListing records.")
        if (
            listing.provider_code != EODDATA_PROVIDER_CODE
            or listing.market != exchange_policy.exchange
        ):
            raise OHLCVConfigError(
                "EODData listing does not match its configured exchange policy."
            )

    result = upsert_provider_listings(cursor=cursor, listings=prepared)
    for resolved in result.resolved:
        cursor.execute(
            """
            SELECT session_policy_code, status
            FROM stonks.provider_listing
            WHERE provider_listing_id = %s
              AND provider_code = %s
              AND market = %s
            FOR UPDATE
            """,
            (
                resolved.provider_listing_id,
                EODDATA_PROVIDER_CODE,
                exchange_policy.exchange,
            ),
        )
        row = cursor.fetchone()
        if row is None or row[1] != resolved.status:
            raise OHLCVPersistenceError(
                "Resolved EODData listing policy state is invalid."
            )
        stored_policy_code = row[0]
        expected_policy_code = exchange_policy.policy.code
        if resolved.outcome == "inserted":
            if stored_policy_code is not None:
                raise OHLCVPersistenceError(
                    "New EODData listing has an unexpected session policy."
                )
            cursor.execute(
                """
                UPDATE stonks.provider_listing
                SET session_policy_code = %s
                WHERE provider_listing_id = %s
                """,
                (expected_policy_code, resolved.provider_listing_id),
            )
        elif stored_policy_code != expected_policy_code:
            raise OHLCVConfigError(
                "Existing EODData listing has an invalid session policy."
            )
    return result


def _validate_exchanges(exchanges: object) -> None:
    if not isinstance(exchanges, tuple) or not exchanges:
        raise OHLCVConfigError("EODData exchanges must be a non-empty tuple.")
    if len(exchanges) != len(set(exchanges)):
        raise OHLCVConfigError("EODData exchanges must be unique.")
    if any(item not in _POLICY_CODE_BY_EXCHANGE for item in exchanges):
        raise OHLCVConfigError(
            "EODData exchange does not have a reviewed session policy."
        )


def _policies_by_code(rows: object) -> dict[str, SessionPolicy]:
    if not isinstance(rows, (tuple, list)):
        raise OHLCVConfigError("EODData session policy query returned invalid data.")
    policies: dict[str, SessionPolicy] = {}
    for row in rows:
        if not isinstance(row, (tuple, list)) or len(row) != 7:
            raise OHLCVConfigError(
                "EODData session policy query returned invalid data."
            )
        try:
            policy = SessionPolicy(
                code=row[0],
                calendar_name=row[1],
                timezone_name=row[2],
                eligibility_rule=EligibilityRule(row[3]),
                cutoff_local_time=row[4],
                availability_delay_minutes=row[5],
                session_date_rule=SessionDateRule(row[6]),
            )
        except (TypeError, ValueError) as exc:
            raise OHLCVConfigError(
                "EODData session policy query returned invalid data."
            ) from exc
        if policy.code in policies or policy != _EXPECTED_POLICIES.get(policy.code):
            raise OHLCVConfigError(
                "EODData session policy does not match the reviewed contract."
            )
        policies[policy.code] = policy
    return policies
