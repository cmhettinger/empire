from __future__ import annotations

from uuid import uuid4

from empire_youtube.scripts import put_config as script


def test_parse_args_defaults():
    args = script.parse_args(["deploy/config/youtube/daily.yml"])

    assert args.config_file == "deploy/config/youtube/daily.yml"
    assert args.logical_name == "youtube-daily-config"
    assert args.filename == "daily.yml"
    assert args.storage_root is None
    assert args.storage_key is None


def test_main_publishes_config(monkeypatch, tmp_path, capsys):
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
    fake_store = FakeObjectStore()
    monkeypatch.setenv("EMPIRE_STORAGE_KEY_YOUTUBE", "youtube")
    monkeypatch.setattr(
        script.EmpireDatabase,
        "connect_from_env",
        lambda: FakeConnection(),
    )
    monkeypatch.setattr(
        script.ObjectStore,
        "from_connection",
        lambda connection: fake_store,
    )

    script.main([str(config_file)])

    assert fake_store.calls[0]["object_scope"] == "reference"
    assert fake_store.calls[0]["domain"] == "youtube"
    assert fake_store.calls[0]["logical_name"] == "youtube-daily-config"
    assert fake_store.calls[0]["storage_root"] == "global"
    assert fake_store.calls[0]["object_key"] == "youtube/config"
    assert fake_store.calls[0]["filename"] == "daily.yml"
    assert fake_store.calls[0]["content_type"] == "text/yaml"
    assert fake_store.calls[0]["object_kind"] == "scraper_config"
    assert "stored_object_id:" in capsys.readouterr().out


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None


class FakeObject:
    object_id = uuid4()
    logical_name = "youtube-daily-config"
    object_key = "youtube/config"
    filename = "daily.yml"


class FakeObjectStore:
    def __init__(self):
        self.calls = []

    def put_bytes(self, **kwargs):
        self.calls.append(kwargs)
        return FakeObject()
