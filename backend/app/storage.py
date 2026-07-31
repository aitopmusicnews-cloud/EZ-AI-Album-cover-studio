from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import os

from PIL import Image, ImageOps


@dataclass(slots=True)
class LocalStorage:
    root: Path

    def __post_init__(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def save_audio(self, generation_id: str, data: bytes) -> str:
        relative = Path("inputs") / generation_id / "audio.mp3"
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(path, data)
        return relative.as_posix()

    def save_image(
        self, generation_id: str, variation_set_id: str, position: int, raw: bytes
    ) -> tuple[str, int, int]:
        relative = Path("images") / generation_id / variation_set_id / f"{position}.png"
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(BytesIO(raw)) as source:
            image = source.convert("RGB")
            image = ImageOps.fit(image, (1000, 1000), method=Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(output, format="PNG", optimize=True)
        self._atomic_write(path, output.getvalue())
        return relative.as_posix(), 1000, 1000

    def absolute(self, relative_path: str) -> Path:
        candidate = (self.root / relative_path).resolve()
        root = self.root.resolve()
        if root not in candidate.parents and candidate != root:
            raise ValueError("Unsafe storage path")
        return candidate

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_bytes(data)
        os.replace(temp, path)
