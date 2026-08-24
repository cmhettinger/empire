from __future__ import annotations

import json
import os
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pypdf import PdfReader

from empire_core import ObjectStore, RunService
from empire_stonks_tech_indicators import (
    ReportOutcome,
    TechIndicatorsBackfillScope,
    TechIndicatorsConfig,
    TechIndicatorsDailyScope,
    run_tech_indicators_backfill,
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


def test_phase_9_runner_vertical_from_append_through_resumed_backfill() -> None:
    if any(not os.environ.get(name) for name in DATABASE_ENVIRONMENT):
        pytest.skip("Empire database environment is not configured.")
    work = EmpireDatabase.connect_from_env()
    core_connection = EmpireDatabase.connect_from_env()
    object_connection = EmpireDatabase.connect_from_env()
    cleanup = EmpireDatabase.connect_from_env()
    marker = uuid4().hex[:12].upper()
    runner = f"pytest.j98.{marker}"
    listing_id: UUID | None = None
    benchmark_id: UUID | None = None
    appended_date = None
    source_run_ids: list[UUID] = []
    stored_paths: list[tuple[Path, Path]] = []
    try:
        cursor = work.cursor()
        cursor.execute(
            """
            SELECT listing.provider_listing_id, max(daily.trading_date)
            FROM stonks.ohlcv_daily AS daily
            JOIN stonks.provider_listing AS listing
              USING (provider_listing_id)
            WHERE listing.provider_code = 'YAHOO'
              AND listing.market = 'XIDX'
              AND listing.ticker = 'SPX'
              AND listing.status = 'ACTIVE'
            GROUP BY listing.provider_listing_id
            """
        )
        benchmark_id, baseline_date = cursor.fetchone()
        appended_date = baseline_date + timedelta(days=1)
        start_date = baseline_date - timedelta(days=1000)
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
            VALUES ('EODDATA', 'NASDAQ', %s, 'ACTIVE', '{"type":"Equity"}')
            RETURNING provider_listing_id
            """,
            (f"J98{marker}",),
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
            (listing_id, start_date, baseline_date),
        )
        source_run_ids.extend(
            _insert_source_evidence(
                cursor=cursor,
                effective_dates=(baseline_date, appended_date),
                runner=runner,
            )
        )
        work.commit()

        object_store = ObjectStore.from_connection(object_connection)
        services = {
            "run_service": RunService.from_connection(core_connection),
            "connection": work,
            "lock_connection_factory": EmpireDatabase.connect_from_env,
            "object_store": object_store,
            "config": TechIndicatorsConfig(),
            "run_type": "manual",
            "runner": runner,
        }

        baseline = run_tech_indicators_daily(
            **services,
            scope=TechIndicatorsDailyScope(
                effective_date=baseline_date,
                provider_listing_ids=(listing_id, benchmark_id),
            ),
        )
        assert baseline.outcome is ReportOutcome.PASS

        cursor.execute(
            """
            INSERT INTO stonks.ohlcv_daily (
                provider_listing_id, trading_date, open, high, low, close,
                volume, change, changepct, typ, hl_range, oc_range
            )
            VALUES (%s, %s, 10, 12, 9, 11, 100, NULL, NULL,
                    10.66666667, 3, 1)
            """,
            (benchmark_id, appended_date),
        )
        work.commit()
        daily_scope = TechIndicatorsDailyScope(
            effective_date=appended_date,
            provider_listing_ids=(benchmark_id,),
        )
        appended = run_tech_indicators_daily(**services, scope=daily_scope)
        assert appended.outcome is ReportOutcome.PASS
        assert _publication_kind(work, appended.publication_id) == "DAILY"
        assert _published_count(work, listing_id) == 1001

        publication_count = _publication_count(work, benchmark_id)
        noop = run_tech_indicators_daily(**services, scope=daily_scope)
        assert noop.outcome is ReportOutcome.NO_OP
        assert noop.publication_id is None
        assert _publication_count(work, benchmark_id) == publication_count

        correction_date = start_date + timedelta(days=500)
        cursor.execute(
            """
            UPDATE stonks.ohlcv_daily
            SET close = 10.5, typ = 10.5, oc_range = 0.5
            WHERE provider_listing_id = %s AND trading_date = %s
            """,
            (listing_id, correction_date),
        )
        work.commit()
        corrected = run_tech_indicators_daily(
            **services,
            scope=TechIndicatorsDailyScope(
                effective_date=baseline_date,
                provider_listing_ids=(listing_id, benchmark_id),
            ),
        )
        assert corrected.outcome is ReportOutcome.PASS
        assert _publication_kind(work, corrected.publication_id) == "CORRECTION"
        cursor.execute(
            """
            SELECT close
            FROM stonks.ohlcv_daily_tech_indicators
            WHERE provider_listing_id = %s AND trading_date = %s
            """,
            (listing_id, correction_date),
        )
        assert str(cursor.fetchone()[0]) == "10.5000000000"

        rebuilt = run_tech_indicators_backfill(
            **services,
            scope=TechIndicatorsBackfillScope(
                effective_date=baseline_date,
                start_date=start_date,
                end_date=baseline_date,
                provider_listing_ids=(listing_id,),
                batch_size=1000,
                rebuild=True,
            ),
        )
        assert rebuilt.outcome is ReportOutcome.PASS
        assert _publication_kind(work, rebuilt.publication_id) == (
            "VERSION_REBUILD"
        )
        assert _published_count(work, listing_id) == 1001

        backfill_scope = TechIndicatorsBackfillScope(
            effective_date=baseline_date,
            start_date=start_date,
            end_date=baseline_date,
            provider_listing_ids=(listing_id,),
            batch_size=1000,
        )
        partial = run_tech_indicators_backfill(
            **services,
            scope=backfill_scope,
            batch_limit=1,
        )
        assert partial.outcome is ReportOutcome.PARTIAL
        assert partial.resume_cursor is not None
        assert partial.resume_cursor.batch_number == 1
        assert _published_count(work, listing_id) == 1001

        resumed = run_tech_indicators_backfill(
            **services,
            scope=TechIndicatorsBackfillScope(
                effective_date=baseline_date,
                start_date=start_date,
                end_date=baseline_date,
                provider_listing_ids=(listing_id,),
                batch_size=1000,
                resume_cursor=partial.resume_cursor,
            ),
        )
        assert resumed.outcome is ReportOutcome.PASS
        assert resumed.publication_id == partial.publication_id
        assert _publication_kind(work, resumed.publication_id) == "BACKFILL"
        assert _published_count(work, listing_id) == 1001
        cursor.execute(
            """
            SELECT status, completed_batch_count, staged_payload_row_count
            FROM stonks.tech_indicators_publication
            WHERE publication_id = %s
            """,
            (resumed.publication_id,),
        )
        assert cursor.fetchone() == ("PUBLISHED", 2, 1001)

        expected = (
            (baseline, "succeeded", "PASS"),
            (appended, "succeeded", "PASS"),
            (noop, "succeeded", "NO_OP"),
            (corrected, "succeeded", "PASS"),
            (rebuilt, "succeeded", "PASS"),
            (partial, "failed", "PARTIAL"),
            (resumed, "succeeded", "PASS"),
        )
        for result, core_status, outcome in expected:
            _assert_core_and_reports(
                connection=work,
                object_store=object_store,
                result=result,
                core_status=core_status,
                outcome=outcome,
            )
    finally:
        for connection in (work, core_connection, object_connection):
            try:
                connection.rollback()
            finally:
                connection.close()
        cleanup_cursor = cleanup.cursor()
        cleanup_cursor.execute(
            "SELECT run_id FROM core.core_run WHERE runner = %s",
            (runner,),
        )
        workflow_run_ids = [row[0] for row in cleanup_cursor.fetchall()]
        all_run_ids = [*source_run_ids, *workflow_run_ids]
        publication_ids: list[UUID] = []
        if workflow_run_ids:
            cleanup_cursor.execute(
                "SELECT publication_id "
                "FROM stonks.tech_indicators_publication "
                "WHERE run_id = ANY(%s::uuid[])",
                (workflow_run_ids,),
            )
            publication_ids = [row[0] for row in cleanup_cursor.fetchall()]
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
                (Path(root) / key / filename, Path(root))
                for root, key, filename in cleanup_cursor.fetchall()
            ]
        if publication_ids:
            cleanup_cursor.execute(
                "DELETE FROM stonks.tech_indicators_publication_listing "
                "WHERE publication_id = ANY(%s::uuid[])",
                (publication_ids,),
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
                    f"DELETE FROM {table_name} "
                    "WHERE provider_listing_id = %s",
                    (benchmark_id,),
                )
        if benchmark_id is not None and appended_date is not None:
            cleanup_cursor.execute(
                "DELETE FROM stonks.ohlcv_daily "
                "WHERE provider_listing_id = %s AND trading_date = %s",
                (benchmark_id, appended_date),
            )
        if publication_ids:
            cleanup_cursor.execute(
                "DELETE FROM stonks.tech_indicators_publication "
                "WHERE publication_id = ANY(%s::uuid[])",
                (publication_ids,),
            )
        if workflow_run_ids:
            cleanup_cursor.execute(
                "DELETE FROM core.stored_object "
                "WHERE run_id = ANY(%s::uuid[])",
                (workflow_run_ids,),
            )
        if all_run_ids:
            cleanup_cursor.execute(
                "DELETE FROM core.core_run WHERE run_id = ANY(%s::uuid[])",
                (all_run_ids,),
            )
        cleanup_cursor.execute(
            "SELECT count(*) FROM core.core_run WHERE runner = %s",
            (runner,),
        )
        assert cleanup_cursor.fetchone() == (0,)
        cleanup_cursor.execute(
            "SELECT count(*) FROM stonks.provider_listing WHERE ticker = %s",
            (f"J98{marker}",),
        )
        assert cleanup_cursor.fetchone() == (0,)
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


def _insert_source_evidence(
    *, cursor: object, effective_dates: tuple[object, ...], runner: str
) -> tuple[UUID, ...]:
    run_ids: list[UUID] = []
    for effective_date in effective_dates:
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
            cursor.execute(  # type: ignore[union-attr]
                """
                INSERT INTO core.core_run (
                    domain, job_name, subject_key, effective_date, run_type,
                    status, runner, summary, completed_at
                ) VALUES (
                    'stonks', %s, 'pytest', %s, 'manual', 'succeeded',
                    %s, %s::jsonb, now()
                )
                RETURNING run_id
                """,
                (job_name, effective_date, runner, json.dumps(summary)),
            )
            run_ids.append(cursor.fetchone()[0])  # type: ignore[union-attr]
    return tuple(run_ids)


def _publication_kind(connection: object, publication_id: UUID) -> str:
    cursor = connection.cursor()  # type: ignore[union-attr]
    cursor.execute(
        "SELECT publication_kind FROM stonks.tech_indicators_publication "
        "WHERE publication_id = %s",
        (publication_id,),
    )
    return cursor.fetchone()[0]


def _publication_count(connection: object, listing_id: UUID) -> int:
    cursor = connection.cursor()  # type: ignore[union-attr]
    cursor.execute(
        "SELECT count(DISTINCT publication_id) "
        "FROM stonks.tech_indicators_publication_listing "
        "WHERE provider_listing_id = %s",
        (listing_id,),
    )
    return cursor.fetchone()[0]


def _published_count(connection: object, listing_id: UUID) -> int:
    cursor = connection.cursor()  # type: ignore[union-attr]
    cursor.execute(
        "SELECT count(*) FROM stonks.ohlcv_daily_tech_indicators "
        "WHERE provider_listing_id = %s",
        (listing_id,),
    )
    return cursor.fetchone()[0]


def _assert_core_and_reports(
    *,
    connection: object,
    object_store: ObjectStore,
    result: object,
    core_status: str,
    outcome: str,
) -> None:
    cursor = connection.cursor()  # type: ignore[union-attr]
    cursor.execute(
        """
        SELECT status, summary ->> 'outcome', summary ->> 'json_report_object_id',
               summary ->> 'pdf_report_object_id'
        FROM core.core_run
        WHERE run_id = %s
        """,
        (result.run_id,),
    )
    assert cursor.fetchone() == (
        core_status,
        outcome,
        str(result.json_report_object_id),
        str(result.pdf_report_object_id),
    )
    cursor.execute(
        """
        SELECT object_id, object_kind, metadata ->> 'outcome'
        FROM core.stored_object
        WHERE run_id = %s
        ORDER BY object_kind
        """,
        (result.run_id,),
    )
    assert cursor.fetchall() == [
        (
            result.pdf_report_object_id,
            "stonks_tech_indicators_pdf_report",
            outcome,
        ),
        (
            result.json_report_object_id,
            "stonks_tech_indicators_report",
            outcome,
        ),
    ]
    report = json.loads(object_store.get_bytes(result.json_report_object_id))
    assert report["identity"]["run_id"] == str(result.run_id)
    assert report["outcome"] == outcome
    pdf_bytes = object_store.get_bytes(result.pdf_report_object_id)
    reader = PdfReader(BytesIO(pdf_bytes))
    assert 1 <= len(reader.pages) <= 25
    document_text = "\n".join(page.extract_text() for page in reader.pages)
    assert outcome.replace("_", " ") in document_text
