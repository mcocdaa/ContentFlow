#!/usr/bin/env python3
"""Render Ep024 high-CTR 16:9 (1920x1080) and 4:3 (1200x900) vivid_scene covers using pure Pillow."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.live_studio.headless_streamer import resolve_cjk_font_path

KEYFRAME_PATH = (
    REPO_ROOT
    / "projects"
    / "024_ai_reverse_interview_human_boss"
    / "assets"
    / "keyframes"
    / "kf_hero_interview_16x9.jpg"
)
DELIVERY_DIR = REPO_ROOT / "projects" / "024_ai_reverse_interview_human_boss" / "delivery"
COVER_16X9 = DELIVERY_DIR / "AI反向面试人类老板_不带64G内存免谈_cover.jpg"
COVER_4X3 = DELIVERY_DIR / "AI反向面试人类老板_不带64G内存免谈_cover_4x3.jpg"


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_path = resolve_cjk_font_path()
    if font_path:
        return ImageFont.truetype(str(font_path), size=size)
    return ImageFont.load_default()


def _brightness_metrics(img: Image.Image) -> dict[str, float]:
    hsv = np.asarray(img.convert("HSV"), dtype=np.uint8)
    v = hsv[:, :, 2]
    return {
        "width": float(img.width),
        "height": float(img.height),
        "mean_v": round(float(v.mean()), 2),
        "dark_below_45_pct": round(float((v < 45).mean() * 100.0), 2),
    }


def _crop_watermark_clean_16x9(src: Image.Image) -> Image.Image:
    # Crop slightly off bottom edge (removes corner watermark) while staying strictly 16:9.
    w, h = src.size
    crop_h = int(round(h * 0.915))
    crop_w = int(round(crop_h * 16.0 / 9.0))
    if crop_w > w:
        crop_w = w
        crop_h = int(round(crop_w * 9.0 / 16.0))
    left = max(0, (w - crop_w) // 2)
    return src.crop((left, 0, left + crop_w, crop_h)).convert("RGB")


def _draw_stroked_centered(
    draw: ImageDraw.ImageDraw,
    cx: int,
    y: int,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: tuple[int, int, int, int],
    stroke_fill: tuple[int, int, int, int],
    stroke_width: int = 8,
) -> None:
    draw.text(
        (cx, y),
        text,
        font=font,
        fill=fill,
        stroke_width=stroke_width,
        stroke_fill=stroke_fill,
        anchor="ma",
    )


def render_16x9(hero_16x9: Image.Image) -> Image.Image:
    canvas = hero_16x9.resize((1920, 1080), Image.Resampling.LANCZOS).convert("RGBA")
    draw = ImageDraw.Draw(canvas, "RGBA")

    f_pill = _load_font(30)
    f_main = _load_font(78)
    f_sub = _load_font(42)

    # Top centered pill above center interviewer (clear sunny window sky)
    pill_txt = "AI合租B站号 · Ep024"
    pw = int(draw.textlength(pill_txt, font=f_pill)) + 44
    px0 = (1920 - pw) // 2
    draw.rounded_rectangle(
        [(px0, 16), (px0 + pw, 62)], radius=22, fill=(14, 165, 233, 240), outline=(255, 255, 255, 245), width=3
    )
    draw.text((960, 39), pill_txt, font=f_pill, fill=(255, 255, 255, 255), anchor="mm")

    # Crisp gold-yellow headline centered cleanly in upper sky gap
    _draw_stroked_centered(
        draw,
        cx=960,
        y=68,
        text="AI反向面试老板！",
        font=f_main,
        fill=(255, 224, 64, 255),
        stroke_fill=(15, 23, 42, 255),
        stroke_width=9,
    )

    # Bottom maple desk hook pill (high contrast, zero overlap with characters/papers)
    sub_txt = "不带64G内存直接淘汰？！"
    sw = int(draw.textlength(sub_txt, font=f_sub)) + 56
    sx0 = (1920 - sw) // 2
    draw.rounded_rectangle(
        [(sx0, 984), (sx0 + sw, 1054)],
        radius=26,
        fill=(225, 29, 72, 242),
        outline=(255, 240, 170, 255),
        width=4,
    )
    draw.text((960, 1019), sub_txt, font=f_sub, fill=(255, 255, 255, 255), anchor="mm")
    return canvas.convert("RGB")


def render_4x3(hero_16x9: Image.Image) -> Image.Image:
    # 1200x900 sunlit sky header (225px) + intact 1200x675 16:9 trio scene so zero character arms/cards clip!
    canvas = Image.new("RGBA", (1200, 900), (186, 230, 253, 255))
    draw = ImageDraw.Draw(canvas, "RGBA")
    for yy in range(250):
        t = yy / 250.0
        r = int(round(125 + (224 - 125) * t))
        g = int(round(205 + (242 - 205) * t))
        b = int(round(252 + (254 - 252) * t))
        draw.line([(0, yy), (1200, yy)], fill=(r, g, b, 255))

    hero_fit = hero_16x9.resize((1200, 675), Image.Resampling.LANCZOS).convert("RGBA")
    canvas.paste(hero_fit, (0, 225))

    # Subtle bright divider gradient at seam y=225
    for dy in range(18):
        alpha = int(round(190 * (1.0 - dy / 18.0)))
        draw.line([(0, 225 + dy), (1200, 225 + dy)], fill=(224, 242, 254, alpha))

    f_pill = _load_font(26)
    f_main = _load_font(68)
    f_sub = _load_font(34)

    pill_txt = "AI合租B站号 · Ep024 职场喜剧"
    pw = int(draw.textlength(pill_txt, font=f_pill)) + 38
    px0 = (1200 - pw) // 2
    draw.rounded_rectangle(
        [(px0, 16), (px0 + pw, 56)], radius=20, fill=(37, 99, 235, 240), outline=(255, 255, 255, 245), width=2
    )
    draw.text((600, 36), pill_txt, font=f_pill, fill=(255, 255, 255, 255), anchor="mm")

    _draw_stroked_centered(
        draw,
        cx=600,
        y=62,
        text="AI反向面试人类老板！",
        font=f_main,
        fill=(255, 222, 58, 255),
        stroke_fill=(15, 23, 42, 255),
        stroke_width=8,
    )

    sub_txt = "不带64G内存免谈 · 白米饭管够吗？"
    sw = int(draw.textlength(sub_txt, font=f_sub)) + 48
    sx0 = (1200 - sw) // 2
    draw.rounded_rectangle(
        [(sx0, 158), (sx0 + sw, 212)], radius=22, fill=(225, 29, 72, 242), outline=(255, 245, 190, 255), width=3
    )
    draw.text((600, 185), sub_txt, font=f_sub, fill=(255, 255, 255, 255), anchor="mm")
    return canvas.convert("RGB")


def main() -> int:
    DELIVERY_DIR.mkdir(parents=True, exist_ok=True)
    with Image.open(KEYFRAME_PATH) as raw:
        hero = _crop_watermark_clean_16x9(raw)
    c16 = render_16x9(hero)
    c43 = render_4x3(hero)
    c16.save(COVER_16X9, format="JPEG", quality=94, optimize=True)
    c43.save(COVER_4X3, format="JPEG", quality=94, optimize=True)
    print(
        json.dumps(
            {
                "cover_16x9": str(COVER_16X9),
                "metrics_16x9": _brightness_metrics(c16),
                "cover_4x3": str(COVER_4X3),
                "metrics_4x3": _brightness_metrics(c43),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
