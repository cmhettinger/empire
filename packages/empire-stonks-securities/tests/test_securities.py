from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from empire_stonks_securities.securities import (
    PROVISIONAL_INSTRUMENT_TYPE,
    SECURITY_IDENTIFIER_CONFIDENCE,
    SecSecurityObservation,
    select_sec_security_observations,
    upsert_sec_securities,
)


OBSERVED_AT = datetime(2026, 6, 18, 12, 30, tzinfo=UTC)


def test_creates_security_from_ticker_exchange_observation():
    conn = FakeConnection()
    issuer_id = conn.add_issuer("0000320193", "Apple Inc.")
    observation = security_observation(provider_code="SEC_COMPANY_TICKERS_EXCHANGE")
    conn.add_issuer_evidence(observation.provider_observation_id, issuer_id)

    result = upsert_sec_securities(connection=conn, observations=[observation])

    assert result.securities_created == 1
    assert result.security_identifiers_inserted == 1
    assert result.evidence_inserted == 1
    security = next(iter(conn.securities.values()))
    assert security["issuer_id"] == issuer_id
    assert security["instrument_type_code"] == PROVISIONAL_INSTRUMENT_TYPE
    assert security["security_title"] == "Apple Inc."
    assert conn.security_identifiers[0]["id_value"] == "AAPL"
    assert conn.security_identifiers[0]["confidence_code"] == SECURITY_IDENTIFIER_CONFIDENCE


def test_creates_security_from_ticker_observation():
    conn = FakeConnection()
    issuer_id = conn.add_issuer("0000320193", "Apple Inc.")
    observation = security_observation(provider_code="SEC_COMPANY_TICKERS")
    conn.add_issuer_evidence(observation.provider_observation_id, issuer_id)

    result = upsert_sec_securities(connection=conn, observations=[observation])

    assert result.securities_created == 1
    assert next(iter(conn.securities.values()))["issuer_id"] == issuer_id


def test_resolves_issuer_using_evidence_link():
    conn = FakeConnection()
    issuer_id = conn.add_issuer("0000320193", "Apple Inc.")
    observation = security_observation()
    conn.add_issuer_evidence(observation.provider_observation_id, issuer_id)

    result = upsert_sec_securities(connection=conn, observations=[observation])

    assert result.issuers_resolved == 1
    assert next(iter(conn.securities.values()))["issuer_id"] == issuer_id


def test_falls_back_to_issuer_by_cik_without_evidence():
    conn = FakeConnection()
    issuer_id = conn.add_issuer("0000320193", "Apple Inc.")

    result = upsert_sec_securities(connection=conn, observations=[security_observation()])

    assert result.issuers_resolved == 1
    assert next(iter(conn.securities.values()))["issuer_id"] == issuer_id


def test_same_cik_ticker_from_both_sources_resolves_to_same_security():
    conn = FakeConnection()
    issuer_id = conn.add_issuer("0000320193", "Apple Inc.")
    first = security_observation(provider_code="SEC_COMPANY_TICKERS_EXCHANGE")
    second = security_observation(
        provider_observation_id=uuid4(),
        provider_code="SEC_COMPANY_TICKERS",
    )
    conn.add_issuer_evidence(first.provider_observation_id, issuer_id)
    conn.add_issuer_evidence(second.provider_observation_id, issuer_id)

    result = upsert_sec_securities(connection=conn, observations=[first, second])

    assert result.securities_created == 1
    assert result.security_identifiers_inserted == 1
    assert result.security_identifiers_skipped == 1
    assert len(conn.securities) == 1
    assert len(conn.provider_evidence) == 4


def test_same_issuer_with_two_tickers_creates_two_securities():
    conn = FakeConnection()
    issuer_id = conn.add_issuer("0000320193", "Apple Inc.")
    first = security_observation(ticker_norm="AAPL")
    second = security_observation(provider_observation_id=uuid4(), ticker_norm="AAPLW")
    conn.add_issuer_evidence(first.provider_observation_id, issuer_id)
    conn.add_issuer_evidence(second.provider_observation_id, issuer_id)

    result = upsert_sec_securities(connection=conn, observations=[first, second])

    assert result.securities_created == 2
    assert {row["id_value"] for row in conn.security_identifiers} == {"AAPL", "AAPLW"}


def test_same_ticker_with_two_issuers_does_not_merge_securities():
    conn = FakeConnection()
    apple_id = conn.add_issuer("0000320193", "Apple Inc.")
    other_id = conn.add_issuer("0000000002", "Other AAPL Issuer")
    first = security_observation(cik=320193, cik_padded="0000320193", ticker_norm="AAPL")
    second = security_observation(
        provider_observation_id=uuid4(),
        cik=2,
        cik_padded="0000000002",
        ticker_norm="AAPL",
        company_name="Other AAPL Issuer",
    )
    conn.add_issuer_evidence(first.provider_observation_id, apple_id)
    conn.add_issuer_evidence(second.provider_observation_id, other_id)

    result = upsert_sec_securities(connection=conn, observations=[first, second])

    assert result.securities_created == 2
    assert {row["issuer_id"] for row in conn.securities.values()} == {apple_id, other_id}


def test_writes_evidence_link_from_observation_to_security():
    conn = FakeConnection()
    issuer_id = conn.add_issuer("0000320193", "Apple Inc.")
    observation = security_observation()
    conn.add_issuer_evidence(observation.provider_observation_id, issuer_id)

    upsert_sec_securities(connection=conn, observations=[observation])

    security_evidence = [
        row for row in conn.provider_evidence if row["security_id"] is not None
    ][0]
    assert security_evidence["provider_observation_id"] == observation.provider_observation_id
    assert security_evidence["issuer_id"] == issuer_id
    assert security_evidence["listing_id"] is None
    assert security_evidence["event_id"] is None


def test_rerun_is_idempotent():
    conn = FakeConnection()
    issuer_id = conn.add_issuer("0000320193", "Apple Inc.")
    observation = security_observation()
    conn.add_issuer_evidence(observation.provider_observation_id, issuer_id)

    first = upsert_sec_securities(connection=conn, observations=[observation])
    second = upsert_sec_securities(connection=conn, observations=[observation])

    assert first.securities_created == 1
    assert second.securities_created == 0
    assert second.security_identifiers_skipped == 1
    assert second.evidence_skipped == 1
    assert len(conn.securities) == 1
    assert len(conn.security_identifiers) == 1
    assert len([row for row in conn.provider_evidence if row["security_id"] is not None]) == 1


def test_does_not_create_listing_rows_or_symbol_history():
    conn = FakeConnection()
    issuer_id = conn.add_issuer("0000320193", "Apple Inc.")
    observation = security_observation()
    conn.add_issuer_evidence(observation.provider_observation_id, issuer_id)

    upsert_sec_securities(connection=conn, observations=[observation])

    assert conn.listing_writes == 0
    assert conn.listing_symbol_history_writes == 0


def test_does_not_assume_common_stock():
    conn = FakeConnection()
    issuer_id = conn.add_issuer("0000320193", "Apple Inc.")
    observation = security_observation()
    conn.add_issuer_evidence(observation.provider_observation_id, issuer_id)

    upsert_sec_securities(connection=conn, observations=[observation])

    assert next(iter(conn.securities.values()))["instrument_type_code"] == "UNKNOWN"


def test_security_selector_uses_reconciliation_state_not_run_scope():
    conn = FakeSelectConnection()

    observations = select_sec_security_observations(
        connection=conn,
        source_run_id=uuid4(),
        limit=10,
    )

    assert observations == []
    assert "core.stored_object" not in conn.executed_sql
    assert "so.run_id" not in conn.executed_sql
    assert "NOT EXISTS" in conn.executed_sql
    assert "pe.security_id IS NOT NULL" in conn.executed_sql
    assert "pe.listing_id IS NULL" in conn.executed_sql
    assert "pe.created_at >= po.created_at" in conn.executed_sql
    assert set(conn.params[0]) == {"SEC_COMPANY_TICKERS", "SEC_COMPANY_TICKERS_EXCHANGE"}
    assert conn.params[1] == 10


def security_observation(
    *,
    provider_observation_id: UUID | None = None,
    provider_code: str = "SEC_COMPANY_TICKERS_EXCHANGE",
    provider_date: date | None = date(2026, 6, 18),
    cik: int | None = 320193,
    cik_padded: str | None = "0000320193",
    ticker_norm: str | None = "AAPL",
    company_name: str | None = "Apple Inc.",
) -> SecSecurityObservation:
    summary_json = {"source_code": "sec_company_tickers_exchange"}
    if cik is not None:
        summary_json["cik"] = cik
    if cik_padded is not None:
        summary_json["cik_padded"] = cik_padded
    if ticker_norm is not None:
        summary_json["ticker_norm"] = ticker_norm
        summary_json["ticker"] = ticker_norm.lower()
    if company_name is not None:
        summary_json["company_name"] = company_name
    return SecSecurityObservation(
        provider_observation_id=provider_observation_id or uuid4(),
        provider_code=provider_code,
        provider_date=provider_date,
        observed_at=OBSERVED_AT,
        summary_json=summary_json,
    )


class FakeConnection:
    def __init__(self) -> None:
        self.issuers: dict[UUID, dict] = {}
        self.securities: dict[UUID, dict] = {}
        self.security_identifiers: list[dict] = []
        self.provider_evidence: list[dict] = []
        self.listing_writes = 0
        self.listing_symbol_history_writes = 0
        self.commit_count = 0
        self.last_result = None

    def add_issuer(self, cik: str, current_name: str) -> UUID:
        issuer_id = uuid4()
        self.issuers[issuer_id] = {
            "issuer_id": issuer_id,
            "cik": cik,
            "current_name": current_name,
        }
        return issuer_id

    def add_issuer_evidence(self, provider_observation_id: UUID, issuer_id: UUID) -> None:
        self.provider_evidence.append(
            {
                "provider_evidence_id": uuid4(),
                "provider_observation_id": provider_observation_id,
                "issuer_id": issuer_id,
                "security_id": None,
                "listing_id": None,
                "event_id": None,
                "evidence_role": "CREATED_FROM",
                "notes": "issuer evidence",
            }
        )

    def cursor(self):
        return FakeCursor(self)

    def commit(self) -> None:
        self.commit_count += 1


class FakeSelectConnection:
    def __init__(self) -> None:
        self.executed_sql = ""
        self.params = None

    def cursor(self):
        return FakeSelectCursor(self)


class FakeSelectCursor:
    def __init__(self, connection: FakeSelectConnection) -> None:
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql: str, params=None) -> None:
        self.connection.executed_sql = " ".join(sql.split())
        self.connection.params = params

    def fetchall(self):
        return []


class FakeCursor:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql: str, params=None) -> None:
        normalized = " ".join(sql.split())
        if "stonks.listing_symbol_history" in normalized:
            self.connection.listing_symbol_history_writes += 1
        if "INSERT INTO stonks.listing" in normalized or "UPDATE stonks.listing" in normalized:
            self.connection.listing_writes += 1

        if "FROM stonks.provider_evidence" in normalized and "issuer_id IS NOT NULL" in normalized:
            provider_observation_id = params[0]
            self.connection.last_result = next(
                (
                    (row["issuer_id"],)
                    for row in self.connection.provider_evidence
                    if row["provider_observation_id"] == provider_observation_id
                    and row["issuer_id"] is not None
                    and row["security_id"] is None
                    and row["listing_id"] is None
                    and row["event_id"] is None
                ),
                None,
            )
            return

        if "FROM stonks.issuer WHERE cik" in normalized:
            cik = params[0]
            self.connection.last_result = next(
                (
                    (issuer["issuer_id"],)
                    for issuer in self.connection.issuers.values()
                    if issuer["cik"] == cik
                ),
                None,
            )
            return

        if "JOIN stonks.security_identifier" in normalized:
            issuer_id, ticker_norm = params
            identifier = next(
                (
                    row
                    for row in self.connection.security_identifiers
                    if row["id_type"] == "TICKER" and row["id_value"] == ticker_norm
                ),
                None,
            )
            security = (
                self.connection.securities.get(identifier["security_id"])
                if identifier is not None
                else None
            )
            self.connection.last_result = (
                security if security is not None and security["issuer_id"] == issuer_id else None
            )
            return

        if "INSERT INTO stonks.security (" in normalized:
            security_id = uuid4()
            self.connection.securities[security_id] = {
                "security_id": security_id,
                "issuer_id": params[0],
                "instrument_type_code": params[1],
                "security_title": params[2],
                "first_seen": params[3],
                "last_seen": params[4],
            }
            self.connection.last_result = (security_id,)
            return

        if "UPDATE stonks.security SET" in normalized:
            security_id = params[5]
            security = self.connection.securities[security_id]
            if params[0] is not None:
                security["security_title"] = params[1]
            if params[2] is not None:
                security["last_seen"] = max(security["last_seen"] or params[3], params[4])
            self.connection.last_result = None
            return

        if "INSERT INTO stonks.security_identifier" in normalized:
            security_id, ticker_norm, valid_from, provider_code, confidence_code = params
            existing = next(
                (
                    row
                    for row in self.connection.security_identifiers
                    if row["security_id"] == security_id
                    and row["id_type"] == "TICKER"
                    and row["id_value"] == ticker_norm
                ),
                None,
            )
            if existing is not None:
                self.connection.last_result = None
                return
            identifier_id = uuid4()
            self.connection.security_identifiers.append(
                {
                    "security_identifier_id": identifier_id,
                    "security_id": security_id,
                    "id_type": "TICKER",
                    "id_value": ticker_norm,
                    "valid_from": valid_from,
                    "provider_code": provider_code,
                    "confidence_code": confidence_code,
                }
            )
            self.connection.last_result = (identifier_id,)
            return

        if "FROM stonks.provider_evidence" in normalized and "security_id =" in normalized:
            provider_observation_id, security_id = params
            self.connection.last_result = next(
                (
                    row
                    for row in self.connection.provider_evidence
                    if row["provider_observation_id"] == provider_observation_id
                    and row["security_id"] == security_id
                    and row["listing_id"] is None
                    and row["event_id"] is None
                ),
                None,
            )
            return

        if "INSERT INTO stonks.provider_evidence" in normalized:
            provider_observation_id, issuer_id, security_id, evidence_role, notes = params
            evidence_id = uuid4()
            self.connection.provider_evidence.append(
                {
                    "provider_evidence_id": evidence_id,
                    "provider_observation_id": provider_observation_id,
                    "issuer_id": issuer_id,
                    "security_id": security_id,
                    "listing_id": None,
                    "event_id": None,
                    "evidence_role": evidence_role,
                    "notes": notes,
                }
            )
            self.connection.last_result = (evidence_id,)
            return

        raise AssertionError(f"Unexpected SQL: {normalized}")

    def fetchone(self):
        return self.connection.last_result
