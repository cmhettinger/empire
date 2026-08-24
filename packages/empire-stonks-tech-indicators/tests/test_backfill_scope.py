from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime
from uuid import UUID

import pytest

import empire_stonks_tech_indicators as public_api
from empire_stonks_tech_indicators import (
    ResolvedTechIndicatorsBackfillScope,
    TechIndicatorsBackfillCursor,
    TechIndicatorsBackfillScope,
    TechIndicatorsValidationError,
    resolve_tech_indicators_backfill_scope,
)
from empire_stonks_tech_indicators import backfill_scope as scope_module
from empire_stonks_tech_indicators.queries import EligibleListing


EFFECTIVE_DATE = date(2026, 8, 24)
START_DATE = date(2025, 1, 1)
END_DATE = date(2026, 8, 23)
LISTING_ID = UUID("00000000-0000-4000-8000-000000000001")
OTHER_LISTING_ID = UUID("00000000-0000-4000-8000-000000000002")


class Cursor:
    def execute(self, *_args: object) -> None:
        pass


def _listing(
    identifier: UUID = LISTING_ID,
    *,
    ticker: str = "AAA",
    status: str = "ACTIVE",
    first_date: date | None = START_DATE,
    last_date: date | None = END_DATE,
    count: int = 10,
) -> EligibleListing:
    return EligibleListing(
        provider_listing_id=identifier,
        provider_code="EODDATA",
        market="NASDAQ",
        ticker=ticker,
        instrument_type_code="COMMON_STOCK",
        status=status,
        first_trading_date=first_date,
        last_trading_date=last_date,
        source_observation_count=count,
    )


def _resolve(
    monkeypatch: pytest.MonkeyPatch,
    scope: TechIndicatorsBackfillScope,
    *,
    listings: tuple[EligibleListing, ...] = (_listing(),),
    resume_exists: bool = True,
) -> ResolvedTechIndicatorsBackfillScope:
    observed: list[object] = []

    def select(*, cursor: object, scope: object) -> tuple[EligibleListing, ...]:
        assert isinstance(cursor, Cursor)
        observed.append(scope)
        return listings

    monkeypatch.setattr(scope_module, "select_eligible_listings", select)
    monkeypatch.setattr(
        scope_module,
        "_resume_source_key_exists",
        lambda *_args: resume_exists,
    )
    resolved = resolve_tech_indicators_backfill_scope(
        cursor=Cursor(),
        scope=scope,
    )
    assert observed == [scope.selection_scope]
    return resolved


def test_backfill_scope_api_is_explicitly_exported() -> None:
    assert scope_module.__all__ == [
        "BACKFILL_CONFIRMATION_MAX_LISTINGS",
        "BACKFILL_CONFIRMATION_MAX_SOURCE_ROWS",
        "ResolvedTechIndicatorsBackfillScope",
        "TechIndicatorsBackfillCursor",
        "TechIndicatorsBackfillScope",
        "resolve_tech_indicators_backfill_scope",
    ]
    assert (
        public_api.ResolvedTechIndicatorsBackfillScope
        is ResolvedTechIndicatorsBackfillScope
    )
    assert public_api.TechIndicatorsBackfillCursor is TechIndicatorsBackfillCursor
    assert public_api.TechIndicatorsBackfillScope is TechIndicatorsBackfillScope
    assert public_api.BACKFILL_CONFIRMATION_MAX_LISTINGS == 100
    assert public_api.BACKFILL_CONFIRMATION_MAX_SOURCE_ROWS == 1_000_000
    assert (
        public_api.resolve_tech_indicators_backfill_scope
        is resolve_tech_indicators_backfill_scope
    )


def test_exact_backfill_normalizes_bounded_inputs_and_resume_cursor() -> None:
    resume = TechIndicatorsBackfillCursor(
        provider_listing_id=LISTING_ID,
        trading_date=date(2026, 1, 2),
        batch_number=3,
    )
    scope = TechIndicatorsBackfillScope(
        effective_date=EFFECTIVE_DATE,
        start_date=START_DATE,
        end_date=END_DATE,
        provider_listing_ids=(OTHER_LISTING_ID, LISTING_ID, OTHER_LISTING_ID),
        batch_size=1_000,
        resume_cursor=resume,
        rebuild=True,
        dry_run=True,
    )

    assert scope.provider_listing_ids == (LISTING_ID, OTHER_LISTING_ID)
    assert scope.is_filtered is True
    assert scope.is_broad_scope is False
    assert scope.selection_scope.start_date == START_DATE
    assert scope.selection_scope.end_date == END_DATE
    assert scope.to_dict()["resume_cursor"] == resume.to_dict()
    assert resume.to_report_cursor().batch_number == 3
    with pytest.raises(FrozenInstanceError):
        scope.rebuild = False


@pytest.mark.parametrize(
    ("args", "error", "message"),
    [
        (("not-a-uuid", END_DATE, 1), TypeError, "UUID"),
        ((LISTING_ID, datetime.now(UTC), 1), TypeError, "date or None"),
        ((LISTING_ID, END_DATE, True), TypeError, "integer"),
        ((LISTING_ID, END_DATE, 0), ValueError, "positive"),
    ],
)
def test_backfill_cursor_rejects_invalid_boundaries(
    args: tuple[object, object, object],
    error: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error, match=message):
        TechIndicatorsBackfillCursor(*args)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("kwargs", "error", "message"),
    [
        ({"effective_date": datetime.now(UTC)}, TypeError, "effective_date"),
        ({"start_date": END_DATE, "end_date": START_DATE}, ValueError, "after"),
        (
            {"effective_date": END_DATE, "end_date": EFFECTIVE_DATE},
            ValueError,
            "effective_date",
        ),
        ({"provider_codes": ["EODDATA"]}, TypeError, "tuple"),
        ({"provider_codes": ("eoddata",)}, ValueError, "uppercase"),
        (
            {
                "provider_codes": ("EODDATA",),
                "provider_listing_ids": (LISTING_ID,),
            },
            ValueError,
            "cannot be combined",
        ),
        (
            {"include_inactive": True, "provider_listing_ids": ()},
            ValueError,
            "listing-only",
        ),
        ({"batch_size": 999}, ValueError, "between 1000 and 10000"),
        ({"batch_size": 10_001}, ValueError, "between 1000 and 10000"),
        ({"batch_size": True}, TypeError, "batch_size"),
        ({"resume_cursor": object()}, TypeError, "resume_cursor"),
        (
            {"calculation_version": "TECH_INDICATORS_V2"},
            ValueError,
            "TECH_INDICATORS_V1",
        ),
        ({"rebuild": 1}, TypeError, "rebuild"),
        ({"dry_run": 1}, TypeError, "dry_run"),
        ({"confirm_broad_scope": 1}, TypeError, "confirm_broad_scope"),
    ],
)
def test_backfill_scope_rejects_invalid_inputs(
    kwargs: dict[str, object],
    error: type[Exception],
    message: str,
) -> None:
    values: dict[str, object] = {
        "effective_date": EFFECTIVE_DATE,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "provider_listing_ids": (LISTING_ID,),
    }
    values.update(kwargs)
    with pytest.raises(error, match=message):
        TechIndicatorsBackfillScope(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "selectors",
    [
        {},
        {"provider_codes": ("EODDATA",)},
        {"markets": ("NASDAQ",)},
        {"provider_codes": ("EODDATA",), "markets": ("NASDAQ",)},
    ],
)
def test_every_dimension_or_unfiltered_scope_requires_confirmation(
    selectors: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="confirm_broad_scope=True"):
        TechIndicatorsBackfillScope(
            effective_date=EFFECTIVE_DATE,
            start_date=START_DATE,
            end_date=END_DATE,
            dry_run=True,
            **selectors,  # type: ignore[arg-type]
        )
    confirmed = TechIndicatorsBackfillScope(
        effective_date=EFFECTIVE_DATE,
        start_date=START_DATE,
        end_date=END_DATE,
        confirm_broad_scope=True,
        **selectors,  # type: ignore[arg-type]
    )
    assert confirmed.is_broad_scope is True


def test_more_than_pilot_listing_envelope_requires_confirmation() -> None:
    listing_ids = tuple(UUID(int=value) for value in range(1, 102))
    with pytest.raises(ValueError, match="confirm_broad_scope=True"):
        TechIndicatorsBackfillScope(
            effective_date=EFFECTIVE_DATE,
            start_date=START_DATE,
            end_date=END_DATE,
            provider_listing_ids=listing_ids,
        )


def test_resolved_scope_has_exact_canonical_identity_and_report_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scope = TechIndicatorsBackfillScope(
        effective_date=EFFECTIVE_DATE,
        start_date=START_DATE,
        end_date=END_DATE,
        provider_codes=("EODDATA",),
        markets=("NASDAQ",),
        batch_size=1_000,
        rebuild=True,
        dry_run=True,
        confirm_broad_scope=True,
    )
    listings = (
        _listing(),
        _listing(OTHER_LISTING_ID, ticker="BBB"),
    )
    resolved = _resolve(monkeypatch, scope, listings=listings)
    expected = (
        b'{"calculation_version":"TECH_INDICATORS_V1","dry_run":true,'
        b'"effective_date":null,"end_date":"2026-08-23",'
        b'"include_inactive":false,"provider_listing_ids":['
        b'"00000000-0000-4000-8000-000000000001",'
        b'"00000000-0000-4000-8000-000000000002"],"rebuild":true,'
        b'"scope_schema_version":1,"start_date":"2025-01-01",'
        b'"workflow_kind":"BACKFILL"}'
    )

    assert resolved.canonical_json == expected
    assert resolved.scope_hash == hashlib.sha256(expected).hexdigest()
    assert resolved.subject_key == f"scope:{resolved.scope_hash}"
    assert resolved.explicit_rebuild_listing_ids == (
        LISTING_ID,
        OTHER_LISTING_ID,
    )
    report_scope = resolved.to_report_scope()
    assert report_scope.effective_date is None
    assert report_scope.start_date == START_DATE
    assert report_scope.end_date == END_DATE
    assert report_scope.requested_listing_count == 0
    assert report_scope.resolved_listing_count == 2
    assert report_scope.force is False
    assert report_scope.rebuild is True
    assert str(LISTING_ID) not in json.dumps(resolved.to_dict())


def test_unfiltered_scope_uses_all_series_subject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved = _resolve(
        monkeypatch,
        TechIndicatorsBackfillScope(
            effective_date=EFFECTIVE_DATE,
            start_date=START_DATE,
            end_date=END_DATE,
            confirm_broad_scope=True,
        ),
    )
    assert resolved.subject_key == "all_series"


def test_operational_batch_resume_confirmation_and_effective_date_do_not_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = _resolve(
        monkeypatch,
        TechIndicatorsBackfillScope(
            effective_date=EFFECTIVE_DATE,
            start_date=START_DATE,
            end_date=END_DATE,
            provider_listing_ids=(LISTING_ID,),
            batch_size=1_000,
        ),
    )
    resumed = _resolve(
        monkeypatch,
        TechIndicatorsBackfillScope(
            effective_date=date(2026, 8, 25),
            start_date=START_DATE,
            end_date=END_DATE,
            provider_listing_ids=(LISTING_ID,),
            batch_size=10_000,
            resume_cursor=TechIndicatorsBackfillCursor(
                provider_listing_id=LISTING_ID,
                trading_date=date(2026, 1, 2),
                batch_number=2,
            ),
            confirm_broad_scope=True,
        ),
    )
    assert resumed.canonical_json == original.canonical_json
    assert resumed.scope_hash == original.scope_hash
    assert resumed.resumed_from_cursor is not None


@pytest.mark.parametrize(
    "changes",
    [
        {"rebuild": True},
        {"dry_run": True},
        {"include_inactive": True},
        {"start_date": date(2025, 1, 2)},
    ],
)
def test_material_backfill_scope_changes_hash(
    monkeypatch: pytest.MonkeyPatch,
    changes: dict[str, object],
) -> None:
    values: dict[str, object] = {
        "effective_date": EFFECTIVE_DATE,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "provider_listing_ids": (LISTING_ID,),
    }
    original = _resolve(
        monkeypatch,
        TechIndicatorsBackfillScope(**values),  # type: ignore[arg-type]
    )
    values.update(changes)
    changed = _resolve(
        monkeypatch,
        TechIndicatorsBackfillScope(**values),  # type: ignore[arg-type]
    )
    assert changed.scope_hash != original.scope_hash


def test_resolution_rejects_empty_or_inexact_listing_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scope = TechIndicatorsBackfillScope(
        effective_date=EFFECTIVE_DATE,
        start_date=START_DATE,
        end_date=END_DATE,
        provider_listing_ids=(LISTING_ID, OTHER_LISTING_ID),
    )
    with pytest.raises(TechIndicatorsValidationError, match="ineligible"):
        _resolve(monkeypatch, scope, listings=(_listing(),))
    with pytest.raises(TechIndicatorsValidationError, match="no eligible"):
        _resolve(monkeypatch, scope, listings=())


def test_resolved_row_envelope_requires_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scope = TechIndicatorsBackfillScope(
        effective_date=EFFECTIVE_DATE,
        start_date=START_DATE,
        end_date=END_DATE,
        provider_listing_ids=(LISTING_ID,),
    )
    with pytest.raises(TechIndicatorsValidationError, match="1,000,000-row"):
        _resolve(
            monkeypatch,
            scope,
            listings=(_listing(count=1_000_001),),
        )


@pytest.mark.parametrize(
    ("resume", "listings", "message"),
    [
        (
            TechIndicatorsBackfillCursor(
                OTHER_LISTING_ID,
                date(2026, 1, 2),
                1,
            ),
            (_listing(),),
            "does not belong",
        ),
        (
            TechIndicatorsBackfillCursor(
                LISTING_ID,
                date(2024, 12, 31),
                1,
            ),
            (_listing(),),
            "outside the requested",
        ),
        (
            TechIndicatorsBackfillCursor(LISTING_ID, None, 1),
            (_listing(),),
            "empty listing",
        ),
    ],
)
def test_resolution_rejects_invalid_resume_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    resume: TechIndicatorsBackfillCursor,
    listings: tuple[EligibleListing, ...],
    message: str,
) -> None:
    scope = TechIndicatorsBackfillScope(
        effective_date=EFFECTIVE_DATE,
        start_date=START_DATE,
        end_date=END_DATE,
        provider_listing_ids=(LISTING_ID,),
        resume_cursor=resume,
    )
    with pytest.raises(TechIndicatorsValidationError, match=message):
        _resolve(monkeypatch, scope, listings=listings)


def test_resolution_rejects_resume_cursor_for_deleted_source_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scope = TechIndicatorsBackfillScope(
        effective_date=EFFECTIVE_DATE,
        start_date=START_DATE,
        end_date=END_DATE,
        provider_listing_ids=(LISTING_ID,),
        resume_cursor=TechIndicatorsBackfillCursor(
            LISTING_ID,
            date(2026, 1, 2),
            1,
        ),
    )
    with pytest.raises(TechIndicatorsValidationError, match="current source row"):
        _resolve(monkeypatch, scope, resume_exists=False)


def test_empty_listing_accepts_null_date_resume_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scope = TechIndicatorsBackfillScope(
        effective_date=EFFECTIVE_DATE,
        start_date=START_DATE,
        end_date=END_DATE,
        provider_listing_ids=(LISTING_ID,),
        resume_cursor=TechIndicatorsBackfillCursor(LISTING_ID, None, 1),
    )
    resolved = _resolve(
        monkeypatch,
        scope,
        listings=(
            _listing(first_date=None, last_date=None, count=0),
        ),
    )
    assert resolved.resumed_from_cursor is not None
    assert resolved.resumed_from_cursor.trading_date is None


def test_resolved_scope_rejects_tampered_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved = _resolve(
        monkeypatch,
        TechIndicatorsBackfillScope(
            effective_date=EFFECTIVE_DATE,
            start_date=START_DATE,
            end_date=END_DATE,
            provider_listing_ids=(LISTING_ID,),
        ),
    )
    with pytest.raises(ValueError, match="scope_hash"):
        ResolvedTechIndicatorsBackfillScope(
            request=resolved.request,
            listings=resolved.listings,
            canonical_json=resolved.canonical_json,
            scope_hash="0" * 64,
            subject_key=resolved.subject_key,
        )
