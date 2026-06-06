#!/usr/bin/env python3
"""Convert PostgreSQL schema metadata TSV into Mermaid database diagrams."""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import DefaultDict


@dataclass(frozen=True)
class Column:
    name: str
    dtype: str
    nullable: bool
    ordinal: int


def mermaid_type(pg_type: str) -> str:
    mapping = {
        "bigint": "BIGINT",
        "integer": "INT",
        "smallint": "SMALLINT",
        "numeric": "NUMERIC",
        "double precision": "DOUBLE",
        "real": "REAL",
        "boolean": "BOOL",
        "text": "TEXT",
        "character varying": "VARCHAR",
        "character": "CHAR",
        "timestamp without time zone": "TIMESTAMP",
        "timestamp with time zone": "TIMESTAMPTZ",
        "date": "DATE",
        "uuid": "UUID",
        "json": "JSON",
        "jsonb": "JSONB",
    }
    return mapping.get(pg_type.lower(), pg_type.upper().replace(" ", "_"))


def load_table_filter(path: Path | None) -> set[str] | None:
    if path is None:
        return None

    tables: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        tables.add(line)

    if not tables:
        raise SystemExit(f"ERROR: no tables found in table filter: {path}")

    return tables


def generate(
    meta_path: Path,
    out_path: Path,
    selected_tables: set[str] | None,
    compact: bool,
) -> None:
    tables: set[str] = set()
    columns: DefaultDict[str, list[Column]] = defaultdict(list)
    pk_cols: DefaultDict[str, set[str]] = defaultdict(set)
    fk_cols: DefaultDict[str, set[str]] = defaultdict(set)
    unique_columns: DefaultDict[str, dict[str, list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )
    fk_map: DefaultDict[tuple[str, str], list[tuple[str, str, str]]] = defaultdict(list)

    with meta_path.open("r", encoding="utf-8") as meta_file:
        for raw in meta_file:
            line = raw.rstrip("\n")
            if not line:
                continue

            parts = line.split("\t")
            rec = parts[0]

            if rec == "T":
                table = parts[2]
                if selected_tables is None or table in selected_tables:
                    tables.add(table)

            elif rec == "C":
                table = parts[2]
                if selected_tables is not None and table not in selected_tables:
                    continue
                columns[table].append(
                    Column(
                        name=parts[3],
                        dtype=parts[4],
                        nullable=parts[5].upper() == "YES",
                        ordinal=int(parts[6]),
                    )
                )

            elif rec == "PK":
                table = parts[2]
                if selected_tables is None or table in selected_tables:
                    pk_cols[table].add(parts[3])

            elif rec == "UQ":
                table = parts[2]
                if selected_tables is None or table in selected_tables:
                    unique_columns[table][parts[3]].append(parts[4])

            elif rec == "FK":
                table = parts[2]
                ref_table = parts[6]
                if selected_tables is not None and (
                    table not in selected_tables or ref_table not in selected_tables
                ):
                    continue
                fk_cols[table].add(parts[4])
                fk_map[(table, parts[3])].append((parts[4], ref_table, parts[7]))

    if selected_tables is not None:
        missing_tables = selected_tables - tables
        if missing_tables:
            missing = ", ".join(sorted(missing_tables))
            raise SystemExit(f"ERROR: table filter includes unknown tables: {missing}")

    for table_columns in columns.values():
        table_columns.sort(key=lambda column: column.ordinal)

    unique_sets: DefaultDict[str, list[set[str]]] = defaultdict(list)
    for table, constraints in unique_columns.items():
        for constraint_columns in constraints.values():
            unique_sets[table].append(set(constraint_columns))

    def fk_is_unique(child_table: str, fk_column_list: list[str]) -> bool:
        fk_set = set(fk_column_list)
        return any(fk_set == unique_set for unique_set in unique_sets.get(child_table, []))

    if compact:
        lines = ["flowchart LR"]

        for table in sorted(tables):
            lines.append(f'  {table}["{table}"]')

        if tables and fk_map:
            lines.append("")

        for (child, constraint), pairs in sorted(fk_map.items()):
            if not pairs:
                continue
            parent = pairs[0][1]
            lines.append(f"  {parent} -->|{constraint}| {child}")

        lines.append("")
        out_path.write_text("\n".join(lines), encoding="utf-8")
        return

    lines = ["erDiagram"]

    for table in sorted(tables):
        lines.append(f"  {table} {{")
        for column in columns.get(table, []):
            is_pk = column.name in pk_cols.get(table, set())
            is_fk = column.name in fk_cols.get(table, set())
            tag = " PK" if is_pk else (" FK" if is_fk else "")
            lines.append(f"    {mermaid_type(column.dtype)} {column.name}{tag}")
        lines.append("  }")
        lines.append("")

    for (child, constraint), pairs in sorted(fk_map.items()):
        if not pairs:
            continue
        parent = pairs[0][1]
        child_cols = [pair[0] for pair in pairs]
        cardinality = "||--||" if fk_is_unique(child, child_cols) else "||--o{"
        lines.append(f'  {parent} {cardinality} {child} : "{constraint}"')

    lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("meta_path", type=Path)
    parser.add_argument("out_path", type=Path)
    parser.add_argument("--tables-file", type=Path)
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Generate table-name-only relationship flowchart instead of field ERD.",
    )
    args = parser.parse_args()

    selected_tables = load_table_filter(args.tables_file)
    generate(args.meta_path, args.out_path, selected_tables, args.compact)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
