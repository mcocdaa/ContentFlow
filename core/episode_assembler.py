"""Reusable multi-act 60FPS optical-flow and beat-synced camera assembler for ContentFlow.

Codifies shared video engineering across episodes:
  - Aspect-preserving center crop to 1920x1080 (zero horizontal/vertical stretch).
  - Exact frame-rate resampling via cached symmetric DIS optical flow (24/25/30fps -> 60.00fps).
  - Beat-synced multi-shot framing (`apply_beat_camera_framing`) alternating wide shots with
    medium close-ups on musical downbeats so single-camera choreography never feels static.
  - Standardized 1920x1080 @ 60.00fps H.264/yuv420p/bt709 encoding with EBU R128 -14 LUFS audio
    and Noto Sans CJK SC subtitle burn-in.
"""

from __future__ import annotations

import gc
import json
import math
import subprocess
import tempfile
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union, cast

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from config.settings import DEFAULT_FONTS


@dataclass
class ActSpec:
    """Single act input video and optional post-processing camera/transition parameters."""

    video_path: Path
    transition_in: str = "none"  # "none" | "flash_cyan" | "flash_neon"
    beat_punch_bpm: Optional[float] = None
    punch_scale: float = 1.32
    focus_y_ratio: float = 0.34
    beats_per_shot: int = 4
    punch_start_sec: float = 0.0


@dataclass
class EpisodeSpec:
    """Complete multi-act episode assembly specification."""

    acts: List[ActSpec]
    audio_path: Path
    output_mp4_path: Path
    subtitle_srt_path: Optional[Path] = None
    target_fps: float = 60.0
    width: int = 1920
    height: int = 1080
    loudnorm_target_i: float = -14.0
    hook_banner_text: Optional[str] = None
    hook_banner_sec: float = 1.6
    copy_video_stream: bool = False


def _crop_frame_to_target(frm: np.ndarray, target_w: int = 1920, target_h: int = 1080) -> np.ndarray:
    """Uniformly center-crops a single decoded frame to target_w x target_h (never stretches)."""
    h, w = frm.shape[:2]
    if w == target_w and h == target_h:
        return frm
    if w >= target_w and h >= target_h and (w - target_w) <= 32 and (h - target_h) <= 32:
        # Kling 1920x1088 / slightly padded outputs: center-crop exact pixels
        y0 = max(0, (h - target_h) // 2)
        x0 = max(0, (w - target_w) // 2)
        return frm[y0 : y0 + target_h, x0 : x0 + target_w]
    scale = max(target_w / float(w), target_h / float(h))
    rw, rh = int(round(w * scale)), int(round(h * scale))
    resized = cv2.resize(frm, (rw, rh), interpolation=cv2.INTER_LANCZOS4)
    y0 = max(0, (rh - target_h) // 2)
    x0 = max(0, (rw - target_w) // 2)
    return resized[y0 : y0 + target_h, x0 : x0 + target_w]


def probe_video_frame_info(video_path: Union[str, Path]) -> Tuple[int, float]:
    """Counts frames via decode-free cap.grab() and reads valid FPS with O(1) memory."""
    vpath = Path(video_path)
    cap = cv2.VideoCapture(str(vpath))
    if not cap.isOpened():
        raise RuntimeError(f"Unable to open video: {vpath}")
    src_fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    if src_fps <= 1.0 or math.isnan(src_fps):
        src_fps = 30.0
    n_in = 0
    try:
        while cap.grab():
            n_in += 1
    finally:
        cap.release()
    if n_in <= 0:
        raise RuntimeError(f"Video has 0 frames: {vpath}")
    return n_in, src_fps


def load_cropped_1080p_frames(
    video_path: Union[str, Path],
    target_w: int = 1920,
    target_h: int = 1080,
) -> Tuple[List[np.ndarray], float]:
    """Loads video frames and uniformly center-crops (never stretches) to target_w x target_h."""
    vpath = Path(video_path)
    cap = cv2.VideoCapture(str(vpath))
    if not cap.isOpened():
        raise RuntimeError(f"Unable to open video: {vpath}")

    src_fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    if src_fps <= 1.0 or math.isnan(src_fps):
        src_fps = 30.0

    frames: List[np.ndarray] = []
    try:
        while True:
            ok, frm = cap.read()
            if not ok:
                break
            frames.append(_crop_frame_to_target(frm, target_w=target_w, target_h=target_h))
    finally:
        cap.release()
    return frames, src_fps


def _compute_bidirectional_dis_flow(
    f0: np.ndarray,
    f1: np.ndarray,
    dis: cv2.DISOpticalFlow,
) -> Tuple[np.ndarray, np.ndarray]:
    """Computes upscaled symmetric forward/backward DIS optical flow fields."""
    h, w = f0.shape[:2]
    s0 = cv2.resize(cv2.cvtColor(f0, cv2.COLOR_BGR2GRAY), (max(8, w // 2), max(8, h // 2)))
    s1 = cv2.resize(cv2.cvtColor(f1, cv2.COLOR_BGR2GRAY), (max(8, w // 2), max(8, h // 2)))
    flow_f = cv2.resize(dis.calc(s0, s1, cast(Any, None)), (w, h), interpolation=cv2.INTER_LINEAR) * 2.0
    flow_b = cv2.resize(dis.calc(s1, s0, cast(Any, None)), (w, h), interpolation=cv2.INTER_LINEAR) * 2.0
    return flow_f, flow_b


def _blend_optical_flow_pair(
    f0: np.ndarray,
    f1: np.ndarray,
    flow_f: np.ndarray,
    flow_b: np.ndarray,
    gx: np.ndarray,
    gy: np.ndarray,
    alpha: float,
) -> np.ndarray:
    """Warps f0 forward and f1 backward using precomputed optical flow and alpha-blends."""
    w0 = cv2.remap(
        f0,
        gx - alpha * flow_f[..., 0],
        gy - alpha * flow_f[..., 1],
        cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
    w1 = cv2.remap(
        f1,
        gx - (1.0 - alpha) * flow_b[..., 0],
        gy - (1.0 - alpha) * flow_b[..., 1],
        cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return cv2.addWeighted(w0, 1.0 - alpha, w1, alpha, 0)


def iter_interpolated_60fps(
    raw_frames: List[np.ndarray],
    src_fps: float,
    dis: cv2.DISOpticalFlow,
    target_fps: float = 60.0,
) -> Iterator[np.ndarray]:
    """Resamples raw_frames at src_fps -> target_fps via cached symmetric DIS optical flow."""
    n_in = len(raw_frames)
    if n_in == 0:
        return
    if n_in == 1:
        yield raw_frames[0]
        return

    out_count = int(round((n_in - 1) * (target_fps / src_fps))) + 1
    h, w = raw_frames[0].shape[:2]
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))

    cached_idx = -1
    cached_flow_f: Optional[np.ndarray] = None
    cached_flow_b: Optional[np.ndarray] = None

    for k in range(out_count):
        pos = k * (src_fps / target_fps)
        i0 = min(int(math.floor(pos)), n_in - 1)
        alpha = pos - i0
        if alpha < 1e-3 or i0 >= n_in - 1:
            yield raw_frames[i0]
            continue

        if cached_idx != i0:
            cached_flow_f, cached_flow_b = _compute_bidirectional_dis_flow(raw_frames[i0], raw_frames[i0 + 1], dis)
            cached_idx = i0

        assert cached_flow_f is not None and cached_flow_b is not None
        yield _blend_optical_flow_pair(raw_frames[i0], raw_frames[i0 + 1], cached_flow_f, cached_flow_b, gx, gy, alpha)


def stream_interpolated_60fps(
    video_path: Union[str, Path],
    n_in: int,
    src_fps: float,
    dis: cv2.DISOpticalFlow,
    target_fps: float = 60.0,
    target_w: int = 1920,
    target_h: int = 1080,
) -> Iterator[np.ndarray]:
    """Streams src_fps -> target_fps frames using an O(1) 2-frame sliding window (<45 MiB RAM)."""
    if n_in <= 0:
        return

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Unable to open video for streaming: {video_path}")

    try:
        ok0, raw0 = cap.read()
        if not ok0:
            return
        f0 = _crop_frame_to_target(raw0, target_w=target_w, target_h=target_h)
        if n_in == 1:
            yield f0
            return

        ok1, raw1 = cap.read()
        f1: Optional[np.ndarray] = _crop_frame_to_target(raw1, target_w=target_w, target_h=target_h) if ok1 else None
        if f1 is None:
            yield f0
            return

        out_count = int(round((n_in - 1) * (target_fps / src_fps))) + 1
        gx, gy = np.meshgrid(np.arange(target_w, dtype=np.float32), np.arange(target_h, dtype=np.float32))
        cur_i0 = 0
        cached_idx = -1
        cached_flow_f: Optional[np.ndarray] = None
        cached_flow_b: Optional[np.ndarray] = None

        for k in range(out_count):
            pos = k * (src_fps / target_fps)
            i0 = min(int(math.floor(pos)), n_in - 1)
            alpha = pos - i0

            while cur_i0 < i0:
                if f1 is None:
                    break
                f0 = f1
                cur_i0 += 1
                ok_next, raw_next = cap.read()
                f1 = _crop_frame_to_target(raw_next, target_w=target_w, target_h=target_h) if ok_next else None

            if alpha < 1e-3 or i0 >= n_in - 1 or f1 is None:
                yield f0
                continue

            if cached_idx != i0:
                cached_flow_f, cached_flow_b = _compute_bidirectional_dis_flow(f0, f1, dis)
                cached_idx = i0

            assert cached_flow_f is not None and cached_flow_b is not None
            yield _blend_optical_flow_pair(f0, f1, cached_flow_f, cached_flow_b, gx, gy, alpha)
    finally:
        cap.release()


def apply_beat_camera_framing(
    frame: np.ndarray,
    t_act_sec: float,
    bpm: float = 132.0,
    punch_scale: float = 1.32,
    focus_y_ratio: float = 0.34,
    beats_per_shot: int = 4,
    punch_start_sec: float = 0.0,
) -> np.ndarray:
    """Alternates wide choreography shots (1.0x) with beat-synced medium close-ups (punch_scale)."""
    if bpm <= 0 or punch_scale <= 1.01 or t_act_sec < punch_start_sec:
        return frame
    beat_sec = 60.0 / float(bpm)
    shot_dur = beat_sec * max(1, int(beats_per_shot))
    shot_idx = int(max(0.0, t_act_sec) / shot_dur)
    if (shot_idx % 2) == 0:
        return frame

    h, w = frame.shape[:2]
    cw = max(64, min(w, int(round(w / float(punch_scale)))))
    ch = max(36, min(h, int(round(h / float(punch_scale)))))
    cx = w // 2
    cy = int(round(h * float(focus_y_ratio)))
    x0 = max(0, min(w - cw, cx - cw // 2))
    y0 = max(0, min(h - ch, cy - ch // 2))
    cropped = frame[y0 : y0 + ch, x0 : x0 + cw]
    return cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LANCZOS4)


def apply_transition_flash(frame: np.ndarray, mode: str, alpha: float) -> np.ndarray:
    """Applies a short flash overlay at act boundaries (`flash_cyan` or `flash_neon`)."""
    if mode == "none" or alpha <= 1e-3:
        return frame
    h, w = frame.shape[:2]
    flash = np.empty_like(frame)
    if mode == "flash_neon":
        flash[:, : w // 2] = (255, 230, 80)
        flash[:, w // 2 :] = (230, 90, 255)
    else:
        flash[:, :] = (255, 245, 200)
    return cv2.addWeighted(frame, 1.0 - alpha, flash, alpha, 0)


def _load_hook_banner_font(size: int) -> Union[ImageFont.FreeTypeFont, ImageFont.ImageFont]:
    """Loads Noto Sans CJK SC Bold (fallback DEFAULT_FONTS) at the requested pixel size."""
    candidates: List[str] = ["/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"]
    for fpath in DEFAULT_FONTS:
        if fpath not in candidates:
            candidates.append(fpath)
    for cand in candidates:
        if Path(cand).exists():
            lower = cand.lower()
            if "notosanscjk" in lower and lower.endswith(".ttc"):
                try:
                    return ImageFont.truetype(cand, size=size, index=2)
                except Exception:
                    pass
            try:
                return ImageFont.truetype(cand, size=size)
            except Exception:
                continue
    return ImageFont.load_default(size=size)


def _sanitize_hook_banner_text(raw_text: str) -> str:
    """Strips emoji/dingbat codepoints missing from CJK fonts so no .notdef boxes appear."""
    kept: List[str] = []
    for ch in raw_text:
        cp = ord(ch)
        if cp > 0xFFFF or (0x2600 <= cp <= 0x27BF) or (0xFE00 <= cp <= 0xFE0F) or cp in (0x200B, 0x200D, 0xFEFF):
            continue
        kept.append(" " if ch in ("\r", "\n", "\t") else ch)
    return " ".join("".join(kept).split()).strip()


def _split_hook_banner_segments(text: str) -> Tuple[str, str]:
    """Splits a hook headline into (cyan_prefix, gold_main) when a concise prefix exists."""
    for sep in ("：", ":", "｜", "|", "·"):
        if sep in text:
            left, right = text.split(sep, 1)
            left_s, right_s = left.strip(), right.strip()
            if 1 <= len(left_s) <= 8 and right_s:
                return f"{left_s}{sep}", right_s
    if " " in text:
        left, right = text.split(" ", 1)
        left_s, right_s = left.strip(), right.strip()
        if 2 <= len(left_s) <= 7 and right_s:
            return f"{left_s} ", right_s
    return "", text


def render_hook_banner_rgba(
    text: str,
    frame_width: int = 1920,
    frame_height: int = 1080,
) -> Optional[np.ndarray]:
    """Pre-renders a compact variety capsule RGBA patch (bh, bw, 4) (<1 MiB RAM)."""
    clean_text = _sanitize_hook_banner_text(text)
    if not clean_text:
        return None

    scale = max(0.25, min(frame_width / 1920.0, frame_height / 1080.0))
    max_bw = max(120, min(int(round(frame_width * 0.80)), 1400))
    start_size = max(13, int(round(42 * scale)))
    min_size = max(10, int(round(22 * scale)))
    stroke_w = max(2, int(round(4 * scale)))
    pad_x = max(10, int(round(30 * scale)))
    pad_y = max(5, int(round(13 * scale)))
    icon_w = max(8, int(round(20 * scale)))
    icon_gap = max(5, int(round(11 * scale)))
    margin = max(2, int(round(4 * scale)))
    border_w = max(2, int(round(3 * scale)))

    prefix, main_text = _split_hook_banner_segments(clean_text)
    full_text = f"{prefix}{main_text}"

    probe_img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    probe_draw = ImageDraw.Draw(probe_img)
    font_size = start_size
    font = _load_hook_banner_font(font_size)
    bbox = probe_draw.textbbox((0, 0), full_text, font=font, stroke_width=stroke_w)
    while font_size > min_size:
        cand_bw = int(bbox[2] - bbox[0]) + icon_w + icon_gap + pad_x * 2 + margin * 2
        if cand_bw <= max_bw:
            break
        font_size = max(min_size, font_size - 2)
        font = _load_hook_banner_font(font_size)
        bbox = probe_draw.textbbox((0, 0), full_text, font=font, stroke_width=stroke_w)

    tw = max(8, int(bbox[2] - bbox[0]))
    th = max(8, int(bbox[3] - bbox[1]))
    pill_w = icon_w + icon_gap + tw + pad_x * 2
    pill_h = th + pad_y * 2
    bw = pill_w + margin * 2
    bh = pill_h + margin * 2

    canvas = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    sh_off = max(1, int(round(3 * scale)))
    px0, py0 = margin, margin
    px1, py1 = margin + pill_w - 1, margin + pill_h - 1
    radius = pill_h // 2

    # Subtle drop shadow + dark variety capsule with bright gold #FFD700 border and cyan inner rim
    draw.rounded_rectangle(
        [px0 + sh_off, py0 + sh_off, px1 + sh_off, py1 + sh_off],
        radius=radius,
        fill=(0, 0, 0, 125),
    )
    draw.rounded_rectangle(
        [px0, py0, px1, py1],
        radius=radius,
        fill=(16, 20, 34, 232),
        outline=(255, 215, 0, 255),
        width=border_w,
    )
    if pill_h > border_w * 4:
        draw.rounded_rectangle(
            [px0 + border_w, py0 + border_w, px1 - border_w, py1 - border_w],
            radius=max(2, radius - border_w),
            outline=(0, 240, 255, 135),
            width=1,
        )

    # Geometric cyan lightning spark icon (avoids missing emoji glyphs)
    icon_h = max(10, int(round(pill_h * 0.54)))
    ix = float(px0 + pad_x)
    iy = float(py0 + (pill_h - icon_h) / 2.0)
    iw_f = float(icon_w)
    ih_f = float(icon_h)
    bolt_pts = [
        (ix + iw_f * 0.58, iy),
        (ix + iw_f * 0.12, iy + ih_f * 0.54),
        (ix + iw_f * 0.46, iy + ih_f * 0.54),
        (ix + iw_f * 0.34, iy + ih_f),
        (ix + iw_f * 0.88, iy + ih_f * 0.44),
        (ix + iw_f * 0.52, iy + ih_f * 0.44),
    ]
    draw.polygon(bolt_pts, fill=(0, 240, 255, 255), outline=(0, 0, 0, 230))

    # Black-stroked gold-cyan headline typography
    tx = int(px0 + pad_x + icon_w + icon_gap - bbox[0])
    ty = int(py0 + (pill_h - th) // 2 - bbox[1])
    text_sh = max(1, int(round(2 * scale)))
    draw.text(
        (tx + text_sh, ty + text_sh),
        full_text,
        font=font,
        fill=(0, 0, 0, 190),
        stroke_width=stroke_w,
        stroke_fill=(0, 0, 0, 190),
    )
    if prefix:
        draw.text(
            (tx, ty),
            prefix,
            font=font,
            fill=(0, 240, 255, 255),
            stroke_width=stroke_w,
            stroke_fill=(0, 0, 0, 255),
        )
        adv = int(round(float(draw.textlength(prefix, font=font))))
        draw.text(
            (tx + adv, ty),
            main_text,
            font=font,
            fill=(255, 215, 0, 255),
            stroke_width=stroke_w,
            stroke_fill=(0, 0, 0, 255),
        )
    else:
        draw.text(
            (tx, ty),
            main_text,
            font=font,
            fill=(255, 215, 0, 255),
            stroke_width=stroke_w,
            stroke_fill=(0, 0, 0, 255),
        )

    # Enforce strict < 1 MiB RGBA patch footprint and fit within max_bw
    max_pixels = 230_000  # 230k * 4 bytes = ~0.88 MiB < 1 MiB
    if bw > max_bw or (bw * bh) > max_pixels:
        fit_ratio = min(max_bw / float(bw), math.sqrt(max_pixels / float(bw * bh)))
        nbw = max(16, int(round(bw * fit_ratio)))
        nbh = max(8, int(round(bh * fit_ratio)))
        canvas = canvas.resize((nbw, nbh), Image.Resampling.LANCZOS)

    return np.ascontiguousarray(np.asarray(canvas, dtype=np.uint8))


def apply_hook_banner_overlay(
    frame: np.ndarray,
    banner_rgba: Optional[np.ndarray],
    t_sec: float,
    hook_banner_sec: float = 1.6,
    top_y: Optional[int] = None,
    pop_in_sec: float = 0.18,
) -> np.ndarray:
    """Composites a pre-rendered RGBA banner patch onto a BGR frame while t_sec < hook_banner_sec."""
    if (
        banner_rgba is None
        or banner_rgba.size == 0
        or hook_banner_sec <= 0.0
        or t_sec < 0.0
        or t_sec >= hook_banner_sec
    ):
        return frame

    fh, fw = frame.shape[:2]
    bh_orig, bw_orig = banner_rgba.shape[:2]

    if pop_in_sec > 1e-6 and t_sec < pop_in_sec:
        u = max(0.0, min(1.0, t_sec / pop_in_sec))
        ease = 1.0 - (1.0 - u) ** 3
        cur_scale = 0.86 + 0.14 * ease
        alpha_gain = 0.76 + 0.24 * ease
        slide_dy = int(round(-6.0 * (1.0 - ease) * (fh / 1080.0)))
    else:
        cur_scale = 1.0
        alpha_gain = 1.0
        slide_dy = 0

    if abs(cur_scale - 1.0) > 1e-3:
        pw = max(4, int(round(bw_orig * cur_scale)))
        ph = max(4, int(round(bh_orig * cur_scale)))
        interp = cv2.INTER_AREA if cur_scale < 1.0 else cv2.INTER_LINEAR
        active_rgba = cv2.resize(banner_rgba, (pw, ph), interpolation=interp)
    else:
        active_rgba = banner_rgba
        ph, pw = bh_orig, bw_orig

    base_y = top_y if top_y is not None else max(8, int(round(52.0 * (fh / 1080.0))))
    y0 = base_y + (bh_orig - ph) // 2 + slide_dy
    x0 = (fw - pw) // 2

    sx0 = max(0, -x0)
    sy0 = max(0, -y0)
    dx0 = max(0, x0)
    dy0 = max(0, y0)
    cw = min(pw - sx0, fw - dx0)
    ch = min(ph - sy0, fh - dy0)
    if cw <= 0 or ch <= 0:
        return frame

    out = frame.copy()
    sub_rgba = active_rgba[sy0 : sy0 + ch, sx0 : sx0 + cw]
    sub_bgr = sub_rgba[..., [2, 1, 0]].astype(np.uint16)
    alpha_u16 = sub_rgba[..., 3:4].astype(np.uint16)
    if alpha_gain < 0.999:
        alpha_u16 = ((alpha_u16 * np.uint16(int(round(alpha_gain * 256.0)))) >> np.uint16(8)).astype(np.uint16)
    roi = out[dy0 : dy0 + ch, dx0 : dx0 + cw].astype(np.uint16)
    out[dy0 : dy0 + ch, dx0 : dx0 + cw] = ((sub_bgr * alpha_u16 + roi * (255 - alpha_u16) + 127) // 255).astype(
        np.uint8
    )
    return out


def _probe_stream(path: Path, selector: str) -> Dict[str, Any]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", selector, "-show_streams", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    streams = json.loads(result.stdout)["streams"]
    if len(streams) != 1:
        raise ValueError(f"copy_video_stream requires a {selector} stream in {path.name}")
    return cast(Dict[str, Any], streams[0])


def _check_packet_timeline(path: Path, selector: str, end: int, frame_ticks: Optional[int] = None) -> int:
    """Verify a complete interval starting at PTS zero. MP4 delivers H.264 packets in decode order."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        selector,
        "-show_packets",
        "-show_entries",
        "packet=pts,duration,flags:packet_side_data=skip_samples,discard_padding",
        "-of",
        "compact=p=0",
        str(path),
    ]
    next_pts = count = 0
    pending: set[int] = set()
    with subprocess.Popen(cmd, text=True, stdout=subprocess.PIPE) as probe:
        assert probe.stdout is not None
        try:
            for line in probe.stdout:
                if not line.strip():
                    continue
                fields = dict(part.split("=", 1) for part in line.strip().split("|") if "=" in part)
                try:
                    pts, duration = int(fields["pts"]), int(fields["duration"])
                except (KeyError, ValueError) as exc:
                    raise ValueError(f"copy_video_stream packet timing unavailable for {path.name}") from exc
                bad_flags = {"C", "D"}.intersection(fields.get("flags", ""))
                if duration <= 0 or pts < next_pts or pts + duration > end or bad_flags:
                    raise ValueError(f"copy_video_stream invalid {selector} packet at {pts} in {path.name}")
                if int(fields.get("skip_samples", 0)) or int(fields.get("discard_padding", 0)):
                    raise ValueError(f"copy_video_stream found trimmed packets in {path.name}")
                if frame_ticks is None:
                    if pts != next_pts:
                        raise ValueError(f"copy_video_stream discontinuous audio at {pts} in {path.name}")
                    next_pts += duration
                else:
                    if duration != frame_ticks or pts % frame_ticks or pts in pending:
                        raise ValueError(f"copy_video_stream non-CFR video at {pts} in {path.name}")
                    pending.add(pts)
                    while next_pts in pending:
                        pending.remove(next_pts)
                        next_pts += frame_ticks
                    # H.264 reorders B frames. Bound memory even for malformed input.
                    if len(pending) > 64:
                        raise ValueError(f"copy_video_stream excessive packet reordering or a gap in {path.name}")
                count += 1
            if probe.wait():
                raise RuntimeError(f"ffprobe could not read the complete {selector} stream in {path.name}")
        finally:
            if probe.poll() is None:
                probe.kill()
    if not count or pending or next_pts != end:
        raise ValueError(f"copy_video_stream incomplete or nonzero-start {selector} timeline in {path.name}")
    return count


def _assemble_with_stream_copy(spec: EpisodeSpec) -> Dict[str, Any]:
    if len(spec.acts) != 1 or spec.subtitle_srt_path or spec.hook_banner_text:
        raise ValueError("copy_video_stream requires one act without subtitles or a banner")
    act = spec.acts[0]
    if act.transition_in != "none" or act.beat_punch_bpm is not None:
        raise ValueError("copy_video_stream cannot apply transitions or camera moves")

    video = _probe_stream(act.video_path, "v:0")
    aspect = Fraction(spec.width, spec.height)
    expected = {
        "codec_name": "h264",
        "pix_fmt": "yuv420p",
        "color_primaries": "bt709",
        "color_transfer": "bt709",
        "color_space": "bt709",
        "width": spec.width,
        "height": spec.height,
        "sample_aspect_ratio": "1:1",
        "display_aspect_ratio": f"{aspect.numerator}:{aspect.denominator}",
        "field_order": "progressive",
        "start_pts": 0,
    }
    for key, value in expected.items():
        if video.get(key) != value:
            raise ValueError(f"copy_video_stream requires {key}={value}, got {video.get(key)}")
    if video.get("disposition", {}).get("attached_pic") or any(
        d.get("side_data_type") == "Display Matrix" for d in video.get("side_data_list", [])
    ):
        raise ValueError("copy_video_stream requires a video track without display transforms")
    fps = Fraction(str(spec.target_fps))
    if fps <= 0 or any(Fraction(video[key]) != fps for key in ("r_frame_rate", "avg_frame_rate")):
        raise ValueError("copy_video_stream source frame rate differs from target_fps")
    video_tick = Fraction(video["time_base"])
    step = 1 / (fps * video_tick)
    if step.denominator != 1:
        raise ValueError("copy_video_stream cannot represent constant frame intervals in the source time base")
    video_end = int(video["duration_ts"])
    count = _check_packet_timeline(act.video_path, "v:0", video_end, int(step))

    audio = _probe_stream(spec.audio_path, "a:0")
    audio_end = int(audio["duration_ts"])
    if audio_end * Fraction(audio["time_base"]) != video_end * video_tick:
        raise ValueError("copy_video_stream requires equal source video and audio durations")
    _check_packet_timeline(spec.audio_path, "a:0", audio_end)

    destination = spec.output_mp4_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Same filesystem for atomic replacement; concurrent attempts use independent staging files.
    with tempfile.TemporaryDirectory(prefix=".assemble-", dir=destination.parent) as directory:
        staged = Path(directory) / "master.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-xerror",
                "-i",
                str(act.video_path),
                "-i",
                str(spec.audio_path),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-map_metadata",
                "-1",
                "-map_chapters",
                "-1",
                "-c:v",
                "copy",
                "-af",
                f"loudnorm=I={spec.loudnorm_target_i}:LRA=7:TP=-1.5",
                "-c:a",
                "aac",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                "-movie_timescale",
                "48000",
                str(staged),
            ],
            check=True,
        )
        muxed = _probe_stream(staged, "v:0")
        if (
            muxed.get("start_pts") != 0
            or int(muxed["nb_frames"]) != count
            or int(muxed["duration_ts"]) * Fraction(muxed["time_base"]) != video_end * video_tick
        ):
            raise RuntimeError("stream copy did not preserve the video timeline")
        soundtrack = _probe_stream(staged, "a:0")
        if (
            soundtrack.get("codec_name") != "aac"
            or soundtrack.get("sample_rate") != "48000"
            or soundtrack.get("channels") != 2
            or soundtrack.get("start_pts") != 0
            or abs(int(soundtrack["duration_ts"]) * Fraction(soundtrack["time_base"]) - video_end * video_tick)
            > Fraction(1, 48000)
        ):
            raise RuntimeError("stream copy output has an invalid or truncated AAC soundtrack")
        staged.replace(destination)
    return {
        "output_mp4": str(destination),
        "frames": count,
        "fps": spec.target_fps,
        "duration_sec": round(count / spec.target_fps, 3),
        "act_start_times": [0.0],
    }


class EpisodeAssembler:
    """Stitches multi-act raw video clips into a 1080P @ 60FPS H.264 master with -14 LUFS audio."""

    @staticmethod
    def _parse_spec_dict(data: Dict[str, Any], base_dir: Path) -> EpisodeSpec:
        def _resolve(p: Union[str, Path]) -> Path:
            cand = Path(p)
            return cand if cand.is_absolute() else (base_dir / cand).resolve()

        acts = [
            ActSpec(
                video_path=_resolve(a["video_path"]),
                transition_in=str(a.get("transition_in") or "none"),
                beat_punch_bpm=float(a["beat_punch_bpm"]) if a.get("beat_punch_bpm") is not None else None,
                punch_scale=float(a.get("punch_scale") or 1.32),
                focus_y_ratio=float(a.get("focus_y_ratio") or 0.34),
                beats_per_shot=int(a.get("beats_per_shot") or 4),
                punch_start_sec=float(a.get("punch_start_sec") or 0.0),
            )
            for a in data["acts"]
        ]
        srt_raw = data.get("subtitle_srt_path")
        raw_banner = data.get("hook_banner_text")
        hook_banner_text = str(raw_banner).strip() if raw_banner is not None and str(raw_banner).strip() else None
        raw_banner_sec = data.get("hook_banner_sec")
        hook_banner_sec = float(raw_banner_sec) if raw_banner_sec is not None else 1.6
        copy_stream = data.get("copy_video_stream", False)
        if not isinstance(copy_stream, bool):
            raise ValueError("copy_video_stream must be a boolean")
        return EpisodeSpec(
            copy_video_stream=copy_stream,
            acts=acts,
            audio_path=_resolve(data["audio_path"]),
            output_mp4_path=_resolve(data["output_mp4_path"]),
            subtitle_srt_path=_resolve(srt_raw) if srt_raw else None,
            target_fps=float(data.get("target_fps") or 60.0),
            width=int(data.get("width") or 1920),
            height=int(data.get("height") or 1080),
            loudnorm_target_i=float(data.get("loudnorm_target_i") or -14.0),
            hook_banner_text=hook_banner_text,
            hook_banner_sec=hook_banner_sec,
        )

    @classmethod
    def assemble_from_json(cls, spec_path: Union[str, Path]) -> Dict[str, Any]:
        """Loads an EpisodeSpec JSON file and runs assembly."""
        spath = Path(spec_path).resolve()
        data = json.loads(spath.read_text(encoding="utf-8"))
        spec = cls._parse_spec_dict(data, spath.parent)
        return cls.assemble(spec)

    @classmethod
    def assemble(cls, spec: EpisodeSpec) -> Dict[str, Any]:
        """Executes O(1)-memory optical-flow 60FPS interpolation, beat framing, and FFmpeg encode."""
        if not spec.acts:
            raise ValueError("EpisodeSpec.acts must not be empty")
        if not spec.audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {spec.audio_path}")

        if spec.copy_video_stream:
            return _assemble_with_stream_copy(spec)

        act_infos: List[Tuple[ActSpec, int, float, int]] = []
        for act in spec.acts:
            n_in, src_fps = probe_video_frame_info(act.video_path)
            n_out = int(round((n_in - 1) * (spec.target_fps / src_fps))) + 1
            act_infos.append((act, n_in, src_fps, n_out))

        banner_rgba: Optional[np.ndarray] = None
        banner_top_y = max(8, int(round(52.0 * (spec.height / 1080.0))))
        if spec.hook_banner_text and spec.hook_banner_text.strip() and spec.hook_banner_sec > 0.0:
            banner_rgba = render_hook_banner_rgba(
                spec.hook_banner_text,
                frame_width=spec.width,
                frame_height=spec.height,
            )

        spec.output_mp4_path.parent.mkdir(parents=True, exist_ok=True)
        vf_parts: List[str] = []
        if spec.subtitle_srt_path and spec.subtitle_srt_path.exists():
            sub_style = (
                "Fontname=Noto Sans CJK SC,"
                "FontSize=24,"
                "PrimaryColour=&H00FFFFFF,"
                "OutlineColour=&H00000000,"
                "BackColour=&H88000000,"
                "BorderStyle=1,"
                "Outline=2.6,"
                "Shadow=1.0,"
                "MarginV=40,"
                "Alignment=2"
            )
            vf_parts.append(f"subtitles={spec.subtitle_srt_path.resolve().as_posix()}:force_style='{sub_style}'")
        vf_parts.extend(["setsar=1", "setdar=16/9", f"fps={int(round(spec.target_fps))}", "format=yuv420p"])
        vf = ",".join(vf_parts)

        cmd = [
            "ffmpeg",
            "-y",
            "-nostats",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-vcodec",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-s",
            f"{spec.width}x{spec.height}",
            "-r",
            str(int(round(spec.target_fps))),
            "-i",
            "-",
            "-i",
            str(spec.audio_path),
            "-vf",
            vf,
            "-af",
            f"loudnorm=I={spec.loudnorm_target_i}:LRA=7:TP=-1.5",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-profile:v",
            "high",
            "-preset",
            "fast",
            "-crf",
            "16",
            "-b:v",
            "6200k",
            "-maxrate",
            "7500k",
            "-bufsize",
            "9000k",
            "-pix_fmt",
            "yuv420p",
            "-color_primaries",
            "bt709",
            "-color_trc",
            "bt709",
            "-colorspace",
            "bt709",
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(spec.output_mp4_path),
        ]

        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        assert proc.stdin is not None
        cv2_any = cast(Any, cv2)
        dis = cv2_any.DISOpticalFlow_create(cv2_any.DISOPTICAL_FLOW_PRESET_MEDIUM)

        out_idx = 0
        act_boundaries: List[float] = []
        try:
            for act_idx, (act, n_in, src_fps, n_out) in enumerate(act_infos):
                act_boundaries.append(round(out_idx / spec.target_fps, 3))
                next_trans = act_infos[act_idx + 1][0].transition_in if act_idx + 1 < len(act_infos) else "none"
                frame_stream = stream_interpolated_60fps(
                    act.video_path,
                    n_in=n_in,
                    src_fps=src_fps,
                    dis=dis,
                    target_fps=spec.target_fps,
                    target_w=spec.width,
                    target_h=spec.height,
                )
                for local_i, frm in enumerate(frame_stream):
                    cur = frm
                    if act.beat_punch_bpm is not None:
                        cur = apply_beat_camera_framing(
                            cur,
                            t_act_sec=local_i / spec.target_fps,
                            bpm=act.beat_punch_bpm,
                            punch_scale=act.punch_scale,
                            focus_y_ratio=act.focus_y_ratio,
                            beats_per_shot=act.beats_per_shot,
                            punch_start_sec=act.punch_start_sec,
                        )
                    if next_trans != "none":
                        dist_end = (n_out - 1) - local_i
                        if dist_end < 4:
                            cur = apply_transition_flash(cur, next_trans, 0.62 * (1.0 - dist_end / 4.0))
                    if act.transition_in != "none" and local_i < 5:
                        cur = apply_transition_flash(cur, act.transition_in, 0.62 * (1.0 - local_i / 5.0))
                    if banner_rgba is not None and (out_idx / spec.target_fps) < spec.hook_banner_sec:
                        cur = apply_hook_banner_overlay(
                            cur,
                            banner_rgba,
                            t_sec=out_idx / spec.target_fps,
                            hook_banner_sec=spec.hook_banner_sec,
                            top_y=banner_top_y,
                        )
                    proc.stdin.write(cur.tobytes())
                    out_idx += 1

            proc.stdin.close()
            proc.stdin = None
            _, err = proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"FFmpeg encode failed: {err.decode(errors='ignore')[-500:]}")
        finally:
            if proc.stdin is not None:
                try:
                    proc.stdin.close()
                except Exception:
                    pass
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            del banner_rgba
            del dis
            gc.collect()

        return {
            "output_mp4": str(spec.output_mp4_path),
            "frames": out_idx,
            "fps": spec.target_fps,
            "duration_sec": round(out_idx / spec.target_fps, 3),
            "act_start_times": act_boundaries,
        }
