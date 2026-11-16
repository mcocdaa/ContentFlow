#!/usr/bin/env python3
"""1080P @ 60FPS Two-Act Office Rage -> Street Dance Pipeline for Project 011 (Yowane Haku)."""

from __future__ import annotations

import math
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

import cv2
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
PROJ_DIR = SCRIPT_DIR.parent
ROOT_DIR = PROJ_DIR.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.cover_designer import CoverDesigner  # noqa: E402
from core.local_tts import LocalNeuralTTS  # noqa: E402
from core.studio_renderer import segment_character_rgba  # noqa: E402

ASSETS_DIR = PROJ_DIR / "assets"
CUTOUTS_DIR = PROJ_DIR / "output" / "cutouts"
DELIV_DIR = PROJ_DIR / "delivery"

ACT1_RAW_MP4 = PROJ_DIR / "output" / "act1_office_rage_5s_1080p.mp4"
ACT2_RAW_MP4 = PROJ_DIR / "output" / "act2_street_dance_10s_1080p.mp4"
HERO_ANCHOR_IMG = ASSETS_DIR / "yowane_act1_office_rage_16x9.jpg"
CUTOUT_PNG = CUTOUTS_DIR / "yowane_office_rage_cutout.png"

OUT_MP4 = DELIV_DIR / "社畜弱音回答我下班街头潮舞_final.mp4"
OUT_SRT = DELIV_DIR / "社畜弱音回答我下班街头潮舞_subtitle.srt"
OUT_COVER = DELIV_DIR / "社畜弱音回答我下班街头潮舞_cover.jpg"


def load_cropped_1080p_frames(video_path: Path) -> Tuple[List[np.ndarray], float]:
    """Loads frames from a raw video and center-crops (never stretches) to 1920x1080."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Unable to open video: {video_path}")
    src_fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    if src_fps <= 1.0 or math.isnan(src_fps):
        src_fps = 30.0

    frames: List[np.ndarray] = []
    while True:
        ok, frm = cap.read()
        if not ok:
            break
        h, w = frm.shape[:2]
        if w != 1920 or h != 1080:
            if w >= 1920 and h >= 1080:
                y0 = max(0, (h - 1080) // 2)
                x0 = max(0, (w - 1920) // 2)
                frm = frm[y0 : y0 + 1080, x0 : x0 + 1920]
            else:
                scale = max(1920.0 / w, 1080.0 / h)
                rw, rh = int(round(w * scale)), int(round(h * scale))
                resized = cv2.resize(frm, (rw, rh), interpolation=cv2.INTER_LANCZOS4)
                y0 = max(0, (rh - 1080) // 2)
                x0 = max(0, (rw - 1920) // 2)
                frm = resized[y0 : y0 + 1080, x0 : x0 + 1920]
        frames.append(frm)
    cap.release()
    return frames, src_fps


def iter_interpolated_60fps(
    raw_frames: List[np.ndarray], src_fps: float, dis: cv2.DISOpticalFlow
) -> Iterator[np.ndarray]:
    """Resamples raw_frames at src_fps -> 60.0fps via cached symmetric DIS optical flow."""
    n_in = len(raw_frames)
    if n_in == 0:
        return
    if n_in == 1:
        yield raw_frames[0]
        return

    out_count = int(round((n_in - 1) * (60.0 / src_fps))) + 1
    h, w = raw_frames[0].shape[:2]
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))

    cached_idx = -1
    cached_flow_f: Optional[np.ndarray] = None
    cached_flow_b: Optional[np.ndarray] = None

    for k in range(out_count):
        pos = k * (src_fps / 60.0)
        i0 = min(int(math.floor(pos)), n_in - 1)
        alpha = pos - i0
        if alpha < 1e-3 or i0 >= n_in - 1:
            yield raw_frames[i0]
            continue

        if cached_idx != i0:
            f0 = raw_frames[i0]
            f1 = raw_frames[i0 + 1]
            s0 = cv2.resize(cv2.cvtColor(f0, cv2.COLOR_BGR2GRAY), (w // 2, h // 2))
            s1 = cv2.resize(cv2.cvtColor(f1, cv2.COLOR_BGR2GRAY), (w // 2, h // 2))
            cached_flow_f = cv2.resize(dis.calc(s0, s1, None), (w, h), interpolation=cv2.INTER_LINEAR) * 2.0
            cached_flow_b = cv2.resize(dis.calc(s1, s0, None), (w, h), interpolation=cv2.INTER_LINEAR) * 2.0
            cached_idx = i0

        assert cached_flow_f is not None and cached_flow_b is not None
        f0 = raw_frames[i0]
        f1 = raw_frames[i0 + 1]
        w0 = cv2.remap(
            f0,
            gx - alpha * cached_flow_f[..., 0],
            gy - alpha * cached_flow_f[..., 1],
            cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
        w1 = cv2.remap(
            f1,
            gx - (1.0 - alpha) * cached_flow_b[..., 0],
            gy - (1.0 - alpha) * cached_flow_b[..., 1],
            cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
        yield cv2.addWeighted(w0, 1.0 - alpha, w1, alpha, 0)


def apply_neon_clock_flash(frame: np.ndarray, alpha: float, badge_label: str = "18:30 OFF WORK!") -> np.ndarray:
    """Blends a crisp cyan-magenta neon flash + brief 18:30 clock stamp across the off-work transition."""
    if alpha <= 1e-3:
        return frame
    flash = np.empty_like(frame)
    flash[:, :960] = (255, 230, 80)  # BGR neon cyan
    flash[:, 960:] = (230, 90, 255)  # BGR neon magenta
    blended = cv2.addWeighted(frame, 1.0 - alpha, flash, alpha, 0)
    if alpha >= 0.25:
        cv2.putText(
            blended,
            badge_label,
            (620, 560),
            cv2.FONT_HERSHEY_SIMPLEX,
            2.2,
            (255, 255, 255),
            6,
            cv2.LINE_AA,
        )
    return blended


def resample_audio_to_48k(wav: np.ndarray, src_sr: int = 24000, dst_sr: int = 48000) -> np.ndarray:
    """Linearly resamples a mono waveform from src_sr to dst_sr."""
    if wav.size == 0 or src_sr == dst_sr:
        return wav.astype(np.float32)
    dst_len = max(1, int(round(wav.size * (dst_sr / float(src_sr)))))
    x_old = np.linspace(0.0, 1.0, wav.size, dtype=np.float64)
    x_new = np.linspace(0.0, 1.0, dst_len, dtype=np.float64)
    return np.interp(x_new, x_old, wav).astype(np.float32)


def time_fit_waveform(wav: np.ndarray, max_samples: int) -> np.ndarray:
    """Compresses a vocal waveform linearly if it exceeds max_samples."""
    if wav.size <= max_samples or max_samples <= 16:
        return wav[:max_samples]
    x_old = np.linspace(0.0, 1.0, wav.size, dtype=np.float64)
    x_new = np.linspace(0.0, 1.0, max_samples, dtype=np.float64)
    return np.interp(x_new, x_old, wav).astype(np.float32)


def synthesize_office_to_phonk_soundtrack(
    out_wav: Path,
    total_dur: float,
    t_trans: float,
    vocal_act1: np.ndarray,
    vocal_act2: np.ndarray,
    sr: int = 48000,
) -> Path:
    """Synthesizes tense office desk-slam + 18:30 chime -> 130 BPM Drift-Phonk soundtrack."""
    n_samples = int(round(total_dur * sr))
    t = np.arange(n_samples, dtype=np.float32) / float(sr)
    rng = np.random.default_rng(20261118)
    white = rng.normal(0.0, 1.0, n_samples).astype(np.float32)

    # --- Act 1: Desk slam sub-impact + rapid mechanical keyboard ticks + 18:30 Ding-Dong! ---
    is_act1 = t < t_trans

    # Heavy desk-slam boom at 0.18s & dramatic tense hit at 2.35s
    slam = np.zeros(n_samples, dtype=np.float32)
    for t_hit in (0.18, 2.35):
        dt_h = np.maximum(0.0, t - t_hit)
        h_mask = (t >= t_hit) & (t < t_hit + 0.55)
        f_sweep = 45.0 + 160.0 * np.exp(-dt_h * 26.0)
        slam += np.where(
            h_mask,
            0.65 * np.tanh(1.8 * np.sin(2.0 * math.pi * f_sweep * dt_h)) * np.exp(-dt_h * 7.5),
            0.0,
        )

    # Mechanical keyboard rapid ticks during 0.45s .. (t_trans - 0.50s)
    key_step = 0.095
    key_time = np.mod(t, key_step)
    key_active = (t >= 0.45) & (t < t_trans - 0.50) & (key_time < 0.025)
    hp_click = np.diff(white, prepend=0.0) * 0.65
    keys = np.where(key_active, 0.20 * hp_click * np.exp(-key_time * 95.0), 0.0)

    # Tense low pulse pad (F#m tension)
    tense_pulse = 0.15 * np.sin(2.0 * math.pi * 92.50 * t) * (0.55 + 0.45 * np.sin(2.0 * math.pi * 3.5 * t))

    # Crisp two-tone "18:30 Ding-Dong!" chime right before transition
    c1_t0 = max(0.0, t_trans - 0.36)
    c2_t0 = max(0.0, t_trans - 0.18)
    ding = np.where(
        (t >= c1_t0) & (t < c2_t0),
        0.38 * np.sin(2.0 * math.pi * 880.0 * (t - c1_t0)) * np.exp(-(t - c1_t0) * 11.0),
        0.0,
    )
    dong = np.where(
        (t >= c2_t0) & (t < t_trans + 0.35),
        0.42 * np.sin(2.0 * math.pi * 659.25 * (t - c2_t0)) * np.exp(-(t - c2_t0) * 6.5),
        0.0,
    )

    act1_bed_l = np.where(is_act1, slam + keys + tense_pulse, 0.0) + ding + dong
    act1_bed_r = np.where(is_act1, slam + np.roll(keys, 36) + tense_pulse, 0.0) + ding + dong

    # --- Act 2: 130 BPM Drift-Phonk Street Groove (t_trans .. total_dur) ---
    is_act2 = t >= t_trans
    t2 = np.maximum(0.0, t - t_trans)
    bpm = 130.0
    beat_dur = 60.0 / bpm
    step_dur = beat_dur / 4.0

    beat_phase = np.mod(t2, beat_dur) / beat_dur
    beat_time = np.mod(t2, beat_dur)
    beat_idx = np.floor(t2 / beat_dur).astype(np.int32)
    step_idx = np.floor(t2 / step_dur).astype(np.int32)
    step_time = np.mod(t2, step_dur)

    # Hard Phonk Kick + Saturated 808 Bassline (F# -> D -> E -> C#)
    kick_env = np.exp(-beat_time * 19.0) * (beat_time < 0.22)
    kick_freq = 46.0 + 150.0 * np.exp(-beat_time * 42.0)
    kick_phase = np.cumsum(2.0 * math.pi * np.where(is_act2, kick_freq, 0.0) / sr).astype(np.float32)
    kick = 0.80 * np.tanh(1.8 * np.sin(kick_phase)) * kick_env

    bass_roots = [92.50, 73.42, 82.41, 69.30]  # F#2, D2, E2, C#2
    bar_idx = (beat_idx // 4) % 4
    root_f = np.array([bass_roots[b] for b in bar_idx], dtype=np.float32)
    duck_808 = np.clip(0.24 + 0.76 * (beat_phase / 0.30), 0.24, 1.0)
    sub_808 = np.tanh(2.1 * np.sin(2.0 * math.pi * root_f * t2) + 0.45 * np.sin(2.0 * math.pi * (root_f * 2.0) * t2))
    bass_808 = 0.36 * duck_808 * sub_808

    # Snappy Phonk Snare on beats 2 and 4 + fast 16th hi-hats
    is_snare = (beat_idx % 2) == 1
    snare_env = np.where(is_snare & (beat_time < 0.15), np.exp(-beat_time * 24.0), 0.0)
    snare_body = np.sin(2.0 * math.pi * 195.0 * beat_time) * np.exp(-beat_time * 28.0)
    snare = 0.38 * (0.75 * white + 0.45 * snare_body) * snare_env

    hp_hat = np.diff(white, prepend=0.0) * 0.72
    hat_env = np.where((step_idx % 2) == 0, np.exp(-step_time * 45.0), np.exp(-step_time * 75.0) * 0.45)
    hats = 0.22 * hp_hat * hat_env

    # Iconic Metallic Drift-Phonk Cowbell Riff (F#m pentatonic)
    cowbell_bars = [
        [739.99, 0.0, 880.00, 0.0, 987.77, 880.00, 739.99, 0.0, 659.25, 0.0, 739.99, 880.00, 987.77, 0.0, 1108.73, 0.0],
        [587.33, 0.0, 739.99, 0.0, 880.00, 739.99, 587.33, 0.0, 554.37, 0.0, 587.33, 739.99, 880.00, 0.0, 739.99, 0.0],
        [659.25, 0.0, 783.99, 0.0, 987.77, 783.99, 659.25, 0.0, 587.33, 0.0, 659.25, 783.99, 987.77, 0.0, 880.00, 0.0],
        [554.37, 0.0, 659.25, 0.0, 830.61, 659.25, 554.37, 0.0, 493.88, 0.0, 554.37, 659.25, 739.99, 0.0, 880.00, 0.0],
    ]
    cb_f = np.zeros(n_samples, dtype=np.float32)
    for b_i in range(4):
        notes_arr = np.array([cowbell_bars[b_i][s % 16] for s in step_idx], dtype=np.float32)
        cb_f = np.where(bar_idx == b_i, notes_arr, cb_f)

    cb_active = cb_f > 1.0
    cb_phase1 = np.cumsum(2.0 * math.pi * np.where(is_act2 & cb_active, cb_f, 0.0) / sr).astype(np.float32)
    cb_phase2 = np.cumsum(2.0 * math.pi * np.where(is_act2 & cb_active, cb_f * 1.48, 0.0) / sr).astype(np.float32)
    cowbell_tone = np.tanh(1.6 * (0.65 * np.sign(np.sin(cb_phase1)) + 0.45 * np.sign(np.sin(cb_phase2))))
    cowbell = np.where(cb_active, 0.24 * cowbell_tone * np.exp(-step_time * 14.0), 0.0)

    act2_bed_l = np.where(is_act2, kick + bass_808 + snare + hats + cowbell, 0.0)
    act2_bed_r = np.where(is_act2, kick + bass_808 + snare * 0.96 + np.roll(hats, 40) + np.roll(cowbell, 88) * 0.96, 0.0)

    bed_l = act1_bed_l + act2_bed_l
    bed_r = act1_bed_r + act2_bed_r

    # --- Place Parody Vocals & Sidechain-Duck the Bed ---
    vocal_track = np.zeros(n_samples, dtype=np.float32)
    speech_env = np.zeros(n_samples, dtype=np.float32)

    v1_start = int(0.10 * sr)
    v1_max = max(16, int((t_trans - 0.18) * sr) - v1_start)
    v1 = time_fit_waveform(resample_audio_to_48k(vocal_act1, 24000, sr), v1_max)
    vocal_track[v1_start : v1_start + v1.size] += v1 * 1.15
    speech_env[v1_start : v1_start + v1.size] = 1.0

    v2_start = int((t_trans + 0.08) * sr)
    v2_max = max(16, min(int(3.6 * sr), n_samples - v2_start - int(0.25 * sr)))
    v2 = time_fit_waveform(resample_audio_to_48k(vocal_act2, 24000, sr), v2_max)
    vocal_track[v2_start : v2_start + v2.size] += v2 * 1.12
    speech_env[v2_start : v2_start + v2.size] = 1.0

    duck_gain = np.where(speech_env > 0.5, 0.42, 1.0).astype(np.float32)
    duck_gain = np.convolve(duck_gain, np.ones(1200, dtype=np.float32) / 1200.0, mode="same")

    mix_l = bed_l * duck_gain + vocal_track
    mix_r = bed_r * duck_gain + vocal_track

    fade_n = min(int(0.12 * sr), n_samples // 8)
    fade_win = np.ones(n_samples, dtype=np.float32)
    fade_win[-fade_n:] = np.linspace(1.0, 0.0, fade_n, dtype=np.float32)

    mix_l = np.tanh(mix_l * 0.85) * fade_win * 0.90
    mix_r = np.tanh(mix_r * 0.85) * fade_win * 0.90

    stereo = np.stack([mix_l, mix_r], axis=-1)
    pcm = (np.clip(stereo, -0.98, 0.98) * 32767.0).astype(np.int16)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return out_wav


def write_subtitles_srt(srt_path: Path, t_trans: float, total_dur: float) -> None:
    """Writes clean Simplified Chinese meme captions aligned to both acts."""
    half1 = t_trans * 0.48
    rem2 = max(3.0, total_dur - t_trans)
    cues: List[Tuple[float, float, str]] = [
        (0.08, half1, "需求改了八遍还不给加内存？！"),
        (half1 + 0.05, max(half1 + 0.8, t_trans - 0.14), "Look in my eyes！回答我！到底为什么？！"),
        (t_trans + 0.05, t_trans + min(3.7, rem2 * 0.44), "叮咚六点半！社畜准点下班 直接开摇！"),
        (t_trans + min(3.75, rem2 * 0.45), max(t_trans + 4.4, total_dur - 0.12), "18:30全速狂飙 霓虹斑马线1080P街头热舞！"),
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
    srt_path.parent.mkdir(parents=True, exist_ok=True)
    srt_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    for p in (ACT1_RAW_MP4, ACT2_RAW_MP4, HERO_ANCHOR_IMG):
        if not p.exists():
            raise FileNotFoundError(f"Missing required asset: {p}")

    # 1. Segment intense office rage hero cutout and render 16:9 + 4:3 viral cover
    segment_character_rgba(HERO_ANCHOR_IMG, CUTOUT_PNG, crop_roi=(0.18, 0.0, 0.82, 0.86))
    CoverDesigner().design_project_cover(PROJ_DIR, output_path=OUT_COVER)

    # 2. Load raw frames & inspect exact native FPS
    act1_frames, fps1 = load_cropped_1080p_frames(ACT1_RAW_MP4)
    act2_frames, fps2 = load_cropped_1080p_frames(ACT2_RAW_MP4)

    n1_out = int(round((len(act1_frames) - 1) * (60.0 / fps1))) + 1
    n2_out = int(round((len(act2_frames) - 1) * (60.0 / fps2))) + 1
    total_60_frames = n1_out + n2_out
    t_trans = n1_out / 60.0
    total_dur = total_60_frames / 60.0

    write_subtitles_srt(OUT_SRT, t_trans=t_trans, total_dur=total_dur)

    # 3. Synthesize parody vocals sequentially and immediately free Kokoro memory
    tts = LocalNeuralTTS(device="cpu")
    try:
        v1 = tts.synthesize_text(
            "需求改了八遍还不给加内存？看着我的眼睛！回答我！到底为什么？！",
            voice="zf_001",
            speed=1.18,
        )
        v2 = tts.synthesize_text(
            "叮咚六点半！社畜准点下班，街头潮舞直接开摇！",
            voice="zf_001",
            speed=1.14,
        )
    finally:
        tts.close()

    with tempfile.TemporaryDirectory() as tmpdir:
        master_wav = Path(tmpdir) / "yowane_phonk_master.wav"
        synthesize_office_to_phonk_soundtrack(
            master_wav, total_dur=total_dur, t_trans=t_trans, vocal_act1=v1, vocal_act2=v2
        )

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
            str(master_wav),
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
        dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)

        out_idx = 0
        for local_i, frm in enumerate(iter_interpolated_60fps(act1_frames, fps1, dis)):
            dist_to_cut = (n1_out - 1) - local_i
            if dist_to_cut < 4:
                flash_a = 0.62 * (1.0 - dist_to_cut / 4.0)
                frm = apply_neon_clock_flash(frm, flash_a)
            proc.stdin.write(frm.tobytes())
            out_idx += 1

        for local_i, frm in enumerate(iter_interpolated_60fps(act2_frames, fps2, dis)):
            if local_i < 5:
                flash_a = 0.62 * (1.0 - local_i / 5.0)
                frm = apply_neon_clock_flash(frm, flash_a)
            proc.stdin.write(frm.tobytes())
            out_idx += 1

        proc.stdin.close()
        proc.stdin = None
        _, err = proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg encode failed: {err.decode(errors='ignore')[-500:]}")

    print(
        f"[+] Built 011 60FPS Office-to-Street Dance ({out_idx} frames, {total_dur:.2f}s, cut@{t_trans:.2f}s) -> {OUT_MP4}"
    )


if __name__ == "__main__":
    main()
