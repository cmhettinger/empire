"""Run orchestration hooks for stonks securities.

The package skeleton intentionally keeps collection/loading out until the provider
and database contracts are finalized. Airflow should eventually call package
functions from this module rather than owning business logic itself.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StonksSecuritiesRunResult:
    """Summary of one stonks securities run."""

    run_id: str
    stored_object_ids: list[str]
