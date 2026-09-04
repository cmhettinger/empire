# Technical Indicators Package Action Plan

This document tracks the implementation roadmap for provider-native daily
technical indicators in Empire Stonks.

The first implementation creates a reusable
`empire-stonks-tech-indicators` package
that reads `stonks.ohlcv_daily`, calculates versioned daily analytical
features, and stores current state in
`stonks.ohlcv_daily_tech_indicators`. It does not put calculation logic in the
OHLCV package, DAGs, reports, or strategies.

The delivery proves one manageable, testable layer at a time: contracts,
runtime dependencies, schema, inputs, calculation families, persistence,
reports, runners, CLIs, Airflow coordination, development closeout, and a
separate production buildout.

## Starting A Task In A New Codex Chat

Copy this prompt and replace `<TASK_ID>` with the task to complete.

```text
Complete task <TASK_ID> from docs/todo/tech-ind-task-plan.md.

Before changing code, read AGENTS.md, the full active plan and archive, and the
full docs/stonks/technical-indicators-design-contract.md. Also read the OHLCV
plans/source contracts required by the task. Inspect the live repository and
completed prerequisite Done: notes; do not assume the plan is newer than the
implementation.

Implement only the named task and necessary integration points. Follow Empire
package, database, Core, reporting, environment, CLI, and Airflow conventions.
Run the focused formatting, tests, imports, DB validation, report rendering,
CLI smoke, or Airflow validation appropriate to the task. Fix failures caused
by the work. Mark the task [x] and add a terse dated Done: note with key files
and exact verification. If blocked, leave it unchecked and report the blocker
instead of weakening completion criteria.
```

## Package Boundary

`empire-stonks-tech-indicators` owns chronological OHLCV reads, benchmark
resolution, TA-Lib/NumPy calculation adapters, versioned formulas, numerical
validation, affected-range planning, current-state persistence, daily and
backfill runners, feature/coverage queries, JSON/PDF run reports, and thin CLI
entrypoints.

It does not own provider ingestion, OHLCV mutation, canonical identity,
corporate-action normalization, strategy thresholds, target selection,
portfolio/backtest execution, point-in-time sector mappings, intraday
indicators, or Airflow business logic. `empire-stonks-ohlcv` stays upstream and
must not import `empire_stonks_tech_indicators`.

## Required Design Baseline

The agreed table shape, feature inventory, formula direction, generated-versus
Python ownership, validation split, SPX identity, index philosophy, operational
surfaces, deferred indicators, and narrowly scoped open decisions are preserved
in the
[daily technical indicators design contract](../stonks/technical-indicators-design-contract.md).

Implementation tasks refine and prove that baseline. They must not restart the
indicator-selection or table-design discussion without new evidence and an
explicit contract update.

```text
empire-stonks-ohlcv -> stonks.ohlcv_daily
    -> empire-stonks-tech-indicators -> stonks.ohlcv_daily_tech_indicators
    -> reports / screens / future backtests
```

## Initial Persistence And Calculation Contract

`stonks.ohlcv_daily_tech_indicators` has one current row per
`(provider_listing_id, trading_date)` with an owning FK to `ohlcv_daily`. Rows
remain provider-native. The read-optimized table copies OHLCV so ordinary
screens need no source join, stores historical/cross-series outputs calculated
in Python, and may use `STORED` generated columns for cheap same-row formulas.

Analytical values normally use `DOUBLE PRECISION`; copied source values remain
exact `NUMERIC`. Percentage fields store ratios (`0.05` means 5 percent).
Python, as the only normal writer, strictly validates finite values, formulas,
warm-up nullability, and benchmark semantics. PostgreSQL retains keys, FKs,
basic bounds, and row-shape invariants rather than an exhaustive float check.

The table stores current calculated state, not revision history. Unchanged
reruns are idempotent. Source, SPX, and calculation-version changes trigger
tested affected-range recalculation. A calculation-state table is allowed only
if the recursive-equivalence prototype proves it necessary.

Model consumers see only complete publication units with one calculation
version and complete benchmark semantics. The package owns database-backed
scope locking across daily, backfill, CLI, and Airflow entry points; Airflow
scheduler limits are not the concurrency boundary.

Lookbacks count chronological observations, never future rows. TA-Lib warm-up
and unstable periods are versioned; expected pre-lookback non-finite output
becomes null, while post-lookback non-finite output fails calculation.
Subject/SPX observations align by exact date without forward fill. Adjustment
semantics remain provider-native and are disclosed. Backtest consumers still
own point-in-time universes, survivorship, execution timing, slippage, and
transaction costs.

## Version-1 Feature Families

- Source and state: OHLCV, dollar volume, observation count, up/down streaks.
- Returns: 1/2/3/5/10/20/63/126/252 observations.
- Bar structure: gap, intraday return, range percentage, close location.
- Trend: SMA 20/50/200; EMA 12/20/26/50; price/average distances;
  cross-distances; 20-observation SMA 50/200 changes.
- Range: 20/50/252 highs, 20/50 lows, and close distances.
- Momentum/volatility: RSI 14, ATR 14/percentage, 20/60 return volatility,
  1d/3d 20-observation z-scores.
- Bollinger: 20-observation price deviation, `%b`, and BandWidth; redundant
  upper/lower bands are not stored.
- Directional movement: +DI 14, -DI 14, and ADX 14.
- MACD: 12/26/9 line, signal, histogram, and normalized line/histogram.
- Volume: 20/60 average volume, 20 average dollar volume, relative volume 20.
- SPX: price ratio and 20/50 trend, 20/63/126/252 relative returns, and
  60/252 beta and correlation using `YAHOO/XIDX/SPX`.

Strategy booleans, thresholds, sector-relative features, and the remaining
TA-Lib catalog are deferred until a concrete consumer justifies them.

## Run, Report, And Runtime Contract

Every substantive daily/backfill run creates durable `report.json` and
professional Empire-branded `report.pdf`. They cover run scope, versions,
source readiness, feature/benchmark coverage, writes, warm-up/null state,
performance, warnings, and bounded diagnostics without recommendations or
full feature payloads.

Reusable code reads only `os.environ` and receives injected database/Core
services. Runtimes own environment loading. Airflow is orchestration only.

## How To Use This Checklist

Status values are `[ ]` not started, `[~]` in progress, and `[x]` complete.
Add a dated `Done:` note below the phase when completing a task. Move only fully
completed phases to the
[technical indicators action plan archive](tech-ind-task-plan-archive.md).

## Completed Phase Archive

Phases 0-12 are archived there with task IDs P0.1-P0.10, B1.1-B1.8,
S2.1-S2.8, I3.1-I3.7, C4.1-C4.8, T5.1-T5.8, X6.1-X6.8, W7.1-W7.10,
R8.1-R8.8, J9.1-J9.9, O10.1-O10.7, A11.1-A11.8, and V12.1-V12.8,
together with their `Done:` notes.

---

## Phase 13: Build Out Production And Start Daily Operation

Goal: upgrade the existing `hub-1` home-lab host for production, establish
durable local and NAS-backed operation, add deployment-aware Airflow cadence,
seed production history, build initial technical coverage, and start automated
daily EODData, Yahoo, and technical-indicator workflows while local development
stays manual.

Phase 13 starts only after V12.8 records a ready decision. Broad imports and
backfills run on the upgraded production host, not on the development laptop.
Each long-running step must have a reviewed scope, capacity check, durable
report, checkpoint or resume path, stop criteria, and post-run coverage audit.

| ID | Status | Goal | Complete When | Depends On |
|----|--------|------|---------------|------------|
| P13.1 | [x] | Size and procure the compact production host | Convert the V12.8 CPU, memory, storage-growth, database, container, and network assumptions into a reviewed in-place-upgrade or replacement configuration; evaluate a dedicated 64 GB RAM / 2 TB added local SSD Empire host with a separate AI host deferred, prioritizing the lowest practical complete price. Require Ubuntu Server LTS for non-macOS devices; retain the earlier complete-host and combined-host AI quotes as comparisons. Record the selected host and parts, expansion headroom, warranty/support tradeoff, expected delivery, and purchase decision. HPE is optional. | V12.8 |
| P13.2 | [ ] | Install the upgrade and establish the host baseline | Back up and shut down the existing HP Elite Mini 805 G8 `hub-1`, inspect the second M.2 position and retaining hardware, install the ordered matched 64 GB PNY kit and 2 TB WD_BLACK SSD, and prove firmware detection, dual-channel memory, full memory diagnostics, NVMe health, sustained load temperatures, and stable reboot while the return window is open. Recheck and patch BIOS, Ubuntu Server LTS, Docker/Compose, time synchronization, administrative access, firewall, power/restart behavior, existing-service recovery, and monitoring prerequisites. Preserve and verify the Mac's existing `ssh hub-1` path; install and authenticate Codex CLI plus the supported Linux sandbox on `hub-1`, expose `codex` through the remote login shell, and configure least-privilege production inspection access so Codex Desktop on the Mac can use an SSH project to read the deployed filesystem, service/container logs, and database diagnostics without making `hub-1` a development workstation. Record versions, serial-safe inventory, permissions, remote-access recovery, and the hardware rollback path. | P13.1 |
| P13.3 | [ ] | Connect production networking, local storage, and NAS | Preserve the stable `hub-1` identity, reviewed network configuration, and existing `/opt/empire` control/configuration tree. Partition and format the new 2 TB SSD, mount it directly at `/opt/empire/data`, and place `EMPIRE_POSTGRES_DATA_DIR`, `EMPIRE_AIRFLOW_LOGS_DIR`, `EMPIRE_AIRFLOW_PLUGINS_DIR`, and `EMPIRE_TEMP_DIR` beneath that mount. Create the production NAS shares and Core object-store/database-backup layout with least-privilege ownership. Prove UUID-based boot mounts, a local-volume sentinel, reconnect, local/NAS throughput, free space, backup placement, missing-mount service refusal, and recovery without disrupting the retained boot disk or existing services. Do not initialize or start Empire storage roots until every expected mount is present. | P13.2 |
| P13.4 | [ ] | Design deployment-aware Airflow cadence | Evaluate one shared DAG definition with a small validated deployment profile and environment-supplied schedules against separate local/prod DAG files. Prefer shared task logic and one DAG ID per workflow: local resolves EODData and Yahoo to `schedule=None`, production resolves explicit reviewed schedules, and the technical coordinator stays event-driven with `schedule=None`. Define parse-time validation, timezone/DST behavior, tags and observability, pause/rollback, configuration ownership, and safe behavior for missing or invalid settings. Duplicate DAG files are allowed only if Airflow import/serialization evidence shows the shared design is unsafe or materially harder to operate. | V12.8, A11.8 |
| P13.5 | [ ] | Implement and verify scheduling profiles | Implement the selected cadence configuration without duplicating package business logic. Add committed non-secret defaults/templates and deployment wiring; update the Yahoo provider-access decision and rollout contracts for a conservative production cadence. Tests must parse the same DAG code under local and production profiles, prove local source DAGs are manual, prove production EODData and Yahoo schedules are exact, prove catchup/overlap protections and source-triggered technical dispatch remain intact, and prove rollback to manual operation requires configuration plus the documented Airflow refresh/restart rather than a code fork. | P13.4 |
| P13.6 | [ ] | Deploy the reviewed Empire release | Create or update `/opt/empire/repos/empire` as the dedicated production checkout on `hub-1`, check out the exact commit reviewed after P13.5, and register that checkout as the production SSH project used by Codex Desktop on the Mac. Create the uncommitted production environment and secrets from the committed template, and configure the production Airflow profile, database, and mounted local/NAS storage roots without absorbing unrelated existing services. Select a Compose topology that does not start Empire's bundled Jellyfin service or collide with the existing `empire-hub-1` Jellyfin container/port/configuration. Build the required images, run Flyway, initialize Core storage roots only after mount validation, and initialize Airflow using repository workflows. | V12.8, P13.3, P13.5 |
| P13.7 | [ ] | Prove upgraded production infrastructure readiness | Run database, PgBouncer, storage, package, CLI, report, and Airflow preflights on the upgraded `hub-1`; verify expected DAGs and import health, exact production schedules, local-versus-production profile isolation, backups and restore procedure, service restart/reboot recovery, hardware health and temperature telemetry, memory and disk headroom, observability, and initial paused states before source loading. From Codex Desktop on the Mac over `ssh hub-1`, prove read-only inspection of the deployed revision, mounted filesystems, systemd/container/Airflow logs, and bounded PostgreSQL diagnostics; require explicit operator approval for code pulls, database writes or migrations, service restarts, and production-file changes, with normal development remaining on the Mac. Record the return-to-old-RAM/boot-only recovery path if the new hardware fails. | P13.6 |
| P13.8 | [ ] | Run the weekend Stooq starter import | Manually acquire and record the approved Stooq archive and provenance, run the production Stooq historical import on upgraded `hub-1` for the reviewed U.S. stock partitions with checkpoints, resource monitoring, and stop criteria, resume safely as needed, and audit counts, coverage, warnings, performance, Core lineage, JSON/PDF reports, and absence of canonical/source crossover. | P13.7 |
| P13.9 | [ ] | Backfill the Yahoo benchmark universe | Run the bounded seeded Yahoo index, yield, volatility, currency, commodity, and continuous-futures backfill on upgraded `hub-1` with provider-safe pacing, resource monitoring, and resume; verify SPX identity/history, calendar coverage, native semantics, request volume, lineage, and JSON/PDF reports. | P13.7 |
| P13.10 | [ ] | Build initial production technical coverage | After the Stooq and Yahoo source audits pass, backfill technical indicators in staged provider/market cohorts on upgraded `hub-1`. Verify counts, warm-up/null and generated/SPX coverage, publication isolation, resume, adjustment warnings, inactive-listing handling, no OHLCV mutation, reports, and the frozen production performance/RSS/disk gates on the actual Ryzen 5 PRO 5650G host before increasing scope. | P13.8-P13.9 |
| P13.11 | [ ] | Rehearse the automated production daily path | With normal automation still paused, temporarily exercise the production schedules or their exact scheduled-run semantics for bounded same-date EODData and Yahoo prerequisites followed by source-triggered technical refresh. Inspect effective-date derivation, readiness, atomic publication, idempotency, correction behavior, locking, Core lineage, reports, Airflow dispatch, and rollback; confirm the local profile remains manual. | P13.10, A11.8 |
| P13.12 | [ ] | Start the first Monday automated daily cycle | Enable the reviewed production EODData and Yahoo schedules while leaving local development manual. Release the technical coordinator only under the reviewed readiness and backlog procedure, then record same-date source completion, automatic dispatch, technical freshness, resource use, and recovery evidence. | P13.11 |
| P13.13 | [ ] | Observe bounded production operation | Verify at least three consecutive ready effective dates and one unchanged rerun within release targets; audit scheduled-run timing, queued wakes, warnings, source and benchmark coverage, provider request pressure, Ryzen 5 PRO 5650G CPU saturation, memory pressure, SSD/NAS growth and temperature, reports, backups, and stop conditions before normal activation. | P13.12 |
| P13.14 | [ ] | Close the production rollout gate | Record the deployed commit, exact upgraded `hub-1` hardware and storage layout, local and production cadence profiles, calculation version, supported universes, coverage, production performance, provider-access evidence, risks, recovery, and explicit go/no-go. On a go decision, leave the reviewed production source schedules and technical coordinator enabled while retaining `schedule=None` for the corresponding local-development source DAGs. | P13.13 |

P13.1 scope clarification (2026-09-02): the owner requires new hardware only;
the HP Elite Mini example establishes the compact form factor, not an HPE
vendor requirement. See the
[host sizing and procurement review](../stonks/tech-indicators-production-host-p13.1.md).
The latest same-date direction considers a dedicated 64 GB / 2 TB Empire
production host and a separate AI host later. Every non-macOS device must run
Ubuntu Server LTS. The review retains the earlier 128 GB combined-host quotes
and budget as comparison evidence; BOSGAME is no longer the recommendation.
The production budget releases its model-storage allowance to Empire headroom.
Exact-machine Ubuntu support and a fresh complete 64 GB / 2 TB quote remain
purchase checks. This changes procurement planning, not deployment or routing.
The owner subsequently prioritized stronger CPU responsiveness, quiet cooling,
and 12–24 months of planning headroom at 64 GB / 2 TB. The review now includes
a complete new Framework Desktop Max+ 395 / Noctua quote ($2,528; $2,817 with
three-year warranty), measured noise comparisons, and explicit Mac CPU and
Ubuntu Server LTS limitations. Its 4.5 L enclosure is larger than the HP Elite
Mini reference, so size acceptance remained pending at that stage. No purchase
had been approved at that stage.
The original HP i7-14700 / 64 GB / 2 TB Amazon configuration was then rechecked
at $2,099 assembled (seller Poly Molly). It leads on value and size; Framework
offers more measured parallel throughput, with similar single-core results in
separate reviews. Seller warranty and actual Ubuntu/Empire acceptance remain
unresolved; the comparison is not a production performance result.

P13.1 selected upgrade (2026-09-04): the owner will operate the existing
`hub-1` (HP Elite Mini 805 G8, Ryzen 5 PRO 5650G, Ubuntu Server LTS) for
approximately one year instead of buying a replacement. Live inventory
confirmed one 16 GB DDR4-2667 module, one visible healthy 512 GB Samsung boot
NVMe, and BIOS 02.17.00. The owner ordered a new PNY
`MN64GK2D43200-TB` matched 64 GB DDR4-3200 SODIMM kit and WD_BLACK SN7100
`WDS200T4X0E` 2 TB TLC NVMe SSD, with arrival shown for 2026-09-05. The
observed selected-offer planning subtotal is $721.98 before tax; the private
order confirmation governs the actual charge. RAM reaches the documented
64 GB maximum and both M.2 positions will be occupied after installation.
Physical M.2 fit, burn-in, storage setup, and the unchanged production
performance/recovery gates move to P13.2-P13.7.

Done: 2026-09-04 — selected and purchased the in-place `hub-1` upgrade in
`docs/stonks/tech-indicators-production-host-p13.1.md`; revised P13.2-P13.14
for hardware installation, mounted local/NAS storage, deployment, and measured
Ryzen 5 PRO 5650G acceptance. `git diff --check` and the focused standard-
library Markdown/phase assertions passed; no runtime, database, CLI, report,
or Airflow behavior changed.

P13 directory-layout handoff (2026-09-04): inspection of the added
`empire-hub-1` repository confirms `/opt/empire` already owns repositories,
secrets, host logs/backups/tmp, and existing service state. P13.3 therefore
keeps that boot-disk control tree and mounts the new SSD at
`/opt/empire/data`; P13.6 maps Empire's database/Airflow/temp settings there,
uses the reviewed NAS mount for durable Core objects and backups, and avoids
the aggregate Compose file's bundled Jellyfin collision with the existing
service. Exact UUIDs, NAS paths, UIDs/GIDs, and systemd units remain live-host
evidence for those tasks.

P13 remote-operations handoff (2026-09-04): P13.2 now establishes Codex CLI,
the Linux sandbox, and least-privilege access through the Mac's existing
`ssh hub-1` connection. P13.6 registers the deployed checkout as the remote
project, and P13.7 proves production filesystem, log, container, and bounded
database inspection while development and routine code changes remain on the
Mac.

---

## Deferred Work

- Sector-relative returns until point-in-time mappings exist.
- Strategy target flags and threshold-specific indexes.
- Portfolio/backtest engines and execution/performance analytics.
- Cross-sectional ranks until the historical universe is explicit.
- Stochastic, Williams `%R`, CCI, MFI, OBV, Chaikin A/D, Aroon, Parabolic SAR,
  Ichimoku, Keltner, candlestick-pattern, and cycle/Hilbert families.
- Intraday indicators and true session VWAP.
- Canonical/cross-provider consensus technical histories.
- Append-only technical revision history.

New indicators require a concrete consumer, exact versioned formula,
incremental behavior, storage/query justification, and independent regression.
