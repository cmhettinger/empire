from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from reportlab.lib.utils import ImageReader
from reportlab.platypus import Flowable, Paragraph

from empire_reports.renderers.pdf.styles import ReportStyles


@dataclass(frozen=True, slots=True)
class ChartBlockSpec:
    image_path: Path
    caption: str | None = None
    caption_gap: float = 6.0
    allow_upscale: bool = False
    pad: float = 6.0


class ChartBlock(Flowable):
    def __init__(self, spec: ChartBlockSpec, *, styles: ReportStyles) -> None:
        super().__init__()
        self.spec = spec
        self.styles = styles
        self._reader = ImageReader(str(spec.image_path))
        width, height = self._reader.getSize()
        self._image_width = float(width)
        self._image_height = float(height)
        self._draw_width = 0.0
        self._draw_height = 0.0
        self._caption: Paragraph | None = None
        self._caption_height = 0.0
        self._total_height = 0.0

    def wrap(self, availWidth: float, availHeight: float) -> tuple[float, float]:  # noqa: N802
        available_width = max(1.0, float(availWidth) - self.spec.pad)
        available_height = max(1.0, float(availHeight) - self.spec.pad)
        caption_gap = self.spec.caption_gap if self.spec.caption else 0.0

        self._caption = Paragraph(self.spec.caption, self.styles.small) if self.spec.caption else None
        self._caption_height = 0.0
        if self._caption:
            _, self._caption_height = self._caption.wrap(available_width, available_height)

        image_height = max(1.0, available_height - self._caption_height - caption_gap)
        scale = min(available_width / self._image_width, image_height / self._image_height)
        if not self.spec.allow_upscale:
            scale = min(scale, 1.0)

        self._draw_width = self._image_width * scale
        self._draw_height = self._image_height * scale
        self._total_height = self._draw_height + caption_gap + self._caption_height
        return self._draw_width, self._total_height

    def draw(self) -> None:
        caption_gap = self.spec.caption_gap if self._caption else 0.0
        y = self._caption_height + caption_gap
        self.canv.drawImage(
            self._reader,
            0,
            y,
            width=self._draw_width,
            height=self._draw_height,
            preserveAspectRatio=True,
            mask="auto",
        )
        if self._caption:
            self._caption.drawOn(self.canv, 0, 0)
