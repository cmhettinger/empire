from __future__ import annotations

import pytest

from empire_youtube.config import YouTubeAPIConfig, YouTubeScraperConfig
from empire_youtube.exceptions import YouTubeConfigError


def test_missing_api_key(monkeypatch):
    monkeypatch.delenv("EMPIRE_YOUTUBE_GOOGLE_API_KEY", raising=False)

    with pytest.raises(YouTubeConfigError, match="EMPIRE_YOUTUBE_GOOGLE_API_KEY"):
        YouTubeAPIConfig.from_env()


def test_api_key_from_env(monkeypatch):
    monkeypatch.setenv("EMPIRE_YOUTUBE_GOOGLE_API_KEY", "test-key")

    config = YouTubeAPIConfig.from_env()

    assert config.api_key == "test-key"


def test_scraper_config_from_yaml():
    config = YouTubeScraperConfig.from_yaml(
        """
youtube:
  name: daily_youtube_scraper
  version: 1
  lookback_hours: 26
  max_results_per_query: 10
  filters:
    exclude_shorts: false
    min_duration_minutes: 2
    language: en
  thumbnail_preference:
    - maxres
    - high
    - default
  topic_sections:
    - key: home_automation
      name: Home Automation
      enabled: true
      topics:
        - key: home_assistant
          name: Home Assistant
          queries:
            - "home assistant"
  followed_channels:
    - channel_name: Graham Hancock
      channel_id: UCk_foUwmaHeFhmAZMnEHQsw
      enabled: true
"""
    )

    assert config.name == "daily_youtube_scraper"
    assert config.lookback_hours == 26
    assert config.filters.min_duration_minutes == 2
    assert config.filters.language == "en"
    assert config.topic_sections[0].topics[0].queries == ["home assistant"]
    assert config.followed_channels[0].channel_id == "UCk_foUwmaHeFhmAZMnEHQsw"
    assert config.followed_channels[0].enabled is True


def test_followed_channel_requires_channel_id():
    with pytest.raises(YouTubeConfigError, match="channel_id"):
        YouTubeScraperConfig.from_mapping(
            {
                "youtube": {
                    "name": "daily",
                    "version": 1,
                    "lookback_hours": 24,
                    "max_results_per_query": 10,
                    "followed_channels": [
                        {"channel_name": "Missing Id", "enabled": True}
                    ],
                }
            }
        )


def test_hydration_is_not_part_of_v1_config_contract():
    with pytest.raises(YouTubeConfigError, match="hydration"):
        YouTubeScraperConfig.from_mapping(
            {
                "youtube": {
                    "name": "daily",
                    "version": 1,
                    "lookback_hours": 24,
                    "max_results_per_query": 10,
                    "hydration": {"parts": ["snippet"]},
                }
            }
        )


def test_max_results_must_match_youtube_limit():
    with pytest.raises(YouTubeConfigError, match="between 1 and 50"):
        YouTubeScraperConfig.from_mapping(
            {
                "youtube": {
                    "name": "daily",
                    "version": 1,
                    "lookback_hours": 24,
                    "max_results_per_query": 51,
                }
            }
        )
