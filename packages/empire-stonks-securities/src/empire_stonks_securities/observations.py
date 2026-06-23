"""Write parsed SEC rows as provider observations."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable
from uuid import UUID

from empire_core import ObjectStore
from empire_core.db.postgres import json_dumps
from empire_core.object_store.models import StoredObject

from empire_stonks_securities.acquisition import SEC_SOURCE_OBJECT_KIND
from empire_stonks_securities.parsing import (
    SEC_COMPANY_TICKERS_EXCHANGE_PROVIDER,
    SEC_COMPANY_TICKERS_PROVIDER,
    SEC_COMPANY_TICKERS_EXCHANGE_SOURCE,
    SEC_COMPANY_TICKERS_SOURCE,
    SecCompanyTickerExchangeRecord,
    SecCompanyTickerRecord,
    SecSourceParser,
    get_sec_source_parser,
)
from empire_stonks_securities.runner import DEFAULT_DAILY_SOURCE_KEYS


logger = logging.getLogger(__name__)

SEC_PROVIDER_CODE = "SEC"
SEC_SOURCE_PROVIDER_CODES = {
    SEC_COMPANY_TICKERS_EXCHANGE_SOURCE: SEC_COMPANY_TICKERS_EXCHANGE_PROVIDER,
    SEC_COMPANY_TICKERS_SOURCE: SEC_COMPANY_TICKERS_PROVIDER,
}
SEC_SOURCE_PARSER_VERSION = "sec-security-master-v1"


SecObservationRecord = SecCompanyTickerExchangeRecord | SecCompanyTickerRecord


class SecObservationWriteError(ValueError):
    """Raised when a parsed SEC row cannot be written as an observation."""


@dataclass(frozen=True)
class SecSourceFileMetadata:
    """Metadata for the cached source file backing a batch of observations."""

    source_code: str
    source_url: str | None = None
    downloaded_at: datetime | None = None
    file_path: str | None = None
    object_id: UUID | None = None
    object_key: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    etag: str | None = None
    last_modified: str | None = None


@dataclass(frozen=True)
class SecObservationWriteItem:
    """Prepared provider observation for one SEC parsed row."""

    provider_code: str
    provider_date: date | None
    observed_at: datetime | None
    object_id: UUID | None
    object_key: str | None
    source_snapshot_id: UUID | None
    source_url: str | None
    raw_key: str
    row_hash: str
    summary_json: dict[str, Any]


@dataclass(frozen=True)
class SecObservationWriteSummary:
    """Counts for one observation write batch."""

    source_code: str
    provider_code: str
    inserted_count: int
    skipped_count: int
    failed_count: int = 0

    @property
    def input_count(self) -> int:
        return self.inserted_count + self.skipped_count + self.failed_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_code": self.source_code,
            "provider_code": self.provider_code,
            "input_count": self.input_count,
            "inserted_count": self.inserted_count,
            "skipped_count": self.skipped_count,
            "failed_count": self.failed_count,
        }


@dataclass(frozen=True)
class StonksSecuritiesObservationRunResult:
    """Observation-writing result for a stonks securities source run."""

    input_run_id: str
    source_summaries: list[SecObservationWriteSummary]

    @property
    def inserted_count(self) -> int:
        return sum(summary.inserted_count for summary in self.source_summaries)

    @property
    def skipped_count(self) -> int:
        return sum(summary.skipped_count for summary in self.source_summaries)

    @property
    def failed_count(self) -> int:
        return sum(summary.failed_count for summary in self.source_summaries)

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_run_id": self.input_run_id,
            "inserted_count": self.inserted_count,
            "skipped_count": self.skipped_count,
            "failed_count": self.failed_count,
            "source_summaries": [summary.to_dict() for summary in self.source_summaries],
        }


def write_sec_observations(
    *,
    connection: Any,
    records: Iterable[SecObservationRecord],
    source_metadata: SecSourceFileMetadata | None = None,
) -> SecObservationWriteSummary:
    """Write parsed SEC rows into stonks.provider_observation idempotently."""

    record_list = list(records)
    prepared = [
        build_sec_observation(record, source_metadata=source_metadata)
        for record in record_list
    ]
    source_code = (
        source_metadata.source_code
        if source_metadata is not None
        else _single_source_code(record.source_code for record in record_list)
    )
    provider_code = _provider_code_for_source(source_code)
    source_snapshot_id: UUID | None = None

    inserted_count = 0
    skipped_count = 0
    failed_count = 0

    with connection.cursor() as cursor:
        ensure_sec_observation_providers(cursor)
        source_snapshot_id = upsert_provider_source_snapshot(
            cursor=cursor,
            provider_code=provider_code,
            source_metadata=source_metadata,
        )
        for item in prepared:
            try:
                cursor.execute(
                    """
                    INSERT INTO stonks.provider_observation (
                        provider_code,
                        provider_date,
                        observed_at,
                        object_id,
                        object_key,
                        source_snapshot_id,
                        source_url,
                        raw_key,
                        summary_json
                    )
                    VALUES (
                        %s, %s,
                        COALESCE(%s::timestamptz, now()),
                        %s, %s, %s, %s, %s, %s::jsonb
                    )
                    ON CONFLICT (provider_code, raw_key) WHERE raw_key IS NOT NULL
                    DO NOTHING
                    RETURNING provider_observation_id
                    """,
                    (
                        item.provider_code,
                        item.provider_date,
                        item.observed_at,
                        item.object_id,
                        item.object_key,
                        source_snapshot_id,
                        item.source_url,
                        item.raw_key,
                        json_dumps(item.summary_json),
                    ),
                )
                if cursor.fetchone() is None:
                    skipped_count += 1
                else:
                    inserted_count += 1
            except Exception:
                failed_count += 1
                raise

    connection.commit()
    return SecObservationWriteSummary(
        source_code=source_code,
        provider_code=provider_code,
        inserted_count=inserted_count,
        skipped_count=skipped_count,
        failed_count=failed_count,
    )


def upsert_provider_source_snapshot(
    *,
    cursor: Any,
    provider_code: str,
    source_metadata: SecSourceFileMetadata | None,
) -> UUID | None:
    """Upsert canonical source content identity and link the stored object to it."""

    if source_metadata is None or not source_metadata.sha256:
        return None

    cursor.execute(
        """
        INSERT INTO stonks.provider_source_snapshot (
            provider_code,
            source_code,
            content_sha256,
            first_seen_object_id,
            first_seen_run_id,
            parser_version
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            (SELECT run_id FROM core.stored_object WHERE object_id = %s),
            %s
        )
        ON CONFLICT ON CONSTRAINT uq_provider_source_snapshot_identity
        DO NOTHING
        RETURNING source_snapshot_id
        """,
        (
            provider_code,
            source_metadata.source_code,
            source_metadata.sha256,
            source_metadata.object_id,
            source_metadata.object_id,
            SEC_SOURCE_PARSER_VERSION,
        ),
    )
    row = cursor.fetchone()
    if row is None:
        cursor.execute(
            """
            SELECT source_snapshot_id
            FROM stonks.provider_source_snapshot
            WHERE provider_code = %s
              AND source_code = %s
              AND content_sha256 = %s
            """,
            (
                provider_code,
                source_metadata.source_code,
                source_metadata.sha256,
            ),
        )
        row = cursor.fetchone()
    source_snapshot_id = row[0] if row is not None else None
    if source_snapshot_id is None or source_metadata.object_id is None:
        return source_snapshot_id

    cursor.execute(
        """
        INSERT INTO stonks.provider_source_snapshot_object (
            source_snapshot_id,
            object_id
        )
        VALUES (%s, %s)
        ON CONFLICT ON CONSTRAINT uq_provider_source_snapshot_object_object
        DO NOTHING
        """,
        (source_snapshot_id, source_metadata.object_id),
    )
    return source_snapshot_id


def run_stonks_securities_daily_observation_writer(
    *,
    connection: Any,
    object_store: ObjectStore,
    input_run_id: str | UUID,
    source_codes: Iterable[str] = DEFAULT_DAILY_SOURCE_KEYS,
) -> StonksSecuritiesObservationRunResult:
    """Parse cached daily SEC source objects and write provider observations."""

    parsed_run_id = input_run_id if isinstance(input_run_id, UUID) else UUID(str(input_run_id))
    summaries: list[SecObservationWriteSummary] = []
    for source_code in source_codes:
        parser = get_sec_source_parser(source_code)
        stored = find_sec_source_object(
            object_store=object_store,
            input_run_id=parsed_run_id,
            parser=parser,
        )
        if stored is None:
            raise SecObservationWriteError(
                "SEC source object not found for observation writer: "
                f"input_run_id={parsed_run_id}, source_code={parser.source_code}, "
                f"filename={parser.filename}"
            )
        parsed = parser.parse_object(object_store, stored.object_id)
        summary = write_sec_observations(
            connection=connection,
            records=parsed.records,
            source_metadata=source_file_metadata_from_stored_object(
                source_code=parser.source_code,
                stored=stored,
            ),
        )
        logger.info(
            "Wrote SEC provider observations: source_code=%s object_id=%s "
            "inserted_count=%s skipped_count=%s failed_count=%s",
            summary.source_code,
            stored.object_id,
            summary.inserted_count,
            summary.skipped_count,
            summary.failed_count,
        )
        summaries.append(summary)

    result = StonksSecuritiesObservationRunResult(
        input_run_id=str(parsed_run_id),
        source_summaries=summaries,
    )
    logger.info(
        "Completed stonks securities observation writer for input_run_id=%s: "
        "inserted_count=%s skipped_count=%s failed_count=%s",
        result.input_run_id,
        result.inserted_count,
        result.skipped_count,
        result.failed_count,
    )
    return result


def build_sec_observation(
    record: SecObservationRecord,
    *,
    source_metadata: SecSourceFileMetadata | None = None,
) -> SecObservationWriteItem:
    """Build a deterministic provider observation payload for one parsed SEC row."""

    _validate_record(record)
    source_code = record.source_code
    provider_code = _provider_code_for_source(source_code)
    summary = summary_json_for_record(record)
    row_hash = compute_row_hash(summary)
    file_identity = (
        source_metadata.sha256
        or source_metadata.object_key
        or source_metadata.file_path
        if source_metadata is not None
        else None
    )
    raw_key = build_observation_raw_key(
        source_code=source_code,
        file_identity=file_identity,
        cik_padded=record.cik_padded,
        ticker_norm=record.ticker_norm,
        exchange=getattr(record, "exchange", None),
        row_hash=row_hash,
    )
    downloaded_at = source_metadata.downloaded_at if source_metadata is not None else None
    summary["row_hash"] = row_hash
    if source_metadata is not None:
        summary["source_file"] = {
            "file_path": source_metadata.file_path,
            "object_id": str(source_metadata.object_id) if source_metadata.object_id else None,
            "object_key": source_metadata.object_key,
            "sha256": source_metadata.sha256,
            "size_bytes": source_metadata.size_bytes,
            "etag": source_metadata.etag,
            "last_modified": source_metadata.last_modified,
            "downloaded_at": downloaded_at.isoformat() if downloaded_at else None,
        }

    return SecObservationWriteItem(
        provider_code=provider_code,
        provider_date=downloaded_at.date() if downloaded_at else None,
        observed_at=downloaded_at,
        object_id=source_metadata.object_id if source_metadata is not None else None,
        object_key=source_metadata.object_key if source_metadata is not None else None,
        source_snapshot_id=None,
        source_url=source_metadata.source_url if source_metadata is not None else None,
        raw_key=raw_key,
        row_hash=row_hash,
        summary_json=summary,
    )


def summary_json_for_record(record: SecObservationRecord) -> dict[str, Any]:
    """Return the evidence-ready summary JSON for a parsed SEC row."""

    base: dict[str, Any] = {
        "source_code": record.source_code,
        "cik": record.cik,
        "cik_padded": record.cik_padded,
        "ticker": record.ticker,
        "ticker_norm": record.ticker_norm,
        "company_name": record.company_name,
    }
    if isinstance(record, SecCompanyTickerExchangeRecord):
        base["exchange"] = record.exchange
    base["raw"] = record.raw
    return base


def compute_row_hash(summary_json: dict[str, Any]) -> str:
    """Compute a deterministic row hash from the normalized summary/raw row."""

    encoded = json.dumps(
        summary_json,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_observation_raw_key(
    *,
    source_code: str,
    file_identity: str | None,
    cik_padded: str,
    ticker_norm: str,
    exchange: str | None,
    row_hash: str,
) -> str:
    """Build a stable unique key for provider_observation.raw_key."""

    key_parts = {
        "source_code": source_code,
        "file_identity": file_identity,
        "cik_padded": cik_padded,
        "ticker_norm": ticker_norm,
        "exchange": exchange,
        "row_hash": row_hash,
    }
    digest = hashlib.sha256(
        json.dumps(key_parts, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"{source_code}:{digest}"


def ensure_sec_observation_providers(cursor: Any) -> None:
    """Ensure SEC and the two SEC source providers exist."""

    cursor.execute(
        """
        INSERT INTO stonks.provider (
            provider_code,
            provider_name,
            provider_type,
            website,
            description
        )
        VALUES
            (
                'SEC',
                'U.S. Securities and Exchange Commission',
                'REGULATOR',
                'https://www.sec.gov/',
                'U.S. securities filings and regulatory reference data'
            ),
            (
                'SEC_COMPANY_TICKERS_EXCHANGE',
                'SEC Company Tickers Exchange',
                'DATA_SOURCE',
                'https://www.sec.gov/files/company_tickers_exchange.json',
                'SEC company ticker records with exchange names'
            ),
            (
                'SEC_COMPANY_TICKERS',
                'SEC Company Tickers',
                'DATA_SOURCE',
                'https://www.sec.gov/files/company_tickers.json',
                'SEC company ticker records'
            )
        ON CONFLICT (provider_code) DO UPDATE
        SET
            provider_name = EXCLUDED.provider_name,
            provider_type = EXCLUDED.provider_type,
            website = EXCLUDED.website,
            description = EXCLUDED.description,
            is_active = TRUE
        """
    )


def find_sec_source_object(
    *,
    object_store: ObjectStore,
    input_run_id: UUID,
    parser: SecSourceParser,
) -> StoredObject | None:
    """Find a cached SEC source object from a run for a parser."""

    for logical_name in (parser.provider_code, parser.source_code):
        stored = object_store.find_one(
            run_id=input_run_id,
            object_kind=SEC_SOURCE_OBJECT_KIND,
            filename=parser.filename,
            logical_name=logical_name,
        )
        if stored is not None:
            return stored
    return None


def source_file_metadata_from_stored_object(
    *,
    source_code: str,
    stored: StoredObject,
) -> SecSourceFileMetadata:
    """Build source metadata from object-store metadata."""

    metadata = stored.metadata or {}
    return SecSourceFileMetadata(
        source_code=source_code,
        source_url=_optional_str(metadata.get("source_url")),
        downloaded_at=_parse_datetime(metadata.get("downloaded_at")),
        file_path=_optional_str(metadata.get("file_path")),
        object_id=stored.object_id,
        object_key=stored.object_key,
        size_bytes=_optional_int(metadata.get("size_bytes")) or stored.size_bytes,
        sha256=_optional_str(metadata.get("sha256")) or stored.checksum_sha256,
        etag=_optional_str(metadata.get("etag")),
        last_modified=_optional_str(metadata.get("last_modified")),
    )


def _provider_code_for_source(source_code: str) -> str:
    try:
        return SEC_SOURCE_PROVIDER_CODES[source_code]
    except KeyError as exc:
        raise SecObservationWriteError(
            f"No observation provider registered for SEC source {source_code!r}"
        ) from exc


def _validate_record(record: SecObservationRecord) -> None:
    expected_provider = _provider_code_for_source(record.source_code)
    if not expected_provider:
        raise SecObservationWriteError(f"Unsupported SEC observation source: {record.source_code}")
    if record.cik <= 0:
        raise SecObservationWriteError("SEC observation CIK must be greater than zero")
    if not record.cik_padded:
        raise SecObservationWriteError("SEC observation cik_padded cannot be blank")
    if not record.ticker_norm:
        raise SecObservationWriteError("SEC observation ticker_norm cannot be blank")
    if not record.company_name:
        raise SecObservationWriteError("SEC observation company_name cannot be blank")
    if not isinstance(record.raw, dict):
        raise SecObservationWriteError("SEC observation raw row must be a mapping")


def _single_source_code(source_codes: Iterable[str]) -> str:
    unique = set(source_codes)
    if len(unique) != 1:
        raise SecObservationWriteError(
            f"Expected records from exactly one source, found {sorted(unique)!r}"
        )
    return next(iter(unique))


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    return datetime.fromisoformat(text)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    parsed = str(value).strip()
    return parsed or None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
