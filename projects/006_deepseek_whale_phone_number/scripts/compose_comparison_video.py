#!/usr/bin/env python3
"""Tri-Pipeline Comparison Video Compositor.
Merges Line 1 (3D + AI Polish), Line 2 (2D Keyframe + RIFE), and Line 3 (Seedance + AI Enhance)
into a unified 3-way split comparison video with professional cyber HUD labels.
"""

import sys
import subprocess
from pathlib import Path

PROJ_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJ_DIR / "output"
ASSETS_DIR = PROJ_DIR / "assets"

LINE1_VIDEO = OUTPUT_DIR / "line1_3d_ai_polished.mp4"
LINE2_VIDEO = OUTPUT_DIR / "line2_dense_keyframes_rife.mp4"
LINE3_VIDEO = OUTPUT_DIR / "line3_seedance_api_enhanced.mp4"
AUDIO_PATH = ASSETS_DIR / "phone_number_chorus.mp3"

FINAL_SPLIT = OUTPUT_DIR / "three_pipeline_comparison_split.mp4"


def check_inputs():
    missing = []
    for name, p in [("Line 1", LINE1_VIDEO), ("Line 2", LINE2_VIDEO), ("Line 3", LINE3_VIDEO)]:
        if not p.exists():
            missing.append(f"{name}: {p}")
    return missing


def build_horizontal_trisplit():
    """Combines three 9:16 videos side-by-side into a single 1920x1080 video with labels."""
    print("[*] Generating horizontal tri-split comparison video (1920x1080)...")
    
    # Each input scaled to 640x1080 (maintaining 9:16 approx)
    # Total width: 640 * 3 = 1920, height: 1080
    filter_complex = (
        "[0:v]scale=640:1080:force_original_aspect_ratio=decrease,pad=640:1080:(ow-iw)/2:(oh-ih)/2:color=black,"
        "drawbox=y=0:color=black@0.7:width=iw:height=76:t=fill,"
        "drawtext=fontfile='/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc':text='路线一：3D骨骼+AI神经重绘(去穿模)':fontcolor=white:fontsize=28:x=(w-text_w)/2:y=22[v0];"
        
        "[1:v]scale=640:1080:force_original_aspect_ratio=decrease,pad=640:1080:(ow-iw)/2:(oh-ih)/2:color=black,"
        "drawbox=y=0:color=black@0.7:width=iw:height=76:t=fill,"
        "drawtext=fontfile='/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc':text='路线二：2D连贯生图+密集光流':fontcolor=0x00FFFF:fontsize=28:x=(w-text_w)/2:y=22[v1];"
        
        "[2:v]scale=640:1080:force_original_aspect_ratio=decrease,pad=640:1080:(ow-iw)/2:(oh-ih)/2:color=black,"
        "drawbox=y=0:color=black@0.7:width=iw:height=76:t=fill,"
        "drawtext=fontfile='/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc':text='路线三：Seedance大模型+AI超分':fontcolor=0xFFD700:fontsize=28:x=(w-text_w)/2:y=22[v2];"
        
        "[v0][v1][v2]hstack=inputs=3[outv]"
    )
    
    cmd = [
        "ffmpeg", "-y",
        "-i", str(LINE1_VIDEO),
        "-i", str(LINE2_VIDEO),
        "-i", str(LINE3_VIDEO),
        "-i", str(AUDIO_PATH),
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-map", "3:a",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(FINAL_SPLIT)
    ]
    
    print("[*] Running command:", " ".join(cmd))
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        print(f"[+] Successfully generated tri-split comparison video at: {FINAL_SPLIT}")
    else:
        print(f"[-] FFmpeg error:\n{res.stderr}")


if __name__ == "__main__":
    missing = check_inputs()
    if missing:
        print("[!] Cannot composite comparison video yet. Missing:")
        for m in missing:
            print("   -", m)
        sys.exit(1)
    build_horizontal_trisplit()
