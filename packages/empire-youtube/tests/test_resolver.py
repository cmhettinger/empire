from __future__ import annotations

import pytest

from empire_youtube.exceptions import YouTubeResponseError
from empire_youtube.resolver import YouTubeChannelResolver, resolve_channel


class FakeYouTubeClient:
    def __init__(self) -> None:
        self.calls = []

    def resolve_channel_handle(self, handle):
        self.calls.append(("resolve_channel_handle", handle))
        return {
            "items": [
                {
                    "id": "UCk_foUwmaHeFhmAZMnEHQsw",
                    "snippet": {
                        "title": "Graham Hancock",
                        "customUrl": "@grahamhancock",
                        "description": "Author",
                        "publishedAt": "2012-01-01T00:00:00Z",
                        "thumbnails": {
                            "high": {"url": "https://example/high.jpg"}
                        },
                    },
                    "contentDetails": {
                        "relatedPlaylists": {"uploads": "UUk_foUwmaHeFhmAZMnEHQsw"}
                    },
                }
            ]
        }

    def get_channel(self, channel_id):
        self.calls.append(("get_channel", channel_id))
        return {
            "items": [
                {
                    "id": channel_id,
                    "snippet": {"title": "All-In Podcast"},
                    "contentDetails": {
                        "relatedPlaylists": {"uploads": "UUESLZhusAkFfsNsApnjF_Cg"}
                    },
                }
            ]
        }

    def search_channel(self, query, *, max_results):
        self.calls.append(("search_channel", query, max_results))
        return {"items": [{"id": {"channelId": "UCSEARCH"}}]}


def test_resolve_handle():
    resolver = YouTubeChannelResolver(FakeYouTubeClient())

    channel = resolver.resolve("@grahamhancock")

    assert channel.channel_name == "Graham Hancock"
    assert channel.channel_id == "UCk_foUwmaHeFhmAZMnEHQsw"
    assert channel.handle == "@grahamhancock"
    assert channel.custom_url == "@grahamhancock"
    assert channel.thumbnail_url == "https://example/high.jpg"
    assert channel.uploads_playlist_id == "UUk_foUwmaHeFhmAZMnEHQsw"


def test_resolve_channel_id():
    resolver = YouTubeChannelResolver(FakeYouTubeClient())

    channel = resolver.resolve("UCESLZhusAkFfsNsApnjF_Cg")

    assert channel.channel_name == "All-In Podcast"
    assert channel.channel_id == "UCESLZhusAkFfsNsApnjF_Cg"


def test_resolve_search_query_uses_first_channel_result():
    client = FakeYouTubeClient()
    resolver = YouTubeChannelResolver(client)

    channel = resolver.resolve("All-In Podcast")

    assert channel.channel_id == "UCSEARCH"
    assert client.calls == [
        ("search_channel", "All-In Podcast", 1),
        ("get_channel", "UCSEARCH"),
    ]


def test_package_level_resolve_channel():
    channel = resolve_channel("@grahamhancock", client=FakeYouTubeClient())

    assert channel.channel_name == "Graham Hancock"


def test_empty_channel_identifier_fails():
    resolver = YouTubeChannelResolver(FakeYouTubeClient())

    with pytest.raises(YouTubeResponseError, match="required"):
        resolver.resolve(" ")
