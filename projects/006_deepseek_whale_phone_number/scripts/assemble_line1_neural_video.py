#!/usr/bin/env python3
"""Assemble Line 1: 3D Rigged Motion + AI Neural Polish Keyframes + 60FPS RIFE Interpolation.

Fuses the 3D Phone Number choreography with Doubao-Seedream-5.0-Pro neural keyframes.
Interpolates across all 4 keyframe dance intervals using RIFE v4.6 Vulkan to produce
exactly 240 frames @ 60.00 FPS (4.000s), muxes with aligned Phone Number chorus audio,
and outputs output/line1_3d_ai_polished.mp4.
"""

import sys
import shutil
import subprocess
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from core.enhancer import MediaEnhancer

PROJ_DIR = Path(__file__).resolve().parent.parent
NEURAL_KF_DIR = PROJ_DIR / "assets" / "line1_neural_keyframes"
OUTPUT_DIR = PROJ_DIR / "output"
WORK_DIR = OUTPUT_DIR / "line1_work"
AUDIO_PATH = PROJ_DIR / "assets" / "phone_number_chorus.mp3"
FINAL_VIDEO = OUTPUT_DIR / "line1_3d_ai_polished.mp4"

KEYFRAME_FILES = [
    "neural_keyframe_1410.jpg",
    "neural_keyframe_1440.jpg",
    "neural_keyframe_1470.jpg",
    "neural_keyframe_1500.jpg",
    "neural_keyframe_1530.jpg",
]

TARGET_W = 720
TARGET_H = 1280
FRAMES_PER_SEGMENT = 61  # 4 segments * 60 frames = 240 frames @ 60FPS = 4.000s


def main():
    print("=" * 60)
    print("[*] Starting Line 1: 3D Motion + AI Neural Polish Video Assembly")
    print("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    enhancer = MediaEnhancer()
    rife_bin = enhancer.rife_path
    rife_model = rife_bin.parent / "rife-v4.6"

    # Step 1: Pre-scale keyframes to 720x1280 (Lanczos)
    scaled_keyframes = []
    scaled_dir = WORK_DIR / "scaled_keyframes"
    scaled_dir.mkdir(parents=True, exist_ok=True)

    for i, name in enumerate(KEYFRAME_FILES):
        src = NEURAL_KF_DIR / name
        if not src.exists():
            raise FileNotFoundError(f"Missing neural keyframe: {src}")
        dst = scaled_dir / f"kf_{i:02d}.png"
        subprocess.run([
            "ffmpeg", "-y", "-i", str(src),
            "-vf", f"scale={TARGET_W}:{TARGET_H}:flags=lanczos",
            str(dst)
        ], check=True, capture_output=True)
        scaled_keyframes.append(dst)
        print(f"  [+] Scaled keyframe {i}: {dst.name}")

    # Step 2: Dense optical flow interpolation across 4 segments
    interpolated_dir = WORK_DIR / "interpolated_sequence"
    interpolated_dir.mkdir(parents=True, exist_ok=True)

    global_frame_idx = 1
    t0 = time.time()

    for seg_idx in range(len(scaled_keyframes) - 1):
        k_start = scaled_keyframes[seg_idx]
        k_end = scaled_keyframes[seg_idx + 1]

        seg_in = WORK_DIR / f"seg_{seg_idx}_in"
        seg_out = WORK_DIR / f"seg_{seg_idx}_out"
        seg_in.mkdir(parents=True, exist_ok=True)
        seg_out.mkdir(parents=True, exist_ok=True)

        shutil.copy2(k_start, seg_in / "00000001.png")
        shutil.copy2(k_end, seg_in / "00000002.png")

        print(f"[*] Interpolating Segment {seg_idx+1}/{len(scaled_keyframes)-1} ({FRAMES_PER_SEGMENT-1} frames)...")
        cmd = [
            str(rife_bin),
            "-i", str(seg_in),
            "-o", str(seg_out),
            "-m", str(rife_model),
            "-n", str(FRAMES_PER_SEGMENT),
            "-f", "%08d.png",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"[-] RIFE error on segment {seg_idx}:\n{res.stderr}")
            sys.exit(1)

        seg_frames = sorted(seg_out.glob("*.png"))
        print(f"  [+] Segment {seg_idx+1} produced {len(seg_frames)} frames.")

        # Take first 60 frames of each 61-frame segment to avoid duplicating endpoint
        slice_end = len(seg_frames) - 1
        for f in seg_frames[:slice_end]:
            dst = interpolated_dir / f"{global_frame_idx:08d}.png"
            shutil.copy2(f, dst)
            global_frame_idx += 1

    total_frames = global_frame_idx - 1
    duration = total_frames / 60.0
    elapsed = time.time() - t0
    print(f"[+] Total interpolated continuous sequence: {total_frames} frames in {elapsed:.1f}s ({duration:.3f}s @ 60FPS)")

    # Step 3: FFmpeg Encode to H.264 High Profile and mux with audio
    print("[*] Assembling final video with audio sync...")
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-framerate", "60",
        "-i", str(interpolated_dir / "%08d.png"),
        "-ss", "1.0",
        "-i", str(AUDIO_PATH),
        "-c:v", "libx264",
        "-crf", "17",
        "-preset", "slow",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "320k",
        "-t", f"{duration:.3f}",
        "-af", f"afade=t=out:st={duration - 0.25:.3f}:d=0.25",
        str(FINAL_VIDEO),
    ]

    res = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    if res.returncode == 0:
        print(f"[+] Successfully generated Line 1 Video: {FINAL_VIDEO}")
        # Verify output
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=width,height,r_frame_rate,duration:format=duration,size",
            "-of", "default=noprint_wrappers=1",
            str(FINAL_VIDEO)
        ]
        probe_res = subprocess.run(probe_cmd, capture_output=True, text=True)
        print("Probe info:\n", probe_res.stdout)
        # Cleanup temp work dir
        shutil.rmtree(WORK_DIR, ignore_errors=True)
    else:
        print(f"[-] FFmpeg encoding failed:\n{res.stderr}")
        sys.exit(1)


if __name__ == "__main__":
    main()
