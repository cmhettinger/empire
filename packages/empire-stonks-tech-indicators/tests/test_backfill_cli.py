from __future__ import annotations

import json
from datetime import date
from uuid import UUID

import pytest

from empire_core import ObjectStore, RunService
from empire_stonks_tech_indicators import ReportOutcome, TechIndicatorsConfig
from empire_stonks_tech_indicators.backfill_runner import (
    TechIndicatorsBackfillRunResult,
)
from empire_stonks_tech_indicators.backfill_scope import (
    TechIndicatorsBackfillCursor,
)
from empire_stonks_tech_indicators.scripts import backfill as cli
from empire_stonks_tech_indicators.writer_lock import (
    TECH_INDICATORS_LOCK_CONTENDED_MESSAGE,
    TECH_INDICATORS_TEMPORARY_FAILURE_EXIT_CODE,
)


EFFECTIVE_DATE = date(2026, 8, 24)
START_DATE = date(2025, 1, 1)
END_DATE = date(2026, 8, 23)
LISTING_ID = UUID("00000000-0000-4000-8000-000000000001")
RUN_ID = UUID("10000000-0000-4000-8000-000000000001")
PUBLICATION_ID = UUID("20000000-0000-4000-8000-000000000001")
JSON_ID = UUID("30000000-0000-4000-8000-000000000001")
PDF_ID = UUID("40000000-0000-4000-8000-000000000001")
RESUME_CURSOR = TechIndicatorsBackfillCursor(
    provider_listing_id=LISTING_ID,
    trading_date=date(2026, 1, 2),
    batch_number=3,
)


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


def _partial_result() -> TechIndicatorsBackfillRunResult:
    return TechIndicatorsBackfillRunResult(
        status="partial",
        effective_date=EFFECTIVE_DATE,
        run_id=RUN_ID,
        publication_id=PUBLICATION_ID,
        json_report_object_id=JSON_ID,
        pdf_report_object_id=PDF_ID,
        outcome=ReportOutcome.PARTIAL,
        resume_cursor=RESUME_CURSOR,
    )


def _success_result() -> TechIndicatorsBackfillRunResult:
    return TechIndicatorsBackfillRunResult(
        status="succeeded",
        effective_date=EFFECTIVE_DATE,
        run_id=RUN_ID,
        publication_id=PUBLICATION_ID,
        json_report_object_id=JSON_ID,
        pdf_report_object_id=PDF_ID,
        outcome=ReportOutcome.PASS,
    )


def test_backfill_cli_wires_exact_resume_rebuild_and_progress(
    capsys: pytest.CaptureFixture[str],
) -> None:
    factory = ConnectionFactory()
    captured: dict[str, object] = {}

    def runner(**kwargs: object) -> TechIndicatorsBackfillRunResult:
        captured.update(kwargs)
        progress_sink = kwargs["progress_sink"]
        progress_sink(  # type: ignore[operator]
            {
                "stage": "batch",
                "completed_batch_count": 3,
                "resume_cursor": RESUME_CURSOR.to_dict(),
            }
        )
        return _partial_result()

    exit_code = cli.main(
        [
            "--effective-date",
            "2026-08-24",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2026-08-23",
            "--provider-listing-id",
            str(LISTING_ID),
            "--include-inactive",
            "--batch-size",
            "1000",
            "--batch-limit",
            "2",
            "--resume-provider-listing-id",
            str(LISTING_ID),
            "--resume-trading-date",
            "2026-01-02",
            "--resume-batch-number",
            "3",
            "--calculation-version",
            "TECH_INDICATORS_V1",
            "--rebuild",
            "--confirm-rebuild",
        ],
        connect_from_env=factory,
        runner=runner,
    )

    output = capsys.readouterr()
    assert exit_code == 0
    assert output.out == cli._compact_json(_partial_result().to_dict()) + "\n"
    progress = json.loads(output.err)
    assert progress["event"] == "tech_indicators_backfill_progress"
    assert progress["completed_batch_count"] == 3
    assert len(factory.connections) == 3
    assert all(item.entered and item.exited for item in factory.connections)
    assert isinstance(captured["run_service"], RunService)
    assert captured["connection"] is factory.connections[0]
    assert isinstance(captured["object_store"], ObjectStore)
    assert captured["lock_connection_factory"] is factory
    assert isinstance(captured["config"], TechIndicatorsConfig)
    assert captured["run_type"] == "cli"
    assert captured["runner"] == cli.RUNNER_NAME
    assert captured["batch_limit"] == 2
    scope = captured["scope"]
    assert scope.provider_listing_ids == (LISTING_ID,)
    assert scope.include_inactive is True
    assert scope.batch_size == 1000
    assert scope.resume_cursor == RESUME_CURSOR
    assert scope.rebuild is True
    assert scope.confirm_broad_scope is False


def test_backfill_cli_wires_confirmed_dimension_scope(
    capsys: pytest.CaptureFixture[str],
) -> None:
    factory = ConnectionFactory()
    captured: dict[str, object] = {}

    def runner(**kwargs: object) -> TechIndicatorsBackfillRunResult:
        captured.update(kwargs)
        return _success_result()

    assert (
        cli.main(
            [
                "--effective-date",
                "2026-08-24",
                "--start-date",
                "2025-01-01",
                "--end-date",
                "2026-08-23",
                "--provider-code",
                "EODDATA",
                "--market",
                "NASDAQ",
                "--confirm-broad-scope",
                "--dry-run",
            ],
            connect_from_env=factory,
            runner=runner,
        )
        == 0
    )
    scope = captured["scope"]
    assert scope.provider_codes == ("EODDATA",)
    assert scope.markets == ("NASDAQ",)
    assert scope.confirm_broad_scope is True
    assert scope.dry_run is True
    capsys.readouterr()


def test_backfill_cli_maps_contention_to_stderr_and_exit_75(
    capsys: pytest.CaptureFixture[str],
) -> None:
    factory = ConnectionFactory()
    result = TechIndicatorsBackfillRunResult(
        status="contended",
        effective_date=EFFECTIVE_DATE,
        message=TECH_INDICATORS_LOCK_CONTENDED_MESSAGE,
    )

    exit_code = cli.main(
        [
            "--effective-date",
            "2026-08-24",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2026-08-23",
            "--provider-listing-id",
            str(LISTING_ID),
        ],
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
        ("--provider-code", "eoddata", "--confirm-broad-scope"),
        ("--provider-listing-id", "NOT-A-UUID"),
        ("--batch-size", "999"),
        ("--batch-limit", "0"),
        ("--calculation-version", "TECH_INDICATORS_V2"),
        ("--provider-code", "EODDATA", "--provider-listing-id", str(LISTING_ID)),
        ("--provider-code", "EODDATA"),
        ("--include-inactive",),
        ("--rebuild",),
        ("--confirm-rebuild",),
        ("--resume-provider-listing-id", str(LISTING_ID)),
        ("--resume-batch-number", "1"),
        ("--resume-trading-date", "2026-01-02"),
        ("--dry-run", "--batch-limit", "1"),
        (
            "--dry-run",
            "--resume-provider-listing-id",
            str(LISTING_ID),
            "--resume-batch-number",
            "1",
        ),
    ),
)
def test_invalid_scope_stops_before_database(
    arguments: tuple[str, ...],
) -> None:
    base = (
        "--effective-date",
        "2026-08-24",
        "--start-date",
        "2025-01-01",
        "--end-date",
        "2026-08-23",
    )
    with pytest.raises(SystemExit) as raised:
        cli.main(
            [*base, *arguments],
            connect_from_env=lambda: pytest.fail("database must not open"),
        )

    assert raised.value.code == 2


def test_invalid_date_order_stops_before_database() -> None:
    with pytest.raises(SystemExit) as raised:
        cli.main(
            [
                "--effective-date",
                "2026-08-24",
                "--start-date",
                "2026-08-24",
                "--end-date",
                "2025-01-01",
                "--provider-listing-id",
                str(LISTING_ID),
            ],
            connect_from_env=lambda: pytest.fail("database must not open"),
        )

    assert raised.value.code == 2


def test_backfill_cli_hides_runtime_exception_text(
    capsys: pytest.CaptureFixture[str],
) -> None:
    factory = ConnectionFactory()

    def fail(**_: object) -> TechIndicatorsBackfillRunResult:
        raise RuntimeError("password=must-not-leak")

    exit_code = cli.main(
        [
            "--effective-date",
            "2026-08-24",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2026-08-23",
            "--provider-listing-id",
            str(LISTING_ID),
        ],
        connect_from_env=factory,
        runner=fail,
    )

    output = capsys.readouterr()
    assert exit_code == 1
    assert output.out == ""
    assert output.err == cli.SAFE_BACKFILL_FAILURE + "\n"
    assert "must-not-leak" not in output.err
    assert all(item.exited for item in factory.connections)


def test_backfill_cli_hides_missing_config_and_does_not_connect(
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
        [
            "--effective-date",
            "2026-08-24",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2026-08-23",
            "--provider-listing-id",
            str(LISTING_ID),
        ],
        connect_from_env=lambda: pytest.fail("database must not open"),
    )

    output = capsys.readouterr()
    assert exit_code == 1
    assert output.out == ""
    assert output.err == cli.SAFE_BACKFILL_FAILURE + "\n"
    assert "must-not-leak" not in output.err


def test_backfill_cli_help_does_not_connect(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.main(
            ["--help"],
            connect_from_env=lambda: pytest.fail("database must not open"),
        )

    assert raised.value.code == 0
    assert "stonks-tech-indicators-backfill" in capsys.readouterr().out
