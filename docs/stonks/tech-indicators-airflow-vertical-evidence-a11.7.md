# Technical Indicators Airflow Vertical Evidence A11.7

## Scope

This records the bounded A11.7 deployed-runtime verification performed on
2026-08-29. It starts at two valid source-completion fixtures, runs their exact
date-scoped provenance through the live technical-indicator coordinator, and
inspects the resulting Core, publication, JSON, and PDF state. It does not call
either external market-data provider and does not decide the production
cadence assigned to A11.8.

The verification used
`tools/tech-indicators/airflow-vertical.py`. The probe refuses to create a
fixture when SPX already has active technical publication membership or slot
rows. It records exact identifiers, matches workflow runs by the resolved Core
subject, validates before cleanup, and deletes only recorded fixture state.

## Fresh Runtime

`make airflow-build` completed all 21 image stages with a no-cache dependency
install. `make airflow-recreate` then recreated the API server, scheduler, DAG
processor, triggerer, and worker from that image. The live runtime reported:

- Apache Airflow `3.2.1`;
- `apache-airflow-providers-standard` `1.12.3`;
- `python -m pip check`: `No broken requirements found.`;
- `airflow dags list-import-errors --output json`: `[]`;
- all three EODData, Yahoo, and technical-indicator DAGs registered.

The technical-indicator coordinator began paused, was unpaused only for the
two bounded runs below, and was returned to paused state before artifact
inspection. Its schedule remained `None` throughout.

## Fixture And Airflow Runs

The probe selected the latest exact SPX bar date, `2026-08-03`, and created one
active `EODDATA/NASDAQ` equity listing with one same-date bar. The resolved
two-listing daily scope was ready with Core subject:

```text
scope:80eb899f853f271f9f604d1d09705d856aa3b0d8076ca41bcb12cd86aa2bd6a7
```

The healthy source completion fixtures were:

| Provider | Source Core run | Coordinator run |
|----------|-----------------|-----------------|
| EODDATA | `87bfb38e-4390-4779-bc3e-bcff13ee6221` | `source__eoddata__87bfb38e-4390-4779-bc3e-bcff13ee6221` |
| YAHOO | `29b97db3-c444-4b48-9712-08a5b9a52de2` | `source__yahoo__29b97db3-c444-4b48-9712-08a5b9a52de2` |

Each coordinator run received the package-owned source provenance plus only
the two exact fixture listing IDs. Both DAG runs succeeded. In both runs,
`check_source_readiness` and `run_tech_indicators_daily` succeeded; no task was
skipped, retried, or failed.

## Core, Publication, And Objects

The first wake created succeeded Core run
`49062042-8475-4833-bd87-912ec145cd7f` with outcome `PASS`. It created one
`PUBLISHED` daily publication,
`b52d9c62-cb23-4076-b0e5-0c6540fb5ec1`, with exactly two active listing
memberships. Four committed batches inserted 15,498 rows: one fixture row and
15,497 SPX history rows. There were zero failed or rolled-back batches.

The second wake created succeeded Core run
`c71c1cff-5e71-4584-b173-09736611f303` with outcome `NO_OP`. It created no
second publication and reported zero batches and zero inserts, updates, or
deletes.

Each Core run owned exactly one JSON and one PDF object:

| Outcome | Kind | Object ID | Bytes | SHA-256 |
|---------|------|-----------|------:|---------|
| PASS | JSON | `71ad6700-d0bb-4806-a040-70f769d6cb50` | 21,362 | `5df2241734da5c39dc521df38c6dfdcff085e57e3ae08631fcde00e3556299da` |
| PASS | PDF | `76ecbc9d-a42c-413e-af34-e26492c0678f` | 176,739 | `0c5efadf062d10c53090b2ba78200c30eaf3d5acae5f2811e01c8e2196f692fa` |
| NO_OP | JSON | `4a5c7ff9-2e3f-4e28-a68e-2a97eec17db5` | 21,290 | `8a8427b2a0adee48eec9040f953e153fc5909145526247961e741e615b7a236d` |
| NO_OP | PDF | `f5ae4750-6c12-432c-83a6-d823ac3b94e4` | 176,726 | `78d79d9b60a423241b94ba3ca8d60e85e54688ad5e83b96570cbfa245dd75894` |

The probe reread every object through Core, matched its stored size and SHA-256
checksum, parsed both schema-V1 JSON documents, and verified their run, scope,
outcome, and exact EODData/Yahoo evidence IDs. `pdfinfo` independently
identified both reports as 12-page PDF 1.4 documents; the probe also checked
their PDF header and EOF framing.

## Cleanup And Rollout State

Cleanup removed the exact four Core runs, four object rows and files, one
publication, fixture membership and payload rows, source bar, and provider
listing. Its six database residue counts and report-file residue count were all
zero. The two successful Airflow DAG-run records remain in Airflow metadata as
deployment evidence.

After cleanup, the live import-error result remained `[]`, and
`stonks_tech_indicators_daily_refresh` was confirmed paused. A11.8 therefore
retained the full cadence, pause, backlog, and rollback decision. It
subsequently selected event-driven source-completion operation while keeping
the coordinator paused until the P13.14 go decision; see
`tech-indicators-airflow-rollout-v1.md`.
