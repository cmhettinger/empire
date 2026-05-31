from __future__ import annotations

from datetime import UTC, datetime

import pytest
from empire_core.exceptions import ValidationError

from empire_youtube.retention import (
    DEFAULT_YOUTUBE_DAYS_TO_KEEP,
    YOUTUBE_DAYS_TO_KEEP_ENV,
    youtube_expires_at,
)


def test_youtube_expires_at_uses_default_when_unset(monkeypatch):
    monkeypatch.delenv(YOUTUBE_DAYS_TO_KEEP_ENV, raising=False)
    now = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)

    assert youtube_expires_at(now=now) == datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
    assert DEFAULT_YOUTUBE_DAYS_TO_KEEP == 10


def test_youtube_expires_at_uses_days_to_keep(monkeypatch):
    monkeypatch.setenv(YOUTUBE_DAYS_TO_KEEP_ENV, "14")
    now = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)

    assert youtube_expires_at(now=now) == datetime(2026, 6, 14, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize("value", ["0", "-1", "abc"])
def test_youtube_expires_at_rejects_invalid_values(monkeypatch, value):
    monkeypatch.setenv(YOUTUBE_DAYS_TO_KEEP_ENV, value)

    with pytest.raises(ValidationError, match=YOUTUBE_DAYS_TO_KEEP_ENV):
        youtube_expires_at()
