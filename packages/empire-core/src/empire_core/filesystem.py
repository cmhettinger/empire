"""Small, bounded filesystem cleanup helpers."""

from __future__ import annotations

from pathlib import Path

from empire_core.exceptions import ValidationError


def remove_file_and_prune_empty_parents(
    file_path: str | Path,
    *,
    stop_at: str | Path,
) -> None:
    """Remove a file and its empty parents without removing the boundary."""

    path = Path(file_path).expanduser().resolve()
    boundary = Path(stop_at).expanduser().resolve()
    if boundary not in path.parents:
        raise ValidationError(f"file_path must be beneath stop_at: {file_path}")

    path.unlink(missing_ok=True)
    current = path.parent
    while current != boundary:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent
