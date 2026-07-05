"""Data loading for the stonks securities daily refresh summary report."""

from __future__ import annotations

from typing import Any

from empire_core.db.postgres import row_to_dict


DEFAULT_MARKET_GROUP_LIMIT = 10


def load_canonical_market_snapshot(
    cursor: Any,
    *,
    market_group_limit: int = DEFAULT_MARKET_GROUP_LIMIT,
) -> dict[str, Any]:
    """Load current canonical issuer/security/listing counts by represented market."""

    total = _fetch_one(
        cursor,
        "daily_summary_canonical_market_totals",
        """
        SELECT
          COUNT(DISTINCT i.issuer_id) AS issuers_total,
          COUNT(DISTINCT s.security_id) AS securities_total,
          COUNT(DISTINCT s.security_id) FILTER (
            WHERE COALESCE(s.identity_status, 'PROVISIONAL') = 'PROVISIONAL'
          ) AS securities_provisional_total,
          COUNT(DISTINCT s.security_id) FILTER (
            WHERE COALESCE(s.identity_status, 'PROVISIONAL') = 'CONFIRMED'
          ) AS securities_confirmed_total,
          COUNT(DISTINCT s.security_id) FILTER (
            WHERE COALESCE(s.identity_status, 'PROVISIONAL') NOT IN ('PROVISIONAL', 'CONFIRMED')
          ) AS securities_unknown_identity_status_total,
          COUNT(DISTINCT l.listing_id) AS listings_total
        FROM stonks.listing l
        JOIN stonks.security s ON s.security_id = l.security_id
        LEFT JOIN stonks.issuer i ON i.issuer_id = s.issuer_id
        WHERE l.status = 'ACTIVE'
          AND l.valid_to IS NULL
        """,
    )
    rows = _fetch_all(
        cursor,
        "daily_summary_canonical_markets",
        """
        SELECT
          e.exchange_code,
          e.exchange_name,
          COUNT(DISTINCT i.issuer_id) AS issuers_total,
          COUNT(DISTINCT s.security_id) AS securities_total,
          COUNT(DISTINCT s.security_id) FILTER (
            WHERE COALESCE(s.identity_status, 'PROVISIONAL') = 'PROVISIONAL'
          ) AS securities_provisional_total,
          COUNT(DISTINCT s.security_id) FILTER (
            WHERE COALESCE(s.identity_status, 'PROVISIONAL') = 'CONFIRMED'
          ) AS securities_confirmed_total,
          COUNT(DISTINCT s.security_id) FILTER (
            WHERE COALESCE(s.identity_status, 'PROVISIONAL') NOT IN ('PROVISIONAL', 'CONFIRMED')
          ) AS securities_unknown_identity_status_total,
          COUNT(DISTINCT l.listing_id) AS listings_total
        FROM stonks.listing l
        JOIN stonks.exchange e ON e.exchange_id = l.exchange_id
        JOIN stonks.security s ON s.security_id = l.security_id
        LEFT JOIN stonks.issuer i ON i.issuer_id = s.issuer_id
        WHERE l.status = 'ACTIVE'
          AND l.valid_to IS NULL
        GROUP BY e.exchange_code, e.exchange_name
        ORDER BY listings_total DESC, e.exchange_code
        """,
    )
    grouped = _group_smaller_markets(rows, market_group_limit=market_group_limit)
    return {
        "scope": "canonical_current_active_listings",
        "market_group_limit": market_group_limit,
        "markets_represented": len(rows),
        "markets_reported": len(grouped),
        "totals": _counts(total),
        "markets": grouped,
    }


def _group_smaller_markets(
    rows: list[dict[str, Any]],
    *,
    market_group_limit: int,
) -> list[dict[str, Any]]:
    if market_group_limit < 1 or len(rows) <= market_group_limit:
        return [_market_row(row) for row in rows]

    visible_count = max(market_group_limit - 1, 1)
    visible = [_market_row(row) for row in rows[:visible_count]]
    hidden = rows[visible_count:]
    other = {
        "exchange_code": "OTHER",
        "exchange_name": "Other represented markets",
        "market_count": len(hidden),
        "issuers_total": sum(int(row.get("issuers_total") or 0) for row in hidden),
        "securities_total": sum(int(row.get("securities_total") or 0) for row in hidden),
        "securities_provisional_total": sum(
            int(row.get("securities_provisional_total") or 0) for row in hidden
        ),
        "securities_confirmed_total": sum(
            int(row.get("securities_confirmed_total") or 0) for row in hidden
        ),
        "securities_unknown_identity_status_total": sum(
            int(row.get("securities_unknown_identity_status_total") or 0) for row in hidden
        ),
        "listings_total": sum(int(row.get("listings_total") or 0) for row in hidden),
    }
    return [*visible, other]


def _market_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "exchange_code": row.get("exchange_code"),
        "exchange_name": row.get("exchange_name"),
        "market_count": 1,
        **_counts(row),
    }


def _counts(row: dict[str, Any] | None) -> dict[str, int]:
    row = row or {}
    return {
        "issuers_total": int(row.get("issuers_total") or 0),
        "securities_total": int(row.get("securities_total") or 0),
        "securities_provisional_total": int(row.get("securities_provisional_total") or 0),
        "securities_confirmed_total": int(row.get("securities_confirmed_total") or 0),
        "securities_unknown_identity_status_total": int(
            row.get("securities_unknown_identity_status_total") or 0
        ),
        "listings_total": int(row.get("listings_total") or 0),
    }


def _fetch_all(cursor: Any, metric: str, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cursor.execute(f"/* metric: {metric} */\n{sql}", params)
    return [_row_to_dict(cursor, row) for row in cursor.fetchall()]


def _fetch_one(cursor: Any, metric: str, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
    cursor.execute(f"/* metric: {metric} */\n{sql}", params)
    row = cursor.fetchone()
    return _row_to_dict(cursor, row) if row is not None else {}


def _row_to_dict(cursor: Any, row: Any) -> dict[str, Any]:
    if isinstance(row, tuple) and len(row) == 1 and isinstance(row[0], dict):
        return row[0]
    return row_to_dict(cursor, row)
