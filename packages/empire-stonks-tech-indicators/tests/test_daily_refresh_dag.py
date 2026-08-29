from __future__ import annotations

import importlib.util
import logging
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from uuid import UUID

import pytest


DAG_ID = "stonks_tech_indicators_daily_refresh"
LISTING_ID_A = UUID("10000000-0000-4000-8000-000000000001")
LISTING_ID_B = UUID("20000000-0000-4000-8000-000000000002")
LETTERED_LISTING_ID = UUID("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee")


def test_daily_refresh_dag_is_manual_one_task_and_thin(monkeypatch) -> None:
    module, _fake_sdk = _load_dag_module(monkeypatch)

    dag = module.stonks_tech_indicators_daily_refresh_dag

    assert dag.dag_id == DAG_ID
    assert dag.schedule is None
    assert dag.start_date == datetime(
        2026,
        8,
        29,
        tzinfo=module.MARKET_TIMEZONE,
    )
    assert dag.start_date.tzinfo.key == "America/New_York"
    assert dag.catchup is False
    assert dag.max_active_runs == 1
    assert dag.tags == ["stonks", "tech-indicators", "manual"]
    assert [item.task_id for item in dag.tasks] == [
        "check_source_readiness",
        "run_tech_indicators_daily"
    ]
    assert dag.tasks[0].call_args == ()
    assert dag.tasks[0].call_kwargs == {}
    assert dag.tasks[1].call_args == (dag.tasks[0],)
    assert dag.tasks[1].call_kwargs == {}

    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "run_tech_indicators_daily(" in source
    assert "from empire_stonks_tech_indicators." not in source
    assert "decide_source_readiness" not in source
    assert "assemble_feature_rows" not in source
    assert "calculate_" not in source
    assert "psycopg" not in source
    assert ".execute(" not in source
    assert "SELECT " not in source.upper()
    assert "INSERT " not in source.upper()
    assert "UPDATE " not in source.upper()
    assert "DELETE " not in source.upper()
    assert "os.environ" not in source
    assert "dotenv" not in source


def test_scope_requires_exact_effective_date(monkeypatch) -> None:
    module, _fake_sdk = _load_dag_module(monkeypatch)

    scope = module._scope_from_context(
        _context({"effective_date": "2026-08-28"}),
        module.TechIndicatorsConfig(),
    )

    assert scope == module.TechIndicatorsDailyScope(
        effective_date=date(2026, 8, 28),
    )


@pytest.mark.parametrize(
    ("conf", "message"),
    [
        ({}, "effective_date is required"),
        ({"effective_date": 20260828}, "effective_date is required"),
        ({"effective_date": "08/28/2026"}, "effective_date must use"),
        ({"effective_date": "2026-8-28"}, "effective_date must use"),
    ],
)
def test_scope_rejects_missing_or_invalid_effective_date(
    monkeypatch,
    conf,
    message,
) -> None:
    module, _fake_sdk = _load_dag_module(monkeypatch)

    with pytest.raises(ValueError, match=message):
        module._scope_from_context(
            _context(conf),
            module.TechIndicatorsConfig(),
        )


@pytest.mark.parametrize("conf", [None, [], "not-an-object"])
def test_scope_requires_json_object_configuration(
    monkeypatch,
    conf,
) -> None:
    module, _fake_sdk = _load_dag_module(monkeypatch)

    with pytest.raises(ValueError, match="must be a JSON object"):
        module._scope_from_context(
            {"dag_run": SimpleNamespace(conf=conf)},
            module.TechIndicatorsConfig(),
        )


def test_scope_normalizes_dimension_overrides(monkeypatch) -> None:
    module, _fake_sdk = _load_dag_module(monkeypatch)

    scope = module._scope_from_context(
        _context(
            {
                "effective_date": "2026-08-28",
                "provider_codes": ["STOOQ", "EODDATA", "EODDATA"],
                "markets": ["nyse", "NASDAQ", "NASDAQ"],
                "calculation_version": "TECH_INDICATORS_V1",
                "dry_run": True,
                "force": True,
            }
        ),
        module.TechIndicatorsConfig(),
    )

    assert scope.to_dict() == {
        "effective_date": "2026-08-28",
        "provider_codes": ["EODDATA", "STOOQ"],
        "markets": ["NASDAQ", "nyse"],
        "provider_listing_ids": [],
        "calculation_version": "TECH_INDICATORS_V1",
        "dry_run": True,
        "force": True,
    }


def test_scope_normalizes_exact_listing_overrides(monkeypatch) -> None:
    module, _fake_sdk = _load_dag_module(monkeypatch)

    scope = module._scope_from_context(
        _context(
            {
                "effective_date": "2026-08-28",
                "provider_listing_ids": [
                    str(LISTING_ID_B),
                    str(LISTING_ID_A),
                    str(LISTING_ID_A),
                ],
            }
        ),
        module.TechIndicatorsConfig(),
    )

    assert scope.provider_listing_ids == (LISTING_ID_A, LISTING_ID_B)
    assert scope.provider_codes == ()
    assert scope.markets == ()


def test_scope_accepts_reserved_source_coordination_provenance(
    monkeypatch,
) -> None:
    module, _fake_sdk = _load_dag_module(monkeypatch)

    scope = module._scope_from_context(
        _context(
            {
                "coordination_schema_version": 1,
                "effective_date": "2026-08-28",
                "source_provider_code": "YAHOO",
                "source_code": "yahoo_daily",
                "source_job_name": "stonks_ohlcv_yahoo_daily",
                "source_core_run_id": str(LISTING_ID_A),
                "source_dag_id": "stonks_ohlcv_yahoo_daily_scrape",
                "source_dag_run_id": "manual__2026-08-29T12:00:00+00:00",
            }
        ),
        module.TechIndicatorsConfig(),
    )

    assert scope == module.TechIndicatorsDailyScope(
        effective_date=date(2026, 8, 28),
    )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"provider_codes": "EODDATA"}, "JSON array"),
        ({"provider_codes": ["eoddata"]}, "trimmed uppercase"),
        ({"markets": [" NASDAQ"]}, "exact trimmed"),
        ({"provider_listing_ids": "uuid"}, "JSON array"),
        ({"provider_listing_ids": ["not-a-uuid"]}, "canonical UUID"),
        (
            {"provider_listing_ids": [str(LETTERED_LISTING_ID).upper()]},
            "canonical UUID",
        ),
        ({"calculation_version": "TECH_INDICATORS_V2"}, "must be"),
        ({"dry_run": "true"}, "JSON boolean"),
        ({"force": 1}, "JSON boolean"),
        ({"unexpected": True}, "unsupported keys"),
        (
            {
                "provider_codes": ["EODDATA"],
                "provider_listing_ids": [str(LISTING_ID_A)],
            },
            "cannot be combined",
        ),
    ],
)
def test_scope_rejects_invalid_or_ambiguous_overrides(
    monkeypatch,
    changes,
    message,
) -> None:
    module, _fake_sdk = _load_dag_module(monkeypatch)
    conf = {"effective_date": "2026-08-28", **changes}

    with pytest.raises((TypeError, ValueError), match=message):
        module._scope_from_context(
            _context(conf),
            module.TechIndicatorsConfig(),
        )


def test_preflight_task_returns_ready_decision_without_workflow_services(
    monkeypatch,
    caplog,
) -> None:
    module, fake_sdk = _load_dag_module(monkeypatch)
    fake_sdk.context = _context({"effective_date": "2026-08-28"})
    config = module.TechIndicatorsConfig()
    connection = object()
    calls: list[dict[str, object]] = []
    payload = {
        "effective_date": "2026-08-28",
        "ready": True,
        "selected_listing_count": 84,
        "eoddata_source_run_id": str(LISTING_ID_A),
        "yahoo_source_run_id": str(LISTING_ID_B),
        "reasons": [],
    }
    decision = SimpleNamespace(ready=True, to_dict=lambda: payload)

    monkeypatch.setattr(
        module.EmpireDatabase,
        "connect_from_env",
        lambda: FakeConnectionContext(connection, [], []),
    )
    monkeypatch.setattr(module.TechIndicatorsConfig, "from_env", lambda: config)
    monkeypatch.setattr(
        module,
        "preflight_tech_indicators_daily",
        lambda **values: calls.append(values) or decision,
    )
    monkeypatch.setattr(
        module.RunService,
        "from_connection",
        lambda _value: pytest.fail("preflight created a Core service"),
    )
    monkeypatch.setattr(
        module.ObjectStore,
        "from_connection",
        lambda _value: pytest.fail("preflight created an object service"),
    )

    with caplog.at_level(logging.INFO, logger=module.__name__):
        result = _preflight_task(module).python_callable()

    assert result == payload
    assert calls == [
        {
            "connection": connection,
            "config": config,
            "scope": module.TechIndicatorsDailyScope(
                effective_date=date(2026, 8, 28)
            ),
        }
    ]
    assert "source readiness satisfied" in caplog.text
    assert str(LISTING_ID_A) in caplog.text
    assert str(LISTING_ID_B) in caplog.text


def test_preflight_task_skips_not_ready_without_workflow_state(
    monkeypatch,
    caplog,
) -> None:
    module, fake_sdk = _load_dag_module(monkeypatch)
    fake_sdk.context = _context({"effective_date": "2026-08-28"})
    payload = {
        "effective_date": "2026-08-28",
        "ready": False,
        "selected_listing_count": 84,
        "eoddata_source_run_id": str(LISTING_ID_A),
        "yahoo_source_run_id": None,
        "reasons": ["YAHOO_SOURCE_EVIDENCE_MISSING"],
    }
    decision = SimpleNamespace(ready=False, to_dict=lambda: payload)

    monkeypatch.setattr(
        module.EmpireDatabase,
        "connect_from_env",
        lambda: FakeConnectionContext(object(), [], []),
    )
    monkeypatch.setattr(
        module.TechIndicatorsConfig,
        "from_env",
        module.TechIndicatorsConfig,
    )
    monkeypatch.setattr(
        module,
        "preflight_tech_indicators_daily",
        lambda **_values: decision,
    )
    monkeypatch.setattr(
        module,
        "run_tech_indicators_daily",
        lambda **_values: pytest.fail("not-ready preflight invoked runner"),
    )

    with caplog.at_level(logging.INFO, logger=module.__name__):
        with pytest.raises(
            module.AirflowSkipException,
            match="readiness is not satisfied",
        ):
            _preflight_task(module).python_callable()

    assert "YAHOO_SOURCE_EVIDENCE_MISSING" in caplog.text


def test_task_delegates_with_separate_services_and_logs_compact_result(
    monkeypatch,
    caplog,
) -> None:
    module, fake_sdk = _load_dag_module(monkeypatch)
    fake_sdk.context = _context(
        {
            "effective_date": "2026-08-28",
            "provider_codes": ["EODDATA"],
            "markets": ["NASDAQ"],
            "dry_run": True,
        }
    )
    config = module.TechIndicatorsConfig()
    work_connection = object()
    core_connection = object()
    object_connection = object()
    connections = [work_connection, core_connection, object_connection]
    entered: list[object] = []
    exited: list[object] = []
    connect_calls: list[None] = []
    run_service = object()
    object_store = object()
    runner_calls: list[dict[str, object]] = []
    expected_payload = {
        "status": "succeeded",
        "effective_date": "2026-08-28",
        "run_id": "30000000-0000-4000-8000-000000000003",
        "publication_id": "40000000-0000-4000-8000-000000000004",
        "json_report_object_id": "50000000-0000-4000-8000-000000000005",
        "pdf_report_object_id": "60000000-0000-4000-8000-000000000006",
        "outcome": "PASS",
        "message": None,
    }

    def connect_from_env():
        connection = connections[len(connect_calls)]
        connect_calls.append(None)
        return FakeConnectionContext(connection, entered, exited)

    def run(**values):
        runner_calls.append(values)
        return SimpleNamespace(to_dict=lambda: expected_payload)

    monkeypatch.setattr(
        module.EmpireDatabase,
        "connect_from_env",
        connect_from_env,
    )
    monkeypatch.setattr(module.TechIndicatorsConfig, "from_env", lambda: config)
    monkeypatch.setattr(
        module.RunService,
        "from_connection",
        lambda value: run_service if value is core_connection else None,
    )
    monkeypatch.setattr(
        module.ObjectStore,
        "from_connection",
        lambda value: object_store if value is object_connection else None,
    )
    monkeypatch.setattr(module, "run_tech_indicators_daily", run)

    with caplog.at_level(logging.INFO, logger=module.__name__):
        payload = _run_task(module).python_callable({"ready": True})

    assert payload == expected_payload
    assert len(connect_calls) == 3
    assert entered == connections
    assert exited == list(reversed(connections))
    assert runner_calls == [
        {
            "run_service": run_service,
            "connection": work_connection,
            "lock_connection_factory": connect_from_env,
            "object_store": object_store,
            "config": config,
            "scope": module.TechIndicatorsDailyScope(
                effective_date=date(2026, 8, 28),
                provider_codes=("EODDATA",),
                markets=("NASDAQ",),
                dry_run=True,
            ),
            "run_type": "airflow",
            "runner": "airflow",
        }
    ]
    assert caplog.messages == [
        "Completed technical-indicator daily task with status=succeeded, "
        "effective_date=2026-08-28, "
        "run_id=30000000-0000-4000-8000-000000000003, "
        "publication_id=40000000-0000-4000-8000-000000000004, "
        "JSON report=50000000-0000-4000-8000-000000000005, "
        "PDF report=60000000-0000-4000-8000-000000000006, outcome=PASS"
    ]
    assert "EODDATA" not in caplog.text
    assert "NASDAQ" not in caplog.text


def test_task_propagates_runner_failure_and_closes_connections(
    monkeypatch,
) -> None:
    module, fake_sdk = _load_dag_module(monkeypatch)
    fake_sdk.context = _context({"effective_date": "2026-08-28"})
    connections = [object(), object(), object()]
    exited: list[object] = []

    def connect_from_env():
        connection = connections.pop(0)
        return FakeConnectionContext(connection, [], exited)

    monkeypatch.setattr(
        module.EmpireDatabase,
        "connect_from_env",
        connect_from_env,
    )
    monkeypatch.setattr(
        module.TechIndicatorsConfig,
        "from_env",
        module.TechIndicatorsConfig,
    )
    monkeypatch.setattr(
        module.RunService,
        "from_connection",
        lambda _value: object(),
    )
    monkeypatch.setattr(
        module.ObjectStore,
        "from_connection",
        lambda _value: object(),
    )
    monkeypatch.setattr(
        module,
        "run_tech_indicators_daily",
        lambda **_values: (_ for _ in ()).throw(
            RuntimeError("runner failed")
        ),
    )

    with pytest.raises(RuntimeError, match="runner failed"):
        _run_task(module).python_callable({"ready": True})

    assert len(exited) == 3


def _context(conf):
    return {
        "dag_run": SimpleNamespace(
            conf=conf,
            run_id="manual__2026-08-29T12:00:00+00:00",
        )
    }


def _run_task(module):
    return module.stonks_tech_indicators_daily_refresh_dag.task_by_id[
        "run_tech_indicators_daily"
    ]


def _preflight_task(module):
    return module.stonks_tech_indicators_daily_refresh_dag.task_by_id[
        "check_source_readiness"
    ]


def _load_dag_module(monkeypatch):
    fake_sdk = FakeAirflowSdk()
    airflow_module = ModuleType("airflow")
    airflow_sdk_module = ModuleType("airflow.sdk")
    airflow_sdk_exceptions_module = ModuleType("airflow.sdk.exceptions")
    airflow_sdk_exceptions_module.AirflowSkipException = AirflowSkipException
    airflow_sdk_module.dag = fake_sdk.dag
    airflow_sdk_module.task = fake_sdk.task
    airflow_sdk_module.get_current_context = fake_sdk.get_current_context
    monkeypatch.setitem(sys.modules, "airflow", airflow_module)
    monkeypatch.setitem(
        sys.modules,
        "airflow.sdk.exceptions",
        airflow_sdk_exceptions_module,
    )
    monkeypatch.setitem(sys.modules, "airflow.sdk", airflow_sdk_module)

    repo_root = Path(__file__).resolve().parents[3]
    dag_path = (
        repo_root
        / "dags"
        / "stonks"
        / "stonks_tech_indicators_daily_refresh.py"
    )
    module_name = "test_stonks_tech_indicators_daily_refresh_dag"
    spec = importlib.util.spec_from_file_location(module_name, dag_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module, fake_sdk


class FakeAirflowSdk:
    def __init__(self):
        self.active_dag: FakeDag | None = None
        self.context: dict[str, object] | None = None

    def dag(self, **dag_kwargs):
        def decorator(factory):
            def wrapper():
                dag = FakeDag(**dag_kwargs)
                previous_dag = self.active_dag
                self.active_dag = dag
                try:
                    factory()
                finally:
                    self.active_dag = previous_dag
                return dag

            return wrapper

        return decorator

    def task(self, *, task_id):
        def decorator(python_callable):
            def wrapper(*args, **kwargs):
                assert self.active_dag is not None
                task_call = FakeTaskCall(
                    task_id=task_id,
                    python_callable=python_callable,
                    call_args=args,
                    call_kwargs=kwargs,
                )
                self.active_dag.tasks.append(task_call)
                return task_call

            return wrapper

        return decorator

    def get_current_context(self):
        assert self.context is not None
        return self.context


@dataclass
class FakeDag:
    dag_id: str
    start_date: datetime
    schedule: object
    catchup: bool
    max_active_runs: int
    tags: list[str]
    tasks: list[FakeTaskCall] = field(default_factory=list)

    @property
    def task_by_id(self):
        return {item.task_id: item for item in self.tasks}


@dataclass
class FakeTaskCall:
    task_id: str
    python_callable: object
    call_args: tuple[object, ...]
    call_kwargs: dict[str, object]


class AirflowSkipException(Exception):
    pass


class FakeConnectionContext:
    def __init__(
        self,
        connection: object,
        entered: list[object],
        exited: list[object],
    ) -> None:
        self.connection = connection
        self.entered = entered
        self.exited = exited

    def __enter__(self):
        self.entered.append(self.connection)
        return self.connection

    def __exit__(self, *_args):
        self.exited.append(self.connection)
        return None
