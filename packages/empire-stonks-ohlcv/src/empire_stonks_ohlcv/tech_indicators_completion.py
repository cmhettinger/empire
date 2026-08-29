"""Secret-safe daily source completion signals for downstream coordination."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Final
from uuid import UUID


TECH_INDICATORS_COMPLETION_SCHEMA_VERSION: Final = 1
TECH_INDICATORS_COMPLETION_SIGNAL_TYPE: Final = (
    "stonks_ohlcv_daily_completion"
)
TECH_INDICATORS_BENCHMARK_TICKER: Final = "SPX"

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
        contract = (self.provider_code, self.source_code, self.job_name)
        if contract not in _SOURCE_CONTRACTS:
            raise ValueError("source completion identity is not supported.")
        if type(self.effective_date) is not date:
            raise TypeError("effective_date must be a date.")
        if not isinstance(self.source_run_id, UUID):
            raise TypeError("source_run_id must be a UUID.")
        if self.report_outcome not in {"PASS", "WARN"}:
            raise ValueError("report_outcome must be PASS or WARN.")
        if self.schema_version != TECH_INDICATORS_COMPLETION_SCHEMA_VERSION:
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


__all__ = [
    "TECH_INDICATORS_BENCHMARK_TICKER",
    "TECH_INDICATORS_COMPLETION_SCHEMA_VERSION",
    "TECH_INDICATORS_COMPLETION_SIGNAL_TYPE",
    "TechIndicatorsSourceCompletionSignal",
]
