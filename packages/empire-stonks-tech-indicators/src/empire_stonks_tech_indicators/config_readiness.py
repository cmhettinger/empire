"""Secret-safe runtime and database readiness for operator configuration."""

from __future__ import annotations

import platform
from dataclasses import dataclass
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from empire_stonks_tech_indicators.config import TechIndicatorsConfig
from empire_stonks_tech_indicators.exceptions import (
    TechIndicatorsValidationError,
)
from empire_stonks_tech_indicators.models import ResolvedBenchmark
from empire_stonks_tech_indicators.queries import resolve_spx_benchmark
from empire_stonks_tech_indicators.talib_adapter import validate_talib_runtime


_DEPENDENCIES = (
    ("empire-core", "empire_core"),
    ("empire-reports", "empire_reports"),
    ("psycopg", "psycopg"),
    ("reportlab", "reportlab"),
)
_REQUIRED_RELATIONS = (
    ("core.core_run", "r", "SELECT,INSERT,UPDATE"),
    ("core.storage_root", "r", "SELECT"),
    ("core.stored_object", "r", "SELECT,INSERT,UPDATE"),
    ("stonks.provider_listing", "r", "SELECT"),
    ("stonks.ohlcv_daily", "r", "SELECT"),
    (
        "stonks.ohlcv_daily_tech_indicators_a",
        "r",
        "SELECT,INSERT,UPDATE,DELETE",
    ),
    (
        "stonks.ohlcv_daily_tech_indicators_b",
        "r",
        "SELECT,INSERT,UPDATE,DELETE",
    ),
    (
        "stonks.tech_indicators_publication",
        "r",
        "SELECT,INSERT,UPDATE,DELETE",
    ),
    (
        "stonks.tech_indicators_publication_listing",
        "r",
        "SELECT,INSERT,UPDATE,DELETE",
    ),
    ("stonks.ohlcv_daily_tech_indicators", "v", "SELECT"),
)
_SUPPORTED_PYTHON_MIN = (3, 11)
_SUPPORTED_PYTHON_MAX = (3, 14)


class TechIndicatorsConfigReadinessError(TechIndicatorsValidationError):
    """A safe readiness failure classified by one fixed stage."""

    def __init__(self, stage: str) -> None:
        if stage not in {"runtime", "dependency", "database", "benchmark"}:
            raise ValueError("stage must be a config-readiness stage.")
        self.stage = stage
        super().__init__(f"Technical-indicator {stage} readiness failed.")


@dataclass(frozen=True)
class TechIndicatorsConfigReadiness:
    """Bounded facts proving an operator runtime is ready."""

    config: TechIndicatorsConfig
    python_version: str
    package_version: str
    numpy_version: str
    talib_python_version: str
    talib_c_version: str
    dependencies: tuple[tuple[str, str], ...]
    postgresql_version: str
    relation_count: int
    benchmark: ResolvedBenchmark

    def to_safe_dict(self) -> dict[str, object]:
        return {
            "ready": True,
            "config": self.config.to_safe_dict(),
            "runtime": {
                "python_version": self.python_version,
                "package_version": self.package_version,
                "numpy_version": self.numpy_version,
                "talib_python_version": self.talib_python_version,
                "talib_c_version": self.talib_c_version,
            },
            "dependencies": {
                "ready": True,
                "packages": [
                    {"name": name, "version": package_version}
                    for name, package_version in self.dependencies
                ],
            },
            "database": {
                "ready": True,
                "postgresql_version": self.postgresql_version,
                "required_relation_count": self.relation_count,
                "report_storage_root": "global",
            },
            "benchmark": {"ready": True, **self.benchmark.to_dict()},
        }


def check_tech_indicators_config_readiness(
    *,
    cursor: Any,
    config: TechIndicatorsConfig,
) -> TechIndicatorsConfigReadiness:
    """Prove config, calculation runtime, dependencies, DB, and benchmark."""

    _validate_cursor(cursor)
    if not isinstance(config, TechIndicatorsConfig):
        raise TypeError("config must be a TechIndicatorsConfig.")

    try:
        python_version = _validated_python_version()
        runtime = validate_talib_runtime()
        package_version = version("empire-stonks-tech-indicators")
    except Exception:
        raise TechIndicatorsConfigReadinessError("runtime") from None

    try:
        dependencies = _dependency_versions()
    except Exception:
        raise TechIndicatorsConfigReadinessError("dependency") from None

    try:
        postgresql_version = _database_readiness(cursor)
    except Exception:
        raise TechIndicatorsConfigReadinessError("database") from None

    try:
        benchmark = resolve_spx_benchmark(
            cursor=cursor,
            config=config.benchmark,
        )
    except Exception:
        raise TechIndicatorsConfigReadinessError("benchmark") from None

    return TechIndicatorsConfigReadiness(
        config=config,
        python_version=python_version,
        package_version=package_version,
        numpy_version=runtime.numpy_version,
        talib_python_version=runtime.python_wrapper_version,
        talib_c_version=runtime.c_library_version,
        dependencies=dependencies,
        postgresql_version=postgresql_version,
        relation_count=len(_REQUIRED_RELATIONS),
        benchmark=benchmark,
    )


def _validated_python_version() -> str:
    current = platform.python_version_tuple()
    major_minor = (int(current[0]), int(current[1]))
    if not _SUPPORTED_PYTHON_MIN <= major_minor <= _SUPPORTED_PYTHON_MAX:
        raise RuntimeError("unsupported Python runtime")
    return platform.python_version()


def _dependency_versions() -> tuple[tuple[str, str], ...]:
    versions = []
    for distribution_name, module_name in _DEPENDENCIES:
        import_module(module_name)
        try:
            dependency_version = version(distribution_name)
        except PackageNotFoundError:
            raise RuntimeError("dependency metadata is missing") from None
        versions.append((distribution_name, dependency_version))
    return tuple(versions)


def _database_readiness(cursor: Any) -> str:
    relation_names = [item[0] for item in _REQUIRED_RELATIONS]
    cursor.execute(
        """
        SELECT current_setting('server_version')
        """
    )
    version_row = cursor.fetchone()
    if (
        not isinstance(version_row, (tuple, list))
        or len(version_row) != 1
        or not isinstance(version_row[0], str)
        or not version_row[0]
    ):
        raise RuntimeError("PostgreSQL version is unavailable")

    cursor.execute(
        """
        SELECT
            namespace.nspname || '.' || relation.relname,
            relation.relkind
        FROM pg_catalog.pg_class AS relation
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname || '.' || relation.relname = ANY(%s)
        ORDER BY namespace.nspname, relation.relname
        """,
        (relation_names,),
    )
    relation_rows = cursor.fetchall()
    actual_kinds = {row[0]: row[1] for row in relation_rows}
    expected_kinds = {name: kind for name, kind, _ in _REQUIRED_RELATIONS}
    if actual_kinds != expected_kinds:
        raise RuntimeError("required database relations are unavailable")

    for relation_name, _, privileges in _REQUIRED_RELATIONS:
        cursor.execute(
            "SELECT has_table_privilege(current_user, %s, %s)",
            (relation_name, privileges),
        )
        privilege_row = cursor.fetchone()
        if privilege_row != (True,):
            raise RuntimeError("required database privileges are unavailable")
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM core.storage_root
            WHERE root_name = 'global'
              AND is_active
        )
        """
    )
    if cursor.fetchone() != (True,):
        raise RuntimeError("report storage root is unavailable")
    return version_row[0]


def _validate_cursor(cursor: object) -> None:
    for method_name in ("execute", "fetchone", "fetchall"):
        if not callable(getattr(cursor, method_name, None)):
            raise TypeError(
                "cursor must provide execute(), fetchone(), and fetchall()."
            )


__all__ = [
    "TechIndicatorsConfigReadiness",
    "TechIndicatorsConfigReadinessError",
    "check_tech_indicators_config_readiness",
]
