#!/usr/bin/env python3
"""Video Assembler & 60FPS Interpolator for Project 006: Line 1.

Interpolates AI-polished frames to 60FPS using RIFE Vulkan,
muxes with aligned Phone Number chorus audio, and encodes
to high-quality H.264 MP4.
"""

import sys
import os
import argparse
import shutil
import subprocess
import json
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
POLISHED_FRAMES_DIR = ROOT_DIR / "projects" / "006_deepseek_whale_phone_number" / "output" / "line1_polished_frames"
OUTPUT_VIDEO = ROOT_DIR / "projects" / "006_deepseek_whale_phone_number" / "output" / "line1_3d_ai_polished.mp4"
AUDIO_FILE = ROOT_DIR / "projects" / "006_deepseek_whale_phone_number" / "assets" / "phone_number_chorus.mp3"
RIFE_BIN = ROOT_DIR / "vendor" / "bin" / "rife" / "rife-ncnn-vulkan"
RIFE_MODEL_DIR = ROOT_DIR / "vendor" / "bin" / "rife" / "rife-v4.6"


def interpolate_rife_60fps(input_dir: Path, output_dir: Path) -> Path:
    """Run RIFE Vulkan interpolation from 30FPS to 60FPS."""
    if not RIFE_BIN.exists():
        raise FileNotFoundError(f"RIFE executable not found at {RIFE_BIN}")
    if not RIFE_MODEL_DIR.exists():
        raise FileNotFoundError(f"RIFE model not found at {RIFE_MODEL_DIR}")

    output_dir.mkdir(parents=True, exist_ok=True)
    input_frames = sorted(input_dir.glob("*.png"))
    if not input_frames:
        raise FileNotFoundError(f"No frames found in {input_dir}")

    # For N frames at 30fps, 2x interpolation gives (2N - 1) frames at 60fps
    target_count = len(input_frames) * 2 - 1

    print(f"Running RIFE v4.6 Vulkan frame interpolation: {len(input_frames)} -> {target_count} frames (60FPS)...")
    cmd = [
        str(RIFE_BIN),
        "-i", str(input_dir),
        "-o", str(output_dir),
        "-m", str(RIFE_MODEL_DIR),
        "-f", "%08d.png",
        "-n", str(target_count),
    ]

    t0 = time.time()
    res = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.time() - t0

    if res.returncode != 0:
        raise RuntimeError(f"RIFE interpolation failed: {res.stderr or res.stdout}")

    out_frames = sorted(output_dir.glob("*.png"))
    print(f"RIFE interpolation completed in {elapsed:.1f}s ({len(out_frames)} frames generated).")
    return output_dir


def assemble_video_with_audio(
    frames_dir: Path,
    audio_path: Path,
    output_path: Path,
    fps: int = 60,
    audio_offset: float = 1.0,
):
    """Assemble image sequence into H.264 MP4 with synchronized audio."""
    frames = sorted(frames_dir.glob("*.png"))
    if not frames:
        raise FileNotFoundError(f"No frames found in {frames_dir}")

    # Re-sequence frames sequentially to avoid pattern matching errors
    staging_dir = frames_dir.parent / "_rife_sequential"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    for idx, f in enumerate(frames, start=1):
        target_name = f"{idx:08d}.png"
        shutil.copy2(f, staging_dir / target_name)

    video_duration = len(frames) / fps
    print(f"Total video frames: {len(frames)}, target FPS: {fps}, Duration: {video_duration:.3f}s")
    print(f"Synchronizing audio from {audio_path.name} at offset {audio_offset:.2f}s...")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Audio fade out over final 0.25s
    fade_start = max(0.0, video_duration - 0.25)
    audio_filter = f"afade=t=out:st={fade_start:.2f}:d=0.25"

    cmd = [
        "ffmpeg", "-y",
        "-r", str(fps),
        "-pattern_type", "sequence",
        "-i", str(staging_dir / "%08d.png"),
        "-ss", str(audio_offset),
        "-t", str(video_duration),
        "-i", str(audio_path),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-crf", "17",
        "-preset", "slow",
        "-c:a", "aac",
        "-b:a", "320k",
        "-af", audio_filter,
        "-shortest",
        str(output_path),
    ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    # Clean staging dir
    shutil.rmtree(staging_dir, ignore_errors=True)

    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg assembly failed: {res.stderr or res.stdout}")

    print(f"Video assembled successfully: {output_path}")


def verify_output(video_path: Path):
    """Verify video properties using ffprobe."""
    if not video_path.exists() or video_path.stat().st_size == 0:
        raise RuntimeError(f"Output video missing or empty: {video_path}")

    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=codec_name,codec_type,width,height,r_frame_rate,duration:format=duration,size,bit_rate",
        "-of", "json",
        str(video_path)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(res.stdout)

    v_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    a_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    fmt = data.get("format", {})

    print("=" * 60)
    print("Output Video Verification Metrics:")
    print(f"  File Path:      {video_path}")
    print(f"  File Size:      {int(fmt.get('size', 0)) / (1024*1024):.2f} MB")
    print(f"  Total Duration: {float(fmt.get('duration', 0)):.3f} seconds")
    print(f"  Total Bitrate:  {int(fmt.get('bit_rate', 0)) // 1000} kbps")
    if v_stream:
        fps_parts = v_stream.get("r_frame_rate", "60/1").split("/")
        fps_val = float(fps_parts[0]) / float(fps_parts[1]) if len(fps_parts) == 2 else float(fps_parts[0])
        print(f"  Video Codec:    {v_stream.get('codec_name')} ({v_stream.get('width')}x{v_stream.get('height')} @ {fps_val:.2f} fps)")
    if a_stream:
        print(f"  Audio Codec:    {a_stream.get('codec_name')} (Sample rate: {a_stream.get('sample_rate', '48000')}Hz)")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Assemble 60FPS Video with Audio")
    parser.add_argument("--input", type=Path, default=POLISHED_FRAMES_DIR, help="Polished frames directory")
    parser.add_argument("--output", type=Path, default=OUTPUT_VIDEO, help="Output MP4 file")
    parser.add_argument("--audio", type=Path, default=AUDIO_FILE, help="Chorus audio file")
    parser.add_argument("--offset", type=float, default=1.0, help="Audio start offset in seconds (default: 1.0)")
    args = parser.parse_args()

    rife_out_dir = args.output.parent / "line1_rife_60fps_frames"
    interpolate_rife_60fps(args.input, rife_out_dir)
    assemble_video_with_audio(rife_out_dir, args.audio, args.output, fps=60, audio_offset=args.offset)
    verify_output(args.output)


if __name__ == "__main__":
    main()
