#!/usr/bin/env python3
"""1080P @ 60FPS Villa Tea -> Poolside Popping Dance Pipeline for Project 012 (Real Hongtu Audio + Beat Cuts)."""

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

ACT1_RAW_MP4 = PROJ_DIR / "output" / "act1_tea_boss_5s_1080p.mp4"
ACT2_RAW_MP4 = PROJ_DIR / "output" / "act2_hongtu_popping_10s_1080p.mp4"
HERO_ANCHOR_IMG = ASSETS_DIR / "dafeiyu_act1_villa_tea_16x9.jpg"
CUTOUT_PNG = CUTOUTS_DIR / "dafeiyu_villa_boss_cutout.png"
LOCAL_HONGTU_MP4 = Path(
    "/home/mcocdaa/.gemini/antigravity-cli/brain/41ad8e76-ac57-4779-8d42-6235758b0251/scratch/hongtu_popping.mp4"
)

OUT_MP4 = DELIV_DIR / "大肥鱼爆改别墅大展鸿图机械舞_final.mp4"
OUT_SRT = DELIV_DIR / "大肥鱼爆改别墅大展鸿图机械舞_subtitle.srt"
OUT_COVER = DELIV_DIR / "大肥鱼爆改别墅大展鸿图机械舞_cover.jpg"


def _probe_act_out_duration(video_path: Path, target_fps: float = 60.0) -> Tuple[int, float]:
    cap = cv2.VideoCapture(str(video_path))
    n_in = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    src_fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    cap.release()
    n_out = int(round((max(1, n_in) - 1) * (target_fps / src_fps))) + 1
    return n_out, n_out / target_fps


def build_synced_cold_open_wav(out_wav: Path, duration_sec: float, sr: int = 48000) -> None:
    """Generates a crisp Cantonese porcelain teacup clink + sub riser for the 0.8s cold open."""
    n = max(1, int(round(duration_sec * sr)))
    t = np.arange(n, dtype=np.float32) / float(sr)
    # Crisp porcelain clink at 0.10s + riser into the rap intro
    dt = np.maximum(0.0, t - 0.10)
    clink = np.where(
        t >= 0.10,
        (0.28 * np.sin(2.0 * math.pi * 2380.0 * dt) + 0.18 * np.sin(2.0 * math.pi * 3920.0 * dt)) * np.exp(-dt * 18.0),
        0.0,
    )
    riser_f = 55.0 + 75.0 * (t / max(0.2, duration_sec))
    riser = 0.20 * np.sin(2.0 * math.pi * riser_f * t) * (t / max(0.2, duration_sec))
    sig = clink + riser
    pcm = (np.stack([sig, sig], axis=-1).clip(-0.95, 0.95) * 32767.0).astype(np.int16)
    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def write_subtitles_srt(srt_path: Path, t_trans: float, total_dur: float) -> None:
    """Writes crisp Simplified Chinese captions aligned with the tea-table drop into popping."""
    rem = max(3.0, total_dur - t_trans)
    cues: List[Tuple[float, float, str]] = [
        (0.08, max(0.9, t_trans * 0.50), "别墅里面唱K 水池里面……银龙鱼？！"),
        (t_trans * 0.52, max(t_trans * 0.65, t_trans - 0.12), "看清楚！是墨镜黑金 DeepSeek 蓝色大肥鱼！"),
        (t_trans + 0.04, t_trans + min(4.2, rem * 0.45), "鼓点到位！别墅夜光泳池爆跳机械版《大展鸿图》！"),
        (t_trans + min(4.25, rem * 0.46), max(t_trans + 5.0, total_dur - 0.12), "1080P · 60FPS 零帧踩点多机位机械震感狂飙！"),
    ]

    def fmt_ts(sec: float) -> str:
        ms = int(round(max(0.0, sec) * 1000.0))
        hh, rem_ms = divmod(ms, 3600000)
        mm, rem_ms = divmod(rem_ms, 60000)
        ss, mmm = divmod(rem_ms, 1000)
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

    segment_character_rgba(HERO_ANCHOR_IMG, CUTOUT_PNG, crop_roi=(0.37, 0.01, 0.95, 0.67))
    CoverDesigner().design_project_cover(PROJ_DIR, output_path=OUT_COVER, cover_style="vivid_scene")

    _, dur1 = _probe_act_out_duration(ACT1_RAW_MP4, 60.0)
    _, dur2 = _probe_act_out_duration(ACT2_RAW_MP4, 60.0)
    total_dur = dur1 + dur2
    write_subtitles_srt(OUT_SRT, t_trans=dur1, total_dur=total_dur)

    hunter = BilibiliBgmHunter()
    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        cold_open_wav = td / "cold_open.wav"
        hongtu_song_wav = td / "hongtu_song.wav"
        master_wav = td / "hongtu_master.wav"

        # Align exact choreography drop t=4.20s in hongtu_popping to exact cut t=dur1
        drop_offset_in_song = 4.20
        cold_open_dur = max(0.0, dur1 - drop_offset_in_song)
        song_start = max(0.0, drop_offset_in_song - dur1)
        song_dur = total_dur - cold_open_dur

        src_hongtu = LOCAL_HONGTU_MP4 if LOCAL_HONGTU_MP4.exists() else "BV1veMtzGEHf"
        hunter.extract_audio_clip(
            source=src_hongtu,
            output_wav=hongtu_song_wav,
            start_sec=song_start,
            duration_sec=song_dur,
            fade_in_sec=0.04,
            fade_out_sec=0.16,
        )

        segments = []
        if cold_open_dur > 0.05:
            build_synced_cold_open_wav(cold_open_wav, cold_open_dur)
            segments.append({"wav_path": cold_open_wav, "duration_sec": cold_open_dur, "gain": 1.0, "edge_fade_sec": 0.01})
        segments.append({"wav_path": hongtu_song_wav, "duration_sec": song_dur, "gain": 1.0, "edge_fade_sec": 0.01})

        hunter.concat_or_duck_segments(
            segments=segments,
            output_wav=master_wav,
            impact_times_sec=[max(0.4, dur1 - 0.03)],
        )

        spec = EpisodeSpec(
            acts=[
                ActSpec(video_path=ACT1_RAW_MP4, transition_in="none", beat_punch_bpm=None),
                ActSpec(
                    video_path=ACT2_RAW_MP4,
                    transition_in="flash_cyan",
                    beat_punch_bpm=126.0,
                    punch_scale=1.32,
                    focus_y_ratio=0.33,
                    beats_per_shot=4,
                ),
            ],
            audio_path=master_wav,
            output_mp4_path=OUT_MP4,
            subtitle_srt_path=OUT_SRT,
            target_fps=60.0,
        )
        res = EpisodeAssembler.assemble(spec)

    print(f"[+] Built 012 Villa Popping Dance: {res}")


if __name__ == "__main__":
    main()
