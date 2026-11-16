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
from core.competitor_benchmark import CompetitorBenchmarkEngine
from core.cover_designer import CoverDesigner
from core.episode_assembler import ActSpec, EpisodeAssembler, EpisodeSpec, apply_beat_camera_framing
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
