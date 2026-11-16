"""Unit tests for CompetitorBenchmarkEngine, EpisodeAssembler, and vivid_scene CoverDesigner."""

from __future__ import annotations

import json
import subprocess
import wave
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

from core.aesthetic_evaluator import release_pyiqa_models
from core.bgm_hunter import BilibiliBgmHunter
from core.competitor_benchmark import CompetitorBenchmarkEngine
from core.cover_designer import CoverDesigner
from core.episode_assembler import (
    ActSpec,
    EpisodeAssembler,
    EpisodeSpec,
    apply_beat_camera_framing,
    apply_hook_banner_overlay,
    iter_interpolated_60fps,
    load_cropped_1080p_frames,
    probe_video_frame_info,
    render_hook_banner_rgba,
    stream_interpolated_60fps,
)
from core.quality_gate import VideoQualityGate


def _write_test_wav(path: Path, dur_sec: float = 0.6, sr: int = 48000) -> None:
    n = int(round(dur_sec * sr))
    t = np.arange(n, dtype=np.float32) / float(sr)
    tone = 0.25 * np.sin(2.0 * np.pi * 440.0 * t)
    stereo = np.stack([tone, tone], axis=-1)
    pcm = (stereo * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def _write_synthetic_video(path: Path, width: int = 640, height: int = 360, fps: int = 24, n_frames: int = 8) -> None:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")  # type: ignore[attr-defined]
    vw = cv2.VideoWriter(str(path), fourcc, float(fps), (width, height))
    assert vw.isOpened()
    for i in range(n_frames):
        frame = np.full((height, width, 3), (45, 70, 120), dtype=np.uint8)
        cx = int(width * 0.25 + i * 25)
        cv2.circle(frame, (cx % width, height // 2), 40, (240, 220, 80), -1)
        vw.write(frame)
    vw.release()


def test_vivid_scene_cover_and_benchmark_gap_detection(tmp_path: Path) -> None:
    """Verifies vivid_scene eliminates pitch-black voids, scores 20/20 on Cover QC, and removes cover gaps."""
    proj = tmp_path / "projects" / "091_vivid_meme"
    (proj / "delivery").mkdir(parents=True)

    # Dark textured stage source image (mirrors real anime night stage luma ~40-60)
    dark_src = tmp_path / "dark_stage.png"
    arr = np.full((1080, 1920, 3), (30, 34, 52), dtype=np.uint8)
    for lx in range(80, 1920, 180):
        arr[:, lx : lx + 24] = (68, 92, 148)
    for ly in range(90, 1080, 160):
        arr[ly : ly + 12, :] = np.maximum(arr[ly : ly + 12, :], np.array([58, 76, 128], dtype=np.uint8))
    arr[120:980, 1060:1620] = (145, 195, 245)
    arr[220:380, 1220:1460] = (45, 65, 110)
    Image.fromarray(arr, mode="RGB").save(dark_src)

    hero_cutout = tmp_path / "hero_cutout.png"
    hero_img = Image.new("RGBA", (640, 920), (0, 0, 0, 0))
    hdraw = ImageDraw.Draw(hero_img)
    hdraw.rounded_rectangle([80, 30, 560, 900], radius=90, fill=(235, 244, 255, 255))
    for hx in range(100, 540, 14):
        hdraw.line([(hx, 40), (hx + 18, 880)], fill=(20, 30, 58, 255), width=3)
    hero_img.save(hero_cutout)

    designer = CoverDesigner()
    vivid_cov = proj / "delivery" / "demo_cover.jpg"
    res = designer.design_cover(
        base_image_path=dark_src,
        output_path=vivid_cov,
        hook_line1="前一秒深夜敲代码",
        hook_line2="下一秒六点半打卡",
        hook_line3="街头丝滑开摇！",
        badge_text="热梗新创实录",
        bottom_tags=["60FPS街头潮舞", "高明度实景"],
        transparent_hero_path=hero_cutout,
        cover_style="vivid_scene",
    )
    assert res.layout_mode == "vivid_scene_16x9"
    assert vivid_cov.exists()
    assert res.output_4x3_path is not None and res.output_4x3_path.exists()

    engine = CompetitorBenchmarkEngine(root_dir=tmp_path)
    cov_metrics = engine.measure_cover(vivid_cov)
    assert cov_metrics["mean_brightness"] >= 105.0
    assert cov_metrics["dark_area_ratio"] <= 0.20

    report_vivid = engine.compare_project_against_benchmarks(proj)
    assert not any(g["area"] == "cover" for g in report_vivid["gaps"])

    gate = VideoQualityGate(root_dir=tmp_path)
    blockers: list[str] = []
    try:
        cov_dim = gate._eval_cover_ctr(vivid_cov, blockers)
        assert not blockers
        assert cov_dim.score == 20.0
        assert cov_dim.details.get("cover_split_hierarchy_ok") is True
    finally:
        release_pyiqa_models()

    # Verify benchmark catches an overly dark cover
    pitch_dark_cov = proj / "delivery" / "demo_cover.jpg"
    Image.new("RGB", (1920, 1080), (10, 10, 14)).save(pitch_dark_cov)
    report_dark = engine.compare_project_against_benchmarks(proj)
    assert any(g["area"] == "cover" and g["severity"] == "P0" for g in report_dark["gaps"])


def test_beat_camera_framing_and_episode_assembler_60fps(tmp_path: Path) -> None:
    """Verifies beat-synced wide/close-up framing and 24fps->60fps SAR=1:1/DAR=16:9 EpisodeAssembler output."""
    wide = np.zeros((1080, 1920, 3), dtype=np.uint8)
    wide[:, :] = (40, 80, 160)
    # Place high-contrast checkerboard around the upper-body focus point (x=960, y=367)
    wide[300:440, 880:1040] = (245, 240, 120)

    # Beat 0..3 @ 120 BPM (0.0s..1.9s) -> shot 0 (wide, unchanged)
    f_wide = apply_beat_camera_framing(wide, t_act_sec=0.5, bpm=120.0, punch_scale=1.32, beats_per_shot=4)
    assert np.array_equal(f_wide, wide)

    # Beat 4..7 @ 120 BPM (2.0s..3.9s) -> shot 1 (punched-in medium close-up)
    f_punch = apply_beat_camera_framing(wide, t_act_sec=2.1, bpm=120.0, punch_scale=1.32, beats_per_shot=4)
    assert f_punch.shape == (1080, 1920, 3)
    assert not np.array_equal(f_punch, wide)
    # Bright focus region grows substantially inside the punched-in frame
    assert (f_punch[..., 0] > 200).sum() > (wide[..., 0] > 200).sum()

    # Full EpisodeAssembler synthetic 24fps -> 60fps pipeline test (scaled 640x360 for fast CI)
    act_vid = tmp_path / "act1_24fps.mp4"
    _write_synthetic_video(act_vid, width=640, height=360, fps=24, n_frames=8)
    aud_wav = tmp_path / "track.wav"
    _write_test_wav(aud_wav, dur_sec=0.8)
    srt_path = tmp_path / "subs.srt"
    srt_path.write_text("1\n00:00:00,000 --> 00:00:00,400\n鼓点切镜测试\n", encoding="utf-8")
    out_mp4 = tmp_path / "assembled_60fps.mp4"

    spec = EpisodeSpec(
        acts=[ActSpec(video_path=act_vid, transition_in="flash_cyan", beat_punch_bpm=180.0, beats_per_shot=1)],
        audio_path=aud_wav,
        output_mp4_path=out_mp4,
        subtitle_srt_path=srt_path,
        target_fps=60.0,
        width=640,
        height=360,
    )
    res = EpisodeAssembler.assemble(spec)
    assert out_mp4.exists()
    assert res["frames"] >= 16

    probe_proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,width,height,sample_aspect_ratio,display_aspect_ratio,r_frame_rate,pix_fmt",
            "-of",
            "json",
            str(out_mp4),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    streams = json.loads(probe_proc.stdout)["streams"]
    v_stream = next(s for s in streams if s["codec_type"] == "video")
    assert v_stream["width"] == 640
    assert v_stream["height"] == 360
    assert v_stream["sample_aspect_ratio"] == "1:1"
    assert v_stream["display_aspect_ratio"] == "16:9"
    assert v_stream["r_frame_rate"] == "60/1"
    assert v_stream["pix_fmt"] == "yuv420p"

    # Verify O(1) streaming probe & frame interpolation match eager loader
    n_in, src_fps = probe_video_frame_info(act_vid)
    raw_frames, loaded_fps = load_cropped_1080p_frames(act_vid, target_w=640, target_h=360)
    assert n_in == len(raw_frames) == 8
    assert src_fps == loaded_fps
    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)  # type: ignore[attr-defined]
    streamed = list(
        stream_interpolated_60fps(
            act_vid, n_in=n_in, src_fps=src_fps, dis=dis, target_fps=60.0, target_w=640, target_h=360
        )
    )
    eager = list(iter_interpolated_60fps(raw_frames, src_fps=loaded_fps, dis=dis, target_fps=60.0))
    assert len(streamed) == len(eager)
    assert np.array_equal(streamed[0], eager[0])
    assert np.array_equal(streamed[-1], eager[-1])


def test_bgm_hunter_local_extract_and_sidechain_duck_and_punch_start(tmp_path: Path) -> None:
    """Verifies local WAV slice extraction, multi-segment sidechain ducking, and beat punch_start_sec."""
    src_wav = tmp_path / "full_song.wav"
    _write_test_wav(src_wav, dur_sec=1.2, sr=48000)

    hunter = BilibiliBgmHunter(cookies={})
    sliced_wav = tmp_path / "slice.wav"
    info = hunter.extract_audio_clip(
        source=src_wav,
        output_wav=sliced_wav,
        start_sec=0.1,
        duration_sec=0.5,
        fade_in_sec=0.02,
        fade_out_sec=0.05,
    )
    assert sliced_wav.exists()
    assert abs(float(info["duration_sec"]) - 0.5) <= 0.02
    assert "credit_line" in info and "full_song.wav" in info["credit_line"]
    with wave.open(str(sliced_wav), "rb") as wf:
        assert wf.getnchannels() == 2
        assert wf.getframerate() == 48000
        assert wf.getsampwidth() == 2

    vocal_wav = tmp_path / "vocal.wav"
    _write_test_wav(vocal_wav, dur_sec=0.35, sr=48000)
    master_wav = tmp_path / "master.wav"
    BilibiliBgmHunter.concat_or_duck_segments(
        segments=[
            {"wav_path": sliced_wav, "duration_sec": 0.45, "gain": 0.9},
            {"wav_path": sliced_wav, "duration_sec": 0.50, "gain": 1.0},
        ],
        output_wav=master_wav,
        vocal_overlays=[{"wav_path": vocal_wav, "start_sec": 0.05, "gain": 1.1, "duck_gain": 0.35}],
        impact_times_sec=[0.42],
        sr=48000,
    )
    assert master_wav.exists()
    with wave.open(str(master_wav), "rb") as wf:
        assert wf.getnchannels() == 2
        assert wf.getframerate() == 48000
        assert wf.getsampwidth() == 2
        assert wf.getnframes() == int(round((0.45 + 0.50) * 48000))

    wide = np.zeros((1080, 1920, 3), dtype=np.uint8)
    wide[300:440, 880:1040] = (240, 220, 100)
    before_punch = apply_beat_camera_framing(
        wide,
        t_act_sec=2.1,
        bpm=120.0,
        punch_scale=1.32,
        beats_per_shot=4,
        punch_start_sec=2.5,
    )
    assert np.array_equal(before_punch, wide)
    at_punch = apply_beat_camera_framing(
        wide,
        t_act_sec=2.6,
        bpm=120.0,
        punch_scale=1.32,
        beats_per_shot=4,
        punch_start_sec=2.5,
    )
    assert not np.array_equal(at_punch, wide)
    assert (at_punch[..., 0] > 200).sum() > (wide[..., 0] > 200).sum()


def test_episode_assembler_hook_banner_overlay(tmp_path: Path) -> None:
    """Verifies EpisodeSpec/_parse_spec_dict hook fields, <1 MiB RGBA patch, and t < hook_banner_sec gating."""
    default_spec = EpisodeSpec(
        acts=[ActSpec(video_path=tmp_path / "act1.mp4")],
        audio_path=tmp_path / "audio.wav",
        output_mp4_path=tmp_path / "out.mp4",
    )
    assert default_spec.hook_banner_text is None
    assert default_spec.hook_banner_sec == 1.6

    parsed = EpisodeAssembler._parse_spec_dict(
        {
            "acts": [{"video_path": "act1.mp4"}],
            "audio_path": "bgm.wav",
            "output_mp4_path": "final.mp4",
            "hook_banner_text": "  高能预警：下一秒全员开摇！  ",
            "hook_banner_sec": 1.35,
        },
        base_dir=tmp_path,
    )
    assert parsed.hook_banner_text == "高能预警：下一秒全员开摇！"
    assert parsed.hook_banner_sec == 1.35

    parsed_blank = EpisodeAssembler._parse_spec_dict(
        {
            "acts": [{"video_path": "act1.mp4"}],
            "audio_path": "bgm.wav",
            "output_mp4_path": "final.mp4",
            "hook_banner_text": "   ",
            "hook_banner_sec": 0.0,
        },
        base_dir=tmp_path,
    )
    assert parsed_blank.hook_banner_text is None
    assert parsed_blank.hook_banner_sec == 0.0

    # Pre-rendered 1080p RGBA patch must stay compact (< 1 MiB) and leave inactive frames untouched
    patch_1080 = render_hook_banner_rgba("⚡ 高能预警：深夜机房突然开摇！", frame_width=1920, frame_height=1080)
    assert patch_1080 is not None
    assert patch_1080.ndim == 3 and patch_1080.shape[2] == 4 and patch_1080.dtype == np.uint8
    assert patch_1080.nbytes < 1024 * 1024

    base_frame = np.full((1080, 1920, 3), (45, 70, 120), dtype=np.uint8)
    base_snapshot = base_frame.copy()
    f_pop = apply_hook_banner_overlay(base_frame, patch_1080, t_sec=0.0, hook_banner_sec=1.6)
    f_steady = apply_hook_banner_overlay(base_frame, patch_1080, t_sec=0.25, hook_banner_sec=1.6)
    f_inactive = apply_hook_banner_overlay(base_frame, patch_1080, t_sec=1.6, hook_banner_sec=1.6)

    assert np.array_equal(base_frame, base_snapshot)
    assert f_inactive is base_frame
    assert not np.array_equal(f_pop[:180, 560:1360], base_frame[:180, 560:1360])
    assert not np.array_equal(f_steady[:180, 560:1360], base_frame[:180, 560:1360])
    assert not np.array_equal(f_pop[:180, 560:1360], f_steady[:180, 560:1360])
    assert np.array_equal(f_steady[240:, :], base_frame[240:, :])

    # End-to-end streaming assembly via JSON spec: active window (t < 0.35s) vs clean tail (t >= 0.40s)
    act_vid = tmp_path / "hook_act_24fps.mp4"
    _write_synthetic_video(act_vid, width=640, height=360, fps=24, n_frames=18)
    aud_wav = tmp_path / "hook_track.wav"
    _write_test_wav(aud_wav, dur_sec=0.85)
    out_mp4 = tmp_path / "hook_assembled_60fps.mp4"
    spec_json = tmp_path / "episode_spec.json"
    spec_json.write_text(
        json.dumps(
            {
                "acts": [{"video_path": act_vid.name}],
                "audio_path": aud_wav.name,
                "output_mp4_path": out_mp4.name,
                "target_fps": 60.0,
                "width": 640,
                "height": 360,
                "hook_banner_text": "高能预警：下一秒丝滑开摇！",
                "hook_banner_sec": 0.35,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    res = EpisodeAssembler.assemble_from_json(spec_json)
    assert out_mp4.exists()
    assert res["frames"] >= 40

    cap = cv2.VideoCapture(str(out_mp4))
    assert cap.isOpened()
    decoded_frames: list[np.ndarray] = []
    try:
        while True:
            ok, frm = cap.read()
            if not ok:
                break
            decoded_frames.append(frm)
    finally:
        cap.release()

    assert len(decoded_frames) >= 36
    for idx in range(1, 18):
        frm = decoded_frames[idx]
        ref_bg = frm[15:52, 10:60].astype(np.float32).mean(axis=(0, 1))
        top_center_diff = float(np.abs(frm[15:52, 230:410].astype(np.float32) - ref_bg).mean())
        assert top_center_diff > 18.0, f"Expected active hook banner at frame {idx}, got diff={top_center_diff:.2f}"

    for idx in range(24, len(decoded_frames)):
        frm = decoded_frames[idx]
        ref_bg = frm[15:52, 10:60].astype(np.float32).mean(axis=(0, 1))
        top_center_diff = float(np.abs(frm[15:52, 230:410].astype(np.float32) - ref_bg).mean())
        assert top_center_diff < 5.0, (
            f"Expected un-overlaid frame {idx} after hook_banner_sec, got diff={top_center_diff:.2f}"
        )
