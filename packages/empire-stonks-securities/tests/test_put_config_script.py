from __future__ import annotations

from uuid import uuid4

from empire_stonks_securities.scripts import put_config as script
from empire_stonks_securities.scripts.put_config import (
    DEFAULT_LOCAL_CONFIG_FILE,
    parse_args,
)


def test_put_config_defaults_to_seed_config_file():
    args = parse_args([])

    assert args.config_file is None


def test_put_config_default_path_constant_points_to_seed_config():
    assert DEFAULT_LOCAL_CONFIG_FILE == "object-store/config/stonks-securities/config.yml"


def test_main_publishes_config(monkeypatch, tmp_path, capsys):
    config_file = tmp_path / "config.yml"
    config_file.write_text(
        """
stonks_securities:
  name: stonks_securities
  version: 1
  sec:
    user_agent: "Empire Stonks Securities/0.1 (test@example.com)"
    base_url: https://www.sec.gov
    archives_url: https://www.sec.gov/Archives
  providers:
    sec_company_tickers:
      provider_code: SEC_COMPANY_TICKERS
      enabled: true
      url: https://www.sec.gov/files/company_tickers.json
      expected_format: json
      description: SEC company-to-ticker mapping with CIK identifiers.
  processing:
    historical_backfill:
      start_date: "1995-01-01"
      end_date: "current"
""",
        encoding="utf-8",
    )
    fake_store = FakeObjectStore()
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
    assert fake_store.calls[0]["domain"] == "stonks"
    assert fake_store.calls[0]["logical_name"] == "stonks-securities-config"
    assert fake_store.calls[0]["storage_root"] == "config"
    assert fake_store.calls[0]["object_key"] == "stonks-securities"
    assert fake_store.calls[0]["filename"] == "config.yml"
    assert fake_store.calls[0]["content_type"] == "text/yaml"
    assert fake_store.calls[0]["object_kind"] == "stonks_securities_config"
    assert fake_store.calls[0]["overwrite"] is True
    assert "stored_object_id:" in capsys.readouterr().out


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None


class FakeObject:
    object_id = uuid4()
    logical_name = "stonks-securities-config"
    object_key = "stonks-securities"
    filename = "config.yml"


class FakeObjectStore:
    def __init__(self):
        self.calls = []

    def put_bytes(self, **kwargs):
        self.calls.append(kwargs)
        return FakeObject()
