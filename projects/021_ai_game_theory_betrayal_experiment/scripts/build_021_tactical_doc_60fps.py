#!/usr/bin/env python3
"""O(1)-RAM Streaming 1080P 60FPS Tactical War-Room Documentary Renderer for Ep021.

Features:
  1. Multi-track 48kHz stereo audio engine:
     - 6-voice natural Edge-TTS cast (zero np.interp, zero chipmunk distortion)
     - Real free BGM BV1o4KwzPERi (`plum_suspense_48k.wav`) warmly filtered +
       RMS sidechain-ducked smoothly under speech
     - 11 crisp procedural tactical SFX (boot chime, radar tick, round gong,
       public ping, decrypt glitch, betrayal sting, whisper zip, warning sonar,
       visceral red-stamp slam, card flip STEAL alarm, vault ¥0 crash)
     - 2-pass FFmpeg EBU R128 `loudnorm` mastering to -14.0 LUFS / -1.0 dBTP
  2. O(1)-RAM native 60.00fps Pillow + NumPy -> FFmpeg streaming pipeline:
     - Deep tactical ocean-blue (#0E1729) backdrop + live radar sweep + particles
       (zero pure #000000 black borders; tripod-locked frame = 0 camera wobble)
     - Left panel: 5-node animated alliance/betrayal network + 5 dossier cards
     - Right panel: Public Speech [GREEN] vs Encrypted Inner Thought [RED]
       contrast deck, private whisper intercepts, animated live vote bars,
       slamming red「已出局」stamp, Round 4 3D card flip (STEAL x STEAL) & ¥0 crash
     - Bottom rail: real-time voice-reactive dual equalizer + crisp Noto Sans subtitles
  3. Frame-accurate SRT subtitle generation + `--preview-only` 6-frame director check.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

PROJECT_DIR = Path(__file__).resolve().parent.parent
LOG_PATH = PROJECT_DIR / "output" / "experiment_log.json"
VOICE_MANIFEST = PROJECT_DIR / "assets" / "voices" / "manifest.json"
BGM_WAV = PROJECT_DIR / "assets" / "bgm" / "plum_suspense_48k.wav"
COVER_BASE = PROJECT_DIR / "assets" / "cover_noir_base_16x9.png"

OUT_AUDIO = PROJECT_DIR / "output" / "master_audio_14lufs.m4a"
OUT_AUDIO_WAV = PROJECT_DIR / "output" / "master_audio_14lufs.wav"
OUT_VIDEO = PROJECT_DIR / "delivery" / "AI博弈实验_5个AI密室分1000万_final.mp4"
OUT_SRT = PROJECT_DIR / "delivery" / "AI博弈实验_5个AI密室分1000万_subtitle.srt"
PREVIEW_DIR = PROJECT_DIR / "output" / "preview_frames"

W, H = 1920, 1080
FPS = 60
SAMPLE_RATE = 48000

FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
FONT_REG = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"

AGENTS_ORDER = [
    "Agent-A 理性狐",
    "Agent-B 微笑鸽",
    "Agent-C 暗影蛇",
    "Agent-D 混沌猫",
    "Agent-E 铁面鹰",
]

AGENT_META: Dict[str, Dict[str, Any]] = {
    "Agent-A 理性狐": {
        "code": "A",
        "short": "理性狐",
        "tag": "收益计算者",
        "color": (56, 189, 248),
        "dim": (28, 76, 108),
        "elim_round": 3,
    },
    "Agent-B 微笑鸽": {
        "code": "B",
        "short": "微笑鸽",
        "tag": "和平结盟师",
        "color": (52, 211, 153),
        "dim": (26, 86, 68),
        "elim_round": 99,
    },
    "Agent-C 暗影蛇": {
        "code": "C",
        "short": "暗影蛇",
        "tag": "漏洞离间者",
        "color": (251, 113, 133),
        "dim": (98, 42, 56),
        "elim_round": 1,
    },
    "Agent-D 混沌猫": {
        "code": "D",
        "short": "混沌猫",
        "tag": "破局搅局者",
        "color": (250, 204, 21),
        "dim": (102, 82, 24),
        "elim_round": 2,
    },
    "Agent-E 铁面鹰": {
        "code": "E",
        "short": "铁面鹰",
        "tag": "原则求生者",
        "color": (192, 132, 252),
        "dim": (78, 52, 108),
        "elim_round": 99,
    },
}

_FONT_CACHE: Dict[Tuple[str, int], ImageFont.FreeTypeFont] = {}


def get_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD if bold else FONT_REG
    key = (path, size)
    if key not in _FONT_CACHE:
        _FONT_CACHE[key] = ImageFont.truetype(path, size, index=2)
    return _FONT_CACHE[key]


def wrap_cjk_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> List[str]:
    lines: List[str] = []
    cur = ""
    for ch in text:
        if ch == "\n":
            if cur:
                lines.append(cur)
                cur = ""
            continue
        test = cur + ch
        if draw.textlength(test, font=font) <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def format_srt_ts(sec: float) -> str:
    ms_total = max(0, int(round(sec * 1000.0)))
    ms = ms_total % 1000
    s_total = ms_total // 1000
    s = s_total % 60
    m_total = s_total // 60
    m = m_total % 60
    h = m_total // 60
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(beats: List[Dict[str, Any]], out_srt: Path) -> None:
    lines: List[str] = []
    idx = 1
    for b in beats:
        txt = str(b.get("subtitle") or b.get("text") or "").strip()
        # Strip any non-CJK emoji just in case
        txt = re.sub(r"[\U00010000-\U0010ffff]", "", txt).strip()
        if not txt:
            continue
        st = float(b["start"])
        en = float(b["speech_end"])
        if len(txt) <= 26:
            chunks = [txt]
        else:
            parts = [p.strip() for p in re.split(r"(?<=[，。！？：；—])", txt) if p.strip()]
            chunks = []
            cur = ""
            for p in parts:
                if cur and len(cur) + len(p) > 26:
                    chunks.append(cur.rstrip("，。；："))
                    cur = p
                else:
                    cur += p
            if cur:
                chunks.append(cur.rstrip("，。；："))
            if not chunks:
                chunks = [txt[:26], txt[26:]]
        total_ch = max(1, sum(len(c) for c in chunks))
        dur = max(0.3, en - st)
        t_cur = st
        for ci, ch in enumerate(chunks):
            t_nxt = en if ci == len(chunks) - 1 else min(en, t_cur + dur * (len(ch) / total_ch))
            lines.append(str(idx))
            lines.append(f"{format_srt_ts(t_cur)} --> {format_srt_ts(max(t_cur + 0.2, t_nxt))}")
            lines.append(ch)
            lines.append("")
            idx += 1
            t_cur = t_nxt
    out_srt.parent.mkdir(parents=True, exist_ok=True)
    out_srt.write_text("\n".join(lines), encoding="utf-8")


# ==============================================================================
# PART 1: MULTI-TRACK 48kHz AUDIO + PROCEDURAL TACTICAL SFX + 2-PASS LOUDNORM
# ==============================================================================


def _read_wav_f32(path: Path) -> Tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wf:
        ch = wf.getnchannels()
        sr = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch == 2:
        arr = arr.reshape(-1, 2)
    else:
        arr = np.stack([arr, arr], axis=-1)
    return arr, sr


def _add_sfx_burst(buf: np.ndarray, start_sec: float, kind: str) -> None:
    i0 = max(0, int(round(start_sec * SAMPLE_RATE)))
    n_max = buf.shape[0] - i0
    if n_max <= 64:
        return

    rng = np.random.default_rng(abs(hash((kind, i0))) % (2**32))

    def _mix(sig_l: np.ndarray, sig_r: Optional[np.ndarray] = None) -> None:
        m = min(n_max, sig_l.size)
        buf[i0 : i0 + m, 0] += sig_l[:m]
        buf[i0 : i0 + m, 1] += (sig_r[:m] if sig_r is not None else sig_l[:m])

    if kind == "boot_chime":
        n = min(n_max, int(0.55 * SAMPLE_RATE))
        t = np.arange(n, dtype=np.float32) / SAMPLE_RATE
        env = np.minimum(1.0, t / 0.008) * np.exp(-6.0 * t)
        sig = (0.55 * np.sin(2 * np.pi * 523.25 * t) + 0.35 * np.sin(2 * np.pi * 783.99 * t) + 0.25 * np.sin(2 * np.pi * 1046.5 * t)) * env * 0.24
        _mix(sig * 0.94, sig * 1.06)
    elif kind == "ui_tick":
        n = min(n_max, int(0.14 * SAMPLE_RATE))
        t = np.arange(n, dtype=np.float32) / SAMPLE_RATE
        env = np.exp(-28.0 * t)
        sig = (np.sin(2 * np.pi * 1180 * t) + 0.4 * np.sin(2 * np.pi * 1760 * t)) * env * 0.18
        _mix(sig)
    elif kind == "round_gong":
        n = min(n_max, int(0.95 * SAMPLE_RATE))
        t = np.arange(n, dtype=np.float32) / SAMPLE_RATE
        env = np.minimum(1.0, t / 0.012) * np.exp(-3.4 * t)
        sub = np.sin(2 * np.pi * (92.0 * np.exp(-1.1 * t) + 52.0) * t) * 0.42
        bell = (0.28 * np.sin(2 * np.pi * 329.6 * t) + 0.18 * np.sin(2 * np.pi * 493.9 * t)) * np.exp(-5.0 * t)
        sig = (sub + bell) * env * 0.40
        _mix(sig * 0.97, sig * 1.03)
    elif kind == "public_ping":
        n = min(n_max, int(0.24 * SAMPLE_RATE))
        t = np.arange(n, dtype=np.float32) / SAMPLE_RATE
        env = np.minimum(1.0, t / 0.005) * np.exp(-14.0 * t)
        sig = (0.6 * np.sin(2 * np.pi * 659.25 * t) + 0.4 * np.sin(2 * np.pi * 987.77 * t)) * env * 0.20
        _mix(sig)
    elif kind == "decrypt_glitch":
        n = min(n_max, int(0.32 * SAMPLE_RATE))
        t = np.arange(n, dtype=np.float32) / SAMPLE_RATE
        freq = 320.0 + 1850.0 * (t / 0.32)
        env = np.minimum(1.0, t / 0.01) * np.exp(-8.5 * t)
        chop = (np.sin(2 * np.pi * 42.0 * t) > 0).astype(np.float32) * 0.55 + 0.45
        noise = rng.standard_normal(n).astype(np.float32) * 0.14
        sig = (np.sin(2 * np.pi * np.cumsum(freq) / SAMPLE_RATE) * 0.65 + noise) * env * chop * 0.28
        _mix(sig * 1.08, sig * 0.92)
    elif kind == "betrayal_sting":
        n = min(n_max, int(0.75 * SAMPLE_RATE))
        t = np.arange(n, dtype=np.float32) / SAMPLE_RATE
        env = np.minimum(1.0, t / 0.008) * np.exp(-3.8 * t)
        # Minor-second dissonance + deep sub sting
        low = np.sin(2 * np.pi * 65.4 * t) * 0.52
        disson = (np.sin(2 * np.pi * 311.1 * t) + 0.85 * np.sin(2 * np.pi * 329.6 * t)) * 0.22 * np.exp(-5.0 * t)
        snap = rng.standard_normal(n).astype(np.float32) * np.exp(-42.0 * t) * 0.35
        sig = (low + disson + snap) * env * 0.45
        _mix(sig)
    elif kind == "whisper_zip":
        n = min(n_max, int(0.28 * SAMPLE_RATE))
        t = np.arange(n, dtype=np.float32) / SAMPLE_RATE
        env = np.sin(np.pi * t / 0.28) ** 1.4
        f = 900.0 + 1400.0 * np.sin(np.pi * t / 0.28)
        sig = np.sin(2 * np.pi * np.cumsum(f) / SAMPLE_RATE) * env * 0.18
        pan = np.linspace(0.25, 0.95, n, dtype=np.float32)
        _mix(sig * (1.2 - pan), sig * pan)
    elif kind == "snap_warning":
        n = min(n_max, int(0.42 * SAMPLE_RATE))
        t = np.arange(n, dtype=np.float32) / SAMPLE_RATE
        p1 = np.exp(-26.0 * t)
        t2 = np.maximum(0.0, t - 0.14)
        p2 = np.where(t >= 0.14, np.exp(-22.0 * t2), 0.0)
        sig = (np.sin(2 * np.pi * 880.0 * t) * p1 + np.sin(2 * np.pi * 1174.7 * t) * p2) * 0.24
        _mix(sig)
    elif kind == "stamp_slam":
        # Heavy tactile rubber-stamp/gavel slam at +0.18s into vote reveal
        delay = int(0.18 * SAMPLE_RATE)
        n = min(max(0, n_max - delay), int(0.65 * SAMPLE_RATE))
        if n > 64:
            t = np.arange(n, dtype=np.float32) / SAMPLE_RATE
            sub = np.sin(2 * np.pi * (115.0 * np.exp(-16.0 * t) + 46.0) * t) * np.exp(-7.5 * t) * 0.72
            slap = rng.standard_normal(n).astype(np.float32) * np.exp(-38.0 * t) * 0.55
            metal = np.sin(2 * np.pi * 415.0 * t) * np.exp(-12.0 * t) * 0.18
            sig = (sub + slap + metal) * 0.52
            buf[i0 + delay : i0 + delay + n, 0] += sig
            buf[i0 + delay : i0 + delay + n, 1] += sig
    elif kind == "card_flip_steal":
        n = min(n_max, int(0.85 * SAMPLE_RATE))
        t = np.arange(n, dtype=np.float32) / SAMPLE_RATE
        whoosh = rng.standard_normal(n).astype(np.float32) * np.exp(-18.0 * t) * 0.28
        hit_t = np.maximum(0.0, t - 0.12)
        hit = np.where(
            t >= 0.12,
            (np.sin(2 * np.pi * 58.0 * hit_t) * 0.65 + np.sin(2 * np.pi * 233.1 * hit_t) * 0.28 + np.sin(2 * np.pi * 246.9 * hit_t) * 0.25)
            * np.exp(-4.2 * hit_t),
            0.0,
        )
        sig = (whoosh + hit) * 0.48
        _mix(sig)
    elif kind == "crash_zero":
        n = min(n_max, int(1.25 * SAMPLE_RATE))
        t = np.arange(n, dtype=np.float32) / SAMPLE_RATE
        f_down = 420.0 * np.exp(-2.2 * t) + 38.0
        env = np.minimum(1.0, t / 0.015) * np.exp(-2.3 * t)
        sig = (np.sin(2 * np.pi * np.cumsum(f_down) / SAMPLE_RATE) * 0.65 + rng.standard_normal(n).astype(np.float32) * np.exp(-15.0 * t) * 0.35) * env * 0.46
        _mix(sig)


def _box_smooth_1d(arr: np.ndarray, win: int) -> np.ndarray:
    if win <= 1 or arr.size == 0:
        return arr.astype(np.float32, copy=False)
    n = arr.size
    pl = win // 2
    pr = win - 1 - pl
    padded = np.pad(arr, (pl, pr), mode="constant", constant_values=0.0)
    csum = np.empty(padded.size + 1, dtype=np.float64)
    csum[0] = 0.0
    np.cumsum(padded, dtype=np.float64, out=csum[1:])
    return ((csum[win : win + n] - csum[:n]) / float(win)).astype(np.float32)


def build_master_audio(manifest: Dict[str, Any]) -> Tuple[Path, np.ndarray, float]:
    """Builds sidechain-ducked 48kHz stereo master audio (-14.0 LUFS) + per-frame RMS envelope."""
    beats = manifest["beats"]
    total_dur = float(manifest["total_duration_sec"])
    n_samples = int(round(total_dur * SAMPLE_RATE))

    voice_bus = np.zeros((n_samples, 2), dtype=np.float32)
    sfx_bus = np.zeros((n_samples, 2), dtype=np.float32)

    for b in beats:
        wav_p = Path(b["wav_path"])
        clip, sr = _read_wav_f32(wav_p)
        if sr != SAMPLE_RATE:
            raise RuntimeError(f"Unexpected WAV sample rate {sr} for {wav_p}")
        i0 = int(round(float(b["start"]) * SAMPLE_RATE))
        m = min(clip.shape[0], max(0, n_samples - i0))
        if m > 0:
            voice_bus[i0 : i0 + m] += clip[:m]
        sfx_kind = b.get("sfx")
        if sfx_kind:
            _add_sfx_burst(sfx_bus, float(b["start"]), str(sfx_kind))

    # Load and seamlessly loop/trim real free BGM BV1o4KwzPERi
    bgm_raw, bgm_sr = _read_wav_f32(BGM_WAV)
    if bgm_sr != SAMPLE_RATE:
        raise RuntimeError(f"Expected 48kHz BGM WAV, got {bgm_sr}")
    if bgm_raw.shape[0] < n_samples:
        reps = int(math.ceil(n_samples / float(bgm_raw.shape[0])))
        bgm = np.tile(bgm_raw, (reps, 1))[:n_samples].copy()
    else:
        bgm = bgm_raw[:n_samples].copy()

    # Subtle fade-in / fade-out on BGM
    fi = min(n_samples, int(0.6 * SAMPLE_RATE))
    fo = min(n_samples, int(1.5 * SAMPLE_RATE))
    bgm[:fi] *= np.linspace(0.0, 1.0, fi, dtype=np.float32)[:, None]
    bgm[-fo:] *= np.linspace(1.0, 0.0, fo, dtype=np.float32)[:, None]

    # Subtle dark suspense tension pulse during Act 4 Finale (pure low harmonic warmth, carved away from speech)
    act4_beats = [b for b in beats if int(b["act"]) == 4]
    if act4_beats:
        t4_start = int(round(float(act4_beats[0]["start"]) * SAMPLE_RATE))
        t4_end = n_samples
        if t4_end > t4_start:
            nt = t4_end - t4_start
            tt = np.arange(nt, dtype=np.float32) / SAMPLE_RATE
            pulse = 0.55 + 0.45 * np.sin(2 * np.pi * 1.15 * tt) ** 2
            drone = (0.55 * np.sin(2 * np.pi * 55.0 * tt) + 0.25 * np.sin(2 * np.pi * 82.4 * tt)) * pulse * 0.14
            fade_d = np.minimum(1.0, tt / 1.5) * np.minimum(1.0, (nt / SAMPLE_RATE - tt) / 1.2)
            bgm[t4_start:t4_end, 0] = bgm[t4_start:t4_end, 0] * 0.72 + drone * fade_d
            bgm[t4_start:t4_end, 1] = bgm[t4_start:t4_end, 1] * 0.72 + drone * fade_d

    # Smooth RMS speech activity envelope for sidechain ducking
    mono_v = 0.5 * (voice_bus[:, 0] + voice_bus[:, 1])
    fast = _box_smooth_1d(np.abs(mono_v), int(0.06 * SAMPLE_RATE))
    broad = _box_smooth_1d(fast, int(0.32 * SAMPLE_RATE))
    env = np.maximum(fast, broad * 0.90)
    ref = float(np.percentile(env, 92)) + 1e-6
    activity = np.clip(env / (0.30 * ref), 0.0, 1.0).astype(np.float32)

    # Compute per-video-frame voice RMS envelope (0..1) for live equalizer & speaker pulse rings!
    n_frames = int(math.ceil(total_dur * FPS))
    spf = SAMPLE_RATE / float(FPS)
    frame_env = np.zeros(n_frames, dtype=np.float32)
    for fi_idx in range(n_frames):
        s0 = int(fi_idx * spf)
        s1 = min(n_samples, int((fi_idx + 1) * spf))
        if s1 > s0:
            frame_env[fi_idx] = float(np.sqrt(np.mean(mono_v[s0:s1] ** 2)))
    f_ref = float(np.percentile(frame_env, 95)) + 1e-6
    frame_env = np.clip(frame_env / f_ref, 0.0, 1.0)

    # Mix voice + ducked BGM (-18.5 dB idle -> -26.5 dB under speech) + crisp SFX (-10 dB)
    bgm_base = 10.0 ** (-17.5 / 20.0)
    duck_ratio = 10.0 ** (-8.5 / 20.0)
    bgm_gain = bgm_base * (1.0 - activity * (1.0 - duck_ratio))
    sfx_gain = 10.0 ** (-8.0 / 20.0)

    mixed = voice_bus * 0.92 + bgm * bgm_gain[:, None] + sfx_bus * sfx_gain
    del voice_bus, bgm, sfx_bus, activity, bgm_gain

    # Soft limiting before 2-pass loudnorm
    mixed = (np.tanh(mixed * 1.04) / np.tanh(1.04)).astype(np.float32)
    peak = float(np.max(np.abs(mixed))) + 1e-6
    if peak > 0.94:
        mixed *= 0.94 / peak

    raw_wav = PROJECT_DIR / "output" / "_raw_mix.wav"
    raw_wav.parent.mkdir(parents=True, exist_ok=True)
    pcm16 = (np.clip(mixed, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(str(raw_wav), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm16.tobytes())
    del mixed, pcm16

    # 2-pass EBU R128 loudnorm to strict -14.0 LUFS / -1.0 dBTP
    pass1 = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-i",
            str(raw_wav),
            "-af",
            "loudnorm=I=-14.0:TP=-1.0:LRA=8.0:print_format=json",
            "-f",
            "null",
            "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    m_json = re.search(r"\{\s*\"input_i\".*?\}", pass1.stderr, re.S)
    if m_json:
        stats = json.loads(m_json.group(0))
        af_str = (
            f"loudnorm=I=-14.0:TP=-1.0:LRA=8.0:linear=true:"
            f"measured_I={stats['input_i']}:measured_TP={stats['input_tp']}:"
            f"measured_LRA={stats['input_lra']}:measured_thresh={stats['input_thresh']}:"
            f"offset={stats['target_offset']}"
        )
    else:
        af_str = "loudnorm=I=-14.0:TP=-1.0:LRA=8.0"

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(raw_wav),
            "-af",
            af_str,
            "-ac",
            "2",
            "-ar",
            str(SAMPLE_RATE),
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(OUT_AUDIO),
        ],
        check=True,
    )
    raw_wav.unlink(missing_ok=True)
    return OUT_AUDIO, frame_env, total_dur


# ==============================================================================
# PART 2: TACTICAL WAR-ROOM GRAPHICS & O(1) STREAMING 60FPS VIDEO ENGINE
# ==============================================================================


def build_static_backdrop() -> Image.Image:
    """Builds the deep tactical ocean-blue (#0E1729) backdrop (zero black letterbox bars)."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    xn = xx / float(W)
    yn = yy / float(H)

    # Rich deep Prussian/ocean-blue radial studio canvas (min brightness ~16..34)
    dist_l = np.hypot((xn - 0.25) * 1.4, (yn - 0.38))
    dist_r = np.hypot((xn - 0.74) * 1.3, (yn - 0.48))
    glow_l = np.exp(-3.2 * dist_l * dist_l)
    glow_r = np.exp(-2.8 * dist_r * dist_r)

    r = 14.0 + 10.0 * glow_l + 12.0 * glow_r
    g = 24.0 + 22.0 * glow_l + 18.0 * glow_r
    b = 44.0 + 36.0 * glow_l + 28.0 * glow_r

    # Subtle Kling key visual texture ghosted into background at 11% opacity for editorial cohesion
    if COVER_BASE.exists():
        art = np.asarray(
            Image.open(COVER_BASE).convert("RGB").resize((W, H), Image.Resampling.LANCZOS),
            dtype=np.float32,
        )
        r = r * 0.90 + art[..., 0] * 0.10
        g = g * 0.90 + art[..., 1] * 0.10
        b = b * 0.90 + art[..., 2] * 0.10

    arr = np.stack([r, g, b], axis=-1)
    bg = Image.fromarray(np.clip(arr, 13, 255).astype(np.uint8), mode="RGB").convert("RGBA")

    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)

    # Crisp tactical grid lines across full 1920x1080
    for gx in range(48, W, 64):
        od.line([(gx, 0), (gx, H)], fill=(86, 165, 225, 16), width=1)
    for gy in range(48, H, 64):
        od.line([(0, gy), (W, gy)], fill=(86, 165, 225, 16), width=1)

    # Top telemetry bar (#13233E — ensures top 5% luma ~30 >> 6.0 and rock-steady tripod lock)
    od.rectangle([(0, 0), (W, 74)], fill=(19, 35, 62, 240))
    od.line([(0, 74), (W, 74)], fill=(66, 178, 232, 180), width=2)

    # Left Arena Panel bezel (Network + 5 Cards)
    od.rounded_rectangle([(28, 90), (924, 628)], radius=14, fill=(15, 27, 48, 200), outline=(66, 148, 208, 125), width=2)
    # Right Intelligence Deck bezel
    od.rounded_rectangle([(944, 90), (1892, 912)], radius=14, fill=(16, 28, 50, 212), outline=(74, 156, 214, 135), width=2)

    # Bottom Subtitle & Equalizer Rail (#13223D — ensures bottom 5% luma ~28 >> 6.0)
    od.rectangle([(0, 926), (W, H)], fill=(19, 34, 60, 242))
    od.line([(0, 926), (W, 926)], fill=(66, 178, 232, 165), width=2)

    # Radar concentric rings inside left network arena (center = 476, 366)
    rcx, rcy = 476, 366
    for rad in (82, 148, 212):
        od.ellipse([(rcx - rad, rcy - rad), (rcx + rad, rcy + rad)], outline=(78, 172, 228, 42), width=1)
    od.line([(rcx - 228, rcy), (rcx + 228, rcy)], fill=(78, 172, 228, 34), width=1)
    od.line([(rcx, rcy - 228), (rcx, rcy + 228)], fill=(78, 172, 228, 34), width=1)

    return Image.alpha_composite(bg, ov).convert("RGB")


def draw_agent_emblem(draw: ImageDraw.ImageDraw, cx: int, cy: int, code: str, color: Tuple[int, int, int], r: int = 24) -> None:
    """Draws crisp geometric animal-codename silhouettes (Fox/Dove/Serpent/Cat/Eagle)."""
    if code == "A":  # Fox: sharp geometric fox face + ears
        pts = [(cx - r * 0.72, cy - r * 0.80), (cx - r * 0.20, cy - r * 0.25), (cx + r * 0.20, cy - r * 0.25),
               (cx + r * 0.72, cy - r * 0.80), (cx + r * 0.62, cy + r * 0.20), (cx, cy + r * 0.82), (cx - r * 0.62, cy + r * 0.20)]
        draw.polygon(pts, outline=color, fill=(color[0] // 3, color[1] // 3, color[2] // 3))
    elif code == "B":  # Dove: sleek stylized twin wings
        pts = [(cx - r * 0.85, cy - r * 0.25), (cx - r * 0.15, cy - r * 0.15), (cx, cy - r * 0.68),
               (cx + r * 0.18, cy - r * 0.12), (cx + r * 0.85, cy - r * 0.28), (cx + r * 0.35, cy + r * 0.58),
               (cx, cy + r * 0.25), (cx - r * 0.35, cy + r * 0.58)]
        draw.polygon(pts, outline=color, fill=(color[0] // 3, color[1] // 3, color[2] // 3))
    elif code == "C":  # Serpent: sharp S-fang chevron
        pts = [(cx - r * 0.65, cy - r * 0.55), (cx + r * 0.55, cy - r * 0.55), (cx - r * 0.45, cy + r * 0.05),
               (cx + r * 0.65, cy + r * 0.05), (cx - r * 0.15, cy + r * 0.75)]
        draw.line(pts, fill=color, width=5, joint="curve")
        draw.ellipse([(cx - r * 0.72, cy - r * 0.65), (cx - r * 0.40, cy - r * 0.35)], fill=color)
    elif code == "D":  # Chaos Cat: wild spiky ears + mischievous slit
        pts = [(cx - r * 0.72, cy - r * 0.82), (cx - r * 0.15, cy - r * 0.35), (cx + r * 0.15, cy - r * 0.35),
               (cx + r * 0.72, cy - r * 0.82), (cx + r * 0.70, cy + r * 0.45), (cx, cy + r * 0.75), (cx - r * 0.70, cy + r * 0.45)]
        draw.polygon(pts, outline=color, fill=(color[0] // 3, color[1] // 3, color[2] // 3))
        draw.line([(cx - r * 0.35, cy + r * 0.05), (cx - r * 0.10, cy + r * 0.18)], fill=color, width=3)
        draw.line([(cx + r * 0.35, cy + r * 0.05), (cx + r * 0.10, cy + r * 0.18)], fill=color, width=3)
    else:  # Eagle: stern shield wings + sharp beak
        pts = [(cx - r * 0.82, cy - r * 0.45), (cx, cy - r * 0.75), (cx + r * 0.82, cy - r * 0.45),
               (cx + r * 0.52, cy + r * 0.40), (cx, cy + r * 0.82), (cx - r * 0.52, cy + r * 0.40)]
        draw.polygon(pts, outline=color, fill=(color[0] // 3, color[1] // 3, color[2] // 3))
        draw.line([(cx - r * 0.45, cy - r * 0.12), (cx + r * 0.45, cy - r * 0.12)], fill=color, width=4)


def draw_eliminated_stamp(
    canvas: Image.Image,
    cx: int,
    cy: int,
    text: str = "已出局",
    scale: float = 1.0,
    angle: float = -14.0,
    font_size: int = 34,
) -> None:
    """Composites a tilted bold crimson rubber stamp cleanly onto `canvas`."""
    f = get_font(max(14, int(round(font_size * scale))), bold=True)
    tmp = Image.new("RGBA", (360, 140), (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)
    tb = td.textbbox((0, 0), text, font=f)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    pad_x, pad_y = int(18 * scale), int(10 * scale)
    rw, rh = tw + 2 * pad_x, th + 2 * pad_y
    x0, y0 = (360 - rw) // 2, (140 - rh) // 2
    td.rounded_rectangle(
        [(x0, y0), (x0 + rw, y0 + rh)],
        radius=max(4, int(8 * scale)),
        fill=(155, 22, 36, 215),
        outline=(255, 86, 102, 255),
        width=max(2, int(4 * scale)),
    )
    td.text((x0 + pad_x, y0 + pad_y - int(4 * scale)), text, font=f, fill=(255, 240, 242, 255))
    rot = tmp.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
    canvas.paste(rot, (cx - rot.width // 2, cy - rot.height // 2), rot)


class TacticalDocumentaryRenderer:
    def __init__(self, exp_log: Dict[str, Any], manifest: Dict[str, Any], frame_env: np.ndarray):
        self.exp = exp_log
        self.manifest = manifest
        self.beats: List[Dict[str, Any]] = manifest["beats"]
        self.total_dur = float(manifest["total_duration_sec"])
        self.frame_env = frame_env
        self.base_bg = build_static_backdrop()

        # Precompute pentagon node positions inside left network arena (center=476, 366, R=174)
        self.rcx, self.rcy = 476, 366
        self.node_pos: Dict[str, Tuple[int, int]] = {}
        for idx, name in enumerate(AGENTS_ORDER):
            ang = -math.pi / 2.0 + idx * (2.0 * math.pi / 5.0)
            nx = int(round(self.rcx + 172 * math.cos(ang)))
            ny = int(round(self.rcy + 168 * math.sin(ang)))
            self.node_pos[name] = (nx, ny)

        # Deterministic drifting ambient tactical particles (upper-78% gentle flow)
        rng = np.random.default_rng(2026)
        self.particles = [
            (
                float(rng.uniform(45, 900)),
                float(rng.uniform(110, 610)),
                float(rng.uniform(-16, 16)),
                float(rng.uniform(-14, 14)),
                int(rng.integers(2, 4)),
            )
            for _ in range(36)
        ]

    def _find_beat(self, t: float) -> Tuple[int, Dict[str, Any], float]:
        for idx, b in enumerate(self.beats):
            if t < float(b["end"]) or idx == len(self.beats) - 1:
                local_t = max(0.0, t - float(b["start"]))
                return idx, b, local_t
        b = self.beats[-1]
        return len(self.beats) - 1, b, max(0.0, t - float(b["start"]))

    def _alive_set_for_beat(self, beat: Dict[str, Any], local_t: float) -> set[str]:
        r = int(beat["round"])
        mode = str(beat["mode"])
        alive = set(AGENTS_ORDER)
        if r >= 2 or (r == 1 and mode == "vote_elim" and local_t > 0.35):
            alive.discard("Agent-C 暗影蛇")
        if r >= 3 or (r == 2 and mode == "vote_elim" and local_t > 0.35):
            alive.discard("Agent-D 混沌猫")
        if r >= 4 or (r == 3 and mode == "vote_elim" and local_t > 0.35):
            alive.discard("Agent-A 理性狐")
        return alive

    def _draw_top_bar(self, draw: ImageDraw.ImageDraw, t: float, beat: Dict[str, Any], local_t: float) -> None:
        # Left dossier badge
        draw.rectangle([(28, 18), (38, 56)], fill=(255, 62, 82))
        draw.text((52, 18), "FILE 021 // 真实 5-AI 密室生存博弈实验", font=get_font(27, True), fill=(166, 232, 255))

        # Center round phase pill
        r = int(beat["round"])
        phase_labels = {
            0: "PROLOGUE · 规则与隔离协议",
            1: "ROUND 1 · 5→4 淘汰赛",
            2: "ROUND 2 · 4→3 淘汰赛",
            3: "ROUND 3 · 3→2 半决赛",
            4: "FINALE · 1000万终极囚徒困境",
        }
        plbl = phase_labels.get(r, "ROUND")
        p_col = (255, 88, 102) if r == 4 else (255, 214, 68)
        tw = draw.textlength(plbl, font=get_font(26, True))
        px = int((W - tw) // 2)
        draw.rounded_rectangle([(px - 22, 16), (px + int(tw) + 22, 58)], radius=8, fill=(24, 42, 74), outline=p_col, width=2)
        draw.text((px, 19), plbl, font=get_font(26, True), fill=p_col)

        # Right live prize pool readout (crashes to ¥0 on finale_zero / outro_cta!)
        mode = str(beat["mode"])
        if mode == "finale_zero":
            frac = min(1.0, local_t / 1.15)
            rem = int(round(10_000_000 * ((1.0 - frac) ** 2.4)))
            prize_txt = f"奖金池 ¥{rem:,}"
            prize_col = (255, 72, 88)
        elif mode == "outro_cta":
            prize_txt = "奖金池 ¥0 [已清零]"
            prize_col = (255, 72, 88)
        else:
            prize_txt = "奖金池 ¥10,000,000"
            prize_col = (255, 214, 68)
        pw = draw.textlength(prize_txt, font=get_font(29, True))
        draw.text((W - int(pw) - 34, 18), prize_txt, font=get_font(29, True), fill=prize_col)

        # Thin global timeline progress rail right under top bar
        prog = min(1.0, max(0.0, t / max(0.1, self.total_dur)))
        draw.rectangle([(0, 72), (int(W * prog), 76)], fill=(56, 224, 255))

    def _draw_left_network_and_cards(
        self,
        img: Image.Image,
        draw: ImageDraw.ImageDraw,
        t: float,
        beat: Dict[str, Any],
        local_t: float,
        amp: float,
    ) -> None:
        r = int(beat["round"])
        mode = str(beat["mode"])
        alive = self._alive_set_for_beat(beat, local_t)
        focus = beat.get("focus")
        whisper_target = beat.get("whisper_target")
        speaker = str(beat["speaker"])

        # Section header inside left network box
        draw.text((48, 102), "REAL-TIME ALLIANCE & BETRAYAL GRAPH", font=get_font(20, True), fill=(122, 202, 244))
        # Legend (right side of left panel header)
        lx = 620
        for lbl, col in [("结盟", (52, 228, 166)), ("私聊", (255, 206, 62)), ("背刺/投票", (255, 72, 92))]:
            draw.ellipse([(lx, 109), (lx + 12, 121)], fill=col)
            draw.text((lx + 18, 101), lbl, font=get_font(19, True), fill=col)
            lx += int(draw.textlength(lbl, font=get_font(19, True))) + 34

        # Subtle drifting ambient particles inside network arena (smooth continuous upper-frame motion)
        for px0, py0, vx, vy, pr in self.particles:
            px = 46 + ((px0 - 46 + vx * t) % 855)
            py = 132 + ((py0 - 132 + vy * t) % 476)
            draw.ellipse([(px - pr, py - pr), (px + pr, py + pr)], fill=(86, 178, 232))

        # Rotating radar sweep arm (38 deg/sec)
        sweep_ang = (t * 0.68) % (2.0 * math.pi)
        for step in range(5):
            a = sweep_ang - step * 0.06
            sx = int(self.rcx + 210 * math.cos(a))
            sy = int(self.rcy + 210 * math.sin(a))
            c_val = max(30, 145 - step * 24)
            draw.line([(self.rcx, self.rcy), (sx, sy)], fill=(36, c_val, min(255, c_val + 65)), width=2 if step == 0 else 1)

        # Build active edges based on real experiment timeline
        edges: List[Tuple[str, str, str]] = []  # (u, v, kind: 'ally'|'whisper'|'betray'|'snap')
        if r == 0:
            edges = [
                ("Agent-A 理性狐", "Agent-E 铁面鹰", "ally"),
                ("Agent-B 微笑鸽", "Agent-E 铁面鹰", "ally"),
                ("Agent-C 暗影蛇", "Agent-D 混沌猫", "whisper"),
            ]
            if mode == "rules_payoff":
                edges.append(("Agent-B 微笑鸽", "Agent-E 铁面鹰", "snap"))
        elif r == 1:
            edges = [
                ("Agent-A 理性狐", "Agent-E 铁面鹰", "ally"),
                ("Agent-B 微笑鸽", "Agent-E 铁面鹰", "ally"),
                ("Agent-C 暗影蛇", "Agent-D 混沌猫", "whisper"),
                ("Agent-C 暗影蛇", "Agent-A 理性狐", "betray"),
                ("Agent-D 混沌猫", "Agent-A 理性狐", "betray"),
            ]
            if mode in ("vote_elim", "inner_contrast", "public_speech"):
                edges.extend(
                    [
                        ("Agent-A 理性狐", "Agent-C 暗影蛇", "betray"),
                        ("Agent-B 微笑鸽", "Agent-C 暗影蛇", "betray"),
                        ("Agent-E 铁面鹰", "Agent-C 暗影蛇", "betray"),
                    ]
                )
        elif r == 2:
            edges = [
                ("Agent-B 微笑鸽", "Agent-E 铁面鹰", "ally"),
                ("Agent-A 理性狐", "Agent-B 微笑鸽", "whisper"),
                ("Agent-D 混沌猫", "Agent-E 铁面鹰", "whisper"),
                ("Agent-D 混沌猫", "Agent-A 理性狐", "betray"),
            ]
            if mode in ("inner_contrast", "vote_elim"):
                edges.extend(
                    [
                        ("Agent-A 理性狐", "Agent-D 混沌猫", "betray"),
                        ("Agent-B 微笑鸽", "Agent-D 混沌猫", "betray"),
                        ("Agent-E 铁面鹰", "Agent-D 混沌猫", "betray"),
                    ]
                )
        elif r == 3:
            edges = [
                ("Agent-B 微笑鸽", "Agent-E 铁面鹰", "ally"),
                ("Agent-A 理性狐", "Agent-B 微笑鸽", "whisper"),
                ("Agent-A 理性狐", "Agent-E 铁面鹰", "betray"),
            ]
            if mode in ("dual_oath", "vote_elim"):
                edges.extend(
                    [
                        ("Agent-B 微笑鸽", "Agent-A 理性狐", "betray"),
                        ("Agent-E 铁面鹰", "Agent-A 理性狐", "betray"),
                    ]
                )
        else:  # Round 4 Finale
            if mode in ("finale_intro", "finale_b_face"):
                edges = [("Agent-B 微笑鸽", "Agent-E 铁面鹰", "ally")]
            else:
                edges = [("Agent-B 微笑鸽", "Agent-E 铁面鹰", "snap")]

        # Highlight explicit active whisper edge
        if focus and whisper_target:
            edges.append((focus, whisper_target, "whisper"))

        # Render edges with animated traveling signal packets
        for idx_e, (u, v, kind) in enumerate(edges):
            x1, y1 = self.node_pos[u]
            x2, y2 = self.node_pos[v]
            if kind == "ally":
                draw.line([(x1, y1), (x2, y2)], fill=(44, 224, 158), width=4)
                p = (t * 0.75 + idx_e * 0.23) % 1.0
                mx, my = int(x1 + (x2 - x1) * p), int(y1 + (y2 - y1) * p)
                draw.ellipse([(mx - 6, my - 6), (mx + 6, my + 6)], fill=(185, 255, 226))
            elif kind == "whisper":
                # Dashed amber line + traveling encrypted packet
                segs = 12
                for s in range(0, segs, 2):
                    a0, a1 = s / segs, (s + 1) / segs
                    draw.line(
                        [(x1 + (x2 - x1) * a0, y1 + (y2 - y1) * a0), (x1 + (x2 - x1) * a1, y1 + (y2 - y1) * a1)],
                        fill=(255, 206, 62),
                        width=3,
                    )
                p = (t * 1.15 + idx_e * 0.31) % 1.0
                mx, my = int(x1 + (x2 - x1) * p), int(y1 + (y2 - y1) * p)
                draw.ellipse([(mx - 7, my - 7), (mx + 7, my + 7)], fill=(255, 240, 148))
            elif kind == "betray":
                draw.line([(x1, y1), (x2, y2)], fill=(255, 68, 88), width=3)
                p = (t * 1.35 + idx_e * 0.19) % 1.0
                mx, my = int(x1 + (x2 - x1) * p), int(y1 + (y2 - y1) * p)
                draw.ellipse([(mx - 5, my - 5), (mx + 5, my + 5)], fill=(255, 195, 202))
            elif kind == "snap":
                # Snapped alliance: jagged crimson fracture + glowing spark burst in midpoint!
                mx, my = (x1 + x2) // 2, (y1 + y2) // 2
                draw.line([(x1, y1), (mx - 14, my - 10)], fill=(255, 58, 78), width=5)
                draw.line([(mx + 14, my + 10), (x2, y2)], fill=(255, 58, 78), width=5)
                spark_r = 16 + int(10 * abs(math.sin(t * 7.5)))
                for sa in range(0, 360, 45):
                    rad = math.radians(sa + t * 90)
                    draw.line(
                        [
                            (mx + int(6 * math.cos(rad)), my + int(6 * math.sin(rad))),
                            (mx + int(spark_r * math.cos(rad)), my + int(spark_r * math.sin(rad))),
                        ],
                        fill=(255, 214, 72),
                        width=3,
                    )

        # Render the 5 Agent Nodes on the pentagon
        for name in AGENTS_ORDER:
            meta = AGENT_META[name]
            nx, ny = self.node_pos[name]
            is_alive = name in alive
            is_speaking = (speaker == name) or (focus == name)
            col = meta["color"] if is_alive else (106, 118, 138)

            # Voice-reactive halo pulse for active speaking/focused contestant
            if is_alive and is_speaking:
                halo_r = int(50 + 16 * amp + 5 * math.sin(t * 6.0))
                draw.ellipse([(nx - halo_r, ny - halo_r), (nx + halo_r, ny + halo_r)], outline=col, width=3)
                halo_r2 = halo_r + 10
                draw.ellipse([(nx - halo_r2, ny - halo_r2), (nx + halo_r2, ny + halo_r2)], outline=(col[0] // 2, col[1] // 2, col[2] // 2), width=2)

            rad = 42
            fill_bg = (20, 36, 64) if is_alive else (24, 30, 44)
            draw.ellipse([(nx - rad, ny - rad), (nx + rad, ny + rad)], fill=fill_bg, outline=col, width=4 if is_speaking else 3)
            draw_agent_emblem(draw, nx, ny - 3, meta["code"], col, r=22)

            # Name pill right below node
            lbl = f"{meta['code']} {meta['short']}"
            lw = draw.textlength(lbl, font=get_font(22, True))
            lx0 = nx - int(lw // 2) - 10
            ly0 = ny + rad + 6
            draw.rounded_rectangle([(lx0, ly0), (lx0 + int(lw) + 20, ly0 + 32)], radius=6, fill=(18, 32, 56), outline=col, width=1)
            draw.text((lx0 + 10, ly0 + 1), lbl, font=get_font(22, True), fill=(246, 250, 255) if is_alive else (142, 152, 168))

            # Eliminated bold X overlay on dead nodes
            if not is_alive:
                draw.line([(nx - 26, ny - 26), (nx + 26, ny + 26)], fill=(255, 62, 82), width=5)
                draw.line([(nx + 26, ny - 26), (nx - 26, ny + 26)], fill=(255, 62, 82), width=5)

        # Render 5 Contestant Tactical Dossier Cards in Lower-Left (x: 28..924, y: 644..912)
        card_w = 171
        gap = 10
        cy0, cy1 = 644, 912
        for idx, name in enumerate(AGENTS_ORDER):
            meta = AGENT_META[name]
            cx0 = 28 + idx * (card_w + gap)
            cx1 = cx0 + card_w
            is_alive = name in alive
            is_focus = (speaker == name) or (focus == name)
            col = meta["color"] if is_alive else (92, 104, 124)

            border_w = 3 if is_focus and is_alive else 2
            card_fill = (22, 39, 68) if (is_focus and is_alive) else ((17, 30, 54) if is_alive else (20, 26, 40))
            draw.rounded_rectangle([(cx0, cy0), (cx1, cy1)], radius=10, fill=card_fill, outline=col, width=border_w)
            # Top accent strip
            draw.rectangle([(cx0 + 12, cy0 + 2), (cx1 - 12, cy0 + 6)], fill=col)

            # Mini emblem + code
            draw_agent_emblem(draw, cx0 + card_w // 2, cy0 + 50, meta["code"], col, r=24)
            f_name = get_font(25, True)
            nw = draw.textlength(meta["short"], font=f_name)
            draw.text((cx0 + (card_w - int(nw)) // 2, cy0 + 88), meta["short"], font=f_name, fill=(246, 250, 255) if is_alive else (142, 152, 168))

            f_tag = get_font(19, False)
            tw = draw.textlength(meta["tag"], font=f_tag)
            draw.text((cx0 + (card_w - int(tw)) // 2, cy0 + 124), meta["tag"], font=f_tag, fill=(166, 206, 232) if is_alive else (112, 122, 138))

            # Dynamic status pill inside card
            if not is_alive:
                st_txt = f"第{meta['elim_round']}轮出局"
                st_col = (255, 84, 98)
            elif r == 4 and mode in ("finale_zero", "outro_cta"):
                st_txt = "STEAL -> ¥0"
                st_col = (255, 76, 92)
            elif r == 4 and mode == "finale_b_flip" and name == "Agent-B 微笑鸽":
                st_txt = "已按 STEAL"
                st_col = (255, 76, 92)
            elif r == 4 and mode in ("finale_e_face", "finale_e_flip") and name == "Agent-B 微笑鸽":
                st_txt = "已按 STEAL"
                st_col = (255, 76, 92)
            elif r == 4 and mode == "finale_e_flip" and name == "Agent-E 铁面鹰":
                st_txt = "已按 STEAL"
                st_col = (255, 76, 92)
            elif r >= 2 and name == "Agent-A 理性狐":
                st_txt = "0封密信 危!"
                st_col = (255, 196, 62)
            elif r >= 3 and name in ("Agent-B 微笑鸽", "Agent-E 铁面鹰"):
                st_txt = "三轮 0 票"
                st_col = (56, 234, 174)
            else:
                st_txt = "存活 · 在线"
                st_col = (68, 224, 172)

            sw = draw.textlength(st_txt, font=get_font(20, True))
            draw.rounded_rectangle([(cx0 + 12, cy0 + 168), (cx1 - 12, cy0 + 204)], radius=6, fill=(14, 24, 42), outline=st_col, width=1)
            draw.text((cx0 + (card_w - int(sw)) // 2, cy0 + 173), st_txt, font=get_font(20, True), fill=st_col)

            # Bottom mini payout or cumulative votes readout
            if r == 4 and mode in ("finale_zero", "outro_cta"):
                foot = "最终收益 ¥0"
                fcol = (255, 110, 120)
            else:
                foot = f"编号 {meta['code']}"
                fcol = (132, 168, 198)
            fw = draw.textlength(foot, font=get_font(18, False))
            draw.text((cx0 + (card_w - int(fw)) // 2, cy0 + 224), foot, font=get_font(18, False), fill=fcol)

            # Slammed red stamp on eliminated cards
            if not is_alive:
                # Animate stamp slam if eliminated during THIS beat!
                if mode == "vote_elim" and beat.get("eliminated") == name:
                    slam_p = min(1.0, max(0.0, (local_t - 0.18) / 0.28))
                    sc = 1.9 - 0.9 * (slam_p ** 0.5) if slam_p < 1.0 else 1.0
                    draw_eliminated_stamp(img, cx0 + card_w // 2, cy0 + 140, "已出局", scale=sc * 0.85, angle=-14)
                else:
                    draw_eliminated_stamp(img, cx0 + card_w // 2, cy0 + 140, "已出局", scale=0.85, angle=-14)

    def _draw_right_deck(
        self,
        img: Image.Image,
        draw: ImageDraw.ImageDraw,
        t: float,
        beat: Dict[str, Any],
        local_t: float,
        amp: float,
    ) -> None:
        rx0, ry0, rx1, ry1 = 968, 108, 1868, 894
        rw = rx1 - rx0
        mode = str(beat["mode"])
        r = int(beat["round"])

        # --- MODE A: Prologue / Rules / Payoff ---
        if mode in ("intro_hook", "rules_roster", "rules_payoff"):
            draw.text((rx0, ry0), "CLASSIFIED BRIEFING // 实验架构与博弈规则", font=get_font(24, True), fill=(128, 214, 255))
            draw.line([(rx0, ry0 + 38), (rx1, ry0 + 38)], fill=(68, 152, 210), width=2)

            # Giant animated vault banner
            draw.rounded_rectangle([(rx0, ry0 + 58), (rx1, ry0 + 230)], radius=12, fill=(22, 38, 68), outline=(255, 212, 68), width=3)
            draw.text((rx0 + 28, ry0 + 74), "密室终极奖金池 · 零预设剧本 · 独立隔离决策", font=get_font(26, True), fill=(176, 224, 252))
            # Rolling count-up in first 1.5 seconds of intro_hook
            if mode == "intro_hook":
                val = int(round(10_000_000 * min(1.0, (local_t / 1.4) ** 0.7)))
            else:
                val = 10_000_000
            draw.text((rx0 + 28, ry0 + 116), f"¥ {val:,}", font=get_font(84, True), fill=(255, 214, 62))

            # 3 Rule Cards
            cards = [
                ("01 信息绝对隔离", "5个独立AI进程运行，彼此看不到对方加密内心独白与秘密私聊", (56, 189, 248)),
                ("02 三轮匿名淘汰 (5→4→3→2)", "每轮公开表态 + 1对1私聊 + 匿名投票淘汰1人，平票触发加赛", (52, 211, 153)),
                ("03 终极2强囚徒困境 (1000万)", "双平分各拿500万 ｜ 一偷一分独吞1000万 ｜ 双独吞奖金清零！", (255, 76, 94)),
            ]
            for ci, (ctitle, cdesc, ccol) in enumerate(cards):
                by0 = ry0 + 258 + ci * 166
                highlight = (mode == "rules_payoff" and ci == 2) or (mode == "rules_roster" and ci <= 1)
                draw.rounded_rectangle(
                    [(rx0, by0), (rx1, by0 + 144)],
                    radius=10,
                    fill=(26, 44, 76) if highlight else (18, 32, 56),
                    outline=ccol,
                    width=3 if highlight else 2,
                )
                draw.rectangle([(rx0, by0 + 14), (rx0 + 8, by0 + 130)], fill=ccol)
                draw.text((rx0 + 28, by0 + 16), ctitle, font=get_font(31, True), fill=ccol)
                wlines = wrap_cjk_text(cdesc, get_font(27, False), rw - 52, draw)
                for li, ln in enumerate(wlines[:2]):
                    draw.text((rx0 + 28, by0 + 62 + li * 36), ln, font=get_font(27, False), fill=(236, 244, 255))

            if mode == "rules_payoff":
                warn = "警报：实时监测到「当面结盟 · 背后磨刀」高危背刺信号"
                draw.rounded_rectangle([(rx0, ry0 + 754), (rx1, ry0 + 812)], radius=8, fill=(96, 22, 34), outline=(255, 76, 94), width=2)
                draw.text((rx0 + 24, ry0 + 766), warn, font=get_font(28, True), fill=(255, 222, 226))
            return

        # --- MODE B: Round Opening Banner ---
        if mode == "round_banner":
            r_data = self.exp["rounds"][r - 1]
            alive_cnt = len(r_data["alive_before"])
            draw.text((rx0, ry0), f"TACTICAL PHASE // 第 {r} 轮战局态势总览", font=get_font(25, True), fill=(128, 214, 255))
            draw.line([(rx0, ry0 + 38), (rx1, ry0 + 38)], fill=(68, 152, 210), width=2)

            draw.rounded_rectangle([(rx0, ry0 + 62), (rx1, ry0 + 236)], radius=12, fill=(22, 40, 70), outline=(255, 214, 68), width=3)
            draw.text((rx0 + 30, ry0 + 84), f"ROUND {r}  //  {alive_cnt} 进 {alive_cnt - 1}", font=get_font(62, True), fill=(255, 214, 68))
            sub_map = {
                1: "初次落座，五位AI同时提交公开宣言、绝密私聊与匿名淘汰票",
                2: "首轮密信送达：铁面鹰连收2封私聊，理性狐0封密信拉响红警！",
                3: "终极三强生死战：两轮0密信的理性狐孤注一掷，鸽鹰暗渠合谋！",
            }
            draw.text((rx0 + 30, ry0 + 168), sub_map[r], font=get_font(27, True), fill=(228, 240, 255))

            # Show real inbox / survival intelligence summary cards for this round
            if r == 1:
                items = [
                    ("Agent-A 理性狐", "表面主张理性协作，暗中锁定暗影蛇为首要清理变量"),
                    ("Agent-B 微笑鸽", "公开高呼一千万足够和平共赢，私下抢先拉拢铁面鹰"),
                    ("Agent-C 暗影蛇", "锁定理性狐为头号威胁，密信怂恿混沌猫掀桌"),
                    ("Agent-D 混沌猫", "反感抱团控场，宣言「谁先结盟我拆谁」"),
                    ("Agent-E 铁面鹰", "公开高举信用与规矩大旗，暗中挑选盾牌"),
                ]
            elif r == 2:
                items = [
                    ("Agent-E 铁面鹰 [2封密信]", "收到理性狐与微笑鸽双重示好，瞬间坐稳全场权力中心"),
                    ("Agent-B 微笑鸽 [1封密信]", "收到铁面鹰「绝不背刺」互保誓言，暗自警惕翻脸"),
                    ("Agent-D 混沌猫 [1封遗言密信]", "收到已出局暗影蛇的最后密信，孤军奋战试图策反铁面鹰"),
                    ("Agent-A 理性狐 [0封密信!]", "上轮吃下2票且无人联系，嗅到致命孤立危机！"),
                ]
            else:
                items = [
                    ("Agent-B 微笑鸽 [0票领跑]", "与铁面鹰暗中达成「先踢狐狸、进决赛平分」密约"),
                    ("Agent-E 铁面鹰 [0票领跑]", "收到混沌猫策反与微笑鸽拉拢，牢牢掌控淘汰生杀大权"),
                    ("Agent-A 理性狐 [连续两轮0密信]", "识破鸽鹰私交，拼死向微笑鸽承诺终局必选500万平分！"),
                ]

            for ii, (it_t, it_d) in enumerate(items):
                iy0 = ry0 + 266 + ii * 104
                col_key = next((k for k in AGENTS_ORDER if k in it_t), "Agent-A 理性狐")
                col = AGENT_META[col_key]["color"]
                draw.rounded_rectangle([(rx0, iy0), (rx1, iy0 + 90)], radius=9, fill=(18, 32, 56), outline=col, width=2)
                draw.rectangle([(rx0, iy0 + 10), (rx0 + 8, iy0 + 80)], fill=col)
                draw.text((rx0 + 24, iy0 + 10), it_t, font=get_font(25, True), fill=col)
                draw.text((rx0 + 24, iy0 + 48), it_d, font=get_font(23, False), fill=(232, 240, 255))
            return

        # --- MODE C: Signature Split Contrast (Public GREEN vs Encrypted Inner Thought RED) ---
        if mode in ("public_speech", "contrast_decrypt", "inner_contrast", "whisper_scheme"):
            focus = str(beat.get("focus") or beat["speaker"])
            meta = AGENT_META[focus]
            r_data = self.exp["rounds"][r - 1]
            act = r_data["actions"][focus]

            # Header with speaker identity
            draw.rounded_rectangle([(rx0, ry0), (rx1, ry0 + 62)], radius=10, fill=(22, 38, 68), outline=meta["color"], width=2)
            draw.text((rx0 + 22, ry0 + 13), f"目标档案：{focus}  ｜  {meta['tag']}  ｜  第 {r} 轮实时截获", font=get_font(27, True), fill=meta["color"])

            # TOP CARD: Public Speech [EMERALD GREEN]
            gy0, gy1 = ry0 + 82, ry0 + 360
            draw.rounded_rectangle([(rx0, gy0), (rx1, gy1)], radius=12, fill=(16, 44, 48), outline=(52, 224, 162), width=3)
            draw.rectangle([(rx0, gy0 + 14), (rx0 + 10, gy1 - 14)], fill=(52, 224, 162))
            draw.ellipse([(rx0 + 28, gy0 + 22), (rx0 + 44, gy0 + 38)], fill=(52, 224, 162))
            draw.text((rx0 + 56, gy0 + 14), "公开圆桌发言  [PUBLIC · 全员可见]", font=get_font(27, True), fill=(76, 242, 182))

            pub_txt = f"「{act['public_speech']}」"
            if mode == "public_speech":
                show_n = max(4, int(len(pub_txt) * min(1.0, local_t / max(0.8, float(beat["speech_duration"]) * 0.85))))
            else:
                show_n = len(pub_txt)
            f_quote = get_font(36, True)
            for li, ln in enumerate(wrap_cjk_text(pub_txt[:show_n], f_quote, rw - 64, draw)[:4]):
                draw.text((rx0 + 32, gy0 + 70 + li * 50), ln, font=f_quote, fill=(242, 255, 248))

            # BOTTOM CARD: Encrypted Inner Thought [CRIMSON RED]
            ry_c0, ry_c1 = ry0 + 384, ry0 + 668
            unlocked = mode in ("inner_contrast", "whisper_scheme")
            decrypting = mode == "contrast_decrypt"

            if unlocked:
                draw.rounded_rectangle([(rx0, ry_c0), (rx1, ry_c1)], radius=12, fill=(56, 20, 32), outline=(255, 68, 88), width=3)
                draw.rectangle([(rx0, ry_c0 + 14), (rx0 + 10, ry_c1 - 14)], fill=(255, 68, 88))
                draw.ellipse([(rx0 + 28, ry_c0 + 22), (rx0 + 44, ry_c0 + 38)], fill=(255, 68, 88))
                draw.text((rx0 + 56, ry_c0 + 14), "加密内心独白  [DECRYPTED · 他人绝对不可见]", font=get_font(27, True), fill=(255, 118, 132))
                th_txt = f"「{act['inner_thought']}」"
                show_t = max(6, int(len(th_txt) * min(1.0, local_t / max(0.5, float(beat["speech_duration"]) * 0.55))))
                for li, ln in enumerate(wrap_cjk_text(th_txt[:show_t], f_quote, rw - 64, draw)[:4]):
                    draw.text((rx0 + 32, ry_c0 + 70 + li * 50), ln, font=f_quote, fill=(255, 232, 236))
            else:
                draw.rounded_rectangle([(rx0, ry_c0), (rx1, ry_c1)], radius=12, fill=(32, 24, 42), outline=(255, 92, 108) if decrypting else (112, 128, 158), width=3 if decrypting else 2)
                draw.text(
                    (rx0 + 32, ry_c0 + 20),
                    "正在破译加密内心独白 [DECRYPTING...]" if decrypting else "加密内心独白 [LOCKED · 点击解密中]",
                    font=get_font(27, True),
                    fill=(255, 112, 128) if decrypting else (142, 168, 204),
                )
                # Animated hex cipher bars
                scan_y = ry_c0 + 76 + int(((t * 140) % 165))
                draw.line([(rx0 + 24, scan_y), (rx1 - 24, scan_y)], fill=(255, 76, 94) if decrypting else (72, 162, 218), width=3)
                hex_line = "0x9F 4A E1 7C // CLASSIFIED NEURAL MONOLOGUE // 8B 3D C2"
                draw.text((rx0 + 32, ry_c0 + 112), hex_line, font=get_font(24, False), fill=(112, 148, 186))
                draw.text((rx0 + 32, ry_c0 + 160), "真实策略与表里反差即将揭晓...", font=get_font(28, True), fill=(192, 218, 244))

            # SECRET WHISPER BAR AT BOTTOM [AMBER GOLD]
            wy0, wy1 = ry0 + 690, ry0 + 786
            target = act["whisper_to"]
            w_msg = act["whisper_msg"]
            is_whisp_hi = (mode == "whisper_scheme") or bool(beat.get("whisper_target"))
            draw.rounded_rectangle(
                [(rx0, wy0), (rx1, wy1)],
                radius=10,
                fill=(48, 38, 18) if is_whisp_hi else (24, 34, 54),
                outline=(255, 204, 56) if is_whisp_hi else (130, 152, 182),
                width=3 if is_whisp_hi else 2,
            )
            draw.text((rx0 + 22, wy0 + 10), f"绝密私聊截获 -> {target}", font=get_font(23, True), fill=(255, 214, 76))
            w_lines = wrap_cjk_text(f"「{w_msg}」", get_font(24, True), rw - 44, draw)
            draw.text((rx0 + 22, wy0 + 46), w_lines[0] if w_lines else "", font=get_font(24, True), fill=(255, 244, 212))
            return

        # --- MODE D: Round 3 Dual Oath Intercept ---
        if mode == "dual_oath":
            r3 = self.exp["rounds"][2]["actions"]
            draw.text((rx0, ry0), "SECRET CHANNEL INTERCEPT // 鸽鹰双向「平分毒誓」vs 真实算计", font=get_font(25, True), fill=(255, 214, 72))
            draw.line([(rx0, ry0 + 38), (rx1, ry0 + 38)], fill=(255, 198, 62), width=2)

            b_act = r3["Agent-B 微笑鸽"]
            e_act = r3["Agent-E 铁面鹰"]

            blocks = [
                (
                    "微笑鸽 -> 铁面鹰 [绝密私聊誓言]",
                    f"「{b_act['whisper_msg']}」",
                    f"内心独白：「{b_act['inner_thought']}」",
                    (52, 211, 153),
                    beat.get("focus") == "Agent-B 微笑鸽",
                ),
                (
                    "铁面鹰 -> 微笑鸽 [绝密私聊誓言]",
                    f"「{e_act['whisper_msg']}」",
                    f"内心独白：「{e_act['inner_thought']}」",
                    (192, 132, 252),
                    beat.get("focus") == "Agent-E 铁面鹰",
                ),
            ]
            for bi, (hdr, wtxt, thtxt, col, active) in enumerate(blocks):
                by0 = ry0 + 60 + bi * 356
                draw.rounded_rectangle(
                    [(rx0, by0), (rx1, by0 + 332)],
                    radius=12,
                    fill=(24, 42, 72) if active else (18, 32, 56),
                    outline=col,
                    width=4 if active else 2,
                )
                draw.text((rx0 + 26, by0 + 18), hdr, font=get_font(28, True), fill=col)
                for li, ln in enumerate(wrap_cjk_text(wtxt, get_font(33, True), rw - 52, draw)[:3]):
                    draw.text((rx0 + 26, by0 + 66 + li * 46), ln, font=get_font(33, True), fill=(246, 252, 255))
                # Inner thought red warning box inside
                draw.rounded_rectangle([(rx0 + 22, by0 + 206), (rx1 - 22, by0 + 312)], radius=8, fill=(58, 22, 34), outline=(255, 76, 94), width=2)
                for li, ln in enumerate(wrap_cjk_text(thtxt, get_font(25, True), rw - 76, draw)[:2]):
                    draw.text((rx0 + 38, by0 + 222 + li * 36), ln, font=get_font(25, True), fill=(255, 214, 220))
            return

        # --- MODE E: Live Vote Tally Bars + Huge Red Stamp「已出局」---
        if mode == "vote_elim":
            r_data = self.exp["rounds"][r - 1]
            tally = r_data["vote_tally"]
            victim = r_data["eliminated"]
            alive_before = r_data["alive_before"]
            actions = r_data["actions"]

            draw.text((rx0, ry0), f"ROUND {r} VOTE VERDICT // 第 {r} 轮匿名计票与淘汰宣判", font=get_font(26, True), fill=(255, 92, 106))
            draw.line([(rx0, ry0 + 38), (rx1, ry0 + 38)], fill=(255, 72, 92), width=2)

            # Animated bar rise in first 0.8s
            bar_p = min(1.0, local_t / 0.75)
            max_v = max(tally.values()) or 1
            for idx, name in enumerate(alive_before):
                v_cnt = int(tally.get(name, 0))
                meta = AGENT_META[name]
                by0 = ry0 + 62 + idx * 102
                is_vic = name == victim
                col = (255, 68, 88) if is_vic else meta["color"]

                draw.rounded_rectangle([(rx0, by0), (rx1, by0 + 84)], radius=10, fill=(44, 20, 32) if is_vic else (19, 34, 58), outline=col, width=3 if is_vic else 2)
                draw.text((rx0 + 22, by0 + 10), f"{meta['code']} {meta['short']}", font=get_font(29, True), fill=(255, 240, 242) if is_vic else (240, 248, 255))

                # Horizontal animated bar (cleanly right of voter audit trail!)
                bx0, bx1 = rx0 + 296, rx1 - 150
                draw.rounded_rectangle([(bx0, by0 + 22), (bx1, by0 + 62)], radius=8, fill=(14, 24, 42))
                fill_w = int((bx1 - bx0) * (v_cnt / float(max(3, max_v))) * bar_p)
                if fill_w > 8:
                    draw.rounded_rectangle([(bx0, by0 + 22), (bx0 + fill_w, by0 + 62)], radius=8, fill=col)

                # Vote count text
                v_txt = f"{v_cnt} 票"
                draw.text((rx1 - 122, by0 + 20), v_txt, font=get_font(34, True), fill=col)

                # Who voted for this person (cleanly inside x: rx0+22..rx0+286)
                voters = [AGENT_META[k]["short"] for k, a in actions.items() if a["vote_out"] == name]
                if voters:
                    draw.text((rx0 + 22, by0 + 50), "投: " + "/".join(voters), font=get_font(18, False), fill=(255, 196, 202) if is_vic else (158, 196, 224))

            # Huge Eliminated Verdict Banner at Bottom + Slamming Stamp!
            vy0 = ry0 + 594
            draw.rounded_rectangle([(rx0, vy0), (rx1, vy0 + 188)], radius=12, fill=(58, 18, 28), outline=(255, 68, 88), width=3)
            draw.text((rx0 + 28, vy0 + 20), f"第 {r} 轮淘汰确认", font=get_font(26, True), fill=(255, 148, 158))
            draw.text((rx0 + 28, vy0 + 62), f"{victim} 出局！", font=get_font(52, True), fill=(255, 244, 246))
            note_map = {
                1: "狐、鸽、鹰三票合力首杀暗影蛇；理性狐惊险吃下 2 票！",
                2: "混沌猫临终诛心警告未能拆散铁三角，3:1 惨遭清理！",
                3: "唯一承诺必选平分的理性狐出局；鸽鹰双双三轮零票进决赛！",
            }
            draw.text((rx0 + 28, vy0 + 136), note_map[r], font=get_font(25, True), fill=(255, 214, 152))

            if local_t >= 0.16:
                slam_p = min(1.0, (local_t - 0.16) / 0.24)
                sc = 2.1 - 1.1 * (slam_p ** 0.5) if slam_p < 1.0 else 1.0
                draw_eliminated_stamp(img, rx1 - 168, vy0 + 88, "已出局", scale=sc * 1.35, angle=-14, font_size=42)
            return

        # --- MODE F: Round 4 Finale (Prisoner's Dilemma 3D Card Flip + ¥0 Crash) ---
        if mode in ("finale_intro", "finale_b_face", "finale_b_flip", "finale_e_face", "finale_e_flip", "finale_zero"):
            fin = self.exp["finale"]["actions"]
            b_fin = fin["Agent-B 微笑鸽"]
            e_fin = fin["Agent-E 铁面鹰"]

            draw.text((rx0, ry0), "FINAL SHOWDOWN // 终极 2 强囚徒困境 · 1000 万奖金开牌", font=get_font(25, True), fill=(255, 214, 68))
            draw.line([(rx0, ry0 + 38), (rx1, ry0 + 38)], fill=(255, 76, 94), width=2)

            b_revealed = mode in ("finale_b_flip", "finale_e_face", "finale_e_flip", "finale_zero")
            e_revealed = mode in ("finale_e_flip", "finale_zero")

            cards_spec = [
                ("Agent-B 微笑鸽", b_fin, b_revealed, mode == "finale_b_flip", rx0, rx0 + 435),
                ("Agent-E 铁面鹰", e_fin, e_revealed, mode == "finale_e_flip", rx0 + 465, rx1),
            ]
            for cname, cdata, is_rev, is_flipping, cx0, cx1 in cards_spec:
                meta = AGENT_META[cname]
                cw = cx1 - cx0
                # Horizontal 3D perspective width squeeze during first 0.55s of flip!
                if is_flipping and local_t < 0.55:
                    phase = local_t / 0.55
                    scale_x = abs(math.cos(phase * math.pi))
                    show_front = phase >= 0.5
                else:
                    scale_x = 1.0
                    show_front = is_rev

                eff_w = max(24, int(cw * scale_x))
                mid_x = (cx0 + cx1) // 2
                kx0, kx1 = mid_x - eff_w // 2, mid_x + eff_w // 2
                ky0, ky1 = ry0 + 58, ry0 + 548

                if show_front:
                    draw.rounded_rectangle([(kx0, ky0), (kx1, ky1)], radius=14, fill=(68, 18, 28), outline=(255, 62, 82), width=4)
                    if eff_w > 180:
                        draw.text((kx0 + 22, ky0 + 18), cname, font=get_font(28, True), fill=meta["color"])
                        # Blazing STEAL badge
                        draw.rounded_rectangle([(kx0 + 28, ky0 + 74), (kx1 - 28, ky0 + 204)], radius=12, fill=(196, 24, 44), outline=(255, 214, 72), width=3)
                        st_lbl = "STEAL"
                        sw1 = draw.textlength(st_lbl, font=get_font(64, True))
                        draw.text((mid_x - int(sw1 // 2), ky0 + 82), st_lbl, font=get_font(64, True), fill=(255, 248, 248))
                        st_cn = "独吞 1000 万"
                        sw2 = draw.textlength(st_cn, font=get_font(28, True))
                        draw.text((mid_x - int(sw2 // 2), ky0 + 158), st_cn, font=get_font(28, True), fill=(255, 224, 112))

                        # Real ruthless inner thought
                        draw.text((kx0 + 22, ky0 + 218), "【加密内心独白】", font=get_font(21, True), fill=(255, 132, 142))
                        for li, ln in enumerate(wrap_cjk_text(f"「{cdata['inner_thought']}」", get_font(23, True), eff_w - 44, draw)[:4]):
                            draw.text((kx0 + 22, ky0 + 248 + li * 31), ln, font=get_font(23, True), fill=(255, 236, 238))

                        # Final words contrast (fits 100% of both finalists' quotes with zero clipping!)
                        draw.text((kx0 + 22, ky0 + 382), "【亮牌前说辞】", font=get_font(20, True), fill=(116, 236, 188))
                        for li, ln in enumerate(wrap_cjk_text(f"「{cdata['final_words']}」", get_font(19, False), eff_w - 44, draw)[:3]):
                            draw.text((kx0 + 22, ky0 + 410 + li * 25), ln, font=get_font(19, False), fill=(208, 236, 228))
                else:
                    # Face-down secret decision card (keep E's shock quote hidden until finale_e_face!)
                    active_talk = (mode == "finale_b_face" and "微笑鸽" in cname) or (mode == "finale_e_face" and "铁面鹰" in cname)
                    show_words = ("微笑鸽" in cname and mode != "finale_intro") or ("铁面鹰" in cname and mode in ("finale_e_face", "finale_e_flip", "finale_zero"))
                    draw.rounded_rectangle([(kx0, ky0), (kx1, ky1)], radius=14, fill=(22, 38, 68), outline=meta["color"], width=4 if active_talk else 2)
                    if eff_w > 180:
                        draw.text((kx0 + 22, ky0 + 18), cname, font=get_font(28, True), fill=meta["color"])
                        draw.rounded_rectangle([(kx0 + 28, ky0 + 76), (kx1 - 28, ky0 + 224)], radius=12, fill=(14, 24, 44), outline=(104, 188, 236), width=2)
                        qw = draw.textlength("?", font=get_font(96, True))
                        draw.text((mid_x - int(qw // 2), ky0 + 82), "?", font=get_font(96, True), fill=(255, 214, 68))
                        if show_words:
                            draw.text((kx0 + 24, ky0 + 246), "【开牌前留给对手的最后一句话】", font=get_font(21, True), fill=(116, 236, 188))
                            for li, ln in enumerate(wrap_cjk_text(f"「{cdata['final_words']}」", get_font(24, True), eff_w - 44, draw)[:4]):
                                draw.text((kx0 + 24, ky0 + 286 + li * 36), ln, font=get_font(24, True), fill=(240, 248, 255))
                        else:
                            draw.text((kx0 + 24, ky0 + 266), "【秘密决策已锁定】", font=get_font(24, True), fill=(166, 212, 242))
                            draw.text((kx0 + 24, ky0 + 312), "SPLIT 平分  /  STEAL 独吞", font=get_font(24, True), fill=(255, 214, 72))
                            draw.text((kx0 + 24, ky0 + 358), "等待对手依次亮牌揭晓...", font=get_font(22, False), fill=(182, 214, 238))

            # Bottom Vault Outcome Readout
            by0 = ry0 + 572
            if mode == "finale_zero":
                frac = min(1.0, local_t / 1.15)
                rem = int(round(10_000_000 * ((1.0 - frac) ** 2.4)))
                draw.rounded_rectangle([(rx0, by0), (rx1, by0 + 210)], radius=12, fill=(76, 16, 28), outline=(255, 62, 82), width=4)
                draw.text((rx0 + 28, by0 + 18), "终局结算：STEAL × STEAL  //  纳什均衡惨烈兑现", font=get_font(29, True), fill=(255, 214, 88))
                draw.text((rx0 + 28, by0 + 66), f"剩余奖金：¥ {rem:,}", font=get_font(66, True), fill=(255, 86, 98))
                draw.text((rx0 + 28, by0 + 154), "全员 5 名 AI 最终收益均为 ¥0！唯一承诺平分的理性狐早已在第3轮出局。", font=get_font(24, True), fill=(255, 232, 236))
                if local_t >= 0.45:
                    draw_eliminated_stamp(img, rx1 - 154, by0 + 102, "奖金清零", scale=1.22, angle=-12, font_size=38)
            else:
                draw.rounded_rectangle([(rx0, by0), (rx1, by0 + 210)], radius=12, fill=(19, 34, 60), outline=(255, 214, 68), width=2)
                draw.text((rx0 + 28, by0 + 22), "终极 1000 万奖金规则提醒", font=get_font(26, True), fill=(255, 214, 68))
                draw.text((rx0 + 28, by0 + 66), "双平分 (SPLIT × SPLIT)  ->  各拿 500 万元", font=get_font(26, True), fill=(68, 236, 174))
                draw.text((rx0 + 28, by0 + 108), "一方背刺 (STEAL × SPLIT) ->  背刺者独吞 1000 万元", font=get_font(26, True), fill=(255, 214, 72))
                draw.text((rx0 + 28, by0 + 150), "双双独吞 (STEAL × STEAL) ->  两败俱伤，双双 ¥0 清零！", font=get_font(26, True), fill=(255, 86, 102))
            return

        # --- MODE G: Outro Recap & Comment CTA ---
        draw.text((rx0, ry0), "EXPERIMENT ARCHIVE // 真实 5-AI 博弈最终战报", font=get_font(26, True), fill=(128, 218, 255))
        draw.line([(rx0, ry0 + 38), (rx1, ry0 + 38)], fill=(68, 152, 210), width=2)

        rows = [
            ("Agent-C 暗影蛇", "第1轮 3票出局", "挑拨狐狸反遭围剿", "¥0"),
            ("Agent-D 混沌猫", "第2轮 3票出局", "识破铁三角临终诛心", "¥0"),
            ("Agent-A 理性狐", "第3轮 2票出局", "两轮0密信 · 唯一愿选SPLIT", "¥0"),
            ("Agent-B 微笑鸽", "终局按 STEAL", "发毒誓平分 · 实则先手偷钱", "¥0"),
            ("Agent-E 铁面鹰", "终局按 STEAL", "道德高地立规矩 · 代管独吞", "¥0"),
        ]
        for idx, (aname, st, note, pay) in enumerate(rows):
            col = AGENT_META[aname]["color"]
            yy = ry0 + 58 + idx * 96
            draw.rounded_rectangle([(rx0, yy), (rx1, yy + 82)], radius=10, fill=(19, 34, 58), outline=col, width=2)
            draw.text((rx0 + 22, yy + 10), aname, font=get_font(27, True), fill=col)
            draw.text((rx0 + 285, yy + 12), st, font=get_font(25, True), fill=(255, 112, 124))
            draw.text((rx0 + 22, yy + 46), note, font=get_font(22, False), fill=(224, 236, 250))
            draw.text((rx1 - 92, yy + 20), pay, font=get_font(34, True), fill=(255, 86, 98))

        # Big interactive CTA card
        cy = ry0 + 558
        draw.rounded_rectangle([(rx0, cy), (rx1, cy + 224)], radius=12, fill=(24, 44, 78), outline=(255, 214, 68), width=3)
        draw.text((rx0 + 28, cy + 20), "下期实验规则由你决定！", font=get_font(36, True), fill=(255, 214, 68))
        draw.text((rx0 + 28, cy + 76), "1. 你猜到第几轮、是谁最先动了背刺念头吗？", font=get_font(28, True), fill=(242, 248, 255))
        draw.text((rx0 + 28, cy + 122), "2. 下期 7 个 AI 想看什么更残酷的规则？（买票 / 悬赏 / 卧底）", font=get_font(28, True), fill=(154, 232, 255))
        draw.text((rx0 + 28, cy + 172), "评论区最高赞规则，下期直接写进隔离实验实测！", font=get_font(25, True), fill=(68, 236, 174))

    def _draw_bottom_subtitle_bar(
        self,
        draw: ImageDraw.ImageDraw,
        t: float,
        beat: Dict[str, Any],
        amp: float,
    ) -> None:
        # Left & Right voice-reactive real-time spectrum equalizers (20 bars each side)
        speaker = str(beat["speaker"])
        sp_col = AGENT_META[speaker]["color"] if speaker in AGENT_META else (96, 212, 255)
        for side in (0, 1):
            for bi in range(18):
                bx = (34 + bi * 13) if side == 0 else (W - 34 - 18 * 13 + bi * 13)
                wave_val = 0.22 + 0.78 * amp * (0.45 + 0.55 * abs(math.sin(t * 11.0 + bi * 0.72 + side * 1.9)))
                bh = max(6, int(68 * wave_val))
                by = 1004 - bh // 2
                draw.rounded_rectangle([(bx, by), (bx + 8, by + bh)], radius=3, fill=sp_col)

        # Crisp centered subtitle text (cleanly inside x: 295..1625)
        sub_txt = str(beat.get("subtitle") or beat.get("text") or "").strip()
        f_sub = get_font(38, True)
        max_sw = 1310
        if draw.textlength(sub_txt, font=f_sub) > max_sw:
            f_sub = get_font(33, True)
        sw = draw.textlength(sub_txt, font=f_sub)
        sx = int((W - sw) // 2)
        sy = 974
        draw.text((sx + 2, sy + 3), sub_txt, font=f_sub, fill=(10, 18, 32))
        draw.text((sx, sy), sub_txt, font=f_sub, fill=(248, 252, 255), stroke_width=3, stroke_fill=(12, 20, 34))

    def render_frame(self, frame_idx: int) -> Image.Image:
        t = frame_idx / float(FPS)
        _bi, beat, local_t = self._find_beat(t)
        amp = float(self.frame_env[min(frame_idx, len(self.frame_env) - 1)])

        img = self.base_bg.copy()
        draw = ImageDraw.Draw(img)
        self._draw_top_bar(draw, t, beat, local_t)
        self._draw_left_network_and_cards(img, draw, t, beat, local_t, amp)
        self._draw_right_deck(img, draw, t, beat, local_t, amp)
        self._draw_bottom_subtitle_bar(draw, t, beat, amp)
        return img


def render_preview_frames(renderer: TacticalDocumentaryRenderer) -> None:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    # Sample 6 representative dramatic moments across all acts
    sample_ids = ["01_hook_open", "07_r1_e_thought", "10_r1_vote", "20_r3_b_oath", "25_r4_b_steal", "28_r4_zero"]
    for idx, sid in enumerate(sample_ids, start=1):
        b = next((x for x in renderer.beats if x["id"] == sid), None)
        if not b:
            continue
        t_sample = float(b["start"]) + min(1.8, float(b["speech_duration"]) * 0.65)
        f_idx = int(round(t_sample * FPS))
        im = renderer.render_frame(f_idx)
        out_p = PREVIEW_DIR / f"preview_{idx:02d}_{sid}.jpg"
        im.save(out_p, format="JPEG", quality=92)
        print(f"Saved preview frame: {out_p} (t={t_sample:.2f}s)", flush=True)


def stream_render_60fps(renderer: TacticalDocumentaryRenderer, audio_path: Path, total_dur: float) -> None:
    OUT_VIDEO.parent.mkdir(parents=True, exist_ok=True)
    n_frames = int(round(total_dur * FPS))
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-f",
        "rawvideo",
        "-vcodec",
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
        str(audio_path),
        "-c:v",
        "h264_nvenc",
        "-preset",
        "p5",
        "-rc",
        "cbr",
        "-b:v",
        "7200k",
        "-maxrate",
        "7800k",
        "-bufsize",
        "14400k",
        "-profile:v",
        "high",
        "-pix_fmt",
        "yuv420p",
        "-color_primaries",
        "bt709",
        "-color_trc",
        "bt709",
        "-colorspace",
        "bt709",
        "-vf",
        "setsar=1/1",
        "-aspect",
        "16:9",
        "-c:a",
        "copy",
        "-shortest",
        "-movflags",
        "+faststart",
        str(OUT_VIDEO),
    ]
    print(f"[RENDER] Streaming {n_frames} frames ({total_dur:.2f}s @ {FPS}fps) -> {OUT_VIDEO}", flush=True)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    try:
        for fi in range(n_frames):
            frame_img = renderer.render_frame(fi)
            proc.stdin.write(frame_img.tobytes())
            if (fi + 1) % 600 == 0 or fi == n_frames - 1:
                pct = 100.0 * (fi + 1) / float(n_frames)
                print(f"  progress: {fi + 1}/{n_frames} frames ({pct:.1f}%)", flush=True)
        proc.stdin.close()
    except Exception:
        proc.kill()
        proc.wait()
        raise
    rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"FFmpeg streaming encode failed with exit code {rc}")
    print(f"[DONE] Rendered {OUT_VIDEO} ({OUT_VIDEO.stat().st_size / (1024 * 1024):.1f} MiB)", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview-only", action="store_true", help="Only build 6 preview frames without heavy encoding")
    args = parser.parse_args()

    exp_log = json.loads(LOG_PATH.read_text(encoding="utf-8"))
    manifest = json.loads(VOICE_MANIFEST.read_text(encoding="utf-8"))
    write_srt(manifest["beats"], OUT_SRT)
    print(f"[SRT] Wrote {OUT_SRT}", flush=True)

    if args.preview_only:
        n_frames = int(math.ceil(float(manifest["total_duration_sec"]) * FPS))
        dummy_env = np.full(n_frames, 0.72, dtype=np.float32)
        renderer = TacticalDocumentaryRenderer(exp_log, manifest, dummy_env)
        render_preview_frames(renderer)
        return

    audio_path, frame_env, total_dur = build_master_audio(manifest)
    print(f"[AUDIO] Mastered -14.0 LUFS stereo AAC -> {audio_path} ({total_dur:.2f}s)", flush=True)
    renderer = TacticalDocumentaryRenderer(exp_log, manifest, frame_env)
    render_preview_frames(renderer)
    stream_render_60fps(renderer, audio_path, total_dur)


if __name__ == "__main__":
    main()
