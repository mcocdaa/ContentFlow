#!/usr/bin/env python3
"""1080P @ 60FPS Multi-AI Comedy Reversal + Trio Saotui Dance (30 Sexy) Pipeline for Project 016."""

from __future__ import annotations

import gc
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
PROJ_DIR = SCRIPT_DIR.parent
ROOT_DIR = PROJ_DIR.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.bgm_hunter import BilibiliBgmHunter  # noqa: E402
from core.cover_designer import CoverDesigner  # noqa: E402
from core.episode_assembler import ActSpec, EpisodeAssembler, EpisodeSpec, probe_video_frame_info  # noqa: E402
from core.local_tts import LocalNeuralTTS  # noqa: E402
from core.studio_renderer import segment_character_rgba  # noqa: E402

ASSETS_DIR = PROJ_DIR / "assets"
OUTPUT_DIR = PROJ_DIR / "output"
CUTOUTS_DIR = OUTPUT_DIR / "cutouts"
DELIV_DIR = PROJ_DIR / "delivery"

ACT1_RAW_MP4 = OUTPUT_DIR / "act1_ginkgo_broom_7s_1080p.mp4"
ACT2_RAW_MP4 = OUTPUT_DIR / "act2_ginkgo_saotui_10s_1080p.mp4"
ACT3A_RAW_MP4 = OUTPUT_DIR / "act3a_caught_dancing_8s_1080p.mp4"
ACT3B_RAW_MP4 = OUTPUT_DIR / "act3b_trio_saotui_8s_1080p.mp4"
ACT4_RAW_MP4 = OUTPUT_DIR / "act4_trio_finale_cta_8s_1080p.mp4"

HERO_ANCHOR_IMG = ASSETS_DIR / "trio_ginkgo_cover_hero_16x9.jpg"
CLEAN_BG_IMG = ASSETS_DIR / "yowane_ginkgo_clean_bg_16x9.jpg"
CUTOUT_PNG = CUTOUTS_DIR / "yowane_ginkgo_hero_cutout.png"

LOCAL_SAOTUI_MP4 = Path(
    "/home/mcocdaa/.gemini/antigravity-cli/brain/39f8b9d2-5144-4147-abc6-0d24e37e1d80/scratch/saotui_1080_full.mp4"
)
BVID_SAOTUI = "BV1MA3gzHEsh"
BVID_COMEDY_BGM = "BV1o4KwzPERi"

OUT_MP4 = DELIV_DIR / "弱音银杏大道扫腿舞_final.mp4"
OUT_SRT = DELIV_DIR / "弱音银杏大道扫腿舞_subtitle.srt"
OUT_COVER = DELIV_DIR / "弱音银杏大道扫腿舞_cover.jpg"


def _probe_act_out_duration(video_path: Path, target_fps: float = 60.0) -> Tuple[int, float]:
    n_in, src_fps = probe_video_frame_info(video_path)
    n_out = int(round((max(1, n_in) - 1) * (target_fps / src_fps))) + 1
    return n_out, n_out / target_fps


def _write_srt(srt_path: Path, cues: List[Tuple[float, float, str]]) -> None:
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


def _trim_silence(wav: np.ndarray, sr: int = 24000, thresh: float = 0.008) -> np.ndarray:
    active = np.where(np.abs(wav) > thresh)[0]
    if active.size == 0:
        return wav
    i0 = max(0, int(active[0]) - int(0.03 * sr))
    i1 = min(wav.size, int(active[-1]) + int(0.05 * sr))
    return wav[i0:i1]


def _synth_character_line(tts: LocalNeuralTTS, text: str, speaker: str) -> np.ndarray:
    """Synthesizes 3 distinctly voiced lines for Yowane Haku, DeepSeek Dafeiyu, and Gemini Neko."""
    if speaker == "yowane":
        edge_voice, kokoro_voice, speed = "zh-TW-HsiaoChenNeural", "zf_002", 1.14
    elif speaker == "dafeiyu":
        edge_voice, kokoro_voice, speed = "zh-CN-XiaoxiaoNeural", "zf_018", 1.18
    else:
        edge_voice, kokoro_voice, speed = "zh-CN-XiaoyiNeural", "zf_001", 1.20

    try:
        wav = tts._synth_edge_tts(text, edge_voice=edge_voice, speed=speed)
    except Exception:
        wav = tts.synthesize_text(text, voice=kokoro_voice, speed=speed, edge_voice=edge_voice)

    wav = _trim_silence(wav, sr=tts.sample_rate)
    peak = float(np.max(np.abs(wav))) if wav.size else 1.0
    if peak > 1e-4:
        wav = np.clip(wav * (0.90 / peak), -0.98, 0.98)
    return wav


def render_cover(crop_roi: Tuple[float, float, float, float] = (0.068, 0.01, 0.885, 0.99)) -> None:
    """Clears stale cutout cache, cleans corner mark, segments canonical trio hero, and renders vivid_scene covers."""
    if not HERO_ANCHOR_IMG.exists():
        raise FileNotFoundError(f"Missing trio hero anchor: {HERO_ANCHOR_IMG}")
    import cv2

    base_bg = CLEAN_BG_IMG if CLEAN_BG_IMG.exists() else HERO_ANCHOR_IMG
    CUTOUTS_DIR.mkdir(parents=True, exist_ok=True)
    CUTOUT_PNG.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory() as tmpdir:
        clean_hero = Path(tmpdir) / "trio_hero_clean.jpg"
        bgr = cv2.imread(str(HERO_ANCHOR_IMG))
        if bgr is not None:
            hh, ww = bgr.shape[:2]
            wm_mask = np.zeros((hh, ww), dtype=np.uint8)
            wm_mask[int(hh * 0.915) : hh, int(ww * 0.825) : ww] = 255
            bgr = cv2.inpaint(bgr, wm_mask, 7, cv2.INPAINT_TELEA)
            cv2.imwrite(str(clean_hero), bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 96])
            hero_src = clean_hero
        else:
            hero_src = HERO_ANCHOR_IMG
        segment_character_rgba(hero_src, CUTOUT_PNG, crop_roi=crop_roi, clean_corner_wm=False)
    CoverDesigner().design_cover(
        base_image_path=base_bg,
        output_path=OUT_COVER,
        hook_line1="让你扫银杏落叶？",
        hook_line2="弱音偷跳被抓包",
        hook_line3="反拉全员扫腿舞！",
        badge_text="全员抓包神反转",
        bottom_tags=["大肥鱼×Gemini娘", "60帧原声踩点"],
        transparent_hero_path=CUTOUT_PNG,
        hero_alpha_crop_top_ratio=0.98,
        cover_style="vivid_scene",
    )


def _check_freezedetect(video_path: Path) -> None:
    """Runs ffmpeg freezedetect (-50dB, 0.30s) on the rendered delivery MP4."""
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(video_path),
            "-vf",
            "freezedetect=n=-50dB:d=0.30",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    lines = [ln for ln in proc.stderr.splitlines() if "freeze_" in ln]
    print(f"[check] freezedetect (-50dB, 0.30s): {len(lines)} events")
    for ln in lines:
        print(f"  {ln}")


def main() -> None:
    raw_clips = [ACT1_RAW_MP4, ACT2_RAW_MP4, ACT3A_RAW_MP4, ACT3B_RAW_MP4, ACT4_RAW_MP4]
    for p in (*raw_clips, HERO_ANCHOR_IMG):
        if not p.exists():
            raise FileNotFoundError(f"Missing required asset: {p}")

    render_cover()

    acts: List[ActSpec] = [
        ActSpec(video_path=ACT1_RAW_MP4, transition_in="none", beat_punch_bpm=None),
        ActSpec(
            video_path=ACT2_RAW_MP4,
            transition_in="flash_cyan",
            beat_punch_bpm=108.5,
            punch_scale=1.26,
            focus_y_ratio=0.46,
            beats_per_shot=3,
        ),
        ActSpec(
            video_path=ACT3A_RAW_MP4,
            transition_in="flash_neon",
            beat_punch_bpm=105.0,
            punch_scale=1.18,
            focus_y_ratio=0.36,
            beats_per_shot=5,
            punch_start_sec=2.4,
        ),
        ActSpec(
            video_path=ACT3B_RAW_MP4,
            transition_in="flash_cyan",
            beat_punch_bpm=108.5,
            punch_scale=1.22,
            focus_y_ratio=0.40,
            beats_per_shot=3,
            punch_start_sec=0.8,
        ),
        ActSpec(
            video_path=ACT4_RAW_MP4,
            transition_in="flash_neon",
            beat_punch_bpm=108.5,
            punch_scale=1.16,
            focus_y_ratio=0.35,
            beats_per_shot=4,
            punch_start_sec=1.6,
        ),
    ]

    act_starts: List[float] = []
    act_durs: List[float] = []
    cur_t = 0.0
    for act in acts:
        act_starts.append(cur_t)
        _, dur = _probe_act_out_duration(act.video_path, 60.0)
        act_durs.append(dur)
        cur_t += dur
    total_dur = cur_t

    dialogue_plan: List[Tuple[str, float, float, str, str]] = [
        (
            "yowane",
            act_starts[0] + 0.14,
            act_durs[0] * 0.45,
            "周日傍晚老板派我扫银杏落叶？",
            "【弱音】周日傍晚老板派我来扫银杏落叶？",
        ),
        (
            "yowane",
            act_starts[0] + act_durs[0] * 0.49,
            act_durs[0] * 0.48,
            "等等，这洗脑前奏一响，还扫什么地呀！",
            "【弱音】等等，这洗脑前奏一响，还扫什么地呀！",
        ),
        (
            "yowane",
            act_starts[1] + 0.14,
            act_durs[1] * 0.44,
            "扫帚一甩！银杏大道直接开跳扫腿舞！",
            "【弱音】扫帚一甩！金黄银杏大道直接开跳《扫腿舞》！",
        ),
        (
            "yowane",
            act_starts[1] + act_durs[1] * 0.56,
            act_durs[1] * 0.40,
            "这波60帧大长腿，把周一焦虑全踢飞！",
            "【弱音】这波60帧大长腿 把周一焦虑全踢飞！",
        ),
        (
            "dafeiyu",
            act_starts[2] + 0.12,
            act_durs[2] * 0.47,
            "抓包！弱音姐，老板派你扫银杏落叶，你咋偷偷在这儿狂跳扫腿舞啊？！",
            "【大肥鱼】抓包！老板让你扫银杏落叶 你咋偷跳扫腿舞啊？！",
        ),
        (
            "gemini",
            act_starts[2] + act_durs[2] * 0.50,
            act_durs[2] * 0.47,
            "喵哈哈！已全程高清录屏！这波摸鱼铁证发给老板，晚饭加小鱼干喵！",
            "【Gemini娘】喵哈哈！已高清录屏！铁证发给老板加小鱼干喵！",
        ),
        (
            "yowane",
            act_starts[3] + 0.12,
            act_durs[3] * 0.47,
            "别告状啦！单人扫地哪有播放量，咱仨一起跳扫腿舞，把老板小号干爆！",
            "【弱音】别告状啦！咱仨一起跳扫腿舞 把老板小号直接干爆！",
        ),
        (
            "dafeiyu",
            act_starts[3] + act_durs[3] * 0.50,
            act_durs[3] * 0.47,
            "等等，这鼓点怎么这么上头？！我的鲸鱼尾鳍也忍不住跟着甩起来啦！",
            "【大肥鱼】等等这鼓点怎么这么上头？！尾鳍也忍不住甩起来啦！",
        ),
        (
            "gemini",
            act_starts[4] + 0.12,
            act_durs[4] * 0.44,
            "全员摸鱼成功喵！金黄银杏大道三人狂舞，周一焦虑统统踢飞！",
            "【Gemini娘】全员摸鱼成功喵！银杏大道三人狂舞 踢飞周一焦虑！",
        ),
        (
            "yowane",
            act_starts[4] + act_durs[4] * 0.47,
            act_durs[4] * 0.50,
            "弹幕和评论区投票下期接棒跳热舞，扣1大肥鱼，扣2Gemini娘，速速三连！",
            "【弱音】弹幕/评论区投票下期接棒热舞：扣1大肥鱼 扣2Gemini娘！",
        ),
    ]

    vocal_overlays: List[Dict[str, Any]] = []
    srt_cues: List[Tuple[float, float, str]] = []
    tts = LocalNeuralTTS(device="cpu")
    try:
        for speaker, start_s, max_d, spoken, caption in dialogue_plan:
            wav_arr = _synth_character_line(tts, spoken, speaker=speaker)
            actual_d = min(max_d, wav_arr.size / float(tts.sample_rate))
            vocal_overlays.append(
                {
                    "wav": wav_arr,
                    "src_sr": tts.sample_rate,
                    "start_sec": start_s,
                    "max_duration_sec": max_d,
                    "gain": 1.28,
                    "duck_gain": 0.26,
                }
            )
            srt_cues.append((start_s, start_s + max(1.15, actual_d + 0.10), caption))
    finally:
        tts.close()
        gc.collect()

    _write_srt(OUT_SRT, srt_cues)

    dur_solo = act_starts[2]
    dur_caught = act_durs[2]
    dur_trio = max(1.0, total_dur - act_starts[3])

    hunter = BilibiliBgmHunter()
    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        saotui_solo_wav = td / "saotui_solo.wav"
        comedy_caught_wav = td / "comedy_caught.wav"
        saotui_trio_wav = td / "saotui_trio.wav"
        master_wav = td / "ep016_planb_master.wav"

        # Align exact choreography start t=7.50s in BV1MA3gzHEsh to Act1->Act2 cut
        drop_offset_in_song = 7.50
        song_start = max(0.0, drop_offset_in_song - act_durs[0])
        src_saotui = LOCAL_SAOTUI_MP4 if LOCAL_SAOTUI_MP4.exists() else BVID_SAOTUI

        hunter.extract_audio_clip(
            source=src_saotui,
            output_wav=saotui_solo_wav,
            start_sec=song_start,
            duration_sec=dur_solo + 0.20,
            fade_in_sec=0.03,
            fade_out_sec=0.08,
        )
        hunter.extract_audio_clip(
            source=BVID_COMEDY_BGM,
            output_wav=comedy_caught_wav,
            start_sec=0.0,
            duration_sec=dur_caught + 0.20,
            fade_in_sec=0.03,
            fade_out_sec=0.08,
        )
        hunter.extract_audio_clip(
            source=src_saotui,
            output_wav=saotui_trio_wav,
            start_sec=drop_offset_in_song,
            duration_sec=dur_trio + 0.20,
            fade_in_sec=0.03,
            fade_out_sec=0.22,
        )

        impacts = [
            max(0.4, act_starts[1] - 0.03),
            act_starts[2],
            act_starts[3],
            act_starts[4],
        ]
        hunter.concat_or_duck_segments(
            segments=[
                {"wav_path": saotui_solo_wav, "duration_sec": dur_solo, "gain": 0.90, "edge_fade_sec": 0.03},
                {"wav_path": comedy_caught_wav, "duration_sec": dur_caught, "gain": 0.78, "edge_fade_sec": 0.03},
                {"wav_path": saotui_trio_wav, "duration_sec": dur_trio, "gain": 0.94, "edge_fade_sec": 0.03},
            ],
            output_wav=master_wav,
            vocal_overlays=vocal_overlays,
            impact_times_sec=impacts,
        )

        spec = EpisodeSpec(
            acts=acts,
            audio_path=master_wav,
            output_mp4_path=OUT_MP4,
            subtitle_srt_path=OUT_SRT,
            target_fps=60.0,
            hook_banner_text="让你扫银杏落叶？弱音抓包全员狂跳扫腿舞！",
            hook_banner_sec=2.0,
        )
        res = EpisodeAssembler.assemble(spec)

    _check_freezedetect(OUT_MP4)
    print(f"[+] Built 016 Plan B Multi-AI Trio Saotui Dance: {res}")


if __name__ == "__main__":
    main()
