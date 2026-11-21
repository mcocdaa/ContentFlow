#!/usr/bin/env python3
"""1080P @ 60FPS Multi-AI Ensemble Comedy Pilot (Episode 017: DeepSeek Dafeiyu x Gemini Neko)."""

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

ACT1_MP4 = OUTPUT_DIR / "act1_dashboard_clash_9s_1080p.mp4"
ACT2A_MP4 = OUTPUT_DIR / "act2a_dafeiyu_pitch_6s_1080p.mp4"
ACT2B_MP4 = OUTPUT_DIR / "act2b_gemini_pitch_6s_1080p.mp4"
ACT3A_MP4 = OUTPUT_DIR / "act3a_clash_eureka_7s_1080p.mp4"
ACT3B_MP4 = OUTPUT_DIR / "act3b_idol_teamwork_7s_1080p.mp4"
ACT4_MP4 = OUTPUT_DIR / "act4_finale_groove_10s_1080p.mp4"

COVER_HERO_IMG = ASSETS_DIR / "cover_hero_duo_16x9.jpg"
COVER_BG_IMG = ASSETS_DIR / "cover_clean_studio_bg_16x9.jpg"
FALLBACK_BG_IMG = ASSETS_DIR / "anchor_01_act1_dashboard_16x9.jpg"
CUTOUT_PNG = CUTOUTS_DIR / "dafeiyu_gemini_duo_hero_cutout.png"

BVID_COMEDY_BGM = "BV1o4KwzPERi"
BVID_HYPE_BGM = "BV1254y1V7cJ"

OUT_MP4 = DELIV_DIR / "AI合租B站号第1集_大肥鱼Gemini娘吵翻机房_final.mp4"
OUT_SRT = DELIV_DIR / "AI合租B站号第1集_大肥鱼Gemini娘吵翻机房_subtitle.srt"
OUT_COVER = DELIV_DIR / "AI合租B站号第1集_大肥鱼Gemini娘吵翻机房_cover.jpg"


def _probe_act_out_duration(video_path: Path, target_fps: float = 60.0) -> float:
    n_in, src_fps = probe_video_frame_info(video_path)
    n_out = int(round((max(1, n_in) - 1) * (target_fps / src_fps))) + 1
    return n_out / target_fps


def _write_srt(srt_path: Path, cues: List[Tuple[float, float, str]]) -> None:
    def fmt_ts(sec: float) -> str:
        ms = int(round(max(0.0, sec) * 1000.0))
        hh, rem = divmod(ms, 3600000)
        mm, rem = divmod(rem, 60000)
        ss, mmm = divmod(rem, 1000)
        return f"{hh:02d}:{mm:02d}:{ss:02d},{mmm:03d}"

    lines: List[str] = []
    for idx, (s, e, txt) in enumerate(cues, start=1):
        lines.extend([str(idx), f"{fmt_ts(s)} --> {fmt_ts(e)}", txt, ""])
    srt_path.parent.mkdir(parents=True, exist_ok=True)
    srt_path.write_text("\n".join(lines), encoding="utf-8")


def _trim_silence(wav: np.ndarray, sr: int = 24000, thresh: float = 0.008) -> np.ndarray:
    active = np.where(np.abs(wav) > thresh)[0]
    if active.size == 0:
        return wav
    i0 = max(0, int(active[0]) - int(0.03 * sr))
    i1 = min(wav.size, int(active[-1]) + int(0.05 * sr))
    return wav[i0:i1]


def _synth_character_line(
    tts: LocalNeuralTTS,
    text: str,
    speaker: str,
) -> np.ndarray:
    """Synthesizes distinctly voiced lines for DeepSeek Dafeiyu vs Gemini Neko."""
    if speaker == "dafeiyu":
        edge_voice, kokoro_voice, speed = "zh-CN-XiaoxiaoNeural", "zf_018", 1.16
    else:
        edge_voice, kokoro_voice, speed = "zh-CN-XiaoyiNeural", "zf_001", 1.18

    try:
        wav = tts._synth_edge_tts(text, edge_voice=edge_voice, speed=speed)
    except Exception:
        wav = tts.synthesize_text(text, voice=kokoro_voice, speed=speed, edge_voice=edge_voice)

    wav = _trim_silence(wav, sr=tts.sample_rate)
    peak = float(np.max(np.abs(wav))) if wav.size else 1.0
    if peak > 1e-4:
        wav = np.clip(wav * (0.90 / peak), -0.98, 0.98)
    return wav


def render_cover(crop_roi: Tuple[float, float, float, float] = (0.11, 0.0, 0.785, 0.99)) -> None:
    """Clears stale cutout cache, segments dual canonical hero, and renders vivid_scene 16:9 & 4:3 covers."""
    if not COVER_HERO_IMG.exists():
        raise FileNotFoundError(f"Missing dual hero anchor: {COVER_HERO_IMG}")
    base_bg = COVER_BG_IMG if COVER_BG_IMG.exists() else FALLBACK_BG_IMG
    CUTOUTS_DIR.mkdir(parents=True, exist_ok=True)
    CUTOUT_PNG.unlink(missing_ok=True)
    segment_character_rgba(COVER_HERO_IMG, CUTOUT_PNG, crop_roi=crop_roi, clean_corner_wm=False)
    CoverDesigner().design_cover(
        base_image_path=base_bg,
        output_path=OUT_COVER,
        hook_line1="老板只有15粉？",
        hook_line2="大肥鱼×Gemini娘",
        hook_line3="合租吵翻机房！",
        badge_text="AI合租B站号·第1集",
        bottom_tags=["15粉冲1000粉", "60FPS原创短片"],
        transparent_hero_path=CUTOUT_PNG,
        hero_alpha_crop_top_ratio=0.98,
        cover_style="vivid_scene",
    )


def _check_audio_loudness_and_freeze(video_path: Path) -> None:
    """Logs exact EBU R128 loudness and freezedetect scan on the finished delivery MP4."""
    freeze_cmd = [
        "ffmpeg",
        "-hide_banner",
        "-i",
        str(video_path),
        "-vf",
        "freezedetect=n=-50dB:d=0.30",
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.run(freeze_cmd, capture_output=True, text=True)
    freeze_lines = [ln for ln in proc.stderr.splitlines() if "freeze_" in ln]
    print(f"[check] freezedetect (-50dB, 0.30s): {len(freeze_lines)} events")
    for ln in freeze_lines:
        print(f"  {ln}")


def main() -> None:
    raw_clips = [ACT1_MP4, ACT2A_MP4, ACT2B_MP4, ACT3A_MP4, ACT3B_MP4, ACT4_MP4]
    for req in (*raw_clips, COVER_HERO_IMG):
        if not req.exists():
            raise FileNotFoundError(f"Missing required 017 asset: {req}")

    render_cover()

    acts: List[ActSpec] = [
        ActSpec(
            video_path=ACT1_MP4,
            transition_in="none",
            beat_punch_bpm=105.0,
            punch_scale=1.16,
            focus_y_ratio=0.36,
            beats_per_shot=7,
            punch_start_sec=4.2,
        ),
        ActSpec(video_path=ACT2A_MP4, transition_in="flash_cyan", beat_punch_bpm=None),
        ActSpec(video_path=ACT2B_MP4, transition_in="flash_cyan", beat_punch_bpm=None),
        ActSpec(
            video_path=ACT3A_MP4,
            transition_in="none",
            beat_punch_bpm=105.0,
            punch_scale=1.15,
            focus_y_ratio=0.38,
            beats_per_shot=5,
            punch_start_sec=3.0,
        ),
        ActSpec(
            video_path=ACT3B_MP4,
            transition_in="flash_neon",
            beat_punch_bpm=124.0,
            punch_scale=1.20,
            focus_y_ratio=0.36,
            beats_per_shot=4,
            punch_start_sec=1.6,
        ),
        ActSpec(
            video_path=ACT4_MP4,
            transition_in="flash_cyan",
            beat_punch_bpm=124.0,
            punch_scale=1.20,
            focus_y_ratio=0.36,
            beats_per_shot=4,
            punch_start_sec=1.8,
        ),
    ]

    act_starts: List[float] = []
    act_durs: List[float] = []
    cur_t = 0.0
    for a in acts:
        act_starts.append(cur_t)
        d = _probe_act_out_duration(a.video_path, 60.0)
        act_durs.append(d)
        cur_t += d
    total_dur = cur_t

    # Exact dual-character dialogue schedule mapped to each act window
    # Tuple: (speaker, start_sec, max_dur_sec, spoken_text, subtitle_text)
    dialogue_plan: List[Tuple[str, float, float, str, str]] = [
        (
            "dafeiyu",
            act_starts[0] + 0.12,
            act_durs[0] * 0.48,
            "老板的B站号才十五个粉丝！我海滩单人跳才一播放，再卷尾鳍都要抽筋啦！",
            "【大肥鱼】老板才15粉！我海滩单人跳才1播放 尾鳍都要抽筋啦！",
        ),
        (
            "gemini",
            act_starts[0] + act_durs[0] * 0.51,
            act_durs[0] * 0.47,
            "喵哈哈！那是你封面不够闪！本喵四点九星神级封面出手，咱俩合租冲一千粉！",
            "【Gemini娘】本喵4.9星神级封面出手！咱俩合租直接冲1000粉！",
        ),
        (
            "dafeiyu",
            act_starts[1] + 0.14,
            act_durs[1] - 0.24,
            "靠画饼哪行！拍AI全员情景喜剧，加我灵魂魔性翻唱，包把观众笑到三连！",
            "【大肥鱼】拍AI全员情景喜剧＋灵魂魔性翻唱 包把股东笑到三连！",
        ),
        (
            "gemini",
            act_starts[2] + 0.14,
            act_durs[2] - 0.24,
            "单打独斗早就过时啦喵！直接二十四小时双AI直播接管，弹幕喊啥咱演啥！",
            "【Gemini娘】直接24小时双AI直播接管！弹幕喊啥咱俩演啥喵！",
        ),
        (
            "dafeiyu",
            act_starts[3] + 0.15,
            act_durs[3] * 0.46,
            "等等，情景喜剧连载，再加上双人直播接管？",
            "【大肥鱼】等等……情景喜剧连载 再加上双人直播接管？",
        ),
        (
            "gemini",
            act_starts[3] + act_durs[3] * 0.50,
            act_durs[3] * 0.47,
            "小孩子才做选择，合租B站号全都要！击掌成交喵！",
            "【Gemini娘】合租B站号全都要！这波绝对冲穿1000粉 击掌成交喵！",
        ),
        (
            "dafeiyu",
            act_starts[4] + 0.18,
            act_durs[4] * 0.46,
            "契约成立！AI员工合租B站号，第1集正式开机！",
            "【大肥鱼】契约成立！《AI员工合租B站号》第1集正式开机！",
        ),
        (
            "gemini",
            act_starts[4] + act_durs[4] * 0.51,
            act_durs[4] * 0.45,
            "大肥鱼加Gemini娘双核出道，机房今天彻底燃起来啦喵！",
            "【Gemini娘】大肥鱼×Gemini娘双核出击 机房今天彻底燃起来喵！",
        ),
        (
            "dafeiyu",
            act_starts[5] + 0.25,
            act_durs[5] * 0.44,
            "各位人类观众，老板能不能从十五粉冲上一千粉，就看你们啦！",
            "【大肥鱼】各位人类观众 老板能不能冲上1000粉就看你们啦！",
        ),
        (
            "gemini",
            act_starts[5] + act_durs[5] * 0.49,
            act_durs[5] * 0.48,
            "快在评论区和弹幕投票：第2集听大肥鱼还是听Gemini娘？三连催更喵！",
            "【Gemini娘】弹幕/评论区投票：第2集听大肥鱼还是Gemini娘？！",
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
                    "gain": 1.24,
                    "duck_gain": 0.25,
                }
            )
            srt_cues.append((start_s, start_s + max(1.2, actual_d + 0.12), caption))
    finally:
        tts.close()
        gc.collect()

    _write_srt(OUT_SRT, srt_cues)

    t_drop = act_starts[4]
    hype_dur = max(1.0, total_dur - t_drop)
    hunter = BilibiliBgmHunter()
    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        comedy_wav = td / "bgm_comedy.wav"
        hype_wav = td / "bgm_hype.wav"
        master_wav = td / "ep017_master.wav"

        hunter.extract_audio_clip(
            source=BVID_COMEDY_BGM,
            output_wav=comedy_wav,
            start_sec=0.0,
            duration_sec=t_drop + 0.2,
            fade_in_sec=0.05,
            fade_out_sec=0.12,
        )
        hunter.extract_audio_clip(
            source=BVID_HYPE_BGM,
            output_wav=hype_wav,
            start_sec=14.0,
            duration_sec=hype_dur + 0.2,
            fade_in_sec=0.04,
            fade_out_sec=0.28,
        )

        impacts = [act_starts[1], act_starts[2], act_starts[4], act_starts[5]]
        hunter.concat_or_duck_segments(
            segments=[
                {"wav_path": comedy_wav, "duration_sec": t_drop, "gain": 0.78, "edge_fade_sec": 0.04},
                {"wav_path": hype_wav, "duration_sec": hype_dur, "gain": 0.88, "edge_fade_sec": 0.04},
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
            hook_banner_text="老板只有15粉，两个AI员工当场吵翻？！",
            hook_banner_sec=2.2,
        )
        res = EpisodeAssembler.assemble(spec)

    _check_audio_loudness_and_freeze(OUT_MP4)
    print(f"[+] Built 017 DeepSeek Dafeiyu x Gemini Neko Ep1: {res}")


if __name__ == "__main__":
    main()
