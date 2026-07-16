"""Acquisition, parsing, and transactional OHLCV import boundary."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, TypeAlias

from empire_core import RunContext

from empire_stonks_ohlcv.daily_bars import DailyBarWriteInput, upsert_daily_bars
from empire_stonks_ohlcv.exceptions import OHLCVWorkflowError
from empire_stonks_ohlcv.listings import upsert_provider_listings
from empire_stonks_ohlcv.results import (
    AcquiredObject,
    ParsedListingBatch,
    ProviderImportResult,
)
from empire_stonks_ohlcv.source_snapshots import upsert_provider_source_snapshot


AcquireProviderObjects: TypeAlias = Callable[
    [RunContext],
    tuple[AcquiredObject, ...],
]
ParseProviderObjects: TypeAlias = Callable[
    [tuple[AcquiredObject, ...]],
    tuple[ParsedListingBatch, ...],
]


def execute_import_boundary(
    *,
    connection: Any,
    run_context: RunContext,
    provider_code: str,
    acquire: AcquireProviderObjects,
    parse: ParseProviderObjects,
    parser_versions: Mapping[str, str] | None = None,
) -> ProviderImportResult:
    """Acquire, parse, and atomically register/write one provider input.

    Core raw-object storage performed by ``acquire`` is independently durable.
    Source-snapshot membership, provider listings, and daily bars commit once as
    one database transaction after parsing succeeds.
    """

    _validate_boundary_inputs(
        run_context=run_context,
        provider_code=provider_code,
        acquire=acquire,
        parse=parse,
    )
    try:
        acquired_objects = acquire(run_context)
        _validate_acquired_objects(acquired_objects)
        resolved_parser_versions = _validate_parser_versions(
            parser_versions,
            acquired_objects=acquired_objects,
        )
    except Exception as exc:
        raise OHLCVWorkflowError("acquisition") from exc

    try:
        parsed_batches = parse(acquired_objects)
        _validate_parsed_batches(parsed_batches)
    except Exception as exc:
        raise OHLCVWorkflowError("parsing") from exc

    try:
        with connection.cursor() as cursor:
            for acquired_object in sorted(
                acquired_objects,
                key=lambda item: (
                    item.source_code,
                    item.checksum_sha256,
                    str(item.object_id),
                ),
            ):
                upsert_provider_source_snapshot(
                    cursor=cursor,
                    provider_code=provider_code,
                    acquired_object=acquired_object,
                    parser_version=resolved_parser_versions.get(
                        acquired_object.source_code
                    ),
                )
            listing_result = upsert_provider_listings(
                cursor=cursor,
                listings=(batch.listing for batch in parsed_batches),
            )
            bar_counts = upsert_daily_bars(
                cursor=cursor,
                bars=(
                    DailyBarWriteInput(
                        provider_listing_id=(
                            listing_result.provider_listing_id_for(batch.listing)
                        ),
                        bar=bar,
                    )
                    for batch in parsed_batches
                    for bar in batch.bars
                ),
            )
            import_result = ProviderImportResult(
                provider_code=provider_code,
                acquired_objects=acquired_objects,
                listing_counts=listing_result.counts,
                bar_counts=bar_counts,
            )
        connection.commit()
    except Exception as exc:
        connection.rollback()
        raise OHLCVWorkflowError("persistence") from exc
    return import_result


def _validate_boundary_inputs(
    *,
    run_context: RunContext,
    provider_code: str,
    acquire: AcquireProviderObjects,
    parse: ParseProviderObjects,
) -> None:
    if not isinstance(run_context, RunContext):
        raise TypeError("run_context must be a Core RunContext.")
    if run_context.domain != "stonks" or run_context.status != "started":
        raise ValueError("run_context must be an active stonks run.")
    if not isinstance(provider_code, str) or provider_code != provider_code.upper():
        raise ValueError("provider_code must be uppercase.")
    if not callable(acquire):
        raise TypeError("acquire must be callable.")
    if not callable(parse):
        raise TypeError("parse must be callable.")


def _validate_acquired_objects(acquired_objects: object) -> None:
    if not isinstance(acquired_objects, tuple) or not acquired_objects:
        raise TypeError("acquire must return a non-empty tuple of AcquiredObject.")
    if any(not isinstance(item, AcquiredObject) for item in acquired_objects):
        raise TypeError("acquire must return only AcquiredObject records.")
    object_ids = [item.object_id for item in acquired_objects]
    if len(set(object_ids)) != len(object_ids):
        raise ValueError("acquire returned duplicate Core object IDs.")


def _validate_parsed_batches(parsed_batches: object) -> None:
    if not isinstance(parsed_batches, tuple):
        raise TypeError("parse must return a tuple of ParsedListingBatch.")
    if any(not isinstance(item, ParsedListingBatch) for item in parsed_batches):
        raise TypeError("parse must return only ParsedListingBatch records.")


def _validate_parser_versions(
    parser_versions: Mapping[str, str] | None,
    *,
    acquired_objects: tuple[AcquiredObject, ...],
) -> dict[str, str]:
    if parser_versions is None:
        return {}
    if not isinstance(parser_versions, Mapping):
        raise TypeError("parser_versions must be a mapping.")
    source_codes = {item.source_code for item in acquired_objects}
    unknown = set(parser_versions) - source_codes
    if unknown:
        raise ValueError("parser_versions contains an unacquired source code.")
    if any(not isinstance(value, str) for value in parser_versions.values()):
        raise TypeError("parser_versions values must be strings.")
    return dict(parser_versions)
