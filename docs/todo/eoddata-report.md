# EODData Daily Market Report TODO

## Purpose

This document tracks logical pages present in the legacy daily report that are
not yet implemented in Empire's EODData daily market report.

The comparison source is `tmp/2026-03-30-daily.pdf`. Page numbers below refer
to that 67-page legacy report. The current Empire report intentionally avoids
placeholder pages and unsupported claims: a page should be added only when its
data and methodology are supported by the current schema or by a tested
calculation over that data.

## Provider-Separated Benchmark Implementation

Legacy pages 5-8 are intentionally not part of the EODData equity report. Their
supported equivalents are implemented in the Yahoo Daily Benchmark Report,
which uses active Yahoo listings, stable Empire tickers, exact-date coverage,
session-policy-aware unavailable states, and provider-native continuous futures.
This preserves the boundary between EODData equities and Yahoo benchmarks while
allowing both reports to evolve independently.

## Missing Pages

### Sector and Industry Analysis

| Legacy pages | Page or section | Why it is not implemented |
| --- | --- | --- |
| 26 | Sector Performance | EODData provider listings do not currently carry a reliable sector taxonomy for the report universe. Joining unrelated Yahoo or canonical classifications would violate the current provider-native boundary. |
| 27-30 | Industry Performance | Reliable provider-native industry membership is unavailable. The legacy page also required a minimum group size, which cannot be applied correctly until classification coverage and taxonomy ownership are defined. |

These pages require a deliberate classification capability with taxonomy,
source, validity dates, provider-to-security mapping, and coverage reporting.

### Technical Indicator Pages

| Legacy pages | Page or section | Why it is not implemented |
| --- | --- | --- |
| 39-40 | High-Quality Trending Stocks | Requires tested RSI, moving-average, relative-volume, and trend calculations with explicit lookback sufficiency. Some legacy filters also depend on relative strength versus SPX. |
| 41-42 | Breakout Watchlist | Requires 20-day highs, 50-day moving averages, volume ratios, and deterministic handling of incomplete history. |
| 43 | Relative Strength Leaders | Requires a supported SPX benchmark series plus aligned-date relative-strength calculations. The benchmark capability is not yet available. |
| 44-45 | Pullback in Uptrend | Requires 20-day EMA, 50-day and 200-day moving averages, RSI, distance from recent highs, volume ratios, and sufficient historical coverage. |
| 46-47 | Overbought | Requires a tested RSI calculation layer and minimum-history rules. |
| 48-49 | Oversold | Requires a tested RSI calculation layer and minimum-history rules. |
| 50-51 | Penny Stock Movers | Requires RSI, 20-day volume ratios, price-band eligibility, and a more reliable instrument-type filter for excluding warrants, rights, units, and similar listings. |
| 52-53 | Penny Stock Strength | Requires the Penny Stock Movers inputs plus supported relative strength versus SPX. |
| 54 | Top 20 Investments by Momentum | Requires relative strength versus SPX, RSI, moving-average trend state, volume ratios, and an approved composite ranking. |
| 55 | Top 20 by Pullback Opportunity | Requires RSI, relative strength, recent-high distance, moving-average trend state, volume ratios, and an approved composite ranking. |

Most raw inputs for standalone rolling indicators can be derived from stored
OHLCV history, but Empire does not yet have the reusable indicator calculation
and validation layer. Before these pages are added, that layer needs exact
formulas, lookback requirements, missing-session behavior, split/adjustment
semantics, and PostgreSQL integration tests. SPX-relative pages additionally
depend on the benchmark capability above.

### Volatility Pages

| Legacy pages | Page or section | Why it is not implemented |
| --- | --- | --- |
| 56 | Highest Volatility Names | Requires tested ATR and ATR-percent calculations, RSI, 20-day volume ratios, and sufficient historical coverage. |
| 57 | High Volatility Leaders | Requires the volatility calculations plus moving-average trend state and relative strength versus SPX. |

These pages should be implemented with the same future indicator layer rather
than embedding report-specific rolling calculations in the PDF renderer.

### Data Quality

| Legacy pages | Page or section | Why it is not implemented |
| --- | --- | --- |
| 65 | Data Quality | The existing run-status JSON/PDF reports run-scoped acquisition, parsing, reconciliation, and write outcomes. A date-scoped market report may combine bars contributed by multiple runs, but the current OHLCV tables do not retain all staged quality facts by trading date. |

A market-report data-quality page needs a separate date-scoped contract. It
should distinguish current database coverage from run-specific ingest quality
without duplicating or contradicting the existing run-status report.

### Legacy Placeholder Pages

| Legacy pages | Page or section | Why it is not implemented |
| --- | --- | --- |
| 66 | Market Heatmap | The legacy page was only a placeholder. A real heatmap requires sector or industry classification, an aggregation method, a visual encoding contract, and coverage disclosure. |
| 67 | Selected Charts | The legacy page was only a placeholder. A real page needs deterministic chart-selection rules, historical-series queries, a reusable chart component, and a policy for missing or insufficient history. |

These should not be recreated as empty scaffolding. They should be added only
after their data, selection, and visualization contracts are defined.

## Already Implemented

The following legacy capabilities have current Empire equivalents and are not
part of this TODO:

- Professional title and disclaimer pages.
- Executive summary, exchange breadth, and return distribution.
- Session and per-exchange leaders and laggards.
- High-volume leaders by exchange.
- Low-volume equities with positive reported volume by exchange.
- High-Volume, Low Movement by exchange.
- Unconfirmed Price Moves using a 5% absolute return and bottom-quintile volume.
- High-Conviction Movers using price-mover and high-volume overlap.
- Magnificent Seven performance.
- Configured Dow 30 and Nasdaq-100 basket performance with coverage disclosure.
- Price and volume anomalies supported by the current schema.
- Methodology, scope, and provider-native capability disclosures.
- Core U.S., European, Asia-Pacific, regional, and global index benchmarks in
  the separate Yahoo Daily Benchmark Report.
- Yahoo volatility, currency, Treasury-yield, equity-index-futures, commodity,
  energy, metals, agriculture, and livestock benchmark pages.
