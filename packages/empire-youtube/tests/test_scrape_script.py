from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from empire_youtube.models import YouTubeScrapeResult
from empire_youtube.scripts import scrape as script


def test_parse_args_defaults_to_object_store_logical_name():
    args = script.parse_args([])

    assert args.config_file is None
    assert args.config_object_id is None
    assert args.config_logical_name == "youtube-daily-config"
    assert args.run_type == "cli"
    assert args.runner == "bin/youtube-scrape"
    assert args.output_file is None


def test_parse_args_accepts_config_file_override():
    args = script.parse_args(["--config-file", "object-store/config/youtube/config.yml"])

    assert args.config_file == "object-store/config/youtube/config.yml"


def test_parse_args_accepts_output_file():
    args = script.parse_args(["--output-file", "/tmp/youtube-scraper.json"])

    assert args.output_file == "/tmp/youtube-scraper.json"


def test_load_config_from_file(tmp_path, monkeypatch):
    config_file = tmp_path / "daily.yml"
    config_file.write_text(
        """
youtube:
  name: daily_youtube_scraper
  version: 1
  lookback_hours: 26
  max_results_per_query: 10
  followed_channels:
    - channel_name: All-In Podcast
      channel_id: UCESLZhusAkFfsNsApnjF_Cg
""",
        encoding="utf-8",
    )
    args = script.parse_args(["--config-file", str(config_file)])

    config = script.load_config(args, object_store=object())

    assert config.name == "daily_youtube_scraper"
    assert config.followed_channels[0].channel_id == "UCESLZhusAkFfsNsApnjF_Cg"


def test_load_config_from_object_id(monkeypatch):
    object_id = uuid4()
    calls = []
    monkeypatch.setattr(
        script,
        "load_config_from_object_id",
        lambda object_store, value: calls.append((object_store, value)) or "config",
    )
    args = script.parse_args(["--config-object-id", str(object_id)])
    object_store = object()

    config = script.load_config(args, object_store=object_store)

    assert config == "config"
    assert calls == [(object_store, str(object_id))]


def test_load_config_from_logical_name(monkeypatch):
    calls = []
    monkeypatch.setattr(
        script,
        "load_config_by_logical_name",
        lambda object_store, *, logical_name: calls.append(
            (object_store, logical_name)
        )
        or "config",
    )
    args = script.parse_args(["--config-logical-name", "youtube-test-config"])
    object_store = object()

    config = script.load_config(args, object_store=object_store)

    assert config == "config"
    assert calls == [(object_store, "youtube-test-config")]


def test_main_with_config_file_and_output_file_bypasses_database(
    tmp_path,
    monkeypatch,
    capsys,
):
    config_file = tmp_path / "daily.yml"
    output_file = tmp_path / "out" / "youtube-scraper.json"
    config_file.write_text(
        """
youtube:
  name: daily_youtube_scraper
  version: 1
  lookback_hours: 26
  max_results_per_query: 10
  followed_channels:
    - channel_name: All-In Podcast
      channel_id: UCESLZhusAkFfsNsApnjF_Cg
""",
        encoding="utf-8",
    )

    class FakeScraper:
        def __init__(self, config):
            self.config = config

        def scrape(self):
            return YouTubeScrapeResult(
                source="youtube",
                generated_at=datetime(2026, 5, 23, 22, 0, tzinfo=UTC),
                window_hours=self.config.lookback_hours,
                run_id=None,
                config_name=self.config.name,
                config_version=self.config.version,
                videos=[],
            )

    monkeypatch.setattr(script, "YouTubeScraper", FakeScraper)
    monkeypatch.setattr(
        script.EmpireDatabase,
        "connect_from_env",
        lambda: (_ for _ in ()).throw(AssertionError("database not expected")),
    )

    script.main(
        [
            "--config-file",
            str(config_file),
            "--output-file",
            str(output_file),
        ]
    )

    assert output_file.exists()
    assert "video_count: 0" in capsys.readouterr().out
