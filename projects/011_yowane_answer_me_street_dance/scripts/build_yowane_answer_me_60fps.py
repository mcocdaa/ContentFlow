#!/usr/bin/env python3
"""1080P @ 60FPS Two-Act Office Rage -> Street Dance Pipeline for Project 011 (Real Viral BGM + Beat Cuts)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import List, Tuple

import cv2

SCRIPT_DIR = Path(__file__).resolve().parent
PROJ_DIR = SCRIPT_DIR.parent
ROOT_DIR = PROJ_DIR.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.bgm_hunter import BilibiliBgmHunter  # noqa: E402
from core.cover_designer import CoverDesigner  # noqa: E402
from core.episode_assembler import ActSpec, EpisodeAssembler, EpisodeSpec  # noqa: E402
from core.local_tts import LocalNeuralTTS  # noqa: E402
from core.studio_renderer import segment_character_rgba  # noqa: E402

ASSETS_DIR = PROJ_DIR / "assets"
CUTOUTS_DIR = PROJ_DIR / "output" / "cutouts"
DELIV_DIR = PROJ_DIR / "delivery"

ACT1_RAW_MP4 = PROJ_DIR / "output" / "act1_office_rage_5s_1080p.mp4"
ACT2_RAW_MP4 = PROJ_DIR / "output" / "act2_street_dance_10s_1080p.mp4"
HERO_ANCHOR_IMG = ASSETS_DIR / "yowane_act1_office_rage_16x9.jpg"
CUTOUT_PNG = CUTOUTS_DIR / "yowane_office_rage_cutout.png"
LOCAL_STREET_REF = Path(
    "/home/mcocdaa/.gemini/antigravity-cli/brain/41ad8e76-ac57-4779-8d42-6235758b0251/scratch/ref_street_cand2.mp4"
)

OUT_MP4 = DELIV_DIR / "社畜弱音回答我下班街头潮舞_final.mp4"
OUT_SRT = DELIV_DIR / "社畜弱音回答我下班街头潮舞_subtitle.srt"
OUT_COVER = DELIV_DIR / "社畜弱音回答我下班街头潮舞_cover.jpg"


def write_subtitles_srt(srt_path: Path, t_trans: float, total_dur: float) -> None:
    """Writes clean Simplified Chinese meme captions aligned to both acts."""
    half1 = t_trans * 0.48
    rem2 = max(3.0, total_dur - t_trans)
    cues: List[Tuple[float, float, str]] = [
        (0.08, half1, "需求改了八遍还不给加内存？！"),
        (half1 + 0.05, max(half1 + 0.8, t_trans - 0.14), "Look in my eyes！回答我！到底为什么？！"),
        (t_trans + 0.05, t_trans + min(3.7, rem2 * 0.44), "叮咚六点半！社畜准点下班 直接开摇！"),
        (t_trans + min(3.75, rem2 * 0.45), max(t_trans + 4.4, total_dur - 0.12), "18:30全速狂飙 霓虹斑马线1080P多机位街头热舞！"),
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

    segment_character_rgba(HERO_ANCHOR_IMG, CUTOUT_PNG, crop_roi=(0.18, 0.0, 0.82, 0.86))
    CoverDesigner().design_project_cover(PROJ_DIR, output_path=OUT_COVER, cover_style="vivid_scene")

    _, dur1 = _probe_act_out_duration(ACT1_RAW_MP4, 60.0)
    _, dur2 = _probe_act_out_duration(ACT2_RAW_MP4, 60.0)
    total_dur = dur1 + dur2
    write_subtitles_srt(OUT_SRT, t_trans=dur1, total_dur=total_dur)

    tts = LocalNeuralTTS(device="cpu")
    try:
        v1 = tts.synthesize_text(
            "需求改了八遍还不给加内存？看着我的眼睛！回答我！到底为什么？！",
            voice="zf_001",
            speed=1.18,
        )
    finally:
        tts.close()

    hunter = BilibiliBgmHunter()
    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        act1_wav = td / "phonk_intro.wav"
        act2_wav = td / "street_dance_sync.wav"
        master_wav = td / "yowane_real_master.wav"

        hunter.extract_audio_clip("BV1cwvTzfEoj", act1_wav, start_sec=0.0, duration_sec=dur1, fade_out_sec=0.10)
        act2_src = LOCAL_STREET_REF if LOCAL_STREET_REF.exists() else "BV1n6ovYQEZX"
        hunter.extract_audio_clip(act2_src, act2_wav, start_sec=7.0, duration_sec=dur2, fade_in_sec=0.04, fade_out_sec=0.16)

        hunter.concat_or_duck_segments(
            segments=[
                {"wav_path": act1_wav, "duration_sec": dur1, "gain": 0.90},
                {"wav_path": act2_wav, "duration_sec": dur2, "gain": 1.05},
            ],
            output_wav=master_wav,
            vocal_overlays=[
                {
                    "wav": v1,
                    "src_sr": 24000,
                    "start_sec": 0.10,
                    "max_duration_sec": max(1.0, dur1 - 0.20),
                    "gain": 1.15,
                    "duck_gain": 0.35,
                }
            ],
            impact_times_sec=[0.14, max(0.5, dur1 - 0.04)],
        )

        spec = EpisodeSpec(
            acts=[
                ActSpec(video_path=ACT1_RAW_MP4, transition_in="none", beat_punch_bpm=None),
                ActSpec(
                    video_path=ACT2_RAW_MP4,
                    transition_in="flash_neon",
                    beat_punch_bpm=132.0,
                    punch_scale=1.32,
                    focus_y_ratio=0.30,
                    beats_per_shot=4,
                ),
            ],
            audio_path=master_wav,
            output_mp4_path=OUT_MP4,
            subtitle_srt_path=OUT_SRT,
            target_fps=60.0,
        )
        res = EpisodeAssembler.assemble(spec)

    print(f"[+] Built 011 Real-BGM Multi-Shot Office-to-Street Dance: {res}")


if __name__ == "__main__":
    main()
