from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

import empire_stonks_ohlcv.scripts.stooq_backfill as cli
from empire_stonks_ohlcv import EODDataCredentials, OHLCVConfig


SECRET = "stooq-cli-secret"
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
WRAPPER = REPOSITORY_ROOT / "bin" / "stonks-ohlcv-stooq-backfill"


class FakeConnection:
    def __init__(self) -> None:
        self.entered = False
        self.exited = False

    def __enter__(self) -> FakeConnection:
        self.entered = True
        return self

    def __exit__(self, *_args: object) -> None:
        self.exited = True


def _archive(tmp_path: Path) -> Path:
    path = tmp_path / "d_us_txt.zip"
    path.write_bytes(b"operator archive")
    return path


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


def test_cli_delegates_explicit_scope_and_prints_safe_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    archive = _archive(tmp_path)
    connection = FakeConnection()
    _install_runtime(monkeypatch, connection)
    calls: list[dict[str, object]] = []
    expected = {"status": "succeeded", "report_outcome": "PASS"}

    def run(**values: object) -> SimpleNamespace:
        calls.append(values)
        progress_sink = values["progress_sink"]
        assert callable(progress_sink)
        progress_sink(
            {
                "stage": "persistence",
                "files_completed": 2,
                "current_member": "data/daily/us/nasdaq/1/aacb.us.txt",
            }
        )
        return SimpleNamespace(to_dict=lambda: expected)

    monkeypatch.setattr(cli, "run_stooq_history_backfill", run)

    exit_code = cli.main(
        [
            "--input-path",
            str(archive),
            "--effective-date",
            "2026-07-18",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2026-07-17",
            "--market",
            "nyse",
            "--market",
            "nasdaq",
            "--ticker",
            "ZZZ.US",
            "--ticker",
            "AACB.US",
            "--chunk-size",
            "1234",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out) == expected
    progress = json.loads(captured.err)
    assert progress["event"] == "stooq_history_progress"
    assert progress["stage"] == "persistence"
    assert len(calls) == 1
    assert calls[0]["input_path"] == archive.resolve()
    assert calls[0]["scope"].effective_date == date(2026, 7, 18)
    assert calls[0]["scope"].start_date == date(2024, 1, 1)
    assert calls[0]["scope"].end_date == date(2026, 7, 17)
    assert calls[0]["scope"].markets == ("nasdaq", "nyse")
    assert calls[0]["scope"].tickers == ("AACB.US", "ZZZ.US")
    assert calls[0]["chunk_size"] == 1234
    assert calls[0]["run_type"] == "cli"
    assert calls[0]["runner"] == "bin/stonks-ohlcv-stooq-backfill"
    assert calls[0]["runner_ref"] == {
        "command": "bin/stonks-ohlcv-stooq-backfill"
    }
    assert calls[0]["connection"] is connection
    assert calls[0]["run_service"] == ("runs", connection)
    assert calls[0]["object_store"] == ("objects", connection)
    assert connection.entered is True
    assert connection.exited is True
    assert SECRET not in captured.out
    assert SECRET not in captured.err
    assert str(archive.resolve()) not in captured.out
    assert str(archive.resolve()) not in captured.err


def test_cli_defaults_to_all_markets_and_bounded_chunk_size(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    archive = _archive(tmp_path)
    connection = FakeConnection()
    _install_runtime(monkeypatch, connection)
    calls: list[dict[str, object]] = []

    def run(**values: object) -> SimpleNamespace:
        calls.append(values)
        return SimpleNamespace(to_dict=lambda: {"status": "succeeded"})

    monkeypatch.setattr(cli, "run_stooq_history_backfill", run)

    assert (
        cli.main(
            [
                "--input-path",
                str(archive),
                "--effective-date",
                "2026-07-18",
            ]
        )
        == 0
    )

    captured = capsys.readouterr()
    assert captured.err == ""
    assert calls[0]["scope"].markets == ("nasdaq", "nyse", "nysemkt")
    assert calls[0]["scope"].tickers == ()
    assert calls[0]["chunk_size"] == cli.DEFAULT_CHUNK_SIZE


@pytest.mark.parametrize(
    "arguments",
    (
        (),
        ("--effective-date", "2026-07-18"),
        ("--effective-date", "2026-7-18", "--input-path", "missing"),
        ("--effective-date", "2026-07-18", "--chunk-size", "0"),
        ("--effective-date", "2026-07-18", "--chunk-size", "100001"),
    ),
)
def test_cli_rejects_invalid_basic_arguments_before_runtime(
    monkeypatch: pytest.MonkeyPatch,
    arguments: tuple[str, ...],
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


@pytest.mark.parametrize(
    "scope_arguments",
    (
        ("--start-date", "2026-07-18", "--end-date", "2026-07-17"),
        ("--market", "nasdaq", "--market", "nasdaq"),
        ("--ticker", "AACB.US", "--ticker", "AACB.US"),
        ("--ticker", "aacb.us"),
        ("--market", "amex"),
    ),
)
def test_cli_rejects_invalid_scope_before_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scope_arguments: tuple[str, ...],
) -> None:
    archive = _archive(tmp_path)
    monkeypatch.setattr(
        cli,
        "EmpireDatabase",
        SimpleNamespace(
            connect_from_env=lambda: pytest.fail("database must not open")
        ),
    )
    arguments = (
        "--input-path",
        str(archive),
        "--effective-date",
        "2026-07-18",
        *scope_arguments,
    )

    with pytest.raises(SystemExit) as error:
        cli.main(arguments)

    assert error.value.code == 2


def test_cli_rejects_wrong_archive_name_before_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    archive = tmp_path / "renamed.zip"
    archive.write_bytes(b"archive")
    monkeypatch.setattr(
        cli,
        "EmpireDatabase",
        SimpleNamespace(
            connect_from_env=lambda: pytest.fail("database must not open")
        ),
    )

    with pytest.raises(SystemExit) as error:
        cli.main(
            [
                "--input-path",
                str(archive),
                "--effective-date",
                "2026-07-18",
            ]
        )

    assert error.value.code == 2


def test_cli_failure_is_nonzero_and_hides_exception_details(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    archive = _archive(tmp_path)
    connection = FakeConnection()
    _install_runtime(monkeypatch, connection)
    monkeypatch.setattr(
        cli,
        "run_stooq_history_backfill",
        lambda **_values: (_ for _ in ()).throw(RuntimeError(SECRET)),
    )

    exit_code = cli.main(
        [
            "--input-path",
            str(archive),
            "--effective-date",
            "2026-07-18",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == "ERROR: Stooq historical backfill failed.\n"
    assert SECRET not in captured.err
    assert connection.exited is True


def test_bin_wrapper_is_executable_valid_and_uses_env_load() -> None:
    contents = WRAPPER.read_text(encoding="utf-8")

    assert WRAPPER.stat().st_mode & 0o111
    assert (
        'source "${REPO_ROOT}/bin/env-load" "${ENV_FILE}" >/dev/null'
        in contents
    )
    assert "empire_stonks_ohlcv.scripts.stooq_backfill" in contents
    assert "run_stooq_history_backfill" not in contents
    assert "curl" not in contents
    subprocess.run(["bash", "-n", str(WRAPPER)], check=True)
    help_result = subprocess.run(
        [str(WRAPPER), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert help_result.returncode == 0
    assert "--input-path PATH" in help_result.stdout
    assert "--effective-date YYYY-MM-DD" in help_result.stdout
    assert "--chunk-size ROWS" in help_result.stdout
    assert "does not download" in help_result.stdout
    assert SECRET not in help_result.stdout


def test_poetry_exposes_operator_command() -> None:
    pyproject = (
        REPOSITORY_ROOT / "packages" / "empire-stonks-ohlcv" / "pyproject.toml"
    ).read_text(encoding="utf-8")

    assert (
        "stonks-ohlcv-stooq-backfill = "
        '"empire_stonks_ohlcv.scripts.stooq_backfill:main"'
    ) in pyproject
