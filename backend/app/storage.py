from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import os

from PIL import Image, ImageDraw, ImageFont, ImageOps


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
        self,
        generation_id: str,
        variation_set_id: str,
        position: int,
        raw: bytes,
        *,
        title: str | None = None,
        artist: str | None = None,
        parental_advisory: bool = False,
    ) -> tuple[str, int, int]:
        relative = Path("images") / generation_id / variation_set_id / f"{position}.png"
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(BytesIO(raw)) as source:
            image = source.convert("RGB")
            image = ImageOps.fit(image, (1000, 1000), method=Image.Resampling.LANCZOS)
            if title or artist or parental_advisory:
                image = self._apply_release_text(
                    image,
                    title=title,
                    artist=artist,
                    parental_advisory=parental_advisory,
                )
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

    @classmethod
    def _apply_release_text(
        cls,
        image: Image.Image,
        *,
        title: str | None,
        artist: str | None,
        parental_advisory: bool,
    ) -> Image.Image:
        canvas = image.convert("RGBA")
        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        if title or artist:
            left = 48
            top = 46
            max_width = 830
            title_lines: list[str] = []
            title_font = None
            if title:
                title_font, title_lines = cls._fit_wrapped_text(
                    title,
                    max_width=max_width,
                    max_lines=3,
                    start_size=76,
                    min_size=34,
                    bold=True,
                )
            artist_font = cls._font(34, bold=True)
            artist_text = artist or ""

            measured = []
            if title_font and title_lines:
                for line in title_lines:
                    box = draw.textbbox((0, 0), line, font=title_font, stroke_width=1)
                    measured.append((box[2] - box[0], box[3] - box[1]))
            if artist_text:
                box = draw.textbbox((0, 0), artist_text, font=artist_font)
                measured.append((box[2] - box[0], box[3] - box[1]))
            panel_width = min(max_width + 34, max((size[0] for size in measured), default=300) + 38)
            title_height = sum(size[1] + 8 for size in measured[:len(title_lines)])
            artist_height = measured[-1][1] + 12 if artist_text and measured else 0
            panel_height = max(92, title_height + artist_height + 42)

            draw.rounded_rectangle(
                (left - 18, top - 16, left - 18 + panel_width, top - 16 + panel_height),
                radius=18,
                fill=(5, 6, 6, 118),
                outline=(255, 255, 255, 30),
                width=1,
            )
            draw.rounded_rectangle(
                (left - 4, top - 2, left + 5, top - 2 + max(42, panel_height - 28)),
                radius=4,
                fill=(215, 122, 36, 235),
            )

            y = top
            if title_font:
                for line in title_lines:
                    draw.text(
                        (left + 20, y),
                        line,
                        font=title_font,
                        fill=(255, 255, 255, 255),
                        stroke_width=2,
                        stroke_fill=(0, 0, 0, 120),
                    )
                    box = draw.textbbox((0, 0), line, font=title_font, stroke_width=2)
                    y += (box[3] - box[1]) + 8
            if artist_text:
                y += 5
                draw.text(
                    (left + 21, y),
                    artist_text,
                    font=artist_font,
                    fill=(240, 161, 91, 255),
                    stroke_width=1,
                    stroke_fill=(0, 0, 0, 100),
                )

        if parental_advisory:
            cls._draw_parental_advisory(draw)

        return Image.alpha_composite(canvas, overlay).convert("RGB")

    @classmethod
    def _draw_parental_advisory(cls, draw: ImageDraw.ImageDraw) -> None:
        width, height = 230, 108
        x = 1000 - width - 42
        y = 1000 - height - 42
        draw.rectangle((x, y, x + width, y + height), fill=(245, 245, 242, 244), outline=(0, 0, 0, 255), width=5)
        draw.rectangle((x + 5, y + 5, x + width - 5, y + 44), fill=(0, 0, 0, 255))
        top_font = cls._font(25, bold=True)
        bottom_font = cls._font(19, bold=True)
        label = "PARENTAL ADVISORY"
        sub = "EXPLICIT CONTENT"
        cls._center_text(draw, (x + width / 2, y + 24), label, top_font, fill=(255, 255, 255, 255))
        cls._center_text(draw, (x + width / 2, y + 74), sub, bottom_font, fill=(0, 0, 0, 255))

    @staticmethod
    def _center_text(draw: ImageDraw.ImageDraw, center: tuple[float, float], text: str, font: ImageFont.ImageFont, *, fill: tuple[int, int, int, int]) -> None:
        box = draw.textbbox((0, 0), text, font=font)
        w = box[2] - box[0]
        h = box[3] - box[1]
        draw.text((center[0] - w / 2, center[1] - h / 2 - box[1]), text, font=font, fill=fill)

    @classmethod
    def _fit_wrapped_text(
        cls,
        text: str,
        *,
        max_width: int,
        max_lines: int,
        start_size: int,
        min_size: int,
        bold: bool,
    ) -> tuple[ImageFont.ImageFont, list[str]]:
        for size in range(start_size, min_size - 1, -2):
            font = cls._font(size, bold=bold)
            lines = cls._wrap_text(text, font, max_width)
            if len(lines) <= max_lines:
                return font, lines
        font = cls._font(min_size, bold=bold)
        lines = cls._wrap_text(text, font, max_width)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            last = lines[-1]
            while last and cls._text_width(last + "…", font) > max_width:
                last = last[:-1]
            lines[-1] = last.rstrip() + "…"
        return font, lines

    @classmethod
    def _wrap_text(cls, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
        words = text.split()
        if not words:
            return []
        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if cls._text_width(candidate, font) <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    @staticmethod
    def _text_width(text: str, font: ImageFont.ImageFont) -> int:
        box = font.getbbox(text)
        return int(box[2] - box[0])

    @staticmethod
    def _font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
        candidates = (
            [
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                "/System/Library/Fonts/Supplemental/Arial.ttf",
                "/Library/Fonts/Arial Bold.ttf",
            ]
            if bold
            else [
                "/System/Library/Fonts/Supplemental/Arial.ttf",
                "/Library/Fonts/Arial.ttf",
            ]
        )
        candidates += [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        ]
        for candidate in candidates:
            try:
                return ImageFont.truetype(candidate, size=size)
            except OSError:
                continue
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            return ImageFont.load_default()

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_bytes(data)
        os.replace(temp, path)
