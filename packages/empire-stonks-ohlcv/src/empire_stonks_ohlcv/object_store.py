"""Core object-store helpers for short-lived raw OHLCV provider inputs."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite
from pathlib import Path
from typing import TypeAlias

from empire_core import ObjectStore, RunContext, StoredObject

from empire_stonks_ohlcv.config import OHLCVConfig
from empire_stonks_ohlcv.exceptions import OHLCVAcquisitionError
from empire_stonks_ohlcv.results import AcquiredObject


DEFAULT_STORAGE_ROOT = "global"
RAW_SOURCE_OBJECT_KIND = "stonks_ohlcv_raw_source"
RAW_METADATA_SCHEMA_VERSION = 1

_SAFE_TOKEN_PATTERN = re.compile(r"^[a-z0-9]+(?:[_-][a-z0-9]+)*$")
_FORMAT_SUFFIX_PATTERN = re.compile(r"^[a-z0-9]+(?:\.[a-z0-9]+)*$")
_PARSER_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SAFE_PROVIDER_METADATA_KEYS = frozenset(
    {
        "etag",
        "http_status",
        "last_modified",
        "market",
        "provider_file_date",
        "request_scope",
    }
)

MetadataScalar: TypeAlias = str | int | float | bool | None
Clock: TypeAlias = Callable[[], datetime]


@dataclass(frozen=True)
class _RawObjectSpec:
    object_key: str
    filename: str
    expires_at: datetime
    metadata: dict[str, MetadataScalar]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def build_raw_object_key(
    *,
    storage_key: str,
    provider_code: str,
    run_context: RunContext,
    source_code: str,
) -> str:
    """Build the deterministic provider/date/run/source key for a raw input."""

    provider_path = _validate_provider_and_source(provider_code, source_code)
    _validate_run_context(run_context)
    prefix = _normalize_storage_key(storage_key)
    effective_date = run_context.effective_date
    assert effective_date is not None
    return "/".join(
        (
            prefix,
            provider_path,
            "runs",
            f"{effective_date:%Y}",
            f"{effective_date:%m}",
            f"{effective_date:%d}",
            str(run_context.run_id),
            source_code,
        )
    )


def build_raw_filename(*, format_suffix: str, part_key: str | None = None) -> str:
    """Build a stable single- or multipart raw filename."""

    if not isinstance(format_suffix, str) or not _FORMAT_SUFFIX_PATTERN.fullmatch(
        format_suffix
    ):
        raise OHLCVAcquisitionError(
            "format_suffix must be a lowercase source-contract suffix."
        )
    if part_key is None:
        return f"raw.{format_suffix}"
    _require_safe_token(part_key, "part_key")
    return f"raw-{part_key}.{format_suffix}"


def store_raw_bytes(
    *,
    object_store: ObjectStore,
    run_context: RunContext,
    config: OHLCVConfig,
    provider_code: str,
    source_code: str,
    format_suffix: str,
    data: bytes,
    content_type: str,
    part_key: str | None = None,
    parser_version: str | None = None,
    provider_metadata: Mapping[str, MetadataScalar] | None = None,
    storage_root: str = DEFAULT_STORAGE_ROOT,
    clock: Clock = _utc_now,
) -> AcquiredObject:
    """Store downloaded bytes as one short-lived Core run object."""

    if not isinstance(data, bytes):
        raise OHLCVAcquisitionError("data must be bytes.")
    spec = _prepare_raw_object(
        run_context=run_context,
        config=config,
        provider_code=provider_code,
        source_code=source_code,
        format_suffix=format_suffix,
        content_type=content_type,
        part_key=part_key,
        parser_version=parser_version,
        provider_metadata=provider_metadata,
        clock=clock,
    )
    stored = object_store.put_bytes(
        run_context=run_context,
        object_scope="run",
        domain="stonks",
        logical_name=source_code,
        storage_root=storage_root,
        object_key=spec.object_key,
        filename=spec.filename,
        data=data,
        content_type=content_type,
        object_kind=RAW_SOURCE_OBJECT_KIND,
        expires_at=spec.expires_at,
        metadata=spec.metadata,
    )
    return _acquired_object(source_code, stored)


def store_raw_file(
    *,
    object_store: ObjectStore,
    run_context: RunContext,
    config: OHLCVConfig,
    provider_code: str,
    source_code: str,
    format_suffix: str,
    source_path: str | Path,
    content_type: str,
    part_key: str | None = None,
    parser_version: str | None = None,
    provider_metadata: Mapping[str, MetadataScalar] | None = None,
    storage_root: str = DEFAULT_STORAGE_ROOT,
    move: bool = True,
    clock: Clock = _utc_now,
) -> AcquiredObject:
    """Store a downloaded file without loading it into memory."""

    spec = _prepare_raw_object(
        run_context=run_context,
        config=config,
        provider_code=provider_code,
        source_code=source_code,
        format_suffix=format_suffix,
        content_type=content_type,
        part_key=part_key,
        parser_version=parser_version,
        provider_metadata=provider_metadata,
        clock=clock,
    )
    stored = object_store.put_file(
        run_context=run_context,
        object_scope="run",
        domain="stonks",
        logical_name=source_code,
        storage_root=storage_root,
        object_key=spec.object_key,
        filename=spec.filename,
        source_path=source_path,
        move=move,
        content_type=content_type,
        object_kind=RAW_SOURCE_OBJECT_KIND,
        expires_at=spec.expires_at,
        metadata=spec.metadata,
    )
    return _acquired_object(source_code, stored)


def _prepare_raw_object(
    *,
    run_context: RunContext,
    config: OHLCVConfig,
    provider_code: str,
    source_code: str,
    format_suffix: str,
    content_type: str,
    part_key: str | None,
    parser_version: str | None,
    provider_metadata: Mapping[str, MetadataScalar] | None,
    clock: Clock,
) -> _RawObjectSpec:
    if not isinstance(config, OHLCVConfig):
        raise OHLCVAcquisitionError("config must be an OHLCVConfig.")
    if not isinstance(content_type, str) or not content_type.strip():
        raise OHLCVAcquisitionError("content_type is required.")
    if content_type != content_type.strip() or "/" not in content_type:
        raise OHLCVAcquisitionError("content_type must be a valid media type.")

    stored_at = clock()
    if not isinstance(stored_at, datetime) or stored_at.tzinfo is None:
        raise OHLCVAcquisitionError("clock must return a timezone-aware datetime.")
    stored_at = stored_at.astimezone(UTC)
    object_key = build_raw_object_key(
        storage_key=config.storage_key,
        provider_code=provider_code,
        run_context=run_context,
        source_code=source_code,
    )
    metadata: dict[str, MetadataScalar] = {
        "schema_version": RAW_METADATA_SCHEMA_VERSION,
        "provider_code": provider_code,
        "source_code": source_code,
        "effective_date": run_context.effective_date.isoformat(),
        "acquired_at": stored_at.isoformat(),
        "retention_days": config.raw_retention_days,
    }
    if parser_version is not None:
        if not isinstance(parser_version, str) or not _PARSER_VERSION_PATTERN.fullmatch(
            parser_version
        ):
            raise OHLCVAcquisitionError("parser_version is invalid.")
        metadata["parser_version"] = parser_version
    metadata.update(_validated_provider_metadata(provider_metadata))
    return _RawObjectSpec(
        object_key=object_key,
        filename=build_raw_filename(
            format_suffix=format_suffix,
            part_key=part_key,
        ),
        expires_at=stored_at + timedelta(days=config.raw_retention_days),
        metadata=metadata,
    )


def _validated_provider_metadata(
    provider_metadata: Mapping[str, MetadataScalar] | None,
) -> dict[str, MetadataScalar]:
    if provider_metadata is None:
        return {}
    invalid_keys = sorted(set(provider_metadata) - _SAFE_PROVIDER_METADATA_KEYS)
    if invalid_keys:
        raise OHLCVAcquisitionError("provider_metadata contains unsupported keys.")
    validated: dict[str, MetadataScalar] = {}
    for key, value in provider_metadata.items():
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise OHLCVAcquisitionError(
                f"provider_metadata {key!r} must be a JSON scalar."
            )
        if isinstance(value, float) and not isfinite(value):
            raise OHLCVAcquisitionError(
                f"provider_metadata {key!r} must be finite."
            )
        validated[key] = value
    return validated


def _validate_run_context(run_context: RunContext) -> None:
    if not isinstance(run_context, RunContext):
        raise OHLCVAcquisitionError("run_context must be a Core RunContext.")
    if run_context.domain != "stonks":
        raise OHLCVAcquisitionError("run_context domain must be 'stonks'.")
    if run_context.status != "started":
        raise OHLCVAcquisitionError("run_context must be active.")
    if run_context.effective_date is None:
        raise OHLCVAcquisitionError("run_context effective_date is required.")


def _validate_provider_and_source(provider_code: str, source_code: str) -> str:
    if not isinstance(provider_code, str) or provider_code != provider_code.upper():
        raise OHLCVAcquisitionError("provider_code must be uppercase.")
    provider_path = provider_code.lower()
    _require_safe_token(provider_path, "provider_code")
    _require_safe_token(source_code, "source_code")
    if not source_code.startswith(f"{provider_path}_"):
        raise OHLCVAcquisitionError(
            "source_code must be prefixed by the lowercase provider code."
        )
    return provider_path


def _normalize_storage_key(storage_key: str) -> str:
    if not isinstance(storage_key, str):
        raise OHLCVAcquisitionError("storage_key must be a string.")
    prefix = storage_key.strip("/")
    if not prefix:
        raise OHLCVAcquisitionError("storage_key is required.")
    segments = prefix.split("/")
    if any(not _SAFE_TOKEN_PATTERN.fullmatch(segment) for segment in segments):
        raise OHLCVAcquisitionError("storage_key contains an invalid path segment.")
    return prefix


def _require_safe_token(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not _SAFE_TOKEN_PATTERN.fullmatch(value):
        raise OHLCVAcquisitionError(
            f"{field_name} must be a lowercase path-safe token."
        )


def _acquired_object(source_code: str, stored: StoredObject) -> AcquiredObject:
    if stored.size_bytes is None or stored.checksum_sha256 is None:
        raise OHLCVAcquisitionError(
            "Core stored object did not return size and checksum metadata."
        )
    return AcquiredObject(
        source_code=source_code,
        object_id=stored.object_id,
        object_key=stored.object_key,
        filename=stored.filename,
        size_bytes=stored.size_bytes,
        checksum_sha256=stored.checksum_sha256,
    )
