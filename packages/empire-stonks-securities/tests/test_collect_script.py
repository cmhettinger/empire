from __future__ import annotations

import pytest

from empire_stonks_securities.scripts.collect import parse_args


def test_collect_parse_args_accepts_weather_style_config_and_object_store_options():
    args = parse_args(
        [
            "--config-file",
            "object-store/config/stonks-securities/config.yml",
            "--storage-root",
            "global",
            "--storage-key",
            "stonks/securities",
            "--acquisition-date",
            "2026-06-10",
            "--acquisition-id",
            "512578ba-2f75-42be-89b5-6dfc47ea36c1",
            "--temp-dir",
            "/tmp/empire",
            "--force",
            "source",
            "sec_submissions_zip",
        ]
    )

    assert args.config_file == "object-store/config/stonks-securities/config.yml"
    assert args.config_object_id is None
    assert args.config_logical_name == "stonks-securities-config"
    assert args.storage_root == "global"
    assert args.storage_key == "stonks/securities"
    assert args.acquisition_date == "2026-06-10"
    assert args.acquisition_id == "512578ba-2f75-42be-89b5-6dfc47ea36c1"
    assert args.temp_dir == "/tmp/empire"
    assert args.force is True
    assert args.command == "source"
    assert args.source == ["sec_submissions_zip"]


def test_collect_parse_args_accepts_config_object_id_for_quarterly_mode():
    args = parse_args(
        [
            "--config-object-id",
            "00000000-0000-0000-0000-000000000000",
            "quarterly",
            "--start-year",
            "2024",
            "--end-year",
            "2026",
            "--quarter",
            "1",
            "--quarter",
            "2",
        ]
    )

    assert args.config_object_id == "00000000-0000-0000-0000-000000000000"
    assert args.command == "quarterly"
    assert args.start_year == 2024
    assert args.end_year == 2026
    assert args.quarter == [1, 2]


def test_collect_config_sources_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        parse_args(
            [
                "--config-file",
                "config.yml",
                "--config-object-id",
                "00000000-0000-0000-0000-000000000000",
                "source",
                "sec_submissions_zip",
            ]
        )
