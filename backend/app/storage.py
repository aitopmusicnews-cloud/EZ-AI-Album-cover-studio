from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import os

from PIL import Image, ImageDraw, ImageFont, ImageOps

WORKING_IMAGE_SIZE = 1000
FINAL_IMAGE_SIZE = 3000


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
            image = ImageOps.fit(image, (WORKING_IMAGE_SIZE, WORKING_IMAGE_SIZE), method=Image.Resampling.LANCZOS)
            if title or artist or parental_advisory:
                image = self._apply_release_text(
                    image,
                    title=title,
                    artist=artist,
                    parental_advisory=parental_advisory,
                    position=position,
                )
            # OpenAI currently returns a smaller square source image. Compose exact
            # typography in the established 1000px design coordinate system, then
            # upscale the finished square to the required distribution export size.
            image = image.resize((FINAL_IMAGE_SIZE, FINAL_IMAGE_SIZE), Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(output, format="PNG", optimize=True)
        self._atomic_write(path, output.getvalue())
        return relative.as_posix(), FINAL_IMAGE_SIZE, FINAL_IMAGE_SIZE

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
        position: int = 1,
    ) -> Image.Image:
        """Composite exact release text with album-cover typography.

        OpenAI is asked not to generate lettering because image-model text can be
        misspelled.  We add the exact title/artist afterward.  Each variation uses
        a different editorial layout so a set feels like distinct cover concepts,
        not the same UI label pasted onto every image.
        """
        canvas = image.convert("RGBA")
        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        layout = ((position - 1) % 5) + 1
        if title or artist:
            if layout == 1:
                cls._draw_top_left_release(draw, title, artist)
            elif layout == 2:
                cls._draw_bottom_left_release(draw, title, artist)
            elif layout == 3:
                cls._draw_center_release(draw, title, artist)
            elif layout == 4:
                cls._draw_top_center_release(draw, title, artist)
            else:
                cls._draw_bottom_center_release(draw, title, artist)

        if parental_advisory:
            cls._draw_parental_advisory(draw)

        return Image.alpha_composite(canvas, overlay).convert("RGB")

    @classmethod
    def _draw_top_left_release(cls, draw: ImageDraw.ImageDraw, title: str | None, artist: str | None) -> None:
        cls._vertical_gradient(draw, 0, 0, 1000, 380, top_alpha=190, bottom_alpha=0)
        x, y = 54, 45
        if artist:
            artist_font = cls._font(30, bold=True)
            draw.text((x + 2, y), artist.upper(), font=artist_font, fill=(242, 225, 198, 255), stroke_width=1, stroke_fill=(0, 0, 0, 160))
            y += 48
        if title:
            font, lines = cls._fit_wrapped_text(title, max_width=860, max_lines=3, start_size=100, min_size=42, bold=True)
            for line in lines:
                draw.text((x, y), line, font=font, fill=(248, 246, 240, 255), stroke_width=3, stroke_fill=(0, 0, 0, 210))
                box = draw.textbbox((0, 0), line, font=font, stroke_width=3)
                y += box[3] - box[1] + 4

    @classmethod
    def _draw_bottom_left_release(cls, draw: ImageDraw.ImageDraw, title: str | None, artist: str | None) -> None:
        cls._vertical_gradient(draw, 0, 610, 1000, 1000, top_alpha=0, bottom_alpha=220)
        font, lines = cls._fit_wrapped_text(title or "", max_width=820, max_lines=3, start_size=112, min_size=44, bold=True)
        title_height = cls._lines_height(draw, lines, font, spacing=2)
        artist_height = 42 if artist else 0
        y = 930 - title_height - artist_height
        x = 54
        if artist:
            artist_font = cls._font(30, bold=True)
            draw.text((x + 2, y), artist.upper(), font=artist_font, fill=(230, 170, 100, 255), stroke_width=1, stroke_fill=(0, 0, 0, 180))
            y += 43
        for line in lines:
            draw.text((x, y), line, font=font, fill=(248, 248, 244, 255), stroke_width=4, stroke_fill=(0, 0, 0, 230))
            box = draw.textbbox((0, 0), line, font=font, stroke_width=4)
            y += box[3] - box[1] + 2

    @classmethod
    def _draw_center_release(cls, draw: ImageDraw.ImageDraw, title: str | None, artist: str | None) -> None:
        # A strong rap/mixtape-style title band: large, exact lettering without
        # pretending the image model can spell it correctly.
        font, lines = cls._fit_wrapped_text(title or "", max_width=900, max_lines=3, start_size=128, min_size=48, bold=True)
        title_height = cls._lines_height(draw, lines, font, spacing=-2)
        center_y = 650
        band_top = max(430, center_y - title_height // 2 - 48)
        band_bottom = min(900, center_y + title_height // 2 + 72 + (38 if artist else 0))
        draw.rectangle((0, band_top, 1000, band_bottom), fill=(0, 0, 0, 118))
        y = center_y - title_height / 2
        for line in lines:
            cls._center_text(draw, (500, y + cls._line_height(draw, line, font) / 2), line.upper(), font, fill=(232, 232, 228, 255), stroke_width=4)
            y += cls._line_height(draw, line, font) - 2
        if artist:
            artist_font = cls._font(30, bold=True)
            cls._center_text(draw, (500, min(915, y + 34)), artist.upper(), artist_font, fill=(223, 156, 91, 255), stroke_width=1)

    @classmethod
    def _draw_top_center_release(cls, draw: ImageDraw.ImageDraw, title: str | None, artist: str | None) -> None:
        cls._vertical_gradient(draw, 0, 0, 1000, 330, top_alpha=175, bottom_alpha=0)
        y = 38
        if artist:
            artist_font = cls._font(25, bold=True)
            cls._center_text(draw, (500, y + 20), artist.upper(), artist_font, fill=(238, 231, 216, 255), stroke_width=1)
            y += 48
        if title:
            font, lines = cls._fit_wrapped_text(title, max_width=900, max_lines=2, start_size=96, min_size=42, bold=True)
            for line in lines:
                h = cls._line_height(draw, line, font)
                cls._center_text(draw, (500, y + h / 2), line, font, fill=(245, 238, 219, 255), stroke_width=3)
                y += h + 2

    @classmethod
    def _draw_bottom_center_release(cls, draw: ImageDraw.ImageDraw, title: str | None, artist: str | None) -> None:
        cls._vertical_gradient(draw, 0, 625, 1000, 1000, top_alpha=0, bottom_alpha=220)
        font, lines = cls._fit_wrapped_text(title or "", max_width=900, max_lines=2, start_size=106, min_size=44, bold=True)
        title_height = cls._lines_height(draw, lines, font, spacing=2)
        y = 925 - title_height - (40 if artist else 0)
        for line in lines:
            h = cls._line_height(draw, line, font)
            cls._center_text(draw, (500, y + h / 2), line, font, fill=(249, 247, 238, 255), stroke_width=4)
            y += h + 2
        if artist:
            artist_font = cls._font(28, bold=True)
            cls._center_text(draw, (500, min(960, y + 26)), artist.upper(), artist_font, fill=(224, 158, 92, 255), stroke_width=1)

    @classmethod
    def _draw_parental_advisory(cls, draw: ImageDraw.ImageDraw) -> None:
        width, height = 200, 94
        x = 1000 - width - 34
        y = 1000 - height - 30
        draw.rectangle((x, y, x + width, y + height), fill=(245, 245, 242, 248), outline=(0, 0, 0, 255), width=4)
        draw.rectangle((x + 4, y + 4, x + width - 4, y + 39), fill=(0, 0, 0, 255))
        top_font = cls._font(21, bold=True)
        bottom_font = cls._font(17, bold=True)
        cls._center_text(draw, (x + width / 2, y + 20), "PARENTAL ADVISORY", top_font, fill=(255, 255, 255, 255))
        cls._center_text(draw, (x + width / 2, y + 65), "EXPLICIT CONTENT", bottom_font, fill=(0, 0, 0, 255))

    @staticmethod
    def _vertical_gradient(
        draw: ImageDraw.ImageDraw,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        *,
        top_alpha: int,
        bottom_alpha: int,
    ) -> None:
        height = max(1, y1 - y0)
        for y in range(y0, y1):
            t = (y - y0) / height
            alpha = int(top_alpha + (bottom_alpha - top_alpha) * t)
            draw.line((x0, y, x1, y), fill=(0, 0, 0, alpha))

    @staticmethod
    def _line_height(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
        box = draw.textbbox((0, 0), text or "Ag", font=font, stroke_width=2)
        return max(1, box[3] - box[1])

    @classmethod
    def _lines_height(cls, draw: ImageDraw.ImageDraw, lines: list[str], font: ImageFont.ImageFont, *, spacing: int) -> int:
        if not lines:
            return 0
        return sum(cls._line_height(draw, line, font) for line in lines) + spacing * (len(lines) - 1)

    @staticmethod
    def _center_text(
        draw: ImageDraw.ImageDraw,
        center: tuple[float, float],
        text: str,
        font: ImageFont.ImageFont,
        *,
        fill: tuple[int, int, int, int],
        stroke_width: int = 0,
    ) -> None:
        box = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
        w = box[2] - box[0]
        h = box[3] - box[1]
        draw.text(
            (center[0] - w / 2, center[1] - h / 2 - box[1]),
            text,
            font=font,
            fill=fill,
            stroke_width=stroke_width,
            stroke_fill=(0, 0, 0, 220) if stroke_width else None,
        )

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
                "/System/Library/Fonts/Supplemental/Arial Black.ttf",
                "/System/Library/Fonts/Supplemental/Impact.ttf",
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
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
