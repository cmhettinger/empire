from __future__ import annotations

import os

import pytest

from empire_stonks_tech_indicators import (
    BenchmarkConfig,
    TechIndicatorsScope,
    resolve_spx_benchmark,
    select_eligible_listings,
)
from empire_stonks_tech_indicators.inspection import inspect_tech_indicators


EmpireDatabase = pytest.importorskip(
    "empire_core.db.connection",
    reason="Empire Core database runtime is not installed.",
).EmpireDatabase

DATABASE_ENVIRONMENT = (
    "EMPIRE_DB_HOST",
    "EMPIRE_DB_NAME",
    "EMPIRE_DB_USER",
    "EMPIRE_DB_PASSWORD",
)


def test_live_inspection_is_bounded_and_returns_connection_idle() -> None:
    if any(not os.environ.get(name) for name in DATABASE_ENVIRONMENT):
        pytest.skip("Empire database environment is not configured.")
    connection = EmpireDatabase.connect_from_env()
    try:
        cursor = connection.cursor()
        benchmark = resolve_spx_benchmark(
            cursor=cursor,
            config=BenchmarkConfig(),
        )
        listing = select_eligible_listings(
            cursor=cursor,
            scope=TechIndicatorsScope(
                provider_listing_ids=(benchmark.provider_listing_id,)
            ),
        )[0]
        assert listing.last_trading_date is not None
        effective_date = listing.last_trading_date
        connection.rollback()

        result = inspect_tech_indicators(
            connection=connection,
            scope=TechIndicatorsScope(
                provider_listing_ids=(benchmark.provider_listing_id,),
                start_date=effective_date,
                end_date=effective_date,
            ),
            effective_date=effective_date,
            benchmark_config=BenchmarkConfig(),
            sample_limit=1,
            page_size=1000,
        )

        payload = result.to_dict()
        assert result.coverage.selected_listing_count == 1
        assert result.coverage_listing_count == 1
        assert result.freshness_listing_count == 1
        assert result.drift.listing_count == 1
        assert len(payload["coverage_listing_facts"]["samples"]) <= 1
        assert len(payload["freshness"]["samples"]) <= 1
        assert len(payload["drift"]["samples"]) <= 1
        assert "recommendations" in payload["disclosure"]
        assert connection.info.transaction_status.name == "IDLE"
    finally:
        connection.rollback()
        connection.close()
