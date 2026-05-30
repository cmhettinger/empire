from __future__ import annotations

import json
from xml.etree import ElementTree

from empire_youtube.processor import (
    FANART_FILENAME,
    MOVIE_NFO_FILENAME,
    ThumbnailAsset,
    YouTubeScrapeProcessor,
    build_jellyfin_object_key,
    jellyfin_friendly_name,
    select_thumbnail_url,
)


def test_processor_builds_jellyfin_library_plan():
    payload = {
        "source": "youtube",
        "schema_version": 1,
        "run_id": "scrape-run",
        "videos": [
            {
                "video_id": "ti41EgYepRA",
                "url": "https://www.youtube.com/watch?v=ti41EgYepRA",
                "title": (
                    "The Psychedelic Christ, the Ark of the Covenant, "
                    "and the Lost Sacrament with William Henry"
                ),
                "description": "A conversation.",
                "channel": {
                    "channel_id": "UC123",
                    "channel_name": "The Randall Carlson",
                },
                "published_at": "2026-05-25T12:00:00Z",
                "content": {"duration_seconds": 4680},
                "thumbnails": {
                    "maxres": {
                        "url": "https://i.ytimg.com/vi/ti41EgYepRA/maxresdefault.jpg"
                    }
                },
            }
        ],
    }

    plan = YouTubeScrapeProcessor(
        thumbnail_fetcher=FakeThumbnailFetcher(),
    ).process(payload)

    assert plan.source == "youtube"
    assert plan.schema_version == 1
    assert plan.source_schema_version == 1
    assert plan.source_run_id == "scrape-run"
    assert plan.source_video_count == 1
    entry = plan.entries[0]
    assert entry.object_key == (
        "media/youtube/The Randall Carlson/"
        "2026-05-25 - The Psychedelic Christ the Ark of the Covenant and the Lost "
        "[ti41EgYepRA]"
    )
    assert entry.movie_filename == "movie.mp4"
    assert entry.empire_metadata_uri == (
        "empire://youtube/videos/ti41EgYepRA/metadata.json"
    )
    assert [file.filename for file in entry.files] == [
        "empire.json",
        MOVIE_NFO_FILENAME,
        FANART_FILENAME,
    ]

    empire = json.loads(entry.files[0].data)
    assert empire["video_id"] == "ti41EgYepRA"
    nfo = entry.files[1].data.decode("utf-8")
    assert "<title>The Psychedelic Christ" in nfo
    assert "<runtime>78</runtime>" in nfo
    assert '<uniqueid type="youtube" default="true">ti41EgYepRA</uniqueid>' in nfo
    assert "plugin://plugin.video.youtube/?action=play_video&amp;videoid=ti41EgYepRA" in nfo
    assert "<source>" not in nfo
    assert "<source_url>" not in nfo
    assert "<empire_metadata_uri>" not in nfo
    assert entry.files[2].data == b"jpg"
    assert json.loads(plan.to_json())["entries"][0]["movie_filename"] == "movie.mp4"
    ElementTree.fromstring(entry.files[1].data)


def test_movie_nfo_escapes_and_removes_unsafe_xml_text():
    payload = {
        "source": "youtube",
        "schema_version": 1,
        "videos": [
            {
                "video_id": "abc123",
                "title": "A & B < C\u0001",
                "description": "Line one & line two < line three\u0008",
                "channel": {"channel_name": "Channel & Co"},
                "published_at": "2026-05-25T12:00:00Z",
            }
        ],
    }

    plan = YouTubeScrapeProcessor(
        thumbnail_fetcher=FakeThumbnailFetcher(),
    ).process(payload)

    nfo = next(
        file for file in plan.entries[0].files if file.filename == MOVIE_NFO_FILENAME
    )
    parsed = ElementTree.fromstring(nfo.data)
    assert parsed.findtext("title") == "A & B < C"
    assert parsed.findtext("plot") == "Line one & line two < line three"
    assert parsed.findtext("studio") == "Channel & Co"


def test_jellyfin_friendly_name_cleans_and_truncates_titles():
    assert (
        jellyfin_friendly_name(
            "The Psychedelic Christ, the Ark of the Covenant, and the Lost "
            "Sacrament with William Henry"
        )
        == "The Psychedelic Christ the Ark of the Covenant and the Lost"
    )
    assert jellyfin_friendly_name("CON") == "CON_video"
    assert jellyfin_friendly_name("  <>:/?*  ") == "untitled"


def test_build_jellyfin_object_key():
    key = build_jellyfin_object_key(
        storage_key_prefix="/media/youtube/",
        channel_name="The Randall Carlson",
        published_date="2026-05-25",
        title="A: Strange/Title?",
        video_id="abc123",
    )

    assert key == (
        "media/youtube/The Randall Carlson/"
        "2026-05-25 - A Strange Title [abc123]"
    )


def test_select_thumbnail_prefers_maxres():
    assert (
        select_thumbnail_url(
            {
                "preferred_thumbnail_url": "preferred",
                "thumbnails": {
                    "high": {"url": "high"},
                    "maxres": {"url": "maxres"},
                },
            }
        )
        == "maxres"
    )


class FakeThumbnailFetcher:
    def fetch(self, url: str) -> ThumbnailAsset:
        assert url.endswith("/maxresdefault.jpg")
        return ThumbnailAsset(data=b"jpg", content_type="image/jpeg")
