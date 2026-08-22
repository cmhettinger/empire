#!/usr/bin/env python3
"""Benchmark R8.2 summary aggregates in a disposable PostgreSQL schema."""

from __future__ import annotations

import json
import re
import statistics
from time import perf_counter
from typing import Any
from uuid import uuid4

from empire_core import EmpireDatabase
from empire_stonks_tech_indicators.reporting_queries import (
    _feature_coverage_expressions,
)


LISTING_COUNT = 100
ROWS_PER_LISTING = 10_000
PLAN_RUNS = 5
MAXIMUM_SUMMARY_SECONDS = 30.0
_SCHEMA_PATTERN = re.compile(r"^tech_indicators_r82_[a-f0-9]{12}$")
_ELIGIBLE_SUBJECT = """(
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
)"""


def _qualified(schema: str, relation: str) -> str:
    if not _SCHEMA_PATTERN.fullmatch(schema):
        raise ValueError("unsafe R8.2 benchmark schema name")
    return f'"{schema}"."{relation}"'


def _create_pilot(cursor: Any, *, schema: str) -> dict[str, object]:
    payload = _qualified(schema, "pilot_payload")
    cursor.execute(f'CREATE SCHEMA "{schema}"')
    cursor.execute(
        f"""
        CREATE TABLE {payload} (
            LIKE stonks.ohlcv_daily_tech_indicators_a
                INCLUDING DEFAULTS INCLUDING GENERATED
        )
        """
    )
    started = perf_counter()
    cursor.execute(
        f"""
        WITH selected AS (
            SELECT listing.provider_listing_id
            FROM stonks.provider_listing AS listing
            INNER JOIN stonks.ohlcv_daily AS daily
                USING (provider_listing_id)
            WHERE listing.status = 'ACTIVE'
              AND {_ELIGIBLE_SUBJECT}
            GROUP BY listing.provider_listing_id
            HAVING count(*) >= %s
            ORDER BY count(*) DESC, listing.provider_listing_id
            LIMIT %s
        )
        INSERT INTO {payload} (
            provider_listing_id,
            trading_date,
            history_observation_count,
            calculation_version,
            calculated_at,
            open,
            high,
            low,
            close,
            volume,
            consecutive_up_days,
            consecutive_down_days
        )
        SELECT
            selected.provider_listing_id,
            bars.trading_date,
            bars.history_observation_count,
            'TECH_INDICATORS_V1',
            now(),
            bars.open,
            bars.high,
            bars.low,
            bars.close,
            bars.volume,
            0,
            0
        FROM selected
        CROSS JOIN LATERAL (
            SELECT
                daily.trading_date,
                daily.open,
                daily.high,
                daily.low,
                daily.close,
                daily.volume,
                row_number() OVER (
                    ORDER BY daily.trading_date
                )::integer AS history_observation_count
            FROM stonks.ohlcv_daily AS daily
            WHERE daily.provider_listing_id = selected.provider_listing_id
            ORDER BY daily.trading_date
            LIMIT %s
        ) AS bars
        """,
        (ROWS_PER_LISTING, LISTING_COUNT, ROWS_PER_LISTING),
    )
    cursor.execute(f"ANALYZE {payload}")
    cursor.execute(
        f"SELECT count(*), count(DISTINCT provider_listing_id), max(trading_date) "
        f"FROM {payload}"
    )
    row_count, listing_count, effective_date = cursor.fetchone()
    expected_rows = LISTING_COUNT * ROWS_PER_LISTING
    if row_count != expected_rows or listing_count != LISTING_COUNT:
        raise AssertionError("R8.2 pilot size does not match its contract")
    return {
        "build_seconds": perf_counter() - started,
        "effective_date": effective_date,
        "listing_count": listing_count,
        "row_count": row_count,
    }


def _plan(cursor: Any, sql: str, parameters: tuple[object, ...]) -> dict[str, object]:
    cursor.execute(
        "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql,
        parameters,
    )
    document = cursor.fetchone()[0][0]
    root = document["Plan"]
    nodes: list[str] = []
    sorts: list[dict[str, object]] = []

    def visit(node: dict[str, object]) -> None:
        nodes.append(str(node["Node Type"]))
        if "Sort Method" in node:
            sorts.append(
                {
                    "method": node["Sort Method"],
                    "space_kib": node.get("Sort Space Used", 0),
                    "space_type": node.get("Sort Space Type"),
                }
            )
        for child in node.get("Plans", []):
            visit(child)

    visit(root)
    return {
        "actual_rows": root["Actual Rows"],
        "execution_ms": document["Execution Time"],
        "loops": root["Actual Loops"],
        "node_types": sorted(set(nodes)),
        "planned_rows": root["Plan Rows"],
        "planning_ms": document["Planning Time"],
        "shared_hit_blocks": root.get("Shared Hit Blocks", 0),
        "shared_read_blocks": root.get("Shared Read Blocks", 0),
        "sorts": sorts,
        "temp_read_blocks": root.get("Temp Read Blocks", 0),
        "temp_written_blocks": root.get("Temp Written Blocks", 0),
    }


def _measure(cursor: Any, *, schema: str, effective_date: object) -> dict[str, object]:
    payload = _qualified(schema, "pilot_payload")
    cursor.execute(
        f"SELECT array_agg(DISTINCT provider_listing_id) FROM {payload}"
    )
    supported_identifiers = cursor.fetchone()[0]
    version_sql = f"""
        SELECT
            provider_listing_id,
            calculation_version,
            min(trading_date),
            max(trading_date),
            count(*),
            count(*) FILTER (WHERE trading_date = %s),
            count(*) FILTER (
                WHERE relative_strength_benchmark_provider_listing_id IS NOT NULL
            ),
            count(rel_spx),
            count(rel_spx) FILTER (WHERE trading_date = %s),
            count(*) FILTER (
                WHERE pct_rel_spx_20 IS NOT NULL
                  AND relative_return_spx_20d_pct IS NOT NULL
            ),
            count(pct_rel_spx_50),
            count(*) FILTER (
                WHERE spx_beta_60d IS NOT NULL
                  AND spx_correlation_60d IS NOT NULL
            ),
            count(relative_return_spx_63d_pct),
            count(relative_return_spx_126d_pct),
            count(*) FILTER (
                WHERE relative_return_spx_252d_pct IS NOT NULL
                  AND spx_beta_252d IS NOT NULL
                  AND spx_correlation_252d IS NOT NULL
            )
        FROM {payload}
        WHERE provider_listing_id = ANY(%s::uuid[])
        GROUP BY provider_listing_id, calculation_version
    """
    feature_sql = (
        f"SELECT {', '.join(_feature_coverage_expressions())} FROM {payload} "
        "WHERE provider_listing_id = ANY(%s::uuid[])"
    )
    history_sql = f"""
        SELECT
            history_observation_count,
            count(*),
            count(*) FILTER (WHERE provider_listing_id = ANY(%s::uuid[]))
        FROM {payload}
        WHERE provider_listing_id = ANY(%s::uuid[])
        GROUP BY history_observation_count
    """
    runs: list[dict[str, object]] = []
    for _run in range(PLAN_RUNS):
        version = _plan(
            cursor,
            version_sql,
            (effective_date, effective_date, supported_identifiers),
        )
        history = _plan(
            cursor,
            history_sql,
            (supported_identifiers, supported_identifiers),
        )
        features = _plan(cursor, feature_sql, (supported_identifiers,))
        runs.append(
            {
                "features": features,
                "history": history,
                "total_execution_ms": (
                    float(version["execution_ms"])
                    + float(history["execution_ms"])
                    + float(features["execution_ms"])
                ),
                "versions": version,
            }
        )
    totals = [float(item["total_execution_ms"]) for item in runs]
    if max(totals) > MAXIMUM_SUMMARY_SECONDS * 1_000:
        raise AssertionError("R8.2 summary exceeded the P0.8 maximum")
    return {
        "maximum_total_execution_ms": max(totals),
        "median_total_execution_ms": statistics.median(totals),
        "runs": runs,
    }


def main() -> int:
    schema = f"tech_indicators_r82_{uuid4().hex[:12]}"
    connection = EmpireDatabase.connect_from_env()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT version(), current_setting('shared_buffers'), "
                "current_setting('work_mem'), current_setting('maintenance_work_mem')"
            )
            version, shared_buffers, work_mem, maintenance_work_mem = cursor.fetchone()
            pilot = _create_pilot(cursor, schema=schema)
            connection.commit()
            plans = _measure(
                cursor,
                schema=schema,
                effective_date=pilot["effective_date"],
            )
        print(
            json.dumps(
                {
                    "database": {
                        "maintenance_work_mem": maintenance_work_mem,
                        "postgres_version": version,
                        "shared_buffers": shared_buffers,
                        "work_mem": work_mem,
                    },
                    "gate_seconds": MAXIMUM_SUMMARY_SECONDS,
                    "pilot": pilot,
                    "plans": plans,
                },
                default=str,
                sort_keys=True,
            )
        )
        return 0
    finally:
        connection.rollback()
        if _SCHEMA_PATTERN.fullmatch(schema):
            with connection.cursor() as cursor:
                cursor.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            connection.commit()
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
