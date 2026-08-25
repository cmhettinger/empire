from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import UUID

import pytest

from empire_stonks_tech_indicators import BenchmarkConfig, TechIndicatorsConfig
from empire_stonks_tech_indicators.scripts import inspect as cli


LISTING_ID = UUID("00000000-0000-4000-8000-000000000001")


class Connection:
    def __init__(self) -> None:
        self.entered = False
        self.exited = False

    def __enter__(self) -> Connection:
        self.entered = True
        return self

    def __exit__(self, *args: object) -> None:
        self.exited = True


def test_inspect_cli_wires_exact_bounded_scope_and_compact_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    connection = Connection()
    captured: dict[str, object] = {}
    result = SimpleNamespace(
        to_dict=lambda: {
            "schema_version": 1,
            "disclosure": "no recommendations",
        }
    )
    monkeypatch.setattr(
        cli.TechIndicatorsConfig,
        "from_env",
        lambda: TechIndicatorsConfig(
            source_read_page_size=1000,
            diagnostic_sample_limit=7,
        ),
    )

    def inspector(**kwargs: object) -> object:
        captured.update(kwargs)
        return result

    exit_code = cli.main(
        [
            "--effective-date",
            "2026-08-24",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-08-24",
            "--provider-listing-id",
            str(LISTING_ID),
            "--include-inactive",
            "--calculation-version",
            "TECH_INDICATORS_V1",
            "--sample-limit",
            "3",
        ],
        connect_from_env=lambda: connection,
        inspector=inspector,  # type: ignore[arg-type]
    )

    output = capsys.readouterr()
    assert exit_code == 0
    assert output.err == ""
    assert output.out == (
        '{"disclosure":"no recommendations","schema_version":1}\n'
    )
    assert json.loads(output.out) == result.to_dict()
    assert connection.entered and connection.exited
    assert captured["connection"] is connection
    assert captured["effective_date"].isoformat() == "2026-08-24"
    assert isinstance(captured["benchmark_config"], BenchmarkConfig)
    assert captured["calculation_version"] == "TECH_INDICATORS_V1"
    assert captured["sample_limit"] == 3
    assert captured["page_size"] == 1000
    scope = captured["scope"]
    assert scope.provider_listing_ids == (LISTING_ID,)
    assert scope.include_inactive is True


def test_inspect_cli_uses_configured_sample_default(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        cli.TechIndicatorsConfig,
        "from_env",
        lambda: TechIndicatorsConfig(diagnostic_sample_limit=7),
    )

    def inspector(**kwargs: object) -> object:
        captured.update(kwargs)
        return SimpleNamespace(to_dict=lambda: {"schema_version": 1})

    assert (
        cli.main(
            ["--effective-date", "2026-08-24"],
            connect_from_env=Connection,
            inspector=inspector,  # type: ignore[arg-type]
        )
        == 0
    )
    assert captured["sample_limit"] == 7
    capsys.readouterr()


@pytest.mark.parametrize(
    "arguments",
    (
        ("--effective-date", "2026-8-24"),
        ("--effective-date", "2026-08-24", "--start-date", "2026-01-01"),
        ("--effective-date", "2026-08-24", "--end-date", "2026-08-24"),
        (
            "--effective-date",
            "2026-08-24",
            "--start-date",
            "2026-08-25",
            "--end-date",
            "2026-08-26",
        ),
        ("--effective-date", "2026-08-24", "--provider-code", "eoddata"),
        ("--effective-date", "2026-08-24", "--provider-listing-id", "bad"),
        (
            "--effective-date",
            "2026-08-24",
            "--provider-code",
            "EODDATA",
            "--provider-listing-id",
            str(LISTING_ID),
        ),
        ("--effective-date", "2026-08-24", "--include-inactive"),
        (
            "--effective-date",
            "2026-08-24",
            "--calculation-version",
            "TECH_INDICATORS_V2",
        ),
        ("--effective-date", "2026-08-24", "--sample-limit", "0"),
        ("--effective-date", "2026-08-24", "--sample-limit", "101"),
    ),
)
def test_invalid_inspection_scope_stops_before_database(
    arguments: tuple[str, ...],
) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.main(
            arguments,
            connect_from_env=lambda: pytest.fail("database must not open"),
        )
    assert raised.value.code == 2


def test_inspect_cli_hides_runtime_exception_text(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    connection = Connection()
    monkeypatch.setattr(
        cli.TechIndicatorsConfig,
        "from_env",
        lambda: TechIndicatorsConfig(),
    )

    def fail(**_: object) -> object:
        raise RuntimeError("password=must-not-leak")

    exit_code = cli.main(
        ["--effective-date", "2026-08-24"],
        connect_from_env=lambda: connection,
        inspector=fail,  # type: ignore[arg-type]
    )

    output = capsys.readouterr()
    assert exit_code == 1
    assert output.out == ""
    assert output.err == cli.SAFE_INSPECTION_FAILURE + "\n"
    assert "must-not-leak" not in output.err
    assert connection.exited is True


def test_inspect_cli_hides_missing_config_and_does_not_connect(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli.TechIndicatorsConfig,
        "from_env",
        lambda: (_ for _ in ()).throw(
            RuntimeError("password=must-not-leak")
        ),
    )

    exit_code = cli.main(
        ["--effective-date", "2026-08-24"],
        connect_from_env=lambda: pytest.fail("database must not open"),
    )

    output = capsys.readouterr()
    assert exit_code == 1
    assert output.out == ""
    assert output.err == cli.SAFE_INSPECTION_FAILURE + "\n"
    assert "must-not-leak" not in output.err


def test_inspect_cli_help_does_not_connect(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.main(
            ["--help"],
            connect_from_env=lambda: pytest.fail("database must not open"),
        )
    assert raised.value.code == 0
    assert "stonks-tech-indicators-inspect" in capsys.readouterr().out
