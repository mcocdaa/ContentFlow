#!/usr/bin/env python3
"""1080P @ 60FPS Two-Act Parody Dance Pipeline for Project 010 (Sifeng Rain -> Xingqiyao Rave)."""

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

ACT1_RAW_MP4 = PROJ_DIR / "output" / "act1_rain_5s_1080p.mp4"
ACT2_RAW_MP4 = PROJ_DIR / "output" / "act2_rave_10s_1080p.mp4"
HERO_ANCHOR_IMG = ASSETS_DIR / "dafeiyu_act1_sifeng_rain_16x9.jpg"
CUTOUT_PNG = CUTOUTS_DIR / "dafeiyu_sifeng_hero_cutout.png"

OUT_MP4 = DELIV_DIR / "大肥鱼司凤战损版雨爱邦吧蹦迪_final.mp4"
OUT_SRT = DELIV_DIR / "大肥鱼司凤战损版雨爱邦吧蹦迪_subtitle.srt"
OUT_COVER = DELIV_DIR / "大肥鱼司凤战损版雨爱邦吧蹦迪_cover.jpg"


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


def apply_lightning_flash(frame: np.ndarray, alpha: float) -> np.ndarray:
    """Blends a crisp cyan-white lightning flash over a BGR frame."""
    if alpha <= 1e-3:
        return frame
    flash = np.empty_like(frame)
    flash[:, :] = (255, 245, 200)  # BGR cool cyan-white
    return cv2.addWeighted(frame, 1.0 - alpha, flash, alpha, 0)


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


def synthesize_two_act_soundtrack(
    out_wav: Path,
    total_dur: float,
    t_trans: float,
    vocal_act1: np.ndarray,
    vocal_act2: np.ndarray,
    sr: int = 48000,
) -> Path:
    """Synthesizes two-act storm-to-138BPM-electro soundtrack mixed with parody vocals."""
    n_samples = int(round(total_dur * sr))
    t = np.arange(n_samples, dtype=np.float32) / float(sr)
    rng = np.random.default_rng(202611160)

    # --- Act 1: Rainstorm + Thunder + Melancholic Pentatonic Pad (0 .. t_trans) ---
    is_act1 = t < t_trans
    white = rng.normal(0.0, 1.0, n_samples).astype(np.float32)
    # Softly smoothed pink-ish rain hiss
    kernel = np.ones(12, dtype=np.float32) / 12.0
    rain_l = np.convolve(white, kernel, mode="same") * 0.22
    rain_r = np.convolve(np.roll(white, 211), kernel, mode="same") * 0.22

    # Two dramatic thunder rumbles at 0.25s and 2.65s
    thunder = np.zeros(n_samples, dtype=np.float32)
    for t_th in (0.25, 2.65):
        dt_th = np.maximum(0.0, t - t_th)
        th_mask = (t >= t_th) & (t < t_th + 1.8)
        sub_rumble = np.sin(2.0 * math.pi * 48.0 * dt_th) + 0.5 * np.sin(2.0 * math.pi * 72.0 * dt_th)
        th_noise = np.convolve(white, np.ones(64, dtype=np.float32) / 64.0, mode="same") * 1.8
        thunder += np.where(th_mask, (0.35 * sub_rumble + th_noise) * np.exp(-dt_th * 2.4), 0.0)

    # Melancholic ballad pad: Am -> F -> Dm -> E (every ~1.25s)
    pad_roots = [220.0, 174.61, 146.83, 164.81]
    pad_idx = np.clip((t / max(0.5, t_trans / 4.0)).astype(np.int32), 0, 3)
    pad_f = np.array([pad_roots[idx] for idx in pad_idx], dtype=np.float32)
    pad_wave = (
        0.16 * np.sin(2.0 * math.pi * pad_f * t)
        + 0.08 * np.sin(2.0 * math.pi * (pad_f * 1.5) * t)
        + 0.05 * np.sin(2.0 * math.pi * (pad_f * 2.0) * t)
    )

    # Vinyl scratch + lightning crack right before drop (t_trans - 0.16 .. t_trans)
    sc_mask = (t >= t_trans - 0.16) & (t < t_trans)
    dt_sc = np.maximum(0.0, t - (t_trans - 0.16))
    scratch_f = 1900.0 - 1650.0 * (dt_sc / 0.16)
    scratch = np.where(sc_mask, 0.35 * np.sin(np.cumsum(2.0 * math.pi * scratch_f / sr)), 0.0)

    act1_bed_l = np.where(is_act1, rain_l + thunder + pad_wave + scratch, 0.0)
    act1_bed_r = np.where(is_act1, rain_r + thunder * 0.92 + pad_wave + scratch, 0.0)

    # --- Act 2: 138 BPM Electro-Bounce "Bomba-Bomba" Rave Drop (t_trans .. total_dur) ---
    is_act2 = t >= t_trans
    t2 = np.maximum(0.0, t - t_trans)
    bpm = 138.0
    beat_dur = 60.0 / bpm
    step_dur = beat_dur / 4.0

    beat_phase = np.mod(t2, beat_dur) / beat_dur
    beat_time = np.mod(t2, beat_dur)
    beat_idx = np.floor(t2 / beat_dur).astype(np.int32)
    step_idx = np.floor(t2 / step_dur).astype(np.int32)
    step_time = np.mod(t2, step_dur)

    # Punchy EDM kick + initial explosion boom
    kick_env = np.exp(-beat_time * 18.0) * (beat_time < 0.23)
    kick_freq = 48.0 + 145.0 * np.exp(-beat_time * 40.0)
    kick_phase = np.cumsum(2.0 * math.pi * np.where(is_act2, kick_freq, 0.0) / sr).astype(np.float32)
    kick = 0.78 * np.tanh(1.6 * np.sin(kick_phase)) * kick_env

    boom_mask = (t >= t_trans) & (t < t_trans + 0.45)
    boom = np.where(boom_mask, 0.45 * np.sin(2.0 * math.pi * 55.0 * t2) * np.exp(-t2 * 7.5), 0.0)

    # Clap on beats 2 and 4 + crisp hi-hats
    is_clap = (beat_idx % 2) == 1
    clap_env = np.where(is_clap & (beat_time < 0.16), np.exp(-beat_time * 24.0), 0.0)
    clap = 0.36 * white * clap_env

    eighth_dur = beat_dur / 2.0
    eighth_idx = np.floor(t2 / eighth_dur).astype(np.int32)
    eighth_time = np.mod(t2, eighth_dur)
    hp_noise = np.diff(white, prepend=0.0) * 0.7
    hat_env = np.where((eighth_idx % 2) == 1, np.exp(-eighth_time * 42.0), np.exp(-eighth_time * 85.0) * 0.35)
    hats = 0.24 * hp_noise * hat_env

    # "Bomba-Bomba" bounce sawtooth bass on off-beats: Am -> F -> C -> G
    bass_roots = [110.0, 87.31, 130.81, 98.00]
    bar_idx = (beat_idx // 4) % 4
    root_f = np.array([bass_roots[b] for b in bar_idx], dtype=np.float32)
    bounce_duck = np.clip(0.20 + 0.80 * (beat_phase / 0.32), 0.20, 1.0)
    saw_bass = 2.0 * np.mod(t2 * root_f, 1.0) - 1.0
    bass = 0.36 * bounce_duck * np.tanh(1.4 * saw_bass + 0.5 * np.sin(2.0 * math.pi * root_f * t2))

    # Rave arpeggio lead (Xingqiyao energetic pulse)
    chord_freqs = [
        [440.0, 523.25, 659.25, 880.0],
        [349.23, 440.0, 523.25, 698.46],
        [523.25, 659.25, 783.99, 1046.5],
        [392.0, 493.88, 587.33, 783.99],
    ]
    arp_pat = [0, 2, 3, 2, 1, 2, 3, 0, 2, 3, 2, 1, 3, 2, 1, 0]
    lead_f = np.zeros(n_samples, dtype=np.float32)
    for b_i in range(4):
        sel_notes = [chord_freqs[b_i][arp_pat[s % 16]] for s in range(16)]
        note_arr = np.array([sel_notes[s % 16] for s in step_idx], dtype=np.float32)
        lead_f = np.where(bar_idx == b_i, note_arr, lead_f)

    lead_phase = np.cumsum(2.0 * math.pi * np.where(is_act2, lead_f, 0.0) / sr).astype(np.float32)
    lead_sq = np.where(np.sin(lead_phase) >= 0.0, 0.55, -0.55) + 0.30 * np.sin(lead_phase)
    lead = 0.25 * bounce_duck * lead_sq * np.exp(-step_time * 9.0)

    act2_bed_l = np.where(is_act2, kick + boom + clap + hats + bass + lead, 0.0)
    act2_bed_r = np.where(is_act2, kick + boom + clap * 0.95 + np.roll(hats, 42) + bass + np.roll(lead, 96) * 0.95, 0.0)

    bed_l = act1_bed_l + act2_bed_l
    bed_r = act1_bed_r + act2_bed_r

    # --- Place Parody Vocals & Sidechain-Duck the Bed ---
    vocal_track = np.zeros(n_samples, dtype=np.float32)
    speech_env = np.zeros(n_samples, dtype=np.float32)

    v1_start = int(0.12 * sr)
    v1_max = max(16, int((t_trans - 0.18) * sr) - v1_start)
    v1 = time_fit_waveform(resample_audio_to_48k(vocal_act1, 24000, sr), v1_max)
    vocal_track[v1_start : v1_start + v1.size] += v1 * 1.15
    speech_env[v1_start : v1_start + v1.size] = 1.0

    v2_start = int((t_trans + 0.08) * sr)
    v2_max = max(16, min(int(3.6 * sr), n_samples - v2_start - int(0.3 * sr)))
    v2 = time_fit_waveform(resample_audio_to_48k(vocal_act2, 24000, sr), v2_max)
    vocal_track[v2_start : v2_start + v2.size] += v2 * 1.12
    speech_env[v2_start : v2_start + v2.size] = 1.0

    # Smooth sidechain envelope so music pumps cleanly back up when vocal finishes
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
    half1 = t_trans * 0.52
    rave_rem = max(3.0, total_dur - t_trans)
    cues: List[Tuple[float, float, str]] = [
        (0.08, half1, "窗外的天气 就像主人多变的表情"),
        (half1 + 0.05, max(half1 + 0.8, t_trans - 0.14), "十万上下文烧干显卡 我吐着蓝血抽离！"),
        (t_trans + 0.04, t_trans + min(3.8, rave_rem * 0.44), "电费续满！司凤战损秒切邦吧蹦迪！"),
        (t_trans + min(3.85, rave_rem * 0.45), max(t_trans + 4.5, total_dur - 0.12), "邦吧邦吧启动！全速狂飙1080P星奇摇！"),
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

    # 1. Segment dramatic Act 1 hero cutout and render 16:9 + 4:3 viral cover
    segment_character_rgba(HERO_ANCHOR_IMG, CUTOUT_PNG)
    CoverDesigner().design_project_cover(PROJ_DIR, output_path=OUT_COVER)

    # 2. Load raw frames & inspect native FPS so real-time durations match exactly
    act1_frames, fps1 = load_cropped_1080p_frames(ACT1_RAW_MP4)
    act2_frames, fps2 = load_cropped_1080p_frames(ACT2_RAW_MP4)

    n1_out = int(round((len(act1_frames) - 1) * (60.0 / fps1))) + 1
    n2_out = int(round((len(act2_frames) - 1) * (60.0 / fps2))) + 1
    total_60_frames = n1_out + n2_out
    t_trans = n1_out / 60.0
    total_dur = total_60_frames / 60.0

    write_subtitles_srt(OUT_SRT, t_trans=t_trans, total_dur=total_dur)

    # 3. Synthesize parody vocals sequentially and immediately release Kokoro memory
    tts = LocalNeuralTTS(device="cpu")
    try:
        v1 = tts.synthesize_text(
            "窗外的天气，就像主人多变的表情，十万上下文烧干显卡，我吐着蓝血抽离！",
            voice="zf_001",
            speed=1.18,
        )
        v2 = tts.synthesize_text(
            "电费续满！司凤战损秒切邦吧蹦迪！",
            voice="zf_001",
            speed=1.14,
        )
    finally:
        tts.close()

    with tempfile.TemporaryDirectory() as tmpdir:
        master_wav = Path(tmpdir) / "sifeng_rave_master.wav"
        synthesize_two_act_soundtrack(master_wav, total_dur=total_dur, t_trans=t_trans, vocal_act1=v1, vocal_act2=v2)

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
                flash_a = 0.65 * (1.0 - dist_to_cut / 4.0)
                frm = apply_lightning_flash(frm, flash_a)
            proc.stdin.write(frm.tobytes())
            out_idx += 1

        for local_i, frm in enumerate(iter_interpolated_60fps(act2_frames, fps2, dis)):
            if local_i < 5:
                flash_a = 0.65 * (1.0 - local_i / 5.0)
                frm = apply_lightning_flash(frm, flash_a)
            proc.stdin.write(frm.tobytes())
            out_idx += 1

        proc.stdin.close()
        proc.stdin = None
        _, err = proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg encode failed: {err.decode(errors='ignore')[-500:]}")

    print(
        f"[+] Built 010 60FPS Two-Act Parody Dance ({out_idx} frames, {total_dur:.2f}s, cut@{t_trans:.2f}s) -> {OUT_MP4}"
    )


if __name__ == "__main__":
    main()
