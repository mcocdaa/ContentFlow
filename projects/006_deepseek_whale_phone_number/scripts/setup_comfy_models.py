#!/usr/bin/env python3
"""
Downloads essential models for ComfyUI AnimateDiff + ControlNet pipeline via ModelScope CDN:
1. Checkpoint: Counterfeit-V2.5_fp16.safetensors -> vendor/ComfyUI/models/checkpoints/
2. Motion Module: v3_sd15_mm.ckpt -> vendor/ComfyUI/models/animatediff_models/ and custom_nodes/ComfyUI-AnimateDiff-Evolved/models/
3. Lineart ControlNet: control_v11p_sd15_lineart.pth -> vendor/ComfyUI/models/controlnet/
"""

import os
import shutil
import time
from modelscope.hub.file_download import model_file_download

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_DIR = os.path.dirname(os.path.dirname(BASE_DIR))
COMFY_DIR = os.path.join(ROOT_DIR, "vendor", "ComfyUI")

CKPT_DIR = os.path.join(COMFY_DIR, "models", "checkpoints")
CONTROLNET_DIR = os.path.join(COMFY_DIR, "models", "controlnet")
ANIMATEDIFF_DIR = os.path.join(COMFY_DIR, "models", "animatediff_models")
ADE_MODELS_DIR = os.path.join(COMFY_DIR, "custom_nodes", "ComfyUI-AnimateDiff-Evolved", "models")

os.makedirs(CKPT_DIR, exist_ok=True)
os.makedirs(CONTROLNET_DIR, exist_ok=True)
os.makedirs(ANIMATEDIFF_DIR, exist_ok=True)
os.makedirs(ADE_MODELS_DIR, exist_ok=True)

DOWNLOAD_TASKS = [
    {
        "name": "Counterfeit-V2.5_fp16.safetensors (Anime Checkpoint)",
        "model_id": "AI-ModelScope/Counterfeit-V2.5",
        "file_path": "Counterfeit-V2.5_fp16.safetensors",
        "dest_dir": CKPT_DIR,
        "final_name": "Counterfeit-V2.5_fp16.safetensors",
    },
    {
        "name": "v3_sd15_mm.ckpt (AnimateDiff v3 Motion Module)",
        "model_id": "AI-ModelScope/AnimateDiff_ms",
        "file_path": "models/Motion_Module/v3_sd15_mm.ckpt",
        "dest_dir": ANIMATEDIFF_DIR,
        "final_name": "v3_sd15_mm.ckpt",
        "symlink_to": os.path.join(ADE_MODELS_DIR, "v3_sd15_mm.ckpt"),
    },
    {
        "name": "control_v11p_sd15_lineart.pth (ControlNet Lineart)",
        "model_id": "AI-ModelScope/ControlNet-v1-1",
        "file_path": "control_v11p_sd15_lineart.pth",
        "dest_dir": CONTROLNET_DIR,
        "final_name": "control_v11p_sd15_lineart.pth",
    },
]

def main():
    print("=" * 65)
    print("Downloading ComfyUI Models via High-Speed ModelScope CDN")
    print("=" * 65)
    
    t0 = time.time()
    for task in DOWNLOAD_TASKS:
        final_dest = os.path.join(task["dest_dir"], task["final_name"])
        if os.path.exists(final_dest) and os.path.getsize(final_dest) > 100000000:
            print(f"✓ Already present: {task['name']} ({os.path.getsize(final_dest)/(1024*1024):.1f} MB)")
            continue
            
        print(f"\n>>> Downloading: {task['name']}...")
        dl_path = model_file_download(
            model_id=task["model_id"],
            file_path=task["file_path"],
            local_dir=task["dest_dir"]
        )
        if dl_path != final_dest and os.path.exists(dl_path):
            shutil.move(dl_path, final_dest)
            
        if "symlink_to" in task:
            sym = task["symlink_to"]
            if not os.path.exists(sym):
                try:
                    os.symlink(final_dest, sym)
                except Exception:
                    shutil.copy2(final_dest, sym)
                    
        print(f"✓ Completed: {task['name']} -> {final_dest}")
        
    print("\n" + "=" * 65)
    print(f"All ComfyUI models ready in {time.time() - t0:.1f}s!")
    print("=" * 65)

if __name__ == "__main__":
    main()
