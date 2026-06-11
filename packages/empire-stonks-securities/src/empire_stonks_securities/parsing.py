"""Parsers for cached SEC security-master source files."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generic, Iterable, TypeVar
from uuid import UUID

from empire_core import ObjectStore

from empire_stonks_securities.acquisition import SEC_SOURCE_OBJECT_KIND


logger = logging.getLogger(__name__)

SEC_COMPANY_TICKERS_EXCHANGE_SOURCE = "sec_company_tickers_exchange"
SEC_COMPANY_TICKERS_SOURCE = "sec_company_tickers"
SEC_COMPANY_TICKERS_EXCHANGE_PROVIDER = "SEC_COMPANY_TICKERS_EXCHANGE"
SEC_COMPANY_TICKERS_PROVIDER = "SEC_COMPANY_TICKERS"


class SecSourceParseError(ValueError):
    """Raised when a SEC source record cannot be parsed."""


@dataclass(frozen=True)
class SecCompanyTickerExchangeRecord:
    """Normalized row from SEC company_tickers_exchange.json."""

    source_code: str
    cik: int
    cik_padded: str
    company_name: str
    ticker: str
    ticker_norm: str
    exchange: str | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class SecCompanyTickerRecord:
    """Normalized row from SEC company_tickers.json."""

    source_code: str
    cik: int
    cik_padded: str
    company_name: str
    ticker: str
    ticker_norm: str
    raw: dict[str, Any]


@dataclass(frozen=True)
class SecSourceBadRecord:
    """Malformed source row retained for diagnostics."""

    source_code: str
    row_number: int | str
    raw: Any
    error: str


RecordT = TypeVar(
    "RecordT",
    SecCompanyTickerExchangeRecord,
    SecCompanyTickerRecord,
)


@dataclass(frozen=True)
class SecSourceParseResult(Generic[RecordT]):
    """Parsed records plus malformed rows that were skipped."""

    source_code: str
    records: list[RecordT]
    bad_records: list[SecSourceBadRecord]


class SecSourceParser(Generic[RecordT]):
    """Base parser for one cached SEC JSON source."""

    source_code: str
    provider_code: str
    filename: str

    def parse_path(self, path: str | Path) -> SecSourceParseResult[RecordT]:
        data = Path(path).read_bytes()
        return self.parse_bytes(data)

    def parse_records_path(self, path: str | Path) -> list[RecordT]:
        return self.parse_path(path).records

    def parse_bytes(self, data: bytes) -> SecSourceParseResult[RecordT]:
        try:
            payload = json.loads(data.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise SecSourceParseError(f"{self.source_code} is not valid JSON: {exc}") from exc
        return self.parse_payload(payload)

    def parse_records_bytes(self, data: bytes) -> list[RecordT]:
        return self.parse_bytes(data).records

    def parse_object(
        self,
        object_store: ObjectStore,
        object_id: str | UUID,
    ) -> SecSourceParseResult[RecordT]:
        parsed_object_id = object_id if isinstance(object_id, UUID) else UUID(str(object_id))
        return self.parse_bytes(object_store.get_bytes(parsed_object_id))

    def parse_records_object(
        self,
        object_store: ObjectStore,
        object_id: str | UUID,
    ) -> list[RecordT]:
        return self.parse_object(object_store, object_id).records

    def parse_run(
        self,
        object_store: ObjectStore,
        run_id: str | UUID,
    ) -> SecSourceParseResult[RecordT]:
        parsed_run_id = run_id if isinstance(run_id, UUID) else UUID(str(run_id))
        stored = object_store.find_one(
            run_id=parsed_run_id,
            object_kind=SEC_SOURCE_OBJECT_KIND,
            filename=self.filename,
            logical_name=self.provider_code,
        )
        if stored is None:
            stored = object_store.find_one(
                run_id=parsed_run_id,
                object_kind=SEC_SOURCE_OBJECT_KIND,
                filename=self.filename,
                logical_name=self.source_code,
            )
        if stored is None:
            raise SecSourceParseError(
                "SEC source object not found for run: "
                f"run_id={parsed_run_id}, source_code={self.source_code}, filename={self.filename}"
            )
        return self.parse_object(object_store, stored.object_id)

    def parse_records_run(
        self,
        object_store: ObjectStore,
        run_id: str | UUID,
    ) -> list[RecordT]:
        return self.parse_run(object_store, run_id).records

    def parse_payload(self, payload: Any) -> SecSourceParseResult[RecordT]:
        records: list[RecordT] = []
        bad_records: list[SecSourceBadRecord] = []
        for row_number, row in self.iter_rows(payload):
            try:
                records.append(self.parse_row(row))
            except SecSourceParseError as exc:
                logger.debug(
                    "Skipping malformed SEC source record",
                    extra={
                        "source_code": self.source_code,
                        "row_number": row_number,
                        "error": str(exc),
                    },
                )
                bad_records.append(
                    SecSourceBadRecord(
                        source_code=self.source_code,
                        row_number=row_number,
                        raw=row,
                        error=str(exc),
                    )
                )
        return SecSourceParseResult(
            source_code=self.source_code,
            records=records,
            bad_records=bad_records,
        )

    def iter_rows(self, payload: Any) -> Iterable[tuple[int | str, Any]]:
        raise NotImplementedError

    def parse_row(self, row: Any) -> RecordT:
        raise NotImplementedError


class SecCompanyTickerExchangeParser(SecSourceParser[SecCompanyTickerExchangeRecord]):
    """Parse SEC company_tickers_exchange.json."""

    source_code = SEC_COMPANY_TICKERS_EXCHANGE_SOURCE
    provider_code = SEC_COMPANY_TICKERS_EXCHANGE_PROVIDER
    filename = "company_tickers_exchange.json"

    def iter_rows(self, payload: Any) -> Iterable[tuple[int | str, Any]]:
        if isinstance(payload, dict) and "fields" in payload and "data" in payload:
            fields = payload["fields"]
            rows = payload["data"]
            if not isinstance(fields, list) or not all(isinstance(field, str) for field in fields):
                raise SecSourceParseError(f"{self.source_code}.fields must be a list of strings")
            if not isinstance(rows, list):
                raise SecSourceParseError(f"{self.source_code}.data must be a list")
            for index, values in enumerate(rows):
                if isinstance(values, list):
                    yield index, dict(zip(fields, values, strict=False))
                else:
                    yield index, values
            return

        if isinstance(payload, list):
            for index, row in enumerate(payload):
                yield index, row
            return

        raise SecSourceParseError(
            f"{self.source_code} must be a SEC fields/data object or a list of rows"
        )

    def parse_row(self, row: Any) -> SecCompanyTickerExchangeRecord:
        if not isinstance(row, dict):
            raise SecSourceParseError("row must be a mapping")
        cik = _required_int(row, "cik")
        ticker = _required_str(row, "ticker")
        company_name = _required_str(row, "name")
        exchange = _optional_str(row, "exchange")
        return SecCompanyTickerExchangeRecord(
            source_code=self.source_code,
            cik=cik,
            cik_padded=_pad_cik(cik),
            company_name=company_name,
            ticker=ticker,
            ticker_norm=ticker.upper(),
            exchange=exchange,
            raw=dict(row),
        )


class SecCompanyTickerParser(SecSourceParser[SecCompanyTickerRecord]):
    """Parse SEC company_tickers.json."""

    source_code = SEC_COMPANY_TICKERS_SOURCE
    provider_code = SEC_COMPANY_TICKERS_PROVIDER
    filename = "company_tickers.json"

    def iter_rows(self, payload: Any) -> Iterable[tuple[int | str, Any]]:
        if not isinstance(payload, dict):
            raise SecSourceParseError(f"{self.source_code} must be an object keyed by sequence number")
        for key, row in payload.items():
            yield str(key), row

    def parse_row(self, row: Any) -> SecCompanyTickerRecord:
        if not isinstance(row, dict):
            raise SecSourceParseError("row must be a mapping")
        cik = _required_int(row, "cik_str")
        ticker = _required_str(row, "ticker")
        company_name = _required_str(row, "title")
        return SecCompanyTickerRecord(
            source_code=self.source_code,
            cik=cik,
            cik_padded=_pad_cik(cik),
            company_name=company_name,
            ticker=ticker,
            ticker_norm=ticker.upper(),
            raw=dict(row),
        )


def get_sec_source_parser(source_code: str) -> SecSourceParser:
    """Return the parser registered for a source key or provider code."""

    try:
        return SEC_SOURCE_PARSER_REGISTRY[_source_lookup_key(source_code)]
    except KeyError as exc:
        raise SecSourceParseError(f"No SEC source parser registered for {source_code!r}") from exc


def parse_sec_source_path(source_code: str, path: str | Path) -> SecSourceParseResult:
    """Parse one SEC source file from a local path."""

    return get_sec_source_parser(source_code).parse_path(path)


def parse_sec_source_records_path(source_code: str, path: str | Path) -> list:
    """Parse one SEC source file from a local path and return only valid records."""

    return parse_sec_source_path(source_code, path).records


def parse_sec_source_run(
    source_code: str,
    object_store: ObjectStore,
    run_id: str | UUID,
) -> SecSourceParseResult:
    """Parse one SEC source file from an object-store run."""

    return get_sec_source_parser(source_code).parse_run(object_store, run_id)


def parse_sec_source_records_run(
    source_code: str,
    object_store: ObjectStore,
    run_id: str | UUID,
) -> list:
    """Parse one SEC source file from an object-store run and return only valid records."""

    return parse_sec_source_run(source_code, object_store, run_id).records


def _source_lookup_key(source_code: str) -> str:
    return source_code.strip().lower()


SEC_SOURCE_PARSER_REGISTRY: dict[str, SecSourceParser] = {}
for _parser in (SecCompanyTickerExchangeParser(), SecCompanyTickerParser()):
    SEC_SOURCE_PARSER_REGISTRY[_source_lookup_key(_parser.source_code)] = _parser
    SEC_SOURCE_PARSER_REGISTRY[_source_lookup_key(_parser.provider_code)] = _parser


def _required_int(row: dict[str, Any], field_name: str) -> int:
    value = row.get(field_name)
    if value is None:
        raise SecSourceParseError(f"missing required field: {field_name}")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise SecSourceParseError(f"{field_name} must be an integer") from exc
    if parsed <= 0:
        raise SecSourceParseError(f"{field_name} must be greater than zero")
    return parsed


def _required_str(row: dict[str, Any], field_name: str) -> str:
    value = row.get(field_name)
    if value is None:
        raise SecSourceParseError(f"missing required field: {field_name}")
    if not isinstance(value, str):
        value = str(value)
    parsed = value.strip()
    if not parsed:
        raise SecSourceParseError(f"{field_name} cannot be blank")
    return parsed


def _optional_str(row: dict[str, Any], field_name: str) -> str | None:
    value = row.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    parsed = value.strip()
    return parsed or None


def _pad_cik(cik: int) -> str:
    return f"{cik:010d}"
