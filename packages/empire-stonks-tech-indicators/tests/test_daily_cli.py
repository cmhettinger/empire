from __future__ import annotations

import json
from datetime import date
from uuid import UUID

import pytest

from empire_core import ObjectStore, RunService
from empire_stonks_tech_indicators import ReportOutcome, TechIndicatorsConfig
from empire_stonks_tech_indicators.daily_runner import (
    TechIndicatorsDailyRunResult,
)
from empire_stonks_tech_indicators.scripts import daily as cli
from empire_stonks_tech_indicators.writer_lock import (
    TECH_INDICATORS_LOCK_CONTENDED_MESSAGE,
    TECH_INDICATORS_TEMPORARY_FAILURE_EXIT_CODE,
)


EFFECTIVE_DATE = date(2026, 8, 24)
LISTING_ID = UUID("00000000-0000-4000-8000-000000000001")
RUN_ID = UUID("10000000-0000-4000-8000-000000000001")
PUBLICATION_ID = UUID("20000000-0000-4000-8000-000000000001")
JSON_ID = UUID("30000000-0000-4000-8000-000000000001")
PDF_ID = UUID("40000000-0000-4000-8000-000000000001")


class FakeConnection:
    def __init__(self, number: int) -> None:
        self.number = number
        self.entered = False
        self.exited = False

    def __enter__(self) -> FakeConnection:
        self.entered = True
        return self

    def __exit__(self, *args: object) -> None:
        self.exited = True


class ConnectionFactory:
    def __init__(self) -> None:
        self.connections: list[FakeConnection] = []

    def __call__(self) -> FakeConnection:
        connection = FakeConnection(len(self.connections) + 1)
        self.connections.append(connection)
        return connection


def _success_result() -> TechIndicatorsDailyRunResult:
    return TechIndicatorsDailyRunResult(
        status="succeeded",
        effective_date=EFFECTIVE_DATE,
        run_id=RUN_ID,
        publication_id=PUBLICATION_ID,
        json_report_object_id=JSON_ID,
        pdf_report_object_id=PDF_ID,
        outcome=ReportOutcome.PASS,
    )


def test_daily_cli_wires_exact_scope_and_prints_compact_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    factory = ConnectionFactory()
    captured: dict[str, object] = {}

    def runner(**kwargs: object) -> TechIndicatorsDailyRunResult:
        captured.update(kwargs)
        return _success_result()

    exit_code = cli.main(
        [
            "--effective-date",
            "2026-08-24",
            "--provider-code",
            "STOOQ",
            "--provider-code",
            "EODDATA",
            "--market",
            "nyse",
            "--market",
            "NASDAQ",
            "--calculation-version",
            "TECH_INDICATORS_V1",
            "--dry-run",
            "--force",
        ],
        connect_from_env=factory,
        runner=runner,
    )

    output = capsys.readouterr()
    assert exit_code == 0
    assert output.err == ""
    assert output.out.count("\n") == 1
    assert json.loads(output.out) == _success_result().to_dict()
    assert len(factory.connections) == 3
    assert all(item.entered and item.exited for item in factory.connections)
    assert isinstance(captured["run_service"], RunService)
    assert captured["connection"] is factory.connections[0]
    assert isinstance(captured["object_store"], ObjectStore)
    assert captured["lock_connection_factory"] is factory
    assert captured["run_type"] == "cli"
    assert captured["runner"] == cli.RUNNER_NAME
    assert isinstance(captured["config"], TechIndicatorsConfig)
    scope = captured["scope"]
    assert scope.provider_codes == ("EODDATA", "STOOQ")
    assert scope.markets == ("NASDAQ", "nyse")
    assert scope.provider_listing_ids == ()
    assert scope.dry_run is True
    assert scope.force is True


def test_daily_cli_wires_exact_listing_scope(
    capsys: pytest.CaptureFixture[str],
) -> None:
    factory = ConnectionFactory()
    captured: dict[str, object] = {}

    def runner(**kwargs: object) -> TechIndicatorsDailyRunResult:
        captured.update(kwargs)
        return _success_result()

    assert (
        cli.main(
            [
                "--effective-date",
                "2026-08-24",
                "--provider-listing-id",
                str(LISTING_ID),
            ],
            connect_from_env=factory,
            runner=runner,
        )
        == 0
    )
    assert captured["scope"].provider_listing_ids == (LISTING_ID,)
    capsys.readouterr()


def test_daily_cli_maps_contention_to_stderr_and_exit_75(
    capsys: pytest.CaptureFixture[str],
) -> None:
    factory = ConnectionFactory()
    result = TechIndicatorsDailyRunResult(
        status="contended",
        effective_date=EFFECTIVE_DATE,
        message=TECH_INDICATORS_LOCK_CONTENDED_MESSAGE,
    )

    exit_code = cli.main(
        ["--effective-date", "2026-08-24"],
        connect_from_env=factory,
        runner=lambda **_: result,
    )

    output = capsys.readouterr()
    assert exit_code == TECH_INDICATORS_TEMPORARY_FAILURE_EXIT_CODE
    assert output.out == ""
    assert json.loads(output.err) == result.to_dict()


@pytest.mark.parametrize(
    "arguments",
    (
        ("--effective-date", "2026-8-24"),
        ("--effective-date", "2026-08-24", "--provider-code", "eoddata"),
        (
            "--effective-date",
            "2026-08-24",
            "--provider-listing-id",
            "NOT-A-UUID",
        ),
        (
            "--effective-date",
            "2026-08-24",
            "--calculation-version",
            "TECH_INDICATORS_V2",
        ),
        (
            "--effective-date",
            "2026-08-24",
            "--provider-code",
            "EODDATA",
            "--provider-listing-id",
            str(LISTING_ID),
        ),
    ),
)
def test_invalid_scope_stops_before_database(
    arguments: tuple[str, ...],
) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.main(
            arguments,
            connect_from_env=lambda: pytest.fail("database must not open"),
        )

    assert raised.value.code == 2


def test_daily_cli_hides_runtime_exception_text(
    capsys: pytest.CaptureFixture[str],
) -> None:
    factory = ConnectionFactory()

    def fail(**_: object) -> TechIndicatorsDailyRunResult:
        raise RuntimeError("password=must-not-leak")

    exit_code = cli.main(
        ["--effective-date", "2026-08-24"],
        connect_from_env=factory,
        runner=fail,
    )

    output = capsys.readouterr()
    assert exit_code == 1
    assert output.out == ""
    assert output.err == cli.SAFE_DAILY_FAILURE + "\n"
    assert "must-not-leak" not in output.err
    assert all(item.exited for item in factory.connections)


def test_daily_cli_help_does_not_connect(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.main(
            ["--help"],
            connect_from_env=lambda: pytest.fail("database must not open"),
        )

    assert raised.value.code == 0
    assert "stonks-tech-indicators-daily" in capsys.readouterr().out
