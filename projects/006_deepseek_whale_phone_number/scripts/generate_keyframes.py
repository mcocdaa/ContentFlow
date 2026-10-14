#!/usr/bin/env python3
"""Runner script to generate keyframes for Line 2 using generate.js."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]
GENERATE_JS = BASE_DIR / ".agents" / "skills" / "byted-ark-seedream-skill" / "scripts" / "generate.js"
ANCHOR_IMG = BASE_DIR / "projects" / "006_deepseek_whale_phone_number" / "assets" / "character_anchor.jpg"
KEYFRAMES_DIR = BASE_DIR / "projects" / "006_deepseek_whale_phone_number" / "assets" / "keyframes"

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
        "id": 1,
        "name": "pose1_call_me_sway_right",
        "prompt": "保持参考图1中同一位角色DeepSeek鲸鱼娘的外貌、身材、服装、发型与亚克力手办底座完全一致。【角色特征保持】：绝美动人的二次元偶像面容，清澈明亮天蓝色眼眸，银白微蓝光泽的双马尾，精致半透明鲸鱼鳍发带与发饰，深蓝白色相间抹胸开衩偶像打歌服与透明青蓝飘带，透肉黑丝袜，深蓝高跟短靴，圆形透明亚克力底座。【全新姿态与神态】：俏皮可爱的打电话手势（🤙 Call-me hand gesture），右手大拇指和小拇指伸出比作电话放在耳边，头微偏甜美微笑；左手自然叉腰，重心偏向右胯，性感优雅的胯部右侧摆动（hip swaying right），双腿微屈交叉立于透明亚克力手办圆形底座上。纯净极简浅灰白摄影棚背景，全身立绘，8k超高清壁纸，顶级手办大厂做工，发丝流光细节。"
    },
    {
        "id": 2,
        "name": "pose2_seductive_hip_left",
        "prompt": "保持参考图1中同一位角色DeepSeek鲸鱼娘的外貌、身材、服装、发型与亚克力手办底座完全一致。【角色特征保持】：绝美动人的二次元偶像面容，清澈明亮天蓝色眼眸，银白微蓝光泽的双马尾，精致半透明鲸鱼鳍发带与发饰，深蓝白色相间抹胸开衩偶像打歌服与透明青蓝飘带，透肉黑丝袜，深蓝高跟短靴，圆形透明亚克力底座。【全新姿态与神态】：魅惑迷人的胯部切换至左侧（seductive hip switch to the left），重心平稳转移到左腿；右手优雅地向前平摊舒展伸出（hand gracefully extended forward），掌心向上做邀请姿态；左手轻搭在左侧大腿上，眼神迷离微带笑意，双马尾随着转胯动作自然向右侧微扬飘动。纯净极简浅灰白摄影棚背景，全身立绘，8k超高清壁纸，顶级手办大厂做工，发丝流光细节。"
    },
    {
        "id": 3,
        "name": "pose3_rhythmic_double_pulse",
        "prompt": "保持参考图1中同一位角色DeepSeek鲸鱼娘的外貌、身材、服装、发型与亚克力手办底座完全一致。【角色特征保持】：绝美动人的二次元偶像面容，清澈明亮天蓝色眼眸，银白微蓝光泽的双马尾，精致半透明鲸鱼鳍发带与发饰，深蓝白色相间抹胸开衩偶像打歌服与透明青蓝飘带，透肉黑丝袜，深蓝高跟短靴，圆形透明亚克力底座。【全新姿态与神态】：胸前有节奏感的双倍脉动律动动作（rhythmic double pulse at chest level），双手握拳微曲置于胸口前方，身体略微前倾，洋溢着自信魅力的偶像笑容（confident idol smile），双马尾如波浪般对称扬起，充满跃动感与偶像元气。纯净极简浅灰白摄影棚背景，全身立绘，8k超高清壁纸，顶级手办大厂做工，发丝流光细节。"
    },
    {
        "id": 4,
        "name": "pose4_turn_back_swirling_tails",
        "prompt": "保持参考图1中同一位角色DeepSeek鲸鱼娘的外貌、身材、服装、发型与亚克力手办底座完全一致。【角色特征保持】：绝美动人的二次元偶像面容，清澈明亮天蓝色眼眸，银白微蓝光泽的双马尾，精致半透明鲸鱼鳍发带与发饰，深蓝白色相间抹胸开衩偶像打歌服与透明青蓝飘带，透肉黑丝袜，深蓝高跟短靴，圆形透明亚克力底座。【全新姿态与神态】：回眸惊艳一瞥（turn-back glance looking back over shoulder），身体背侧微转展现背部与优美沙漏身材曲线，头转回向镜头投来娇俏灵动的眼神；双马尾大幅度向外旋绕飘飞（twin-tails swirling），清晰展示发尾精致半透明的蓝色鲸鱼鳍飘带与蝴蝶结；双腿交错。纯净极简浅灰白摄影棚背景，全身立绘，8k超高清壁纸，顶级手办大厂做工，发丝流光细节。"
    },
    {
        "id": 5,
        "name": "pose5_final_wink_dynamic_idol",
        "prompt": "保持参考图1中同一位角色DeepSeek鲸鱼娘的外貌、身材、服装、发型与亚克力手办底座完全一致。【角色特征保持】：绝美动人的二次元偶像面容，清澈明亮天蓝色眼眸，银白微蓝光泽的双马尾，精致半透明鲸鱼鳍发带与发饰，深蓝白色相间抹胸开衩偶像打歌服与透明青蓝飘带，透肉黑丝袜，深蓝高跟短靴，圆形透明亚克力底座。【全新姿态与神态】：定点收尾高潮姿态，俏皮眨眼wink（call-me wink），右手放在脸颊耳侧比出标准的call-me手势（🤙），左手在身侧比心；身体形成充满张力的S型动态偶像姿势，单脚轻踮，充满舞台统治力与治愈元气。纯净极简浅灰白摄影棚背景，全身立绘，8k超高清壁纸，顶级手办大厂做工，发丝流光细节。"
    }
]

def generate_pose(pose_info):
    pose_num = pose_info["id"]
    pose_name = pose_info["name"]
    prompt = pose_info["prompt"]
    target_path = KEYFRAMES_DIR / f"{pose_name}.jpg"

    if target_path.exists() and target_path.stat().st_size > 10000:
        print(f"[=] Keyframe {pose_num} already exists: {target_path}")
        return target_path

    env["ARK_SEEDREAM_TIMEOUT_MS"] = "240000"
    for attempt in range(1, 4):
        print(f"\n[+] Generating Pose {pose_num}: {pose_name} (Attempt {attempt}/3)...")
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
                print(f"[+] Successfully saved pose {pose_num} to {target_path}")
                return target_path
            except Exception as e:
                print(f"[-] Failed to parse output: {e}")
        else:
            print(f"[-] Attempt {attempt} failed: {res.stderr or res.stdout}")
    
    print(f"[-] All attempts failed for pose {pose_num}")
    sys.exit(1)

if __name__ == "__main__":
    pose_to_run = int(sys.argv[1]) if len(sys.argv) > 1 else None
    for p in POSES:
        if pose_to_run is None or p["id"] == pose_to_run:
            generate_pose(p)
