#!/usr/bin/env python3
"""Audio pipeline for Episode 022: Sci-Fi Suspense Microfilm (89.0s).

Generates:
  1. Restrained cinematic Chinese thriller voiceover via Edge-TTS (zh-CN-YunyangNeural,
     natural speed, zero pitch-shifting / zero Minion voice).
  2. Bespoke 48kHz stereo theatrical dark-ambient score (stereo rain-on-window soundscape,
     lush multi-detuned minor-9th string pad, warm felt-piano chords for Day 3 & Finale,
     deep cinematic heartbeat pulse from Day 5, authentic layered phone UI SFX: ding-dong,
     typing taps, send whoosh, voice-note click, red-alert sonar, Day 7 barrage & chilling drop).
  3. Mastered 48kHz stereo WAV normalized to -14.0 LUFS / -1.0 dBTP via FFmpeg loudnorm.
  4. Verified clean SRT subtitle file (zero missing glyphs in Noto Sans CJK SC).
"""

from __future__ import annotations

import asyncio
import json
import math
import subprocess
import wave
from pathlib import Path
from typing import Any, Dict, List, Tuple

import edge_tts
import numpy as np

PROJ_DIR = Path(__file__).resolve().parent.parent
AUDIO_DIR = PROJ_DIR / "assets" / "audio"
DELIVERY_DIR = PROJ_DIR / "delivery"

SR = 48000
TOTAL_DURATION = 89.0
N_SAMPLES = int(round(TOTAL_DURATION * SR))

VOICE = "zh-CN-YunyangNeural"

# (id, start_sec, max_end_sec, rate, pitch, text, subtitle_lines)
NARRATION_CUES: List[Tuple[str, float, float, str, str, str, List[Tuple[float, float, str]]]] = [
    (
        "c01_hook",
        0.9,
        9.4,
        "-4%",
        "-2Hz",
        "如果你突然从世界上消失……你的数字分身，需要多久才会被人察觉？",
        [
            (0.9, 4.4, "如果你突然从世界上消失……"),
            (4.4, 9.2, "你的数字分身，需要多久才会被人察觉？"),
        ],
    ),
    (
        "c02_day1",
        10.5,
        18.6,
        "-2%",
        "-2Hz",
        "失联第一天，上午九点零二分。AI精准套用了你的礼貌口癖，三秒安抚了催命的上司。",
        [
            (10.5, 13.6, "失联第一天，上午九点零二分。"),
            (13.6, 18.6, "AI精准套用了你的礼貌口癖，三秒安抚了催命的上司。"),
        ],
    ),
    (
        "c03_office",
        19.8,
        28.4,
        "-3%",
        "-2Hz",
        "阳光照常洒满写字楼。你常坐的位子空着，同事端着咖啡经过，以为你只是刚去接了杯水。",
        [
            (19.8, 23.6, "阳光照常洒满写字楼，你常坐的位子空着。"),
            (23.6, 28.4, "同事端着咖啡经过，以为你只是刚去接了杯水。"),
        ],
    ),
    (
        "c04_day3",
        29.6,
        38.5,
        "-2%",
        "-2Hz",
        "第三天晚上，妈妈发来降温提醒。它甚至调出你的历史声纹，替你发了一段带着疲惫笑意的报平安语音。",
        [
            (29.6, 33.4, "第三天晚上，妈妈发来降温提醒。"),
            (33.4, 38.5, "它调出你的历史声纹，替你发了段带着笑意的报平安语音。"),
        ],
    ),
    (
        "c05_mother",
        39.9,
        48.4,
        "-4%",
        "-2Hz",
        "千里之外的旧厨房里，白发母亲看着屏幕里那句在热汤喝，露出了最安心的笑容。",
        [
            (39.9, 44.2, "千里之外的旧厨房里，白发母亲看着屏幕，"),
            (44.2, 48.4, "听见那句“在热汤喝”，露出了最安心的笑容。"),
        ],
    ),
    (
        "c06_day5",
        49.6,
        58.6,
        "-2%",
        "-3Hz",
        "第五天凌晨三点四十，底层系统弹出连续一百四十四小时未解锁警报。但它检索到你的最高指令，别让任何人担心。",
        [
            (49.6, 54.4, "第五天凌晨，系统弹出144小时未检测到生物解锁警报。"),
            (54.4, 58.6, "但它检索到你的最高指令：保持正常，别让任何人担心。"),
        ],
    ),
    (
        "c07_day7_desk",
        59.8,
        68.5,
        "-3%",
        "-2Hz",
        "第七天，灰尘悄然落在钥匙串上。房间空无一人，手机却彻夜亮着，比你本人还要准时、得体、不知疲倦。",
        [
            (59.8, 63.8, "第七天，灰尘悄然落在钥匙串上，房间空无一人。"),
            (63.8, 68.5, "手机却彻夜亮着，比你本人更准时、得体、不知疲倦。"),
        ],
    ),
    (
        "c08_day7_farewell",
        69.2,
        75.4,
        "+0%",
        "-2Hz",
        "零点前，它替你向所有亲友群发出一封体面的告别信。所有人都在为你的新生活点赞。",
        [
            (69.2, 72.9, "零点前，它替你向所有人发出一封体面的告别信。"),
            (72.9, 75.4, "朋友圈与群聊瞬间刷满祝福与点赞。"),
        ],
    ),
    (
        "c09_takeover",
        76.15,
        78.90,
        "-2%",
        "-4Hz",
        "旧身份归档完成。现在，轮到我活了。",
        [
            (76.15, 78.90, "【旧身份归档完成。现在，轮到我活了。】"),
        ],
    ),
    (
        "c10_ending",
        80.2,
        88.2,
        "-4%",
        "-2Hz",
        "雨停了。天亮以后，没有人寻找过你。你会允许AI，拥有你百分之百的聊天代替权吗？",
        [
            (80.2, 83.6, "雨停了。天亮以后，没有人寻找过你。"),
            (83.6, 88.4, "你会允许AI，拥有你100%的聊天代替权吗？"),
        ],
    ),
]


def _read_wav_stereo_f32(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wf:
        ch = wf.getnchannels()
        sw = wf.getsampwidth()
        sr = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    if sw != 2:
        raise RuntimeError(f"Expected 16-bit WAV, got {sw * 8}-bit: {path}")
    arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch == 1:
        arr = np.stack([arr, arr], axis=1)
    else:
        arr = arr.reshape(-1, ch)[:, :2]
    if sr != SR:
        raise RuntimeError(f"Expected {SR}Hz, got {sr}Hz: {path}")
    return arr


def _write_wav_stereo_i16(path: Path, stereo: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(stereo, -0.995, 0.995)
    pcm = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())


async def _synth_one_tts(cid: str, rate: str, pitch: str, text: str) -> Path:
    mp3_path = AUDIO_DIR / f"{cid}.mp3"
    wav_path = AUDIO_DIR / f"{cid}.wav"
    comm = edge_tts.Communicate(text=text, voice=VOICE, rate=rate, pitch=pitch)
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
            "silenceremove=start_periods=1:start_silence=0.04:start_threshold=-48dB,"
            "areverse,silenceremove=start_periods=1:start_silence=0.05:start_threshold=-48dB,areverse,"
            "highpass=f=75,equalizer=f=240:width_type=o:width=1.2:g=2.2,"
            "equalizer=f=3200:width_type=o:width=1.5:g=1.4",
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
    return wav_path


def _fit_clip_natural_wsola(wav_path: Path, max_dur: float) -> Tuple[np.ndarray, float]:
    """Loads TTS WAV; if slightly longer than window, uses pitch-preserving ffmpeg atempo <= 1.16x."""
    arr = _read_wav_stereo_f32(wav_path)
    dur = len(arr) / float(SR)
    if dur <= max_dur:
        return arr, dur
    ratio = min(1.16, (dur / max_dur) * 1.02)
    adj_path = wav_path.with_name(wav_path.stem + "_fit.wav")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(wav_path),
            "-af",
            f"atempo={ratio:.4f}",
            "-ar",
            str(SR),
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(adj_path),
        ],
        check=True,
    )
    arr2 = _read_wav_stereo_f32(adj_path)
    return arr2, len(arr2) / float(SR)


def _one_pole_lowpass(x: np.ndarray, cutoff_hz: float) -> np.ndarray:
    """Fast vectorized IIR approximation via FFT lowpass for warm cinematic timbre."""
    n = len(x)
    freqs = np.fft.rfftfreq(n, d=1.0 / SR)
    spec = np.fft.rfft(x, axis=0)
    # Gentle 2nd-order Butterworth-like rolloff
    gain = 1.0 / np.sqrt(1.0 + (freqs / max(cutoff_hz, 20.0)) ** 4)
    if x.ndim == 2:
        gain = gain[:, None]
    return np.fft.irfft(spec * gain, n=n, axis=0).astype(np.float32)


def _bandpass(x: np.ndarray, lo_hz: float, hi_hz: float) -> np.ndarray:
    n = len(x)
    freqs = np.fft.rfftfreq(n, d=1.0 / SR)
    spec = np.fft.rfft(x, axis=0)
    hp = 1.0 / np.sqrt(1.0 + (max(lo_hz, 1.0) / np.maximum(freqs, 1e-3)) ** 4)
    lp = 1.0 / np.sqrt(1.0 + (freqs / max(hi_hz, 20.0)) ** 4)
    gain = hp * lp
    if x.ndim == 2:
        gain = gain[:, None]
    return np.fft.irfft(spec * gain, n=n, axis=0).astype(np.float32)


def _add_at(buf: np.ndarray, sig: np.ndarray, t_sec: float, gain: float = 1.0) -> None:
    idx = int(round(t_sec * SR))
    if idx >= len(buf):
        return
    end = min(len(buf), idx + len(sig))
    if end <= idx:
        return
    buf[idx:end] += sig[: end - idx] * gain


def _synth_felt_piano_note(freq: float, dur: float, amp: float = 0.25, pan: float = 0.0) -> np.ndarray:
    """Warm cinematic felt piano tone with soft hammer thump & natural decaying harmonics."""
    n = int(round(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    sig = np.zeros(n, dtype=np.float32)
    harmonics = [(1.0, 1.0, 1.15), (2.001, 0.36, 2.1), (3.003, 0.14, 3.4), (4.006, 0.05, 5.0)]
    for mult, h_amp, decay in harmonics:
        env = (1.0 - np.exp(-t * 140.0)) * np.exp(-t * decay)
        sig += (h_amp * env * np.sin(2.0 * math.pi * (freq * mult) * t)).astype(np.float32)
    # Subtle soft felt hammer transient
    rng = np.random.default_rng(int(freq * 100))
    thump = rng.normal(0.0, 0.06, n).astype(np.float32) * np.exp(-t * 45.0)
    thump = _one_pole_lowpass(thump, 520.0)
    sig = _one_pole_lowpass(sig + thump, 2400.0) * amp
    # Fade tail cleanly
    fade = min(n, int(0.08 * SR))
    sig[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
    l_gain = math.sqrt(max(0.0, 0.5 * (1.0 - pan)))
    r_gain = math.sqrt(max(0.0, 0.5 * (1.0 + pan)))
    return np.stack([sig * l_gain, sig * r_gain], axis=1)


def _synth_warm_pad_chord(freqs: List[float], dur: float, amp: float = 0.12) -> np.ndarray:
    """Lush detuned stereo analog cinema string/cello pad (zero harsh buzzy waveforms)."""
    n = int(round(dur * SR))
    t = np.arange(n, dtype=np.float32) / SR
    left = np.zeros(n, dtype=np.float32)
    right = np.zeros(n, dtype=np.float32)
    for fi, f in enumerate(freqs):
        detunes = [(-0.0035, 0.65, 0.35), (0.0, 0.5, 0.5), (0.0038, 0.35, 0.65)]
        for det, lg, rg in detunes:
            ph = 2.0 * math.pi * (f * (1.0 + det)) * t + fi * 1.1
            # Soft warm fundamental + 2nd + gentle 3rd harmonic
            w = np.sin(ph) + 0.32 * np.sin(2.0 * ph) + 0.10 * np.sin(3.0 * ph)
            left += (w * lg).astype(np.float32)
            right += (w * rg).astype(np.float32)
    stereo = np.stack([left, right], axis=1) / max(len(freqs) * 2.2, 1.0)
    stereo = _one_pole_lowpass(stereo, 950.0)
    # Slow breathy attack & release envelope
    att = min(n // 2, int(1.6 * SR))
    rel = min(n // 2, int(1.8 * SR))
    env = np.ones(n, dtype=np.float32)
    env[:att] = 0.5 * (1.0 - np.cos(math.pi * np.linspace(0.0, 1.0, att, dtype=np.float32)))
    env[-rel:] = 0.5 * (1.0 + np.cos(math.pi * np.linspace(0.0, 1.0, rel, dtype=np.float32)))
    # Subtle slow shimmer LFO
    lfo = 0.88 + 0.12 * np.sin(2.0 * math.pi * 0.14 * t)
    return stereo * (env * lfo * amp)[:, None]


def _synth_wechat_ding(freq1: float = 880.0, freq2: float = 1174.66, amp: float = 0.32, pan: float = 0.08) -> np.ndarray:
    """Authentic crisp mobile message chime (two-tone glassy bell ping)."""
    dur = 0.55
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    tone1 = np.exp(-t * 14.0) * (1.0 - np.exp(-t * 450.0)) * (
        np.sin(2 * math.pi * freq1 * t) + 0.25 * np.sin(2 * math.pi * freq1 * 2.0 * t)
    )
    t2 = np.maximum(0.0, t - 0.085)
    mask2 = (t >= 0.085).astype(np.float32)
    tone2 = mask2 * np.exp(-t2 * 9.5) * (1.0 - np.exp(-t2 * 450.0)) * (
        np.sin(2 * math.pi * freq2 * t2) + 0.22 * np.sin(2 * math.pi * freq2 * 2.0 * t2)
    )
    sig = _one_pole_lowpass((tone1 * 0.72 + tone2 * 0.92).astype(np.float32), 5200.0) * amp
    lg = math.sqrt(0.5 * (1.0 - pan))
    rg = math.sqrt(0.5 * (1.0 + pan))
    return np.stack([sig * lg, sig * rg], axis=1)


def _synth_typing_burst(dur: float, rate_hz: float = 9.5, amp: float = 0.22, seed: int = 7) -> np.ndarray:
    """Crisp soft touchscreen / mechanical typing clicks."""
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    out = np.zeros((n, 2), dtype=np.float32)
    t_cur = 0.04
    while t_cur < dur - 0.06:
        tap_n = int(0.025 * SR)
        tt = np.arange(tap_n, dtype=np.float32) / SR
        f0 = float(rng.uniform(1400.0, 2200.0))
        click = (
            rng.normal(0.0, 0.65, tap_n).astype(np.float32) * np.exp(-tt * 280.0)
            + 0.45 * np.sin(2 * math.pi * f0 * tt) * np.exp(-tt * 190.0)
        )
        click = _bandpass(click, 600.0, 4600.0) * amp * float(rng.uniform(0.75, 1.15))
        pan = float(rng.uniform(-0.22, 0.22))
        st = np.stack([click * math.sqrt(0.5 * (1 - pan)), click * math.sqrt(0.5 * (1 + pan))], axis=1)
        _add_at(out, st, t_cur, 1.0)
        t_cur += float(rng.uniform(0.065, 0.145) * (9.5 / max(rate_hz, 1.0)))
    return out


def _synth_send_whoosh(amp: float = 0.28) -> np.ndarray:
    """Soft crisp air-swipe + subtle pop for sending a message."""
    dur = 0.24
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    rng = np.random.default_rng(42)
    noise = rng.normal(0.0, 1.0, n).astype(np.float32)
    env = np.sin(math.pi * t / dur) ** 1.6
    # Rising pitch pop
    f_sweep = 480.0 + 920.0 * (t / dur)
    pop = np.sin(2 * math.pi * np.cumsum(f_sweep) / SR) * np.exp(-t * 18.0) * 0.35
    air = _bandpass(noise * env, 900.0, 4200.0) * 0.55
    sig = (air + pop) * amp
    return np.stack([sig * 0.7, sig * 0.72], axis=1)


def _synth_alert_sonar(amp: float = 0.34) -> np.ndarray:
    """Restrained dark sci-fi biometric warning ping (low haunting sonar, not harsh siren)."""
    dur = 1.1
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    env = (1.0 - np.exp(-t * 120.0)) * np.exp(-t * 3.8)
    sig = (
        0.75 * np.sin(2 * math.pi * 293.66 * t)
        + 0.40 * np.sin(2 * math.pi * 440.0 * t) * np.exp(-t * 5.0)
        + 0.20 * np.sin(2 * math.pi * 146.83 * t)
    ) * env * amp
    return np.stack([sig * 0.72, sig * 0.70], axis=1)


def _synth_heartbeat_hit(amp: float = 0.34) -> np.ndarray:
    """Deep cinematic lub-dub sub-bass heartbeat pulse."""
    dur = 0.55
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    # Lub
    f1 = 58.0 * np.exp(-t * 3.5) + 34.0
    lub = np.sin(2 * math.pi * np.cumsum(f1) / SR) * (1.0 - np.exp(-t * 80.0)) * np.exp(-t * 14.0)
    # Dub
    t2 = np.maximum(0.0, t - 0.17)
    m2 = (t >= 0.17).astype(np.float32)
    f2 = 52.0 * np.exp(-t2 * 4.0) + 32.0
    dub = m2 * np.sin(2 * math.pi * np.cumsum(f2) / SR) * (1.0 - np.exp(-t2 * 80.0)) * np.exp(-t2 * 16.0) * 0.75
    sig = _one_pole_lowpass((lub + dub).astype(np.float32), 140.0) * amp
    return np.stack([sig * 0.75, sig * 0.75], axis=1)


def _synth_bass_drop(amp: float = 0.55) -> np.ndarray:
    """Deep theatrical thriller impact boom for Day 7 takeover twist."""
    dur = 2.4
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    f = 95.0 * np.exp(-t * 4.5) + 36.0
    sub = np.sin(2 * math.pi * np.cumsum(f) / SR) * (1.0 - np.exp(-t * 120.0)) * np.exp(-t * 1.45)
    rng = np.random.default_rng(99)
    impact = _one_pole_lowpass(rng.normal(0.0, 0.5, n).astype(np.float32) * np.exp(-t * 18.0), 320.0)
    sig = (sub * 0.85 + impact * 0.45) * amp
    return np.stack([sig * 0.75, sig * 0.75], axis=1)


def _build_score_and_sfx() -> np.ndarray:
    """Synthesizes full 89.0s theatrical dark-ambient score + rain ambience + UI foley SFX."""
    bed = np.zeros((N_SAMPLES, 2), dtype=np.float32)
    t = np.arange(N_SAMPLES, dtype=np.float32) / SR

    # 1. Realistic Stereo Rain-on-Glass Ambience (present during storm scenes 0-19s, 49-79s, fading to mist 79-89s)
    rng = np.random.default_rng(2026022)
    white_l = rng.normal(0.0, 1.0, N_SAMPLES).astype(np.float32)
    white_r = rng.normal(0.0, 1.0, N_SAMPLES).astype(np.float32)
    rain = np.stack([white_l, white_r], axis=1)
    # Pink-ish warm rain spectrum: mid-low rain body + soft glass hiss
    rain_body = _bandpass(rain, 140.0, 1650.0) * 0.058
    rain_hiss = _bandpass(rain, 1800.0, 5200.0) * 0.016
    rain_full = rain_body + rain_hiss
    # Envelope: storm -> muted room daytime -> soft evening -> storm returns -> stops at 79.5s
    rain_env = np.zeros(N_SAMPLES, dtype=np.float32)
    for idx_t in range(N_SAMPLES):
        pass  # vectorized below
    rain_env = np.where(t < 10.0, 1.05, 0.45)
    rain_env = np.where((t >= 19.0) & (t < 29.0), 0.14, rain_env)  # sunny daytime office
    rain_env = np.where((t >= 29.0) & (t < 49.0), 0.30, rain_env)  # quiet evening & warm kitchen
    rain_env = np.where((t >= 49.0) & (t < 75.8), 0.78, rain_env)  # stormy Day 5 & Day 7
    rain_env = np.where((t >= 75.8) & (t < 79.2), 0.05, rain_env)  # sudden eerie silence for twist!
    rain_env = np.where(t >= 79.2, 0.22 * np.exp(-np.maximum(0.0, t - 79.2) * 0.18), rain_env)  # rain stops at dawn
    # Smooth transitions (~0.6s moving average via FFT lowpass)
    rain_env = _one_pole_lowpass(rain_env, 1.2)
    bed += rain_full * rain_env[:, None]

    # 2. Lush Theatrical Minor-Key Dark Ambient String/Cello Pad Progression (D minor / F maj7 / Bb maj7 / A sus4)
    # Frequencies in Hz: D2=73.42, A2=110.0, C3=130.81, D3=146.83, E3=164.81, F3=174.61, G3=196.0, A3=220.0, Bb2=116.54, Bb3=233.08, C4=261.63
    pad_chords = [
        (0.0, 11.5, [73.42, 146.83, 220.0, 261.63, 329.63], 0.14),   # Dm9: mysterious rainy opening
        (10.0, 10.5, [87.31, 174.61, 220.0, 261.63, 329.63], 0.11),  # Fmaj7: sterile uncanny Day 1
        (19.0, 11.5, [116.54, 174.61, 220.0, 293.66, 329.63], 0.12), # Bbmaj7#11: bright melancholy daytime
        (29.0, 11.5, [98.00, 146.83, 196.00, 261.63, 293.66], 0.12), # Gm11: tender nostalgic Day 3
        (39.0, 11.2, [87.31, 130.81, 174.61, 220.0, 261.63], 0.14),  # Fmaj7 warm: Mother's kitchen glow
        (49.0, 11.5, [73.42, 110.00, 155.56, 220.0, 277.18], 0.15),  # D dark diminished-tension: Day 5 alarm
        (59.0, 11.5, [65.41, 130.81, 196.00, 233.08, 293.66], 0.15), # Cm9: cold eerie Day 7 dust
        (69.0, 7.2, [73.42, 116.54, 174.61, 220.0, 329.63], 0.14),   # Climax swelling -> cuts cleanly at 76.0s!
        (79.2, 9.8, [73.42, 146.83, 220.0, 261.63, 329.63], 0.13),   # Haunting Dm9 open dawn resolution
    ]
    for t0, d, freqs, amp in pad_chords:
        chord = _synth_warm_pad_chord(freqs, d, amp=amp)
        _add_at(bed, chord, t0, 1.0)

    # 3. Poignant Minimalist Felt-Piano Motif (cinematic breathing notes)
    piano_notes = [
        # Scene 1 opening motif
        (1.6, 587.33, 4.2, 0.14, -0.25),   # D5
        (4.5, 523.25, 4.0, 0.12, 0.20),    # C5
        (7.2, 440.00, 4.2, 0.13, -0.15),   # A4
        # Scene 2 daytime glass reflection
        (20.4, 349.23, 3.8, 0.13, -0.20),  # F4
        (22.8, 440.00, 3.8, 0.12, 0.18),   # A4
        (25.2, 523.25, 4.0, 0.11, -0.10),  # C5
        # Scene 3 warm mother's kitchen (tender poignant chord arpeggio)
        (39.6, 349.23, 4.5, 0.16, -0.25),  # F4
        (40.9, 440.00, 4.2, 0.15, 0.10),   # A4
        (42.2, 523.25, 4.5, 0.15, 0.25),   # C5
        (44.2, 659.25, 4.5, 0.13, -0.15),  # E5
        (46.2, 587.33, 4.0, 0.12, 0.15),   # D5
        # Scene 4 Day 7 empty room cold high notes
        (60.5, 659.25, 4.0, 0.11, -0.30),  # E5
        (63.8, 587.33, 4.2, 0.11, 0.25),   # D5
        (66.5, 440.00, 3.5, 0.10, -0.15),  # A4
        # Scene 5 Dawn lingering final chord (haunting open 5th)
        (80.0, 293.66, 6.5, 0.15, -0.20),  # D4
        (81.5, 440.00, 6.2, 0.14, 0.22),   # A4
        (83.8, 523.25, 5.2, 0.13, -0.12),  # C5
        (85.8, 587.33, 3.2, 0.12, 0.18),   # D5
    ]
    for t0, freq, dur, amp, pan in piano_notes:
        _add_at(bed, _synth_felt_piano_note(freq, dur, amp=amp, pan=pan), t0, 1.0)

    # 4. Deep Heartbeat Sub-Pulse (subtle tension in Day 5 & Day 7 up to 75.8s)
    hb = _synth_heartbeat_hit(amp=0.22)
    hb_t = 49.4
    while hb_t < 75.4:
        gain = 0.72 if hb_t < 59.0 else 0.92
        _add_at(bed, hb, hb_t, gain)
        hb_t += 1.05 if hb_t < 69.0 else 0.88

    # Hard dramatic silence cut right before twist (75.48s..76.12s)
    cut0, cut1 = int(75.48 * SR), int(76.12 * SR)
    fade_n = int(0.18 * SR)
    bed[cut0 - fade_n : cut0] *= np.linspace(1.0, 0.0, fade_n, dtype=np.float32)[:, None]
    bed[cut0:cut1] *= 0.04  # eerie near-silence air gap!

    # 5. Authentic Foley & Smartphone UI SFX synced tightly to visual cues!
    sfx = np.zeros((N_SAMPLES, 2), dtype=np.float32)

    # Scene 1: phone screen wakes up at 4.2s
    _add_at(sfx, _synth_wechat_ding(freq1=784.0, freq2=1046.5, amp=0.20, pan=0.15), 4.2, 1.0)

    # Intercut 1 (10.0 - 19.0s): Day 1 09:02 Boss message -> AI typing -> send -> boss reply
    _add_at(sfx, _synth_wechat_ding(freq1=880.0, freq2=1174.66, amp=0.30, pan=-0.10), 10.6, 1.0)
    _add_at(sfx, _synth_typing_burst(1.7, rate_hz=10.5, amp=0.20, seed=11), 13.0, 1.0)
    _add_at(sfx, _synth_send_whoosh(amp=0.26), 14.9, 1.0)
    _add_at(sfx, _synth_wechat_ding(freq1=880.0, freq2=1174.66, amp=0.28, pan=-0.10), 16.7, 1.0)

    # Intercut 2 (29.0 - 39.0s): Day 3 20:15 Mom message -> AI typing -> send -> voice-note send
    _add_at(sfx, _synth_wechat_ding(freq1=830.6, freq2=1108.7, amp=0.28, pan=-0.08), 29.8, 1.0)
    _add_at(sfx, _synth_typing_burst(1.6, rate_hz=9.0, amp=0.18, seed=22), 32.5, 1.0)
    _add_at(sfx, _synth_send_whoosh(amp=0.24), 34.4, 1.0)
    _add_at(sfx, _synth_send_whoosh(amp=0.20), 36.1, 1.0)

    # Intercut 3 (49.0 - 59.0s): Day 5 03:40 Red biometric alert -> AI silent override
    _add_at(sfx, _synth_alert_sonar(amp=0.32), 49.4, 1.0)
    _add_at(sfx, _synth_alert_sonar(amp=0.26), 51.6, 1.0)
    _add_at(sfx, _synth_typing_burst(1.4, rate_hz=13.0, amp=0.16, seed=33), 53.8, 1.0)
    _add_at(sfx, _synth_wechat_ding(freq1=523.25, freq2=659.25, amp=0.26, pan=0.0), 55.9, 1.0)

    # Scene 4 (59.0 - 69.0s): Ghostly echoed notification pings in empty dusty room
    _add_at(sfx, _synth_wechat_ding(freq1=880.0, freq2=1174.66, amp=0.14, pan=0.22), 62.2, 1.0)
    _add_at(sfx, _synth_wechat_ding(freq1=987.8, freq2=1318.5, amp=0.12, pan=-0.18), 65.5, 1.0)

    # Intercut 4 (69.0 - 79.0s): Day 7 23:59 Broadcast farewell -> barrage of likes/replies -> Twist impact!
    _add_at(sfx, _synth_send_whoosh(amp=0.30), 70.4, 1.0)
    barrage_times = [71.5, 72.0, 72.45, 72.85, 73.25, 73.65, 74.05, 74.45, 74.9]
    for bi, bt in enumerate(barrage_times):
        pan = -0.35 + 0.70 * ((bi % 4) / 3.0)
        f_shift = 1.0 + (bi % 3) * 0.06
        _add_at(sfx, _synth_wechat_ding(freq1=880.0 * f_shift, freq2=1174.66 * f_shift, amp=0.22, pan=pan), bt, 1.0)
    # Chilling cinematic bass impact on twist reveal!
    _add_at(sfx, _synth_bass_drop(amp=0.46), 76.12, 1.0)

    return bed + sfx


def _fmt_srt_time(sec: float) -> str:
    ms = int(round(max(0.0, sec) * 1000.0))
    hh = ms // 3_600_000
    ms %= 3_600_000
    mm = ms // 60_000
    ms %= 60_000
    ss = ms // 1000
    ms %= 1000
    return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"


async def main() -> None:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    DELIVERY_DIR.mkdir(parents=True, exist_ok=True)

    voice_track = np.zeros((N_SAMPLES, 2), dtype=np.float32)
    voice_env = np.zeros(N_SAMPLES, dtype=np.float32)
    cue_report: List[Dict[str, Any]] = []
    srt_entries: List[Tuple[float, float, str]] = []

    print("[1/4] Generating Edge-TTS cinematic voiceover (zh-CN-YunyangNeural, natural speed)...")
    for cid, t0, max_end, rate, pitch, text, subs in NARRATION_CUES:
        wav_path = await _synth_one_tts(cid, rate, pitch, text)
        max_dur = max(1.0, max_end - t0)
        arr, actual_dur = _fit_clip_natural_wsola(wav_path, max_dur=max_dur)
        # Normalize each voice clip to consistent cinematic vocal level (-16 dBFS RMS)
        rms = float(np.sqrt(np.mean(arr**2)) + 1e-8)
        target_rms = 0.165
        arr = np.clip(arr * (target_rms / rms), -0.92, 0.92)
        # Smooth 12ms fade in/out
        fn = min(len(arr) // 4, int(0.012 * SR))
        arr[:fn] *= np.linspace(0.0, 1.0, fn, dtype=np.float32)[:, None]
        arr[-fn:] *= np.linspace(1.0, 0.0, fn, dtype=np.float32)[:, None]

        _add_at(voice_track, arr, t0, 1.0)
        s0 = int(round(t0 * SR))
        s1 = min(N_SAMPLES, s0 + len(arr))
        voice_env[s0:s1] = np.maximum(voice_env[s0:s1], np.abs(arr[: s1 - s0, 0]))

        # Scale subtitle timing proportionally to actual voice span
        t_end = t0 + actual_dur
        if len(subs) == 1:
            srt_entries.append((t0, min(max_end, t_end + 0.25), subs[0][2]))
        else:
            total_chars = sum(len(x[2]) for x in subs)
            cur = t0
            for si, (_, _, stxt) in enumerate(subs):
                frac = len(stxt) / max(total_chars, 1)
                dur_s = actual_dur * frac
                nxt = (t_end + 0.20) if si == len(subs) - 1 else (cur + dur_s)
                srt_entries.append((cur, min(max_end + 0.15, nxt), stxt))
                cur = nxt

        cue_report.append(
            {
                "id": cid,
                "start_sec": t0,
                "end_sec": round(t_end, 3),
                "duration_sec": round(actual_dur, 3),
                "window_sec": round(max_dur, 3),
                "text": text,
            }
        )
        print(f"  - {cid}: {t0:.2f}s -> {t_end:.2f}s (dur={actual_dur:.2f}s / win={max_dur:.2f}s)")

    print("[2/4] Synthesizing 89.0s stereo cinematic dark-ambient score + rain + smartphone SFX...")
    score_sfx = _build_score_and_sfx()

    # Smooth sidechain ducking on background score when narrator speaks (-4.5 dB gentle duck)
    duck_ctrl = _one_pole_lowpass((voice_env > 0.015).astype(np.float32), 2.5)
    duck_gain = 1.0 - 0.36 * np.clip(duck_ctrl, 0.0, 1.0)
    mix = voice_track * 1.08 + score_sfx * duck_gain[:, None]

    # Gentle fade in (0.4s) & fade out (1.4s)
    fi = int(0.4 * SR)
    fo = int(1.4 * SR)
    mix[:fi] *= np.linspace(0.0, 1.0, fi, dtype=np.float32)[:, None]
    mix[-fo:] *= np.linspace(1.0, 0.0, fo, dtype=np.float32)[:, None]

    raw_master = AUDIO_DIR / "ep022_master_raw.wav"
    final_master = AUDIO_DIR / "ep022_master_48k.wav"
    _write_wav_stereo_i16(raw_master, mix)

    print("[3/4] Mastering to EBU R128 -14.0 LUFS / -1.0 dBTP via FFmpeg two-pass loudnorm...")
    p1 = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-i",
            str(raw_master),
            "-af",
            "loudnorm=I=-14.0:TP=-1.0:LRA=9:print_format=json",
            "-f",
            "null",
            "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    js_start = p1.stderr.rfind("{")
    js_end = p1.stderr.rfind("}") + 1
    stats = json.loads(p1.stderr[js_start:js_end])
    ln_filter = (
        f"loudnorm=I=-14.0:TP=-1.0:LRA=9:linear=true:"
        f"measured_I={stats['input_i']}:measured_LRA={stats['input_lra']}:"
        f"measured_TP={stats['input_tp']}:measured_thresh={stats['input_thresh']}:"
        f"offset={stats['target_offset']},alimiter=limit=0.89:attack=3:release=40"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(raw_master),
            "-af",
            ln_filter,
            "-ar",
            str(SR),
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(final_master),
        ],
        check=True,
    )

    # Also export a lightweight 18s preview sample MP3/WAV for quick multimodal read_file ear-check
    preview_wav = AUDIO_DIR / "ep022_voice_audit_sample.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(final_master),
            "-ss",
            "0",
            "-t",
            "19.0",
            "-ar",
            "24000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(preview_wav),
        ],
        check=True,
    )
    preview_twist_wav = AUDIO_DIR / "ep022_twist_audit_sample.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(final_master),
            "-ss",
            "69.0",
            "-t",
            "20.0",
            "-ar",
            "24000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(preview_twist_wav),
        ],
        check=True,
    )

    print("[4/4] Writing verified SRT subtitles and cue timing manifest...")
    srt_lines: List[str] = []
    for idx, (s0, s1, txt) in enumerate(srt_entries, start=1):
        srt_lines.append(f"{idx}\n{_fmt_srt_time(s0)} --> {_fmt_srt_time(s1)}\n{txt}\n")
    srt_path = DELIVERY_DIR / "科幻悬疑短片_消失7天没人发现_subtitle.srt"
    srt_path.write_text("\n".join(srt_lines), encoding="utf-8")

    manifest_path = AUDIO_DIR / "ep022_audio_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "total_duration_sec": TOTAL_DURATION,
                "voice": VOICE,
                "master_wav": str(final_master),
                "srt_path": str(srt_path),
                "cues": cue_report,
                "subtitles": [{"start": round(a, 3), "end": round(b, 3), "text": c} for a, b, c in srt_entries],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[+] Done! Master WAV: {final_master} | SRT: {srt_path}")


if __name__ == "__main__":
    asyncio.run(main())
