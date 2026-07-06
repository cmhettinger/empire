from __future__ import annotations

from dataclasses import FrozenInstanceError
from uuid import UUID, uuid4

import pytest

from empire_stonks_securities.reconciliation_audit import (
    APPLIED_DECISION_PROMOTE_TO_CONFIRMED,
    EVALUATION_DECISION_PROMOTION_CANDIDATE,
    EVIDENCE_ROLE_SUPPORTS,
    IDENTITY_STATUS_CONFIRMED,
    IDENTITY_STATUS_PROVISIONAL,
    EvaluationEvidenceLink,
    SecurityReconciliationAuditError,
    SecurityReconciliationDecision,
    SecurityReconciliationEvaluation,
    insert_security_reconciliation_decision,
    insert_security_reconciliation_evaluation,
)


def test_insert_evaluation_writes_append_only_audit_row_and_evidence_links():
    conn = FakeConnection()
    provider_evidence_id = uuid4()
    evaluation = evaluation_input(
        reason_codes=("ISSUER_MATCH", "STABLE_TICKER"),
        details_json={"source": "unit-test"},
        evidence_links=(
            EvaluationEvidenceLink(
                provider_evidence_id=provider_evidence_id,
                evidence_role=EVIDENCE_ROLE_SUPPORTS,
            ),
        ),
    )

    evaluation_id = insert_security_reconciliation_evaluation(
        connection=conn,
        evaluation=evaluation,
    )

    assert evaluation_id == conn.evaluation_id
    assert conn.commit_count == 1
    assert len(conn.statements) == 2
    assert "INSERT INTO stonks.security_reconciliation_evaluation" in conn.statements[0]
    assert "RETURNING evaluation_id" in conn.statements[0]
    assert "INSERT INTO stonks.security_reconciliation_evaluation_evidence" in conn.statements[1]
    assert conn.params[0] == (
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
        ["ISSUER_MATCH", "STABLE_TICKER"],
        '{"source": "unit-test"}',
    )
    assert conn.params[1] == (
        evaluation_id,
        provider_evidence_id,
        EVIDENCE_ROLE_SUPPORTS,
    )
    assert_only_append_sql(conn.statements)


def test_insert_decision_writes_append_only_applied_decision_row():
    conn = FakeConnection()
    decision = decision_input(details_json={"evaluation": "accepted"})

    decision_id = insert_security_reconciliation_decision(
        connection=conn,
        decision=decision,
    )

    assert decision_id == conn.decision_id
    assert conn.commit_count == 1
    assert len(conn.statements) == 1
    assert "INSERT INTO stonks.security_reconciliation_decision" in conn.statements[0]
    assert "RETURNING decision_id" in conn.statements[0]
    assert conn.params[0] == (
        decision.evaluation_id,
        decision.run_id,
        decision.security_id,
        decision.decision_type,
        decision.previous_identity_status,
        decision.new_identity_status,
        decision.applied_by,
        decision.explanation,
        '{"evaluation": "accepted"}',
    )
    assert_only_append_sql(conn.statements)


def test_evaluation_inputs_are_frozen():
    evaluation = evaluation_input()

    with pytest.raises(FrozenInstanceError):
        evaluation.explanation = "changed"


def test_decision_inputs_are_frozen():
    decision = decision_input()

    with pytest.raises(FrozenInstanceError):
        decision.explanation = "changed"


def test_evaluation_requires_core_fields_before_writing():
    conn = FakeConnection()
    evaluation = evaluation_input(rule_id="")

    with pytest.raises(SecurityReconciliationAuditError, match="rule_id is required"):
        insert_security_reconciliation_evaluation(connection=conn, evaluation=evaluation)

    assert conn.statements == []
    assert conn.commit_count == 0


def test_evaluation_rejects_invalid_confidence_score_before_writing():
    conn = FakeConnection()
    evaluation = evaluation_input(confidence_score="1.1")

    with pytest.raises(
        SecurityReconciliationAuditError,
        match="confidence_score must be between 0 and 1",
    ):
        insert_security_reconciliation_evaluation(connection=conn, evaluation=evaluation)

    assert conn.statements == []
    assert conn.commit_count == 0


def test_evaluation_rejects_invalid_evidence_role_before_writing():
    conn = FakeConnection()
    evaluation = evaluation_input(
        evidence_links=(EvaluationEvidenceLink(provider_evidence_id=uuid4(), evidence_role="BAD"),)
    )

    with pytest.raises(SecurityReconciliationAuditError, match="evidence_role must be one of"):
        insert_security_reconciliation_evaluation(connection=conn, evaluation=evaluation)

    assert conn.statements == []
    assert conn.commit_count == 0


def test_decision_requires_supported_one_way_transition_before_writing():
    conn = FakeConnection()
    decision = decision_input(
        previous_identity_status=IDENTITY_STATUS_CONFIRMED,
        new_identity_status=IDENTITY_STATUS_PROVISIONAL,
    )

    with pytest.raises(
        SecurityReconciliationAuditError,
        match="PROVISIONAL -> CONFIRMED",
    ):
        insert_security_reconciliation_decision(connection=conn, decision=decision)

    assert conn.statements == []
    assert conn.commit_count == 0


def evaluation_input(**overrides) -> SecurityReconciliationEvaluation:
    values = {
        "run_id": uuid4(),
        "security_id": uuid4(),
        "decision_type": EVALUATION_DECISION_PROMOTION_CANDIDATE,
        "rule_id": "sec-series-class-v1",
        "rule_version": "1.0.0",
        "confidence_code": "HIGH",
        "previous_identity_status": IDENTITY_STATUS_PROVISIONAL,
        "evaluated_identity_status": IDENTITY_STATUS_CONFIRMED,
        "explanation": "SEC evidence supports promotion.",
        "issuer_id": uuid4(),
        "listing_id": uuid4(),
        "related_security_id": None,
        "related_listing_id": None,
        "confidence_score": "0.99000",
    }
    values.update(overrides)
    return SecurityReconciliationEvaluation(**values)


def decision_input(**overrides) -> SecurityReconciliationDecision:
    values = {
        "evaluation_id": uuid4(),
        "run_id": uuid4(),
        "security_id": uuid4(),
        "decision_type": APPLIED_DECISION_PROMOTE_TO_CONFIRMED,
        "previous_identity_status": IDENTITY_STATUS_PROVISIONAL,
        "new_identity_status": IDENTITY_STATUS_CONFIRMED,
        "applied_by": "unit-test",
        "explanation": "Applied deterministic promotion.",
    }
    values.update(overrides)
    return SecurityReconciliationDecision(**values)


def assert_only_append_sql(statements: list[str]) -> None:
    joined = " ".join(statements).upper()
    assert "INSERT INTO" in joined
    assert "UPDATE " not in joined
    assert "DELETE " not in joined
    assert "ON CONFLICT" not in joined
    assert "UPDATED_AT" not in joined


class FakeConnection:
    def __init__(self) -> None:
        self.evaluation_id = uuid4()
        self.decision_id = uuid4()
        self.statements: list[str] = []
        self.params: list[tuple] = []
        self.commit_count = 0
        self.next_result: tuple[UUID] | None = None

    def cursor(self):
        return FakeCursor(self)

    def commit(self) -> None:
        self.commit_count += 1


class FakeCursor:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql: str, params=()) -> None:
        normalized = " ".join(sql.split())
        self.connection.statements.append(normalized)
        self.connection.params.append(params)
        if "RETURNING evaluation_id" in normalized:
            self.connection.next_result = (self.connection.evaluation_id,)
            return
        if "RETURNING decision_id" in normalized:
            self.connection.next_result = (self.connection.decision_id,)
            return
        self.connection.next_result = None

    def fetchone(self):
        return self.connection.next_result
