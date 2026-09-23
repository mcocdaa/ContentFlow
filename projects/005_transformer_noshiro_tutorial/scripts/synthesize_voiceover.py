#!/usr/bin/env python3
"""Doubao Seed-TTS 2.0 Narration Synthesizer for Noshiro Transformer Tutorial.

Voice: zh_female_shuangkuaisisi_uranus_bigtts (爽快思思 - 清脆明快、技术干货主播音色)
Pacing: speed=1.02, pitch=1.02
"""

import os
import sys
import json
import subprocess
from pathlib import Path

# Add ContentFlow root to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
CONTENTFLOW_ROOT = PROJECT_ROOT.parent.parent
if str(CONTENTFLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTENTFLOW_ROOT))

from core.seed_tts import DoubaoSeedTTS

SCENES = [
    {
        "scene": 1,
        "title": "痛点引入：传统RNN的黄昏",
        "text": "指挥官，在 Transformer 诞生前，机器理解语言就像在单行道上排队。传统循环神经网络必须一个字接一个字串行处理，面对长文本不仅极度缓慢，还经常丢三落四发生长程遗忘。大模型的革命，正是从打破这个串行枷锁开始的！",
    },
    {
        "scene": 2,
        "title": "数字化基石：Token与Embedding",
        "text": "大模型眼中的世界并不是文字，而是高维几何空间。输入的第一步是将文本切分成最小语义单元 Token，再通过词嵌入矩阵，映射为几千维的稠密向量。在机器的几何宇宙里，语义相近的词会在空间中紧紧相依！",
    },
    {
        "scene": 3,
        "title": "时空暗号：位置编码",
        "text": "但自注意力机制是全对称并行的，如果打乱语序，模型根本分辨不出先后。为了让无序变有序，Transformer 引入了位置编码。无论是经典的正弦余弦波，还是现代的旋转位置编码 RoPE，都像给每个 Token 烙上了精准的时空罗盘！",
    },
    {
        "scene": 4,
        "title": "核心心脏：自注意力机制QKV",
        "text": "接下来是全架构的心脏——自注意力机制！记住这个最通俗的比喻：Query 是你的寻宝雷达，Key 是各个信息的匹配标签，Value 则是真正的内容真身。雷达和标签点积计算出相关性权重，经过 Softmax 归一化后对内容加权求和，精准萃取关键上下文！",
    },
    {
        "scene": 5,
        "title": "兼听则明：多头注意力机制",
        "text": "为什么一个注意力头远远不够？因为人类语言极其复杂！多头注意力机制就像拥有多重视角的专家团队：有的头死盯主谓宾语法骨架，有的头专注代词指代，有的头则敏锐捕捉因果与情感色彩。各司其职又融会贯通！",
    },
    {
        "scene": 6,
        "title": "稳定之锚：残差连接与LayerNorm",
        "text": "大模型动辄堆叠几十甚至上百层，为什么梯度不会消失殆尽？答案就是 Add and Norm！残差连接架起了一条绕过复杂计算的绿色高速天桥，让梯度畅通无阻反向传播；而层归一化则像安全阀一样，牢牢锁住数值稳定！",
    },
    {
        "scene": 7,
        "title": "记忆中枢：前馈神经网络FFN",
        "text": "注意力层的作用是临时在上下文中搜集线索，而真正沉淀知识的则是前馈神经网络 FFN。信息在这里经过升维非线性变换与门控激活，就像大脑皮层进行概念归纳。大模型庞大的参数记忆，大半都储存在这里！",
    },
    {
        "scene": 8,
        "title": "终极进化：现代全员Decoder-Only",
        "text": "看到这里你可能会问，原始论文的 Encoder 去哪儿了？为什么现在的 GPT 和 DeepSeek 全都是 Decoder-Only 架构？因为在因果掩码的保护下，单向自回归下一个 Token 预测被证明是泛化能力最强、扩展效率最高的终极路线！",
    },
    {
        "scene": 9,
        "title": "全景总结与彩蛋预告",
        "text": "这就是让大模型通晓人类智慧的 Transformer 全貌！你彻底搞懂它的运作逻辑了吗？下期能代带你揭秘推理加速黑科技：为什么大模型生成越长显存越吃紧？KV Cache 到底如何实现毫秒级响应！记得点赞收藏，我们下期见！",
    },
]


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
    api_key = os.environ.get("DOUBAO_TTS_API_KEY") or os.environ.get("ARK_API_KEY")
    if not api_key:
        print("[-] Error: DOUBAO_TTS_API_KEY environment variable required.", file=sys.stderr)
        sys.exit(1)

    voice_type = "zh_female_shuangkuaisisi_uranus_bigtts"
    speed_ratio = 1.02
    pitch_ratio = 1.02

    tts = DoubaoSeedTTS(api_key=api_key)
    out_dir = PROJECT_ROOT / "audio"
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    print(f"[*] Starting Doubao Seed-TTS 2.0 voiceover synthesis for {len(SCENES)} scenes...")
    print(f"    - Voice: {voice_type} (shuangkuaisisi)")
    print(f"    - Speed: {speed_ratio} | Pitch: {pitch_ratio}")

    for item in SCENES:
        idx = item["scene"]
        txt = item["text"]
        title = item["title"]
        out_file = out_dir / f"scene_{idx}.mp3"
        print(f"\n--- Scene {idx}: {title} ---")
        print(f"Text: {txt}")

        tts.synthesize(
            text=txt,
            output_file=out_file,
            voice_type=voice_type,
            speed_ratio=speed_ratio,
            pitch_ratio=pitch_ratio,
        )

        dur = get_audio_duration(out_file)
        print(f"[+] Generated: {out_file.name} ({dur:.2f}s, {out_file.stat().st_size} bytes)")

        manifest.append({
            "scene": idx,
            "title": title,
            "text": txt,
            "audio_file": str(out_file.relative_to(PROJECT_ROOT)),
            "duration": dur,
        })

    manifest_file = PROJECT_ROOT / "audio" / "manifest.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    total_dur = sum(m["duration"] for m in manifest)
    print(f"\n[+] All {len(manifest)} scenes synthesized successfully!")
    print(f"    - Total Narration Duration: {total_dur:.2f}s (~{total_dur/60:.1f} mins)")
    print(f"    - Manifest saved: {manifest_file}")


if __name__ == "__main__":
    main()
