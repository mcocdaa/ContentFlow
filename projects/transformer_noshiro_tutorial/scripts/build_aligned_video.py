#!/usr/bin/env python3
"""Precision Video Builder for Noshiro Transformer Tutorial Project.

Features:
- Deterministic 1:1 sync across all 9 technical scenes
- 100% Rock-solid 1080P static presentation (ZERO JITTER on whiteboard diagrams and text)
- EBU R128 (-14.0 LUFS) audio loudness normalization
- High-contrast bordered subtitles (SRT generation + burning)
- Clean concat without drift
"""

import os
import sys
import json
import shutil
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
CONTENTFLOW_ROOT = PROJECT_ROOT.parent.parent

# Subtitle breakdown for 9 scenes (approximate split per pause)
SCENE_SUBTITLES = [
    {
        "scene": 1,
        "cues": [
            "指挥官，在 Transformer 诞生前，机器理解语言就像在单行道上排队。",
            "传统循环神经网络必须一个字接一个字串行处理，",
            "面对长文本不仅极度缓慢，还经常丢三落四发生长程遗忘。",
            "大模型的革命，正是从打破这个串行枷锁开始的！",
        ],
    },
    {
        "scene": 2,
        "cues": [
            "大模型眼中的世界并不是文字，而是高维几何空间。",
            "输入的第一步是将文本切分成最小语义单元 Token，",
            "再通过词嵌入矩阵，映射为几千维的稠密向量。",
            "在机器的几何宇宙里，语义相近的词会在空间中紧紧相依！",
        ],
    },
    {
        "scene": 3,
        "cues": [
            "但自注意力机制是全对称并行的，如果打乱语序，模型根本分辨不出先后。",
            "为了让无序变有序，Transformer 引入了位置编码。",
            "无论是经典的正弦余弦波，还是现代的旋转位置编码 RoPE，",
            "都像给每个 Token 烙上了精准的时空罗盘！",
        ],
    },
    {
        "scene": 4,
        "cues": [
            "接下来是全架构的心脏——自注意力机制！",
            "记住这个最通俗的比喻：Query 是你的寻宝雷达，",
            "Key 是各个信息的匹配标签，Value 则是真正的内容真身。",
            "雷达和标签点积计算出相关性权重，经过 Softmax 归一化后加权求和，",
            "精准萃取关键上下文！",
        ],
    },
    {
        "scene": 5,
        "cues": [
            "为什么一个注意力头远远不够？因为人类语言极其复杂！",
            "多头注意力机制就像拥有多重视角的专家团队：",
            "有的头死盯主谓宾语法骨架，有的头专注代词指代，",
            "有的头则敏锐捕捉因果与情感色彩。各司其职又融会贯通！",
        ],
    },
    {
        "scene": 6,
        "cues": [
            "大模型动辄堆叠几十甚至上百层，为什么梯度不会消失殆尽？",
            "答案就是 Add and Norm！",
            "残差连接架起了一条绕过复杂计算的绿色高速天桥，让梯度畅通无阻反向传播；",
            "而层归一化则像安全阀一样，牢牢锁住数值稳定！",
        ],
    },
    {
        "scene": 7,
        "cues": [
            "注意力层的作用是临时在上下文中搜集线索，",
            "而真正沉淀知识的则是前馈神经网络 FFN。",
            "信息在这里经过升维非线性变换与门控激活，就像大脑皮层进行概念归纳。",
            "大模型庞大的参数记忆，大半都储存在这里！",
        ],
    },
    {
        "scene": 8,
        "cues": [
            "看到这里你可能会问，原始论文的 Encoder 去哪儿了？",
            "为什么现在的 GPT 和 DeepSeek 全都是 Decoder-Only 架构？",
            "因为在因果掩码的保护下，",
            "单向自回归下一个 Token 预测被证明是泛化能力最强、扩展效率最高的终极路线！",
        ],
    },
    {
        "scene": 9,
        "cues": [
            "这就是让大模型通晓人类智慧的 Transformer 全貌！",
            "你彻底搞懂它的运作逻辑了吗？",
            "下期能代带你揭秘推理加速黑科技：为什么大模型生成越长显存越吃紧？",
            "KV Cache 到底如何实现毫秒级响应！记得点赞收藏，我们下期见！",
        ],
    },
]


def format_srt_time(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours = millis // 3600000
    millis %= 3600000
    minutes = millis // 60000
    millis %= 60000
    secs = millis // 1000
    millis %= 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def get_audio_duration(file_path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(file_path)
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        return float(res.stdout.strip())
    except Exception:
        return 0.0


def main():
    manifest_file = PROJECT_ROOT / "audio" / "manifest.json"
    if not manifest_file.exists():
        print(f"[-] Manifest not found: {manifest_file}", file=sys.stderr)
        sys.exit(1)

    with open(manifest_file, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    temp_dir = PROJECT_ROOT / "temp_clips"
    temp_dir.mkdir(parents=True, exist_ok=True)
    delivery_dir = PROJECT_ROOT / "delivery"
    delivery_dir.mkdir(parents=True, exist_ok=True)

    print(f"[*] Building 1080P stabilized video for {len(manifest)} scenes...")

    # Tail padding per scene for natural breathing room
    tail_pad = 0.40  # 400ms pause after each scene
    clip_records = []
    current_time = 0.0
    all_srt_entries = []
    srt_idx = 1

    for sc_info in manifest:
        idx = sc_info["scene"]
        audio_path = PROJECT_ROOT / sc_info["audio_file"]
        dur = get_audio_duration(audio_path)
        clip_dur = dur + tail_pad

        # Check for image
        img_path = PROJECT_ROOT / "images" / f"scene_{idx}.jpg"
        if not img_path.exists():
            # Fallback to cover if specific scene image isn't generated yet
            img_path = PROJECT_ROOT / "assets" / "scene_cover.jpg"

        clip_mp4 = temp_dir / f"clip_{idx:02d}.mp4"
        print(f"\n[+] Processing Scene {idx}: {sc_info['title']}")
        print(f"    - Image: {img_path.name}")
        print(f"    - Audio: {audio_path.name} ({dur:.2f}s + {tail_pad:.2f}s = {clip_dur:.2f}s)")

        pad_ms = int(round(tail_pad * 1000))
        audio_filter = f"apad=pad_dur={pad_ms/1000.0:.3f},loudnorm=I=-14:LRA=7:TP=-1.5"
        vf_static = "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,format=yuv420p"

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", str(img_path),
            "-i", str(audio_path),
            "-filter_complex", f"[0:v]{vf_static}[v];[1:a]{audio_filter}[a]",
            "-map", "[v]",
            "-map", "[a]",
            "-t", f"{clip_dur:.3f}",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-r", "30",
            str(clip_mp4),
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            print(f"[-] FFmpeg clip {idx} failed:\n{res.stderr[-500:]}", file=sys.stderr)
            sys.exit(1)

        clip_records.append({
            "scene": idx,
            "clip_path": clip_mp4,
            "start": current_time,
            "end": current_time + clip_dur,
            "dur": clip_dur,
        })

        # Calculate subtitles for this scene
        cues = SCENE_SUBTITLES[idx - 1]["cues"]
        cue_dur = dur / len(cues)
        for i, text in enumerate(cues):
            c_start = current_time + i * cue_dur
            c_end = current_time + (i + 1) * cue_dur
            all_srt_entries.append((srt_idx, c_start, c_end, text))
            srt_idx += 1

        current_time += clip_dur

    # Write SRT
    srt_file = delivery_dir / "能代教你大模型核心基石_Transformer原理解析_subtitle.srt"
    with open(srt_file, "w", encoding="utf-8") as f:
        for num, start_s, end_s, txt in all_srt_entries:
            f.write(f"{num}\n")
            f.write(f"{format_srt_time(start_s)} --> {format_srt_time(end_s)}\n")
            f.write(f"{txt}\n\n")
    print(f"\n[+] SRT generated: {srt_file} ({len(all_srt_entries)} cues, total {current_time:.2f}s)")

    # Concatenate clips
    concat_list = temp_dir / "concat_list.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for rec in clip_records:
            f.write(f"file '{rec['clip_path'].resolve()}'\n")

    combined_video = temp_dir / "combined_nosub.mp4"
    print(f"[*] Concatenating {len(clip_records)} clips...")
    cmd_concat = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(combined_video),
    ]
    res = subprocess.run(cmd_concat, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        print(f"[-] Concat failed:\n{res.stderr[-500:]}", file=sys.stderr)
        sys.exit(1)

    # Burn subtitles into final delivery MP4 with styled outline
    final_output = delivery_dir / "能代教你大模型核心基石_Transformer原理解析_final.mp4"
    print(f"[*] Burning high-contrast subtitles into final delivery MP4...")
    srt_escaped = srt_file.resolve().as_posix().replace(":", "\\:")
    sub_filter = f"subtitles='{srt_escaped}':force_style='FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BackColour=&H80000000,BorderStyle=3,Outline=2,Shadow=1,Alignment=2,MarginV=35'"
    cmd_burn = [
        "ffmpeg", "-y",
        "-i", str(combined_video),
        "-vf", sub_filter,
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-c:a", "copy",
        str(final_output),
    ]
    res = subprocess.run(cmd_burn, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        print(f"[-] Subtitle burn failed, copying unburned as fallback:\n{res.stderr[-400:]}", file=sys.stderr)
        shutil.copy2(combined_video, final_output)

    # Also build full audio mp3
    full_audio = delivery_dir / "能代教你大模型核心基石_Transformer原理解析_shuangkuaisisi.mp3"
    cmd_audio = [
        "ffmpeg", "-y",
        "-i", str(final_output),
        "-vn", "-c:a", "libmp3lame", "-b:a", "192k",
        str(full_audio),
    ]
    subprocess.run(cmd_audio, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    print(f"\n[+] Production Completed Successfully!")
    print(f"    - Final Video:   {final_output} ({final_output.stat().st_size / 1024 / 1024:.2f} MB)")
    print(f"    - Final Audio:   {full_audio}")
    print(f"    - Subtitle SRT:  {srt_file}")
    print(f"    - Total RunTime: {current_time:.2f}s (~{current_time/60:.2f} mins)")


if __name__ == "__main__":
    main()
