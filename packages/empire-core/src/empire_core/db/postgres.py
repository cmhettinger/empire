"""Small Postgres repository helpers."""

from __future__ import annotations

import json
from typing import Any


def json_dumps(value: dict[str, Any]) -> str:
    return json.dumps(value)


def row_to_dict(cursor: Any, row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return row
    columns = [
        column.name if hasattr(column, "name") else column[0]
        for column in cursor.description
    ]
    return dict(zip(columns, row))
