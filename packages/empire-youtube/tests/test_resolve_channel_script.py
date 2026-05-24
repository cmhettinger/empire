from __future__ import annotations

from empire_youtube.models import YouTubeChannel
from empire_youtube.scripts import resolve_channel as script


def test_resolve_channel_script_outputs_config_snippet(monkeypatch, capsys):
    monkeypatch.setattr(
        script,
        "resolve_channel",
        lambda value: YouTubeChannel(
            channel_name="Graham Hancock Official Channel",
            channel_id="UCk_foUwmaHeFhmAZMnEHQsw",
            handle="@grahamhancock",
        ),
    )
    monkeypatch.setattr("sys.argv", ["resolve_channel.py", "@grahamhancock"])

    script.main()

    assert capsys.readouterr().out == (
        "channel_name: Graham Hancock Official Channel\n"
        "channel_id: UCk_foUwmaHeFhmAZMnEHQsw\n"
        "handle: '@grahamhancock'\n"
        "enabled: true\n"
    )
