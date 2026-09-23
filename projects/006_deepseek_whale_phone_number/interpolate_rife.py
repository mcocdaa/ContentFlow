#!/usr/bin/env python3
"""Dense Optical Flow Interpolation using RIFE Vulkan for Line 2."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
RIFE_BIN = BASE_DIR / "vendor" / "bin" / "rife" / "rife-ncnn-vulkan"
RIFE_MODEL = BASE_DIR / "vendor" / "bin" / "rife" / "rife-v4.6"
COMPOSITE_DIR = BASE_DIR / "projects" / "006_deepseek_whale_phone_number" / "assets" / "composite_keyframes"
OUTPUT_DIR = BASE_DIR / "projects" / "006_deepseek_whale_phone_number" / "output"
INTERP_FRAMES_DIR = OUTPUT_DIR / "interpolated_frames"
AUDIO_PATH = BASE_DIR / "projects" / "006_deepseek_whale_phone_number" / "assets" / "phone_number_chorus.mp3"
FINAL_VIDEO_PATH = OUTPUT_DIR / "line2_dense_keyframes_rife.mp4"

INTERP_FRAMES_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def main():
    keyframes = sorted(COMPOSITE_DIR.glob("composite_keyframe_*.jpg"))
    if len(keyframes) < 2:
        print(f"[-] Error: Need at least 2 keyframes, found {len(keyframes)}")
        sys.exit(1)

    print(f"[*] Found {len(keyframes)} composite keyframes:")
    for k in keyframes:
        print(f"    - {k.name}")

    # Clean existing interpolated frames
    for f in INTERP_FRAMES_DIR.glob("*.png"):
        f.unlink()

    all_frame_paths = []
    global_frame_idx = 1
    frames_per_transition = 45  # 4 * 45 = ~180 frames

    temp_stage = OUTPUT_DIR / "temp_rife_stage"
    temp_stage.mkdir(parents=True, exist_ok=True)

    for i in range(len(keyframes) - 1):
        k_start = keyframes[i]
        k_end = keyframes[i + 1]

        print(f"\n[*] Interpolating segment {i+1}/{len(keyframes)-1}: {k_start.name} -> {k_end.name}...")

        seg_in = temp_stage / "in"
        seg_out = temp_stage / "out"
        shutil.rmtree(seg_in, ignore_errors=True)
        shutil.rmtree(seg_out, ignore_errors=True)
        seg_in.mkdir(parents=True, exist_ok=True)
        seg_out.mkdir(parents=True, exist_ok=True)

        shutil.copy2(k_start, seg_in / "00000001.png")
        shutil.copy2(k_end, seg_in / "00000002.png")

        cmd = [
            str(RIFE_BIN),
            "-i", str(seg_in),
            "-o", str(seg_out),
            "-m", str(RIFE_MODEL),
            "-n", str(frames_per_transition),
            "-f", "%08d.png"
        ]

        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"[-] RIFE failed: {res.stderr or res.stdout}")
            sys.exit(1)

        seg_frames = sorted(seg_out.glob("*.png"))
        print(f"[+] Generated {len(seg_frames)} intermediate frames for segment {i+1}")

        # Skip the first frame if not the first segment to prevent duplicating transition boundary
        start_idx = 0 if i == 0 else 1
        for f in seg_frames[start_idx:]:
            dest = INTERP_FRAMES_DIR / f"{global_frame_idx:08d}.png"
            shutil.copy2(f, dest)
            all_frame_paths.append(dest)
            global_frame_idx += 1

    shutil.rmtree(temp_stage, ignore_errors=True)
    total_frames = len(all_frame_paths)
    print(f"\n[+] Total interpolated frames generated: {total_frames} (Target: ~150-200 frames)")

    # Final Assembly & Muxing at 60 FPS
    print(f"\n[*] Assembling frames into 60FPS MP4 video...")
    print(f"    Audio track: {AUDIO_PATH}")
    print(f"    Output destination: {FINAL_VIDEO_PATH}")

    # FFmpeg assembly command
    # Video duration = total_frames / 60
    # Mux with audio using -shortest
    mux_cmd = [
        "ffmpeg", "-y",
        "-r", "60",
        "-pattern_type", "sequence",
        "-i", str(INTERP_FRAMES_DIR / "%08d.png"),
        "-i", str(AUDIO_PATH),
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "320k",
        "-shortest",
        str(FINAL_VIDEO_PATH)
    ]

    res = subprocess.run(mux_cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[-] FFmpeg muxing failed: {res.stderr}")
        sys.exit(1)

    print(f"[+] Video rendered successfully: {FINAL_VIDEO_PATH}")
    print(f"    File size: {FINAL_VIDEO_PATH.stat().st_size} bytes")

if __name__ == "__main__":
    main()
