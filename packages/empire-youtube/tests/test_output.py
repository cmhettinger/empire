from __future__ import annotations

import json
from datetime import UTC, datetime

from empire_youtube.models import NormalizedVideo, YouTubeScrapeResult
from empire_youtube.output import write_result_to_file


def test_write_result_to_file_creates_parent_directories(tmp_path):
    result = YouTubeScrapeResult(
        source="youtube",
        generated_at=datetime(2026, 5, 23, 22, 0, tzinfo=UTC),
        window_hours=26,
        run_id="d7e5c5f9-6a5c-4f18-9b1d-8fd1c0d2f92f",
        config_name="daily_youtube_scraper",
        config_version=1,
        videos=[
            NormalizedVideo(
                video_id="abc123",
                url="https://www.youtube.com/watch?v=abc123",
                title="Example",
                description="Description",
                channel_id="UC123",
                channel_name="Example Channel",
                published_at="2026-05-23T12:00:00Z",
            )
        ],
    )
    output_path = tmp_path / "youtube" / "daily" / "youtube-scraper.json"

    returned_path = write_result_to_file(result, output_path)

    assert returned_path == output_path
    assert json.loads(output_path.read_text(encoding="utf-8")) == result.to_dict()
