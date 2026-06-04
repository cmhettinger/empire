from __future__ import annotations

from uuid import uuid4

from empire_weather.scripts import put_config as script
from empire_weather.scripts.put_config import DEFAULT_LOCAL_CONFIG_FILE, parse_args


def test_put_config_defaults_to_seed_config_file():
    args = parse_args([])

    assert args.config_file is None


def test_put_config_default_path_constant_points_to_seed_config():
    assert DEFAULT_LOCAL_CONFIG_FILE == "object-store/config/weather/config.yml"


def test_main_publishes_config(monkeypatch, tmp_path, capsys):
    config_file = tmp_path / "config.yml"
    config_file.write_text(
        """
weather:
  name: daily_weather
  version: 1
  locations:
    - key: ashburn_va
      name: Ashburn
      county: Loudoun
      state: Virginia
      lat: 39.0277
      lon: -77.4714
      nws:
        gridId: LWX
        gridX: 80
        gridY: 76
  providers:
    openweather: {}
    nws:
      user_agent: empire-weather-test
""",
        encoding="utf-8",
    )
    fake_store = FakeObjectStore()
    monkeypatch.setenv("EMPIRE_WEATHER_OPENWEATHER_API_KEY", "test-key")
    monkeypatch.setenv("EMPIRE_STORAGE_KEY_WEATHER", "/weather/")
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
    assert fake_store.calls[0]["domain"] == "weather"
    assert fake_store.calls[0]["logical_name"] == "weather-config"
    assert fake_store.calls[0]["storage_root"] == "config"
    assert fake_store.calls[0]["object_key"] == "weather"
    assert fake_store.calls[0]["filename"] == "config.yml"
    assert fake_store.calls[0]["content_type"] == "text/yaml"
    assert fake_store.calls[0]["object_kind"] == "weather_config"
    assert fake_store.calls[0]["overwrite"] is True
    assert "stored_object_id:" in capsys.readouterr().out


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None


class FakeObject:
    object_id = uuid4()
    logical_name = "weather-config"
    object_key = "weather"
    filename = "config.yml"


class FakeObjectStore:
    def __init__(self):
        self.calls = []

    def put_bytes(self, **kwargs):
        self.calls.append(kwargs)
        return FakeObject()
