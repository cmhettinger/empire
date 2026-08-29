#!/usr/bin/env python3
"""Create, inspect, and remove the cleanup-safe A11.7 Airflow fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from empire_core import EmpireDatabase, ObjectStore
from empire_stonks_ohlcv import TechIndicatorsSourceCompletionSignal
from empire_stonks_tech_indicators import (
    TechIndicatorsConfig,
    TechIndicatorsDailyScope,
    resolve_tech_indicators_daily_scope,
)


DEFAULT_STATE_FILE = "/tmp/empire-tech-indicators-a11.7.json"
SOURCE_JOBS = (
    (
        "EODDATA",
        "eoddata_daily",
        "stonks_ohlcv_eoddata_daily",
        "stonks_ohlcv_eoddata_daily_scrape",
    ),
    (
        "YAHOO",
        "yahoo_daily",
        "stonks_ohlcv_yahoo_daily",
        "stonks_ohlcv_yahoo_daily_scrape",
    ),
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manage the bounded, cleanup-safe A11.7 Airflow fixture."
    )
    parser.add_argument(
        "command",
        choices=("setup", "show", "inspect", "cleanup"),
    )
    parser.add_argument("--state-file", default=DEFAULT_STATE_FILE)
    return parser.parse_args()


def _read_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"fixture state does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise RuntimeError("fixture state schema is invalid")
    return payload


def _write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _source_summary(provider_code: str, effective_date: str) -> dict[str, Any]:
    if provider_code == "EODDATA":
        return {
            "provider_code": provider_code,
            "effective_date": effective_date,
            "failure_count": 0,
            "missing_session_count": 0,
            "report_outcome": "PASS",
        }
    return {
        "provider_code": provider_code,
        "source_code": "yahoo_daily",
        "outcome": "succeeded",
        "scope": {
            "effective_date": effective_date,
            "tickers": ["SPX"],
        },
        "report_outcome": "PASS",
    }


def _setup(state_path: Path) -> dict[str, Any]:
    if state_path.exists():
        raise RuntimeError(
            f"fixture state already exists; inspect or clean it: {state_path}"
        )
    marker = uuid4().hex[:12].upper()
    fixture_runner = f"a11.7.{marker.lower()}"
    connection = EmpireDatabase.connect_from_env()
    listing_id: UUID | None = None
    source_run_ids: list[UUID] = []
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT clock_timestamp()")
        setup_at = cursor.fetchone()[0]
        cursor.execute(
            """
            SELECT listing.provider_listing_id, max(daily.trading_date)
            FROM stonks.provider_listing AS listing
            JOIN stonks.ohlcv_daily AS daily USING (provider_listing_id)
            WHERE listing.provider_code = 'YAHOO'
              AND listing.market = 'XIDX'
              AND listing.ticker = 'SPX'
              AND listing.status = 'ACTIVE'
            GROUP BY listing.provider_listing_id
            """
        )
        benchmark_row = cursor.fetchone()
        if benchmark_row is None:
            raise RuntimeError("active YAHOO/XIDX/SPX history is unavailable")
        benchmark_id, effective_date = benchmark_row
        cursor.execute(
            """
            SELECT
                EXISTS (
                    SELECT 1
                    FROM stonks.tech_indicators_publication_listing
                    WHERE provider_listing_id = %s AND is_active
                ),
                (SELECT count(*)
                 FROM stonks.ohlcv_daily_tech_indicators_a
                 WHERE provider_listing_id = %s),
                (SELECT count(*)
                 FROM stonks.ohlcv_daily_tech_indicators_b
                 WHERE provider_listing_id = %s)
            """,
            (benchmark_id, benchmark_id, benchmark_id),
        )
        if cursor.fetchone() != (False, 0, 0):
            raise RuntimeError("SPX technical state is not cleanup-safe")

        cursor.execute(
            """
            INSERT INTO stonks.provider_listing (
                provider_code, market, ticker, status, metadata
            )
            VALUES ('EODDATA', 'NASDAQ', %s, 'ACTIVE', '{"type":"Equity"}')
            RETURNING provider_listing_id
            """,
            (f"A117{marker}",),
        )
        listing_id = cursor.fetchone()[0]
        cursor.execute(
            """
            INSERT INTO stonks.ohlcv_daily (
                provider_listing_id, trading_date, open, high, low, close,
                volume, change, changepct, typ, hl_range, oc_range
            )
            VALUES (%s, %s, 10, 12, 9, 11, 100, NULL, NULL,
                    10.66666667, 3, 1)
            """,
            (listing_id, effective_date),
        )

        source_rows: list[dict[str, Any]] = []
        effective_date_text = effective_date.isoformat()
        for provider_code, source_code, job_name, source_dag_id in SOURCE_JOBS:
            summary = _source_summary(provider_code, effective_date_text)
            cursor.execute(
                """
                INSERT INTO core.core_run (
                    domain, job_name, subject_key, effective_date, run_type,
                    status, runner, summary, completed_at
                )
                VALUES (
                    'stonks', %s, %s, %s, 'airflow', 'succeeded',
                    %s, %s::jsonb, clock_timestamp()
                )
                RETURNING run_id
                """,
                (
                    job_name,
                    f"fixture:{marker.lower()}",
                    effective_date,
                    fixture_runner,
                    json.dumps(summary),
                ),
            )
            source_run_id = cursor.fetchone()[0]
            source_run_ids.append(source_run_id)
            signal = TechIndicatorsSourceCompletionSignal(
                provider_code=provider_code,
                source_code=source_code,
                job_name=job_name,
                effective_date=effective_date,
                source_run_id=source_run_id,
                report_outcome="PASS",
            )
            source_dag_run_id = (
                f"fixture__a11_7__{provider_code.lower()}__{marker.lower()}"
            )
            conf = signal.to_trigger_conf(
                source_dag_run_id=source_dag_run_id
            )
            conf["provider_listing_ids"] = sorted(
                (str(listing_id), str(benchmark_id))
            )
            source_rows.append(
                {
                    "provider_code": provider_code,
                    "source_core_run_id": str(source_run_id),
                    "source_dag_id": source_dag_id,
                    "source_dag_run_id": source_dag_run_id,
                    "trigger_conf": conf,
                    "trigger_run_id": signal.trigger_run_id,
                }
            )

        config = TechIndicatorsConfig.from_env()
        scope = TechIndicatorsDailyScope(
            effective_date=effective_date,
            provider_listing_ids=(listing_id, benchmark_id),
        )
        resolved = resolve_tech_indicators_daily_scope(
            cursor=cursor,
            scope=scope,
            benchmark_config=config.benchmark,
        )
        if not resolved.ready or len(resolved.listings) != 2:
            raise RuntimeError(
                "fixture did not satisfy exact-date source readiness"
            )
        connection.commit()
        state = {
            "schema_version": 1,
            "marker": marker,
            "fixture_runner": fixture_runner,
            "setup_at": setup_at.astimezone(timezone.utc).isoformat(),
            "effective_date": effective_date_text,
            "benchmark_provider_listing_id": str(benchmark_id),
            "fixture_provider_listing_id": str(listing_id),
            "scope_hash": resolved.scope_hash,
            "subject_key": resolved.subject_key,
            "sources": source_rows,
        }
        _write_state(state_path, state)
        return state
    except BaseException:
        connection.rollback()
        if source_run_ids or listing_id is not None:
            _remove_setup_rows(
                connection,
                listing_id=listing_id,
                source_run_ids=source_run_ids,
            )
        raise
    finally:
        connection.close()


def _remove_setup_rows(
    connection: Any,
    *,
    listing_id: UUID | None,
    source_run_ids: list[UUID],
) -> None:
    cursor = connection.cursor()
    if listing_id is not None:
        cursor.execute(
            "DELETE FROM stonks.provider_listing "
            "WHERE provider_listing_id = %s",
            (listing_id,),
        )
    if source_run_ids:
        cursor.execute(
            "DELETE FROM core.core_run WHERE run_id = ANY(%s::uuid[])",
            (source_run_ids,),
        )
    connection.commit()


def _inspect(state_path: Path) -> dict[str, Any]:
    state = _read_state(state_path)
    connection = EmpireDatabase.connect_from_env()
    object_connection = EmpireDatabase.connect_from_env()
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT run_id, status, summary, completed_at
            FROM core.core_run
            WHERE domain = 'stonks'
              AND job_name = 'stonks_tech_indicators_daily'
              AND effective_date = %s
              AND subject_key = %s
              AND run_type = 'airflow'
              AND runner = 'airflow'
              AND created_at >= %s::timestamptz
            ORDER BY created_at, run_id
            """,
            (
                state["effective_date"],
                state["subject_key"],
                state["setup_at"],
            ),
        )
        workflow_rows = cursor.fetchall()
        if len(workflow_rows) != 2:
            raise RuntimeError(
                f"expected two technical Core runs, found {len(workflow_rows)}"
            )

        outcomes = [row[2].get("outcome") for row in workflow_rows]
        if outcomes != ["PASS", "NO_OP"]:
            raise RuntimeError(f"unexpected workflow outcomes: {outcomes}")
        if any(row[1] != "succeeded" or row[3] is None for row in workflow_rows):
            raise RuntimeError("technical Core runs are not completed successes")

        object_store = ObjectStore.from_connection(object_connection)
        run_facts: list[dict[str, Any]] = []
        object_paths: list[str] = []
        for run_id, status, summary, completed_at in workflow_rows:
            cursor.execute(
                """
                SELECT object_id, object_kind, content_type, size_bytes,
                       checksum_sha256, metadata, root.base_uri,
                       object.object_key, object.filename
                FROM core.stored_object AS object
                JOIN core.storage_root AS root USING (storage_root_id)
                WHERE object.run_id = %s AND object.deleted_at IS NULL
                ORDER BY object.object_kind
                """,
                (run_id,),
            )
            objects = cursor.fetchall()
            if len(objects) != 2:
                raise RuntimeError(f"run {run_id} does not own two reports")
            object_facts: list[dict[str, Any]] = []
            for row in objects:
                object_id = row[0]
                data = object_store.get_bytes(object_id)
                if len(data) != row[3]:
                    raise RuntimeError(f"object size mismatch: {object_id}")
                if hashlib.sha256(data).hexdigest() != row[4]:
                    raise RuntimeError(f"object checksum mismatch: {object_id}")
                if row[1] == "stonks_tech_indicators_report":
                    report = json.loads(data)
                    if (
                        report["identity"]["run_id"] != str(run_id)
                        or report["outcome"] != summary["outcome"]
                        or report["scope"]["scope_hash"] != state["scope_hash"]
                        or report["scope"]["resolved_listing_count"] != 2
                    ):
                        raise RuntimeError("JSON report identity is invalid")
                    source_ids = {
                        item["provider_code"]: item[
                            "latest_successful_run_id"
                        ]
                        for item in report["source_readiness"][
                            "provider_evidence"
                        ]
                    }
                    expected_source_ids = {
                        item["provider_code"]: item["source_core_run_id"]
                        for item in state["sources"]
                    }
                    if source_ids != expected_source_ids:
                        raise RuntimeError("JSON source evidence is invalid")
                    inspected = {"json_schema_version": report["schema_version"]}
                elif row[1] == "stonks_tech_indicators_pdf_report":
                    if not data.startswith(b"%PDF-") or b"%%EOF" not in data[-64:]:
                        raise RuntimeError("PDF report framing is invalid")
                    inspected = {"pdf_framing": "valid"}
                else:
                    raise RuntimeError(f"unexpected object kind: {row[1]}")
                path = str(Path(row[6]) / row[7] / row[8])
                object_paths.append(path)
                object_facts.append(
                    {
                        "object_id": str(object_id),
                        "object_kind": row[1],
                        "content_type": row[2],
                        "size_bytes": row[3],
                        "checksum_sha256": row[4],
                        "metadata_outcome": row[5]["outcome"],
                        "path": path,
                        **inspected,
                    }
                )
            run_facts.append(
                {
                    "run_id": str(run_id),
                    "status": status,
                    "outcome": summary["outcome"],
                    "publication_id": summary.get("publication_id"),
                    "completed_at": completed_at.astimezone(timezone.utc).isoformat(),
                    "objects": object_facts,
                }
            )

        workflow_run_ids = [UUID(item["run_id"]) for item in run_facts]
        cursor.execute(
            """
            SELECT publication_id, run_id, status, publication_kind,
                   expected_listing_count, staged_payload_row_count
            FROM stonks.tech_indicators_publication
            WHERE run_id = ANY(%s::uuid[])
            ORDER BY created_at
            """,
            (workflow_run_ids,),
        )
        publications = cursor.fetchall()
        if len(publications) != 1 or publications[0][2] != "PUBLISHED":
            raise RuntimeError("expected one published technical publication")
        publication_id = publications[0][0]
        cursor.execute(
            """
            SELECT count(*), count(*) FILTER (WHERE is_active),
                   array_agg(provider_listing_id::text ORDER BY provider_listing_id)
            FROM stonks.tech_indicators_publication_listing
            WHERE publication_id = %s
            """,
            (publication_id,),
        )
        membership_count, active_count, listing_ids = cursor.fetchone()
        expected_listing_ids = sorted(
            (
                state["benchmark_provider_listing_id"],
                state["fixture_provider_listing_id"],
            )
        )
        if (
            membership_count != 2
            or active_count != 2
            or listing_ids != expected_listing_ids
        ):
            raise RuntimeError("published listing membership is invalid")

        listing_uuid = UUID(state["fixture_provider_listing_id"])
        benchmark_uuid = UUID(state["benchmark_provider_listing_id"])
        cursor.execute(
            """
            SELECT provider_listing_id::text, count(*)
            FROM stonks.ohlcv_daily_tech_indicators
            WHERE provider_listing_id = ANY(%s::uuid[])
            GROUP BY provider_listing_id
            ORDER BY provider_listing_id
            """,
            ([listing_uuid, benchmark_uuid],),
        )
        payload_counts = cursor.fetchall()
        if len(payload_counts) != 2 or any(row[1] < 1 for row in payload_counts):
            raise RuntimeError("published payload coverage is incomplete")

        state["workflow_run_ids"] = [str(item) for item in workflow_run_ids]
        state["publication_ids"] = [str(publication_id)]
        state["object_paths"] = object_paths
        _write_state(state_path, state)
        return {
            "status": "ok",
            "effective_date": state["effective_date"],
            "scope_hash": state["scope_hash"],
            "runs": run_facts,
            "publication": {
                "publication_id": str(publication_id),
                "run_id": str(publications[0][1]),
                "status": publications[0][2],
                "publication_kind": publications[0][3],
                "expected_listing_count": publications[0][4],
                "staged_payload_row_count": publications[0][5],
                "active_listing_count": active_count,
            },
            "published_payload_counts": [
                {"provider_listing_id": row[0], "row_count": row[1]}
                for row in payload_counts
            ],
        }
    finally:
        connection.rollback()
        object_connection.rollback()
        connection.close()
        object_connection.close()


def _cleanup(state_path: Path) -> dict[str, Any]:
    state = _read_state(state_path)
    workflow_run_ids = [UUID(value) for value in state.get("workflow_run_ids", [])]
    publication_ids = [UUID(value) for value in state.get("publication_ids", [])]
    source_run_ids = [
        UUID(item["source_core_run_id"]) for item in state["sources"]
    ]
    listing_id = UUID(state["fixture_provider_listing_id"])
    benchmark_id = UUID(state["benchmark_provider_listing_id"])
    paths = [Path(value) for value in state.get("object_paths", [])]
    if len(workflow_run_ids) != 2 or len(publication_ids) != 1 or len(paths) != 4:
        raise RuntimeError("inspect must succeed before cleanup")

    connection = EmpireDatabase.connect_from_env()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "DELETE FROM stonks.tech_indicators_publication_listing "
            "WHERE publication_id = ANY(%s::uuid[])",
            (publication_ids,),
        )
        cursor.execute(
            "DELETE FROM stonks.provider_listing "
            "WHERE provider_listing_id = %s",
            (listing_id,),
        )
        for table_name in (
            "stonks.ohlcv_daily_tech_indicators_a",
            "stonks.ohlcv_daily_tech_indicators_b",
        ):
            cursor.execute(
                f"DELETE FROM {table_name} WHERE provider_listing_id = %s",
                (benchmark_id,),
            )
        cursor.execute(
            "DELETE FROM stonks.tech_indicators_publication "
            "WHERE publication_id = ANY(%s::uuid[])",
            (publication_ids,),
        )
        cursor.execute(
            "DELETE FROM core.stored_object "
            "WHERE run_id = ANY(%s::uuid[])",
            (workflow_run_ids,),
        )
        all_run_ids = [*source_run_ids, *workflow_run_ids]
        cursor.execute(
            "DELETE FROM core.core_run WHERE run_id = ANY(%s::uuid[])",
            (all_run_ids,),
        )
        connection.commit()

        cursor.execute(
            """
            SELECT
                (SELECT count(*) FROM core.core_run
                 WHERE run_id = ANY(%s::uuid[])),
                (SELECT count(*) FROM core.stored_object
                 WHERE run_id = ANY(%s::uuid[])),
                (SELECT count(*) FROM stonks.tech_indicators_publication
                 WHERE publication_id = ANY(%s::uuid[])),
                (SELECT count(*) FROM stonks.provider_listing
                 WHERE provider_listing_id = %s),
                (SELECT count(*) FROM stonks.ohlcv_daily_tech_indicators_a
                 WHERE provider_listing_id = %s),
                (SELECT count(*) FROM stonks.ohlcv_daily_tech_indicators_b
                 WHERE provider_listing_id = %s)
            """,
            (
                all_run_ids,
                workflow_run_ids,
                publication_ids,
                listing_id,
                benchmark_id,
                benchmark_id,
            ),
        )
        residue = cursor.fetchone()
        if residue != (0, 0, 0, 0, 0, 0):
            raise RuntimeError(f"fixture cleanup left residue: {residue}")
    finally:
        connection.rollback()
        connection.close()

    for path in paths:
        path.unlink(missing_ok=True)
    remaining_paths = [str(path) for path in paths if path.exists()]
    if remaining_paths:
        raise RuntimeError(f"fixture report files remain: {remaining_paths}")
    state_path.unlink()
    return {
        "status": "clean",
        "database_residue": [0, 0, 0, 0, 0, 0],
        "report_file_residue": 0,
    }


def main() -> int:
    args = _parse_args()
    state_path = Path(args.state_file)
    if args.command == "setup":
        result = _setup(state_path)
    elif args.command == "show":
        result = _read_state(state_path)
    elif args.command == "inspect":
        result = _inspect(state_path)
    else:
        result = _cleanup(state_path)
    json.dump(result, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
