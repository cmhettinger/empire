from __future__ import annotations

import logging
from collections.abc import Mapping
from contextlib import ExitStack
from datetime import date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from airflow.sdk import dag, get_current_context, task
from airflow.sdk.exceptions import AirflowSkipException
from empire_core import EmpireDatabase, ObjectStore, RunService
from empire_stonks_tech_indicators import (
    TechIndicatorsConfig,
    TechIndicatorsDailyScope,
    preflight_tech_indicators_daily,
    run_tech_indicators_daily,
)


DAG_ID = "stonks_tech_indicators_daily_refresh"
MARKET_TIMEZONE = ZoneInfo("America/New_York")

_SCOPE_CONF_KEYS = frozenset(
    {
        "effective_date",
        "provider_codes",
        "markets",
        "provider_listing_ids",
        "calculation_version",
        "dry_run",
        "force",
    }
)
_COORDINATION_CONF_KEYS = frozenset(
    {
        "coordination_schema_version",
        "source_provider_code",
        "source_code",
        "source_job_name",
        "source_core_run_id",
        "source_dag_id",
        "source_dag_run_id",
    }
)

log = logging.getLogger(__name__)


def _dag_run_conf(context: Mapping[str, object]) -> Mapping[str, object]:
    dag_run = context.get("dag_run")
    conf = getattr(dag_run, "conf", None)
    if not isinstance(conf, Mapping):
        raise ValueError("Airflow dag_run.conf must be a JSON object.")
    unexpected = set(conf) - _SCOPE_CONF_KEYS - _COORDINATION_CONF_KEYS
    if unexpected:
        raise ValueError(
            "Airflow dag_run.conf contains unsupported keys: "
            + ", ".join(sorted(str(key) for key in unexpected))
            + "."
        )
    return conf


def _scope_from_context(
    context: Mapping[str, object],
    config: TechIndicatorsConfig,
) -> TechIndicatorsDailyScope:
    """Build the package-owned exact-date scope from manual overrides."""

    conf = _dag_run_conf(context)
    return TechIndicatorsDailyScope(
        effective_date=_required_date(conf, "effective_date"),
        provider_codes=_optional_text_values(
            conf,
            "provider_codes",
            uppercase=True,
        ),
        markets=_optional_text_values(conf, "markets"),
        provider_listing_ids=_optional_uuids(conf, "provider_listing_ids"),
        calculation_version=_optional_text(
            conf,
            "calculation_version",
        )
        or config.calculation_version,
        dry_run=_optional_bool(conf, "dry_run"),
        force=_optional_bool(conf, "force"),
    )


def _required_date(conf: Mapping[str, object], key: str) -> date:
    value = conf.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} is required and must use YYYY-MM-DD.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{key} must use YYYY-MM-DD.") from None
    if parsed.isoformat() != value:
        raise ValueError(f"{key} must use YYYY-MM-DD.")
    return parsed


def _optional_text_values(
    conf: Mapping[str, object],
    key: str,
    *,
    uppercase: bool = False,
) -> tuple[str, ...]:
    value = conf.get(key)
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a JSON array of strings.")
    result: list[str] = []
    for item in value:
        if (
            not isinstance(item, str)
            or not item
            or item != item.strip()
            or any(ord(character) < 32 for character in item)
            or (uppercase and item != item.upper())
        ):
            qualifier = " uppercase" if uppercase else ""
            raise ValueError(
                f"{key} must contain exact trimmed{qualifier} strings."
            )
        result.append(item)
    return tuple(result)


def _optional_uuids(
    conf: Mapping[str, object],
    key: str,
) -> tuple[UUID, ...]:
    value = conf.get(key)
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a JSON array of UUID strings.")
    result: list[UUID] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{key} must contain canonical UUID strings.")
        try:
            parsed = UUID(item)
        except ValueError:
            raise ValueError(
                f"{key} must contain canonical UUID strings."
            ) from None
        if str(parsed) != item:
            raise ValueError(f"{key} must contain canonical UUID strings.")
        result.append(parsed)
    return tuple(result)


def _optional_text(
    conf: Mapping[str, object],
    key: str,
) -> str | None:
    value = conf.get(key)
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError(f"{key} must be exact trimmed text.")
    return value


def _optional_bool(conf: Mapping[str, object], key: str) -> bool:
    value = conf.get(key, False)
    if type(value) is not bool:
        raise ValueError(f"{key} must be a JSON boolean.")
    return value


@dag(
    dag_id=DAG_ID,
    start_date=datetime(2026, 8, 29, tzinfo=MARKET_TIMEZONE),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["stonks", "tech-indicators", "manual"],
)
def stonks_tech_indicators_daily_refresh():
    @task(task_id="check_source_readiness")
    def check_readiness() -> dict[str, object]:
        context = get_current_context()
        config = TechIndicatorsConfig.from_env()
        scope = _scope_from_context(context, config)

        with EmpireDatabase.connect_from_env() as connection:
            decision = preflight_tech_indicators_daily(
                connection=connection,
                config=config,
                scope=scope,
            )

        payload = decision.to_dict()
        if not decision.ready:
            log.info(
                "Technical-indicator source readiness not satisfied for %s; "
                "selected listings=%s, reasons=%s",
                payload["effective_date"],
                payload["selected_listing_count"],
                ",".join(payload["reasons"]),
            )
            raise AirflowSkipException(
                "Technical-indicator source readiness is not satisfied."
            )
        log.info(
            "Technical-indicator source readiness satisfied for %s; "
            "selected listings=%s, EODData run=%s, Yahoo run=%s",
            payload["effective_date"],
            payload["selected_listing_count"],
            payload["eoddata_source_run_id"],
            payload["yahoo_source_run_id"],
        )
        return payload

    @task(task_id="run_tech_indicators_daily")
    def run_daily(_readiness: dict[str, object]) -> dict[str, object]:
        context = get_current_context()
        config = TechIndicatorsConfig.from_env()
        scope = _scope_from_context(context, config)

        with ExitStack() as stack:
            work_connection = stack.enter_context(
                EmpireDatabase.connect_from_env()
            )
            core_connection = stack.enter_context(
                EmpireDatabase.connect_from_env()
            )
            object_connection = stack.enter_context(
                EmpireDatabase.connect_from_env()
            )
            result = run_tech_indicators_daily(
                run_service=RunService.from_connection(core_connection),
                connection=work_connection,
                lock_connection_factory=EmpireDatabase.connect_from_env,
                object_store=ObjectStore.from_connection(object_connection),
                config=config,
                scope=scope,
                run_type="airflow",
                runner="airflow",
            )

        payload = result.to_dict()
        log.info(
            "Completed technical-indicator daily task with status=%s, "
            "effective_date=%s, run_id=%s, publication_id=%s, "
            "JSON report=%s, PDF report=%s, outcome=%s",
            payload["status"],
            payload["effective_date"],
            payload["run_id"],
            payload["publication_id"],
            payload["json_report_object_id"],
            payload["pdf_report_object_id"],
            payload["outcome"],
        )
        return payload

    run_daily(check_readiness())


stonks_tech_indicators_daily_refresh_dag = (
    stonks_tech_indicators_daily_refresh()
)
