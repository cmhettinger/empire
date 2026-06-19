from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from empire_stonks_securities.issuers import (
    SecIssuerObservation,
    upsert_sec_issuers,
)


OBSERVED_AT = datetime(2026, 6, 18, 12, 30, tzinfo=UTC)


def test_creates_issuer_from_ticker_exchange_observation():
    conn = FakeConnection()

    result = upsert_sec_issuers(
        connection=conn,
        observations=[issuer_observation(provider_code="SEC_COMPANY_TICKERS_EXCHANGE")],
    )

    assert result.to_dict() == {
        "observations_scanned": 1,
        "observations_skipped": 0,
        "issuers_created": 1,
        "issuers_updated": 0,
        "issuer_identifiers_inserted": 1,
        "issuer_identifiers_skipped": 0,
        "name_history_inserted": 1,
        "name_history_skipped": 0,
        "evidence_inserted": 1,
        "evidence_skipped": 0,
        "warning_count": 0,
    }
    issuer = next(iter(conn.issuers.values()))
    assert issuer["cik"] == "0000320193"
    assert issuer["current_name"] == "Apple Inc."
    assert conn.issuer_identifiers[0]["id_type"] == "CIK"
    assert conn.issuer_identifiers[0]["id_value"] == "0000320193"
    assert conn.provider_evidence[0]["issuer_id"] == issuer["issuer_id"]


def test_creates_issuer_from_ticker_observation():
    conn = FakeConnection()

    result = upsert_sec_issuers(
        connection=conn,
        observations=[issuer_observation(provider_code="SEC_COMPANY_TICKERS")],
    )

    assert result.issuers_created == 1
    assert result.issuer_identifiers_inserted == 1
    assert next(iter(conn.issuers.values()))["cik"] == "0000320193"


def test_rerun_is_idempotent():
    conn = FakeConnection()
    observation = issuer_observation()

    first = upsert_sec_issuers(connection=conn, observations=[observation])
    second = upsert_sec_issuers(connection=conn, observations=[observation])

    assert first.issuers_created == 1
    assert second.issuers_created == 0
    assert second.issuer_identifiers_skipped == 1
    assert second.name_history_skipped == 1
    assert second.evidence_skipped == 1
    assert len(conn.issuers) == 1
    assert len(conn.issuer_identifiers) == 1
    assert len(conn.issuer_name_history) == 1
    assert len(conn.provider_evidence) == 1


def test_same_cik_from_both_sources_resolves_to_same_issuer():
    conn = FakeConnection()

    result = upsert_sec_issuers(
        connection=conn,
        observations=[
            issuer_observation(
                provider_observation_id=uuid4(),
                provider_code="SEC_COMPANY_TICKERS_EXCHANGE",
            ),
            issuer_observation(
                provider_observation_id=uuid4(),
                provider_code="SEC_COMPANY_TICKERS",
            ),
        ],
    )

    assert result.issuers_created == 1
    assert len(conn.issuers) == 1
    assert len(conn.provider_evidence) == 2


def test_different_company_names_for_same_cik_preserve_name_history():
    conn = FakeConnection()

    result = upsert_sec_issuers(
        connection=conn,
        observations=[
            issuer_observation(company_name="Apple Inc.", provider_date=date(2026, 6, 18)),
            issuer_observation(
                provider_observation_id=uuid4(),
                company_name="Apple Computer Inc.",
                provider_date=date(2026, 6, 19),
            ),
        ],
    )

    assert result.issuers_created == 1
    assert result.issuers_updated == 1
    assert result.name_history_inserted == 2
    assert {row["name"] for row in conn.issuer_name_history} == {
        "Apple Inc.",
        "Apple Computer Inc.",
    }
    assert next(iter(conn.issuers.values()))["current_name"] == "Apple Computer Inc."


def test_writes_evidence_link_from_observation_to_issuer():
    conn = FakeConnection()
    observation = issuer_observation()

    upsert_sec_issuers(connection=conn, observations=[observation])

    evidence = conn.provider_evidence[0]
    assert evidence["provider_observation_id"] == observation.provider_observation_id
    assert evidence["issuer_id"] == next(iter(conn.issuers.values()))["issuer_id"]
    assert evidence["security_id"] is None
    assert evidence["listing_id"] is None
    assert evidence["event_id"] is None


def test_does_not_create_security_or_listing_rows():
    conn = FakeConnection()

    upsert_sec_issuers(connection=conn, observations=[issuer_observation()])

    assert conn.security_writes == 0
    assert conn.listing_writes == 0


def test_missing_cik_is_skipped_and_logged_in_counts():
    conn = FakeConnection()

    result = upsert_sec_issuers(
        connection=conn,
        observations=[issuer_observation(cik=None, cik_padded=None)],
    )

    assert result.observations_scanned == 1
    assert result.observations_skipped == 1
    assert result.warning_count == 1
    assert len(conn.issuers) == 0


def test_missing_company_name_preserves_existing_issuer_name():
    conn = FakeConnection()
    upsert_sec_issuers(
        connection=conn,
        observations=[issuer_observation(company_name="Apple Inc.")],
    )

    result = upsert_sec_issuers(
        connection=conn,
        observations=[
            issuer_observation(
                provider_observation_id=uuid4(),
                company_name=None,
            )
        ],
    )

    issuer = next(iter(conn.issuers.values()))
    assert result.issuers_updated == 0
    assert result.name_history_skipped == 1
    assert issuer["current_name"] == "Apple Inc."


def issuer_observation(
    *,
    provider_observation_id: UUID | None = None,
    provider_code: str = "SEC_COMPANY_TICKERS_EXCHANGE",
    provider_date: date | None = date(2026, 6, 18),
    cik: int | None = 320193,
    cik_padded: str | None = "0000320193",
    company_name: str | None = "Apple Inc.",
) -> SecIssuerObservation:
    summary_json = {
        "source_code": "sec_company_tickers_exchange",
        "ticker": "AAPL",
        "ticker_norm": "AAPL",
    }
    if cik is not None:
        summary_json["cik"] = cik
    if cik_padded is not None:
        summary_json["cik_padded"] = cik_padded
    if company_name is not None:
        summary_json["company_name"] = company_name
    return SecIssuerObservation(
        provider_observation_id=provider_observation_id or uuid4(),
        provider_code=provider_code,
        provider_date=provider_date,
        observed_at=OBSERVED_AT,
        summary_json=summary_json,
    )


class FakeConnection:
    def __init__(self) -> None:
        self.issuers: dict[UUID, dict] = {}
        self.issuer_identifiers: list[dict] = []
        self.issuer_name_history: list[dict] = []
        self.provider_evidence: list[dict] = []
        self.security_writes = 0
        self.listing_writes = 0
        self.commit_count = 0
        self.last_result = None

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

    def execute(self, sql: str, params=None) -> None:
        normalized = " ".join(sql.split())
        if "stonks.security" in normalized:
            self.connection.security_writes += 1
        if "stonks.listing" in normalized:
            self.connection.listing_writes += 1

        if "FROM stonks.issuer WHERE cik" in normalized:
            cik = params[0]
            self.connection.last_result = next(
                (issuer for issuer in self.connection.issuers.values() if issuer["cik"] == cik),
                None,
            )
            return

        if "JOIN stonks.issuer_identifier" in normalized:
            cik = params[0]
            identifier = next(
                (
                    row
                    for row in self.connection.issuer_identifiers
                    if row["id_type"] == "CIK" and row["id_value"] == cik
                ),
                None,
            )
            self.connection.last_result = (
                self.connection.issuers[identifier["issuer_id"]] if identifier else None
            )
            return

        if "INSERT INTO stonks.issuer (" in normalized:
            issuer_id = uuid4()
            self.connection.issuers[issuer_id] = {
                "issuer_id": issuer_id,
                "cik": params[0],
                "current_name": params[1],
                "first_seen": params[2],
                "last_seen": params[3],
            }
            self.connection.last_result = (issuer_id,)
            return

        if "UPDATE stonks.issuer SET" in normalized:
            issuer_id = params[6]
            issuer = self.connection.issuers[issuer_id]
            if params[0] is not None:
                issuer["cik"] = params[0]
            if params[1] is not None:
                issuer["current_name"] = params[2]
            if params[3] is not None:
                issuer["last_seen"] = max(issuer["last_seen"] or params[4], params[5])
            self.connection.last_result = None
            return

        if "INSERT INTO stonks.issuer_identifier" in normalized:
            issuer_id, cik_padded, valid_from, provider_code = params
            existing = next(
                (
                    row
                    for row in self.connection.issuer_identifiers
                    if row["issuer_id"] == issuer_id
                    and row["id_type"] == "CIK"
                    and row["id_value"] == cik_padded
                ),
                None,
            )
            if existing:
                self.connection.last_result = None
                return
            identifier_id = uuid4()
            self.connection.issuer_identifiers.append(
                {
                    "issuer_identifier_id": identifier_id,
                    "issuer_id": issuer_id,
                    "id_type": "CIK",
                    "id_value": cik_padded,
                    "valid_from": valid_from,
                    "provider_code": provider_code,
                    "confidence_code": "HIGH",
                }
            )
            self.connection.last_result = (identifier_id,)
            return

        if "FROM stonks.issuer_name_history" in normalized:
            issuer_id, name, valid_from = params
            self.connection.last_result = next(
                (
                    row
                    for row in self.connection.issuer_name_history
                    if row["issuer_id"] == issuer_id
                    and row["name"] == name
                    and row["valid_from"] == valid_from
                ),
                None,
            )
            return

        if "INSERT INTO stonks.issuer_name_history" in normalized:
            issuer_id, name, valid_from, provider_code = params
            name_id = uuid4()
            self.connection.issuer_name_history.append(
                {
                    "issuer_name_id": name_id,
                    "issuer_id": issuer_id,
                    "name": name,
                    "valid_from": valid_from,
                    "provider_code": provider_code,
                    "confidence_code": "HIGH",
                }
            )
            self.connection.last_result = (name_id,)
            return

        if "FROM stonks.provider_evidence" in normalized:
            provider_observation_id, issuer_id = params
            self.connection.last_result = next(
                (
                    row
                    for row in self.connection.provider_evidence
                    if row["provider_observation_id"] == provider_observation_id
                    and row["issuer_id"] == issuer_id
                    and row["security_id"] is None
                    and row["listing_id"] is None
                    and row["event_id"] is None
                ),
                None,
            )
            return

        if "INSERT INTO stonks.provider_evidence" in normalized:
            provider_observation_id, issuer_id, evidence_role, notes = params
            evidence_id = uuid4()
            self.connection.provider_evidence.append(
                {
                    "provider_evidence_id": evidence_id,
                    "provider_observation_id": provider_observation_id,
                    "issuer_id": issuer_id,
                    "security_id": None,
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
