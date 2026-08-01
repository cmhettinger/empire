from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

import empire_stonks_ohlcv.scripts.yahoo_daily as cli
from empire_stonks_ohlcv import OHLCVConfig


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
WRAPPER = REPOSITORY_ROOT / "bin" / "stonks-ohlcv-yahoo-daily"


class ConnectionContext:
    def __enter__(self) -> object:
        return object()

    def __exit__(self, *_args: object) -> None:
        return None


def _runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli,
        "EmpireDatabase",
        SimpleNamespace(connect_from_env=lambda: ConnectionContext()),
    )
    monkeypatch.setattr(
        cli,
        "RunService",
        SimpleNamespace(from_connection=lambda _: object()),
    )
    monkeypatch.setattr(
        cli,
        "ObjectStore",
        SimpleNamespace(from_connection=lambda _: object()),
    )


def test_cli_builds_configured_default_scope_and_prints_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, object] = {}
    result = SimpleNamespace(to_dict=lambda: {"status": "succeeded"})
    monkeypatch.setattr(
        cli.OHLCVConfig,
        "from_env",
        lambda: OHLCVConfig(yahoo_daily_lookback_days=10),
    )
    _runtime(monkeypatch)

    def run(**values: object) -> object:
        captured.update(values)
        return result

    monkeypatch.setattr(cli, "run_yahoo_daily", run)

    assert cli.main(["--effective-date", "2026-07-30"]) == 0

    scope = captured["scope"]
    assert scope.effective_date == date(2026, 7, 30)  # type: ignore[union-attr]
    assert scope.start_date == date(2026, 7, 21)  # type: ignore[union-attr]
    assert scope.end_date == date(2026, 7, 30)  # type: ignore[union-attr]
    assert scope.tickers == ()  # type: ignore[union-attr]
    assert captured["runner"] == cli.RUNNER_NAME
    assert json.loads(capsys.readouterr().out) == result.to_dict()


def test_cli_forwards_explicit_scope_tickers_and_progress(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(cli.OHLCVConfig, "from_env", OHLCVConfig)
    _runtime(monkeypatch)

    def run(**values: object) -> object:
        captured.update(values)
        progress = values["progress_sink"]
        progress(  # type: ignore[operator]
            {"phase": "reconciliation", "ticker": "SPX"}
        )
        return SimpleNamespace(to_dict=lambda: {"status": "succeeded"})

    monkeypatch.setattr(cli, "run_yahoo_daily", run)

    assert (
        cli.main(
            [
                "--effective-date",
                "2026-07-30",
                "--start-date",
                "2026-07-01",
                "--end-date",
                "2026-07-29",
                "--ticker",
                "SPX",
                "--ticker",
                "DOW",
            ]
        )
        == 0
    )

    scope = captured["scope"]
    assert scope.tickers == ("DOW", "SPX")  # type: ignore[union-attr]
    assert scope.end_date == date(2026, 7, 29)  # type: ignore[union-attr]
    progress = json.loads(capsys.readouterr().err)
    assert progress["event"] == "yahoo_daily_progress"
    assert progress["phase"] == "reconciliation"


def test_cli_failure_is_secret_safe(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli.OHLCVConfig, "from_env", OHLCVConfig)
    _runtime(monkeypatch)
    monkeypatch.setattr(
        cli,
        "run_yahoo_daily",
        lambda **_: (_ for _ in ()).throw(
            RuntimeError("provider-secret-body")
        ),
    )

    assert cli.main(["--effective-date", "2026-07-30"]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err.strip() == cli.SAFE_CLI_FAILURE
    assert "secret" not in output.err


def test_invalid_scope_stops_before_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli.OHLCVConfig, "from_env", OHLCVConfig)
    monkeypatch.setattr(
        cli,
        "EmpireDatabase",
        SimpleNamespace(
            connect_from_env=lambda: pytest.fail("database must not open")
        ),
    )

    with pytest.raises(SystemExit) as raised:
        cli.main(
            [
                "--effective-date",
                "2026-07-30",
                "--start-date",
                "2026-07-31",
            ]
        )
    assert raised.value.code == 2


def test_bin_wrapper_is_executable_valid_and_uses_env_load() -> None:
    contents = WRAPPER.read_text(encoding="utf-8")

    assert WRAPPER.stat().st_mode & 0o111
    assert (
        'source "${REPO_ROOT}/bin/env-load" "${ENV_FILE}" >/dev/null'
        in contents
    )
    assert "empire_stonks_ohlcv.scripts.yahoo_daily" in contents
    assert "empire-reports/src" in contents
    assert "curl" not in contents
    subprocess.run(["bash", "-n", str(WRAPPER)], check=True)
    help_result = subprocess.run(
        [str(WRAPPER), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert help_result.returncode == 0
    assert "--effective-date YYYY-MM-DD" in help_result.stdout
    assert "--end-date YYYY-MM-DD" in help_result.stdout
    assert "recent-session reconciliation" in help_result.stdout


def test_poetry_exposes_operator_command() -> None:
    pyproject = (
        REPOSITORY_ROOT
        / "packages"
        / "empire-stonks-ohlcv"
        / "pyproject.toml"
    ).read_text(encoding="utf-8")

    assert (
        "stonks-ohlcv-yahoo-daily = "
        '"empire_stonks_ohlcv.scripts.yahoo_daily:main"'
    ) in pyproject
