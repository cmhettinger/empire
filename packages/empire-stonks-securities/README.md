# empire-stonks-securities

Reusable securities reference-data utilities for Empire stonks.

This package owns the package-level config model and object-store integration for
SEC-backed securities reference data. Airflow and other runtimes should call into
this package rather than embedding provider or object-store logic directly.

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

Download all current fixed sources by naming them explicitly:

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

Use `--acquisition-id` to provide a DAG/run identifier, and `--force` to
replace a cached file. Re-running the same command skips a source when both the
final file and `<filename>.metadata.json` sidecar already exist.

Each sidecar includes `source_code`, `source_url`, `downloaded_at`,
`file_path`, `size_bytes`, `sha256`, `http_status`, `etag`, and
`last_modified`. Large downloads are streamed to `EMPIRE_TEMP_DIR` and then
moved into the object store through `ObjectStore.put_file()`.

This acquisition layer only downloads and caches SEC source files. It does not
parse SEC files or write normalized stonks tables.

## Airflow

`empire-stonks-securities` is installed into the Airflow image by
`deploy/docker/airflow/Dockerfile`. The Airflow Compose stack passes
`EMPIRE_STORAGE_KEY_STONKS_SECURITIES` through to all Airflow services alongside
the other Empire storage keys.

The manual acquisition DAG is:

```text
dags/stonks/stonks_securities_daily_scrape.py
```

It is manual-only (`schedule=None`) and currently downloads:

```text
sec_company_tickers_exchange
sec_company_tickers
```

The DAG loads the published `stonks-securities-config` object, starts a core run,
uses that run id as the acquisition folder, and writes each SEC file plus its
metadata sidecar to the global object store.

The scrape DAG triggers `stonks_securities_daily_verify` with the acquisition
`run_id`. The verify DAG parses the two downloaded daily SEC JSON files and logs
good-record and parse-error counts with source object details for investigation.

## Status

Config parsing, config publication, and SEC source-file acquisition are in
place. Normalization and database loading should be added in later phases once
the securities ingestion contract is finalized.
