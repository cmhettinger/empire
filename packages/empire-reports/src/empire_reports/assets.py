from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AssetRegistry:
    """Resolve shared Empire report assets from the runtime resource root."""

    root: Path

    @classmethod
    def discover(cls, start: Path | None = None) -> "AssetRegistry":
        env_root = os.environ.get("EMPIRE_RESOURCES_ROOT")
        if env_root:
            return cls(root=Path(env_root).expanduser().resolve())

        start_path = Path(start or Path.cwd()).expanduser().resolve()
        for candidate in (start_path, *start_path.parents):
            resources_root = candidate / "resources"
            if resources_root.exists():
                return cls(root=resources_root)

        package_path = Path(__file__).resolve()
        for candidate in package_path.parents:
            resources_root = candidate / "resources"
            if resources_root.exists():
                return cls(root=resources_root)

        return cls(root=(start_path / "resources").resolve())

    @property
    def branding_dir(self) -> Path:
        return self.root / "branding"

    @property
    def images_dir(self) -> Path:
        return self.root / "images"

    @property
    def icons_dir(self) -> Path:
        return self.images_dir / "icons"

    def image_path(self, filename: str | Path) -> Path:
        return self._required_file(self.images_dir, filename, kind="Image")

    def icon_path(self, filename: str | Path) -> Path:
        return self._required_file(self.icons_dir, filename, kind="Icon")

    @staticmethod
    def _required_file(base: Path, filename: str | Path, *, kind: str) -> Path:
        relative_path = Path(filename)
        if relative_path.is_absolute():
            raise ValueError(f"{kind} path must be relative: {filename}")

        resolved_base = base.resolve()
        resolved_path = (resolved_base / relative_path).resolve()
        if not resolved_path.is_relative_to(resolved_base):
            raise ValueError(f"{kind} path escapes {resolved_base}: {filename}")
        if not resolved_path.is_file():
            raise FileNotFoundError(f"{kind} not found: {resolved_path}")
        return resolved_path
