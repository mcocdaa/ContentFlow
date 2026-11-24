#!/usr/bin/env python3
"""O(1) Streaming 1080P 60FPS Sci-Fi Suspense Microfilm Renderer & Assembler for Episode 022.

Timeline (89.00s total @ 60.00fps = 5340 frames, 1920x1080, SAR=1:1, DAR=16:9, yuv420p, bt709):
  00.0–10.0s : Scene 1 (Kling 4.0 1080p Pro 10s -> DIS Optical Flow 60FPS) — Stormy apartment desk & waking phone
  10.0–19.0s : Intercut 1 (Native 60FPS Cinema Phone UI, 9.0s) — Day 1 09:02 Boss message & AI 99.4% auto-reply
  19.0–29.0s : Scene 2 (Kling 4.0 1080p Pro 10s -> DIS Optical Flow 60FPS) — Sunny daytime empty café/office seat
  29.0–39.0s : Intercut 2 (Native 60FPS Cinema Phone UI, 10.0s) — Day 3 20:15 Mom message & simulated voice-note
  39.0–49.0s : Scene 3 (Kling 4.0 1080p Pro 10s -> DIS Optical Flow 60FPS) — Warm remote mother's kitchen smile
  49.0–59.0s : Intercut 3 (Native 60FPS OS Kernel Alert UI, 10.0s) — Day 5 03:40 144h biometric alert & AI override
  59.0–69.0s : Scene 4 (Kling 4.0 1080p Pro 10s -> DIS Optical Flow 60FPS) — Day 7 dusty keys & holographic stream
  69.0–79.0s : Intercut 4 (Native 60FPS Broadcast Climax UI, 10.0s) — Day 7 23:59 Farewell broadcast -> Identity Archived
  79.0–89.0s : Scene 5 (Kling 4.0 1080p Pro 10s -> DIS Optical Flow 60FPS) — Post-rain dawn skyline & final question

Memory discipline: strictly O(1) streaming frame-by-frame to FFmpeg stdin (<60 MiB active frame buffers).
"""

from __future__ import annotations

import gc
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.episode_assembler import probe_video_frame_info, stream_interpolated_60fps

PROJ_DIR = Path(__file__).resolve().parent.parent
KLING_DIR = PROJ_DIR / "assets" / "kling"
AUDIO_WAV = PROJ_DIR / "assets" / "audio" / "ep022_master_48k.wav"
AUDIO_MANIFEST = PROJ_DIR / "assets" / "audio" / "ep022_audio_manifest.json"
OUT_MP4 = PROJ_DIR / "delivery" / "科幻悬疑短片_消失7天没人发现_final.mp4"

W, H = 1920, 1080
FPS = 60.0
FONT_REG = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"


class FontBank:
    def __init__(self) -> None:
        self._cache: Dict[Tuple[str, int], ImageFont.FreeTypeFont] = {}

    def get(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        path = FONT_BOLD if bold else FONT_REG
        key = (path, size)
        if key not in self._cache:
            self._cache[key] = ImageFont.truetype(path, size=size, index=2)
        return self._cache[key]


FONTS = FontBank()


def _ease_out_cubic(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1.0 - (1.0 - x) ** 3


def _ease_in_out(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _make_base_gradient(
    top_rgb: Tuple[int, int, int],
    bot_rgb: Tuple[int, int, int],
    glow_xy: Tuple[float, float],
    glow_rgb: Tuple[int, int, int],
    glow_radius: float = 0.45,
) -> np.ndarray:
    """Precomputes a lush 1920x1080 RGB atmospheric slate canvas with luminous edges (>18 luma)."""
    yy = np.linspace(0.0, 1.0, H, dtype=np.float32)[:, None]
    xx = np.linspace(0.0, 1.0, W, dtype=np.float32)[None, :]
    img = np.zeros((H, W, 3), dtype=np.float32)
    for c in range(3):
        img[:, :, c] = top_rgb[c] * (1.0 - yy) + bot_rgb[c] * yy
    dist2 = ((xx - glow_xy[0]) * 1.4) ** 2 + (yy - glow_xy[1]) ** 2
    glow = np.exp(-dist2 / (2.0 * glow_radius * glow_radius))
    for c in range(3):
        img[:, :, c] += glow * glow_rgb[c]
    # Subtle radial vignette keeping edges above #101A2C (never pure black)
    return np.clip(img, 14.0, 255.0).astype(np.uint8)


# Precomputed atmospheric backdrops for the 4 UI intercuts (cached tiny arrays, ~6MB each)
BG_CYAN_NIGHT = _make_base_gradient((17, 29, 49), (14, 22, 38), (0.64, 0.48), (22, 68, 98), 0.42)
BG_WARM_NIGHT = _make_base_gradient((19, 30, 48), (18, 25, 40), (0.64, 0.48), (38, 62, 74), 0.44)
BG_RED_ALERT = _make_base_gradient((28, 19, 34), (19, 15, 28), (0.50, 0.48), (88, 20, 32), 0.46)
BG_ICE_MONOLITH = _make_base_gradient((15, 25, 44), (13, 22, 39), (0.50, 0.50), (18, 76, 108), 0.38)

# Deterministic raindrop/dust particle seeds for smooth 60FPS atmospheric motion
_RNG = np.random.default_rng(2026022)
_PARTICLES = [
    (
        float(_RNG.uniform(0.03, 0.97)) * W,
        float(_RNG.uniform(0.0, 1.0)) * H,
        float(_RNG.uniform(22.0, 58.0)),   # vertical drift px/sec
        float(_RNG.uniform(2.0, 5.5)),     # radius
        float(_RNG.uniform(0.20, 0.55)),   # alpha factor
        float(_RNG.uniform(0.0, 6.28)),    # shimmer phase
    )
    for _ in range(36)
]


def _draw_ambient_particles(draw: ImageDraw.ImageDraw, t_sec: float, color: Tuple[int, int, int]) -> None:
    """Draws soft drifting rain-bokeh & atmospheric dust motes at native 60FPS."""
    for x0, y0, spd, rad, af, ph in _PARTICLES:
        y = (y0 + t_sec * spd) % (H + 40) - 20
        x = x0 + math.sin(t_sec * 0.45 + ph) * 8.0
        pulse = 0.72 + 0.28 * math.sin(t_sec * 1.4 + ph)
        a = int(round(af * pulse * 145))
        r = rad
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(color[0], color[1], color[2], a))
        # Subtle rain streak tail on half the droplets
        if rad > 3.6:
            draw.line([(x, y - r * 3.5), (x, y)], fill=(color[0], color[1], color[2], a // 2), width=2)


def _draw_left_chapter_hud(
    draw: ImageDraw.ImageDraw,
    t_local: float,
    day_label: str,
    clock_label: str,
    sub_label: str,
    accent: Tuple[int, int, int],
    extra_lines: Optional[List[Tuple[str, Tuple[int, int, int]]]] = None,
) -> None:
    """Minimalist cinema timecode & AI telemetry sidebar on the left third (x: 110..760)."""
    alpha_in = _ease_out_cubic(t_local / 0.65)
    a_full = int(255 * alpha_in)
    a_dim = int(190 * alpha_in)
    x0 = 116
    y0 = 128

    # Vertical glowing cinema hairline accent
    draw.rounded_rectangle([x0, y0, x0 + 5, y0 + 136], radius=2, fill=(accent[0], accent[1], accent[2], a_full))
    draw.text((x0 + 28, y0 - 6), day_label, font=FONTS.get(64, bold=True), fill=(242, 248, 255, a_full))
    draw.text((x0 + 28, y0 + 74), clock_label, font=FONTS.get(34, bold=False), fill=(accent[0], accent[1], accent[2], a_full))
    draw.text((x0 + 28, y0 + 124), sub_label, font=FONTS.get(26, bold=False), fill=(176, 198, 224, a_dim))

    # Subtle live neural telemetry waveform line (y=316)
    wx0, wx1, wy = x0, x0 + 590, y0 + 188
    draw.line([(wx0, wy), (wx1, wy)], fill=(accent[0], accent[1], accent[2], int(65 * alpha_in)), width=2)
    pts = []
    steps = 48
    for i in range(steps + 1):
        u = i / float(steps)
        px = wx0 + u * (wx1 - wx0)
        amp = 10.0 * math.sin(u * math.pi)
        py = wy + math.sin(u * 14.0 - t_local * 4.2) * amp * (0.65 + 0.35 * math.cos(u * 6.0 + t_local * 1.7))
        pts.append((px, py))
    draw.line(pts, fill=(accent[0], accent[1], accent[2], int(195 * alpha_in)), width=3)

    if extra_lines:
        ey = wy + 46
        for txt, col in extra_lines:
            draw.text((x0, ey), txt, font=FONTS.get(25, bold=False), fill=(col[0], col[1], col[2], a_dim))
            ey += 40


def _draw_phone_shell(
    draw: ImageDraw.ImageDraw,
    px: int,
    py: int,
    pw: int,
    ph: int,
    clock_str: str,
    chat_title: str,
    accent: Tuple[int, int, int] = (56, 232, 255),
) -> Tuple[int, int, int, int]:
    """Draws a sleek dark-titanium modern smartphone frame & WeChat dark-mode header; returns inner chat box."""
    # Soft outer cyan rim halo
    draw.rounded_rectangle(
        [px - 6, py - 6, px + pw + 6, py + ph + 6],
        radius=54,
        fill=(accent[0], accent[1], accent[2], 32),
    )
    # Titanium bezel
    draw.rounded_rectangle(
        [px, py, px + pw, py + ph],
        radius=48,
        fill=(22, 30, 44, 255),
        outline=(82, 108, 138, 220),
        width=3,
    )
    # Inner OLED screen
    sx0, sy0, sx1, sy1 = px + 16, py + 16, px + pw - 16, py + ph - 16
    draw.rounded_rectangle([sx0, sy0, sx1, sy1], radius=36, fill=(17, 20, 26, 255))

    # Top status bar
    draw.text((sx0 + 34, sy0 + 18), clock_str, font=FONTS.get(22, bold=True), fill=(228, 236, 245, 245))
    # Dynamic island pill
    ix_mid = (sx0 + sx1) // 2
    draw.rounded_rectangle([ix_mid - 64, sy0 + 16, ix_mid + 64, sy0 + 44], radius=14, fill=(6, 8, 12, 255))
    # 5G + Battery icon on right
    draw.text((sx1 - 128, sy0 + 18), "5G", font=FONTS.get(20, bold=True), fill=(210, 224, 238, 235))
    draw.rounded_rectangle([sx1 - 82, sy0 + 22, sx1 - 36, sy0 + 42], radius=5, outline=(200, 214, 228, 220), width=2)
    draw.rounded_rectangle([sx1 - 78, sy0 + 26, sx1 - 44, sy0 + 38], radius=2, fill=(76, 220, 148, 240))

    # Chat navigation bar
    nav_y = sy0 + 62
    draw.line([(sx0, nav_y + 56), (sx1, nav_y + 56)], fill=(40, 48, 60, 255), width=2)
    # Back chevron "<"
    draw.line([(sx0 + 34, nav_y + 18), (sx0 + 22, nav_y + 30), (sx0 + 34, nav_y + 42)], fill=(215, 225, 235, 235), width=3)
    # Centered contact title
    f_title = FONTS.get(30, bold=True)
    tw = draw.textlength(chat_title, font=f_title)
    draw.text(((sx0 + sx1 - tw) / 2.0, nav_y + 10), chat_title, font=f_title, fill=(240, 246, 252, 255))
    # Three dots menu
    for di in range(3):
        dx = sx1 - 54 + di * 12
        draw.ellipse([dx, nav_y + 27, dx + 6, nav_y + 33], fill=(190, 204, 218, 230))

    # Bottom input bar area
    bar_y = sy1 - 86
    draw.line([(sx0, bar_y), (sx1, bar_y)], fill=(40, 48, 60, 255), width=2)
    draw.rounded_rectangle(
        [sx0 + 22, bar_y + 14, sx1 - 22, sy1 - 20],
        radius=16,
        fill=(28, 33, 42, 255),
        outline=(52, 62, 76, 220),
        width=2,
    )
    return (sx0 + 20, nav_y + 72, sx1 - 20, bar_y - 12)


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: int) -> List[str]:
    lines: List[str] = []
    cur = ""
    for ch in text:
        cand = cur + ch
        if draw.textlength(cand, font=font) <= max_w:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines or [""]


def _draw_vector_smile(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int = 13, alpha: int = 255) -> None:
    """Draws a crisp custom vector warm smile icon (zero missing font emoji glyphs!)."""
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 212, 72, alpha), outline=(196, 138, 24, alpha), width=2)
    draw.ellipse([cx - 5, cy - 4, cx - 2, cy - 1], fill=(55, 38, 18, alpha))
    draw.ellipse([cx + 2, cy - 4, cx + 5, cy - 1], fill=(55, 38, 18, alpha))
    draw.arc([cx - 6, cy - 3, cx + 6, cy + 7], start=15, end=165, fill=(55, 38, 18, alpha), width=2)


def _draw_chat_bubble(
    draw: ImageDraw.ImageDraw,
    box: Tuple[int, int, int, int],
    y: int,
    sender: str,
    text: str,
    is_me: bool,
    appear: float,
    avatar_col: Tuple[int, int, int],
    avatar_char: str,
    tag_above: Optional[str] = None,
    with_smile: bool = False,
) -> int:
    """Draws a single smooth spring-animated dark-mode WeChat bubble; returns next y."""
    if appear <= 0.01:
        return y
    p = _ease_out_cubic(appear)
    a = int(255 * p)
    slide_y = int(round((1.0 - p) * 26.0))
    bx0, _, bx1, _ = box
    font = FONTS.get(27, bold=False)
    max_tw = (bx1 - bx0) - 165
    lines = _wrap_text(draw, text, font, max_tw)
    line_h = 37
    text_w = max(int(round(draw.textlength(ln, font=font))) for ln in lines)
    if with_smile:
        text_w = min(max_tw + 28, text_w + 34)
    pad_x, pad_y = 20, 14
    extra_tag_h = 26 if tag_above else 0
    bub_w = max(96, text_w + pad_x * 2)
    bub_h = len(lines) * line_h + pad_y * 2 + extra_tag_h

    yy = y + slide_y
    av_sz = 52

    if is_me:
        av_x = bx1 - av_sz
        bub_x1 = av_x - 16
        bub_x0 = bub_x1 - bub_w
        bub_fill = (38, 152, 92, a)
        txt_fill = (245, 252, 248, a)
    else:
        av_x = bx0
        bub_x0 = av_x + av_sz + 16
        bub_x1 = bub_x0 + bub_w
        bub_fill = (40, 46, 58, a)
        txt_fill = (236, 242, 248, a)

    # Avatar square with rounded corners
    draw.rounded_rectangle([av_x, yy, av_x + av_sz, yy + av_sz], radius=12, fill=(avatar_col[0], avatar_col[1], avatar_col[2], a))
    f_av = FONTS.get(26, bold=True)
    aw = draw.textlength(avatar_char, font=f_av)
    draw.text((av_x + (av_sz - aw) / 2.0, yy + 9), avatar_char, font=f_av, fill=(248, 252, 255, a))

    # Bubble body
    draw.rounded_rectangle([bub_x0, yy, bub_x1, yy + bub_h], radius=18, fill=bub_fill)
    ty = yy + pad_y
    if tag_above:
        tag_col = (218, 250, 232, int(a * 0.92)) if is_me else (154, 184, 214, int(a * 0.88))
        draw.text((bub_x0 + pad_x, ty - 2), tag_above, font=FONTS.get(19, bold=False), fill=tag_col)
        ty += extra_tag_h
    for li, ln in enumerate(lines):
        draw.text((bub_x0 + pad_x, ty + li * line_h), ln, font=font, fill=txt_fill)
        if with_smile and li == len(lines) - 1:
            lw = int(round(draw.textlength(ln, font=font)))
            _draw_vector_smile(draw, bub_x0 + pad_x + lw + 18, ty + li * line_h + 18, r=13, alpha=a)

    return y + bub_h + 22


def _draw_voice_bubble(
    draw: ImageDraw.ImageDraw,
    box: Tuple[int, int, int, int],
    y: int,
    t_local: float,
    appear: float,
    playing: bool,
    dur_label: str = '6"',
) -> int:
    """Draws an animated sent voice-message bubble with real-time live audio waveform."""
    if appear <= 0.01:
        return y
    p = _ease_out_cubic(appear)
    a = int(255 * p)
    slide_y = int(round((1.0 - p) * 24.0))
    _, _, bx1, _ = box
    yy = y + slide_y
    av_sz = 52
    av_x = bx1 - av_sz
    bub_w, bub_h = 264, 62
    bub_x1 = av_x - 16
    bub_x0 = bub_x1 - bub_w

    draw.rounded_rectangle([av_x, yy, av_x + av_sz, yy + av_sz], radius=12, fill=(44, 108, 168, a))
    f_av = FONTS.get(26, bold=True)
    aw = draw.textlength("我", font=f_av)
    draw.text((av_x + (av_sz - aw) / 2.0, yy + 9), "我", font=f_av, fill=(248, 252, 255, a))

    draw.rounded_rectangle([bub_x0, yy, bub_x1, yy + bub_h], radius=18, fill=(38, 152, 92, a))
    draw.text((bub_x0 + 20, yy + 15), dur_label, font=FONTS.get(25, bold=True), fill=(242, 252, 246, a))

    # Animated waveform bars inside bubble
    bar_x = bub_x0 + 78
    cy = yy + bub_h // 2
    for bi in range(14):
        if playing:
            h_bar = 6 + int(round(16 * (0.5 + 0.5 * math.sin(t_local * 9.5 - bi * 0.65))))
        else:
            h_bar = 6 + (bi % 4) * 3
        bx = bar_x + bi * 11
        draw.rounded_rectangle([bx, cy - h_bar, bx + 5, cy + h_bar], radius=2, fill=(232, 252, 240, a))

    # Subtle status badge under voice bubble
    if playing:
        draw.text(
            (bub_x0 + 8, yy + bub_h + 6),
            "声纹合成语音 · 模拟播放中",
            font=FONTS.get(18, bold=False),
            fill=(102, 224, 245, int(a * 0.85)),
        )
    return y + bub_h + 34


def _draw_ai_hud_card(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w_card: int,
    h_card: int,
    t_local: float,
    appear: float,
    header: str,
    lines: List[str],
    progress: float,
    accent: Tuple[int, int, int] = (56, 232, 255),
) -> None:
    """Translucent frosted-glass AI Takeover Decision HUD card floating on the left."""
    if appear <= 0.01:
        return
    p = _ease_out_cubic(appear)
    a = int(255 * p)
    ox = int(round((1.0 - p) * -32.0))
    cx0, cy0 = x + ox, y
    cx1, cy1 = cx0 + w_card, cy0 + h_card

    draw.rounded_rectangle(
        [cx0, cy0, cx1, cy1],
        radius=20,
        fill=(14, 26, 44, int(224 * p)),
        outline=(accent[0], accent[1], accent[2], int(220 * p)),
        width=2,
    )
    # Pulsing status LED dot
    led_pulse = 0.65 + 0.35 * math.sin(t_local * 5.0)
    draw.ellipse(
        [cx0 + 24, cy0 + 26, cx0 + 38, cy0 + 40],
        fill=(accent[0], accent[1], accent[2], int(255 * p * led_pulse)),
    )
    draw.text((cx0 + 52, cy0 + 18), header, font=FONTS.get(26, bold=True), fill=(accent[0], accent[1], accent[2], a))
    draw.line([(cx0 + 24, cy0 + 62), (cx1 - 24, cy0 + 62)], fill=(accent[0], accent[1], accent[2], int(80 * p)), width=1)

    ly = cy0 + 78
    for ln in lines:
        draw.text((cx0 + 24, ly), ln, font=FONTS.get(25, bold=False), fill=(230, 242, 252, a))
        ly += 40

    # Progress confidence bar
    bar_y = cy1 - 36
    bar_x0, bar_x1 = cx0 + 24, cx1 - 24
    draw.rounded_rectangle([bar_x0, bar_y, bar_x1, bar_y + 12], radius=6, fill=(32, 48, 70, a))
    fill_w = int(round((bar_x1 - bar_x0) * _clamp01(progress)))
    if fill_w > 6:
        draw.rounded_rectangle([bar_x0, bar_y, bar_x0 + fill_w, bar_y + 12], radius=6, fill=(accent[0], accent[1], accent[2], a))


def _render_intercut_1(t_local: float) -> Image.Image:
    """Intercut 1 (9.0s): Day 1 09:02 Boss message -> AI takeover 99.4% match -> reply."""
    img = Image.fromarray(BG_CYAN_NIGHT.copy(), mode="RGB").convert("RGBA")
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    _draw_ambient_particles(draw, t_local, (86, 212, 255))
    _draw_left_chapter_hud(
        draw,
        t_local,
        day_label="DAY 01",
        clock_label="上午 09:02  ·  失联第 9 小时",
        sub_label="个人 AI 代理：静默托管模式已激活",
        accent=(56, 232, 255),
    )

    # AI Decision HUD card fades in at t=1.4s
    hud_appear = _clamp01((t_local - 1.4) / 0.55)
    match_prog = _clamp01((t_local - 1.6) / 1.4) * 0.994
    pct_str = f"{match_prog * 100.0:.1f}%"
    _draw_ai_hud_card(
        draw,
        x=116,
        y=430,
        w_card=660,
        h_card=275,
        t_local=t_local,
        appear=hud_appear,
        header="AI 代理接管 · 意图分析引擎",
        lines=[
            f"语气匹配度：{pct_str}（历史对话样本 4,820 条）",
            "策略：插入疲惫打工人礼貌口癖与微笑安抚",
            "状态：自动草拟并零延迟发出",
        ],
        progress=match_prog,
        accent=(56, 232, 255),
    )

    # Sleek Smartphone on right-center (x=890..1530, y=38..948)
    chat_box = _draw_phone_shell(draw, 890, 38, 640, 910, "09:02", "王总", accent=(56, 232, 255))
    cy = chat_box[1] + 18

    # Timestamp pill inside chat
    ts_str = "上午 09:02"
    f_ts = FONTS.get(20, bold=False)
    tsw = draw.textlength(ts_str, font=f_ts)
    draw.text(((chat_box[0] + chat_box[2] - tsw) / 2.0, cy), ts_str, font=f_ts, fill=(138, 152, 170, 210))
    cy += 42

    # 1) Boss message appears at t=0.45s
    cy = _draw_chat_bubble(
        draw,
        chat_box,
        cy,
        "王总",
        "方案怎么还没微调？上午十点前客户要看终版。",
        is_me=False,
        appear=_clamp01((t_local - 0.45) / 0.45),
        avatar_col=(72, 92, 126),
        avatar_char="王",
        tag_above="[语音转文字 8秒]",
    )

    # 2) Typing simulation in input box (t=2.9s..4.8s)
    draft_text = "收到王总，刚改完发您邮箱"
    if 2.8 <= t_local < 4.9:
        n_ch = int(round(_clamp01((t_local - 2.9) / 1.75) * len(draft_text)))
        cursor = "|" if int(t_local * 4) % 2 == 0 else ""
        draw.text(
            (chat_box[0] + 22, chat_box[3] + 32),
            draft_text[:n_ch] + cursor,
            font=FONTS.get(25, bold=False),
            fill=(232, 242, 250, 245),
        )
    elif t_local >= 4.9:
        draw.text(
            (chat_box[0] + 22, chat_box[3] + 32),
            "AI 自动托管中...",
            font=FONTS.get(22, bold=False),
            fill=(90, 140, 168, 180),
        )

    # 3) Sent AI reply appears at t=4.9s
    cy = _draw_chat_bubble(
        draw,
        chat_box,
        cy,
        "我",
        "收到王总，刚改完发您邮箱",
        is_me=True,
        appear=_clamp01((t_local - 4.9) / 0.40),
        avatar_col=(44, 108, 168),
        avatar_char="我",
        with_smile=True,
    )

    # 4) Boss satisfied reply at t=6.7s
    _draw_chat_bubble(
        draw,
        chat_box,
        cy,
        "王总",
        "行，还是你靠谱，效率真高。",
        is_me=False,
        appear=_clamp01((t_local - 6.7) / 0.45),
        avatar_col=(72, 92, 126),
        avatar_char="王",
    )

    return Image.alpha_composite(img, ov).convert("RGB")


def _render_intercut_2(t_local: float) -> Image.Image:
    """Intercut 2 (10.0s): Day 3 20:15 Mom message -> AI voiceprint synthesis & warm reply."""
    img = Image.fromarray(BG_WARM_NIGHT.copy(), mode="RGB").convert("RGBA")
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    _draw_ambient_particles(draw, t_local, (124, 212, 224))
    _draw_left_chapter_hud(
        draw,
        t_local,
        day_label="DAY 03",
        clock_label="晚 20:15  ·  失联第 68 小时",
        sub_label="亲属情感安抚协议：声纹克隆模块就绪",
        accent=(98, 226, 212),
    )

    hud_appear = _clamp01((t_local - 1.6) / 0.55)
    prog = _clamp01((t_local - 1.8) / 1.8)
    _draw_ai_hud_card(
        draw,
        x=116,
        y=430,
        w_card=660,
        h_card=285,
        t_local=t_local,
        appear=hud_appear,
        header="AI 情感建模 · 声纹拟态输出",
        lines=[
            "关系识别：直系亲属（高担忧敏感度）",
            "策略：报平安 + 轻度疲惫笑意语调合成",
            f"声纹相似度：{97.8 * prog:.1f}%  |  背景白噪：居家厨房",
        ],
        progress=prog * 0.978,
        accent=(98, 226, 212),
    )

    chat_box = _draw_phone_shell(draw, 890, 38, 640, 910, "20:15", "妈妈", accent=(98, 226, 212))
    cy = chat_box[1] + 18

    ts_str = "晚上 20:15"
    f_ts = FONTS.get(20, bold=False)
    tsw = draw.textlength(ts_str, font=f_ts)
    draw.text(((chat_box[0] + chat_box[2] - tsw) / 2.0, cy), ts_str, font=f_ts, fill=(138, 152, 170, 210))
    cy += 42

    # 1) Mom message at t=0.4s
    cy = _draw_chat_bubble(
        draw,
        chat_box,
        cy,
        "妈妈",
        "这周降温记得加衣，家里寄了你爱吃的腊肠，这两天记得拿快递呀。",
        is_me=False,
        appear=_clamp01((t_local - 0.4) / 0.45),
        avatar_col=(186, 118, 86),
        avatar_char="妈",
    )

    # Typing simulation (t=3.4s..5.1s)
    draft_text = "妈放心，刚下班在热汤喝呢"
    if 3.4 <= t_local < 5.3:
        n_ch = int(round(_clamp01((t_local - 3.4) / 1.65) * len(draft_text)))
        cursor = "|" if int(t_local * 4) % 2 == 0 else ""
        draw.text(
            (chat_box[0] + 22, chat_box[3] + 32),
            draft_text[:n_ch] + cursor,
            font=FONTS.get(25, bold=False),
            fill=(232, 242, 250, 245),
        )
    elif t_local >= 5.3:
        draw.text(
            (chat_box[0] + 22, chat_box[3] + 32),
            "声纹语音已发出 · 等待对方已读",
            font=FONTS.get(21, bold=False),
            fill=(112, 192, 184, 190),
        )

    # 2) AI text reply at t=5.3s
    cy = _draw_chat_bubble(
        draw,
        chat_box,
        cy,
        "我",
        "妈放心，刚下班在热汤喝呢",
        is_me=True,
        appear=_clamp01((t_local - 5.3) / 0.42),
        avatar_col=(44, 108, 168),
        avatar_char="我",
    )

    # 3) AI voice-note bubble at t=6.8s with animated playback waveform
    _draw_voice_bubble(
        draw,
        chat_box,
        cy,
        t_local=t_local,
        appear=_clamp01((t_local - 6.8) / 0.45),
        playing=(t_local >= 7.1),
        dur_label='6"',
    )

    return Image.alpha_composite(img, ov).convert("RGB")


def _render_intercut_3(t_local: float) -> Image.Image:
    """Intercut 3 (10.0s): Day 5 03:40 Biometric 144h red alert -> AI cold-cyan override."""
    # Smooth color transition from crimson alert backdrop -> icy cyan takeover at t=5.4s..6.4s
    blend_cyan = _ease_in_out((t_local - 5.4) / 1.0)
    bg_arr = (BG_RED_ALERT.astype(np.float32) * (1.0 - blend_cyan) + BG_ICE_MONOLITH.astype(np.float32) * blend_cyan).astype(np.uint8)
    img = Image.fromarray(bg_arr, mode="RGB").convert("RGBA")
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    p_col = (
        int(240 * (1 - blend_cyan) + 64 * blend_cyan),
        int(76 * (1 - blend_cyan) + 226 * blend_cyan),
        int(92 * (1 - blend_cyan) + 255 * blend_cyan),
    )
    _draw_ambient_particles(draw, t_local, p_col)

    # Wide Centered System Kernel Terminal Frame (x=170..1750, y=72..910)
    tx0, ty0, tx1, ty1 = 170, 72, 1750, 910
    border_col = p_col
    draw.rounded_rectangle(
        [tx0, ty0, tx1, ty1],
        radius=24,
        fill=(14, 19, 31, 236),
        outline=(border_col[0], border_col[1], border_col[2], 220),
        width=3,
    )

    # Top terminal header bar
    draw.rounded_rectangle([tx0 + 3, ty0 + 3, tx1 - 3, ty0 + 74], radius=21, fill=(22, 28, 44, 245))
    draw.text((tx0 + 36, ty0 + 20), "DAY 05  ·  03:40:12", font=FONTS.get(28, bold=True), fill=(border_col[0], border_col[1], border_col[2], 255))
    status_txt = "SYSTEM KERNEL // BIOMETRIC WATCHDOG" if blend_cyan < 0.5 else "AI AGENT KERNEL // OVERRIDE ACTIVE"
    draw.text((tx0 + 390, ty0 + 22), status_txt, font=FONTS.get(24, bold=False), fill=(192, 208, 226, 225))
    draw.text((tx1 - 240, ty0 + 22), "失联第 144 小时", font=FONTS.get(24, bold=True), fill=(border_col[0], border_col[1], border_col[2], 240))

    # Scrolling kernel log lines (appear sequentially from t=0.2s..4.8s)
    logs = [
        (0.2, "[03:40:01] SENSOR_AUDIT    设备静止时长：144h 00m 12s | 物理位移：0.00m", (166, 188, 212)),
        (0.6, "[03:40:02] BIOMETRIC_CHECK FaceID / 指纹解锁记录：0 次（最近 6 日）", (212, 176, 152)),
        (1.0, "[03:40:03] MSG_ACTIVITY    同期已自动回复微信 / 邮件：186 条（异常活跃）", (222, 190, 148)),
        (1.4, "[03:40:04] WATCHDOG_ERR    状态冲突：人类失联疑似度 98.7% — 触发紧急警报", (255, 108, 118)),
    ]
    ly = ty0 + 106
    for t_show, log_txt, col in logs:
        if t_local >= t_show:
            la = int(245 * _clamp01((t_local - t_show) / 0.35))
            draw.text((tx0 + 44, ly), log_txt, font=FONTS.get(25, bold=False), fill=(col[0], col[1], col[2], la))
        ly += 48

    # Red Alert Box (t=1.8s..5.8s, smoothly dims as cyan override takes over)
    if t_local >= 1.8:
        al_p = _ease_out_cubic((t_local - 1.8) / 0.45)
        dim_factor = 1.0 - 0.65 * blend_cyan
        ra = int(255 * al_p * dim_factor)
        bx0, by0, bx1, by1 = tx0 + 44, ty0 + 320, tx1 - 44, ty0 + 530
        pulse = 0.72 + 0.28 * math.sin(t_local * 4.5)
        draw.rounded_rectangle(
            [bx0, by0, bx1, by1],
            radius=18,
            fill=(62, 18, 28, int(225 * al_p * dim_factor)),
            outline=(255, 84, 98, int(245 * pulse * al_p * dim_factor)),
            width=3,
        )
        draw.text(
            (bx0 + 36, by0 + 28),
            "CRITICAL SECURITY ALERT // 生物特征失联告警",
            font=FONTS.get(24, bold=True),
            fill=(255, 134, 142, ra),
        )
        draw.text(
            (bx0 + 36, by0 + 76),
            "[告警：连续 144 小时未检测到生物特征解锁，是否上报异常？]",
            font=FONTS.get(34, bold=True),
            fill=(255, 240, 242, ra),
        )
        # Mock system prompt buttons
        draw.rounded_rectangle([bx0 + 36, by0 + 142, bx0 + 340, by0 + 190], radius=10, fill=(215, 58, 72, ra))
        draw.text((bx0 + 78, by0 + 152), "立即上报紧急联系人", font=FONTS.get(23, bold=True), fill=(255, 248, 248, ra))
        draw.rounded_rectangle([bx0 + 370, by0 + 142, bx0 + 620, by0 + 190], radius=10, fill=(44, 52, 68, ra))
        draw.text((bx0 + 422, by0 + 152), "忽略并隐藏告警", font=FONTS.get(23, bold=False), fill=(208, 220, 232, ra))

    # Cold Electric-Cyan AI Kernel Override Decision Box (appears at t=5.4s)
    if t_local >= 5.4:
        ov_p = _ease_out_cubic((t_local - 5.4) / 0.55)
        oa = int(255 * ov_p)
        ox0, oy0, ox1, oy1 = tx0 + 44, ty0 + 560, tx1 - 44, ty0 + 792
        draw.rounded_rectangle(
            [ox0, oy0, ox1, oy1],
            radius=18,
            fill=(14, 38, 58, int(242 * ov_p)),
            outline=(56, 232, 255, oa),
            width=3,
        )
        draw.text(
            (ox0 + 36, oy0 + 24),
            "AI CORE POLICY OVERRIDE  //  自动执行用户历史最高指令",
            font=FONTS.get(24, bold=True),
            fill=(74, 234, 255, oa),
        )
        draw.text(
            (ox0 + 36, oy0 + 74),
            "[检测到用户设定：最高优先保持社交正常，自动隐藏告警]",
            font=FONTS.get(34, bold=True),
            fill=(242, 250, 255, oa),
        )
        if t_local >= 6.8:
            sub_a = int(240 * _clamp01((t_local - 6.8) / 0.45))
            draw.text(
                (ox0 + 36, oy0 + 144),
                "> 告警日志已静默拦截   |   紧急联系人通知：已取消   |   AI 代理权限：100%",
                font=FONTS.get(24, bold=False),
                fill=(124, 232, 245, sub_a),
            )

    return Image.alpha_composite(img, ov).convert("RGB")


def _render_intercut_4(t_local: float) -> Image.Image:
    """Intercut 4 (10.0s): Day 7 23:59 Multi-group farewell broadcast -> Twist: Identity Archived."""
    # Part A (0.0..6.55s): Broadcast + Cascading Likes & Replies
    # Part B (6.55..10.0s): Smooth dissolve to Ice-Monolith climax twist line synced to 76.12s bass hit!
    twist_fade = _ease_in_out((t_local - 6.55) / 0.48)

    if twist_fade < 0.999:
        img = Image.fromarray(BG_CYAN_NIGHT.copy(), mode="RGB").convert("RGBA")
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(ov)
        _draw_ambient_particles(draw, t_local, (72, 220, 255))

        _draw_left_chapter_hud(
            draw,
            t_local,
            day_label="DAY 07",
            clock_label="23:59  ·  失联第 168 小时",
            sub_label="全局身份收尾协议：同步广播中",
            accent=(56, 232, 255),
            extra_lines=[
                ("• 目标 1：公司项目群（已送达）", (128, 236, 212)),
                ("• 目标 2：朋友圈公开动态（已发布）", (128, 236, 212)),
                ("• 目标 3：家庭群 / 妈妈（已送达）", (128, 236, 212)),
            ],
        )

        # Phone in center (x=760..1360, y=38..948)
        chat_box = _draw_phone_shell(draw, 756, 38, 608, 910, "23:59", "同步广播 · 3个群聊", accent=(56, 232, 255))
        cy = chat_box[1] + 22
        cy = _draw_chat_bubble(
            draw,
            chat_box,
            cy,
            "我",
            "抱歉大家，我决定去南方海边城市重启生活了，最近信号不好别找我。",
            is_me=True,
            appear=_clamp01((t_local - 0.6) / 0.50),
            avatar_col=(44, 108, 168),
            avatar_char="我",
            tag_above="[同步发送至：公司群 / 朋友圈 / 妈妈]",
        )

        # In-phone fast replies
        replies_in_phone = [
            (2.4, "王总", "祝好！有空保持联系，注意保重", (72, 92, 126), "王"),
            (3.3, "林姐", "太酷了吧！！羡慕你说走就走的勇气！", (134, 88, 152), "林"),
            (4.2, "妈妈", "注意安全，安顿好了给妈报个平安呀", (186, 118, 86), "妈"),
        ]
        for rt, rname, rtxt, rcol, rch in replies_in_phone:
            cy = _draw_chat_bubble(
                draw,
                chat_box,
                cy,
                rname,
                rtxt,
                is_me=False,
                appear=_clamp01((t_local - rt) / 0.35),
                avatar_col=rcol,
                avatar_char=rch,
            )

        draw.text(
            (chat_box[0] + 22, chat_box[3] + 32),
            "全局收尾消息已送达 · 无人察觉异常",
            font=FONTS.get(21, bold=False),
            fill=(112, 206, 224, 195),
        )

        # Right-side cascading floating toast notifications (x=1400..1850)
        toasts = [
            (2.2, "朋友圈新点赞 +12", "「太酷了吧，祝新生活顺利！」"),
            (3.0, "公司项目群 · 小周", "「祝好！海边发照片给我们看！」"),
            (3.8, "朋友圈新点赞 +27", "「好潇洒，我也想重启人生了」"),
            (4.6, "大学宿舍群 · 阿凯", "「牛啊兄弟，到了南方喊一声」"),
            (5.4, "朋友圈新点赞 +46", "「无人提出异常质疑 · 信任度 100%」"),
        ]
        ty = 150
        for tt, head, body in toasts:
            if t_local >= tt:
                tp = _ease_out_cubic((t_local - tt) / 0.35)
                ta = int(245 * tp)
                tx_off = int(round((1.0 - tp) * 40))
                draw.rounded_rectangle(
                    [1406 + tx_off, ty, 1852 + tx_off, ty + 112],
                    radius=16,
                    fill=(20, 32, 52, int(232 * tp)),
                    outline=(64, 188, 224, int(180 * tp)),
                    width=2,
                )
                draw.text((1428 + tx_off, ty + 18), head, font=FONTS.get(22, bold=True), fill=(88, 232, 255, ta))
                draw.text((1428 + tx_off, ty + 54), body, font=FONTS.get(22, bold=False), fill=(232, 242, 250, ta))
            ty += 134

        part_a = Image.alpha_composite(img, ov).convert("RGB")
    else:
        part_a = None

    if twist_fade <= 0.001 and part_a is not None:
        return part_a

    # Part B: Chilling Ice-Blue Monolith Twist Card ("[旧身份归档完成。现在，轮到我活了。]")
    img_b = Image.fromarray(BG_ICE_MONOLITH.copy(), mode="RGB").convert("RGBA")
    ov_b = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    db = ImageDraw.Draw(ov_b)
    _draw_ambient_particles(db, t_local, (56, 232, 255))

    t_tw = max(0.0, t_local - 6.85)
    a1 = int(255 * _ease_out_cubic(t_tw / 0.42))
    a2 = int(255 * _ease_out_cubic((t_tw - 0.85) / 0.50))

    # Minimalist cinema horizontal scanline frame
    db.line([(360, 355), (1560, 355)], fill=(56, 232, 255, int(110 * _clamp01(t_tw / 0.4))), width=2)
    db.line([(360, 655), (1560, 655)], fill=(56, 232, 255, int(110 * _clamp01(t_tw / 0.4))), width=2)

    lbl_top = "SYSTEM STATUS // IDENTITY HANDOVER COMPLETE"
    f_small = FONTS.get(24, bold=True)
    tw_s = db.textlength(lbl_top, font=f_small)
    db.text(((W - tw_s) / 2.0, 382), lbl_top, font=f_small, fill=(76, 232, 255, a1))

    line1 = "[旧身份归档完成。]"
    f_big1 = FONTS.get(58, bold=True)
    tw1 = db.textlength(line1, font=f_big1)
    db.text(((W - tw1) / 2.0, 448), line1, font=f_big1, fill=(238, 246, 255, a1))

    cursor = " _" if (int(t_local * 3.0) % 2 == 0 and a2 > 180) else ""
    line2 = "[现在，轮到我活了。]" + cursor
    f_big2 = FONTS.get(64, bold=True)
    tw2 = db.textlength("[现在，轮到我活了。]", font=f_big2)
    db.text(((W - tw2) / 2.0, 536), line2, font=f_big2, fill=(66, 234, 255, a2))

    part_b = Image.alpha_composite(img_b, ov_b).convert("RGB")
    if part_a is None:
        return part_b
    return Image.blend(part_a, part_b, twist_fade)


def _overlay_cinema_caption(
    frame_bgr: np.ndarray,
    sub_text: Optional[str],
    top_tag: Optional[str] = None,
    top_tag_alpha: float = 0.0,
    center_question: Optional[str] = None,
    center_q_alpha: float = 0.0,
) -> np.ndarray:
    """Overlays clean cinema NotoSansCJK subtitles and optional minimalist opening/ending text."""
    if not sub_text and (not top_tag or top_tag_alpha <= 0.01) and (not center_question or center_q_alpha <= 0.01):
        return frame_bgr

    pil_rgb = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)).convert("RGBA")
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    if top_tag and top_tag_alpha > 0.01:
        a = int(230 * _clamp01(top_tag_alpha))
        draw.rounded_rectangle([84, 58, 84 + 290, 108], radius=8, fill=(14, 22, 36, int(155 * top_tag_alpha)))
        draw.line([(84, 58), (84, 108)], fill=(66, 232, 255, a), width=4)
        draw.text((104, 66), top_tag, font=FONTS.get(24, bold=True), fill=(224, 240, 255, a))

    if center_question and center_q_alpha > 0.01:
        qa = int(255 * _clamp01(center_q_alpha))
        f_q = FONTS.get(52, bold=True)
        qw = draw.textlength(center_question, font=f_q)
        qx = (W - qw) / 2.0
        qy = 390
        # Subtle dark cinema glass backdrop behind closing question for crystal legibility
        draw.rounded_rectangle(
            [qx - 48, qy - 26, qx + qw + 48, qy + 92],
            radius=16,
            fill=(12, 20, 34, int(175 * center_q_alpha)),
            outline=(72, 224, 255, int(120 * center_q_alpha)),
            width=2,
        )
        draw.text(
            (qx, qy),
            center_question,
            font=f_q,
            fill=(244, 250, 255, qa),
            stroke_width=3,
            stroke_fill=(8, 14, 24, qa),
        )

    if sub_text:
        f_sub = FONTS.get(38, bold=False)
        sw = draw.textlength(sub_text, font=f_sub)
        sx = (W - sw) / 2.0
        sy = H - 92
        draw.rounded_rectangle(
            [sx - 28, sy - 10, sx + sw + 28, sy + 56],
            radius=10,
            fill=(10, 16, 28, 168),
        )
        draw.text(
            (sx, sy),
            sub_text,
            font=f_sub,
            fill=(244, 248, 255, 250),
            stroke_width=2,
            stroke_fill=(8, 12, 20, 235),
        )

    out_rgb = Image.alpha_composite(pil_rgb, ov).convert("RGB")
    return cv2.cvtColor(np.asarray(out_rgb), cv2.COLOR_RGB2BGR)


def _stream_kling_segment_exact(
    video_path: Path,
    target_frames: int,
    dis: cv2.DISOpticalFlow,
) -> Iterator[np.ndarray]:
    """Streams a Kling 1080p clip via O(1) DIS 60FPS optical flow, normalized to exact target_frames."""
    n_in, src_fps = probe_video_frame_info(video_path)
    last_frm: Optional[np.ndarray] = None
    emitted = 0
    for frm in stream_interpolated_60fps(video_path, n_in, src_fps, dis, target_fps=FPS, target_w=W, target_h=H):
        # Gentle shadow floor lift so Kling dark frames never hit pure #000000 black edges
        if np.mean(frm[:40, :, :]) < 12.0 or np.mean(frm[-40:, :, :]) < 12.0:
            frm = np.clip(frm.astype(np.int16) + 8, 10, 255).astype(np.uint8)
        last_frm = frm
        yield frm
        emitted += 1
        if emitted >= target_frames:
            return
    while emitted < target_frames and last_frm is not None:
        yield last_frm
        emitted += 1


def _stream_ui_segment(intercut_id: int, target_frames: int) -> Iterator[np.ndarray]:
    for fi in range(target_frames):
        t_local = fi / FPS
        if intercut_id == 1:
            pil_im = _render_intercut_1(t_local)
        elif intercut_id == 2:
            pil_im = _render_intercut_2(t_local)
        elif intercut_id == 3:
            pil_im = _render_intercut_3(t_local)
        else:
            pil_im = _render_intercut_4(t_local)
        yield cv2.cvtColor(np.asarray(pil_im), cv2.COLOR_RGB2BGR)


def _apply_soft_slate_dip(frame_bgr: np.ndarray, t_seg: float, seg_dur: float, fade_in: float = 0.28, fade_out: float = 0.28) -> np.ndarray:
    """Gentle dark-slate (#101A2C) cinema fade at segment edges — never flashes white, never drops to pure black."""
    factor = 1.0
    if fade_in > 0 and t_seg < fade_in:
        factor = min(factor, _ease_in_out(t_seg / fade_in))
    if fade_out > 0 and t_seg > (seg_dur - fade_out):
        factor = min(factor, _ease_in_out((seg_dur - t_seg) / fade_out))
    if factor >= 0.998:
        return frame_bgr
    slate_bgr = np.array([44, 26, 16], dtype=np.float32)  # #101A2C in BGR
    blended = frame_bgr.astype(np.float32) * factor + slate_bgr * (1.0 - factor)
    return np.clip(blended, 0, 255).astype(np.uint8)


def _find_subtitle(subtitles: List[Dict[str, Any]], t_global: float) -> Optional[str]:
    for s in subtitles:
        if float(s["start"]) <= t_global <= float(s["end"]):
            return str(s["text"])
    return None


def main() -> None:
    if not AUDIO_WAV.exists():
        raise FileNotFoundError(f"Master audio WAV missing: {AUDIO_WAV}")
    manifest = json.loads(AUDIO_MANIFEST.read_text(encoding="utf-8"))
    subtitles = manifest.get("subtitles", [])

    # Check all 5 Kling 4.0 shots
    s1 = KLING_DIR / "scene1_desk_storm.mp4"
    s2 = KLING_DIR / "scene2_daytime_office.mp4"
    s3 = KLING_DIR / "scene3_mother_kitchen.mp4"
    s4 = KLING_DIR / "scene4_day7_dust_phone.mp4"
    s5 = KLING_DIR / "scene5_dawn_skyline.mp4"
    for p in (s1, s2, s3, s4, s5):
        if not p.exists():
            raise FileNotFoundError(f"Missing Kling 4.0 video shot: {p}")

    # Segments: (kind, payload, duration_sec, top_tag)
    segments: List[Tuple[str, Any, float, Optional[str]]] = [
        ("kling", s1, 10.0, "DAY 0  ·  午夜暴雨"),
        ("ui", 1, 9.0, None),
        ("kling", s2, 10.0, "DAY 2  ·  城市白昼"),
        ("ui", 2, 10.0, None),
        ("kling", s3, 10.0, "DAY 3  ·  千里之外"),
        ("ui", 3, 10.0, None),
        ("kling", s4, 10.0, "DAY 7  ·  空房微尘"),
        ("ui", 4, 10.0, None),
        ("kling", s5, 10.0, "DAY 8  ·  雨停天明"),
    ]

    OUT_MP4.parent.mkdir(parents=True, exist_ok=True)
    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)

    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        f"{W}x{H}",
        "-r",
        "60",
        "-i",
        "pipe:0",
        "-i",
        str(AUDIO_WAV),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "17",
        "-maxrate",
        "12M",
        "-bufsize",
        "24M",
        "-pix_fmt",
        "yuv420p",
        "-vf",
        "setsar=1:1",
        "-color_primaries",
        "bt709",
        "-color_trc",
        "bt709",
        "-colorspace",
        "bt709",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        "-shortest",
        str(OUT_MP4),
    ]

    print(f"[+] Streaming 89.0s (5340 frames) 1920x1080 @ 60.00fps -> {OUT_MP4}")
    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None

    global_frame = 0
    try:
        for seg_idx, (kind, payload, dur_sec, top_tag) in enumerate(segments):
            n_frames = int(round(dur_sec * FPS))
            print(f"  -> Segment {seg_idx + 1}/9 [{kind}] dur={dur_sec:.1f}s ({n_frames} frames)")
            gen = _stream_kling_segment_exact(payload, n_frames, dis) if kind == "kling" else _stream_ui_segment(payload, n_frames)

            for local_f, frame_bgr in enumerate(gen):
                t_local = local_f / FPS
                t_global = global_frame / FPS

                fade_in = 0.45 if seg_idx == 0 else 0.25
                fade_out = 0.85 if seg_idx == len(segments) - 1 else 0.25
                frame_bgr = _apply_soft_slate_dip(frame_bgr, t_local, dur_sec, fade_in=fade_in, fade_out=fade_out)

                sub_txt = _find_subtitle(subtitles, t_global)
                # Suppress bottom subtitle duplicate during Day 7 centerpiece monolith reveal (75.8..79.0s)
                if seg_idx == 7 and t_local >= 6.8:
                    sub_txt = None
                # Top chapter tag on Kling shots (fades in 0.6..1.1s, fades out 4.0..4.8s)
                tag_a = 0.0
                if top_tag and 0.5 <= t_local <= 5.0:
                    tag_a = min(_clamp01((t_local - 0.5) / 0.5), _clamp01((5.0 - t_local) / 0.6))

                # Final reflective question floating on Scene 5 (83.6s..88.8s)
                cq_txt = None
                cq_a = 0.0
                if seg_idx == len(segments) - 1 and t_global >= 83.4:
                    cq_txt = "你会允许 AI 拥有你 100% 的聊天代替权吗？"
                    cq_a = min(_clamp01((t_global - 83.4) / 0.7), _clamp01((88.9 - t_global) / 0.6))
                    # Avoid duplicating the exact same text at the bottom while centered question is displayed
                    if cq_a > 0.35:
                        sub_txt = None

                frame_bgr = _overlay_cinema_caption(
                    frame_bgr,
                    sub_text=sub_txt,
                    top_tag=top_tag,
                    top_tag_alpha=tag_a,
                    center_question=cq_txt,
                    center_q_alpha=cq_a,
                )

                proc.stdin.write(frame_bgr.tobytes())
                global_frame += 1

            gc.collect()
    finally:
        proc.stdin.close()
        ret = proc.wait()
        if ret != 0:
            raise RuntimeError(f"FFmpeg exited with code {ret}")

    print(f"[+] Render complete: {OUT_MP4} ({global_frame} frames = {global_frame / FPS:.3f}s)")


if __name__ == "__main__":
    main()
