from __future__ import annotations

import json
from datetime import UTC, datetime

from empire_youtube.models import NormalizedVideo, YouTubeScrapeResult


def test_scrape_result_output_contract():
    result = YouTubeScrapeResult(
        source="youtube",
        generated_at=datetime(2026, 5, 23, 22, 0, tzinfo=UTC),
        window_hours=26,
        run_id="d7e5c5f9-6a5c-4f18-9b1d-8fd1c0d2f92f",
        config_name="daily_youtube_scraper",
        config_version=1,
        videos=[
            NormalizedVideo(
                video_id="abc123xyz",
                url="https://www.youtube.com/watch?v=abc123xyz",
                title="Example Video",
                description="Description",
                channel_id="UC123",
                channel_name="Example Channel",
                published_at="2026-05-23T14:22:17Z",
            )
        ],
    )

    data = result.to_dict()

    assert data["source"] == "youtube"
    assert data["schema_version"] == 1
    assert data["generated_at"] == "2026-05-23T22:00:00Z"
    assert data["window_hours"] == 26
    assert data["run_id"] == "d7e5c5f9-6a5c-4f18-9b1d-8fd1c0d2f92f"
    assert data["config"] == {
        "name": "daily_youtube_scraper",
        "version": 1,
        "topic_section_names": {},
    }
    assert data["videos"][0]["video_id"] == "abc123xyz"

    serialized = result.to_json()
    assert json.loads(serialized) == data
    assert serialized.endswith("\n") is False
