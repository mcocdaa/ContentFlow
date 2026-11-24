#!/usr/bin/env python3
"""Compose Episode 023 high-CTR Bilibili AI Product / Red-Alert HUD cover (16:9 + 4:3).

Strictly rejects old double-pill / 3-line yellow-white-cyan template.
Uses dramatic red-alert HUD framing + concise 7-char pain-point phrase ('切屏3秒 / 全屏警报')
positioned cleanly in the left safe-zone so the panicked geek, glowing monitor, and thermal
receipt printer remain completely unobstructed.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageStat

PROJ_DIR = Path(__file__).resolve().parent.parent
RAW_HERO = PROJ_DIR / "assets" / "kling_cover_hero_raw.png"
OUT_16X9 = PROJ_DIR / "delivery" / "AI整活工具_毒舌AI监工防摸鱼_cover.jpg"
OUT_4X3 = PROJ_DIR / "delivery" / "AI整活工具_毒舌AI监工防摸鱼_cover_4x3.jpg"
BRAIN_COPY = Path("/home/mcocdaa/.gemini/antigravity-cli/brain/d89cb67e-4fab-42d5-b0b5-fc891f1b66db/ep023_cover.jpg")

FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"


def load_font(size: int) -> ImageFont.FreeTypeFont:
    # index=2 is Noto Sans CJK SC Bold
    return ImageFont.truetype(FONT_BOLD, size=size, index=2)


def draw_rounded_box(
    overlay: Image.Image,
    xy: tuple[int, int, int, int],
    radius: int,
    fill: tuple[int, int, int, int],
    outline: tuple[int, int, int, int] | None = None,
    width: int = 3,
) -> None:
    d = ImageDraw.Draw(overlay)
    d.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def build_cover() -> None:
    assert RAW_HERO.exists(), f"Missing Kling raw hero: {RAW_HERO}"
    with Image.open(RAW_HERO) as src:
        base = src.convert("RGB").resize((1920, 1080), Image.Resampling.LANCZOS)

    # Gently lift deep shadows + punch saturation/sharpness for vivid mobile thumbnail pop
    arr = np.asarray(base, dtype=np.float32)
    # Soft shadow floor lift to keep rich indigo-cobalt instead of crushed black
    arr = np.clip(arr * 0.94 + 16.0, 0, 255)
    base = Image.fromarray(arr.astype(np.uint8), mode="RGB")
    base = ImageEnhance.Color(base).enhance(1.12)
    base = ImageEnhance.Contrast(base).enhance(1.06)
    base = ImageEnhance.Sharpness(base).enhance(1.18)

    canvas = base.convert("RGBA")

    # Subtle radial red-alert glow along top-left & left HUD zone (non-black!)
    glow = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([120, -80, 1080, 520], fill=(220, 24, 68, 52))
    gd.ellipse([140, 760, 960, 1180], fill=(0, 190, 255, 42))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=42))
    canvas = Image.alpha_composite(canvas, glow)

    overlay = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # 1. Subtle 4:3 Safe-Zone Red-Alert Viewfinder Corner Brackets (x: 256..1664, y: 28..1052)
    bx0, by0, bx1, by1 = 258, 28, 1662, 1052
    clen = 42
    ccol = (255, 58, 92, 220)
    for (x, y, dx, dy) in [
        (bx0, by0, clen, clen),
        (bx1, by0, -clen, clen),
        (bx0, by1, clen, -clen),
        (bx1, by1, -clen, -clen),
    ]:
        draw.line([(x, y), (x + dx, y)], fill=ccol, width=6)
        draw.line([(x, y), (x, y + dy)], fill=ccol, width=6)

    # 2. Top-Left Red-Alert Product HUD Plate (x: 266..916, y: 42..440) — cleanly encloses all 3 rows!
    px0, py0, px1, py1 = 266, 42, 916, 440
    draw_rounded_box(
        overlay,
        (px0, py0, px1, py1),
        radius=22,
        fill=(18, 24, 48, 224),
        outline=(255, 52, 88, 240),
        width=5,
    )
    # Left glowing crimson vertical accent bar inside plate
    draw.rounded_rectangle([px0 + 16, py0 + 18, px0 + 30, py1 - 18], radius=7, fill=(255, 42, 85, 255))

    # Live status header strip inside plate
    f_eyebrow = load_font(30)
    draw.ellipse([px0 + 50, py0 + 25, px0 + 70, py0 + 45], fill=(255, 54, 88, 255))
    draw.text(
        (px0 + 82, py0 + 15),
        "RED ALERT  ·  失焦 00:03.0",
        font=f_eyebrow,
        fill=(255, 198, 102, 255),
    )

    # Line 1: Massive ultra-clean white "切屏3秒"
    f_big1 = load_font(124)
    t1 = "切屏3秒"
    tx1, ty1 = px0 + 48, py0 + 56
    draw.text(
        (tx1, ty1),
        t1,
        font=f_big1,
        fill=(255, 255, 255, 255),
        stroke_width=10,
        stroke_fill=(20, 14, 42, 255),
    )

    # Line 2: High-impact crimson hazard block cleanly inside plate with ultra-crisp yellow-white "全屏警报"
    band_y0, band_y1 = py0 + 206, py0 + 346
    draw.rounded_rectangle(
        [px0 + 46, band_y0, px1 - 24, band_y1],
        radius=16,
        fill=(235, 26, 66, 255),
        outline=(255, 224, 102, 245),
        width=5,
    )
    f_big2 = load_font(118)
    t2 = "全屏警报"
    bbox2 = draw.textbbox((0, 0), t2, font=f_big2)
    tw2 = bbox2[2] - bbox2[0]
    th2 = bbox2[3] - bbox2[1]
    bx_mid = (px0 + 46 + px1 - 24) // 2
    by_mid = (band_y0 + band_y1) // 2
    draw.text(
        (bx_mid - tw2 // 2, by_mid - th2 // 2 - 14),
        t2,
        font=f_big2,
        fill=(255, 248, 178, 255),
        stroke_width=9,
        stroke_fill=(58, 10, 24, 255),
    )

    # Crisp footer telemetry line cleanly INSIDE the dark plate (y = py0 + 356..390 < py1=440)
    draw.text(
        (px0 + 50, py0 + 356),
        "Lv.1 提醒  ▶  Lv.2 弹幕  ▶  Lv.3 锁屏",
        font=load_font(27),
        fill=(158, 238, 255, 255),
        stroke_width=2,
        stroke_fill=(14, 20, 38, 255),
    )

    # 3. Bottom-Left Compact Product Telemetry Strip (x: 266..865, y: 924..1028) — clean below monitor, clears printer!
    bx_a, by_a, bx_b, by_b = 266, 924, 868, 1026
    draw_rounded_box(
        overlay,
        (bx_a, by_a, bx_b, by_b),
        radius=18,
        fill=(16, 26, 52, 222),
        outline=(0, 229, 255, 230),
        width=3,
    )
    draw.rounded_rectangle([bx_a + 14, by_a + 16, bx_a + 24, by_b - 16], radius=5, fill=(0, 229, 255, 255))
    f_sub = load_font(38)
    draw.text(
        (bx_a + 42, by_a + 24),
        "纯Python开源 · 摸鱼罪证小票",
        font=f_sub,
        fill=(236, 248, 255, 255),
        stroke_width=3,
        stroke_fill=(14, 22, 42, 255),
    )

    # 4. Small top-right floating alert stamp inside 4:3 safe zone (x: 1368..1648, y: 48..112)
    rx0, ry0, rx1, ry1 = 1358, 48, 1648, 112
    draw_rounded_box(
        overlay,
        (rx0, ry0, rx1, ry1),
        radius=14,
        fill=(22, 28, 56, 215),
        outline=(255, 212, 82, 230),
        width=3,
    )
    f_tag = load_font(34)
    draw.text(
        (rx0 + 24, ry0 + 11),
        "赛博功德 -99",
        font=f_tag,
        fill=(255, 224, 102, 255),
        stroke_width=3,
        stroke_fill=(26, 16, 38, 255),
    )

    final_rgb = Image.alpha_composite(canvas, overlay).convert("RGB")
    OUT_16X9.parent.mkdir(parents=True, exist_ok=True)
    final_rgb.save(OUT_16X9, format="JPEG", quality=95, subsampling=0)

    # 4:3 center safe crop (1440x1080)
    crop_4x3 = final_rgb.crop((240, 0, 1680, 1080))
    crop_4x3.save(OUT_4X3, format="JPEG", quality=95, subsampling=0)

    BRAIN_COPY.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(OUT_16X9, BRAIN_COPY)

    # Objective Cover Quality Self-Audit
    w, h = final_rgb.size
    safe_crop = final_rgb.crop((int(w * 0.125), 0, int(w * 0.875), h))
    left_typo = final_rgb.crop((int(w * 0.125), int(h * 0.08), int(w * 0.53), int(h * 0.88)))
    safe_edge = ImageStat.Stat(safe_crop.convert("L").filter(ImageFilter.FIND_EDGES)).mean[0]
    left_edge = ImageStat.Stat(left_typo.convert("L").filter(ImageFilter.FIND_EDGES)).mean[0]
    safe_luma_std = ImageStat.Stat(safe_crop.convert("L")).stddev[0]
    left_luma_std = ImageStat.Stat(left_typo.convert("L")).stddev[0]
    mid_torso = np.array(final_rgb.crop((int(w * 0.30), int(h * 0.50), int(w * 0.58), int(h * 0.85))))
    black_torso = float(np.mean(np.all(mid_torso < 10, axis=-1)))
    rgb_arr = np.array(final_rgb)
    dark_ratio = float(np.mean(np.max(rgb_arr, axis=-1) < 45))
    hsv_v_mean = float(np.mean(np.max(rgb_arr, axis=-1)))

    print(f"Saved 16:9 cover: {OUT_16X9} ({w}x{h})")
    print(f"Saved 4:3  cover: {OUT_4X3} ({crop_4x3.size})")
    print(f"Copied to brain : {BRAIN_COPY}")
    print(
        f"Metrics -> safe_edge={safe_edge:.2f}, left_edge={left_edge:.2f}, "
        f"safe_luma_std={safe_luma_std:.2f}, left_luma_std={left_luma_std:.2f}, "
        f"black_torso={black_torso:.4f}, dark_ratio={dark_ratio:.3f}, hsv_v_mean={hsv_v_mean:.1f}"
    )


if __name__ == "__main__":
    build_cover()
