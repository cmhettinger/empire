from __future__ import annotations

import json

from empire_stonks_ohlcv.scripts.config import main


def test_config_script_prints_secret_safe_json(monkeypatch, capsys) -> None:
    secret = "do-not-print-this-api-key"
    monkeypatch.setenv("EMPIRE_STORAGE_KEY_STONKS_OHLCV", "test/ohlcv")
    monkeypatch.setenv("EMPIRE_STONKS_OHLCV_RAW_RETENTION_DAYS", "5")
    monkeypatch.setenv("EMPIRE_STONKS_OHLCV_HTTP_TIMEOUT_SECONDS", "12.5")
    monkeypatch.setenv("EMPIRE_STONKS_OHLCV_MAX_RETRIES", "2")
    monkeypatch.setenv("EMPIRE_STONKS_OHLCV_EODDATA_API_KEY", secret)
    monkeypatch.setenv(
        "EMPIRE_STONKS_OHLCV_EODDATA_REQUEST_DELAY_SECONDS",
        "3.5",
    )

    assert main([]) == 0

    output = capsys.readouterr().out
    assert secret not in output
    assert json.loads(output) == {
        "eoddata_base_url": "https://api.eoddata.com",
        "eoddata_configured": True,
        "eoddata_exchanges": "NYSE,NASDAQ,AMEX",
        "eoddata_request_delay_seconds": 3.5,
        "http_timeout_seconds": 12.5,
        "max_retries": 2,
        "raw_retention_days": 5,
        "storage_key": "test/ohlcv",
        "yahoo_backfill_chunk_days": 3650,
        "yahoo_backfill_start_date": "1965-01-01",
        "yahoo_daily_lookback_days": 30,
        "yahoo_daily_request_max_days": 30,
        "yahoo_base_url": "https://query2.finance.yahoo.com",
        "yahoo_failure_cooldown_max_seconds": 18.0,
        "yahoo_failure_cooldown_min_seconds": 8.0,
        "yahoo_reconciliation_sessions": 7,
        "yahoo_request_delay_seconds": 25.0,
        "yahoo_request_jitter_max_seconds": 10.0,
        "yahoo_request_jitter_min_seconds": 5.0,
    }
