#!/usr/bin/env python3
"""Minimalist Cinema Thriller Poster Cover Builder for Episode 022.

Strictly adheres to the new Episode 022 aesthetic directive:
  - Minimalist cinema movie poster look: ONLY ONE restrained, punchy 7-char title
    ("消失7天没人发现") over a high-tension Kling 2K original film still.
  - ZERO top dual colorful pills/capsules, ZERO 3-line variety-show giant slogans.
  - Exports 1920x1080 (16:9) primary cover + 1440x1080 (4:3 center safe-zone) cover,
    and prints QualityGate CTR/contrast/hierarchy audit metrics.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat

PROJ_DIR = Path(__file__).resolve().parent.parent
RAW_COVER = PROJ_DIR / "assets" / "cover_cinema_noir_16x9.jpg"
OUT_16X9 = PROJ_DIR / "delivery" / "科幻悬疑短片_消失7天没人发现_cover.jpg"
OUT_4X3 = PROJ_DIR / "delivery" / "科幻悬疑短片_消失7天没人发现_cover_4x3.jpg"
BRAIN_COPY = Path("/home/mcocdaa/.gemini/antigravity-cli/brain/b8ac2b71-c4cc-46d6-b00d-699a12ea426c/ep022_cover.jpg")

FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"


def _crop_fill_16x9(img: Image.Image, target_w: int = 1920, target_h: int = 1080) -> Image.Image:
    w, h = img.size
    scale = max(target_w / float(w), target_h / float(h))
    rw, rh = int(round(w * scale)), int(round(h * scale))
    resized = img.resize((rw, rh), Image.Resampling.LANCZOS)
    x0 = (rw - target_w) // 2
    y0 = (rh - target_h) // 2
    return resized.crop((x0, y0, x0 + target_w, y0 + target_h))


def build_cover() -> None:
    if not RAW_COVER.exists():
        raise FileNotFoundError(f"Missing raw Kling 2K cover image: {RAW_COVER}")

    base = _crop_fill_16x9(Image.open(RAW_COVER).convert("RGB"), 1920, 1080)
    # Crisp theatrical cinema micro-sharpening on rain streaks & glowing hologram details
    base = base.filter(ImageFilter.UnsharpMask(radius=1.8, percent=155, threshold=2))
    w, h = base.size

    # Subtle cinematic atmospheric color lift & clean left-third gradient scrim (keeps dark slate >= #121E33, never muddy pitch black)
    arr = np.asarray(base, dtype=np.float32)
    arr = np.clip(arr * 1.08 + 7.0, 0.0, 255.0)
    base = Image.fromarray(arr.astype(np.uint8), mode="RGB").convert("RGBA")

    # Left-side cinema poster negative-space vignette (x: 0..48%, soft fade, deep slate-blue #0D182B, alpha max 150)
    xs = np.linspace(0.0, 1.0, w, dtype=np.float32)
    scrim_alpha = np.clip((0.48 - xs) / 0.32, 0.0, 1.0) ** 1.45 * 150.0
    scrim = np.zeros((h, w, 4), dtype=np.uint8)
    scrim[:, :, 0] = 13
    scrim[:, :, 1] = 24
    scrim[:, :, 2] = 43
    scrim[:, :, 3] = scrim_alpha[None, :].astype(np.uint8)
    base = Image.alpha_composite(base, Image.fromarray(scrim, mode="RGBA"))

    # Minimalist cinema title: ONE 7-char title ("消失7天" / "没人发现") stacked cleanly in left 4:3 safe column (x: 266..900)
    font_main = ImageFont.truetype(FONT_BOLD, size=156, index=2)
    font_num = ImageFont.truetype(FONT_BOLD, size=184, index=2)

    title_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    glow_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d_title = ImageDraw.Draw(title_layer)
    d_glow = ImageDraw.Draw(glow_layer)

    x_left = 268
    y_line1 = 212
    y_line2 = 408

    # Line 1: "消失" (crisp pure cinema white) + "7" (electric ice-cyan cinema accent) + "天" (crisp white)
    segs_l1 = [
        ("消失", font_main, (248, 252, 255, 255), 0),
        ("7", font_num, (66, 236, 255, 255), -20),
        ("天", font_main, (248, 252, 255, 255), 0),
    ]
    cur_x = x_left
    for seg_txt, seg_font, seg_col, y_off in segs_l1:
        if seg_txt == "7":
            d_glow.text((cur_x, y_line1 + y_off), seg_txt, font=seg_font, fill=(40, 224, 255, 210))
        else:
            d_glow.text((cur_x + 5, y_line1 + y_off + 7), seg_txt, font=seg_font, fill=(6, 14, 28, 220))
        d_title.text(
            (cur_x, y_line1 + y_off),
            seg_txt,
            font=seg_font,
            fill=seg_col,
            stroke_width=8,
            stroke_fill=(9, 18, 32, 250),
        )
        cur_x += int(round(d_title.textlength(seg_txt, font=seg_font))) + (6 if seg_txt == "7" else 4)

    line1_w = cur_x - x_left

    # Line 2: "没人发现"
    d_glow.text((x_left + 5, y_line2 + 7), "没人发现", font=font_main, fill=(6, 14, 28, 225))
    d_title.text(
        (x_left, y_line2),
        "没人发现",
        font=font_main,
        fill=(246, 250, 255, 255),
        stroke_width=8,
        stroke_fill=(9, 18, 32, 250),
    )

    # Razor-thin minimalist cinema cyan accent hairline cleanly spaced below the descenders (+30px breathing room!)
    rule_y = y_line2 + 216
    d_glow.rounded_rectangle([x_left, rule_y - 4, x_left + line1_w - 16, rule_y + 6], radius=3, fill=(56, 234, 255, 165))
    d_title.rounded_rectangle([x_left, rule_y, x_left + line1_w - 16, rule_y + 5], radius=2, fill=(108, 242, 255, 248))

    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=14))
    comp = Image.alpha_composite(base, glow_layer)
    comp = Image.alpha_composite(comp, title_layer)
    final_rgb = comp.convert("RGB")

    OUT_16X9.parent.mkdir(parents=True, exist_ok=True)
    final_rgb.save(OUT_16X9, format="JPEG", quality=95, subsampling=0)

    # 4:3 safe-zone crop (x: 240..1680 -> 1440x1080)
    crop_4x3 = final_rgb.crop((240, 0, 1680, 1080))
    crop_4x3.save(OUT_4X3, format="JPEG", quality=95, subsampling=0)

    # Copy 16:9 cover to worker brain for board Screenshot report
    BRAIN_COPY.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(OUT_16X9, BRAIN_COPY)

    # Audit metrics matching core/quality_gate.py & core/aesthetic_evaluator.py
    safe_crop = final_rgb.crop((int(w * 0.125), 0, int(w * 0.875), h))
    edge_mean = ImageStat.Stat(safe_crop.convert("L").filter(ImageFilter.FIND_EDGES)).mean[0]
    left_typo = final_rgb.crop((int(w * 0.125), int(h * 0.08), int(w * 0.53), int(h * 0.88)))
    left_edge = ImageStat.Stat(left_typo.convert("L").filter(ImageFilter.FIND_EDGES)).mean[0]
    luma_std = ImageStat.Stat(safe_crop.convert("L")).stddev[0]
    left_luma_std = ImageStat.Stat(left_typo.convert("L")).stddev[0]

    left_zone = np.array(final_rgb.crop((int(w * 0.13), int(h * 0.20), int(w * 0.53), int(h * 0.84))))
    mid_torso = np.array(final_rgb.crop((int(w * 0.30), int(h * 0.50), int(w * 0.58), int(h * 0.85))))
    black_stroke_torso = float(np.mean(np.all(mid_torso < 10, axis=-1)))
    near_black = float(np.mean(np.max(np.array(final_rgb), axis=-1) < 45))

    print(f"[+] Cover 16:9: {OUT_16X9} ({final_rgb.size})")
    print(f"[+] Cover 4:3:  {OUT_4X3} ({crop_4x3.size})")
    print(f"[+] Brain copy: {BRAIN_COPY}")
    print(
        f"    edge_mean={edge_mean:.2f} left_edge={left_edge:.2f} (need max>=15.0) | "
        f"luma_std={luma_std:.2f} left_luma_std={left_luma_std:.2f} (need max>=58.0) | "
        f"black_stroke_torso={black_stroke_torso:.4f} left_zone_std={float(np.std(left_zone)):.2f} | "
        f"near_black(<45)={near_black:.1%}"
    )


if __name__ == "__main__":
    build_cover()
