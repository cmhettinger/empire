#!/usr/bin/env python3
"""Generate compact Graphviz DOT relation diagrams from ERD metadata TSV."""

from __future__ import annotations

import argparse
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


def quote_dot(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("meta_path", type=Path)
    parser.add_argument("out_path", type=Path)
    parser.add_argument("--tables-file", type=Path)
    args = parser.parse_args()

    selected_tables = load_tables(args.tables_file)
    tables: set[str] = set()
    edges: set[tuple[str, str, str]] = set()

    with args.meta_path.open("r", encoding="utf-8") as meta_file:
        for raw_line in meta_file:
            line = raw_line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            record_type = parts[0]

            if record_type == "T":
                table = parts[2]
                if selected_tables is None or table in selected_tables:
                    tables.add(table)

            elif record_type == "FK":
                child = parts[2]
                constraint = parts[3]
                parent = parts[6]
                if selected_tables is not None and (
                    child not in selected_tables or parent not in selected_tables
                ):
                    continue
                edges.add((parent, child, constraint))

    if selected_tables is not None:
        missing_tables = selected_tables - tables
        if missing_tables:
            missing = ", ".join(sorted(missing_tables))
            raise SystemExit(f"ERROR: group includes unknown tables: {missing}")

    lines = [
        "digraph schema_relations {",
        "  graph [rankdir=LR, bgcolor=\"transparent\", pad=\"0.25\", nodesep=\"0.6\", ranksep=\"0.9\"];",
        "  node [shape=box, style=\"rounded,filled\", fillcolor=\"#f8fafc\", color=\"#334155\", fontname=\"Helvetica\", fontsize=11, margin=\"0.10,0.06\"];",
        "  edge [color=\"#64748b\", fontname=\"Helvetica\", fontsize=8, arrowsize=0.7];",
        "",
    ]

    for table in sorted(tables):
        lines.append(f"  {quote_dot(table)};")

    if tables and edges:
        lines.append("")

    for parent, child, constraint in sorted(edges):
        lines.append(
            f"  {quote_dot(parent)} -> {quote_dot(child)} [label={quote_dot(constraint)}];"
        )

    lines.append("}")
    args.out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
