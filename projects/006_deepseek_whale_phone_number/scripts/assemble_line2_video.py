#!/usr/bin/env python3
"""Line 2 Pipeline: 2D Keyframe Optical Flow Morphing & Audio Assembly.
Takes the 5 high-consistency composite keyframes, scales them to 720x1280 (9:16),
runs RIFE v4.6 Vulkan dense optical flow morphing (60 frames per transition -> 241 frames @ 60FPS),
and muxes with phone_number_chorus.mp3 into output/line2_dense_keyframes_rife.mp4.
"""

import sys
import shutil
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from core.enhancer import MediaEnhancer

PROJ_DIR = Path(__file__).resolve().parent.parent
COMPOSITE_DIR = PROJ_DIR / "assets" / "composite_keyframes"
OUTPUT_DIR = PROJ_DIR / "output"
WORK_DIR = OUTPUT_DIR / "line2_work"
AUDIO_PATH = PROJ_DIR / "assets" / "phone_number_chorus.mp3"
FINAL_VIDEO = OUTPUT_DIR / "line2_dense_keyframes_rife.mp4"

KEYFRAME_NAMES = [
    "composite_keyframe_01.jpg",
    "composite_keyframe_02.jpg",
    "composite_keyframe_03.jpg",
    "composite_keyframe_04.jpg",
    "composite_keyframe_05.jpg",
    "composite_keyframe_06.jpg",
    "composite_keyframe_07.jpg",
]

TARGET_W = 720
TARGET_H = 1280
FRAMES_PER_TRANSITION = 41  # 6 transitions * 40 frames = 240 frames = 4.00s @ 60fps


def main():
    print("[*] Starting Line 2 Dense Optical Flow Interpolation Pipeline...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    enhancer = MediaEnhancer()
    rife_bin = enhancer.rife_path
    rife_model = rife_bin.parent / "rife-v4.6"

    # Step 1: Pre-scale keyframes to 720x1280 for sharp, artifact-free optical flow
    scaled_keyframes = []
    scaled_dir = WORK_DIR / "scaled_keyframes"
    scaled_dir.mkdir(parents=True, exist_ok=True)

    for i, name in enumerate(KEYFRAME_NAMES):
        src_path = COMPOSITE_DIR / name
        if not src_path.exists():
            raise FileNotFoundError(f"Missing keyframe: {src_path}")
        dst_path = scaled_dir / f"kf_{i+1:02d}.png"
        subprocess.run([
            "ffmpeg", "-y", "-i", str(src_path),
            "-vf", f"scale={TARGET_W}:{TARGET_H}:flags=lanczos",
            str(dst_path)
        ], check=True, capture_output=True)
        scaled_keyframes.append(dst_path)
        print(f"  [+] Prepared scaled keyframe {i+1}: {dst_path}")

    # Step 2: Dense multi-stage optical flow interpolation between each consecutive pair
    interpolated_frames_dir = WORK_DIR / "interpolated_sequence"
    interpolated_frames_dir.mkdir(parents=True, exist_ok=True)

    global_frame_idx = 1

    for seg_idx in range(len(scaled_keyframes) - 1):
        k_start = scaled_keyframes[seg_idx]
        k_end = scaled_keyframes[seg_idx + 1]

        seg_in = WORK_DIR / f"seg_{seg_idx}_in"
        seg_out = WORK_DIR / f"seg_{seg_idx}_out"
        seg_in.mkdir(parents=True, exist_ok=True)
        seg_out.mkdir(parents=True, exist_ok=True)

        shutil.copy2(k_start, seg_in / "00000001.png")
        shutil.copy2(k_end, seg_in / "00000002.png")

        print(f"[*] Interpolating Transition {seg_idx+1}/{len(scaled_keyframes)-1} with {FRAMES_PER_TRANSITION} frames...")
        # Use rife-ncnn-vulkan -n <num_frames>
        cmd = [
            str(rife_bin),
            "-i", str(seg_in),
            "-o", str(seg_out),
            "-m", str(rife_model),
            "-n", str(FRAMES_PER_TRANSITION),
            "-f", "%08d.png",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"[-] RIFE error on segment {seg_idx}:\n{res.stderr}")
            sys.exit(1)

        # Collect segment frames
        seg_frames = sorted(seg_out.glob("*.png"))
        print(f"  [+] Segment {seg_idx+1} produced {len(seg_frames)} frames.")

        # Each transition contributes 40 frames for exactly 240 frames = 4.00s @ 60FPS
        slice_end = len(seg_frames) - 1
        for f in seg_frames[:slice_end]:
            dst = interpolated_frames_dir / f"{global_frame_idx:08d}.png"
            shutil.copy2(f, dst)
            global_frame_idx += 1

    total_frames = global_frame_idx - 1
    duration = total_frames / 60.0
    print(f"[+] Total interpolated continuous sequence: {total_frames} frames ({duration:.2f}s @ 60FPS)")

    # Step 3: FFmpeg Encode to H.264 High Profile and mux with audio
    print("[*] Assembling final video with audio sync...")
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-framerate", "60",
        "-i", str(interpolated_frames_dir / "%08d.png"),
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
        print(f"[+] Successfully generated Line 2 Video: {FINAL_VIDEO}")
        # Cleanup temp work dir to save disk
        shutil.rmtree(WORK_DIR, ignore_errors=True)
    else:
        print(f"[-] FFmpeg encoding failed:\n{res.stderr}")
        sys.exit(1)


if __name__ == "__main__":
    main()
