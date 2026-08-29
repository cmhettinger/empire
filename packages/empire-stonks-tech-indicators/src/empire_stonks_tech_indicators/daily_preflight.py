"""Read-only daily source-readiness preflight for runtime coordinators."""

from __future__ import annotations

from typing import Any

from empire_stonks_tech_indicators.config import TechIndicatorsConfig
from empire_stonks_tech_indicators.daily_scope import (
    TechIndicatorsDailyScope,
    resolve_tech_indicators_daily_scope,
)
from empire_stonks_tech_indicators.readiness import SourceReadinessDecision


def preflight_tech_indicators_daily(
    *,
    connection: Any,
    config: TechIndicatorsConfig,
    scope: TechIndicatorsDailyScope,
) -> SourceReadinessDecision:
    """Return exact-date readiness without locks or durable workflow state."""

    if not hasattr(connection, "cursor") or not callable(connection.cursor):
        raise TypeError("connection must provide cursor().")
    if not hasattr(connection, "rollback") or not callable(
        connection.rollback
    ):
        raise TypeError("connection must provide rollback().")
    if not isinstance(config, TechIndicatorsConfig):
        raise TypeError("config must be a TechIndicatorsConfig.")
    if not isinstance(scope, TechIndicatorsDailyScope):
        raise TypeError("scope must be a TechIndicatorsDailyScope.")

    cursor = connection.cursor()
    try:
        cursor.execute(
            "BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
        )
        resolved = resolve_tech_indicators_daily_scope(
            cursor=cursor,
            scope=scope,
            benchmark_config=config.benchmark,
        )
        return resolved.readiness
    finally:
        try:
            connection.rollback()
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()


__all__ = ["preflight_tech_indicators_daily"]
