from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from empire_core import ObjectStore, RunService
from empire_stonks_tech_indicators import (
    ReportOutcome,
    TechIndicatorsConfig,
    TechIndicatorsDailyScope,
    run_tech_indicators_daily,
)
from test_report_storage import FakeObjectRepository


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


@pytest.mark.parametrize("dry_run", (True, False))
def test_daily_runner_sequences_real_postgresql_core_and_reports(
    tmp_path: Path,
    dry_run: bool,
) -> None:
    if any(not os.environ.get(name) for name in DATABASE_ENVIRONMENT):
        pytest.skip("Empire database environment is not configured.")
    work = EmpireDatabase.connect_from_env()
    core_connection = EmpireDatabase.connect_from_env()
    object_connection = EmpireDatabase.connect_from_env()
    cleanup = EmpireDatabase.connect_from_env()
    listing_id: UUID | None = None
    source_run_ids: list[UUID] = []
    result = None
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
            INSERT INTO stonks.provider_listing (
                provider_code, market, ticker, status, metadata
            )
            VALUES ('EODDATA', 'NASDAQ', %s, 'ACTIVE', '{"type": "Equity"}')
            RETURNING provider_listing_id
            """,
            (f"J93DRY{marker}",),
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

        object_store = (
            ObjectStore(FakeObjectRepository(tmp_path))
            if dry_run
            else ObjectStore.from_connection(object_connection)
        )
        result = run_tech_indicators_daily(
            run_service=RunService.from_connection(core_connection),
            connection=work,
            lock_connection_factory=EmpireDatabase.connect_from_env,
            object_store=object_store,
            config=TechIndicatorsConfig(),
            scope=TechIndicatorsDailyScope(
                effective_date=effective_date,
                provider_listing_ids=(listing_id,),
                dry_run=dry_run,
            ),
            run_type="manual",
            runner="pytest",
        )

        assert result.status == "succeeded"
        assert result.outcome is ReportOutcome.PASS
        assert (result.publication_id is None) is dry_run
        if dry_run:
            assert len(object_store.repository.objects) == 2
        cursor.execute(
            "SELECT count(*) FROM stonks.tech_indicators_publication "
            "WHERE run_id = %s",
            (result.run_id,),
        )
        assert cursor.fetchone() == ((0,) if dry_run else (1,))
        for table_name in (
            "stonks.ohlcv_daily_tech_indicators_a",
            "stonks.ohlcv_daily_tech_indicators_b",
        ):
            cursor.execute(
                f"SELECT count(*) FROM {table_name} "
                "WHERE provider_listing_id = %s",
                (listing_id,),
            )
            observed = cursor.fetchone()[0]
            if dry_run:
                assert observed == 0
            else:
                assert observed in {0, 1}
        if not dry_run:
            cursor.execute(
                "SELECT status FROM stonks.tech_indicators_publication "
                "WHERE publication_id = %s",
                (result.publication_id,),
            )
            assert cursor.fetchone() == ("PUBLISHED",)
            cursor.execute(
                "SELECT count(*) FROM stonks.ohlcv_daily_tech_indicators "
                "WHERE provider_listing_id = %s",
                (listing_id,),
            )
            assert cursor.fetchone() == (1,)
        cursor.execute(
            "SELECT status FROM core.core_run WHERE run_id = %s",
            (result.run_id,),
        )
        assert cursor.fetchone() == ("succeeded",)
        assert benchmark_id is not None
    finally:
        for connection in (work, core_connection, object_connection):
            try:
                connection.rollback()
            finally:
                connection.close()
        cleanup_cursor = cleanup.cursor()
        stored_paths: list[tuple[Path, Path]] = []
        if result is not None and result.run_id is not None:
            cleanup_cursor.execute(
                """
                SELECT root.base_uri, object.object_key, object.filename
                FROM core.stored_object AS object
                JOIN core.storage_root AS root USING (storage_root_id)
                WHERE object.run_id = %s
                """,
                (result.run_id,),
            )
            stored_paths = [
                (Path(base_uri) / object_key / filename, Path(base_uri))
                for base_uri, object_key, filename in cleanup_cursor.fetchall()
            ]
        if listing_id is not None:
            cleanup_cursor.execute(
                "DELETE FROM stonks.provider_listing "
                "WHERE provider_listing_id = %s",
                (listing_id,),
            )
        if result is not None and result.publication_id is not None:
            cleanup_cursor.execute(
                "DELETE FROM stonks.tech_indicators_publication "
                "WHERE publication_id = %s",
                (result.publication_id,),
            )
        if result is not None and result.run_id is not None:
            cleanup_cursor.execute(
                "DELETE FROM core.stored_object WHERE run_id = %s",
                (result.run_id,),
            )
        run_ids = [*source_run_ids]
        if result is not None and result.run_id is not None:
            run_ids.append(result.run_id)
        if run_ids:
            cleanup_cursor.execute(
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
