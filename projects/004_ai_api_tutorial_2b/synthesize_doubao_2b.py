#!/usr/bin/env python3
"""Doubao Seed-TTS 2.0 Voiceover Synthesizer for 2B Tutorial Project.

Synthesizes high-fidelity 2B anime character voice for:
projects/ai_api_tutorial_2b/ (大模型 API 核心三要素)

Features:
- Character-specific emotion tags ([冷静地], [严肃地], [知性地], [微笑着])
- Tailored speed (0.95) and pitch (0.92) to match 2B's android persona
- Direct MP3 synthesis via ByteDance OpenSpeech V3 API (seed-tts-2.0)
- Optional seamless video audio track re-muxing via FFmpeg
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path

# Add project root to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
CONTENTFLOW_ROOT = SCRIPT_DIR.parent.parent
if str(CONTENTFLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTENTFLOW_ROOT))

from core.seed_tts import DoubaoSeedTTS, DEFAULT_TTS_BASE_URL, DEFAULT_RESOURCE_ID

# 2B Spoken Dialogue for 6 Scenes (Pure natural spoken script - NO bracket tags)
SCENE_SCRIPTS = [
    {
        "scene": 1,
        "title": "痛点引出",
        "text": "为什么你的 AI 客户端总是连接失败报 401 或者 404？别慌，不是大模型变笨了，而是你的三大通信参数配错啦！",
    },
    {
        "scene": 2,
        "title": "Base URL",
        "text": "第一把钥匙是 Base URL，也就是通信基地址。它决定请求飞向哪台服务器。大部分兼容客户端都必须加上斜杠 v1 路径哦！",
    },
    {
        "scene": 3,
        "title": "API Key",
        "text": "第二把钥匙是 API Key，也就是安全护照。它以 Bearer Token 格式鉴权。千万别写死在代码里提交开源，小心额度被盗刷！",
    },
    {
        "scene": 4,
        "title": "Model Name",
        "text": "第三把钥匙是 Model Name，也就是模型代号。比如 deepseek-reasoner 或 gpt-4o。必须严格匹配官方代号，错一个字母都会报错！",
    },
    {
        "scene": 5,
        "title": "排查手册",
        "text": "排查手册拿好：401 查 Key 和余额；404 查基地址路径和模型名；429 是并发或频率超限。按图索骥三秒搞定排障！",
    },
    {
        "scene": 6,
        "title": "收尾点赞",
        "text": "参数全部配齐，点击测试看到 200 OK 绿灯全亮！恭喜你彻底打通大模型通信！觉得有用记得点赞收藏，下期带你解锁进阶玩法！",
    },
]


def build_full_script() -> str:
    """Builds clean, natural narration script without any tag artifacts."""
    return " ".join(item["text"] for item in SCENE_SCRIPTS)


def get_audio_duration(audio_file: Path) -> float:
    """Gets audio duration in seconds via ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_file)
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        return float(res.stdout.strip())
    except Exception:
        return 0.0


def remux_video_with_audio(video_file: Path, audio_file: Path, output_file: Path) -> Path:
    """Re-mux existing video with newly synthesized Doubao voiceover, matching exact duration."""
    duration = get_audio_duration(audio_file)
    print(f"[*] Re-muxing video with new Doubao 2B audio...")
    print(f"    - Input Video: {video_file}")
    print(f"    - New Audio:   {audio_file} ({duration:.2f}s)")
    print(f"    - Output:      {output_file}")

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_file),
        "-i", str(audio_file),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
    ]
    if duration > 0:
        cmd.extend(["-t", f"{duration:.3f}"])

    cmd.append(str(output_file))
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        print(f"[-] FFmpeg re-mux failed:\n{res.stderr[-500:]}", file=sys.stderr)
        raise RuntimeError("Video re-mux failed")
    print(f"[+] Video re-muxed successfully: {output_file} (duration: {duration:.2f}s)")
    return output_file


def main():
    parser = argparse.ArgumentParser(
        description="Synthesize 2B voiceover with Doubao Seed-TTS 2.0"
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Volcengine API Key (defaults to DOUBAO_TTS_API_KEY env)",
    )
    parser.add_argument(
        "--voice",
        default="zh_female_xiaohe_uranus_bigtts",
        help="Voice model ID (e.g. zh_female_xiaohe_uranus_bigtts / zh_female_vv_uranus_bigtts)",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=0.95,
        help="Speech rate ratio (0.5 - 2.0, default 0.95 for calm 2B cadence)",
    )
    parser.add_argument(
        "--pitch",
        type=float,
        default=0.92,
        help="Speech pitch ratio (0.5 - 2.0, default 0.92 for android resonance)",
    )
    parser.add_argument(
        "--remux",
        action="store_true",
        default=True,
        help="Automatically re-mux into final MP4 video",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview clean script and API config without sending request",
    )

    args = parser.parse_args()

    full_script = build_full_script()
    out_dir = CONTENTFLOW_ROOT / "output" / "ai_api_tutorial_2b" / "video"
    out_dir.mkdir(parents=True, exist_ok=True)
    audio_out = out_dir / "2B小姐姐教你大模型API核心三要素_doubao_2b.mp3"
    existing_video = out_dir / "2B小姐姐教你大模型API核心三要素_final.mp4"
    remuxed_video = out_dir / "2B小姐姐教你大模型API核心三要素_doubao_final.mp4"

    print("=" * 70)
    print(" 🤖 2B Anime Voiceover Generator (Doubao Seed-TTS 2.0)")
    print("=" * 70)
    print(f"[*] Base URL:       {DEFAULT_TTS_BASE_URL}")
    print(f"[*] Resource ID:    {DEFAULT_RESOURCE_ID}")
    print(f"[*] Voice ID:       {args.voice} (知性/清冷)")
    print(f"[*] Acoustic Tune:  Speed={args.speed}x | Pitch={args.pitch}x")
    print(f"[*] Output Audio:   {audio_out}")
    print("-" * 70)
    print("[*] Clean Dialogue Script (6 Scenes):")
    for sc in SCENE_SCRIPTS:
        print(f"    - Scene {sc['scene']} ({sc['title']}): {sc['text']}")
    print("-" * 70)

    if args.dry_run:
        print("[!] Dry-run complete. Set DOUBAO_TTS_API_KEY and run without --dry-run to synthesize.")
        return 0

    api_key = args.api_key or os.environ.get("DOUBAO_TTS_API_KEY") or os.environ.get("ARK_API_KEY")
    if not api_key:
        print("[-] Error: Doubao TTS API Key not found!", file=sys.stderr)
        print("    Please set the environment variable:", file=sys.stderr)
        print("      export DOUBAO_TTS_API_KEY=\"your-volcengine-api-key\"", file=sys.stderr)
        print("    Or pass via command line:", file=sys.stderr)
        print("      python3 synthesize_doubao_2b.py --api-key \"your-key\"", file=sys.stderr)
        print("    Or run with --dry-run to preview.", file=sys.stderr)
        return 1

    client = DoubaoSeedTTS(
        api_key=api_key,
        base_url=DEFAULT_TTS_BASE_URL,
        resource_id=DEFAULT_RESOURCE_ID,
    )

    print("[*] Contacting ByteDance OpenSpeech V3...")
    try:
        saved_audio = client.synthesize(
            text=full_script,
            output_file=audio_out,
            voice_type=args.voice,
            speed_ratio=args.speed,
            pitch_ratio=args.pitch,
        )
        print(f"[+] Audio successfully synthesized: {saved_audio} ({saved_audio.stat().st_size} bytes)")
    except Exception as e:
        print(f"[-] Synthesis failed: {e}", file=sys.stderr)
        return 1

    if args.remux and existing_video.exists():
        remux_video_with_audio(existing_video, saved_audio, remuxed_video)
        print(f"[+] Complete 2B Doubao Video Ready: {remuxed_video}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
