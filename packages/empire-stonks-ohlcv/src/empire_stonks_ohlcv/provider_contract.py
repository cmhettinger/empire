"""Small callable boundary implemented by provider-specific adapters."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeAlias

from empire_core import RunContext

from empire_stonks_ohlcv.results import AcquiredObject, ParsedProviderOutput


AcquireProviderObjects: TypeAlias = Callable[
    [RunContext],
    tuple[AcquiredObject, ...],
]
ParseProviderObjects: TypeAlias = Callable[
    [tuple[AcquiredObject, ...]],
    ParsedProviderOutput,
]
