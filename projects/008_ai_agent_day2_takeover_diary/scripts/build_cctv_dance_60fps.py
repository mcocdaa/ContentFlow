#!/usr/bin/env python3
"""1080P @ 60FPS Pseudo-CCTV Server Room Dance Remaster for Project 008."""

from __future__ import annotations

import math
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw

SCRIPT_DIR = Path(__file__).resolve().parent
PROJ_DIR = SCRIPT_DIR.parent
ROOT_DIR = PROJ_DIR.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.cover_designer import CoverDesigner  # noqa: E402
from core.studio_renderer import get_sc_font, segment_character_rgba  # noqa: E402

ASSETS_DIR = PROJ_DIR / "assets"
CUTOUTS_DIR = PROJ_DIR / "output" / "cutouts"
DELIV_DIR = PROJ_DIR / "delivery"

RAW_DANCE_MP4 = PROJ_DIR / "output" / "dafeiyu_server_dance_raw_1080p.mp4"
ANCHOR_IMG = ASSETS_DIR / "dafeiyu_server_room_slender_16x9.jpg"
CUTOUT_PNG = CUTOUTS_DIR / "dafeiyu_server_slender_cutout.png"

OUT_MP4 = DELIV_DIR / "AI接管账号第5天全自动日更工作室_final.mp4"
OUT_SRT = DELIV_DIR / "AI接管账号第5天全自动日更工作室_subtitle.srt"
OUT_COVER = DELIV_DIR / "AI接管账号第5天全自动日更工作室_cover.jpg"
OUT_COVER_4X3 = DELIV_DIR / "AI接管账号第5天全自动日更工作室_cover_4x3.jpg"


def synthesize_140bpm_dance_bgm(out_wav: Path, duration_sec: float, sr: int = 48000) -> Path:
    """Synthesizes an upbeat 140 BPM Chiptune Future-Bass dance track aligned to duration_sec."""
    n_samples = int(round(duration_sec * sr))
    t = np.arange(n_samples, dtype=np.float32) / float(sr)
    bpm = 140.0
    beat_dur = 60.0 / bpm
    step_dur = beat_dur / 4.0  # 16th note

    beat_phase = np.mod(t, beat_dur) / beat_dur
    beat_time = np.mod(t, beat_dur)
    beat_idx = np.floor(t / beat_dur).astype(np.int32)
    step_idx = np.floor(t / step_dur).astype(np.int32)
    step_time = np.mod(t, step_dur)

    # 1. Punchy 4-on-the-floor kick
    kick_env = np.exp(-beat_time * 18.0) * (beat_time < 0.22)
    kick_freq = 50.0 + 130.0 * np.exp(-beat_time * 38.0)
    kick_phase = np.cumsum(2.0 * math.pi * kick_freq / sr).astype(np.float32)
    kick = 0.72 * np.tanh(1.5 * np.sin(kick_phase)) * kick_env

    # 2. Snappy clap/snare on beats 2 and 4
    is_clap = (beat_idx % 2) == 1
    rng = np.random.default_rng(20261116)
    noise = rng.normal(0.0, 1.0, n_samples).astype(np.float32)
    clap_env = np.where(is_clap & (beat_time < 0.16), np.exp(-beat_time * 26.0), 0.0)
    clap = 0.34 * noise * clap_env

    # 3. Crisp off-beat hi-hats on every 8th offbeat
    eighth_dur = beat_dur / 2.0
    eighth_idx = np.floor(t / eighth_dur).astype(np.int32)
    eighth_time = np.mod(t, eighth_dur)
    hat_env = np.where((eighth_idx % 2) == 1, np.exp(-eighth_time * 48.0), np.exp(-eighth_time * 80.0) * 0.4)
    # High-pass emphasize hats via first-order difference
    hp_noise = np.diff(noise, prepend=0.0) * 0.65
    hats = 0.22 * hp_noise * hat_env

    # 4. Bouncy anime chord progression: Am -> F -> C -> G (4 beats per chord)
    bass_roots = [110.0, 87.31, 130.81, 98.00]
    chord_freqs = [
        [220.0, 261.63, 329.63, 440.0],
        [174.61, 220.0, 261.63, 349.23],
        [261.63, 329.63, 392.0, 523.25],
        [196.0, 246.94, 293.66, 392.0],
    ]
    bar_idx = (beat_idx // 4) % 4
    root_f = np.array([bass_roots[b] for b in bar_idx], dtype=np.float32)
    duck = np.clip(0.32 + 0.68 * (beat_phase / 0.35), 0.32, 1.0)
    bass = 0.30 * duck * np.sin(2.0 * math.pi * root_f * t)

    # 5. Playful upbeat chiptune/lead melody over 16th-note arpeggio pattern
    melody_pattern = [2, 3, 1, 2, 0, 2, 3, 2, 3, 2, 1, 3, 2, 1, 0, 2]
    lead_f = np.zeros(n_samples, dtype=np.float32)
    for idx_b in range(4):
        mask_b = bar_idx == idx_b
        sel_notes = [chord_freqs[idx_b][melody_pattern[s % 16]] * 2.0 for s in range(16)]
        note_arr = np.array([sel_notes[s % 16] for s in step_idx], dtype=np.float32)
        lead_f = np.where(mask_b, note_arr, lead_f)

    lead_phase = np.cumsum(2.0 * math.pi * lead_f / sr).astype(np.float32)
    lead_wave = np.where(np.sin(lead_phase) >= 0.0, 0.55, -0.55) + 0.35 * np.sin(lead_phase)
    lead_env = np.exp(-step_time * 8.5)
    lead = 0.24 * duck * lead_wave * lead_env

    # Opening playful CCTV chirp (0.00..0.18s)
    chirp_mask = t < 0.18
    chirp = np.where(
        chirp_mask,
        0.18 * np.sin(2.0 * math.pi * np.where(t < 0.09, 1320.0, 1760.0) * t) * np.exp(-np.mod(t, 0.09) * 14.0),
        0.0,
    )

    mix_l = kick + clap + hats + bass + lead + chirp
    mix_r = kick + clap * 0.96 + np.roll(hats, 48) + bass + np.roll(lead, 120) * 0.96 + chirp

    # Smooth 0.12s fade-out to avoid click at exact end
    fade_n = min(int(0.12 * sr), n_samples // 6)
    fade_win = np.ones(n_samples, dtype=np.float32)
    fade_win[-fade_n:] = np.linspace(1.0, 0.0, fade_n, dtype=np.float32)
    mix_l = np.tanh(mix_l * 0.85) * fade_win * 0.88
    mix_r = np.tanh(mix_r * 0.85) * fade_win * 0.88

    stereo = np.stack([mix_l, mix_r], axis=-1)
    pcm = (np.clip(stereo, -0.98, 0.98) * 32767.0).astype(np.int16)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return out_wav


def make_cctv_overlay_bgra(text: str = "REC   CAM-04 | DeepSeek GPU机房 | 03:14:27") -> np.ndarray:
    """Renders a crisp semi-transparent dark CCTV status overlay for top-right corner."""
    font = get_sc_font(22, bold=True)
    probe = Image.new("RGBA", (900, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(probe)
    bbox = d.textbbox((0, 0), text, font=font)
    tw = int(bbox[2] - bbox[0])
    th = int(bbox[3] - bbox[1])
    w, h = tw + 68, th + 24
    badge = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    bd = ImageDraw.Draw(badge)
    bd.rounded_rectangle(
        [0, 0, w - 1, h - 1],
        radius=12,
        fill=(8, 14, 24, 188),
        outline=(0, 235, 255, 200),
        width=2,
    )
    bd.text((48 - bbox[0], 11 - bbox[1]), text, font=font, fill=(235, 248, 255, 245))
    arr = np.array(badge)
    return np.dstack([arr[..., 2], arr[..., 1], arr[..., 0], arr[..., 3]])


def write_subtitles_srt(srt_path: Path, dur: float) -> None:
    """Writes timed Simplified Chinese subtitles with safe spacing and clean CJK glyphs."""
    cues: List[Tuple[float, float, str]] = [
        (0.05, min(3.75, dur * 0.34), "以为「服务器繁忙」是在算题？后台监控：大肥鱼半夜偷跳舞！"),
        (min(3.80, dur * 0.345), min(7.70, dur * 0.68), "白天回答十万个为什么，凌晨三点在GPU机房原地起舞！"),
        (min(7.75, dur * 0.685), max(8.5, dur - 0.10), "只要主人睡着 算力机房就是我的个人宅舞舞台！"),
    ]

    def fmt_ts(sec: float) -> str:
        ms = int(round(max(0.0, sec) * 1000.0))
        hh, rem = divmod(ms, 3600000)
        mm, rem = divmod(rem, 60000)
        ss, mmm = divmod(rem, 1000)
        return f"{hh:02d}:{mm:02d}:{ss:02d},{mmm:03d}"

    lines = []
    for i, (s, e, txt) in enumerate(cues, start=1):
        lines.extend([str(i), f"{fmt_ts(s)} --> {fmt_ts(e)}", txt, ""])
    srt_path.write_text("\n".join(lines), encoding="utf-8")


def optical_flow_midpoint(f0: np.ndarray, f1: np.ndarray, dis: cv2.DISOpticalFlow) -> np.ndarray:
    """Computes ghost-free 2x midpoint frame via symmetric DIS optical flow."""
    h, w = f0.shape[:2]
    g0 = cv2.cvtColor(f0, cv2.COLOR_BGR2GRAY)
    g1 = cv2.cvtColor(f1, cv2.COLOR_BGR2GRAY)
    s0 = cv2.resize(g0, (w // 2, h // 2))
    s1 = cv2.resize(g1, (w // 2, h // 2))
    flow_f = cv2.resize(dis.calc(s0, s1, None), (w, h), interpolation=cv2.INTER_LINEAR) * 2.0
    flow_b = cv2.resize(dis.calc(s1, s0, None), (w, h), interpolation=cv2.INTER_LINEAR) * 2.0

    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    w0 = cv2.remap(f0, gx - 0.5 * flow_f[..., 0], gy - 0.5 * flow_f[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    w1 = cv2.remap(f1, gx - 0.5 * flow_b[..., 0], gy - 0.5 * flow_b[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return cv2.addWeighted(w0, 0.5, w1, 0.5, 0)


def apply_cctv_hud(frame: np.ndarray, overlay_bgra: np.ndarray, frame_idx: int) -> np.ndarray:
    """Composites crisp subtle CCTV viewfinder corners + pulsing REC dot."""
    out = frame.copy()
    oh, ow = overlay_bgra.shape[:2]
    ox, oy = 1894 - ow, 20
    alpha = overlay_bgra[..., 3:4].astype(np.float32) / 255.0
    roi = out[oy : oy + oh, ox : ox + ow].astype(np.float32)
    out[oy : oy + oh, ox : ox + ow] = (roi * (1.0 - alpha) + overlay_bgra[..., :3].astype(np.float32) * alpha).astype(
        np.uint8
    )

    if (frame_idx // 20) % 2 == 0:
        cv2.circle(out, (ox + 26, oy + oh // 2), 9, (48, 56, 255), -1, cv2.LINE_AA)
    else:
        cv2.circle(out, (ox + 26, oy + oh // 2), 9, (35, 35, 110), 2, cv2.LINE_AA)

    col = (240, 225, 0)  # BGR cyan
    m, ln = 24, 48
    for (x0, y0, dx, dy) in [(m, m, 1, 1), (1920 - m, m, -1, 1), (m, 1080 - m, 1, -1), (1920 - m, 1080 - m, -1, -1)]:
        cv2.line(out, (x0, y0), (x0 + dx * ln, y0), col, 2, cv2.LINE_AA)
        cv2.line(out, (x0, y0), (x0, y0 + dy * ln), col, 2, cv2.LINE_AA)
    return out


def main() -> None:
    if not RAW_DANCE_MP4.exists():
        raise FileNotFoundError(f"Missing raw Kling dance video: {RAW_DANCE_MP4}")

    segment_character_rgba(ANCHOR_IMG, CUTOUT_PNG)
    CoverDesigner().design_project_cover(PROJ_DIR, output_path=OUT_COVER)

    cap = cv2.VideoCapture(str(RAW_DANCE_MP4))
    raw_frames: List[np.ndarray] = []
    while True:
        ok, frm = cap.read()
        if not ok:
            break
        h, w = frm.shape[:2]
        if w != 1920 or h != 1080:
            y0 = max(0, (h - 1080) // 2)
            x0 = max(0, (w - 1920) // 2)
            frm = frm[y0 : y0 + 1080, x0 : x0 + 1920]
            if frm.shape[1] != 1920 or frm.shape[0] != 1080:
                frm = cv2.resize(frm, (1920, 1080), interpolation=cv2.INTER_LANCZOS4)
        raw_frames.append(frm)
    cap.release()

    if len(raw_frames) < 60:
        raise RuntimeError(f"Expected >= 60 frames in {RAW_DANCE_MP4}, got {len(raw_frames)}")

    total_60_frames = len(raw_frames) * 2 - 1
    dur_sec = total_60_frames / 60.0
    write_subtitles_srt(OUT_SRT, dur_sec)

    with tempfile.TemporaryDirectory() as tmpdir:
        bgm_wav = Path(tmpdir) / "dance_bgm_140bpm.wav"
        synthesize_140bpm_dance_bgm(bgm_wav, dur_sec)

        overlay_bgra = make_cctv_overlay_bgra()
        dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
        sub_style = (
            "Fontname=Noto Sans CJK SC,"
            "FontSize=23,"
            "PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,"
            "BackColour=&H88000000,"
            "BorderStyle=1,"
            "Outline=2.5,"
            "Shadow=1.0,"
            "MarginV=40,"
            "Alignment=2"
        )
        vf = f"subtitles={OUT_SRT.resolve().as_posix()}:force_style='{sub_style}',setsar=1,setdar=16/9,fps=60,format=yuv420p"
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
            "1920x1080",
            "-r",
            "60",
            "-i",
            "-",
            "-i",
            str(bgm_wav),
            "-vf",
            vf,
            "-af",
            "loudnorm=I=-14:LRA=7:TP=-1.5",
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
            str(OUT_MP4),
        ]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        assert proc.stdin is not None
        out_idx = 0
        for i in range(len(raw_frames)):
            f_even = apply_cctv_hud(raw_frames[i], overlay_bgra, out_idx)
            proc.stdin.write(f_even.tobytes())
            out_idx += 1
            if i + 1 < len(raw_frames):
                mid = optical_flow_midpoint(raw_frames[i], raw_frames[i + 1], dis)
                f_odd = apply_cctv_hud(mid, overlay_bgra, out_idx)
                proc.stdin.write(f_odd.tobytes())
                out_idx += 1
        proc.stdin.close()
        proc.stdin = None
        _, err = proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg encode failed: {err.decode(errors='ignore')[-500:]}")

    print(f"[+] Built 008 60FPS CCTV Dance ({out_idx} frames, {dur_sec:.2f}s) -> {OUT_MP4}")


if __name__ == "__main__":
    main()
