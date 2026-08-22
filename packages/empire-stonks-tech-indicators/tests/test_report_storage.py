from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from empire_core import ObjectStore, RunContext, StorageRoot, StoredObject
from empire_stonks_tech_indicators import (
    BACKFILL_JSON_REPORT_LOGICAL_NAME,
    DAILY_JSON_REPORT_LOGICAL_NAME,
    JSON_REPORT_CONTENT_TYPE,
    JSON_REPORT_FILENAME,
    JSON_REPORT_LOGICAL_NAMES,
    JSON_REPORT_OBJECT_KIND,
    TechIndicatorsConfig,
    build_tech_indicators_report_object_key,
    render_tech_indicators_report_json,
    store_tech_indicators_json_report,
    tech_indicators_report_metadata,
)
from test_reports import _daily_pass, _no_op, _partial


STORED_AT = datetime(2026, 8, 22, 14, 0, tzinfo=UTC)


class FakeObjectRepository:
    def __init__(self, base_uri: Path) -> None:
        self.root = StorageRoot(
            storage_root_id=1,
            root_name="global",
            backend_type="filesystem",
            base_uri=str(base_uri),
        )
        self.objects: dict[UUID, StoredObject] = {}

    def get_storage_root(self, root_name: str) -> StorageRoot | None:
        return self.root if root_name == self.root.root_name else None

    def insert_object(self, **values: object) -> StoredObject:
        stored = StoredObject(
            object_id=uuid4(),
            run_id=values["run_id"],
            storage_root_id=values["storage_root_id"],
            storage_root_name=self.root.root_name,
            base_uri=self.root.base_uri,
            object_key=values["object_key"],
            filename=values["filename"],
            object_scope=values["object_scope"],
            domain=values["domain"],
            logical_name=values["logical_name"],
            content_type=values["content_type"],
            object_kind=values["object_kind"],
            size_bytes=values["size_bytes"],
            checksum_sha256=values["checksum_sha256"],
            expires_at=values["expires_at"],
            deleted_at=None,
            purge_after=None,
            metadata=values["metadata"],
            created_at=STORED_AT,
            updated_at=STORED_AT,
        )
        self.objects[stored.object_id] = stored
        return stored

    def get_object(self, object_id: UUID) -> StoredObject | None:
        return self.objects.get(object_id)


def _run_context(report, **overrides: object) -> RunContext:
    values = {
        "run_id": report.identity.run_id,
        "domain": "stonks",
        "job_name": report.identity.core_job_name,
        "subject_key": report.identity.core_subject_key,
        "effective_date": report.identity.effective_date,
        "run_type": "cli",
        "status": "started",
        "runner": "pytest",
    }
    values.update(overrides)
    return RunContext(**values)


def test_stores_daily_report_with_exact_core_contract(tmp_path: Path) -> None:
    report = _daily_pass()
    repository = FakeObjectRepository(tmp_path)
    object_store = ObjectStore(repository)

    stored = store_tech_indicators_json_report(
        object_store=object_store,
        run_context=_run_context(report),
        config=TechIndicatorsConfig(),
        report=report,
    )

    payload = render_tech_indicators_report_json(report)
    assert stored.object_key == (
        "stonks/tech-indicators/runs/2026/08/21/"
        "81111111-1111-4111-8111-111111111111/reports"
    )
    assert stored.filename == JSON_REPORT_FILENAME == "report.json"
    assert stored.object_scope == "run"
    assert stored.run_id == report.identity.run_id
    assert stored.domain == "stonks"
    assert stored.logical_name == DAILY_JSON_REPORT_LOGICAL_NAME
    assert stored.object_kind == JSON_REPORT_OBJECT_KIND
    assert stored.content_type == JSON_REPORT_CONTENT_TYPE
    assert stored.expires_at is None
    assert stored.size_bytes == len(payload)
    assert stored.checksum_sha256 == hashlib.sha256(payload).hexdigest()
    assert stored.metadata == {
        "schema_version": 1,
        "report_id": "stonks.tech-indicators.daily",
        "workflow_kind": "DAILY",
        "outcome": "PASS",
        "effective_date": "2026-08-21",
        "calculation_version": "TECH_INDICATORS_V1",
        "scope_hash": "a" * 64,
        "publication_id": "82222222-2222-4222-8222-222222222222",
        "generated_at": "2026-08-22T12:00:10.000001Z",
    }
    assert object_store.get_bytes(stored.object_id) == payload
    assert json.loads(payload)["identity"]["json_object_id"] is None


@pytest.mark.parametrize(
    ("report_factory", "logical_name"),
    (
        (_no_op, DAILY_JSON_REPORT_LOGICAL_NAME),
        (_partial, BACKFILL_JSON_REPORT_LOGICAL_NAME),
    ),
)
def test_storage_handles_no_op_and_resumed_partial_backfill(
    tmp_path: Path,
    report_factory,
    logical_name: str,
) -> None:
    report = report_factory()

    stored = store_tech_indicators_json_report(
        object_store=ObjectStore(FakeObjectRepository(tmp_path)),
        run_context=_run_context(report),
        config=TechIndicatorsConfig(),
        report=report,
    )

    assert stored.logical_name == logical_name
    assert stored.metadata == tech_indicators_report_metadata(report)
    assert stored.metadata["publication_id"] == (
        None
        if report.identity.publication_id is None
        else str(report.identity.publication_id)
    )


@pytest.mark.parametrize(
    ("override", "message"),
    (
        ({"status": "succeeded"}, "active stonks"),
        ({"domain": "weather"}, "active stonks"),
        ({"run_id": uuid4()}, "run_id"),
        ({"job_name": "stonks_tech_indicators_daily"}, "Core job"),
        ({"subject_key": "different"}, "subject key"),
        ({"effective_date": date(2026, 8, 20)}, "effective date"),
    ),
)
def test_rejects_mismatched_core_run_relationship(
    tmp_path: Path,
    override: dict[str, object],
    message: str,
) -> None:
    report = _partial()

    with pytest.raises(ValueError, match=message):
        store_tech_indicators_json_report(
            object_store=ObjectStore(FakeObjectRepository(tmp_path)),
            run_context=_run_context(report, **override),
            config=TechIndicatorsConfig(),
            report=report,
        )


def test_key_builder_and_storage_reject_unsafe_paths(tmp_path: Path) -> None:
    report = _daily_pass()
    run_context = _run_context(report)

    assert build_tech_indicators_report_object_key(
        storage_key="stonks/tech-indicators",
        run_context=run_context,
    ).endswith(f"/{report.identity.run_id}/reports")
    with pytest.raises(ValueError, match="path-safe"):
        build_tech_indicators_report_object_key(
            storage_key="stonks/../secret",
            run_context=run_context,
        )
    with pytest.raises(ValueError, match="path-safe"):
        store_tech_indicators_json_report(
            object_store=ObjectStore(FakeObjectRepository(tmp_path)),
            run_context=run_context,
            config=TechIndicatorsConfig(),
            report=report,
            storage_root="../global",
        )


def test_logical_name_vocabulary_is_immutable() -> None:
    with pytest.raises(TypeError):
        JSON_REPORT_LOGICAL_NAMES["DAILY"] = "changed"  # type: ignore[index]
