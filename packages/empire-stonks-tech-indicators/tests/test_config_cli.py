from __future__ import annotations

import json

import pytest

from empire_stonks_tech_indicators import TechIndicatorsConfig
from empire_stonks_tech_indicators.config_readiness import (
    TechIndicatorsConfigReadinessError,
)
from empire_stonks_tech_indicators.scripts import config as cli


class FakeCursor:
    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None


class FakeConnection:
    read_only = False

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return FakeCursor()


class FakeResult:
    def to_safe_dict(self) -> dict[str, object]:
        return {"ready": True, "token": "safe"}


def test_config_cli_prints_one_compact_json_result(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    connection = FakeConnection()
    monkeypatch.setattr(
        cli,
        "check_tech_indicators_config_readiness",
        lambda *, cursor, config: FakeResult(),
    )

    exit_code = cli.main([], connect_from_env=lambda: connection)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out) == {"ready": True, "token": "safe"}
    assert captured.out.count("\n") == 1
    assert captured.err == ""
    assert connection.read_only is True


def test_config_cli_reports_only_safe_readiness_stage(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail(**_: object) -> object:
        raise TechIndicatorsConfigReadinessError("benchmark")

    monkeypatch.setattr(cli, "check_tech_indicators_config_readiness", fail)

    exit_code = cli.main([], connect_from_env=FakeConnection)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert json.loads(captured.out) == {
        "ready": False,
        "failure_stage": "benchmark",
    }
    assert captured.err == cli.SAFE_CONFIG_FAILURE + "\n"


def test_config_cli_hides_config_and_database_exception_text(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        TechIndicatorsConfig,
        "from_env",
        classmethod(
            lambda cls: (_ for _ in ()).throw(
                RuntimeError("password=must-not-leak")
            )
        ),
    )

    exit_code = cli.main(
        [],
        connect_from_env=lambda: pytest.fail("database must not open"),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == cli.SAFE_CONFIG_FAILURE + "\n"
    assert "must-not-leak" not in captured.err


def test_config_cli_help_does_not_connect(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.main(
            ["--help"],
            connect_from_env=lambda: pytest.fail("database must not open"),
        )

    assert raised.value.code == 0
    assert "stonks-tech-indicators-config" in capsys.readouterr().out
