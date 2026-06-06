# Database Documentation Tools

Empire database documentation is generated from the live local Postgres
container through Make targets in `tools/make/docs.mk`.

Generated files are written under each schema's `generated/` directory:

```text
docs/db/core/generated/
docs/db/stonks/generated/
```

Those directories are tool-owned. Each contains a generated `README.md` marker
with a UTC timestamp from the most recent run. Do not hand-edit files under
`generated/`; update migrations, group files, or the generator code instead.

Human-authored database docs should live outside `generated/`, for example:

```text
docs/db/core/README.md
docs/db/stonks/security-master.md
docs/db/tools-docs.md
```

Temporary inputs, raw dumps, filtered SQL, DOT files, SchemaSpy HTML, and caches
are written under `tmp/docs/db/`. The `tmp/` tree is not canonical and can be
cleaned periodically.

## Main Targets

Generate all database documentation:

```bash
make docs-db
```

This runs the canonical docs, pg-diagram image generation, grouped pg-diagrams,
and SchemaSpy HTML generation.

Generate only the canonical checked-in docs:

```bash
make docs-db-canon
```

This writes DDL and Mermaid Markdown files under `docs/db/<schema>/generated/`.
It does not run SchemaSpy.

List configured schemas and ERD groups:

```bash
make docs-db-list
```

Show resolved output paths for a schema:

```bash
make docs-db-print-vars SCHEMA=stonks
```

## Schema DDL

Generate DDL for one schema:

```bash
make docs-db-schema SCHEMA=stonks
```

Generate DDL for all configured schemas:

```bash
make docs-db-schema-all
```

Canonical DDL output:

```text
docs/db/<schema>/generated/schema.sql
```

Scratch files:

```text
tmp/docs/db/<schema>/ddl/schema.raw.sql
tmp/docs/db/<schema>/ddl/schema.tables.sql
```

## Mermaid ERDs

Generate Mermaid diagrams for one schema:

```bash
make docs-db-erd SCHEMA=stonks
```

Generate Mermaid diagrams for all configured schemas:

```bash
make docs-db-erd-all
```

Each schema gets two Mermaid Markdown files:

```text
docs/db/<schema>/generated/erd.md
docs/db/<schema>/generated/erd-relations.md
```

`erd.md` is the field-rich ER diagram. `erd-relations.md` is a compact
table-and-relationship diagram.

## ERD Groups

Large schemas can define focused diagram groups. Group inputs live under:

```text
tools/docs/db/schemas/<schema>/groups/
```

Each group file is a plain text list of table names, one table per line.
Blank lines and `#` comments are ignored.

Example:

```text
tools/docs/db/schemas/stonks/groups/security-master-core.txt
```

Generate one Mermaid group:

```bash
make docs-db-erd-group SCHEMA=stonks GROUP=security-master-core
```

Generate all Mermaid groups for a schema:

```bash
make docs-db-erd-groups SCHEMA=stonks
```

Group output:

```text
docs/db/<schema>/generated/erd-groups/<group>.md
docs/db/<schema>/generated/erd-groups/<group>-relations.md
```

Schemas without group files do not get empty group output directories.

Current `stonks` groups:

```text
instrument-types
issuer-classifications
issuer-identity
market-reference
provider-evidence
security-events
security-identity
security-master-core
security-master
```

## pg-diagram Images

Generate pg-diagram images for one schema:

```bash
make docs-db-pg-diagram SCHEMA=stonks
```

Generate pg-diagram images for all configured schemas:

```bash
make docs-db-pg-diagram-all
```

Output:

```text
docs/db/<schema>/generated/pg-diagram/erd.svg
docs/db/<schema>/generated/pg-diagram/erd.png
docs/db/<schema>/generated/pg-diagram/erd-relations.svg
docs/db/<schema>/generated/pg-diagram/erd-relations.png
```

`erd.svg` and `erd.png` are field-rich diagrams rendered through `pg_diagram`.
`erd-relations.svg` and `erd-relations.png` are compact relation diagrams
rendered from Graphviz DOT.

Generate pg-diagram images for one group:

```bash
make docs-db-pg-diagram-group SCHEMA=stonks GROUP=security-master-core
```

Generate pg-diagram images for all groups in a schema:

```bash
make docs-db-pg-diagram-groups SCHEMA=stonks
```

Grouped pg-diagram output:

```text
docs/db/<schema>/generated/pg-diagram-groups/<group>/erd.svg
docs/db/<schema>/generated/pg-diagram-groups/<group>/erd.png
docs/db/<schema>/generated/pg-diagram-groups/<group>/erd-relations.svg
docs/db/<schema>/generated/pg-diagram-groups/<group>/erd-relations.png
```

## SchemaSpy

Generate SchemaSpy HTML for one schema:

```bash
make docs-db-schemaspy SCHEMA=stonks
```

Generate SchemaSpy HTML for all configured schemas:

```bash
make docs-db-schemaspy-all
```

SchemaSpy output is intentionally temporary:

```text
tmp/docs/db/<schema>/schemaspy/index.html
```

The JDBC driver cache is stored at:

```text
tmp/docs/db/.cache/
```

SchemaSpy may log PostgreSQL catalog warnings on newer Postgres versions while
still completing successfully and writing `index.html`.

## Adding A Group

To add a focused diagram group:

1. Create a group file under `tools/docs/db/schemas/<schema>/groups/`.
2. Add one table name per line.
3. Run `make docs-db-list` to confirm the group is detected.
4. Run the group generators.

Example:

```bash
make docs-db-list
make docs-db-erd-group SCHEMA=stonks GROUP=my-new-group
make docs-db-pg-diagram-group SCHEMA=stonks GROUP=my-new-group
```

The group name is the filename without `.txt`.
