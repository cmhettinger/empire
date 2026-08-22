"""Immutable schema-V1 technical-indicator report facts and JSON rendering."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, fields, replace
from datetime import UTC, date, datetime
from enum import Enum
from math import isclose, isfinite
from types import MappingProxyType
from typing import Any
from uuid import UUID

from empire_stonks_tech_indicators.config import DEFAULT_CALCULATION_VERSION
from empire_stonks_tech_indicators.publication import (
    TECH_INDICATORS_WRITER_LOCK_KEY,
    TECH_INDICATORS_WRITER_LOCK_SEED,
)
from empire_stonks_tech_indicators.reporting_queries import (
    REPORT_FEATURE_FIELDS,
    ReportBenchmarkCoverage,
    ReportDatabaseSummary,
    ReportDateCoverage,
    ReportDimensionCoverage,
    ReportFeatureCoverage,
    ReportVersionCoverage,
)


REPORT_SCHEMA_VERSION = 1
REPORT_MAXIMUM_BYTES = 2 * 1024 * 1024
REPORT_DIAGNOSTIC_SAMPLE_LIMIT = 100
BENCHMARK_CONTRACT_VERSION = "TECH_INDICATORS_SPX_V1"
DAILY_REPORT_ID = "stonks.tech-indicators.daily"
BACKFILL_REPORT_ID = "stonks.tech-indicators.backfill"
DAILY_CORE_JOB_NAME = "stonks_tech_indicators_daily"
BACKFILL_CORE_JOB_NAME = "stonks_tech_indicators_backfill"

REPORT_PHASE_ORDER = (
    "LOCK",
    "SCOPE_RESOLUTION",
    "SOURCE_READINESS",
    "PLANNING",
    "SOURCE_READ",
    "CALCULATION",
    "VALIDATION",
    "PERSISTENCE",
    "PUBLICATION_PREPARATION",
    "SUMMARY_QUERIES",
    "REPORT_FACTS",
)

SOURCE_READINESS_REASON_CODES = frozenset(
    {
        "NO_ELIGIBLE_LISTINGS",
        "BENCHMARK_UNAVAILABLE",
        "EODDATA_SOURCE_EVIDENCE_MISSING",
        "YAHOO_SOURCE_EVIDENCE_MISSING",
        "SPX_COVERAGE_INCOMPLETE",
    }
)
PUBLICATION_READINESS_REASON_CODES = frozenset(
    {
        "NO_ACTIVE_PUBLICATION",
        "SCOPE_MISMATCH",
        "COVERAGE_INCOMPLETE",
        "VERSION_MISMATCH",
        "SOURCE_DRIFT",
        "PUBLICATION_NOT_READY",
        "BENCHMARK_UNAVAILABLE",
        "BENCHMARK_MISMATCH",
        "SPX_COVERAGE_INCOMPLETE",
    }
)

REPORT_MESSAGE_CATALOG = MappingProxyType({
    "BACKFILL_INCOMPLETE": "Backfill work remains safely resumable and unpublished.",
    "BENCHMARK_COVERAGE_WARNING": "Benchmark coverage requires operator review.",
    "CALCULATION_FAILED": "Technical-indicator calculation failed validation.",
    "CANCELLED": "The workflow was cancelled before publication.",
    "CORE_LIFECYCLE_FAILED": "The Core run lifecycle did not complete safely.",
    "LOCK_LOST": "The package-owned writer lock was lost during the workflow.",
    "PERSISTENCE_FAILED": "Technical-indicator persistence failed safely.",
    "PUBLICATION_NOT_READY": "The candidate publication is not ready.",
    "REPORT_VALIDATION_FAILED": "Report facts failed schema validation.",
    "SOURCE_COVERAGE_WARNING": "Source coverage requires operator review.",
    "SOURCE_NOT_READY": "Required source evidence is not ready.",
    "UNEXPECTED_NULL": "A required post-warm-up feature value is null.",
    "VALIDATION_FAILED": "Technical-indicator output validation failed.",
    "WRITE_RECONCILIATION_FAILED": "Write outcome counts did not reconcile.",
})
REPORT_DIAGNOSTIC_MESSAGE_CATALOG = MappingProxyType({
    **REPORT_MESSAGE_CATALOG,
    "BENCHMARK_MISMATCH": "Published benchmark identity is incompatible.",
    "BENCHMARK_UNAVAILABLE": "The reviewed SPX benchmark is unavailable.",
    "COVERAGE_INCOMPLETE": "Published feature coverage is incomplete.",
    "EODDATA_SOURCE_EVIDENCE_MISSING": "EODData source evidence is missing.",
    "NO_ACTIVE_PUBLICATION": "No compatible active publication exists.",
    "NO_ELIGIBLE_LISTINGS": "The resolved scope has no eligible listings.",
    "SCOPE_MISMATCH": "Published membership does not match the resolved scope.",
    "SOURCE_DRIFT": "Published rows do not match current source state.",
    "SPX_COVERAGE_INCOMPLETE": "Exact-date SPX coverage is incomplete.",
    "VERSION_MISMATCH": "Published calculation versions are incompatible.",
    "YAHOO_SOURCE_EVIDENCE_MISSING": "Yahoo source evidence is missing.",
})

NATIVE_VALUE_NOTE_MESSAGES = MappingProxyType({
    "EODDATA_OHLC_ADJUSTMENT_UNSPECIFIED": (
        "EODData does not specify the adjustment basis of persisted OHLC values."
    ),
    "EODDATA_VOLUME_BASIS_UNSPECIFIED": (
        "EODData does not specify the basis of persisted volume values."
    ),
    "EODDATA_LISTING_CURRENCY_NOT_BAR_CURRENCY": (
        "EODData listing currency metadata is not verified bar currency."
    ),
    "STOOQ_OHLC_ADJUSTMENT_UNSPECIFIED": (
        "Stooq does not specify the adjustment basis of persisted OHLC values."
    ),
    "STOOQ_VOLUME_BASIS_UNSPECIFIED_FRACTIONAL_ALLOWED": (
        "Stooq volume basis is unspecified and fractional values are retained."
    ),
    "STOOQ_CURRENCY_UNSPECIFIED": "Stooq bar currency is unspecified.",
    "STOOQ_CORPORATE_ACTIONS_UNSPECIFIED": (
        "Stooq corporate-action treatment is unspecified."
    ),
    "YAHOO_NATIVE_UNADJUSTED_OHLC": "Yahoo OHLC values are native and unadjusted.",
    "YAHOO_ADJUSTED_CLOSE_NOT_PERSISTED": (
        "Yahoo adjusted close is not persisted in the source relation."
    ),
    "YAHOO_VOLUME_NULLABLE": "Yahoo source volume may be null.",
    "CORPORATE_ACTIONS_NOT_NORMALIZED": (
        "Technical indicators do not normalize corporate actions."
    ),
    "NOMINAL_DOLLAR_VOLUME_NOT_USD": (
        "Nominal dollar-volume fields are not asserted to be US dollars."
    ),
    "CROSS_PROVIDER_VALUES_NOT_NORMALIZED": (
        "Values are not normalized for comparison across providers."
    ),
})
NATIVE_VALUE_NOTE_ORDER = tuple(NATIVE_VALUE_NOTE_MESSAGES)

_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_FIELD_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_SEMVER_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
_SAMPLE_ID_PATTERN = re.compile(r"^S[0-9]{3}$")
_UNSAFE_TEXT = re.compile(
    r"(?i)(password\s*=|authorization:|bearer\s+|cookie:|traceback \(|"
    r"postgres(?:ql)?://|https?://[^\s]*@|dbname\s*=|hostaddr\s*=)"
)


class WorkflowKind(str, Enum):
    DAILY = "DAILY"
    BACKFILL = "BACKFILL"


class ReportOutcome(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    NO_OP = "NO_OP"
    PARTIAL = "PARTIAL"
    FAIL = "FAIL"


class LockOutcome(str, Enum):
    ACQUIRED = "ACQUIRED"
    LOST = "LOST"


class SourceReadinessStatus(str, Enum):
    READY = "READY"
    NOT_READY = "NOT_READY"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class PublicationMethod(str, Enum):
    IN_PLACE = "IN_PLACE"
    STAGED = "STAGED"
    NONE = "NONE"


class PublicationReportPhase(str, Enum):
    PREPARED_CANDIDATE = "PREPARED_CANDIDATE"
    EXISTING_PUBLICATION = "EXISTING_PUBLICATION"
    UNPUBLISHED_PARTIAL = "UNPUBLISHED_PARTIAL"
    DRY_RUN = "DRY_RUN"
    FAILED = "FAILED"


class PublicationReadiness(str, Enum):
    READY = "READY"
    NOT_READY = "NOT_READY"


def _require_enum(name: str, value: object, enum_type: type[Enum]) -> None:
    if not isinstance(value, enum_type):
        raise TypeError(f"{name} must be a {enum_type.__name__}.")


def _nonnegative_int(name: str, value: object) -> None:
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer.")
    if value < 0:
        raise ValueError(f"{name} must be non-negative.")


def _positive_int(name: str, value: object) -> None:
    _nonnegative_int(name, value)
    if value == 0:
        raise ValueError(f"{name} must be positive.")


def _finite_number(name: str, value: object) -> None:
    if type(value) not in (int, float) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number.")
    if value < 0:
        raise ValueError(f"{name} must be non-negative.")


def _safe_text(name: str, value: object, *, maximum: int = 500) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string.")
    if not value or value != value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must be non-empty, trimmed, and bounded.")
    if any(ord(character) < 32 for character in value) or _UNSAFE_TEXT.search(value):
        raise ValueError(f"{name} contains unsafe report text.")


def _code(name: str, value: object) -> None:
    _safe_text(name, value, maximum=64)
    if not _CODE_PATTERN.fullmatch(value):
        raise ValueError(f"{name} must be an uppercase code.")


def _field_name(name: str, value: object) -> None:
    _safe_text(name, value, maximum=64)
    if not _FIELD_PATTERN.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase field name.")


def _utc_datetime(name: str, value: object) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise TypeError(f"{name} must be a timezone-aware datetime.")
    if value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{name} must use UTC.")


def _uuid(name: str, value: object, *, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    if not isinstance(value, UUID):
        raise TypeError(f"{name} must be a UUID{' or None' if nullable else ''}.")


def _date(name: str, value: object, *, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    if type(value) is not date:
        raise TypeError(f"{name} must be a date{' or None' if nullable else ''}.")


def _bool(name: str, value: object) -> None:
    if type(value) is not bool:
        raise TypeError(f"{name} must be a boolean.")


def _typed_tuple(name: str, value: object, item_type: type[Any]) -> None:
    if not isinstance(value, tuple) or any(
        not isinstance(item, item_type) for item in value
    ):
        raise TypeError(f"{name} must be a tuple of {item_type.__name__} values.")


def _sorted_unique_text(name: str, value: object) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"{name} must be a tuple.")
    for item in value:
        _safe_text(name, item, maximum=64)
    if value != tuple(sorted(set(value))):
        raise ValueError(f"{name} must be sorted and unique.")


def _reason_counts(
    name: str,
    value: object,
    allowed: frozenset[str],
) -> None:
    _typed_tuple(name, value, ReportReasonCount)
    codes = tuple(item.code for item in value)
    if codes != tuple(sorted(set(codes))) or any(code not in allowed for code in codes):
        raise ValueError(f"{name} contains invalid or unsorted reason codes.")


@dataclass(frozen=True)
class ReportReasonCount:
    code: str
    count: int

    def __post_init__(self) -> None:
        _code("code", self.code)
        _positive_int("count", self.count)


@dataclass(frozen=True)
class ReportIdentity:
    run_id: UUID
    core_subject_key: str
    effective_date: date
    publication_id: UUID | None = None
    existing_readiness_token: str | None = None
    core_domain: str = "stonks"
    core_job_name: str = DAILY_CORE_JOB_NAME
    json_object_id: None = None
    pdf_object_id: None = None

    def __post_init__(self) -> None:
        _uuid("run_id", self.run_id)
        _safe_text("core_subject_key", self.core_subject_key, maximum=200)
        _date("effective_date", self.effective_date)
        _uuid("publication_id", self.publication_id, nullable=True)
        if self.existing_readiness_token is not None and not _HASH_PATTERN.fullmatch(
            self.existing_readiness_token
        ):
            raise ValueError("existing_readiness_token must be lowercase SHA-256.")
        if self.core_domain != "stonks":
            raise ValueError("core_domain must be stonks.")
        if self.core_job_name not in {DAILY_CORE_JOB_NAME, BACKFILL_CORE_JOB_NAME}:
            raise ValueError("core_job_name is not a frozen report job.")
        if self.json_object_id is not None or self.pdf_object_id is not None:
            raise ValueError("report object IDs must be null inside report JSON.")


@dataclass(frozen=True)
class ReportScope:
    scope_hash: str
    effective_date: date | None
    start_date: date | None
    end_date: date | None
    provider_codes: tuple[str, ...] = ()
    markets: tuple[str, ...] = ()
    instrument_type_codes: tuple[str, ...] = ()
    requested_listing_count: int = 0
    resolved_listing_count: int = 0
    include_inactive: bool = False
    dry_run: bool = False
    force: bool = False
    rebuild: bool = False
    scope_schema_version: int = 1

    def __post_init__(self) -> None:
        if not _HASH_PATTERN.fullmatch(self.scope_hash):
            raise ValueError("scope_hash must be lowercase SHA-256.")
        for name in ("effective_date", "start_date", "end_date"):
            _date(name, getattr(self, name), nullable=True)
        if (self.start_date is None) != (self.end_date is None):
            raise ValueError("scope range dates must be populated together.")
        if self.start_date is not None and self.start_date > self.end_date:
            raise ValueError("scope start_date must not exceed end_date.")
        for name in ("provider_codes", "markets", "instrument_type_codes"):
            _sorted_unique_text(name, getattr(self, name))
        if any(value != value.upper() for value in self.provider_codes):
            raise ValueError("provider_codes must be uppercase.")
        for name in ("requested_listing_count", "resolved_listing_count"):
            _nonnegative_int(name, getattr(self, name))
        for name in ("include_inactive", "dry_run", "force", "rebuild"):
            _bool(name, getattr(self, name))
        if self.scope_schema_version != 1:
            raise ValueError("scope_schema_version must be 1.")


@dataclass(frozen=True)
class ReportVersions:
    package_version: str
    python_version: str
    postgresql_version: str | None
    calculation_version: str = DEFAULT_CALCULATION_VERSION
    benchmark_contract_version: str = BENCHMARK_CONTRACT_VERSION
    numpy_version: str = "2.4.6"
    talib_python_version: str = "0.7.1"
    talib_c_version: str = "0.7.1"

    def __post_init__(self) -> None:
        if self.calculation_version != DEFAULT_CALCULATION_VERSION:
            raise ValueError("calculation_version is not the V1 profile.")
        if self.benchmark_contract_version != BENCHMARK_CONTRACT_VERSION:
            raise ValueError("benchmark_contract_version is not V1.")
        if not _SEMVER_PATTERN.fullmatch(self.package_version):
            raise ValueError("package_version must be semantic-version text.")
        _safe_text("python_version", self.python_version, maximum=100)
        if self.postgresql_version is not None:
            _safe_text("postgresql_version", self.postgresql_version)
        if (self.numpy_version, self.talib_python_version, self.talib_c_version) != (
            "2.4.6",
            "0.7.1",
            "0.7.1",
        ):
            raise ValueError("calculation dependency versions must be pinned V1.")


@dataclass(frozen=True)
class ReportLock:
    outcome: LockOutcome
    heartbeat_count: int
    heartbeat_failure_count: int
    name: str = TECH_INDICATORS_WRITER_LOCK_SEED
    key: int = TECH_INDICATORS_WRITER_LOCK_KEY
    held_through_report: bool = True

    def __post_init__(self) -> None:
        _require_enum("outcome", self.outcome, LockOutcome)
        _nonnegative_int("heartbeat_count", self.heartbeat_count)
        _nonnegative_int("heartbeat_failure_count", self.heartbeat_failure_count)
        if self.heartbeat_failure_count not in (0, 1):
            raise ValueError("heartbeat_failure_count must be zero or one.")
        if self.name != TECH_INDICATORS_WRITER_LOCK_SEED:
            raise ValueError("lock name does not match the frozen seed.")
        if self.key != TECH_INDICATORS_WRITER_LOCK_KEY:
            raise ValueError("lock key does not match the frozen key.")
        if self.held_through_report is not True:
            raise ValueError("held_through_report must be true.")
        if self.outcome is LockOutcome.LOST and self.heartbeat_failure_count != 1:
            raise ValueError("LOST requires one heartbeat failure.")
        if self.outcome is LockOutcome.ACQUIRED and self.heartbeat_failure_count:
            raise ValueError("ACQUIRED cannot retain a heartbeat failure.")


@dataclass(frozen=True)
class ReportProviderEvidence:
    provider_code: str
    evidence_kind: str
    required: bool
    ready: bool
    successful_run_count: int
    latest_successful_run_id: UUID | None
    source_listing_count: int
    source_row_count: int
    effective_date_row_count: int

    def __post_init__(self) -> None:
        if self.provider_code not in {"EODDATA", "STOOQ", "YAHOO"}:
            raise ValueError("provider_code is not in the readiness vocabulary.")
        expected_kind = (
            "COVERAGE_ONLY" if self.provider_code == "STOOQ" else "CORE_AND_COVERAGE"
        )
        if self.evidence_kind != expected_kind:
            raise ValueError("evidence_kind does not match provider convention.")
        _bool("required", self.required)
        _bool("ready", self.ready)
        for name in (
            "successful_run_count",
            "source_listing_count",
            "source_row_count",
            "effective_date_row_count",
        ):
            _nonnegative_int(name, getattr(self, name))
        _uuid(
            "latest_successful_run_id",
            self.latest_successful_run_id,
            nullable=True,
        )
        if self.latest_successful_run_id is not None and not self.successful_run_count:
            raise ValueError("source run ID requires a successful run count.")
        if self.effective_date_row_count > self.source_row_count:
            raise ValueError("effective-date source rows exceed source rows.")
        if self.required and self.ready and not self.source_listing_count:
            raise ValueError("ready required evidence must cover a listing.")


@dataclass(frozen=True)
class ReportSourceBenchmark:
    required: bool
    ready: bool
    provider_listing_id: UUID | None
    effective_date_bar_present: bool
    provider_code: str = "YAHOO"
    market: str = "XIDX"
    ticker: str = "SPX"

    def __post_init__(self) -> None:
        _bool("required", self.required)
        _bool("ready", self.ready)
        _uuid(
            "provider_listing_id",
            self.provider_listing_id,
            nullable=True,
        )
        _bool("effective_date_bar_present", self.effective_date_bar_present)
        if (self.provider_code, self.market, self.ticker) != (
            "YAHOO",
            "XIDX",
            "SPX",
        ):
            raise ValueError("source benchmark identity is not the reviewed SPX.")
        if self.ready and self.required and (
            self.provider_listing_id is None or not self.effective_date_bar_present
        ):
            raise ValueError("ready required benchmark evidence is incomplete.")
        if not self.required and (
            self.ready
            or self.provider_listing_id is not None
            or self.effective_date_bar_present
        ):
            raise ValueError("unrequired benchmark evidence must be empty.")


@dataclass(frozen=True)
class ReportSourceReadiness:
    decision: SourceReadinessStatus
    effective_date: date | None
    reason_counts: tuple[ReportReasonCount, ...]
    provider_evidence: tuple[ReportProviderEvidence, ...]
    benchmark: ReportSourceBenchmark

    def __post_init__(self) -> None:
        _require_enum("decision", self.decision, SourceReadinessStatus)
        _date("effective_date", self.effective_date, nullable=True)
        _reason_counts(
            "reason_counts",
            self.reason_counts,
            SOURCE_READINESS_REASON_CODES,
        )
        _typed_tuple(
            "provider_evidence",
            self.provider_evidence,
            ReportProviderEvidence,
        )
        codes = tuple(item.provider_code for item in self.provider_evidence)
        if codes != tuple(sorted(set(codes))):
            raise ValueError("provider_evidence must be sorted and unique.")
        if not isinstance(self.benchmark, ReportSourceBenchmark):
            raise TypeError("benchmark must be ReportSourceBenchmark.")
        if self.decision is SourceReadinessStatus.READY:
            if self.reason_counts or any(
                item.required and not item.ready for item in self.provider_evidence
            ) or (self.benchmark.required and not self.benchmark.ready):
                raise ValueError("READY source evidence is incomplete.")
        elif self.decision is SourceReadinessStatus.NOT_READY:
            if not self.reason_counts:
                raise ValueError("NOT_READY requires bounded reasons.")
        else:
            if (
                self.effective_date is not None
                or self.reason_counts
                or self.provider_evidence
                or self.benchmark.required
                or self.benchmark.ready
                or self.benchmark.provider_listing_id is not None
                or self.benchmark.effective_date_bar_present
            ):
                raise ValueError("NOT_APPLICABLE source readiness has invalid facts.")


@dataclass(frozen=True)
class ReportCursor:
    provider_listing_id: UUID
    trading_date: date | None
    batch_number: int

    def __post_init__(self) -> None:
        _uuid("provider_listing_id", self.provider_listing_id)
        _date("trading_date", self.trading_date, nullable=True)
        _positive_int("batch_number", self.batch_number)


@dataclass(frozen=True)
class ReportPublication:
    method: PublicationMethod
    report_phase: PublicationReportPhase
    candidate_status: str | None
    readiness_at_report: PublicationReadiness
    readiness_reason_counts: tuple[ReportReasonCount, ...]
    publication_listing_count: int
    publication_source_row_count: int
    publication_payload_row_count: int
    benchmark_provider_listing_id: UUID | None
    benchmark_contract_version: str | None
    resume_cursor: ReportCursor | None

    def __post_init__(self) -> None:
        _require_enum("method", self.method, PublicationMethod)
        _require_enum("report_phase", self.report_phase, PublicationReportPhase)
        _require_enum(
            "readiness_at_report",
            self.readiness_at_report,
            PublicationReadiness,
        )
        if self.candidate_status not in {
            None,
            "BUILDING",
            "PREPARED",
            "PUBLISHED",
            "FAILED",
            "ABANDONED",
        }:
            raise ValueError("candidate_status is not a publication status.")
        _reason_counts(
            "readiness_reason_counts",
            self.readiness_reason_counts,
            PUBLICATION_READINESS_REASON_CODES,
        )
        for name in (
            "publication_listing_count",
            "publication_source_row_count",
            "publication_payload_row_count",
        ):
            _nonnegative_int(name, getattr(self, name))
        _uuid(
            "benchmark_provider_listing_id",
            self.benchmark_provider_listing_id,
            nullable=True,
        )
        if self.benchmark_contract_version not in (
            None,
            BENCHMARK_CONTRACT_VERSION,
        ):
            raise ValueError("benchmark_contract_version is not V1 or null.")
        if self.resume_cursor is not None and not isinstance(
            self.resume_cursor,
            ReportCursor,
        ):
            raise TypeError("resume_cursor must be ReportCursor or None.")
        self._validate_phase()

    def _validate_phase(self) -> None:
        if self.readiness_at_report is PublicationReadiness.READY:
            if self.readiness_reason_counts:
                raise ValueError("READY publication cannot retain reasons.")
        elif not self.readiness_reason_counts:
            raise ValueError("NOT_READY publication requires bounded reasons.")
        if self.report_phase is PublicationReportPhase.PREPARED_CANDIDATE:
            if (
                self.method is PublicationMethod.NONE
                or self.candidate_status != "PREPARED"
                or self.resume_cursor is not None
            ):
                raise ValueError("prepared candidate publication facts are invalid.")
            if self.readiness_at_report is not PublicationReadiness.NOT_READY:
                raise ValueError("prepared candidate cannot claim readiness.")
        elif self.report_phase is PublicationReportPhase.EXISTING_PUBLICATION:
            if (
                self.method is not PublicationMethod.NONE
                or self.candidate_status is not None
                or self.readiness_at_report is not PublicationReadiness.READY
                or self.resume_cursor is not None
            ):
                raise ValueError("existing publication facts are invalid.")
        elif self.report_phase is PublicationReportPhase.UNPUBLISHED_PARTIAL:
            if (
                self.method is not PublicationMethod.STAGED
                or self.candidate_status not in {"BUILDING", "PREPARED"}
                or self.readiness_at_report is not PublicationReadiness.NOT_READY
                or self.resume_cursor is None
            ):
                raise ValueError("partial publication facts are invalid.")
        elif self.report_phase is PublicationReportPhase.DRY_RUN:
            if (
                self.method is not PublicationMethod.NONE
                or self.candidate_status is not None
                or self.readiness_at_report is not PublicationReadiness.NOT_READY
                or self.resume_cursor is not None
            ):
                raise ValueError("dry-run publication facts are invalid.")
        else:
            if self.readiness_at_report is not PublicationReadiness.NOT_READY:
                raise ValueError("failed publication cannot claim readiness.")
            if (
                self.method is PublicationMethod.NONE
                and self.candidate_status is not None
            ) or (
                self.method is not PublicationMethod.NONE
                and self.candidate_status not in {"FAILED", "ABANDONED"}
            ):
                raise ValueError("failed publication lifecycle facts are invalid.")


@dataclass(frozen=True)
class ReportDimensionCount:
    code: str
    listing_count: int
    source_row_count: int
    evaluated_row_count: int
    payload_row_count: int
    published_row_count: int

    def __post_init__(self) -> None:
        _safe_text("code", self.code, maximum=64)
        for name in (
            "listing_count",
            "source_row_count",
            "evaluated_row_count",
            "payload_row_count",
            "published_row_count",
        ):
            _nonnegative_int(name, getattr(self, name))

    @classmethod
    def from_database(
        cls,
        value: ReportDimensionCoverage,
        *,
        evaluated_row_count: int,
    ) -> ReportDimensionCount:
        if not isinstance(value, ReportDimensionCoverage):
            raise TypeError("value must be ReportDimensionCoverage.")
        return cls(
            code=value.code,
            listing_count=value.listing_count,
            source_row_count=value.source_row_count,
            evaluated_row_count=evaluated_row_count,
            payload_row_count=value.payload_row_count,
            published_row_count=value.published_row_count,
        )


@dataclass(frozen=True)
class ReportCounts:
    eligible_listing_count: int
    selected_listing_count: int
    source_listing_count: int
    source_row_count: int
    evaluated_row_count: int
    payload_row_count: int
    published_listing_count: int
    published_row_count: int
    providers: tuple[ReportDimensionCount, ...]
    markets: tuple[ReportDimensionCount, ...]
    instrument_types: tuple[ReportDimensionCount, ...]

    def __post_init__(self) -> None:
        for name in (
            "eligible_listing_count",
            "selected_listing_count",
            "source_listing_count",
            "source_row_count",
            "evaluated_row_count",
            "payload_row_count",
            "published_listing_count",
            "published_row_count",
        ):
            _nonnegative_int(name, getattr(self, name))
        if self.selected_listing_count > self.eligible_listing_count:
            raise ValueError("selected listings exceed eligible listings.")
        if any(
            value > self.selected_listing_count
            for value in (
                self.source_listing_count,
                self.published_listing_count,
            )
        ):
            raise ValueError("covered listing counts exceed selected listings.")
        for name in ("providers", "markets", "instrument_types"):
            values = getattr(self, name)
            _typed_tuple(name, values, ReportDimensionCount)
            codes = tuple(item.code for item in values)
            if codes != tuple(sorted(set(codes))):
                raise ValueError(f"{name} must be sorted and unique.")
            expected = (
                self.selected_listing_count,
                self.source_row_count,
                self.evaluated_row_count,
                self.payload_row_count,
                self.published_row_count,
            )
            actual = tuple(
                sum(getattr(item, field_name) for item in values)
                for field_name in (
                    "listing_count",
                    "source_row_count",
                    "evaluated_row_count",
                    "payload_row_count",
                    "published_row_count",
                )
            )
            if actual != expected:
                raise ValueError(f"{name} counts do not reconcile.")

    @classmethod
    def from_database_summary(
        cls,
        summary: ReportDatabaseSummary,
        *,
        eligible_listing_count: int,
        evaluated_row_count: int,
        evaluated_provider_rows: dict[str, int],
        evaluated_market_rows: dict[str, int],
        evaluated_instrument_type_rows: dict[str, int],
    ) -> ReportCounts:
        """Combine R8.2 database facts with runner-owned evaluation counts."""

        if not isinstance(summary, ReportDatabaseSummary):
            raise TypeError("summary must be ReportDatabaseSummary.")
        dimensions = (
            ("providers", summary.providers, evaluated_provider_rows),
            ("markets", summary.markets, evaluated_market_rows),
            (
                "instrument_types",
                summary.instrument_types,
                evaluated_instrument_type_rows,
            ),
        )
        built: dict[str, tuple[ReportDimensionCount, ...]] = {}
        for name, values, evaluated in dimensions:
            if set(evaluated) != {item.code for item in values}:
                raise ValueError(f"{name} evaluated codes do not match database facts.")
            built[name] = tuple(
                ReportDimensionCount.from_database(
                    item,
                    evaluated_row_count=evaluated[item.code],
                )
                for item in values
            )
        return cls(
            eligible_listing_count=eligible_listing_count,
            selected_listing_count=summary.selected_listing_count,
            source_listing_count=summary.source_listing_count,
            source_row_count=summary.source_row_count,
            evaluated_row_count=evaluated_row_count,
            payload_row_count=summary.payload_row_count,
            published_listing_count=summary.published_listing_count,
            published_row_count=summary.published_row_count,
            providers=built["providers"],
            markets=built["markets"],
            instrument_types=built["instrument_types"],
        )


@dataclass(frozen=True)
class ReportWrites:
    inserted: int = 0
    updated: int = 0
    deleted: int = 0
    equivalent: int = 0
    copied_equivalent: int = 0
    unchanged: int = 0
    failed: int = 0
    batch_count: int = 0
    committed_batch_count: int = 0
    rolled_back_batch_count: int = 0

    def __post_init__(self) -> None:
        for item in fields(self):
            _nonnegative_int(item.name, getattr(self, item.name))
        if (
            self.committed_batch_count + self.rolled_back_batch_count
            != self.batch_count
        ):
            raise ValueError("batch outcome counts do not reconcile.")

    @property
    def persisted_rows(self) -> int:
        return self.inserted + self.updated

    @property
    def evaluated_outcome_rows(self) -> int:
        return (
            self.inserted
            + self.updated
            + self.equivalent
            + self.unchanged
            + self.failed
        )


@dataclass(frozen=True)
class ReportCoverage:
    date: ReportDateCoverage
    versions: tuple[ReportVersionCoverage, ...]
    features: tuple[ReportFeatureCoverage, ...]
    benchmark: ReportBenchmarkCoverage

    def __post_init__(self) -> None:
        if not isinstance(self.date, ReportDateCoverage):
            raise TypeError("date must be ReportDateCoverage.")
        _typed_tuple("versions", self.versions, ReportVersionCoverage)
        version_codes = tuple(item.calculation_version for item in self.versions)
        if version_codes != tuple(sorted(set(version_codes))):
            raise ValueError("version coverage must be sorted and unique.")
        _typed_tuple("features", self.features, ReportFeatureCoverage)
        if tuple(item.feature_name for item in self.features) != REPORT_FEATURE_FIELDS:
            raise ValueError("feature coverage must contain the ordered V1 inventory.")
        if not isinstance(self.benchmark, ReportBenchmarkCoverage):
            raise TypeError("benchmark must be ReportBenchmarkCoverage.")
        if (
            self.benchmark.aligned_row_count
            > self.benchmark.benchmark_linked_row_count
        ):
            raise ValueError("aligned rows exceed benchmark-linked rows.")
        if (
            self.benchmark.effective_date_aligned_count
            > self.date.effective_date_payload_rows
        ):
            raise ValueError("effective-date aligned rows exceed payload rows.")
        if any(
            value > self.benchmark.aligned_row_count
            for value in (
                self.benchmark.complete_20_count,
                self.benchmark.complete_50_count,
                self.benchmark.complete_60_count,
                self.benchmark.complete_63_count,
                self.benchmark.complete_126_count,
                self.benchmark.complete_252_count,
            )
        ):
            raise ValueError("complete-window rows exceed aligned rows.")

    @classmethod
    def from_database_summary(
        cls,
        summary: ReportDatabaseSummary,
    ) -> ReportCoverage:
        if not isinstance(summary, ReportDatabaseSummary):
            raise TypeError("summary must be ReportDatabaseSummary.")
        return cls(
            date=summary.dates,
            versions=summary.versions,
            features=summary.features,
            benchmark=summary.benchmark,
        )


@dataclass(frozen=True)
class ReportBackfill:
    applicable: bool
    batch_size: int | None
    planned_batch_count: int | None
    completed_batch_count: int
    last_completed_cursor: ReportCursor | None
    resumed_from_cursor: ReportCursor | None
    remaining_listing_count: int
    remaining_row_count: int

    def __post_init__(self) -> None:
        _bool("applicable", self.applicable)
        for name in ("batch_size", "planned_batch_count"):
            value = getattr(self, name)
            if value is not None:
                _positive_int(name, value)
        _nonnegative_int("completed_batch_count", self.completed_batch_count)
        for name in ("last_completed_cursor", "resumed_from_cursor"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, ReportCursor):
                raise TypeError(f"{name} must be ReportCursor or None.")
        for name in ("remaining_listing_count", "remaining_row_count"):
            _nonnegative_int(name, getattr(self, name))
        if (
            self.planned_batch_count is not None
            and self.completed_batch_count > self.planned_batch_count
        ):
            raise ValueError("completed batches exceed planned batches.")
        if (self.completed_batch_count == 0) != (
            self.last_completed_cursor is None
        ):
            raise ValueError("completed batches and last cursor do not reconcile.")
        if (
            self.last_completed_cursor is not None
            and self.last_completed_cursor.batch_number
            != self.completed_batch_count
        ):
            raise ValueError("last cursor batch number does not reconcile.")
        if (
            self.resumed_from_cursor is not None
            and self.last_completed_cursor is not None
            and self.resumed_from_cursor.batch_number
            >= self.last_completed_cursor.batch_number
        ):
            raise ValueError("resume cursor must precede the last completed cursor.")
        if not self.applicable and any(
            value is not None and value != 0
            for value in (
                self.batch_size,
                self.planned_batch_count,
                self.completed_batch_count,
                self.last_completed_cursor,
                self.resumed_from_cursor,
                self.remaining_listing_count,
                self.remaining_row_count,
            )
        ):
            raise ValueError("daily backfill facts must be null or zero.")


@dataclass(frozen=True)
class ReportPhaseTiming:
    phase: str
    elapsed_seconds: float

    def __post_init__(self) -> None:
        if self.phase not in REPORT_PHASE_ORDER:
            raise ValueError("phase is not in the R8.3 phase vocabulary.")
        _finite_number("elapsed_seconds", self.elapsed_seconds)


@dataclass(frozen=True)
class ReportThroughput:
    evaluated_rows: int
    persisted_rows: int
    elapsed_seconds: float
    evaluated_rows_per_second: float | None
    persisted_rows_per_second: float | None

    def __post_init__(self) -> None:
        _nonnegative_int("evaluated_rows", self.evaluated_rows)
        _nonnegative_int("persisted_rows", self.persisted_rows)
        _finite_number("elapsed_seconds", self.elapsed_seconds)
        expected = (
            (None, None)
            if self.elapsed_seconds == 0
            else (
                self.evaluated_rows / self.elapsed_seconds,
                self.persisted_rows / self.elapsed_seconds,
            )
        )
        for name, actual, target in (
            (
                "evaluated_rows_per_second",
                self.evaluated_rows_per_second,
                expected[0],
            ),
            (
                "persisted_rows_per_second",
                self.persisted_rows_per_second,
                expected[1],
            ),
        ):
            if actual is not None:
                _finite_number(name, actual)
            if (actual is None) != (target is None) or (
                actual is not None and not isclose(actual, target, rel_tol=1e-12)
            ):
                raise ValueError(f"{name} does not match its denominator.")


@dataclass(frozen=True)
class ReportDatabasePerformance:
    read_page_count: int
    write_batch_count: int
    largest_read_page_rows: int
    largest_write_batch_rows: int
    longest_write_transaction_seconds: float | None

    def __post_init__(self) -> None:
        for name in (
            "read_page_count",
            "write_batch_count",
            "largest_read_page_rows",
            "largest_write_batch_rows",
        ):
            _nonnegative_int(name, getattr(self, name))
        if self.longest_write_transaction_seconds is not None:
            _finite_number(
                "longest_write_transaction_seconds",
                self.longest_write_transaction_seconds,
            )


@dataclass(frozen=True)
class ReportPerformance:
    started_at: datetime
    finished_at: datetime
    elapsed_seconds: float
    peak_rss_bytes: int | None
    phases: tuple[ReportPhaseTiming, ...]
    throughput: ReportThroughput
    database: ReportDatabasePerformance

    def __post_init__(self) -> None:
        _utc_datetime("started_at", self.started_at)
        _utc_datetime("finished_at", self.finished_at)
        if self.finished_at < self.started_at:
            raise ValueError("finished_at must not precede started_at.")
        _finite_number("elapsed_seconds", self.elapsed_seconds)
        actual = (self.finished_at - self.started_at).total_seconds()
        if abs(actual - self.elapsed_seconds) > 0.001:
            raise ValueError("elapsed_seconds does not match timestamps.")
        if self.peak_rss_bytes is not None:
            _nonnegative_int("peak_rss_bytes", self.peak_rss_bytes)
        _typed_tuple("phases", self.phases, ReportPhaseTiming)
        phase_names = tuple(item.phase for item in self.phases)
        expected_order = tuple(
            phase for phase in REPORT_PHASE_ORDER if phase in phase_names
        )
        if phase_names != expected_order or len(set(phase_names)) != len(phase_names):
            raise ValueError("phases must be unique and contract ordered.")
        if (
            sum(item.elapsed_seconds for item in self.phases)
            > self.elapsed_seconds + 0.001
        ):
            raise ValueError("phase durations exceed total elapsed time.")
        if not isinstance(self.throughput, ReportThroughput):
            raise TypeError("throughput must be ReportThroughput.")
        if not isinstance(self.database, ReportDatabasePerformance):
            raise TypeError("database must be ReportDatabasePerformance.")


@dataclass(frozen=True)
class ReportIssueAggregate:
    code: str
    count: int
    sample_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.code not in REPORT_MESSAGE_CATALOG:
            raise ValueError("issue code is not in the R8.3 message vocabulary.")
        _positive_int("count", self.count)
        if not isinstance(self.sample_ids, tuple) or any(
            not _SAMPLE_ID_PATTERN.fullmatch(item) for item in self.sample_ids
        ):
            raise ValueError("sample_ids must contain canonical sample IDs.")
        if self.sample_ids != tuple(sorted(set(self.sample_ids))):
            raise ValueError("sample_ids must be sorted and unique.")
        if len(self.sample_ids) > self.count:
            raise ValueError("sample IDs cannot exceed the complete issue count.")

    @property
    def message(self) -> str:
        return REPORT_MESSAGE_CATALOG[self.code]


@dataclass(frozen=True)
class ReportDiagnosticSample:
    sample_id: str
    code: str
    message: str
    provider_listing_id: UUID | None = None
    provider_code: str | None = None
    market: str | None = None
    ticker: str | None = None
    trading_date: date | None = None
    field_name: str | None = None

    def __post_init__(self) -> None:
        if not _SAMPLE_ID_PATTERN.fullmatch(self.sample_id):
            raise ValueError("sample_id must use the S001 form.")
        if self.code not in REPORT_DIAGNOSTIC_MESSAGE_CATALOG:
            raise ValueError("diagnostic code is not in the R8.3 vocabulary.")
        if self.message != REPORT_DIAGNOSTIC_MESSAGE_CATALOG[self.code]:
            raise ValueError("diagnostic message does not match its fixed code.")
        _uuid(
            "provider_listing_id",
            self.provider_listing_id,
            nullable=True,
        )
        for name in ("provider_code", "market", "ticker"):
            value = getattr(self, name)
            if value is not None:
                _safe_text(name, value, maximum=64)
        _date("trading_date", self.trading_date, nullable=True)
        if self.field_name is not None:
            _field_name("field_name", self.field_name)


@dataclass(frozen=True)
class ReportNativeValueSemantics:
    notes: tuple[str, ...]
    provider_native_grain: bool = True
    canonical_identity: bool = False
    cross_provider_normalized: bool = False
    corporate_actions_normalized: bool = False
    percentages_are_ratios: bool = True
    benchmark_alignment: str = "EXACT_DATE_NO_FILL"

    def __post_init__(self) -> None:
        if (
            self.provider_native_grain,
            self.canonical_identity,
            self.cross_provider_normalized,
            self.corporate_actions_normalized,
            self.percentages_are_ratios,
            self.benchmark_alignment,
        ) != (True, False, False, False, True, "EXACT_DATE_NO_FILL"):
            raise ValueError("native-value semantics must match the V1 contract.")
        expected = tuple(code for code in NATIVE_VALUE_NOTE_ORDER if code in self.notes)
        if self.notes != expected or len(set(self.notes)) != len(self.notes):
            raise ValueError("native-value notes must be unique and contract ordered.")

    @classmethod
    def for_providers(
        cls,
        provider_codes: tuple[str, ...],
        *,
        analytical_rows_present: bool,
    ) -> ReportNativeValueSemantics:
        _sorted_unique_text("provider_codes", provider_codes)
        selected: set[str] = set()
        if "EODDATA" in provider_codes:
            selected.update(NATIVE_VALUE_NOTE_ORDER[:3])
        if "STOOQ" in provider_codes:
            selected.update(NATIVE_VALUE_NOTE_ORDER[3:7])
        if "YAHOO" in provider_codes:
            selected.update(NATIVE_VALUE_NOTE_ORDER[7:10])
        if analytical_rows_present:
            selected.update(NATIVE_VALUE_NOTE_ORDER[10:])
        return cls(tuple(code for code in NATIVE_VALUE_NOTE_ORDER if code in selected))


@dataclass(frozen=True)
class TechIndicatorsReport:
    report_id: str
    workflow_kind: WorkflowKind
    outcome: ReportOutcome
    generated_at: datetime
    identity: ReportIdentity
    scope: ReportScope
    versions: ReportVersions
    lock: ReportLock
    source_readiness: ReportSourceReadiness
    publication: ReportPublication
    counts: ReportCounts
    writes: ReportWrites
    coverage: ReportCoverage
    backfill: ReportBackfill
    performance: ReportPerformance
    warnings: tuple[ReportIssueAggregate, ...]
    failures: tuple[ReportIssueAggregate, ...]
    diagnostic_samples: tuple[ReportDiagnosticSample, ...]
    native_value_semantics: ReportNativeValueSemantics
    schema_version: int = REPORT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != REPORT_SCHEMA_VERSION:
            raise ValueError("schema_version must be 1.")
        _require_enum("workflow_kind", self.workflow_kind, WorkflowKind)
        _require_enum("outcome", self.outcome, ReportOutcome)
        _utc_datetime("generated_at", self.generated_at)
        expected_types = {
            "identity": ReportIdentity,
            "scope": ReportScope,
            "versions": ReportVersions,
            "lock": ReportLock,
            "source_readiness": ReportSourceReadiness,
            "publication": ReportPublication,
            "counts": ReportCounts,
            "writes": ReportWrites,
            "coverage": ReportCoverage,
            "backfill": ReportBackfill,
            "performance": ReportPerformance,
            "native_value_semantics": ReportNativeValueSemantics,
        }
        for name, expected_type in expected_types.items():
            if not isinstance(getattr(self, name), expected_type):
                raise TypeError(f"{name} must be {expected_type.__name__}.")
        _typed_tuple("warnings", self.warnings, ReportIssueAggregate)
        _typed_tuple("failures", self.failures, ReportIssueAggregate)
        _typed_tuple(
            "diagnostic_samples",
            self.diagnostic_samples,
            ReportDiagnosticSample,
        )
        self._validate_identity()
        self._validate_counts()
        self._validate_outcome()
        self._validate_diagnostics()

    def _validate_identity(self) -> None:
        expected = {
            WorkflowKind.DAILY: (
                DAILY_REPORT_ID,
                DAILY_CORE_JOB_NAME,
                False,
            ),
            WorkflowKind.BACKFILL: (
                BACKFILL_REPORT_ID,
                BACKFILL_CORE_JOB_NAME,
                True,
            ),
        }[self.workflow_kind]
        if (
            self.report_id,
            self.identity.core_job_name,
            self.backfill.applicable,
        ) != expected:
            raise ValueError("report identity does not match workflow kind.")
        if self.workflow_kind is WorkflowKind.DAILY:
            if (
                self.scope.effective_date is None
                or self.scope.start_date is not None
                or self.scope.end_date is not None
                or self.scope.effective_date != self.identity.effective_date
            ):
                raise ValueError("daily scope date shape is invalid.")
        elif (
            self.scope.effective_date is not None
            or self.scope.start_date is None
            or self.scope.end_date is None
        ):
            raise ValueError("backfill scope date shape is invalid.")
        if self.generated_at < self.performance.finished_at:
            raise ValueError("generated_at precedes performance.finished_at.")
        if self.scope.resolved_listing_count != self.counts.selected_listing_count:
            raise ValueError("resolved scope and selected counts do not reconcile.")
        if self.workflow_kind is WorkflowKind.DAILY and (
            self.source_readiness.effective_date is not None
            and self.source_readiness.effective_date != self.identity.effective_date
        ):
            raise ValueError("daily source-readiness date does not reconcile.")

    def _validate_counts(self) -> None:
        if self.writes.evaluated_outcome_rows != self.counts.evaluated_row_count:
            raise ValueError("write outcomes do not reconcile with evaluated rows.")
        if (
            self.performance.throughput.evaluated_rows
            != self.counts.evaluated_row_count
        ):
            raise ValueError("throughput evaluated rows do not reconcile.")
        if self.performance.throughput.persisted_rows != self.writes.persisted_rows:
            raise ValueError("throughput persisted rows do not reconcile.")
        if self.performance.database.write_batch_count != self.writes.batch_count:
            raise ValueError("database and write batch counts do not reconcile.")
        if (
            sum(item.row_count for item in self.coverage.versions)
            != self.counts.payload_row_count
        ):
            raise ValueError("coverage version rows do not reconcile.")
        if any(
            item.listing_count > self.counts.selected_listing_count
            for item in self.coverage.versions
        ):
            raise ValueError("version listing counts exceed selected listings.")
        if (
            self.coverage.date.effective_date_source_rows
            > self.counts.source_row_count
            or self.coverage.date.effective_date_payload_rows
            > self.counts.payload_row_count
            or self.coverage.date.effective_date_published_rows
            > self.counts.published_row_count
        ):
            raise ValueError("effective-date coverage exceeds root counts.")
        if any(
            item.eligible_row_count != self.counts.payload_row_count
            for item in self.coverage.features
        ):
            raise ValueError(
                "feature eligible rows do not reconcile with payload rows."
            )
        if (
            self.coverage.benchmark.supported_listing_count
            + self.coverage.benchmark.unsupported_listing_count
            != self.counts.selected_listing_count
        ):
            raise ValueError("benchmark listing counts do not reconcile.")
        if (
            self.coverage.benchmark.benchmark_linked_row_count
            + self.coverage.benchmark.benchmark_unlinked_row_count
            != self.counts.payload_row_count
        ):
            raise ValueError("benchmark row counts do not reconcile.")
        if (
            self.publication.publication_listing_count
            != self.counts.selected_listing_count
        ):
            raise ValueError("publication listing count does not reconcile.")
        if (
            self.publication.publication_payload_row_count
            != self.counts.payload_row_count
        ):
            raise ValueError("publication and payload rows do not reconcile.")
        if (
            self.publication.publication_source_row_count
            != self.counts.source_row_count
        ):
            raise ValueError("publication and source rows do not reconcile.")
        benchmark = self.coverage.benchmark
        if not benchmark.supported_listing_count:
            if any(
                (
                    benchmark.benchmark_linked_row_count,
                    benchmark.aligned_row_count,
                    benchmark.complete_20_count,
                    benchmark.complete_50_count,
                    benchmark.complete_60_count,
                    benchmark.complete_63_count,
                    benchmark.complete_126_count,
                    benchmark.complete_252_count,
                )
            ) or self.publication.benchmark_provider_listing_id is not None:
                raise ValueError("unsupported scope has benchmark coverage.")
        elif self.outcome is not ReportOutcome.FAIL:
            if (
                self.publication.benchmark_provider_listing_id is None
                or self.publication.benchmark_contract_version
                != BENCHMARK_CONTRACT_VERSION
            ):
                raise ValueError("supported scope lacks publication benchmark facts.")
            source_identifier = self.source_readiness.benchmark.provider_listing_id
            if source_identifier is not None and (
                source_identifier
                != self.publication.benchmark_provider_listing_id
            ):
                raise ValueError("source and publication benchmark IDs differ.")
        provider_codes = tuple(item.code for item in self.counts.providers)
        expected_semantics = ReportNativeValueSemantics.for_providers(
            provider_codes,
            analytical_rows_present=self.counts.payload_row_count > 0,
        )
        if self.native_value_semantics != expected_semantics:
            raise ValueError("native-value disclosures do not match report coverage.")

    def _validate_outcome(self) -> None:
        warning_codes = tuple(item.code for item in self.warnings)
        failure_codes = tuple(item.code for item in self.failures)
        if warning_codes != tuple(sorted(set(warning_codes))):
            raise ValueError("warnings must be sorted and unique by code.")
        if failure_codes != tuple(sorted(set(failure_codes))):
            raise ValueError("failures must be sorted and unique by code.")
        has_unexpected = any(
            item.unexpected_null_count for item in self.coverage.features
        )
        forced_failure = (
            self.lock.outcome is LockOutcome.LOST
            or self.writes.failed > 0
            or bool(self.failures)
            or has_unexpected
        )
        if forced_failure and self.outcome is not ReportOutcome.FAIL:
            raise ValueError("failure facts require outcome FAIL.")
        if (
            self.source_readiness.decision
            is SourceReadinessStatus.NOT_APPLICABLE
            and self.outcome is not ReportOutcome.FAIL
        ):
            raise ValueError("unevaluated source readiness requires outcome FAIL.")
        if (
            self.source_readiness.decision is SourceReadinessStatus.NOT_READY
            and self.outcome not in {ReportOutcome.PARTIAL, ReportOutcome.FAIL}
        ):
            raise ValueError("unready source evidence requires incomplete outcome.")
        if self.outcome is ReportOutcome.PASS and (self.warnings or self.failures):
            raise ValueError("PASS cannot retain warnings or failures.")
        if self.outcome is ReportOutcome.WARN and (
            not self.warnings or self.failures
        ):
            raise ValueError("WARN requires warnings and no failures.")
        if self.outcome is ReportOutcome.NO_OP:
            if (
                self.warnings
                or self.failures
                or any(getattr(self.writes, item.name) for item in fields(self.writes))
                or self.identity.existing_readiness_token is None
                or self.identity.publication_id is not None
                or self.publication.report_phase
                is not PublicationReportPhase.EXISTING_PUBLICATION
                or self.source_readiness.decision is not SourceReadinessStatus.READY
                or self.backfill.completed_batch_count
                or self.backfill.remaining_listing_count
                or self.backfill.remaining_row_count
            ):
                raise ValueError("NO_OP facts are invalid.")
        elif self.identity.existing_readiness_token is not None:
            raise ValueError("existing readiness token is no-op only.")
        if self.outcome is ReportOutcome.PARTIAL:
            if (
                self.workflow_kind is not WorkflowKind.BACKFILL
                or self.publication.report_phase
                is not PublicationReportPhase.UNPUBLISHED_PARTIAL
                or not (self.warnings or self.failures)
                or not (
                    self.backfill.remaining_listing_count
                    or self.backfill.remaining_row_count
                )
            ):
                raise ValueError("PARTIAL facts are invalid.")
        elif self.outcome in {ReportOutcome.PASS, ReportOutcome.WARN} and (
            self.backfill.remaining_listing_count or self.backfill.remaining_row_count
        ):
            raise ValueError("complete outcomes cannot retain backfill work.")
        if self.outcome is ReportOutcome.FAIL and not self.failures:
            raise ValueError("FAIL requires at least one bounded failure.")
        phase = self.publication.report_phase
        if self.outcome in {ReportOutcome.PASS, ReportOutcome.WARN} and phase not in {
            PublicationReportPhase.PREPARED_CANDIDATE,
            PublicationReportPhase.DRY_RUN,
        }:
            raise ValueError("complete outcome has an invalid publication phase.")
        if (
            self.outcome is ReportOutcome.FAIL
            and phase is not PublicationReportPhase.FAILED
        ):
            raise ValueError("FAIL must use the failed publication phase.")
        if phase in {
            PublicationReportPhase.PREPARED_CANDIDATE,
            PublicationReportPhase.UNPUBLISHED_PARTIAL,
        } and self.identity.publication_id is None:
            raise ValueError("candidate report phase requires a publication ID.")
        if phase in {
            PublicationReportPhase.EXISTING_PUBLICATION,
            PublicationReportPhase.DRY_RUN,
        } and self.identity.publication_id is not None:
            raise ValueError(
                "non-candidate report phase requires a null publication ID."
            )
        if self.outcome is ReportOutcome.PARTIAL and (
            self.publication.resume_cursor != self.backfill.last_completed_cursor
        ):
            raise ValueError("partial publication and backfill cursors differ.")
        if self.lock.outcome is LockOutcome.LOST and (
            self.publication.report_phase is not PublicationReportPhase.FAILED
            or self.publication.readiness_at_report
            is not PublicationReadiness.NOT_READY
        ):
            raise ValueError("lock loss must remain unpublished and failed.")
        if self.scope.dry_run:
            if (
                self.publication.report_phase is not PublicationReportPhase.DRY_RUN
                or self.identity.publication_id is not None
            ):
                raise ValueError("dry-run report facts are invalid.")

    def _validate_diagnostics(self) -> None:
        if len(self.diagnostic_samples) > REPORT_DIAGNOSTIC_SAMPLE_LIMIT:
            raise ValueError("diagnostic samples exceed the 100-sample ceiling.")
        expected = tuple(
            f"S{index:03d}" for index in range(1, len(self.diagnostic_samples) + 1)
        )
        actual = tuple(item.sample_id for item in self.diagnostic_samples)
        if actual != expected:
            raise ValueError("diagnostic sample IDs must be contiguous and ordered.")
        sort_keys = tuple(
            _diagnostic_sort_key(item) for item in self.diagnostic_samples
        )
        if sort_keys != tuple(sorted(sort_keys)):
            raise ValueError("diagnostic samples are not contract ordered.")
        sample_ids = set(actual)
        referenced = {
            sample_id
            for issue in (*self.warnings, *self.failures)
            for sample_id in issue.sample_ids
        }
        if not referenced.issubset(sample_ids):
            raise ValueError("an issue references a missing diagnostic sample.")
        readiness_codes = {
            item.code
            for item in (
                *self.source_readiness.reason_counts,
                *self.publication.readiness_reason_counts,
            )
        }
        unexpected_fields = {
            item.feature_name
            for item in self.coverage.features
            if item.unexpected_null_count
        }
        for sample in self.diagnostic_samples:
            if (
                sample.sample_id not in referenced
                and sample.code not in readiness_codes
                and sample.field_name not in unexpected_fields
            ):
                raise ValueError("diagnostic sample is not referenced by report facts.")

    def to_dict(self) -> dict[str, object]:
        return _json_value(self)


def make_report_diagnostic_samples(
    samples: tuple[ReportDiagnosticSample, ...],
) -> tuple[ReportDiagnosticSample, ...]:
    """Sort diagnostic facts and assign stable S001-style identifiers."""

    _typed_tuple("samples", samples, ReportDiagnosticSample)
    if len(samples) > REPORT_DIAGNOSTIC_SAMPLE_LIMIT:
        raise ValueError("diagnostic samples exceed the 100-sample ceiling.")
    ordered = sorted(samples, key=_diagnostic_sort_key)
    return tuple(
        replace(item, sample_id=f"S{index:03d}")
        for index, item in enumerate(ordered, start=1)
    )


def render_tech_indicators_report_json(report: TechIndicatorsReport) -> bytes:
    """Return deterministic compact schema-V1 UTF-8 JSON with one newline."""

    if not isinstance(report, TechIndicatorsReport):
        raise TypeError("report must be a TechIndicatorsReport.")
    payload = json.dumps(
        report.to_dict(),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    if len(payload) > REPORT_MAXIMUM_BYTES:
        raise ValueError("report.json exceeds the 2 MiB contract bound.")
    return payload


def _diagnostic_sort_key(item: ReportDiagnosticSample) -> tuple[object, ...]:
    return (
        item.provider_code or "",
        item.market or "",
        item.ticker or "",
        "" if item.provider_listing_id is None else str(item.provider_listing_id),
        date.min if item.trading_date is None else item.trading_date,
        item.field_name or "",
        item.code,
        item.message,
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
    if type(value) is date:
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        result: dict[str, object] = {}
        for item in fields(value):
            if isinstance(value, ReportIssueAggregate) and item.name == "sample_ids":
                result["message"] = value.message
            result[item.name] = _json_value(getattr(value, item.name))
        return result
    if value is None or type(value) in (str, int, float, bool):
        return value
    raise TypeError(f"Unsupported report value type: {type(value).__name__}.")


__all__ = [
    "BACKFILL_CORE_JOB_NAME",
    "BACKFILL_REPORT_ID",
    "BENCHMARK_CONTRACT_VERSION",
    "DAILY_CORE_JOB_NAME",
    "DAILY_REPORT_ID",
    "LockOutcome",
    "NATIVE_VALUE_NOTE_MESSAGES",
    "NATIVE_VALUE_NOTE_ORDER",
    "PublicationMethod",
    "PublicationReadiness",
    "PublicationReportPhase",
    "PUBLICATION_READINESS_REASON_CODES",
    "REPORT_DIAGNOSTIC_SAMPLE_LIMIT",
    "REPORT_DIAGNOSTIC_MESSAGE_CATALOG",
    "REPORT_MAXIMUM_BYTES",
    "REPORT_MESSAGE_CATALOG",
    "REPORT_PHASE_ORDER",
    "REPORT_SCHEMA_VERSION",
    "SOURCE_READINESS_REASON_CODES",
    "ReportBackfill",
    "ReportCounts",
    "ReportCoverage",
    "ReportCursor",
    "ReportDatabasePerformance",
    "ReportDiagnosticSample",
    "ReportDimensionCount",
    "ReportIdentity",
    "ReportIssueAggregate",
    "ReportLock",
    "ReportNativeValueSemantics",
    "ReportOutcome",
    "ReportPerformance",
    "ReportPhaseTiming",
    "ReportProviderEvidence",
    "ReportPublication",
    "ReportReasonCount",
    "ReportScope",
    "ReportSourceBenchmark",
    "ReportSourceReadiness",
    "ReportThroughput",
    "ReportVersions",
    "ReportWrites",
    "SourceReadinessStatus",
    "TechIndicatorsReport",
    "WorkflowKind",
    "make_report_diagnostic_samples",
    "render_tech_indicators_report_json",
]
