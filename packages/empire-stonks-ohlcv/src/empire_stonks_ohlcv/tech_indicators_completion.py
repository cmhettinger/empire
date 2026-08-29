"""Secret-safe daily source completion signals for downstream coordination."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, Final
from uuid import UUID


TECH_INDICATORS_COMPLETION_SCHEMA_VERSION: Final = 1
TECH_INDICATORS_COMPLETION_SIGNAL_TYPE: Final = (
    "stonks_ohlcv_daily_completion"
)
TECH_INDICATORS_BENCHMARK_TICKER: Final = "SPX"
TECH_INDICATORS_COORDINATOR_DAG_ID: Final = (
    "stonks_tech_indicators_daily_refresh"
)

_SOURCE_CONTRACTS: Final = {
    (
        "EODDATA",
        "eoddata_daily",
        "stonks_ohlcv_eoddata_daily",
    ): "stonks_ohlcv_eoddata_daily_scrape",
    (
        "YAHOO",
        "yahoo_daily",
        "stonks_ohlcv_yahoo_daily",
    ): "stonks_ohlcv_yahoo_daily_scrape",
}
_AIRFLOW_RUN_ID_PATTERN: Final = re.compile(r"^[A-Za-z0-9_.~:+-]+$")


@dataclass(frozen=True)
class TechIndicatorsSourceCompletionSignal:
    """One qualifying OHLCV completion that may wake the coordinator.

    The signal is an orchestration hint, not source-readiness proof. The
    technical-indicator package must recheck Core and OHLCV/SPX state for the
    exact effective date before calculation or publication.
    """

    provider_code: str
    source_code: str
    job_name: str
    effective_date: date
    source_run_id: UUID
    report_outcome: str
    schema_version: int = TECH_INDICATORS_COMPLETION_SCHEMA_VERSION
    signal_type: str = TECH_INDICATORS_COMPLETION_SIGNAL_TYPE

    def __post_init__(self) -> None:
        for field_name in (
            "provider_code",
            "source_code",
            "job_name",
            "report_outcome",
            "signal_type",
        ):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be a string.")
        contract = (self.provider_code, self.source_code, self.job_name)
        if contract not in _SOURCE_CONTRACTS:
            raise ValueError("source completion identity is not supported.")
        if type(self.effective_date) is not date:
            raise TypeError("effective_date must be a date.")
        if not isinstance(self.source_run_id, UUID):
            raise TypeError("source_run_id must be a UUID.")
        if self.report_outcome not in {"PASS", "WARN"}:
            raise ValueError("report_outcome must be PASS or WARN.")
        if (
            type(self.schema_version) is not int
            or self.schema_version
            != TECH_INDICATORS_COMPLETION_SCHEMA_VERSION
        ):
            raise ValueError("schema_version is not supported.")
        if self.signal_type != TECH_INDICATORS_COMPLETION_SIGNAL_TYPE:
            raise ValueError("signal_type is not supported.")

    @property
    def source_dag_id(self) -> str:
        """Return the exact Airflow producer DAG for this source contract."""

        return _SOURCE_CONTRACTS[
            (self.provider_code, self.source_code, self.job_name)
        ]

    @property
    def trigger_run_id(self) -> str:
        """Return a deterministic coordinator run ID for retry coalescence."""

        return (
            f"source__{self.provider_code.lower()}__{self.source_run_id}"
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the exact small source output shared through runtime XCom."""

        return {
            "schema_version": self.schema_version,
            "signal_type": self.signal_type,
            "provider_code": self.provider_code,
            "source_code": self.source_code,
            "job_name": self.job_name,
            "effective_date": self.effective_date.isoformat(),
            "source_run_id": str(self.source_run_id),
            "report_outcome": self.report_outcome,
            "trigger_run_id": self.trigger_run_id,
        }

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, object],
    ) -> TechIndicatorsSourceCompletionSignal:
        """Rebuild one signal only from its exact public JSON contract."""

        expected_keys = {
            "schema_version",
            "signal_type",
            "provider_code",
            "source_code",
            "job_name",
            "effective_date",
            "source_run_id",
            "report_outcome",
            "trigger_run_id",
        }
        if not isinstance(payload, Mapping) or set(payload) != expected_keys:
            raise ValueError("source completion signal shape is invalid.")
        effective_date = _parse_date(payload["effective_date"])
        source_run_id = _parse_uuid(payload["source_run_id"])
        signal = cls(
            provider_code=payload["provider_code"],
            source_code=payload["source_code"],
            job_name=payload["job_name"],
            effective_date=effective_date,
            source_run_id=source_run_id,
            report_outcome=payload["report_outcome"],
            schema_version=payload["schema_version"],
            signal_type=payload["signal_type"],
        )
        if payload["trigger_run_id"] != signal.trigger_run_id:
            raise ValueError("source completion trigger_run_id is invalid.")
        return signal

    def to_trigger_conf(self, *, source_dag_run_id: str) -> dict[str, Any]:
        """Build the exact A11.1 coordinator trigger configuration."""

        _validate_airflow_run_id(source_dag_run_id)
        return {
            "coordination_schema_version": self.schema_version,
            "effective_date": self.effective_date.isoformat(),
            "source_provider_code": self.provider_code,
            "source_code": self.source_code,
            "source_job_name": self.job_name,
            "source_core_run_id": str(self.source_run_id),
            "source_dag_id": self.source_dag_id,
            "source_dag_run_id": source_dag_run_id,
        }


def _validate_airflow_run_id(value: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 250
        or _AIRFLOW_RUN_ID_PATTERN.fullmatch(value) is None
    ):
        raise ValueError("source_dag_run_id is not a safe Airflow run ID.")


def build_tech_indicators_dispatch(
    source_result: Mapping[str, object],
    *,
    source_dag_id: str,
    source_dag_run_id: str,
) -> dict[str, object] | None:
    """Build one strict coordinator dispatch from a compact source result."""

    if not isinstance(source_result, Mapping):
        raise TypeError("source_result must be a mapping.")
    signal_payload = source_result.get("tech_indicators_completion_signal")
    if signal_payload is None:
        return None
    if not isinstance(signal_payload, Mapping):
        raise ValueError("source completion signal must be a JSON object.")
    signal = TechIndicatorsSourceCompletionSignal.from_dict(signal_payload)
    if signal.source_dag_id != source_dag_id:
        raise ValueError("source completion DAG identity does not match.")
    return {
        "trigger_run_id": signal.trigger_run_id,
        "conf": signal.to_trigger_conf(
            source_dag_run_id=source_dag_run_id,
        ),
    }


def _parse_date(value: object) -> date:
    if not isinstance(value, str):
        raise ValueError("source completion effective_date is invalid.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError(
            "source completion effective_date is invalid."
        ) from None
    if parsed.isoformat() != value:
        raise ValueError("source completion effective_date is invalid.")
    return parsed


def _parse_uuid(value: object) -> UUID:
    if not isinstance(value, str):
        raise ValueError("source completion source_run_id is invalid.")
    try:
        parsed = UUID(value)
    except ValueError:
        raise ValueError(
            "source completion source_run_id is invalid."
        ) from None
    if str(parsed) != value:
        raise ValueError("source completion source_run_id is invalid.")
    return parsed


__all__ = [
    "TECH_INDICATORS_BENCHMARK_TICKER",
    "TECH_INDICATORS_COMPLETION_SCHEMA_VERSION",
    "TECH_INDICATORS_COMPLETION_SIGNAL_TYPE",
    "TECH_INDICATORS_COORDINATOR_DAG_ID",
    "TechIndicatorsSourceCompletionSignal",
    "build_tech_indicators_dispatch",
]
