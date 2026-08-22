#!/usr/bin/env python3
"""Benchmark tech-indicator persistence in an isolated PostgreSQL schema."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import re
import resource
import shutil
import statistics
import sys
from dataclasses import replace
from datetime import date, datetime, timezone
from time import perf_counter
from typing import Any, Sequence
from uuid import UUID, uuid4

import numpy
import talib
from empire_core import EmpireDatabase
from empire_stonks_tech_indicators import (
    BenchmarkConfig,
    EligibleListing,
    FeatureRow,
    SourceBar,
    assemble_feature_rows,
    load_spx_benchmark_history,
    normalize_source_bars,
)
from empire_stonks_tech_indicators.persistence import (
    _WRITE_COLUMNS,
    _counts_from_merge_actions,
    _feature_row_arrays,
    _upsert_sql,
)


DEFAULT_PILOT_LISTINGS = 100
DEFAULT_ROWS_PER_LISTING = 10_000
DEFAULT_DAILY_ROWS = 25_000
DEFAULT_BATCH_SIZE = 5_000
DEFAULT_PLAN_RUNS = 5
MAXIMUM_TRANSACTION_SECONDS = 60.0
TARGET_TRANSACTION_SECONDS = 30.0
MAXIMUM_PEAK_RSS_MIB = 2_048.0
MAXIMUM_COMBINED_SLOT_GIB = 40.0
MINIMUM_HEADROOM_GIB = 10.0
_SCHEMA_PATTERN = re.compile(r"^tech_indicators_w79_[a-f0-9]{12}$")

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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the rollback-safe W7.9 persistence benchmark in a disposable "
            "logged schema."
        )
    )
    parser.add_argument(
        "--pilot-listings",
        type=int,
        default=DEFAULT_PILOT_LISTINGS,
    )
    parser.add_argument(
        "--rows-per-listing",
        type=int,
        default=DEFAULT_ROWS_PER_LISTING,
    )
    parser.add_argument("--daily-rows", type=int, default=DEFAULT_DAILY_ROWS)
    parser.add_argument(
        "--airflow-version",
        default=os.environ.get(
            "EMPIRE_STONKS_TECH_INDICATORS_BENCHMARK_AIRFLOW_VERSION"
        ),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
    )
    parser.add_argument("--plan-runs", type=int, default=DEFAULT_PLAN_RUNS)
    return parser.parse_args()


def _validate_args(args: argparse.Namespace) -> None:
    for name in (
        "pilot_listings",
        "rows_per_listing",
        "daily_rows",
        "batch_size",
        "plan_runs",
    ):
        if getattr(args, name) < 1:
            raise ValueError(f"--{name.replace('_', '-')} must be positive")
    if args.pilot_listings > 100:
        raise ValueError("--pilot-listings cannot exceed the P0.8 bound of 100")
    if args.pilot_listings * args.rows_per_listing > 1_000_000:
        raise ValueError("the pilot cannot exceed 1,000,000 rows")
    if not 1_000 <= args.batch_size <= 10_000:
        raise ValueError("--batch-size must be between 1,000 and 10,000")
    if args.daily_rows > 25_000:
        raise ValueError("--daily-rows cannot exceed 25,000")
    if args.plan_runs > 10:
        raise ValueError("--plan-runs cannot exceed 10")


def _peak_rss_mib() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return peak / (1024.0 * 1024.0)
    return peak / 1024.0


def _qualified(schema: str, relation: str) -> str:
    if not _SCHEMA_PATTERN.fullmatch(schema):
        raise ValueError("unsafe benchmark schema name")
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", relation):
        raise ValueError("unsafe benchmark relation name")
    return f'"{schema}"."{relation}"'


def _database_facts(cursor: Any) -> dict[str, object]:
    cursor.execute(
        """
        SELECT
            version(),
            current_setting('shared_buffers'),
            current_setting('work_mem'),
            current_setting('maintenance_work_mem'),
            (SELECT count(*) FROM stonks.ohlcv_daily),
            (SELECT count(*) FROM stonks.provider_listing),
            (SELECT count(*) FROM stonks.ohlcv_daily_tech_indicators),
            pg_current_wal_lsn()
        """
    )
    row = cursor.fetchone()
    return {
        "maintenance_work_mem": row[3],
        "ohlcv_row_count": row[4],
        "postgres_version": row[0],
        "provider_listing_count": row[5],
        "published_technical_row_count": row[6],
        "shared_buffers": row[1],
        "starting_wal_lsn": str(row[7]),
        "work_mem": row[2],
    }


def _select_pilot_listings(
    cursor: Any,
    *,
    listing_count: int,
    rows_per_listing: int,
) -> tuple[tuple[EligibleListing, int], ...]:
    cursor.execute(
        f"""
        WITH coverage AS (
            SELECT
                listing.provider_listing_id,
                listing.provider_code,
                listing.market,
                listing.ticker,
                listing.instrument_type_code,
                listing.status,
                min(daily.trading_date) AS first_trading_date,
                max(daily.trading_date) AS last_trading_date,
                count(*) AS observation_count
            FROM stonks.provider_listing AS listing
            INNER JOIN stonks.ohlcv_daily AS daily
                USING (provider_listing_id)
            WHERE listing.status = 'ACTIVE'
              AND {_ELIGIBLE_SUBJECT}
            GROUP BY listing.provider_listing_id
        )
        SELECT *
        FROM coverage
        WHERE observation_count >= %s
        ORDER BY observation_count DESC, provider_listing_id
        LIMIT %s
        """,
        (rows_per_listing, listing_count),
    )
    rows = cursor.fetchall()
    if len(rows) != listing_count:
        raise AssertionError("database lacks the requested representative histories")
    return tuple(
        (
            EligibleListing(
                provider_listing_id=row[0],
                provider_code=row[1],
                market=row[2],
                ticker=row[3],
                instrument_type_code=row[4],
                status=row[5],
                first_trading_date=row[6],
                last_trading_date=row[7],
                source_observation_count=row[8],
            ),
            row[8],
        )
        for row in rows
    )


def _load_bars(
    cursor: Any,
    *,
    listing: EligibleListing,
    limit: int,
) -> tuple[SourceBar, ...]:
    cursor.execute(
        """
        SELECT provider_listing_id, trading_date, open, high, low, close, volume
        FROM stonks.ohlcv_daily
        WHERE provider_listing_id = %s
        ORDER BY trading_date
        LIMIT %s
        """,
        (listing.provider_listing_id, limit),
    )
    bars = tuple(SourceBar(*row) for row in cursor.fetchall())
    if len(bars) != limit:
        raise AssertionError("pilot history did not satisfy its selected bound")
    return bars


def _bounded_subject(
    listing: EligibleListing,
    bars: tuple[SourceBar, ...],
) -> EligibleListing:
    return replace(
        listing,
        first_trading_date=bars[0].trading_date,
        last_trading_date=bars[-1].trading_date,
        source_observation_count=len(bars),
    )


def _create_payload_clone(cursor: Any, schema: str, relation: str) -> str:
    target = _qualified(schema, relation)
    cursor.execute(
        f"""
        CREATE TABLE {target} (
            LIKE stonks.ohlcv_daily_tech_indicators_a INCLUDING ALL
        )
        """
    )
    return target


def _write_rows(
    connection: Any,
    *,
    target: str,
    rows: Sequence[FeatureRow],
    batch_size: int,
) -> dict[str, object]:
    inserted = 0
    updated = 0
    unchanged = 0
    transaction_seconds: list[float] = []
    statement = _upsert_sql(target)
    for offset in range(0, len(rows), batch_size):
        batch = rows[offset : offset + batch_size]
        started = perf_counter()
        with connection.cursor() as cursor:
            cursor.execute(statement, _feature_row_arrays(batch))
            counts = _counts_from_merge_actions(cursor.fetchall(), len(batch))
        connection.commit()
        elapsed = perf_counter() - started
        if elapsed > MAXIMUM_TRANSACTION_SECONDS:
            raise AssertionError("a write transaction exceeded 60 seconds")
        inserted += counts.inserted_rows
        updated += counts.updated_rows
        unchanged += counts.unchanged_rows
        transaction_seconds.append(elapsed)
    return {
        "batch_count": len(transaction_seconds),
        "batch_size": batch_size,
        "inserted_rows": inserted,
        "maximum_transaction_seconds": max(transaction_seconds, default=0.0),
        "median_transaction_seconds": statistics.median(transaction_seconds),
        "target_transaction_seconds_met": (
            max(transaction_seconds, default=0.0) <= TARGET_TRANSACTION_SECONDS
        ),
        "total_seconds": sum(transaction_seconds),
        "unchanged_rows": unchanged,
        "updated_rows": updated,
    }


def _relation_size(cursor: Any, target: str) -> dict[str, int]:
    cursor.execute(
        """
        SELECT
            pg_relation_size(%s::regclass),
            pg_indexes_size(%s::regclass),
            pg_total_relation_size(%s::regclass)
        """,
        (target, target, target),
    )
    row = cursor.fetchone()
    return {"heap_bytes": row[0], "index_bytes": row[1], "total_bytes": row[2]}


def _wal_lsn(cursor: Any) -> str:
    cursor.execute("SELECT pg_current_wal_lsn()")
    return str(cursor.fetchone()[0])


def _wal_bytes(cursor: Any, start_lsn: str, end_lsn: str) -> int:
    cursor.execute("SELECT pg_wal_lsn_diff(%s, %s)::bigint", (end_lsn, start_lsn))
    return cursor.fetchone()[0]


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
    runs: int,
    median_limit_ms: float,
    maximum_limit_ms: float,
) -> dict[str, object]:
    plans: list[dict[str, Any]] = []
    for _ in range(runs):
        cursor.execute(
            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query,
            parameters,
        )
        plans.append(cursor.fetchone()[0][0])
    execution = [float(plan["Execution Time"]) for plan in plans]
    median = statistics.median(execution)
    maximum = max(execution)
    if median > median_limit_ms or maximum > maximum_limit_ms:
        raise AssertionError(f"{name} exceeded its P0.8 latency gate")
    final = plans[-1]
    nodes = _walk_plan(final["Plan"])
    temporary_read = sum(int(node.get("Temp Read Blocks", 0)) for node in nodes)
    temporary_written = sum(
        int(node.get("Temp Written Blocks", 0)) for node in nodes
    )
    return {
        "actual_rows": final["Plan"].get("Actual Rows"),
        "execution_maximum_ms": maximum,
        "execution_median_ms": median,
        "execution_ms": execution,
        "node_types": [node.get("Node Type") for node in nodes],
        "indexes": sorted(
            {
                node["Index Name"]
                for node in nodes
                if node.get("Index Name") is not None
            }
        ),
        "planned_rows": final["Plan"].get("Plan Rows"),
        "planning_ms": [float(plan["Planning Time"]) for plan in plans],
        "shared_hit_blocks": int(final["Plan"].get("Shared Hit Blocks", 0)),
        "shared_read_blocks": int(final["Plan"].get("Shared Read Blocks", 0)),
        "sorts": [
            {
                "method": node.get("Sort Method"),
                "space_kib": node.get("Sort Space Used"),
                "space_type": node.get("Sort Space Type"),
            }
            for node in nodes
            if node.get("Node Type") == "Sort"
        ],
        "temporary_read_blocks": temporary_read,
        "temporary_written_blocks": temporary_written,
    }


def _create_daily_slice(
    connection: Any,
    *,
    schema: str,
    pilot_target: str,
    row_count: int,
) -> tuple[str, str, date]:
    with connection.cursor() as cursor:
        daily_b = _create_payload_clone(cursor, schema, "daily_b")
        membership = _qualified(schema, "active_membership")
        published = _qualified(schema, "published_payload")
        columns = ", ".join(_WRITE_COLUMNS)
        expressions = ", ".join(
            (
                "md5('w79-daily-' || generated.ordinality::text)::uuid"
                if column == "provider_listing_id"
                else "%s::date"
                if column == "trading_date"
                else "now()"
                if column == "calculated_at"
                else f"seed.{column}"
            )
            for column in _WRITE_COLUMNS
        )
        effective_date = date(2097, 12, 31)
        cursor.execute(
            f"""
            INSERT INTO {pilot_target} ({columns})
            SELECT {expressions}
            FROM (
                SELECT *
                FROM {pilot_target}
                WHERE history_observation_count >= 252
                  AND relative_strength_benchmark_provider_listing_id IS NOT NULL
                ORDER BY provider_listing_id, trading_date DESC
                LIMIT 1
            ) AS seed
            CROSS JOIN generate_series(1, %s) WITH ORDINALITY AS generated
            """,
            (effective_date, row_count),
        )
        cursor.execute(
            f"""
            CREATE TABLE {membership} (
                provider_listing_id UUID PRIMARY KEY,
                target_slot CHAR(1) NOT NULL
            )
            """
        )
        cursor.execute(
            f"""
            INSERT INTO {membership}
            SELECT DISTINCT provider_listing_id, 'A' FROM {pilot_target}
            """
        )
        cursor.execute(
            f"""
            CREATE VIEW {published} AS
            SELECT payload.*
            FROM {pilot_target} AS payload
            INNER JOIN {membership} AS active
                USING (provider_listing_id)
            WHERE active.target_slot = 'A'
            UNION ALL
            SELECT payload.*
            FROM {daily_b} AS payload
            INNER JOIN {membership} AS active
                USING (provider_listing_id)
            WHERE active.target_slot = 'B'
            """
        )
        cursor.execute(f"ANALYZE {pilot_target}")
        cursor.execute(f"ANALYZE {daily_b}")
        cursor.execute(f"ANALYZE {membership}")
    connection.commit()
    return published, pilot_target, effective_date


def _query_plans(
    cursor: Any,
    *,
    pilot_target: str,
    published_target: str,
    representative_listing_id: UUID,
    representative_history_count: int,
    historical_row_count: int,
    effective_date: date,
    runs: int,
) -> dict[str, object]:
    history_page_rows = min(1_000, representative_history_count)
    history_cursor_offset = max(
        0,
        representative_history_count - history_page_rows - 1,
    )
    cursor.execute(
        f"""
        SELECT trading_date
        FROM {pilot_target}
        WHERE provider_listing_id = %s
        ORDER BY trading_date
        OFFSET %s
        LIMIT 1
        """,
        (representative_listing_id, history_cursor_offset),
    )
    history_cursor_date = cursor.fetchone()[0]
    listing_history = _plan_case(
        cursor,
        name="exact_listing_history",
        query=f"""
            SELECT provider_listing_id, trading_date, close, rsi_14
            FROM {pilot_target}
            WHERE provider_listing_id = %s
              AND trading_date > %s
            ORDER BY trading_date
            LIMIT %s
        """,
        parameters=(
            representative_listing_id,
            history_cursor_date,
            history_page_rows,
        ),
        runs=runs,
        median_limit_ms=100.0,
        maximum_limit_ms=500.0,
    )
    listing_history["required_shape_met"] = not listing_history["sorts"] and (
        "Seq Scan" not in listing_history["node_types"]
    )
    latest_slice = _plan_case(
        cursor,
        name="latest_date_slice",
        query=f"""
            SELECT provider_listing_id, trading_date, close, rsi_14
            FROM {published_target}
            WHERE trading_date = %s
        """,
        parameters=(effective_date,),
        runs=runs,
        median_limit_ms=250.0,
        maximum_limit_ms=1_000.0,
    )
    latest_slice["required_shape_met"] = any(
        "trading_date" in index_name
        for index_name in latest_slice["indexes"]
    )
    if historical_row_count >= 100_000 and not latest_slice[
        "required_shape_met"
    ]:
        raise AssertionError("latest-date slice did not use its date-leading index")
    ranking = _plan_case(
        cursor,
        name="latest_date_rank",
        query=f"""
            SELECT provider_listing_id, rsi_14
            FROM {published_target}
            WHERE trading_date = %s
            ORDER BY rsi_14 DESC NULLS LAST, provider_listing_id
            LIMIT 25000
        """,
        parameters=(effective_date,),
        runs=runs,
        median_limit_ms=500.0,
        maximum_limit_ms=2_000.0,
    )
    if ranking["temporary_read_blocks"] or ranking["temporary_written_blocks"]:
        raise AssertionError("latest-date rank spilled to temporary storage")
    coverage = _plan_case(
        cursor,
        name="million_row_coverage",
        query=f"""
            SELECT
                provider_listing_id,
                min(trading_date),
                max(trading_date),
                count(*),
                min(calculation_version),
                max(calculation_version)
            FROM {pilot_target}
            WHERE trading_date <> %s
            GROUP BY provider_listing_id
        """,
        parameters=(effective_date,),
        runs=runs,
        median_limit_ms=10_000.0,
        maximum_limit_ms=30_000.0,
    )
    return {
        "exact_listing_history": listing_history,
        "latest_date_rank": ranking,
        "latest_date_slice": latest_slice,
        "million_row_coverage": coverage,
    }


def _batch_comparison(
    connection: Any,
    *,
    schema: str,
    rows: Sequence[FeatureRow],
) -> dict[str, object]:
    results: dict[str, object] = {}
    for batch_size in (1_000, 5_000, 10_000):
        relation = f"batch_{batch_size}"
        with connection.cursor() as cursor:
            target = _create_payload_clone(cursor, schema, relation)
        connection.commit()
        result = _write_rows(
            connection,
            target=target,
            rows=rows,
            batch_size=batch_size,
        )
        with connection.cursor() as cursor:
            result["relation_size"] = _relation_size(cursor, target)
        results[str(batch_size)] = result
    return results


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def run(args: argparse.Namespace) -> dict[str, object]:
    _validate_args(args)
    started = perf_counter()
    schema = f"tech_indicators_w79_{uuid4().hex[:12]}"
    connection = EmpireDatabase.connect_from_env()
    cleanup_complete = False
    try:
        with connection.cursor() as cursor:
            database = _database_facts(cursor)
            selected = _select_pilot_listings(
                cursor,
                listing_count=args.pilot_listings,
                rows_per_listing=args.rows_per_listing,
            )
            benchmark_history = load_spx_benchmark_history(
                cursor=cursor,
                config=BenchmarkConfig(),
            )
            cursor.execute(f'CREATE SCHEMA "{schema}"')
            pilot_target = _create_payload_clone(cursor, schema, "pilot_payload")
        connection.commit()

        phase_seconds = {"source_read": 0.0, "calculation_validation": 0.0}
        write_seconds = 0.0
        inserted_rows = 0
        transactions: list[float] = []
        sample_rows: list[FeatureRow] = []
        calculated_at = datetime.now(timezone.utc)
        wal_start: str
        with connection.cursor() as cursor:
            wal_start = _wal_lsn(cursor)

        for listing, _observed_count in selected:
            phase_started = perf_counter()
            with connection.cursor() as cursor:
                bars = _load_bars(
                    cursor,
                    listing=listing,
                    limit=args.rows_per_listing,
                )
            connection.rollback()
            phase_seconds["source_read"] += perf_counter() - phase_started

            phase_started = perf_counter()
            rows = assemble_feature_rows(
                normalize_source_bars(bars),
                subject=_bounded_subject(listing, bars),
                calculated_at=calculated_at,
                benchmark_history=benchmark_history,
            )
            phase_seconds["calculation_validation"] += (
                perf_counter() - phase_started
            )
            if len(sample_rows) < args.daily_rows:
                needed = args.daily_rows - len(sample_rows)
                sample_rows.extend(rows[:needed])
            result = _write_rows(
                connection,
                target=pilot_target,
                rows=rows,
                batch_size=args.batch_size,
            )
            inserted_rows += int(result["inserted_rows"])
            write_seconds += float(result["total_seconds"])
            transactions.append(float(result["maximum_transaction_seconds"]))

        expected_rows = args.pilot_listings * args.rows_per_listing
        if inserted_rows != expected_rows:
            raise AssertionError("pilot inserts did not reconcile")
        with connection.cursor() as cursor:
            cursor.execute(f"ANALYZE {pilot_target}")
            pilot_size = _relation_size(cursor, pilot_target)
            wal_after_pilot = _wal_lsn(cursor)
            pilot_wal_bytes = _wal_bytes(cursor, wal_start, wal_after_pilot)
        connection.commit()

        batch_results = _batch_comparison(
            connection,
            schema=schema,
            rows=sample_rows,
        )
        unchanged_result = _write_rows(
            connection,
            target=pilot_target,
            rows=sample_rows,
            batch_size=args.batch_size,
        )
        corrected_at = datetime.now(timezone.utc)
        corrected_rows = tuple(
            replace(
                row,
                calculated_at=corrected_at,
                rel_spx=(row.rel_spx or 0.0) + 0.0001,
            )
            for row in sample_rows
        )
        updated_result = _write_rows(
            connection,
            target=pilot_target,
            rows=corrected_rows,
            batch_size=args.batch_size,
        )
        if unchanged_result["unchanged_rows"] != len(sample_rows):
            raise AssertionError("equivalent rerun did not converge")
        if updated_result["updated_rows"] != len(sample_rows):
            raise AssertionError("correction update did not reconcile")

        with connection.cursor() as cursor:
            pre_daily_size = _relation_size(cursor, pilot_target)
        published_target, daily_target, effective_date = _create_daily_slice(
            connection,
            schema=schema,
            pilot_target=pilot_target,
            row_count=args.daily_rows,
        )
        with connection.cursor() as cursor:
            plans = _query_plans(
                cursor,
                pilot_target=pilot_target,
                published_target=published_target,
                representative_listing_id=selected[0][0].provider_listing_id,
                representative_history_count=args.rows_per_listing,
                historical_row_count=expected_rows,
                effective_date=effective_date,
                runs=args.plan_runs,
            )
            daily_size = _relation_size(cursor, daily_target)
            wal_end = _wal_lsn(cursor)
            total_wal_bytes = _wal_bytes(cursor, wal_start, wal_end)
        connection.rollback()

        bytes_per_pilot_row = pilot_size["total_bytes"] / expected_rows
        initial_universe_rows = 20_584_282
        projected_combined_bytes = int(
            bytes_per_pilot_row * initial_universe_rows * 2
        )
        projected_combined_gib = projected_combined_bytes / (1024.0**3)
        free_disk_bytes = shutil.disk_usage(os.getcwd()).free
        required_free_bytes = 2 * projected_combined_bytes + int(
            MINIMUM_HEADROOM_GIB * 1024**3
        )
        peak_rss = _peak_rss_mib()
        if peak_rss > MAXIMUM_PEAK_RSS_MIB:
            raise AssertionError("pilot exceeded the 2 GiB peak RSS gate")
        if projected_combined_gib > MAXIMUM_COMBINED_SLOT_GIB:
            raise AssertionError("projected two-slot footprint exceeds 40 GiB")
        if free_disk_bytes < required_free_bytes:
            raise AssertionError("available disk does not satisfy P0.8 headroom")

        return {
            "batch_comparison": batch_results,
            "database": database,
            "daily_slice": {
                "incremental_relation_bytes": (
                    daily_size["total_bytes"] - pre_daily_size["total_bytes"]
                ),
                "relation_size": daily_size,
                "row_count": args.daily_rows,
            },
            "gates": {
                "combined_slot_footprint_met": True,
                "disk_headroom_met": True,
                "peak_rss_met": True,
                "transaction_hard_maximum_met": max(transactions) <= 60.0,
                "transaction_target_met": max(transactions) <= 30.0,
            },
            "pilot": {
                "batch_size": args.batch_size,
                "calculated_and_validated_rows": expected_rows,
                "listing_count": args.pilot_listings,
                "maximum_observed_history": max(item[1] for item in selected),
                "maximum_transaction_seconds": max(transactions),
                "minimum_observed_history": min(item[1] for item in selected),
                "persisted_rows": inserted_rows,
                "relation_size": pilot_size,
                "rows_per_listing": args.rows_per_listing,
                "throughput_rows_per_second": expected_rows
                / (phase_seconds["calculation_validation"] + write_seconds),
                "wal_bytes": pilot_wal_bytes,
                "write_seconds": write_seconds,
            },
            "plans": plans,
            "platform": {
                "airflow_version": args.airflow_version
                or _package_version("apache-airflow"),
                "empire_package_version": _package_version(
                    "empire-stonks-tech-indicators"
                ),
                "numpy_version": numpy.__version__,
                "platform": platform.platform(),
                "python_version": platform.python_version(),
                "talib_version": talib.__version__,
            },
            "projection": {
                "available_disk_bytes": free_disk_bytes,
                "bytes_per_pilot_row": bytes_per_pilot_row,
                "initial_universe_rows": initial_universe_rows,
                "projected_combined_slot_bytes": projected_combined_bytes,
                "projected_combined_slot_gib": projected_combined_gib,
                "required_free_disk_bytes": required_free_bytes,
                "wal_bytes_per_inserted_row": pilot_wal_bytes / expected_rows,
            },
            "repeat_write": {
                "correction": updated_result,
                "equivalent": unchanged_result,
            },
            "resource": {"peak_rss_mib": peak_rss},
            "status": "ok",
            "timing_seconds": {
                **phase_seconds,
                "total": perf_counter() - started,
                "write": write_seconds,
            },
            "wal": {
                "pilot_bytes": pilot_wal_bytes,
                "total_benchmark_bytes": total_wal_bytes,
            },
        }
    finally:
        try:
            connection.rollback()
            if _SCHEMA_PATTERN.fullmatch(schema):
                with connection.cursor() as cursor:
                    cursor.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
                connection.commit()
                cleanup_complete = True
        finally:
            connection.close()
        if not cleanup_complete:
            raise RuntimeError(f"benchmark schema cleanup failed: {schema}")


def main() -> int:
    result = run(_parse_args())
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
