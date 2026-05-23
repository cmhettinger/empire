"""Database connection helpers."""

from __future__ import annotations

from empire_core.config import DatabaseConfig


class EmpireDatabase:
    """Factory for Empire database connections."""

    @classmethod
    def connect_from_env(cls):
        """Create a psycopg connection using Empire database environment variables."""

        import psycopg

        return psycopg.connect(DatabaseConfig.from_env().to_conninfo())
