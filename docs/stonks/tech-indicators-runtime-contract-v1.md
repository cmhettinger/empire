# Tech-Indicators Runtime Contract V1

Status: frozen dependency and packaging contract for B1.1 as of 2026-08-09.

This contract pins the native calculation runtime selected for
`TECH_INDICATORS_V1`. It extends the
[`technical-indicators-design-contract.md`](technical-indicators-design-contract.md)
and does not scaffold the package, select an incremental recurrence strategy,
or install the future package into Airflow ahead of B1.3 and B1.7.

## Selected Versions

The exact V1 combination is:

```text
TA-Lib Python distribution: 0.7.1
Bundled TA-Lib C library:   0.7.1
NumPy:                      2.4.6
Supported Empire Python:    3.11 through 3.14
```

The future `empire-stonks-tech-indicators` package must declare exact
`TA-Lib == 0.7.1` and `numpy == 2.4.6` runtime dependencies. Airflow pins the
same pair in `deploy/docker/airflow/airflow-requirements.txt` so its base
runtime is resolved before Empire packages are installed.

TA-Lib 0.7.1 is the corrected wrapper release whose wheels use TA-Lib C 0.7.1.
Its project metadata supports Python 3.9 through 3.14 and NumPy 2. NumPy 2.4.6
supports Python 3.11 through 3.14, matching Empire's existing
`python = ">=3.11,<4.0"` package boundary. NumPy 2.5 was not selected because
it drops Python 3.11, and the dependency contract must not narrow Empire's
current supported range implicitly.

## Wheel And Native-Library Behavior

TA-Lib publishes platform wheels for CPython 3.9 through 3.14 on Linux, macOS,
and Windows, including both ARM64 and x86-64. Starting with wrapper 0.6.5,
those wheels bundle the underlying C library. Empire therefore uses the wheel
path and does not install a separate operating-system `ta-lib` package or add
compiler/header tooling to the Airflow image.

The reviewed local environment is macOS ARM64 with CPython 3.14.6. Poetry
selected `ta_lib-0.7.1-cp314-cp314-macosx_14_0_arm64.whl`; the extension has
an `@loader_path` dependency on the wheel-bundled 0.7.1 dylib and no system
TA-Lib dependency. The reviewed Airflow image is Linux ARM64 with CPython
3.13.13. Pip selected the CPython 3.13 manylinux ARM64 wheel; `ldd` resolved
`libta-lib` from the wheel's `ta_lib.libs` directory rather than the operating
system. Both environments reported the embedded C version as `0.7.1`.

Source builds are not an accepted normal runtime path. Installation must fail
closed when no matching binary wheel exists; an operator must not silently add
an unreviewed compiler-built TA-Lib or system shared library. A future Python,
base-image, architecture, TA-Lib, or NumPy upgrade must rerun the local and
Airflow wheel, import, calculation, native-linkage, and license review before
changing these pins.

## Calculation Smoke Contract

`tools/tech-indicators/runtime-smoke.py` is the package-independent runtime
probe. It requires the exact pins, contiguous `float64` inputs, default TA-Lib
compatibility, zero unstable periods, the P0.4 null prefixes, and finite
post-lookback outputs for SMA, EMA, RSI, ATR, +DI, -DI, ADX, and MACD.

The probe proves installation, import, native extension loading, version
identity, and representative Function API execution. It does not replace B1.2
recursive-equivalence work or later independent formula and golden tests.

## License Review

- The TA-Lib Python wrapper is BSD-2-Clause.
- The bundled TA-Lib C library is BSD-3-Clause.
- NumPy is BSD-3-Clause and its wheel carries third-party license notices.

These permissive licenses present no B1.1 distribution blocker. Binary
redistribution must retain the applicable copyright, license conditions, and
disclaimers. Empire does not copy or modify upstream source in this task; the
installed wheels retain their distribution metadata and license files.

Primary review sources:

- <https://github.com/TA-Lib/ta-lib-python/releases/tag/v0.7.1>
- <https://github.com/TA-Lib/ta-lib-python#versions->
- <https://github.com/TA-Lib/ta-lib-python#wheels->
- <https://github.com/TA-Lib/ta-lib-python/blob/v0.7.1/LICENSE>
- <https://github.com/TA-Lib/ta-lib/blob/v0.7.1/LICENSE>
- <https://numpy.org/doc/stable/release/2.4.6-notes.html>
- <https://github.com/numpy/numpy/blob/v2.4.6/LICENSE.txt>

## Rollback

B1.1 changes no database state and publishes no calculated rows. To roll back,
remove the two exact pins from the Airflow requirements file, rebuild the prior
Airflow image, and leave B1.1 incomplete. After B1.3, package rollback must
instead restore the last reviewed exact pair in both package metadata/lock and
Airflow requirements, rebuild both runtimes, and rerun this smoke contract.

A library downgrade or upgrade after technical rows exist is a calculation
runtime change: do not mix outputs under one calculation version. Restore the
previous complete publication or introduce a reviewed calculation version and
rebuild through the frozen recalculation/publication contracts.
