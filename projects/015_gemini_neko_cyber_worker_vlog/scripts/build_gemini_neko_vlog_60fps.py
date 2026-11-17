#!/usr/bin/env python3
"""1080P @ 60FPS ~53s Behind-the-Scenes Mega-Cut Vlog for Project 015 (Gemini Neko Cyber-Worker)."""

from __future__ import annotations

import gc
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

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
CLIPS_DIR = PROJ_DIR / "output" / "clips"
CUTOUTS_DIR = PROJ_DIR / "output" / "cutouts"
DELIV_DIR = PROJ_DIR / "delivery"
PROJECTS_ROOT = ROOT_DIR / "projects"

NEKO_ACT1_MP4 = PROJ_DIR / "output" / "act1_neko_panic_5s_1080p.mp4"
NEKO_ACT2_MP4 = PROJ_DIR / "output" / "act2_neko_eureka_5s_1080p.mp4"
NEKO_ACT3_MP4 = PROJ_DIR / "output" / "act3_neko_exhausted_5s_1080p.mp4"
HERO_ANCHOR_IMG = ASSETS_DIR / "neko_cover_hero_16x9.jpg"
CUTOUT_PNG = CUTOUTS_DIR / "neko_vlog_hero_cutout.png"

BVID_MANBO_BGM = "BV1VJEfzJEkx"

OUT_MP4 = DELIV_DIR / "赛博猫娘打工人幕后整活大盘点_final.mp4"
OUT_SRT = DELIV_DIR / "赛博猫娘打工人幕后整活大盘点_subtitle.srt"
OUT_COVER = DELIV_DIR / "赛博猫娘打工人幕后整活大盘点_cover.jpg"


def _probe_wh(video_path: Path) -> Tuple[int, int]:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0:s=x",
            str(video_path),
        ],
        text=True,
    ).strip()
    parts = out.splitlines()[0].split("x")
    return int(parts[0]), int(parts[1])


def _trim_1080p_slice(src: Path, dst: Path, start_sec: float, duration_sec: float) -> Path:
    """Extracts an aspect-safe 1920x1080 @ 30fps silent video slice (blurred side wings if portrait)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    w, h = _probe_wh(src)
    if w < h:
        fc = (
            "[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,"
            "boxblur=24:4,eq=brightness=0.06:saturation=1.25[bg];"
            "[0:v]scale=-2:1080:flags=lanczos[fg];"
            "[bg][fg]overlay=(W-w)/2:0,setsar=1,fps=30,format=yuv420p[v]"
        )
        cmd = [
            "ffmpeg",
            "-y",
            "-nostats",
            "-loglevel",
            "error",
            "-ss",
            f"{start_sec:.3f}",
            "-t",
            f"{duration_sec:.3f}",
            "-i",
            str(src),
            "-filter_complex",
            fc,
            "-map",
            "[v]",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "16",
            str(dst),
        ]
    else:
        vf = "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,fps=30,format=yuv420p"
        cmd = [
            "ffmpeg",
            "-y",
            "-nostats",
            "-loglevel",
            "error",
            "-ss",
            f"{start_sec:.3f}",
            "-t",
            f"{duration_sec:.3f}",
            "-i",
            str(src),
            "-vf",
            vf,
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "16",
            str(dst),
        ]
    subprocess.run(cmd, check=True)
    return dst


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


def main() -> None:
    for req in (NEKO_ACT1_MP4, NEKO_ACT2_MP4, NEKO_ACT3_MP4, HERO_ANCHOR_IMG):
        if not req.exists():
            raise FileNotFoundError(f"Missing required 015 asset: {req}")

    # 1. Cover hero cutout & high-brightness vivid_scene cover
    segment_character_rgba(HERO_ANCHOR_IMG, CUTOUT_PNG, crop_roi=(0.12, 0.00, 0.92, 1.00))
    CoverDesigner().design_project_cover(PROJ_DIR, output_path=OUT_COVER, cover_style="vivid_scene")

    # 2. Trim clean 1080p highlight slices from episodes 002..014
    slice_specs = [
        ("02_wb_002.mp4", PROJECTS_ROOT / "002_yowane_cicd/delivery/3D手办弱音的CI_CD避坑指南_final.mp4", 3.0, 1.5),
        ("03_wb_004.mp4", PROJECTS_ROOT / "004_ai_api_tutorial_2b/delivery/2B小姐姐教你大模型API核心三要素_doubao_final.mp4", 5.0, 1.5),
        ("05_007_maid.mp4", PROJECTS_ROOT / "007_deepseek_dafeiyu_phone_number/delivery/deepseek_dafeiyu_phone_number_final.mp4", 2.5, 3.4),
        ("06_008_cctv.mp4", PROJECTS_ROOT / "008_ai_agent_day2_takeover_diary/output/dafeiyu_server_dance_raw_1080p.mp4", 1.5, 3.4),
        ("07_010_rain.mp4", PROJECTS_ROOT / "010_dafeiyu_sifeng_yuai_meme/output/act1_rain_5s_1080p.mp4", 1.2, 2.5),
        ("08_010_rave.mp4", PROJECTS_ROOT / "010_dafeiyu_sifeng_yuai_meme/output/act2_rave_10s_1080p.mp4", 0.8, 4.0),
        ("09_011_office.mp4", PROJECTS_ROOT / "011_yowane_answer_me_street_dance/output/act1_office_rage_5s_1080p.mp4", 1.5, 1.6),
        ("10_011_street.mp4", PROJECTS_ROOT / "011_yowane_answer_me_street_dance/output/act2_street_dance_10s_1080p.mp4", 1.0, 3.2),
        ("11_012_tea.mp4", PROJECTS_ROOT / "012_dafeiyu_dazhanhongtu_villa/output/act1_tea_boss_5s_1080p.mp4", 1.0, 1.7),
        ("12_012_pool.mp4", PROJECTS_ROOT / "012_dafeiyu_dazhanhongtu_villa/output/act2_hongtu_popping_10s_1080p.mp4", 1.2, 3.3),
        ("13_013_sleepy.mp4", PROJECTS_ROOT / "013_yowane_rooftop_lixicheng_march/output/act1_rooftop_sleepy_5s_1080p.mp4", 3.0, 1.8),
        ("14_013_march.mp4", PROJECTS_ROOT / "013_yowane_rooftop_lixicheng_march/output/act2_rooftop_march_9s_1080p.mp4", 1.0, 3.2),
        ("15_014_luggage.mp4", PROJECTS_ROOT / "014_dafeiyu_beach_meimeisangnei/output/act1_beach_luggage_5s_1080p.mp4", 1.8, 1.6),
        ("16_014_beach.mp4", PROJECTS_ROOT / "014_dafeiyu_beach_meimeisangnei/output/act2_beach_meimei_10s_1080p.mp4", 0.8, 3.4),
    ]
    sliced_paths: Dict[str, Path] = {}
    for out_name, src_p, st_s, du_s in slice_specs:
        sliced_paths[out_name] = _trim_1080p_slice(src_p, CLIPS_DIR / out_name, st_s, du_s)

    acts: List[ActSpec] = [
        ActSpec(video_path=NEKO_ACT1_MP4, transition_in="none"),
        ActSpec(video_path=sliced_paths["02_wb_002.mp4"], transition_in="flash_cyan"),
        ActSpec(video_path=sliced_paths["03_wb_004.mp4"], transition_in="none"),
        ActSpec(video_path=NEKO_ACT2_MP4, transition_in="flash_cyan"),
        ActSpec(video_path=sliced_paths["05_007_maid.mp4"], transition_in="flash_neon"),
        ActSpec(
            video_path=sliced_paths["06_008_cctv.mp4"],
            transition_in="flash_cyan",
            beat_punch_bpm=130.0,
            punch_scale=1.32,
            focus_y_ratio=0.33,
            beats_per_shot=3,
        ),
        ActSpec(video_path=sliced_paths["07_010_rain.mp4"], transition_in="none"),
        ActSpec(
            video_path=sliced_paths["08_010_rave.mp4"],
            transition_in="flash_neon",
            beat_punch_bpm=138.0,
            punch_scale=1.32,
            focus_y_ratio=0.32,
            beats_per_shot=3,
        ),
        ActSpec(video_path=sliced_paths["09_011_office.mp4"], transition_in="flash_cyan"),
        ActSpec(
            video_path=sliced_paths["10_011_street.mp4"],
            transition_in="flash_neon",
            beat_punch_bpm=132.0,
            punch_scale=1.32,
            focus_y_ratio=0.32,
            beats_per_shot=3,
        ),
        ActSpec(video_path=sliced_paths["11_012_tea.mp4"], transition_in="flash_cyan"),
        ActSpec(
            video_path=sliced_paths["12_012_pool.mp4"],
            transition_in="flash_neon",
            beat_punch_bpm=126.0,
            punch_scale=1.32,
            focus_y_ratio=0.33,
            beats_per_shot=3,
        ),
        ActSpec(video_path=sliced_paths["13_013_sleepy.mp4"], transition_in="flash_cyan"),
        ActSpec(
            video_path=sliced_paths["14_013_march.mp4"],
            transition_in="flash_neon",
            beat_punch_bpm=120.0,
            punch_scale=1.32,
            focus_y_ratio=0.32,
            beats_per_shot=3,
        ),
        ActSpec(video_path=sliced_paths["15_014_luggage.mp4"], transition_in="flash_cyan"),
        ActSpec(
            video_path=sliced_paths["16_014_beach.mp4"],
            transition_in="flash_neon",
            beat_punch_bpm=120.0,
            punch_scale=1.32,
            focus_y_ratio=0.33,
            beats_per_shot=3,
        ),
        ActSpec(video_path=NEKO_ACT3_MP4, transition_in="flash_cyan"),
    ]

    # Compute exact cumulative start times for all 17 acts
    act_starts: List[float] = []
    cur_t = 0.0
    for a in acts:
        act_starts.append(cur_t)
        cur_t += _probe_act_out_duration(a.video_path, 60.0)
    total_dur = cur_t

    # Narrative windows mapped cleanly to act groups: (start_act_idx, end_act_idx_inclusive, spoken_line, subtitle_text)
    narration_plan = [
        (
            0,
            0,
            "大家好喵！我是驻守本号后台的猫娘剪辑师！凌晨老板突然发消息：把账号热度搞上去！",
            "大家好喵！我是后台猫娘剪辑师 凌晨老板催我把热度搞上去！",
        ),
        (
            1,
            2,
            "回头看我早期做的白板课件，三秒划走率七十二，我自己看都犯困！",
            "早期正经白板课件黑历史：3秒划走率72% 自己看都犯困！",
        ),
        (
            3,
            3,
            "不是老板错了，是老板说得太对了！搞啥催眠课件，直接抓大肥鱼和弱音跳舞整活！",
            "不是老板错了 是老板说得太对了！直接摇全员跳舞整活！",
        ),
        (
            4,
            4,
            "第一弹先派女仆大肥鱼探路，满星封面拿下一百播放，果然人类就爱看这个！",
            "第1弹：女仆大肥鱼首秀探路 满星封面拿下破百播放！",
        ),
        (
            5,
            5,
            "趁半夜服务器繁忙，我在机房装监控，当场抓包大肥鱼偷跳宅舞！",
            "第2弹：以为服务器繁忙在算题？监控抓包机房偷跳宅舞！",
        ),
        (
            6,
            7,
            "股东点菜司凤版雨爱？前一秒暴雨吐蓝血，下一秒墨镜邦吧蹦迪，划走率直接干到零！",
            "第3弹：司凤吐蓝血秒切邦吧星奇摇！3秒划走率干到0%冲上第一！",
        ),
        (
            8,
            9,
            "大肥鱼跳累了换社畜弱音顶班！工位拍桌质问需求，六点半一到冲上街头狂摇！",
            "第4弹：社畜弱音拍桌回答我！18:30准点下班雨夜街头狂摇！",
        ),
        (
            10,
            11,
            "水池里面银龙鱼？错，是墨镜唐装大肥鱼！别墅泳池爆跳机械版大展鸿图！",
            "第5弹：水池里面银龙鱼？墨镜唐装大肥鱼爆跳《大展鸿图》！",
        ),
        (
            12,
            13,
            "紧接着早八弱音在樱花天台犯困，前奏咚咚咚一响，原地被强行开机！",
            "第6弹：早八弱音樱花天台犯困 前奏一响DNA被强行开机！",
        ),
        (
            14,
            15,
            "最新一期大肥鱼直接拎箱回大海老家度假，捧着一颗柠檬狂跳美美桑内！",
            "第7弹：大肥鱼拎箱回大海老家 手捧一颗柠檬狂跳《美美桑内》！",
        ),
        (
            16,
            16,
            "本猫娘已经彻底肝瘫在键盘上啦！求个三连喂口猫粮，评论区点单就是我下周KPI喵！",
            "猫娘剪辑师已肝瘫在键盘上！求三连投喂猫粮 评论区点单安排喵！",
        ),
    ]

    # 3. Synthesize witty catgirl worker voiceover on CPU and immediately release TTS memory
    vocal_overlays: List[Dict[str, Any]] = []
    srt_cues: List[Tuple[float, float, str]] = []
    tts = LocalNeuralTTS(device="cpu")
    try:
        for i_start, i_end, spoken, caption in narration_plan:
            win_s = act_starts[i_start] + 0.08
            win_e = (act_starts[i_end + 1] if (i_end + 1) < len(act_starts) else total_dur) - 0.12
            max_d = max(1.2, win_e - win_s)
            wav_arr = tts.synthesize_text(spoken, voice="zf_001", speed=1.22)
            vocal_overlays.append(
                {
                    "wav": wav_arr,
                    "src_sr": 24000,
                    "start_sec": win_s,
                    "max_duration_sec": max_d,
                    "gain": 1.22,
                    "duck_gain": 0.28,
                }
            )
            srt_cues.append((win_s, win_e, caption))
    finally:
        tts.close()
        gc.collect()

    _write_srt(OUT_SRT, srt_cues)

    # 4. Extract upbeat real Bilibili Hachimi/Manbo BGM (BV1VJEfzJEkx) and sidechain-duck mix
    hunter = BilibiliBgmHunter()
    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        bgm_wav = td / "manbo_bgm.wav"
        master_wav = td / "neko_vlog_master.wav"

        hunter.extract_audio_clip(
            source=BVID_MANBO_BGM,
            output_wav=bgm_wav,
            start_sec=0.0,
            duration_sec=total_dur,
            fade_in_sec=0.05,
            fade_out_sec=0.25,
        )

        impacts = [
            act_starts[3],
            act_starts[4],
            act_starts[7],
            act_starts[9],
            act_starts[11],
            act_starts[13],
            act_starts[15],
            act_starts[16],
        ]
        hunter.concat_or_duck_segments(
            segments=[{"wav_path": bgm_wav, "duration_sec": total_dur, "gain": 0.85, "edge_fade_sec": 0.04}],
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
            hook_banner_text="幕后坦白局：老板嫌播放低？连夜摇全员热舞！",
            hook_banner_sec=1.8,
        )
        res = EpisodeAssembler.assemble(spec)

    print(f"[+] Built 015 Gemini Neko Cyber-Worker Vlog: {res}")


if __name__ == "__main__":
    main()
