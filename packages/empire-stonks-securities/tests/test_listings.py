from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from empire_stonks_securities.listings import SecListingObservation, upsert_sec_listings


OBSERVED_AT = datetime(2026, 6, 18, 12, 30, tzinfo=UTC)


def test_creates_listing_and_symbol_history_from_exchange_observation():
    conn = FakeConnection()
    issuer_id, security_id, exchange_id = seed_prereqs(conn)
    observation = listing_observation()
    conn.add_issuer_evidence(observation.provider_observation_id, issuer_id)
    conn.add_security_evidence(observation.provider_observation_id, issuer_id, security_id)

    result = upsert_sec_listings(connection=conn, observations=[observation])

    assert result.listings_created == 1
    assert result.symbol_history_inserted == 1
    assert result.evidence_inserted == 1
    listing = next(iter(conn.listings.values()))
    assert listing["security_id"] == security_id
    assert listing["exchange_id"] == exchange_id
    assert listing["ticker_norm"] == "AAPL"
    assert listing["status"] == "ACTIVE"
    assert conn.symbol_history[0]["ticker_norm"] == "AAPL"


def test_resolves_issuer_and_security_using_evidence_links():
    conn = FakeConnection()
    issuer_id, security_id, _ = seed_prereqs(conn)
    observation = listing_observation()
    conn.add_issuer_evidence(observation.provider_observation_id, issuer_id)
    conn.add_security_evidence(observation.provider_observation_id, issuer_id, security_id)

    result = upsert_sec_listings(connection=conn, observations=[observation])

    assert result.issuers_resolved == 1
    assert result.securities_resolved == 1


def test_falls_back_to_cik_and_ticker_when_evidence_is_missing():
    conn = FakeConnection()
    issuer_id, security_id, _ = seed_prereqs(conn)

    result = upsert_sec_listings(connection=conn, observations=[listing_observation()])

    assert result.issuers_resolved == 1
    assert result.securities_resolved == 1
    assert next(iter(conn.listings.values()))["security_id"] == security_id
    assert issuer_id in conn.issuers


def test_resolves_exchange_through_alias():
    conn = FakeConnection()
    _, _, exchange_id = seed_prereqs(conn, raw_exchange="Nasdaq", exchange_code="NASDAQ")

    upsert_sec_listings(connection=conn, observations=[listing_observation(exchange="Nasdaq")])

    assert next(iter(conn.listings.values()))["exchange_id"] == exchange_id


def test_skips_unknown_exchange():
    conn = FakeConnection()
    seed_prereqs(conn)

    result = upsert_sec_listings(
        connection=conn,
        observations=[listing_observation(exchange="Mystery Exchange")],
    )

    assert result.observations_skipped == 1
    assert result.exchanges_unknown == 1
    assert result.warning_count == 1
    assert len(conn.listings) == 0


def test_skips_observation_without_exchange_or_ticker():
    conn = FakeConnection()
    seed_prereqs(conn)

    result = upsert_sec_listings(
        connection=conn,
        observations=[
            listing_observation(provider_observation_id=uuid4(), exchange=None),
            listing_observation(provider_observation_id=uuid4(), ticker_norm=None),
        ],
    )

    assert result.observations_scanned == 2
    assert result.observations_skipped == 2
    assert result.warning_count == 2
    assert len(conn.listings) == 0


def test_rerun_is_idempotent_and_does_not_duplicate_symbol_history():
    conn = FakeConnection()
    issuer_id, security_id, _ = seed_prereqs(conn)
    observation = listing_observation()
    conn.add_issuer_evidence(observation.provider_observation_id, issuer_id)
    conn.add_security_evidence(observation.provider_observation_id, issuer_id, security_id)

    first = upsert_sec_listings(connection=conn, observations=[observation])
    second = upsert_sec_listings(connection=conn, observations=[observation])

    assert first.listings_created == 1
    assert second.listings_created == 0
    assert second.symbol_history_skipped == 1
    assert second.evidence_skipped == 1
    assert len(conn.listings) == 1
    assert len(conn.symbol_history) == 1
    assert len([row for row in conn.provider_evidence if row["listing_id"] is not None]) == 1


def test_writes_evidence_link_from_observation_to_listing():
    conn = FakeConnection()
    issuer_id, security_id, _ = seed_prereqs(conn)
    observation = listing_observation()
    conn.add_issuer_evidence(observation.provider_observation_id, issuer_id)
    conn.add_security_evidence(observation.provider_observation_id, issuer_id, security_id)

    upsert_sec_listings(connection=conn, observations=[observation])

    listing_id = next(iter(conn.listings))
    evidence = [row for row in conn.provider_evidence if row["listing_id"] is not None][0]
    assert evidence["provider_observation_id"] == observation.provider_observation_id
    assert evidence["issuer_id"] == issuer_id
    assert evidence["security_id"] == security_id
    assert evidence["listing_id"] == listing_id


def test_does_not_create_issuer_or_security_rows_or_deactivate_listings():
    conn = FakeConnection()
    seed_prereqs(conn)

    upsert_sec_listings(connection=conn, observations=[listing_observation()])

    assert conn.issuer_writes == 0
    assert conn.security_writes == 0
    assert conn.deactivate_listing_writes == 0


def listing_observation(
    *,
    provider_observation_id: UUID | None = None,
    provider_date: date | None = date(2026, 6, 18),
    cik: int | None = 320193,
    cik_padded: str | None = "0000320193",
    ticker_norm: str | None = "AAPL",
    exchange: str | None = "Nasdaq",
) -> SecListingObservation:
    summary_json = {"source_code": "sec_company_tickers_exchange"}
    if cik is not None:
        summary_json["cik"] = cik
    if cik_padded is not None:
        summary_json["cik_padded"] = cik_padded
    if ticker_norm is not None:
        summary_json["ticker"] = ticker_norm.lower()
        summary_json["ticker_norm"] = ticker_norm
    if exchange is not None:
        summary_json["exchange"] = exchange
    return SecListingObservation(
        provider_observation_id=provider_observation_id or uuid4(),
        provider_code="SEC_COMPANY_TICKERS_EXCHANGE",
        provider_date=provider_date,
        observed_at=OBSERVED_AT,
        summary_json=summary_json,
    )


def seed_prereqs(
    conn: "FakeConnection",
    *,
    cik: str = "0000320193",
    ticker_norm: str = "AAPL",
    raw_exchange: str = "Nasdaq",
    exchange_code: str = "NASDAQ",
) -> tuple[UUID, UUID, UUID]:
    issuer_id = conn.add_issuer(cik)
    security_id = conn.add_security(issuer_id, ticker_norm)
    exchange_id = conn.add_exchange(exchange_code)
    conn.add_exchange_alias(exchange_id, raw_exchange)
    return issuer_id, security_id, exchange_id


class FakeConnection:
    def __init__(self) -> None:
        self.issuers: dict[UUID, dict] = {}
        self.securities: dict[UUID, dict] = {}
        self.security_identifiers: list[dict] = []
        self.exchanges: dict[UUID, dict] = {}
        self.exchange_aliases: list[dict] = []
        self.listings: dict[UUID, dict] = {}
        self.symbol_history: list[dict] = []
        self.provider_evidence: list[dict] = []
        self.issuer_writes = 0
        self.security_writes = 0
        self.deactivate_listing_writes = 0
        self.last_result = None

    def add_issuer(self, cik: str) -> UUID:
        issuer_id = uuid4()
        self.issuers[issuer_id] = {"issuer_id": issuer_id, "cik": cik}
        return issuer_id

    def add_security(self, issuer_id: UUID, ticker_norm: str) -> UUID:
        security_id = uuid4()
        self.securities[security_id] = {
            "security_id": security_id,
            "issuer_id": issuer_id,
        }
        self.security_identifiers.append(
            {"security_id": security_id, "id_type": "TICKER", "id_value": ticker_norm}
        )
        return security_id

    def add_exchange(self, exchange_code: str) -> UUID:
        exchange_id = uuid4()
        self.exchanges[exchange_id] = {
            "exchange_id": exchange_id,
            "exchange_code": exchange_code,
            "exchange_name": exchange_code,
            "is_active": True,
        }
        return exchange_id

    def add_exchange_alias(self, exchange_id: UUID, raw_name: str) -> None:
        self.exchange_aliases.append(
            {
                "exchange_id": exchange_id,
                "provider_code": "SEC",
                "raw_name": raw_name,
                "is_active": True,
            }
        )

    def add_issuer_evidence(self, provider_observation_id: UUID, issuer_id: UUID) -> None:
        self.provider_evidence.append(
            {
                "provider_evidence_id": uuid4(),
                "provider_observation_id": provider_observation_id,
                "issuer_id": issuer_id,
                "security_id": None,
                "listing_id": None,
                "event_id": None,
            }
        )

    def add_security_evidence(
        self,
        provider_observation_id: UUID,
        issuer_id: UUID,
        security_id: UUID,
    ) -> None:
        self.provider_evidence.append(
            {
                "provider_evidence_id": uuid4(),
                "provider_observation_id": provider_observation_id,
                "issuer_id": issuer_id,
                "security_id": security_id,
                "listing_id": None,
                "event_id": None,
            }
        )

    def cursor(self):
        return FakeCursor(self)

    def commit(self) -> None:
        pass


class FakeCursor:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql: str, params=None) -> None:
        normalized = " ".join(sql.split())
        if "INSERT INTO stonks.issuer" in normalized or "UPDATE stonks.issuer" in normalized:
            self.connection.issuer_writes += 1
        if "INSERT INTO stonks.security" in normalized or "UPDATE stonks.security" in normalized:
            self.connection.security_writes += 1
        if "SET status = 'INACTIVE'" in normalized or "valid_to =" in normalized and "UPDATE stonks.listing" in normalized:
            self.connection.deactivate_listing_writes += 1

        if "FROM stonks.provider_evidence" in normalized and "issuer_id IS NOT NULL" in normalized:
            provider_observation_id = params[0]
            self.connection.last_result = next(
                (
                    (row["issuer_id"],)
                    for row in self.connection.provider_evidence
                    if row["provider_observation_id"] == provider_observation_id
                    and row["issuer_id"] is not None
                ),
                None,
            )
            return

        if "SELECT issuer_id FROM stonks.issuer WHERE cik" in normalized:
            cik = params[0]
            self.connection.last_result = next(
                ((row["issuer_id"],) for row in self.connection.issuers.values() if row["cik"] == cik),
                None,
            )
            return

        if "FROM stonks.provider_evidence" in normalized and "security_id IS NOT NULL" in normalized:
            provider_observation_id = params[0]
            self.connection.last_result = next(
                (
                    (row["security_id"],)
                    for row in self.connection.provider_evidence
                    if row["provider_observation_id"] == provider_observation_id
                    and row["security_id"] is not None
                    and row["listing_id"] is None
                    and row["event_id"] is None
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
                (security["security_id"],)
                if security is not None and security["issuer_id"] == issuer_id
                else None
            )
            return

        if "FROM stonks.exchange_alias" in normalized:
            exchange = params[0]
            alias = next(
                (
                    row
                    for row in self.connection.exchange_aliases
                    if row["provider_code"] == "SEC"
                    and row["is_active"]
                    and row["raw_name"].lower() == exchange.lower()
                ),
                None,
            )
            self.connection.last_result = (alias["exchange_id"],) if alias else None
            return

        if "FROM stonks.exchange WHERE" in normalized:
            exchange = params[0]
            row = next(
                (
                    row
                    for row in self.connection.exchanges.values()
                    if row["is_active"]
                    and (
                        row["exchange_code"].lower() == exchange.lower()
                        or row["exchange_name"].lower() == exchange.lower()
                    )
                ),
                None,
            )
            self.connection.last_result = (row["exchange_id"],) if row else None
            return

        if "FROM stonks.listing WHERE exchange_id" in normalized:
            exchange_id, ticker_norm = params
            self.connection.last_result = next(
                (
                    row
                    for row in self.connection.listings.values()
                    if row["exchange_id"] == exchange_id
                    and row["ticker_norm"] == ticker_norm
                    and row["valid_to"] is None
                ),
                None,
            )
            return

        if "INSERT INTO stonks.listing_symbol_history" in normalized:
            symbol_id = uuid4()
            self.connection.symbol_history.append(
                {
                    "listing_symbol_id": symbol_id,
                    "listing_id": params[0],
                    "ticker_raw": params[1],
                    "ticker_norm": params[2],
                    "ticker_display": params[3],
                    "valid_from": params[4],
                    "provider_code": params[5],
                    "confidence_code": params[6],
                }
            )
            self.connection.last_result = (symbol_id,)
            return

        if "INSERT INTO stonks.listing (" in normalized:
            listing_id = uuid4()
            self.connection.listings[listing_id] = {
                "listing_id": listing_id,
                "security_id": params[0],
                "exchange_id": params[1],
                "current_ticker": params[2],
                "ticker_norm": params[3],
                "status": "ACTIVE",
                "valid_from": params[4],
                "valid_to": None,
                "first_seen": params[5],
                "last_seen": params[6],
            }
            self.connection.last_result = (listing_id,)
            return

        if "UPDATE stonks.listing SET" in normalized:
            listing_id = params[5]
            listing = self.connection.listings[listing_id]
            listing["current_ticker"] = params[0]
            listing["ticker_norm"] = params[1]
            if params[2] is not None:
                listing["last_seen"] = max(listing["last_seen"] or params[3], params[4])
            self.connection.last_result = None
            return

        if "FROM stonks.listing_symbol_history" in normalized:
            listing_id, ticker_norm, valid_from = params
            self.connection.last_result = next(
                (
                    row
                    for row in self.connection.symbol_history
                    if row["listing_id"] == listing_id
                    and row["ticker_norm"] == ticker_norm
                    and row["valid_from"] == valid_from
                ),
                None,
            )
            return

        if "FROM stonks.provider_evidence" in normalized and "listing_id =" in normalized:
            provider_observation_id, listing_id = params
            self.connection.last_result = next(
                (
                    row
                    for row in self.connection.provider_evidence
                    if row["provider_observation_id"] == provider_observation_id
                    and row["listing_id"] == listing_id
                ),
                None,
            )
            return

        if "INSERT INTO stonks.provider_evidence" in normalized:
            evidence_id = uuid4()
            self.connection.provider_evidence.append(
                {
                    "provider_evidence_id": evidence_id,
                    "provider_observation_id": params[0],
                    "issuer_id": params[1],
                    "security_id": params[2],
                    "listing_id": params[3],
                    "event_id": None,
                    "evidence_role": params[4],
                    "notes": params[5],
                }
            )
            self.connection.last_result = (evidence_id,)
            return

        raise AssertionError(f"Unexpected SQL: {normalized}")

    def fetchone(self):
        return self.connection.last_result
