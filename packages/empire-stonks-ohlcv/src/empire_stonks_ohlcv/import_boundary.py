"""Acquisition, parsing, and transactional OHLCV import boundary."""

from __future__ import annotations

from typing import Any

from empire_core import RunContext

from empire_stonks_ohlcv.daily_bars import DailyBarWriteInput, upsert_daily_bars
from empire_stonks_ohlcv.exceptions import OHLCVWorkflowError
from empire_stonks_ohlcv.listings import upsert_provider_listings
from empire_stonks_ohlcv.provider_contract import (
    AcquireProviderObjects,
    ParseProviderObjects,
)
from empire_stonks_ohlcv.results import (
    AcquiredObject,
    ParsedProviderOutput,
    ProviderImportResult,
)
from empire_stonks_ohlcv.source_snapshots import upsert_provider_source_snapshot


def execute_import_boundary(
    *,
    connection: Any,
    run_context: RunContext,
    provider_code: str,
    acquire: AcquireProviderObjects,
    parse: ParseProviderObjects,
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
    except Exception as exc:
        raise OHLCVWorkflowError("acquisition") from exc

    try:
        parsed_output = parse(acquired_objects)
        _validate_parsed_output(
            parsed_output,
            acquired_objects=acquired_objects,
            provider_code=provider_code,
        )
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
                    parser_version=parsed_output.parser_version_for(
                        acquired_object.source_code
                    ),
                )
            listing_result = upsert_provider_listings(
                cursor=cursor,
                listings=(batch.listing for batch in parsed_output.batches),
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
                    for batch in parsed_output.batches
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


def _validate_parsed_output(
    parsed_output: object,
    *,
    acquired_objects: tuple[AcquiredObject, ...],
    provider_code: str,
) -> None:
    if not isinstance(parsed_output, ParsedProviderOutput):
        raise TypeError("parse must return a ParsedProviderOutput.")
    acquired_source_codes = {item.source_code for item in acquired_objects}
    output_source_codes = {source.source_code for source in parsed_output.sources}
    if output_source_codes != acquired_source_codes:
        raise ValueError(
            "parsed source metadata must exactly match acquired source codes."
        )
    if any(
        batch.listing.provider_code != provider_code
        for batch in parsed_output.batches
    ):
        raise ValueError("parsed listings must match the import provider_code.")
