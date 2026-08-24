from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest

from empire_stonks_tech_indicators.backfill_publication import (
    BackfillPublicationProgress,
    complete_backfill_listing,
    record_backfill_batch,
)
from empire_stonks_tech_indicators.backfill_scope import (
    TechIndicatorsBackfillCursor,
)
from empire_stonks_tech_indicators.exceptions import TechIndicatorsWorkflowError
from empire_stonks_tech_indicators.persistence import (
    SlotWriteCounts,
    TechIndicatorsPayloadSlot,
)
from empire_stonks_tech_indicators.queries import EligibleListing


class FakeCursor:
    def __init__(self, *, rowcount: int = 1, fetched: object = None) -> None:
        self.rowcount = rowcount
        self.fetched = fetched
        self.executions: list[tuple[str, object]] = []

    def execute(self, sql: str, parameters: object = None) -> None:
        self.executions.append((sql, parameters))

    def fetchone(self) -> object:
        return self.fetched


def test_record_batch_advances_exactly_once_with_cumulative_counts() -> None:
    publication_id = uuid4()
    listing_id = uuid4()
    cursor = FakeCursor()
    progress = BackfillPublicationProgress(
        publication_id,
        2,
        2000,
        TechIndicatorsBackfillCursor(
            listing_id, date(2026, 8, 23), 2
        ),
        1700,
        200,
        100,
        3,
    )

    observed = record_backfill_batch(
        cursor=cursor,
        progress=progress,
        provider_listing_id=listing_id,
        trading_date=date(2026, 8, 24),
        row_count=1000,
        writes=SlotWriteCounts(800, 150, 50),
    )

    assert observed.completed_batch_count == 3
    assert observed.staged_payload_row_count == 3000
    assert observed.cursor.batch_number == 3
    assert observed.cursor.provider_listing_id == listing_id
    assert (
        observed.inserted_row_count,
        observed.updated_row_count,
        observed.equivalent_row_count,
        observed.deleted_row_count,
    ) == (2500, 350, 150, 3)


def test_existing_complete_membership_must_match_exact_image() -> None:
    publication_id = uuid4()
    listing = EligibleListing(
        provider_listing_id=uuid4(),
        provider_code="EODDATA",
        market="NASDAQ",
        ticker="TEST",
        instrument_type_code="EQUITY",
        status="ACTIVE",
        first_trading_date=date(2026, 8, 1),
        last_trading_date=date(2026, 8, 2),
        source_observation_count=2,
    )
    cursor = FakeCursor(
        rowcount=0,
        fetched=("B", "TECH_INDICATORS_V1", None, None, 0, 0, None),
    )

    with pytest.raises(
        TechIndicatorsWorkflowError,
        match="does not match the complete image",
    ):
        complete_backfill_listing(
            cursor=cursor,
            publication_id=publication_id,
            listing=listing,
            target_slot=TechIndicatorsPayloadSlot.B,
            calculation_version="TECH_INDICATORS_V1",
            benchmark_provider_listing_id=None,
        )
