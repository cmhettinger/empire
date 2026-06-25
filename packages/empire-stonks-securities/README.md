# empire-stonks-securities

Reusable securities reference-data utilities for Empire stonks.

This package owns package-level config, SEC source acquisition, source
verification, provider observations, issuer/security/listing upserts, validation,
conflict reporting, and daily summary reporting for SEC-backed securities
reference data. Airflow and other runtimes should call into this package rather
than embedding provider, object-store, or security-master logic directly.

## Config

The seed config currently lives at:

```text
object-store/config/stonks-securities/config.yml
```

Publish it to the Empire object store with:

```bash
bin/stonks-securities-put-config
```

The canonical object-store registration is:

```text
config:stonks-securities/config.yml
```

with logical name:

```text
stonks-securities-config
```

SEC acquisition settings are under `stonks_securities.sec`,
`stonks_securities.rate_limit`, and `stonks_securities.download`.

Set `stonks_securities.sec.user_agent` to a realistic contact-bearing value
before running against SEC.gov, for example:

```yaml
sec:
  user_agent: "Empire Stonks Securities/0.1 (name@example.com)"
```

The downloader always sends that User-Agent. Rate limiting defaults to 5
requests per second in the seed config, below SEC's 10 requests per second
limit. Retry count and exponential backoff are configured by
`max_retries` and `retry_backoff_seconds`.

## SEC Collection

Download one configured fixed source:

```bash
bin/stonks-securities-collect \
  --config-file object-store/config/stonks-securities/config.yml \
  source sec_submissions_zip
```

Download configured fixed sources by naming them explicitly:

```bash
bin/stonks-securities-collect \
  --config-file object-store/config/stonks-securities/config.yml \
  source sec_company_tickers_exchange sec_company_tickers sec_submissions_zip
```

Download quarterly EDGAR `master.zip` files for a year range:

```bash
bin/stonks-securities-collect \
  --config-file object-store/config/stonks-securities/config.yml \
  quarterly --start-year 2024 --end-year 2026
```

Load the published config from the object store by logical name:

```bash
bin/stonks-securities-collect \
  --config-logical-name stonks-securities-config \
  source sec_company_tickers sec_submissions_zip
```

Load a specific stored config object:

```bash
bin/stonks-securities-collect \
  --config-object-id 00000000-0000-0000-0000-000000000000 \
  quarterly --start-year 2024 --end-year 2024 --quarter 1
```

Override the object-store destination and deterministic acquisition folder:

```bash
bin/stonks-securities-collect \
  --config-file object-store/config/stonks-securities/config.yml \
  --storage-root global \
  --storage-key stonks/securities \
  --acquisition-date 2026-06-10 \
  --acquisition-id 512578ba-2f75-42be-89b5-6dfc47ea36c1 \
  source sec_submissions_zip
```

By default the command writes to storage root `global` with object key prefix
from `EMPIRE_STORAGE_KEY_STONKS_SECURITIES`, falling back to
`stonks/securities`. Files are organized under deterministic acquisition
folders:

```text
stonks/securities/runs/YYYY/MM/DD/manual/<source>/
```

Use `--acquisition-id` to provide a DAG/run identifier. Re-running the same
command skips a source when both the final file and `<filename>.metadata.json`
sidecar already exist, unless `--force` is set.

Each sidecar includes `source_code`, `source_url`, `downloaded_at`,
`file_path`, `size_bytes`, `sha256`, `http_status`, `etag`, and
`last_modified`. Large downloads are streamed to `EMPIRE_TEMP_DIR` and then
moved into the object store through `ObjectStore.put_file()`.

The CLI acquisition command only downloads and caches SEC source files. The
daily Airflow chain described below performs verification, observation loading,
canonical upserts, and report generation.

## Airflow

`empire-stonks-securities` is installed into the Airflow image by
`deploy/docker/airflow/Dockerfile`. The Airflow Compose stack passes
`EMPIRE_STORAGE_KEY_STONKS_SECURITIES` through to all Airflow services alongside
the other Empire storage keys.

The daily SEC security-master chain is manual-only today. It starts with:

```text
dags/stonks/stonks_securities_daily_scrape.py
```

The scrape DAG currently downloads:

```text
sec_company_tickers_exchange
sec_company_tickers
```

The DAG loads the published `stonks-securities-config` object, starts a core run,
uses that run id as the acquisition folder, and writes each SEC file plus its
metadata sidecar to the global object store.

The scrape DAG then triggers the rest of the chain with the same source
`run_id`:

```text
stonks_securities_daily_verify
stonks_securities_daily_observations
stonks_securities_daily_issuers
stonks_securities_daily_securities
stonks_securities_daily_listings
stonks_securities_daily_validation
stonks_securities_daily_conflicts
stonks_securities_daily_refresh_summary
```

The stages are intentionally thin Airflow wrappers. Package code performs the
work:

- verify parses the two downloaded SEC JSON files, validates checksums, and
  writes a durable verify report.
- observations writes parsed SEC rows to `stonks.provider_observation` and links
  them to `stonks.provider_source_snapshot`.
- issuers, securities, and listings reconcile eligible observations into
  canonical tables and write `stonks.provider_evidence`.
- validation checks source coverage, entity counts, evidence coverage, listing
  quality, exchange quality, duplicates, orphans, and conflict candidates.
- conflicts emits reviewable conflict candidates for identity, listing, exchange,
  and evidence issues.
- daily summary links verify, validation, and conflict reports and summarizes
  freshness, deltas, warnings, failures, and stage health.

Reports are written under deterministic run-report paths:

```text
stonks/securities/runs/YYYY/MM/DD/run-reports/{verify,validation,conflicts,summary}/
```

When generated by Airflow, report objects are stored with `object_scope = 'run'`
and the source scrape run id. Manual/CLI report writes remain manual-scoped.

Healthy zero-change days are expected. If SEC serves unchanged files, the chain
does not create duplicate observations or evidence; the daily summary reports
`zero_observations_reason = "unchanged_sources_no_new_observations"`.

## Reports

The package includes CLI helpers for validation, conflict, and daily summary
reports:

```bash
bin/stonks-securities-validate --source-run-id <core-run-id> --json
bin/stonks-securities-conflicts --source-run-id <core-run-id> --json
bin/stonks-securities-daily-summary --source-run-id <core-run-id> --json
```

Each durable report has a common envelope:

```text
report_name
generated_at
status
healthy
run_context
summary
warnings
failures
```

Report-specific sections carry the detailed payload, such as source coverage,
listing quality, conflict categories, pipeline stage health, and linked report
summaries.

### Interpreting Reports

Report status is intentionally operational:

- `PASS` means the report completed with no warnings or failures.
- `WARN` means the report completed with usable output and no failures, but an
  operator should review the warning list.
- `FAIL` means the report found a failure that makes the output untrustworthy
  for handoff or downstream use.

`healthy` is `true` for `PASS` and `WARN`, and `false` for `FAIL`.

Healthy zero-change SEC days are expected. When SEC serves the same source files
again, the scrape and verify stages can still succeed while observations,
evidence, issuers, securities, and listings create no new rows. In that case the
daily summary should explain the zero delta with
`zero_observations_reason = "unchanged_sources_no_new_observations"`.

Expected warnings on an otherwise healthy current daily run:

- `ticker_exchange_observations_missing_exchange`: SEC source rows with no raw
  exchange value. These are visible for review but are not guessed into a
  listing.
- `validation_report_warn` in the daily summary when the linked validation
  report is `WARN` only because of expected validation warnings.

Warnings that should be investigated before treating the run as clean:

- `raw_sec_exchange_values_unmapped`: a new SEC exchange value needs an
  explicit `exchange_alias` mapping or a deliberate decision to leave it
  unmapped.
- conflict report warnings or non-zero conflict counts.
- missing source files, checksum failures, report read failures, stage
  starvation, or any report with `failures_total > 0`.

## Status

Implemented:

- Config parsing and publication.
- SEC source-file acquisition and metadata sidecars.
- Source verification.
- Provider source snapshot identity.
- Provider observation loading.
- SEC-backed issuer, provisional security, and listing upserts.
- Provider evidence for issuer/security/listing reconciliation.
- Validation, conflict, verify, and daily summary reports.
- Current-run scoping through the daily chain.
- Active listing and active symbol-history guards.

Current caveat:

SEC-created securities are provisional bootstrap records. The daily path is
usable for the current SEC issuer -> security -> listing backbone, but broad
historical backfill or provider hydration should not promote, merge, split, or
overwrite canonical security identity until explicit reconciliation rules exist.
