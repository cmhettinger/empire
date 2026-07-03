from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType, SimpleNamespace

from empire_stonks_securities import DEFAULT_DAILY_REFRESH_DAG_ID


EXPECTED_TASK_ORDER = [
    "collect_sec_sources",
    "verify_sec_sources",
    "write_sec_observations",
    "upsert_sec_issuers",
    "upsert_sec_securities",
    "upsert_sec_listings",
    "generate_validation_report",
    "generate_conflict_report",
    "generate_daily_refresh_summary",
]


def test_consolidated_sec_daily_scrape_dag_imports(monkeypatch):
    module, _fake_sdk = _load_dag_module(monkeypatch)

    dag = module.stonks_securities_sec_daily_scrape_dag

    assert dag.dag_id == DEFAULT_DAILY_REFRESH_DAG_ID
    assert dag.schedule is None
    assert dag.catchup is False
    assert dag.max_active_runs == 1
    assert dag.tags == ["stonks", "securities", "sec", "manual"]
    assert [task.task_id for task in dag.tasks] == EXPECTED_TASK_ORDER


def test_consolidated_sec_daily_scrape_dag_preserves_stage_order(monkeypatch):
    module, _fake_sdk = _load_dag_module(monkeypatch)

    dag = module.stonks_securities_sec_daily_scrape_dag
    edges = [(upstream.task_id, downstream.task_id) for upstream, downstream in dag.edges]

    assert edges == list(zip(EXPECTED_TASK_ORDER, EXPECTED_TASK_ORDER[1:]))
    assert dag.task_by_id["verify_sec_sources"].call_args[0].task_id == "collect_sec_sources"
    assert (
        dag.task_by_id["write_sec_observations"].call_args[0].task_id
        == "verify_sec_sources"
    )
    assert [
        task.task_id for task in dag.task_by_id["generate_daily_refresh_summary"].call_args
    ] == [
        "verify_sec_sources",
        "generate_validation_report",
        "generate_conflict_report",
    ]


def test_consolidated_sec_daily_scrape_dag_builds_run_context(monkeypatch):
    module, fake_sdk = _load_dag_module(monkeypatch)
    fake_sdk.context = {
        "dag_run": SimpleNamespace(
            dag_id=DEFAULT_DAILY_REFRESH_DAG_ID,
            run_id="manual__2026-07-03T12:00:00+00:00",
        ),
        "logical_date": "2026-07-03T12:00:00+00:00",
    }

    context = module._airflow_run_context()

    assert context.workflow_id == DEFAULT_DAILY_REFRESH_DAG_ID
    assert context.run_id == "manual__2026-07-03T12:00:00+00:00"
    assert context.logical_date == "2026-07-03T12:00:00+00:00"
    assert context.environment == "airflow"


def _load_dag_module(monkeypatch):
    fake_sdk = FakeAirflowSdk()
    airflow_module = ModuleType("airflow")
    airflow_sdk_module = ModuleType("airflow.sdk")
    airflow_sdk_module.dag = fake_sdk.dag
    airflow_sdk_module.task = fake_sdk.task
    airflow_sdk_module.get_current_context = fake_sdk.get_current_context
    monkeypatch.setitem(sys.modules, "airflow", airflow_module)
    monkeypatch.setitem(sys.modules, "airflow.sdk", airflow_sdk_module)

    repo_root = Path(__file__).resolve().parents[3]
    dag_path = repo_root / "dags" / "stonks" / "stonks_securities_sec_daily_scrape.py"
    module_name = "test_stonks_securities_sec_daily_scrape_dag"
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
                dag = FakeDag(
                    dag_id=dag_kwargs["dag_id"],
                    schedule=dag_kwargs["schedule"],
                    catchup=dag_kwargs["catchup"],
                    max_active_runs=dag_kwargs["max_active_runs"],
                    tags=dag_kwargs["tags"],
                )
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
                    dag=self.active_dag,
                    task_id=task_id,
                    python_callable=python_callable,
                    call_args=args,
                    call_kwargs=kwargs,
                )
                self.active_dag.add_task(task_call)
                return task_call

            return wrapper

        return decorator

    def get_current_context(self):
        assert self.context is not None
        return self.context


@dataclass
class FakeDag:
    dag_id: str
    schedule: object
    catchup: bool
    max_active_runs: int
    tags: list[str]
    tasks: list["FakeTaskCall"] = field(default_factory=list)
    edges: list[tuple["FakeTaskCall", "FakeTaskCall"]] = field(default_factory=list)

    @property
    def task_by_id(self):
        return {task.task_id: task for task in self.tasks}

    def add_task(self, task_call):
        self.tasks.append(task_call)


@dataclass
class FakeTaskCall:
    dag: FakeDag
    task_id: str
    python_callable: object
    call_args: tuple[object, ...]
    call_kwargs: dict[str, object]

    def __rshift__(self, other):
        self.dag.edges.append((self, other))
        return other
