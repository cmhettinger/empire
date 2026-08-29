from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from uuid import UUID

import pytest

import empire_stonks_tech_indicators as public_api
from empire_stonks_tech_indicators import (
    SourceReadinessDecision,
    TechIndicatorsConfig,
    TechIndicatorsDailyScope,
    preflight_tech_indicators_daily,
)
from empire_stonks_tech_indicators import daily_preflight as preflight_module


EFFECTIVE_DATE = date(2026, 8, 28)
BENCHMARK_ID = UUID("10000000-0000-4000-8000-000000000001")
EODDATA_RUN_ID = UUID("20000000-0000-4000-8000-000000000002")
YAHOO_RUN_ID = UUID("30000000-0000-4000-8000-000000000003")


class Cursor:
    def __init__(self) -> None:
        self.executions: list[tuple[object, ...]] = []
        self.closed = False

    def execute(self, *values: object) -> None:
        self.executions.append(values)

    def close(self) -> None:
        self.closed = True


class Connection:
    def __init__(self) -> None:
        self.cursor_value = Cursor()
        self.rollback_count = 0

    def cursor(self) -> Cursor:
        return self.cursor_value

    def rollback(self) -> None:
        self.rollback_count += 1


def _decision(*, reasons: tuple[str, ...] = ()) -> SourceReadinessDecision:
    return SourceReadinessDecision(
        effective_date=EFFECTIVE_DATE,
        selected_listing_count=1,
        eoddata_listing_count=1,
        stooq_listing_count=0,
        yahoo_listing_count=0,
        effective_date_bar_count=1,
        supported_subject_bar_count=1,
        benchmark_identity_required=True,
        spx_bar_required=True,
        benchmark_provider_listing_id=BENCHMARK_ID,
        benchmark_bar_present=True,
        eoddata_evidence_required=True,
        yahoo_evidence_required=True,
        eoddata_source_run_id=EODDATA_RUN_ID,
        yahoo_source_run_id=(
            None
            if "YAHOO_SOURCE_EVIDENCE_MISSING" in reasons
            else YAHOO_RUN_ID
        ),
        reasons=reasons,
    )


def test_preflight_uses_read_only_snapshot_and_returns_bounded_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = Connection()
    config = TechIndicatorsConfig()
    scope = TechIndicatorsDailyScope(effective_date=EFFECTIVE_DATE)
    decision = _decision()
    calls: list[dict[str, object]] = []

    def resolve(**values: object) -> object:
        calls.append(values)
        return SimpleNamespace(readiness=decision)

    monkeypatch.setattr(
        preflight_module,
        "resolve_tech_indicators_daily_scope",
        resolve,
    )

    result = preflight_tech_indicators_daily(
        connection=connection,
        config=config,
        scope=scope,
    )

    assert result is decision
    assert calls == [
        {
            "cursor": connection.cursor_value,
            "scope": scope,
            "benchmark_config": config.benchmark,
        }
    ]
    assert connection.cursor_value.executions == [
        (
            "BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY",
        )
    ]
    assert connection.rollback_count == 1
    assert connection.cursor_value.closed is True
    assert public_api.preflight_tech_indicators_daily is (
        preflight_tech_indicators_daily
    )
    assert preflight_module.__all__ == ["preflight_tech_indicators_daily"]


def test_preflight_rolls_back_and_closes_after_resolution_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = Connection()

    def fail(**_values: object) -> object:
        raise RuntimeError("read failed")

    monkeypatch.setattr(
        preflight_module,
        "resolve_tech_indicators_daily_scope",
        fail,
    )

    with pytest.raises(RuntimeError, match="read failed"):
        preflight_tech_indicators_daily(
            connection=connection,
            config=TechIndicatorsConfig(),
            scope=TechIndicatorsDailyScope(effective_date=EFFECTIVE_DATE),
        )

    assert connection.rollback_count == 1
    assert connection.cursor_value.closed is True


@pytest.mark.parametrize(
    "values",
    [
        {"connection": object()},
        {"config": object()},
        {"scope": object()},
    ],
)
def test_preflight_rejects_invalid_runtime_inputs(
    values: dict[str, object],
) -> None:
    arguments: dict[str, object] = {
        "connection": Connection(),
        "config": TechIndicatorsConfig(),
        "scope": TechIndicatorsDailyScope(effective_date=EFFECTIVE_DATE),
    }
    arguments.update(values)

    with pytest.raises(TypeError):
        preflight_tech_indicators_daily(**arguments)  # type: ignore[arg-type]
