# Data remediations

This directory contains opt-in, version-controlled SQL corrections for
historical domain data in an existing environment. They are intentionally
separate from `db/flyway/sql`: a fresh database must not apply them
automatically.

Each remediation must:

- live beneath its domain directory and use an ISO-date-prefixed filename;
- run in a single transaction and be safe to rerun;
- assert the records it expects before changing them;
- document the evidence, scope, and verification queries; and
- record durable audit information using the domain's existing audit model
  where one is available.

Run a remediation explicitly from the repository root:

```bash
bin/run-data-remediation \
  --file db/data-remediations/stonks/2026-07-11-exxon-xom-successor.sql \
  --apply
```

The command loads `deploy/env/local.env` by default, then runs `psql` inside
the configured Postgres container. Pass `--env-file` for a different
environment. It prints the target container, database, and script checksum
before it makes a connection.

`make db-data-remediation REMEDIATION=...` is an equivalent convenience
command. Do not add this directory to Flyway's migration locations.
