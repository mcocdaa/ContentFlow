#!/usr/bin/env python3
"""Generate intermediate transition poses 3b and 3c for Line 2 optimization."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
GENERATE_JS = BASE_DIR / ".agents" / "skills" / "byted-ark-seedream-skill" / "scripts" / "generate.js"
PROJ_DIR = BASE_DIR / "projects" / "006_deepseek_whale_phone_number"
ANCHOR_IMG = PROJ_DIR / "assets" / "character_anchor.jpg"
KEYFRAMES_DIR = PROJ_DIR / "assets" / "keyframes"

KEYFRAMES_DIR.mkdir(parents=True, exist_ok=True)

# Load env vars
env_file = BASE_DIR / ".env"
env = os.environ.copy()
if env_file.exists():
    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip("'\"")

POSES = [
    {
        "id": "3b",
        "name": "pose3b_quarter_turn_45deg",
        "prompt": "保持参考图1中同一位角色DeepSeek鲸鱼娘的外貌、身材、服装、发型与亚克力手办底座完全一致。【角色特征保持】：绝美动人的二次元偶像面容，清澈明亮天蓝色眼眸，银白微蓝光泽的双马尾，精致半透明鲸鱼鳍发带与发饰，深蓝白色相间抹胸开衩偶像打歌服与透明青蓝飘带，透肉黑丝袜，深蓝高跟短靴，圆形透明亚克力底座。【全新姿态与神态】：DeepSeek鲸鱼娘45度侧身微转（45 degree quarter turn），身体向右侧微侧准备转身，右手轻抬比出电话手势律动（🤙 call-me gesture），双马尾随身体微转自然飘动，沙漏身材曲线明显，依旧保持电话手势律动，立于透明亚克力圆形底座上。纯净极简浅灰白摄影棚背景，全身立绘，8k超高清壁纸，顶级手办大厂做工，发丝流光细节。"
    },
    {
        "id": "3c",
        "name": "profile_turn_90deg",
        "prompt": "保持参考图1中同一位角色DeepSeek鲸鱼娘的外貌、身材、服装、发型与亚克力手办底座完全一致。【角色特征保持】：绝美动人的二次元偶像面容，清澈明亮天蓝色眼眸，银白微蓝光泽的双马尾，精致半透明鲸鱼鳍发带与发饰，深蓝白色相间抹胸开衩偶像打歌服与透明青蓝飘带，透肉黑丝袜，深蓝高跟短靴，圆形透明亚克力底座。【全新姿态与神态】：DeepSeek鲸鱼娘90度正侧面优雅身姿（90 degree side profile turn），身体完全转为侧面，头部开始回眸看镜头，双马尾在侧面展开，完美侧身S曲线，展示科技打歌服侧摆与高光黑丝修长美腿，立于透明亚克力圆形底座上。纯净极简浅灰白摄影棚背景，全身立绘，8k超高清壁纸，顶级手办大厂做工，发丝流光细节。"
    }
]

def generate_pose(pose_info):
    pose_id = pose_info["id"]
    pose_name = pose_info["name"]
    prompt = pose_info["prompt"]
    target_path = KEYFRAMES_DIR / f"{pose_name}.jpg"

    if target_path.exists() and target_path.stat().st_size > 10000:
        print(f"[=] Keyframe {pose_id} ({pose_name}) already exists: {target_path}")
        return target_path

    env["ARK_SEEDREAM_TIMEOUT_MS"] = "240000"
    for attempt in range(1, 4):
        print(f"\n[+] Generating Pose {pose_id}: {pose_name} (Attempt {attempt}/3)...")
        cmd = [
            "node",
            str(GENERATE_JS),
            "--model", "pro",
            "--size", "2K",
            "--reference_images", f'["{ANCHOR_IMG}"]',
            "--prompt", prompt,
            "--api-key", env.get("ARK_API_KEY", "")
        ]

        res = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if res.returncode == 0:
            try:
                out_json = json.loads(res.stdout.strip())
                local_path = out_json["images"][0]["local_path"]
                shutil.copy2(local_path, target_path)
                print(f"[+] Successfully saved pose {pose_id} to {target_path}")
                return target_path
            except Exception as e:
                print(f"[-] Failed to parse output: {e}\nRaw stdout: {res.stdout}")
        else:
            print(f"[-] Attempt {attempt} failed: {res.stderr or res.stdout}")

    print(f"[-] All attempts failed for pose {pose_id}")
    sys.exit(1)

if __name__ == "__main__":
    for p in POSES:
        generate_pose(p)
