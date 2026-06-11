"""SEC source-file acquisition and object-store caching."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlparse

import requests

from empire_core import ObjectStore
from empire_core.exceptions import ValidationError
from empire_core.object_store.storage import FilesystemStorageBackend

from empire_stonks_securities.config import ProviderConfig, StonksSecuritiesConfig


DEFAULT_STORAGE_ROOT = "global"
DEFAULT_STORAGE_KEY_ENV = "EMPIRE_STORAGE_KEY_STONKS_SECURITIES"
DEFAULT_STORAGE_KEY = "stonks/securities"
DEFAULT_TEMP_SUBDIR = "stonks/securities/sec"
SEC_SOURCE_OBJECT_KIND = "sec_source_file"
SEC_SOURCE_METADATA_OBJECT_KIND = "sec_source_file_metadata"
TRANSIENT_HTTP_STATUSES = frozenset({408, 429, 500, 502, 503, 504})


@dataclass(frozen=True)
class SecDownloadTarget:
    """One SEC source file to acquire."""

    source_key: str
    source_code: str
    source_url: str
    filename: str
    object_key: str
    content_type: str | None = None
    year: int | None = None
    quarter: int | None = None

    @property
    def metadata_filename(self) -> str:
        return f"{self.filename}.metadata.json"


@dataclass(frozen=True)
class SecDownloadResult:
    """Outcome for one SEC source download."""

    source_code: str
    source_url: str
    object_key: str
    filename: str
    metadata_filename: str
    status: str
    skipped: bool = False
    object_id: str | None = None
    metadata_object_id: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    http_status: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_code": self.source_code,
            "source_url": self.source_url,
            "object_key": self.object_key,
            "filename": self.filename,
            "metadata_filename": self.metadata_filename,
            "status": self.status,
            "skipped": self.skipped,
            "object_id": self.object_id,
            "metadata_object_id": self.metadata_object_id,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "http_status": self.http_status,
        }


class SecDownloadError(RuntimeError):
    """Raised when SEC acquisition fails."""


class RateLimiter:
    """Simple minimum-interval limiter for polite SEC access."""

    def __init__(
        self,
        requests_per_second: float,
        *,
        sleep_func: Callable[[float], None] = time.sleep,
        monotonic_func: Callable[[], float] = time.monotonic,
    ) -> None:
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be greater than zero")
        self.minimum_interval = 1.0 / requests_per_second
        self.sleep_func = sleep_func
        self.monotonic_func = monotonic_func
        self._last_request_at: float | None = None

    def wait(self) -> None:
        now = self.monotonic_func()
        if self._last_request_at is not None:
            remaining = self.minimum_interval - (now - self._last_request_at)
            if remaining > 0:
                self.sleep_func(remaining)
        self._last_request_at = self.monotonic_func()


class SecDownloader:
    """Download SEC source files into the Empire object store."""

    def __init__(
        self,
        config: StonksSecuritiesConfig,
        *,
        session: requests.Session | None = None,
        sleep_func: Callable[[float], None] = time.sleep,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self.config = config
        self.session = session or requests.Session()
        self.sleep_func = sleep_func
        self.rate_limiter = rate_limiter or RateLimiter(
            config.rate_limit.requests_per_second,
            sleep_func=sleep_func,
        )

    def download_target(
        self,
        *,
        target: SecDownloadTarget,
        object_store: ObjectStore,
        storage_root: str = DEFAULT_STORAGE_ROOT,
        run_context=None,
        object_scope: str | None = None,
        force: bool = False,
        temp_dir: str | Path | None = None,
    ) -> SecDownloadResult:
        """Download one target unless the cached file and metadata already exist."""

        if not force and cached_pair_exists(
            object_store=object_store,
            storage_root=storage_root,
            object_key=target.object_key,
            filename=target.filename,
            metadata_filename=target.metadata_filename,
        ):
            return SecDownloadResult(
                source_code=target.source_code,
                source_url=target.source_url,
                object_key=target.object_key,
                filename=target.filename,
                metadata_filename=target.metadata_filename,
                status="skipped",
                skipped=True,
            )

        work_dir = _work_dir(temp_dir, target)
        work_dir.mkdir(parents=True, exist_ok=True)
        part_path = work_dir / f"{target.filename}.part"
        staged_path = work_dir / target.filename

        try:
            http_status, headers = self._download_to_file(target.source_url, part_path)
            os.replace(part_path, staged_path)
            size_bytes, sha256 = file_digest(staged_path)
            if self.config.processing.validation.verify_non_empty_file and size_bytes <= 0:
                raise SecDownloadError(f"SEC download produced an empty file: {target.source_url}")

            if force:
                delete_existing_objects(
                    object_store=object_store,
                    storage_root=storage_root,
                    object_key=target.object_key,
                    filenames=[target.filename, target.metadata_filename],
                )

            metadata = build_metadata(
                target=target,
                storage_root=storage_root,
                object_store=object_store,
                size_bytes=size_bytes,
                sha256=sha256,
                http_status=http_status,
                headers=headers,
            )
            stored = object_store.put_file(
                run_context=run_context,
                object_scope=object_scope or ("run" if run_context else "manual"),
                domain="stonks",
                logical_name=target.source_code,
                storage_root=storage_root,
                object_key=target.object_key,
                filename=target.filename,
                source_path=staged_path,
                move=True,
                content_type=target.content_type,
                object_kind=SEC_SOURCE_OBJECT_KIND,
                metadata=metadata,
            )
            metadata_stored = object_store.put_bytes(
                run_context=run_context,
                object_scope=object_scope or ("run" if run_context else "manual"),
                domain="stonks",
                logical_name=f"{target.source_code}.metadata",
                storage_root=storage_root,
                object_key=target.object_key,
                filename=target.metadata_filename,
                data=json.dumps(metadata, indent=2, sort_keys=True).encode("utf-8"),
                content_type="application/json",
                object_kind=SEC_SOURCE_METADATA_OBJECT_KIND,
                metadata=metadata,
            )
            return SecDownloadResult(
                source_code=target.source_code,
                source_url=target.source_url,
                object_key=target.object_key,
                filename=target.filename,
                metadata_filename=target.metadata_filename,
                status="downloaded",
                object_id=str(stored.object_id),
                metadata_object_id=str(metadata_stored.object_id),
                size_bytes=size_bytes,
                sha256=sha256,
                http_status=http_status,
            )
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)
            _remove_empty_temp_parents(work_dir)

    def _download_to_file(self, url: str, path: Path) -> tuple[int, dict[str, str]]:
        headers = {"User-Agent": self.config.sec.user_agent}
        last_error: Exception | None = None
        attempts = self.config.max_retries + 1
        for attempt in range(1, attempts + 1):
            if self.config.respect_rate_limits:
                self.rate_limiter.wait()
            try:
                with self.session.get(
                    url,
                    headers=headers,
                    timeout=self.config.timeout_seconds,
                    stream=True,
                ) as response:
                    status_code = int(response.status_code)
                    response_headers = dict(response.headers)
                    if status_code == 403:
                        raise SecDownloadError(
                            "SEC returned 403 Forbidden. Check the configured User-Agent "
                            "and reduce request rate before retrying."
                        )
                    if status_code in TRANSIENT_HTTP_STATUSES:
                        if attempt < attempts:
                            self._sleep_before_retry(attempt, response_headers)
                            continue
                        if status_code == 429:
                            raise SecDownloadError(
                                "SEC returned 429 Too Many Requests after retries. "
                                "Lower stonks_securities.rate_limit.requests_per_second."
                            )
                        raise SecDownloadError(
                            f"SEC returned transient HTTP {status_code} after retries: {url}"
                        )
                    if status_code >= 400:
                        raise SecDownloadError(f"SEC returned HTTP {status_code}: {url}")

                    with path.open("wb") as output:
                        for chunk in response.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                output.write(chunk)
                    return status_code, response_headers
            except requests.RequestException as exc:
                last_error = exc
                if attempt < attempts:
                    self._sleep_before_retry(attempt, {})
                    continue
                raise SecDownloadError(f"SEC request failed after retries: {exc}") from exc

        raise SecDownloadError(f"SEC request failed after retries: {last_error}")

    def _sleep_before_retry(self, attempt: int, headers: dict[str, str]) -> None:
        retry_after = headers.get("Retry-After") if self.config.rate_limit.retry_after_header else None
        if retry_after:
            try:
                delay = float(retry_after)
            except ValueError:
                delay = self.config.retry_backoff_seconds * (2 ** (attempt - 1))
        else:
            delay = self.config.retry_backoff_seconds * (2 ** (attempt - 1))
        if delay > 0:
            self.sleep_func(delay)


def build_configured_source_targets(
    *,
    config: StonksSecuritiesConfig,
    storage_key: str,
    acquisition_date: date,
    acquisition_id: str,
    source_keys: Iterable[str] | None = None,
) -> list[SecDownloadTarget]:
    """Build targets for enabled fixed-URL providers."""

    requested = set(source_keys or [])
    targets: list[SecDownloadTarget] = []
    for provider in config.enabled_providers:
        if provider.url is None:
            continue
        if requested and provider.key not in requested and provider.provider_code not in requested:
            continue
        targets.append(
            target_from_provider(
                provider=provider,
                storage_key=storage_key,
                acquisition_date=acquisition_date,
                acquisition_id=acquisition_id,
            )
        )
    return targets


def build_quarterly_master_index_targets(
    *,
    config: StonksSecuritiesConfig,
    storage_key: str,
    acquisition_date: date,
    acquisition_id: str,
    start_year: int | None = None,
    end_year: int | None = None,
    quarters: Iterable[int] | None = None,
) -> list[SecDownloadTarget]:
    provider = provider_by_key(config, "sec_quarterly_master_index")
    if provider.url_template is None:
        raise SecDownloadError("sec_quarterly_master_index must define url_template.")
    range_config = config.download.quarterly_master_index
    resolved_start = start_year if start_year is not None else range_config.start_year
    resolved_end = end_year if end_year is not None else range_config.end_year
    if resolved_end is None:
        resolved_end = acquisition_date.year
    resolved_quarters = tuple(quarters or range_config.quarters)
    if resolved_start > resolved_end:
        raise SecDownloadError("start_year cannot be greater than end_year.")

    targets: list[SecDownloadTarget] = []
    for year in range(resolved_start, resolved_end + 1):
        for quarter in resolved_quarters:
            if quarter < 1 or quarter > 4:
                raise SecDownloadError("quarters must contain values 1-4.")
            url = provider.url_template.format(year=year, quarter=quarter)
            targets.append(
                target_from_provider(
                    provider=provider,
                    storage_key=storage_key,
                    acquisition_date=acquisition_date,
                    acquisition_id=acquisition_id,
                    url=url,
                    filename=f"{year}-QTR{quarter}-master.zip",
                    path_parts=("quarterly-master-index", str(year), f"QTR{quarter}"),
                    year=year,
                    quarter=quarter,
                )
            )
    return targets


def target_from_provider(
    *,
    provider: ProviderConfig,
    storage_key: str,
    acquisition_date: date,
    acquisition_id: str,
    url: str | None = None,
    filename: str | None = None,
    path_parts: tuple[str, ...] = (),
    year: int | None = None,
    quarter: int | None = None,
) -> SecDownloadTarget:
    source_url = url or provider.url
    if source_url is None:
        raise SecDownloadError(f"Provider does not define a concrete URL: {provider.key}")
    resolved_filename = filename or filename_from_url(source_url)
    object_key = build_object_key(
        storage_key=storage_key,
        acquisition_date=acquisition_date,
        acquisition_id=acquisition_id,
        source_key=provider.key,
        path_parts=path_parts,
    )
    return SecDownloadTarget(
        source_key=provider.key,
        source_code=provider.provider_code,
        source_url=source_url,
        filename=resolved_filename,
        object_key=object_key,
        content_type=content_type_for_filename(resolved_filename),
        year=year,
        quarter=quarter,
    )


def build_object_key(
    *,
    storage_key: str,
    acquisition_date: date,
    acquisition_id: str,
    source_key: str,
    path_parts: tuple[str, ...] = (),
) -> str:
    parts = [
        storage_key.strip("/"),
        "runs",
        f"{acquisition_date:%Y}",
        f"{acquisition_date:%m}",
        f"{acquisition_date:%d}",
        acquisition_id.strip("/"),
        source_key.strip("/"),
        *[part.strip("/") for part in path_parts if part.strip("/")],
    ]
    return "/".join(part for part in parts if part)


def build_metadata(
    *,
    target: SecDownloadTarget,
    storage_root: str,
    object_store: ObjectStore,
    size_bytes: int,
    sha256: str,
    http_status: int,
    headers: dict[str, str],
) -> dict[str, Any]:
    return {
        "source_code": target.source_code,
        "source_url": target.source_url,
        "downloaded_at": datetime.now(UTC).isoformat(),
        "file_path": str(resolve_object_path(object_store, storage_root, target.object_key, target.filename)),
        "size_bytes": size_bytes,
        "sha256": sha256,
        "http_status": http_status,
        "etag": headers.get("ETag") or headers.get("etag"),
        "last_modified": headers.get("Last-Modified") or headers.get("last-modified"),
    }


def cached_pair_exists(
    *,
    object_store: ObjectStore,
    storage_root: str,
    object_key: str,
    filename: str,
    metadata_filename: str,
) -> bool:
    return object_exists(
        object_store=object_store,
        storage_root=storage_root,
        object_key=object_key,
        filename=filename,
    ) and object_exists(
        object_store=object_store,
        storage_root=storage_root,
        object_key=object_key,
        filename=metadata_filename,
    )


def object_exists(
    *,
    object_store: ObjectStore,
    storage_root: str,
    object_key: str,
    filename: str,
) -> bool:
    root = object_store.repository.get_storage_root(storage_root)
    if root is None or root.backend_type != "filesystem":
        return False
    return FilesystemStorageBackend(root.base_uri).exists(object_key, filename)


def delete_existing_objects(
    *,
    object_store: ObjectStore,
    storage_root: str,
    object_key: str,
    filenames: Iterable[str],
) -> int:
    root = object_store.repository.get_storage_root(storage_root)
    if root is None:
        return 0
    filename_set = set(filenames)
    candidates = []
    objects = getattr(object_store.repository, "objects", None)
    if isinstance(objects, dict):
        candidates = [
            obj
            for obj in objects.values()
            if obj.storage_root_id == root.storage_root_id
            and obj.object_key == object_key
            and obj.filename in filename_set
            and obj.deleted_at is None
        ]
    else:
        connection = getattr(object_store.repository, "connection", None)
        if connection is not None:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT object_id
                    FROM core.stored_object
                    WHERE storage_root_id = %s
                      AND object_key = %s
                      AND filename = ANY(%s)
                      AND deleted_at IS NULL
                    """,
                    (root.storage_root_id, object_key, list(filename_set)),
                )
                candidates = [object_store.get_object(row[0]) for row in cursor.fetchall()]

    deleted_count = 0
    for stored in candidates:
        if object_store.delete_object(stored.object_id):
            deleted_count += 1
    return deleted_count


def resolve_object_path(
    object_store: ObjectStore,
    storage_root: str,
    object_key: str,
    filename: str,
) -> Path:
    root = object_store.repository.get_storage_root(storage_root)
    if root is None or root.backend_type != "filesystem":
        raise ValidationError(f"Storage root not found or unsupported: {storage_root}")
    return FilesystemStorageBackend(root.base_uri).resolve_path(object_key, filename)


def file_digest(path: Path) -> tuple[int, str]:
    checksum = hashlib.sha256()
    size_bytes = 0
    with path.open("rb") as input_file:
        while True:
            chunk = input_file.read(1024 * 1024)
            if not chunk:
                break
            checksum.update(chunk)
            size_bytes += len(chunk)
    return size_bytes, checksum.hexdigest()


def filename_from_url(url: str) -> str:
    name = Path(urlparse(url).path).name
    if not name:
        raise SecDownloadError(f"Could not determine filename from URL: {url}")
    return name


def content_type_for_filename(filename: str) -> str | None:
    if filename.endswith(".json"):
        return "application/json"
    if filename.endswith(".zip"):
        return "application/zip"
    if filename.endswith(".idx"):
        return "text/plain"
    return None


def provider_by_key(config: StonksSecuritiesConfig, key: str) -> ProviderConfig:
    for provider in config.enabled_providers:
        if provider.key == key:
            return provider
    raise SecDownloadError(f"Enabled provider not found: {key}")


def default_storage_key() -> str:
    return os.environ.get(DEFAULT_STORAGE_KEY_ENV, DEFAULT_STORAGE_KEY).strip("/") or DEFAULT_STORAGE_KEY


def default_temp_dir() -> Path:
    value = os.environ.get("EMPIRE_TEMP_DIR")
    if not value:
        raise ValidationError("Missing required environment variable: EMPIRE_TEMP_DIR")
    return Path(value)


def _work_dir(temp_dir: str | Path | None, target: SecDownloadTarget) -> Path:
    root = Path(temp_dir) if temp_dir is not None else default_temp_dir()
    return root / DEFAULT_TEMP_SUBDIR / target.object_key.replace("/", "_")


def _remove_empty_temp_parents(work_dir: Path) -> None:
    current = work_dir.parent
    for _ in range(4):
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent
