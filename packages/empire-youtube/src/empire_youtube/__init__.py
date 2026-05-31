"""Reusable YouTube metadata scraping helpers for Empire."""

from empire_youtube.client import YouTubeClient
from empire_youtube.config import YouTubeAPIConfig, YouTubeScraperConfig
from empire_youtube.downloader import (
    YouTubeDownloadEntry,
    YouTubeDownloadError,
    YouTubeDownloadResult,
    download_entry_to_object_store,
    find_download_entry,
    iter_download_entries,
    load_library_plan_from_object_id,
    load_library_plan_from_run_id,
)
from empire_youtube.exceptions import (
    EmpireYouTubeError,
    YouTubeAPIError,
    YouTubeConfigError,
    YouTubeResponseError,
)
from empire_youtube.models import (
    MatchedChannel,
    NormalizedVideo,
    Thumbnail,
    YouTubeChannel,
    YouTubeScrapeResult,
)
from empire_youtube.object_store import (
    DEFAULT_CONFIG_LOGICAL_NAME,
    load_config_by_logical_name,
    load_config_from_object_id,
)
from empire_youtube.output import write_result_to_file
from empire_youtube.processor import YouTubeLibraryPlan, YouTubeScrapeProcessor
from empire_youtube.retention import (
    DEFAULT_YOUTUBE_DAYS_TO_KEEP,
    YOUTUBE_DAYS_TO_KEEP_ENV,
    youtube_expires_at,
)
from empire_youtube.resolver import YouTubeChannelResolver, resolve_channel
from empire_youtube.runner import (
    DEFAULT_LIBRARY_PLAN_FILENAME,
    DEFAULT_OUTPUT_FILENAME,
    YouTubeProcessRunResult,
    YouTubeScrapeRunResult,
    run_youtube_processor_to_object_store,
    run_youtube_scraper_to_object_store,
)
from empire_youtube.scraper import YouTubeScraper

__all__ = [
    "DEFAULT_CONFIG_LOGICAL_NAME",
    "DEFAULT_OUTPUT_FILENAME",
    "EmpireYouTubeError",
    "MatchedChannel",
    "NormalizedVideo",
    "Thumbnail",
    "YouTubeChannel",
    "YouTubeAPIConfig",
    "YouTubeAPIError",
    "YouTubeClient",
    "YouTubeConfigError",
    "YouTubeDownloadEntry",
    "YouTubeDownloadError",
    "YouTubeDownloadResult",
    "YouTubeLibraryPlan",
    "YouTubeProcessRunResult",
    "YouTubeResponseError",
    "YouTubeScrapeRunResult",
    "YouTubeScrapeResult",
    "YouTubeScrapeProcessor",
    "YouTubeScraper",
    "YouTubeScraperConfig",
    "YouTubeChannelResolver",
    "DEFAULT_YOUTUBE_DAYS_TO_KEEP",
    "YOUTUBE_DAYS_TO_KEEP_ENV",
    "DEFAULT_LIBRARY_PLAN_FILENAME",
    "download_entry_to_object_store",
    "find_download_entry",
    "iter_download_entries",
    "load_config_by_logical_name",
    "load_config_from_object_id",
    "load_library_plan_from_object_id",
    "load_library_plan_from_run_id",
    "resolve_channel",
    "run_youtube_processor_to_object_store",
    "run_youtube_scraper_to_object_store",
    "write_result_to_file",
    "youtube_expires_at",
]
