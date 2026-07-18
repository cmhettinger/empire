from __future__ import annotations

import json
import logging
import traceback
from dataclasses import asdict

import pytest

from empire_stonks_ohlcv import EODDataCredentials, OHLCVConfig, OHLCVConfigError
from empire_stonks_ohlcv.config import (
    EODDATA_API_KEY_ENV,
    MAX_RETRIES_ENV,
)


SECRET_API_KEY = "private-eoddata-api-key"
SECRET_TOKEN = "private-provider-token"


def _configured() -> OHLCVConfig:
    return OHLCVConfig(
        eoddata_credentials=EODDataCredentials(
            api_key=SECRET_API_KEY,
        )
    )


def _assert_secret_values_absent(text: str) -> None:
    assert SECRET_API_KEY not in text
    assert SECRET_TOKEN not in text


def test_config_and_credentials_have_redacted_representations() -> None:
    config = _configured()
    credentials = config.require_eoddata_credentials()

    _assert_secret_values_absent(repr(config))
    _assert_secret_values_absent(str(config))
    _assert_secret_values_absent(repr(credentials))
    _assert_secret_values_absent(str(credentials))
    assert "<redacted>" in repr(credentials)


def test_credentials_are_immutable_and_not_implicitly_json_serializable() -> None:
    config = _configured()
    credentials = config.require_eoddata_credentials()

    with pytest.raises(AttributeError, match="immutable"):
        credentials.api_key = "replacement"  # type: ignore[misc]

    implicit_payload = asdict(config)
    _assert_secret_values_absent(repr(implicit_payload))
    with pytest.raises(TypeError):
        json.dumps(implicit_payload)


def test_validation_errors_do_not_echo_credentials_or_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(EODDATA_API_KEY_ENV, SECRET_API_KEY)
    monkeypatch.setenv(MAX_RETRIES_ENV, SECRET_TOKEN)

    with pytest.raises(OHLCVConfigError) as token_error:
        OHLCVConfig.from_env()

    assert token_error.value.__context__ is None
    formatted_error = "".join(
        traceback.format_exception(
            type(token_error.value),
            token_error.value,
            token_error.value.__traceback__,
        )
    )
    _assert_secret_values_absent(formatted_error)


def test_config_logging_does_not_expose_credentials(
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = _configured()
    logger = logging.getLogger("empire_stonks_ohlcv.secret_safety_test")

    with caplog.at_level(logging.INFO, logger=logger.name):
        logger.info("Loaded OHLCV config: %r", config)
        logger.info("Loaded EODData credentials: %s", config.eoddata_credentials)

    _assert_secret_values_absent(caplog.text)


def test_safe_dict_excludes_secrets_from_operational_surfaces() -> None:
    safe_config = _configured().to_safe_dict()
    surfaces = {
        "core_run_parameters": safe_config,
        "object_metadata": {"config": safe_config},
        "report": {"configuration": safe_config},
        "serialized_result": {"configuration": safe_config},
    }

    serialized = json.dumps(surfaces, sort_keys=True)

    _assert_secret_values_absent(serialized)
    assert safe_config["eoddata_configured"] is True
    assert set(safe_config) == {
        "storage_key",
        "raw_retention_days",
        "http_timeout_seconds",
        "max_retries",
        "eoddata_base_url",
        "eoddata_exchanges",
        "eoddata_request_delay_seconds",
        "eoddata_configured",
    }
