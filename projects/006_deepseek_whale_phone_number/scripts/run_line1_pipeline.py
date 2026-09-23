#!/usr/bin/env python3
"""Full Automated Pipeline Runner for Line 1:
3D Rigging + Deep AI Anti-Clipping Polish + RIFE 60FPS Upscale.
"""

import sys
import os
import argparse
import subprocess
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
PYTHON_EXE = PROJECT_DIR.parent.parent / ".venv" / "bin" / "python"
if not PYTHON_EXE.exists():
    PYTHON_EXE = Path(sys.executable)

RAW_FRAMES_DIR = PROJECT_DIR / "output" / "line1_raw_frames"
POLISHED_FRAMES_DIR = PROJECT_DIR / "output" / "line1_polished_frames"
FINAL_VIDEO = PROJECT_DIR / "output" / "line1_3d_ai_polished.mp4"
AUDIO_FILE = PROJECT_DIR / "assets" / "phone_number_chorus.mp3"


def run_pipeline(skip_render: bool = False):
    t_start = time.time()
    print("=" * 70)
    print("🚀 Project 006: Line 1 (3D Rigging + Deep AI Anti-Clipping + 60FPS)")
    print("=" * 70)

    # Step 1: Render 3D Base Frames (if needed)
    raw_frames = list(RAW_FRAMES_DIR.glob("frame_*.png"))
    if not skip_render and len(raw_frames) < 120:
        print("\n[Stage 1/3] Rendering 3D Base Animation via Blender Cycles GPU...")
        cmd_render = [
            str(PYTHON_EXE),
            str(SCRIPT_DIR / "render_3d_base.py"),
            "--start", "1410",
            "--end", "1530",
            "--samples", "12",
        ]
        res = subprocess.run(cmd_render, check=True)
    else:
        print(f"\n[Stage 1/3] Found {len(raw_frames)} raw frames, skipping render.")

    # Step 2: AI Polish (Anti-clipping, SSS, Silky Hair Specular, Temporal Coherence)
    print("\n[Stage 2/3] Executing Deep AI Anti-Clipping & Material Luster Polishing...")
    cmd_polish = [
        str(PYTHON_EXE),
        str(SCRIPT_DIR / "ai_figure_polisher.py"),
        "--input", str(RAW_FRAMES_DIR),
        "--output", str(POLISHED_FRAMES_DIR),
    ]
    subprocess.run(cmd_polish, check=True)

    # Step 3: RIFE 60FPS Interpolation & Audio-Synced H.264 Assembly
    print("\n[Stage 3/3] Running RIFE Vulkan 60FPS Interpolation & FFmpeg Muxing...")
    cmd_assemble = [
        str(PYTHON_EXE),
        str(SCRIPT_DIR / "assemble_line1_video.py"),
        "--input", str(POLISHED_FRAMES_DIR),
        "--output", str(FINAL_VIDEO),
        "--audio", str(AUDIO_FILE),
        "--offset", "1.0",
    ]
    subprocess.run(cmd_assemble, check=True)

    total_time = time.time() - t_start
    print("\n" + "=" * 70)
    print(f"🎉 Line 1 Complete in {total_time:.1f}s!")
    print(f"Final Video: {FINAL_VIDEO}")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Run full Line 1 Pipeline")
    parser.add_argument("--skip-render", action="store_true", help="Skip 3D Blender render if frames exist")
    args = parser.parse_args()
    run_pipeline(skip_render=args.skip_render)


if __name__ == "__main__":
    main()
