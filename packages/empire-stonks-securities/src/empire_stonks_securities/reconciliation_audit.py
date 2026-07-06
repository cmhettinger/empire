"""Append-only security reconciliation audit writes."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Mapping
from uuid import UUID

from empire_core.db.postgres import json_dumps


IDENTITY_STATUS_PROVISIONAL = "PROVISIONAL"
IDENTITY_STATUS_CONFIRMED = "CONFIRMED"
IDENTITY_STATUSES = frozenset({IDENTITY_STATUS_PROVISIONAL, IDENTITY_STATUS_CONFIRMED})

EVALUATION_DECISION_PROMOTION_CANDIDATE = "PROMOTION_CANDIDATE"
EVALUATION_DECISION_PROMOTION_BLOCKED = "PROMOTION_BLOCKED"
EVALUATION_DECISION_NO_ACTION = "NO_ACTION"
EVALUATION_DECISION_DUPLICATE_CANDIDATE = "DUPLICATE_CANDIDATE"
EVALUATION_DECISION_SUCCESSOR_LISTING_CANDIDATE = "SUCCESSOR_LISTING_CANDIDATE"
EVALUATION_DECISION_MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"
EVALUATION_DECISION_TYPES = frozenset(
    {
        EVALUATION_DECISION_PROMOTION_CANDIDATE,
        EVALUATION_DECISION_PROMOTION_BLOCKED,
        EVALUATION_DECISION_NO_ACTION,
        EVALUATION_DECISION_DUPLICATE_CANDIDATE,
        EVALUATION_DECISION_SUCCESSOR_LISTING_CANDIDATE,
        EVALUATION_DECISION_MANUAL_REVIEW_REQUIRED,
    }
)

EVIDENCE_ROLE_SUPPORTS = "SUPPORTS"
EVIDENCE_ROLE_CONFLICTS = "CONFLICTS"
EVIDENCE_ROLE_BLOCKS = "BLOCKS"
EVIDENCE_ROLE_CONTEXT = "CONTEXT"
EVIDENCE_ROLES = frozenset(
    {
        EVIDENCE_ROLE_SUPPORTS,
        EVIDENCE_ROLE_CONFLICTS,
        EVIDENCE_ROLE_BLOCKS,
        EVIDENCE_ROLE_CONTEXT,
    }
)

APPLIED_DECISION_PROMOTE_TO_CONFIRMED = "PROMOTE_TO_CONFIRMED"
APPLIED_DECISION_TYPES = frozenset({APPLIED_DECISION_PROMOTE_TO_CONFIRMED})


class SecurityReconciliationAuditError(ValueError):
    """Raised when a reconciliation audit write input is invalid."""


@dataclass(frozen=True)
class EvaluationEvidenceLink:
    """Provider evidence linked to one reconciliation evaluation."""

    provider_evidence_id: UUID
    evidence_role: str = EVIDENCE_ROLE_SUPPORTS


@dataclass(frozen=True)
class SecurityReconciliationEvaluation:
    """Append-only evaluation audit input."""

    run_id: UUID
    security_id: UUID
    decision_type: str
    rule_id: str
    rule_version: str
    confidence_code: str
    previous_identity_status: str
    evaluated_identity_status: str
    explanation: str
    issuer_id: UUID | None = None
    listing_id: UUID | None = None
    related_security_id: UUID | None = None
    related_listing_id: UUID | None = None
    confidence_score: Decimal | float | str | None = None
    reason_codes: tuple[str, ...] = ()
    details_json: Mapping[str, Any] = field(default_factory=dict)
    evidence_links: tuple[EvaluationEvidenceLink, ...] = ()


@dataclass(frozen=True)
class SecurityReconciliationDecision:
    """Append-only applied reconciliation decision input."""

    evaluation_id: UUID
    run_id: UUID
    security_id: UUID
    decision_type: str
    previous_identity_status: str
    new_identity_status: str
    explanation: str
    applied_by: str | None = None
    details_json: Mapping[str, Any] = field(default_factory=dict)


def insert_security_reconciliation_evaluation(
    *,
    connection: Any,
    evaluation: SecurityReconciliationEvaluation,
) -> UUID:
    """Insert an immutable reconciliation evaluation row and evidence links."""

    _validate_evaluation(evaluation)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO stonks.security_reconciliation_evaluation (
                run_id,
                security_id,
                issuer_id,
                listing_id,
                related_security_id,
                related_listing_id,
                decision_type,
                rule_id,
                rule_version,
                confidence_code,
                confidence_score,
                previous_identity_status,
                evaluated_identity_status,
                explanation,
                reason_codes,
                details_json
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s::jsonb
            )
            RETURNING evaluation_id
            """,
            (
                evaluation.run_id,
                evaluation.security_id,
                evaluation.issuer_id,
                evaluation.listing_id,
                evaluation.related_security_id,
                evaluation.related_listing_id,
                evaluation.decision_type,
                evaluation.rule_id,
                evaluation.rule_version,
                evaluation.confidence_code,
                evaluation.confidence_score,
                evaluation.previous_identity_status,
                evaluation.evaluated_identity_status,
                evaluation.explanation,
                list(evaluation.reason_codes),
                json_dumps(dict(evaluation.details_json)),
            ),
        )
        evaluation_id = cursor.fetchone()[0]
        for link in evaluation.evidence_links:
            cursor.execute(
                """
                INSERT INTO stonks.security_reconciliation_evaluation_evidence (
                    evaluation_id,
                    provider_evidence_id,
                    evidence_role
                )
                VALUES (%s, %s, %s)
                """,
                (evaluation_id, link.provider_evidence_id, link.evidence_role),
            )

    connection.commit()
    return evaluation_id


def insert_security_reconciliation_decision(
    *,
    connection: Any,
    decision: SecurityReconciliationDecision,
) -> UUID:
    """Insert an immutable applied reconciliation decision row."""

    _validate_decision(decision)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO stonks.security_reconciliation_decision (
                evaluation_id,
                run_id,
                security_id,
                decision_type,
                previous_identity_status,
                new_identity_status,
                applied_by,
                explanation,
                details_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING decision_id
            """,
            (
                decision.evaluation_id,
                decision.run_id,
                decision.security_id,
                decision.decision_type,
                decision.previous_identity_status,
                decision.new_identity_status,
                decision.applied_by,
                decision.explanation,
                json_dumps(dict(decision.details_json)),
            ),
        )
        decision_id = cursor.fetchone()[0]

    connection.commit()
    return decision_id


def _validate_evaluation(evaluation: SecurityReconciliationEvaluation) -> None:
    _require_uuid("run_id", evaluation.run_id)
    _require_uuid("security_id", evaluation.security_id)
    _require_choice("decision_type", evaluation.decision_type, EVALUATION_DECISION_TYPES)
    _require_text("rule_id", evaluation.rule_id)
    _require_text("rule_version", evaluation.rule_version)
    _require_text("confidence_code", evaluation.confidence_code)
    _require_choice(
        "previous_identity_status",
        evaluation.previous_identity_status,
        IDENTITY_STATUSES,
    )
    _require_choice(
        "evaluated_identity_status",
        evaluation.evaluated_identity_status,
        IDENTITY_STATUSES,
    )
    _require_text("explanation", evaluation.explanation)
    if evaluation.confidence_score is not None:
        score = Decimal(str(evaluation.confidence_score))
        if score < 0 or score > 1:
            raise SecurityReconciliationAuditError("confidence_score must be between 0 and 1")
    for reason_code in evaluation.reason_codes:
        _require_text("reason_codes", reason_code)
    for link in evaluation.evidence_links:
        _require_uuid("provider_evidence_id", link.provider_evidence_id)
        _require_choice("evidence_role", link.evidence_role, EVIDENCE_ROLES)


def _validate_decision(decision: SecurityReconciliationDecision) -> None:
    _require_uuid("evaluation_id", decision.evaluation_id)
    _require_uuid("run_id", decision.run_id)
    _require_uuid("security_id", decision.security_id)
    _require_choice("decision_type", decision.decision_type, APPLIED_DECISION_TYPES)
    _require_choice(
        "previous_identity_status",
        decision.previous_identity_status,
        IDENTITY_STATUSES,
    )
    _require_choice("new_identity_status", decision.new_identity_status, IDENTITY_STATUSES)
    _require_text("explanation", decision.explanation)
    if (
        decision.previous_identity_status != IDENTITY_STATUS_PROVISIONAL
        or decision.new_identity_status != IDENTITY_STATUS_CONFIRMED
    ):
        raise SecurityReconciliationAuditError(
            "applied decisions currently support only PROVISIONAL -> CONFIRMED"
        )


def _require_uuid(field_name: str, value: UUID) -> None:
    if not isinstance(value, UUID):
        raise SecurityReconciliationAuditError(f"{field_name} is required")


def _require_text(field_name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise SecurityReconciliationAuditError(f"{field_name} is required")


def _require_choice(field_name: str, value: str, allowed_values: frozenset[str]) -> None:
    _require_text(field_name, value)
    if value not in allowed_values:
        allowed = ", ".join(sorted(allowed_values))
        raise SecurityReconciliationAuditError(
            f"{field_name} must be one of: {allowed}"
        )
