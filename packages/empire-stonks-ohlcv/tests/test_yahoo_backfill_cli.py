from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

import empire_stonks_ohlcv.scripts.yahoo_backfill as cli
from empire_stonks_ohlcv import OHLCVConfig


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
WRAPPER = REPOSITORY_ROOT / "bin" / "stonks-ohlcv-yahoo-backfill"


class ConnectionContext:
    def __enter__(self) -> object:
        return object()

    def __exit__(self, *_args: object) -> None:
        return None


def test_cli_builds_default_scope_and_prints_compact_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, object] = {}
    result = SimpleNamespace(
        to_dict=lambda: {
            "status": "succeeded",
            "report_outcome": "PASS",
        }
    )
    monkeypatch.setattr(
        cli.OHLCVConfig,
        "from_env",
        lambda: OHLCVConfig(
            yahoo_backfill_start_date="1970-01-01",
        ),
    )
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

    def run(**values: object) -> object:
        captured.update(values)
        return result

    monkeypatch.setattr(cli, "run_yahoo_backfill", run)

    exit_code = cli.main(
        [
            "--effective-date",
            "2026-07-30",
        ]
    )

    assert exit_code == 0
    scope = captured["scope"]
    assert scope.effective_date == date(2026, 7, 30)  # type: ignore[union-attr]
    assert scope.start_date == date(1970, 1, 1)  # type: ignore[union-attr]
    assert scope.end_date_exclusive == date(  # type: ignore[union-attr]
        2026,
        7,
        31,
    )
    assert scope.tickers == ()  # type: ignore[union-attr]
    assert captured["runner"] == cli.RUNNER_NAME
    assert json.loads(capsys.readouterr().out) == result.to_dict()


def test_cli_forwards_explicit_range_tickers_resume_and_progress(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        cli.OHLCVConfig,
        "from_env",
        lambda: OHLCVConfig(),
    )
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

    def run(**values: object) -> object:
        captured.update(values)
        progress = values["progress_sink"]
        progress({"stage": "acquisition", "ticker": "SPX"})  # type: ignore[operator]
        return SimpleNamespace(to_dict=lambda: {"status": "succeeded"})

    monkeypatch.setattr(cli, "run_yahoo_backfill", run)

    assert (
        cli.main(
            [
                "--effective-date",
                "2026-07-30",
                "--start-date",
                "2026-01-01",
                "--end-date-exclusive",
                "2026-07-01",
                "--ticker",
                "SPX",
                "--ticker",
                "DOW",
                "--resume-from",
                "SPX",
            ]
        )
        == 0
    )

    scope = captured["scope"]
    assert scope.tickers == ("DOW", "SPX")  # type: ignore[union-attr]
    assert scope.resume_from_ticker == "SPX"  # type: ignore[union-attr]
    stderr = capsys.readouterr().err
    progress = json.loads(stderr)
    assert progress["event"] == "yahoo_backfill_progress"
    assert progress["ticker"] == "SPX"


def test_cli_failure_is_secret_safe(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli.OHLCVConfig,
        "from_env",
        lambda: OHLCVConfig(),
    )
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
    monkeypatch.setattr(
        cli,
        "run_yahoo_backfill",
        lambda **_: (_ for _ in ()).throw(
            RuntimeError("provider-secret-body")
        ),
    )

    assert cli.main(["--effective-date", "2026-07-30"]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err.strip() == cli.SAFE_CLI_FAILURE
    assert "secret" not in output.err


def test_config_failure_is_nonzero_and_secret_safe(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli.OHLCVConfig,
        "from_env",
        lambda: (_ for _ in ()).throw(
            RuntimeError("configuration-secret")
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
    monkeypatch.setattr(
        cli.OHLCVConfig,
        "from_env",
        lambda: OHLCVConfig(),
    )
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
    assert "empire_stonks_ohlcv.scripts.yahoo_backfill" in contents
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
    assert "--end-date-exclusive YYYY-MM-DD" in help_result.stdout
    assert "--resume-from EMPIRE_TICKER" in help_result.stdout
    assert "idempotent" in help_result.stdout


def test_poetry_exposes_operator_command() -> None:
    pyproject = (
        REPOSITORY_ROOT
        / "packages"
        / "empire-stonks-ohlcv"
        / "pyproject.toml"
    ).read_text(encoding="utf-8")

    assert (
        "stonks-ohlcv-yahoo-backfill = "
        '"empire_stonks_ohlcv.scripts.yahoo_backfill:main"'
    ) in pyproject
