"""Verification helpers for cached SEC security-master source files."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Iterable
from uuid import UUID

from empire_core import ObjectStore
from empire_core.object_store.models import StoredObject

from empire_stonks_securities.acquisition import SEC_SOURCE_OBJECT_KIND
from empire_stonks_securities.parsing import (
    SecSourceParseError,
    SecSourceParser,
    get_sec_source_parser,
)
from empire_stonks_securities.runner import DEFAULT_DAILY_SOURCE_KEYS


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SecSourceVerifySummary:
    """Verification counts for one SEC source file."""

    source_code: str
    object_id: str | None
    object_key: str | None
    filename: str | None
    good_record_count: int
    parse_error_count: int
    bad_record_count: int
    exchange_null_count: int = 0
    failed: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_code": self.source_code,
            "object_id": self.object_id,
            "object_key": self.object_key,
            "filename": self.filename,
            "good_record_count": self.good_record_count,
            "parse_error_count": self.parse_error_count,
            "bad_record_count": self.bad_record_count,
            "exchange_null_count": self.exchange_null_count,
            "failed": self.failed,
            "error": self.error,
        }


@dataclass(frozen=True)
class StonksSecuritiesDailyVerifyResult:
    """Verification result for a stonks securities acquisition run."""

    input_run_id: str
    source_summaries: list[SecSourceVerifySummary]

    @property
    def good_record_count(self) -> int:
        return sum(summary.good_record_count for summary in self.source_summaries)

    @property
    def parse_error_count(self) -> int:
        return sum(summary.parse_error_count for summary in self.source_summaries)

    @property
    def failed_source_count(self) -> int:
        return sum(1 for summary in self.source_summaries if summary.failed)

    @property
    def exchange_null_count(self) -> int:
        return sum(summary.exchange_null_count for summary in self.source_summaries)

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_run_id": self.input_run_id,
            "good_record_count": self.good_record_count,
            "parse_error_count": self.parse_error_count,
            "failed_source_count": self.failed_source_count,
            "exchange_null_count": self.exchange_null_count,
            "source_summaries": [summary.to_dict() for summary in self.source_summaries],
        }


def verify_stonks_securities_daily_sources(
    *,
    object_store: ObjectStore,
    input_run_id: str | UUID,
    source_codes: Iterable[str] = DEFAULT_DAILY_SOURCE_KEYS,
    raw_preview_chars: int = 1000,
) -> StonksSecuritiesDailyVerifyResult:
    """Parse downloaded daily SEC sources and log verification counts."""

    parsed_run_id = input_run_id if isinstance(input_run_id, UUID) else UUID(str(input_run_id))
    summaries = [
        verify_sec_source(
            object_store=object_store,
            input_run_id=parsed_run_id,
            source_code=source_code,
            raw_preview_chars=raw_preview_chars,
        )
        for source_code in source_codes
    ]
    result = StonksSecuritiesDailyVerifyResult(
        input_run_id=str(parsed_run_id),
        source_summaries=summaries,
    )
    logger.info(
        "Completed stonks securities daily verify for input_run_id=%s: "
        "good_record_count=%s parse_error_count=%s failed_source_count=%s "
        "exchange_null_count=%s",
        result.input_run_id,
        result.good_record_count,
        result.parse_error_count,
        result.failed_source_count,
        result.exchange_null_count,
    )
    return result


def verify_sec_source(
    *,
    object_store: ObjectStore,
    input_run_id: UUID,
    source_code: str,
    raw_preview_chars: int = 1000,
) -> SecSourceVerifySummary:
    """Parse one source object and log enough context to investigate bad rows."""

    parser = get_sec_source_parser(source_code)
    stored = _find_source_object(
        object_store=object_store,
        input_run_id=input_run_id,
        parser=parser,
    )
    if stored is None:
        error = (
            "SEC source object not found for verify: "
            f"input_run_id={input_run_id}, source_code={parser.source_code}, "
            f"filename={parser.filename}"
        )
        logger.error(error)
        return SecSourceVerifySummary(
            source_code=parser.source_code,
            object_id=None,
            object_key=None,
            filename=parser.filename,
            good_record_count=0,
            parse_error_count=1,
            bad_record_count=0,
            failed=True,
            error=error,
        )

    try:
        parsed = parser.parse_object(object_store, stored.object_id)
    except SecSourceParseError as exc:
        logger.exception(
            "Failed to parse SEC source object: source_code=%s object_id=%s "
            "object_key=%s filename=%s error=%s",
            parser.source_code,
            stored.object_id,
            stored.object_key,
            stored.filename,
            exc,
        )
        return SecSourceVerifySummary(
            source_code=parser.source_code,
            object_id=str(stored.object_id),
            object_key=stored.object_key,
            filename=stored.filename,
            good_record_count=0,
            parse_error_count=1,
            bad_record_count=0,
            failed=True,
            error=str(exc),
        )

    for bad_record in parsed.bad_records:
        logger.warning(
            "Malformed SEC source row: source_code=%s object_id=%s object_key=%s "
            "filename=%s row_number=%s error=%s raw_preview=%s",
            parser.source_code,
            stored.object_id,
            stored.object_key,
            stored.filename,
            bad_record.row_number,
            bad_record.error,
            _raw_preview(bad_record.raw, raw_preview_chars),
        )

    summary = SecSourceVerifySummary(
        source_code=parser.source_code,
        object_id=str(stored.object_id),
        object_key=stored.object_key,
        filename=stored.filename,
        good_record_count=len(parsed.records),
        parse_error_count=len(parsed.bad_records),
        bad_record_count=len(parsed.bad_records),
        exchange_null_count=_exchange_null_count(parsed.records),
    )
    logger.info(
        "Verified SEC source: source_code=%s object_id=%s object_key=%s filename=%s "
        "good_record_count=%s parse_error_count=%s exchange_null_count=%s",
        summary.source_code,
        summary.object_id,
        summary.object_key,
        summary.filename,
        summary.good_record_count,
        summary.parse_error_count,
        summary.exchange_null_count,
    )
    return summary


def _find_source_object(
    *,
    object_store: ObjectStore,
    input_run_id: UUID,
    parser: SecSourceParser,
) -> StoredObject | None:
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


def _raw_preview(raw: Any, max_chars: int) -> str:
    try:
        rendered = json.dumps(raw, sort_keys=True, default=str)
    except TypeError:
        rendered = repr(raw)
    if len(rendered) <= max_chars:
        return rendered
    return f"{rendered[:max_chars]}..."


def _exchange_null_count(records: Iterable[Any]) -> int:
    return sum(
        1
        for record in records
        if hasattr(record, "exchange") and getattr(record, "exchange") is None
    )
