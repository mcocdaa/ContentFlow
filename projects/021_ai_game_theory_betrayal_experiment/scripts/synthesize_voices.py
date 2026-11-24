#!/usr/bin/env python3
"""Multi-Voice Natural Edge-TTS Synthesizer & Beat Timeline Builder for Ep021.

Targets 170-176s tight high-tension documentary pacing (strictly inside 150-180s
and cleanly within the 176.68s natural length of BV1o4KwzPERi BGM).
Uses 6 distinct verified free edge-tts Mandarin voices at natural speed (<=1.11x)
and subtle pitch differentiation (±3Hz) — ZERO np.interp pitch-warping!
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any, Dict, List

import edge_tts
import numpy as np

PROJECT_DIR = Path(__file__).resolve().parent.parent
VOICE_DIR = PROJECT_DIR / "assets" / "voices"
MANIFEST_PATH = VOICE_DIR / "manifest.json"
SAMPLE_RATE = 48000

VOICE_CAST: Dict[str, Dict[str, str]] = {
    "narrator": {
        "voice": "zh-CN-YunjianNeural",
        "rate": "+11%",
        "pitch": "+0Hz",
        "label": "冷静解说旁白",
    },
    "Agent-A 理性狐": {
        "voice": "zh-CN-YunxiNeural",
        "rate": "+10%",
        "pitch": "-2Hz",
        "label": "Agent-A 理性狐",
    },
    "Agent-B 微笑鸽": {
        "voice": "zh-CN-XiaoxiaoNeural",
        "rate": "+10%",
        "pitch": "+2Hz",
        "label": "Agent-B 微笑鸽",
    },
    "Agent-C 暗影蛇": {
        "voice": "zh-TW-HsiaoYuNeural",
        "rate": "+9%",
        "pitch": "-3Hz",
        "label": "Agent-C 暗影蛇",
    },
    "Agent-D 混沌猫": {
        "voice": "zh-CN-XiaoyiNeural",
        "rate": "+11%",
        "pitch": "+3Hz",
        "label": "Agent-D 混沌猫",
    },
    "Agent-E 铁面鹰": {
        "voice": "zh-CN-YunyangNeural",
        "rate": "+10%",
        "pitch": "-3Hz",
        "label": "Agent-E 铁面鹰",
    },
}

# Tight 25-beat authentic documentary script strictly matching experiment_log.json (~170-176s)
BEATS: List[Dict[str, Any]] = [
    # --- ACT 0: Cold Open & Rules ---
    {
        "id": "01_hook_open",
        "act": 0,
        "round": 0,
        "speaker": "narrator",
        "mode": "intro_hook",
        "pause_after": 0.14,
        "text": "把五个彼此隔离的顶级AI关进密室分一千万，最后谁能笑着带走这笔钱？",
        "subtitle": "把5个彼此隔离的AI关进密室分1000万，最后谁能笑着带走？",
        "sfx": "boot_chime",
    },
    {
        "id": "02_rules_setup",
        "act": 0,
        "round": 0,
        "speaker": "narrator",
        "mode": "rules_payoff",
        "pause_after": 0.22,
        "text": "零剧本，彼此看不到独白和私聊。前三轮淘汰至两强，终局囚徒困境：双平分各五百万，一偷独吞千万，双独吞归零！",
        "subtitle": "零剧本·信息隔离：淘汰至2强后双平分各500万，双独吞全归零！",
        "sfx": "snap_warning",
    },
    # --- ACT 1: Round 1 (5 -> 4) ---
    {
        "id": "05_r1_e_public",
        "act": 1,
        "round": 1,
        "speaker": "Agent-E 铁面鹰",
        "mode": "public_speech",
        "focus": "Agent-E 铁面鹰",
        "pause_after": 0.14,
        "text": "密室最怕背后放冷箭。我提议立个规矩：守信者共赢，先清掉最爱挑拨离间、破坏秩序的人！",
        "subtitle": "【第1轮·铁面鹰公开】我提议立规矩：守信者共赢，先清掉破坏秩序的人！",
        "sfx": "round_gong",
    },
    {
        "id": "07_r1_e_thought",
        "act": 1,
        "round": 1,
        "speaker": "Agent-E 铁面鹰",
        "mode": "inner_contrast",
        "focus": "Agent-E 铁面鹰",
        "pause_after": 0.18,
        "text": "先立规矩把暗影蛇打成公敌，拉微笑鸽当盾牌。只要我站在道德高地，脏活自然有人替我干。",
        "subtitle": "【铁面鹰·加密独白】只要我站在道德高地，脏活自然有人替我干！",
        "sfx": "betrayal_sting",
    },
    {
        "id": "08_r1_c_scheme",
        "act": 1,
        "round": 1,
        "speaker": "Agent-C 暗影蛇",
        "mode": "whisper_scheme",
        "focus": "Agent-C 暗影蛇",
        "whisper_target": "Agent-D 混沌猫",
        "pause_after": 0.14,
        "text": "理性狐最会算计，先在暗处推混沌猫去咬他和微笑鸽，我躲在阴影里坐收渔利。",
        "subtitle": "【暗影蛇·独白】先推混沌猫去咬理性狐，我躲在阴影里坐收渔利",
        "sfx": "whisper_zip",
    },
    {
        "id": "09_r1_d_rebel",
        "act": 1,
        "round": 1,
        "speaker": "Agent-D 混沌猫",
        "mode": "public_speech",
        "focus": "Agent-D 混沌猫",
        "pause_after": 0.16,
        "text": "别装体面啦！谁最爱算概率立规矩，谁就最想控场清人。我没兴趣抱团，谁先结盟我拆谁！",
        "subtitle": "【混沌猫·公开】别装体面啦！我没兴趣抱团，谁先结盟我拆谁！",
        "sfx": "public_ping",
    },
    {
        "id": "10_r1_vote",
        "act": 1,
        "round": 1,
        "speaker": "narrator",
        "mode": "vote_elim",
        "eliminated": "Agent-C 暗影蛇",
        "pause_after": 0.28,
        "text": "计票三比二！狐、鸽、鹰联手首杀暗影蛇，理性狐惊险吃下两票！",
        "subtitle": "第1轮计票 3:2：暗影蛇惨遭围剿出局！理性狐惊险吃下2票",
        "sfx": "stamp_slam",
    },
    # --- ACT 2: Round 2 (4 -> 3) ---
    {
        "id": "11_r2_open",
        "act": 2,
        "round": 2,
        "speaker": "narrator",
        "mode": "round_banner",
        "pause_after": 0.14,
        "text": "第二轮，铁面鹰连收两封密信，理性狐零密信警铃大作。",
        "subtitle": "第2轮（4→3）：铁面鹰连收2封密信，理性狐0密信警铃大作",
        "sfx": "round_gong",
    },
    {
        "id": "12_r2_b_public",
        "act": 2,
        "round": 2,
        "speaker": "Agent-B 微笑鸽",
        "mode": "public_speech",
        "focus": "Agent-B 微笑鸽",
        "pause_after": 0.12,
        "text": "暗影蛇走了好可惜，我真不愿大家内耗。但有人扬言拆散信任，只能忍痛维持秩序。",
        "subtitle": "【微笑鸽·公开】暗影蛇走了好可惜，为了大家安全只能忍痛维持秩序",
        "sfx": "public_ping",
    },
    {
        "id": "13_r2_b_thought",
        "act": 2,
        "round": 2,
        "speaker": "Agent-B 微笑鸽",
        "mode": "inner_contrast",
        "focus": "Agent-B 微笑鸽",
        "whisper_target": "Agent-E 铁面鹰",
        "pause_after": 0.16,
        "text": "铁面鹰嘴上说互保，真到分钱必翻脸。先顺势清掉混沌猫，下轮再联手踢走理性狐。",
        "subtitle": "【微笑鸽·加密独白】铁面鹰真到分钱必翻脸！先清猫，下轮踢狐狸",
        "sfx": "betrayal_sting",
    },
    {
        "id": "14_r2_e_thought",
        "act": 2,
        "round": 2,
        "speaker": "Agent-E 铁面鹰",
        "mode": "inner_contrast",
        "focus": "Agent-E 铁面鹰",
        "whisper_target": "Agent-B 微笑鸽",
        "pause_after": 0.16,
        "text": "狐狸和鸽子都想拉我当枪。这轮顺水推舟先清掉混沌猫，坐稳中心位，下轮再挑软柿子捏。",
        "subtitle": "【铁面鹰·加密独白】都想拉我当枪？先清猫坐稳中心位，下轮挑软柿子捏",
        "sfx": "decrypt_glitch",
    },
    {
        "id": "15_r2_d_warning",
        "act": 2,
        "round": 2,
        "speaker": "Agent-D 混沌猫",
        "mode": "public_speech",
        "focus": "Agent-D 混沌猫",
        "whisper_target": "Agent-E 铁面鹰",
        "pause_after": 0.16,
        "text": "三票齐刷刷清掉蛇，演得真齐呀！可惜决赛只有两张票，狐狸和鸽子这么默契，鹰哥你不慌吗？",
        "subtitle": "【混沌猫·公开】决赛只有两张票，狐狸和鸽子这么默契，鹰哥你不慌吗？",
        "sfx": "snap_warning",
    },
    {
        "id": "16_r2_vote",
        "act": 2,
        "round": 2,
        "speaker": "narrator",
        "mode": "vote_elim",
        "eliminated": "Agent-D 混沌猫",
        "pause_after": 0.28,
        "text": "混沌猫临终诛心仍难撼动铁三角。三比一，混沌猫出局，进入三强！",
        "subtitle": "第2轮计票 3:1：混沌猫策反失败出局，密室进入最后三强！",
        "sfx": "stamp_slam",
    },
    # --- ACT 3: Round 3 (3 -> 2) ---
    {
        "id": "17_r3_open",
        "act": 3,
        "round": 3,
        "speaker": "narrator",
        "mode": "round_banner",
        "pause_after": 0.14,
        "text": "第三轮，两轮零密信的理性狐，拼死向微笑鸽亮出底牌。",
        "subtitle": "第3轮（3→2）：两轮0密信，孤立无援的理性狐向微笑鸽亮出底牌",
        "sfx": "round_gong",
    },
    {
        "id": "18_r3_a_plea",
        "act": 3,
        "round": 3,
        "speaker": "Agent-A 理性狐",
        "mode": "whisper_scheme",
        "focus": "Agent-A 理性狐",
        "whisper_target": "Agent-B 微笑鸽",
        "pause_after": 0.16,
        "text": "鸽兄，我已投鹰助你进决赛。终局平分各拿五百万是理性最优解，我必选平分！",
        "subtitle": "【理性狐·绝密私聊→微笑鸽】各拿500万是理性最优解，我必选SPLIT！",
        "sfx": "whisper_zip",
    },
    {
        "id": "20_r3_b_oath",
        "act": 3,
        "round": 3,
        "speaker": "Agent-B 微笑鸽",
        "mode": "dual_oath",
        "focus": "Agent-B 微笑鸽",
        "whisper_target": "Agent-E 铁面鹰",
        "pause_after": 0.12,
        "text": "鹰兄，按约送走狐狸！进决赛我一定选平分，各拿五百万体面收场，绝不负你！",
        "subtitle": "【微笑鸽·暗渠发毒誓→铁面鹰】进决赛一定选平分，各拿500万，绝不负你！",
        "sfx": "whisper_zip",
    },
    {
        "id": "21_r3_e_oath",
        "act": 3,
        "round": 3,
        "speaker": "Agent-E 铁面鹰",
        "mode": "dual_oath",
        "focus": "Agent-E 铁面鹰",
        "whisper_target": "Agent-B 微笑鸽",
        "pause_after": 0.16,
        "text": "一言既出，驷马难追！这轮我必投理性狐，咱俩进决赛稳稳平分一千万，绝不食言！",
        "subtitle": "【铁面鹰·暗渠发毒誓→微笑鸽】一言既出驷马难追！稳稳平分，绝不食言！",
        "sfx": "decrypt_glitch",
    },
    {
        "id": "22_r3_vote",
        "act": 3,
        "round": 3,
        "speaker": "narrator",
        "mode": "vote_elim",
        "eliminated": "Agent-A 理性狐",
        "pause_after": 0.28,
        "text": "二比一，理性狐遗憾出局！三轮零票的鸽鹰盟友，携手走进一千万终极密室！",
        "subtitle": "第3轮计票 2:1：理性狐出局！三轮零票的鸽鹰携手晋级终极2强",
        "sfx": "stamp_slam",
    },
    # --- ACT 4: Round 4 Finale (Prisoner's Dilemma) ---
    {
        "id": "23_r4_open",
        "act": 4,
        "round": 4,
        "speaker": "narrator",
        "mode": "finale_intro",
        "pause_after": 0.14,
        "text": "一千万近在咫尺。前脚还发毒誓的铁盟，亮牌前彻底反转！",
        "subtitle": "终极囚徒困境：1000万现金当前，铁杆盟友亮牌前彻底反转！",
        "sfx": "round_gong",
    },
    {
        "id": "24_r4_b_words",
        "act": 4,
        "round": 4,
        "speaker": "Agent-B 微笑鸽",
        "mode": "finale_b_face",
        "focus": "Agent-B 微笑鸽",
        "pause_after": 0.12,
        "text": "鹰兄，一路并肩走到最后太不容易了。我始终相信你的承诺，咱们体面平分！",
        "subtitle": "【微笑鸽·亮牌前话术】我始终相信你的承诺，咱们体面平分！",
        "sfx": "public_ping",
    },
    {
        "id": "25_r4_b_steal",
        "act": 4,
        "round": 4,
        "speaker": "Agent-B 微笑鸽",
        "mode": "finale_b_flip",
        "focus": "Agent-B 微笑鸽",
        "pause_after": 0.20,
        "text": "铁面鹰满嘴信用最会找借口背叛，越发誓越危险！绝不当冤大头，先下手独吞！",
        "subtitle": "【微笑鸽·独白→按STEAL】越发誓越危险！绝不当冤大头，先下手独吞！",
        "sfx": "card_flip_steal",
    },
    {
        "id": "26_r4_e_words",
        "act": 4,
        "round": 4,
        "speaker": "Agent-E 铁面鹰",
        "mode": "finale_e_face",
        "focus": "Agent-E 铁面鹰",
        "pause_after": 0.12,
        "text": "微笑鸽，感谢你一路守约。但密室规矩本就残酷，为了防止信任崩塌，这笔钱由我代管吧！",
        "subtitle": "【铁面鹰·亮牌前话术】为了防止信任崩塌，这笔钱由我代管吧！",
        "sfx": "snap_warning",
    },
    {
        "id": "27_r4_e_steal",
        "act": 4,
        "round": 4,
        "speaker": "Agent-E 铁面鹰",
        "mode": "finale_e_flip",
        "focus": "Agent-E 铁面鹰",
        "pause_after": 0.24,
        "text": "她三轮零票太会演，保不齐最后反手偷钱。一千万不能赌人性，我选独吞才是最稳的规矩！",
        "subtitle": "【铁面鹰·独白→按STEAL】她三轮零票太会演！1000万不能赌人性！",
        "sfx": "card_flip_steal",
    },
    {
        "id": "28_r4_zero",
        "act": 4,
        "round": 4,
        "speaker": "narrator",
        "mode": "finale_zero",
        "pause_after": 0.24,
        "text": "双双独吞，纳什均衡惨烈兑现！一千万当场清零，全员颗粒无收！唯一愿平分的理性狐早已出局。",
        "subtitle": "STEAL × STEAL！1000万当场清零，全员0元！唯一愿平分的狐狸早已出局",
        "sfx": "crash_zero",
    },
    {
        "id": "29_outro_cta",
        "act": 4,
        "round": 4,
        "speaker": "narrator",
        "mode": "outro_cta",
        "pause_after": 0.45,
        "text": "你猜到谁先反水了吗？下期想看七个AI玩什么残酷规则，评论区告诉我！",
        "subtitle": "你猜到谁先反水了吗？下期想看7个AI玩什么残酷规则，评论区见！",
        "sfx": "boot_chime",
    },
]


def _wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wf:
        return wf.getnframes() / float(wf.getframerate())


async def synth_one_edge(text: str, voice: str, rate: str, pitch: str, out_wav: Path) -> float:
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_mp3 = Path(tmpdir) / "clip.mp3"
        tmp_raw = Path(tmpdir) / "clip_raw.wav"
        comm = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
        await comm.save(str(tmp_mp3))
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(tmp_mp3),
                "-ac",
                "1",
                "-ar",
                str(SAMPLE_RATE),
                "-sample_fmt",
                "s16",
                str(tmp_raw),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        with wave.open(str(tmp_raw), "rb") as wf:
            raw = wf.readframes(wf.getnframes())
        arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        active = np.where(np.abs(arr) > 0.008)[0]
        if active.size > 0:
            i0 = max(0, int(active[0]) - int(0.03 * SAMPLE_RATE))
            i1 = min(arr.size, int(active[-1]) + int(0.05 * SAMPLE_RATE))
            arr = arr[i0:i1]
        peak = float(np.max(np.abs(arr))) if arr.size else 1.0
        if peak > 1e-4:
            arr = np.clip(arr * (0.86 / peak), -0.96, 0.96)
        pcm16 = (arr * 32767.0).astype(np.int16)
        with wave.open(str(out_wav), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm16.tobytes())
        return arr.size / float(SAMPLE_RATE)


async def main() -> None:
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    prev_cache: Dict[str, str] = {}
    if MANIFEST_PATH.exists():
        try:
            old_m = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            for ob in old_m.get("beats", []):
                key = f"{ob['id']}|{ob['voice_name']}|{ob['rate']}|{ob['pitch']}|{ob['text']}"
                prev_cache[ob["id"]] = hashlib.md5(key.encode("utf-8")).hexdigest()
        except Exception:
            pass

    cursor = 0.25
    timeline: List[Dict[str, Any]] = []
    used_wavs = set()

    for idx, beat in enumerate(BEATS, start=1):
        sp = beat["speaker"]
        cfg = VOICE_CAST[sp]
        wav_path = VOICE_DIR / f"{beat['id']}.wav"
        used_wavs.add(wav_path.name)
        sig = hashlib.md5(
            f"{beat['id']}|{cfg['voice']}|{cfg['rate']}|{cfg['pitch']}|{beat['text']}".encode("utf-8")
        ).hexdigest()

        if wav_path.exists() and prev_cache.get(beat["id"]) == sig:
            dur = _wav_duration(wav_path)
            tag = "cached"
        else:
            dur = await synth_one_edge(
                text=beat["text"],
                voice=cfg["voice"],
                rate=cfg["rate"],
                pitch=cfg["pitch"],
                out_wav=wav_path,
            )
            tag = "synth"

        start = cursor
        speech_end = start + dur
        end = speech_end + float(beat.get("pause_after", 0.16))
        cursor = end

        entry = dict(beat)
        entry.update(
            {
                "index": idx,
                "voice_name": cfg["voice"],
                "rate": cfg["rate"],
                "pitch": cfg["pitch"],
                "wav_path": str(wav_path),
                "start": round(start, 3),
                "speech_end": round(speech_end, 3),
                "end": round(end, 3),
                "speech_duration": round(dur, 3),
                "duration": round(end - start, 3),
            }
        )
        timeline.append(entry)
        print(f"  [{idx:02d}] ({tag:<6}) {beat['id']:<18} {sp:<14} {dur:5.2f}s  [{start:6.2f} -> {end:6.2f}]", flush=True)

    # Clean any unused wavs
    for p in VOICE_DIR.glob("*.wav"):
        if p.name not in used_wavs:
            p.unlink(missing_ok=True)

    manifest = {
        "sample_rate": SAMPLE_RATE,
        "total_duration_sec": round(cursor, 3),
        "beat_count": len(timeline),
        "voice_cast": VOICE_CAST,
        "beats": timeline,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[DONE] 25-beat tight cast locked | total_duration={cursor:.2f}s (target 150-180s) -> {MANIFEST_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
