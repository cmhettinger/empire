from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


DAG_ID = "stonks_ohlcv_eoddata_daily_scrape"


def test_eoddata_daily_dag_is_manual_until_deployment_profiles_exist(
    monkeypatch,
):
    module, _fake_sdk = _load_dag_module(monkeypatch)

    dag = module.stonks_ohlcv_eoddata_daily_scrape_dag

    assert dag.dag_id == DAG_ID
    assert dag.schedule is None
    assert dag.start_date.tzinfo.key == "America/New_York"
    assert dag.catchup is False
    assert dag.max_active_runs == 1
    assert dag.tags == ["stonks", "ohlcv", "eoddata", "manual"]
    assert [item.task_id for item in dag.tasks] == [
        "run_eoddata_daily",
        "prepare_tech_indicators_dispatch",
        "trigger_tech_indicators_refresh",
    ]
    assert dag.tasks[1].call_args == (dag.tasks[0],)
    assert dag.tasks[2].operator_kwargs == {
        "task_id": "trigger_tech_indicators_refresh",
        "trigger_dag_id": "stonks_tech_indicators_daily_refresh",
        "trigger_run_id": FakeXComArg(
            "prepare_tech_indicators_dispatch",
            "trigger_run_id",
        ),
        "conf": FakeXComArg("prepare_tech_indicators_dispatch", "conf"),
        "reset_dag_run": False,
        "wait_for_completion": False,
        "skip_when_already_exists": True,
    }

    source = Path(module.__file__).read_text(encoding="utf-8")
    manual_note = source.index("Local development remains manual")
    dag_instance = source.rindex("stonks_ohlcv_eoddata_daily_scrape()")
    assert manual_note > dag_instance
    assert "schedule=None" in source
    assert "20:15 and 23:15 ET each weekday" in source
    assert "P13.4-P13.5" in source
    assert "deployment-aware" in source
    assert "America/New_York" in source
    assert "package planner" in source
    assert "EMPIRE_STONKS_OHLCV_EODDATA_API_KEY" not in source
    assert "os.environ" not in source


def test_effective_date_uses_airflow_interval_new_york_date(monkeypatch):
    module, _fake_sdk = _load_dag_module(monkeypatch)
    context = {
        "dag_run": SimpleNamespace(conf={}),
        "data_interval_end": datetime(2026, 7, 18, 0, tzinfo=UTC),
    }

    assert module._effective_date_from_context(context) == date(2026, 7, 17)


def test_effective_date_accepts_manual_override(monkeypatch):
    module, _fake_sdk = _load_dag_module(monkeypatch)
    context = {
        "dag_run": SimpleNamespace(conf={"effective_date": "2026-07-15"}),
        "data_interval_end": datetime(2026, 7, 18, 0, tzinfo=UTC),
    }

    assert module._effective_date_from_context(context) == date(2026, 7, 15)


@pytest.mark.parametrize(
    ("interval_end", "message"),
    [
        (None, "Airflow data_interval_end is required"),
        (
            datetime(2026, 7, 17, 20),
            "Airflow data_interval_end must be timezone-aware",
        ),
    ],
)
def test_effective_date_requires_aware_interval_end(
    monkeypatch,
    interval_end,
    message,
):
    module, _fake_sdk = _load_dag_module(monkeypatch)
    context = {
        "dag_run": SimpleNamespace(conf={}),
        "data_interval_end": interval_end,
    }

    with pytest.raises(ValueError, match=message):
        module._effective_date_from_context(context)


@pytest.mark.parametrize("value", ["07/15/2026", "2026-7-15", 20260715])
def test_effective_date_rejects_invalid_override(monkeypatch, value):
    module, _fake_sdk = _load_dag_module(monkeypatch)
    context = {
        "dag_run": SimpleNamespace(conf={"effective_date": value}),
        "data_interval_end": datetime(2026, 7, 18, 0, tzinfo=UTC),
    }

    with pytest.raises(ValueError, match="effective_date must use YYYY-MM-DD"):
        module._effective_date_from_context(context)


def test_eoddata_daily_task_delegates_noop_result(monkeypatch):
    module, fake_sdk = _load_dag_module(monkeypatch)
    dag_run = SimpleNamespace(
        conf={},
        run_id="scheduled__2026-07-18T00:00:00+00:00",
    )
    fake_sdk.context = {
        "dag_run": dag_run,
        "data_interval_end": datetime(2026, 7, 18, 0, tzinfo=UTC),
    }
    connection = object()
    config = object()
    run_service = object()
    object_store = object()
    expected_payload = {
        "run_id": "8ca3c91f-d67c-44ba-aae6-20e7b12629c3",
        "status": "succeeded",
        "provider_code": "EODDATA",
        "effective_date": "2026-07-17",
        "report_object_id": "7a7e188f-272b-4384-a63a-0d6fb3695d5a",
        "pdf_report_object_id": "92d58710-d9f5-4b79-9c76-26348c2733e4",
        "market_pdf_report_object_id": "aaec1a3e-6934-4ce6-9668-c2de7696c131",
        "report_outcome": "PASS",
        "listing_counts": {"inserted": 0, "updated": 0, "unchanged": 0},
        "bar_counts": {"inserted": 0, "updated": 0, "unchanged": 0},
        "skipped_inactive_bars": 0,
        "failure_count": 0,
        "warning_count": 0,
        "expected_session_count": 0,
        "eligible_session_count": 0,
        "missing_session_count": 0,
        "ineligible_exchange_count": 3,
        "planned_exchange_count": 0,
        "retry_count": 0,
        "corrected_current_rows": 0,
    }
    calls = []

    class FakeConnectionContext:
        def __enter__(self):
            return connection

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(
        module.EmpireDatabase,
        "connect_from_env",
        lambda: FakeConnectionContext(),
    )
    monkeypatch.setattr(module.OHLCVConfig, "from_env", lambda: config)
    monkeypatch.setattr(
        module.RunService,
        "from_connection",
        lambda received: run_service if received is connection else None,
    )
    monkeypatch.setattr(
        module.ObjectStore,
        "from_connection",
        lambda received: object_store if received is connection else None,
    )

    def run(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(to_dict=lambda: expected_payload)

    monkeypatch.setattr(module, "run_eoddata_daily", run)

    result = dag_run_task(module).python_callable()

    assert result == expected_payload
    assert calls == [
        {
            "run_service": run_service,
            "connection": connection,
            "object_store": object_store,
            "config": config,
            "effective_date": date(2026, 7, 17),
            "run_type": "airflow",
            "runner": "airflow",
            "runner_ref": {
                "dag_id": DAG_ID,
                "dag_run_id": dag_run.run_id,
            },
        }
    ]


def test_eoddata_daily_task_propagates_runner_failure(monkeypatch):
    module, fake_sdk = _load_dag_module(monkeypatch)
    fake_sdk.context = {
        "dag_run": SimpleNamespace(conf={}, run_id="manual__failure"),
        "data_interval_end": datetime(2026, 8, 1, 13, tzinfo=UTC),
    }

    class FakeConnectionContext:
        def __enter__(self):
            return object()

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(
        module.EmpireDatabase,
        "connect_from_env",
        lambda: FakeConnectionContext(),
    )
    monkeypatch.setattr(module.OHLCVConfig, "from_env", lambda: object())
    monkeypatch.setattr(
        module,
        "run_eoddata_daily",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("runner failed")),
    )

    with pytest.raises(RuntimeError, match="runner failed"):
        dag_run_task(module).python_callable()


def test_eoddata_dispatch_uses_exact_source_dag_run_provenance(monkeypatch):
    module, fake_sdk = _load_dag_module(monkeypatch)
    fake_sdk.context = {
        "dag_run": SimpleNamespace(run_id="scheduled__2026-08-28T23:15:00+00:00")
    }
    source_result = {"tech_indicators_completion_signal": {"safe": True}}
    expected = {
        "trigger_run_id": "source__eoddata__run-id",
        "conf": {
            "source_core_run_id": "run-id",
            "effective_date": "2026-08-28",
        },
    }
    calls = []

    def build(*args, **kwargs):
        calls.append((args, kwargs))
        return expected

    monkeypatch.setattr(module, "build_tech_indicators_dispatch", build)

    assert prepare_dispatch_task(module).python_callable(source_result) == expected
    assert calls == [
        (
            (source_result,),
            {
                "source_dag_id": DAG_ID,
                "source_dag_run_id": (
                    "scheduled__2026-08-28T23:15:00+00:00"
                ),
            },
        )
    ]


def dag_run_task(module):
    return module.stonks_ohlcv_eoddata_daily_scrape_dag.task_by_id[
        "run_eoddata_daily"
    ]


def prepare_dispatch_task(module):
    return module.stonks_ohlcv_eoddata_daily_scrape_dag.task_by_id[
        "prepare_tech_indicators_dispatch"
    ]


def _load_dag_module(monkeypatch):
    fake_sdk = FakeAirflowSdk()
    airflow_module = ModuleType("airflow")
    airflow_sdk_exceptions_module = ModuleType("airflow.sdk.exceptions")
    airflow_providers_module = ModuleType("airflow.providers")
    airflow_standard_module = ModuleType("airflow.providers.standard")
    airflow_operators_module = ModuleType(
        "airflow.providers.standard.operators"
    )
    airflow_trigger_module = ModuleType(
        "airflow.providers.standard.operators.trigger_dagrun"
    )
    airflow_sdk_module = ModuleType("airflow.sdk")
    airflow_sdk_exceptions_module.AirflowSkipException = AirflowSkipException
    airflow_trigger_module.TriggerDagRunOperator = (
        fake_sdk.trigger_dag_run_operator
    )
    airflow_sdk_module.dag = fake_sdk.dag
    airflow_sdk_module.task = fake_sdk.task
    airflow_sdk_module.get_current_context = fake_sdk.get_current_context
    monkeypatch.setitem(sys.modules, "airflow", airflow_module)
    monkeypatch.setitem(
        sys.modules,
        "airflow.sdk.exceptions",
        airflow_sdk_exceptions_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "airflow.providers",
        airflow_providers_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "airflow.providers.standard",
        airflow_standard_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "airflow.providers.standard.operators",
        airflow_operators_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "airflow.providers.standard.operators.trigger_dagrun",
        airflow_trigger_module,
    )
    monkeypatch.setitem(sys.modules, "airflow.sdk", airflow_sdk_module)

    repo_root = Path(__file__).resolve().parents[3]
    dag_path = (
        repo_root / "dags" / "stonks" / "stonks_ohlcv_eoddata_daily_scrape.py"
    )
    module_name = "test_stonks_ohlcv_eoddata_daily_scrape_dag"
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

    def trigger_dag_run_operator(self, **operator_kwargs):
        assert self.active_dag is not None
        operator = FakeOperatorCall(
            task_id=operator_kwargs["task_id"],
            operator_kwargs=operator_kwargs,
        )
        self.active_dag.tasks.append(operator)
        return operator


@dataclass
class FakeDag:
    dag_id: str
    start_date: datetime
    schedule: object
    catchup: bool
    max_active_runs: int
    tags: list[str]
    tasks: list[object] = field(default_factory=list)

    @property
    def task_by_id(self):
        return {item.task_id: item for item in self.tasks}


@dataclass
class FakeTaskCall:
    task_id: str
    python_callable: object
    call_args: tuple[object, ...]
    call_kwargs: dict[str, object]

    def __getitem__(self, key: str):
        return FakeXComArg(self.task_id, key)


@dataclass(frozen=True)
class FakeXComArg:
    task_id: str
    key: str


@dataclass
class FakeOperatorCall:
    task_id: str
    operator_kwargs: dict[str, object]


class AirflowSkipException(Exception):
    pass
