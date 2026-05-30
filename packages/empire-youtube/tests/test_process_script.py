from __future__ import annotations

import json
from uuid import uuid4

from empire_youtube.scripts import process as script


def test_parse_args_requires_one_input_source():
    args = script.parse_args(["--input-file", "/tmp/youtube-scraper.json"])

    assert args.input_file == "/tmp/youtube-scraper.json"
    assert args.input_object_id is None
    assert args.input_run_id is None
    assert args.run_type == "cli"
    assert args.runner == "bin/youtube-process"
    assert args.input_source == {
        "type": "file",
        "path": "/tmp/youtube-scraper.json",
    }


def test_parse_args_accepts_object_id():
    object_id = str(uuid4())

    args = script.parse_args(["--input-object-id", object_id])

    assert args.input_object_id == object_id
    assert args.input_source == {"type": "object", "object_id": object_id}


def test_parse_args_accepts_run_id():
    run_id = str(uuid4())

    args = script.parse_args(["--input-run-id", run_id])

    assert args.input_run_id == run_id
    assert args.input_source == {"type": "run", "run_id": run_id}


def test_load_scrape_payload_from_file(tmp_path):
    input_file = tmp_path / "youtube-scraper.json"
    input_file.write_text('{"source": "youtube", "videos": []}', encoding="utf-8")
    args = script.parse_args(["--input-file", str(input_file)])

    payload = script.load_scrape_payload(args, object_store=object())

    assert payload == {"source": "youtube", "videos": []}


def test_load_scrape_payload_from_object_id(monkeypatch):
    object_id = uuid4()
    args = script.parse_args(["--input-object-id", str(object_id)])

    class FakeObjectStore:
        def get_bytes(self, value):
            assert value == object_id
            return b'{"source": "youtube", "videos": []}'

    payload = script.load_scrape_payload(args, FakeObjectStore())

    assert payload == {"source": "youtube", "videos": []}


def test_load_scrape_payload_from_run_id():
    expected_run_id = uuid4()
    object_id = uuid4()
    args = script.parse_args(["--input-run-id", str(expected_run_id)])

    class Stored:
        def __init__(self):
            self.object_id = object_id

    class FakeObjectStore:
        def find_one(self, *, run_id, object_kind, filename, logical_name=None):
            assert run_id == expected_run_id
            assert object_kind == "normalized_payload"
            assert filename == "youtube-scraper.json"
            assert logical_name is None
            return Stored()

        def get_bytes(self, value):
            assert value == object_id
            return json.dumps({"source": "youtube", "videos": []}).encode("utf-8")

    payload = script.load_scrape_payload(args, FakeObjectStore())

    assert payload == {"source": "youtube", "videos": []}
