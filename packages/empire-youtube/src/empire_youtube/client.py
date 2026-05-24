"""Lightweight YouTube Data API v3 client."""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from empire_youtube.config import YouTubeAPIConfig
from empire_youtube.exceptions import YouTubeAPIError, YouTubeResponseError


logger = logging.getLogger(__name__)

DEFAULT_SEARCH_THROTTLE_SECONDS = 7.0


class YouTubeClient:
    """Small API-key client for YouTube Data API v3."""

    def __init__(
        self,
        config: YouTubeAPIConfig | None = None,
        *,
        session: requests.Session | None = None,
        retry_count: int = 2,
        retry_backoff_seconds: float = 0.5,
        search_throttle_seconds: float = DEFAULT_SEARCH_THROTTLE_SECONDS,
    ) -> None:
        self.config = config or YouTubeAPIConfig.from_env()
        self.session = session or requests.Session()
        self.retry_count = retry_count
        self.retry_backoff_seconds = retry_backoff_seconds
        self.search_throttle_seconds = search_throttle_seconds
        self._last_search_request_at: float | None = None

    def search_channel(self, query: str, *, max_results: int = 5) -> dict[str, Any]:
        self._throttle_search_request()
        return self._get(
            "search",
            {
                "part": "snippet",
                "q": query,
                "type": "channel",
                "maxResults": max_results,
            },
        )

    def search_videos(
        self,
        query: str,
        *,
        max_results: int = 10,
        published_after: str | None = None,
        relevance_language: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "order": "date",
            "maxResults": max_results,
        }
        if published_after:
            params["publishedAfter"] = published_after
        if relevance_language:
            params["relevanceLanguage"] = relevance_language
        self._throttle_search_request()
        return self._get("search", params)

    def get_channel(self, channel_id: str) -> dict[str, Any]:
        return self._get(
            "channels",
            {
                "part": "snippet,contentDetails,statistics",
                "id": channel_id,
            },
        )

    def resolve_channel_handle(self, handle: str) -> dict[str, Any]:
        return self._get(
            "channels",
            {
                "part": "snippet,contentDetails,statistics",
                "forHandle": handle,
            },
        )

    def get_channel_uploads_playlist(self, channel_id: str) -> str:
        response = self.get_channel(channel_id)
        items = response.get("items") or []
        if not items:
            raise YouTubeResponseError(f"Channel not found: {channel_id}")
        uploads = (
            items[0]
            .get("contentDetails", {})
            .get("relatedPlaylists", {})
            .get("uploads")
        )
        if not uploads:
            raise YouTubeResponseError(
                f"Channel does not expose an uploads playlist: {channel_id}"
            )
        return str(uploads)

    def get_playlist(self, playlist_id: str) -> dict[str, Any]:
        return self._get(
            "playlists",
            {
                "part": "snippet,contentDetails",
                "id": playlist_id,
            },
        )

    def get_playlist_items(
        self,
        playlist_id: str,
        *,
        max_results: int = 25,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "part": "snippet,contentDetails",
            "playlistId": playlist_id,
            "maxResults": max_results,
        }
        if page_token:
            params["pageToken"] = page_token
        return self._get("playlistItems", params)

    def get_video(self, video_id: str, *, parts: list[str] | None = None) -> dict[str, Any]:
        return self.get_videos([video_id], parts=parts)

    def get_videos(
        self,
        video_ids: list[str],
        *,
        parts: list[str] | None = None,
    ) -> dict[str, Any]:
        if not video_ids:
            return {"items": []}
        return self._get(
            "videos",
            {
                "part": ",".join(parts or ["snippet", "contentDetails", "statistics"]),
                "id": ",".join(video_ids),
            },
        )

    def get_recent_channel_uploads(
        self,
        channel_id: str,
        max_results: int,
        *,
        published_after: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "part": "snippet",
            "channelId": channel_id,
            "type": "video",
            "order": "date",
            "maxResults": max_results,
        }
        if published_after:
            params["publishedAfter"] = published_after
        self._throttle_search_request()
        return self._get("search", params)

    def _throttle_search_request(self) -> None:
        if self.search_throttle_seconds <= 0:
            return
        now = time.monotonic()
        if self._last_search_request_at is not None:
            elapsed = now - self._last_search_request_at
            wait_seconds = self.search_throttle_seconds - elapsed
            if wait_seconds > 0:
                logger.debug(
                    "Throttling YouTube search request",
                    extra={"wait_seconds": wait_seconds},
                )
                time.sleep(wait_seconds)
        self._last_search_request_at = time.monotonic()

    def _get(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.config.base_url.rstrip('/')}/{endpoint}"
        request_params = {**params, "key": self.config.api_key}

        logger.debug(
            "Calling YouTube Data API",
            extra={"endpoint": endpoint, "params": _safe_params(request_params)},
        )
        for attempt in range(self.retry_count + 1):
            try:
                response = self.session.get(
                    url,
                    params=request_params,
                    timeout=self.config.timeout_seconds,
                )
            except requests.RequestException as exc:
                if attempt >= self.retry_count:
                    raise YouTubeAPIError(f"YouTube API request failed: {exc}") from exc
                time.sleep(self.retry_backoff_seconds * (2**attempt))
                continue

            if response.status_code >= 500 and attempt < self.retry_count:
                time.sleep(self.retry_backoff_seconds * (2**attempt))
                continue

            if response.status_code >= 400:
                raise YouTubeAPIError(
                    f"YouTube API returned HTTP {response.status_code}: {response.text}"
                )

            try:
                payload = response.json()
            except ValueError as exc:
                raise YouTubeResponseError("YouTube API returned invalid JSON.") from exc

            if not isinstance(payload, dict):
                raise YouTubeResponseError("YouTube API response must be a JSON object.")
            return payload

        raise YouTubeAPIError("YouTube API request failed after retries.")


def _safe_params(params: dict[str, Any]) -> dict[str, Any]:
    safe = dict(params)
    if "key" in safe:
        safe["key"] = "***"
    return safe
