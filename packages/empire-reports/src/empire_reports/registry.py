from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from empire_reports.contracts import OutputFormat, RenderResult


RenderCallable = Callable[..., RenderResult]


@dataclass(frozen=True, slots=True)
class RegisteredRenderer:
    report_id: str
    output_format: OutputFormat
    render: RenderCallable


class RendererRegistry:
    def __init__(self) -> None:
        self._renderers: dict[tuple[str, OutputFormat], RegisteredRenderer] = {}

    def register(self, renderer: RegisteredRenderer) -> None:
        key = (renderer.report_id, renderer.output_format)
        self._renderers[key] = renderer

    def get(self, report_id: str, output_format: OutputFormat) -> RegisteredRenderer:
        key = (report_id, output_format)
        if key not in self._renderers:
            known = sorted(f"{r}.{fmt.value}" for r, fmt in self._renderers)
            raise KeyError(f"Unknown renderer {report_id}.{output_format.value}; known={known}")
        return self._renderers[key]

    def all(self) -> tuple[RegisteredRenderer, ...]:
        return tuple(self._renderers.values())
