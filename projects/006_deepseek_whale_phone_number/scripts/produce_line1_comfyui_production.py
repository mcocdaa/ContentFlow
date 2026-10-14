#!/usr/bin/env python3
"""
produce_line1_comfyui_production.py
Full Production Pipeline for Line 1 using ComfyUI:
1. Prepares all 121 continuous 3D MMD dance frames (1410 to 1530).
2. Submits AnimateDiff v3 + IP-Adapter Plus + OpenPose/LineArt ControlNet workflow to ComfyUI.
3. Decodes 121 pristine, flicker-free, non-clipping DeepSeek Whale-chan dance frames.
4. Uses RIFE v4.6 Vulkan to interpolate the 121 frames to 241 frames at 60.00 FPS.
5. Muxes with Phone Number chorus audio into final line1_3d_ai_polished.mp4.
6. Re-composes the horizontal 3-pipeline comparison video.
"""

import os
import sys
import json
import time
import shutil
import subprocess
import urllib.request
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_DIR = os.path.dirname(os.path.dirname(BASE_DIR))

RAW_FRAMES_DIR = os.path.join(BASE_DIR, "output", "line1_raw_frames")
COMFY_INPUT_DIR = os.path.join(BASE_DIR, "output", "comfy_input_frames")
COMFY_OUT_DIR = os.path.join(ROOT_DIR, "vendor", "ComfyUI", "output")
FINAL_OUT_DIR = os.path.join(BASE_DIR, "output")
AUDIO_FILE = os.path.join(BASE_DIR, "assets", "phone_number_chorus.mp3")

RIFE_BIN = Path(ROOT_DIR) / "vendor" / "bin" / "rife" / "rife-ncnn-vulkan"
START_FRAME = 1410
END_FRAME = 1530
TOTAL_FRAMES = END_FRAME - START_FRAME + 1  # 121 frames

COMFY_URL = "http://127.0.0.1:8188"

def prepare_all_frames():
    os.makedirs(COMFY_INPUT_DIR, exist_ok=True)
    for f in os.listdir(COMFY_INPUT_DIR):
        os.remove(os.path.join(COMFY_INPUT_DIR, f))
        
    print(f"Preparing all {TOTAL_FRAMES} continuous 3D frames ({START_FRAME}..{END_FRAME})...")
    for i in range(TOTAL_FRAMES):
        idx = START_FRAME + i
        src = os.path.join(RAW_FRAMES_DIR, f"frame_{idx}.png")
        if not os.path.exists(src):
            raise FileNotFoundError(f"Missing frame {src}")
        dst = os.path.join(COMFY_INPUT_DIR, f"frame_{i:04d}.png")
        shutil.copy2(src, dst)
    print(f"✓ All {TOTAL_FRAMES} frames ready in {COMFY_INPUT_DIR}")
    return COMFY_INPUT_DIR

def build_production_workflow(input_dir):
    workflow = {
        # 1. Base Checkpoint Loader
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": "Counterfeit-V2.5_fp16.safetensors"
            }
        },
        # 2. IP-Adapter Unified Loader (Plus preset)
        "2": {
            "class_type": "IPAdapterUnifiedLoader",
            "inputs": {
                "model": ["1", 0],
                "preset": "PLUS (high strength)"
            }
        },
        # 3. Load Character Anchor Image (DeepSeek Whale-chan)
        "3": {
            "class_type": "LoadImage",
            "inputs": {
                "image": "character_anchor.jpg"
            }
        },
        # 4. Apply IP-Adapter
        "4": {
            "class_type": "IPAdapterAdvanced",
            "inputs": {
                "model": ["2", 0],
                "ipadapter": ["2", 1],
                "image": ["3", 0],
                "weight": 0.88,
                "weight_type": "linear",
                "combine_embeds": "concat",
                "start_at": 0.0,
                "end_at": 1.0,
                "embeds_scaling": "V only"
            }
        },
        # 50. Context Options (Sliding Window 16 frames, stride 1, overlap 4, pyramid fusion)
        "50": {
            "class_type": "ADE_StandardUniformContextOptions",
            "inputs": {
                "context_length": 16,
                "context_stride": 1,
                "context_overlap": 4,
                "fuse_method": "pyramid"
            }
        },
        # 5. AnimateDiff Loader with Context (Sliding Window for 121 frames)
        "5": {
            "class_type": "ADE_AnimateDiffLoaderWithContext",
            "inputs": {
                "model": ["4", 0],
                "model_name": "v3_sd15_mm.ckpt",
                "beta_schedule": "sqrt_linear (AnimateDiff)",
                "motion_scale": 1.0,
                "apply_v2_models_properly": True,
                "context_options": ["50", 0]
            }
        },
        # 6. ControlNet Loaders
        "6": {
            "class_type": "ControlNetLoader",
            "inputs": {
                "control_net_name": "control_v11p_sd15_openpose.pth"
            }
        },
        "7": {
            "class_type": "ControlNetLoader",
            "inputs": {
                "control_net_name": "control_v11p_sd15_lineart.pth"
            }
        },
        # 8. Load All 121 Frames
        "8": {
            "class_type": "VHS_LoadImagesPath",
            "inputs": {
                "directory": input_dir,
                "image_load_cap": TOTAL_FRAMES,
                "skip_first_images": 0,
                "select_every_nth": 1
            }
        },
        # 9. Scale Frames to 512x896 (optimal 9:16 aspect ratio)
        "9": {
            "class_type": "ImageScale",
            "inputs": {
                "image": ["8", 0],
                "upscale_method": "area",
                "width": 512,
                "height": 896,
                "crop": "disabled"
            }
        },
        # 10. OpenPose Preprocessor
        "10": {
            "class_type": "OpenposePreprocessor",
            "inputs": {
                "image": ["9", 0],
                "detect_hand": "enable",
                "detect_body": "enable",
                "detect_face": "enable",
                "resolution": 512
            }
        },
        # 11. LineArt Preprocessor
        "11": {
            "class_type": "LineArtPreprocessor",
            "inputs": {
                "image": ["9", 0],
                "coarse": "disable",
                "resolution": 512
            }
        },
        # 12. Positive Prompt
        "12": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["1", 1],
                "text": (
                    "masterpiece, best quality, (ultra-detailed anime 3D figure:1.2), DeepSeek whale girl, "
                    "(silver-white and cyan blue luminous gradient twin tails:1.2), (glowing whale fin ribbons:1.1), "
                    "gorgeous anime face, (detailed bright crystal blue eyes:1.1), joyful confident smile, "
                    "(cyber idol corset dress:1.2), high-tech gold and cyan glowing circuitry, "
                    "(sheer 40D translucent black stockings:1.1), patent leather navy blue boots, "
                    "(transparent circular acrylic figure base:1.1), reflective floor, "
                    "1girl, solo, dynamic dancing pose, (sharp focus:1.2), octane render, 8k"
                )
            }
        },
        # 13. Negative Prompt
        "13": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["1", 1],
                "text": (
                    "worst quality, low quality, bad anatomy, deformed limbs, extra legs, extra arms, "
                    "blurry, distorted face, mutated hands, multiple views, bad hands, missing fingers, "
                    "lowres, ugly, ghosting, double body, bloomers, duplicate limbs"
                )
            }
        },
        # 14. Apply OpenPose (High strength: 0.92)
        "14": {
            "class_type": "ControlNetApplyAdvanced",
            "inputs": {
                "positive": ["12", 0],
                "negative": ["13", 0],
                "control_net": ["6", 0],
                "image": ["10", 0],
                "strength": 0.92,
                "start_percent": 0.0,
                "end_percent": 0.95
            }
        },
        # 15. Apply LineArt (Gentle strength: 0.32)
        "15": {
            "class_type": "ControlNetApplyAdvanced",
            "inputs": {
                "positive": ["14", 0],
                "negative": ["14", 1],
                "control_net": ["7", 0],
                "image": ["11", 0],
                "strength": 0.32,
                "start_percent": 0.10,
                "end_percent": 0.75
            }
        },
        # 16. VAE Encode Input Frames
        "16": {
            "class_type": "VAEEncode",
            "inputs": {
                "pixels": ["9", 0],
                "vae": ["1", 2]
            }
        },
        # 17. KSampler (24 steps, cfg 8.0, denoise 0.76)
        "17": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["5", 0],
                "positive": ["15", 0],
                "negative": ["15", 1],
                "latent_image": ["16", 0],
                "seed": 2026,
                "steps": 24,
                "cfg": 8.0,
                "sampler_name": "euler_ancestral",
                "scheduler": "karras",
                "denoise": 0.76
            }
        },
        # 18. VAE Decode
        "18": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["17", 0],
                "vae": ["1", 2]
            }
        },
        # 19. Video Combine & Save MP4
        "19": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["18", 0],
                "frame_rate": 30.0,
                "loop_count": 0,
                "filename_prefix": "DeepSeek_Whale_Line1_Production",
                "format": "video/h264-mp4",
                "pingpong": False,
                "save_output": True
            }
        }
    }
    return workflow

def submit_and_wait(workflow):
    payload = json.dumps({"prompt": workflow}).encode("utf-8")
    req = urllib.request.Request(
        f"{COMFY_URL}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode("utf-8"))
    prompt_id = res["prompt_id"]
    print(f"Submitted Full Production Prompt ID: {prompt_id}")
    
    print("Waiting for AnimateDiff 121-frame generation (estimated ~4-6 minutes)...")
    t0 = time.time()
    while time.time() - t0 < 1800:
        req = urllib.request.Request(f"{COMFY_URL}/history/{prompt_id}")
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if prompt_id in data:
                status = data[prompt_id].get("status", {})
                if status.get("completed", False):
                    print(f"\n✓ ComfyUI generation completed in {time.time() - t0:.1f}s!")
                    outputs = data[prompt_id].get("outputs", {})
                    return outputs
                elif status.get("status_str") == "error":
                    raise RuntimeError(f"ComfyUI failed: {status.get('messages')}")
        except Exception as e:
            if "ComfyUI failed" in str(e):
                raise
        time.sleep(5)
        elapsed = int(time.time() - t0)
        if elapsed % 20 == 0:
            print(f"  Rendering in progress... ({elapsed}s elapsed, ~{elapsed/60:.1f} mins)")
            
    raise TimeoutError("Prompt timed out")

def main():
    print("=" * 70)
    print("Project 006: Line 1 Full Production Pipeline (ComfyUI AnimateDiff)")
    print(f"Target: 121 continuous frames ({START_FRAME}..{END_FRAME}) @ 60FPS final")
    print("=" * 70)
    
    input_dir = prepare_all_frames()
    workflow = build_production_workflow(input_dir)
    outputs = submit_and_wait(workflow)
    
    video_info = outputs.get("19", {}).get("gifs", [{}])[0]
    raw_video_path = video_info.get("fullpath")
    if not raw_video_path or not os.path.exists(raw_video_path):
        raise FileNotFoundError(f"Cannot find generated video: {raw_video_path}")
        
    print(f"\nGenerated 30FPS raw video: {raw_video_path}")
    
    # Extract frames for 60FPS RIFE upscale
    work_frames_dir = os.path.join(FINAL_OUT_DIR, "comfy_raw_121_frames")
    rife_out_dir = os.path.join(FINAL_OUT_DIR, "comfy_rife_60fps_frames")
    os.makedirs(work_frames_dir, exist_ok=True)
    os.makedirs(rife_out_dir, exist_ok=True)
    
    # Clean previous
    for d in [work_frames_dir, rife_out_dir]:
        for f in os.listdir(d):
            os.remove(os.path.join(d, f))
            
    print("\nPhase 2: Extracting 121 production frames...")
    subprocess.run([
        "ffmpeg", "-y", "-i", raw_video_path,
        "-vf", "scale=720:1280:flags=lanczos",
        os.path.join(work_frames_dir, "frame_%04d.png")
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    input_frames = sorted([f for f in os.listdir(work_frames_dir) if f.endswith(".png")])
    print("Phase 3: RIFE v4.6 Vulkan 60FPS motion interpolation...")
    subprocess.run([
        str(RIFE_BIN),
        "-m", str(RIFE_BIN.parent / "rife-v4.6"),
        "-i", work_frames_dir,
        "-o", rife_out_dir,
        "-n", str(len(input_frames) * 2)
    ], check=True)
    
    rife_frames = sorted([f for f in os.listdir(rife_out_dir) if f.endswith(".png")])
    print(f"✓ RIFE generated {len(rife_frames)} interpolated 60FPS frames!")
    
    print("\nPhase 4: Assembling Line 1 60FPS Video with Audio Mux...")
    final_line1_video = os.path.join(FINAL_OUT_DIR, "line1_3d_ai_polished.mp4")
    temp_video = os.path.join(FINAL_OUT_DIR, "line1_temp.mp4")
    
    subprocess.run([
        "ffmpeg", "-y",
        "-framerate", "60",
        "-i", os.path.join(rife_out_dir, "%08d.png"),
        "-i", AUDIO_FILE,
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "320k",
        "-shortest",
        temp_video
    ], check=True)
    shutil.move(temp_video, final_line1_video)
    print(f"✓ Line 1 Final Video Assembled: {final_line1_video}")
    
    print("\nPhase 5: Re-composing Horizontal Tri-Split Comparison Video...")
    subprocess.run([
        "python3", os.path.join(BASE_DIR, "scripts", "compose_comparison_video.py")
    ], check=True)
    
    # Clean up intermediate frames
    shutil.rmtree(work_frames_dir, ignore_errors=True)
    shutil.rmtree(rife_out_dir, ignore_errors=True)
    
    print("\n" + "=" * 70)
    print("LINE 1 PRODUCTION PIPELINE 100% COMPLETED SUCCESSFULLY!")
    print(f"Final Line 1: {final_line1_video}")
    print(f"Comparison:   {os.path.join(FINAL_OUT_DIR, 'three_pipeline_comparison_split.mp4')}")
    print("=" * 70)

if __name__ == "__main__":
    main()
