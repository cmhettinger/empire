"""Retention helpers for short-lived YouTube media artifacts."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from empire_core.exceptions import ValidationError


YOUTUBE_DAYS_TO_KEEP_ENV = "EMPIRE_YOUTUBE_DAYS_TO_KEEP"
DEFAULT_YOUTUBE_DAYS_TO_KEEP = 10


def youtube_expires_at(*, now: datetime | None = None) -> datetime | None:
    """Return the expiration timestamp for short-lived YouTube artifacts."""

    raw_value = os.environ.get(YOUTUBE_DAYS_TO_KEEP_ENV)
    if raw_value is None or not raw_value.strip():
        days_to_keep = DEFAULT_YOUTUBE_DAYS_TO_KEEP
    else:
        try:
            days_to_keep = int(raw_value)
        except ValueError as exc:
            raise ValidationError(
                f"{YOUTUBE_DAYS_TO_KEEP_ENV} must be a positive integer number of days"
            ) from exc
    if days_to_keep <= 0:
        raise ValidationError(
            f"{YOUTUBE_DAYS_TO_KEEP_ENV} must be a positive integer number of days"
        )

    base_time = now or datetime.now(UTC)
    if base_time.tzinfo is None:
        base_time = base_time.replace(tzinfo=UTC)
    return base_time + timedelta(days=days_to_keep)
