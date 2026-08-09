from __future__ import annotations

import os
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterator
from uuid import UUID, uuid4

import pytest

from empire_stonks_tech_indicators import (
    BenchmarkConfig,
    TechIndicatorsScope,
    TechIndicatorsValidationError,
    decide_source_readiness,
    iter_source_bar_pages,
    iter_state_comparison_pages,
    load_spx_benchmark_history,
    resolve_spx_benchmark,
    select_eligible_listings,
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


@pytest.fixture
def database_connection() -> Iterator[object]:
    if any(not os.environ.get(name) for name in DATABASE_ENVIRONMENT):
        pytest.skip("Empire database environment is not configured.")

    connection = EmpireDatabase.connect_from_env()
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


def _insert_listing(
    cursor: object,
    *,
    provider_code: str,
    market: str,
    ticker: str,
    status: str = "ACTIVE",
    metadata_json: str | None = None,
) -> UUID:
    cursor.execute(  # type: ignore[union-attr]
        """
        INSERT INTO stonks.provider_listing (
            provider_code,
            market,
            ticker,
            status,
            metadata
        )
        VALUES (%s, %s, %s, %s, %s::jsonb)
        RETURNING provider_listing_id
        """,
        (provider_code, market, ticker, status, metadata_json),
    )
    return cursor.fetchone()[0]  # type: ignore[union-attr,no-any-return]


def _insert_bar(cursor: object, provider_listing_id: UUID, trading_date: date) -> None:
    cursor.execute(  # type: ignore[union-attr]
        """
        INSERT INTO stonks.ohlcv_daily (
            provider_listing_id,
            trading_date,
            open,
            high,
            low,
            close,
            volume,
            change,
            changepct,
            typ,
            hl_range,
            oc_range
        )
        VALUES (
            %s, %s, 10, 12, 9, 11, 100, NULL, NULL,
            round((12::numeric + 9 + 11) / 3, 8), 3, 1
        )
        """,
        (provider_listing_id, trading_date),
    )


def _insert_exact_bar(
    cursor: object,
    *,
    provider_listing_id: UUID,
    trading_date: date,
    open_value: Decimal,
    high_value: Decimal,
    low_value: Decimal,
    close_value: Decimal,
    volume: Decimal | None,
) -> None:
    cursor.execute(  # type: ignore[union-attr]
        """
        INSERT INTO stonks.ohlcv_daily (
            provider_listing_id,
            trading_date,
            open,
            high,
            low,
            close,
            volume,
            change,
            changepct,
            typ,
            hl_range,
            oc_range
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, NULL, NULL,
            round((%s + %s + %s) / 3, 8),
            round(%s - %s, 8),
            round(%s - %s, 8)
        )
        """,
        (
            provider_listing_id,
            trading_date,
            open_value,
            high_value,
            low_value,
            close_value,
            volume,
            high_value,
            low_value,
            close_value,
            high_value,
            low_value,
            close_value,
            open_value,
        ),
    )


def _publish_drifted_state(
    cursor: object,
    *,
    provider_listing_id: UUID,
    first_date: date,
    drift_date: date,
    marker: str,
) -> None:
    cursor.execute(  # type: ignore[union-attr]
        """
        INSERT INTO stonks.ohlcv_daily_tech_indicators_a (
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
            source.provider_listing_id,
            source.trading_date,
            CASE WHEN source.trading_date = %s THEN 1 ELSE 99 END,
            CASE
                WHEN source.trading_date = %s
                    THEN 'TECH_INDICATORS_OLD'
                ELSE 'TECH_INDICATORS_V1'
            END,
            now(),
            source.open,
            source.high,
            source.low,
            source.close,
            CASE
                WHEN source.trading_date = %s THEN 999::numeric
                ELSE source.volume
            END,
            0,
            0
        FROM stonks.ohlcv_daily AS source
        WHERE source.provider_listing_id = %s
          AND source.trading_date IN (%s, %s)
        """,
        (
            first_date,
            drift_date,
            drift_date,
            provider_listing_id,
            first_date,
            drift_date,
        ),
    )
    cursor.execute(  # type: ignore[union-attr]
        """
        INSERT INTO core.core_run (
            domain,
            job_name,
            subject_key,
            run_type,
            status,
            runner
        )
        VALUES (
            'stonks',
            'stonks_tech_indicators_backfill',
            %s,
            'manual',
            'succeeded',
            'pytest'
        )
        RETURNING run_id
        """,
        (f"i35:{marker}",),
    )
    run_id = cursor.fetchone()[0]  # type: ignore[union-attr]
    cursor.execute(  # type: ignore[union-attr]
        """
        SELECT storage_root_id
        FROM core.storage_root
        WHERE root_name = 'global'
          AND is_active
        """
    )
    storage_root_id = cursor.fetchone()[0]  # type: ignore[union-attr]
    object_ids: list[UUID] = []
    for filename, logical_name, content_type, object_kind, checksum in (
        (
            "report.json",
            "tech_indicators_backfill_report",
            "application/json",
            "stonks_tech_indicators_report",
            "a" * 64,
        ),
        (
            "report.pdf",
            "tech_indicators_backfill_pdf_report",
            "application/pdf",
            "stonks_tech_indicators_pdf_report",
            "b" * 64,
        ),
    ):
        cursor.execute(  # type: ignore[union-attr]
            """
            INSERT INTO core.stored_object (
                run_id,
                storage_root_id,
                object_key,
                filename,
                object_scope,
                domain,
                logical_name,
                content_type,
                object_kind,
                size_bytes,
                checksum_sha256,
                metadata
            )
            VALUES (
                %s, %s, %s, %s, 'run', 'stonks', %s, %s, %s,
                1, %s, '{}'::jsonb
            )
            RETURNING object_id
            """,
            (
                run_id,
                storage_root_id,
                f"stonks/tech-indicators/tests/{marker}",
                filename,
                logical_name,
                content_type,
                object_kind,
                checksum,
            ),
        )
        object_ids.append(cursor.fetchone()[0])  # type: ignore[union-attr]
    cursor.execute(  # type: ignore[union-attr]
        """
        INSERT INTO stonks.tech_indicators_publication (
            publication_kind,
            status,
            calculation_version
        )
        VALUES ('BACKFILL', 'BUILDING', 'TECH_INDICATORS_V1')
        RETURNING publication_id
        """
    )
    publication_id = cursor.fetchone()[0]  # type: ignore[union-attr]
    cursor.execute(  # type: ignore[union-attr]
        """
        UPDATE stonks.tech_indicators_publication
        SET
            publication_method = 'STAGED',
            scope_schema_version = 1,
            scope_hash = repeat('a', 64),
            run_id = %s,
            benchmark_required = false,
            expected_listing_count = 1,
            expected_source_row_count = 4,
            expected_payload_row_count = 2,
            inserted_row_count = 2,
            updated_row_count = 0,
            deleted_row_count = 0,
            equivalent_row_count = 0,
            warning_count = 0,
            failure_count = 0,
            completed_batch_count = 0,
            staged_payload_row_count = 0,
            json_report_object_id = %s,
            pdf_report_object_id = %s,
            source_validated_at = now(),
            prepared_at = now(),
            status = 'PREPARED',
            updated_at = now()
        WHERE publication_id = %s
        """,
        (run_id, object_ids[0], object_ids[1], publication_id),
    )
    cursor.execute(  # type: ignore[union-attr]
        """
        INSERT INTO stonks.tech_indicators_publication_listing (
            publication_id,
            provider_listing_id,
            action,
            target_slot,
            calculation_version,
            source_coverage_start_date,
            source_coverage_end_date,
            source_row_count,
            payload_row_count,
            candidate_completed_at
        )
        VALUES (
            %s, %s, 'PRESENT', 'A', 'TECH_INDICATORS_V1',
            %s, %s, 2, 2, now()
        )
        """,
        (publication_id, provider_listing_id, first_date, drift_date),
    )
    cursor.execute(  # type: ignore[union-attr]
        """
        UPDATE stonks.tech_indicators_publication
        SET status = 'PUBLISHED', published_at = now(), updated_at = now()
        WHERE publication_id = %s
        """,
        (publication_id,),
    )
    cursor.execute(  # type: ignore[union-attr]
        """
        UPDATE stonks.tech_indicators_publication_listing
        SET is_active = true, activated_at = now(), updated_at = now()
        WHERE publication_id = %s
          AND provider_listing_id = %s
        """,
        (publication_id, provider_listing_id),
    )


def test_eligible_listing_query_enforces_policy_status_dates_and_history(
    database_connection: object,
) -> None:
    marker = uuid4().hex[:12].upper()
    first_date = date(2026, 1, 2)
    second_date = date(2026, 1, 5)

    with database_connection.cursor() as cursor:  # type: ignore[union-attr]
        active_id = _insert_listing(
            cursor,
            provider_code="EODDATA",
            market="NASDAQ",
            ticker=f"I31A{marker}",
            metadata_json='{"type": " equity "}',
        )
        short_id = _insert_listing(
            cursor,
            provider_code="EODDATA",
            market="NYSE",
            ticker=f"I31S{marker}",
            metadata_json='{"type": "Equity"}',
        )
        amex_id = _insert_listing(
            cursor,
            provider_code="EODDATA",
            market="AMEX",
            ticker=f"I31E{marker}",
            metadata_json='{"type": "EQUITY"}',
        )
        inactive_id = _insert_listing(
            cursor,
            provider_code="STOOQ",
            market="nasdaq",
            ticker=f"I31I{marker}.US",
            status="INACTIVE",
        )
        stooq_nyse_id = _insert_listing(
            cursor,
            provider_code="STOOQ",
            market="nyse",
            ticker=f"I31N{marker}.US",
        )
        stooq_nysemkt_id = _insert_listing(
            cursor,
            provider_code="STOOQ",
            market="nysemkt",
            ticker=f"I31K{marker}.US",
        )
        unsupported_type_id = _insert_listing(
            cursor,
            provider_code="EODDATA",
            market="AMEX",
            ticker=f"I31T{marker}",
            metadata_json='{"type": "ETF"}',
        )
        non_string_type_id = _insert_listing(
            cursor,
            provider_code="EODDATA",
            market="AMEX",
            ticker=f"I31J{marker}",
            metadata_json='{"type": 1}',
        )
        missing_type_id = _insert_listing(
            cursor,
            provider_code="EODDATA",
            market="NYSE",
            ticker=f"I31X{marker}",
            metadata_json='{}',
        )
        unsupported_market_id = _insert_listing(
            cursor,
            provider_code="STOOQ",
            market="NASDAQ",
            ticker=f"I31M{marker}.US",
        )
        unsupported_yahoo_id = _insert_listing(
            cursor,
            provider_code="YAHOO",
            market="XIDX",
            ticker=f"I31Y{marker}",
            metadata_json=f'{{"YahooTicker": "^{marker}"}}',
        )
        _insert_bar(cursor, active_id, first_date)
        _insert_bar(cursor, active_id, second_date)
        _insert_bar(cursor, short_id, second_date)
        _insert_bar(cursor, inactive_id, second_date)

        explicit_ids = (
            active_id,
            short_id,
            amex_id,
            inactive_id,
            stooq_nyse_id,
            stooq_nysemkt_id,
            unsupported_type_id,
            non_string_type_id,
            missing_type_id,
            unsupported_market_id,
            unsupported_yahoo_id,
        )
        active = select_eligible_listings(
            cursor=cursor,
            scope=TechIndicatorsScope(provider_listing_ids=explicit_ids),
        )
        by_id = {item.provider_listing_id: item for item in active}
        assert set(by_id) == {
            active_id,
            short_id,
            amex_id,
            stooq_nyse_id,
            stooq_nysemkt_id,
        }
        assert by_id[active_id].source_observation_count == 2
        assert by_id[short_id].source_observation_count == 1
        assert by_id[amex_id].source_observation_count == 0
        assert by_id[stooq_nyse_id].source_observation_count == 0
        assert by_id[stooq_nysemkt_id].source_observation_count == 0
        assert by_id[active_id].has_minimum_history(2) is True
        assert by_id[short_id].has_minimum_history(2) is False

        scoped = select_eligible_listings(
            cursor=cursor,
            scope=TechIndicatorsScope(
                provider_listing_ids=(active_id, short_id),
                start_date=second_date,
                end_date=second_date,
            ),
        )
        assert [item.source_observation_count for item in scoped] == [1, 1]
        assert all(item.first_trading_date == second_date for item in scoped)
        assert all(item.last_trading_date == second_date for item in scoped)

        inactive = select_eligible_listings(
            cursor=cursor,
            scope=TechIndicatorsScope(
                provider_listing_ids=(inactive_id,),
                include_inactive=True,
            ),
        )
        assert len(inactive) == 1
        assert inactive[0].status == "INACTIVE"
        assert inactive[0].source_observation_count == 1

        cursor.execute(
            """
            SELECT provider_listing_id
            FROM stonks.provider_listing
            WHERE provider_code = 'YAHOO'
              AND market = 'XIDX'
              AND ticker = 'SPX'
              AND status = 'ACTIVE'
            """
        )
        spx_id = cursor.fetchone()[0]
        spx = select_eligible_listings(
            cursor=cursor,
            scope=TechIndicatorsScope(
                provider_listing_ids=(spx_id,),
                start_date=date(2099, 1, 1),
                end_date=date(2099, 1, 1),
            ),
        )
        assert len(spx) == 1
        assert spx[0].provider_code == "YAHOO"
        assert spx[0].market == "XIDX"
        assert spx[0].ticker == "SPX"
        assert spx[0].instrument_type_code == "EQUITY_INDEX"
        assert spx[0].source_observation_count == 0


def test_source_bar_reader_preserves_order_gaps_nulls_and_negative_values(
    database_connection: object,
) -> None:
    marker = uuid4().hex[:12].upper()
    first_date = date(2026, 1, 2)
    gap_date = date(2026, 1, 6)
    other_date = date(2026, 1, 5)

    with database_connection.cursor() as cursor:  # type: ignore[union-attr]
        first_listing_id = _insert_listing(
            cursor,
            provider_code="EODDATA",
            market="NASDAQ",
            ticker=f"I32A{marker}",
            metadata_json='{"type": "Equity"}',
        )
        second_listing_id = _insert_listing(
            cursor,
            provider_code="EODDATA",
            market="NASDAQ",
            ticker=f"I32B{marker}",
            metadata_json='{"type": "Equity"}',
        )
        _insert_exact_bar(
            cursor,
            provider_listing_id=first_listing_id,
            trading_date=first_date,
            open_value=Decimal("-3"),
            high_value=Decimal("-1"),
            low_value=Decimal("-4"),
            close_value=Decimal("-2"),
            volume=None,
        )
        _insert_exact_bar(
            cursor,
            provider_listing_id=first_listing_id,
            trading_date=gap_date,
            open_value=Decimal("10"),
            high_value=Decimal("12"),
            low_value=Decimal("9"),
            close_value=Decimal("11"),
            volume=Decimal("100.25"),
        )
        _insert_exact_bar(
            cursor,
            provider_listing_id=second_listing_id,
            trading_date=other_date,
            open_value=Decimal("20"),
            high_value=Decimal("21"),
            low_value=Decimal("18"),
            close_value=Decimal("19"),
            volume=Decimal("0"),
        )

        pages = list(
            iter_source_bar_pages(
                cursor=cursor,
                scope=TechIndicatorsScope(
                    provider_listing_ids=(
                        second_listing_id,
                        first_listing_id,
                    ),
                    start_date=first_date,
                    end_date=gap_date,
                ),
                page_size=1000,
            )
        )

        assert len(pages) == 1
        expected_keys = sorted(
            [
                (first_listing_id, first_date),
                (first_listing_id, gap_date),
                (second_listing_id, other_date),
            ]
        )
        assert [
            (bar.provider_listing_id, bar.trading_date) for bar in pages[0]
        ] == expected_keys
        by_key = {
            (bar.provider_listing_id, bar.trading_date): bar for bar in pages[0]
        }
        assert by_key[first_listing_id, first_date].open == Decimal(
            "-3.0000000000"
        )
        assert by_key[first_listing_id, first_date].close == Decimal(
            "-2.0000000000"
        )
        assert by_key[first_listing_id, first_date].volume is None
        assert by_key[first_listing_id, gap_date].volume == Decimal("100.25000000")
        assert by_key[second_listing_id, other_date].volume == Decimal("0E-8")


def test_spx_resolver_validates_live_identity_and_fails_closed_on_drift(
    database_connection: object,
) -> None:
    config = BenchmarkConfig()

    with database_connection.cursor() as cursor:  # type: ignore[union-attr]
        resolved = resolve_spx_benchmark(cursor=cursor, config=config)
        assert resolved.provider_code == "YAHOO"
        assert resolved.market == "XIDX"
        assert resolved.ticker == "SPX"

        cursor.execute(
            """
            UPDATE stonks.provider_listing
            SET status = 'INACTIVE'
            WHERE provider_listing_id = %s
            """,
            (resolved.provider_listing_id,),
        )
        with pytest.raises(TechIndicatorsValidationError, match="ACTIVE"):
            resolve_spx_benchmark(cursor=cursor, config=config)
        cursor.execute(
            """
            UPDATE stonks.provider_listing
            SET status = 'ACTIVE', instrument_type_code = 'UNKNOWN'
            WHERE provider_listing_id = %s
            """,
            (resolved.provider_listing_id,),
        )
        with pytest.raises(
            TechIndicatorsValidationError,
            match="instrument type has drifted",
        ):
            resolve_spx_benchmark(cursor=cursor, config=config)
        cursor.execute(
            """
            UPDATE stonks.provider_listing
            SET
                instrument_type_code = 'EQUITY_INDEX',
                metadata = metadata || '{"YahooTicker": "^DRIFT"}'::jsonb
            WHERE provider_listing_id = %s
            """,
            (resolved.provider_listing_id,),
        )
        with pytest.raises(
            TechIndicatorsValidationError,
            match="YahooTicker metadata has drifted",
        ):
            resolve_spx_benchmark(cursor=cursor, config=config)
        cursor.execute(
            """
            UPDATE stonks.provider_listing
            SET metadata = metadata || '{"YahooTicker": "^GSPC"}'::jsonb
            WHERE provider_listing_id = %s
            """,
            (resolved.provider_listing_id,),
        )
        assert resolve_spx_benchmark(cursor=cursor, config=config) == resolved


def test_benchmark_history_reads_only_exact_live_spx_dates(
    database_connection: object,
) -> None:
    config = BenchmarkConfig()

    with database_connection.cursor() as cursor:  # type: ignore[union-attr]
        resolved = resolve_spx_benchmark(cursor=cursor, config=config)
        cursor.execute(
            """
            SELECT trading_date, next_trading_date
            FROM (
                SELECT
                    trading_date,
                    lead(trading_date) OVER (ORDER BY trading_date)
                        AS next_trading_date
                FROM stonks.ohlcv_daily
                WHERE provider_listing_id = %s
            ) AS dated
            WHERE next_trading_date > trading_date + 1
            ORDER BY trading_date
            LIMIT 1
            """,
            (resolved.provider_listing_id,),
        )
        gap_bounds = cursor.fetchone()
        assert gap_bounds is not None
        first_date, last_date = gap_bounds
        missing_date = first_date + timedelta(days=1)

        cursor.execute(
            """
            SELECT trading_date, close
            FROM stonks.ohlcv_daily
            WHERE provider_listing_id = %s
              AND trading_date BETWEEN %s AND %s
            ORDER BY trading_date
            """,
            (resolved.provider_listing_id, first_date, last_date),
        )
        expected = cursor.fetchall()

        history = load_spx_benchmark_history(
            cursor=cursor,
            config=config,
            start_date=first_date,
            end_date=last_date,
            page_size=1000,
        )

        assert history.benchmark == resolved
        assert [
            (bar.trading_date, bar.close) for bar in history.bars
        ] == expected
        assert missing_date not in {trading_date for trading_date, _ in expected}
        assert history.bar_on(missing_date) is None
        assert missing_date not in history.close_by_date()
        assert all(
            bar.provider_listing_id == resolved.provider_listing_id
            for bar in history.bars
        )


def test_state_comparison_detects_published_drift_and_earliest_restart(
    database_connection: object,
) -> None:
    marker = uuid4().hex[:12].upper()
    dates = (
        date(2026, 2, 2),
        date(2026, 2, 3),
        date(2026, 2, 4),
        date(2026, 2, 5),
    )

    with database_connection.cursor() as cursor:  # type: ignore[union-attr]
        listing_id = _insert_listing(
            cursor,
            provider_code="EODDATA",
            market="NASDAQ",
            ticker=f"I35{marker}",
            metadata_json='{"type": "Equity"}',
        )
        for index, trading_date in enumerate(dates):
            base = Decimal(10 + index)
            _insert_exact_bar(
                cursor,
                provider_listing_id=listing_id,
                trading_date=trading_date,
                open_value=base,
                high_value=base + 2,
                low_value=base - 1,
                close_value=base + 1,
                volume=Decimal(100 + index),
            )
        _publish_drifted_state(
            cursor,
            provider_listing_id=listing_id,
            first_date=dates[0],
            drift_date=dates[2],
            marker=marker,
        )

        pages = list(
            iter_state_comparison_pages(
                cursor=cursor,
                scope=TechIndicatorsScope(
                    provider_listing_ids=(listing_id,),
                    start_date=dates[1],
                    end_date=dates[3],
                ),
                calculation_version="TECH_INDICATORS_V1",
                page_size=1000,
            )
        )

        assert len(pages) == 1
        assert len(pages[0]) == 1
        comparison = pages[0][0]
        assert comparison.provider_listing_id == listing_id
        assert comparison.source_observation_count == 4
        assert comparison.last_technical_date == dates[2]
        assert comparison.tail_append_count == 1
        assert comparison.earliest_tail_append_date == dates[3]
        assert comparison.missing_tech_row_count == 1
        assert comparison.earliest_missing_tech_date == dates[1]
        assert comparison.source_copy_drift_count == 1
        assert comparison.earliest_source_copy_drift_date == dates[2]
        assert comparison.history_count_drift_count == 1
        assert comparison.earliest_history_count_drift_date == dates[2]
        assert comparison.version_drift_count == 1
        assert comparison.earliest_version_drift_date == dates[2]
        assert comparison.earliest_recalculation_date == dates[0]

        equivalent_pages = list(
            iter_state_comparison_pages(
                cursor=cursor,
                scope=TechIndicatorsScope(
                    provider_listing_ids=(listing_id,),
                    start_date=dates[0],
                    end_date=dates[0],
                ),
                calculation_version="TECH_INDICATORS_V1",
                page_size=1000,
            )
        )
        assert equivalent_pages[0][0].is_equivalent is True
        assert equivalent_pages[0][0].earliest_recalculation_date is None


def test_source_readiness_uses_same_date_live_coverage_and_core_evidence(
    database_connection: object,
) -> None:
    effective_date = date(2026, 8, 3)

    with database_connection.cursor() as cursor:  # type: ignore[union-attr]
        cursor.execute(
            """
            SELECT listing.provider_listing_id
            FROM stonks.provider_listing AS listing
            INNER JOIN stonks.ohlcv_daily AS daily
                ON daily.provider_listing_id = listing.provider_listing_id
               AND daily.trading_date = %s
            WHERE listing.provider_code = 'EODDATA'
              AND listing.market = 'NASDAQ'
              AND listing.status = 'ACTIVE'
              AND jsonb_typeof(listing.metadata) = 'object'
              AND jsonb_typeof(listing.metadata -> 'type') = 'string'
              AND upper(btrim(listing.metadata ->> 'type')) = 'EQUITY'
            ORDER BY listing.ticker, listing.provider_listing_id
            LIMIT 1
            """,
            (effective_date,),
        )
        listing_id = cursor.fetchone()[0]
        scope = TechIndicatorsScope(
            provider_listing_ids=(listing_id,),
            start_date=effective_date,
            end_date=effective_date,
        )

        ready = decide_source_readiness(
            cursor=cursor,
            scope=scope,
            effective_date=effective_date,
            benchmark_config=BenchmarkConfig(),
        )

        assert ready.ready is True
        assert ready.selected_listing_count == 1
        assert ready.effective_date_bar_count == 1
        assert ready.supported_subject_bar_count == 1
        assert ready.benchmark_bar_present is True
        assert ready.eoddata_source_run_id is not None
        assert ready.yahoo_source_run_id is not None
        assert ready.reasons == ()

        unsupported_date = date(2099, 1, 5)
        not_ready = decide_source_readiness(
            cursor=cursor,
            scope=TechIndicatorsScope(
                provider_listing_ids=(listing_id,),
                start_date=unsupported_date,
                end_date=unsupported_date,
            ),
            effective_date=unsupported_date,
            benchmark_config=BenchmarkConfig(),
        )

        assert not_ready.ready is False
        assert not_ready.effective_date_bar_count == 0
        assert not_ready.spx_bar_required is False
        assert not_ready.yahoo_evidence_required is False
        assert not_ready.reasons == (
            "EODDATA_SOURCE_EVIDENCE_MISSING",
        )
