from __future__ import annotations

from empire_youtube.normalize import (
    build_video_url,
    choose_preferred_thumbnail_url,
    normalize_thumbnails,
    normalize_video,
    parse_iso8601_duration_seconds,
)


def test_duration_parsing():
    assert parse_iso8601_duration_seconds("PT1H23M10S") == 4990
    assert parse_iso8601_duration_seconds("PT2M") == 120
    assert parse_iso8601_duration_seconds("P1DT2H") == 93600
    assert parse_iso8601_duration_seconds(None) is None
    assert parse_iso8601_duration_seconds("not-a-duration") is None


def test_video_url_building():
    assert build_video_url("abc123") == "https://www.youtube.com/watch?v=abc123"


def test_thumbnail_normalization_and_preference():
    thumbnails = normalize_thumbnails(
        {
            "default": {"url": "https://example/default.jpg", "width": 120},
            "maxres": {
                "url": "https://example/maxres.jpg",
                "width": "1280",
                "height": "720",
            },
            "broken": {"width": 10},
        }
    )

    assert sorted(thumbnails) == ["default", "maxres"]
    assert thumbnails["maxres"].width == 1280
    assert thumbnails["maxres"].height == 720
    assert (
        choose_preferred_thumbnail_url(thumbnails, ["standard", "maxres"])
        == "https://example/maxres.jpg"
    )


def test_normalize_video_payload():
    video = normalize_video(
        {
            "id": "abc123xyz",
            "snippet": {
                "title": "Example Video",
                "description": "Description",
                "channelId": "UC123",
                "channelTitle": "Example Channel",
                "publishedAt": "2026-05-23T14:22:17Z",
                "thumbnails": {
                    "high": {
                        "url": "https://example/high.jpg",
                        "width": 480,
                        "height": 360,
                    }
                },
                "tags": ["tag1", "tag2"],
                "categoryId": "27",
                "defaultLanguage": "en",
                "defaultAudioLanguage": "en",
                "liveBroadcastContent": "none",
            },
            "contentDetails": {
                "duration": "PT1H24M51S",
                "definition": "hd",
                "caption": "true",
                "licensedContent": True,
                "projection": "rectangular",
            },
            "statistics": {
                "viewCount": "45231",
                "likeCount": "3180",
                "commentCount": "512",
            },
            "status": {
                "privacyStatus": "public",
                "embeddable": True,
                "madeForKids": False,
            },
            "topicDetails": {
                "topicCategories": ["https://en.wikipedia.org/wiki/Science"]
            },
            "recordingDetails": {"recordingDate": "2026-05-20"},
            "liveStreamingDetails": {"actualStartTime": None, "actualEndTime": None},
            "player": {"embedHtml": "<iframe></iframe>"},
            "paidProductPlacementDetails": {"hasPaidProductPlacement": False},
        },
        thumbnail_preference=["maxres", "high"],
    )

    data = video.to_dict()
    assert data == {
        "video_id": "abc123xyz",
        "url": "https://www.youtube.com/watch?v=abc123xyz",
        "title": "Example Video",
        "description": "Description",
        "channel": {
            "channel_id": "UC123",
            "channel_name": "Example Channel",
        },
        "published_at": "2026-05-23T14:22:17Z",
        "content": {
            "duration_iso8601": "PT1H24M51S",
            "duration_seconds": 5091,
            "definition": "hd",
            "caption": True,
            "licensed_content": True,
            "projection": "rectangular",
        },
        "statistics": {
            "view_count": 45231,
            "like_count": 3180,
            "comment_count": 512,
        },
        "status": {
            "privacy_status": "public",
            "embeddable": True,
            "made_for_kids": False,
        },
        "topics": {
            "youtube_topic_categories": ["https://en.wikipedia.org/wiki/Science"],
        },
        "recording": {
            "recording_date": "2026-05-20",
        },
        "live_stream": {
            "live_broadcast_content": "none",
            "actual_start_time": None,
            "actual_end_time": None,
        },
        "thumbnails": {
            "high": {
                "url": "https://example/high.jpg",
                "width": 480,
                "height": 360,
            }
        },
        "preferred_thumbnail_url": "https://example/high.jpg",
        "tags": ["tag1", "tag2"],
        "default_language": "en",
        "default_audio_language": "en",
        "matched_sections": [],
        "matched_topics": [],
        "matched_queries": [],
        "matched_channels": [],
        "discovery_sources": [],
        "youtube": {
            "category_id": "27",
            "embed_html": "<iframe></iframe>",
            "contains_paid_product_placement": False,
        },
    }
