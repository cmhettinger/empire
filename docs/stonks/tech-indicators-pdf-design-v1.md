# Tech-Indicators PDF Design V1

Status: frozen presentation contract for R8.5 as of 2026-08-22.

This document defines the professional, human-readable PDF companion for the
daily and backfill technical-indicator reports. It extends the
[report schema](tech-indicators-report-schema-v1.md), the
[performance and release gates](tech-indicators-performance-release-gates-v1.md),
and the [source-value policy](tech-indicators-source-value-policy-v1.md).

The PDF is an operational report, not a market letter, security analysis,
screen, strategy, or recommendation. JSON remains authoritative for complete
structured facts. R8.6 implements this design from the same immutable
`TechIndicatorsReport`; R8.7 visually verifies its required variants; R8.8
stores it and proves paired facts agree.

## Render Boundary

- The domain renderer belongs in `empire-stonks-tech-indicators`. It accepts
  only one already validated immutable `TechIndicatorsReport` and an explicit
  output directory/filename. It performs no SQL, Core reads, recalculation,
  readiness decision, publication mutation, or environment loading.
- The renderer composes `ReportMetadata`, `RenderContext`, `PdfRenderer`,
  `professional_letter_title_page`,
  `professional_letter_disclaimer_page`, common tables, headings, styles, and
  header/footer templates from `empire-reports`. Domain language, section
  selection, family rollups, and presentation models remain package-owned.
- The workflow's PDF and JSON use the same `report_id`, schema version,
  generated timestamp, immutable facts, and Core metadata allowlist. PDF
  object naming and storage remain R8.8 concerns.
- Rendering must not infer a missing value, recompute a business fact, parse
  serialized JSON, or turn null into zero. Presentation-only totals may sum
  explicitly named immutable count fields; their grain and denominator must be
  printed.
- The local render is deterministic for the same report facts and branding
  bundle. Variable PDF producer timestamps or object metadata must not alter
  visible content. The renderer overwrites only its explicit local output path;
  Core publishing is separate.

Recommended R8.6 layout:

```text
empire_stonks_tech_indicators/reports/tech_indicators/
  __init__.py
  pdf/
    __init__.py
    render.py
    sections.py
    components.py
```

This is a simple domain layout, not a registry or plugin boundary.

## Format, Branding, And Accessibility

The artifact is US Letter portrait. Body pages use the shared `letter_body`
template and its established margins, Source Sans 3 body face, Cinzel display
face, Source Code Pro identifiers, Empire red accent, dark-grey text, and
horizontal color logo. If packaged fonts are unavailable, the normal
`empire-reports` fallback applies without changing content or pagination
requirements.

Shared visible text is exact:

| Element | Text |
|---|---|
| Header | `EMPIRE RESEARCH DIVISION` |
| Footer/classification | `PROPRIETARY / INTERNAL USE ONLY` |
| Daily title | `Daily Technical Indicators Operational Report` |
| Backfill title | `Backfill Technical Indicators Operational Report` |
| Subtitle | `Provider-Native Calculation and Publication Evidence` |
| Disclaimer banner | `DISCLAIMER` |
| Disclaimer warning | `Operational evidence only; not investment advice or a trading recommendation.` |

The cover shows the Empire logo, title, subtitle, report date, and
classification. Daily uses `identity.effective_date` as the report date.
Backfill also uses `identity.effective_date` as the generated workflow's as-of
date; its inclusive requested range appears in the first body-page scope card
and must not be mislabeled as one trading date.

Page 2 uses the reusable Empire disclaimer page with the exact warning above.
The first body page repeats a smaller use-limitation callout:

> Operational calculation and publication evidence only. This report contains
> no investment advice, target, ranking, strategy, or trading recommendation.
> Values remain provider-native and may not be comparable across providers.

Body headers add the exact effective date for daily and `start_date – end_date`
for backfill. Body footers number content pages starting at 1 after the two
front-matter pages. Every page repeats the classification.

Color reinforces but never replaces text. Status chips and charts print their
label or value directly and use this palette:

| Status | Visual treatment |
|---|---|
| `PASS` | green plus visible `PASS` |
| `WARN` | amber plus visible `WARN` |
| `NO_OP` | slate blue plus visible `NO OP` |
| `PARTIAL` | amber plus visible `PARTIAL — UNPUBLISHED` |
| `FAIL` | Empire red plus visible `FAIL — UNPUBLISHED` |

Tables repeat header rows after a page break. They use a minimum 8-point font,
wrapped cells, alternating neutral row fills, and left-aligned text except
right-aligned numbers. UUIDs and hashes use the monospace face and may wrap at
safe separators; they are never clipped or silently shortened. Charts require
a visible title, direct data labels, a text caption naming the denominator,
and an adjacent table carrying the same values. No meaning may depend on hue,
legend order, decorative iconography, or tooltip behavior.

## Page And Section Order

The renderer uses this fixed order. A section is present even when its facts
are empty; the section then prints the empty-state language defined below.

| Order | Section | Required content |
|---:|---|---|
| 1 | Cover | branding, workflow title, subtitle, report date, classification |
| 2 | Disclaimer | exact warning and Empire disclaimer treatment |
| 3 | Executive Status | outcome, run identity, generated time, status narrative, use limitation |
| 4 | Scope And Readiness | requested/resolved scope, lock, source evidence, publication state, backfill progress |
| 5 | Coverage And Writes | root counts, provider/market/type dimensions, dates, versions, write/batch outcomes |
| 6 | Feature Quality | ten fixed feature-family rollups, null reasons, bounded anomaly detail |
| 7 | Benchmark Health | reviewed SPX identity/readiness, linkage, alignment, complete-window counts |
| 8 | Performance | timing, throughput, paging/batching, memory, ordered phase duration |
| 9 | Warnings And Failures | complete aggregates and bounded diagnostic samples |
| 10 | Methodology And Disclosures | calculation profile, library versions, units, null semantics, provider-native notes, limitations |

The executive section begins on body page 1. Scope/readiness may follow it on
the same page when both blocks fit. Feature Quality, Benchmark Health,
Warnings And Failures, and Methodology each begin on a new page. Other sections
flow naturally with `KeepTogether` only for a heading, its introductory line,
and the first table row. A renderer must not reserve a mostly blank page merely
to keep a whole long table together.

The whole PDF is at most 25 pages and 5 MiB. Daily rendering must complete
within 30 seconds and 512 MiB peak RSS; backfill rendering must complete within
60 seconds and 512 MiB. Cover and disclaimer count toward the page bound.
Required facts may be compacted through the deterministic rules below, never
by clipping, dropping a failure, shrinking below the minimum type size, or
splitting one report into per-listing artifacts.

## Executive Status

The opening status block contains:

- the exact outcome label and one outcome-specific sentence;
- `workflow_kind`, schema version, full `run_id`, `core_subject_key`, report ID,
  generated UTC timestamp, and effective date;
- publication ID or `Not created`, and existing readiness token or `Not
  applicable`; hashes remain full text;
- selected listings, source rows, evaluated rows, payload rows, published rows,
  inserted plus updated rows, warning count, and failure count; and
- one prominent publication badge derived only from
  `publication.report_phase` and `publication.readiness_at_report`.

Outcome sentences are fixed:

| Outcome | Sentence |
|---|---|
| `PASS` | `The workflow completed with no retained warning or failure.` |
| `WARN` | `The workflow completed with retained warnings requiring review.` |
| `NO_OP` | `Ready source and publication evidence required no feature mutation.` |
| `PARTIAL` | `Backfill progress is safely resumable and remains unpublished.` |
| `FAIL` | `The workflow failed and no incomplete candidate became published.` |

These sentences describe the immutable report snapshot. A prepared candidate
must say `NOT READY AT REPORT TIME`; the PDF cannot predict the later terminal
publication commit.

## Scope And Readiness

Scope prints all scalar selectors and flags. Empty provider, market, or
instrument-type arrays display `All eligible`; a non-empty array is joined in
its existing sorted order. No resolved listing UUID array is reconstructed.
The full scope hash is printed with requested and resolved listing counts.

Readiness uses three compact blocks:

1. **Writer lock:** name, signed key, outcome, heartbeat counts, and
   `Held through report: Yes`. It never displays backend, owner, connection, or
   wait-event details.
2. **Source readiness:** decision, date/range, every provider-evidence row, and
   all complete reason counts. A required provider prints `Ready` or `Not
   ready`; a non-required provider prints `Informational`. A null latest Core
   run ID prints `Not available`.
3. **Publication:** method, report phase, candidate status, readiness, complete
   reason counts, membership/source/payload counts, benchmark contract, and
   resume cursor when present. `NOT_READY` is never softened to pending success.

For a backfill, show planned/completed batch counts, batch size, remaining
listing/row counts, resumed-from cursor, and last-completed cursor. Daily prints
`Backfill progress: Not applicable` rather than a zero-filled progress table.

## Coverage And Writes

The root coverage table retains eligible, selected, source, evaluated, payload,
and published listing/row facts at their named grains. Provider, market, and
instrument-type tables show their complete sorted rows with five count columns;
these dimensions remain separate and are never added together.

Date coverage shows source/payload first and last dates plus the three
effective-date row counts. Version coverage shows every calculation version,
listing count, and row count. If there are no rows, dates display `No data` and
the table retains zero counts.

Writes show all ten immutable fields. `Persisted` may be displayed as the
explicit presentation sum `inserted + updated`, labeled exactly `Persisted
(inserted + updated)`. Equivalent, copied-equivalent, unchanged, deleted,
failed, committed, and rolled-back facts remain individually visible.

## Feature Quality

The 76 feature rows are rolled up into exactly these ten non-overlapping
families. R8.6 must assert at import/test time that the union equals the ordered
`REPORT_FEATURE_FIELDS` inventory and that no field occurs twice.

| Family | Fields |
|---|---|
| Returns | `return_1d_pct`, `return_2d_pct`, `return_3d_pct`, `return_5d_pct`, `return_10d_pct`, `return_20d_pct`, `return_63d_pct`, `return_126d_pct`, `return_252d_pct` |
| Bar structure and streaks | `gap_1d_pct`, `consecutive_up_days`, `consecutive_down_days`, `intraday_return_1d_pct`, `daily_range_pct`, `close_location_1d` |
| Trend | `sma_20`, `sma_50`, `sma_200`, `ema_12`, `ema_20`, `ema_26`, `ema_50`, `sma_50_change_20d_pct`, `sma_200_change_20d_pct`, `pct_sma_20`, `pct_sma_50`, `pct_sma_200`, `pct_ema_20`, `pct_ema_50`, `pct_sma_20_vs_50`, `pct_sma_20_vs_200`, `pct_sma_50_vs_200` |
| Range | `hh_20`, `hh_50`, `hh_252`, `ll_20`, `ll_50`, `pct_hh_20`, `pct_hh_50`, `pct_hh_252`, `pct_ll_20`, `pct_ll_50` |
| Momentum and volatility | `rsi_14`, `atr_14`, `return_volatility_20d_pct`, `return_volatility_60d_pct`, `return_1d_zscore_20d`, `return_3d_zscore_20d`, `atr_pct_14` |
| Bollinger | `price_stddev_20`, `bollinger_percent_b_20_2`, `bollinger_bandwidth_20_2` |
| Directional movement | `plus_di_14`, `minus_di_14`, `adx_14` |
| MACD | `macd_12_26`, `macd_signal_12_26_9`, `macd_histogram_12_26_9`, `macd_12_26_pct`, `macd_histogram_12_26_9_pct` |
| Volume | `volume_avg_20`, `volume_avg_60`, `dollar_volume_avg_20`, `dollar_volume`, `volume_ratio_20` |
| SPX relative | `rel_spx`, `pct_rel_spx_20`, `pct_rel_spx_50`, `relative_return_spx_20d_pct`, `relative_return_spx_63d_pct`, `relative_return_spx_126d_pct`, `relative_return_spx_252d_pct`, `spx_beta_60d`, `spx_beta_252d`, `spx_correlation_60d`, `spx_correlation_252d` |

Each family row sums eligible, populated, warm-up null, dependency null,
unsupported null, and unexpected null counts across its member features. The
table labels these as **feature-observations**, not source rows or listings,
and prints the family field count. A stacked horizontal coverage chart may be
rendered from populated/warm-up/dependency/unsupported counts only when the
same table is present. Unexpected nulls are not hidden in the chart: any
nonzero value receives a red text callout and detail table.

The PDF does not print 76 all-zero or routine feature rows. It prints an
exception detail row for every feature with `unexpected_null_count > 0`, then
at most 18 additional features with a nonzero dependency or unsupported count
in immutable profile order. The heading states `Showing N of M feature
exceptions`; complete per-feature facts remain in JSON. Warm-up alone is
expected and does not enter exception detail.

## Benchmark Health

Benchmark Health names the reviewed benchmark exactly as `YAHOO / XIDX / SPX`,
states `Exact-date alignment; no forward fill`, and displays whether it was
required, resolved, ready, and present on the effective date. It shows the full
resolved provider-listing UUID when present and the frozen benchmark contract
version.

Coverage displays supported/unsupported listings, linked/unlinked payload
rows, aligned rows, effective-date aligned rows, and complete 20/50/60/63/126/
252 observation-window counts. Every window count is labeled as rows, not
listings. The section must not call relative return alpha, claim total-return
comparability, or interpret beta/correlation as a recommendation.

## Performance

Performance prints start, finish, elapsed seconds, peak RSS or `Not measured`,
evaluated/persisted throughput with their explicit elapsed denominator, read
page count, write batch count, largest read/write batch rows, and longest write
transaction or `Not measured`.

All recorded phases appear in frozen contract order. A horizontal duration bar
chart is optional and must be paired with the exact seconds table. It must not
imply phase durations partition total elapsed time; the caption says they are
non-overlapping recorded phase durations and may sum to less than wall time.
The report describes measurements only. It does not label a run fast, slow,
healthy, or release-ready by comparing with P0.8 gates; release decisions
remain outside the immutable R8.3 facts.

## Warnings, Failures, And Samples

All warning and failure aggregates are printed in their existing code order
with complete count and fixed message. Empty states are exact:

- warnings: `No retained warnings.`
- failures: `No retained failures.`
- diagnostics: `No bounded diagnostic samples were retained.`

Failures render before warnings. Each aggregate states how many sample IDs it
references. Diagnostic detail is divided into Failure, Warning, Readiness, and
Coverage subsections; each subsection shows at most 10 rows chosen in the
existing immutable sample order. Across the whole PDF, show at most 18 distinct
listing UUIDs; once that ceiling is reached, later sample tables keep
counts/messages but omit additional listing rows and state the number omitted.
A sample is assigned once using priority failure, warning, source-readiness
reason, publication-readiness reason, then coverage anomaly; this prevents
duplicate rows from consuming the bounds.

Sample columns are ID, code, provider/market/ticker, listing UUID, date, field,
and fixed message. Null cells display an em dash. No feature value, OHLCV,
formula input, raw exception, SQL, or arbitrary source text is added.

## Methodology And Provider-Native Disclosures

Methodology is concise and operational. It prints:

- schema, package, calculation, benchmark-contract, Python, NumPy, TA-Lib
  Python/C, and PostgreSQL versions;
- 76 analytical fields: 53 Python-computed and 23 PostgreSQL generated;
- chronological stored-observation lookbacks, complete-window warm-up, null
  rather than sentinel zero, percentage fields stored as ratios, and
  post-warm-up non-finite/unexpected output failing validation;
- provider-native current-state OHLCV, correction sensitivity, no canonical
  identity, no cross-provider normalization, no corporate-action
  normalization, and exact-date SPX alignment without fill; and
- nominal dollar volume is provider-native price times volume and is not
  asserted to be USD or cross-listing comparable.

Every code in `native_value_semantics.notes` is rendered once, in its existing
order, using the fixed reviewed `NATIVE_VALUE_NOTE_MESSAGES` text. A report
with no notes prints `No provider-specific disclosure applies to this empty
scope.` Renderers cannot accept replacement prose.

The methodology section contains no source or feature values, thresholds,
ranks, screens, forecasts, targets, trade language, or suggestions to buy,
sell, hold, size, time, or avoid an instrument. Links in the PDF may reference
Empire's versioned internal contracts, but the artifact must remain
understandable without opening them.

## Deterministic Compaction And Empty States

Compaction order is fixed:

1. retain cover, disclaimer, executive status, every aggregate warning and
   failure, every required section, and all complete count tables;
2. retain every unexpected feature row and at most 18 other feature-exception
   rows in profile order;
3. retain at most 10 sample rows per diagnostic subsection and 18 distinct
   sampled listing UUIDs across the PDF;
4. omit optional charts before reducing any table or text; and
5. fail rendering if the 25-page/5-MiB bounds still cannot be met.

No-op still renders all sections: zero writes, existing publication readiness,
ordinary coverage, no backfill table, and no warnings/failures. Failure before
readiness renders `NOT_APPLICABLE` and `Not evaluated`, not healthy-looking
zeros. An empty selected scope renders explicit zero counts and `No data`.
Partial backfill prominently repeats `UNPUBLISHED` and the exact resume facts.

## R8.6-R8.8 Acceptance Handoff

R8.6 must add focused tests proving:

- only `TechIndicatorsReport` is accepted and no report fact is mutated;
- daily/backfill titles, all five outcome labels, disclaimer, classification,
  section order, version text, and fixed disclosures are present;
- the ten-family map covers all 76 features once and family sums reconcile;
- complete dimension/issue aggregates survive compaction, sample ceilings are
  deterministic, and unexpected nulls cannot be hidden;
- null/zero, ratio/count, readiness/publication, partial/no-op/failure language
  remains distinct; and
- output is a valid PDF within the frozen size/page bounds.

R8.7 renders success, warning, no-op, failure, resumed partial backfill, and
largest bounded samples. It inspects every page for clipping, wrapping,
repeated headers, orphan headings, sparse pages, legibility, chart/table
agreement, status text, branding, and the 25-page limit.

R8.8 stores `report.pdf` through Core with the frozen PDF kind/name/media type,
same run relationship and nine metadata facts as JSON, and no expiration. Its
paired-fact test compares report ID, schema, workflow, outcome, effective date,
calculation version, scope hash, publication ID, generated time, primary
counts, writes, readiness/publication state, warning/failure counts, and
benchmark coverage from one immutable model rather than scraping PDF text.
