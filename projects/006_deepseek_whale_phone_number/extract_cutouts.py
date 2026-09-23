#!/usr/bin/env python3
"""Batch extract clean transparent cutouts for all keyframes using rembg."""

import os
import sys
from pathlib import Path
from PIL import Image

# Ensure telemetry is disabled for fast execution
os.environ["ORT_DISABLE_TELEMETRY"] = "1"

import rembg

KEYFRAMES_DIR = Path("projects/006_deepseek_whale_phone_number/assets/keyframes")

def main():
    print("[*] Initializing rembg session...")
    session = rembg.new_session("u2net")
    
    jpg_files = sorted(KEYFRAMES_DIR.glob("pose*.jpg"))
    print(f"[*] Found {len(jpg_files)} keyframe JPGs to process.")

    for jpg_path in jpg_files:
        png_path = KEYFRAMES_DIR / f"{jpg_path.stem}_transparent.png"
        if png_path.exists() and png_path.stat().st_size > 100000:
            print(f"[=] Cutout already exists: {png_path.name}")
            continue

        print(f"[*] Processing {jpg_path.name} -> {png_path.name}...")
        img = Image.open(jpg_path)
        cutout = rembg.remove(img, session=session)
        cutout.save(png_path)
        print(f"[+] Successfully saved {png_path.name} ({png_path.stat().st_size} bytes)")

    print("[+] All cutouts completed successfully!")

if __name__ == "__main__":
    main()
