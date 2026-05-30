"""Download planned YouTube videos into the Jellyfin object store."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from empire_core import ObjectStore
from empire_core.exceptions import ValidationError
from empire_core.object_store.storage import FilesystemStorageBackend

from empire_youtube.processor import MOVIE_FILENAME
from empire_youtube.runner import DEFAULT_LIBRARY_PLAN_FILENAME


DOWNLOAD_REPORT_FILENAME = "youtube-download-report.json"
DOWNLOAD_REPORT_OBJECT_KIND = "youtube_download_report"
MEDIA_ASSET_OBJECT_KIND = "youtube_media_asset"
DEFAULT_LIBRARY_STORAGE_ROOT = "jellyfin"
DEFAULT_PLAN_OBJECT_KIND = "jellyfin_library_plan"
DEFAULT_TEMP_SUBDIR = "youtube/downloads"


@dataclass(frozen=True)
class YouTubeDownloadEntry:
    """One planned video download target."""

    video_id: str
    title: str
    object_key: str
    source_url: str
    movie_filename: str = MOVIE_FILENAME

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "YouTubeDownloadEntry":
        video_id = _required_text(data, "video_id")
        return cls(
            video_id=video_id,
            title=_text_or_default(data.get("title"), video_id),
            object_key=_required_text(data, "object_key"),
            source_url=_required_text(data, "source_url"),
            movie_filename=_text_or_default(data.get("movie_filename"), MOVIE_FILENAME),
        )


@dataclass(frozen=True)
class YouTubeDownloadResult:
    """Result of attempting one planned video download."""

    video_id: str
    status: str
    object_id: str | None = None
    object_key: str | None = None
    filename: str | None = None
    skipped: bool = False
    error_message: str | None = None
    cleanup_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "video_id": self.video_id,
            "status": self.status,
            "object_id": self.object_id,
            "object_key": self.object_key,
            "filename": self.filename,
            "skipped": self.skipped,
            "error_message": self.error_message,
            "cleanup_count": self.cleanup_count,
        }


class YtDlpCommand:
    """Shell out to yt-dlp for one video."""

    def __init__(self, executable: str = "yt-dlp") -> None:
        self.executable = executable

    def download(self, *, url: str, output_template: Path) -> None:
        command = [
            self.executable,
            "--no-playlist",
            "-f",
            "bv*+ba/b",
            "--merge-output-format",
            "mp4",
            "--socket-timeout",
            "30",
            "--retries",
            "5",
            "--fragment-retries",
            "5",
            "--extractor-retries",
            "3",
            "--retry-sleep",
            "http:exp=5:120",
            "--retry-sleep",
            "fragment:exp=5:120",
            "--sleep-requests",
            "2",
            "--sleep-interval",
            "10",
            "--max-sleep-interval",
            "30",
            "-o",
            str(output_template),
            url,
        ]
        subprocess.run(command, check=True)


def load_library_plan_from_object_id(
    object_store: ObjectStore,
    object_id: str | UUID,
) -> dict[str, Any]:
    parsed_object_id = object_id if isinstance(object_id, UUID) else UUID(str(object_id))
    payload = json.loads(object_store.get_bytes(parsed_object_id).decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("YouTube library plan must be a JSON object.")
    return payload


def load_library_plan_from_run_id(
    object_store: ObjectStore,
    run_id: str | UUID,
) -> dict[str, Any]:
    stored = object_store.find_one(
        run_id=run_id if isinstance(run_id, UUID) else UUID(str(run_id)),
        object_kind=DEFAULT_PLAN_OBJECT_KIND,
        filename=DEFAULT_LIBRARY_PLAN_FILENAME,
    )
    if stored is None:
        raise RuntimeError(f"No YouTube library plan found for run: {run_id}")
    return load_library_plan_from_object_id(object_store, stored.object_id)


def iter_download_entries(plan: dict[str, Any]) -> list[YouTubeDownloadEntry]:
    entries = plan.get("entries")
    if not isinstance(entries, list):
        return []
    return [
        YouTubeDownloadEntry.from_mapping(entry)
        for entry in entries
        if isinstance(entry, dict)
    ]


def find_download_entry(
    plan: dict[str, Any],
    *,
    video_id: str,
) -> YouTubeDownloadEntry:
    for entry in iter_download_entries(plan):
        if entry.video_id == video_id:
            return entry
    raise RuntimeError(f"Video id not found in library plan: {video_id}")


def download_entry_to_object_store(
    *,
    entry: YouTubeDownloadEntry,
    object_store: ObjectStore,
    run_context,
    temp_dir: str | Path | None = None,
    storage_root: str = DEFAULT_LIBRARY_STORAGE_ROOT,
    downloader: YtDlpCommand | None = None,
    cleanup_on_failure: bool = False,
) -> YouTubeDownloadResult:
    """Download one planned video and store it as movie.mp4."""

    if object_exists(
        object_store=object_store,
        storage_root=storage_root,
        object_key=entry.object_key,
        filename=entry.movie_filename,
    ):
        return YouTubeDownloadResult(
            video_id=entry.video_id,
            status="skipped",
            object_key=entry.object_key,
            filename=entry.movie_filename,
            skipped=True,
        )

    work_dir = _work_dir(temp_dir, str(run_context.run_id), entry.video_id)
    work_dir.mkdir(parents=True, exist_ok=True)
    output_template = work_dir / "movie.%(ext)s"
    movie_path = work_dir / MOVIE_FILENAME
    downloader = downloader or YtDlpCommand()

    try:
        downloader.download(url=entry.source_url, output_template=output_template)
        if not movie_path.is_file() or movie_path.stat().st_size <= 0:
            raise RuntimeError(f"yt-dlp did not create a non-empty {MOVIE_FILENAME}")
        stored = object_store.put_file(
            run_context=run_context,
            storage_root=storage_root,
            object_key=entry.object_key,
            filename=entry.movie_filename,
            source_path=movie_path,
            content_type="video/mp4",
            object_kind=MEDIA_ASSET_OBJECT_KIND,
            metadata={
                "source": "youtube",
                "youtube_video_id": entry.video_id,
                "source_url": entry.source_url,
            },
        )
        _remove_dir_if_empty(work_dir)
        return YouTubeDownloadResult(
            video_id=entry.video_id,
            status="downloaded",
            object_id=str(stored.object_id),
            object_key=stored.object_key,
            filename=stored.filename,
        )
    except Exception as exc:
        cleanup_count = 0
        if cleanup_on_failure:
            cleanup_count = cleanup_entry_sidecars(
                object_store=object_store,
                storage_root=storage_root,
                entry=entry,
            )
        raise YouTubeDownloadError(
            result=YouTubeDownloadResult(
                video_id=entry.video_id,
                status="failed",
                object_key=entry.object_key,
                filename=entry.movie_filename,
                error_message=str(exc),
                cleanup_count=cleanup_count,
            )
        ) from exc
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


class YouTubeDownloadError(RuntimeError):
    """Raised when one planned video download fails."""

    def __init__(self, *, result: YouTubeDownloadResult) -> None:
        super().__init__(result.error_message or "YouTube download failed")
        self.result = result


def cleanup_entry_sidecars(
    *,
    object_store: ObjectStore,
    storage_root: str,
    entry: YouTubeDownloadEntry,
) -> int:
    """Delete all object-store objects in one planned video folder."""

    repository = object_store.repository
    objects = getattr(repository, "objects", None)
    if isinstance(objects, dict):
        candidates = [
            obj
            for obj in objects.values()
            if obj.object_key == entry.object_key and obj.deleted_at is None
        ]
    else:
        connection = getattr(repository, "connection", None)
        if connection is None:
            return 0
        root = repository.get_storage_root(storage_root)
        if root is None:
            return 0
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT object_id
                FROM core.stored_object
                WHERE storage_root_id = %s
                  AND object_key = %s
                  AND deleted_at IS NULL
                """,
                (root.storage_root_id, entry.object_key),
            )
            candidates = [
                object_store.get_object(row[0])
                for row in cursor.fetchall()
            ]

    deleted_count = 0
    for stored in candidates:
        if object_store.delete_object(stored.object_id):
            deleted_count += 1
    return deleted_count


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

    objects = getattr(object_store.repository, "objects", None)
    if isinstance(objects, dict):
        if any(
            obj.storage_root_id == root.storage_root_id
            and obj.object_key == object_key
            and obj.filename == filename
            and obj.deleted_at is None
            for obj in objects.values()
        ):
            return True

    connection = getattr(object_store.repository, "connection", None)
    if connection is not None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1
                FROM core.stored_object
                WHERE storage_root_id = %s
                  AND object_key = %s
                  AND filename = %s
                  AND deleted_at IS NULL
                LIMIT 1
                """,
                (root.storage_root_id, object_key, filename),
            )
            if cursor.fetchone() is not None:
                return True

    return FilesystemStorageBackend(root.base_uri).exists(object_key, filename)


def default_temp_dir() -> Path:
    value = os.environ.get("EMPIRE_TEMP_DIR")
    if not value:
        raise ValidationError("Missing required environment variable: EMPIRE_TEMP_DIR")
    return Path(value)


def _work_dir(temp_dir: str | Path | None, run_id: str, video_id: str) -> Path:
    root = Path(temp_dir) if temp_dir is not None else default_temp_dir()
    return root / DEFAULT_TEMP_SUBDIR / run_id / video_id


def _remove_dir_if_empty(path: Path) -> None:
    try:
        path.rmdir()
    except OSError:
        return


def _required_text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise RuntimeError(f"YouTube library plan entry missing required field: {key}")


def _text_or_default(value: Any, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default
