from __future__ import annotations

from uuid import UUID

import pytest

from empire_stonks_tech_indicators import BenchmarkConfig, TechIndicatorsConfig
from empire_stonks_tech_indicators import config_readiness as readiness_module
from empire_stonks_tech_indicators.config_readiness import (
    TechIndicatorsConfigReadinessError,
    check_tech_indicators_config_readiness,
)
from empire_stonks_tech_indicators.models import ResolvedBenchmark
from empire_stonks_tech_indicators.talib_adapter import TALibRuntimeInfo


SPX_ID = UUID("00000000-0000-4000-8000-000000000001")


class ReadinessCursor:
    def __init__(
        self,
        *,
        relations: list[tuple[str, str]] | None = None,
        privileges: list[tuple[bool]] | None = None,
        benchmark_rows: list[tuple[object, ...]] | None = None,
    ) -> None:
        self.relations = (
            [
                (name, kind)
                for name, kind, _ in readiness_module._REQUIRED_RELATIONS
            ]
            if relations is None
            else relations
        )
        self.privileges = (
            [(True,) for _ in readiness_module._REQUIRED_RELATIONS]
            if privileges is None
            else privileges
        )
        self.benchmark_rows = (
            [
                (
                    SPX_ID,
                    "YAHOO",
                    "XIDX",
                    "SPX",
                    "EQUITY_INDEX",
                    "ACTIVE",
                    {"YahooTicker": "^GSPC"},
                )
            ]
            if benchmark_rows is None
            else benchmark_rows
        )
        self.executions: list[tuple[str, object]] = []
        self._phase = "version"

    def execute(self, sql: str, parameters: object = None) -> None:
        self.executions.append((sql, parameters))
        if "FROM pg_catalog.pg_class" in sql:
            self._phase = "relations"
        elif "has_table_privilege" in sql:
            self._phase = "privilege"
        elif "FROM core.storage_root" in sql:
            self._phase = "storage_root"
        elif "FROM stonks.provider_listing" in sql:
            self._phase = "benchmark"

    def fetchone(self) -> tuple[object, ...] | None:
        if self._phase == "version":
            return ("18.4",)
        if self._phase == "privilege":
            return self.privileges.pop(0)
        if self._phase == "storage_root":
            return (True,)
        raise AssertionError(f"unexpected fetchone phase: {self._phase}")

    def fetchall(self) -> list[tuple[object, ...]]:
        if self._phase == "relations":
            return list(self.relations)
        if self._phase == "benchmark":
            return list(self.benchmark_rows)
        raise AssertionError(f"unexpected fetchall phase: {self._phase}")


@pytest.fixture
def stub_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        readiness_module,
        "_validated_python_version",
        lambda: "3.14.6",
    )
    monkeypatch.setattr(
        readiness_module,
        "validate_talib_runtime",
        lambda: TALibRuntimeInfo(
            library_name="TA-Lib",
            python_wrapper_version="0.7.1",
            c_library_version="0.7.1",
            numpy_version="2.4.6",
            compatibility="DEFAULT",
            unstable_period=0,
        ),
    )
    monkeypatch.setattr(
        readiness_module,
        "version",
        lambda name: "0.1.0" if name == "empire-stonks-tech-indicators" else "x",
    )
    monkeypatch.setattr(
        readiness_module,
        "_dependency_versions",
        lambda: (("empire-core", "0.1.0"), ("psycopg", "3.3.4")),
    )


def test_config_readiness_returns_bounded_safe_facts(stub_runtime: None) -> None:
    cursor = ReadinessCursor()

    result = check_tech_indicators_config_readiness(
        cursor=cursor,
        config=TechIndicatorsConfig(),
    )

    assert result.benchmark.provider_listing_id == SPX_ID
    assert result.relation_count == 10
    assert result.to_safe_dict() == {
        "ready": True,
        "config": TechIndicatorsConfig().to_safe_dict(),
        "runtime": {
            "python_version": "3.14.6",
            "package_version": "0.1.0",
            "numpy_version": "2.4.6",
            "talib_python_version": "0.7.1",
            "talib_c_version": "0.7.1",
        },
        "dependencies": {
            "ready": True,
            "packages": [
                {"name": "empire-core", "version": "0.1.0"},
                {"name": "psycopg", "version": "3.3.4"},
            ],
        },
        "database": {
            "ready": True,
            "postgresql_version": "18.4",
            "required_relation_count": 10,
            "report_storage_root": "global",
        },
        "benchmark": {
            "ready": True,
            "provider_listing_id": str(SPX_ID),
            "provider_code": "YAHOO",
            "market": "XIDX",
            "ticker": "SPX",
            "instrument_type_code": "EQUITY_INDEX",
            "status": "ACTIVE",
            "yahoo_ticker": "^GSPC",
        },
    }
    assert all("INSERT" not in sql for sql, _ in cursor.executions)


def test_database_readiness_fails_closed_on_missing_relation(
    stub_runtime: None,
) -> None:
    cursor = ReadinessCursor(relations=[])

    with pytest.raises(TechIndicatorsConfigReadinessError) as raised:
        check_tech_indicators_config_readiness(
            cursor=cursor,
            config=TechIndicatorsConfig(),
        )

    assert raised.value.stage == "database"
    assert str(raised.value) == "Technical-indicator database readiness failed."


def test_benchmark_readiness_fails_closed_on_identity_drift(
    stub_runtime: None,
) -> None:
    cursor = ReadinessCursor(
        benchmark_rows=[
            (
                SPX_ID,
                "YAHOO",
                "XIDX",
                "SPX",
                "EQUITY_INDEX",
                "INACTIVE",
                {"YahooTicker": "^GSPC"},
            )
        ]
    )

    with pytest.raises(TechIndicatorsConfigReadinessError) as raised:
        check_tech_indicators_config_readiness(
            cursor=cursor,
            config=TechIndicatorsConfig(benchmark=BenchmarkConfig()),
        )

    assert raised.value.stage == "benchmark"


def test_real_calculation_runtime_smoke() -> None:
    runtime = readiness_module.validate_talib_runtime()

    assert runtime.numpy_version == "2.4.6"
    assert runtime.python_wrapper_version == "0.7.1"
    assert runtime.c_library_version == "0.7.1"
