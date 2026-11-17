#!/usr/bin/env python3
"""1080P @ 60FPS Sunny Beach Luggage -> Meimei Sangnei (One Spot) Dance Pipeline for Project 014."""

from __future__ import annotations

import math
import sys
import tempfile
import wave
from pathlib import Path
from typing import List, Tuple

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
PROJ_DIR = SCRIPT_DIR.parent
ROOT_DIR = PROJ_DIR.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.bgm_hunter import BilibiliBgmHunter  # noqa: E402
from core.cover_designer import CoverDesigner  # noqa: E402
from core.episode_assembler import ActSpec, EpisodeAssembler, EpisodeSpec, probe_video_frame_info  # noqa: E402
from core.studio_renderer import segment_character_rgba  # noqa: E402

ASSETS_DIR = PROJ_DIR / "assets"
CUTOUTS_DIR = PROJ_DIR / "output" / "cutouts"
DELIV_DIR = PROJ_DIR / "delivery"

ACT1_RAW_MP4 = PROJ_DIR / "output" / "act1_beach_luggage_5s_1080p.mp4"
ACT2_RAW_MP4 = PROJ_DIR / "output" / "act2_beach_meimei_10s_1080p.mp4"
HERO_ANCHOR_IMG = ASSETS_DIR / "dafeiyu_cover_hero_16x9.jpg"
CUTOUT_PNG = CUTOUTS_DIR / "dafeiyu_beach_hero_cutout.png"
LOCAL_JCOOKIE_MP4 = Path(
    "/home/mcocdaa/.gemini/antigravity-cli/brain/41ad8e76-ac57-4779-8d42-6235758b0251/scratch/014_meimei_jcookie.mp4"
)
BVID_JCOOKIE = "BV173GHzBEf3"

OUT_MP4 = DELIV_DIR / "大肥鱼海滩度假美美桑内_final.mp4"
OUT_SRT = DELIV_DIR / "大肥鱼海滩度假美美桑内_subtitle.srt"
OUT_COVER = DELIV_DIR / "大肥鱼海滩度假美美桑内_cover.jpg"


def _probe_act_out_duration(video_path: Path, target_fps: float = 60.0) -> Tuple[int, float]:
    n_in, src_fps = probe_video_frame_info(video_path)
    n_out = int(round((max(1, n_in) - 1) * (target_fps / src_fps))) + 1
    return n_out, n_out / target_fps


def build_synced_cold_open_wav(out_wav: Path, duration_sec: float, sr: int = 48000) -> None:
    """Generates a crisp ice-glass clink lead-in if Act 1 is slightly longer than 5.00s."""
    n = max(1, int(round(duration_sec * sr)))
    t = np.arange(n, dtype=np.float32) / float(sr)
    dt = np.maximum(0.0, t - 0.01)
    clink = (
        0.22 * np.sin(2.0 * math.pi * 1760.0 * dt)
        + 0.14 * np.sin(2.0 * math.pi * 2637.0 * dt)
    ) * np.exp(-dt * 16.0)
    pcm = (np.stack([clink, clink], axis=-1).clip(-0.95, 0.95) * 32767.0).astype(np.int16)
    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def write_subtitles_srt(srt_path: Path, t_trans: float, total_dur: float) -> None:
    """Writes crisp Simplified Chinese captions aligned with the beach vacation -> dance drop."""
    rem = max(3.0, total_dur - t_trans)
    cues: List[Tuple[float, float, str]] = [
        (0.08, max(0.95, t_trans * 0.48), "终于不报服务器繁忙！拎箱回大海老家度假啦～"),
        (t_trans * 0.50, max(t_trans * 0.68, t_trans - 0.10), "手捧冰镇“一颗柠檬” 心情真是美美桑内！"),
        (t_trans + 0.04, t_trans + min(4.6, rem * 0.48), "副歌鼓点到位！阳光椰林海滩元气开跳《美美桑内》！"),
        (t_trans + min(4.66, rem * 0.50), max(t_trans + 5.2, total_dur - 0.12), "1080P · 60FPS 原声踩点多机位纯享热舞！"),
    ]

    def fmt_ts(sec: float) -> str:
        ms = int(round(max(0.0, sec) * 1000.0))
        hh, rem_ms = divmod(ms, 3600000)
        mm, rem_ms = divmod(rem_ms, 60000)
        ss, mmm = divmod(rem_ms, 1000)
        return f"{hh:02d}:{mm:02d}:{ss:02d},{mmm:03d}"

    lines: List[str] = []
    for i, (s, e, txt) in enumerate(cues, start=1):
        lines.extend([str(i), f"{fmt_ts(s)} --> {fmt_ts(e)}", txt, ""])
    srt_path.parent.mkdir(parents=True, exist_ok=True)
    srt_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    for p in (ACT1_RAW_MP4, ACT2_RAW_MP4, HERO_ANCHOR_IMG):
        if not p.exists():
            raise FileNotFoundError(f"Missing required asset: {p}")

    segment_character_rgba(HERO_ANCHOR_IMG, CUTOUT_PNG, crop_roi=(0.20, 0.01, 0.80, 0.98))
    CoverDesigner().design_project_cover(PROJ_DIR, output_path=OUT_COVER, cover_style="vivid_scene")

    _, dur1 = _probe_act_out_duration(ACT1_RAW_MP4, 60.0)
    _, dur2 = _probe_act_out_duration(ACT2_RAW_MP4, 60.0)
    total_dur = dur1 + dur2
    write_subtitles_srt(OUT_SRT, t_trans=dur1, total_dur=total_dur)

    hunter = BilibiliBgmHunter()
    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        cold_open_wav = td / "cold_open.wav"
        main_song_wav = td / "meimei_main.wav"
        master_wav = td / "meimei_master.wav"

        # Align exact choreography start t=5.00s in BV173GHzBEf3 to exact cut t=dur1
        drop_offset_in_song = 5.00
        cold_open_dur = max(0.0, dur1 - drop_offset_in_song)
        song_start = max(0.0, drop_offset_in_song - dur1)
        needed_song_dur = total_dur - cold_open_dur

        src_media = LOCAL_JCOOKIE_MP4 if LOCAL_JCOOKIE_MP4.exists() else BVID_JCOOKIE
        hunter.extract_audio_clip(
            source=src_media,
            output_wav=main_song_wav,
            start_sec=song_start,
            duration_sec=needed_song_dur,
            fade_in_sec=0.04,
            fade_out_sec=0.16,
        )

        segments = []
        if cold_open_dur > 0.03:
            build_synced_cold_open_wav(cold_open_wav, cold_open_dur)
            segments.append(
                {
                    "wav_path": cold_open_wav,
                    "duration_sec": cold_open_dur,
                    "gain": 1.0,
                    "edge_fade_sec": 0.01,
                }
            )
        segments.append(
            {
                "wav_path": main_song_wav,
                "duration_sec": needed_song_dur,
                "gain": 1.0,
                "edge_fade_sec": 0.01,
            }
        )

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
                    beat_punch_bpm=120.0,
                    punch_scale=1.32,
                    focus_y_ratio=0.33,
                    beats_per_shot=3,
                ),
            ],
            audio_path=master_wav,
            output_mp4_path=OUT_MP4,
            subtitle_srt_path=OUT_SRT,
            target_fps=60.0,
            hook_banner_text="终于放假：大肥鱼回大海喝柠檬水美美桑内？！",
            hook_banner_sec=1.6,
        )
        res = EpisodeAssembler.assemble(spec)

    print(f"[+] Built 014 Sunny Beach Meimei Sangnei: {res}")


if __name__ == "__main__":
    main()
