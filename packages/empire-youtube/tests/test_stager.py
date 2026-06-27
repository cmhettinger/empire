from __future__ import annotations

import json
from xml.etree import ElementTree

import pytest

from empire_youtube.processor import MOVIE_FILENAME
from empire_youtube.stager import (
    build_video_from_ytdlp_metadata,
    parse_youtube_video_id,
    stage_youtube_video,
    stage_folder_name,
)


def test_parse_youtube_video_id_accepts_common_urls():
    assert (
        parse_youtube_video_id("https://www.youtube.com/watch?v=y7zqvSpt1gw")
        == "y7zqvSpt1gw"
    )
    assert parse_youtube_video_id("https://youtu.be/y7zqvSpt1gw?t=10") == "y7zqvSpt1gw"
    assert (
        parse_youtube_video_id("https://www.youtube.com/shorts/y7zqvSpt1gw")
        == "y7zqvSpt1gw"
    )


def test_build_video_from_ytdlp_metadata_maps_processor_shape():
    video = build_video_from_ytdlp_metadata(
        {
            "id": "abc123",
            "webpage_url": "https://www.youtube.com/watch?v=abc123",
            "title": "Example Video",
            "description": "A useful example.",
            "channel": "Example Channel",
            "channel_id": "UC123",
            "upload_date": "20260601",
            "duration": 125,
            "thumbnail": "https://example.test/thumb.jpg",
            "view_count": "10",
            "tags": ["one", "two"],
        },
        source_url="https://www.youtube.com/watch?v=abc123",
        requested_video_id=None,
    )

    assert video["video_id"] == "abc123"
    assert video["channel"]["channel_name"] == "Example Channel"
    assert video["published_at"] == "2026-06-01T00:00:00Z"
    assert video["content"]["duration_seconds"] == 125
    assert video["statistics"]["view_count"] == 10
    assert video["preferred_thumbnail_url"] == "https://example.test/thumb.jpg"


def test_stage_youtube_video_writes_movie_and_sidecars(tmp_path):
    result = stage_youtube_video(
        url="https://www.youtube.com/watch?v=abc123",
        temp_dir=tmp_path,
        info_extractor=FakeInfoExtractor(),
        downloader=FakeDownloader(),
    )

    output_dir = tmp_path / "Example Video [abc123]"
    assert result.video_id == "abc123"
    assert result.output_dir == output_dir
    assert result.files == ["empire.json", "movie.mp4", "movie.nfo"]
    assert (output_dir / MOVIE_FILENAME).read_bytes() == b"video"

    empire = json.loads((output_dir / "empire.json").read_text(encoding="utf-8"))
    assert empire["video_id"] == "abc123"
    assert empire["discovery_sources"] == ["youtube_stage"]
    nfo = ElementTree.fromstring((output_dir / "movie.nfo").read_bytes())
    assert nfo.findtext("title") == "Example Video"
    assert nfo.findtext("runtime") == "2"
    assert not (output_dir / ".download").exists()


def test_stage_youtube_video_uses_empire_temp_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("EMPIRE_TEMP_DIR", str(tmp_path))

    result = stage_youtube_video(
        url="https://www.youtube.com/watch?v=abc123",
        info_extractor=FakeInfoExtractor(),
        downloader=FakeDownloader(),
    )

    assert result.output_dir == tmp_path / "Example Video [abc123]"


def test_stage_folder_name_uses_title_and_video_id_without_date():
    entry = FakeEntry(
        video_id="abc123",
        title="Example: Video?",
        published_date="2026-06-01",
    )

    assert stage_folder_name(entry) == "Example Video [abc123]"


def test_stage_youtube_video_rejects_live_video(tmp_path):
    with pytest.raises(RuntimeError, match="not download-ready"):
        stage_youtube_video(
            url="https://www.youtube.com/watch?v=abc123",
            temp_dir=tmp_path,
            info_extractor=FakeInfoExtractor(live_status="is_live"),
            downloader=FakeDownloader(),
        )


class FakeInfoExtractor:
    def __init__(self, live_status: str = "not_live"):
        self.live_status = live_status

    def extract(self, url):
        assert url == "https://www.youtube.com/watch?v=abc123"
        return {
            "id": "abc123",
            "webpage_url": url,
            "title": "Example Video",
            "description": "A useful example.",
            "channel": "Example Channel",
            "channel_id": "UC123",
            "upload_date": "20260601",
            "duration": 125,
            "live_status": self.live_status,
        }


class FakeDownloader:
    def download(self, *, url, output_template):
        assert url == "https://www.youtube.com/watch?v=abc123"
        output_template.parent.mkdir(parents=True, exist_ok=True)
        (output_template.parent / MOVIE_FILENAME).write_bytes(b"video")


class FakeEntry:
    def __init__(self, *, video_id: str, title: str, published_date: str):
        self.video_id = video_id
        self.title = title
        self.published_date = published_date
