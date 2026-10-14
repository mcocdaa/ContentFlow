#!/usr/bin/env python3
"""
run_comfyui_animatediff.py
State-of-the-Art ComfyUI Anime Figure Vid2Vid Pipeline:
1. Base Checkpoint: Counterfeit-V2.5_fp16.safetensors
2. Character Persona: IP-Adapter Plus (character_anchor.jpg) injecting DeepSeek Whale-chan
   - High twin-tails with cyan/blue gradient
   - Luminous whale fin ribbons
   - Cyber idol corset & sheer black stockings
3. Motion Engine: AnimateDiff v3 (v3_sd15_mm.ckpt) with sliding context window (temporal consistency)
4. Kinematic Control: ControlNet OpenPose (0.90) + Soft LineArt (0.35) locking 3D dance motion
5. Denoise: 0.78 (replaces 3D base tube top with DeepSeek idol outfit while 100% preserving motion)
"""

import os
import sys
import json
import time
import shutil
import urllib.request
import urllib.parse

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_DIR = os.path.dirname(os.path.dirname(BASE_DIR))

RAW_FRAMES_DIR = os.path.join(BASE_DIR, "output", "line1_raw_frames")
COMFY_INPUT_DIR = os.path.join(BASE_DIR, "output", "comfy_input_frames")
FINAL_OUTPUT_DIR = os.path.join(BASE_DIR, "output")

COMFY_HOST = "127.0.0.1"
COMFY_PORT = 8188
COMFY_URL = f"http://{COMFY_HOST}:{COMFY_PORT}"

def prepare_input_frames(start_idx=1410, count=16):
    """Prepares continuous 3D frames into comfy_input_frames directory."""
    os.makedirs(COMFY_INPUT_DIR, exist_ok=True)
    for f in os.listdir(COMFY_INPUT_DIR):
        os.remove(os.path.join(COMFY_INPUT_DIR, f))
        
    print(f"Preparing {count} input frames (frame_{start_idx}.png to frame_{start_idx+count-1}.png)...")
    for i in range(count):
        src = os.path.join(RAW_FRAMES_DIR, f"frame_{start_idx + i}.png")
        if not os.path.exists(src):
            raise FileNotFoundError(f"Missing frame: {src}")
        dst = os.path.join(COMFY_INPUT_DIR, f"input_{i:04d}.png")
        shutil.copy2(src, dst)
    print(f"✓ {count} frames ready in {COMFY_INPUT_DIR}")
    return COMFY_INPUT_DIR

def build_workflow(input_dir, frame_count=16, denoise=0.78, seed=42):
    """Builds complete ComfyUI API prompt dictionary."""
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
                "weight": 0.85,
                "weight_type": "linear",
                "combine_embeds": "concat",
                "start_at": 0.0,
                "end_at": 1.0,
                "embeds_scaling": "V only"
            }
        },
        # 5. AnimateDiff Loader with Sliding Context
        "5": {
            "class_type": "ADE_AnimateDiffLoaderWithContext",
            "inputs": {
                "model": ["4", 0],
                "model_name": "v3_sd15_mm.ckpt",
                "beta_schedule": "sqrt_linear (AnimateDiff)",
                "motion_scale": 1.0,
                "apply_v2_models_properly": True
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
        # 8. Load 3D Video Frames
        "8": {
            "class_type": "VHS_LoadImagesPath",
            "inputs": {
                "directory": input_dir,
                "image_load_cap": frame_count,
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
                    "masterpiece, best quality, ultra-detailed anime 3D figure, DeepSeek whale girl, "
                    "silver-white and cyan gradient luminous twin tails, hair ornament whale fin ribbons, "
                    "gorgeous anime face, blue crystal eyes, joyful smile, cyber idol corset dress, "
                    "sheer 40D black stockings, patent leather dark blue boots, transparent acrylic circular figure base, "
                    "1girl, solo, dancing, clean lighting, octane render, 8k"
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
                    "lowres, ugly, ghosting, double body, bloomers"
                )
            }
        },
        # 14. Apply OpenPose (High strength to lock dancing skeleton)
        "14": {
            "class_type": "ControlNetApplyAdvanced",
            "inputs": {
                "positive": ["12", 0],
                "negative": ["13", 0],
                "control_net": ["6", 0],
                "image": ["10", 0],
                "strength": 0.90,
                "start_percent": 0.0,
                "end_percent": 0.95
            }
        },
        # 15. Apply LineArt (Gentle strength so it doesn't lock raw 3D tube top)
        "15": {
            "class_type": "ControlNetApplyAdvanced",
            "inputs": {
                "positive": ["14", 0],
                "negative": ["14", 1],
                "control_net": ["7", 0],
                "image": ["11", 0],
                "strength": 0.35,
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
        # 17. KSampler
        "17": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["5", 0],
                "positive": ["15", 0],
                "negative": ["15", 1],
                "latent_image": ["16", 0],
                "seed": seed,
                "steps": 22,
                "cfg": 7.5,
                "sampler_name": "euler_ancestral",
                "scheduler": "karras",
                "denoise": denoise
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
                "filename_prefix": "DeepSeek_Whale_IPAdapter_Line1",
                "format": "video/h264-mp4",
                "pingpong": False,
                "save_output": True
            }
        }
    }
    return workflow

def submit_prompt(workflow):
    """Submits workflow to ComfyUI prompt queue."""
    payload = json.dumps({"prompt": workflow}).encode("utf-8")
    req = urllib.request.Request(
        f"{COMFY_URL}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode("utf-8"))
    prompt_id = res["prompt_id"]
    print(f"Submitted Prompt ID: {prompt_id}")
    return prompt_id

def wait_for_completion(prompt_id, timeout=900):
    """Polls ComfyUI history until prompt completes."""
    print("Waiting for ComfyUI generation to finish...")
    t0 = time.time()
    while time.time() - t0 < timeout:
        req = urllib.request.Request(f"{COMFY_URL}/history/{prompt_id}")
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if prompt_id in data:
                status = data[prompt_id].get("status", {})
                if status.get("completed", False):
                    print(f"✓ Prompt {prompt_id} completed successfully in {time.time() - t0:.1f}s!")
                    outputs = data[prompt_id].get("outputs", {})
                    return outputs
                elif status.get("status_str") == "error":
                    messages = status.get("messages", [])
                    raise RuntimeError(f"ComfyUI execution failed: {messages}")
        except Exception as e:
            if "HTTP Error" in str(e) or "Connection refused" in str(e):
                pass
            elif "ComfyUI execution failed" in str(e):
                raise
        time.sleep(3)
        elapsed = int(time.time() - t0)
        if elapsed % 15 == 0:
            print(f"  Still running... ({elapsed}s elapsed)")
            
    raise TimeoutError(f"ComfyUI prompt {prompt_id} timed out after {timeout}s")

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=16, help="Number of frames to process")
    parser.add_argument("--start", type=int, default=1410, help="Starting 3D frame index")
    parser.add_argument("--denoise", type=float, default=0.78, help="Img2Img denoise strength")
    args = parser.parse_args()
    
    input_dir = prepare_input_frames(start_idx=args.start, count=args.count)
    workflow = build_workflow(input_dir, frame_count=args.count, denoise=args.denoise)
    
    prompt_id = submit_prompt(workflow)
    outputs = wait_for_completion(prompt_id, timeout=900)
    print("Execution outputs:", json.dumps(outputs, indent=2))

if __name__ == "__main__":
    main()
