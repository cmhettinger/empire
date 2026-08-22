from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest

import empire_stonks_tech_indicators as public_api
from empire_stonks_tech_indicators import (
    BenchmarkConfig,
    EligibleListing,
    ListingStateComparison,
    PublishedModelInputSnapshot,
    SourceReadinessDecision,
    TechIndicatorsScope,
    read_published_model_inputs,
    select_published_feature_coverage,
    select_published_feature_freshness,
    select_published_feature_ranking,
)
from empire_stonks_tech_indicators import published_queries as module


LISTING_ID = UUID("81111111-1111-4111-8111-111111111111")
SECOND_ID = UUID("82222222-2222-4222-8222-222222222222")
BENCHMARK_ID = UUID("83333333-3333-4333-8333-333333333333")
PUBLICATION_ID = UUID("84444444-4444-4444-8444-444444444444")
RUN_ID = UUID("85555555-5555-4555-8555-555555555555")
EFFECTIVE_DATE = date(2026, 8, 21)
CALCULATED_AT = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)


class SequencedCursor:
    def __init__(self, responses: list[list[tuple[object, ...]]]) -> None:
        self.responses = responses
        self.executions: list[tuple[str, tuple[object, ...]]] = []
        self.closed = False

    def execute(
        self,
        sql: str,
        parameters: tuple[object, ...] = (),
    ) -> None:
        self.executions.append((sql, parameters))

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.responses.pop(0)

    def close(self) -> None:
        self.closed = True


class FakeConnection:
    def __init__(self, cursor: SequencedCursor) -> None:
        self._cursor = cursor
        self.rollback_count = 0

    def cursor(self) -> SequencedCursor:
        return self._cursor

    def rollback(self) -> None:
        self.rollback_count += 1


def _listing(
    provider_listing_id: UUID = LISTING_ID,
    *,
    provider_code: str = "EODDATA",
    market: str = "NYSE",
    ticker: str = "READY",
    first_date: date | None = EFFECTIVE_DATE,
    last_date: date | None = EFFECTIVE_DATE,
    row_count: int = 1,
) -> EligibleListing:
    return EligibleListing(
        provider_listing_id=provider_listing_id,
        provider_code=provider_code,
        market=market,
        ticker=ticker,
        instrument_type_code="UNKNOWN",
        status="ACTIVE",
        first_trading_date=first_date,
        last_trading_date=last_date,
        source_observation_count=row_count,
    )


def _comparison(**overrides: object) -> ListingStateComparison:
    values: dict[str, object] = {
        "provider_listing_id": LISTING_ID,
        "provider_code": "EODDATA",
        "market": "NYSE",
        "ticker": "READY",
        "first_source_date": EFFECTIVE_DATE,
        "last_source_date": EFFECTIVE_DATE,
        "source_observation_count": 1,
        "last_technical_date": EFFECTIVE_DATE,
        "tail_append_count": 0,
        "missing_tech_row_count": 0,
        "source_copy_drift_count": 0,
        "history_count_drift_count": 0,
        "version_drift_count": 0,
        "earliest_tail_append_date": None,
        "earliest_missing_tech_date": None,
        "earliest_source_copy_drift_date": None,
        "earliest_history_count_drift_date": None,
        "earliest_version_drift_date": None,
    }
    values.update(overrides)
    return ListingStateComparison(**values)  # type: ignore[arg-type]


def _benchmark_listing() -> EligibleListing:
    return _listing(
        BENCHMARK_ID,
        provider_code="YAHOO",
        market="XIDX",
        ticker="SPX",
    )


def _benchmark_comparison() -> ListingStateComparison:
    return _comparison(
        provider_listing_id=BENCHMARK_ID,
        provider_code="YAHOO",
        market="XIDX",
        ticker="SPX",
    )


def _selected_or_benchmark_listings(
    *,
    scope: TechIndicatorsScope,
    **_: object,
) -> tuple[EligibleListing, ...]:
    if scope.provider_listing_ids == (BENCHMARK_ID,):
        return (_benchmark_listing(),)
    return (_listing(),)


def _source_ready() -> SourceReadinessDecision:
    return SourceReadinessDecision(
        effective_date=EFFECTIVE_DATE,
        selected_listing_count=1,
        eoddata_listing_count=1,
        stooq_listing_count=0,
        yahoo_listing_count=0,
        effective_date_bar_count=1,
        supported_subject_bar_count=1,
        benchmark_identity_required=True,
        spx_bar_required=True,
        benchmark_provider_listing_id=BENCHMARK_ID,
        benchmark_bar_present=True,
        eoddata_evidence_required=True,
        yahoo_evidence_required=True,
        eoddata_source_run_id=RUN_ID,
        yahoo_source_run_id=RUN_ID,
        reasons=(),
    )


def _membership_row(
    **overrides: object,
) -> tuple[object, ...]:
    values: list[object] = [
        LISTING_ID,
        PUBLICATION_ID,
        "PRESENT",
        "A",
        "TECH_INDICATORS_V1",
        EFFECTIVE_DATE,
        EFFECTIVE_DATE,
        1,
        1,
        BENCHMARK_ID,
        "PUBLISHED",
        "TECH_INDICATORS_V1",
        True,
        BENCHMARK_ID,
        "TECH_INDICATORS_SPX_V1",
    ]
    positions = {
        "provider_listing_id": 0,
        "publication_id": 1,
        "action": 2,
        "target_slot": 3,
        "calculation_version": 4,
        "source_coverage_start_date": 5,
        "source_coverage_end_date": 6,
        "source_row_count": 7,
        "payload_row_count": 8,
        "benchmark_provider_listing_id": 9,
        "publication_status": 10,
        "publication_calculation_version": 11,
        "benchmark_required": 12,
        "publication_benchmark_provider_listing_id": 13,
        "benchmark_contract_version": 14,
    }
    for name, value in overrides.items():
        values[positions[name]] = value
    return tuple(values)


def test_public_query_api_and_field_inventories_are_explicit() -> None:
    for name in (
        "PublishedFeatureCoverage",
        "PublishedFeatureFreshness",
        "PublishedFeatureRankingRow",
        "PublishedReadinessToken",
        "PublishedModelInputRow",
        "PublishedModelInputSnapshot",
        "select_published_feature_coverage",
        "select_published_feature_freshness",
        "select_published_feature_ranking",
        "read_published_model_inputs",
    ):
        assert name in public_api.__all__
        assert getattr(public_api, name) is not None

    assert "rsi_14" in public_api.PUBLISHED_RANKING_FIELDS
    assert "close" in public_api.PUBLISHED_MODEL_INPUT_FIELDS
    assert "above_sma_200" not in public_api.PUBLISHED_MODEL_INPUT_FIELDS
    assert len(public_api.PUBLISHED_MODEL_INPUT_FIELDS) == 81


def test_coverage_reads_only_the_published_view_and_keeps_missing_listings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listings = (
        _listing(),
        _listing(
            SECOND_ID,
            ticker="MISSING",
            first_date=None,
            last_date=None,
            row_count=0,
        ),
    )
    monkeypatch.setattr(module, "select_eligible_listings", lambda **_: listings)
    cursor = SequencedCursor(
        [
            [
                (
                    LISTING_ID,
                    EFFECTIVE_DATE,
                    EFFECTIVE_DATE,
                    1,
                    CALCULATED_AT,
                    CALCULATED_AT,
                    ["TECH_INDICATORS_V1"],
                    [BENCHMARK_ID],
                )
            ]
        ]
    )

    coverage = select_published_feature_coverage(
        cursor=cursor,
        scope=TechIndicatorsScope(),
    )

    assert len(coverage) == 2
    assert coverage[0].source_and_published_keys_match is True
    assert coverage[0].calculation_versions == ("TECH_INDICATORS_V1",)
    assert coverage[0].benchmark_provider_listing_ids == (BENCHMARK_ID,)
    assert coverage[1].published_row_count == 0
    assert coverage[1].calculation_versions == ()
    sql, parameters = cursor.executions[0]
    assert "FROM stonks.ohlcv_daily_tech_indicators" in sql
    assert "ohlcv_daily_tech_indicators_a" not in sql
    assert parameters == ([LISTING_ID, SECOND_ID],)


@pytest.mark.parametrize(
    "feature_name",
    ("rsi_14; DROP TABLE x", "above_sma_200", "close"),
)
def test_ranking_rejects_non_feature_and_strategy_columns(
    feature_name: str,
) -> None:
    with pytest.raises(ValueError, match="allowlist"):
        select_published_feature_ranking(
            cursor=SequencedCursor([]),
            scope=TechIndicatorsScope(),
            trading_date=EFFECTIVE_DATE,
            feature_name=feature_name,
        )


def test_ranking_uses_a_bounded_date_slice_and_stable_tie_breakers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        module,
        "select_eligible_listings",
        lambda **_: (_listing(),),
    )
    cursor = SequencedCursor(
        [
            [
                (
                    LISTING_ID,
                    "EODDATA",
                    "NYSE",
                    "READY",
                    EFFECTIVE_DATE,
                    61.5,
                )
            ]
        ]
    )

    rows = select_published_feature_ranking(
        cursor=cursor,
        scope=TechIndicatorsScope(),
        trading_date=EFFECTIVE_DATE,
        feature_name="rsi_14",
        limit=250,
    )

    assert rows[0].feature_value == 61.5
    sql, parameters = cursor.executions[0]
    assert "feature.rsi_14 DESC NULLS LAST" in sql
    assert "feature.trading_date = %s" in sql
    assert parameters == ([LISTING_ID], EFFECTIVE_DATE, 250)


def test_freshness_is_as_of_bounded_and_has_no_stale_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listings = (
        _listing(),
        _listing(
            SECOND_ID,
            ticker="NO_DATA",
            first_date=None,
            last_date=None,
            row_count=0,
        ),
    )
    monkeypatch.setattr(module, "select_eligible_listings", lambda **_: listings)
    latest_date = date(2026, 8, 18)
    cursor = SequencedCursor(
        [
            [
                (
                    LISTING_ID,
                    latest_date,
                    CALCULATED_AT,
                    CALCULATED_AT,
                    ["TECH_INDICATORS_V1"],
                    [BENCHMARK_ID],
                )
            ]
        ]
    )

    freshness = select_published_feature_freshness(
        cursor=cursor,
        scope=TechIndicatorsScope(),
        as_of_date=EFFECTIVE_DATE,
    )

    assert freshness[0].calendar_age_days == 3
    assert freshness[0].latest_trading_date == latest_date
    assert freshness[1].calendar_age_days is None
    assert "status" not in freshness[0].to_dict()
    sql, parameters = cursor.executions[0]
    assert "trading_date <= %s" in sql
    assert parameters == ([LISTING_ID, SECOND_ID], EFFECTIVE_DATE)


def test_ready_model_input_snapshot_validates_membership_and_builds_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        module,
        "select_eligible_listings",
        _selected_or_benchmark_listings,
    )
    monkeypatch.setattr(module, "decide_source_readiness", lambda **_: _source_ready())
    monkeypatch.setattr(
        module,
        "iter_state_comparison_pages",
        lambda **_: iter(((_comparison(), _benchmark_comparison()),)),
    )
    cursor = SequencedCursor(
        [
            [(LISTING_ID,)],
            [
                _membership_row(),
                _membership_row(
                    provider_listing_id=BENCHMARK_ID,
                    benchmark_provider_listing_id=None,
                ),
            ],
            [
                (
                    LISTING_ID,
                    EFFECTIVE_DATE,
                    "TECH_INDICATORS_V1",
                    BENCHMARK_ID,
                    Decimal("101.25"),
                    61.5,
                )
            ],
        ]
    )

    snapshot = module._read_model_input_snapshot(
        cursor=cursor,
        scope=TechIndicatorsScope(provider_listing_ids=(LISTING_ID,)),
        effective_date=EFFECTIVE_DATE,
        calculation_version="TECH_INDICATORS_V1",
        benchmark_config=BenchmarkConfig(),
        feature_names=("close", "rsi_14"),
        max_rows=100,
    )

    assert snapshot.ready is True
    assert snapshot.reasons == ()
    assert snapshot.token is not None
    assert snapshot.token.model_row_count == 1
    assert snapshot.rows[0].values == (
        ("close", Decimal("101.25")),
        ("rsi_14", 61.5),
    )
    serialized = snapshot.to_dict()
    assert serialized["rows"][0]["values"]["close"] == "101.25"  # type: ignore[index]


def test_source_drift_fails_closed_before_model_row_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        module,
        "select_eligible_listings",
        _selected_or_benchmark_listings,
    )
    monkeypatch.setattr(module, "decide_source_readiness", lambda **_: _source_ready())
    monkeypatch.setattr(
        module,
        "iter_state_comparison_pages",
        lambda **_: iter(
            (
                (
                    _comparison(
                        source_copy_drift_count=1,
                        earliest_source_copy_drift_date=EFFECTIVE_DATE,
                    ),
                    _benchmark_comparison(),
                ),
            )
        ),
    )
    cursor = SequencedCursor(
        [
            [(LISTING_ID,)],
            [
                _membership_row(),
                _membership_row(
                    provider_listing_id=BENCHMARK_ID,
                    benchmark_provider_listing_id=None,
                ),
            ],
        ]
    )

    snapshot = module._read_model_input_snapshot(
        cursor=cursor,
        scope=TechIndicatorsScope(),
        effective_date=EFFECTIVE_DATE,
        calculation_version="TECH_INDICATORS_V1",
        benchmark_config=BenchmarkConfig(),
        feature_names=("rsi_14",),
        max_rows=100,
    )

    assert snapshot.ready is False
    assert snapshot.reasons == ("SOURCE_DRIFT",)
    assert snapshot.token is None
    assert snapshot.rows == ()
    assert len(cursor.executions) == 2


def test_benchmark_source_drift_has_benchmark_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        module,
        "select_eligible_listings",
        _selected_or_benchmark_listings,
    )
    monkeypatch.setattr(module, "decide_source_readiness", lambda **_: _source_ready())
    benchmark_drift = _comparison(
        provider_listing_id=BENCHMARK_ID,
        provider_code="YAHOO",
        market="XIDX",
        ticker="SPX",
        source_copy_drift_count=1,
        earliest_source_copy_drift_date=EFFECTIVE_DATE,
    )
    monkeypatch.setattr(
        module,
        "iter_state_comparison_pages",
        lambda **_: iter(((_comparison(), benchmark_drift),)),
    )
    cursor = SequencedCursor(
        [
            [(LISTING_ID,)],
            [
                _membership_row(),
                _membership_row(
                    provider_listing_id=BENCHMARK_ID,
                    benchmark_provider_listing_id=None,
                ),
            ],
        ]
    )

    snapshot = module._read_model_input_snapshot(
        cursor=cursor,
        scope=TechIndicatorsScope(),
        effective_date=EFFECTIVE_DATE,
        calculation_version="TECH_INDICATORS_V1",
        benchmark_config=BenchmarkConfig(),
        feature_names=("rsi_14",),
        max_rows=100,
    )

    assert snapshot.reasons == ("BENCHMARK_MISMATCH",)
    assert snapshot.rows == ()


def test_model_input_read_owns_and_releases_repeatable_read_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = PublishedModelInputSnapshot(
        effective_date=EFFECTIVE_DATE,
        calculation_version="TECH_INDICATORS_V1",
        feature_names=("rsi_14",),
        selected_listing_count=0,
        effective_date_source_row_count=0,
        token=None,
        rows=(),
        reasons=("SCOPE_MISMATCH",),
    )
    monkeypatch.setattr(module, "_read_model_input_snapshot", lambda **_: expected)
    cursor = SequencedCursor([])
    connection = FakeConnection(cursor)

    actual = read_published_model_inputs(
        connection=connection,
        scope=TechIndicatorsScope(),
        effective_date=EFFECTIVE_DATE,
        calculation_version="TECH_INDICATORS_V1",
        benchmark_config=BenchmarkConfig(),
        feature_names=("rsi_14",),
    )

    assert actual is expected
    assert cursor.executions == [
        ("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY", ())
    ]
    assert connection.rollback_count == 1
    assert cursor.closed is True


def test_model_input_read_rolls_back_when_snapshot_validation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(**_: object) -> PublishedModelInputSnapshot:
        raise ValueError("invalid database state")

    monkeypatch.setattr(module, "_read_model_input_snapshot", fail)
    cursor = SequencedCursor([])
    connection = FakeConnection(cursor)

    with pytest.raises(ValueError, match="invalid database state"):
        read_published_model_inputs(
            connection=connection,
            scope=TechIndicatorsScope(),
            effective_date=EFFECTIVE_DATE,
            calculation_version="TECH_INDICATORS_V1",
            benchmark_config=BenchmarkConfig(),
            feature_names=("rsi_14",),
        )

    assert connection.rollback_count == 1
    assert cursor.closed is True
