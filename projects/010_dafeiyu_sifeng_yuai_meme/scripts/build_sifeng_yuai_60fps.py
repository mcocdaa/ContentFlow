#!/usr/bin/env python3
"""1080P @ 60FPS Two-Act Parody Dance Pipeline for Project 010 (Real Viral Sifeng Remix + Beat Punch-In)."""

from __future__ import annotations

import math
import sys
import tempfile
import wave
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
PROJ_DIR = SCRIPT_DIR.parent
ROOT_DIR = PROJ_DIR.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.bgm_hunter import BilibiliBgmHunter  # noqa: E402
from core.cover_designer import CoverDesigner  # noqa: E402
from core.episode_assembler import ActSpec, EpisodeAssembler, EpisodeSpec  # noqa: E402
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


def add_storm_rain_and_thunder_overlay(bgm_wav: Path, t_trans: float, sr: int = 48000) -> None:
    """Blends subtle Act-1 rain ambience & thunder/drop hits without muddying the viral song vocals."""
    arr = BilibiliBgmHunter.load_wav_stereo_f32(bgm_wav, target_sr=sr).copy()
    n_samples = arr.shape[0]
    t = np.arange(n_samples, dtype=np.float32) / float(sr)
    rng = np.random.default_rng(20261116)
    white = rng.normal(0.0, 1.0, n_samples).astype(np.float32)

    # Subtle filtered rain whisper strictly during Act 1 (0 .. t_trans - 0.1s)
    smooth_rain = np.convolve(white, np.ones(16, dtype=np.float32) / 16.0, mode="same")
    rain_mask = np.where(t < max(0.2, t_trans - 0.1), 0.05, 0.0).astype(np.float32)

    # Subtle thunder rumble at 0.30s and explosive bass/lightning impact at t_trans - 0.05s
    impacts = np.zeros(n_samples, dtype=np.float32)
    for t_hit, gain in ((0.30, 0.18), (max(0.5, t_trans - 0.05), 0.28)):
        dt_h = np.maximum(0.0, t - t_hit)
        h_mask = (t >= t_hit) & (t < t_hit + 0.65)
        f_sweep = 46.0 + 135.0 * np.exp(-dt_h * 28.0)
        impacts += np.where(h_mask, gain * np.sin(2.0 * math.pi * f_sweep * dt_h) * np.exp(-dt_h * 6.5), 0.0)

    arr[:, 0] += smooth_rain * rain_mask + impacts
    arr[:, 1] += np.roll(smooth_rain, 149) * rain_mask + impacts

    peak = float(np.max(np.abs(arr))) if arr.size else 1.0
    if peak > 0.94:
        arr = np.tanh(arr * (0.90 / peak))
    pcm = (np.clip(arr, -0.98, 0.98) * 32767.0).astype(np.int16)
    with wave.open(str(bgm_wav), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def write_subtitles_srt(srt_path: Path, t_trans: float, total_dur: float) -> None:
    """Writes clean Simplified Chinese meme captions aligned to both acts."""
    rave_rem = max(3.0, total_dur - t_trans)
    cues: List[Tuple[float, float, str]] = [
        (0.08, max(0.8, t_trans * 0.50), "窗外的天气 就像是你多变的表情……"),
        (t_trans * 0.51, max(t_trans * 0.6, t_trans - 0.12), "十万字上下文烧干显卡 战损大肥鱼吐蓝血！"),
        (t_trans + 0.04, t_trans + min(3.8, rave_rem * 0.44), "真希望雨能下不停——邦吧邦吧蹦迪启动！"),
        (t_trans + min(3.85, rave_rem * 0.45), max(t_trans + 4.5, total_dur - 0.12), "原声司凤战损《雨爱》× 60FPS 星奇摇多机位狂飙！"),
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


def _probe_act_out_duration(video_path: Path, target_fps: float = 60.0) -> Tuple[int, float]:
    cap = cv2.VideoCapture(str(video_path))
    n_in = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    src_fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    cap.release()
    n_out = int(round((max(1, n_in) - 1) * (target_fps / src_fps))) + 1
    return n_out, n_out / target_fps


def main() -> None:
    for p in (ACT1_RAW_MP4, ACT2_RAW_MP4, HERO_ANCHOR_IMG):
        if not p.exists():
            raise FileNotFoundError(f"Missing required asset: {p}")

    segment_character_rgba(HERO_ANCHOR_IMG, CUTOUT_PNG)
    CoverDesigner().design_project_cover(PROJ_DIR, output_path=OUT_COVER, cover_style="vivid_scene")

    _, dur1 = _probe_act_out_duration(ACT1_RAW_MP4, 60.0)
    _, dur2 = _probe_act_out_duration(ACT2_RAW_MP4, 60.0)
    total_dur = dur1 + dur2
    write_subtitles_srt(OUT_SRT, t_trans=dur1, total_dur=total_dur)

    with tempfile.TemporaryDirectory() as tmpdir:
        bgm_wav = Path(tmpdir) / "sifeng_viral_real.wav"
        BilibiliBgmHunter().extract_audio_clip(
            source="BV1faak6AEzm",
            output_wav=bgm_wav,
            start_sec=0.0,
            duration_sec=total_dur,
            fade_in_sec=0.05,
            fade_out_sec=0.18,
        )
        add_storm_rain_and_thunder_overlay(bgm_wav, t_trans=dur1)

        spec = EpisodeSpec(
            acts=[
                ActSpec(video_path=ACT1_RAW_MP4, transition_in="none", beat_punch_bpm=None),
                ActSpec(
                    video_path=ACT2_RAW_MP4,
                    transition_in="flash_cyan",
                    beat_punch_bpm=138.0,
                    punch_scale=1.32,
                    focus_y_ratio=0.33,
                    beats_per_shot=4,
                ),
            ],
            audio_path=bgm_wav,
            output_mp4_path=OUT_MP4,
            subtitle_srt_path=OUT_SRT,
            target_fps=60.0,
        )
        res = EpisodeAssembler.assemble(spec)

    print(f"[+] Built 010 Real-Music Multi-Shot Parody Dance: {res}")


if __name__ == "__main__":
    main()
