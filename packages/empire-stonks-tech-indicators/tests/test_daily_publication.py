from __future__ import annotations

from datetime import date
from uuid import UUID

import pytest

from empire_stonks_tech_indicators.daily_publication import (
    DailyCandidateListing,
    create_daily_candidate,
    prepare_daily_candidate,
    select_daily_target_slots,
)
from empire_stonks_tech_indicators.persistence import TechIndicatorsPayloadSlot


LISTING_A = UUID("11111111-1111-4111-8111-111111111111")
LISTING_B = UUID("22222222-2222-4222-8222-222222222222")
RUN_ID = UUID("33333333-3333-4333-8333-333333333333")
PUBLICATION_ID = UUID("44444444-4444-4444-8444-444444444444")
BENCHMARK_ID = UUID("55555555-5555-4555-8555-555555555555")
JSON_ID = UUID("66666666-6666-4666-8666-666666666666")
PDF_ID = UUID("77777777-7777-4777-8777-777777777777")
TRADING_DATE = date(2026, 8, 21)


class Cursor:
    def __init__(self, rows: tuple[tuple[object, ...], ...] = ()) -> None:
        self.rows = rows
        self.executions: list[tuple[str, object]] = []
        self.rowcount = 1

    def execute(self, sql: str, parameters: object = None) -> None:
        self.executions.append((" ".join(sql.split()), parameters))

    def fetchall(self) -> list[tuple[object, ...]]:
        return list(self.rows)


def _membership(listing_id: UUID) -> DailyCandidateListing:
    return DailyCandidateListing(
        provider_listing_id=listing_id,
        target_slot=TechIndicatorsPayloadSlot.A,
        source_coverage_start_date=TRADING_DATE,
        source_coverage_end_date=TRADING_DATE,
        source_row_count=1,
        benchmark_provider_listing_id=BENCHMARK_ID,
    )


def test_daily_target_slots_reuse_active_and_choose_a_initially() -> None:
    cursor = Cursor(((LISTING_A, "B"),))

    result = select_daily_target_slots(
        cursor=cursor,
        provider_listing_ids=(LISTING_B, LISTING_A),
    )

    assert result == {
        LISTING_A: TechIndicatorsPayloadSlot.B,
        LISTING_B: TechIndicatorsPayloadSlot.A,
    }
    assert "WHERE is_active" in cursor.executions[0][0]


def test_create_daily_candidate_writes_building_parent_then_memberships() -> None:
    cursor = Cursor()

    result = create_daily_candidate(
        cursor=cursor,
        publication_kind="CORRECTION",
        effective_date=TRADING_DATE,
        run_id=RUN_ID,
        scope_hash="a" * 64,
        memberships=(_membership(LISTING_A),),
        benchmark_provider_listing_id=BENCHMARK_ID,
        benchmark_coverage_start_date=TRADING_DATE,
        benchmark_coverage_end_date=TRADING_DATE,
        benchmark_source_row_count=1,
        publication_id=PUBLICATION_ID,
    )

    assert result == PUBLICATION_ID
    assert len(cursor.executions) == 2
    assert "status" in cursor.executions[0][0]
    assert "'BUILDING'" in cursor.executions[0][0]
    assert "publication_listing" in cursor.executions[1][0]
    assert "'PRESENT'" in cursor.executions[1][0]


def test_prepare_daily_candidate_sets_exact_terminal_candidate_facts() -> None:
    cursor = Cursor()

    prepare_daily_candidate(
        cursor=cursor,
        publication_id=PUBLICATION_ID,
        expected_listing_count=1,
        expected_source_row_count=2,
        expected_payload_row_count=2,
        inserted_row_count=1,
        updated_row_count=0,
        deleted_row_count=0,
        equivalent_row_count=1,
        warning_count=0,
        failure_count=0,
        json_report_object_id=JSON_ID,
        pdf_report_object_id=PDF_ID,
    )

    sql, parameters = cursor.executions[0]
    assert "status = 'PREPARED'" in sql
    assert "source_validated_at = now()" in sql
    assert parameters[-3:] == (JSON_ID, PDF_ID, PUBLICATION_ID)


def test_candidate_rejects_incomplete_benchmark_coverage() -> None:
    with pytest.raises(ValueError, match="benchmark coverage is incomplete"):
        create_daily_candidate(
            cursor=Cursor(),
            publication_kind="DAILY",
            effective_date=TRADING_DATE,
            run_id=RUN_ID,
            scope_hash="a" * 64,
            memberships=(_membership(LISTING_A),),
            benchmark_provider_listing_id=BENCHMARK_ID,
            benchmark_coverage_start_date=None,
            benchmark_coverage_end_date=None,
            benchmark_source_row_count=None,
            publication_id=PUBLICATION_ID,
        )
