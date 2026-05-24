"""Channel resolution utilities for YouTube metadata scraping."""

from __future__ import annotations

from empire_youtube.client import YouTubeClient
from empire_youtube.exceptions import YouTubeResponseError
from empire_youtube.models import YouTubeChannel


class YouTubeChannelResolver:
    """Resolve public YouTube channel identifiers into canonical metadata."""

    def __init__(self, client: YouTubeClient | None = None) -> None:
        self.client = client or YouTubeClient()

    def resolve(self, value: str) -> YouTubeChannel:
        """Resolve a channel id, handle, or search query."""

        cleaned = value.strip()
        if not cleaned:
            raise YouTubeResponseError("Channel identifier is required.")

        if cleaned.startswith("UC"):
            return self.resolve_channel_id(cleaned)
        if cleaned.startswith("@"):
            return self.resolve_handle(cleaned)
        return self.search_channel(cleaned)

    def resolve_handle(self, handle: str) -> YouTubeChannel:
        """Resolve a YouTube handle such as @grahamhancock."""

        response = self.client.resolve_channel_handle(handle)
        items = response.get("items") or []
        if not items:
            raise YouTubeResponseError(f"YouTube channel handle not found: {handle}")
        return channel_from_api_item(items[0], requested_handle=handle)

    def resolve_channel_id(self, channel_id: str) -> YouTubeChannel:
        """Resolve a YouTube channel id such as UC..."""

        response = self.client.get_channel(channel_id)
        items = response.get("items") or []
        if not items:
            raise YouTubeResponseError(f"YouTube channel id not found: {channel_id}")
        return channel_from_api_item(items[0])

    def search_channel(self, query: str) -> YouTubeChannel:
        """Resolve the first channel match for a search query."""

        response = self.client.search_channel(query, max_results=1)
        items = response.get("items") or []
        if not items:
            raise YouTubeResponseError(f"YouTube channel search returned no results: {query}")

        search_item = items[0]
        channel_id = (search_item.get("id") or {}).get("channelId")
        if not channel_id:
            raise YouTubeResponseError("YouTube channel search result did not include channelId.")
        return self.resolve_channel_id(str(channel_id))


def resolve_channel(value: str, *, client: YouTubeClient | None = None) -> YouTubeChannel:
    """Resolve a YouTube channel id, handle, or search query."""

    return YouTubeChannelResolver(client=client).resolve(value)


def channel_from_api_item(
    item: dict,
    *,
    requested_handle: str | None = None,
) -> YouTubeChannel:
    snippet = item.get("snippet") or {}
    content_details = item.get("contentDetails") or {}
    related_playlists = content_details.get("relatedPlaylists") or {}

    channel_id = item.get("id")
    if not channel_id:
        raise YouTubeResponseError("YouTube channel response did not include id.")

    return YouTubeChannel(
        channel_id=str(channel_id),
        channel_name=snippet.get("title") or str(channel_id),
        description=snippet.get("description"),
        custom_url=snippet.get("customUrl"),
        handle=requested_handle or snippet.get("customUrl"),
        published_at=snippet.get("publishedAt"),
        thumbnail_url=_best_thumbnail_url(snippet.get("thumbnails") or {}),
        uploads_playlist_id=related_playlists.get("uploads"),
    )


def _best_thumbnail_url(thumbnails: dict) -> str | None:
    for name in ["maxres", "standard", "high", "medium", "default"]:
        thumbnail = thumbnails.get(name) or {}
        if thumbnail.get("url"):
            return str(thumbnail["url"])
    return None
