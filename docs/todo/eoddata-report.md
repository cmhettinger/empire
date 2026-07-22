# EODData Daily Market Report TODO

## Purpose

This document tracks logical pages present in the legacy daily report that are
not yet implemented in Empire's EODData daily market report.

The comparison source is `tmp/2026-03-30-daily.pdf`. Page numbers below refer
to that 67-page legacy report. The current Empire report intentionally avoids
placeholder pages and unsupported claims: a page should be added only when its
data and methodology are supported by the current schema or by a tested
calculation over that data.

## Missing Pages

### Indices and Benchmarks

| Legacy pages | Page or section | Why it is not implemented |
| --- | --- | --- |
| 5 | Core U.S. Benchmarks and Volatility/Macro | The provider-native EODData equity report does not yet have a supported index benchmark universe or reliable mappings for SPX, DJI, NDX, VIX, MOVE, and DXY. |
| 6 | Europe and Asia/APAC Indices | International index series and their provider-native symbol mappings are not yet modeled for this report. |
| 7 | India, Americas ex-U.S., Emerging Markets, and Global Indices | The required benchmark series and mappings are not yet available through the current report model. |
| 8 | Commodity, Energy, and Metals Benchmarks | Commodity and macro benchmark series are not yet part of the EODData daily report universe. |

These pages should wait for an explicit benchmark/index capability rather than
using unversioned ticker guesses. That capability needs durable provider
symbols, benchmark identity, coverage checks, and clear adjustment semantics.

### Additional Volume and Mover Analysis

| Legacy pages | Page or section | Why it is not implemented |
| --- | --- | --- |
| 10, 12, 14 | Low Volume - NYSE, NASDAQ, and NYSE American | The current report implements high-volume leaders but not the inverse low-volume ranking. Before adding it, the eligibility rule needs a useful liquidity floor so the pages do not become lists of dormant or immaterial listings. |
| 24 | Unconfirmed Price Moves | This requires a defined low-volume threshold combined with a large-move threshold. The legacy implementation used a cross-sectional volume percentile; Empire has not yet approved or tested that methodology for the provider-native universe. |
| 25 | High-Conviction Movers | This requires a documented intersection between outsized returns and high-volume participation. The current report has both mover and volume data, but the overlap rule and ranking have not yet been formalized or tested. |

These pages can be built from current OHLCV data once their eligibility,
threshold, and ranking contracts are made explicit. They should use the normal
one-page pattern of up to 12 semantic quote tiles followed by the matching
detail table.

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
- High-Volume, Low Movement by exchange.
- Magnificent Seven performance.
- Configured Dow 30 and Nasdaq-100 basket performance with coverage disclosure.
- Price and volume anomalies supported by the current schema.
- Methodology, scope, and provider-native capability disclosures.

