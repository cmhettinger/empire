#!/usr/bin/env python3
"""Prepare pg_dump schema SQL for pg_diagram, optionally filtering tables."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


def load_tables(path: Path | None) -> set[str] | None:
    if path is None:
        return None

    tables: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        tables.add(line)

    if not tables:
        raise SystemExit(f"ERROR: no tables found in group file: {path}")

    return tables


def sanitize_sql(sql: str) -> str:
    sql = re.sub(r"(?m)^--.*$", "", sql)
    sql = re.sub(r"(?m)^\s*\\.*$", "", sql)
    sql = re.sub(
        r"(?ims)^\s*CREATE(?:\s+CONSTRAINT)?\s+TRIGGER\b.*?;\s*$",
        "",
        sql,
    )
    sql = re.sub(
        r"(?ims)^\s*CREATE\s+EVENT\s+TRIGGER\b.*?;\s*$",
        "",
        sql,
    )
    sql = re.sub(r"\n{3,}", "\n\n", sql)
    return sql.strip() + "\n"


def split_statements(sql: str) -> list[str]:
    statements: list[str] = []
    buffer: list[str] = []

    for line in sql.splitlines():
        buffer.append(line)
        if line.rstrip().endswith(";"):
            statement = "\n".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer = []

    tail = "\n".join(buffer).strip()
    if tail:
        statements.append(tail)

    return statements


def extract_create_table_name(statement: str, schema: str) -> str | None:
    patterns = [
        rf"\bCREATE\s+(?:UNLOGGED\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?{re.escape(schema)}\.([A-Za-z_][A-Za-z0-9_]*)\b",
        rf'\bCREATE\s+(?:UNLOGGED\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"{re.escape(schema)}"\."([^"]+)"\b',
        rf'\bCREATE\s+(?:UNLOGGED\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"{re.escape(schema)}"\.([A-Za-z_][A-Za-z0-9_]*)\b',
        rf'\bCREATE\s+(?:UNLOGGED\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?{re.escape(schema)}\."([^"]+)"\b',
    ]
    for pattern in patterns:
        match = re.search(pattern, statement, re.I | re.S)
        if match:
            return match.group(1)
    return None


def extract_alter_table_name(statement: str, schema: str) -> str | None:
    patterns = [
        rf"\bALTER\s+TABLE\s+(?:ONLY\s+)?{re.escape(schema)}\.([A-Za-z_][A-Za-z0-9_]*)\b",
        rf'\bALTER\s+TABLE\s+(?:ONLY\s+)?"{re.escape(schema)}"\."([^"]+)"\b',
        rf'\bALTER\s+TABLE\s+(?:ONLY\s+)?"{re.escape(schema)}"\.([A-Za-z_][A-Za-z0-9_]*)\b',
        rf'\bALTER\s+TABLE\s+(?:ONLY\s+)?{re.escape(schema)}\."([^"]+)"\b',
    ]
    for pattern in patterns:
        match = re.search(pattern, statement, re.I | re.S)
        if match:
            return match.group(1)
    return None


def extract_fk_reference(statement: str, schema: str) -> str | None:
    patterns = [
        rf"\bREFERENCES\s+{re.escape(schema)}\.([A-Za-z_][A-Za-z0-9_]*)\b",
        rf'\bREFERENCES\s+"{re.escape(schema)}"\."([^"]+)"\b',
        rf'\bREFERENCES\s+"{re.escape(schema)}"\.([A-Za-z_][A-Za-z0-9_]*)\b',
        rf'\bREFERENCES\s+{re.escape(schema)}\."([^"]+)"\b',
    ]
    for pattern in patterns:
        match = re.search(pattern, statement, re.I | re.S)
        if match:
            return match.group(1)
    return None


def should_keep(statement: str, selected_tables: set[str], schema: str) -> bool:
    normalized = statement.strip()
    upper = normalized.upper()

    if not normalized:
        return False
    if upper.startswith("SET "):
        return False
    if upper.startswith("SELECT PG_CATALOG.SET_CONFIG"):
        return False
    if upper.startswith("CREATE SCHEMA "):
        return False
    if upper.startswith("COMMENT ON EXTENSION "):
        return False
    if upper.startswith("CREATE EXTENSION "):
        return False
    if upper.startswith("CREATE FUNCTION "):
        return False
    if upper.startswith("CREATE OR REPLACE FUNCTION "):
        return False
    if upper.startswith("CREATE SEQUENCE "):
        return False
    if upper.startswith("ALTER SEQUENCE "):
        return False
    if upper.startswith("COMMENT ON "):
        return False
    if upper.startswith("ALTER TABLE ") and " ADD GENERATED " in upper:
        return False

    table_name = extract_create_table_name(normalized, schema)
    if table_name is not None:
        return table_name in selected_tables

    alter_table_name = extract_alter_table_name(normalized, schema)
    if alter_table_name is not None:
        if alter_table_name not in selected_tables:
            return False

        referenced_table = extract_fk_reference(normalized, schema)
        if referenced_table is not None:
            return referenced_table in selected_tables

        return True

    return False


def should_keep_full(statement: str) -> bool:
    normalized = statement.strip()
    upper = normalized.upper()

    if not normalized:
        return False
    if upper.startswith("SET "):
        return False
    if upper.startswith("SELECT PG_CATALOG.SET_CONFIG"):
        return False
    if upper.startswith("CREATE SCHEMA "):
        return False
    if upper.startswith("COMMENT ON EXTENSION "):
        return False
    if upper.startswith("CREATE EXTENSION "):
        return False
    if upper.startswith("CREATE FUNCTION "):
        return False
    if upper.startswith("CREATE OR REPLACE FUNCTION "):
        return False
    if upper.startswith("CREATE SEQUENCE "):
        return False
    if upper.startswith("ALTER SEQUENCE "):
        return False
    if upper.startswith("COMMENT ON "):
        return False
    if upper.startswith("ALTER TABLE ") and " ADD GENERATED " in upper:
        return False

    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("raw_sql", type=Path)
    parser.add_argument("out_sql", type=Path)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--tables-file", type=Path)
    args = parser.parse_args()

    selected_tables = load_tables(args.tables_file)
    clean_sql = sanitize_sql(args.raw_sql.read_text(encoding="utf-8"))
    statements = split_statements(clean_sql)

    if selected_tables is None:
        kept = [statement.rstrip() for statement in statements if should_keep_full(statement)]
        args.out_sql.write_text("\n\n".join(kept) + "\n", encoding="utf-8")
        return 0

    kept = [
        statement.rstrip()
        for statement in statements
        if should_keep(statement, selected_tables, args.schema)
    ]

    if not kept:
        raise SystemExit(
            "ERROR: filtering produced zero SQL statements. "
            "Check schema and group table names."
        )

    args.out_sql.write_text("\n\n".join(kept) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
