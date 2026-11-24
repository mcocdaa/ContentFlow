#!/usr/bin/env python3
"""Episode 023 O(1) Streaming 1080P 60FPS Video Renderer (Pillow + NumPy -> FFmpeg).

Renders a fast-paced, hilarious, razor-sharp 125-135s product build & live-demo showcase
for 'Cyber Focus Warden (赛博防摸鱼毒舌监工)':
  - Resolution: 1920x1080 @ 60.00fps, SAR=1:1, DAR=16:9, yuv420p, bt709, >= 6500 kbps
  - Strict O(1) RAM: streams 1 frame (6.2 MB) at a time directly into ffmpeg stdin
  - Zero black bars: base gradient #101726 -> #162238 (edge brightness > 22 >> 6.0)
  - Zero camera wobble: locked steady top HUD header bar + smooth kinetic stage animations
  - Zero harsh strobing: smooth sinusoidal breathing siren aura on Lv.3 lockdown
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

PROJ_DIR = Path(__file__).resolve().parent.parent
MANIFEST_PATH = PROJ_DIR / "assets" / "audio" / "manifest.json"
KLING_HERO_PATH = PROJ_DIR / "assets" / "kling_cover_hero_raw.png"
OUT_VIDEO = PROJ_DIR / "delivery" / "AI整活工具_毒舌AI监工防摸鱼_final.mp4"

W, H = 1920, 1080
FPS = 60
FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
FONT_REG = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"

_FONT_CACHE: Dict[Tuple[str, int, int], ImageFont.FreeTypeFont] = {}


def font(size: int, bold: bool = True, idx: int = 2) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD if bold else FONT_REG
    key = (path, size, idx)
    if key not in _FONT_CACHE:
        _FONT_CACHE[key] = ImageFont.truetype(path, size=size, index=idx)
    return _FONT_CACHE[key]


def ease_out_cubic(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1.0 - (1.0 - x) ** 3


def ease_in_out(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * max(0.0, min(1.0, t))


def make_base_backdrop() -> Image.Image:
    """Pre-renders clean #101726 -> #18253E tech gradient with subtle grid & ambient glows (no black bars)."""
    y = np.linspace(0.0, 1.0, H, dtype=np.float32)[:, None]
    x = np.linspace(0.0, 1.0, W, dtype=np.float32)[None, :]

    # Deep tech slate-blue gradient (edge brightness ~ 25..36, well above 6.0!)
    r = 16.0 + 10.0 * (1.0 - np.abs(y - 0.5) * 1.4) + 12.0 * np.exp(-((x - 0.85) ** 2 + (y - 0.22) ** 2) / 0.14)
    g = 23.0 + 14.0 * (1.0 - np.abs(y - 0.5) * 1.3) + 22.0 * np.exp(-((x - 0.16) ** 2 + (y - 0.20) ** 2) / 0.14)
    b = 38.0 + 22.0 * (1.0 - np.abs(y - 0.5) * 1.1) + 34.0 * np.exp(-((x - 0.50) ** 2 + (y - 0.85) ** 2) / 0.22)

    # Subtle cyber blueprint grid
    grid_x = (np.arange(W) % 80 == 0)[None, :]
    grid_y = (np.arange(H) % 80 == 0)[:, None]
    grid = (grid_x | grid_y).astype(np.float32)
    r = np.clip(r + grid * 8.0, 0, 255)
    g = np.clip(g + grid * 14.0, 0, 255)
    b = np.clip(b + grid * 22.0, 0, 255)

    arr = np.stack([r, g, b], axis=-1).astype(np.uint8)
    return Image.fromarray(arr, mode="RGB")


def draw_header_hud(draw: ImageDraw.ImageDraw, act_idx: int, t: float, total_dur: float) -> None:
    """Tripod-locked steady top HUD bar (y: 0..76) -> guarantees zero camera jitter/wobble."""
    draw.rectangle([0, 0, W, 74], fill=(18, 28, 48))
    draw.line([(0, 74), (W, 74)], fill=(45, 76, 124), width=2)

    act_labels = {
        1: ("ACT 01", "凌晨摸鱼痛点 · AI监工登场", (0, 229, 255)),
        2: ("ACT 02", "纯Python零依赖架构 · 核心源码", (52, 232, 158)),
        3: ("ACT 03", "高能实机实测 · 三级惩罚连环翻车", (255, 76, 108)),
        4: ("ACT 04", "MIT开源一行启动 · v2.0共创投票", (255, 204, 72)),
    }
    code, title, accent = act_labels.get(act_idx, act_labels[1])

    # Left chapter badge
    draw.rounded_rectangle([32, 16, 146, 58], radius=10, fill=accent)
    draw.text((46, 20), code, font=font(24, True), fill=(10, 18, 32))
    draw.text((164, 19), title, font=font(26, True), fill=(235, 245, 255))

    # Right fixed privacy/app telemetry badge (comfortably inside 1920px!)
    draw.rounded_rectangle([1210, 16, 1888, 58], radius=10, fill=(24, 38, 64), outline=(66, 114, 178), width=2)
    draw.ellipse([1230, 29, 1246, 45], fill=(34, 229, 138))
    draw.text((1260, 21), "CYBER FOCUS WARDEN · 零摄像头 · 零麦克风 · 本地离线", font=font(21, True), fill=(182, 224, 255))

    # Smooth monotonic timeline progress strip (y=70..74)
    prog_w = int(W * max(0.0, min(1.0, t / max(total_dur, 1.0))))
    draw.rectangle([0, 70, prog_w, 74], fill=accent)


def draw_subtitle(draw: ImageDraw.ImageDraw, seg: Dict[str, Any] | None) -> None:
    """Renders crisp dual-style bottom captions safely above bottom margin."""
    if not seg:
        return
    text = seg["subtitle"]
    is_warden = seg["speaker"] == "warden"
    f_sub = font(40, True)
    bbox = draw.textbbox((0, 0), text, font=f_sub)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    pad_x, pad_y = 34, 14
    cx = W // 2
    y_bot = 1042
    x0 = max(60, cx - tw // 2 - pad_x)
    x1 = min(W - 60, cx + tw // 2 + pad_x)
    y0 = y_bot - th - pad_y * 2

    bg = (42, 14, 28) if is_warden else (14, 24, 44)
    border = (255, 68, 98) if is_warden else (0, 215, 255)
    fg = (255, 232, 118) if is_warden else (255, 255, 255)

    draw.rounded_rectangle([x0, y0, x1, y_bot], radius=16, fill=bg, outline=border, width=3)
    draw.text(
        (cx - tw // 2, y0 + pad_y - 4),
        text,
        font=f_sub,
        fill=fg,
        stroke_width=3,
        stroke_fill=(12, 16, 28),
    )


def draw_cursor(draw: ImageDraw.ImageDraw, x: float, y: float, click_pulse: float = 0.0) -> None:
    """Draws a crisp vector mouse cursor + optional expanding click ripple."""
    ix, iy = int(x), int(y)
    if click_pulse > 0.0:
        rad = int(12 + 38 * click_pulse)
        draw.ellipse([ix - rad, iy - rad, ix + rad, iy + rad], outline=(0, 229, 255), width=4)
    poly = [
        (ix, iy),
        (ix, iy + 36),
        (ix + 10, iy + 27),
        (ix + 18, iy + 41),
        (ix + 25, iy + 37),
        (ix + 17, iy + 24),
        (ix + 29, iy + 23),
    ]
    draw.polygon(poly, fill=(255, 255, 255), outline=(12, 18, 34))


def draw_voice_equalizer(
    draw: ImageDraw.ImageDraw,
    x0: int,
    y0: int,
    t: float,
    active: bool,
    color: Tuple[int, int, int],
    n_bars: int = 14,
) -> None:
    for i in range(n_bars):
        if active:
            h = int(10 + 28 * abs(math.sin(t * 11.5 + i * 0.72) * math.cos(t * 5.3 + i * 1.1)))
        else:
            h = 6
        bx = x0 + i * 12
        draw.rounded_rectangle([bx, y0 + 38 - h, bx + 7, y0 + 38], radius=3, fill=color)


def draw_ring_arc(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    r: int,
    frac: float,
    color: Tuple[int, int, int],
    width: int = 16,
) -> None:
    box = [cx - r, cy - r, cx + r, cy + r]
    draw.ellipse(box, outline=(42, 62, 96), width=width)
    span = max(2.0, 360.0 * max(0.0, min(1.0, frac)))
    draw.arc(box, start=-90, end=-90 + span, fill=color, width=width)


class Episode023Renderer:
    def __init__(self, manifest: Dict[str, Any]) -> None:
        self.manifest = manifest
        self.segments: List[Dict[str, Any]] = manifest["segments"]
        self.seg_by_id = {s["id"]: s for s in self.segments}
        self.total_dur = float(manifest["exact_duration_sec"])
        self.total_frames = int(manifest["exact_frames_60fps"])

        self.backdrop = make_base_backdrop()
        self.hero_inset = self._prepare_hero_inset()
        self.browser_shell = self._prebuild_browser_shell()
        self.code_card_js = self._prebuild_code_card_js()
        self.code_card_py = self._prebuild_code_card_py()
        self.receipt_lines = [
            "==================================",
            "    CYBER FOCUS WARDEN  v1.0     ",
            "        《今日摸鱼罪证小票》       ",
            "==================================",
            "单号 NO. : CFW-021433-907",
            "签发时间 : 02:14:33 (深夜累犯)",
            "原定任务 : 写完项目代码与复盘报告",
            "----------------------------------",
            "切屏累犯 : 3 次 (触发最高警戒)",
            "摸鱼失焦 : 24.2 秒",
            "赛博功德 : -99  (功德彻底破产)",
            "罪名评级 : 特级摸鱼通缉犯 SSS",
            "----------------------------------",
            "终审判决 : 摸鱼一时爽，赶工火葬场!",
            "           请立刻签字回归专注!",
            "==================================",
            " * 100% 本地离线监工 · 零隐私上传 *",
            "==================================",
        ]

    def _prepare_hero_inset(self) -> Image.Image:
        with Image.open(KLING_HERO_PATH) as im:
            return im.convert("RGB").resize((840, 472), Image.Resampling.LANCZOS)

    def _prebuild_browser_shell(self) -> Image.Image:
        """Pre-renders the high-precision static dark-glass browser frame for Act 3."""
        img = self.backdrop.copy()
        d = ImageDraw.Draw(img)

        # Outer browser frame (x: 76..1844, y: 100..926)
        d.rounded_rectangle([76, 100, 1844, 926], radius=22, fill=(14, 21, 37), outline=(64, 108, 174), width=3)
        # Browser top tab bar
        d.rounded_rectangle([78, 102, 1842, 162], radius=18, fill=(20, 31, 54))
        d.rectangle([78, 142, 1842, 162], fill=(20, 31, 54))
        # Traffic lights
        for idx, col in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
            cx = 112 + idx * 28
            d.ellipse([cx - 8, 124, cx + 8, 140], fill=col)

        # URL bar strip (y: 162..212)
        d.rectangle([78, 162, 1842, 214], fill=(16, 25, 44))
        d.line([(78, 214), (1842, 214)], fill=(45, 72, 118), width=2)
        d.rounded_rectangle([120, 170, 1410, 206], radius=12, fill=(10, 17, 32), outline=(52, 86, 138), width=2)
        d.text((144, 174), "[LOCAL]  http://127.0.0.1:8780/   ·   Cyber Focus Warden (Pure Python Localhost)", font=font(21, False), fill=(156, 214, 255))
        d.rounded_rectangle([1435, 170, 1812, 206], radius=12, fill=(18, 52, 46), outline=(34, 229, 138), width=2)
        d.text((1455, 174), "零摄像头 · 零麦克风 · 本地离线", font=font(20, True), fill=(138, 255, 200))

        return img

    def _prebuild_code_card_js(self) -> Image.Image:
        img = Image.new("RGB", (1020, 710), (13, 20, 36))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, 1019, 709], radius=22, fill=(13, 20, 36), outline=(0, 210, 255), width=3)
        d.rounded_rectangle([3, 3, 1016, 58], radius=18, fill=(22, 34, 58))
        for idx, col in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
            d.ellipse([26 + idx * 26, 22, 40 + idx * 26, 36], fill=col)
        d.text((126, 15), "app/index.html  —  浏览器原生切屏失焦探测器", font=font(24, True), fill=(180, 232, 255))

        code_lines = [
            ("// 1. 监听浏览器切标签页 & 切窗口事件（零权限）", (126, 156, 198)),
            ('document.addEventListener("visibilitychange", () => {', (130, 234, 255)),
            ('  if (document.hidden) handleAwayStart("hidden");', (255, 228, 128)),
            ("  else handleAwayEnd();", (144, 245, 184)),
            ("});", (130, 234, 255)),
            ('window.addEventListener("blur", () => handleAwayStart("blur"));', (130, 234, 255)),
            ("", (120, 140, 170)),
            ("// 2. 失焦计时器：超过 3 秒立刻按累犯次数升级惩罚", (126, 156, 198)),
            ("const awaySec = (Date.now() - state.awayStartedAt) / 1000;", (236, 244, 255)),
            ("if (awaySec >= 3.0 && !state.pendingPenaltyFired) {", (255, 134, 188)),
            ("  state.blurCount += 1;", (255, 228, 128)),
            ("  state.wastedSeconds += awaySec;", (255, 228, 128)),
            ("  const lvl = state.blurCount === 1 ? 1", (144, 245, 184)),
            ("            : state.blurCount === 2 ? 2 : 3;", (144, 245, 184)),
            ("  triggerPenalty(lvl, awaySec);  // 呼叫毒舌监工!", (255, 108, 128)),
            ("}", (255, 134, 188)),
        ]
        f_code = font(24, True)
        f_num = font(21, False)
        for i, (line, col) in enumerate(code_lines):
            y = 84 + i * 38
            d.text((24, y + 2), f"{i + 1:02d}", font=f_num, fill=(84, 112, 152))
            d.text((74, y), line, font=f_code, fill=col)
        return img

    def _prebuild_code_card_py(self) -> Image.Image:
        img = Image.new("RGB", (1020, 710), (13, 20, 36))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, 1019, 709], radius=22, fill=(13, 20, 36), outline=(52, 232, 158), width=3)
        d.rounded_rectangle([3, 3, 1016, 58], radius=18, fill=(22, 34, 58))
        for idx, col in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
            d.ellipse([26 + idx * 26, 22, 40 + idx * 26, 36], fill=col)
        d.text((126, 15), "app/app.py  —  纯标准库 /api/roast & 48条离线毒舌库", font=font(24, True), fill=(156, 255, 206))

        code_lines = [
            ("# 纯 Python 标准库 ThreadingHTTPServer (零三方安装)", (126, 156, 198)),
            ("OFFLINE_ROAST_BANK = {1: [...16条], 2: [...16条], 3: [...16条]}", (255, 228, 128)),
            ("", (120, 140, 170)),
            ("def handle_roast(level, blur_count, wasted_sec, task):", (130, 234, 255)),
            ("    # 1. 若用户配了 OPENAI_API_KEY，优先调真实大模型骂人", (126, 156, 198)),
            ("    roast = call_openai_roast(level, blur_count, wasted_sec)", (144, 245, 184)),
            ("    source = 'openai'", (236, 244, 255)),
            ("    # 2. 未配 Key 或离线：自动秒切本地 3 档 48 条毒舌库", (126, 156, 198)),
            ("    if not roast:", (255, 134, 188)),
            ("        roast = pick_offline_roast(level, history)", (255, 228, 128)),
            ("        source = 'offline'", (236, 244, 255)),
            ("    danmaku = sample_danmaku(5) if level >= 2 else []", (130, 234, 255)),
            ("    return {'level': level, 'roast': roast, 'danmaku': danmaku,", (255, 168, 108)),
            ("            'source': source, 'zero_telemetry': True}", (255, 168, 108)),
            ("", (120, 140, 170)),
            ("# 一行启动: python3 app.py --port 8780", (102, 240, 176)),
        ]
        f_code = font(23, True)
        f_num = font(21, False)
        for i, (line, col) in enumerate(code_lines):
            y = 84 + i * 38
            d.text((24, y + 2), f"{i + 1:02d}", font=f_num, fill=(84, 112, 152))
            d.text((74, y), line, font=f_code, fill=col)
        return img

    def _current_segment(self, t: float) -> Tuple[Dict[str, Any] | None, Dict[str, Any]]:
        active = None
        last_seen = self.segments[0]
        for seg in self.segments:
            if t >= float(seg["start_sec"]):
                last_seen = seg
            if float(seg["start_sec"]) <= t <= float(seg["end_sec"]) + 0.08:
                active = seg
        return active, last_seen

    # ------------------------------------------------------------------
    # ACT 1: Pain-point hook + Hero Reveal
    # ------------------------------------------------------------------
    def render_act1_pain(self, t: float, seg: Dict[str, Any]) -> Image.Image:
        img = self.backdrop.copy()
        d = ImageDraw.Draw(img)
        p = max(0.0, min(1.0, (t - seg["start_sec"]) / max(0.1, seg["duration_sec"])))

        # Left Panel: Giant accelerating Midnight Digital Clock (23:55 -> 02:14)
        d.rounded_rectangle([72, 134, 900, 875], radius=28, fill=(20, 30, 52), outline=(255, 68, 102), width=3)
        d.text((126, 172), "深夜自律翻车现场 · REALITY CHECK", font=font(28, True), fill=(255, 146, 166))

        # Clock accelerates continuously from 23:55 (1435m) to 02:14 (1574m) -> high motion right from frame 0!
        total_mins = int(lerp(23 * 60 + 55, 26 * 60 + 14, ease_in_out(min(1.0, p * 1.15))))
        hh = (total_mins // 60) % 24
        mm = total_mins % 60
        ss = int((t * 17) % 60)
        clock_str = f"{hh:02d}:{mm:02d}:{ss:02d}"
        clock_col = (0, 229, 255) if hh >= 23 else (255, 186, 66) if hh == 0 else (255, 62, 96)

        draw_ring_arc(d, 486, 466, 210, min(1.0, 0.12 + p * 0.88), clock_col, width=20)
        f_clk = font(84, True)
        cb = d.textbbox((0, 0), clock_str, font=f_clk)
        d.text((486 - (cb[2] - cb[0]) // 2, 412), clock_str, font=f_clk, fill=clock_col)
        status_txt = "立下 Flag：就看 5 分钟学习资料" if p < 0.35 else "不知不觉刷掉 2 小时 19 分！！"
        d.text((220, 725), status_txt, font=font(32, True), fill=(255, 232, 138))

        # Animated timeline bar inside left panel
        d.rounded_rectangle([126, 795, 846, 822], radius=12, fill=(32, 46, 76))
        bar_w = int(lerp(90, 720, p))
        d.rounded_rectangle([126, 795, 126 + bar_w, 822], radius=12, fill=clock_col)

        # Right Panel: Browser Tab Stack piling up over "高数复习.pdf"
        d.rounded_rectangle([948, 134, 1848, 875], radius=28, fill=(18, 28, 48), outline=(74, 126, 206), width=3)
        d.text((996, 172), "你的浏览器标签页实时失控记录", font=font(30, True), fill=(154, 224, 255))

        tabs = [
            ("[PDF] 高数复习重点.pdf (原定任务 · 已吃灰)", (38, 64, 108), (168, 214, 255), 0.00),
            ("[HOT] 刷一条就学！超解压热门短片", (88, 44, 92), (255, 198, 255), 0.12),
            ("[FUN] 凌晨两点必看搞笑猫咪合集", (96, 62, 32), (255, 226, 148), 0.32),
            ("[GAME] 下饭操作集锦 · 再看亿集", (34, 78, 88), (144, 248, 255), 0.52),
            ("[FOOD] 深夜放毒美食探店 (彻底沦陷)", (118, 26, 52), (255, 196, 206), 0.72),
        ]
        for idx, (label, bg, fg, appear) in enumerate(tabs):
            prog = ease_out_cubic((p - appear) / 0.18)
            if prog <= 0.01:
                continue
            target_y = 248 + idx * 114
            cur_y = int(lerp(target_y + 110, target_y, prog))
            x_off = int(lerp(180, 0, prog))
            d.rounded_rectangle(
                [996 + x_off, cur_y, 1800, cur_y + 94],
                radius=18,
                fill=bg,
                outline=fg if idx == len(tabs) - 1 else (90, 130, 190),
                width=3,
            )
            d.text((1028 + x_off, cur_y + 26), label, font=font(30, True), fill=fg)

        return img

    def render_act1_reveal(self, t: float, seg: Dict[str, Any]) -> Image.Image:
        img = self.backdrop.copy()
        d = ImageDraw.Draw(img)
        p = max(0.0, min(1.0, (t - seg["start_sec"]) / max(0.1, seg["duration_sec"])))

        # Left column: Big Product Hero Title + 3 Capability Cards
        d.text((86, 138), "CYBER FOCUS WARDEN v1.0", font=font(30, True), fill=(0, 229, 255))
        d.text((82, 186), "赛博防摸鱼", font=font(78, True), fill=(255, 255, 255))
        d.text((82, 276), "毒舌 AI 监工", font=font(78, True), fill=(255, 222, 92))

        features = [
            ("01", "纯 Python 标准库 · 零依赖", "无需配环境，零摄像头零麦克风本地秒启", (0, 229, 255), 0.08),
            ("02", "切屏 3 秒精准抓包", "原生监听 visibilitychange + window.blur", (255, 186, 62), 0.30),
            ("03", "3 级毒舌惩罚 + 罪证小票", "弹幕处刑 → 全屏红蓝通缉令 → 功德 -99 小票", (255, 68, 102), 0.52),
        ]
        for idx, (num, head, desc, col, start_p) in enumerate(features):
            prog = ease_out_cubic((p - start_p) / 0.22)
            if prog <= 0.01:
                continue
            y = 408 + idx * 154
            dx = int(lerp(-140, 0, prog))
            d.rounded_rectangle([84 + dx, y, 896 + dx, y + 130], radius=20, fill=(20, 32, 56), outline=col, width=3)
            d.rounded_rectangle([104 + dx, y + 26, 180 + dx, y + 104], radius=14, fill=col)
            d.text((120 + dx, y + 42), num, font=font(36, True), fill=(10, 18, 32))
            d.text((204 + dx, y + 20), head, font=font(34, True), fill=(255, 255, 255))
            d.text((204 + dx, y + 72), desc, font=font(24, False), fill=(178, 206, 240))

        # Right column: Framed Kling 2K Artwork Preview + Animated Scanner Line
        hx, hy = 966, 178
        d.rounded_rectangle([hx - 14, hy - 14, hx + 854, hy + 590], radius=26, fill=(22, 32, 58), outline=(255, 62, 96), width=4)
        img.paste(self.hero_inset, (hx, hy))
        # Animated scanner sweep across preview
        scan_y = hy + int((t * 140) % 472)
        d.line([(hx, scan_y), (hx + 840, scan_y)], fill=(255, 62, 96), width=4)
        d.rounded_rectangle([hx + 18, hy + 492, hx + 822, hy + 566], radius=14, fill=(44, 16, 32), outline=(255, 76, 108), width=2)
        d.text((hx + 46, hy + 508), "▲ 实测警告：切屏超 3 秒立刻触发全屏红蓝处刑！", font=font(30, True), fill=(255, 232, 130))

        return img

    # ------------------------------------------------------------------
    # ACT 2: Architecture & Real Code Cards
    # ------------------------------------------------------------------
    def render_act2_arch(self, t: float, seg: Dict[str, Any]) -> Image.Image:
        img = self.backdrop.copy()
        d = ImageDraw.Draw(img)
        p = max(0.0, min(1.0, (t - seg["start_sec"]) / max(0.1, seg["duration_sec"])))

        d.text((88, 122), "ZERO-DEPENDENCY LOCAL ARCHITECTURE", font=font(28, True), fill=(52, 232, 158))
        d.text((84, 164), "零三方依赖 · 纯本地离线架构一览", font=font(56, True), fill=(255, 255, 255))

        nodes = [
            (88, 290, 480, 595, "1. 浏览器暗黑前端", "app/index.html", ["• 番茄专注倒计时", "• visibilitychange", "• window.blur 抓包", "• Web Audio 合成音效"], (0, 229, 255)),
            (720, 290, 480, 595, "2. 纯标准库后端", "app/app.py", ["• ThreadingHTTPServer", "• 零 pip 安装依赖", "• POST /api/roast", "• POST /api/receipt"], (52, 232, 158)),
            (1352, 290, 480, 595, "3. 毒舌惩罚引擎", "48条词库 / 可选API", ["• 100% 离线开箱即用", "• Lv.1 温和提醒", "• Lv.2 弹幕 + 功德-1", "• Lv.3 通缉令 + 小票"], (255, 76, 108)),
        ]

        # Animated connecting beams + data packets
        for (x_start, x_end, col) in [(568, 720, (0, 229, 255)), (1200, 1352, (255, 186, 62))]:
            ym = 442
            d.line([(x_start, ym), (x_end, ym)], fill=(64, 96, 148), width=8)
            pkt_x = int(lerp(x_start + 12, x_end - 12, (t * 1.15) % 1.0))
            d.ellipse([pkt_x - 14, ym - 14, pkt_x + 14, ym + 14], fill=col)

        for idx, (nx, ny, nw, nh, title, sub, bullets, col) in enumerate(nodes):
            hl = 1.0 if p >= idx * 0.22 else 0.45
            d.rounded_rectangle([nx, ny, nx + nw, ny + nh], radius=24, fill=(19, 30, 54), outline=col, width=4 if hl > 0.8 else 2)
            d.rounded_rectangle([nx + 24, ny + 24, nx + nw - 24, ny + 106], radius=16, fill=(28, 44, 74))
            d.text((nx + 44, ny + 32), title, font=font(32, True), fill=col)
            d.text((nx + 44, ny + 74), sub, font=font(22, False), fill=(182, 210, 245))
            for bi, btxt in enumerate(bullets):
                d.text((nx + 36, ny + 146 + bi * 54), btxt, font=font(28, True), fill=(238, 246, 255))

        # Bottom Big Emerald Privacy Shield Banner
        d.rounded_rectangle([88, 718, 1832, 868], radius=24, fill=(16, 48, 46), outline=(34, 229, 138), width=4)
        d.text((134, 744), "◆ 绝对隐私保护铁律 · ZERO PERMISSIONS", font=font(34, True), fill=(122, 255, 192))
        d.text((134, 796), "零摄像头权限  ·  零麦克风录音  ·  零云端遥测上传  ·  所有数据留在你的本机 127.0.0.1", font=font(30, True), fill=(232, 255, 244))

        return img

    def render_act2_code_detect(self, t: float, seg: Dict[str, Any]) -> Image.Image:
        img = self.backdrop.copy()
        d = ImageDraw.Draw(img)
        p = max(0.0, min(1.0, (t - seg["start_sec"]) / max(0.1, seg["duration_sec"])))

        # Left: Prebuilt crisp JS code card + animated scanning highlight line
        cx, cy = 72, 138
        img.paste(self.code_card_js, (cx, cy))
        line_idx = int(lerp(1, 14.9, p))
        hy = cy + 80 + line_idx * 38
        d.rounded_rectangle([cx + 14, hy, cx + 1004, hy + 38], radius=8, outline=(0, 229, 255), width=3)

        # Right: Live Detection State Diagram (steady cards, active highlight progresses cleanly)
        rx, rw = 1136, 712
        d.rounded_rectangle([rx, 138, rx + rw, 848], radius=24, fill=(19, 30, 54), outline=(74, 126, 206), width=3)
        d.text((rx + 36, 174), "实时切屏探测流程", font=font(36, True), fill=(0, 229, 255))

        steps = [
            ("STEP 1", "页面正常专注中", "document.hidden === false", (34, 229, 138)),
            ("STEP 2", "用户切去刷视频网页", "触发 visibilitychange / blur", (255, 186, 62)),
            ("STEP 3", "后台精准计时 3.0 秒", "awaySec >= 3.0 立刻锁定证据", (255, 114, 56)),
            ("STEP 4", "累犯计数 + 呼叫监工", "blurCount++ -> POST /api/roast", (255, 56, 94)),
        ]
        active_step = min(3, int(p * 4.2))
        for i, (tag, title, sub, col) in enumerate(steps):
            sy = 250 + i * 144
            is_act = i <= active_step
            d.rounded_rectangle(
                [rx + 36, sy, rx + rw - 36, sy + 114],
                radius=18,
                fill=(30, 46, 78) if is_act else (18, 28, 48),
                outline=col if is_act else (56, 82, 122),
                width=4 if i == active_step else 2,
            )
            d.rounded_rectangle([rx + 56, sy + 24, rx + 178, sy + 88], radius=12, fill=col if is_act else (48, 66, 98))
            d.text((rx + 70, sy + 38), tag, font=font(26, True), fill=(10, 18, 32))
            d.text((rx + 202, sy + 18), title, font=font(30, True), fill=(255, 255, 255) if is_act else (142, 166, 202))
            d.text((rx + 202, sy + 64), sub, font=font(22, False), fill=col if is_act else (112, 134, 168))

        return img

    def render_act2_code_roast(self, t: float, seg: Dict[str, Any]) -> Image.Image:
        img = self.backdrop.copy()
        d = ImageDraw.Draw(img)
        p = max(0.0, min(1.0, (t - seg["start_sec"]) / max(0.1, seg["duration_sec"])))

        cx, cy = 72, 138
        img.paste(self.code_card_py, (cx, cy))
        line_idx = int(lerp(1, 13.9, p))
        hy = cy + 80 + line_idx * 38
        d.rounded_rectangle([cx + 14, hy, cx + 1004, hy + 38], radius=8, outline=(52, 232, 158), width=3)

        # Right: 3-Level Escalating Penalty Ladder
        rx, rw = 1136, 712
        d.rounded_rectangle([rx, 138, rx + rw, 848], radius=24, fill=(19, 30, 54), outline=(52, 232, 158), width=3)
        d.text((rx + 36, 174), "3 级毒舌惩罚状态机", font=font(36, True), fill=(255, 226, 112))

        tiers = [
            ("Lv.1", "失焦 3 秒 · 初级提醒", "柔和警告劝你立刻回头（功德 -5）", (255, 186, 56)),
            ("Lv.2", "二次切屏或超 8 秒", "顶部滚动毒舌弹幕处刑 + 赛博功德 -1", (255, 112, 52)),
            ("Lv.3", "连续累犯 · 终极处刑", "全屏红蓝摸鱼通缉令 + 强制复盘 + 罪证小票", (255, 48, 88)),
        ]
        active_tier = min(2, int(p * 3.4))
        for i, (lv, title, desc, col) in enumerate(tiers):
            sy = 258 + i * 188
            is_act = i <= active_tier
            d.rounded_rectangle(
                [rx + 36, sy, rx + rw - 36, sy + 156],
                radius=20,
                fill=(42, 24, 44) if (i == 2 and is_act) else (28, 44, 76) if is_act else (18, 28, 48),
                outline=col if is_act else (56, 82, 122),
                width=4 if i == active_tier else 2,
            )
            d.rounded_rectangle([rx + 56, sy + 26, rx + 162, sy + 128], radius=16, fill=col)
            d.text((rx + 74, sy + 50), lv, font=font(40, True), fill=(12, 18, 30))
            d.text((rx + 186, sy + 26), title, font=font(32, True), fill=(255, 255, 255))
            d.text((rx + 186, sy + 82), desc, font=font(24, False), fill=(224, 234, 252))

        return img

    # ------------------------------------------------------------------
    # ACT 3: High-Precision Live Browser Simulation of app/index.html
    # ------------------------------------------------------------------
    def _draw_browser_tabs(self, d: ImageDraw.ImageDraw, on_slack_tab: bool) -> None:
        # Tab 1: Cyber Focus Warden
        t1_fill = (28, 46, 82) if not on_slack_tab else (16, 25, 44)
        t1_out = (0, 229, 255) if not on_slack_tab else (54, 78, 118)
        d.rounded_rectangle([206, 112, 620, 158], radius=12, fill=t1_fill, outline=t1_out, width=2)
        d.text((226, 120), "● 赛博防摸鱼毒舌监工 (8780)", font=font(22, True), fill=(240, 248, 255) if not on_slack_tab else (138, 162, 198))

        # Tab 2: Slacking Video Feed
        t2_fill = (82, 26, 54) if on_slack_tab else (16, 25, 44)
        t2_out = (255, 86, 134) if on_slack_tab else (54, 78, 118)
        d.rounded_rectangle([636, 112, 1070, 158], radius=12, fill=t2_fill, outline=t2_out, width=2)
        d.text((656, 120), "▲ 凌晨解压热榜摸鱼视频", font=font(22, True), fill=(255, 222, 234) if on_slack_tab else (138, 162, 198))

    def _draw_warden_dashboard(
        self,
        d: ImageDraw.ImageDraw,
        t: float,
        remain_sec: float,
        total_sec: float,
        running: bool,
        blurs: int,
        wasted: float,
        merit: int,
        level: int,
        roast_badge: str,
        roast_text: str,
        warden_speaking: bool,
        logs: List[Tuple[str, Tuple[int, int, int]]],
        preset_10s: bool = True,
        merit_pop_progress: float = -1.0,
    ) -> None:
        # Perimeter alert aura inside browser content area (x: 84..1836, y: 220..920)
        if level == 1:
            d.rounded_rectangle([84, 220, 1836, 920], radius=16, outline=(255, 186, 52), width=7)
        elif level == 2:
            d.rounded_rectangle([84, 220, 1836, 920], radius=16, outline=(255, 108, 46), width=9)
        elif level >= 3:
            # Smooth sinusoidal breathing crimson <-> cobalt siren aura (ZERO harsh strobing!)
            mix = 0.5 + 0.5 * math.sin(2.0 * math.pi * 1.1 * t)
            col = (int(lerp(255, 45, mix)), int(lerp(42, 110, mix)), int(lerp(85, 255, mix)))
            d.rounded_rectangle([84, 220, 1836, 920], radius=16, outline=col, width=12)

        # LEFT CARD: Pomodoro Focus Core (x: 118..940, y: 242..896)
        d.rounded_rectangle([118, 242, 940, 896], radius=22, fill=(20, 32, 56), outline=(66, 110, 178), width=2)
        d.text((152, 268), "FOCUS REACTOR · 番茄专注引擎", font=font(24, True), fill=(0, 229, 255))

        # Task input box
        d.rounded_rectangle([152, 312, 906, 368], radius=12, fill=(11, 19, 36), outline=(66, 112, 184), width=2)
        d.text((174, 325), "当前任务：写完项目代码与复盘报告", font=font(24, True), fill=(238, 246, 255))

        # Preset chips
        presets = [("25m 标准番茄", not preset_10s), ("15m 快速冲刺", False), ("10s 演示模式", preset_10s)]
        for i, (label, act) in enumerate(presets):
            bx0 = 152 + i * 246
            d.rounded_rectangle(
                [bx0, 386, bx0 + 230, 434],
                radius=24,
                fill=(0, 229, 255) if act else (18, 28, 50),
                outline=(0, 229, 255) if act else (64, 98, 152),
                width=2,
            )
            d.text((bx0 + 36, 396), label, font=font(22, True), fill=(8, 20, 36) if act else (164, 192, 232))

        # Circular Progress Ring
        ring_col = (255, 56, 94) if level >= 3 else (255, 134, 52) if level == 2 else (255, 192, 56) if level == 1 else (0, 229, 255)
        draw_ring_arc(d, 528, 616, 146, remain_sec / max(1.0, total_sec), ring_col, width=16)
        mm, ss = divmod(max(0, int(math.ceil(remain_sec))), 60)
        dig = f"{mm:02d}:{ss:02d}"
        f_dig = font(72, True)
        db = d.textbbox((0, 0), dig, font=f_dig)
        d.text((528 - (db[2] - db[0]) // 2, 564), dig, font=f_dig, fill=(255, 255, 255))
        st_label = "监工已锁定 · 切屏3秒报警" if running else "待机中 · 点击开始专注"
        sb = d.textbbox((0, 0), st_label, font=font(20, False))
        d.text((528 - (sb[2] - sb[0]) // 2, 654), st_label, font=font(20, False), fill=(156, 188, 230))

        # Bottom Control Buttons
        d.rounded_rectangle([188, 804, 488, 864], radius=14, fill=(0, 212, 255) if running else (34, 140, 255))
        d.text((238, 818), "▶ 专注监视运行中" if running else "▶ 开始专注监工", font=font(26, True), fill=(8, 20, 38))
        d.rounded_rectangle([514, 804, 676, 864], radius=14, fill=(32, 48, 80), outline=(80, 120, 184), width=2)
        d.text((558, 818), "|| 暂停", font=font(24, True), fill=(224, 236, 255))
        d.rounded_rectangle([698, 804, 876, 864], radius=14, fill=(214, 38, 76))
        d.text((718, 818), "■ 罪证小票", font=font(24, True), fill=(255, 255, 255))

        # RIGHT CARD: Telemetry + Roast Console + Event Log (x: 970..1804, y: 242..896)
        d.rounded_rectangle([970, 242, 1804, 896], radius=22, fill=(20, 32, 56), outline=(66, 110, 178), width=2)
        d.text((1004, 268), "WARDEN TELEMETRY · 3级状态机", font=font(24, True), fill=(0, 229, 255))
        lv_txt = f"当前状态：Lv.{level} 警戒" if level > 0 else "当前状态：安全 Lv.0"
        d.text((1515, 268), lv_txt, font=font(24, True), fill=ring_col)

        # 3 Stat Boxes
        stats = [
            ("切屏次数", f"{blurs} 次", (255, 192, 56)),
            ("摸鱼秒数", f"{wasted:.1f}s", (255, 76, 108)),
            ("赛博功德", f"{merit}", (255, 56, 94) if merit < 0 else (0, 229, 255)),
        ]
        for i, (lab, val, col) in enumerate(stats):
            sx = 1004 + i * 262
            d.rounded_rectangle([sx, 316, sx + 244, 424], radius=16, fill=(12, 21, 40), outline=(58, 92, 148), width=2)
            d.text((sx + 74, 330), lab, font=font(22, False), fill=(154, 182, 220))
            vb = d.textbbox((0, 0), val, font=font(42, True))
            d.text((sx + 122 - (vb[2] - vb[0]) // 2, 362), val, font=font(42, True), fill=col)

        # Floating "-1" Merit Drop Animation on Lv.2!
        if 0.0 <= merit_pop_progress <= 1.0:
            py = int(lerp(360, 290, merit_pop_progress))
            d.rounded_rectangle([1660, py, 1756, py + 44], radius=10, fill=(235, 32, 72))
            d.text((1682, py + 4), "-1 !", font=font(30, True), fill=(255, 240, 120))

        # Roast Console Box (y: 446..640)
        rc_bg = (52, 14, 28) if level >= 3 else (46, 26, 18) if level == 2 else (38, 34, 18) if level == 1 else (10, 18, 34)
        d.rounded_rectangle([1004, 446, 1770, 646], radius=18, fill=rc_bg, outline=ring_col, width=3)
        d.text((1028, 464), roast_badge, font=font(23, True), fill=ring_col)
        draw_voice_equalizer(d, 1580, 456, t, warden_speaking, ring_col, n_bars=14)

        # Wrap roast text cleanly into 2-3 lines
        f_rt = font(28, True)
        lines: List[str] = []
        cur = ""
        for ch in roast_text:
            if len(cur) >= 24:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
        if cur:
            lines.append(cur)
        for li, ln in enumerate(lines[:3]):
            d.text((1028, 514 + li * 40), ln, font=f_rt, fill=(255, 255, 255))

        # Event Log Box (y: 666..870)
        d.text((1006, 666), "实时抓包黑账日志", font=font(21, True), fill=(154, 188, 232))
        for i, (ltxt, lcol) in enumerate(logs[:4]):
            ly = 702 + i * 44
            d.rounded_rectangle([1004, ly, 1770, ly + 36], radius=8, fill=(13, 22, 40))
            d.rectangle([1004, ly, 1012, ly + 36], fill=lcol)
            d.text((1024, ly + 5), ltxt, font=font(20, False), fill=lcol)

    def _draw_slacking_tab_view(self, d: ImageDraw.ImageDraw, t: float, away_sec: float, target_level: int) -> None:
        """Draws the humorous parody short-video feed when the creator sneaks off-tab + Warden Radar PiP!"""
        # Colorful parody video player card
        d.rounded_rectangle([118, 240, 1260, 892], radius=22, fill=(32, 24, 52), outline=(255, 112, 168), width=3)
        d.rounded_rectangle([152, 272, 1226, 738], radius=18, fill=(52, 34, 84))
        # Animated colorful video waves inside the fake player
        for k in range(6):
            cx = 260 + k * 170
            cy = 490 + int(56 * math.sin(t * 4.5 + k * 0.9))
            d.ellipse([cx - 58, cy - 58, cx + 58, cy + 58], fill=(255 - k * 24, 96 + k * 26, 172))
        d.rounded_rectangle([240, 428, 1138, 570], radius=20, fill=(24, 14, 42), outline=(255, 222, 92), width=3)
        d.text((284, 456), "▶ 凌晨两点超解压摸鱼热榜 · 自动连播中", font=font(38, True), fill=(255, 234, 126))
        d.text((386, 514), "“就看这一条，看完绝对立刻回去学习！”", font=font(26, False), fill=(238, 214, 255))

        # Player scrubbing bar
        d.rounded_rectangle([152, 766, 1226, 784], radius=9, fill=(68, 52, 98))
        d.rounded_rectangle([152, 766, 152 + int(1074 * ((t * 0.25) % 1.0)), 784], radius=9, fill=(255, 92, 148))
        d.text((156, 810), "★ 99.9万赞   ● 弹幕刷屏热议中   ▲ 正在狂消耗你的专注时间", font=font(28, True), fill=(255, 216, 232))

        # Right side: FLOATING WARDEN RADAR PiP counting up away seconds!
        px0, py0, px1, py1 = 1296, 240, 1804, 892
        trig = away_sec >= 3.0
        border_c = (255, 42, 85) if trig else (255, 186, 56)
        d.rounded_rectangle([px0, py0, px1, py1], radius=24, fill=(36, 14, 28) if trig else (22, 30, 54), outline=border_c, width=5)
        d.text((px0 + 36, py0 + 30), "● 后台监工雷达抓包中", font=font(32, True), fill=border_c)
        d.text((px0 + 36, py0 + 82), "visibilitychange: HIDDEN", font=font(24, True), fill=(255, 190, 198))

        # Big radar countdown circle
        draw_ring_arc(d, px0 + 254, py0 + 322, 144, min(1.0, away_sec / 3.0), border_c, width=18)
        sec_str = f"{away_sec:.1f}s"
        sb = d.textbbox((0, 0), sec_str, font=font(78, True))
        d.text((px0 + 254 - (sb[2] - sb[0]) // 2, py0 + 266), sec_str, font=font(78, True), fill=(255, 255, 255))
        d.text((px0 + 148, py0 + 364), "失焦阈值：3.0 秒", font=font(24, True), fill=(255, 218, 128))

        badge = f"▲ 已锁定！准备发射 Lv.{target_level} 惩罚" if trig else f"◆ 倒计时抓包 -> Lv.{target_level} 预警"
        d.rounded_rectangle([px0 + 30, py0 + 530, px1 - 30, py0 + 616], radius=16, fill=(224, 30, 68) if trig else (44, 58, 92))
        d.text((px0 + 48, py0 + 554), badge, font=font(26, True), fill=(255, 250, 210))

    def _draw_danmaku_barrage(self, d: ImageDraw.ImageDraw, elapsed: float) -> None:
        items = [
            ("抓到了！又在偷偷切屏摸鱼！", 122, 0.0, 560, (255, 224, 96), (255, 76, 108)),
            ("赛博功德 -1  -1  -1", 178, 0.4, 620, (255, 134, 148), (255, 52, 86)),
            ("切屏手速堪比职业电竞选手！！", 234, 0.8, 540, (124, 240, 255), (0, 212, 255)),
            ("嘴上说看5分钟，结果看到凌晨2点", 148, 1.5, 590, (255, 242, 168), (255, 168, 56)),
            ("进度条：我真的会谢", 206, 2.2, 640, (162, 255, 198), (34, 229, 138)),
            ("visibilitychange 已经把你卖了！", 262, 2.8, 570, (255, 194, 244), (220, 96, 255)),
            ("前方高能：Lv.3 全屏红蓝警报正在路上", 126, 3.6, 580, (255, 232, 120), (255, 62, 92)),
            ("快滚回去写代码！！！", 188, 4.4, 660, (255, 152, 152), (255, 42, 85)),
        ]
        f_dm = font(30, True)
        for text, y, delay, speed, fg, border in items:
            dt_i = elapsed - delay
            if dt_i < 0:
                continue
            x = int(W + 40 - dt_i * speed)
            if x < -780:
                continue
            bb = d.textbbox((0, 0), text, font=f_dm)
            tw = bb[2] - bb[0]
            d.rounded_rectangle([x - 20, y - 8, x + tw + 24, y + 42], radius=24, fill=(18, 22, 40), outline=border, width=3)
            d.text((x, y), text, font=f_dm, fill=fg)

    def _draw_lv3_modal_and_receipt(
        self,
        d: ImageDraw.ImageDraw,
        t: float,
        elapsed_lv3: float,
        receipt_prog: float,
        warden_speaking: bool,
    ) -> None:
        # Smooth crimson-blue breathing border frame (no harsh full-screen white/black flashes)
        mix = 0.5 + 0.5 * math.sin(2.0 * math.pi * 1.15 * t)
        siren_col = (int(lerp(255, 46, mix)), int(lerp(42, 114, mix)), int(lerp(85, 255, mix)))

        # Center Wanted Modal Card (x: 170..1750, y: 156..912)
        d.rounded_rectangle([170, 156, 1750, 912], radius=28, fill=(18, 22, 40), outline=siren_col, width=8)

        # Left column of modal: Wanted Notice + Oath Input
        d.rounded_rectangle([216, 198, 690, 248], radius=10, fill=(235, 30, 70))
        d.text((238, 206), "▲ LEVEL 3 · FULLSCREEN LOCKDOWN", font=font(24, True), fill=(255, 255, 255))

        d.text((216, 268), "摸鱼通缉令 · 当场抓获！", font=font(56, True), fill=(255, 226, 102))

        d.rounded_rectangle([216, 354, 1010, 560], radius=18, fill=(52, 14, 28), outline=(255, 56, 94), width=3)
        d.text((244, 374), "◆ 毒舌AI监工终极宣判：", font=font(26, True), fill=(255, 166, 182))
        draw_voice_equalizer(d, 800, 368, t, warden_speaking, (255, 68, 104), n_bars=14)
        d.text((244, 424), "连续 3 次切屏累犯！赛博功德暴扣至 -99，", font=font(30, True), fill=(255, 255, 255))
        d.text((244, 472), "全屏强制锁定！当场打印《今日摸鱼罪证小票》！", font=font(30, True), fill=(255, 232, 124))

        # Forced Oath Input Box typing cleanly
        d.text((216, 594), "强制复盘解锁口令（不输完不准关警报）：", font=font(26, True), fill=(180, 208, 244))
        d.rounded_rectangle([216, 642, 1010, 718], radius=14, fill=(10, 18, 34), outline=(0, 229, 255), width=3)
        oath_full = "我立刻回去专注"
        typed_n = int(lerp(0, len(oath_full), max(0.0, min(1.0, (receipt_prog - 0.35) / 0.45))))
        cursor_bar = "|" if int(t * 2.5) % 2 == 0 else ""
        d.text((244, 658), oath_full[:typed_n] + cursor_bar, font=font(34, True), fill=(255, 255, 255))

        d.rounded_rectangle([216, 754, 616, 828], radius=16, fill=(0, 212, 255) if typed_n == len(oath_full) else (54, 72, 106))
        d.text((254, 772), "✓ 签字认错 · 解除锁定", font=font(30, True), fill=(10, 18, 32) if typed_n == len(oath_full) else (154, 176, 208))

        # Right column: Thermal Receipt Printer Slot + Feeding Serrated Paper Receipt!
        rx0, rx1 = 1066, 1698
        # Printer slot bar at top
        d.rounded_rectangle([rx0 - 16, 196, rx1 + 16, 234], radius=12, fill=(36, 46, 68), outline=(108, 134, 178), width=3)
        d.rectangle([rx0 + 8, 210, rx1 - 8, 224], fill=(12, 16, 28))

        # Cream-white thermal paper extending smoothly downward from printer slot
        n_show = max(3, int(lerp(3, len(self.receipt_lines), ease_out_cubic(receipt_prog))))
        paper_h = min(650, 56 + n_show * 33)
        py0, py1 = 224, 224 + paper_h
        d.rectangle([rx0, py0, rx1, py1], fill=(249, 246, 234), outline=(36, 42, 56), width=3)
        # Serrated bottom edge triangles
        for sx in range(rx0, rx1 - 16, 20):
            d.polygon([(sx, py1), (sx + 10, py1 + 12), (sx + 20, py1)], fill=(249, 246, 234))

        f_rec = font(22, True)
        for li in range(n_show):
            line = self.receipt_lines[li]
            col = (210, 26, 62) if ("-99" in line or "SSS" in line or "罪证小票" in line) else (26, 30, 42)
            d.text((rx0 + 24, py0 + 18 + li * 33), line, font=f_rec, fill=col)

        # Bold Crimson Rubber Stamp slamming cleanly into empty right margin of receipt!
        if receipt_prog >= 0.72:
            st_x0, st_y0 = rx0 + 332, py0 + 280
            d.rounded_rectangle(
                [st_x0, st_y0, st_x0 + 278, st_y0 + 102],
                radius=14,
                fill=(255, 240, 242),
                outline=(224, 24, 62),
                width=6,
            )
            d.text((st_x0 + 20, st_y0 + 14), "特级摸鱼通缉犯", font=font(32, True), fill=(224, 24, 62))
            d.text((st_x0 + 44, st_y0 + 58), "SSS · 功德 -99", font=font(25, True), fill=(224, 24, 62))

    def render_act3(self, t: float, seg: Dict[str, Any]) -> Image.Image:
        img = self.browser_shell.copy()
        d = ImageDraw.Draw(img)
        sid = seg["id"]
        p = max(0.0, min(1.0, (t - seg["start_sec"]) / max(0.1, seg["duration_sec"])))

        if sid == "s06_demo_start":
            self._draw_browser_tabs(d, on_slack_tab=False)
            started = p >= 0.38
            remain = 10.0 if not started else max(5.0, 10.0 - (p - 0.38) * 8.0)
            logs = [
                ("[系统就绪] 本地监听 visibilitychange + window.blur", (144, 214, 255)),
            ]
            if started:
                logs.insert(0, ("[00:00] 启动 10s 演示模式 · 进入监工锁定状态！", (122, 255, 192)))
            self._draw_warden_dashboard(
                d, t, remain, 10.0, started, 0, 0.0, 100, 0,
                "● 毒舌监工已上线 · 死盯你的标签页",
                "前五秒表现不错，但我的雷达已经预热完毕，敢切屏试试看？",
                False, logs, preset_10s=(p >= 0.16),
            )
            # Animated cursor clicking 10s preset -> Start button
            if p < 0.25:
                cx, cy = lerp(1100, 745, ease_out_cubic(p / 0.20)), lerp(720, 410, ease_out_cubic(p / 0.20))
                click = max(0.0, (p - 0.16) / 0.09) if p >= 0.16 else 0.0
            elif p < 0.55:
                q = (p - 0.25) / 0.20
                cx, cy = lerp(745, 340, ease_out_cubic(q)), lerp(410, 834, ease_out_cubic(q))
                click = max(0.0, (p - 0.38) / 0.10) if 0.38 <= p <= 0.48 else 0.0
            else:
                cx, cy, click = 340, 834, 0.0
            draw_cursor(d, cx, cy, click)

        elif sid == "s07_demo_switch1":
            switched = p >= 0.22
            self._draw_browser_tabs(d, on_slack_tab=switched)
            if not switched:
                self._draw_warden_dashboard(
                    d, t, 5.0, 10.0, True, 0, 0.0, 100, 0,
                    "● 专注监视中", "正在认真学习……等等，鼠标往哪滑呢？", False,
                    [("[00:05] 专注运行中...", (122, 255, 192))],
                )
                cx = lerp(340, 820, ease_out_cubic(p / 0.22))
                cy = lerp(834, 134, ease_out_cubic(p / 0.22))
                draw_cursor(d, cx, cy, 0.5 if p > 0.18 else 0.0)
            else:
                away = lerp(0.2, 3.4, (p - 0.22) / 0.78)
                self._draw_slacking_tab_view(d, t, away, target_level=1)

        elif sid == "s08_warden_lv1":
            self._draw_browser_tabs(d, on_slack_tab=False)
            self._draw_warden_dashboard(
                d, t, 4.6, 10.0, True, 1, 3.4, 95, 1,
                "▲ Lv.1 初级切屏警告 (离线毒舌库)",
                "检测到切屏去刷摸鱼网页了，快回来！浏览器失焦事件早就把你卖得一干二净！",
                True,
                [
                    ("[Lv.1] 失焦 3.4s 抓包成功！功德 -5", (255, 206, 86)),
                    ("[00:05] 侦测到 visibilitychange: hidden", (255, 178, 96)),
                    ("[00:00] 启动 10s 演示模式", (122, 255, 192)),
                ],
            )
            # Sliding Lv.1 Amber Toast at bottom-right
            slide = ease_out_cubic(min(1.0, p * 4.5))
            ty = int(lerp(960, 774, slide))
            d.rounded_rectangle([1260, ty, 1814, ty + 124], radius=18, fill=(32, 40, 64), outline=(255, 186, 52), width=4)
            d.text((1288, ty + 16), "▲ Lv.1 切屏提醒", font=font(26, True), fill=(255, 196, 64))
            d.text((1288, ty + 58), "检测到切屏去刷摸鱼网页了，快回来！", font=font(24, True), fill=(255, 255, 255))

        elif sid == "s09_demo_switch2":
            switched = p >= 0.42
            self._draw_browser_tabs(d, on_slack_tab=switched)
            if not switched:
                self._draw_warden_dashboard(
                    d, t, 4.2, 10.0, True, 1, 3.4, 95, 1,
                    "▲ Lv.1 初级切屏警告", "再敢切一次屏，马上给你安排 Lv.2 毒舌弹幕公开处刑！", False,
                    [("[Lv.1] 失焦 3.4s 抓包成功！功德 -5", (255, 206, 86))],
                )
                cx = lerp(540, 820, ease_out_cubic(p / 0.42))
                cy = lerp(620, 134, ease_out_cubic(p / 0.42))
                draw_cursor(d, cx, cy, 0.6 if p > 0.36 else 0.0)
            else:
                away = lerp(1.5, 8.6, (p - 0.42) / 0.58)
                self._draw_slacking_tab_view(d, t, away, target_level=2)

        elif sid == "s10_warden_lv2":
            self._draw_browser_tabs(d, on_slack_tab=False)
            merit_pop = p * 2.2 if p < 0.45 else -1.0
            self._draw_warden_dashboard(
                d, t, 3.8, 10.0, True, 2, 12.0, 94, 2,
                "▲ Lv.2 毒舌弹幕拷问 · 功德 -1",
                "二次犯案！启动二级毒舌弹幕处刑，赛博功德减一！切屏手速堪比电竞选手，干正事怎么不见你这么积极？",
                True,
                [
                    ("[Lv.2] 二次累犯(失焦8.6s)！发射毒舌弹幕 + 功德 -1", (255, 138, 76)),
                    ("[Lv.1] 初次失焦 3.4s 抓包警告", (255, 206, 86)),
                    ("[00:00] 启动 10s 演示模式", (122, 255, 192)),
                ],
                merit_pop_progress=merit_pop,
            )
            self._draw_danmaku_barrage(d, t - seg["start_sec"])

        elif sid == "s11_demo_switch3":
            switched = p >= 0.48
            self._draw_browser_tabs(d, on_slack_tab=switched)
            if not switched:
                self._draw_warden_dashboard(
                    d, t, 3.4, 10.0, True, 2, 12.0, 94, 2,
                    "▲ Lv.2 毒舌弹幕拷问", "警告升级！再切一次屏幕将立刻拉响全屏红蓝摸鱼通缉令！", False,
                    [("[Lv.2] 二次累犯！功德 -1", (255, 138, 76))],
                )
                cx = lerp(540, 820, ease_out_cubic(p / 0.48))
                cy = lerp(620, 134, ease_out_cubic(p / 0.48))
                draw_cursor(d, cx, cy, 0.7 if p > 0.42 else 0.0)
            else:
                away = lerp(3.0, 12.2, (p - 0.48) / 0.52)
                self._draw_slacking_tab_view(d, t, away, target_level=3)

        else:
            # s12_warden_lv3 & s13_demo_receipt: Fullscreen Lv.3 Wanted Modal + Receipt Printer!
            self._draw_browser_tabs(d, on_slack_tab=False)
            self._draw_warden_dashboard(
                d, t, 2.0, 10.0, True, 3, 24.2, -99, 3,
                "▲ Lv.3 摸鱼通缉令", "全屏锁定处刑生效！", sid == "s12_warden_lv3",
                [("[Lv.3] 三次累犯！触发全屏摸鱼通缉令 + 罪证小票", (255, 86, 114))],
            )
            s12 = self.seg_by_id["s12_warden_lv3"]
            s13 = self.seg_by_id["s13_demo_receipt"]
            total_lv3_span = max(1.0, s13["end_sec"] - s12["start_sec"])
            elapsed_lv3 = max(0.0, t - s12["start_sec"])
            # Receipt feeds from 28% into s12 through 70% into s13
            receipt_prog = max(0.0, min(1.0, (elapsed_lv3 - 2.2) / (total_lv3_span * 0.65)))
            self._draw_lv3_modal_and_receipt(
                d, t, elapsed_lv3, receipt_prog, warden_speaking=(sid == "s12_warden_lv3")
            )

        return img

    # ------------------------------------------------------------------
    # ACT 4: Open-Source Launch + v2.0 Community CTA
    # ------------------------------------------------------------------
    def render_act4_opensource(self, t: float, seg: Dict[str, Any]) -> Image.Image:
        img = self.backdrop.copy()
        d = ImageDraw.Draw(img)
        p = max(0.0, min(1.0, (t - seg["start_sec"]) / max(0.1, seg["duration_sec"])))

        d.text((88, 126), "100% OPEN SOURCE · MIT LICENSE", font=font(28, True), fill=(34, 229, 138))
        d.text((84, 168), "零安装依赖 · 终端一行命令本地起飞", font=font(56, True), fill=(255, 255, 255))

        # Terminal Window (x: 84..1180, y: 274..856)
        d.rounded_rectangle([84, 274, 1180, 856], radius=24, fill=(11, 17, 31), outline=(34, 229, 138), width=3)
        d.rounded_rectangle([87, 277, 1177, 332], radius=20, fill=(22, 34, 58))
        for idx, col in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
            d.ellipse([114 + idx * 28, 296, 130 + idx * 28, 312], fill=col)
        d.text((220, 290), "bash — cyber-focus-warden/app", font=font(24, True), fill=(182, 224, 255))

        cmd = "$ python3 app.py"
        n_cmd = int(lerp(2, len(cmd), min(1.0, p / 0.22)))
        cur = "█" if int(t * 3) % 2 == 0 else ""
        d.text((126, 370), cmd[:n_cmd] + (cur if p < 0.26 else ""), font=font(42, True), fill=(122, 255, 192))

        term_out = [
            (0.28, "[CyberFocusWarden] Running at http://127.0.0.1:8780/", (0, 229, 255)),
            (0.40, "[CyberFocusWarden] Engine: 100% Offline Built-in Bank", (236, 246, 255)),
            (0.52, "[CyberFocusWarden] Built-in roasts: 48 | Zero Mic / Zero Cam", (255, 226, 112)),
            (0.64, "GET /              -> 200 OK (Dark Glass UI Ready)", (144, 245, 184)),
            (0.76, "POST /api/roast    -> 200 OK (Lv.1 / Lv.2 / Lv.3 Active)", (144, 245, 184)),
            (0.86, "POST /api/receipt  -> 200 OK (《今日摸鱼罪证小票》Ready)", (255, 168, 188)),
        ]
        for idx, (ap, line, col) in enumerate(term_out):
            if p >= ap:
                d.text((126, 456 + idx * 58), line, font=font(27, True), fill=col)

        # Right 3 Open-Source Badges
        cards = [
            ("MIT 开源协议", "源码完全公开，欢迎自由改造与二次整活", (34, 229, 138)),
            ("纯 Python 标准库", "不用 pip install，电脑有 Python3 就能秒跑", (0, 229, 255)),
            ("100% 离线可用", "不联网也能用 48 条毒舌库，零隐私外传", (255, 204, 72)),
        ]
        for i, (head, desc, col) in enumerate(cards):
            cy = 274 + i * 200
            d.rounded_rectangle([1226, cy, 1836, cy + 174], radius=22, fill=(20, 32, 56), outline=col, width=3)
            d.text((1264, cy + 28), head, font=font(36, True), fill=col)
            d.text((1264, cy + 92), desc, font=font(24, False), fill=(224, 236, 255))

        return img

    def render_act4_cta(self, t: float, seg: Dict[str, Any]) -> Image.Image:
        img = self.backdrop.copy()
        d = ImageDraw.Draw(img)
        p = max(0.0, min(1.0, (t - seg["start_sec"]) / max(0.1, seg["duration_sec"])))

        d.text((88, 122), "ROADMAP CO-CREATION · v2.0", font=font(30, True), fill=(255, 204, 72))
        d.text((84, 168), "v2.0 你想给毒舌监工加什么更狠的惩罚？", font=font(60, True), fill=(255, 255, 255))

        ideas = [
            ("脑洞 A", "切屏社死警报铃", "超过 5 秒自动外放高能尴尬语音，室友全听见？", (0, 229, 255), 0.05),
            ("脑洞 B", "硬核惩罚解锁", "累犯三次必须手抄 50 字自律检讨书才能解封？", (255, 168, 62), 0.25),
            ("脑洞 C", "你的终极惩罚脑洞！", "直接写在评论区，最高赞功能写进 v2.0 代码实装！", (255, 62, 98), 0.45),
        ]
        for i, (tag, title, desc, col, ap) in enumerate(ideas):
            prog = ease_out_cubic((p - ap) / 0.22)
            if prog <= 0.01:
                continue
            ix = 88 + i * 594
            dy = int(lerp(90, 0, prog)) + int(6 * math.sin(t * 2.4 + i * 1.4))
            d.rounded_rectangle([ix, 294 + dy, ix + 556, 654 + dy], radius=26, fill=(21, 33, 58), outline=col, width=4)
            d.rounded_rectangle([ix + 34, 330 + dy, ix + 196, 388 + dy], radius=14, fill=col)
            d.text((ix + 58, 338 + dy), tag, font=font(30, True), fill=(10, 18, 32))
            d.text((ix + 34, 424 + dy), title, font=font(42, True), fill=(255, 255, 255))
            # Wrap description cleanly
            d.text((ix + 34, 504 + dy), desc[:15], font=font(28, False), fill=(212, 228, 252))
            if len(desc) > 15:
                d.text((ix + 34, 548 + dy), desc[15:], font=font(28, False), fill=(212, 228, 252))

        # Big High-Contrast CTA Bar
        pulse = 0.5 + 0.5 * math.sin(t * 4.0)
        cta_border = (255, int(lerp(180, 232, pulse)), int(lerp(60, 118, pulse)))
        d.rounded_rectangle([88, 728, 1832, 876], radius=24, fill=(48, 22, 42), outline=cta_border, width=5)
        d.text((156, 764), "★ 评论区留下你的 v2.0 惩罚脑洞  ·  点赞最高直接写进开源代码下期实装！", font=font(38, True), fill=(255, 238, 138))

        return img

    def render_frame(self, frame_idx: int) -> Image.Image:
        t = frame_idx / float(FPS)
        active_seg, cur_seg = self._current_segment(t)
        sid = cur_seg["id"]
        act = int(cur_seg["act"])

        if sid == "s01_hook_pain":
            img = self.render_act1_pain(t, cur_seg)
        elif sid == "s02_hook_reveal":
            img = self.render_act1_reveal(t, cur_seg)
        elif sid == "s03_tech_arch":
            img = self.render_act2_arch(t, cur_seg)
        elif sid == "s04_tech_detect":
            img = self.render_act2_code_detect(t, cur_seg)
        elif sid == "s05_tech_roast":
            img = self.render_act2_code_roast(t, cur_seg)
        elif act == 3:
            img = self.render_act3(t, cur_seg)
        elif sid == "s14_opensource":
            img = self.render_act4_opensource(t, cur_seg)
        else:
            img = self.render_act4_cta(t, cur_seg)

        d = ImageDraw.Draw(img)
        draw_header_hud(d, act, t, self.total_dur)
        draw_subtitle(d, active_seg)
        return img


def choose_h264_encoder() -> List[str]:
    """Prefers h264_nvenc when available on GPU, otherwise crisp libx264."""
    probe = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if "h264_nvenc" in probe.stdout:
        # Quick smoke verify nvenc works in this container
        test = subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=c=0x101726:s=320x180:d=0.1:r=60",
                "-c:v", "h264_nvenc", "-f", "null", "-",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if test.returncode == 0:
            return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "cbr", "-b:v", "7500k", "-maxrate", "9000k", "-bufsize", "15000k"]
    return ["-c:v", "libx264", "-preset", "medium", "-b:v", "7500k", "-maxrate", "9500k", "-bufsize", "15000k"]


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    master_wav = Path(manifest["master_audio_path"])
    assert master_wav.exists(), f"Missing master audio: {master_wav}"

    renderer = Episode023Renderer(manifest)
    v_enc_args = choose_h264_encoder()
    OUT_VIDEO.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{W}x{H}",
        "-r",
        str(FPS),
        "-i",
        "pipe:0",
        "-i",
        str(master_wav),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        *v_enc_args,
        "-vf",
        "setsar=1:1",
        "-aspect",
        "16:9",
        "-pix_fmt",
        "yuv420p",
        "-colorspace",
        "bt709",
        "-color_primaries",
        "bt709",
        "-color_trc",
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
        str(OUT_VIDEO),
    ]

    print(f"Streaming {renderer.total_frames} frames ({renderer.total_dur:.2f}s @ {FPS}fps) using {v_enc_args[1]}...")
    t0 = time.time()
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    try:
        for f_idx in range(renderer.total_frames):
            frame_img = renderer.render_frame(f_idx)
            proc.stdin.write(frame_img.tobytes())
            if (f_idx + 1) % 900 == 0 or f_idx + 1 == renderer.total_frames:
                elapsed = time.time() - t0
                fps_eff = (f_idx + 1) / max(0.01, elapsed)
                print(f"  Rendered {f_idx + 1}/{renderer.total_frames} frames ({fps_eff:.1f} fps, {elapsed:.1f}s)", flush=True)
    finally:
        proc.stdin.close()
        rc = proc.wait()
        if rc != 0:
            raise RuntimeError(f"FFmpeg exited with code {rc}")

    size_mb = OUT_VIDEO.stat().st_size / (1024 * 1024)
    print(f"DONE! Saved {OUT_VIDEO} ({size_mb:.2f} MB) in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
