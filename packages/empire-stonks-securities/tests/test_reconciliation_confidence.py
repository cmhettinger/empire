from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from empire_stonks_securities.reconciliation_confidence import (
    CONFIDENCE_PROFILE_BACKFILL,
    CONFIDENCE_PROFILE_DAILY,
    POLICY_ID_BACKFILL,
    POLICY_ID_DAILY,
    REFUSAL_INSUFFICIENT_BACKFILL_TIME_SPAN,
    StoredReconciliationEvidence,
    evaluate_security_confidence,
)
from empire_stonks_securities.reconciliation_evidence import (
    EVIDENCE_TYPE_SEC_ISSUER_SECURITY_MATCH,
    EVIDENCE_TYPE_SEC_SOURCE_SNAPSHOT_CONTINUITY,
    EVIDENCE_TYPE_SEC_TICKER_EXCHANGE_STABILITY,
)


SECURITY_ID = UUID("00000000-0000-0000-0000-000000000001")
ISSUER_ID = UUID("00000000-0000-0000-0000-000000000002")
LISTING_ID = UUID("00000000-0000-0000-0000-000000000003")


def test_daily_profile_is_deterministic_and_ready_with_two_snapshots():
    evidence = _evidence(snapshot_count=2, span_days=1)

    first = evaluate_security_confidence(
        security_id=SECURITY_ID, identity_status="PROVISIONAL",
        profile=CONFIDENCE_PROFILE_DAILY, evidence=reversed(evidence),
    )
    second = evaluate_security_confidence(
        security_id=SECURITY_ID, identity_status="PROVISIONAL",
        profile=CONFIDENCE_PROFILE_DAILY, evidence=evidence,
    )

    assert first == second
    assert first.policy_id == POLICY_ID_DAILY
    assert first.score == 70
    assert first.confidence_level == "HIGH"
    assert first.continuity_ready is True
    assert first.blocked is False
    assert first.refusal_reasons == ()
    assert first.evidence_ids == tuple(sorted((item.reconciliation_evidence_id for item in evidence), key=str))


def test_backfill_profile_requires_three_snapshots_over_thirty_days():
    result = evaluate_security_confidence(
        security_id=SECURITY_ID, identity_status="PROVISIONAL",
        profile=CONFIDENCE_PROFILE_BACKFILL, evidence=_evidence(snapshot_count=3, span_days=30),
    )

    assert result.policy_id == POLICY_ID_BACKFILL
    assert result.score == 70
    assert result.confidence_level == "HIGH"
    assert result.continuity_ready is True
    assert result.refusal_reasons == ()


def test_backfill_reports_short_span_refusal_without_changing_score_from_other_rules():
    result = evaluate_security_confidence(
        security_id=SECURITY_ID, identity_status="PROVISIONAL",
        profile=CONFIDENCE_PROFILE_BACKFILL, evidence=_evidence(snapshot_count=3, span_days=29),
    )

    assert result.score == 50
    assert result.confidence_level == "MEDIUM"
    assert result.continuity_ready is False
    assert result.refusal_reasons == (REFUSAL_INSUFFICIENT_BACKFILL_TIME_SPAN,)


def test_rejects_unknown_profile_and_evidence_for_another_security():
    with pytest.raises(ValueError, match="daily.*backfill"):
        evaluate_security_confidence(security_id=SECURITY_ID, identity_status="PROVISIONAL", profile="weekly", evidence=())
    with pytest.raises(ValueError, match="belong"):
        evaluate_security_confidence(
            security_id=UUID("00000000-0000-0000-0000-000000000099"),
            identity_status="PROVISIONAL", profile=CONFIDENCE_PROFILE_DAILY, evidence=_evidence(2, 1),
        )


def test_conflicting_or_inconsistent_stored_evidence_blocks_the_result():
    evidence = list(_evidence(snapshot_count=2, span_days=1))
    evidence[1] = replace(evidence[1], evidence_role="CONFLICTS")
    evidence[2] = replace(
        evidence[2],
        issuer_id=UUID("00000000-0000-0000-0000-000000000004"),
    )

    result = evaluate_security_confidence(
        security_id=SECURITY_ID, identity_status="PROVISIONAL",
        profile=CONFIDENCE_PROFILE_DAILY, evidence=evidence,
    )

    assert result.blocked is True
    assert result.continuity_ready is False
    assert result.refusal_reasons == (
        "conflicting_sec_identity_evidence",
        "inconsistent_supporting_evidence",
        "insufficient_ticker_exchange_repetition",
    )


def test_invalid_lineage_blocks_and_cannot_contribute_score():
    evidence = list(_evidence(snapshot_count=2, span_days=1))
    evidence[1] = replace(evidence[1], source_snapshot_ids=())

    result = evaluate_security_confidence(
        security_id=SECURITY_ID, identity_status="PROVISIONAL",
        profile=CONFIDENCE_PROFILE_DAILY, evidence=evidence,
    )

    assert result.blocked is True
    assert result.score == 45
    assert "incomplete_evidence_lineage" in result.refusal_reasons


def _evidence(snapshot_count: int, span_days: int) -> tuple[StoredReconciliationEvidence, ...]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(days=span_days)
    snapshots = tuple(UUID(f"00000000-0000-0000-0000-0000000000{index:02d}") for index in range(10, 10 + snapshot_count))
    provider_ids = (UUID("00000000-0000-0000-0000-000000000020"),)
    return (
        StoredReconciliationEvidence(UUID("00000000-0000-0000-0000-000000000010"), SECURITY_ID, ISSUER_ID, None,
            EVIDENCE_TYPE_SEC_ISSUER_SECURITY_MATCH, "SUPPORTS", {"normalized_values": {"issuer_cik": "0000320193"}}, provider_ids, snapshots),
        StoredReconciliationEvidence(UUID("00000000-0000-0000-0000-000000000011"), SECURITY_ID, ISSUER_ID, LISTING_ID,
            EVIDENCE_TYPE_SEC_TICKER_EXCHANGE_STABILITY, "SUPPORTS", {"normalized_values": {"ticker": "AAPL", "exchange": "NASDAQ", "distinct_snapshot_count": snapshot_count, "insufficient_repeat": False}}, provider_ids, snapshots),
        StoredReconciliationEvidence(UUID("00000000-0000-0000-0000-000000000012"), SECURITY_ID, ISSUER_ID, LISTING_ID,
            EVIDENCE_TYPE_SEC_SOURCE_SNAPSHOT_CONTINUITY, "SUPPORTS", {"normalized_values": {"ticker": "AAPL", "exchange": "NASDAQ", "distinct_snapshot_count": snapshot_count}, "first_observed_at": start.isoformat(), "last_observed_at": end.isoformat()}, provider_ids, snapshots),
    )
