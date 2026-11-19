#!/usr/bin/env python3
"""1080P @ 60FPS Golden Ginkgo Avenue Broom-Pun -> Saotui Dance (30 Sexy) Pipeline for Project 016."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import List, Tuple

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

ACT1_RAW_MP4 = PROJ_DIR / "output" / "act1_ginkgo_broom_7s_1080p.mp4"
ACT2_RAW_MP4 = PROJ_DIR / "output" / "act2_ginkgo_saotui_10s_1080p.mp4"
HERO_ANCHOR_IMG = ASSETS_DIR / "character_anchor.jpg"
CLEAN_BG_IMG = ASSETS_DIR / "yowane_ginkgo_clean_bg_16x9.jpg"
CUTOUT_PNG = CUTOUTS_DIR / "yowane_ginkgo_hero_cutout.png"

LOCAL_SAOTUI_MP4 = Path(
    "/home/mcocdaa/.gemini/antigravity-cli/brain/39f8b9d2-5144-4147-abc6-0d24e37e1d80/scratch/saotui_1080_full.mp4"
)
BVID_SAOTUI = "BV1MA3gzHEsh"

OUT_MP4 = DELIV_DIR / "弱音银杏大道扫腿舞_final.mp4"
OUT_SRT = DELIV_DIR / "弱音银杏大道扫腿舞_subtitle.srt"
OUT_COVER = DELIV_DIR / "弱音银杏大道扫腿舞_cover.jpg"


def _probe_act_out_duration(video_path: Path, target_fps: float = 60.0) -> Tuple[int, float]:
    n_in, src_fps = probe_video_frame_info(video_path)
    n_out = int(round((max(1, n_in) - 1) * (target_fps / src_fps))) + 1
    return n_out, n_out / target_fps


def write_subtitles_srt(srt_path: Path, t_trans: float, total_dur: float) -> None:
    """Writes crisp Simplified Chinese captions aligned with the broom-pun -> Saotui dance drop."""
    rem = max(3.0, total_dur - t_trans)
    cues: List[Tuple[float, float, str]] = [
        (0.08, max(1.20, t_trans * 0.48), "周日傍晚老板派我来扫银杏落叶？"),
        (t_trans * 0.50, max(t_trans * 0.72, t_trans - 0.08), "等等，这魔性前奏一响，还扫什么地啊！"),
        (t_trans + 0.04, t_trans + min(4.8, rem * 0.48), "扫帚一甩！金黄银杏大道直接开跳《扫腿舞》！"),
        (
            t_trans + min(4.86, rem * 0.50),
            max(t_trans + 5.4, total_dur - 0.12),
            "1080P 60FPS 原声踩点，把周一焦虑一脚踢飞！",
        ),
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


def render_cover() -> None:
    """Clears stale cutout cache, re-segments canonical hero, and renders vivid_scene 16:9 & 4:3 covers."""
    if not HERO_ANCHOR_IMG.exists():
        raise FileNotFoundError(f"Missing hero anchor: {HERO_ANCHOR_IMG}")
    base_bg = CLEAN_BG_IMG if CLEAN_BG_IMG.exists() else HERO_ANCHOR_IMG
    CUTOUTS_DIR.mkdir(parents=True, exist_ok=True)
    CUTOUT_PNG.unlink(missing_ok=True)
    segment_character_rgba(HERO_ANCHOR_IMG, CUTOUT_PNG, crop_roi=(0.15, 0.01, 0.82, 0.99))
    CoverDesigner().design_cover(
        base_image_path=base_bg,
        output_path=OUT_COVER,
        hook_line1="让你扫银杏落叶？",
        hook_line2="弱音直接甩飞扫帚",
        hook_line3="60帧狂跳扫腿舞！",
        badge_text="周日整活神反转",
        bottom_tags=["30Sexy原声踩点", "满屏大长腿"],
        transparent_hero_path=CUTOUT_PNG,
        hero_alpha_crop_top_ratio=0.96,
        cover_style="vivid_scene",
    )


def main() -> None:
    for p in (ACT1_RAW_MP4, ACT2_RAW_MP4, HERO_ANCHOR_IMG):
        if not p.exists():
            raise FileNotFoundError(f"Missing required asset: {p}")

    render_cover()

    _, dur1 = _probe_act_out_duration(ACT1_RAW_MP4, 60.0)
    _, dur2 = _probe_act_out_duration(ACT2_RAW_MP4, 60.0)
    total_dur = dur1 + dur2
    write_subtitles_srt(OUT_SRT, t_trans=dur1, total_dur=total_dur)

    hunter = BilibiliBgmHunter()
    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        main_song_wav = td / "saotui_main.wav"
        master_wav = td / "saotui_master.wav"

        # Align exact choreography start t=7.50s in BV1MA3gzHEsh to exact Act1->Act2 cut t=dur1
        drop_offset_in_song = 7.50
        song_start = max(0.0, drop_offset_in_song - dur1)
        src_media = LOCAL_SAOTUI_MP4 if LOCAL_SAOTUI_MP4.exists() else BVID_SAOTUI
        hunter.extract_audio_clip(
            source=src_media,
            output_wav=main_song_wav,
            start_sec=song_start,
            duration_sec=total_dur,
            fade_in_sec=0.03,
            fade_out_sec=0.16,
        )

        hunter.concat_or_duck_segments(
            segments=[
                {
                    "wav_path": main_song_wav,
                    "duration_sec": total_dur,
                    "gain": 1.0,
                    "edge_fade_sec": 0.01,
                }
            ],
            output_wav=master_wav,
            impact_times_sec=[max(0.4, dur1 - 0.03)],
        )

        spec = EpisodeSpec(
            acts=[
                ActSpec(video_path=ACT1_RAW_MP4, transition_in="none", beat_punch_bpm=None),
                ActSpec(
                    video_path=ACT2_RAW_MP4,
                    transition_in="flash_cyan",
                    beat_punch_bpm=108.5,
                    punch_scale=1.26,
                    focus_y_ratio=0.46,
                    beats_per_shot=3,
                ),
            ],
            audio_path=master_wav,
            output_mp4_path=OUT_MP4,
            subtitle_srt_path=OUT_SRT,
            target_fps=60.0,
            hook_banner_text="让你扫银杏落叶，没让你跳《扫腿舞》啊？！",
            hook_banner_sec=1.8,
        )
        res = EpisodeAssembler.assemble(spec)

    print(f"[+] Built 016 Golden Ginkgo Saotui Dance: {res}")


if __name__ == "__main__":
    main()
