# Overview and Getting Started

This document serves as the **entry point** for navigating documentation in the
`empire` repository.

It takes you from a fresh clone of the repository to a working local environment,
including PostgreSQL, Flyway, and Airflow.

No prior context is assumed.

---

## Documentation Principles

- The `docs/` tree is canonical.
- Every directory contains a `README.md`.
- If a directory contains a single document, it **is** `README.md`.

---

## Local Prerequisites

You will need:

- macOS
- Docker Desktop (or equivalent)
- GNU Make
- Python 3
- Poetry
- rsync

Install `rsync`:

```bash
brew install rsync
```

---

## Repository Layout

At a high level, Empire is organized as:

```text
apps/       Runnable applications and services
packages/   Shared reusable libraries
db/         Database migrations and schema assets
deploy/     Docker Compose and environment configuration
dags/       Airflow DAGs
bin/        Operational scripts and workflows
tools/      Makefile fragments and developer tooling
docs/       Documentation
resources/  Static assets, prompts, samples, schemas
```

---

## Local Environment Configuration

Local configuration is **not committed to git**.

Create:

```text
deploy/env/local.env
```

from the example:

```bash
cp deploy/env/local.example.env deploy/env/local.env
```

Review and update values as needed.

### Important Variables

#### PostgreSQL / Docker

Consumed by Docker Compose, Flyway, and Airflow:

```text
POSTGRES_DB
POSTGRES_USER
POSTGRES_PASSWORD
POSTGRES_HOST_PORT

EMPIRE_POSTGRES_CONTAINER
EMPIRE_POSTGRES_DATA_DIR
```

#### PgBouncer

Consumed by PgBouncer:

```text
PGBOUNCER_VERSION
PGBOUNCER_HOST_PORT
PGBOUNCER_POOL_MODE
PGBOUNCER_MAX_CLIENT_CONN
PGBOUNCER_DEFAULT_POOL_SIZE
```

#### Flyway

Consumed by Flyway:

```text
FLYWAY_VERSION
FLYWAY_DEFAULT_SCHEMA
FLYWAY_SCHEMAS
FLYWAY_LOCATIONS
```

#### Airflow

Consumed by Airflow:

```text
AIRFLOW_FERNET_KEY
AIRFLOW_API_AUTH_JWT_SECRET
AIRFLOW_API_SECRET_KEY

AIRFLOW_UID
AIRFLOW_GID

AIRFLOW_DAG_REFRESH_INTERVAL
AIRFLOW_DAG_MIN_FILE_PROCESS_INTERVAL
```

#### Empire Core

Consumed by `packages/empire-core` and operational scripts:

```text
EMPIRE_DB_HOST
EMPIRE_DB_PORT
EMPIRE_DB_NAME
EMPIRE_DB_USER
EMPIRE_DB_PASSWORD

EMPIRE_OBJECT_STORE_TOMBSTONE_DAYS
EMPIRE_STORAGE_ROOT_GLOBAL
EMPIRE_STORAGE_ROOT_JELLYFIN
```

Storage root variables are environment-specific filesystem paths. They are
upserted into `core.storage_root` after Flyway migrations run.

> Secrets **must not** be committed to git.

---

## Generate Required Secrets

Before starting Airflow, generate required secrets.

### Generate Fernet Key

Used for Airflow credential encryption.

```bash
docker run --rm apache/airflow:3.2.1 \
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Generate JWT/API Secrets

Generate two separate secrets:

```bash
openssl rand -hex 32
openssl rand -hex 32
```

Update:

```text
deploy/env/local.env
```

with:

```env
AIRFLOW_FERNET_KEY=<generated_fernet_key>
AIRFLOW_API_AUTH_JWT_SECRET=<openssl_output>
AIRFLOW_API_SECRET_KEY=<openssl_output>
```

---

## First-Time Local Setup

For a fresh clone, initialize the environment in this order.

### 1. Start Database Services

Start PostgreSQL and PgBouncer:

```bash
make db-up
```

Verify:

```bash
make db-ps
```

Optional logs:

```bash
make db-logs
```

Optional `psql` connection:

```bash
make db-psql
```

---

### 2. Apply Database Migrations

Flyway migrations create:

- Schemas
- Tables
- Constraints
- Indexes
- Seed/reference data

Run migrations:

```bash
make db-migrate
```

Check migration status:

```bash
make db-info
```

Validate migration integrity:

```bash
make db-validate
```

If Flyway reports checksum mismatches during local development:

```bash
make db-clean
make db-migrate
```

> **Warning**
>
> `db-clean` removes objects managed by Flyway schemas.
> Use carefully.

---

### 3. Initialize Empire Core Storage Roots

Empire object storage roots are environment-specific and are not hardcoded in
Flyway migrations. Configure them in:

```text
deploy/env/local.env
```

For local development, the initial roots are:

```env
EMPIRE_STORAGE_ROOT_GLOBAL=/Users/chris/Documents/project/empire/empire-object-store/global
EMPIRE_STORAGE_ROOT_JELLYFIN=/Users/chris/Documents/project/empire/empire-object-store/jellyfin
```

Initialize or update `core.storage_root` from the environment:

```bash
bin/init-storage-roots
```

For a first local setup, create the directories too:

```bash
bin/init-storage-roots --create-dirs
```

On a server with mounted storage, make sure mounts exist first and run without
`--create-dirs` to avoid accidentally creating plain local directories where a
mount was expected.

Preview without touching the filesystem or database:

```bash
bin/init-storage-roots --dry-run
```

The script maps variable suffixes to stable root names:

```text
EMPIRE_STORAGE_ROOT_GLOBAL   -> global
EMPIRE_STORAGE_ROOT_JELLYFIN -> jellyfin
```

Use `global` for general shared objects such as weather data and `jellyfin` for
larger media/video objects.

---

### Run Object Cleanup

Clean active stored objects for a specific run with:

```bash
bin/run-objects-cleanup <run_id> --dry-run
bin/run-objects-cleanup <run_id>
```

For example:

```bash
bin/run-objects-cleanup 79f89602-0e85-4765-84b7-82c6284b4fb6 --dry-run
bin/run-objects-cleanup 79f89602-0e85-4765-84b7-82c6284b4fb6
```

The cleanup script deletes physical files and marks matching
`core.stored_object` rows deleted. It leaves the `core.core_run` row in place as
lineage/history.

After cleanup, purge deleted object metadata for a run with:

```bash
bin/run-objects-purge <run_id> --dry-run
bin/run-objects-purge <run_id>
```

By default, purge respects `purge_after`. To purge deleted rows immediately for
that run:

```bash
bin/run-objects-purge <run_id> --ignore-purge-after
```

For local/dev cleanup where the run should be completely removed, use:

```bash
bin/run-nuke <run_id> --dry-run
bin/run-nuke <run_id> --yes
```

`run-nuke` deletes active physical files, purges all deleted object metadata for
the run immediately, and then deletes the `core.core_run` row. Use it only when
you intentionally want the run gone from lineage/history.

---

### 4. Build the Airflow Image

This installs Python dependencies from:

```text
deploy/docker/airflow/airflow-requirements.txt
```

Build:

```bash
make airflow-build
```

---

### 5. Initialize Airflow Metadata

Initialize or upgrade Airflow metadata and create required connections:

```bash
make airflow-init
```

---

### 6. Start the Airflow Stack

Start Redis + Airflow services:

```bash
make airflow-up
```

Verify:

```bash
make airflow-ps
```

Access the UI:

```text
http://localhost:8080
```

Verify DAG visibility:

```bash
make airflow-dags
```

If successful, you now have:

- PostgreSQL running
- PgBouncer running
- Flyway initialized
- Airflow initialized
- Celery executor working
- Redis running
- DAG processing enabled

You are ready to begin development.

---

## Daily Development Workflow

After the initial setup succeeds, you normally do **not** need to repeat the initialization sequence.

Start the full environment:

```bash
make empire-up
```

Check status:

```bash
make empire-ps
```

Tail logs:

```bash
make empire-logs
```

Stop everything:

```bash
make empire-down
```

---

## Airflow Development Notes

### DAG Updates

Changes under:

```text
dags/
```

are automatically detected by Airflow.

No rebuild is required.

---

### Adding Python Libraries

If you add dependencies to:

```text
deploy/docker/airflow/airflow-requirements.txt
```

Rebuild and recreate Airflow:

```bash
make airflow-build
make airflow-recreate
```

---

### Inspect Installed Packages

List installed Python packages:

```bash
make airflow-pip-list
```

Freeze exact versions:

```bash
make airflow-pip-freeze
```

Show details for a package:

```bash
make airflow-pip-show PKG=<package>
```

Example:

```bash
make airflow-pip-show PKG=yfinance
```

---

## Flyway Migration Conventions

Empire uses **versioned migrations only**.

Repeatable migrations (`R__*.sql`) are intentionally avoided.

### Naming Convention

```text
VYYYY.MM.DD.NNNN__module_description.sql
```

Examples:

```text
V2026.05.19.0001__core_create_schema.sql
V2026.05.19.0002__core_create_extensions.sql
V2026.05.19.0003__stonks_create_schema.sql
V2026.05.20.0001__stonks_create_security_master.sql
V2026.05.20.0002__brain_create_document_tables.sql
```

### Guidelines

- Versions are globally ordered.
- Migrations are immutable once committed.
- Module ownership appears in the filename.
- Schema creation is explicit inside migrations.
- Leading zeros are required.

Example:

```sql
CREATE SCHEMA IF NOT EXISTS core;
```
