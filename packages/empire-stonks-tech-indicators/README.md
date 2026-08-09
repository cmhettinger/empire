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
shell. No configuration is implemented by this scaffold; B1.5 owns that work.

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
