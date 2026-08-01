from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


DAG_ID = "stonks_ohlcv_yahoo_daily_scrape"


def test_yahoo_daily_dag_is_manual_and_documents_production_cadence(
    monkeypatch,
):
    module, _fake_sdk = _load_dag_module(monkeypatch)

    dag = module.stonks_ohlcv_yahoo_daily_scrape_dag

    assert dag.dag_id == DAG_ID
    assert dag.schedule is None
    assert dag.start_date.tzinfo.key == "America/New_York"
    assert dag.catchup is False
    assert dag.max_active_runs == 1
    assert dag.tags == ["stonks", "ohlcv", "yahoo", "manual"]
    assert [item.task_id for item in dag.tasks] == ["run_yahoo_daily"]

    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "Local/development policy" in source
    assert "Production rollout policy" in source
    assert "06:00, 10:00, 13:00, 18:00, and 23:00" in source
    assert "America/New_York" in source
    assert "os.environ" not in source


def test_scope_uses_default_lookback_and_new_york_date(monkeypatch):
    module, _fake_sdk = _load_dag_module(monkeypatch)
    context = {
        "dag_run": SimpleNamespace(conf={}),
        "data_interval_end": datetime(2026, 8, 1, 2, tzinfo=UTC),
    }

    scope = module._scope_from_context(
        context,
        SimpleNamespace(yahoo_daily_lookback_days=30),
    )

    assert scope.effective_date == date(2026, 7, 31)
    assert scope.end_date == date(2026, 7, 31)
    assert scope.start_date == date(2026, 7, 2)
    assert scope.tickers == ()


def test_scope_forwards_manual_bounds_and_tickers(monkeypatch):
    module, _fake_sdk = _load_dag_module(monkeypatch)
    context = {
        "dag_run": SimpleNamespace(
            conf={
                "effective_date": "2026-07-30",
                "start_date": "2026-07-28",
                "end_date": "2026-07-30",
                "tickers": ["VXN", "SPX"],
            }
        ),
        "data_interval_end": datetime(2026, 8, 1, 2, tzinfo=UTC),
    }

    scope = module._scope_from_context(
        context,
        SimpleNamespace(yahoo_daily_lookback_days=30),
    )

    assert scope.effective_date == date(2026, 7, 30)
    assert scope.start_date == date(2026, 7, 28)
    assert scope.end_date == date(2026, 7, 30)
    assert scope.tickers == ("SPX", "VXN")


@pytest.mark.parametrize(
    ("conf", "message"),
    [
        ({"effective_date": "07/30/2026"}, "effective_date must use"),
        ({"start_date": 20260728}, "start_date must use"),
        ({"tickers": "SPX"}, "tickers must be a JSON array"),
        ({"tickers": ["spx"]}, "exact trimmed uppercase"),
        ({"tickers": ["SPX", "SPX"]}, "tickers must be unique"),
    ],
)
def test_scope_rejects_invalid_manual_configuration(
    monkeypatch,
    conf,
    message,
):
    module, _fake_sdk = _load_dag_module(monkeypatch)
    context = {
        "dag_run": SimpleNamespace(conf=conf),
        "data_interval_end": datetime(2026, 8, 1, 2, tzinfo=UTC),
    }

    with pytest.raises(ValueError, match=message):
        module._scope_from_context(
            context,
            SimpleNamespace(yahoo_daily_lookback_days=30),
        )


def test_yahoo_daily_task_delegates_noop_result(monkeypatch):
    module, fake_sdk = _load_dag_module(monkeypatch)
    dag_run = SimpleNamespace(
        conf={"effective_date": "2026-07-30", "tickers": ["SPX"]},
        run_id="manual__2026-08-01T13:00:00+00:00",
    )
    fake_sdk.context = {
        "dag_run": dag_run,
        "data_interval_end": datetime(2026, 8, 1, 13, tzinfo=UTC),
    }
    connection = object()
    config = SimpleNamespace(yahoo_daily_lookback_days=30)
    run_service = object()
    object_store = object()
    expected_payload = {
        "run_id": "20ef2f87-5453-44bf-b687-b604a17a7262",
        "status": "succeeded",
        "scope": {
            "effective_date": "2026-07-30",
            "start_date": "2026-07-01",
            "end_date": "2026-07-30",
            "tickers": ["SPX"],
        },
        "ingestion": {"request_count": 0},
        "reconciliation": {"request_count": 0},
        "report_object_id": "c0988359-242d-4a1f-b265-1466e00ae79b",
        "pdf_report_object_id": "f0fa81fb-e88b-4a81-ae28-a221b1dbad8f",
        "report_outcome": "PASS",
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

    monkeypatch.setattr(module, "run_yahoo_daily", run)

    result = dag_run_task(module).python_callable()

    assert result == expected_payload
    assert len(calls) == 1
    assert calls[0] == {
        "run_service": run_service,
        "connection": connection,
        "object_store": object_store,
        "config": config,
        "scope": module.YahooDailyScope(
            effective_date=date(2026, 7, 30),
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 30),
            tickers=("SPX",),
        ),
        "run_type": "airflow",
        "runner": "airflow",
        "runner_ref": {
            "dag_id": DAG_ID,
            "dag_run_id": dag_run.run_id,
        },
    }


def test_yahoo_daily_task_propagates_runner_failure(monkeypatch):
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
    monkeypatch.setattr(
        module.OHLCVConfig,
        "from_env",
        lambda: SimpleNamespace(yahoo_daily_lookback_days=30),
    )
    monkeypatch.setattr(
        module,
        "run_yahoo_daily",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("runner failed")),
    )

    with pytest.raises(RuntimeError, match="runner failed"):
        dag_run_task(module).python_callable()


def dag_run_task(module):
    return module.stonks_ohlcv_yahoo_daily_scrape_dag.task_by_id[
        "run_yahoo_daily"
    ]


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
    dag_path = (
        repo_root / "dags" / "stonks" / "stonks_ohlcv_yahoo_daily_scrape.py"
    )
    module_name = "test_stonks_ohlcv_yahoo_daily_scrape_dag"
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
