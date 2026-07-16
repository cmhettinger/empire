from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from empire_stonks_ohlcv import (
    EODDATA_DAILY_SOURCE,
    EODDATA_SYMBOL_LIST_SOURCE,
    STOOQ_DAILY_SOURCE,
    STOOQ_HISTORY_SOURCE,
    YAHOO_DAILY_SOURCE,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures"
REPOSITORY_ROOT = Path(__file__).parents[3]
MANIFEST_SCHEMA_PATH = FIXTURE_ROOT / "manifest.schema.json"
MAX_PAYLOAD_BYTES = 65_536
PRODUCTION_SOURCES = {
    "EODDATA": {
        EODDATA_SYMBOL_LIST_SOURCE.source_code: (
            EODDATA_SYMBOL_LIST_SOURCE.parser_version
        ),
        EODDATA_DAILY_SOURCE.source_code: EODDATA_DAILY_SOURCE.parser_version,
    },
    "STOOQ": {
        STOOQ_DAILY_SOURCE.source_code: STOOQ_DAILY_SOURCE.parser_version,
        STOOQ_HISTORY_SOURCE.source_code: STOOQ_HISTORY_SOURCE.parser_version,
    },
    "YAHOO": {
        YAHOO_DAILY_SOURCE.source_code: YAHOO_DAILY_SOURCE.parser_version,
    },
}
REQUIRED_FIELDS = {
    "schema_version",
    "provider_code",
    "source_code",
    "parser_version",
    "format_reference",
    "provenance",
    "payload_file",
    "payload_size_bytes",
    "payload_sha256",
    "sanitization",
    "cases",
}
FORBIDDEN_TEXT_PATTERNS = (
    re.compile(r"(?i)authorization\s*[:=]"),
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]"),
    re.compile(r"(?i)cookie\s*[:=]"),
    re.compile(r"https?://[^\s]+\?[^\s]+"),
)


def _manifest_paths() -> tuple[Path, ...]:
    return tuple(
        path
        for path in FIXTURE_ROOT.rglob("*.fixture.json")
        if path != MANIFEST_SCHEMA_PATH
    )


def _load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"{path}: manifest must be a JSON object")
    return value


def _validate_manifest(path: Path) -> Path:
    manifest = _load_manifest(path)
    assert set(manifest) == REQUIRED_FIELDS, f"{path}: manifest fields drifted"
    assert manifest["schema_version"] == 1

    provider_code = manifest["provider_code"]
    source_code = manifest["source_code"]
    assert provider_code in PRODUCTION_SOURCES
    assert source_code in PRODUCTION_SOURCES[provider_code]
    assert manifest["parser_version"] == PRODUCTION_SOURCES[provider_code][
        source_code
    ]
    assert path.parent.name == source_code
    assert path.parent.parent.name == provider_code.lower()

    assert isinstance(manifest["format_reference"], str)
    document_path, _anchor = manifest["format_reference"].split("#", maxsplit=1)
    assert document_path.startswith("docs/")
    assert (REPOSITORY_ROOT / document_path).is_file()
    assert manifest["provenance"] in {
        "sanitized_excerpt",
        "constructed_from_documented_format",
    }
    assert isinstance(manifest["sanitization"], list)
    assert manifest["sanitization"]
    assert all(
        isinstance(item, str) and item.strip()
        for item in manifest["sanitization"]
    )
    assert isinstance(manifest["cases"], list)
    assert manifest["cases"]
    assert all(isinstance(item, str) and item.strip() for item in manifest["cases"])

    payload_name = manifest["payload_file"]
    assert isinstance(payload_name, str)
    assert Path(payload_name).name == payload_name
    assert path.name == f"{payload_name}.fixture.json"
    payload_path = path.parent / payload_name
    payload = payload_path.read_bytes()
    assert 0 < len(payload) <= MAX_PAYLOAD_BYTES
    assert manifest["payload_size_bytes"] == len(payload)
    assert manifest["payload_sha256"] == hashlib.sha256(payload).hexdigest()
    for pattern in FORBIDDEN_TEXT_PATTERNS:
        assert not pattern.search(payload.decode("utf-8", errors="ignore"))
    return payload_path


def test_fixture_manifest_schema_matches_enforced_policy() -> None:
    schema = json.loads(MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8"))

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == REQUIRED_FIELDS
    assert schema["properties"]["payload_size_bytes"]["maximum"] == (
        MAX_PAYLOAD_BYTES
    )
    assert set(schema["properties"]["provider_code"]["enum"]) == set(
        PRODUCTION_SOURCES
    )
    assert set(schema["properties"]["source_code"]["enum"]) == {
        source_code
        for sources in PRODUCTION_SOURCES.values()
        for source_code in sources
    }


def test_committed_provider_fixtures_obey_policy() -> None:
    for manifest_path in _manifest_paths():
        _validate_manifest(manifest_path)


def test_every_committed_provider_payload_has_one_manifest() -> None:
    manifest_payloads = {_validate_manifest(path) for path in _manifest_paths()}
    policy_files = {
        FIXTURE_ROOT / "README.md",
        MANIFEST_SCHEMA_PATH,
    }
    committed_payloads = {
        path
        for path in FIXTURE_ROOT.rglob("*")
        if path.is_file()
        and path not in policy_files
        and not path.name.endswith(".fixture.json")
    }

    assert committed_payloads == manifest_payloads
