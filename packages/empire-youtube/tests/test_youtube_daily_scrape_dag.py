from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

EXPECTED_TASK_ORDER = [
    "scrape_youtube_metadata",
    "process_youtube_library_plan",
    "list_download_video_ids",
    "download_one_video",
    "generate_daily_summary",
    "finalize_downloads",
]


def test_youtube_daily_scrape_dag_imports_and_preserves_settings(monkeypatch):
    module, _fake_sdk = _load_dag_module(monkeypatch)

    dag = module.youtube_daily_scrape_dag

    assert dag.dag_id == "youtube_daily_scrape"
    assert dag.schedule is None
    assert dag.catchup is False
    assert dag.max_active_runs == 1
    assert dag.tags == ["youtube", "jellyfin", "manual"]
    assert [task.task_id for task in dag.tasks] == EXPECTED_TASK_ORDER


def test_youtube_daily_scrape_dag_wires_stages_in_order(monkeypatch):
    module, _fake_sdk = _load_dag_module(monkeypatch)

    dag = module.youtube_daily_scrape_dag

    assert dag.task_by_id["process_youtube_library_plan"].call_args[0].task_id == (
        "scrape_youtube_metadata"
    )
    assert dag.task_by_id["list_download_video_ids"].call_args[0].task_id == (
        "process_youtube_library_plan"
    )
    partial_kwargs = dag.task_by_id["download_one_video"].partial_kwargs
    assert partial_kwargs["plan_result"].task_id == (
        "process_youtube_library_plan"
    )
    assert partial_kwargs["scrape_result"].task_id == "scrape_youtube_metadata"
    assert dag.task_by_id["download_one_video"].expand_kwargs["video_id"].task_id == (
        "list_download_video_ids"
    )
    assert [
        task.task_id for task in dag.task_by_id["generate_daily_summary"].call_args
    ] == [
        "scrape_youtube_metadata",
        "process_youtube_library_plan",
        "download_one_video",
    ]
    assert dag.task_by_id["generate_daily_summary"].decorator_kwargs == {}
    assert dag.task_by_id["finalize_downloads"].decorator_kwargs == {
        "trigger_rule": "all_done"
    }
    assert dag.task_by_id["finalize_downloads"].call_args[0].task_id == (
        "generate_daily_summary"
    )


def test_youtube_daily_scrape_dag_preserves_download_task_configuration(monkeypatch):
    module, _fake_sdk = _load_dag_module(monkeypatch)

    download_task = module.youtube_daily_scrape_dag.task_by_id["download_one_video"]

    assert download_task.decorator_kwargs == {"pool": "youtube_download"}
    assert "retries" not in download_task.decorator_kwargs


def test_download_summary_allows_the_configured_failure_rate(monkeypatch):
    module, _fake_sdk = _load_dag_module(monkeypatch)

    summary = module._summarize_download_results(
        [
            {"video_id": "one", "status": "downloaded"},
            {"video_id": "two", "status": "skipped"},
            {"video_id": "three", "status": "downloaded"},
            {"video_id": "four", "status": "failed"},
            {"video_id": "five", "status": "failed"},
        ]
    )

    assert summary["success_rate"] == 0.6
    assert summary["minimum_success_rate"] == 0.6
    assert summary["failed_video_ids"] == ["four", "five"]


def test_download_cleanup_defaults_to_removing_incomplete_jellyfin_folders(monkeypatch):
    module, _fake_sdk = _load_dag_module(monkeypatch)

    assert module._cleanup_on_failure_from_conf({}) is True
    assert module._cleanup_on_failure_from_conf({"cleanup_on_failure": False}) is False


def test_old_youtube_dag_definitions_are_retired():
    repo_root = Path(__file__).resolve().parents[3]
    dag_files = sorted(path.name for path in (repo_root / "dags" / "youtube").glob("*.py"))

    assert dag_files == ["__init__.py", "youtube_daily_scrape.py"]


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
    dag_path = repo_root / "dags" / "youtube" / "youtube_daily_scrape.py"
    module_name = "test_youtube_daily_scrape_dag_module"
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

    def task(self, *, task_id, **task_kwargs):
        def decorator(python_callable):
            def wrapper(*args, **kwargs):
                assert self.active_dag is not None
                task_call = FakeTaskCall(
                    dag=self.active_dag,
                    task_id=task_id,
                    python_callable=python_callable,
                    call_args=args,
                    call_kwargs=kwargs,
                    decorator_kwargs=task_kwargs,
                )
                self.active_dag.add_task(task_call)
                return task_call

            return FakeTaskDecorator(wrapper)

        return decorator

    def get_current_context(self):
        raise AssertionError("Task functions must not run while constructing the DAG.")


class FakeTaskDecorator:
    def __init__(self, wrapper):
        self.wrapper = wrapper
        self.partial_kwargs: dict[str, object] = {}

    def __call__(self, *args, **kwargs):
        task = self.wrapper(*args, **kwargs)
        task.partial_kwargs = self.partial_kwargs
        return task

    def partial(self, **kwargs):
        self.partial_kwargs = kwargs
        return self

    def expand(self, **kwargs):
        task = self.wrapper()
        task.partial_kwargs = self.partial_kwargs
        task.expand_kwargs = kwargs
        return task


@dataclass
class FakeDag:
    dag_id: str
    schedule: object
    catchup: bool
    max_active_runs: int
    tags: list[str]
    tasks: list["FakeTaskCall"] = field(default_factory=list)

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
    decorator_kwargs: dict[str, object]
    partial_kwargs: dict[str, object] = field(default_factory=dict)
    expand_kwargs: dict[str, object] = field(default_factory=dict)
