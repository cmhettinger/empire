"""Deterministic SEC confidence evaluation for stored reconciliation evidence.

This module deliberately contains policy evaluation only.  It does not select
database rows, write audits, or change a security identity status; those are
separate reconciliation workflow concerns.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping
from uuid import UUID

from empire_stonks_securities.reconciliation_audit import (
    EVIDENCE_ROLE_BLOCKS,
    EVIDENCE_ROLE_CONFLICTS,
    EVIDENCE_ROLE_SUPPORTS,
    IDENTITY_STATUS_PROVISIONAL,
)
from empire_stonks_securities.reconciliation_evidence import (
    EVIDENCE_TYPE_SEC_ISSUER_SECURITY_MATCH,
    EVIDENCE_TYPE_SEC_SOURCE_SNAPSHOT_CONTINUITY,
    EVIDENCE_TYPE_SEC_TICKER_EXCHANGE_STABILITY,
)


CONFIDENCE_PROFILE_DAILY = "daily"
CONFIDENCE_PROFILE_BACKFILL = "backfill"
POLICY_ID_DAILY = "SEC_DAILY_CONTINUITY_V1"
POLICY_ID_BACKFILL = "SEC_BACKFILL_PROMOTION_V1"

RULE_ISSUER_SECURITY_MATCH = "SEC_V1_ISSUER_SECURITY_MATCH"
RULE_TICKER_EXCHANGE_STABILITY = "SEC_V1_TICKER_EXCHANGE_STABILITY"
RULE_SOURCE_SNAPSHOT_CONTINUITY = "SEC_V1_SOURCE_SNAPSHOT_CONTINUITY"
RULE_SERIES_CLASS_RESERVED = "SEC_V1_SERIES_CLASS_RESERVED"
RULE_BLOCK_NON_PROVISIONAL = "SEC_V1_BLOCK_NON_PROVISIONAL"
RULE_BLOCK_EXPLICIT = "SEC_V1_BLOCK_EXPLICIT"
RULE_BLOCK_CONFLICT = "SEC_V1_BLOCK_CONFLICT"
RULE_BLOCK_INCONSISTENT_SUPPORT = "SEC_V1_BLOCK_INCONSISTENT_SUPPORT"
RULE_BLOCK_INVALID_LINEAGE = "SEC_V1_BLOCK_INVALID_LINEAGE"

REFUSAL_DAILY_CANNOT_PROMOTE = "daily_profile_cannot_promote"
REFUSAL_IDENTITY_STATUS_NOT_PROVISIONAL = "identity_status_not_provisional"
REFUSAL_EXPLICIT_BLOCKING_EVIDENCE = "explicit_blocking_evidence"
REFUSAL_CONFLICTING_SEC_IDENTITY_EVIDENCE = "conflicting_sec_identity_evidence"
REFUSAL_INCONSISTENT_SUPPORTING_EVIDENCE = "inconsistent_supporting_evidence"
REFUSAL_INCOMPLETE_EVIDENCE_LINEAGE = "incomplete_evidence_lineage"
REFUSAL_MISSING_ISSUER_SECURITY_MATCH = "missing_issuer_security_match"
REFUSAL_INSUFFICIENT_TICKER_EXCHANGE_REPETITION = "insufficient_ticker_exchange_repetition"
REFUSAL_INSUFFICIENT_SNAPSHOT_CONTINUITY = "insufficient_snapshot_continuity"
REFUSAL_INSUFFICIENT_BACKFILL_TIME_SPAN = "insufficient_backfill_time_span"

_RELEVANT_TYPES = frozenset(
    {
        EVIDENCE_TYPE_SEC_ISSUER_SECURITY_MATCH,
        EVIDENCE_TYPE_SEC_TICKER_EXCHANGE_STABILITY,
        EVIDENCE_TYPE_SEC_SOURCE_SNAPSHOT_CONTINUITY,
    }
)


@dataclass(frozen=True)
class StoredReconciliationEvidence:
    """One persisted derived-evidence record and its retained lineage IDs."""

    reconciliation_evidence_id: UUID
    security_id: UUID
    issuer_id: UUID | None
    listing_id: UUID | None
    evidence_type: str
    evidence_role: str
    summary_json: Mapping[str, Any]
    provider_evidence_ids: tuple[UUID, ...]
    source_snapshot_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class ConfidenceRuleResult:
    """The deterministic outcome of one fixed v1 policy rule."""

    rule_id: str
    satisfied: bool
    score: int = 0
    evidence_ids: tuple[UUID, ...] = ()
    refusal_reason: str | None = None


@dataclass(frozen=True)
class SecurityConfidenceEvaluation:
    """Pure confidence result suitable for a later audit or dry-run report."""

    security_id: UUID
    profile: str
    policy_id: str
    score: int
    confidence_level: str
    rule_results: tuple[ConfidenceRuleResult, ...]
    explanation: str
    evidence_ids: tuple[UUID, ...]
    refusal_reasons: tuple[str, ...]
    blocked: bool
    continuity_ready: bool

    @property
    def rule_ids(self) -> tuple[str, ...]:
        """Return fixed policy rule IDs in evaluation order."""

        return tuple(result.rule_id for result in self.rule_results)


def evaluate_security_confidence(
    *,
    security_id: UUID,
    identity_status: str,
    profile: str,
    evidence: Iterable[StoredReconciliationEvidence],
) -> SecurityConfidenceEvaluation:
    """Evaluate stored SEC evidence under one fixed daily or backfill profile.

    The result never declares a promotion candidate.  That dry-run decision is
    intentionally reserved for C4.3; this evaluator only reports score,
    readiness, blockers, and refusal reasons.
    """

    policy_id, snapshot_threshold, minimum_span_days = _profile_thresholds(profile)
    records = tuple(sorted(evidence, key=lambda item: str(item.reconciliation_evidence_id)))
    if any(item.security_id != security_id for item in records):
        raise ValueError("all evidence must belong to security_id")

    blockers: list[ConfidenceRuleResult] = []
    if identity_status != IDENTITY_STATUS_PROVISIONAL:
        blockers.append(_rule(RULE_BLOCK_NON_PROVISIONAL, REFUSAL_IDENTITY_STATUS_NOT_PROVISIONAL))

    relevant = tuple(item for item in records if item.evidence_type in _RELEVANT_TYPES)
    explicit_blocks = tuple(item for item in relevant if item.evidence_role == EVIDENCE_ROLE_BLOCKS)
    if explicit_blocks:
        blockers.append(_rule(RULE_BLOCK_EXPLICIT, REFUSAL_EXPLICIT_BLOCKING_EVIDENCE, explicit_blocks))
    conflicts = tuple(item for item in relevant if item.evidence_role == EVIDENCE_ROLE_CONFLICTS)
    if conflicts:
        blockers.append(_rule(RULE_BLOCK_CONFLICT, REFUSAL_CONFLICTING_SEC_IDENTITY_EVIDENCE, conflicts))

    support_records = tuple(
        item for item in relevant if item.evidence_role == EVIDENCE_ROLE_SUPPORTS
    )
    invalid_lineage = tuple(item for item in support_records if _invalid_lineage(item))
    if invalid_lineage:
        blockers.append(_rule(RULE_BLOCK_INVALID_LINEAGE, REFUSAL_INCOMPLETE_EVIDENCE_LINEAGE, invalid_lineage))
    invalid_lineage_ids = {item.reconciliation_evidence_id for item in invalid_lineage}
    supports = tuple(
        item
        for item in support_records
        if item.reconciliation_evidence_id not in invalid_lineage_ids
    )

    issuer_matches = tuple(
        item for item in supports
        if item.evidence_type == EVIDENCE_TYPE_SEC_ISSUER_SECURITY_MATCH
        and item.issuer_id is not None
    )
    stability = tuple(
        item for item in supports
        if item.evidence_type == EVIDENCE_TYPE_SEC_TICKER_EXCHANGE_STABILITY
        and _snapshot_count(item) >= snapshot_threshold
        and not bool(_values(item).get("insufficient_repeat"))
        and item.listing_id is not None
        and _mapping(item) is not None
    )
    continuity = tuple(
        item for item in supports
        if item.evidence_type == EVIDENCE_TYPE_SEC_SOURCE_SNAPSHOT_CONTINUITY
        and _snapshot_count(item) >= snapshot_threshold
        and item.listing_id is not None
        and _mapping(item) is not None
        and _span_days(item) >= minimum_span_days
    )

    if _support_mappings_disagree(supports, stability, continuity):
        blockers.append(_rule(
            RULE_BLOCK_INCONSISTENT_SUPPORT,
            REFUSAL_INCONSISTENT_SUPPORTING_EVIDENCE,
            (*stability, *continuity),
        ))

    scored = (
        ConfidenceRuleResult(
            RULE_ISSUER_SECURITY_MATCH,
            bool(issuer_matches),
            25 if issuer_matches else 0,
            _ids(issuer_matches),
            None if issuer_matches else REFUSAL_MISSING_ISSUER_SECURITY_MATCH,
        ),
        ConfidenceRuleResult(
            RULE_TICKER_EXCHANGE_STABILITY,
            bool(stability),
            25 if stability else 0,
            _ids(stability),
            None if stability else REFUSAL_INSUFFICIENT_TICKER_EXCHANGE_REPETITION,
        ),
        ConfidenceRuleResult(
            RULE_SOURCE_SNAPSHOT_CONTINUITY,
            bool(continuity),
            20 if continuity else 0,
            _ids(continuity),
            _continuity_refusal(continuity, supports, minimum_span_days),
        ),
        ConfidenceRuleResult(RULE_SERIES_CLASS_RESERVED, False),
    )
    score = sum(item.score for item in scored)
    blocked = bool(blockers)
    ready = not blocked and score == 70
    refusal_reasons = tuple(
        sorted(
            {
                *(item.refusal_reason for item in blockers if item.refusal_reason),
                *(item.refusal_reason for item in scored if item.refusal_reason),
            }
        )
    )
    selected = tuple(
        sorted(
            {*(_ids(support_records)), *(_ids(explicit_blocks)), *(_ids(conflicts))},
            key=str,
        )
    )
    rules = (*scored, *sorted(blockers, key=lambda item: item.rule_id))
    return SecurityConfidenceEvaluation(
        security_id=security_id,
        profile=profile,
        policy_id=policy_id,
        score=score,
        confidence_level=_confidence_level(score),
        rule_results=rules,
        explanation=_explanation(policy_id, score, blocked, ready, refusal_reasons),
        evidence_ids=selected,
        refusal_reasons=refusal_reasons,
        blocked=blocked,
        continuity_ready=ready,
    )


def _profile_thresholds(profile: str) -> tuple[str, int, int]:
    if profile == CONFIDENCE_PROFILE_DAILY:
        return POLICY_ID_DAILY, 2, 0
    if profile == CONFIDENCE_PROFILE_BACKFILL:
        return POLICY_ID_BACKFILL, 3, 30
    raise ValueError("profile must be 'daily' or 'backfill'")


def _rule(rule_id: str, refusal_reason: str, evidence: Iterable[StoredReconciliationEvidence] = ()) -> ConfidenceRuleResult:
    return ConfidenceRuleResult(rule_id, True, evidence_ids=_ids(evidence), refusal_reason=refusal_reason)


def _ids(evidence: Iterable[StoredReconciliationEvidence]) -> tuple[UUID, ...]:
    return tuple(sorted({item.reconciliation_evidence_id for item in evidence}, key=str))


def _values(evidence: StoredReconciliationEvidence) -> Mapping[str, Any]:
    values = evidence.summary_json.get("normalized_values", {})
    return values if isinstance(values, Mapping) else {}


def _snapshot_count(evidence: StoredReconciliationEvidence) -> int:
    value = _values(evidence).get("distinct_snapshot_count", 0)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _invalid_lineage(evidence: StoredReconciliationEvidence) -> bool:
    if not evidence.provider_evidence_ids:
        return True
    return _snapshot_count(evidence) > 0 and not evidence.source_snapshot_ids


def _mapping(evidence: StoredReconciliationEvidence) -> tuple[UUID, UUID, str, str] | None:
    values = _values(evidence)
    ticker = values.get("ticker")
    exchange = values.get("exchange")
    if (
        evidence.issuer_id is None
        or evidence.listing_id is None
        or not isinstance(ticker, str)
        or not isinstance(exchange, str)
    ):
        return None
    return evidence.issuer_id, evidence.listing_id, ticker, exchange


def _support_mappings_disagree(
    supports: Iterable[StoredReconciliationEvidence],
    stability: Iterable[StoredReconciliationEvidence],
    continuity: Iterable[StoredReconciliationEvidence],
) -> bool:
    issuer_ids = {item.issuer_id for item in supports if item.issuer_id is not None}
    if len(issuer_ids) > 1:
        return True
    mappings = {_mapping(item) for item in (*stability, *continuity)}
    return len(mappings) > 1


def _span_days(evidence: StoredReconciliationEvidence) -> int:
    first = _parse_timestamp(evidence.summary_json.get("first_observed_at"))
    last = _parse_timestamp(evidence.summary_json.get("last_observed_at"))
    return (last - first).days if first is not None and last is not None and last >= first else 0


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _continuity_refusal(
    continuity: tuple[StoredReconciliationEvidence, ...],
    supports: tuple[StoredReconciliationEvidence, ...],
    minimum_span_days: int,
) -> str | None:
    if continuity:
        return None
    raw_continuity = tuple(
        item
        for item in supports
        if item.evidence_type == EVIDENCE_TYPE_SEC_SOURCE_SNAPSHOT_CONTINUITY
    )
    if minimum_span_days and any(_snapshot_count(item) >= 3 for item in raw_continuity):
        return REFUSAL_INSUFFICIENT_BACKFILL_TIME_SPAN
    return REFUSAL_INSUFFICIENT_SNAPSHOT_CONTINUITY


def _confidence_level(score: int) -> str:
    if score >= 70:
        return "HIGH"
    if score >= 45:
        return "MEDIUM"
    return "LOW"


def _explanation(policy_id: str, score: int, blocked: bool, ready: bool, reasons: tuple[str, ...]) -> str:
    state = "blocked" if blocked else "continuity_ready" if ready else "not_continuity_ready"
    suffix = f" Refusal reasons: {', '.join(reasons)}." if reasons else ""
    return f"{policy_id} evaluated {score}/70 ({_confidence_level(score)}): {state}.{suffix}"
