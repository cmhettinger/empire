from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from empire_core import ObjectStore
from empire_core.object_store.models import StorageRoot, StoredObject
from empire_stonks_securities.acquisition import (
    SecDownloadError,
    SecDownloader,
    build_configured_source_targets,
    build_metadata,
    build_object_key,
    build_quarterly_master_index_targets,
    cached_pair_exists,
)
from empire_stonks_securities.config import StonksSecuritiesConfig

from test_config import CONFIG


def test_manifest_loading_includes_quarterly_range():
    config = StonksSecuritiesConfig.from_mapping(CONFIG)

    assert config.download.quarterly_master_index.start_year == 1995
    assert config.download.quarterly_master_index.quarters == (1, 2, 3, 4)


def test_deterministic_path_generation():
    object_key = build_object_key(
        storage_key="/stonks/securities/",
        acquisition_date=date(2026, 6, 10),
        acquisition_id="512578ba-2f75-42be-89b5-6dfc47ea36c1",
        source_key="sec_submissions_zip",
    )

    assert (
        object_key
        == "stonks/securities/runs/2026/06/10/512578ba-2f75-42be-89b5-6dfc47ea36c1/sec_submissions_zip"
    )


def test_quarterly_targets_use_configurable_master_zip_url():
    config = StonksSecuritiesConfig.from_file("object-store/config/stonks-securities/config.yml")

    targets = build_quarterly_master_index_targets(
        config=config,
        storage_key="stonks/securities",
        acquisition_date=date(2026, 6, 10),
        acquisition_id="manual",
        start_year=2025,
        end_year=2025,
        quarters=[2],
    )

    assert targets[0].source_url == "https://www.sec.gov/Archives/edgar/full-index/2025/QTR2/master.zip"
    assert targets[0].filename == "2025-QTR2-master.zip"


def test_metadata_sidecar_generation(tmp_path):
    object_store = ObjectStore(FakeObjectRepository(tmp_path))
    config = StonksSecuritiesConfig.from_mapping(CONFIG)
    target = build_configured_source_targets(
        config=config,
        storage_key="stonks/securities",
        acquisition_date=date(2026, 6, 10),
        acquisition_id="manual",
        source_keys=["sec_company_tickers"],
    )[0]

    metadata = build_metadata(
        target=target,
        storage_root="global",
        object_store=object_store,
        size_bytes=13,
        sha256="abc123",
        http_status=200,
        headers={"ETag": '"test"', "Last-Modified": "Wed, 10 Jun 2026 00:00:00 GMT"},
    )

    assert metadata["source_code"] == "SEC_COMPANY_TICKERS"
    assert metadata["source_url"] == "https://www.sec.gov/files/company_tickers.json"
    assert metadata["size_bytes"] == 13
    assert metadata["sha256"] == "abc123"
    assert metadata["http_status"] == 200
    assert metadata["etag"] == '"test"'
    assert metadata["last_modified"] == "Wed, 10 Jun 2026 00:00:00 GMT"
    assert metadata["file_path"].endswith("stonks/securities/runs/2026/06/10/manual/sec_company_tickers/company_tickers.json")


def test_skip_if_present_behavior(tmp_path):
    object_store = ObjectStore(FakeObjectRepository(tmp_path))
    config = StonksSecuritiesConfig.from_mapping(CONFIG)
    target = build_configured_source_targets(
        config=config,
        storage_key="stonks/securities",
        acquisition_date=date(2026, 6, 10),
        acquisition_id="manual",
        source_keys=["sec_company_tickers"],
    )[0]
    source = tmp_path / "source.json"
    source.write_text("{}", encoding="utf-8")
    object_store.put_file(
        run_context=None,
        object_scope="manual",
        storage_root="global",
        object_key=target.object_key,
        filename=target.filename,
        source_path=source,
    )
    object_store.put_bytes(
        run_context=None,
        object_scope="manual",
        storage_root="global",
        object_key=target.object_key,
        filename=target.metadata_filename,
        data=b"{}",
    )

    result = SecDownloader(config, session=ExplodingSession()).download_target(
        target=target,
        object_store=object_store,
        storage_root="global",
        temp_dir=tmp_path / "tmp",
    )

    assert result.skipped is True
    assert result.status == "skipped"


def test_mocked_http_download_success_writes_file_and_sidecar(tmp_path):
    object_store = ObjectStore(FakeObjectRepository(tmp_path / "store"))
    config = StonksSecuritiesConfig.from_mapping(CONFIG)
    session = FakeSession([FakeResponse(200, [b'{"ok":', b"true}"], {"ETag": '"v1"'})])
    target = build_configured_source_targets(
        config=config,
        storage_key="stonks/securities",
        acquisition_date=date(2026, 6, 10),
        acquisition_id="manual",
        source_keys=["sec_company_tickers"],
    )[0]

    result = SecDownloader(config, session=session, sleep_func=lambda _: None).download_target(
        target=target,
        object_store=object_store,
        storage_root="global",
        temp_dir=tmp_path / "tmp",
    )

    assert result.status == "downloaded"
    assert result.size_bytes == 11
    assert session.requests[0]["headers"]["User-Agent"] == config.sec.user_agent
    assert cached_pair_exists(
        object_store=object_store,
        storage_root="global",
        object_key=target.object_key,
        filename=target.filename,
        metadata_filename=target.metadata_filename,
    )
    sidecar = (tmp_path / "store" / target.object_key / target.metadata_filename).read_text(
        encoding="utf-8"
    )
    assert json.loads(sidecar)["source_code"] == "SEC_COMPANY_TICKERS"


def test_temp_file_is_renamed_then_moved_to_object_store(tmp_path):
    object_store = ObjectStore(FakeObjectRepository(tmp_path / "store"))
    config = StonksSecuritiesConfig.from_mapping(CONFIG)
    session = FakeSession([FakeResponse(200, [b"hello"])])
    target = build_configured_source_targets(
        config=config,
        storage_key="stonks/securities",
        acquisition_date=date(2026, 6, 10),
        acquisition_id="manual",
        source_keys=["sec_company_tickers"],
    )[0]
    temp_dir = tmp_path / "tmp"

    SecDownloader(config, session=session, sleep_func=lambda _: None).download_target(
        target=target,
        object_store=object_store,
        storage_root="global",
        temp_dir=temp_dir,
    )

    assert not list(temp_dir.rglob("*.part"))
    assert (tmp_path / "store" / target.object_key / target.filename).read_bytes() == b"hello"


def test_http_retry_success(tmp_path):
    object_store = ObjectStore(FakeObjectRepository(tmp_path / "store"))
    config_data = {"stonks_securities": dict(CONFIG["stonks_securities"])}
    config_data["stonks_securities"]["respect_rate_limits"] = False
    config = StonksSecuritiesConfig.from_mapping(config_data)
    sleeps: list[float] = []
    session = FakeSession([
        FakeResponse(503, [b""]),
        FakeResponse(200, [b"ok"]),
    ])
    target = build_configured_source_targets(
        config=config,
        storage_key="stonks/securities",
        acquisition_date=date(2026, 6, 10),
        acquisition_id="manual",
        source_keys=["sec_company_tickers"],
    )[0]

    result = SecDownloader(config, session=session, sleep_func=sleeps.append).download_target(
        target=target,
        object_store=object_store,
        storage_root="global",
        temp_dir=tmp_path / "tmp",
    )

    assert result.status == "downloaded"
    assert len(session.requests) == 2
    assert sleeps == [5.0]


def test_http_429_failure_message(tmp_path):
    object_store = ObjectStore(FakeObjectRepository(tmp_path / "store"))
    config_data = {"stonks_securities": dict(CONFIG["stonks_securities"])}
    config_data["stonks_securities"]["max_retries"] = 0
    config = StonksSecuritiesConfig.from_mapping(config_data)
    session = FakeSession([FakeResponse(429, [b"slow down"])])
    target = build_configured_source_targets(
        config=config,
        storage_key="stonks/securities",
        acquisition_date=date(2026, 6, 10),
        acquisition_id="manual",
        source_keys=["sec_company_tickers"],
    )[0]

    with pytest.raises(SecDownloadError, match="Too Many Requests"):
        SecDownloader(config, session=session, sleep_func=lambda _: None).download_target(
            target=target,
            object_store=object_store,
            storage_root="global",
            temp_dir=tmp_path / "tmp",
        )


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        chunks: list[bytes],
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.chunks = chunks
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def iter_content(self, chunk_size: int):
        return iter(self.chunks)


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.requests: list[dict] = []

    def get(self, url: str, **kwargs):
        self.requests.append({"url": url, **kwargs})
        return self.responses.pop(0)


class ExplodingSession:
    def get(self, url: str, **kwargs):
        raise AssertionError("HTTP should not be called when cache is present")


class FakeObjectRepository:
    def __init__(self, base_uri: str | Path):
        self.roots = {
            "global": StorageRoot(
                storage_root_id=1,
                root_name="global",
                backend_type="filesystem",
                base_uri=str(base_uri),
            )
        }
        self.objects: dict[UUID, StoredObject] = {}

    def get_storage_root(self, root_name: str) -> StorageRoot | None:
        return self.roots.get(root_name)

    def insert_object(self, **kwargs) -> StoredObject:
        root = self.roots["global"]
        stored = StoredObject(
            object_id=uuid4(),
            run_id=kwargs["run_id"],
            storage_root_id=kwargs["storage_root_id"],
            storage_root_name=root.root_name,
            base_uri=root.base_uri,
            object_key=kwargs["object_key"],
            filename=kwargs["filename"],
            object_scope=kwargs["object_scope"],
            domain=kwargs["domain"],
            logical_name=kwargs["logical_name"],
            content_type=kwargs["content_type"],
            object_kind=kwargs["object_kind"],
            size_bytes=kwargs["size_bytes"],
            checksum_sha256=kwargs["checksum_sha256"],
            expires_at=kwargs["expires_at"],
            deleted_at=None,
            purge_after=None,
            delete_attempts=0,
            last_delete_error=None,
            metadata=kwargs["metadata"],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self.objects[stored.object_id] = stored
        return stored

    def get_object(self, object_id: UUID) -> StoredObject | None:
        return self.objects.get(object_id)

    def mark_deleted(self, object_id: UUID, purge_after) -> None:
        self.objects[object_id] = replace(
            self.objects[object_id],
            deleted_at=datetime.now(UTC),
            purge_after=purge_after,
            updated_at=datetime.now(UTC),
        )

    def record_delete_error(self, object_id: UUID, error_message: str) -> None:
        self.objects[object_id] = replace(
            self.objects[object_id],
            delete_attempts=self.objects[object_id].delete_attempts + 1,
            last_delete_error=error_message,
            updated_at=datetime.now(UTC),
        )
