"""Bilibili 16:9 High-CTR Viral Cover Typography Engine for ContentFlow.

Transforms 9:16 portrait or 16:9 landscape raw assets into 1920x1080 (16:9)
Bilibili viral covers with 4:3 center safe-zone (x: 240..1680) typography,
8px black stroke + drop shadow, top capsule badge, and bottom highlight tags.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from config.settings import DEFAULT_FONTS

SAFE_ZONE_X_MIN = 240
SAFE_ZONE_X_MAX = 1680
TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080


@dataclass
class CoverDesignResult:
    output_path: Path
    output_4x3_path: Optional[Path]
    width: int
    height: int
    source_size: Tuple[int, int]
    layout_mode: str  # "portrait_to_16x9" or "landscape_16x9"
    safe_zone_x: Tuple[int, int]
    hook_lines: List[str]
    badge_text: str
    bottom_tags: List[str]
    font_path: str

    def __getitem__(self, key: str) -> Any:
        mapping = self.to_dict()
        if key == "cover_path":
            return str(self.output_path)
        if key == "cover_4x3_path":
            return str(self.output_4x3_path) if self.output_4x3_path else None
        return mapping[key]

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["output_path"] = str(self.output_path)
        d["cover_path"] = str(self.output_path)
        d["output_4x3_path"] = str(self.output_4x3_path) if self.output_4x3_path else None
        d["cover_4x3_path"] = str(self.output_4x3_path) if self.output_4x3_path else None
        return d


class CoverDesigner:
    """Renders 1920x1080 (16:9) high-CTR Bilibili covers and 1440x1080 (4:3) safe crops."""

    COLOR_GOLD = (255, 215, 0, 255)  # #FFD700
    COLOR_WHITE = (255, 255, 255, 255)  # #FFFFFF
    COLOR_CYAN = (0, 240, 255, 255)  # #00F0FF
    COLOR_BLACK = (0, 0, 0, 255)  # #000000

    def __init__(self, font_path: Optional[Union[str, Path]] = None):
        self.font_path = self._resolve_font_path(font_path)

    @staticmethod
    def _resolve_font_path(font_path: Optional[Union[str, Path]] = None) -> str:
        candidates: List[str] = []
        if font_path:
            candidates.append(str(font_path))
        candidates.extend(DEFAULT_FONTS)
        candidates.extend(
            [
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            ]
        )
        for cand in candidates:
            if Path(cand).exists():
                return cand
        return ""

    def _load_font(self, size: int) -> Union[ImageFont.FreeTypeFont, ImageFont.ImageFont]:
        if self.font_path and Path(self.font_path).exists():
            if "notosanscjk" in self.font_path.lower() and self.font_path.lower().endswith(".ttc"):
                try:
                    return ImageFont.truetype(self.font_path, size=size, index=2)
                except Exception:
                    pass
            return ImageFont.truetype(self.font_path, size=size)
        return ImageFont.load_default(size=size)

    def _fit_font_to_width(
        self, draw: ImageDraw.ImageDraw, text: str, max_width: int, start_size: int, min_size: int = 44
    ) -> Union[ImageFont.FreeTypeFont, ImageFont.ImageFont]:
        size = start_size
        while size >= min_size:
            font = self._load_font(size)
            bbox = draw.textbbox((0, 0), text, font=font, stroke_width=8)
            w = bbox[2] - bbox[0]
            if w <= max_width:
                return font
            size -= 4
        return self._load_font(min_size)

    @staticmethod
    def _draw_stroked_text(
        canvas: Image.Image,
        position: Tuple[int, int],
        text: str,
        font: Union[ImageFont.FreeTypeFont, ImageFont.ImageFont],
        fill: Tuple[int, int, int, int],
        stroke_width: int = 8,
        shadow_offset: Tuple[int, int] = (6, 8),
    ) -> Tuple[int, int, int, int]:
        """Draws text with soft drop shadow and thick pure-black stroke for maximum CTR legibility."""
        if not text:
            return (position[0], position[1], position[0], position[1])

        x, y = position
        # Shadow layer
        shadow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        s_draw = ImageDraw.Draw(shadow_layer)
        s_draw.text(
            (x + shadow_offset[0], y + shadow_offset[1]),
            text,
            font=font,
            fill=(0, 0, 0, 210),
            stroke_width=stroke_width + 2,
            stroke_fill=(0, 0, 0, 210),
        )
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=6))
        canvas.alpha_composite(shadow_layer)

        # Foreground stroked text
        draw = ImageDraw.Draw(canvas)
        draw.text(
            (x, y),
            text,
            font=font,
            fill=fill,
            stroke_width=stroke_width,
            stroke_fill=(0, 0, 0, 255),
        )
        raw_bbox = draw.textbbox((x, y), text, font=font, stroke_width=stroke_width)
        return (int(raw_bbox[0]), int(raw_bbox[1]), int(raw_bbox[2]), int(raw_bbox[3]))

    def _draw_capsule_badge(
        self,
        canvas: Image.Image,
        x: int,
        y: int,
        text: str,
        bg_color: Tuple[int, int, int, int] = (230, 35, 95, 240),
        border_color: Tuple[int, int, int, int] = (255, 215, 0, 255),
    ) -> Tuple[int, int]:
        """Draws a glowing top capsule badge at (x, y) and returns (width, height)."""
        draw = ImageDraw.Draw(canvas)
        font = self._load_font(36)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = int(bbox[2] - bbox[0])
        th = int(bbox[3] - bbox[1])
        pad_x, pad_y = 28, 14
        w = int(tw + pad_x * 2)
        h = int(th + pad_y * 2)

        draw.rounded_rectangle(
            [x, y, x + w, y + h],
            radius=h // 2,
            fill=bg_color,
            outline=border_color,
            width=3,
        )
        # Draw badge text centered inside capsule
        tx = int(x + (w - tw) // 2 - bbox[0])
        ty = int(y + (h - th) // 2 - bbox[1])
        draw.text(
            (tx, ty),
            text,
            font=font,
            fill=(255, 255, 255, 255),
            stroke_width=2,
            stroke_fill=(0, 0, 0, 200),
        )
        return w, h

    def _draw_bottom_tags(
        self,
        canvas: Image.Image,
        x: int,
        y: int,
        tags: List[str],
    ) -> None:
        """Draws sleek cyber highlight pill tags at the bottom of the safe zone."""
        draw = ImageDraw.Draw(canvas)
        font = self._load_font(34)
        cur_x = int(x)
        for idx, tag in enumerate(tags):
            bbox = draw.textbbox((0, 0), tag, font=font)
            tw = int(bbox[2] - bbox[0])
            th = int(bbox[3] - bbox[1])
            pad_x, pad_y = 24, 12
            w = int(tw + pad_x * 2)
            h = int(th + pad_y * 2)

            accent = (0, 240, 255, 255) if idx % 2 == 0 else (255, 215, 0, 255)
            draw.rounded_rectangle(
                [cur_x, y, cur_x + w, y + h],
                radius=14,
                fill=(10, 22, 42, 230),
                outline=accent,
                width=3,
            )
            tx = int(cur_x + (w - tw) // 2 - bbox[0])
            ty = int(y + (h - th) // 2 - bbox[1])
            draw.text(
                (tx, ty),
                tag,
                font=font,
                fill=accent,
                stroke_width=2,
                stroke_fill=(0, 0, 0, 220),
            )
            cur_x += w + 20

    def _compose_portrait_to_16x9(
        self,
        src: Image.Image,
        hook_lines: List[str],
        badge_text: str,
        bottom_tags: List[str],
    ) -> Image.Image:
        """Converts a 9:16 portrait image into a 1920x1080 viral cover."""
        # 1. Build 1920x1080 deep-sea / cyber glowing background from upscaled blurred base image
        bg_scale = max(TARGET_WIDTH / src.width, TARGET_HEIGHT / src.height) * 1.12
        bg_w, bg_h = int(src.width * bg_scale), int(src.height * bg_scale)
        bg = src.convert("RGB").resize((bg_w, bg_h), Image.Resampling.LANCZOS)
        crop_x = (bg_w - TARGET_WIDTH) // 2
        crop_y = (bg_h - TARGET_HEIGHT) // 3
        bg = bg.crop((crop_x, crop_y, crop_x + TARGET_WIDTH, crop_y + TARGET_HEIGHT))
        bg = bg.filter(ImageFilter.GaussianBlur(radius=32))
        bg = ImageEnhance.Brightness(bg).enhance(0.42)
        bg = ImageEnhance.Color(bg).enhance(1.35)
        canvas = bg.convert("RGBA")

        # 2. Deep ocean / cyber dark gradient vignette on the left for extreme typography contrast
        grad = Image.new("RGBA", (TARGET_WIDTH, TARGET_HEIGHT), (0, 0, 0, 0))
        g_draw = ImageDraw.Draw(grad)
        for x in range(TARGET_WIDTH):
            if x < 980:
                alpha = int(215 - (x / 980.0) * 55)
            elif x < 1260:
                t = (x - 980) / 280.0
                alpha = int(160 * (1.0 - t) + 35 * t)
            else:
                alpha = 35
            g_draw.line([(x, 0), (x, TARGET_HEIGHT)], fill=(6, 14, 32, alpha))

        # Subtle glowing grid lines in background left safe area
        for gx in range(240, 1020, 120):
            g_draw.line([(gx, 0), (gx, TARGET_HEIGHT)], fill=(0, 210, 255, 18), width=1)
        for gy in range(120, TARGET_HEIGHT, 120):
            g_draw.line([(0, gy), (1050, gy)], fill=(0, 210, 255, 18), width=1)
        canvas.alpha_composite(grad)

        # 3. Place HD character subject in right golden visual zone x: 980..1760
        char_target_w = 780  # 1760 - 980 = 780
        char_scale = char_target_w / float(src.width)
        char_h = int(src.height * char_scale)
        char_img = src.convert("RGBA").resize((char_target_w, char_h), Image.Resampling.LANCZOS)

        # Crop top/upper-mid portion (head, face, gesture, torso/skirt) to fit 1080 height
        if char_h > TARGET_HEIGHT:
            char_crop = char_img.crop((0, 0, char_target_w, TARGET_HEIGHT))
        else:
            char_crop = Image.new("RGBA", (char_target_w, TARGET_HEIGHT), (0, 0, 0, 0))
            char_crop.paste(char_img, (0, TARGET_HEIGHT - char_h))

        # Soft horizontal alpha feather on left & right edge of character panel so it blends seamlessly
        mask = Image.new("L", (char_target_w, TARGET_HEIGHT), 255)
        m_draw = ImageDraw.Draw(mask)
        feather_left = 95
        feather_right = 55
        for fx in range(feather_left):
            a = int(255 * (fx / float(feather_left)) ** 1.4)
            m_draw.line([(fx, 0), (fx, TARGET_HEIGHT)], fill=a)
        for fx in range(feather_right):
            a = int(255 * (fx / float(feather_right)) ** 1.4)
            m_draw.line([(char_target_w - 1 - fx, 0), (char_target_w - 1 - fx, TARGET_HEIGHT)], fill=a)

        # Subtle cyan rim glow behind character
        glow = Image.new("RGBA", (TARGET_WIDTH, TARGET_HEIGHT), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        glow_draw.ellipse([1040, 80, 1720, 980], fill=(0, 200, 255, 55))
        glow = glow.filter(ImageFilter.GaussianBlur(radius=60))
        canvas.alpha_composite(glow)

        char_layer = Image.new("RGBA", (TARGET_WIDTH, TARGET_HEIGHT), (0, 0, 0, 0))
        char_layer.paste(char_crop, (980, 0), mask=mask)
        canvas.alpha_composite(char_layer)

        # 4. Left safe-zone typography (x: 240..1020, strictly inside 4:3 safe box x: 240..1680)
        text_x = 255
        max_text_w = 1020 - text_x  # 765px max width so it stays strictly within x: 240..1020

        # Top capsule badge
        if badge_text:
            self._draw_capsule_badge(canvas, text_x, 125, badge_text)

        # 3 lines of giant high-contrast stroked main title
        colors = [self.COLOR_GOLD, self.COLOR_WHITE, self.COLOR_CYAN]
        start_sizes = [104, 96, 92]
        cur_y = 245
        draw = ImageDraw.Draw(canvas)
        for idx, line in enumerate(hook_lines[:3]):
            if not line:
                continue
            color = colors[idx % len(colors)]
            target_sz = start_sizes[idx % len(start_sizes)]
            font = self._fit_font_to_width(draw, line, max_width=max_text_w, start_size=target_sz, min_size=52)
            bbox = self._draw_stroked_text(
                canvas,
                (text_x, cur_y),
                line,
                font=font,
                fill=color,
                stroke_width=8,
                shadow_offset=(6, 8),
            )
            line_h = bbox[3] - bbox[1]
            cur_y += max(line_h + 34, 145)

        # Bottom highlight tags
        if bottom_tags:
            self._draw_bottom_tags(canvas, text_x, 865, bottom_tags)

        return canvas

    def _compose_landscape_16x9(
        self,
        src: Image.Image,
        hook_lines: List[str],
        badge_text: str,
        bottom_tags: List[str],
        repair_whiteboard_artifact: bool = True,
        hero_crop_params: Optional[Tuple[float, float, float]] = None,
    ) -> Image.Image:
        """Converts a 16:9 landscape scene into a 5-Star Split Hero viral cover (Left Dark Hook + Right Waist-Up Hero)."""
        # 1. Build 1920x1080 darkened blurred cyber atmosphere background
        bg = src.convert("RGB").resize((TARGET_WIDTH, TARGET_HEIGHT), Image.Resampling.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(radius=28))
        bg = ImageEnhance.Brightness(bg).enhance(0.38)
        bg = ImageEnhance.Color(bg).enhance(1.30)
        base = bg.convert("RGBA")

        # 2. Left deep dark cyber gradient vignette (x: 0..1020) for 100% clean typography contrast
        grad = Image.new("RGBA", (TARGET_WIDTH, TARGET_HEIGHT), (0, 0, 0, 0))
        g_draw = ImageDraw.Draw(grad)
        for x in range(TARGET_WIDTH):
            if x < 960:
                alpha = int(225 - (x / 960.0) * 50)
            elif x < 1240:
                t = (x - 960) / 280.0
                alpha = int(175 * (1.0 - t) + 25 * t)
            else:
                alpha = 25
            g_draw.line([(x, 0), (x, TARGET_HEIGHT)], fill=(6, 14, 32, alpha))

        for gx in range(240, 1020, 120):
            g_draw.line([(gx, 0), (gx, TARGET_HEIGHT)], fill=(0, 210, 255, 20), width=1)
        for gy in range(120, TARGET_HEIGHT, 120):
            g_draw.line([(0, gy), (1020, gy)], fill=(0, 210, 255, 20), width=1)
        base.alpha_composite(grad)

        # 3. Extract zero-distortion waist-up character hero portrait & place in right zone (x: 960..1920)
        sw, sh = src.size
        cy0_r, cy1_r, center_x_r = hero_crop_params if hero_crop_params is not None else (0.02, 0.76, 0.355)
        char_target_w = 960
        cy0 = max(0, int(sh * cy0_r))
        cy1 = min(sh, int(sh * cy1_r))
        crop_h = max(64, cy1 - cy0)
        crop_w = int(round(crop_h * (char_target_w / float(TARGET_HEIGHT))))
        cx0 = max(0, int(round(center_x_r * sw - 0.422 * crop_w)))
        cx1 = min(sw, cx0 + crop_w)
        if cx1 - cx0 < crop_w:
            cx0 = max(0, cx1 - crop_w)

        char_crop_raw = src.convert("RGB").crop((cx0, cy0, max(cx0 + 32, cx1), max(cy0 + 32, cy1)))
        char_resized = char_crop_raw.resize((char_target_w, TARGET_HEIGHT), Image.Resampling.LANCZOS)
        char_resized = char_resized.filter(ImageFilter.UnsharpMask(radius=1.5, percent=140, threshold=2))
        char_rgba = char_resized.convert("RGBA")

        # Soft horizontal alpha feather on left & right edge of character panel
        mask = Image.new("L", (char_target_w, TARGET_HEIGHT), 255)
        m_draw = ImageDraw.Draw(mask)
        feather_left = 115
        feather_right = 36
        for fx in range(feather_left):
            a = int(255 * (fx / float(feather_left)) ** 1.4)
            m_draw.line([(fx, 0), (fx, TARGET_HEIGHT)], fill=a)
        for fx in range(feather_right):
            a = int(255 * (fx / float(feather_right)) ** 1.4)
            m_draw.line([(char_target_w - 1 - fx, 0), (char_target_w - 1 - fx, TARGET_HEIGHT)], fill=a)

        glow = Image.new("RGBA", (TARGET_WIDTH, TARGET_HEIGHT), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        glow_draw.ellipse([1020, 70, 1720, 990], fill=(0, 210, 255, 58))
        glow = glow.filter(ImageFilter.GaussianBlur(radius=58))
        base.alpha_composite(glow)

        char_layer = Image.new("RGBA", (TARGET_WIDTH, TARGET_HEIGHT), (0, 0, 0, 0))
        char_layer.paste(char_rgba, (960, 0), mask=mask)
        base.alpha_composite(char_layer)

        # 4. Render giant high-contrast typography strictly in left safe zone (x: 255..995)
        text_x = 255
        max_text_w = 995 - text_x  # 740px max width — zero overlap with right character portrait!

        if badge_text:
            self._draw_capsule_badge(
                base,
                text_x,
                120,
                badge_text,
                bg_color=(0, 130, 210, 240),
                border_color=(0, 240, 255, 255),
            )

        colors = [self.COLOR_GOLD, self.COLOR_WHITE, self.COLOR_CYAN]
        start_sizes = [104, 96, 92]
        active_lines = [ln for ln in hook_lines[:3] if ln]
        cur_y = 245
        draw = ImageDraw.Draw(base)
        for idx, line in enumerate(active_lines):
            color = colors[idx % len(colors)]
            target_sz = start_sizes[idx % len(start_sizes)]
            font = self._fit_font_to_width(draw, line, max_width=max_text_w, start_size=target_sz, min_size=52)
            bbox = self._draw_stroked_text(
                base,
                (text_x, cur_y),
                line,
                font=font,
                fill=color,
                stroke_width=8,
                shadow_offset=(6, 8),
            )
            line_h = bbox[3] - bbox[1]
            cur_y += max(line_h + 34, 145)

        if bottom_tags:
            self._draw_bottom_tags(base, text_x, 865, bottom_tags)

        # Crisp micro-contrast sharpening so 16:9 and 4:3 safe-zone typography & portrait pop
        rgb_sharp = base.convert("RGB").filter(ImageFilter.UnsharpMask(radius=1.5, percent=150, threshold=1))
        return rgb_sharp.convert("RGBA")

    def design_cover(
        self,
        base_image_path: Union[str, Path],
        output_path: Union[str, Path],
        hook_line1: str = "AI接管B站账号",
        hook_line2: str = "连夜肝出大肥鱼",
        hook_line3: str = "60帧纯享热舞！",
        badge_text: str = "AI接管账号实录",
        bottom_tags: Optional[List[str]] = None,
        repair_whiteboard_artifact: bool = True,
        save_4x3_crop: bool = True,
        output_4x3_path: Optional[Union[str, Path]] = None,
        hero_crop_params: Optional[Tuple[float, float, float]] = None,
    ) -> CoverDesignResult:
        """Renders a 1920x1080 (16:9) cover and optional 1440x1080 (4:3) safe crop."""
        src_path = Path(base_image_path)
        if not src_path.exists():
            raise FileNotFoundError(f"Base image not found: {src_path}")

        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        src = Image.open(src_path)
        orig_w, orig_h = src.size
        hook_lines = [ln.strip() for ln in (hook_line1, hook_line2, hook_line3) if ln and ln.strip()]
        tags = bottom_tags if bottom_tags is not None else ["2K重绘", "60FPS满帧"]

        if orig_h > orig_w:
            layout_mode = "portrait_to_16x9"
            composed = self._compose_portrait_to_16x9(
                src=src,
                hook_lines=hook_lines,
                badge_text=badge_text,
                bottom_tags=tags,
            )
        else:
            layout_mode = "landscape_16x9"
            composed = self._compose_landscape_16x9(
                src=src,
                hook_lines=hook_lines,
                badge_text=badge_text,
                bottom_tags=tags,
                repair_whiteboard_artifact=repair_whiteboard_artifact,
                hero_crop_params=hero_crop_params,
            )

        rgb_cover = composed.convert("RGB")
        rgb_cover.save(out_path, format="JPEG", quality=95, subsampling=0)

        crop_4x3_file: Optional[Path] = None
        if save_4x3_crop:
            if output_4x3_path:
                crop_4x3_file = Path(output_4x3_path)
            else:
                crop_4x3_file = out_path.with_name(f"{out_path.stem}_4x3{out_path.suffix}")
            crop_4x3_file.parent.mkdir(parents=True, exist_ok=True)
            crop_4x3 = rgb_cover.crop((SAFE_ZONE_X_MIN, 0, SAFE_ZONE_X_MAX, TARGET_HEIGHT))
            crop_4x3.save(crop_4x3_file, format="JPEG", quality=95, subsampling=0)

        return CoverDesignResult(
            output_path=out_path,
            output_4x3_path=crop_4x3_file,
            width=TARGET_WIDTH,
            height=TARGET_HEIGHT,
            source_size=(orig_w, orig_h),
            layout_mode=layout_mode,
            safe_zone_x=(SAFE_ZONE_X_MIN, SAFE_ZONE_X_MAX),
            hook_lines=hook_lines,
            badge_text=badge_text,
            bottom_tags=tags,
            font_path=self.font_path,
        )

    def design_project_cover(
        self,
        project_dir: Union[str, Path],
        hook_line1: Optional[str] = None,
        hook_line2: Optional[str] = None,
        hook_line3: Optional[str] = None,
        badge_text: Optional[str] = None,
        bottom_tags: Optional[List[str]] = None,
        output_path: Optional[Union[str, Path]] = None,
    ) -> CoverDesignResult:
        """Auto-detects project base image and delivery cover path and renders a 16:9 viral cover."""
        pdir = Path(project_dir)
        pid = pdir.name.lower()

        # Locate base image in assets/
        assets_dir = pdir / "assets"
        delivery_dir = pdir / "delivery"
        delivery_dir.mkdir(parents=True, exist_ok=True)

        base_candidates = [
            assets_dir / "character_anchor.jpg",
            pdir / "images" / "scene_1.jpg",
            assets_dir / "scene_cover.jpg",
            assets_dir / "scene6_success_thumbsup.jpg",
            assets_dir / "scene2_base_url.jpg",
            assets_dir / "2b_teaching_base_url.jpg",
            assets_dir / "dafeiyu_master_stage_9x16.jpg",
            assets_dir / "rem_base_cover.jpg",
            assets_dir / "yowane_v3_scene5.jpg",
            assets_dir / "yowane_v3_scene3.jpg",
            assets_dir / "noshiro_reference.jpg",
        ]
        if assets_dir.exists():
            base_candidates.extend(
                [
                    p
                    for p in sorted(assets_dir.glob("*.jpg")) + sorted(assets_dir.glob("*.png"))
                    if p.name != "cover.jpg"
                ]
            )

        base_img: Optional[Path] = None
        for cand in base_candidates:
            if cand.exists():
                base_img = cand
                break

        if base_img is None:
            existing_covers = sorted(delivery_dir.glob("*_cover.jpg"))
            if existing_covers:
                base_img = existing_covers[0]
            else:
                raise FileNotFoundError(f"No suitable base image found in {pdir}")

        # Determine target cover path in delivery/
        if output_path:
            target_cover = Path(output_path)
        else:
            existing_covers = [p for p in sorted(delivery_dir.glob("*_cover.jpg")) if not p.stem.endswith("_4x3")]
            if existing_covers:
                target_cover = existing_covers[0]
            else:
                target_cover = delivery_dir / f"{pdir.name}_cover.jpg"

        # Project-specific viral defaults (check 008 before dafeiyu; 003/009 explicitly)
        repair_wb = False
        hero_crop: Optional[Tuple[float, float, float]] = None
        if "008" in pid or "diary" in pid or "takeover" in pid:
            h1 = hook_line1 or "把账号交给AI第5天"
            h2 = hook_line2 or "连夜爬完百万爆款"
            h3 = hook_line3 if hook_line3 is not None else "搭好全自动产线！"
            badge = badge_text or "AI接管账号·第5期"
            tags = bottom_tags or ["60FPS满帧", "赛博股东招募"]
        elif "007" in pid or "dafeiyu" in pid:
            h1 = hook_line1 or "把B站账号交给AI"
            h2 = hook_line2 or "连夜肝出大肥鱼"
            h3 = hook_line3 if hook_line3 is not None else "60帧纯享热舞！"
            badge = badge_text or "AI接管账号实录"
            tags = bottom_tags or ["2K深海重绘", "60FPS满帧"]
        elif "005" in pid or "noshiro" in pid or "transformer" in pid:
            h1 = hook_line1 or "把B站账号交给AI"
            h2 = hook_line2 or "能代3分钟带你"
            h3 = hook_line3 if hook_line3 is not None else "手撕Transformer！"
            badge = badge_text or "AI接管账号·第2期"
            tags = bottom_tags or ["手撕Attention", "60FPS满帧"]
            repair_wb = True
            hero_crop = (0.06, 0.66, 0.348)
        elif "004" in pid or "2b" in pid:
            h1 = hook_line1 or "API狂报401/404？"
            h2 = hook_line2 or "2B小姐姐手把手"
            h3 = hook_line3 if hook_line3 is not None else "60秒彻底打通！"
            badge = badge_text or "AI接管账号·第3期"
            tags = bottom_tags or ["60FPS满帧", "200 OK全通"]
            hero_crop = (0.02, 0.76, 0.355)
        elif "002" in pid or "yowane" in pid or "cicd" in pid:
            h1 = hook_line1 or "半夜发包又502？"
            h2 = hook_line2 or "3D弱音25秒带你"
            h3 = hook_line3 if hook_line3 is not None else "搞定CI/CD门禁！"
            badge = badge_text or "AI接管账号·第4期"
            tags = bottom_tags or ["60FPS满帧", "Docker全绿交付"]
            hero_crop = (0.11, 0.66, 0.180)
        elif "003" in pid or "managing" in pid or "termflow" in pid:
            h1 = hook_line1 or "怕AI幻觉删库跑路？"
            h2 = hook_line2 or "2B手把手硬核拆解"
            h3 = hook_line3 if hook_line3 is not None else "AI管AI四大护栏！"
            badge = badge_text or "AI接管账号·第6期"
            tags = bottom_tags or ["60FPS满帧", "MCP安全控制舱"]
            hero_crop = (0.02, 0.76, 0.355)
        elif "009" in pid or "rem" in pid or "aeflow" in pid:
            h1 = hook_line1 or "AI怎么自己点鼠标？"
            h2 = hook_line2 or "3D蕾姆60秒拆解"
            h3 = hook_line3 if hook_line3 is not None else "跨桌面GUI智能体！"
            badge = badge_text or "AI接管账号·第7期"
            tags = bottom_tags or ["60FPS满帧", "独立视口不抢鼠标"]
            hero_crop = (0.04, 0.76, 0.625)
        else:
            h1 = hook_line1 or "硬核AI技术实录"
            h2 = hook_line2 or pdir.name[:12]
            h3 = hook_line3 if hook_line3 is not None else "全流程高能解析"
            badge = badge_text or "ContentFlow出品"
            tags = bottom_tags or ["2K超清渲染", "硬核干货"]

        return self.design_cover(
            base_image_path=base_img,
            output_path=target_cover,
            hook_line1=h1,
            hook_line2=h2,
            hook_line3=h3,
            badge_text=badge,
            bottom_tags=tags,
            repair_whiteboard_artifact=repair_wb,
            hero_crop_params=hero_crop,
        )
