from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime
from uuid import UUID

import pytest

import empire_stonks_tech_indicators as public_api
from empire_stonks_tech_indicators import (
    BenchmarkConfig,
    ResolvedTechIndicatorsDailyScope,
    SourceReadinessDecision,
    TechIndicatorsDailyScope,
    resolve_tech_indicators_daily_scope,
)
from empire_stonks_tech_indicators import daily_scope as daily_scope_module
from empire_stonks_tech_indicators.queries import EligibleListing


EFFECTIVE_DATE = date(2026, 8, 22)
LISTING_ID = UUID("00000000-0000-4000-8000-000000000001")
OTHER_LISTING_ID = UUID("00000000-0000-4000-8000-000000000002")


class Cursor:
    def execute(self, *_args: object) -> None:
        pass


def _listing(
    identifier: UUID = LISTING_ID,
    *,
    provider_code: str = "EODDATA",
    market: str = "NASDAQ",
    ticker: str = "TEST",
    instrument_type_code: str = "COMMON_STOCK",
) -> EligibleListing:
    return EligibleListing(
        provider_listing_id=identifier,
        provider_code=provider_code,
        market=market,
        ticker=ticker,
        instrument_type_code=instrument_type_code,
        status="ACTIVE",
        first_trading_date=EFFECTIVE_DATE,
        last_trading_date=EFFECTIVE_DATE,
        source_observation_count=1,
    )


def _readiness(
    *,
    selected_listing_count: int = 1,
    reasons: tuple[str, ...] = (),
) -> SourceReadinessDecision:
    return SourceReadinessDecision(
        effective_date=EFFECTIVE_DATE,
        selected_listing_count=selected_listing_count,
        eoddata_listing_count=selected_listing_count,
        stooq_listing_count=0,
        yahoo_listing_count=0,
        effective_date_bar_count=selected_listing_count,
        supported_subject_bar_count=0,
        benchmark_identity_required=False,
        spx_bar_required=False,
        benchmark_provider_listing_id=None,
        benchmark_bar_present=False,
        eoddata_evidence_required=False,
        yahoo_evidence_required=False,
        eoddata_source_run_id=None,
        yahoo_source_run_id=None,
        reasons=reasons,
    )


def _resolve(
    monkeypatch: pytest.MonkeyPatch,
    scope: TechIndicatorsDailyScope,
    *,
    listings: tuple[EligibleListing, ...] = (_listing(),),
    readiness: SourceReadinessDecision | None = None,
) -> ResolvedTechIndicatorsDailyScope:
    observed_scopes: list[object] = []

    def select(*, cursor: object, scope: object) -> tuple[EligibleListing, ...]:
        assert isinstance(cursor, Cursor)
        observed_scopes.append(scope)
        return listings

    def decide(
        *,
        cursor: object,
        scope: object,
        effective_date: date,
        benchmark_config: BenchmarkConfig,
        resolved_listings: tuple[EligibleListing, ...],
    ) -> SourceReadinessDecision:
        assert isinstance(cursor, Cursor)
        assert effective_date == EFFECTIVE_DATE
        assert isinstance(benchmark_config, BenchmarkConfig)
        assert resolved_listings == listings
        observed_scopes.append(scope)
        return readiness or _readiness(
            selected_listing_count=len(listings)
        )

    monkeypatch.setattr(daily_scope_module, "select_eligible_listings", select)
    monkeypatch.setattr(daily_scope_module, "decide_source_readiness", decide)
    resolved = resolve_tech_indicators_daily_scope(
        cursor=Cursor(),
        scope=scope,
        benchmark_config=BenchmarkConfig(),
    )
    assert observed_scopes == [scope.selection_scope, scope.selection_scope]
    return resolved


def test_daily_scope_api_is_explicitly_exported() -> None:
    assert daily_scope_module.__all__ == [
        "TECH_INDICATORS_SCOPED_SUBJECT_PREFIX",
        "TECH_INDICATORS_SCOPE_SCHEMA_VERSION",
        "ResolvedTechIndicatorsDailyScope",
        "TechIndicatorsDailyScope",
        "resolve_tech_indicators_daily_scope",
    ]
    assert public_api.TechIndicatorsDailyScope is TechIndicatorsDailyScope
    assert (
        public_api.ResolvedTechIndicatorsDailyScope
        is ResolvedTechIndicatorsDailyScope
    )
    assert (
        public_api.resolve_tech_indicators_daily_scope
        is resolve_tech_indicators_daily_scope
    )


def test_daily_scope_normalizes_exact_date_selectors_and_modes() -> None:
    scope = TechIndicatorsDailyScope(
        effective_date=EFFECTIVE_DATE,
        provider_codes=("STOOQ", "EODDATA", "STOOQ"),
        markets=("nyse", "NASDAQ", "nyse"),
        dry_run=True,
        force=True,
    )

    assert scope.provider_codes == ("EODDATA", "STOOQ")
    assert scope.markets == ("NASDAQ", "nyse")
    assert scope.is_filtered is True
    assert scope.selection_scope.start_date == EFFECTIVE_DATE
    assert scope.selection_scope.end_date == EFFECTIVE_DATE
    assert scope.selection_scope.include_inactive is False
    assert scope.to_dict() == {
        "effective_date": "2026-08-22",
        "provider_codes": ["EODDATA", "STOOQ"],
        "markets": ["NASDAQ", "nyse"],
        "provider_listing_ids": [],
        "calculation_version": "TECH_INDICATORS_V1",
        "dry_run": True,
        "force": True,
    }
    with pytest.raises(FrozenInstanceError):
        scope.force = False


@pytest.mark.parametrize(
    ("kwargs", "error", "message"),
    [
        ({"effective_date": datetime.now(UTC)}, TypeError, "effective_date"),
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
            {"markets": ("NASDAQ",), "provider_listing_ids": (LISTING_ID,)},
            ValueError,
            "cannot be combined",
        ),
        (
            {"calculation_version": "TECH_INDICATORS_V2"},
            ValueError,
            "TECH_INDICATORS_V1",
        ),
        ({"dry_run": 1}, TypeError, "dry_run"),
        ({"force": 1}, TypeError, "force"),
    ],
)
def test_daily_scope_rejects_ambiguous_or_invalid_inputs(
    kwargs: dict[str, object],
    error: type[Exception],
    message: str,
) -> None:
    values: dict[str, object] = {"effective_date": EFFECTIVE_DATE}
    values.update(kwargs)
    with pytest.raises(error, match=message):
        TechIndicatorsDailyScope(**values)  # type: ignore[arg-type]


def test_unfiltered_resolution_has_exact_canonical_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved = _resolve(
        monkeypatch,
        TechIndicatorsDailyScope(effective_date=EFFECTIVE_DATE),
    )
    expected = (
        b'{"calculation_version":"TECH_INDICATORS_V1","dry_run":false,'
        b'"effective_date":"2026-08-22","end_date":null,'
        b'"include_inactive":false,"provider_listing_ids":['
        b'"00000000-0000-4000-8000-000000000001"],"rebuild":false,'
        b'"scope_schema_version":1,"start_date":null,'
        b'"workflow_kind":"DAILY"}'
    )

    assert resolved.canonical_json == expected
    assert resolved.scope_hash == hashlib.sha256(expected).hexdigest()
    assert resolved.subject_key == "all_series"
    assert resolved.ready is True
    assert resolved.explicit_rebuild_listing_ids == ()
    json.dumps(resolved.to_dict(), allow_nan=False)


def test_scoped_force_is_stable_rebuild_identity_and_report_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scope = TechIndicatorsDailyScope(
        effective_date=EFFECTIVE_DATE,
        provider_listing_ids=(OTHER_LISTING_ID, LISTING_ID, OTHER_LISTING_ID),
        dry_run=True,
        force=True,
    )
    listings = (
        _listing(
            OTHER_LISTING_ID,
            ticker="OTHER",
            instrument_type_code="ETF",
        ),
        _listing(),
    )
    resolved = _resolve(monkeypatch, scope, listings=listings)
    report_scope = resolved.to_report_scope()

    assert resolved.subject_key == f"scope:{resolved.scope_hash}"
    assert len(resolved.subject_key) == 70
    assert str(LISTING_ID) not in resolved.subject_key
    assert resolved.explicit_rebuild_listing_ids == (
        OTHER_LISTING_ID,
        LISTING_ID,
    )
    payload = json.loads(resolved.canonical_json)
    assert payload["rebuild"] is True
    assert payload["dry_run"] is True
    assert "force" not in payload
    assert report_scope.effective_date == EFFECTIVE_DATE
    assert report_scope.start_date is None
    assert report_scope.requested_listing_count == 2
    assert report_scope.resolved_listing_count == 2
    assert report_scope.instrument_type_codes == ("COMMON_STOCK", "ETF")
    assert report_scope.dry_run is True
    assert report_scope.force is True
    assert report_scope.rebuild is True
    assert str(LISTING_ID) not in json.dumps(resolved.to_dict())
    assert resolved.to_dict()["request"]["requested_listing_count"] == 2


def test_force_does_not_bypass_source_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    not_ready = SourceReadinessDecision(
        effective_date=EFFECTIVE_DATE,
        selected_listing_count=0,
        eoddata_listing_count=0,
        stooq_listing_count=0,
        yahoo_listing_count=0,
        effective_date_bar_count=0,
        supported_subject_bar_count=0,
        benchmark_identity_required=False,
        spx_bar_required=False,
        benchmark_provider_listing_id=None,
        benchmark_bar_present=False,
        eoddata_evidence_required=False,
        yahoo_evidence_required=False,
        eoddata_source_run_id=None,
        yahoo_source_run_id=None,
        reasons=("NO_ELIGIBLE_LISTINGS",),
    )
    resolved = _resolve(
        monkeypatch,
        TechIndicatorsDailyScope(
            effective_date=EFFECTIVE_DATE,
            force=True,
        ),
        listings=(),
        readiness=not_ready,
    )

    assert resolved.ready is False
    assert resolved.readiness.reasons == ("NO_ELIGIBLE_LISTINGS",)
    assert resolved.explicit_rebuild_listing_ids == ()


def test_resolved_scope_rejects_tampered_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved = _resolve(
        monkeypatch,
        TechIndicatorsDailyScope(effective_date=EFFECTIVE_DATE),
    )

    with pytest.raises(ValueError, match="scope_hash"):
        ResolvedTechIndicatorsDailyScope(
            request=resolved.request,
            listings=resolved.listings,
            readiness=resolved.readiness,
            canonical_json=resolved.canonical_json,
            scope_hash="0" * 64,
            subject_key=resolved.subject_key,
        )
