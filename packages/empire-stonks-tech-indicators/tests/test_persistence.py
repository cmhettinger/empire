from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from empire_stonks_tech_indicators import (
    FeatureRow,
    FeatureRowKey,
    SlotWriteCounts,
    SourceBar,
    TechIndicatorsPayloadSlot,
    TechIndicatorsPersistenceError,
    copy_feature_rows_between_slots,
    upsert_feature_rows,
)
from empire_stonks_tech_indicators.config import HARD_MAX_TRANSACTION_ROWS


class _Cursor:
    def __init__(
        self,
        *,
        fetchall_results: list[list[tuple[object, ...]]] | None = None,
        fetchone_results: list[tuple[object, ...] | None] | None = None,
    ) -> None:
        self.executions: list[tuple[str, object]] = []
        self._fetchall_results = list(fetchall_results or [])
        self._fetchone_results = list(fetchone_results or [])

    def execute(self, sql: str, parameters: object) -> None:
        self.executions.append((sql, parameters))

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._fetchall_results.pop(0)

    def fetchone(self) -> tuple[object, ...] | None:
        return self._fetchone_results.pop(0)


def _feature_row(
    *,
    provider_listing_id: UUID | None = None,
    trading_date: date = date(2025, 1, 2),
    run_id: UUID | None = None,
    return_1d_pct: float | None = None,
) -> FeatureRow:
    return FeatureRow(
        source=SourceBar(
            provider_listing_id=provider_listing_id or uuid4(),
            trading_date=trading_date,
            open=Decimal("10.0000000000"),
            high=Decimal("12.0000000000"),
            low=Decimal("9.0000000000"),
            close=Decimal("11.0000000000"),
            volume=Decimal("100.00000000"),
        ),
        history_observation_count=1,
        calculation_version="TECH_INDICATORS_V1",
        calculated_at=datetime(2026, 8, 22, 12, tzinfo=timezone.utc),
        run_id=run_id,
        return_1d_pct=return_1d_pct,
    )


def test_slot_write_counts_are_json_ready() -> None:
    counts = SlotWriteCounts(inserted_rows=2, updated_rows=3, unchanged_rows=4)

    assert counts.total_rows == 9
    assert counts.to_dict() == {
        "inserted_rows": 2,
        "updated_rows": 3,
        "unchanged_rows": 4,
        "total_rows": 9,
    }


def test_upsert_empty_input_does_not_touch_cursor() -> None:
    cursor = _Cursor()

    result = upsert_feature_rows(
        cursor=cursor,
        slot=TechIndicatorsPayloadSlot.A,
        rows=(),
    )

    assert result == SlotWriteCounts()
    assert cursor.executions == []


def test_upsert_uses_explicit_slot_and_fixed_65_column_arrays() -> None:
    row = _feature_row(run_id=uuid4(), return_1d_pct=0.25)
    cursor = _Cursor(
        fetchall_results=[[("INSERT",)]],
    )

    result = upsert_feature_rows(
        cursor=cursor,
        slot=TechIndicatorsPayloadSlot.B,
        rows=(row,),
    )

    assert result == SlotWriteCounts(inserted_rows=1)
    assert len(cursor.executions) == 1
    sql, parameters = cursor.executions[0]
    assert "MERGE INTO stonks.ohlcv_daily_tech_indicators_b" in sql
    assert "RETURNING merge_action()" in sql
    assert "created_at" not in sql
    assert "intraday_return_1d_pct" not in sql
    assert "updated_at = incoming.calculated_at" in sql
    assert isinstance(parameters, tuple)
    assert len(parameters) == 65
    assert all(len(array) == 1 for array in parameters)
    assert parameters[0] == [row.source.provider_listing_id]
    assert parameters[1] == [row.source.trading_date]


def test_upsert_no_change_predicate_uses_frozen_float_tolerance() -> None:
    cursor = _Cursor(fetchall_results=[[]])
    row = _feature_row(run_id=uuid4(), return_1d_pct=0.25)

    result = upsert_feature_rows(
        cursor=cursor,
        slot=TechIndicatorsPayloadSlot.A,
        rows=(row,),
    )

    sql = cursor.executions[0][0]
    matched_predicate = sql.split("WHEN MATCHED AND (", 1)[1].split(
        ") THEN", 1
    )[0]
    assert "1e-12::double precision" in matched_predicate
    assert "1e-10::double precision" in matched_predicate
    assert "target.return_1d_pct" in matched_predicate
    assert "target.run_id" not in matched_predicate
    assert "target.calculated_at" not in matched_predicate
    assert result == SlotWriteCounts(unchanged_rows=1)


def test_upsert_counts_actions_and_batches_deterministically() -> None:
    provider_listing_id = uuid4()
    first_date = date(2000, 1, 1)
    rows = tuple(
        _feature_row(
            provider_listing_id=provider_listing_id,
            trading_date=first_date + timedelta(days=index),
        )
        for index in reversed(range(1_001))
    )
    cursor = _Cursor(
        fetchall_results=[
            [("INSERT",), ("UPDATE",)],
            [],
        ]
    )

    result = upsert_feature_rows(
        cursor=cursor,
        slot=TechIndicatorsPayloadSlot.A,
        rows=rows,
        batch_size=1_000,
    )

    assert result == SlotWriteCounts(
        inserted_rows=1,
        updated_rows=1,
        unchanged_rows=999,
    )
    assert len(cursor.executions) == 2
    first_parameters = cursor.executions[0][1]
    second_parameters = cursor.executions[1][1]
    assert isinstance(first_parameters, tuple)
    assert isinstance(second_parameters, tuple)
    assert first_parameters[1][0] == first_date
    assert second_parameters[1][0] == first_date + timedelta(days=1_000)


@pytest.mark.parametrize("batch_size", [999, 10_001, 1.5])
def test_upsert_rejects_out_of_contract_batch_size(batch_size: object) -> None:
    with pytest.raises((TypeError, TechIndicatorsPersistenceError)):
        upsert_feature_rows(
            cursor=_Cursor(),
            slot=TechIndicatorsPayloadSlot.A,
            rows=(),
            batch_size=batch_size,  # type: ignore[arg-type]
        )


def test_upsert_rejects_unknown_slot_before_sql() -> None:
    cursor = _Cursor()

    with pytest.raises(TypeError, match="TechIndicatorsPayloadSlot"):
        upsert_feature_rows(cursor=cursor, slot="A", rows=())  # type: ignore[arg-type]

    assert cursor.executions == []


def test_upsert_rejects_duplicate_keys_before_sql() -> None:
    cursor = _Cursor()
    row = _feature_row()

    with pytest.raises(TechIndicatorsPersistenceError, match="duplicate"):
        upsert_feature_rows(
            cursor=cursor,
            slot=TechIndicatorsPayloadSlot.A,
            rows=(row, row),
        )

    assert cursor.executions == []


def test_upsert_enforces_transaction_row_ceiling_before_record_types() -> None:
    cursor = _Cursor()

    with pytest.raises(TechIndicatorsPersistenceError, match="25,000"):
        upsert_feature_rows(
            cursor=cursor,
            slot=TechIndicatorsPayloadSlot.A,
            rows=(None,) * (HARD_MAX_TRANSACTION_ROWS + 1),  # type: ignore[arg-type]
        )

    assert cursor.executions == []


def test_copy_requires_distinct_slots_before_sql() -> None:
    cursor = _Cursor()

    with pytest.raises(TechIndicatorsPersistenceError, match="must differ"):
        copy_feature_rows_between_slots(
            cursor=cursor,
            source_slot=TechIndicatorsPayloadSlot.A,
            target_slot=TechIndicatorsPayloadSlot.A,
            keys=(),
        )

    assert cursor.executions == []


def test_copy_fails_closed_when_a_source_key_is_missing() -> None:
    cursor = _Cursor(fetchone_results=[(1,)])
    keys = (
        FeatureRowKey(uuid4(), date(2025, 1, 1)),
        FeatureRowKey(uuid4(), date(2025, 1, 2)),
    )

    with pytest.raises(TechIndicatorsPersistenceError, match="expected 2, found 1"):
        copy_feature_rows_between_slots(
            cursor=cursor,
            source_slot=TechIndicatorsPayloadSlot.A,
            target_slot=TechIndicatorsPayloadSlot.B,
            keys=keys,
        )

    assert len(cursor.executions) == 1
    assert cursor.executions[0][0].lstrip().startswith("SELECT count(*)")


def test_copy_preserves_exact_payload_and_lifecycle_columns() -> None:
    key = FeatureRowKey(uuid4(), date(2025, 1, 2))
    cursor = _Cursor(
        fetchone_results=[(1,)],
        fetchall_results=[[("UPDATE",)]],
    )

    result = copy_feature_rows_between_slots(
        cursor=cursor,
        source_slot=TechIndicatorsPayloadSlot.A,
        target_slot=TechIndicatorsPayloadSlot.B,
        keys=(key,),
    )

    assert result == SlotWriteCounts(unchanged_rows=1)
    assert len(cursor.executions) == 2
    sql, parameters = cursor.executions[1]
    assert "MERGE INTO stonks.ohlcv_daily_tech_indicators_b" in sql
    assert "FROM stonks.ohlcv_daily_tech_indicators_a" in sql
    assert "created_at = incoming.created_at" in sql
    assert "updated_at = incoming.updated_at" in sql
    assert "INSERT (provider_listing_id" in sql
    assert "created_at, updated_at)" in sql
    assert "intraday_return_1d_pct" not in sql
    assert parameters == ([key.provider_listing_id], [key.trading_date])


def test_copy_counts_already_exact_rows_as_unchanged() -> None:
    key = FeatureRowKey(uuid4(), date(2025, 1, 2))
    cursor = _Cursor(fetchone_results=[(1,)], fetchall_results=[[]])

    result = copy_feature_rows_between_slots(
        cursor=cursor,
        source_slot=TechIndicatorsPayloadSlot.B,
        target_slot=TechIndicatorsPayloadSlot.A,
        keys=(key,),
    )

    assert result == SlotWriteCounts(unchanged_rows=1)


def test_unexpected_merge_action_fails_closed() -> None:
    cursor = _Cursor(fetchall_results=[[("DELETE",)]])

    with pytest.raises(TechIndicatorsPersistenceError, match="Unexpected"):
        upsert_feature_rows(
            cursor=cursor,
            slot=TechIndicatorsPayloadSlot.A,
            rows=(_feature_row(),),
        )
