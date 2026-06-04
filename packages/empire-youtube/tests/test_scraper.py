from __future__ import annotations

from datetime import UTC, datetime

from empire_youtube.config import YouTubeScraperConfig
from empire_youtube.models import NormalizedVideo
from empire_youtube.scraper import YouTubeScraper


class FakeYouTubeClient:
    def __init__(self) -> None:
        self.video_calls = []
        self.channel_upload_calls = []

    def search_videos(self, query, *, max_results, published_after, relevance_language):
        if query == "younger dryas":
            return {"items": [{"id": {"videoId": "abc123"}}]}
        return {"items": []}

    def get_recent_channel_uploads(self, channel_id, max_results, *, published_after):
        raise AssertionError("followed channels should use uploads playlists")

    def get_channel_uploads_playlist(self, channel_id):
        self.channel_upload_calls.append(channel_id)
        return "UU123"

    def get_playlist_items(self, playlist_id, *, max_results):
        return {
            "items": [
                {"contentDetails": {"videoId": "abc123"}},
                {"contentDetails": {"videoId": "old123"}},
            ]
        }

    def get_videos(self, video_ids, *, parts):
        self.video_calls.append({"video_ids": video_ids, "parts": parts})
        payloads = {
            "abc123": {
                    "id": "abc123",
                    "snippet": {
                        "title": "The Younger Dryas Impact Theory Explained",
                        "description": "Description",
                        "channelId": "UC123",
                        "channelTitle": "Randall Carlson",
                        "publishedAt": "2026-05-23T14:22:17Z",
                        "thumbnails": {},
                    },
                    "contentDetails": {"duration": "PT1H24M51S"},
                    "statistics": {},
                    "status": {},
                },
            "old123": {
                "id": "old123",
                "snippet": {
                    "title": "Old Video",
                    "description": "Old",
                    "channelId": "UC123",
                    "channelTitle": "Randall Carlson",
                    "publishedAt": "2026-05-20T14:22:17Z",
                    "thumbnails": {},
                },
                "contentDetails": {"duration": "PT10M"},
                "statistics": {},
                "status": {},
            },
        }
        return {
            "items": [
                payloads[video_id]
                for video_id in video_ids
                if video_id in payloads
            ]
        }

    def resolve_channel_handle(self, handle):
        return {
            "items": [
                {
                    "id": "UCk_foUwmaHeFhmAZMnEHQsw",
                    "snippet": {"title": "Graham Hancock"},
                }
            ]
        }


def test_scraper_dedupes_and_merges_discovery_sources():
    config = YouTubeScraperConfig.from_mapping(
        {
            "youtube": {
                "name": "daily_youtube_scraper",
                "version": 1,
                "lookback_hours": 26,
                "max_results_per_query": 10,
                "topic_sections": [
                    {
                        "key": "ancient_history",
                        "name": "Ancient History",
                        "topics": [
                            {
                                "key": "catastrophism",
                                "name": "Catastrophism",
                                "queries": ["younger dryas"],
                            }
                        ],
                    }
                ],
                "followed_channels": [
                    {
                        "channel_name": "Randall Carlson",
                        "channel_id": "UC123",
                        "enabled": True,
                    }
                ],
            }
        }
    )
    client = FakeYouTubeClient()
    scraper = YouTubeScraper(client=client, config=config)

    result = scraper.scrape(
        generated_at=datetime(2026, 5, 23, 22, 0, tzinfo=UTC),
        run_id="d7e5c5f9-6a5c-4f18-9b1d-8fd1c0d2f92f",
    ).to_dict()

    assert result["source"] == "youtube"
    assert result["schema_version"] == 1
    assert result["generated_at"] == "2026-05-23T22:00:00Z"
    assert result["window_hours"] == 26
    assert result["config"] == {
        "name": "daily_youtube_scraper",
        "version": 1,
        "topic_section_names": {"ancient_history": "Ancient History"},
    }
    assert len(result["videos"]) == 1
    video = result["videos"][0]
    assert video["matched_sections"] == ["ancient_history"]
    assert video["matched_topics"] == ["catastrophism"]
    assert video["matched_queries"] == ["younger dryas"]
    assert video["matched_channels"] == [
        {"channel_name": "Randall Carlson", "channel_id": "UC123"}
    ]
    assert video["discovery_sources"] == ["topic_search", "channel_watch"]
    assert client.channel_upload_calls == ["UC123"]


def test_resolve_channel_handle():
    config = YouTubeScraperConfig.from_mapping(
        {
            "youtube": {
                "name": "daily_youtube_scraper",
                "version": 1,
                "lookback_hours": 26,
                "max_results_per_query": 10,
                "followed_channels": [],
            }
        }
    )
    scraper = YouTubeScraper(client=FakeYouTubeClient(), config=config)

    channel = scraper.resolve_channel("@grahamhancock")

    assert channel.channel_name == "Graham Hancock"
    assert channel.channel_id == "UCk_foUwmaHeFhmAZMnEHQsw"


def test_language_filter_keeps_english_and_unknown_language():
    scraper = YouTubeScraper(client=FakeYouTubeClient(), config=_language_config())

    assert scraper._passes_filters(
        _video(default_language="en", default_audio_language=None)
    )
    assert scraper._passes_filters(
        _video(default_language=None, default_audio_language="en-US")
    )
    assert scraper._passes_filters(
        _video(default_language=None, default_audio_language=None)
    )


def test_language_filter_excludes_declared_non_english_language():
    scraper = YouTubeScraper(client=FakeYouTubeClient(), config=_language_config())

    assert not scraper._passes_filters(
        _video(default_language="es", default_audio_language="es")
    )


def _language_config():
    return YouTubeScraperConfig.from_mapping(
        {
            "youtube": {
                "name": "daily_youtube_scraper",
                "version": 1,
                "lookback_hours": 26,
                "max_results_per_query": 10,
                "filters": {"language": "en"},
                "followed_channels": [],
            }
        }
    )


def _video(*, default_language, default_audio_language):
    return NormalizedVideo(
        video_id="abc123",
        url="https://www.youtube.com/watch?v=abc123",
        title="Example",
        description="Description",
        channel_id="UC123",
        channel_name="Example Channel",
        published_at="2026-05-23T12:00:00Z",
        content={"duration_seconds": 120},
        default_language=default_language,
        default_audio_language=default_audio_language,
    )
