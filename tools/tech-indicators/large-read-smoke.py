#!/usr/bin/env python3
"""Verify representative tech-indicator input reads against live PostgreSQL."""

from __future__ import annotations

import json
import platform
import resource
import statistics
import sys
from datetime import date
from time import perf_counter
from typing import Any
from uuid import UUID

import psycopg
from empire_core import EmpireDatabase
from empire_stonks_tech_indicators import (
    BenchmarkConfig,
    TechIndicatorsScope,
    decide_source_readiness,
    iter_source_bar_pages,
    iter_state_comparison_pages,
)


PAGE_SIZE = 10_000
PLAN_RUNS = 5
MINIMUM_REPRESENTATIVE_HISTORY = 8_726
MAXIMUM_SMOKE_SECONDS = 10.0
MAXIMUM_SMOKE_RSS_MIB = 256.0

_ELIGIBLE = """(
    (
        listing.provider_code = 'EODDATA'
        AND listing.market IN ('NYSE', 'NASDAQ', 'AMEX')
        AND jsonb_typeof(listing.metadata) = 'object'
        AND jsonb_typeof(listing.metadata -> 'type') = 'string'
        AND upper(btrim(listing.metadata ->> 'type')) = 'EQUITY'
    )
    OR (
        listing.provider_code = 'STOOQ'
        AND listing.market IN ('nasdaq', 'nyse', 'nysemkt')
    )
    OR (
        listing.provider_code = 'YAHOO'
        AND listing.market = 'XIDX'
        AND listing.ticker = 'SPX'
        AND listing.instrument_type_code = 'EQUITY_INDEX'
        AND jsonb_typeof(listing.metadata) = 'object'
        AND jsonb_typeof(listing.metadata -> 'YahooTicker') = 'string'
        AND listing.metadata ->> 'YahooTicker' = '^GSPC'
    )
)"""


def _peak_rss_mib() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return peak / (1024.0 * 1024.0)
    return peak / 1024.0


def _database_facts(cursor: Any) -> dict[str, object]:
    cursor.execute(
        """
        SELECT
            version(),
            current_setting('shared_buffers'),
            current_setting('work_mem'),
            (SELECT count(*) FROM stonks.ohlcv_daily),
            (SELECT count(*) FROM stonks.provider_listing),
            (SELECT count(*) FROM stonks.ohlcv_daily_tech_indicators)
        """
    )
    row = cursor.fetchone()
    return {
        "ohlcv_row_count": row[3],
        "postgres_version": row[0],
        "provider_listing_count": row[4],
        "published_technical_row_count": row[5],
        "shared_buffers": row[1],
        "work_mem": row[2],
    }


def _representative_listing(cursor: Any) -> tuple[UUID, int, date, date]:
    cursor.execute(
        f"""
        SELECT
            listing.provider_listing_id,
            count(daily.trading_date) AS observation_count,
            min(daily.trading_date),
            max(daily.trading_date)
        FROM stonks.provider_listing AS listing
        JOIN stonks.ohlcv_daily AS daily
          ON daily.provider_listing_id = listing.provider_listing_id
        WHERE listing.status = 'ACTIVE'
          AND {_ELIGIBLE}
        GROUP BY listing.provider_listing_id
        ORDER BY observation_count DESC, listing.provider_listing_id
        LIMIT 1
        """
    )
    row = cursor.fetchone()
    if row is None or row[1] < MINIMUM_REPRESENTATIVE_HISTORY:
        raise AssertionError("live database lacks a representative P99 history")
    return row[0], row[1], row[2], row[3]


def _effective_date(cursor: Any) -> date:
    cursor.execute(
        f"""
        SELECT max(daily.trading_date)
        FROM stonks.ohlcv_daily AS daily
        JOIN stonks.provider_listing AS listing
          ON listing.provider_listing_id = daily.provider_listing_id
        WHERE listing.status = 'ACTIVE'
          AND {_ELIGIBLE}
        """
    )
    value = cursor.fetchone()[0]
    if type(value) is not date:
        raise AssertionError("live database has no eligible effective date")
    return value


def _eligible_listing_ids(cursor: Any) -> list[UUID]:
    cursor.execute(
        f"""
        SELECT listing.provider_listing_id
        FROM stonks.provider_listing AS listing
        WHERE listing.status = 'ACTIVE'
          AND {_ELIGIBLE}
        ORDER BY listing.provider_listing_id
        """
    )
    values = [row[0] for row in cursor.fetchall()]
    if not values:
        raise AssertionError("live database has no eligible listing IDs")
    return values


def _walk_plan(node: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = [node]
    for child in node.get("Plans", []):
        nodes.extend(_walk_plan(child))
    return nodes


def _plan_case(
    cursor: Any,
    *,
    name: str,
    query: str,
    parameters: tuple[object, ...],
    maximum_ms: float,
) -> dict[str, object]:
    runs: list[dict[str, Any]] = []
    for _ in range(PLAN_RUNS):
        cursor.execute(
            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query,
            parameters,
        )
        runs.append(cursor.fetchone()[0][0])

    execution_times = [float(item["Execution Time"]) for item in runs]
    if max(execution_times) > maximum_ms:
        raise AssertionError(f"{name} exceeded its {maximum_ms} ms plan gate")
    final = runs[-1]
    nodes = _walk_plan(final["Plan"])
    temporary_read = sum(int(node.get("Temp Read Blocks", 0)) for node in nodes)
    temporary_written = sum(
        int(node.get("Temp Written Blocks", 0)) for node in nodes
    )
    if temporary_read or temporary_written:
        raise AssertionError(f"{name} used temporary I/O")
    sorts = [
        {
            "method": node.get("Sort Method"),
            "space_kib": node.get("Sort Space Used"),
            "space_type": node.get("Sort Space Type"),
        }
        for node in nodes
        if node.get("Node Type") == "Sort"
    ]
    return {
        "actual_rows": final["Plan"].get("Actual Rows"),
        "execution_ms": execution_times,
        "execution_median_ms": statistics.median(execution_times),
        "execution_maximum_ms": max(execution_times),
        "loops": final["Plan"].get("Actual Loops"),
        "node_types": [node.get("Node Type") for node in nodes],
        "planned_rows": final["Plan"].get("Plan Rows"),
        "planning_ms": [float(item["Planning Time"]) for item in runs],
        "shared_hit_blocks": int(final["Plan"].get("Shared Hit Blocks", 0)),
        "shared_read_blocks": int(final["Plan"].get("Shared Read Blocks", 0)),
        "sorts": sorts,
        "temporary_read_blocks": temporary_read,
        "temporary_written_blocks": temporary_written,
    }


def _query_plans(
    cursor: Any,
    listing_id: UUID,
    eligible_listing_ids: list[UUID],
) -> dict[str, object]:
    listing_history = _plan_case(
        cursor,
        name="exact_listing_history",
        query="""
            SELECT provider_listing_id, trading_date, open, high, low, close, volume
            FROM stonks.ohlcv_daily
            WHERE provider_listing_id = %s
            ORDER BY trading_date
            LIMIT 10000
        """,
        parameters=(listing_id,),
        maximum_ms=500.0,
    )
    if listing_history["sorts"]:
        raise AssertionError("exact listing history used an explicit sort")

    full_scope_page = _plan_case(
        cursor,
        name="full_scope_source_page",
        query="""
            SELECT provider_listing_id, trading_date, open, high, low, close, volume
            FROM stonks.ohlcv_daily
            WHERE provider_listing_id = ANY(%s::uuid[])
            ORDER BY provider_listing_id, trading_date
            LIMIT 50000
        """,
        parameters=(eligible_listing_ids,),
        maximum_ms=5000.0,
    )
    if full_scope_page["sorts"]:
        raise AssertionError("full-scope source page used an explicit sort")

    drift_page = _plan_case(
        cursor,
        name="source_published_drift_page",
        query="""
            SELECT source.provider_listing_id, source.trading_date
            FROM stonks.ohlcv_daily AS source
            LEFT JOIN stonks.ohlcv_daily_tech_indicators AS technical
              USING (provider_listing_id, trading_date)
            ORDER BY source.provider_listing_id, source.trading_date
            LIMIT 50000
        """,
        parameters=(),
        maximum_ms=5000.0,
    )
    return {
        "exact_listing_history": listing_history,
        "full_scope_source_page": full_scope_page,
        "source_published_drift_page": drift_page,
    }


def _exercise_public_reads(
    connection: Any,
    cursor: Any,
    *,
    listing_id: UUID,
    expected_observations: int,
    effective_date: date,
) -> dict[str, object]:
    scope = TechIndicatorsScope(provider_listing_ids=(listing_id,))
    started = perf_counter()
    page_lengths = [
        len(page)
        for page in iter_source_bar_pages(
            cursor=cursor,
            scope=scope,
            page_size=PAGE_SIZE,
        )
    ]
    if sum(page_lengths) != expected_observations:
        raise AssertionError("paged public read did not reconcile source history")
    if not page_lengths or max(page_lengths) > PAGE_SIZE:
        raise AssertionError("public source read exceeded its configured page")

    full_scope_pages = iter_source_bar_pages(
        cursor=cursor,
        scope=TechIndicatorsScope(),
        page_size=PAGE_SIZE,
    )
    full_scope_first_page = next(full_scope_pages)
    full_scope_pages.close()
    if len(full_scope_first_page) != PAGE_SIZE:
        raise AssertionError("full-scope public read did not fill one bounded page")

    state_pages = list(
        iter_state_comparison_pages(
            cursor=cursor,
            scope=scope,
            calculation_version="TECH_INDICATORS_V1",
            page_size=PAGE_SIZE,
        )
    )
    if [len(page) for page in state_pages] != [1]:
        raise AssertionError("state comparison did not return one selected listing")

    readiness = decide_source_readiness(
        cursor=cursor,
        scope=TechIndicatorsScope(
            provider_listing_ids=(listing_id,),
            start_date=effective_date,
            end_date=effective_date,
        ),
        effective_date=effective_date,
        benchmark_config=BenchmarkConfig(),
    )
    elapsed = perf_counter() - started
    if elapsed > MAXIMUM_SMOKE_SECONDS:
        raise AssertionError("public read smoke exceeded ten seconds")
    if connection.info.transaction_status != psycopg.pq.TransactionStatus.INTRANS:
        raise AssertionError("public reads changed caller transaction ownership")
    return {
        "elapsed_seconds": elapsed,
        "full_scope_first_page_length": len(full_scope_first_page),
        "readiness": readiness.to_dict(),
        "source_observation_count": sum(page_lengths),
        "source_page_lengths": page_lengths,
        "state_page_lengths": [len(page) for page in state_pages],
    }


def _exercise_cancellation(connection: Any) -> dict[str, object]:
    connection.rollback()
    with connection.cursor() as cursor:
        cursor.execute("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        cursor.execute("SET LOCAL statement_timeout = '1ms'")
        cancelled = False
        try:
            cursor.execute(
                f"""
                SELECT count(daily.trading_date)
                FROM stonks.provider_listing AS listing
                LEFT JOIN stonks.ohlcv_daily AS daily
                  ON daily.provider_listing_id = listing.provider_listing_id
                WHERE listing.status = 'ACTIVE'
                  AND {_ELIGIBLE}
                """
            )
        except psycopg.errors.QueryCanceled:
            cancelled = True
    if not cancelled:
        raise AssertionError("representative large read was not cancelled")
    if connection.info.transaction_status != psycopg.pq.TransactionStatus.INERROR:
        raise AssertionError("cancelled query did not remain caller-owned")
    connection.rollback()
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        recovered = cursor.fetchone()[0] == 1
    connection.rollback()
    if not recovered:
        raise AssertionError("caller could not recover after cancellation")
    return {"cancelled": cancelled, "caller_rollback_recovered": recovered}


def run() -> dict[str, object]:
    started = perf_counter()
    connection = EmpireDatabase.connect_from_env()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
            )
            database = _database_facts(cursor)
            listing_id, observation_count, first_date, last_date = (
                _representative_listing(cursor)
            )
            effective_date = _effective_date(cursor)
            eligible_listing_ids = _eligible_listing_ids(cursor)
            plans = _query_plans(cursor, listing_id, eligible_listing_ids)
            public_reads = _exercise_public_reads(
                connection,
                cursor,
                listing_id=listing_id,
                expected_observations=observation_count,
                effective_date=effective_date,
            )
        connection.rollback()
        cancellation = _exercise_cancellation(connection)
    finally:
        connection.rollback()
        connection.close()

    peak_rss = _peak_rss_mib()
    if peak_rss > MAXIMUM_SMOKE_RSS_MIB:
        raise AssertionError("large-read smoke exceeded 256 MiB peak RSS")
    return {
        "cancellation": cancellation,
        "database": database,
        "effective_date": effective_date.isoformat(),
        "eligible_listing_count": len(eligible_listing_ids),
        "peak_rss_mib": peak_rss,
        "platform": platform.platform(),
        "plans": plans,
        "public_reads": public_reads,
        "python_version": platform.python_version(),
        "representative_listing": {
            "first_trading_date": first_date.isoformat(),
            "last_trading_date": last_date.isoformat(),
            "observation_count": observation_count,
            "provider_listing_id": str(listing_id),
        },
        "status": "ok",
        "total_elapsed_seconds": perf_counter() - started,
        "transaction": {
            "isolation": "REPEATABLE READ",
            "mode": "READ ONLY",
            "owner": "caller",
        },
    }


def main() -> int:
    json.dump(run(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
