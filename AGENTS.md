# Empire Monorepo Instructions

## Project Overview

Empire is a local-first research, automation, and AI platform.

Empire is intentionally designed as a reusable platform rather than a collection of tightly coupled scripts or framework-specific implementations.

The platform foundation includes:

- PostgreSQL
- PgBouncer
- Flyway
- Airflow
- Redis
- Docker Compose
- Poetry
- Makefile-driven workflows

Empire is Python-first.

---

## Architecture Philosophy

When making implementation decisions, prioritize:

1. Reusable packages over framework-specific code
2. Explicit/simple designs over clever abstractions
3. Platform ownership over framework ownership
4. Real implementation over throwaway/prototype code
5. Minimal dependencies unless clearly justified

Avoid overengineering early.

Build the smallest clean version that can grow naturally.

Prefer maintainable and understandable code.

---

## Ownership Boundaries

Empire owns business logic and reusable capabilities.

Frameworks consume Empire.

### Good

Airflow DAG calls reusable package logic:

```python
from empire_mail import send_report_email

send_report_email(...)
```

### Bad

Business logic embedded directly inside DAG files:

```python
def airflow_task():
    smtp = smtplib.SMTP(...)
```

Airflow should orchestrate only.

Reusable logic belongs under `packages/`.

---

## Monorepo Structure

Expected repository layout:

```text
apps/       runnable applications/services
packages/   reusable shared libraries
db/         flyway migrations and schema
deploy/     docker/compose/env
dags/       airflow orchestration only
bin/        operational scripts
tools/      build tooling
resources/  prompts/assets/etc
```

Guidelines:

- `apps/` = runnable systems
- `packages/` = reusable libraries
- `dags/` = orchestration only
- `db/` = database ownership
- `deploy/` = runtime configuration

If code may be reused, it belongs in `packages/`.

---

## Environment Configuration

Empire uses shared environment files under `deploy/env/`. For local development,
the active file is:

```text
deploy/env/local.env
```

### Rules

Reusable packages MUST:

- Read configuration from `os.environ`
- Be environment-driven
- Remain runtime agnostic

Reusable packages MUST NOT:

- Load `.env` files internally
- Use `python-dotenv`
- Assume paths to files under `deploy/env/`
- Depend on repo filesystem structure
- Own environment loading

Environment loading belongs to the runtime:

- Docker Compose
- Shell scripts
- CLI execution
- Airflow containers
- APIs

### Good

```python
import os

db_host = os.environ["EMPIRE_DB_HOST"]
```

### Bad

```python
from dotenv import load_dotenv

load_dotenv()
load_dotenv("deploy/env/local.env")
```

---

## Python Standards

Empire is Python-first.

### Package Standards

- Use Poetry
- Prefer `src/` layout
- Prefer explicit typing
- Prefer dataclasses for simple models/config
- Keep dependencies minimal
- Use stdlib when practical

### Dependency Philosophy

Ask:

> Does this dependency meaningfully reduce complexity?

If not, prefer stdlib.

Avoid unnecessary frameworks.

---

## Code Style Preferences

Prefer:

- Explicit code
- Small focused modules
- Readability over cleverness
- Clear names
- Simple interfaces

Avoid:

- Deep abstraction layers
- Premature plugin systems
- Overly generic factories
- Heavy dependency injection
- Magic behavior

Simple > clever.

---

## Configuration Philosophy

Empire capabilities should be configured via environment variables.

Example naming:

```text
EMPIRE_DB_HOST
EMPIRE_DB_PORT

EMPIRE_MAIL_SMTP_HOST
EMPIRE_MAIL_USERNAME

EMPIRE_AI_MODEL
```

Configuration should be:

- Explicit
- Environment-driven
- Consistent
- Shared across Empire

---

## Airflow Standards

Airflow is orchestration only.

DAGs should:

- Call reusable package logic
- Remain thin
- Avoid embedding business logic

### Good

```python
from empire_mail import send_report_email

@task
def send():
    send_report_email(...)
```

### Bad

```python
@task
def send():
    smtp = smtplib.SMTP(...)
```

Empire owns capabilities.

Airflow consumes them.

---

## Before Completing Work

Before finishing any implementation:

1. Run formatting if configured
2. Run linting if configured
3. Run tests for changed code
4. Verify imports work
5. Summarize changes made
6. Explain non-obvious design decisions

Do not stop after generating code without validation.

---

## Versioning

Reusable packages should use semantic versioning.

During early development:

```text
0.x.y
```

Example:

```text
0.1.0
```

until APIs stabilize.

---

## General Decision Rule

When uncertain, ask:

> What is the simplest reusable solution that fits Empire architecture without overengineering?
