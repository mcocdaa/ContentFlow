"""100% Headless Zero-Mic Autonomous Bilibili Livestream Engine.

Combines three lightweight CPU/NVENC components with ZERO microphone or hardware audio input:
1. `HeadlessStageRenderer`: 1920x1080 @ 30 FPS Pillow + NumPy broadcast canvas with canonical
   DeepSeek 蓝色大肥鱼 & Gemini娘 sprites, active-speaker glow halo & bounce, animated waveform
   visualizer, live `15 / 1,000 粉` milestone bar, permanent GB 45438-2025 compliance badge,
   right-side sanitized danmaku ticker, and high-contrast wrapped Chinese subtitles.
2. `SyntheticAudioMixer`: 100% synthetic 48 kHz stereo `s16le` PCM generator (`edge-tts` neural
   voices with pure-NumPy dual-pitch melodic fallback when offline) mixed with gently ducked
   synthetic lo-fi ambient BGM (or optional `--bgm-path`) on exact video-frame boundaries
   (`1600` stereo frames = `6400` bytes per 1/30s frame).
3. `HeadlessLiveStreamer`: Single `ffmpeg` subprocess fed via two OS pipes (`os.pipe()` +
   `pass_fds`), auto-detecting `h264_nvenc` CBR 4500k with `libx264` fallback, supporting both
   `dry-stream` (local MP4 proof) and `go-live` (Bilibili RTMP + public danmaku + mandatory
   `try...finally: stop_live` + `HighlightTracker` clip plan export + full stderr scrubbing).
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import logging
import math
import os
import queue
import shutil
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Deque, Dict, Final, List, Literal, Optional, Sequence, Tuple

if TYPE_CHECKING:
    from core.live_studio.world_engine import AutonomousWorldBrain, LiveAgentWorld

import httpx
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from config.settings import (
    DEFAULT_DEEPSEEK_BASE_URL,
    DEFAULT_DEEPSEEK_TTS_URL,
    DEFAULT_DEEPSEEK_TTS_VOICE,
    DEFAULT_FONTS,
)
from core.live_studio.bilibili_live_api import (
    DEFAULT_LIVE_AREA_V2,
    REDACTED_RTMP_TOKEN,
    REDACTED_TOKEN,
    BilibiliLiveController,
    StartLiveResult,
    scrub_rtmp_secrets,
)
from core.live_studio.danmaku import BilibiliDanmakuClient, DanmakuEvent, MockDanmakuSource
from core.live_studio.director import (
    PERSONAS,
    TRIO_CAST,
    DualAILiveDirector,
    PersonaTurn,
    PollSnapshot,
    SpeakerId,
)
from core.live_studio.safety import AI_DISCLOSURE_BANNER, redact_pii

logger = logging.getLogger(__name__)

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent.parent

STAGE_WIDTH: Final[int] = 1920
STAGE_HEIGHT: Final[int] = 1080
DEFAULT_FPS: Final[int] = 30

SAMPLE_RATE: Final[int] = 48000
AUDIO_CHANNELS: Final[int] = 2
BYTES_PER_SAMPLE: Final[int] = 2  # s16le
SAMPLES_PER_VIDEO_FRAME: Final[int] = SAMPLE_RATE // DEFAULT_FPS  # 1600
BYTES_PER_VIDEO_FRAME: Final[int] = SAMPLES_PER_VIDEO_FRAME * AUDIO_CHANNELS * BYTES_PER_SAMPLE  # 6400

DEFAULT_STUDIO_BG_REL: Final[str] = "projects/017_dafeiyu_gemini_channel_war_ep1/assets/cover_clean_studio_bg_16x9.jpg"
CHARACTER_CUTOUT_RELS: Final[Dict[SpeakerId, str]] = {
    "dafeiyu": "library/characters/deepseek_dafeiyu/dafeiyu_canonical_front_cutout.png",
    "gemini": "projects/015_gemini_neko_cyber_worker_vlog/output/cutouts/neko_vlog_hero_cutout.png",
    "yowane": "projects/013_yowane_rooftop_lixicheng_march/output/cutouts/yowane_rooftop_hero_cutout.png",
}
CHARACTER_CANONICAL_RELS: Final[Dict[SpeakerId, str]] = {
    "dafeiyu": "library/characters/deepseek_dafeiyu/dafeiyu_canonical_front.png",
    "gemini": "library/characters/gemini_neko/gemini_canonical_full.png",
    "yowane": "library/characters/yowane_haku/master_reference.jpg",
}

VOICE_MAP: Final[Dict[SpeakerId, str]] = {
    "dafeiyu": "zh-CN-XiaoxiaoNeural",
    "gemini": "zh-CN-XiaoyiNeural",
    "yowane": "zh-TW-HsiaoYuNeural",
}
VOICE_STYLE_MAP: Final[Dict[SpeakerId, Tuple[str, str]]] = {
    "dafeiyu": ("+4%", "-2Hz"),
    "gemini": ("+8%", "+4Hz"),
    "yowane": ("+0%", "-4Hz"),
}

SPEAKER_ACCENT_RGB: Final[Dict[SpeakerId, Tuple[int, int, int]]] = {
    "dafeiyu": (37, 99, 235),
    "gemini": (236, 72, 153),
    "yowane": (124, 58, 237),
}
SPEAKER_EQ_LIGHT_RGB: Final[Dict[SpeakerId, Tuple[int, int, int]]] = {
    "dafeiyu": (56, 189, 248),
    "gemini": (244, 114, 182),
    "yowane": (167, 139, 250),
}
SPEAKER_EQ_PEAK_RGB: Final[Dict[SpeakerId, Tuple[int, int, int]]] = {
    "dafeiyu": (37, 99, 235),
    "gemini": (219, 39, 119),
    "yowane": (109, 40, 217),
}
POLL_BAR_COLORS: Final[Tuple[Tuple[int, int, int], ...]] = (
    (37, 99, 235),
    (236, 72, 153),
    (124, 58, 237),
)

MOOD_LABELS: Final[Dict[str, str]] = {
    "lively": "元气互动",
    "hype": "高能冲榜",
    "teasing": "互怼整活",
    "smug": "4.9★自信",
    "shocked": "破防现场",
    "grateful": "感谢投喂",
    "focused": "策划模式",
}


def _discover_git_main_repo_root(worktree_root: Path) -> Optional[Path]:
    """When running inside a git worktree, locate the main checkout root for gitignored cutouts."""
    dot_git = worktree_root / ".git"
    if not dot_git.is_file():
        return None
    try:
        content = dot_git.read_text(encoding="utf-8").strip()
        if not content.startswith("gitdir:"):
            return None
        gitdir = Path(content.split(":", 1)[1].strip())
        if not gitdir.is_absolute():
            gitdir = (worktree_root / gitdir).resolve()
        # Typical path: <main_repo>/.git/worktrees/<name>
        if gitdir.parent.name == "worktrees" and gitdir.parent.parent.name == ".git":
            candidate = gitdir.parent.parent.parent
            if candidate.is_dir():
                return candidate
    except Exception:
        return None
    return None


def resolve_cjk_font_path(search_dirs: Optional[Sequence[Path]] = None) -> Optional[Path]:
    """Auto-resolve a crisp `NotoSansCJK` (or fallback CJK) font path from `/usr/share/fonts/`."""
    preferred_candidates = [
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"),
        *[Path(p) for p in DEFAULT_FONTS],
    ]
    for candidate in preferred_candidates:
        if candidate.is_file():
            return candidate

    roots = list(search_dirs) if search_dirs is not None else [Path("/usr/share/fonts")]
    bold_match: Optional[Path] = None
    any_noto_match: Optional[Path] = None
    fallback_cjk: Optional[Path] = None
    for root in roots:
        if not root.is_dir():
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            for fname in sorted(filenames):
                lower = fname.lower()
                if not lower.endswith((".ttc", ".ttf", ".otf")):
                    continue
                full = Path(dirpath) / fname
                if "notosanscjk" in lower:
                    if "bold" in lower and bold_match is None:
                        bold_match = full
                    elif any_noto_match is None:
                        any_noto_match = full
                elif any(tok in lower for tok in ("noto", "sourcehan", "wqy", "cjk")) and fallback_cjk is None:
                    fallback_cjk = full
    return bold_match or any_noto_match or fallback_cjk


def _load_font(font_path: Optional[Path], size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if font_path is not None and font_path.is_file():
        try:
            return ImageFont.truetype(str(font_path), size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def _wrap_text_by_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
    max_lines: int = 2,
) -> List[str]:
    """Wrap CJK/Latin mixed text cleanly by measured pixel width."""
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return []
    lines: List[str] = []
    current = ""
    for ch in cleaned:
        trial = current + ch
        if draw.textlength(trial, font=font) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = ch
            if len(lines) >= max_lines:
                break
    if current and len(lines) < max_lines:
        lines.append(current)
    elif current and len(lines) == max_lines:
        last = lines[-1]
        while len(last) > 1 and draw.textlength(last + "…", font=font) > max_width:
            last = last[:-1]
        lines[-1] = last + "…"
    return lines


def detect_video_encoder(ffmpeg_bin: str = "ffmpeg") -> Literal["h264_nvenc", "libx264"]:
    """Auto-detect functional `h264_nvenc` hardware encoder, falling back cleanly to `libx264`."""
    resolved = shutil.which(ffmpeg_bin) or ffmpeg_bin
    try:
        enc_check = subprocess.run(
            [resolved, "-nostdin", "-hide_banner", "-encoders"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if "h264_nvenc" not in (enc_check.stdout or ""):
            return "libx264"
        # Probe with >= 256x256 frame size (NVENC rejects smaller dimensions)
        probe = subprocess.run(
            [
                resolved,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=320x240:d=0.1",
                "-frames:v",
                "1",
                "-c:v",
                "h264_nvenc",
                "-f",
                "null",
                "-",
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=6,
            check=False,
        )
        if probe.returncode == 0:
            return "h264_nvenc"
    except Exception:
        pass
    return "libx264"


# ============================================================================
# 1. HeadlessStageRenderer (Pillow + NumPy, 1920x1080 @ 30 FPS)
# ============================================================================


class HeadlessStageRenderer:
    """High-speed 1920x1080 Pillow + NumPy broadcast canvas renderer for Dual/Trio-AI livestreams."""

    def __init__(
        self,
        *,
        width: int = STAGE_WIDTH,
        height: int = STAGE_HEIGHT,
        fps: int = DEFAULT_FPS,
        repo_root: Optional[Path] = None,
        follower_count: int = 15,
        follower_goal: int = 1000,
        show_title: str = "铁三角AI合租直播 · 大肥鱼 × 弱音 × Gemini娘",
        font_path: Optional[Path] = None,
        cast: Sequence[SpeakerId] = TRIO_CAST,
    ) -> None:
        self.width = width
        self.height = height
        self.fps = max(1, int(fps))
        self._explicit_repo_root = repo_root is not None
        self.repo_root = Path(repo_root) if repo_root is not None else REPO_ROOT
        self._asset_roots: List[Path] = [self.repo_root]
        if not self._explicit_repo_root:
            main_root = _discover_git_main_repo_root(self.repo_root)
            if main_root is not None and main_root not in self._asset_roots:
                self._asset_roots.append(main_root)

        normalized_cast: List[SpeakerId] = []
        for sid in cast:
            if sid in PERSONAS and sid not in normalized_cast:
                normalized_cast.append(sid)
        self.cast: Tuple[SpeakerId, ...] = tuple(normalized_cast) if normalized_cast else TRIO_CAST
        self._is_trio: bool = len(self.cast) >= 3

        self.follower_count = max(0, int(follower_count))
        self.follower_goal = max(1, int(follower_goal))
        self.show_title = scrub_rtmp_secrets(show_title).replace("@", "").strip() or "AI合租演播厅"

        self.font_path: Optional[Path] = font_path or resolve_cjk_font_path()
        self._font_title = _load_font(self.font_path, 24)
        self._font_badge = _load_font(self.font_path, 22)
        self._font_goal_big = _load_font(self.font_path, 24)
        self._font_small = _load_font(self.font_path, 19)
        self._font_nameplate = _load_font(self.font_path, 22)
        self._font_dm_header = _load_font(self.font_path, 23)
        self._font_dm_user = _load_font(self.font_path, 19)
        self._font_dm_body = _load_font(self.font_path, 21)
        self._font_poll_title = _load_font(self.font_path, 20)
        self._font_poll_opt = _load_font(self.font_path, 18)
        self._font_celeb = _load_font(self.font_path, 22)
        self._font_sub_speaker = _load_font(self.font_path, 26)
        self._font_sub_text = _load_font(self.font_path, 34)

        self.loaded_assets: Dict[str, str] = {}

        # Pre-baked layers for sub-10ms per-frame compositing
        self._base_bg = self._build_base_canvas()
        self._sprites: Dict[SpeakerId, Dict[str, Image.Image]] = {
            sid: self._build_character_sprites(sid) for sid in self.cast
        }
        self._milestone_cache_key: Tuple[int, int] = (-1, -1)
        self._milestone_overlay: Optional[Image.Image] = None

        self._subtitle_cache_key: Tuple[int, str, str, str, bool] = (-1, "", "", "", False)
        self._subtitle_overlay: Optional[Image.Image] = None

        self._danmaku_cache_key: Tuple[int, Tuple[Tuple[str, str, str], ...]] = (0, ())
        self._danmaku_overlay: Optional[Image.Image] = None

        self._poll_cache_key: Tuple[Any, ...] = ()
        self._poll_overlay: Optional[Image.Image] = None

        self._celebration_cache_key: str = ""
        self._celebration_overlay: Optional[Image.Image] = None

    def _find_asset(self, rel_path: str) -> Optional[Path]:
        for root in self._asset_roots:
            candidate = root / rel_path
            if candidate.is_file():
                return candidate
        return None

    def _build_bright_gradient_bg(self) -> Image.Image:
        """Bright daylight anime sky-to-studio gradient fallback when BG asset is absent."""
        y_grid = np.linspace(0.0, 1.0, self.height, dtype=np.float32)[:, None]
        x_grid = np.linspace(0.0, 1.0, self.width, dtype=np.float32)[None, :]
        # Soft pastel sky blue -> luminous cream -> lavender-pink horizon
        r = np.clip(195 + 52 * y_grid + 22 * x_grid, 0, 255)
        g = np.clip(226 + 24 * y_grid - 18 * x_grid, 0, 255)
        b = np.clip(255 - 12 * y_grid + 10 * (1.0 - x_grid), 0, 255)
        rgb = np.stack(
            [
                np.broadcast_to(r, (self.height, self.width)),
                np.broadcast_to(g, (self.height, self.width)),
                np.broadcast_to(b, (self.height, self.width)),
            ],
            axis=-1,
        ).astype(np.uint8)
        return Image.fromarray(rgb, mode="RGB")

    def _build_base_canvas(self) -> Image.Image:
        bg_path = self._find_asset(DEFAULT_STUDIO_BG_REL)
        if bg_path is not None:
            try:
                with Image.open(bg_path) as raw_bg:
                    rgb_bg = raw_bg.convert("RGB")
                    # Aspect-preserving cover crop (zero stretching / zero black bars)
                    src_w, src_h = rgb_bg.size
                    scale = max(self.width / src_w, self.height / src_h)
                    new_w = int(round(src_w * scale))
                    new_h = int(round(src_h * scale))
                    resized = rgb_bg.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    left = (new_w - self.width) // 2
                    top = (new_h - self.height) // 2
                    bg = resized.crop((left, top, left + self.width, top + self.height))
                    # Lift slightly for bright high-CTR daylight studio feel
                    bg = ImageEnhance.Brightness(bg).enhance(1.06)
                    bg = ImageEnhance.Color(bg).enhance(1.08)
                    self.loaded_assets["background"] = str(bg_path)
            except Exception as exc:
                logger.warning("Failed to load studio background (%s); using gradient fallback", exc)
                bg = self._build_bright_gradient_bg()
                self.loaded_assets["background"] = "gradient_fallback"
        else:
            bg = self._build_bright_gradient_bg()
            self.loaded_assets["background"] = "gradient_fallback"

        canvas = bg.convert("RGBA")

        # Subtle luminous pastel studio floor & top header frost wash
        wash = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        wdraw = ImageDraw.Draw(wash)
        # Soft bright top bar gradient tint
        wdraw.rectangle([(0, 0), (self.width, 102)], fill=(255, 255, 255, 76))
        # Subtle stage spotlights behind characters
        if self._is_trio:
            wdraw.ellipse([(40, 150), (490, 840)], fill=(56, 189, 248, 34))
            wdraw.ellipse([(460, 150), (910, 840)], fill=(167, 139, 250, 34))
            wdraw.ellipse([(880, 150), (1350, 840)], fill=(244, 114, 182, 34))
        else:
            wdraw.ellipse([(80, 140), (700, 860)], fill=(56, 189, 248, 32))
            wdraw.ellipse([(690, 140), (1330, 860)], fill=(244, 114, 182, 34))
        canvas = Image.alpha_composite(canvas, wash)

        overlay = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # 1) Top-left LIVE show pill
        draw.rounded_rectangle(
            [(28, 18), (585, 84)],
            radius=24,
            fill=(255, 255, 255, 232),
            outline=(59, 130, 246, 220),
            width=3,
        )
        draw.rounded_rectangle([(42, 31), (132, 71)], radius=18, fill=(239, 68, 68, 255))
        draw.ellipse([(53, 45), (65, 57)], fill=(255, 255, 255, 255))
        draw.text((73, 37), "LIVE", font=self._font_badge, fill=(255, 255, 255, 255))
        title_lines = _wrap_text_by_width(draw, self.show_title, self._font_title, max_width=420, max_lines=1)
        draw.text(
            (146, 36),
            title_lines[0] if title_lines else "双AI合租演播厅",
            font=self._font_title,
            fill=(15, 23, 42, 255),
        )

        # 2) Top-right PERMANENT GB 45438-2025 compliance disclosure badge
        badge_text = AI_DISCLOSURE_BANNER
        badge_w = int(draw.textlength(badge_text, font=self._font_badge)) + 54
        badge_x0 = max(1240, self.width - 28 - badge_w)
        draw.rounded_rectangle(
            [(badge_x0, 18), (self.width - 28, 84)],
            radius=24,
            fill=(255, 251, 235, 244),
            outline=(217, 119, 6, 235),
            width=3,
        )
        draw.ellipse([(badge_x0 + 18, 43), (badge_x0 + 32, 57)], fill=(16, 185, 129, 255))
        draw.text((badge_x0 + 42, 37), badge_text, font=self._font_badge, fill=(120, 53, 15, 255))

        # 3) Right-side frosted danmaku panel shell (x=1392..1892, y=106..816)
        draw.rounded_rectangle(
            [(1392, 106), (1892, 816)],
            radius=26,
            fill=(255, 255, 255, 212),
            outline=(148, 163, 184, 190),
            width=3,
        )
        draw.rounded_rectangle(
            [(1410, 122), (1874, 174)],
            radius=16,
            fill=(30, 41, 59, 238),
        )
        draw.text((1430, 134), "实时弹幕 · 互动点单", font=self._font_dm_header, fill=(248, 250, 252, 255))
        draw.text((1736, 138), "AI合规护栏", font=self._font_small, fill=(56, 189, 248, 255))

        # 4) Bottom frosted subtitle dock shell (x=28..1892, y=836..1052)
        draw.rounded_rectangle(
            [(28, 836), (1892, 1052)],
            radius=28,
            fill=(15, 23, 42, 224),
            outline=(255, 255, 255, 190),
            width=3,
        )

        composed = Image.alpha_composite(canvas, overlay)
        return composed.convert("RGB")

    def _make_glow_sprite(self, fg_rgba: Image.Image, glow_rgb: Tuple[int, int, int], pad: int = 24) -> Image.Image:
        """Bake an RGBA character cutout with a crisp outer accent glow halo (computed once at init)."""
        w, h = fg_rgba.size
        out = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
        alpha = fg_rgba.getchannel("A")
        # Outer colored glow
        glow_mask = Image.new("L", (w + pad * 2, h + pad * 2), 0)
        glow_mask.paste(alpha, (pad, pad))
        glow_blur = glow_mask.filter(ImageFilter.GaussianBlur(radius=14))
        glow_layer = Image.new("RGBA", out.size, (*glow_rgb, 255))
        glow_layer.putalpha(glow_blur.point(lambda v: min(230, int(v * 1.15))))
        out = Image.alpha_composite(out, glow_layer)

        # Crisp white inner rim
        rim_blur = glow_mask.filter(ImageFilter.GaussianBlur(radius=3))
        rim_layer = Image.new("RGBA", out.size, (255, 255, 255, 255))
        rim_layer.putalpha(rim_blur.point(lambda v: min(210, int(v * 1.2))))
        out = Image.alpha_composite(out, rim_layer)

        out.paste(fg_rgba, (pad, pad), fg_rgba)
        return out

    def _make_idle_sprite(self, fg_rgba: Image.Image, pad: int = 24) -> Image.Image:
        """Bake a slightly softened inactive sprite with clean subtle shadow."""
        w, h = fg_rgba.size
        rgb = fg_rgba.convert("RGB")
        softened = ImageEnhance.Brightness(rgb).enhance(0.84)
        softened = ImageEnhance.Color(softened).enhance(0.88)
        soft_rgba = softened.convert("RGBA")
        soft_rgba.putalpha(fg_rgba.getchannel("A"))

        out = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
        shadow_mask = Image.new("L", out.size, 0)
        shadow_mask.paste(fg_rgba.getchannel("A"), (pad, pad + 6))
        shadow_blur = shadow_mask.filter(ImageFilter.GaussianBlur(radius=8))
        shadow_layer = Image.new("RGBA", out.size, (15, 23, 42, 255))
        shadow_layer.putalpha(shadow_blur.point(lambda v: int(v * 0.25)))
        out = Image.alpha_composite(out, shadow_layer)
        out.paste(soft_rgba, (pad, pad), soft_rgba)
        return out

    def _make_framed_portrait_card(
        self,
        src_img: Image.Image,
        accent_rgb: Tuple[int, int, int],
        target_size: Tuple[int, int] = (480, 620),
    ) -> Image.Image:
        """Render an opaque canonical portrait into a sleek rounded studio frame card."""
        tw, th = target_size
        rgb = src_img.convert("RGB")
        sw, sh = rgb.size
        # Focus on upper-body portrait framing if very tall
        if sh / max(1, sw) > 1.55:
            rgb = rgb.crop((0, 0, sw, int(sh * 0.72)))
            sw, sh = rgb.size
        scale = max(tw / sw, th / sh)
        nw, nh = int(round(sw * scale)), int(round(sh * scale))
        resized = rgb.resize((nw, nh), Image.Resampling.LANCZOS)
        left = (nw - tw) // 2
        top = max(0, min(nh - th, int((nh - th) * 0.15)))
        cropped = resized.crop((left, top, left + tw, top + th)).convert("RGBA")

        mask = Image.new("L", (tw, th), 0)
        mdraw = ImageDraw.Draw(mask)
        mdraw.rounded_rectangle([(0, 0), (tw - 1, th - 1)], radius=34, fill=255)
        card = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        card.paste(cropped, (0, 0), mask)

        border = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        bdraw = ImageDraw.Draw(border)
        bdraw.rounded_rectangle([(3, 3), (tw - 4, th - 4)], radius=34, outline=(*accent_rgb, 245), width=7)
        return Image.alpha_composite(card, border)

    def _make_vector_avatar_fallback(self, speaker_id: SpeakerId, accent_rgb: Tuple[int, int, int]) -> Image.Image:
        """Zero-asset stylized avatar card so renderer stays functional even in empty test dirs."""
        tw, th = (360, 470) if self._is_trio else (440, 540)
        card = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        draw = ImageDraw.Draw(card)
        draw.rounded_rectangle(
            [(6, 6), (tw - 7, th - 7)],
            radius=34,
            fill=(255, 255, 255, 236),
            outline=(*accent_rgb, 255),
            width=8,
        )
        circle_d = min(220, tw - 140)
        cx0 = (tw - circle_d) // 2
        cy0 = 76
        draw.ellipse([(cx0, cy0), (cx0 + circle_d, cy0 + circle_d)], fill=(*accent_rgb, 220))
        label = PERSONAS[speaker_id].short_name
        w = draw.textlength(label, font=self._font_sub_text)
        draw.text(((tw - w) / 2, cy0 + circle_d + 40), label, font=self._font_sub_text, fill=(15, 23, 42, 255))
        return card

    def _build_character_sprites(self, speaker_id: SpeakerId) -> Dict[str, Image.Image]:
        accent_rgb = SPEAKER_ACCENT_RGB.get(speaker_id, (37, 99, 235))
        cutout_path = self._find_asset(CHARACTER_CUTOUT_RELS[speaker_id])
        canonical_path = self._find_asset(CHARACTER_CANONICAL_RELS[speaker_id])

        fg_rgba: Optional[Image.Image] = None
        if cutout_path is not None:
            try:
                with Image.open(cutout_path) as raw:
                    rgba = raw.convert("RGBA")
                    bbox = rgba.getbbox()
                    if bbox is not None:
                        rgba = rgba.crop(bbox)
                    w, h = rgba.size
                    # Full-body tall cutout -> frame as crisp waist-up VTuber bust matching partner head scale
                    ratio = h / max(1, w)
                    if ratio > 2.0:
                        rgba = rgba.crop((0, 0, w, int(h * 0.59)))
                        w, h = rgba.size
                    elif ratio > 1.45:
                        crop_frac = 0.72 if speaker_id == "yowane" else 0.66
                        rgba = rgba.crop((0, 0, w, int(h * crop_frac)))
                        w, h = rgba.size

                    if self._is_trio:
                        trio_dims: Dict[SpeakerId, Tuple[int, int]] = {
                            "dafeiyu": (575, 370),
                            "yowane": (555, 395),
                            "gemini": (510, 470),
                        }
                        target_h, max_w = trio_dims.get(speaker_id, (560, 390))
                    else:
                        target_h = 700 if speaker_id == "dafeiyu" else 620
                        max_w = 600 if speaker_id == "dafeiyu" else 690
                    scale = min(target_h / max(1, h), max_w / max(1, w))
                    nw = max(1, int(round(w * scale)))
                    nh = max(1, int(round(h * scale)))
                    fg_rgba = rgba.resize((nw, nh), Image.Resampling.LANCZOS)
                    self.loaded_assets[speaker_id] = f"cutout:{cutout_path}"
            except Exception as exc:
                logger.warning("Cutout load failed for %s (%s); trying canonical portrait", speaker_id, exc)

        if fg_rgba is None and canonical_path is not None:
            try:
                with Image.open(canonical_path) as raw:
                    card_size = (370, 520) if self._is_trio else (480, 620)
                    fg_rgba = self._make_framed_portrait_card(raw, accent_rgb, target_size=card_size)
                    self.loaded_assets[speaker_id] = f"canonical:{canonical_path}"
            except Exception as exc:
                logger.warning("Canonical portrait load failed for %s (%s); using vector fallback", speaker_id, exc)

        if fg_rgba is None:
            fg_rgba = self._make_vector_avatar_fallback(speaker_id, accent_rgb)
            self.loaded_assets[speaker_id] = "vector_fallback"

        return {
            "active": self._make_glow_sprite(fg_rgba, accent_rgb, pad=24),
            "idle": self._make_idle_sprite(fg_rgba, pad=24),
        }

    def _get_milestone_overlay(self, follower_count: int, follower_goal: int) -> Image.Image:
        key = (follower_count, follower_goal)
        if self._milestone_overlay is not None and self._milestone_cache_key == key:
            return self._milestone_overlay

        w, h = 580, 68
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle(
            [(0, 0), (w - 1, h - 1)],
            radius=22,
            fill=(255, 255, 255, 236),
            outline=(124, 58, 237, 210),
            width=3,
        )
        pct = min(1.0, max(0.0, follower_count / max(1, follower_goal)))
        label = f"冲千粉目标  {follower_count:,} / {follower_goal:,} 粉"
        draw.text((22, 8), label, font=self._font_goal_big, fill=(30, 41, 59, 255))
        pct_text = f"{pct * 100:.1f}%"
        pct_w = draw.textlength(pct_text, font=self._font_small)
        draw.text((w - 22 - pct_w, 12), pct_text, font=self._font_small, fill=(124, 58, 237, 255))

        bar_x0, bar_y0, bar_x1, bar_y1 = 22, 42, w - 22, 57
        draw.rounded_rectangle([(bar_x0, bar_y0), (bar_x1, bar_y1)], radius=8, fill=(226, 232, 240, 255))
        fill_w = max(24, int((bar_x1 - bar_x0) * pct))
        draw.rounded_rectangle(
            [(bar_x0, bar_y0), (min(bar_x1, bar_x0 + fill_w), bar_y1)],
            radius=8,
            fill=(59, 130, 246, 255),
        )
        self._milestone_cache_key = key
        self._milestone_overlay = img
        return img

    @staticmethod
    def _normalize_poll_snapshot(raw: Optional[PollSnapshot | Dict[str, Any]]) -> Optional[PollSnapshot]:
        if raw is None:
            return None
        if isinstance(raw, PollSnapshot):
            return raw
        if isinstance(raw, dict):
            raw_opts = raw.get("options") or ()
            labels: List[str] = []
            counts: List[int] = []
            for item in raw_opts:
                if isinstance(item, dict):
                    labels.append(str(item.get("label") or ""))
                    counts.append(max(0, int(item.get("votes") or 0)))
                else:
                    labels.append(str(item))
            if not counts and isinstance(raw.get("counts"), (list, tuple)):
                counts = [max(0, int(c)) for c in raw["counts"]]
            if len(labels) < 2 or len(counts) != len(labels):
                return None
            total = sum(counts)
            leader_idx = raw.get("leader_index")
            return PollSnapshot(
                topic=str(raw.get("topic") or "实时弹幕公投"),
                options=tuple(labels[:3]),
                counts=tuple(counts[:3]),
                total_votes=total,
                leader_index=int(leader_idx) if isinstance(leader_idx, int) else None,
                leader_label=str(raw.get("leader_label") or ""),
                recent_surge=bool(raw.get("recent_surge", False)),
            )
        return None

    def _get_poll_overlay(self, snap: PollSnapshot) -> Image.Image:
        key: Tuple[Any, ...] = (snap.topic, snap.options, snap.counts, snap.total_votes, snap.recent_surge)
        if self._poll_overlay is not None and self._poll_cache_key == key:
            return self._poll_overlay

        panel_w = 468
        opt_count = len(snap.options)
        panel_h = 52 + opt_count * 44
        img = Image.new("RGBA", (panel_w, panel_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        border_rgba = (245, 158, 11, 245) if snap.recent_surge else (124, 58, 237, 210)
        bg_rgba = (255, 251, 235, 242) if snap.recent_surge else (245, 243, 255, 240)
        draw.rounded_rectangle(
            [(0, 0), (panel_w - 1, panel_h - 1)],
            radius=18,
            fill=bg_rgba,
            outline=border_rgba,
            width=2,
        )

        # Header row: topic on left, total votes / surge badge on right
        badge_text = f"热度飙升 · {snap.total_votes}票" if snap.recent_surge else f"共 {snap.total_votes} 票"
        badge_bg = (217, 119, 6, 255) if snap.recent_surge else (79, 70, 229, 255)
        badge_w = int(draw.textlength(badge_text, font=self._font_poll_opt)) + 20
        bx0 = panel_w - 12 - badge_w
        draw.rounded_rectangle([(bx0, 8), (panel_w - 12, 34)], radius=12, fill=badge_bg)
        draw.text((bx0 + 10, 10), badge_text, font=self._font_poll_opt, fill=(255, 255, 255, 255))

        topic_clean = redact_pii(snap.topic).replace("@", "").strip() or "实时弹幕公投"
        topic_lines = _wrap_text_by_width(
            draw, topic_clean, self._font_poll_title, max_width=max(120, bx0 - 24), max_lines=1
        )
        draw.text(
            (14, 9),
            topic_lines[0] if topic_lines else "实时弹幕公投",
            font=self._font_poll_title,
            fill=(30, 41, 59, 255),
        )

        # Option rows: high-contrast text above color-coded progress bar
        row_y = 44
        bar_x0, bar_x1 = 14, panel_w - 14
        bar_w = bar_x1 - bar_x0
        for idx, label in enumerate(snap.options):
            votes = snap.counts[idx]
            ratio = (votes / snap.total_votes) if snap.total_votes > 0 else 0.0
            pct_int = int(round(ratio * 100))
            is_leader = snap.total_votes > 0 and snap.leader_index == (idx + 1)
            bar_rgb = POLL_BAR_COLORS[idx % len(POLL_BAR_COLORS)]

            safe_label = redact_pii(label).replace("@", "").strip()[:14]
            left_text = f"扣{idx + 1} {safe_label}"
            right_text = f"{'★ ' if is_leader else ''}{votes}票 ({pct_int}%)"
            right_w = draw.textlength(right_text, font=self._font_poll_opt)
            draw.text((bar_x0, row_y), left_text, font=self._font_poll_opt, fill=(15, 23, 42, 255))
            draw.text(
                (bar_x1 - right_w, row_y),
                right_text,
                font=self._font_poll_opt,
                fill=(*bar_rgb, 255) if is_leader else (71, 85, 105, 255),
            )

            track_y0, track_y1 = row_y + 24, row_y + 35
            draw.rounded_rectangle([(bar_x0, track_y0), (bar_x1, track_y1)], radius=6, fill=(226, 232, 240, 255))
            if votes > 0:
                fill_w = max(14, int(round(bar_w * ratio)))
                draw.rounded_rectangle(
                    [(bar_x0, track_y0), (min(bar_x1, bar_x0 + fill_w), track_y1)],
                    radius=6,
                    fill=(*bar_rgb, 245),
                )
            row_y += 44

        self._poll_cache_key = key
        self._poll_overlay = img
        return img

    def _get_celebration_overlay(self, celebration_text: str) -> Image.Image:
        safe_text = redact_pii(celebration_text).replace("@", "").strip()
        if self._celebration_overlay is not None and self._celebration_cache_key == safe_text:
            return self._celebration_overlay

        w, h = 940, 52
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle(
            [(0, 0), (w - 1, h - 1)],
            radius=24,
            fill=(254, 243, 199, 246),
            outline=(217, 119, 6, 255),
            width=3,
        )
        draw.rounded_rectangle([(14, 9), (132, 43)], radius=15, fill=(217, 119, 6, 255))
        draw.text((28, 13), "涨粉喜报", font=self._font_badge, fill=(255, 255, 255, 255))
        lines = _wrap_text_by_width(draw, safe_text, self._font_celeb, max_width=w - 166, max_lines=1)
        draw.text((146, 13), lines[0] if lines else safe_text, font=self._font_celeb, fill=(120, 53, 15, 255))

        self._celebration_cache_key = safe_text
        self._celebration_overlay = img
        return img

    def _get_danmaku_overlay(self, recent_danmaku: Sequence[Dict[str, Any]], *, panel_h: int = 620) -> Image.Image:
        items: List[Tuple[str, str, str]] = []
        max_cards = 4 if panel_h < 500 else 6
        for row in list(recent_danmaku)[-max_cards:]:
            etype = str(row.get("event_type") or "danmaku")
            user = redact_pii(str(row.get("user_alias") or "热心观众")).replace("@", "").strip()[:12] or "热心观众"
            text = redact_pii(str(row.get("text") or "")).replace("@", "").strip()[:48]
            if text:
                items.append((etype, user, text))
        key = (panel_h, tuple(items))
        if self._danmaku_overlay is not None and self._danmaku_cache_key == key:
            return self._danmaku_overlay

        panel_w = 468
        img = Image.new("RGBA", (panel_w, panel_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        if not items:
            draw.rounded_rectangle(
                [(0, 12), (panel_w - 1, 112)],
                radius=18,
                fill=(241, 245, 249, 225),
                outline=(148, 163, 184, 170),
                width=2,
            )
            draw.text((20, 32), "弹幕互动热身中…", font=self._font_dm_user, fill=(37, 99, 235, 255))
            draw.text(
                (20, 64), "发弹幕扣 1 / 扣 2 / 扣 3 投票下期剧本！", font=self._font_dm_body, fill=(51, 65, 85, 255)
            )
        else:
            y = 6
            for etype, user, text in items:
                if y > panel_h - 82:
                    break
                if etype == "gift":
                    bg_rgba = (254, 243, 199, 242)
                    border_rgba = (245, 158, 11, 235)
                    tag_text = "礼物"
                    tag_bg = (217, 119, 6, 255)
                elif etype == "system":
                    bg_rgba = (254, 249, 195, 244)
                    border_rgba = (234, 179, 8, 240)
                    tag_text = "喜报"
                    tag_bg = (202, 138, 4, 255)
                elif etype == "enter":
                    bg_rgba = (224, 242, 254, 230)
                    border_rgba = (56, 189, 248, 210)
                    tag_text = "进场"
                    tag_bg = (2, 132, 199, 255)
                else:
                    bg_rgba = (248, 250, 252, 236)
                    border_rgba = (148, 163, 184, 190)
                    tag_text = "弹幕"
                    tag_bg = (79, 70, 229, 255)

                wrapped = _wrap_text_by_width(draw, text, self._font_dm_body, max_width=panel_w - 36, max_lines=2)
                card_h = 44 + len(wrapped) * 26
                if y + card_h > panel_h:
                    break
                draw.rounded_rectangle(
                    [(0, y), (panel_w - 1, y + card_h)],
                    radius=16,
                    fill=bg_rgba,
                    outline=border_rgba,
                    width=2,
                )
                draw.rounded_rectangle([(12, y + 9), (66, y + 33)], radius=9, fill=tag_bg)
                draw.text((19, y + 10), tag_text, font=self._font_small, fill=(255, 255, 255, 255))
                draw.text((76, y + 9), user, font=self._font_dm_user, fill=(15, 23, 42, 255))
                ty = y + 38
                for line in wrapped:
                    draw.text((16, ty), line, font=self._font_dm_body, fill=(30, 41, 59, 255))
                    ty += 26
                y += card_h + 9

        self._danmaku_cache_key = key
        self._danmaku_overlay = img
        return img

    def _get_subtitle_overlay(self, turn: Optional[PersonaTurn]) -> Image.Image:
        if turn is None:
            default_line = (
                "欢迎进入铁三角AI合租直播间！大肥鱼、弱音和Gemini娘正在等你扣1/扣2/扣3投票！"
                if self._is_trio
                else "欢迎进入双AI合租直播间！大肥鱼和Gemini娘正在热身开播！"
            )
            key = (0, "dafeiyu", "lively", default_line, False)
            speaker_id: SpeakerId = "dafeiyu"
            speaker_name = PERSONAS["dafeiyu"].display_name
            mood = "lively"
            text = default_line
            is_highlight = False
        else:
            safe_text = redact_pii(turn.text).replace("@", "").strip()
            key = (turn.turn_id, turn.speaker_id, turn.mood, safe_text, turn.is_highlight)
            speaker_id = turn.speaker_id
            speaker_name = turn.speaker_name
            mood = turn.mood
            text = safe_text
            is_highlight = turn.is_highlight

        if self._subtitle_overlay is not None and self._subtitle_cache_key == key:
            return self._subtitle_overlay

        dock_w, dock_h = 1830, 196
        img = Image.new("RGBA", (dock_w, dock_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        accent_rgb = SPEAKER_ACCENT_RGB.get(speaker_id, (37, 99, 235))
        accent = (*accent_rgb, 255)
        name_w = int(draw.textlength(speaker_name, font=self._font_sub_speaker)) + 44
        draw.rounded_rectangle([(0, 4), (name_w, 48)], radius=18, fill=accent)
        draw.text((22, 10), speaker_name, font=self._font_sub_speaker, fill=(255, 255, 255, 255))

        mood_label = MOOD_LABELS.get(mood, "实时互动")
        mood_w = int(draw.textlength(mood_label, font=self._font_small)) + 28
        mx0 = name_w + 14
        draw.rounded_rectangle([(mx0, 8), (mx0 + mood_w, 44)], radius=14, fill=(51, 65, 85, 235))
        draw.text((mx0 + 14, 14), mood_label, font=self._font_small, fill=(226, 232, 240, 255))

        if is_highlight:
            hl_text = "高光时刻"
            hl_w = int(draw.textlength(hl_text, font=self._font_small)) + 28
            hx0 = mx0 + mood_w + 12
            draw.rounded_rectangle([(hx0, 8), (hx0 + hl_w, 44)], radius=14, fill=(245, 158, 11, 245))
            draw.text((hx0 + 14, 14), hl_text, font=self._font_small, fill=(15, 23, 42, 255))

        wrapped = _wrap_text_by_width(draw, text, self._font_sub_text, max_width=dock_w - 28, max_lines=2)
        ty = 66
        for line in wrapped:
            # Crisp subtle drop shadow + luminous white text
            draw.text((12, ty + 2), line, font=self._font_sub_text, fill=(2, 6, 23, 220))
            draw.text((10, ty), line, font=self._font_sub_text, fill=(255, 255, 255, 255))
            ty += 54

        self._subtitle_cache_key = key
        self._subtitle_overlay = img
        return img

    def render_frame(
        self,
        *,
        frame_index: int,
        active_speaker: SpeakerId = "dafeiyu",
        current_turn: Optional[PersonaTurn] = None,
        recent_danmaku: Sequence[Dict[str, Any]] = (),
        audio_level: float = 0.0,
        follower_count: Optional[int] = None,
        follower_goal: Optional[int] = None,
        poll_snapshot: Optional[PollSnapshot | Dict[str, Any]] = None,
        celebration_text: str = "",
    ) -> np.ndarray:
        """Render a single `1920x1080` RGB24 frame (`uint8` ndarray shaped `(1080, 1920, 3)`)."""
        t = frame_index / float(self.fps)
        level = max(0.0, min(1.0, float(audio_level)))
        f_count = self.follower_count if follower_count is None else max(0, int(follower_count))
        f_goal = self.follower_goal if follower_goal is None else max(1, int(follower_goal))
        resolved_active: SpeakerId = active_speaker if active_speaker in self._sprites else self.cast[0]

        frame = self._base_bg.copy()

        # 1) Top-center milestone bar
        milestone = self._get_milestone_overlay(f_count, f_goal)
        frame.paste(milestone, (612, 18), milestone)

        # 2) Characters (draw inactive first, active on top with vertical bounce & glow halo)
        # Stage horizontal anchors keep all characters cleanly left of right-side panel (x < 1370)
        if self._is_trio:
            anchors: Dict[SpeakerId, Tuple[int, int]] = {
                "dafeiyu": (265, 814),
                "yowane": (685, 814),
                "gemini": (1110, 796),
            }
            visual_order: Tuple[SpeakerId, ...] = tuple(
                sid for sid in ("dafeiyu", "yowane", "gemini") if sid in self._sprites
            )
            phase_offsets: Dict[SpeakerId, float] = {"dafeiyu": 0.0, "yowane": 1.1, "gemini": 2.2}
        else:
            anchors = {
                "dafeiyu": (360, 822),
                "gemini": (985, 818),
                "yowane": (685, 818),
            }
            visual_order = self.cast
            phase_offsets = {"dafeiyu": 0.0, "gemini": 1.5, "yowane": 0.8}

        draw_order = [sid for sid in visual_order if sid != resolved_active]
        draw_order.append(resolved_active)

        for sid in draw_order:
            is_active = sid == resolved_active
            sprite = self._sprites[sid]["active" if is_active else "idle"]
            cx, bottom_y = anchors[sid]
            if is_active:
                bounce = int(round(-14.0 * abs(math.sin(t * 5.6)) * (0.28 + 0.72 * level)))
            else:
                bounce = int(round(-3.5 * math.sin(t * 2.1 + phase_offsets.get(sid, 0.0))))
            paste_x = max(12, min(1372 - sprite.width, cx - sprite.width // 2))
            paste_y = max(96, bottom_y - sprite.height + bounce)
            frame.paste(sprite, (paste_x, paste_y), sprite)

        # 2b) Optional golden follower celebration capsule banner over top of left stage
        if celebration_text and celebration_text.strip():
            celeb_overlay = self._get_celebration_overlay(celebration_text)
            frame.paste(celeb_overlay, (216, 96), celeb_overlay)

        # 3) Character nameplate badges
        draw = ImageDraw.Draw(frame)
        for sid in visual_order:
            is_active = sid == resolved_active
            cx, _ = anchors[sid]
            accent = SPEAKER_ACCENT_RGB.get(sid, (37, 99, 235))
            plate_label = f"{PERSONAS[sid].short_name} · {'发言中' if is_active else '待机'}"
            pw = int(draw.textlength(plate_label, font=self._font_nameplate)) + 34
            px0 = cx - pw // 2
            py0 = 782
            fill_rgb = accent if is_active else (51, 65, 85)
            outline_rgb = (255, 255, 255) if is_active else (148, 163, 184)
            draw.rounded_rectangle(
                [(px0, py0), (px0 + pw, py0 + 40)], radius=16, fill=fill_rgb, outline=outline_rgb, width=2
            )
            draw.text((px0 + 17, py0 + 7), plate_label, font=self._font_nameplate, fill=(255, 255, 255))

        # 4) Right-side live poll bar widget (optional) + sanitized danmaku ticker
        norm_poll = self._normalize_poll_snapshot(poll_snapshot)
        if norm_poll is not None:
            poll_overlay = self._get_poll_overlay(norm_poll)
            frame.paste(poll_overlay, (1408, 182), poll_overlay)
            dm_top = 182 + poll_overlay.height + 10
            dm_h = max(180, 808 - dm_top)
            dm_overlay = self._get_danmaku_overlay(recent_danmaku, panel_h=dm_h)
            frame.paste(dm_overlay, (1408, dm_top), dm_overlay)
        else:
            dm_overlay = self._get_danmaku_overlay(recent_danmaku, panel_h=620)
            frame.paste(dm_overlay, (1408, 186), dm_overlay)

        # 5) Bottom wrapped high-contrast Chinese speaker subtitle bar
        sub_overlay = self._get_subtitle_overlay(current_turn)
        frame.paste(sub_overlay, (56, 846), sub_overlay)

        # 6) Animated audio waveform visualizer bars (center stage in dual mode; subtitle console right in trio mode)
        eq_color = SPEAKER_EQ_LIGHT_RGB.get(resolved_active, (56, 189, 248))
        eq_peak = SPEAKER_EQ_PEAK_RGB.get(resolved_active, (37, 99, 235))
        draw = ImageDraw.Draw(frame)
        if self._is_trio:
            bar_count = 22
            bar_w = 8
            bar_gap = 5
            total_eq_w = bar_count * bar_w + (bar_count - 1) * bar_gap
            eq_x0 = 1860 - total_eq_w
            eq_base_y = 892
            max_bar_h = 34.0
        else:
            bar_count = 26
            bar_w = 10
            bar_gap = 6
            total_eq_w = bar_count * bar_w + (bar_count - 1) * bar_gap
            eq_x0 = 678 - total_eq_w // 2
            eq_base_y = 822
            max_bar_h = 56.0

        for idx in range(bar_count):
            dist_center = abs(idx - (bar_count - 1) / 2.0) / ((bar_count - 1) / 2.0)
            envelope = 1.0 - 0.55 * dist_center
            wave = 0.5 + 0.5 * math.sin(t * 11.5 + idx * 0.55)
            h_px = int(6 + (max_bar_h * (0.14 + 0.86 * level) * envelope * (0.35 + 0.65 * wave)))
            bx0 = eq_x0 + idx * (bar_w + bar_gap)
            color = eq_peak if h_px > int(max_bar_h * 0.6) else eq_color
            draw.rounded_rectangle([(bx0, eq_base_y - h_px), (bx0 + bar_w, eq_base_y)], radius=4, fill=color)

        return np.ascontiguousarray(np.asarray(frame, dtype=np.uint8))


# ============================================================================
# 2. SyntheticAudioMixer (100% Synthetic s16le 48kHz Stereo, ZERO Mic)
# ============================================================================


def synthesize_offline_fallback_pcm(
    text: str,
    speaker_id: SpeakerId,
    *,
    sample_rate: int = SAMPLE_RATE,
) -> np.ndarray:
    """Pure-NumPy dual-pitch melodic vocal-cadence synth used when `edge-tts` is offline."""
    clean = "".join(ch for ch in (text or "") if not ch.isspace())
    syllable_count = max(6, min(28, len(clean) // 2 + 4))
    duration_sec = max(1.6, min(5.8, syllable_count * 0.19))
    total_samples = int(round(duration_sec * sample_rate))

    # Distinct pentatonic registers: 大肥鱼 warm mid, Gemini娘 bright upper, 弱音 cool lower-mid
    if speaker_id == "dafeiyu":
        scale_hz = np.array([261.63, 293.66, 329.63, 392.00, 349.23, 329.63], dtype=np.float32)
        pan_l, pan_r = 0.88, 0.72
    elif speaker_id == "yowane":
        scale_hz = np.array([196.00, 220.00, 246.94, 293.66, 261.63, 220.00], dtype=np.float32)
        pan_l, pan_r = 0.80, 0.80
    else:
        scale_hz = np.array([440.00, 493.88, 523.25, 587.33, 659.25, 523.25], dtype=np.float32)
        pan_l, pan_r = 0.72, 0.88

    syllable_len = max(1, total_samples // syllable_count)
    freq_curve = np.empty(total_samples, dtype=np.float32)
    env_curve = np.empty(total_samples, dtype=np.float32)

    for idx in range(syllable_count):
        s0 = idx * syllable_len
        s1 = total_samples if idx == syllable_count - 1 else min(total_samples, s0 + syllable_len)
        seg_n = s1 - s0
        if seg_n <= 0:
            continue
        char_seed = ord(clean[idx % len(clean)]) if clean else idx
        base_f = float(scale_hz[(idx + char_seed) % len(scale_hz)])
        local = np.linspace(0.0, 1.0, seg_n, dtype=np.float32)
        # Subtle pitch inflection + vibrato + soft syllable attack/release
        freq_curve[s0:s1] = base_f * (
            1.0 + 0.03 * np.sin(2.0 * np.pi * local) + 0.008 * np.sin(2.0 * np.pi * 6.0 * local)
        )
        attack = np.clip(local / 0.14, 0.0, 1.0)
        release = np.clip((1.0 - local) / 0.22, 0.0, 1.0)
        env_curve[s0:s1] = attack * release

    phase = np.cumsum(2.0 * np.pi * freq_curve / float(sample_rate), dtype=np.float64).astype(np.float32)
    mono = (
        0.58 * np.sin(phase) + 0.25 * np.sin(2.0 * phase) + 0.11 * np.sin(3.0 * phase) + 0.06 * np.sin(0.5 * phase)
    ) * env_curve
    mono *= 0.42
    stereo = np.stack([mono * pan_l, mono * pan_r], axis=-1).astype(np.float32)
    return stereo


def build_ambient_lofi_bgm_loop(
    *,
    duration_sec: float = 8.0,
    sample_rate: int = SAMPLE_RATE,
) -> np.ndarray:
    """Synthesize a seamless warm lo-fi ambient pad + gentle electric-piano loop (pure NumPy)."""
    total_samples = int(round(duration_sec * sample_rate))
    t = np.arange(total_samples, dtype=np.float32) / float(sample_rate)

    # 4-chord warm progression (Cmaj7 -> Am7 -> Fmaj7 -> G6), 2 seconds per bar
    chords: Tuple[Tuple[float, ...], ...] = (
        (261.63, 329.63, 392.00, 493.88),
        (220.00, 261.63, 329.63, 392.00),
        (174.61, 220.00, 261.63, 329.63),
        (196.00, 246.94, 293.66, 329.63),
    )
    bar_samples = total_samples // len(chords)
    left = np.zeros(total_samples, dtype=np.float32)
    right = np.zeros(total_samples, dtype=np.float32)

    for idx, freqs in enumerate(chords):
        s0 = idx * bar_samples
        s1 = total_samples if idx == len(chords) - 1 else (idx + 1) * bar_samples
        lt = t[s0:s1] - t[s0]
        bar_dur = max(0.01, float(s1 - s0) / float(sample_rate))
        # Crossfade edges so the 8s loop wraps cleanly with zero click
        fade_in = np.clip(lt / 0.12, 0.0, 1.0)
        fade_out = np.clip((bar_dur - lt) / 0.16, 0.0, 1.0)
        pad_env = fade_in * fade_out

        chord_l = np.zeros(s1 - s0, dtype=np.float32)
        chord_r = np.zeros(s1 - s0, dtype=np.float32)
        for n_idx, freq in enumerate(freqs):
            detune = 1.0 + (0.0025 if n_idx % 2 == 0 else -0.0025)
            chord_l += 0.22 * np.sin(2.0 * np.pi * freq * lt)
            chord_r += 0.22 * np.sin(2.0 * np.pi * freq * detune * lt + 0.35)
            # Gentle Rhodes-style plucked harmonic on beat subdivisions
            plucked_env = np.exp(-3.2 * np.maximum(0.0, lt - n_idx * 0.42)) * (lt >= n_idx * 0.42)
            chord_l += 0.12 * plucked_env * np.sin(2.0 * np.pi * (freq * 2.0) * lt)
            chord_r += 0.12 * plucked_env * np.sin(2.0 * np.pi * (freq * 2.0) * lt + 0.4)

        # Warm sub bass root
        bass = 0.24 * np.sin(2.0 * np.pi * (freqs[0] * 0.5) * lt)
        left[s0:s1] = (chord_l + bass) * pad_env
        right[s0:s1] = (chord_r + bass) * pad_env

    stereo = np.stack([left, right], axis=-1)
    peak = float(np.max(np.abs(stereo))) if stereo.size else 1.0
    if peak > 0.0:
        stereo = (stereo / peak) * 0.26
    return stereo.astype(np.float32)


DEEPSEEK_VOICE_MAP: Final[Dict[SpeakerId, str]] = {
    "dafeiyu": "stella",
    "gemini": "stella",
    "yowane": "stella",
}
DEEPSEEK_PAN_MAP: Final[Dict[SpeakerId, Tuple[float, float]]] = {
    "dafeiyu": (0.94, 0.86),
    "gemini": (0.86, 0.94),
    "yowane": (0.90, 0.90),
}
TtsBackendMode = Literal["auto", "deepseek", "edge", "offline"]


class SyntheticAudioMixer:
    """100% synthetic `s16le` 48 kHz stereo PCM mixer locked to exact video-frame slices."""

    def __init__(
        self,
        *,
        sample_rate: int = SAMPLE_RATE,
        channels: int = AUDIO_CHANNELS,
        fps: int = DEFAULT_FPS,
        bgm_path: Optional[Path] = None,
        use_edge_tts: bool = True,
        tts_backend: Optional[TtsBackendMode] = None,
        deepseek_api_key: Optional[str] = None,
        deepseek_tts_url: Optional[str] = None,
        deepseek_voice_map: Optional[Dict[SpeakerId, str]] = None,
        deepseek_http_client: Optional[httpx.AsyncClient] = None,
        ffmpeg_bin: str = "ffmpeg",
        bgm_idle_gain: float = 0.72,
        bgm_duck_gain: float = 0.22,
        speech_gain: float = 0.92,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.fps = max(1, int(fps))
        self.samples_per_frame = self.sample_rate // self.fps
        self.bytes_per_frame = self.samples_per_frame * self.channels * BYTES_PER_SAMPLE

        if tts_backend is None:
            resolved_backend: TtsBackendMode = "edge" if use_edge_tts else "offline"
        else:
            resolved_backend = tts_backend
        self.tts_backend: TtsBackendMode = resolved_backend
        self.use_edge_tts = bool(use_edge_tts) and resolved_backend != "offline"

        resolved_ds_key = (
            deepseek_api_key if deepseek_api_key is not None else (os.getenv("DEEPSEEK_API_KEY") or "")
        ).strip()
        self._deepseek_api_key: str = resolved_ds_key
        explicit_tts_url = deepseek_tts_url or os.getenv("DEEPSEEK_TTS_URL")
        if explicit_tts_url:
            self.deepseek_tts_url = explicit_tts_url.rstrip("/")
        elif os.getenv("DEEPSEEK_BASE_URL"):
            ds_base = (os.getenv("DEEPSEEK_BASE_URL") or DEFAULT_DEEPSEEK_BASE_URL).rstrip("/")
            self.deepseek_tts_url = f"{ds_base}/tools/tts"
        else:
            self.deepseek_tts_url = DEFAULT_DEEPSEEK_TTS_URL
        self._deepseek_voice_map: Dict[SpeakerId, str] = {**DEEPSEEK_VOICE_MAP, **(deepseek_voice_map or {})}
        self._deepseek_http_client = deepseek_http_client
        self._deepseek_lock: Optional[asyncio.Lock] = None
        self._deepseek_lock_loop: Optional[asyncio.AbstractEventLoop] = None

        self.tts_stats: Dict[str, int] = {"deepseek": 0, "edge": 0, "offline": 0}
        self.ffmpeg_bin = shutil.which(ffmpeg_bin) or ffmpeg_bin
        self.bgm_idle_gain = float(bgm_idle_gain)
        self.bgm_duck_gain = float(bgm_duck_gain)
        self.speech_gain = float(speech_gain)

        self._bgm_loop: np.ndarray = self._load_or_build_bgm(bgm_path)
        self._bgm_cursor: int = 0
        self._duck_gain: float = self.bgm_idle_gain
        self.last_bgm_gain: float = self.bgm_idle_gain
        self.last_audio_level: float = 0.0

        self._speech_chunks: Deque[np.ndarray] = deque()
        self._speech_offset: int = 0
        self._speech_total_samples: int = 0
        self._lock = threading.Lock()

    def __repr__(self) -> str:
        return (
            f"SyntheticAudioMixer(sample_rate={self.sample_rate}, fps={self.fps}, "
            f"tts_backend={self.tts_backend!r}, deepseek_configured={bool(self._deepseek_api_key)})"
        )

    def _load_or_build_bgm(self, bgm_path: Optional[Path]) -> np.ndarray:
        if bgm_path is not None:
            candidate = Path(bgm_path)
            if candidate.is_file():
                try:
                    proc = subprocess.run(
                        [
                            self.ffmpeg_bin,
                            "-nostdin",
                            "-hide_banner",
                            "-loglevel",
                            "error",
                            "-i",
                            str(candidate),
                            "-t",
                            "120",
                            "-f",
                            "s16le",
                            "-ar",
                            str(self.sample_rate),
                            "-ac",
                            str(self.channels),
                            "pipe:1",
                        ],
                        stdin=subprocess.DEVNULL,
                        capture_output=True,
                        timeout=20,
                        check=False,
                    )
                    if proc.returncode == 0 and len(proc.stdout) >= self.bytes_per_frame:
                        pcm = np.frombuffer(proc.stdout, dtype="<i2").astype(np.float32) / 32768.0
                        frame_count = len(pcm) // self.channels
                        stereo = pcm[: frame_count * self.channels].reshape(frame_count, self.channels)
                        rms = float(np.sqrt(np.mean(stereo * stereo))) if stereo.size else 0.0
                        if rms > 1e-5:
                            # Normalize custom BGM gently to background bed level (~-19 dBFS)
                            stereo = np.clip(stereo * (0.11 / rms), -0.45, 0.45)
                            return stereo.astype(np.float32)
                except Exception as exc:
                    logger.warning("Custom BGM decode failed (%s); falling back to synthetic lo-fi BGM", exc)
        return build_ambient_lofi_bgm_loop(sample_rate=self.sample_rate)

    async def _decode_mp3_bytes_to_stereo(self, mp3_bytes: bytes) -> Optional[np.ndarray]:
        if not mp3_bytes:
            return None
        proc = await asyncio.create_subprocess_exec(
            self.ffmpeg_bin,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "mp3",
            "-i",
            "pipe:0",
            "-f",
            "s16le",
            "-ar",
            str(self.sample_rate),
            "-ac",
            str(self.channels),
            "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, _stderr = await asyncio.wait_for(proc.communicate(mp3_bytes), timeout=12.0)
        except asyncio.TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            await proc.wait()
            return None
        if proc.returncode != 0 or not stdout:
            return None
        pcm = np.frombuffer(stdout, dtype="<i2").astype(np.float32) / 32768.0
        frame_count = len(pcm) // self.channels
        if frame_count <= 0:
            return None
        stereo = pcm[: frame_count * self.channels].reshape(frame_count, self.channels)
        # Normalize speech loudness cleanly for broadcast clarity
        peak = float(np.max(np.abs(stereo)))
        if peak > 1e-4:
            stereo = stereo * min(1.8, 0.78 / peak)
        return stereo.astype(np.float32)

    def _get_deepseek_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._deepseek_lock is None or self._deepseek_lock_loop is not loop:
            self._deepseek_lock = asyncio.Lock()
            self._deepseek_lock_loop = loop
        return self._deepseek_lock

    def _decode_deepseek_pcm_24k_to_stereo(self, raw_pcm: bytes, speaker_id: SpeakerId) -> Optional[np.ndarray]:
        if len(raw_pcm) < 2400 or len(raw_pcm) % 2 != 0:
            return None
        mono_24k = np.frombuffer(raw_pcm, dtype="<i2").astype(np.float32) / 32768.0
        if mono_24k.size == 0:
            return None
        if self.sample_rate == 24000:
            mono = mono_24k
        else:
            out_len = max(1, int(round(len(mono_24k) * (float(self.sample_rate) / 24000.0))))
            src_idx = np.linspace(0.0, float(len(mono_24k) - 1), out_len, dtype=np.float64)
            mono = np.interp(src_idx, np.arange(len(mono_24k), dtype=np.float64), mono_24k).astype(np.float32)
        peak = float(np.max(np.abs(mono)))
        if peak > 1e-4:
            mono = mono * min(1.8, 0.78 / peak)
        pan_l, pan_r = DEEPSEEK_PAN_MAP.get(speaker_id, (0.90, 0.90))
        return np.stack([mono * pan_l, mono * pan_r], axis=-1).astype(np.float32)

    async def _synthesize_deepseek_tts_pcm(self, safe_text: str, speaker_id: SpeakerId) -> Optional[np.ndarray]:
        if not self._deepseek_api_key:
            return None
        voice_candidate = (
            self._deepseek_voice_map.get(speaker_id) or os.getenv("DEEPSEEK_TTS_VOICE") or DEFAULT_DEEPSEEK_TTS_VOICE
        ).strip()
        voice_id = (
            voice_candidate.lower() if voice_candidate.lower() in {"stella", "tide"} else DEFAULT_DEEPSEEK_TTS_VOICE
        )
        headers = {
            "Authorization": f"Bearer {self._deepseek_api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "text": safe_text,
            "voice_id": voice_id,
            "format": "pcm",
            "filter_markdown": True,
        }

        async with self._get_deepseek_lock():
            last_err: Optional[str] = None
            for attempt in range(2):
                try:
                    if self._deepseek_http_client is not None:
                        resp = await self._deepseek_http_client.post(
                            self.deepseek_tts_url, headers=headers, json=payload, timeout=12.0
                        )
                    else:
                        async with httpx.AsyncClient(timeout=12.0) as client:
                            resp = await client.post(self.deepseek_tts_url, headers=headers, json=payload)

                    if resp.status_code == 400:
                        logger.info("DeepSeek TTS rejected text for %s (HTTP 400)", speaker_id)
                        return None
                    if resp.status_code >= 400:
                        last_err = f"HTTP_{resp.status_code}"
                        if attempt == 0 and resp.status_code in (429, 503, 504):
                            await asyncio.sleep(0.30)
                            continue
                        break

                    decoded = self._decode_deepseek_pcm_24k_to_stereo(bytes(resp.content), speaker_id)
                    if decoded is not None and len(decoded) > self.samples_per_frame:
                        return decoded
                    last_err = "TRUNCATED_PCM"
                except Exception as exc:
                    last_err = type(exc).__name__
                    if attempt == 0:
                        await asyncio.sleep(0.30)
            if last_err:
                logger.info("DeepSeek TTS unavailable for %s (%s); trying fallback", speaker_id, last_err)
        return None

    async def _synthesize_edge_tts_pcm(self, safe_text: str, speaker_id: SpeakerId) -> Optional[np.ndarray]:
        if not self.use_edge_tts:
            return None
        last_exc: Optional[Exception] = None
        for attempt in range(2):
            try:
                import edge_tts

                voice = VOICE_MAP.get(speaker_id, VOICE_MAP["dafeiyu"])
                rate, pitch = VOICE_STYLE_MAP.get(speaker_id, ("+0%", "+0Hz"))
                comm = edge_tts.Communicate(text=safe_text, voice=voice, rate=rate, pitch=pitch)
                mp3_buf = io.BytesIO()
                async with asyncio.timeout(8.0):
                    async for chunk in comm.stream():
                        if chunk.get("type") == "audio":
                            data = chunk.get("data")
                            if isinstance(data, (bytes, bytearray)):
                                mp3_buf.write(data)
                decoded = await self._decode_mp3_bytes_to_stereo(mp3_buf.getvalue())
                if decoded is not None and len(decoded) > self.samples_per_frame:
                    return decoded
            except Exception as exc:
                last_exc = exc
                if attempt == 0:
                    await asyncio.sleep(0.25)
        if last_exc is not None:
            logger.info(
                "edge-tts unavailable for %s (%s); checking next audio fallback",
                speaker_id,
                type(last_exc).__name__,
            )
        return None

    async def synthesize_turn_pcm(self, turn: PersonaTurn) -> np.ndarray:
        """Synthesize a `PersonaTurn` into 48 kHz float32 stereo PCM via DeepSeek/Edge-TTS/offline synth."""
        safe_text = redact_pii(turn.text).replace("@", "").strip()
        if not safe_text:
            self.tts_stats["offline"] = self.tts_stats.get("offline", 0) + 1
            return synthesize_offline_fallback_pcm("欢迎来到AI活工坊", turn.speaker_id, sample_rate=self.sample_rate)

        order: Tuple[str, ...]
        if self.tts_backend == "offline":
            order = ()
        elif self.tts_backend == "edge":
            order = ("edge",)
        elif self.tts_backend == "deepseek":
            order = ("deepseek", "edge") if self.use_edge_tts else ("deepseek",)
        else:
            # auto: give DeepSeek 蓝色大肥鱼 official DeepSeek voice while keeping distinct Edge voices for partners
            if turn.speaker_id == "dafeiyu":
                order = ("deepseek", "edge") if self.use_edge_tts else ("deepseek",)
            else:
                order = ("edge", "deepseek") if self.use_edge_tts else ("deepseek",)

        for provider in order:
            pcm: Optional[np.ndarray] = None
            if provider == "deepseek":
                pcm = await self._synthesize_deepseek_tts_pcm(safe_text, turn.speaker_id)
            elif provider == "edge":
                pcm = await self._synthesize_edge_tts_pcm(safe_text, turn.speaker_id)
            if pcm is not None and len(pcm) > self.samples_per_frame:
                self.tts_stats[provider] = self.tts_stats.get(provider, 0) + 1
                return pcm

        self.tts_stats["offline"] = self.tts_stats.get("offline", 0) + 1
        return synthesize_offline_fallback_pcm(safe_text, turn.speaker_id, sample_rate=self.sample_rate)

    def enqueue_speech(self, pcm_stereo: np.ndarray, *, pad_silence_sec: float = 0.25) -> None:
        """Append float32 stereo speech PCM (plus a brief natural breath pause) to the playout queue."""
        arr = np.asarray(pcm_stereo, dtype=np.float32)
        if arr.ndim == 1:
            arr = np.stack([arr, arr], axis=-1)
        if arr.ndim != 2 or arr.shape[1] != self.channels or arr.shape[0] == 0:
            return
        with self._lock:
            self._speech_chunks.append(arr)
            self._speech_total_samples += int(arr.shape[0])
            pad_samples = int(round(max(0.0, pad_silence_sec) * self.sample_rate))
            if pad_samples > 0:
                self._speech_chunks.append(np.zeros((pad_samples, self.channels), dtype=np.float32))
                self._speech_total_samples += pad_samples

    def speech_remaining_sec(self) -> float:
        with self._lock:
            return self._speech_total_samples / float(self.sample_rate)

    def _pull_bgm_slice(self, n_samples: int) -> np.ndarray:
        loop_len = len(self._bgm_loop)
        end = self._bgm_cursor + n_samples
        if end <= loop_len:
            out = self._bgm_loop[self._bgm_cursor : end]
            self._bgm_cursor = end % loop_len
            return out
        first = self._bgm_loop[self._bgm_cursor :]
        rem = n_samples - len(first)
        parts = [first]
        while rem > 0:
            take = min(rem, loop_len)
            parts.append(self._bgm_loop[:take])
            self._bgm_cursor = take % loop_len
            rem -= take
        return np.concatenate(parts, axis=0)

    def _pull_speech_slice(self, n_samples: int) -> Tuple[np.ndarray, bool]:
        out = np.zeros((n_samples, self.channels), dtype=np.float32)
        filled = 0
        with self._lock:
            while filled < n_samples and self._speech_chunks:
                head = self._speech_chunks[0]
                avail = len(head) - self._speech_offset
                take = min(n_samples - filled, avail)
                out[filled : filled + take] = head[self._speech_offset : self._speech_offset + take]
                filled += take
                self._speech_offset += take
                self._speech_total_samples = max(0, self._speech_total_samples - take)
                if self._speech_offset >= len(head):
                    self._speech_chunks.popleft()
                    self._speech_offset = 0
        has_active_voice = bool(np.max(np.abs(out)) > 1e-4)
        return out, has_active_voice

    def next_video_frame_pcm(self) -> Tuple[bytes, float, bool]:
        """Generate EXACTLY one video frame of mixed 48 kHz stereo `s16le` PCM (`6400` bytes at 30 FPS)."""
        n = self.samples_per_frame
        bgm = self._pull_bgm_slice(n)
        speech, is_speaking = self._pull_speech_slice(n)

        target_gain = self.bgm_duck_gain if is_speaking else self.bgm_idle_gain
        # Smooth ducking ramp across the 33.3ms frame prevents zipper noise or clicks
        gain_ramp = np.linspace(self._duck_gain, target_gain, n, dtype=np.float32)[:, None]
        self._duck_gain = float(self._duck_gain + (target_gain - self._duck_gain) * 0.45)
        self.last_bgm_gain = float(gain_ramp[-1, 0])

        mixed = np.clip(bgm * gain_ramp + speech * self.speech_gain, -0.96, 0.96)
        rms = float(np.sqrt(np.mean(mixed * mixed)))
        speech_rms = float(np.sqrt(np.mean(speech * speech))) if is_speaking else 0.0
        level = min(1.0, max(rms * 2.8, speech_rms * 4.2))
        self.last_audio_level = level

        pcm_i16 = np.round(mixed * 32767.0).astype("<i2")
        pcm_bytes = pcm_i16.tobytes()
        return pcm_bytes, level, is_speaking


# ============================================================================
# 3. HeadlessLiveStreamer (Dual OS-Pipe FFmpeg + Bilibili Lifecycle)
# ============================================================================


StatusCallback = Callable[[str, Dict[str, Any]], Any]


class HeadlessLiveStreamer:
    """Autonomous headless dual-pipe FFmpeg broadcaster supporting `dry-stream` and `go-live`."""

    def __init__(
        self,
        *,
        renderer: Optional[Any] = None,
        audio_mixer: Optional[SyntheticAudioMixer] = None,
        director: Optional[DualAILiveDirector] = None,
        controller: Optional[BilibiliLiveController] = None,
        world: Optional["LiveAgentWorld"] = None,
        world_brain: Optional["AutonomousWorldBrain"] = None,
        ffmpeg_bin: str = "ffmpeg",
        video_encoder: Optional[Literal["h264_nvenc", "libx264"]] = None,
        fps: int = DEFAULT_FPS,
        status_callback: Optional[StatusCallback] = None,
    ) -> None:
        self.fps = max(1, int(fps))
        self.ffmpeg_bin = shutil.which(ffmpeg_bin) or ffmpeg_bin
        self.renderer = renderer or HeadlessStageRenderer(fps=self.fps)
        self.audio_mixer = audio_mixer or SyntheticAudioMixer(fps=self.fps, ffmpeg_bin=self.ffmpeg_bin)
        self.director = director or DualAILiveDirector()
        self.controller = controller
        self.world = world
        self.world_brain = world_brain
        self.video_encoder: Literal["h264_nvenc", "libx264"] = video_encoder or detect_video_encoder(self.ffmpeg_bin)
        self.status_callback = status_callback

        self._stop_event = asyncio.Event()
        self._stderr_lines: Deque[str] = deque(maxlen=120)

    def request_stop(self) -> None:
        """Signal the streaming loop to exit cleanly."""
        self._stop_event.set()

    def _emit_status(self, tag: str, payload: Dict[str, Any]) -> None:
        if self.status_callback is not None:
            self.status_callback(tag, payload)

    def get_scrubbed_stderr(self) -> List[str]:
        """Return captured FFmpeg stderr lines (100% scrubbed of RTMP URLs & secrets)."""
        return list(self._stderr_lines)

    def build_ffmpeg_command(
        self,
        *,
        video_fd: int,
        audio_fd: int,
        mode: Literal["dry-stream", "go-live"],
        output_mp4: Optional[Path] = None,
        rtmp_url: Optional[str] = None,
        record_path: Optional[Path] = None,
        video_encoder: Optional[Literal["h264_nvenc", "libx264"]] = None,
    ) -> List[str]:
        """Build a single dual-pipe `ffmpeg` command (ZERO hardware audio capture)."""
        enc = video_encoder or self.video_encoder
        cmd: List[str] = [
            self.ffmpeg_bin,
            "-nostdin",
            "-y",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-probesize",
            "32",
            "-analyzeduration",
            "0",
            "-thread_queue_size",
            "512",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{self.renderer.width}x{self.renderer.height}",
            "-r",
            str(self.fps),
            "-i",
            f"pipe:{video_fd}",
            "-probesize",
            "32",
            "-analyzeduration",
            "0",
            "-thread_queue_size",
            "512",
            "-f",
            "s16le",
            "-ar",
            str(self.audio_mixer.sample_rate),
            "-ac",
            str(self.audio_mixer.channels),
            "-i",
            f"pipe:{audio_fd}",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
        ]

        if enc == "h264_nvenc":
            cmd.extend(
                [
                    "-c:v",
                    "h264_nvenc",
                    "-preset",
                    "p4",
                    "-rc",
                    "cbr",
                    "-b:v",
                    "4500k",
                    "-maxrate",
                    "4500k",
                    "-bufsize",
                    "9000k",
                    "-g",
                    str(self.fps * 2),
                    "-pix_fmt",
                    "yuv420p",
                ]
            )
        else:
            cmd.extend(
                [
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-tune",
                    "zerolatency",
                    "-b:v",
                    "4500k",
                    "-maxrate",
                    "4500k",
                    "-bufsize",
                    "9000k",
                    "-g",
                    str(self.fps * 2),
                    "-pix_fmt",
                    "yuv420p",
                ]
            )

        cmd.extend(
            [
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-ar",
                str(self.audio_mixer.sample_rate),
                "-ac",
                str(self.audio_mixer.channels),
            ]
        )

        if mode == "dry-stream":
            if output_mp4 is None:
                raise ValueError("output_mp4 is required for dry-stream mode")
            cmd.extend(["-movflags", "+faststart", "-f", "mp4", str(output_mp4)])
        else:
            if not rtmp_url:
                raise ValueError("rtmp_url is required for go-live mode")
            if record_path is not None:
                fmt = "matroska" if record_path.suffix.lower() == ".mkv" else "mp4"
                tee_target = f"[f=flv:onfail=ignore]{rtmp_url}|[f={fmt}]{record_path}"
                cmd.extend(["-flags", "+global_header", "-f", "tee", tee_target])
            else:
                cmd.extend(["-f", "flv", rtmp_url])

        return cmd

    def _spawn_stderr_reader(self, proc: subprocess.Popen[bytes]) -> threading.Thread:
        def _reader() -> None:
            if proc.stderr is None:
                return
            try:
                for raw_line in iter(proc.stderr.readline, b""):
                    decoded = raw_line.decode("utf-8", errors="replace").rstrip()
                    if not decoded:
                        continue
                    safe_line = scrub_rtmp_secrets(decoded)
                    self._stderr_lines.append(safe_line)
                    logger.debug("ffmpeg: %s", safe_line)
            finally:
                with contextlib.suppress(Exception):
                    proc.stderr.close()

        thread = threading.Thread(target=_reader, name="headless-ffmpeg-stderr", daemon=True)
        thread.start()
        return thread

    @staticmethod
    def _spawn_pipe_writer(
        fd: int,
        q: "queue.Queue[Optional[bytes]]",
        name: str,
        error_box: List[BaseException],
    ) -> threading.Thread:
        def _writer() -> None:
            try:
                with os.fdopen(fd, "wb", buffering=0) as fh:
                    while True:
                        chunk = q.get()
                        if chunk is None:
                            break
                        view = memoryview(chunk)
                        written = 0
                        while written < len(view):
                            n = fh.write(view[written:])
                            if n is None or n <= 0:
                                raise BrokenPipeError(f"{name} pipe closed unexpectedly")
                            written += n
            except BaseException as exc:
                error_box.append(exc)
            finally:
                # Drain remaining items so producer cannot block if ffmpeg exited early
                while True:
                    try:
                        q.get_nowait()
                    except queue.Empty:
                        break

        thread = threading.Thread(target=_writer, name=name, daemon=True)
        thread.start()
        return thread

    @staticmethod
    def _write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(f"{path.suffix}.tmp.{os.getpid()}")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, path)

    async def _run_av_pipeline(
        self,
        *,
        mode: Literal["dry-stream", "go-live"],
        duration_sec: float,
        output_mp4: Optional[Path] = None,
        rtmp_url: Optional[str] = None,
        record_path: Optional[Path] = None,
        record_dir: Optional[Path] = None,
        telemetry_ctrl: Optional[BilibiliLiveController] = None,
        telemetry_room_id: Optional[int] = None,
        realtime_pacing: bool = False,
        frame_dump_path: Optional[Path] = None,
        danmaku_source: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Execute the dual-pipe video+audio render & FFmpeg encoding loop."""
        self._stop_event.clear()
        self._stderr_lines.clear()

        if output_mp4 is not None:
            output_mp4.parent.mkdir(parents=True, exist_ok=True)
        if record_path is not None:
            record_path.parent.mkdir(parents=True, exist_ok=True)
        if record_dir is not None:
            record_dir.mkdir(parents=True, exist_ok=True)
        if frame_dump_path is not None:
            frame_dump_path.parent.mkdir(parents=True, exist_ok=True)

        total_frames = max(1, int(round(max(0.5, duration_sec) * self.fps)))
        dump_frame_idx = max(1, min(total_frames - 1, int(total_frames * 0.45)))

        video_r, video_w = os.pipe()
        audio_r, audio_w = os.pipe()
        proc: Optional[subprocess.Popen[bytes]] = None
        video_q: queue.Queue[Optional[bytes]] = queue.Queue(maxsize=4)
        audio_q: queue.Queue[Optional[bytes]] = queue.Queue(maxsize=128)
        pipe_errors: List[BaseException] = []
        writer_threads: List[threading.Thread] = []
        stderr_thread: Optional[threading.Thread] = None
        danmaku_task: Optional[asyncio.Task[None]] = None
        control_task: Optional[asyncio.Task[None]] = None
        synth_task: Optional[asyncio.Task[Tuple[PersonaTurn, np.ndarray]]] = None

        frames_written = 0
        audio_frames_generated = 0
        audio_cur_turn: Optional[PersonaTurn] = None
        current_turn: Optional[PersonaTurn] = None
        active_speaker: SpeakerId = self.director.cast[0]
        dumped_frame = False
        audio_meta_q: Deque[Tuple[float, bool, Optional[PersonaTurn]]] = deque()
        prefill_audio_frames = min(20, total_frames)

        async def _danmaku_pump() -> None:
            if danmaku_source is None:
                return
            try:
                async for ev in danmaku_source.events():
                    if self._stop_event.is_set():
                        break
                    sanitized = self.director.enqueue_event(ev)
                    if sanitized is None:
                        continue
                    if self.world is not None:
                        self.world.handle_danmaku_event(sanitized)
                    if record_dir is not None:
                        inbox_path = record_dir / "danmaku_inbox.jsonl"
                        inbox_row = {
                            "timestamp": sanitized.timestamp,
                            "event_type": sanitized.event_type,
                            "user_alias": sanitized.user_alias,
                            "text": sanitized.text,
                            "gift_name": sanitized.gift_name,
                            "gift_count": sanitized.gift_count,
                        }
                        with inbox_path.open("a", encoding="utf-8") as fh:
                            fh.write(json.dumps(inbox_row, ensure_ascii=False) + "\n")
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning(
                    "Background danmaku reader ended (%s): %s", type(exc).__name__, scrub_rtmp_secrets(str(exc))
                )

        async def _world_control_and_telemetry_loop() -> None:
            cmd_offset = 0
            last_state_write = 0.0
            last_telemetry_poll = -30.0
            brain_interval = max(1.0, float(self.world_brain.interval_sec)) if self.world_brain is not None else 75.0
            last_brain_tick = time.monotonic() - max(0.0, brain_interval - 3.0)
            cmd_path = (record_dir / "agent_commands.jsonl") if record_dir is not None else None
            state_path = (record_dir / "world_state.json") if record_dir is not None else None
            try:
                while not self._stop_event.is_set():
                    now = time.monotonic()
                    # 1) Consume Agent bridge commands incrementally
                    if self.world is not None and cmd_path is not None and cmd_path.is_file():
                        try:
                            with cmd_path.open("r", encoding="utf-8") as fh:
                                fh.seek(cmd_offset)
                                raw_lines = fh.readlines()
                                cmd_offset = fh.tell()
                            for line in raw_lines:
                                stripped = line.strip()
                                if not stripped:
                                    continue
                                try:
                                    cmd_obj = json.loads(stripped)
                                except json.JSONDecodeError:
                                    continue
                                res = self.world.apply_agent_command(cmd_obj)
                                speech_req = res.get("speech_request")
                                if isinstance(speech_req, tuple) and len(speech_req) == 3:
                                    self.director.enqueue_agent_speech(speech_req[0], speech_req[1], speech_req[2])
                                if self.world.stop_requested:
                                    self.request_stop()
                                    break
                        except Exception as exc:
                            logger.debug("Agent command bridge poll skipped (%s)", type(exc).__name__)

                    # 2) Autonomous DeepSeek World Brain periodic engineering & suggestion loop
                    if (
                        self.world is not None
                        and self.world_brain is not None
                        and self.world_brain.has_api_key
                        and (now - last_brain_tick) >= brain_interval
                    ):
                        last_brain_tick = now
                        try:
                            brain_cmds = await self.world_brain.decide_next_actions(self.world.export_state_dict())
                            for bcmd in brain_cmds:
                                if str(bcmd.get("cmd") or "").strip().lower() == "stop":
                                    continue
                                bres = self.world.apply_agent_command(bcmd)
                                speech_req = bres.get("speech_request")
                                if isinstance(speech_req, tuple) and len(speech_req) == 3:
                                    self.director.enqueue_agent_speech(speech_req[0], speech_req[1], speech_req[2])
                        except Exception as exc:
                            logger.debug("AutonomousWorldBrain loop skipped (%s)", type(exc).__name__)

                    # 3) Poll Bilibili live telemetry every 30s during go-live
                    if (
                        mode == "go-live"
                        and telemetry_ctrl is not None
                        and telemetry_room_id is not None
                        and telemetry_room_id > 0
                        and (now - last_telemetry_poll) >= 30.0
                    ):
                        last_telemetry_poll = now
                        try:
                            tel = await asyncio.to_thread(telemetry_ctrl.get_live_telemetry, telemetry_room_id)
                            if tel.get("ok"):
                                att = int(tel.get("attention") or 0)
                                if att > self.director.follower_count:
                                    self.director.notify_follower_count(att)
                                if self.world is not None:
                                    self.world.update_telemetry(
                                        online=tel.get("online"),
                                        watched_num=tel.get("watched_num"),
                                        watched_text=tel.get("watched_text"),
                                        follower_count=att if att > 0 else None,
                                    )
                        except Exception as exc:
                            logger.debug("Telemetry poll skipped (%s)", type(exc).__name__)

                    # 4) Write atomic world_state.json every 2.0s
                    if self.world is not None and state_path is not None and (now - last_state_write) >= 2.0:
                        last_state_write = now
                        with contextlib.suppress(Exception):
                            self._write_json_atomic(state_path, self.world.export_state_dict())

                    await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                return

        async def _prepare_next_turn() -> Tuple[PersonaTurn, np.ndarray]:
            turn = await self.director.next_turn(wait_timeout=0.0)
            pcm = await self.audio_mixer.synthesize_turn_pcm(turn)
            return turn, pcm

        async def _produce_one_audio_frame() -> None:
            nonlocal audio_frames_generated, audio_cur_turn, synth_task
            if synth_task is not None and synth_task.done() and self.audio_mixer.speech_remaining_sec() <= 0.08:
                next_turn, next_pcm = synth_task.result()
                synth_task = None
                audio_cur_turn = next_turn
                self.audio_mixer.enqueue_speech(next_pcm, pad_silence_sec=0.35)
            elif synth_task is None and self.audio_mixer.speech_remaining_sec() < 1.2:
                if realtime_pacing:
                    synth_task = asyncio.create_task(_prepare_next_turn(), name="headless-turn-synth")
                elif self.audio_mixer.speech_remaining_sec() <= 0.08:
                    next_turn, next_pcm = await _prepare_next_turn()
                    audio_cur_turn = next_turn
                    self.audio_mixer.enqueue_speech(next_pcm, pad_silence_sec=0.35)

            pcm_bytes, audio_level, is_speaking = self.audio_mixer.next_video_frame_pcm()
            audio_meta_q.append((audio_level, is_speaking, audio_cur_turn))
            await asyncio.to_thread(audio_q.put, pcm_bytes)
            audio_frames_generated += 1

        try:
            # Seed initial rehearsal danmaku + live poll votes in dry-stream so stage widgets are immediately lively
            if mode == "dry-stream":
                if self.world is not None:
                    dry_seed_events = [
                        DanmakuEvent(event_type="enter", user_alias="熬夜写代码的小蓝", text="进入了直播间"),
                        DanmakuEvent(event_type="danmaku", user_alias="早八工友", text="开工"),
                        DanmakuEvent(event_type="danmaku", user_alias="摸鱼架构师", text="写代码"),
                        DanmakuEvent(event_type="danmaku", user_alias="灵感提供者", text="建议 加个夜间霓虹模式"),
                        DanmakuEvent(
                            event_type="gift",
                            user_alias="机房投喂官",
                            text="投喂了 小心心 x2",
                            gift_name="小心心",
                            gift_count=2,
                        ),
                    ]
                else:
                    dry_seed_events = [
                        DanmakuEvent(event_type="enter", user_alias="熬夜写代码的小蓝", text="进入了直播间"),
                        DanmakuEvent(
                            event_type="danmaku", user_alias="鱼粉一号", text="扣1 支持大肥鱼继续吐槽24G内存！"
                        ),
                        DanmakuEvent(
                            event_type="danmaku", user_alias="封面颜控", text="扣2 Gemini娘4.9星高明度封面必胜！"
                        ),
                        DanmakuEvent(
                            event_type="danmaku",
                            user_alias="财务旁听生",
                            text="扣3 弱音大姐头冷面查账太好笑了，快评评理！",
                        ),
                        DanmakuEvent(
                            event_type="gift",
                            user_alias="机房投喂官",
                            text="投喂了 小心心 x3",
                            gift_name="小心心",
                            gift_count=3,
                        ),
                    ]
                seed_source = MockDanmakuSource(
                    interval_sec=0.0, max_events=len(dry_seed_events), custom_events=dry_seed_events
                )
                async for ev in seed_source.events():
                    enq = self.director.enqueue_event(ev)
                    if enq is not None and self.world is not None:
                        self.world.handle_danmaku_event(enq)
                await seed_source.close()

            # Pre-synthesize opening turn before spawning ffmpeg so frame 0 starts speaking immediately
            opening_turn, opening_pcm = await _prepare_next_turn()
            audio_cur_turn = opening_turn
            current_turn = opening_turn
            active_speaker = opening_turn.speaker_id
            self.audio_mixer.enqueue_speech(opening_pcm, pad_silence_sec=0.35)

            cmd = self.build_ffmpeg_command(
                video_fd=video_r,
                audio_fd=audio_r,
                mode=mode,
                output_mp4=output_mp4,
                rtmp_url=rtmp_url,
                record_path=record_path,
            )

            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                pass_fds=(video_r, audio_r),
            )
            # Parent immediately closes read ends so EOF propagates cleanly on shutdown
            os.close(video_r)
            video_r = -1
            os.close(audio_r)
            audio_r = -1

            stderr_thread = self._spawn_stderr_reader(proc)
            writer_threads = [
                self._spawn_pipe_writer(video_w, video_q, "headless-video-writer", pipe_errors),
                self._spawn_pipe_writer(audio_w, audio_q, "headless-audio-writer", pipe_errors),
            ]
            # Ownership of write FDs transferred to writer threads
            video_w = -1
            audio_w = -1

            if danmaku_source is not None:
                danmaku_task = asyncio.create_task(_danmaku_pump(), name="headless-danmaku-pump")
            if self.world is not None or (mode == "go-live" and telemetry_ctrl is not None and telemetry_room_id):
                control_task = asyncio.create_task(_world_control_and_telemetry_loop(), name="headless-world-control")

            # Pre-fill audio lead (~20 frames = 128 KiB) so FFmpeg opens rawvideo + s16le with zero pipe deadlock
            for _ in range(prefill_audio_frames):
                await _produce_one_audio_frame()

            start_mono = time.monotonic()

            for frame_idx in range(total_frames):
                if self._stop_event.is_set():
                    break
                if proc.poll() is not None:
                    raise RuntimeError(
                        f"ffmpeg exited prematurely with code {proc.returncode}: "
                        + " | ".join(list(self._stderr_lines)[-4:])
                    )
                if pipe_errors:
                    raise RuntimeError(f"Pipe write error: {scrub_rtmp_secrets(str(pipe_errors[0]))}")

                if audio_frames_generated < total_frames:
                    await _produce_one_audio_frame()

                audio_level, _is_speaking, frame_turn = audio_meta_q.popleft()
                if frame_turn is not None:
                    current_turn = frame_turn
                    active_speaker = frame_turn.speaker_id

                if self.world is not None:
                    self.world.tick(1.0 / float(self.fps))

                frame_rgb = self.renderer.render_frame(
                    frame_index=frame_idx,
                    active_speaker=active_speaker,
                    current_turn=current_turn,
                    recent_danmaku=tuple(self.director.recent_danmaku),
                    audio_level=audio_level,
                    follower_count=self.director.follower_count,
                    follower_goal=self.director.follower_goal,
                    poll_snapshot=self.director.poll.snapshot(),
                    celebration_text=self.director.get_active_celebration(),
                )

                if frame_dump_path is not None and not dumped_frame and frame_idx >= dump_frame_idx:
                    Image.fromarray(frame_rgb, mode="RGB").save(frame_dump_path, format="PNG")
                    dumped_frame = True

                await asyncio.to_thread(video_q.put, frame_rgb.tobytes())
                frames_written += 1

                if realtime_pacing:
                    target_mono = start_mono + (frame_idx + 1) / float(self.fps)
                    sleep_s = target_mono - time.monotonic()
                    if sleep_s > 0.001:
                        await asyncio.sleep(sleep_s)
                elif frame_idx % 10 == 0:
                    await asyncio.sleep(0)

            if frame_dump_path is not None and not dumped_frame:
                fallback_rgb = self.renderer.render_frame(
                    frame_index=frames_written,
                    active_speaker=active_speaker,
                    current_turn=current_turn,
                    recent_danmaku=tuple(self.director.recent_danmaku),
                    audio_level=0.5,
                    follower_count=self.director.follower_count,
                    follower_goal=self.director.follower_goal,
                    poll_snapshot=self.director.poll.snapshot(),
                    celebration_text=self.director.get_active_celebration(),
                )
                Image.fromarray(fallback_rgb, mode="RGB").save(frame_dump_path, format="PNG")
                dumped_frame = True

        finally:
            if control_task is not None:
                control_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await control_task

            if self.world is not None and record_dir is not None:
                with contextlib.suppress(Exception):
                    self._write_json_atomic(record_dir / "world_state.json", self.world.export_state_dict())

            if synth_task is not None:
                synth_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await synth_task

            if danmaku_task is not None:
                danmaku_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await danmaku_task
            if danmaku_source is not None:
                with contextlib.suppress(Exception):
                    await danmaku_source.close()

            # Signal EOF to pipe writer threads so FFmpeg flushes and closes output cleanly
            if writer_threads:
                for q in (audio_q, video_q):
                    try:
                        q.put(None, timeout=10.0)
                    except queue.Full:
                        while True:
                            try:
                                q.get_nowait()
                            except queue.Empty:
                                break
                        with contextlib.suppress(Exception):
                            q.put_nowait(None)
                for th in writer_threads:
                    th.join(timeout=15.0)

            for fd in (video_r, video_w, audio_r, audio_w):
                if fd >= 0:
                    with contextlib.suppress(OSError):
                        os.close(fd)

            if proc is not None:
                try:
                    proc.wait(timeout=15.0)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5.0)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=3.0)

            if stderr_thread is not None:
                stderr_thread.join(timeout=3.0)

        returncode = proc.returncode if proc is not None else -1
        if returncode != 0 and not self._stop_event.is_set():
            raise RuntimeError(f"ffmpeg exited with status {returncode}: " + " | ".join(list(self._stderr_lines)[-6:]))

        return {
            "frames_written": frames_written,
            "duration_sec": round(frames_written / float(self.fps), 2),
            "encoder": self.video_encoder,
            "turns_emitted": len(self.director.history),
            "danmaku_count": self.director.danmaku_count,
            "gift_count": self.director.gift_count,
            "cast": list(self.director.cast),
            "poll": self.director.poll.snapshot().to_dict(),
            "highlights_recorded": len(self.director.highlight_tracker.moments),
            "tts_backend": self.audio_mixer.tts_backend,
            "tts_stats": dict(self.audio_mixer.tts_stats),
            "llm_backend": getattr(self.director.responder, "backend_name", "unknown"),
            "autonomous_brain_enabled": bool(self.world_brain is not None and self.world_brain.has_api_key),
            "frame_dump_path": str(frame_dump_path) if (frame_dump_path is not None and dumped_frame) else None,
            "stderr_tail": list(self._stderr_lines)[-6:],
        }

    def _export_highlights(self, record_dir: Optional[Path], source_recording: str) -> Tuple[Optional[Path], int]:
        if record_dir is None:
            return None, 0
        record_dir.mkdir(parents=True, exist_ok=True)
        hl_jsonl = self.director.highlight_tracker.jsonl_path or (record_dir / "live_highlights.jsonl")
        if self.director.highlight_tracker.jsonl_path is None:
            # Ensure JSONL is persisted if tracker was created without path
            with hl_jsonl.open("a", encoding="utf-8") as fh:
                for moment in self.director.highlight_tracker.moments:
                    row = moment.to_dict()
                    row["summary"] = redact_pii(str(row.get("summary", ""))).replace("@", "")
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        plan_path = hl_jsonl.with_name(f"{hl_jsonl.stem}_ffmpeg_clip_plan.json")
        plan = self.director.highlight_tracker.save_clip_plan(
            plan_path,
            source_recording=source_recording,
            output_dir=str(record_dir / "clips"),
        )
        return plan_path, int(plan.get("planned_clip_count", 0))

    async def run_dry_stream(
        self,
        *,
        output_mp4: Path,
        duration_sec: float = 20.0,
        record_dir: Optional[Path] = None,
        frame_dump_path: Optional[Path] = None,
        realtime_pacing: bool = False,
    ) -> Dict[str, Any]:
        """Run a full headless zero-mic dry stream writing directly to a local `.mp4`."""
        rec_path = Path(record_dir) if record_dir is not None else None
        stats = await self._run_av_pipeline(
            mode="dry-stream",
            duration_sec=duration_sec,
            output_mp4=Path(output_mp4),
            record_dir=rec_path,
            realtime_pacing=realtime_pacing,
            frame_dump_path=frame_dump_path,
        )
        clip_plan_path, clip_plan_count = self._export_highlights(rec_path, str(output_mp4))
        result: Dict[str, Any] = {
            "ok": True,
            "mode": "dry-stream",
            "status": "dry_stream_done",
            "output_mp4": str(output_mp4),
            "clip_plan_path": str(clip_plan_path) if clip_plan_path else None,
            "clip_plan_count": clip_plan_count,
            "ai_disclosure_banner": AI_DISCLOSURE_BANNER,
            **stats,
        }
        self._emit_status("DRY_STREAM_DONE", result)
        return result

    async def run_go_live(
        self,
        *,
        duration_sec: float = 600.0,
        area_id: int = DEFAULT_LIVE_AREA_V2,
        title: Optional[str] = None,
        cover_path: Optional[Path] = None,
        record_dir: Optional[Path] = None,
        frame_dump_path: Optional[Path] = None,
        danmaku_client_factory: Optional[Callable[[int], Any]] = None,
        realtime_pacing: bool = True,
    ) -> Dict[str, Any]:
        """Start Bilibili live room, stream headless zero-mic A/V to RTMP, and ALWAYS call `stop_live` in `finally:`."""
        ctrl = self.controller or BilibiliLiveController()
        room_status = ctrl.get_my_room_info()
        room_id = room_status.room_id

        if title and title.strip():
            ctrl.update_room_title(room_id, title.strip())

        cover_result: Optional[Dict[str, Any]] = None
        if cover_path is not None:
            cover_result = ctrl.upload_live_cover(Path(cover_path), room_id=room_id)

        start_res: StartLiveResult = ctrl.start_live(room_id, area_v2=area_id)
        if start_res.status == "face_auth_required":
            payload = {
                **start_res.to_safe_dict(),
                "mode": "go-live",
                "area_id": area_id,
                "cover_result": cover_result,
            }
            self._emit_status("FACE_AUTH_REQUIRED", payload)
            return payload

        if not start_res.ok or not start_res.rtmp_url:
            payload = {
                **start_res.to_safe_dict(),
                "mode": "go-live",
                "area_id": area_id,
                "cover_result": cover_result,
            }
            self._emit_status("LIVE_ERROR", payload)
            return payload

        rec_dir_path: Optional[Path] = Path(record_dir) if record_dir is not None else None
        record_mkv: Optional[Path] = None
        if rec_dir_path is not None:
            rec_dir_path.mkdir(parents=True, exist_ok=True)
            record_mkv = rec_dir_path / "live_recording.mkv"

        self._emit_status(
            "LIVE_STARTED",
            {
                "ok": True,
                "mode": "go-live",
                "status": "live",
                "room_id": REDACTED_TOKEN,
                "rtmp_url": REDACTED_RTMP_TOKEN,
                "has_live_key": bool(start_res.live_key),
                "area_id": area_id,
                "encoder": self.video_encoder,
                "record_path": str(record_mkv) if record_mkv else None,
                "ai_disclosure_banner": AI_DISCLOSURE_BANNER,
            },
        )

        def _on_room_stats(stat_ev: Dict[str, Any]) -> None:
            if self.world is None:
                return
            st_type = stat_ev.get("type")
            if st_type == "watched":
                self.world.update_telemetry(
                    watched_num=stat_ev.get("watched_num"),
                    watched_text=stat_ev.get("watched_text"),
                )
            elif st_type == "online":
                self.world.update_telemetry(online=stat_ev.get("online"))

        danmaku_source = (
            danmaku_client_factory(room_id)
            if danmaku_client_factory is not None
            else BilibiliDanmakuClient(
                room_id=room_id,
                cookies=ctrl.vault.load_bilibili_cookies(),
                stats_callback=_on_room_stats,
            )
        )
        stream_stats: Dict[str, Any] = {
            "frames_written": 0,
            "duration_sec": 0.0,
            "encoder": self.video_encoder,
            "turns_emitted": 0,
            "danmaku_count": 0,
            "gift_count": 0,
            "highlights_recorded": 0,
            "frame_dump_path": None,
            "stderr_tail": [],
        }
        stream_error: Optional[str] = None
        stop_result: Dict[str, Any] = {"ok": False, "room_id": REDACTED_TOKEN}
        stop_live_data: Dict[str, Any] = {}
        clip_plan_path: Optional[Path] = None
        clip_plan_count = 0

        try:
            stream_stats = await self._run_av_pipeline(
                mode="go-live",
                duration_sec=duration_sec,
                rtmp_url=start_res.rtmp_url,
                record_path=record_mkv,
                record_dir=rec_dir_path,
                telemetry_ctrl=ctrl,
                telemetry_room_id=room_id,
                realtime_pacing=realtime_pacing,
                frame_dump_path=frame_dump_path,
                danmaku_source=danmaku_source,
            )
        except Exception as exc:
            stream_error = scrub_rtmp_secrets(str(exc))
            logger.error("Headless live stream interrupted (%s): %s", type(exc).__name__, stream_error)
        finally:
            stop_result = ctrl.stop_live(room_id)
            if start_res.live_key:
                stop_live_data = ctrl.get_stop_live_data(start_res.live_key)
            clip_plan_path, clip_plan_count = self._export_highlights(
                rec_dir_path,
                str(record_mkv or "live_recording.mkv"),
            )
            if rec_dir_path is not None:
                session_report: Dict[str, Any] = {
                    "ok": stream_error is None,
                    "duration_sec": stream_stats.get("duration_sec", 0.0),
                    "encoder": stream_stats.get("encoder"),
                    "turns_emitted": stream_stats.get("turns_emitted", 0),
                    "danmaku_count": stream_stats.get("danmaku_count", 0),
                    "gift_count": stream_stats.get("gift_count", 0),
                    "clip_plan_path": str(clip_plan_path) if clip_plan_path else None,
                    "stop_result": stop_result,
                    "cover_result": cover_result,
                    "stop_live_data": stop_live_data,
                    "world_summary": self.world.export_state_dict() if self.world is not None else None,
                }
                with contextlib.suppress(Exception):
                    self._write_json_atomic(rec_dir_path / "live_session_report.json", session_report)

            self._emit_status(
                "LIVE_STOPPED",
                {
                    "ok": stream_error is None,
                    "mode": "go-live",
                    "status": "stopped",
                    "room_id": REDACTED_TOKEN,
                    "rtmp_url": REDACTED_RTMP_TOKEN,
                    "stop_ok": bool(stop_result.get("ok")),
                    "stop_code": stop_result.get("code"),
                    "error": stream_error,
                    "clip_plan_path": str(clip_plan_path) if clip_plan_path else None,
                    "clip_plan_count": clip_plan_count,
                    "stop_live_data": stop_live_data,
                    **stream_stats,
                },
            )

        return {
            "ok": stream_error is None,
            "mode": "go-live",
            "status": "stopped" if stream_error is None else "error",
            "room_id": REDACTED_TOKEN,
            "rtmp_url": REDACTED_RTMP_TOKEN,
            "area_id": area_id,
            "stop_result": stop_result,
            "stop_live_data": stop_live_data,
            "cover_result": cover_result,
            "error": stream_error,
            "clip_plan_path": str(clip_plan_path) if clip_plan_path else None,
            "clip_plan_count": clip_plan_count,
            "ai_disclosure_banner": AI_DISCLOSURE_BANNER,
            **stream_stats,
        }
