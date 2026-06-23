"""Shared Airflow DAG trigger-conf helpers for stonks securities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID


INPUT_RUN_ID_CONF_KEY = "input_run_id"
VERIFY_REPORT_OBJECT_ID_CONF_KEY = "verify_report_object_id"
VALIDATION_REPORT_OBJECT_ID_CONF_KEY = "validation_report_object_id"
CONFLICT_REPORT_OBJECT_ID_CONF_KEY = "conflict_report_object_id"

JINJA_INPUT_RUN_ID = "{{ dag_run.conf['input_run_id'] }}"
JINJA_VERIFY_REPORT_OBJECT_ID = "{{ dag_run.conf.get('verify_report_object_id') }}"
JINJA_VALIDATION_REPORT_OBJECT_ID = "{{ dag_run.conf.get('validation_report_object_id') }}"
JINJA_SCRAPE_RUN_ID = "{{ ti.xcom_pull(task_ids='collect_sec_sources')['run_id'] }}"


@dataclass(frozen=True)
class StonksSecuritiesTriggerConf:
    """Typed builder for Airflow trigger DAG conf payloads."""

    input_run_id: str
    verify_report_object_id: str | None = None
    validation_report_object_id: str | None = None
    conflict_report_object_id: str | None = None

    def to_dict(self) -> dict[str, str]:
        payload = {INPUT_RUN_ID_CONF_KEY: self.input_run_id}
        if self.verify_report_object_id is not None:
            payload[VERIFY_REPORT_OBJECT_ID_CONF_KEY] = self.verify_report_object_id
        if self.validation_report_object_id is not None:
            payload[VALIDATION_REPORT_OBJECT_ID_CONF_KEY] = self.validation_report_object_id
        if self.conflict_report_object_id is not None:
            payload[CONFLICT_REPORT_OBJECT_ID_CONF_KEY] = self.conflict_report_object_id
        return payload


def scrape_to_verify_conf() -> dict[str, str]:
    return StonksSecuritiesTriggerConf(input_run_id=JINJA_SCRAPE_RUN_ID).to_dict()


def pass_through_conf(
    *,
    verify_report: bool = True,
    validation_report: bool = False,
) -> dict[str, str]:
    return StonksSecuritiesTriggerConf(
        input_run_id=JINJA_INPUT_RUN_ID,
        verify_report_object_id=JINJA_VERIFY_REPORT_OBJECT_ID if verify_report else None,
        validation_report_object_id=(
            JINJA_VALIDATION_REPORT_OBJECT_ID if validation_report else None
        ),
    ).to_dict()


def verify_to_observations_conf(*, verify_task_id: str = "verify_sec_sources") -> dict[str, str]:
    return StonksSecuritiesTriggerConf(
        input_run_id=JINJA_INPUT_RUN_ID,
        verify_report_object_id=_xcom_object_id_template(verify_task_id),
    ).to_dict()


def validation_to_conflicts_conf(
    *, validation_task_id: str = "generate_validation_report"
) -> dict[str, str]:
    return StonksSecuritiesTriggerConf(
        input_run_id=JINJA_INPUT_RUN_ID,
        verify_report_object_id=JINJA_VERIFY_REPORT_OBJECT_ID,
        validation_report_object_id=_xcom_object_id_template(validation_task_id),
    ).to_dict()


def conflicts_to_summary_conf(
    *, conflict_task_id: str = "generate_conflict_report"
) -> dict[str, str]:
    return StonksSecuritiesTriggerConf(
        input_run_id=JINJA_INPUT_RUN_ID,
        verify_report_object_id=JINJA_VERIFY_REPORT_OBJECT_ID,
        validation_report_object_id=JINJA_VALIDATION_REPORT_OBJECT_ID,
        conflict_report_object_id=_xcom_object_id_template(conflict_task_id),
    ).to_dict()


def input_run_id_from_conf(conf: dict[str, Any]) -> UUID:
    input_run_id = conf.get(INPUT_RUN_ID_CONF_KEY)
    if not input_run_id:
        raise RuntimeError("Provide input_run_id in dag_run.conf.")
    return UUID(str(input_run_id))


def optional_object_id(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "null"}:
        return None
    return text


def _xcom_object_id_template(task_id: str) -> str:
    return "{{ ti.xcom_pull(task_ids='" + task_id + "')['object_id'] }}"
