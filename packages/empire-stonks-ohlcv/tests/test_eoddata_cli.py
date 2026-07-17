from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

import empire_stonks_ohlcv.scripts.eoddata_daily as cli
from empire_stonks_ohlcv import (
    EODDataCredentials,
    EODDataDailyRunResult,
    OHLCVConfig,
    PersistenceCounts,
)


EFFECTIVE_DATE = date(2026, 7, 15)
SECRET = "eoddata-cli-secret"
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
WRAPPER = REPOSITORY_ROOT / "bin" / "stonks-ohlcv-eoddata-daily"


class FakeConnection:
    def __init__(self) -> None:
        self.entered = False
        self.exited = False

    def __enter__(self) -> FakeConnection:
        self.entered = True
        return self

    def __exit__(self, *_args: object) -> None:
        self.exited = True


def _result() -> EODDataDailyRunResult:
    return EODDataDailyRunResult(
        run_id=UUID("10000000-0000-4000-8000-000000000001"),
        status="succeeded",
        effective_date=EFFECTIVE_DATE,
        report_object_id=UUID("20000000-0000-4000-8000-000000000002"),
        report_outcome="WARN",
        listing_counts=PersistenceCounts(inserted=3),
        bar_counts=PersistenceCounts(inserted=2, unchanged=1),
        skipped_inactive_bars=1,
        failure_count=0,
        warning_count=2,
    )


def _install_runtime(
    monkeypatch: pytest.MonkeyPatch,
    connection: FakeConnection,
) -> None:
    config = OHLCVConfig(
        eoddata_credentials=EODDataCredentials(api_key=SECRET),
    )
    monkeypatch.setattr(
        cli,
        "EmpireDatabase",
        SimpleNamespace(connect_from_env=lambda: connection),
    )
    monkeypatch.setattr(
        cli,
        "RunService",
        SimpleNamespace(from_connection=lambda value: ("runs", value)),
    )
    monkeypatch.setattr(
        cli,
        "ObjectStore",
        SimpleNamespace(from_connection=lambda value: ("objects", value)),
    )
    monkeypatch.setattr(
        cli,
        "OHLCVConfig",
        SimpleNamespace(from_env=lambda: config),
    )


def test_cli_delegates_explicit_date_and_prints_compact_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    connection = FakeConnection()
    _install_runtime(monkeypatch, connection)
    calls: list[dict[str, object]] = []

    def run(**values: object) -> EODDataDailyRunResult:
        calls.append(values)
        return _result()

    monkeypatch.setattr(cli, "run_eoddata_daily", run)

    exit_code = cli.main(["--effective-date", "2026-07-15"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert json.loads(captured.out) == _result().to_dict()
    assert len(calls) == 1
    assert calls[0]["effective_date"] == EFFECTIVE_DATE
    assert calls[0]["run_type"] == "cli"
    assert calls[0]["runner"] == "bin/stonks-ohlcv-eoddata-daily"
    assert calls[0]["runner_ref"] == {
        "command": "bin/stonks-ohlcv-eoddata-daily"
    }
    assert calls[0]["connection"] is connection
    assert calls[0]["run_service"] == ("runs", connection)
    assert calls[0]["object_store"] == ("objects", connection)
    assert connection.entered is True
    assert connection.exited is True
    assert SECRET not in captured.out


@pytest.mark.parametrize(
    "arguments",
    (
        [],
        ["--effective-date", "2026-7-15"],
        ["--effective-date", "not-a-date"],
    ),
)
def test_cli_rejects_missing_or_invalid_effective_date_before_runtime(
    monkeypatch: pytest.MonkeyPatch,
    arguments: list[str],
) -> None:
    monkeypatch.setattr(
        cli,
        "EmpireDatabase",
        SimpleNamespace(
            connect_from_env=lambda: pytest.fail("database must not open")
        ),
    )

    with pytest.raises(SystemExit) as error:
        cli.main(arguments)

    assert error.value.code == 2


def test_cli_failure_is_nonzero_and_does_not_print_exception_details(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    connection = FakeConnection()
    _install_runtime(monkeypatch, connection)
    monkeypatch.setattr(
        cli,
        "run_eoddata_daily",
        lambda **_values: (_ for _ in ()).throw(RuntimeError(SECRET)),
    )

    exit_code = cli.main(["--effective-date", "2026-07-15"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == "ERROR: EODData daily run failed.\n"
    assert SECRET not in captured.err
    assert connection.exited is True


def test_bin_wrapper_is_executable_valid_and_uses_env_load() -> None:
    contents = WRAPPER.read_text(encoding="utf-8")

    assert WRAPPER.stat().st_mode & 0o111
    assert (
        'source "${REPO_ROOT}/bin/env-load" "${ENV_FILE}" >/dev/null'
        in contents
    )
    assert "empire_stonks_ohlcv.scripts.eoddata_daily" in contents
    assert "run_eoddata_daily" not in contents
    subprocess.run(["bash", "-n", str(WRAPPER)], check=True)
    help_result = subprocess.run(
        [str(WRAPPER), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert help_result.returncode == 0
    assert "--effective-date YYYY-MM-DD" in help_result.stdout
    assert SECRET not in help_result.stdout


def test_poetry_exposes_operator_command() -> None:
    pyproject = (
        REPOSITORY_ROOT / "packages" / "empire-stonks-ohlcv" / "pyproject.toml"
    ).read_text(encoding="utf-8")

    assert (
        "stonks-ohlcv-eoddata-daily = "
        '"empire_stonks_ohlcv.scripts.eoddata_daily:main"'
    ) in pyproject
