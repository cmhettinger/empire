from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest

import empire_stonks_tech_indicators.backfill_runner as backfill_runner_module
from empire_core import ObjectStore, RunService
from empire_stonks_tech_indicators import (
    PublicationRecoveryAction,
    ReportOutcome,
    TechIndicatorsBackfillScope,
    TechIndicatorsConfig,
    TechIndicatorsWorkflowError,
    inspect_publication_recovery,
    run_tech_indicators_backfill,
)
from empire_stonks_tech_indicators.publication import (
    TECH_INDICATORS_WRITER_LOCK_KEY,
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


def test_backfill_commits_partial_progress_and_resumes_without_duplicate_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if any(not os.environ.get(name) for name in DATABASE_ENVIRONMENT):
        pytest.skip("Empire database environment is not configured.")
    work = EmpireDatabase.connect_from_env()
    core_connection = EmpireDatabase.connect_from_env()
    object_connection = EmpireDatabase.connect_from_env()
    cleanup = EmpireDatabase.connect_from_env()
    listing_id: UUID | None = None
    publication_id: UUID | None = None
    publication_ids: list[UUID] = []
    run_ids: list[UUID] = []
    marker = uuid4().hex[:12].upper()
    runner_identity = f"pytest.j96.{marker}"
    try:
        cursor = work.cursor()
        cursor.execute(
            """
            SELECT max(trading_date)
            FROM stonks.ohlcv_daily AS daily
            JOIN stonks.provider_listing AS listing USING (provider_listing_id)
            WHERE listing.provider_code = 'YAHOO'
              AND listing.market = 'XIDX' AND listing.ticker = 'SPX'
            """
        )
        effective_date = cursor.fetchone()[0]
        start_date = effective_date - timedelta(days=1000)
        cursor.execute(
            """
            INSERT INTO stonks.provider_listing (
                provider_code, market, ticker, status, metadata
            ) VALUES ('EODDATA', 'NASDAQ', %s, 'ACTIVE', '{"type":"Equity"}')
            RETURNING provider_listing_id
            """,
            (f"J96{marker}",),
        )
        listing_id = cursor.fetchone()[0]
        cursor.execute(
            """
            INSERT INTO stonks.ohlcv_daily (
                provider_listing_id, trading_date, open, high, low, close,
                volume, change, changepct, typ, hl_range, oc_range
            )
            SELECT %s, day::date, 10, 12, 9, 11, 100,
                   NULL, NULL, 10.66666667, 3, 1
            FROM generate_series(%s::date, %s::date, interval '1 day') AS day
            """,
            (listing_id, start_date, effective_date),
        )
        work.commit()
        object_store = ObjectStore.from_connection(object_connection)
        services = dict(
            run_service=RunService.from_connection(core_connection),
            connection=work,
            lock_connection_factory=EmpireDatabase.connect_from_env,
            object_store=object_store,
            config=TechIndicatorsConfig(),
            run_type="manual",
            runner=runner_identity,
        )
        progress_events: list[dict[str, object]] = []
        first = run_tech_indicators_backfill(
            **services,
            scope=TechIndicatorsBackfillScope(
                effective_date=effective_date,
                start_date=start_date,
                end_date=effective_date,
                provider_listing_ids=(listing_id,),
                batch_size=1000,
            ),
            batch_limit=1,
            progress_sink=progress_events.append,
        )
        assert first.status == "partial"
        assert first.outcome is ReportOutcome.PARTIAL
        assert first.resume_cursor.batch_number == 1
        assert progress_events == [
            {
                "run_id": str(first.run_id),
                "stage": "batch",
                "completed_batch_count": 1,
                "committed_batch_count_this_run": 1,
                "planned_batch_count": 2,
                "staged_payload_row_count": 1000,
                "resume_cursor": first.resume_cursor.to_dict(),
                "durable": True,
            }
        ]
        publication_id = first.publication_id
        publication_ids.append(publication_id)
        run_ids.append(first.run_id)
        cursor.execute(
            """
            SELECT status, completed_batch_count, staged_payload_row_count
            FROM stonks.tech_indicators_publication WHERE publication_id = %s
            """,
            (publication_id,),
        )
        assert cursor.fetchone() == ("BUILDING", 1, 1000)
        cursor.execute(
            """
            SELECT count(*) FROM stonks.ohlcv_daily_tech_indicators
            WHERE provider_listing_id = %s
            """,
            (listing_id,),
        )
        assert cursor.fetchone() == (0,)

        original_upsert = backfill_runner_module.upsert_feature_rows

        def fail_next_batch(**_values: object) -> object:
            raise RuntimeError("database password=should-not-escape")

        monkeypatch.setattr(
            backfill_runner_module,
            "upsert_feature_rows",
            fail_next_batch,
        )
        with pytest.raises(
            TechIndicatorsWorkflowError,
            match="^Technical-indicator workflow failed safely\\.$",
        ) as failure:
            run_tech_indicators_backfill(
                **services,
                scope=TechIndicatorsBackfillScope(
                    effective_date=effective_date,
                    start_date=start_date,
                    end_date=effective_date,
                    provider_listing_ids=(listing_id,),
                    batch_size=1000,
                    resume_cursor=first.resume_cursor,
                ),
            )
        assert isinstance(failure.value.__cause__, RuntimeError)
        assert "password=should-not-escape" not in str(failure.value)
        monkeypatch.setattr(
            backfill_runner_module,
            "upsert_feature_rows",
            original_upsert,
        )
        cursor.execute(
            """
            SELECT status, completed_batch_count, staged_payload_row_count
            FROM stonks.tech_indicators_publication WHERE publication_id = %s
            """,
            (publication_id,),
        )
        assert cursor.fetchone() == ("BUILDING", 1, 1000)
        cursor.execute(
            """
            SELECT status, error_message
            FROM core.core_run
            WHERE job_name = 'stonks_tech_indicators_backfill'
              AND runner = %s
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (runner_identity,),
        )
        assert cursor.fetchone() == (
            "failed",
            "Technical-indicator workflow failed safely.",
        )
        cursor.execute(
            """
            SELECT count(*) FROM stonks.ohlcv_daily_tech_indicators
            WHERE provider_listing_id = %s
            """,
            (listing_id,),
        )
        assert cursor.fetchone() == (0,)
        cursor.execute(
            "SELECT scope_hash FROM stonks.tech_indicators_publication "
            "WHERE publication_id = %s",
            (publication_id,),
        )
        scope_hash = cursor.fetchone()[0]
        cursor.execute(
            "SELECT pg_try_advisory_xact_lock(%s::bigint)",
            (TECH_INDICATORS_WRITER_LOCK_KEY,),
        )
        assert cursor.fetchone() == (True,)
        recovery = inspect_publication_recovery(
            cursor=cursor,
            publication_id=publication_id,
            scope_hash=scope_hash,
            calculation_version="TECH_INDICATORS_V1",
        )
        assert recovery.action is PublicationRecoveryAction.RESUME_BUILDING
        work.rollback()

        second = run_tech_indicators_backfill(
            **services,
            scope=TechIndicatorsBackfillScope(
                effective_date=effective_date,
                start_date=start_date,
                end_date=effective_date,
                provider_listing_ids=(listing_id,),
                batch_size=1000,
                resume_cursor=first.resume_cursor,
            ),
        )
        run_ids.append(second.run_id)
        assert second.status == "succeeded"
        assert second.publication_id == publication_id
        cursor.execute(
            """
            SELECT status, completed_batch_count, staged_payload_row_count,
                   inserted_row_count + updated_row_count + equivalent_row_count
            FROM stonks.tech_indicators_publication WHERE publication_id = %s
            """,
            (publication_id,),
        )
        assert cursor.fetchone() == ("PUBLISHED", 2, 1001, 1001)
        cursor.execute(
            """
            SELECT count(*) FROM stonks.ohlcv_daily_tech_indicators
            WHERE provider_listing_id = %s
            """,
            (listing_id,),
        )
        assert cursor.fetchone() == (1001,)
        cursor.execute(
            """
            SELECT run_id, calculated_at
            FROM stonks.ohlcv_daily_tech_indicators
            WHERE provider_listing_id = %s AND trading_date = %s
            """,
            (listing_id, start_date),
        )
        preserved_before = cursor.fetchone()

        bounded = run_tech_indicators_backfill(
            **services,
            scope=TechIndicatorsBackfillScope(
                effective_date=effective_date,
                start_date=effective_date,
                end_date=effective_date,
                provider_listing_ids=(listing_id,),
                batch_size=1000,
            ),
        )
        run_ids.append(bounded.run_id)
        publication_ids.append(bounded.publication_id)
        assert bounded.status == "succeeded"
        cursor.execute(
            """
            SELECT run_id, calculated_at
            FROM stonks.ohlcv_daily_tech_indicators
            WHERE provider_listing_id = %s AND trading_date = %s
            """,
            (listing_id, start_date),
        )
        assert cursor.fetchone() == preserved_before
    finally:
        for connection in (work, core_connection, object_connection):
            try:
                connection.rollback()
            finally:
                connection.close()
        cursor = cleanup.cursor()
        stored_paths: list[tuple[Path, Path]] = []
        cursor.execute(
            """
            SELECT run_id FROM core.core_run
            WHERE job_name = 'stonks_tech_indicators_backfill'
              AND runner = %s
            """,
            (runner_identity,),
        )
        run_ids = list({*run_ids, *(row[0] for row in cursor.fetchall())})
        if run_ids:
            cursor.execute(
                """
                SELECT publication_id
                FROM stonks.tech_indicators_publication
                WHERE run_id = ANY(%s::uuid[])
                """,
                (run_ids,),
            )
            discovered = [row[0] for row in cursor.fetchall()]
            publication_ids = list({*publication_ids, *discovered})
        if run_ids:
            cursor.execute(
                """
                SELECT root.base_uri, object.object_key, object.filename
                FROM core.stored_object AS object
                JOIN core.storage_root AS root USING (storage_root_id)
                WHERE object.run_id = ANY(%s::uuid[])
                """,
                (run_ids,),
            )
            stored_paths = [
                (Path(root) / key / filename, Path(root))
                for root, key, filename in cursor.fetchall()
            ]
        if listing_id is not None:
            cursor.execute(
                "DELETE FROM stonks.provider_listing WHERE provider_listing_id = %s",
                (listing_id,),
            )
        if publication_ids:
            cursor.execute(
                "DELETE FROM stonks.tech_indicators_publication "
                "WHERE publication_id = ANY(%s::uuid[])",
                (publication_ids,),
            )
        if run_ids:
            cursor.execute(
                "DELETE FROM core.stored_object WHERE run_id = ANY(%s::uuid[])",
                (run_ids,),
            )
            cursor.execute(
                "DELETE FROM core.core_run WHERE run_id = ANY(%s::uuid[])",
                (run_ids,),
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
