# empire-stonks-tech-indicators

Reusable provider-native daily technical-indicator calculation utilities for
Empire Stonks.

This package is the platform-owned boundary for technical calculation,
validation, persistence, operational reporting, and workflow runners. Airflow,
CLIs, and other runtimes will call package-owned capabilities rather than own
business logic. The B1.3 scaffold intentionally contains only the importable
package boundary; later tasks add those capabilities incrementally.

## Runtime contract

The initial package version is `0.1.0` and supports Python `>=3.11,<4.0`. Its
only runtime dependencies are the exact calculation pair frozen by B1.1:

```text
numpy==2.4.6
TA-Lib==0.7.1
```

TA-Lib uses its wheel-bundled native library. Normal installation must not
silently fall back to an unreviewed source build or system library. See the
[runtime contract](../../docs/stonks/tech-indicators-runtime-contract-v1.md)
for wheel, native-library, Python, license, verification, and rollback rules.

V1 recursive indicators calculate each affected provider listing from its
earliest eligible observation through the safe run horizon, then compare or
write only the affected suffix. Fixed bounded replay and persisted recurrence
state are not part of V1. See the
[recursive-equivalence decision](../../docs/stonks/tech-indicators-recursive-equivalence-v1.md).

## Ownership and configuration

Reusable package code reads configuration only from `os.environ`. It does not
load `.env` files, assume repository paths, or depend on Airflow. Environment
loading belongs to runtime wrappers, Docker Compose, Airflow, or the invoking
shell. `TechIndicatorsConfig.from_env()` validates these non-secret settings:

| Environment variable | Default | Accepted value |
|---|---:|---|
| `EMPIRE_STONKS_TECH_INDICATORS_CALCULATION_VERSION` | `TECH_INDICATORS_V1` | Exact implemented calculation version |
| `EMPIRE_STORAGE_KEY_STONKS_TECH_INDICATORS` | `stonks/tech-indicators` | Normalized relative storage prefix |
| `EMPIRE_STONKS_TECH_INDICATORS_BENCHMARK_PROVIDER_CODE` | `YAHOO` | Exact frozen value |
| `EMPIRE_STONKS_TECH_INDICATORS_BENCHMARK_MARKET` | `XIDX` | Exact frozen value |
| `EMPIRE_STONKS_TECH_INDICATORS_BENCHMARK_TICKER` | `SPX` | Exact frozen value |
| `EMPIRE_STONKS_TECH_INDICATORS_BENCHMARK_INSTRUMENT_TYPE_CODE` | `EQUITY_INDEX` | Exact frozen value |
| `EMPIRE_STONKS_TECH_INDICATORS_BENCHMARK_YAHOO_TICKER` | `^GSPC` | Exact frozen value |
| `EMPIRE_STONKS_TECH_INDICATORS_SOURCE_READ_PAGE_SIZE` | `10000` | `1000` through `50000` |
| `EMPIRE_STONKS_TECH_INDICATORS_WRITE_BATCH_SIZE` | `5000` | `1000` through `10000` |
| `EMPIRE_STONKS_TECH_INDICATORS_DIAGNOSTIC_SAMPLE_LIMIT` | `100` | `1` through `100` |

The P0.8 hard ceiling of 25,000 rows in a write transaction is a package
constant, not an environment override. B1.8 adds example/local values and
runtime passthrough; reusable package code never opens those files itself.

The package does not own an internal migration runner. Empire Flyway
migrations under `db/` own the eventual technical-indicator schema. Core run
lifecycle, JSON/PDF reports, package commands, and Airflow orchestration are
introduced only by their assigned implementation tasks.

## Public API

The package root explicitly exports one base exception and five stable failure
categories:

- `EmpireStonksTechIndicatorsError`
- `TechIndicatorsConfigError`
- `TechIndicatorsCalculationError`
- `TechIndicatorsValidationError`
- `TechIndicatorsPersistenceError`
- `TechIndicatorsWorkflowError`

It also exports the two immutable configuration types:

- `BenchmarkConfig`
- `TechIndicatorsConfig`

Callers may catch the package base or the narrow category they can handle. The
public exceptions contain no TA-Lib values, SQL, database-driver exceptions,
connection details, or persistence implementation types. Additional public
models and capabilities are added only by their assigned tasks.

## Development

From this directory:

```bash
poetry install
poetry run pytest
poetry build
```

The committed `poetry.lock` resolves the exact calculation runtime and the
development test dependency. Build output contains both a wheel and source
distribution.
