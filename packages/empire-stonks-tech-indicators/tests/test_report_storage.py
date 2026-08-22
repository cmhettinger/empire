from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pypdf import PdfReader

from empire_core import ObjectStore, RunContext, StorageRoot, StoredObject
from empire_stonks_tech_indicators import (
    BACKFILL_PDF_REPORT_LOGICAL_NAME,
    BACKFILL_JSON_REPORT_LOGICAL_NAME,
    DAILY_PDF_REPORT_LOGICAL_NAME,
    DAILY_JSON_REPORT_LOGICAL_NAME,
    JSON_REPORT_CONTENT_TYPE,
    JSON_REPORT_FILENAME,
    JSON_REPORT_LOGICAL_NAMES,
    JSON_REPORT_OBJECT_KIND,
    PDF_MAXIMUM_BYTES,
    PDF_MAXIMUM_PAGES,
    PDF_REPORT_CONTENT_TYPE,
    PDF_REPORT_FILENAME,
    PDF_REPORT_LOGICAL_NAMES,
    PDF_REPORT_OBJECT_KIND,
    TechIndicatorsConfig,
    build_tech_indicators_report_object_key,
    render_tech_indicators_report_json,
    store_tech_indicators_json_report,
    store_tech_indicators_pdf_report,
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


def _paired_facts(payload: dict[str, object]) -> dict[str, object]:
    identity = payload["identity"]
    versions = payload["versions"]
    scope = payload["scope"]
    readiness = payload["source_readiness"]
    publication = payload["publication"]
    coverage = payload["coverage"]
    assert isinstance(identity, dict)
    assert isinstance(versions, dict)
    assert isinstance(scope, dict)
    assert isinstance(readiness, dict)
    assert isinstance(publication, dict)
    assert isinstance(coverage, dict)
    warnings = payload["warnings"]
    failures = payload["failures"]
    assert isinstance(warnings, list)
    assert isinstance(failures, list)
    return {
        "report_id": payload["report_id"],
        "schema_version": payload["schema_version"],
        "workflow_kind": payload["workflow_kind"],
        "outcome": payload["outcome"],
        "effective_date": identity["effective_date"],
        "calculation_version": versions["calculation_version"],
        "scope_hash": scope["scope_hash"],
        "publication_id": identity["publication_id"],
        "generated_at": payload["generated_at"],
        "counts": payload["counts"],
        "writes": payload["writes"],
        "source_readiness": readiness["decision"],
        "publication_phase": publication["report_phase"],
        "publication_readiness": publication["readiness_at_report"],
        "warning_count": sum(item["count"] for item in warnings),
        "failure_count": sum(item["count"] for item in failures),
        "benchmark_coverage": coverage["benchmark"],
    }


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


def test_stores_daily_pdf_with_exact_core_contract(tmp_path: Path) -> None:
    report = _daily_pass()
    repository = FakeObjectRepository(tmp_path / "objects")
    object_store = ObjectStore(repository)

    stored = store_tech_indicators_pdf_report(
        object_store=object_store,
        run_context=_run_context(report),
        config=TechIndicatorsConfig(),
        report=report,
        output_dir=tmp_path / "render",
    )

    payload = object_store.get_bytes(stored.object_id)
    stored_path = object_store.get_path(stored.object_id)
    assert stored.object_key == (
        "stonks/tech-indicators/runs/2026/08/21/"
        "81111111-1111-4111-8111-111111111111/reports"
    )
    assert stored.filename == PDF_REPORT_FILENAME == "report.pdf"
    assert stored.object_scope == "run"
    assert stored.run_id == report.identity.run_id
    assert stored.domain == "stonks"
    assert stored.logical_name == DAILY_PDF_REPORT_LOGICAL_NAME
    assert stored.object_kind == PDF_REPORT_OBJECT_KIND
    assert stored.content_type == PDF_REPORT_CONTENT_TYPE
    assert stored.expires_at is None
    assert stored.size_bytes == len(payload) <= PDF_MAXIMUM_BYTES
    assert stored.checksum_sha256 == hashlib.sha256(payload).hexdigest()
    assert stored.metadata == tech_indicators_report_metadata(report)
    assert payload.startswith(b"%PDF-")
    assert len(PdfReader(stored_path).pages) <= PDF_MAXIMUM_PAGES


@pytest.mark.parametrize("report_factory", (_daily_pass, _partial))
def test_json_and_pdf_store_matching_facts_from_one_immutable_report(
    tmp_path: Path,
    report_factory,
) -> None:
    report = report_factory()
    before = report.to_dict()
    repository = FakeObjectRepository(tmp_path / "objects")
    object_store = ObjectStore(repository)
    run_context = _run_context(report)

    stored_json = store_tech_indicators_json_report(
        object_store=object_store,
        run_context=run_context,
        config=TechIndicatorsConfig(),
        report=report,
    )
    stored_pdf = store_tech_indicators_pdf_report(
        object_store=object_store,
        run_context=run_context,
        config=TechIndicatorsConfig(),
        report=report,
        output_dir=tmp_path / "render",
    )

    json_facts = json.loads(object_store.get_bytes(stored_json.object_id))
    assert report.to_dict() == before
    assert _paired_facts(json_facts) == _paired_facts(before)
    assert stored_json.run_id == stored_pdf.run_id == report.identity.run_id
    assert stored_json.object_key == stored_pdf.object_key
    assert stored_json.metadata == stored_pdf.metadata
    assert stored_pdf.logical_name == PDF_REPORT_LOGICAL_NAMES[report.workflow_kind]


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
    with pytest.raises(TypeError):
        PDF_REPORT_LOGICAL_NAMES["DAILY"] = "changed"  # type: ignore[index]
