from __future__ import annotations

from datetime import date, time
from uuid import UUID

import pytest

import empire_stonks_ohlcv.eoddata_policies as eoddata_policies
from empire_stonks_ohlcv import (
    EODDATA_EXCHANGE_POLICY_CODES,
    EODDataExchangeSessionPolicy,
    EligibilityRule,
    MarketSessionService,
    OHLCVConfigError,
    ProviderListing,
    ProviderListingWriteResult,
    ResolvedProviderListing,
    SessionDateRule,
    SessionPolicy,
    resolve_eoddata_exchange_policies,
    upsert_eoddata_provider_listings,
)


POLICY_ROWS = [
    (
        "ED_XNAS_1900_60M",
        "NASDAQ",
        "America/New_York",
        "LOCAL_CUTOFF",
        time(19),
        60,
        "PROVIDER_LOCAL_DATE",
    ),
    (
        "ED_XNYS_1900_60M",
        "XNYS",
        "America/New_York",
        "LOCAL_CUTOFF",
        time(19),
        60,
        "PROVIDER_LOCAL_DATE",
    ),
]


class PolicyCursor:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.rows = rows
        self.params: tuple[object, ...] = ()

    def execute(self, _query: str, params: tuple[object, ...]) -> None:
        self.params = params

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.rows


class AssignmentCursor:
    def __init__(self, *, policy_code: str | None, status: str) -> None:
        self.policy_code = policy_code
        self.status = status
        self.updated: list[tuple[object, ...]] = []
        self._result: tuple[object, ...] | None = None

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        if "SELECT session_policy_code, status" in query:
            self._result = (self.policy_code, self.status)
            return
        if "SET session_policy_code" in query:
            self.policy_code = str(params[0])
            self.updated.append(params)
            self._result = None
            return
        raise AssertionError(f"Unexpected SQL: {query}")

    def fetchone(self) -> tuple[object, ...] | None:
        return self._result


def _policy(exchange: str) -> EODDataExchangeSessionPolicy:
    cursor = PolicyCursor(POLICY_ROWS)
    return next(
        item
        for item in resolve_eoddata_exchange_policies(cursor=cursor)
        if item.exchange == exchange
    )


def _listing_result(
    listing: ProviderListing,
    *,
    outcome: str,
    status: str = "ACTIVE",
) -> ProviderListingWriteResult:
    return ProviderListingWriteResult(
        resolved=(
            ResolvedProviderListing(
                listing=listing,
                provider_listing_id=UUID(int=1),
                outcome=outcome,  # type: ignore[arg-type]
                status=status,  # type: ignore[arg-type]
            ),
        )
    )


def test_resolves_all_configured_exchanges_in_configured_order() -> None:
    cursor = PolicyCursor(list(reversed(POLICY_ROWS)))

    result = resolve_eoddata_exchange_policies(cursor=cursor)

    assert tuple(item.exchange for item in result) == (
        "NYSE",
        "NASDAQ",
        "AMEX",
    )
    assert tuple(
        (item.exchange, item.policy.code) for item in result
    ) == EODDATA_EXCHANGE_POLICY_CODES
    assert cursor.params == (
        ["ED_XNYS_1900_60M", "ED_XNAS_1900_60M"],
    )


@pytest.mark.parametrize(
    "rows, message",
    [
        (POLICY_ROWS[:1], "complete"),
        (POLICY_ROWS + [POLICY_ROWS[0]], "reviewed contract"),
        (
            [
                POLICY_ROWS[0],
                (
                    "ED_XNYS_1900_60M",
                    "XNYS",
                    "America/Chicago",
                    "LOCAL_CUTOFF",
                    time(19),
                    60,
                    "PROVIDER_LOCAL_DATE",
                ),
            ],
            "reviewed contract",
        ),
    ],
)
def test_rejects_missing_duplicate_or_drifted_policy_rows(
    rows: list[tuple[object, ...]],
    message: str,
) -> None:
    with pytest.raises(OHLCVConfigError, match=message):
        resolve_eoddata_exchange_policies(cursor=PolicyCursor(rows))


def test_unknown_exchange_fails_closed_without_querying() -> None:
    cursor = PolicyCursor(POLICY_ROWS)

    with pytest.raises(OHLCVConfigError, match="reviewed"):
        resolve_eoddata_exchange_policies(
            cursor=cursor,
            exchanges=("OTC",),
        )

    assert cursor.params == ()


def test_calendar_policies_cover_dst_holiday_and_early_close() -> None:
    service = MarketSessionService()
    for resolved in resolve_eoddata_exchange_policies(
        cursor=PolicyCursor(POLICY_ROWS)
    ):
        dst = service.expected_sessions(
            policy=resolved.policy,
            start_date=date(2026, 3, 6),
            end_date=date(2026, 3, 9),
        )
        assert tuple(
            (item.session_date, item.eligible_at.isoformat()) for item in dst
        ) == (
            (date(2026, 3, 6), "2026-03-07T01:00:00+00:00"),
            (date(2026, 3, 9), "2026-03-10T00:00:00+00:00"),
        )
        holiday = service.expected_sessions(
            policy=resolved.policy,
            start_date=date(2026, 11, 26),
            end_date=date(2026, 11, 27),
        )
        assert tuple(item.session_date for item in holiday) == (
            date(2026, 11, 27),
        )
        assert holiday[0].eligible_at.isoformat() == (
            "2026-11-28T01:00:00+00:00"
        )


def test_new_listing_receives_policy_and_existing_inactive_listing_keeps_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listing = ProviderListing("EODDATA", "NYSE", "POLICY.TEST")
    inserted = _listing_result(listing, outcome="inserted")
    monkeypatch.setattr(
        eoddata_policies,
        "upsert_provider_listings",
        lambda **_values: inserted,
    )
    cursor = AssignmentCursor(policy_code=None, status="ACTIVE")

    result = upsert_eoddata_provider_listings(
        cursor=cursor,
        listings=(listing,),
        exchange_policy=_policy("NYSE"),
    )

    assert result is inserted
    assert cursor.policy_code == "ED_XNYS_1900_60M"
    assert len(cursor.updated) == 1

    inactive = _listing_result(
        listing,
        outcome="unchanged",
        status="INACTIVE",
    )
    monkeypatch.setattr(
        eoddata_policies,
        "upsert_provider_listings",
        lambda **_values: inactive,
    )
    cursor.status = "INACTIVE"

    rerun = upsert_eoddata_provider_listings(
        cursor=cursor,
        listings=(listing,),
        exchange_policy=_policy("NYSE"),
    )

    assert rerun.resolved[0].status == "INACTIVE"
    assert len(cursor.updated) == 1


def test_existing_listing_with_missing_or_wrong_policy_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listing = ProviderListing("EODDATA", "NASDAQ", "DRIFT.TEST")
    existing = _listing_result(listing, outcome="unchanged")
    monkeypatch.setattr(
        eoddata_policies,
        "upsert_provider_listings",
        lambda **_values: existing,
    )

    with pytest.raises(OHLCVConfigError, match="invalid session policy"):
        upsert_eoddata_provider_listings(
            cursor=AssignmentCursor(
                policy_code="ED_XNYS_1900_60M",
                status="ACTIVE",
            ),
            listings=(listing,),
            exchange_policy=_policy("NASDAQ"),
        )


def test_listing_cannot_inherit_another_exchange_policy() -> None:
    listing = ProviderListing("EODDATA", "AMEX", "CROSS.TEST")

    with pytest.raises(OHLCVConfigError, match="does not match"):
        upsert_eoddata_provider_listings(
            cursor=AssignmentCursor(policy_code=None, status="ACTIVE"),
            listings=(listing,),
            exchange_policy=_policy("NASDAQ"),
        )


def test_policy_value_contract_is_explicit() -> None:
    policy = _policy("AMEX").policy

    assert policy == SessionPolicy(
        code="ED_XNYS_1900_60M",
        calendar_name="XNYS",
        timezone_name="America/New_York",
        eligibility_rule=EligibilityRule.LOCAL_CUTOFF,
        cutoff_local_time=time(19),
        availability_delay_minutes=60,
        session_date_rule=SessionDateRule.PROVIDER_LOCAL_DATE,
    )
