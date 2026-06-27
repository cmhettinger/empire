from __future__ import annotations

from pathlib import Path

from empire_youtube.scripts import stage as script


def test_parse_args_accepts_url_and_temp_dir():
    args = script.parse_args(
        ["https://www.youtube.com/watch?v=abc123", "--temp-dir", "/tmp/empire"]
    )

    assert args.url == "https://www.youtube.com/watch?v=abc123"
    assert args.temp_dir == "/tmp/empire"


def test_main_prints_stage_result(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(
        script,
        "stage_youtube_video",
        lambda url, temp_dir: FakeResult(
            video_id="abc123",
            title="Example",
            output_dir=tmp_path / "abc123",
            files=["empire.json", "movie.mp4", "movie.nfo"],
        ),
    )

    script.main(["https://www.youtube.com/watch?v=abc123", "--temp-dir", str(tmp_path)])

    output = capsys.readouterr().out
    assert "video_id: abc123" in output
    assert f"output_dir: {tmp_path / 'abc123'}" in output
    assert "  movie.mp4" in output


class FakeResult:
    def __init__(self, *, video_id: str, title: str, output_dir: Path, files: list[str]):
        self.video_id = video_id
        self.title = title
        self.output_dir = output_dir
        self.files = files
