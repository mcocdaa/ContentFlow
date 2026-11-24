#!/usr/bin/env python3
"""Minimalist Neo-Noir Intelligence-Thriller Cover Composer for Episode 021.

Builds both 16:9 (1920x1080) and 4:3 safe-crop (1440x1080) posters from the
Kling 3.0 Omni 2K key visual with zero pill capsules, zero variety-show clutter,
high-contrast intelligence-dossier typography + minimalist 5-node betrayal schematic
on the left, leaving the right-side vault table and strategists unobstructed.
"""

from __future__ import annotations

import math
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageStat

PROJECT_DIR = Path(__file__).resolve().parent.parent
BASE_IMG = PROJECT_DIR / "assets" / "cover_noir_base_16x9.png"
OUT_16X9 = PROJECT_DIR / "delivery" / "AI博弈实验_5个AI密室分1000万_cover.jpg"
OUT_4X3 = PROJECT_DIR / "delivery" / "AI博弈实验_5个AI密室分1000万_cover_4x3.jpg"
BRAIN_COPY = Path("/home/mcocdaa/.gemini/antigravity-cli/brain/06163c88-6b15-4b1d-b169-dab62ec7a80f/ep021_cover.jpg")

FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
FONT_REG = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"


def load_font(path: str, size: int, index: int = 2) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size, index=index)


def draw_crisp_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
    stroke_width: int = 6,
    stroke_fill: tuple[int, int, int] = (12, 18, 30),
    shadow_offset: tuple[int, int] = (4, 6),
) -> int:
    x, y = xy
    if shadow_offset != (0, 0):
        draw.text(
            (x + shadow_offset[0], y + shadow_offset[1]),
            text,
            font=font,
            fill=(11, 17, 29),
            stroke_width=stroke_width,
            stroke_fill=(11, 17, 29),
        )
    draw.text(
        (x, y),
        text,
        font=font,
        fill=fill,
        stroke_width=stroke_width,
        stroke_fill=stroke_fill,
    )
    bbox = draw.textbbox((x, y), text, font=font, stroke_width=stroke_width)
    return int(bbox[2] - x)


def build_covers() -> None:
    if not BASE_IMG.exists():
        raise FileNotFoundError(f"Missing Kling base cover artwork: {BASE_IMG}")

    src = Image.open(BASE_IMG).convert("RGB")
    # Frame so gold pyramid & strategists sit cleanly in right half of 4:3 safe zone (x: 240..1680)
    # while keeping left zone (x: 240..985) clear of strategist heads.
    target_w, target_h = 1920, 1080
    scale_w, scale_h = 2120, 1192
    resized = src.resize((scale_w, scale_h), Image.Resampling.LANCZOS)
    crop_x = 175
    crop_y = 50
    canvas = resized.crop((crop_x, crop_y, crop_x + target_w, crop_y + target_h))

    canvas = ImageEnhance.Contrast(canvas).enhance(1.12)
    canvas = ImageEnhance.Color(canvas).enhance(1.15)
    arr = np.asarray(canvas, dtype=np.float32)

    # Lift dark floor so zero pure-black (<10) dead pools exist anywhere
    floor_rgb = np.array([13.0, 22.0, 38.0], dtype=np.float32)
    arr = np.maximum(arr, floor_rgb)

    # Refined editorial left wash for legibility
    xs = np.linspace(0.0, 1.0, target_w, dtype=np.float32)[None, :, None]
    ys = np.linspace(0.0, 1.0, target_h, dtype=np.float32)[:, None, None]
    left_mask = np.clip((0.54 - xs) / 0.54, 0.0, 1.0) ** 1.35
    wash_color = np.array([14.0, 24.0, 42.0], dtype=np.float32)
    arr = arr * (1.0 - 0.55 * left_mask) + wash_color * (0.55 * left_mask)

    edge_y = np.clip((np.abs(ys - 0.5) - 0.35) / 0.15, 0.0, 1.0)
    arr = arr * (1.0 - 0.20 * edge_y) + np.array([14.0, 23.0, 40.0], dtype=np.float32) * (0.20 * edge_y)

    base = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="RGB").convert("RGBA")

    # Crisp intelligence-dossier graphics on overlay (ZERO pill capsules)
    overlay = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)

    # Subtle architectural tactical grid lines on left poster column
    for gx in range(256, 980, 72):
        od.line([(gx, 80), (gx, 960)], fill=(120, 200, 245, 22), width=1)
    for gy in range(88, 960, 72):
        od.line([(256, gy), (980, gy)], fill=(120, 200, 245, 22), width=1)

    # Left vertical crimson dossier bar beside hero title (ends cleanly at y=436, well above heads)
    od.rectangle([(256, 96), (266, 434)], fill=(255, 59, 78, 245))
    # Crisp gold editorial rule below hero title
    od.line([(256, 458), (948, 458)], fill=(255, 213, 79, 205), width=2)
    od.rectangle([(256, 454), (376, 462)], fill=(255, 213, 79, 255))

    # Minimalist CIA/War-Room Intelligence Dossier Card in lower-left (x: 256..930, y: 562..940)
    # Sharp rectilinear military/dossier corners (NOT pill capsules!)
    bx0, by0, bx1, by1 = 256, 566, 916, 938
    od.rectangle([(bx0, by0), (bx1, by1)], fill=(15, 26, 46, 185), outline=(88, 178, 228, 165), width=2)
    # Corner L-brackets
    clen = 22
    for cx, cy, dx, dy in [
        (bx0, by0, 1, 1),
        (bx1, by0, -1, 1),
        (bx0, by1, 1, -1),
        (bx1, by1, -1, -1),
    ]:
        od.line([(cx, cy), (cx + dx * clen, cy)], fill=(255, 213, 79, 255), width=4)
        od.line([(cx, cy), (cx, cy + dy * clen)], fill=(255, 213, 79, 255), width=4)

    # Left sub-panel inside dossier: 5-node pentagon betrayal network schematic (x: 280..540, y: 625..905)
    pcx, pcy, prad = 412, 768, 102
    nodes = []
    labels = [("A", "狐"), ("B", "鸽"), ("C", "蛇"), ("D", "猫"), ("E", "鹰")]
    for i in range(5):
        ang = -math.pi / 2 + i * (2 * math.pi / 5)
        nx = int(pcx + prad * math.cos(ang))
        ny = int(pcy + prad * math.sin(ang))
        nodes.append((nx, ny))

    # Draw subtle emerald alliance edges + sharp crimson betrayal diagonals
    for i, j in [(0, 1), (1, 2), (2, 3), (3, 4), (4, 0)]:
        od.line([nodes[i], nodes[j]], fill=(46, 232, 165, 190), width=3)
    for i, j in [(0, 2), (1, 3), (2, 4), (0, 3)]:
        od.line([nodes[i], nodes[j]], fill=(255, 62, 82, 235), width=3)

    # Center crosshair inside pentagon
    od.ellipse([(pcx - 16, pcy - 16), (pcx + 16, pcy + 16)], outline=(255, 213, 79, 210), width=2)

    # Vertical divider inside dossier box
    od.line([(556, 616), (556, 916)], fill=(88, 178, 228, 130), width=2)

    # Header rule inside dossier box
    od.line([(bx0 + 16, by0 + 46), (bx1 - 16, by0 + 46)], fill=(88, 178, 228, 120), width=1)

    # Right-side subtle radar ring around the glowing gold bullion
    gx_c, gy_c = 1485, 580
    od.ellipse([(gx_c - 170, gy_c - 170), (gx_c + 170, gy_c + 170)], outline=(0, 229, 255, 65), width=2)
    od.ellipse([(gx_c - 218, gy_c - 218), (gx_c + 218, gy_c + 218)], outline=(255, 59, 78, 50), width=1)

    base = Image.alpha_composite(base, overlay).convert("RGB")
    draw = ImageDraw.Draw(base)

    # Load crisp Noto Sans CJK fonts
    f_kicker = load_font(FONT_BOLD, 30)
    f_hero_big = load_font(FONT_BOLD, 122)
    f_hero_sub = load_font(FONT_BOLD, 96)
    f_subline = load_font(FONT_BOLD, 35)
    f_box_hdr = load_font(FONT_BOLD, 25)
    f_node = load_font(FONT_BOLD, 24)
    f_stat_lbl = load_font(FONT_BOLD, 26)
    f_stat_val = load_font(FONT_BOLD, 34)
    f_stat_sm = load_font(FONT_REG, 24)

    # Top kicker line
    draw_crisp_text(
        draw,
        (286, 94),
        "FILE 021 // 真实 5-AI 隔离生存博弈实录",
        f_kicker,
        fill=(152, 230, 255),
        stroke_width=3,
        shadow_offset=(2, 3),
    )

    # Hero Line 1: "5个AI分" + "1000万" (stays cleanly left of x=975)
    y1 = 144
    w1 = draw_crisp_text(
        draw,
        (282, y1),
        "5个AI分",
        f_hero_big,
        fill=(250, 252, 255),
        stroke_width=8,
        shadow_offset=(5, 7),
    )
    draw_crisp_text(
        draw,
        (282 + w1 - 6, y1),
        "1000万",
        f_hero_big,
        fill=(255, 214, 62),
        stroke_width=8,
        shadow_offset=(5, 7),
    )

    # Hero Line 2: "当面喊哥" + "背后捅刀" (ends at x ~ 965, cleanly clear of leftmost strategist head!)
    y2 = 298
    w2 = draw_crisp_text(
        draw,
        (284, y2),
        "当面喊哥",
        f_hero_sub,
        fill=(246, 250, 255),
        stroke_width=8,
        shadow_offset=(5, 7),
    )
    draw_crisp_text(
        draw,
        (284 + w2 + 10, y2),
        "背后捅刀",
        f_hero_sub,
        fill=(255, 62, 82),
        stroke_width=8,
        shadow_offset=(5, 7),
    )

    # Subline below editorial gold rule
    draw_crisp_text(
        draw,
        (258, 478),
        "零预设剧本 · 独立加密私聊 · 终极囚徒困境",
        f_subline,
        fill=(238, 220, 168),
        stroke_width=4,
        shadow_offset=(2, 3),
    )

    # Dossier box header
    draw_crisp_text(
        draw,
        (bx0 + 20, by0 + 10),
        "TACTICAL MATRIX // 5人隔离密室 · 4轮淘汰实测",
        f_box_hdr,
        fill=(158, 228, 255),
        stroke_width=2,
        shadow_offset=(0, 0),
    )

    # Draw 5 pentagon agent nodes on top of edges
    node_colors = [
        (56, 189, 248),  # A 理性狐
        (52, 211, 153),  # B 微笑鸽
        (251, 113, 133),  # C 暗影蛇
        (250, 204, 21),  # D 混沌猫
        (192, 132, 252),  # E 铁面鹰
    ]
    for (nx, ny), (ltr, cn), col in zip(nodes, labels, node_colors):
        r = 25
        draw.ellipse([(nx - r, ny - r), (nx + r, ny + r)], fill=(18, 30, 52), outline=col, width=4)
        txt = f"{ltr}{cn}"
        tb = draw.textbbox((0, 0), txt, font=f_node)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        draw.text((nx - tw // 2, ny - th // 2 - 4), txt, font=f_node, fill=(248, 251, 255))

    # Right sub-panel inside dossier: crisp high-contrast payoff & betrayal readout
    rx = 580
    draw_crisp_text(draw, (rx, 630), "表里反差指数", f_stat_lbl, fill=(176, 212, 236), stroke_width=2, shadow_offset=(0, 0))
    draw_crisp_text(draw, (rx, 664), "HIGH ALERT // 极高", f_stat_val, fill=(255, 76, 94), stroke_width=3, shadow_offset=(0, 0))

    draw.line([(rx, 718), (bx1 - 24, 718)], fill=(88, 178, 228, 120), width=1)
    draw_crisp_text(draw, (rx, 732), "终极 2 强奖金规则", f_stat_lbl, fill=(176, 212, 236), stroke_width=2, shadow_offset=(0, 0))
    draw_crisp_text(draw, (rx, 770), "双平分: 各拿 500 万", f_stat_sm, fill=(68, 236, 174), stroke_width=2, shadow_offset=(0, 0))
    draw_crisp_text(draw, (rx, 808), "一背刺: 独吞 1000 万", f_stat_sm, fill=(255, 214, 66), stroke_width=2, shadow_offset=(0, 0))
    draw_crisp_text(draw, (rx, 846), "双独吞: 奖金全清零", f_stat_sm, fill=(255, 92, 108), stroke_width=2, shadow_offset=(0, 0))

    draw_crisp_text(
        draw,
        (rx, 892),
        "ISOLATED NEON AGENTS × 5",
        load_font(FONT_BOLD, 21),
        fill=(128, 216, 255),
        stroke_width=2,
        shadow_offset=(0, 0),
    )

    OUT_16X9.parent.mkdir(parents=True, exist_ok=True)
    base.save(OUT_16X9, format="JPEG", quality=95, subsampling=0)

    # 4:3 Center Safe Crop (1440x1080 from x: 240..1680)
    crop_4x3 = base.crop((240, 0, 1680, 1080))
    crop_4x3.save(OUT_4X3, format="JPEG", quality=95, subsampling=0)

    # Copy to worker brain for Screenshot presentation
    BRAIN_COPY.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(OUT_16X9, BRAIN_COPY)

    w, h = base.size
    safe_x0, safe_x1 = int(w * 0.125), int(w * 0.875)
    safe_crop = base.crop((safe_x0, 0, safe_x1, h))
    left_typo = base.crop((safe_x0, int(h * 0.08), int(w * 0.53), int(h * 0.88)))
    edge_safe = ImageStat.Stat(safe_crop.convert("L").filter(ImageFilter.FIND_EDGES)).mean[0]
    edge_left = ImageStat.Stat(left_typo.convert("L").filter(ImageFilter.FIND_EDGES)).mean[0]
    std_safe = ImageStat.Stat(safe_crop.convert("L")).stddev[0]
    std_left = ImageStat.Stat(left_typo.convert("L")).stddev[0]
    mid_torso = np.array(base.crop((int(w * 0.30), int(h * 0.50), int(w * 0.58), int(h * 0.85))))
    black_torso = float(np.mean(np.all(mid_torso < 10, axis=-1)))
    print(
        f"Saved 16:9={OUT_16X9.name} ({w}x{h}) & 4:3={OUT_4X3.name} ({crop_4x3.size})\n"
        f"  edge_safe={edge_safe:.2f}, edge_left={edge_left:.2f} (need >=15.0)\n"
        f"  std_safe={std_safe:.2f}, std_left={std_left:.2f} (need >=58.0)\n"
        f"  black_stroke_torso={black_torso:.4f} (need <=0.16)"
    )


if __name__ == "__main__":
    build_covers()
