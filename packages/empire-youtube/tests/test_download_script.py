from __future__ import annotations

from uuid import uuid4

from empire_youtube.scripts import download as script


def test_parse_args_accepts_plan_object_id_and_video_id():
    object_id = str(uuid4())

    args = script.parse_args(["--plan-object-id", object_id, "--video-id", "abc123"])

    assert args.plan_object_id == object_id
    assert args.video_id == "abc123"
    assert args.plan_source == {"type": "object", "object_id": object_id}


def test_parse_args_accepts_plan_run_id_and_list():
    run_id = str(uuid4())

    args = script.parse_args(["--plan-run-id", run_id, "--list"])

    assert args.plan_run_id == run_id
    assert args.list is True
    assert args.plan_source == {"type": "run", "run_id": run_id}


def test_load_library_plan_from_object_id(monkeypatch):
    calls = []
    monkeypatch.setattr(
        script,
        "load_library_plan_from_object_id",
        lambda object_store, object_id: calls.append((object_store, object_id))
        or {"entries": []},
    )
    args = script.parse_args(["--plan-object-id", "abc", "--list"])
    object_store = object()

    assert script.load_library_plan(args, object_store) == {"entries": []}
    assert calls == [(object_store, "abc")]
