#!/usr/bin/env python3
"""Precompute OpenPose poses for all 121 frames offline to completely eliminate
GPU memory spikes and prevent ComfyUI from freezing the host system.
"""

import os
import sys
import time
from PIL import Image

sys.path.append("vendor/ComfyUI/custom_nodes/comfyui_controlnet_aux/src")
from custom_controlnet_aux.open_pose import OpenposeDetector

BASE_DIR = "projects/006_deepseek_whale_phone_number"
INPUT_DIR = os.path.join(BASE_DIR, "output", "comfy_input_frames")
OUTPUT_DIR = os.path.join(BASE_DIR, "output", "precomputed_openpose")

os.makedirs(OUTPUT_DIR, exist_ok=True)

print("Loading OpenPose detector...")
t0 = time.time()
detector = OpenposeDetector.from_pretrained().to("cuda")
print(f"Loaded in {time.time() - t0:.2f}s")

files = sorted([f for f in os.listdir(INPUT_DIR) if f.endswith(".png")])
print(f"Found {len(files)} frames to process.")

t_start = time.time()
for idx, f in enumerate(files):
    in_path = os.path.join(INPUT_DIR, f)
    out_path = os.path.join(OUTPUT_DIR, f)
    
    img = Image.open(in_path).convert("RGB")
    # scale to 512x896 to match diffusion aspect ratio
    img = img.resize((512, 896), Image.Resampling.LANCZOS)
    
    # Run detector with body, hand, face enabled
    pose_img = detector(img, include_body=True, include_hand=True, include_face=True, image_resolution=512)
    pose_img.save(out_path)
    
    if (idx + 1) % 20 == 0 or (idx + 1) == len(files):
        print(f"  Processed {idx + 1}/{len(files)} frames ({time.time() - t_start:.1f}s elapsed)")

print(f"✓ All {len(files)} OpenPose frames saved to {OUTPUT_DIR} in {time.time() - t_start:.1f}s!")
