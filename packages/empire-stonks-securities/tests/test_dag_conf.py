from __future__ import annotations

from uuid import UUID

import pytest

from empire_stonks_securities.dag_conf import (
    CONFLICT_REPORT_OBJECT_ID_CONF_KEY,
    INPUT_RUN_ID_CONF_KEY,
    VALIDATION_REPORT_OBJECT_ID_CONF_KEY,
    VERIFY_REPORT_OBJECT_ID_CONF_KEY,
    StonksSecuritiesTriggerConf,
    conflicts_to_summary_conf,
    input_run_id_from_conf,
    optional_object_id,
    pass_through_conf,
    scrape_to_verify_conf,
    validation_to_conflicts_conf,
    verify_to_observations_conf,
)


def test_trigger_conf_builder_omits_absent_optional_values():
    payload = StonksSecuritiesTriggerConf(input_run_id="run-template").to_dict()

    assert payload == {INPUT_RUN_ID_CONF_KEY: "run-template"}


def test_trigger_conf_builder_includes_report_object_ids():
    payload = StonksSecuritiesTriggerConf(
        input_run_id="run-template",
        verify_report_object_id="verify-template",
        validation_report_object_id="validation-template",
        conflict_report_object_id="conflict-template",
    ).to_dict()

    assert payload == {
        INPUT_RUN_ID_CONF_KEY: "run-template",
        VERIFY_REPORT_OBJECT_ID_CONF_KEY: "verify-template",
        VALIDATION_REPORT_OBJECT_ID_CONF_KEY: "validation-template",
        CONFLICT_REPORT_OBJECT_ID_CONF_KEY: "conflict-template",
    }


def test_scrape_to_verify_conf_uses_collect_task_xcom():
    assert scrape_to_verify_conf() == {
        INPUT_RUN_ID_CONF_KEY: "{{ ti.xcom_pull(task_ids='collect_sec_sources')['run_id'] }}"
    }


def test_pass_through_conf_uses_named_keys():
    assert pass_through_conf() == {
        INPUT_RUN_ID_CONF_KEY: "{{ dag_run.conf['input_run_id'] }}",
        VERIFY_REPORT_OBJECT_ID_CONF_KEY: "{{ dag_run.conf.get('verify_report_object_id') }}",
    }


def test_report_stage_confs_use_xcom_report_ids():
    assert verify_to_observations_conf()[VERIFY_REPORT_OBJECT_ID_CONF_KEY] == (
        "{{ ti.xcom_pull(task_ids='verify_sec_sources')['object_id'] }}"
    )
    assert validation_to_conflicts_conf()[VALIDATION_REPORT_OBJECT_ID_CONF_KEY] == (
        "{{ ti.xcom_pull(task_ids='generate_validation_report')['object_id'] }}"
    )
    assert conflicts_to_summary_conf()[CONFLICT_REPORT_OBJECT_ID_CONF_KEY] == (
        "{{ ti.xcom_pull(task_ids='generate_conflict_report')['object_id'] }}"
    )


def test_input_run_id_from_conf_parses_uuid_and_fails_when_missing():
    run_id = "00000000-0000-0000-0000-000000000123"

    assert input_run_id_from_conf({INPUT_RUN_ID_CONF_KEY: run_id}) == UUID(run_id)
    with pytest.raises(RuntimeError, match="input_run_id"):
        input_run_id_from_conf({})


@pytest.mark.parametrize("value", [None, "", " ", "None", "null"])
def test_optional_object_id_treats_empty_template_values_as_missing(value):
    assert optional_object_id(value) is None


def test_optional_object_id_returns_text_for_present_value():
    assert optional_object_id("  report-id  ") == "report-id"
