from __future__ import annotations

from pathlib import Path

from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image


def scaled_image(path: Path, *, max_width: float, max_height: float) -> Image:
    reader = ImageReader(str(path))
    image_width, image_height = reader.getSize()
    scale = min(max_width / float(image_width), max_height / float(image_height), 1.0)
    return Image(str(path), width=image_width * scale, height=image_height * scale)
