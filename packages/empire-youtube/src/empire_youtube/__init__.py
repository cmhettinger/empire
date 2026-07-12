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
from empire_youtube.daily_summary import generate_youtube_daily_summary_pdf_stage
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
from empire_youtube.stager import (
    YouTubeStageResult,
    build_video_from_ytdlp_metadata,
    parse_youtube_video_id,
    stage_folder_name,
    stage_youtube_video,
)

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
    "YouTubeStageResult",
    "YouTubeChannelResolver",
    "DEFAULT_YOUTUBE_DAYS_TO_KEEP",
    "YOUTUBE_DAYS_TO_KEEP_ENV",
    "DEFAULT_LIBRARY_PLAN_FILENAME",
    "build_video_from_ytdlp_metadata",
    "download_entry_to_object_store",
    "find_download_entry",
    "generate_youtube_daily_summary_pdf_stage",
    "iter_download_entries",
    "load_config_by_logical_name",
    "load_config_from_object_id",
    "load_library_plan_from_object_id",
    "load_library_plan_from_run_id",
    "parse_youtube_video_id",
    "resolve_channel",
    "run_youtube_processor_to_object_store",
    "run_youtube_scraper_to_object_store",
    "stage_folder_name",
    "stage_youtube_video",
    "write_result_to_file",
    "youtube_expires_at",
]
