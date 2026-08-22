"""Caller-transaction-owned persistence for technical-indicator payload slots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any, Iterable, Sequence
from uuid import UUID

from empire_stonks_tech_indicators.config import (
    DEFAULT_WRITE_BATCH_SIZE,
    HARD_MAX_TRANSACTION_ROWS,
    MAX_WRITE_BATCH_SIZE,
    MIN_WRITE_BATCH_SIZE,
)
from empire_stonks_tech_indicators.exceptions import (
    TechIndicatorsPersistenceError,
)
from empire_stonks_tech_indicators.models import (
    PYTHON_FEATURE_FIELDS,
    FeatureRow,
)


_KEY_COLUMNS = ("provider_listing_id", "trading_date")
_METADATA_COLUMNS = (
    "relative_strength_benchmark_provider_listing_id",
    "history_observation_count",
    "calculation_version",
    "run_id",
    "calculated_at",
)
_SOURCE_COLUMNS = ("open", "high", "low", "close", "volume")
_WRITE_COLUMNS = (
    *_KEY_COLUMNS,
    *_METADATA_COLUMNS,
    *_SOURCE_COLUMNS,
    *PYTHON_FEATURE_FIELDS,
)
_LIFECYCLE_COLUMNS = ("created_at", "updated_at")
_INTEGER_FEATURE_COLUMNS = (
    "consecutive_up_days",
    "consecutive_down_days",
)
_FLOAT_FEATURE_COLUMNS = tuple(
    column
    for column in PYTHON_FEATURE_FIELDS
    if column not in _INTEGER_FEATURE_COLUMNS
)
_EXACT_EQUIVALENCE_COLUMNS = (
    "relative_strength_benchmark_provider_listing_id",
    "history_observation_count",
    "calculation_version",
    *_SOURCE_COLUMNS,
    *_INTEGER_FEATURE_COLUMNS,
)
_ABSOLUTE_TOLERANCE = "1e-12::double precision"
_RELATIVE_TOLERANCE = "1e-10::double precision"


class TechIndicatorsPayloadSlot(StrEnum):
    """One whitelisted physical technical-indicator payload slot."""

    A = "A"
    B = "B"

    @property
    def table_name(self) -> str:
        return f"stonks.ohlcv_daily_tech_indicators_{self.value.lower()}"


@dataclass(frozen=True, order=True)
class FeatureRowKey:
    """Natural key used to copy an existing payload row between slots."""

    provider_listing_id: UUID
    trading_date: date

    def __post_init__(self) -> None:
        if not isinstance(self.provider_listing_id, UUID):
            raise TypeError("provider_listing_id must be a UUID.")
        if type(self.trading_date) is not date:
            raise TypeError("trading_date must be a date.")


@dataclass(frozen=True)
class SlotWriteCounts:
    """Logical row outcomes from one bounded slot write operation."""

    inserted_rows: int = 0
    updated_rows: int = 0
    unchanged_rows: int = 0

    def __post_init__(self) -> None:
        for field_name in (
            "inserted_rows",
            "updated_rows",
            "unchanged_rows",
        ):
            value = getattr(self, field_name)
            if type(value) is not int:
                raise TypeError(f"{field_name} must be an integer.")
            if value < 0:
                raise ValueError(f"{field_name} must be non-negative.")

    @property
    def total_rows(self) -> int:
        return self.inserted_rows + self.updated_rows + self.unchanged_rows

    def to_dict(self) -> dict[str, int]:
        return {
            "inserted_rows": self.inserted_rows,
            "updated_rows": self.updated_rows,
            "unchanged_rows": self.unchanged_rows,
            "total_rows": self.total_rows,
        }


def upsert_feature_rows(
    *,
    cursor: Any,
    slot: TechIndicatorsPayloadSlot,
    rows: Iterable[FeatureRow],
    batch_size: int = DEFAULT_WRITE_BATCH_SIZE,
) -> SlotWriteCounts:
    """Bulk upsert validated calculation rows into one explicit payload slot.

    The caller owns the cursor and transaction. Generated and lifecycle columns
    are omitted from inserts. An equivalent candidate keeps the stored values,
    calculation run, and lifecycle timestamps without issuing an update.
    """

    table_name = _slot_table_name(slot)
    validated_batch_size = _validate_batch_size(batch_size)
    prepared = _prepare_feature_rows(rows)
    if not prepared:
        return SlotWriteCounts()

    sql = _upsert_sql(table_name)
    totals = SlotWriteCounts()
    for batch in _batches(prepared, validated_batch_size):
        cursor.execute(sql, _feature_row_arrays(batch))
        totals = _add_counts(
            totals,
            _counts_from_merge_actions(cursor.fetchall(), len(batch)),
        )
    return totals


def copy_feature_rows_between_slots(
    *,
    cursor: Any,
    source_slot: TechIndicatorsPayloadSlot,
    target_slot: TechIndicatorsPayloadSlot,
    keys: Iterable[FeatureRowKey],
    batch_size: int = DEFAULT_WRITE_BATCH_SIZE,
) -> SlotWriteCounts:
    """Copy exact existing rows, including lifecycle fields, between slots.

    Every requested source key must exist. The caller owns rollback if this
    fail-closed operation or any later work in the transaction raises. Copied
    rows are logical unchanged/equivalent outcomes regardless of whether the
    target slot physically inserts, repairs, or already contains the row.
    """

    source_table = _slot_table_name(source_slot)
    target_table = _slot_table_name(target_slot)
    if source_slot is target_slot:
        raise TechIndicatorsPersistenceError(
            "Source and target technical-indicator slots must differ."
        )
    validated_batch_size = _validate_batch_size(batch_size)
    prepared = _prepare_feature_row_keys(keys)
    if not prepared:
        return SlotWriteCounts()

    _require_all_source_rows(
        cursor=cursor,
        source_table=source_table,
        keys=prepared,
    )
    sql = _copy_sql(source_table, target_table)
    totals = SlotWriteCounts()
    for batch in _batches(prepared, validated_batch_size):
        cursor.execute(sql, _key_arrays(batch))
        _counts_from_merge_actions(cursor.fetchall(), len(batch))
        totals = _add_counts(
            totals,
            SlotWriteCounts(unchanged_rows=len(batch)),
        )
    return totals


def _slot_table_name(slot: TechIndicatorsPayloadSlot) -> str:
    if not isinstance(slot, TechIndicatorsPayloadSlot):
        raise TypeError("slot must be a TechIndicatorsPayloadSlot.")
    return slot.table_name


def _validate_batch_size(batch_size: int) -> int:
    if type(batch_size) is not int:
        raise TypeError("batch_size must be an integer.")
    if not MIN_WRITE_BATCH_SIZE <= batch_size <= MAX_WRITE_BATCH_SIZE:
        raise TechIndicatorsPersistenceError(
            "batch_size must be between "
            f"{MIN_WRITE_BATCH_SIZE} and {MAX_WRITE_BATCH_SIZE}."
        )
    return batch_size


def _prepare_feature_rows(rows: Iterable[FeatureRow]) -> tuple[FeatureRow, ...]:
    prepared = tuple(rows)
    if len(prepared) > HARD_MAX_TRANSACTION_ROWS:
        raise TechIndicatorsPersistenceError(
            "Technical-indicator slot writes cannot exceed "
            f"{HARD_MAX_TRANSACTION_ROWS:,} rows per transaction."
        )
    if any(not isinstance(row, FeatureRow) for row in prepared):
        raise TypeError("rows must contain only FeatureRow records.")
    identities = [
        (row.source.provider_listing_id, row.source.trading_date)
        for row in prepared
    ]
    _require_unique_identities(identities)
    return tuple(
        sorted(
            prepared,
            key=lambda row: (
                str(row.source.provider_listing_id),
                row.source.trading_date,
            ),
        )
    )


def _prepare_feature_row_keys(
    keys: Iterable[FeatureRowKey],
) -> tuple[FeatureRowKey, ...]:
    prepared = tuple(keys)
    if len(prepared) > HARD_MAX_TRANSACTION_ROWS:
        raise TechIndicatorsPersistenceError(
            "Technical-indicator slot copies cannot exceed "
            f"{HARD_MAX_TRANSACTION_ROWS:,} rows per transaction."
        )
    if any(not isinstance(key, FeatureRowKey) for key in prepared):
        raise TypeError("keys must contain only FeatureRowKey records.")
    _require_unique_identities(
        [(key.provider_listing_id, key.trading_date) for key in prepared]
    )
    return tuple(
        sorted(
            prepared,
            key=lambda key: (str(key.provider_listing_id), key.trading_date),
        )
    )


def _require_unique_identities(
    identities: Sequence[tuple[UUID, date]],
) -> None:
    if len(identities) != len(set(identities)):
        raise TechIndicatorsPersistenceError(
            "Technical-indicator slot input contains duplicate natural keys."
        )


def _batches(values: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for offset in range(0, len(values), size):
        yield values[offset : offset + size]


def _feature_row_values(row: FeatureRow) -> tuple[object, ...]:
    return (
        row.source.provider_listing_id,
        row.source.trading_date,
        row.relative_strength_benchmark_provider_listing_id,
        row.history_observation_count,
        row.calculation_version,
        row.run_id,
        row.calculated_at,
        row.source.open,
        row.source.high,
        row.source.low,
        row.source.close,
        row.source.volume,
        *(getattr(row, column) for column in PYTHON_FEATURE_FIELDS),
    )


def _feature_row_arrays(rows: Sequence[FeatureRow]) -> tuple[list[object], ...]:
    values = tuple(_feature_row_values(row) for row in rows)
    return tuple(
        [row[index] for row in values]
        for index in range(len(_WRITE_COLUMNS))
    )


def _key_arrays(keys: Sequence[FeatureRowKey]) -> tuple[list[object], list[object]]:
    return (
        [key.provider_listing_id for key in keys],
        [key.trading_date for key in keys],
    )


def _require_all_source_rows(
    *,
    cursor: Any,
    source_table: str,
    keys: Sequence[FeatureRowKey],
) -> None:
    cursor.execute(
        f"""
        SELECT count(*)
        FROM {source_table} AS source
        JOIN unnest(%s::uuid[], %s::date[])
            AS requested(provider_listing_id, trading_date)
          USING (provider_listing_id, trading_date)
        """,
        _key_arrays(keys),
    )
    row = cursor.fetchone()
    if row is None or row[0] != len(keys):
        found = 0 if row is None else row[0]
        raise TechIndicatorsPersistenceError(
            "Technical-indicator source slot is missing requested copy rows: "
            f"expected {len(keys)}, found {found}."
        )


def _postgres_type(column: str) -> str:
    if column in {
        "provider_listing_id",
        "relative_strength_benchmark_provider_listing_id",
        "run_id",
    }:
        return "uuid"
    if column == "trading_date":
        return "date"
    if column == "calculated_at":
        return "timestamptz"
    if column in {"history_observation_count", *_INTEGER_FEATURE_COLUMNS}:
        return "integer"
    if column == "calculation_version":
        return "text"
    if column in _SOURCE_COLUMNS:
        return "numeric"
    return "double precision"


def _incoming_rows_sql() -> str:
    parameters = ",\n                ".join(
        f"%s::{_postgres_type(column)}[]" for column in _WRITE_COLUMNS
    )
    columns = ", ".join(_WRITE_COLUMNS)
    return (
        "SELECT *\n"
        "        FROM unnest(\n"
        f"                {parameters}\n"
        f"        ) AS incoming({columns})"
    )


def _float_equivalent(column: str) -> str:
    return (
        f"(target.{column} IS NULL AND incoming.{column} IS NULL)\n"
        "                OR (\n"
        f"                    target.{column} IS NOT NULL\n"
        f"                    AND incoming.{column} IS NOT NULL\n"
        f"                    AND abs(target.{column} - incoming.{column})\n"
        "                        <= greatest(\n"
        f"                            {_ABSOLUTE_TOLERANCE},\n"
        f"                            {_RELATIVE_TOLERANCE}\n"
        "                                * greatest(\n"
        f"                                    abs(target.{column}),\n"
        f"                                    abs(incoming.{column})\n"
        "                                )\n"
        "                        )\n"
        "                )"
    )


def _material_difference_sql() -> str:
    differences = [
        f"target.{column} IS DISTINCT FROM incoming.{column}"
        for column in _EXACT_EQUIVALENCE_COLUMNS
    ]
    differences.extend(
        f"NOT ({_float_equivalent(column)})"
        for column in _FLOAT_FEATURE_COLUMNS
    )
    return "\n            OR ".join(differences)


def _upsert_sql(table_name: str) -> str:
    columns = ", ".join(_WRITE_COLUMNS)
    values = ", ".join(f"incoming.{column}" for column in _WRITE_COLUMNS)
    assignments = ",\n                ".join(
        f"{column} = incoming.{column}"
        for column in _WRITE_COLUMNS
        if column not in _KEY_COLUMNS
    )
    return f"""
        MERGE INTO {table_name} AS target
        USING (
            {_incoming_rows_sql()}
        ) AS incoming
          ON target.provider_listing_id = incoming.provider_listing_id
         AND target.trading_date = incoming.trading_date
        WHEN MATCHED AND (
            {_material_difference_sql()}
        ) THEN
            UPDATE SET
                {assignments},
                updated_at = incoming.calculated_at
        WHEN NOT MATCHED THEN
            INSERT ({columns})
            VALUES ({values})
        RETURNING merge_action()
    """


def _copy_sql(source_table: str, target_table: str) -> str:
    copy_columns = (*_WRITE_COLUMNS, *_LIFECYCLE_COLUMNS)
    columns = ", ".join(copy_columns)
    values = ", ".join(f"incoming.{column}" for column in copy_columns)
    assignments = ",\n                ".join(
        f"{column} = incoming.{column}"
        for column in copy_columns
        if column not in _KEY_COLUMNS
    )
    differences = "\n            OR ".join(
        f"target.{column} IS DISTINCT FROM incoming.{column}"
        for column in copy_columns
        if column not in _KEY_COLUMNS
    )
    return f"""
        MERGE INTO {target_table} AS target
        USING (
            SELECT {values}
            FROM {source_table} AS incoming
            JOIN unnest(%s::uuid[], %s::date[])
                AS requested(provider_listing_id, trading_date)
              USING (provider_listing_id, trading_date)
        ) AS incoming
          ON target.provider_listing_id = incoming.provider_listing_id
         AND target.trading_date = incoming.trading_date
        WHEN MATCHED AND (
            {differences}
        ) THEN
            UPDATE SET
                {assignments}
        WHEN NOT MATCHED THEN
            INSERT ({columns})
            VALUES ({values})
        RETURNING merge_action()
    """


def _counts_from_merge_actions(
    action_rows: Sequence[Sequence[object]],
    input_count: int,
) -> SlotWriteCounts:
    inserted = 0
    updated = 0
    for row in action_rows:
        action = row[0]
        if action == "INSERT":
            inserted += 1
        elif action == "UPDATE":
            updated += 1
        else:
            raise TechIndicatorsPersistenceError(
                f"Unexpected technical-indicator MERGE action: {action!r}."
            )
    changed = inserted + updated
    if changed > input_count:
        raise TechIndicatorsPersistenceError(
            "Technical-indicator MERGE returned more actions than input rows."
        )
    return SlotWriteCounts(
        inserted_rows=inserted,
        updated_rows=updated,
        unchanged_rows=input_count - changed,
    )


def _add_counts(left: SlotWriteCounts, right: SlotWriteCounts) -> SlotWriteCounts:
    return SlotWriteCounts(
        inserted_rows=left.inserted_rows + right.inserted_rows,
        updated_rows=left.updated_rows + right.updated_rows,
        unchanged_rows=left.unchanged_rows + right.unchanged_rows,
    )


__all__ = [
    "FeatureRowKey",
    "SlotWriteCounts",
    "TechIndicatorsPayloadSlot",
    "copy_feature_rows_between_slots",
    "upsert_feature_rows",
]
