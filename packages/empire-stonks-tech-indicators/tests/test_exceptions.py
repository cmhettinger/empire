import json
import subprocess
import sys

import pytest

import empire_stonks_tech_indicators as public_api
from empire_stonks_tech_indicators import exceptions as exceptions_module
from empire_stonks_tech_indicators.exceptions import (
    EmpireStonksTechIndicatorsError,
    TechIndicatorsCalculationError,
    TechIndicatorsConfigError,
    TechIndicatorsPersistenceError,
    TechIndicatorsValidationError,
    TechIndicatorsWorkflowError,
)


PUBLIC_EXCEPTIONS = (
    EmpireStonksTechIndicatorsError,
    TechIndicatorsCalculationError,
    TechIndicatorsConfigError,
    TechIndicatorsPersistenceError,
    TechIndicatorsValidationError,
    TechIndicatorsWorkflowError,
)


def test_public_api_is_explicit() -> None:
    expected = [exception.__name__ for exception in PUBLIC_EXCEPTIONS]

    assert public_api.__all__ == [
        *expected,
        "BenchmarkConfig",
        "TechIndicatorsConfig",
        "BenchmarkHistory",
        "EligibleListing",
        "iter_source_bar_pages",
        "load_spx_benchmark_history",
        "resolve_spx_benchmark",
        "select_eligible_listings",
        "FeatureCounts",
        "FeatureRow",
        "ReasonCount",
        "ResolvedBenchmark",
        "SourceBar",
        "TechIndicatorsIssue",
        "TechIndicatorsRunResult",
        "TechIndicatorsScope",
        "TechIndicatorsSummary",
    ]
    assert exceptions_module.__all__ == expected
    assert all(
        getattr(public_api, name) is exception
        for name, exception in zip(expected, PUBLIC_EXCEPTIONS, strict=True)
    )


@pytest.mark.parametrize("exception", PUBLIC_EXCEPTIONS[1:])
def test_specific_exceptions_share_one_package_base(
    exception: type[EmpireStonksTechIndicatorsError],
) -> None:
    failure = exception("safe failure")

    assert isinstance(failure, EmpireStonksTechIndicatorsError)
    assert str(failure) == "safe failure"


def test_cold_public_import_does_not_load_internal_dependencies() -> None:
    code = """
import json
import sys
import empire_stonks_tech_indicators as package

print(json.dumps({
    "exports": package.__all__,
    "internal_modules": sorted(
        name for name in ("numpy", "psycopg", "talib") if name in sys.modules
    ),
}))
"""
    completed = subprocess.run(
        [sys.executable, "-I", "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )

    result = json.loads(completed.stdout)
    assert result["exports"] == list(public_api.__all__)
    assert result["internal_modules"] == []
