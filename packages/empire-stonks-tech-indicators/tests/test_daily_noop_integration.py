from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from empire_core import ObjectStore, RunService
from empire_stonks_tech_indicators import (
    ReportOutcome,
    TECH_INDICATORS_LOCK_CONTENDED_MESSAGE,
    TechIndicatorsConfig,
    TechIndicatorsDailyScope,
    acquire_tech_indicators_writer_lock,
    run_tech_indicators_daily,
)


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


def test_healthy_noop_reuses_ready_publication_without_payload_writes() -> None:
    if any(not os.environ.get(name) for name in DATABASE_ENVIRONMENT):
        pytest.skip("Empire database environment is not configured.")
    work = EmpireDatabase.connect_from_env()
    core_connection = EmpireDatabase.connect_from_env()
    object_connection = EmpireDatabase.connect_from_env()
    cleanup = EmpireDatabase.connect_from_env()
    listing_id: UUID | None = None
    benchmark_id: UUID | None = None
    source_run_ids: list[UUID] = []
    workflow_run_ids: list[UUID] = []
    publication_id: UUID | None = None
    owner_lock = None
    stored_paths: list[tuple[Path, Path]] = []
    marker = uuid4().hex[:12].upper()
    try:
        cursor = work.cursor()
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
        benchmark_id, effective_date = cursor.fetchone()
        cursor.execute(
            """
            SELECT
                EXISTS (
                    SELECT 1
                    FROM stonks.tech_indicators_publication_listing
                    WHERE provider_listing_id = %s AND is_active
                ),
                (SELECT count(*) FROM stonks.ohlcv_daily_tech_indicators_a
                 WHERE provider_listing_id = %s),
                (SELECT count(*) FROM stonks.ohlcv_daily_tech_indicators_b
                 WHERE provider_listing_id = %s)
            """,
            (benchmark_id, benchmark_id, benchmark_id),
        )
        if cursor.fetchone() != (False, 0, 0):
            pytest.skip("SPX technical fixture state is not cleanup-safe.")
        cursor.execute(
            """
            INSERT INTO stonks.provider_listing (
                provider_code, market, ticker, status, metadata
            )
            VALUES ('EODDATA', 'NASDAQ', %s, 'ACTIVE', '{"type": "Equity"}')
            RETURNING provider_listing_id
            """,
            (f"J94{marker}",),
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
        evidence = (
            (
                "stonks_ohlcv_eoddata_daily",
                {
                    "provider_code": "EODDATA",
                    "effective_date": effective_date.isoformat(),
                    "failure_count": 0,
                    "missing_session_count": 0,
                    "report_outcome": "PASS",
                },
            ),
            (
                "stonks_ohlcv_yahoo_daily",
                {
                    "provider_code": "YAHOO",
                    "source_code": "yahoo_daily",
                    "outcome": "succeeded",
                    "scope": {
                        "effective_date": effective_date.isoformat(),
                        "tickers": ["SPX"],
                    },
                    "report_outcome": "PASS",
                },
            ),
        )
        for job_name, summary in evidence:
            cursor.execute(
                """
                INSERT INTO core.core_run (
                    domain, job_name, subject_key, effective_date, run_type,
                    status, runner, summary, completed_at
                )
                VALUES (
                    'stonks', %s, 'pytest', %s, 'manual', 'succeeded',
                    'pytest', %s::jsonb, now()
                )
                RETURNING run_id
                """,
                (job_name, effective_date, json.dumps(summary)),
            )
            source_run_ids.append(cursor.fetchone()[0])
        work.commit()

        object_store = ObjectStore.from_connection(object_connection)
        scope = TechIndicatorsDailyScope(
            effective_date=effective_date,
            provider_listing_ids=(listing_id, benchmark_id),
        )
        cursor.execute(
            """
            SELECT
                (SELECT count(*) FROM core.core_run
                 WHERE domain = 'stonks'
                   AND job_name = 'stonks_tech_indicators_daily'
                   AND effective_date = %s),
                (SELECT count(*)
                 FROM stonks.tech_indicators_publication),
                (SELECT count(*)
                 FROM stonks.ohlcv_daily_tech_indicators_a
                 WHERE provider_listing_id = %s),
                (SELECT count(*)
                 FROM stonks.ohlcv_daily_tech_indicators_b
                 WHERE provider_listing_id = %s)
            """,
            (effective_date, listing_id, listing_id),
        )
        state_before_contention = cursor.fetchone()
        owner = acquire_tech_indicators_writer_lock(
            connection_factory=EmpireDatabase.connect_from_env
        )
        assert owner.lock is not None
        owner_lock = owner.lock
        contended = run_tech_indicators_daily(
            run_service=RunService.from_connection(core_connection),
            connection=work,
            lock_connection_factory=EmpireDatabase.connect_from_env,
            object_store=object_store,
            config=TechIndicatorsConfig(),
            scope=scope,
            run_type="airflow",
            runner="airflow",
        )
        assert contended.to_dict() == {
            "status": "contended",
            "effective_date": effective_date.isoformat(),
            "run_id": None,
            "publication_id": None,
            "json_report_object_id": None,
            "pdf_report_object_id": None,
            "outcome": None,
            "message": TECH_INDICATORS_LOCK_CONTENDED_MESSAGE,
        }
        cursor.execute(
            """
            SELECT
                (SELECT count(*) FROM core.core_run
                 WHERE domain = 'stonks'
                   AND job_name = 'stonks_tech_indicators_daily'
                   AND effective_date = %s),
                (SELECT count(*)
                 FROM stonks.tech_indicators_publication),
                (SELECT count(*)
                 FROM stonks.ohlcv_daily_tech_indicators_a
                 WHERE provider_listing_id = %s),
                (SELECT count(*)
                 FROM stonks.ohlcv_daily_tech_indicators_b
                 WHERE provider_listing_id = %s)
            """,
            (effective_date, listing_id, listing_id),
        )
        assert cursor.fetchone() == state_before_contention
        owner_lock.rollback()
        owner_lock = None

        first = run_tech_indicators_daily(
            run_service=RunService.from_connection(core_connection),
            connection=work,
            lock_connection_factory=EmpireDatabase.connect_from_env,
            object_store=object_store,
            config=TechIndicatorsConfig(),
            scope=scope,
            run_type="manual",
            runner="pytest",
        )
        workflow_run_ids.append(first.run_id)
        publication_id = first.publication_id
        assert first.outcome is ReportOutcome.PASS
        assert publication_id is not None
        cursor.execute(
            """
            SELECT provider_listing_id, trading_date, updated_at
            FROM stonks.ohlcv_daily_tech_indicators
            WHERE provider_listing_id = ANY(%s::uuid[])
            ORDER BY provider_listing_id, trading_date
            """,
            ([listing_id, benchmark_id],),
        )
        timestamps_before = cursor.fetchall()
        cursor.execute(
            "SELECT count(*) FROM stonks.tech_indicators_publication"
        )
        publication_count_before = cursor.fetchone()[0]

        replacement_source_run_ids: list[UUID] = []
        for job_name, summary in evidence:
            cursor.execute(
                """
                INSERT INTO core.core_run (
                    domain, job_name, subject_key, effective_date, run_type,
                    status, runner, summary, completed_at
                )
                VALUES (
                    'stonks', %s, 'pytest-reconciliation', %s, 'airflow',
                    'succeeded', 'airflow', %s::jsonb, clock_timestamp()
                )
                RETURNING run_id
                """,
                (job_name, effective_date, json.dumps(summary)),
            )
            replacement_source_run_ids.append(cursor.fetchone()[0])
        source_run_ids.extend(replacement_source_run_ids)
        work.commit()

        noop = run_tech_indicators_daily(
            run_service=RunService.from_connection(core_connection),
            connection=work,
            lock_connection_factory=EmpireDatabase.connect_from_env,
            object_store=object_store,
            config=TechIndicatorsConfig(),
            scope=scope,
            run_type="manual",
            runner="pytest",
        )
        workflow_run_ids.append(noop.run_id)

        assert noop.status == "succeeded"
        assert noop.outcome is ReportOutcome.NO_OP
        assert noop.publication_id is None
        report_payload = json.loads(
            object_store.get_bytes(noop.json_report_object_id)
        )
        assert len(report_payload["identity"]["existing_readiness_token"]) == 64
        assert report_payload["identity"]["publication_id"] is None
        assert report_payload["publication"]["report_phase"] == (
            "EXISTING_PUBLICATION"
        )
        assert report_payload["publication"]["readiness_at_report"] == "READY"
        evidence_by_provider = {
            item["provider_code"]: item
            for item in report_payload["source_readiness"][
                "provider_evidence"
            ]
        }
        assert evidence_by_provider["EODDATA"][
            "latest_successful_run_id"
        ] == str(replacement_source_run_ids[0])
        assert evidence_by_provider["YAHOO"][
            "latest_successful_run_id"
        ] == str(replacement_source_run_ids[1])
        assert report_payload["writes"] == {
            "batch_count": 0,
            "committed_batch_count": 0,
            "copied_equivalent": 0,
            "deleted": 0,
            "equivalent": 0,
            "failed": 0,
            "inserted": 0,
            "rolled_back_batch_count": 0,
            "unchanged": 0,
            "updated": 0,
        }
        cursor.execute(
            "SELECT count(*) FROM stonks.tech_indicators_publication"
        )
        assert cursor.fetchone() == (publication_count_before,)
        cursor.execute(
            """
            SELECT provider_listing_id, trading_date, updated_at
            FROM stonks.ohlcv_daily_tech_indicators
            WHERE provider_listing_id = ANY(%s::uuid[])
            ORDER BY provider_listing_id, trading_date
            """,
            ([listing_id, benchmark_id],),
        )
        assert cursor.fetchall() == timestamps_before
        cursor.execute(
            """
            SELECT status, summary ->> 'outcome',
                   summary ->> 'publication_id',
                   summary ->> 'evaluated_row_count',
                   summary ->> 'changed_row_count'
            FROM core.core_run
            WHERE run_id = %s
            """,
            (noop.run_id,),
        )
        assert cursor.fetchone() == ("succeeded", "NO_OP", None, "0", "0")
        cursor.execute(
            """
            SELECT metadata ->> 'outcome', object_kind
            FROM core.stored_object
            WHERE run_id = %s
            ORDER BY object_kind
            """,
            (noop.run_id,),
        )
        assert cursor.fetchall() == [
            ("NO_OP", "stonks_tech_indicators_pdf_report"),
            ("NO_OP", "stonks_tech_indicators_report"),
        ]

        dry_zero = run_tech_indicators_daily(
            run_service=RunService.from_connection(core_connection),
            connection=work,
            lock_connection_factory=EmpireDatabase.connect_from_env,
            object_store=object_store,
            config=TechIndicatorsConfig(),
            scope=TechIndicatorsDailyScope(
                effective_date=effective_date,
                provider_listing_ids=(listing_id, benchmark_id),
                dry_run=True,
            ),
            run_type="manual",
            runner="pytest",
        )
        workflow_run_ids.append(dry_zero.run_id)
        assert dry_zero.outcome is ReportOutcome.PASS
        assert dry_zero.publication_id is None
        dry_payload = json.loads(
            object_store.get_bytes(dry_zero.json_report_object_id)
        )
        assert dry_payload["publication"]["report_phase"] == "DRY_RUN"
        assert dry_payload["identity"]["existing_readiness_token"] is None
        cursor.execute(
            "SELECT count(*) FROM stonks.tech_indicators_publication"
        )
        assert cursor.fetchone() == (publication_count_before,)
        cursor.execute(
            """
            SELECT provider_listing_id, trading_date, updated_at
            FROM stonks.ohlcv_daily_tech_indicators
            WHERE provider_listing_id = ANY(%s::uuid[])
            ORDER BY provider_listing_id, trading_date
            """,
            ([listing_id, benchmark_id],),
        )
        assert cursor.fetchall() == timestamps_before
    finally:
        if owner_lock is not None and owner_lock.is_held:
            owner_lock.rollback()
        for connection in (work, core_connection, object_connection):
            try:
                connection.rollback()
            finally:
                connection.close()
        cleanup_cursor = cleanup.cursor()
        all_run_ids = [*source_run_ids, *workflow_run_ids]
        if workflow_run_ids:
            cleanup_cursor.execute(
                """
                SELECT root.base_uri, object.object_key, object.filename
                FROM core.stored_object AS object
                JOIN core.storage_root AS root USING (storage_root_id)
                WHERE object.run_id = ANY(%s::uuid[])
                """,
                (workflow_run_ids,),
            )
            stored_paths = [
                (Path(base_uri) / object_key / filename, Path(base_uri))
                for base_uri, object_key, filename in cleanup_cursor.fetchall()
            ]
        if publication_id is not None:
            cleanup_cursor.execute(
                "DELETE FROM stonks.tech_indicators_publication_listing "
                "WHERE publication_id = %s",
                (publication_id,),
            )
            cleanup_cursor.execute(
                "DELETE FROM stonks.tech_indicators_publication "
                "WHERE publication_id = %s",
                (publication_id,),
            )
        if listing_id is not None:
            cleanup_cursor.execute(
                "DELETE FROM stonks.provider_listing "
                "WHERE provider_listing_id = %s",
                (listing_id,),
            )
        if benchmark_id is not None:
            for table_name in (
                "stonks.ohlcv_daily_tech_indicators_a",
                "stonks.ohlcv_daily_tech_indicators_b",
            ):
                cleanup_cursor.execute(
                    f"DELETE FROM {table_name} WHERE provider_listing_id = %s",
                    (benchmark_id,),
                )
        if workflow_run_ids:
            cleanup_cursor.execute(
                "DELETE FROM core.stored_object WHERE run_id = ANY(%s::uuid[])",
                (workflow_run_ids,),
            )
        if all_run_ids:
            cleanup_cursor.execute(
                "DELETE FROM core.core_run WHERE run_id = ANY(%s::uuid[])",
                (all_run_ids,),
            )
        cleanup.commit()
        cleanup.close()
        for stored_path, storage_root in stored_paths:
            stored_path.unlink(missing_ok=True)
            parent = stored_path.parent
            while parent != storage_root:
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent
