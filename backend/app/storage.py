from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from math import pi, sin
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
        typography_style: str | None = None,
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
                    position=position,
                    typography_style=typography_style,
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
        position: int = 1,
        typography_style: str | None = None,
    ) -> Image.Image:
        """Composite exact release text with creative, face-safe typography.

        The generated image contains no lettering.  This deterministic compositor
        adds exact title/artist spelling afterward, but treats the lettering as
        cover design rather than UI text: script, italic serif, hand-marker, arc,
        rotation, layered shadows and offset baselines.  Position still defines a
        face-safe zone so typography never crosses the intended portrait region.
        """
        canvas = image.convert("RGBA")
        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))

        layout = ((position - 1) % 5) + 1
        style = typography_style or (
            "street_script",
            "heritage_script",
            "marker_signature",
            "editorial_italic",
            "vintage_arc",
        )[layout - 1]

        if title or artist:
            cls._draw_creative_release(overlay, title, artist, layout=layout, style=style)

        if parental_advisory:
            draw = ImageDraw.Draw(overlay)
            cls._draw_parental_advisory(draw)

        return Image.alpha_composite(canvas, overlay).convert("RGB")

    @classmethod
    def _draw_creative_release(
        cls,
        overlay: Image.Image,
        title: str | None,
        artist: str | None,
        *,
        layout: int,
        style: str,
    ) -> None:
        if style in {"street_script", "luxury_script", "heritage_script"}:
            cls._draw_script_release(overlay, title, artist, layout=layout, style=style)
        elif style == "marker_signature":
            cls._draw_marker_release(overlay, title, artist, layout=layout)
        elif style == "vintage_arc":
            cls._draw_arc_release(overlay, title, artist, layout=layout)
        elif style == "editorial_italic":
            cls._draw_editorial_release(overlay, title, artist, layout=layout)
        else:
            cls._draw_slanted_serif_release(overlay, title, artist, layout=layout)

    @classmethod
    def _draw_script_release(
        cls,
        overlay: Image.Image,
        title: str | None,
        artist: str | None,
        *,
        layout: int,
        style: str,
    ) -> None:
        if not title:
            cls._draw_artist_only(overlay, artist, layout)
            return

        zone = cls._safe_zone(layout)
        max_width = int((zone[2] - zone[0]) * 0.9)
        max_height = int((zone[3] - zone[1]) * 0.72)
        candidates = cls._script_font_candidates(style)
        font = cls._fit_font(title, max_width=max_width, start_size=132, min_size=50, candidates=candidates)

        # Render separately so the whole hand-lettered word/phrase can be tilted.
        bbox = font.getbbox(title)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        pad = 34
        text_layer = Image.new("RGBA", (tw + pad * 2, th + pad * 2), (0, 0, 0, 0))
        d = ImageDraw.Draw(text_layer)

        if style == "luxury_script":
            fill = (246, 236, 214, 255)
            accent = (177, 124, 78, 215)
            angle = -4
            stroke = 1
        elif style == "heritage_script":
            fill = (244, 226, 190, 255)
            accent = (88, 50, 28, 220)
            angle = -5
            stroke = 2
        else:
            fill = (245, 245, 238, 255)
            accent = (214, 112, 62, 235)
            angle = -7
            stroke = 2

        # Copper/ink offset creates hand-painted depth without a block banner.
        d.text((pad + 6, pad + 8 - bbox[1]), title, font=font, fill=accent, stroke_width=stroke + 2, stroke_fill=(0, 0, 0, 155))
        d.text((pad, pad - bbox[1]), title, font=font, fill=fill, stroke_width=stroke, stroke_fill=(0, 0, 0, 195))
        rotated = text_layer.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
        x, y = cls._place_layer(rotated.size, zone, layout)
        overlay.alpha_composite(rotated, (x, y))
        cls._draw_artist_signature(overlay, artist, zone, layout, below_y=y + rotated.height)

    @classmethod
    def _draw_marker_release(
        cls,
        overlay: Image.Image,
        title: str | None,
        artist: str | None,
        *,
        layout: int,
    ) -> None:
        if not title:
            cls._draw_artist_only(overlay, artist, layout)
            return
        zone = cls._safe_zone(layout)
        font = cls._fit_font(
            title,
            max_width=int((zone[2] - zone[0]) * 0.9),
            start_size=126,
            min_size=48,
            candidates=cls._marker_font_candidates(),
        )
        bbox = font.getbbox(title)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        layer = Image.new("RGBA", (tw + 80, th + 90), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        # Multiple imperfect offsets mimic marker/paint buildup.
        d.text((44, 38 - bbox[1]), title, font=font, fill=(0, 0, 0, 190), stroke_width=7, stroke_fill=(0, 0, 0, 170))
        d.text((36, 31 - bbox[1]), title, font=font, fill=(238, 232, 216, 255), stroke_width=2, stroke_fill=(71, 46, 33, 220))
        layer = layer.rotate(4 if layout in {2, 5} else -4, expand=True, resample=Image.Resampling.BICUBIC)
        x, y = cls._place_layer(layer.size, zone, layout)
        overlay.alpha_composite(layer, (x, y))
        cls._draw_artist_signature(overlay, artist, zone, layout, below_y=y + layer.height)

    @classmethod
    def _draw_editorial_release(
        cls,
        overlay: Image.Image,
        title: str | None,
        artist: str | None,
        *,
        layout: int,
    ) -> None:
        if not title:
            cls._draw_artist_only(overlay, artist, layout)
            return
        draw = ImageDraw.Draw(overlay)
        zone = cls._safe_zone(layout)
        font, lines = cls._fit_wrapped_with_candidates(
            title,
            max_width=int((zone[2] - zone[0]) * 0.88),
            max_lines=3,
            start_size=112,
            min_size=44,
            candidates=cls._italic_serif_candidates(),
        )
        total = cls._lines_height(draw, lines, font, spacing=-6)
        y = cls._zone_start_y(zone, total + (42 if artist else 0), layout)
        for i, line in enumerate(lines):
            # Alternating indents feel editorial instead of centered/blocky.
            indent = 0 if i % 2 == 0 else 56
            x = zone[0] + 26 + indent
            if layout in {4, 5}:
                w = cls._text_width(line, font)
                x = int((zone[0] + zone[2] - w) / 2 + (28 if i % 2 else -18))
            draw.text((x + 5, y + 6), line, font=font, fill=(0, 0, 0, 185))
            draw.text((x, y), line, font=font, fill=(246, 239, 224, 255), stroke_width=1, stroke_fill=(61, 36, 24, 210))
            y += cls._line_height(draw, line, font) - 6
        cls._draw_artist_signature(overlay, artist, zone, layout, below_y=y + 10)

    @classmethod
    def _draw_slanted_serif_release(
        cls,
        overlay: Image.Image,
        title: str | None,
        artist: str | None,
        *,
        layout: int,
    ) -> None:
        if not title:
            cls._draw_artist_only(overlay, artist, layout)
            return
        zone = cls._safe_zone(layout)
        font = cls._fit_font(
            title,
            max_width=int((zone[2] - zone[0]) * 0.84),
            start_size=118,
            min_size=44,
            candidates=cls._display_serif_candidates(),
        )
        bbox = font.getbbox(title)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        layer = Image.new("RGBA", (tw + 90, th + 90), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        # Three-color offset resembles print registration / vintage sleeve ink.
        d.text((48, 42 - bbox[1]), title, font=font, fill=(188, 85, 55, 235), stroke_width=2, stroke_fill=(0, 0, 0, 170))
        d.text((37, 30 - bbox[1]), title, font=font, fill=(238, 228, 207, 255), stroke_width=1, stroke_fill=(0, 0, 0, 210))
        layer = layer.rotate(-8 if layout not in {2, 5} else 6, expand=True, resample=Image.Resampling.BICUBIC)
        x, y = cls._place_layer(layer.size, zone, layout)
        overlay.alpha_composite(layer, (x, y))
        cls._draw_artist_signature(overlay, artist, zone, layout, below_y=y + layer.height)

    @classmethod
    def _draw_arc_release(
        cls,
        overlay: Image.Image,
        title: str | None,
        artist: str | None,
        *,
        layout: int,
    ) -> None:
        if not title:
            cls._draw_artist_only(overlay, artist, layout)
            return
        zone = cls._safe_zone(layout)
        font = cls._fit_font(
            title,
            max_width=int((zone[2] - zone[0]) * 0.86),
            start_size=98,
            min_size=38,
            candidates=cls._display_serif_candidates(),
        )
        cls._draw_text_arc(overlay, title, font, zone=zone, layout=layout)
        cls._draw_artist_signature(overlay, artist, zone, layout, below_y=zone[1] + int((zone[3] - zone[1]) * 0.72))

    @classmethod
    def _draw_text_arc(
        cls,
        overlay: Image.Image,
        text: str,
        font: ImageFont.ImageFont,
        *,
        zone: tuple[int, int, int, int],
        layout: int,
    ) -> None:
        widths = [max(1, cls._text_width(ch, font)) for ch in text]
        spacing = max(2, int(getattr(font, "size", 50) * 0.03))
        total = sum(widths) + spacing * max(0, len(text) - 1)
        scale = min(1.0, (zone[2] - zone[0] - 60) / max(1, total))
        if scale < 0.98:
            size = max(28, int(getattr(font, "size", 50) * scale))
            font = cls._font_from_candidates(size, cls._display_serif_candidates())
            widths = [max(1, cls._text_width(ch, font)) for ch in text]
            total = sum(widths) + spacing * max(0, len(text) - 1)

        x = zone[0] + max(24, int((zone[2] - zone[0] - total) / 2))
        upward = layout in {1, 4}
        base_y = zone[1] + (70 if upward else max(58, int((zone[3] - zone[1]) * 0.34)))
        amplitude = min(42, max(20, int((zone[3] - zone[1]) * 0.13)))

        for idx, (ch, cw) in enumerate(zip(text, widths)):
            t = idx / max(1, len(text) - 1)
            arc = sin(t * pi) * amplitude
            y = base_y + (arc if upward else -arc)
            angle = (t - 0.5) * (18 if upward else -18)
            bbox = font.getbbox(ch or " ")
            h = max(1, bbox[3] - bbox[1])
            char_layer = Image.new("RGBA", (cw + 40, h + 50), (0, 0, 0, 0))
            d = ImageDraw.Draw(char_layer)
            d.text((22, 16 - bbox[1]), ch, font=font, fill=(245, 231, 205, 255), stroke_width=2, stroke_fill=(47, 29, 20, 225))
            rotated = char_layer.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
            overlay.alpha_composite(rotated, (int(x - 18), int(y)))
            x += cw + spacing

    @classmethod
    def _draw_artist_signature(
        cls,
        overlay: Image.Image,
        artist: str | None,
        zone: tuple[int, int, int, int],
        layout: int,
        *,
        below_y: int,
    ) -> None:
        if not artist:
            return
        draw = ImageDraw.Draw(overlay)
        font = cls._font_from_candidates(30, cls._italic_serif_candidates())
        label = artist  # preserve the user's exact capitalization
        width = cls._text_width(label, font)
        max_y = zone[3] - 34
        y = min(max(zone[1] + 18, below_y + 3), max_y)
        if layout in {4, 5}:
            x = int((zone[0] + zone[2] - width) / 2)
        else:
            x = zone[0] + 34
        # Fine line + offset gives a designed signature lockup.
        draw.line((x, y - 8, min(zone[2] - 24, x + max(92, width // 2)), y - 8), fill=(210, 136, 79, 220), width=2)
        draw.text((x + 3, y + 3), label, font=font, fill=(0, 0, 0, 185))
        draw.text((x, y), label, font=font, fill=(235, 219, 196, 255))

    @classmethod
    def _draw_artist_only(cls, overlay: Image.Image, artist: str | None, layout: int) -> None:
        if not artist:
            return
        zone = cls._safe_zone(layout)
        cls._draw_artist_signature(overlay, artist, zone, layout, below_y=zone[1] + 40)

    @staticmethod
    def _safe_zone(layout: int) -> tuple[int, int, int, int]:
        # These zones correspond to the composition directions in prompts.py.
        # Layout 3 intentionally starts below y=610 so the portrait face zone
        # (roughly y=120..560) remains untouched.
        return {
            1: (40, 28, 930, 370),       # upper-left
            2: (38, 620, 925, 955),      # lower-left
            3: (38, 610, 955, 930),      # lower third
            4: (45, 25, 955, 335),       # top-center
            5: (45, 635, 955, 950),      # bottom-center
        }.get(layout, (38, 610, 955, 930))

    @staticmethod
    def _place_layer(
        layer_size: tuple[int, int], zone: tuple[int, int, int, int], layout: int
    ) -> tuple[int, int]:
        lw, lh = layer_size
        zw = zone[2] - zone[0]
        zh = zone[3] - zone[1]
        if layout in {4, 5}:
            x = zone[0] + max(0, (zw - lw) // 2)
        else:
            x = zone[0] + 12
        if layout in {1, 4}:
            y = zone[1] + 16
        else:
            y = zone[1] + max(8, (zh - lh) // 2 - 8)
        return max(zone[0], x), max(zone[1], y)

    @staticmethod
    def _zone_start_y(zone: tuple[int, int, int, int], content_height: int, layout: int) -> int:
        if layout in {1, 4}:
            return zone[1] + 24
        return max(zone[1] + 20, zone[3] - content_height - 28)

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
    def _fit_font(
        cls,
        text: str,
        *,
        max_width: int,
        start_size: int,
        min_size: int,
        candidates: list[str],
    ) -> ImageFont.ImageFont:
        for size in range(start_size, min_size - 1, -2):
            font = cls._font_from_candidates(size, candidates)
            if cls._text_width(text, font) <= max_width:
                return font
        return cls._font_from_candidates(min_size, candidates)

    @classmethod
    def _fit_wrapped_with_candidates(
        cls,
        text: str,
        *,
        max_width: int,
        max_lines: int,
        start_size: int,
        min_size: int,
        candidates: list[str],
    ) -> tuple[ImageFont.ImageFont, list[str]]:
        for size in range(start_size, min_size - 1, -2):
            font = cls._font_from_candidates(size, candidates)
            lines = cls._wrap_text(text, font, max_width)
            if len(lines) <= max_lines:
                return font, lines
        font = cls._font_from_candidates(min_size, candidates)
        lines = cls._wrap_text(text, font, max_width)[:max_lines]
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
    def _font_from_candidates(size: int, candidates: list[str]) -> ImageFont.ImageFont:
        for candidate in candidates:
            try:
                return ImageFont.truetype(candidate, size=size)
            except OSError:
                continue
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            return ImageFont.load_default()

    @classmethod
    def _script_font_candidates(cls, style: str) -> list[str]:
        if style == "luxury_script":
            preferred = [
                "/System/Library/Fonts/Supplemental/Snell Roundhand.ttc",
                "/System/Library/Fonts/Apple Chancery.ttf",
            ]
        elif style == "heritage_script":
            preferred = [
                "/System/Library/Fonts/Apple Chancery.ttf",
                "/System/Library/Fonts/Supplemental/Brush Script.ttf",
            ]
        else:
            preferred = [
                "/System/Library/Fonts/Supplemental/Brush Script.ttf",
                "/System/Library/Fonts/Supplemental/Snell Roundhand.ttc",
                "/System/Library/Fonts/Apple Chancery.ttf",
            ]
        return preferred + [
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        ]

    @staticmethod
    def _marker_font_candidates() -> list[str]:
        return [
            "/System/Library/Fonts/MarkerFelt.ttc",
            "/System/Library/Fonts/Noteworthy.ttc",
            "/System/Library/Fonts/Supplemental/Chalkboard.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
        ]

    @staticmethod
    def _italic_serif_candidates() -> list[str]:
        return [
            "/System/Library/Fonts/Supplemental/Didot.ttc",
            "/System/Library/Fonts/Supplemental/Baskerville.ttc",
            "/System/Library/Fonts/Supplemental/Georgia Italic.ttf",
            "/System/Library/Fonts/Supplemental/Times New Roman Italic.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
        ]

    @staticmethod
    def _display_serif_candidates() -> list[str]:
        return [
            "/System/Library/Fonts/Supplemental/Didot.ttc",
            "/System/Library/Fonts/Supplemental/Baskerville.ttc",
            "/System/Library/Fonts/Supplemental/Georgia.ttf",
            "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        ]

    @staticmethod
    def _font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
        candidates = (
            [
                "/System/Library/Fonts/Supplemental/Arial Black.ttf",
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                "/Library/Fonts/Arial Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            ]
            if bold
            else [
                "/System/Library/Fonts/Supplemental/Arial.ttf",
                "/Library/Fonts/Arial.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            ]
        )
        return LocalStorage._font_from_candidates(size, list(candidates))

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_bytes(data)
        os.replace(temp, path)
