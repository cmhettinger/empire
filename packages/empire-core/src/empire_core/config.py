"""Environment-driven configuration for empire-core."""

from __future__ import annotations

import os
from dataclasses import dataclass

from empire_core.exceptions import ConfigurationError


@dataclass(frozen=True)
class DatabaseConfig:
    """Postgres connection settings."""

    host: str
    port: int
    database: str
    user: str
    password: str

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        return cls(
            host=_required("EMPIRE_DB_HOST"),
            port=int(os.environ.get("EMPIRE_DB_PORT", "5432")),
            database=_required("EMPIRE_DB_NAME"),
            user=_required("EMPIRE_DB_USER"),
            password=_required("EMPIRE_DB_PASSWORD"),
        )

    def to_conninfo(self) -> str:
        return (
            f"host={self.host} "
            f"port={self.port} "
            f"dbname={self.database} "
            f"user={self.user} "
            f"password={self.password}"
        )


@dataclass(frozen=True)
class ObjectStoreConfig:
    """Object store behavior configured by environment."""

    tombstone_days: int = 30

    @classmethod
    def from_env(cls) -> "ObjectStoreConfig":
        return cls(
            tombstone_days=int(os.environ.get("EMPIRE_OBJECT_STORE_TOMBSTONE_DAYS", "30"))
        )


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ConfigurationError(f"Missing required environment variable: {name}")
    return value
