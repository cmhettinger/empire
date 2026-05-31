from __future__ import annotations

from empire_weather.scripts.put_config import DEFAULT_LOCAL_CONFIG_FILE, parse_args


def test_put_config_defaults_to_seed_config_file():
    args = parse_args([])

    assert args.config_file is None


def test_put_config_default_path_constant_points_to_seed_config():
    assert DEFAULT_LOCAL_CONFIG_FILE == "deploy/config/weather/config.yml"
