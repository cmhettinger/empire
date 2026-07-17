from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

from empire_stonks_ohlcv import (
    AcquiredObject,
    DailyBar,
    ImportIssue,
    ParsedListingBatch,
    ParsedProviderOutput,
    PersistenceCounts,
    ProviderImportResult,
    ProviderListing,
    ProviderSourceMetadata,
)


OBJECT_ID = UUID("12345678-1234-5678-1234-567812345678")


def _listing() -> ProviderListing:
    return ProviderListing(
        provider_code="EODDATA",
        market="Nasdaq",
        ticker="aapl.US",
        name="Apple Inc.",
        instrument_type_code="COMMON_STOCK",
    )


def _bar() -> DailyBar:
    return DailyBar(
        trading_date=date(2026, 7, 15),
        open=Decimal("210.1250000001"),
        high=Decimal("214.25"),
        low=Decimal("209.50"),
        close=Decimal("213.75"),
        volume=Decimal("1234567.50"),
    )


def _acquired_object() -> AcquiredObject:
    return AcquiredObject(
        source_code="eoddata_daily",
        object_id=OBJECT_ID,
        object_key="stonks/ohlcv/eoddata/runs/2026/07/15/run/source",
        filename="daily.csv",
        size_bytes=512,
        checksum_sha256="a" * 64,
    )


def test_provider_listing_and_daily_bar_are_json_ready() -> None:
    payload = {
        "listing": _listing().to_dict(),
        "bar": _bar().to_dict(),
    }

    assert json.loads(json.dumps(payload)) == {
        "listing": {
            "provider_code": "EODDATA",
            "market": "Nasdaq",
            "ticker": "aapl.US",
                "name": "Apple Inc.",
                "instrument_type_code": "COMMON_STOCK",
                "metadata": None,
            },
        "bar": {
            "trading_date": "2026-07-15",
            "open": "210.1250000001",
            "high": "214.25",
            "low": "209.50",
            "close": "213.75",
            "volume": "1234567.50",
        },
    }


def test_acquired_object_is_json_ready_and_immutable() -> None:
    acquired = _acquired_object()

    assert json.loads(json.dumps(acquired.to_dict())) == {
        "source_code": "eoddata_daily",
        "object_id": str(OBJECT_ID),
        "object_key": "stonks/ohlcv/eoddata/runs/2026/07/15/run/source",
        "filename": "daily.csv",
        "size_bytes": 512,
        "checksum_sha256": "a" * 64,
    }
    with pytest.raises(FrozenInstanceError):
        acquired.filename = "other.csv"  # type: ignore[misc]


def test_parsed_listing_batch_keeps_bars_attached_to_listing() -> None:
    batch = ParsedListingBatch(listing=_listing(), bars=(_bar(),))

    payload = batch.to_dict()
    assert batch.bar_count == 1
    assert payload["listing"]["ticker"] == "aapl.US"
    assert payload["bar_count"] == 1
    assert payload["bars"][0]["trading_date"] == "2026-07-15"
    json.dumps(payload)


def test_parsed_listing_batch_supports_empty_bar_tuple() -> None:
    batch = ParsedListingBatch(listing=_listing(), bars=())

    assert batch.bar_count == 0
    assert batch.to_dict()["bars"] == []


@pytest.mark.parametrize(
    ("listing", "bars", "message"),
    [
        (object(), (), "listing must be a ProviderListing"),
        (_listing(), [], "bars must be a tuple"),
        (_listing(), (object(),), "bars must contain only DailyBar"),
    ],
)
def test_parsed_listing_batch_rejects_invalid_members(
    listing: object,
    bars: object,
    message: str,
) -> None:
    with pytest.raises(TypeError, match=message):
        ParsedListingBatch(listing=listing, bars=bars)  # type: ignore[arg-type]


def test_parsed_provider_output_contains_only_shared_records_and_source_identity(
) -> None:
    source = ProviderSourceMetadata(
        source_code="eoddata_daily",
        parser_version="csv.v1",
    )
    output = ParsedProviderOutput(
        sources=(source,),
        batches=(ParsedListingBatch(listing=_listing(), bars=(_bar(),)),),
    )

    assert output.listing_count == 1
    assert output.bar_count == 1
    assert output.parser_version_for("eoddata_daily") == "csv.v1"
    assert json.loads(json.dumps(output.to_dict()))["sources"] == [
        {
            "source_code": "eoddata_daily",
            "parser_version": "csv.v1",
        }
    ]


@pytest.mark.parametrize(
    ("sources", "batches", "message"),
    [
        ([], (), "sources"),
        ((), (), "sources must not be empty"),
        ((object(),), (), "sources"),
        (
            (
                ProviderSourceMetadata("eoddata_daily", "v1"),
                ProviderSourceMetadata("eoddata_daily", "v2"),
            ),
            (),
            "unique source_code",
        ),
        ((ProviderSourceMetadata("eoddata_daily", "v1"),), [], "batches"),
        (
            (ProviderSourceMetadata("eoddata_daily", "v1"),),
            (object(),),
            "batches",
        ),
    ],
)
def test_parsed_provider_output_rejects_invalid_members(
    sources: object,
    batches: object,
    message: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        ParsedProviderOutput(  # type: ignore[arg-type]
            sources=sources,
            batches=batches,
        )


@pytest.mark.parametrize(
    ("source_code", "parser_version", "message"),
    [
        ("EODDATA_DAILY", "v1", "source_code"),
        ("eoddata/daily", "v1", "source_code"),
        ("eoddata_daily", "bad version", "parser_version"),
        ("eoddata_daily", "", "parser_version"),
    ],
)
def test_provider_source_metadata_rejects_invalid_identifiers(
    source_code: str,
    parser_version: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        ProviderSourceMetadata(
            source_code=source_code,
            parser_version=parser_version,
        )


def test_persistence_counts_are_disjoint_and_json_ready() -> None:
    counts = PersistenceCounts(
        inserted=3,
        updated=2,
        unchanged=5,
        derived_updated=4,
    )

    assert counts.input_count == 10
    assert counts.to_dict() == {
        "inserted": 3,
        "updated": 2,
        "unchanged": 5,
        "derived_updated": 4,
    }
    json.dumps(counts.to_dict())


@pytest.mark.parametrize(
    ("field_name", "invalid_value", "error_type"),
    [
        ("inserted", -1, ValueError),
        ("updated", -1, ValueError),
        ("unchanged", -1, ValueError),
        ("derived_updated", -1, ValueError),
        ("inserted", 1.5, TypeError),
        ("updated", True, TypeError),
    ],
)
def test_persistence_counts_reject_invalid_values(
    field_name: str,
    invalid_value: object,
    error_type: type[Exception],
) -> None:
    values = {
        "inserted": 0,
        "updated": 0,
        "unchanged": 0,
        "derived_updated": 0,
    }
    values[field_name] = invalid_value  # type: ignore[assignment]

    with pytest.raises(error_type, match=field_name):
        PersistenceCounts(**values)


def test_import_issue_is_structured_and_json_ready() -> None:
    issue = ImportIssue(
        code="invalid_volume",
        message="Volume must be non-negative.",
        source_code="eoddata_daily",
        record_reference="row:17",
    )

    assert json.loads(json.dumps(issue.to_dict())) == {
        "code": "invalid_volume",
        "message": "Volume must be non-negative.",
        "source_code": "eoddata_daily",
        "record_reference": "row:17",
    }


def test_provider_import_result_is_compact_and_json_ready() -> None:
    failure = ImportIssue(code="invalid_row", message="One row was rejected.")
    warning = ImportIssue(code="possible_gap", message="Weekday-shaped gap.")
    result = ProviderImportResult(
        provider_code="EODDATA",
        acquired_objects=(_acquired_object(),),
        listing_counts=PersistenceCounts(inserted=1),
        bar_counts=PersistenceCounts(
            inserted=3,
            updated=2,
            unchanged=5,
            derived_updated=1,
        ),
        rejected=1,
        failures=(failure,),
        warnings=(warning,),
    )

    payload = result.to_dict()
    assert result.accepted == 10
    assert payload["accepted"] == 10
    assert payload["rejected"] == 1
    assert payload["failure_count"] == 1
    assert payload["warning_count"] == 1
    assert payload["listing_counts"]["inserted"] == 1
    assert payload["bar_counts"]["derived_updated"] == 1
    assert "bars" not in payload
    json.dumps(payload)


def test_provider_import_result_defaults_to_empty_success() -> None:
    result = ProviderImportResult(provider_code="YAHOO")

    assert result.accepted == 0
    assert result.to_dict() == {
        "provider_code": "YAHOO",
        "acquired_objects": [],
        "listing_counts": PersistenceCounts().to_dict(),
        "bar_counts": PersistenceCounts().to_dict(),
        "accepted": 0,
        "rejected": 0,
        "failure_count": 0,
        "warning_count": 0,
        "failures": [],
        "warnings": [],
    }


@pytest.mark.parametrize(
    ("field_name", "invalid_value", "message"),
    [
        ("acquired_objects", [], "acquired_objects"),
        ("acquired_objects", (object(),), "acquired_objects"),
        ("listing_counts", object(), "listing_counts"),
        ("bar_counts", object(), "bar_counts"),
        ("rejected", -1, "rejected"),
        ("failures", [], "failures"),
        ("failures", (object(),), "failures"),
        ("warnings", [], "warnings"),
        ("warnings", (object(),), "warnings"),
    ],
)
def test_provider_import_result_rejects_invalid_members(
    field_name: str,
    invalid_value: object,
    message: str,
) -> None:
    values: dict[str, object] = {"provider_code": "EODDATA"}
    values[field_name] = invalid_value

    with pytest.raises((TypeError, ValueError), match=message):
        ProviderImportResult(**values)  # type: ignore[arg-type]
