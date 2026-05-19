# Overview and Getting Started

This document serves as the **entry point** for navigating all documentation in the
`empire` repository.

It takes you from a fresh clone of the repository to a working local database and your first successful migrations.

No prior context is assumed.

---

## Documentation Principles

- The `docs/` tree is canonical.
- Every directory contains a `README.md`.
- If a directory has one document, it **is** `README.md`.

---

## Local Prerequisites

You will need:

- macOS
- Docker Desktop (or equivalent)
- GNU Make
- Python 3
- Poetry
- rsync

Install rsync:

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

by starting from the example:

```bash
cp deploy/env/local.example.env deploy/env/local.env
```

Review and update any values as needed.

### Important Variables

#### PostgreSQL / Docker

These are consumed by Docker Compose and Flyway:

```text
POSTGRES_DB
POSTGRES_USER
POSTGRES_PASSWORD
POSTGRES_HOST_PORT

EMPIRE_POSTGRES_CONTAINER
EMPIRE_POSTGRES_DATA_DIR
```

#### PgBouncer

These are consumed by PgBouncer:

```text
PGBOUNCER_VERSION
PGBOUNCER_HOST_PORT
PGBOUNCER_POOL_MODE
PGBOUNCER_MAX_CLIENT_CONN
PGBOUNCER_DEFAULT_POOL_SIZE
```

#### Flyway

These are consumed by Flyway:

```text
FLYWAY_VERSION
FLYWAY_DEFAULT_SCHEMA
FLYWAY_SCHEMAS
FLYWAY_LOCATIONS
```

---

## Start the Local Database

From the repository root:

```bash
make db-up
```

Verify:

```bash
make db-ps
```

View logs:

```bash
make db-logs
```

Connect with `psql`:

```bash
make db-psql
```

Stop the database:

```bash
make db-down
```

---

## Apply Database Migrations

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

CREATE TABLE core.example (
    example_id BIGSERIAL PRIMARY KEY,
    created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## First-Time Local Setup

For a fresh clone:

```bash
cp deploy/env/local.example.env deploy/env/local.env
```

Edit configuration as needed.

Then:

```bash
make db-up
make db-migrate
make db-info
```

If successful, you now have:

- PostgreSQL running
- PgBouncer running
- Empire schemas created
- Flyway initialized

You are ready to begin development.