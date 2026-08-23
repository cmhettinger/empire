"""Effective-date OHLCV and benchmark source-readiness decisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from empire_stonks_tech_indicators.config import BenchmarkConfig
from empire_stonks_tech_indicators.exceptions import (
    TechIndicatorsValidationError,
)
from empire_stonks_tech_indicators.models import TechIndicatorsScope
from empire_stonks_tech_indicators.queries import (
    EligibleListing,
    resolve_spx_benchmark,
    select_eligible_listings,
)


EODDATA_DAILY_JOB_NAME = "stonks_ohlcv_eoddata_daily"
YAHOO_DAILY_JOB_NAME = "stonks_ohlcv_yahoo_daily"

_READINESS_REASONS = (
    "NO_ELIGIBLE_LISTINGS",
    "BENCHMARK_UNAVAILABLE",
    "EODDATA_SOURCE_EVIDENCE_MISSING",
    "YAHOO_SOURCE_EVIDENCE_MISSING",
    "SPX_COVERAGE_INCOMPLETE",
)


@dataclass(frozen=True)
class SourceReadinessDecision:
    """Bounded facts deciding whether one source effective date is ready."""

    effective_date: date
    selected_listing_count: int
    eoddata_listing_count: int
    stooq_listing_count: int
    yahoo_listing_count: int
    effective_date_bar_count: int
    supported_subject_bar_count: int
    benchmark_identity_required: bool
    spx_bar_required: bool
    benchmark_provider_listing_id: UUID | None
    benchmark_bar_present: bool
    eoddata_evidence_required: bool
    yahoo_evidence_required: bool
    eoddata_source_run_id: UUID | None
    yahoo_source_run_id: UUID | None
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.effective_date) is not date:
            raise TypeError("effective_date must be a date.")
        count_fields = (
            "selected_listing_count",
            "eoddata_listing_count",
            "stooq_listing_count",
            "yahoo_listing_count",
            "effective_date_bar_count",
            "supported_subject_bar_count",
        )
        for field_name in count_fields:
            value = getattr(self, field_name)
            if type(value) is not int:
                raise TypeError(f"{field_name} must be an integer.")
            if value < 0:
                raise ValueError(f"{field_name} must be non-negative.")
        if self.selected_listing_count != (
            self.eoddata_listing_count
            + self.stooq_listing_count
            + self.yahoo_listing_count
        ):
            raise ValueError("provider listing counts must equal selected count.")
        if self.effective_date_bar_count > self.selected_listing_count:
            raise ValueError("effective-date bars cannot exceed selected listings.")
        if self.supported_subject_bar_count > self.effective_date_bar_count:
            raise ValueError("supported bars cannot exceed effective-date bars.")
        for field_name in (
            "benchmark_identity_required",
            "spx_bar_required",
            "benchmark_bar_present",
            "eoddata_evidence_required",
            "yahoo_evidence_required",
        ):
            if type(getattr(self, field_name)) is not bool:
                raise TypeError(f"{field_name} must be a boolean.")
        for field_name in (
            "benchmark_provider_listing_id",
            "eoddata_source_run_id",
            "yahoo_source_run_id",
        ):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, UUID):
                raise TypeError(f"{field_name} must be a UUID or None.")
        if self.spx_bar_required and not self.benchmark_identity_required:
            raise ValueError("SPX bar readiness requires benchmark identity.")
        if (
            not self.benchmark_identity_required
            and self.benchmark_provider_listing_id is not None
        ):
            raise ValueError("unrequired benchmark identity must be null.")
        if self.benchmark_bar_present and (
            self.benchmark_provider_listing_id is None
        ):
            raise ValueError("benchmark bar presence requires a benchmark ID.")
        if not self.eoddata_evidence_required and (
            self.eoddata_source_run_id is not None
        ):
            raise ValueError("unrequired EODData evidence must be null.")
        if not self.yahoo_evidence_required and self.yahoo_source_run_id is not None:
            raise ValueError("unrequired Yahoo evidence must be null.")
        if not isinstance(self.reasons, tuple):
            raise TypeError("reasons must be a tuple.")
        expected_reasons = tuple(
            reason for reason in _READINESS_REASONS if reason in self.reasons
        )
        if self.reasons != expected_reasons or len(set(self.reasons)) != len(
            self.reasons
        ):
            raise ValueError("reasons must be unique and contract ordered.")
        self._validate_reason_shape()

    def _validate_reason_shape(self) -> None:
        checks = (
            (
                "NO_ELIGIBLE_LISTINGS",
                self.selected_listing_count == 0,
            ),
            (
                "BENCHMARK_UNAVAILABLE",
                self.benchmark_identity_required
                and self.benchmark_provider_listing_id is None,
            ),
            (
                "EODDATA_SOURCE_EVIDENCE_MISSING",
                self.eoddata_evidence_required
                and self.eoddata_source_run_id is None,
            ),
            (
                "YAHOO_SOURCE_EVIDENCE_MISSING",
                self.yahoo_evidence_required
                and self.yahoo_source_run_id is None,
            ),
            (
                "SPX_COVERAGE_INCOMPLETE",
                self.spx_bar_required
                and self.benchmark_provider_listing_id is not None
                and not self.benchmark_bar_present,
            ),
        )
        for reason, applies in checks:
            if (reason in self.reasons) != applies:
                raise ValueError(f"{reason} does not match readiness facts.")

    @property
    def ready(self) -> bool:
        return not self.reasons

    def to_dict(self) -> dict[str, object]:
        return {
            "effective_date": self.effective_date.isoformat(),
            "ready": self.ready,
            "selected_listing_count": self.selected_listing_count,
            "eoddata_listing_count": self.eoddata_listing_count,
            "stooq_listing_count": self.stooq_listing_count,
            "yahoo_listing_count": self.yahoo_listing_count,
            "effective_date_bar_count": self.effective_date_bar_count,
            "supported_subject_bar_count": self.supported_subject_bar_count,
            "benchmark_identity_required": self.benchmark_identity_required,
            "spx_bar_required": self.spx_bar_required,
            "benchmark_provider_listing_id": _uuid_to_string(
                self.benchmark_provider_listing_id
            ),
            "benchmark_bar_present": self.benchmark_bar_present,
            "eoddata_evidence_required": self.eoddata_evidence_required,
            "yahoo_evidence_required": self.yahoo_evidence_required,
            "eoddata_source_run_id": _uuid_to_string(
                self.eoddata_source_run_id
            ),
            "yahoo_source_run_id": _uuid_to_string(self.yahoo_source_run_id),
            "reasons": list(self.reasons),
        }


def decide_source_readiness(
    *,
    cursor: Any,
    scope: TechIndicatorsScope,
    effective_date: date,
    benchmark_config: BenchmarkConfig,
    resolved_listings: tuple[EligibleListing, ...] | None = None,
) -> SourceReadinessDecision:
    """Decide same-date source readiness from current state and Core evidence.

    A workflow that already resolved its concrete scope may provide that exact
    tuple so readiness and canonical identity use one selection snapshot.
    """

    _validate_cursor(cursor)
    if not isinstance(scope, TechIndicatorsScope):
        raise TypeError("scope must be a TechIndicatorsScope.")
    if type(effective_date) is not date:
        raise TypeError("effective_date must be a date.")
    if not isinstance(benchmark_config, BenchmarkConfig):
        raise TypeError("benchmark_config must be a BenchmarkConfig.")
    if scope.start_date is not None and (
        scope.start_date != effective_date or scope.end_date != effective_date
    ):
        raise ValueError(
            "readiness scope dates must both equal the effective date."
        )

    if resolved_listings is None:
        listings = select_eligible_listings(cursor=cursor, scope=scope)
    else:
        if not isinstance(resolved_listings, tuple) or any(
            not isinstance(item, EligibleListing) for item in resolved_listings
        ):
            raise TypeError(
                "resolved_listings must contain only EligibleListing records."
            )
        listing_ids = tuple(
            item.provider_listing_id for item in resolved_listings
        )
        if len(set(listing_ids)) != len(listing_ids):
            raise ValueError("resolved_listings must contain unique IDs.")
        if any(
            item.provider_code not in {"EODDATA", "STOOQ", "YAHOO"}
            for item in resolved_listings
        ):
            raise ValueError("resolved_listings contains an unsupported provider.")
        listings = resolved_listings
    provider_ids = {
        provider_code: {
            item.provider_listing_id
            for item in listings
            if item.provider_code == provider_code
        }
        for provider_code in ("EODDATA", "STOOQ", "YAHOO")
    }
    if not listings:
        return _decision(
            effective_date=effective_date,
            provider_ids=provider_ids,
            bar_ids=set(),
            benchmark_identity_required=False,
            benchmark_provider_listing_id=None,
            eoddata_source_run_id=None,
            yahoo_source_run_id=None,
        )

    supported_ids = provider_ids["EODDATA"] | provider_ids["STOOQ"]
    benchmark_identity_required = bool(supported_ids or provider_ids["YAHOO"])
    benchmark_provider_listing_id: UUID | None = None
    if benchmark_identity_required:
        try:
            benchmark = resolve_spx_benchmark(
                cursor=cursor,
                config=benchmark_config,
            )
            benchmark_provider_listing_id = benchmark.provider_listing_id
        except TechIndicatorsValidationError:
            pass

    coverage_ids = {item.provider_listing_id for item in listings}
    if benchmark_provider_listing_id is not None:
        coverage_ids.add(benchmark_provider_listing_id)
    bar_ids = _effective_date_bar_ids(
        cursor=cursor,
        provider_listing_ids=coverage_ids,
        effective_date=effective_date,
    )
    supported_subject_bar_count = len(supported_ids & bar_ids)
    spx_bar_required = supported_subject_bar_count > 0
    eoddata_evidence_required = bool(provider_ids["EODDATA"])
    yahoo_evidence_required = bool(provider_ids["YAHOO"]) or spx_bar_required
    evidence = _successful_source_evidence(
        cursor=cursor,
        effective_date=effective_date,
        require_eoddata=eoddata_evidence_required,
        require_yahoo=yahoo_evidence_required,
    )
    return _decision(
        effective_date=effective_date,
        provider_ids=provider_ids,
        bar_ids=bar_ids,
        benchmark_identity_required=benchmark_identity_required,
        benchmark_provider_listing_id=benchmark_provider_listing_id,
        eoddata_source_run_id=evidence.get(EODDATA_DAILY_JOB_NAME),
        yahoo_source_run_id=evidence.get(YAHOO_DAILY_JOB_NAME),
    )


def _decision(
    *,
    effective_date: date,
    provider_ids: dict[str, set[UUID]],
    bar_ids: set[UUID],
    benchmark_identity_required: bool,
    benchmark_provider_listing_id: UUID | None,
    eoddata_source_run_id: UUID | None,
    yahoo_source_run_id: UUID | None,
) -> SourceReadinessDecision:
    selected_ids = set().union(*provider_ids.values())
    supported_ids = provider_ids["EODDATA"] | provider_ids["STOOQ"]
    supported_subject_bar_count = len(supported_ids & bar_ids)
    spx_bar_required = supported_subject_bar_count > 0
    benchmark_bar_present = (
        benchmark_provider_listing_id is not None
        and benchmark_provider_listing_id in bar_ids
    )
    eoddata_evidence_required = bool(provider_ids["EODDATA"])
    yahoo_evidence_required = bool(provider_ids["YAHOO"]) or spx_bar_required
    reason_facts = {
        "NO_ELIGIBLE_LISTINGS": not selected_ids,
        "BENCHMARK_UNAVAILABLE": (
            benchmark_identity_required
            and benchmark_provider_listing_id is None
        ),
        "EODDATA_SOURCE_EVIDENCE_MISSING": (
            eoddata_evidence_required and eoddata_source_run_id is None
        ),
        "YAHOO_SOURCE_EVIDENCE_MISSING": (
            yahoo_evidence_required and yahoo_source_run_id is None
        ),
        "SPX_COVERAGE_INCOMPLETE": (
            spx_bar_required
            and benchmark_provider_listing_id is not None
            and not benchmark_bar_present
        ),
    }
    return SourceReadinessDecision(
        effective_date=effective_date,
        selected_listing_count=len(selected_ids),
        eoddata_listing_count=len(provider_ids["EODDATA"]),
        stooq_listing_count=len(provider_ids["STOOQ"]),
        yahoo_listing_count=len(provider_ids["YAHOO"]),
        effective_date_bar_count=len(selected_ids & bar_ids),
        supported_subject_bar_count=supported_subject_bar_count,
        benchmark_identity_required=benchmark_identity_required,
        spx_bar_required=spx_bar_required,
        benchmark_provider_listing_id=benchmark_provider_listing_id,
        benchmark_bar_present=benchmark_bar_present,
        eoddata_evidence_required=eoddata_evidence_required,
        yahoo_evidence_required=yahoo_evidence_required,
        eoddata_source_run_id=eoddata_source_run_id,
        yahoo_source_run_id=yahoo_source_run_id,
        reasons=tuple(
            reason for reason in _READINESS_REASONS if reason_facts[reason]
        ),
    )


def _effective_date_bar_ids(
    *,
    cursor: Any,
    provider_listing_ids: set[UUID],
    effective_date: date,
) -> set[UUID]:
    cursor.execute(
        """
        SELECT provider_listing_id
        FROM stonks.ohlcv_daily
        WHERE provider_listing_id = ANY(%s::uuid[])
          AND trading_date = %s
        ORDER BY provider_listing_id
        """,
        (sorted(provider_listing_ids), effective_date),
    )
    rows = cursor.fetchall()
    result: set[UUID] = set()
    for row in rows:
        if not isinstance(row, (tuple, list)) or len(row) != 1:
            raise ValueError("Effective-date coverage query returned an invalid row.")
        provider_listing_id = row[0]
        if (
            not isinstance(provider_listing_id, UUID)
            or provider_listing_id not in provider_listing_ids
            or provider_listing_id in result
        ):
            raise ValueError("Effective-date coverage query returned identity drift.")
        result.add(provider_listing_id)
    return result


def _successful_source_evidence(
    *,
    cursor: Any,
    effective_date: date,
    require_eoddata: bool,
    require_yahoo: bool,
) -> dict[str, UUID]:
    required_jobs = tuple(
        job_name
        for job_name, required in (
            (EODDATA_DAILY_JOB_NAME, require_eoddata),
            (YAHOO_DAILY_JOB_NAME, require_yahoo),
        )
        if required
    )
    if not required_jobs:
        return {}
    cursor.execute(
        """
        SELECT DISTINCT ON (run.job_name)
            run.job_name,
            run.run_id
        FROM core.core_run AS run
        WHERE run.domain = 'stonks'
          AND run.effective_date = %s
          AND run.status = 'succeeded'
          AND run.completed_at IS NOT NULL
          AND run.job_name = ANY(%s::text[])
          AND (
              (
                  run.job_name = 'stonks_ohlcv_eoddata_daily'
                  AND run.summary ->> 'provider_code' = 'EODDATA'
                  AND run.summary ->> 'effective_date' = %s
                  AND run.summary ->> 'failure_count' = '0'
                  AND run.summary ->> 'missing_session_count' = '0'
                  AND run.summary ->> 'report_outcome' IN ('PASS', 'WARN')
              )
              OR (
                  run.job_name = 'stonks_ohlcv_yahoo_daily'
                  AND run.summary ->> 'provider_code' = 'YAHOO'
                  AND run.summary ->> 'source_code' = 'yahoo_daily'
                  AND run.summary ->> 'outcome' = 'succeeded'
                  AND run.summary #>> '{scope,effective_date}' = %s
                  AND jsonb_typeof(run.summary #> '{scope,tickers}') = 'array'
                  AND (
                      jsonb_array_length(
                          run.summary #> '{scope,tickers}'
                      ) = 0
                      OR (run.summary #> '{scope,tickers}') ? 'SPX'
                  )
                  AND run.summary ->> 'report_outcome' IN ('PASS', 'WARN')
              )
          )
        ORDER BY
            run.job_name,
            run.completed_at DESC,
            run.run_id
        """,
        (
            effective_date,
            list(required_jobs),
            effective_date.isoformat(),
            effective_date.isoformat(),
        ),
    )
    result: dict[str, UUID] = {}
    for row in cursor.fetchall():
        if not isinstance(row, (tuple, list)) or len(row) != 2:
            raise ValueError("Source-evidence query returned an invalid row.")
        job_name, run_id = row
        if (
            job_name not in required_jobs
            or job_name in result
            or not isinstance(run_id, UUID)
        ):
            raise ValueError("Source-evidence query returned identity drift.")
        result[job_name] = run_id
    return result


def _validate_cursor(cursor: Any) -> None:
    if not callable(getattr(cursor, "execute", None)) or not callable(
        getattr(cursor, "fetchall", None)
    ):
        raise TypeError("cursor must provide execute and fetchall methods.")


def _uuid_to_string(value: UUID | None) -> str | None:
    return None if value is None else str(value)


__all__ = [
    "EODDATA_DAILY_JOB_NAME",
    "SourceReadinessDecision",
    "YAHOO_DAILY_JOB_NAME",
    "decide_source_readiness",
]
