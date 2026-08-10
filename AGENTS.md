# Empire Monorepo Instructions

## Project Identity

Empire is a local-first research, automation, and AI platform focused on
correctness, reproducibility, and explicit system design.

Empire owns reusable capabilities. Frameworks and runtimes consume them.

The platform is Python-first and uses PostgreSQL, PgBouncer, Flyway, Airflow,
Redis, Docker Compose, Poetry, and Make-driven workflows.

## Design Priorities

When making implementation decisions, prioritize:

1. Correctness and reproducibility
2. Reusable packages over framework-specific code
3. Explicit, simple designs over clever abstractions
4. Clear ownership and modular boundaries
5. Working end-to-end increments over unfinished infrastructure
6. Maintainability over short-term convenience

Choose the simplest implementation that fully meets the current requirements.
Build the smallest clean version that works end to end, then add capabilities in
layers without trading away a working system for speculative complexity.

Avoid deep abstraction layers, premature plugin systems, overly generic
factories, heavy dependency injection, hidden behavior, and magic configuration.

## Repository Ownership

```text
apps/          runnable applications and services
packages/      reusable shared libraries and business capabilities
db/            Flyway migrations, schema assets, seeds, and remediations
deploy/        Docker Compose, images, and runtime configuration
dags/          thin Airflow orchestration
bin/           operational entry points and workflows
tools/         build, documentation, and developer tooling
docs/          canonical repository and domain documentation
resources/     versioned prompts, branding, samples, and static assets
object-store/  local runtime storage; only versioned configuration is committed
output/        local generated output, not canonical source
tmp/           disposable local artifacts, caches, and generator intermediates
```

Place reusable logic in `packages/`. Keep `apps/`, `dags/`, and `bin/` focused on
runtime composition, orchestration, and operator-facing entry points.

Before changing established behavior, read the relevant package `README.md` and
domain documentation under `docs/`. Treat documented contracts as intentional
unless the task explicitly changes them.

## Python and Package Standards

Reusable Python packages should:

- Use Poetry and a `src/` layout.
- Prefer explicit typing and small, focused modules.
- Use dataclasses for simple models and configuration when appropriate.
- Expose simple interfaces without depending on repository paths or a specific
  runtime such as Airflow.
- Keep dependencies focused and declared in the owning package.

Before writing a new implementation or adding a dependency, inspect existing
Empire packages and installed dependencies. Check their documentation, public
APIs, and types rather than assuming a capability is missing.

Prefer established, well-maintained libraries when they reduce total complexity
or improve reliability. Otherwise prefer the standard library. Add a dependency
only when its value clearly outweighs its operational and maintenance cost.

## Configuration and Secrets

The local runtime loads configuration from:

```text
deploy/env/local.env
```

The committed template is `deploy/env/local.example.env`. Never commit secrets or
real environment files.

Reusable packages must:

- Read configuration from `os.environ` or accept it explicitly from callers.
- Remain environment-driven and runtime agnostic.
- Use consistent `EMPIRE_*` names for Empire-owned settings.

Reusable packages must not:

- Load `.env` files or use `python-dotenv`.
- Assume the location of `deploy/env/` or any repository-relative file.
- Own environment loading.

Environment loading belongs to Docker Compose, shell entry points, CLIs,
Airflow, APIs, and other runtimes.

## Database and Data Ownership

PostgreSQL schemas and persisted data are compatibility boundaries. Change them
deliberately and provide forward migration or transition handling.

- Add forward Flyway migrations for schema and versioned seed changes.
- Do not rewrite an already-applied versioned migration to change current
  behavior.
- Keep one-off, opt-in data fixes under `db/data-remediations/`; do not add that
  directory to Flyway migration locations.
- Preserve lineage, auditability, and deterministic behavior in ingestion and
  reconciliation workflows.
- Put reusable database access and domain logic in the owning package, not in a
  DAG or shell script.

Use the Make targets and scripts documented by the repository rather than
constructing ad hoc database commands when an established workflow exists.

## Airflow and Operational Boundaries

Airflow is orchestration only. DAGs should call reusable package APIs, remain
thin, and avoid embedding business logic, provider clients, SQL workflows, or
report construction.

Operational scripts under `bin/` should parse operator input, load runtime
configuration, call package logic, and return clear exit status and diagnostics.
Do not duplicate package behavior in shell or DAG code.

## Documentation and Generated Artifacts

The `docs/` tree is canonical documentation. Update relevant documentation when
behavior, configuration, contracts, or operator workflows change.

Files under `docs/db/*/generated/` are tool-owned. Do not edit them by hand;
change migrations, documentation group definitions, or generator code and then
regenerate them with the documented Make targets.

Do not treat `tmp/`, `output/`, caches, runtime object-store data, or other
generated artifacts as canonical source.

## Compatibility and Incremental Change

Do not preserve obsolete internal paths merely out of habit. Remove dead code
when its removal is within scope, and do not add compatibility layers without an
identified consumer or migration need.

Treat these as compatibility boundaries unless the task explicitly changes
them:

- Database schemas and persisted data
- Public package APIs
- CLI arguments, exit behavior, and machine-readable output
- Report and payload contracts
- Object-store keys, layouts, and retention behavior
- Documented operational workflows

When changing a compatibility boundary, update its consumers, tests,
documentation, and migration or transition path together.

Avoid knowingly disposable stopgaps. If temporary work is explicitly required,
isolate it, document the limitation and removal condition, and do not let it
become an implicit architecture.

## Safety

Never run destructive database, object-store, filesystem, or remediation
operations as routine validation. Commands such as `db-clean`, purge/nuke
scripts, and opt-in data remediations require explicit task scope and careful
target verification.

Preserve unrelated user changes in the worktree. Do not overwrite, reset, or
clean files outside the task.

## Validation and Completion

Before finishing an implementation:

1. Inspect the owning package's `pyproject.toml` and `README.md` for its actual
   commands and contracts.
2. Run the narrowest relevant tests, normally `poetry run pytest` from each
   changed package.
3. Run relevant PostgreSQL integration or Make-based schema tests when database
   behavior changes and the required services are available.
4. Run formatting or linting only where configured; do not claim checks that the
   repository does not define.
5. Verify imports, CLI entry points, generated artifacts, and documentation as
   appropriate to the change.
6. Report what was validated and clearly identify anything not run.
7. Summarize changes and explain non-obvious design decisions.

Do not stop after generating code without validation.

## General Decision Rule

When uncertain, ask:

> What is the simplest reusable solution that fits Empire's architecture,
> preserves its intentional contracts, and works cleanly end to end?
