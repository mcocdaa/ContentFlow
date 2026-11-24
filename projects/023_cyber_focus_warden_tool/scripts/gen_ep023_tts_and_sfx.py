#!/usr/bin/env python3
"""Generate Episode 023 dual-voice Edge-TTS tracks + procedural UI/alarm/printer SFX + timeline manifest."""

from __future__ import annotations

import asyncio
import json
import math
import subprocess
import wave
from pathlib import Path
from typing import Any, Dict, List

import edge_tts
import numpy as np

PROJ_DIR = Path(__file__).resolve().parent.parent
AUDIO_DIR = PROJ_DIR / "assets" / "audio"
TTS_DIR = AUDIO_DIR / "tts"
SFX_DIR = AUDIO_DIR / "sfx"
SR = 48000

# 15 punchy dual-voice dialogue lines across 4 acts (Target total ~124-133s natural speech)
LINES: List[Dict[str, Any]] = [
    # ACT 1: Pain-point hook (0 - ~14.5s)
    {
        "id": "s01_hook_pain",
        "act": 1,
        "speaker": "creator",
        "voice": "zh-CN-YunxiNeural",
        "rate": "+6%",
        "pitch": "+0Hz",
        "pre_gap": 0.30,
        "text": "明明只想看五分钟学习资料，一抬头怎么已经凌晨两点？是不是一碰电脑，手就不自觉切去刷视频？",
        "subtitle": "明明只想看 5 分钟学习资料，回过神已经凌晨两点？",
    },
    {
        "id": "s02_hook_reveal",
        "act": 1,
        "speaker": "creator",
        "voice": "zh-CN-YunxiNeural",
        "rate": "+6%",
        "pitch": "+0Hz",
        "pre_gap": 0.30,
        "text": "为了治好这毛病，我连夜用纯 Python 写了个毒舌 AI 监工，切屏超过三秒，当场全屏拉警报！",
        "subtitle": "我连夜写了纯 Python 毒舌 AI 监工：切屏 3 秒全屏拉警报！",
    },
    # ACT 2: Real tech stack & code walkthrough (~14.5 - ~42s)
    {
        "id": "s03_tech_arch",
        "act": 2,
        "speaker": "creator",
        "voice": "zh-CN-YunxiNeural",
        "rate": "+6%",
        "pitch": "+0Hz",
        "pre_gap": 0.40,
        "text": "先看硬核架构：零三方依赖，纯 Python 标准库单文件启动，不开摄像头和麦克风，完全本地运行零隐私外传！",
        "subtitle": "纯 Python 标准库零依赖 · 零摄像头 · 零麦克风 · 100% 本地离线",
    },
    {
        "id": "s04_tech_detect",
        "act": 2,
        "speaker": "creator",
        "voice": "zh-CN-YunxiNeural",
        "rate": "+6%",
        "pitch": "+0Hz",
        "pre_gap": 0.35,
        "text": "抓包代码才十几行：靠浏览器原生的 visibilitychange 和 window blur 监听失焦，切屏超三秒立刻记黑账。",
        "subtitle": "原生 visibilitychange + window.blur 精准统计失焦秒数",
    },
    {
        "id": "s05_tech_roast",
        "act": 2,
        "speaker": "creator",
        "voice": "zh-CN-YunxiNeural",
        "rate": "+6%",
        "pitch": "+0Hz",
        "pre_gap": 0.35,
        "text": "后端可接你自己的大模型 Key 骂人；没配 Key 也内置了三档四十八条毒舌词库，不联网照样开箱即用！",
        "subtitle": "支持自带 API Key，未配 Key 也内置 3 档 48 条离线毒舌库",
    },
    # ACT 3: Live interactive escalation demo (~42 - ~105s)
    {
        "id": "s06_demo_start",
        "act": 3,
        "speaker": "creator",
        "voice": "zh-CN-YunxiNeural",
        "rate": "+6%",
        "pitch": "+0Hz",
        "pre_gap": 0.45,
        "text": "话不多说直接实机开测！切到十秒演示模式点开始专注，看我前五秒多么认真，两耳不闻窗外事。",
        "subtitle": "实机开测！启动 10s 演示模式，前 5 秒假装认真学习中……",
    },
    {
        "id": "s07_demo_switch1",
        "act": 3,
        "speaker": "creator",
        "voice": "zh-CN-YunxiNeural",
        "rate": "+6%",
        "pitch": "+0Hz",
        "pre_gap": 0.40,
        "text": "不行手痒了，切出去偷看一眼热榜视频，就三秒！",
        "subtitle": "手痒切屏刷视频！监工雷达开始 3、2、1 倒计时抓包……",
    },
    {
        "id": "s08_warden_lv1",
        "act": 3,
        "speaker": "warden",
        "voice": "zh-CN-YunjianNeural",
        "rate": "+3%",
        "pitch": "-4Hz",
        "pre_gap": 1.05,
        "text": "警告一级！检测到切屏去刷摸鱼网页了，快回来！浏览器失焦事件早就把你卖得一干二净！",
        "subtitle": "【监工 Lv.1】检测到切屏去刷摸鱼网页了，快回来！",
    },
    {
        "id": "s09_demo_switch2",
        "act": 3,
        "speaker": "creator",
        "voice": "zh-CN-YunxiNeural",
        "rate": "+6%",
        "pitch": "+0Hz",
        "pre_gap": 0.40,
        "text": "才一级警告，语气挺温柔嘛？那我再切出去刷八秒试试！",
        "subtitle": "嘴硬再切屏 8 秒！即将触发 Lv.2 毒舌弹幕公开处刑……",
    },
    {
        "id": "s10_warden_lv2",
        "act": 3,
        "speaker": "warden",
        "voice": "zh-CN-YunjianNeural",
        "rate": "+4%",
        "pitch": "-4Hz",
        "pre_gap": 0.80,
        "text": "二次犯案！启动二级毒舌弹幕处刑，赛博功德减一！切屏手速堪比电竞选手，干正事怎么不见你这么积极？",
        "subtitle": "【监工 Lv.2】二次犯案！顶部毒舌弹幕拷问 + 赛博功德 -1！",
    },
    {
        "id": "s11_demo_switch3",
        "act": 3,
        "speaker": "creator",
        "voice": "zh-CN-YunxiNeural",
        "rate": "+6%",
        "pitch": "+0Hz",
        "pre_gap": 0.40,
        "text": "弹幕贴脸还扣功德是吧？今天我就测测它的极限，第三次切屏走起！",
        "subtitle": "第三次顶风作案！触发最高级别 Lv.3 全屏红蓝警报！",
    },
    {
        "id": "s12_warden_lv3",
        "act": 3,
        "speaker": "warden",
        "voice": "zh-CN-YunjianNeural",
        "rate": "+4%",
        "pitch": "-4Hz",
        "pre_gap": 0.85,
        "text": "三级红蓝警报拉响！摸鱼通缉令生效！赛博功德扣至负九十九，全屏强制锁死，当场打印今日摸鱼罪证小票！",
        "subtitle": "【监工 Lv.3】摸鱼通缉令生效！强制复盘 + 打印罪证小票！",
    },
    {
        "id": "s13_demo_receipt",
        "act": 3,
        "speaker": "creator",
        "voice": "zh-CN-YunxiNeural",
        "rate": "+6%",
        "pitch": "+0Hz",
        "pre_gap": 0.65,
        "text": "我去！不仅逼我手打认错口令才能解锁，还当场打印出精确到秒的罪证小票，直接评成特级摸鱼通缉犯，谁顶得住啊！",
        "subtitle": "《今日摸鱼罪证小票》精准记录切屏次数、浪费秒数与终审判决！",
    },
    # ACT 4: Open-source launch + v2.0 community CTA (~105 - ~128s)
    {
        "id": "s14_opensource",
        "act": 4,
        "speaker": "creator",
        "voice": "zh-CN-YunxiNeural",
        "rate": "+5%",
        "pitch": "+0Hz",
        "pre_gap": 0.45,
        "text": "这套小工具百分百 MIT 开源，零联网就能本地跑！不用装依赖，终端一行 python3 app.py 直接起飞！",
        "subtitle": "100% MIT 开源零联网本地跑！一行 python3 app.py 立刻起飞",
    },
    {
        "id": "s15_outro_cta",
        "act": 4,
        "speaker": "creator",
        "voice": "zh-CN-YunxiNeural",
        "rate": "+5%",
        "pitch": "+0Hz",
        "pre_gap": 0.40,
        "text": "下一版 v2.0，你想让我给毒舌监工加什么更狠的惩罚功能？最高赞直接写进代码，下期实装给你看！",
        "subtitle": "v2.0 你想加什么更狠惩罚？评论区最高赞直接写进代码下期实装！",
    },
]


def save_wav_stereo(path: Path, stereo: np.ndarray, sr: int = SR) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(stereo, -0.98, 0.98)
    pcm = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def generate_sfx_bank() -> Dict[str, str]:
    """Synthesizes crisp, authentic mechanical UI / alarm / thermal-printer SFX at 48kHz stereo."""
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(2026023)
    paths: Dict[str, str] = {}

    t = np.linspace(0, 0.08, int(SR * 0.08), endpoint=False)
    click = (
        0.55 * np.sin(2 * math.pi * 1650 * t) * np.exp(-t * 85)
        + 0.35 * np.sin(2 * math.pi * 3200 * t) * np.exp(-t * 140)
        + 0.12 * rng.standard_normal(len(t)) * np.exp(-t * 180)
    )
    p = SFX_DIR / "ui_click.wav"
    save_wav_stereo(p, np.stack([click, click], axis=1))
    paths["ui_click"] = str(p)

    dur = 1.15
    n = int(SR * dur)
    buf = np.zeros(n, dtype=np.float64)
    for offset, freq in [(0.05, 880), (0.38, 988), (0.72, 1175)]:
        s0 = int(offset * SR)
        lt = np.linspace(0, 0.11, int(SR * 0.11), endpoint=False)
        sig = 0.50 * np.sin(2 * math.pi * freq * lt) * np.exp(-lt * 34) + 0.18 * np.sin(2 * math.pi * freq * 2 * lt) * np.exp(-lt * 55)
        buf[s0 : s0 + len(sig)] += sig
    p = SFX_DIR / "countdown_321.wav"
    save_wav_stereo(p, np.stack([buf, buf], axis=1))
    paths["countdown_321"] = str(p)

    dur = 0.55
    t = np.linspace(0, dur, int(SR * dur), endpoint=False)
    ch1 = 0.45 * np.sin(2 * math.pi * 660 * t) * np.exp(-t * 9)
    t2 = np.maximum(0.0, t - 0.16)
    ch2 = np.where(t >= 0.16, 0.45 * np.sin(2 * math.pi * 523.25 * t2) * np.exp(-t2 * 8), 0.0)
    sig = ch1 + ch2
    p = SFX_DIR / "lv1_chime.wav"
    save_wav_stereo(p, np.stack([sig, sig], axis=1))
    paths["lv1_chime"] = str(p)

    dur = 0.80
    t = np.linspace(0, dur, int(SR * dur), endpoint=False)
    beep1 = np.where((t >= 0.02) & (t < 0.18), 0.36 * np.tanh(2.2 * np.sin(2 * math.pi * 520 * t)) * np.exp(-(t - 0.02) * 10), 0.0)
    beep2 = np.where((t >= 0.22) & (t < 0.44), 0.40 * np.tanh(2.4 * np.sin(2 * math.pi * 415 * t)) * np.exp(-(t - 0.22) * 8), 0.0)
    noise = rng.standard_normal(len(t))
    kernel = np.hanning(41)
    kernel /= kernel.sum()
    smooth_n = np.convolve(noise, kernel, mode="same")
    swoosh = np.where(t >= 0.35, 0.28 * smooth_n * np.sin(math.pi * np.clip((t - 0.35) / 0.42, 0, 1)), 0.0)
    sig = beep1 + beep2 + swoosh
    p = SFX_DIR / "lv2_alert.wav"
    save_wav_stereo(p, np.stack([sig, sig], axis=1))
    paths["lv2_alert"] = str(p)

    dur = 1.25
    t = np.linspace(0, dur, int(SR * dur), endpoint=False)
    f_sweep = 480.0 + 180.0 * np.sin(2 * math.pi * 2.4 * t)
    phase = 2 * math.pi * np.cumsum(f_sweep) / SR
    siren = 0.26 * np.sin(phase) * np.exp(-t * 1.1) + 0.10 * np.sin(2 * phase) * np.exp(-t * 1.5)
    bass_drop = 0.55 * np.sin(2 * math.pi * (115 * np.exp(-t * 2.2) + 42) * t) * np.exp(-t * 3.2)
    sig = siren + bass_drop
    p = SFX_DIR / "lv3_siren.wav"
    save_wav_stereo(p, np.stack([sig, sig], axis=1))
    paths["lv3_siren"] = str(p)

    dur = 1.45
    n = int(SR * dur)
    buf = np.zeros(n, dtype=np.float64)
    for k in range(18):
        s0 = int((0.04 + k * 0.062) * SR)
        ln = int(0.030 * SR)
        if s0 + ln >= n:
            break
        lt = np.linspace(0, 0.030, ln, endpoint=False)
        ratchet = (
            0.35 * np.sin(2 * math.pi * (920 + (k % 3) * 140) * lt) * np.exp(-lt * 110)
            + 0.22 * rng.standard_normal(ln) * np.exp(-lt * 130)
        )
        buf[s0 : s0 + ln] += ratchet
    s_tear = int(1.18 * SR)
    l_tear = n - s_tear
    lt = np.linspace(0, l_tear / SR, l_tear, endpoint=False)
    tear = 0.25 * rng.standard_normal(l_tear) * np.sin(math.pi * lt / (l_tear / SR))
    buf[s_tear:] += tear
    p = SFX_DIR / "receipt_printer.wav"
    save_wav_stereo(p, np.stack([buf, buf], axis=1))
    paths["receipt_printer"] = str(p)

    dur = 0.38
    t = np.linspace(0, dur, int(SR * dur), endpoint=False)
    noise = rng.standard_normal(len(t))
    k_s = np.hanning(65)
    k_s /= k_s.sum()
    sw = np.convolve(noise, k_s, mode="same")
    env = np.sin(math.pi * t / dur) ** 1.5
    tone = 0.18 * np.sin(2 * math.pi * (240 + 480 * t / dur) * t) * env
    sig = 0.26 * sw * env + tone
    p = SFX_DIR / "whoosh.wav"
    save_wav_stereo(p, np.stack([sig, sig], axis=1))
    paths["whoosh"] = str(p)

    return paths


async def synthesize_all_tts() -> List[Dict[str, Any]]:
    TTS_DIR.mkdir(parents=True, exist_ok=True)
    results: List[Dict[str, Any]] = []
    cursor = 0.0

    for item in LINES:
        mp3_path = TTS_DIR / f"{item['id']}.mp3"
        wav_path = TTS_DIR / f"{item['id']}.wav"

        comm = edge_tts.Communicate(
            text=item["text"],
            voice=item["voice"],
            rate=item["rate"],
            pitch=item["pitch"],
        )
        await comm.save(str(mp3_path))

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(mp3_path),
                "-af",
                "silenceremove=start_periods=1:start_duration=0.02:start_threshold=-45dB,"
                "areverse,silenceremove=start_periods=1:start_duration=0.02:start_threshold=-45dB,areverse,"
                "apad=pad_dur=0.06",
                "-ar",
                str(SR),
                "-ac",
                "2",
                "-c:a",
                "pcm_s16le",
                str(wav_path),
            ],
            check=True,
        )

        with wave.open(str(wav_path), "rb") as wf:
            dur = wf.getnframes() / float(wf.getframerate())

        start_sec = round(cursor + float(item["pre_gap"]), 3)
        end_sec = round(start_sec + dur, 3)
        cursor = end_sec

        results.append(
            {
                **item,
                "wav_path": str(wav_path),
                "duration_sec": round(dur, 3),
                "start_sec": start_sec,
                "end_sec": end_sec,
            }
        )
        print(f"  [TTS] {item['id']:<18} {item['voice']:<22} {start_sec:6.2f}s -> {end_sec:6.2f}s ({dur:.2f}s)")

    return results


def fmt_srt_time(sec: float) -> str:
    ms = int(round(sec * 1000))
    hh = ms // 3600000
    mm = (ms % 3600000) // 60000
    ss = (ms % 60000) // 1000
    rem = ms % 1000
    return f"{hh:02d}:{mm:02d}:{ss:02d},{rem:03d}"


def write_srt(segments: List[Dict[str, Any]], srt_path: Path) -> None:
    srt_path.parent.mkdir(parents=True, exist_ok=True)
    blocks: List[str] = []
    for idx, seg in enumerate(segments, start=1):
        blocks.append(
            f"{idx}\n{fmt_srt_time(seg['start_sec'])} --> {fmt_srt_time(seg['end_sec'])}\n{seg['subtitle']}\n"
        )
    srt_path.write_text("\n".join(blocks), encoding="utf-8")


def main() -> None:
    sfx_paths = generate_sfx_bank()
    print(f"Generated {len(sfx_paths)} procedural SFX files.")
    segments = asyncio.run(synthesize_all_tts())
    total_dur = round(segments[-1]["end_sec"] + 1.2, 2)
    manifest = {
        "sample_rate": SR,
        "total_duration_sec": total_dur,
        "sfx": sfx_paths,
        "segments": segments,
    }
    manifest_path = AUDIO_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    srt_path = PROJ_DIR / "delivery" / "AI整活工具_毒舌AI监工防摸鱼_subtitle.srt"
    write_srt(segments, srt_path)
    print(f"\nDONE! Total episode duration = {total_dur:.2f}s | Manifest: {manifest_path} | SRT: {srt_path}")


if __name__ == "__main__":
    main()
