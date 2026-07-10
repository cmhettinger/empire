from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest

from empire_stonks_securities.reconciliation_evidence import (
    EVIDENCE_TYPE_SEC_ISSUER_SECURITY_MATCH,
    EVIDENCE_TYPE_SEC_SOURCE_SNAPSHOT_CONTINUITY,
    EVIDENCE_TYPE_SEC_TICKER_EXCHANGE_STABILITY,
    derive_security_reconciliation_evidence,
    select_provisional_security_evidence_inputs,
    write_derived_security_reconciliation_evidence,
)


SECURITY_ID = UUID("00000000-0000-0000-0000-000000000001")
ISSUER_ID = UUID("00000000-0000-0000-0000-000000000002")
ISSUER_IDENTIFIER_ID = UUID("00000000-0000-0000-0000-000000000003")
SECURITY_IDENTIFIER_ID = UUID("00000000-0000-0000-0000-000000000004")
LISTING_ID = UUID("00000000-0000-0000-0000-000000000005")
EXCHANGE_ID = UUID("00000000-0000-0000-0000-000000000006")
PROVIDER_EVIDENCE_ID = UUID("00000000-0000-0000-0000-000000000007")
PROVIDER_OBSERVATION_ID = UUID("00000000-0000-0000-0000-000000000008")
SNAPSHOT_ID = UUID("00000000-0000-0000-0000-000000000009")
OBSERVED_AT = datetime(2026, 7, 10, 12, tzinfo=UTC)


def test_selects_deterministic_provisional_security_evidence_inputs():
    conn = FakeConnection([_row()])

    first = select_provisional_security_evidence_inputs(connection=conn, limit=10)
    second = select_provisional_security_evidence_inputs(connection=conn, limit=10)

    assert first == second
    assert len(first) == 1
    evidence_input = first[0]
    assert evidence_input.security_id == SECURITY_ID
    assert evidence_input.issuer_cik == "0000320193"
    assert evidence_input.issuer_identifiers[0].id_value == "0000320193"
    assert evidence_input.security_identifiers[0].id_value == "AAPL"
    assert evidence_input.listings[0].exchange_code == "NASDAQ"
    support = evidence_input.supporting_observations[0]
    assert support.provider_evidence_id == PROVIDER_EVIDENCE_ID
    assert support.source_snapshot_id == SNAPSHOT_ID
    assert support.content_sha256 == "a" * 64

    assert "s.identity_status = %s" in conn.executed_sql
    assert "FROM stonks.provider_evidence pe" in conn.executed_sql
    assert "JOIN stonks.provider_observation po" in conn.executed_sql
    assert "LEFT JOIN stonks.provider_source_snapshot pss" in conn.executed_sql
    assert "FROM stonks.issuer_identifier ii" in conn.executed_sql
    assert "FROM stonks.security_identifier si" in conn.executed_sql
    assert "FROM stonks.listing l" in conn.executed_sql
    assert "ORDER BY s.last_seen DESC NULLS LAST, s.security_id" in conn.executed_sql
    assert "ORDER BY po.observed_at NULLS LAST, po.created_at" in conn.executed_sql
    assert conn.params[0] == "PROVISIONAL"
    assert set(conn.params[1]) == {"SEC_COMPANY_TICKERS", "SEC_COMPANY_TICKERS_EXCHANGE"}
    assert conn.params[2] == 10


def test_selection_does_not_skip_already_derived_evidence():
    conn = FakeConnection([])

    select_provisional_security_evidence_inputs(connection=conn)

    assert "security_reconciliation_evidence" not in conn.executed_sql
    assert conn.params[0] == "PROVISIONAL"
    assert set(conn.params[1]) == {"SEC_COMPANY_TICKERS", "SEC_COMPANY_TICKERS_EXCHANGE"}


def test_rejects_negative_limit():
    with pytest.raises(ValueError, match="non-negative"):
        select_provisional_security_evidence_inputs(connection=FakeConnection([]), limit=-1)


def test_derives_stable_sec_evidence_with_distinct_snapshot_counts():
    row = _row()
    row["supporting_observations"][0]["summary_json"]["exchange"] = "NASDAQ"
    row["supporting_observations"].append(
        {
            **row["supporting_observations"][0],
            "provider_evidence_id": uuid4(),
            "provider_observation_id": uuid4(),
            "source_snapshot_id": uuid4(),
            "content_sha256": "b" * 64,
            "observed_at": datetime(2026, 7, 11, 12, tzinfo=UTC),
        }
    )
    evidence_input = select_provisional_security_evidence_inputs(
        connection=FakeConnection([row])
    )[0]

    first = derive_security_reconciliation_evidence(evidence_input)
    second = derive_security_reconciliation_evidence(evidence_input)

    assert first == second
    assert {item.evidence_type for item in first} == {
        EVIDENCE_TYPE_SEC_ISSUER_SECURITY_MATCH,
        EVIDENCE_TYPE_SEC_TICKER_EXCHANGE_STABILITY,
        EVIDENCE_TYPE_SEC_SOURCE_SNAPSHOT_CONTINUITY,
    }
    stability = next(item for item in first if item.evidence_type == EVIDENCE_TYPE_SEC_TICKER_EXCHANGE_STABILITY)
    assert stability.summary_json["normalized_values"]["distinct_snapshot_count"] == 2
    assert stability.summary_json["normalized_values"]["insufficient_repeat"] is False


def test_writer_reuses_existing_evidence_and_does_not_duplicate_lineage_bridges():
    evidence_input = select_provisional_security_evidence_inputs(
        connection=FakeConnection([_row()])
    )[0]
    evidence = derive_security_reconciliation_evidence(evidence_input)[0]
    existing_id = uuid4()
    conn = WriterConnection([(existing_id,), None, (existing_id,)])

    first = write_derived_security_reconciliation_evidence(connection=conn, evidence=evidence)
    second = write_derived_security_reconciliation_evidence(connection=conn, evidence=evidence)

    assert first == type(first)(existing_id, True)
    assert second == type(second)(existing_id, False)
    assert conn.commits == 2
    joined = " ".join(conn.executed_sql)
    assert "ON CONFLICT ON CONSTRAINT uq_sec_recon_evidence_identity DO NOTHING" in joined
    assert joined.count("security_reconciliation_evidence_provider_evidence") == 2
    assert joined.count("security_reconciliation_evidence_source_snapshot") == 2


def _row() -> dict:
    return {
        "security_id": SECURITY_ID,
        "issuer_id": ISSUER_ID,
        "issuer_cik": "0000320193",
        "security_title": "Apple Inc.",
        "instrument_type_code": "UNKNOWN",
        "first_seen": date(2026, 7, 9),
        "last_seen": date(2026, 7, 10),
        "issuer_identifiers": [
            {
                "identifier_id": ISSUER_IDENTIFIER_ID,
                "id_type": "CIK",
                "id_value": "0000320193",
                "valid_from": date(2026, 7, 9),
                "valid_to": None,
                "source_code": "SEC",
                "confidence_code": "HIGH",
            }
        ],
        "security_identifiers": [
            {
                "identifier_id": SECURITY_IDENTIFIER_ID,
                "id_type": "TICKER",
                "id_value": "AAPL",
                "valid_from": date(2026, 7, 9),
                "valid_to": None,
                "source_code": "SEC",
                "confidence_code": "MEDIUM",
            }
        ],
        "listings": [
            {
                "listing_id": LISTING_ID,
                "exchange_id": EXCHANGE_ID,
                "exchange_code": "NASDAQ",
                "ticker_norm": "AAPL",
                "status": "ACTIVE",
                "valid_from": date(2026, 7, 9),
                "valid_to": None,
                "first_seen": date(2026, 7, 9),
                "last_seen": date(2026, 7, 10),
            }
        ],
        "supporting_observations": [
            {
                "provider_evidence_id": PROVIDER_EVIDENCE_ID,
                "provider_observation_id": PROVIDER_OBSERVATION_ID,
                "provider_code": "SEC_COMPANY_TICKERS_EXCHANGE",
                "provider_date": date(2026, 7, 10),
                "observed_at": OBSERVED_AT,
                "summary_json": {"cik_padded": "0000320193", "ticker_norm": "AAPL"},
                "source_snapshot_id": SNAPSHOT_ID,
                "source_code": "sec_company_tickers_exchange",
                "content_sha256": "a" * 64,
                "snapshot_created_at": OBSERVED_AT,
            }
        ],
    }


class FakeConnection:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.executed_sql = ""
        self.params = None

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)


class FakeCursor:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        return False

    def execute(self, sql: str, params=None) -> None:
        self.connection.executed_sql = " ".join(sql.split())
        self.connection.params = params

    def fetchall(self) -> list[dict]:
        return self.connection.rows


class WriterConnection:
    def __init__(self, fetchone_rows) -> None:
        self.fetchone_rows = list(fetchone_rows)
        self.executed_sql: list[str] = []
        self.commits = 0

    def cursor(self) -> "WriterCursor":
        return WriterCursor(self)

    def commit(self) -> None:
        self.commits += 1


class WriterCursor:
    def __init__(self, connection: WriterConnection) -> None:
        self.connection = connection

    def __enter__(self) -> "WriterCursor":
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        return False

    def execute(self, sql: str, params=None) -> None:
        self.connection.executed_sql.append(" ".join(sql.split()))

    def fetchone(self):
        return self.connection.fetchone_rows.pop(0) if self.connection.fetchone_rows else None
