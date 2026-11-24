#!/usr/bin/env python3
"""Mix Episode 023 master stereo audio: Dual-Voice TTS + Procedural SFX + Ducking CC0 BGM (-14.0 LUFS)."""

from __future__ import annotations

import json
import math
import re
import subprocess
import wave
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

PROJ_DIR = Path(__file__).resolve().parent.parent
AUDIO_DIR = PROJ_DIR / "assets" / "audio"
MANIFEST_PATH = AUDIO_DIR / "manifest.json"
BGM_PATH = PROJ_DIR / "assets" / "bgm" / "cc0_upbeat_bgm.wav"
OUT_RAW = AUDIO_DIR / "ep023_mix_raw.wav"
OUT_MASTER = AUDIO_DIR / "ep023_master_48k.wav"
SR = 48000


def load_wav_stereo(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wf:
        ch = wf.getnchannels()
        sr = wf.getframerate()
        sw = wf.getsampwidth()
        n = wf.getnframes()
        raw = wf.readframes(n)
    assert sw == 2, f"Expected 16-bit PCM in {path}, got {sw}"
    arr = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
    if ch == 1:
        arr = np.stack([arr, arr], axis=1)
    else:
        arr = arr.reshape(-1, ch)[:, :2]
    if sr != SR:
        # Linear resample only for mismatched sample-rate BGM fallback (not TTS!)
        new_n = int(round(len(arr) * SR / sr))
        x_old = np.linspace(0, 1, len(arr), endpoint=False)
        x_new = np.linspace(0, 1, new_n, endpoint=False)
        arr = np.stack([np.interp(x_new, x_old, arr[:, 0]), np.interp(x_new, x_old, arr[:, 1])], axis=1)
    return arr


def save_wav_stereo(path: Path, data: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(data, -0.98, 0.98) * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())


def add_clip(bus: np.ndarray, clip: np.ndarray, start_sec: float, gain: float = 1.0) -> None:
    s0 = max(0, int(round(start_sec * SR)))
    if s0 >= len(bus):
        return
    take = min(len(clip), len(bus) - s0)
    bus[s0 : s0 + take] += clip[:take] * gain


def build_looped_bgm(bgm_path: Path, total_samples: int) -> np.ndarray:
    bgm = load_wav_stereo(bgm_path)
    # Normalize BGM RMS gently to ~0.18 baseline before sidechain ducking
    rms = float(np.sqrt(np.mean(bgm**2))) + 1e-9
    bgm = bgm * (0.16 / rms)
    if len(bgm) >= total_samples:
        out = bgm[:total_samples].copy()
    else:
        # Smooth crossfade loop (2.0s crossfade)
        xfade = min(int(2.0 * SR), len(bgm) // 4)
        chunks = [bgm]
        cur_len = len(bgm)
        while cur_len < total_samples + xfade:
            chunks.append(bgm)
            cur_len += len(bgm) - xfade
        out = np.zeros((cur_len, 2), dtype=np.float64)
        pos = 0
        fade_in = np.linspace(0, 1, xfade)[:, None]
        fade_out = 1.0 - fade_in
        for idx, ch in enumerate(chunks):
            if idx == 0:
                out[: len(ch)] = ch
                pos = len(ch) - xfade
            else:
                out[pos : pos + xfade] = out[pos : pos + xfade] * fade_out + ch[:xfade] * fade_in
                rem = len(ch) - xfade
                out[pos + xfade : pos + xfade + rem] = ch[xfade:]
                pos += rem
        out = out[:total_samples]

    # Gentle fade-in (0.4s) & fade-out (1.2s)
    fi = min(int(0.4 * SR), total_samples // 4)
    fo = min(int(1.2 * SR), total_samples // 4)
    out[:fi] *= np.linspace(0.0, 1.0, fi)[:, None]
    out[-fo:] *= np.linspace(1.0, 0.0, fo)[:, None]
    return out


def two_pass_loudnorm(in_wav: Path, out_wav: Path, target_i: float = -14.0, target_tp: float = -1.2) -> Dict[str, Any]:
    p1 = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(in_wav),
            "-af",
            f"loudnorm=I={target_i}:TP={target_tp}:LRA=9:print_format=json",
            "-f",
            "null",
            "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    m = re.search(r"\{[\s\S]*\"input_i\"[\s\S]*\}", p1.stderr)
    assert m, f"Failed to parse loudnorm stats:\n{p1.stderr[-500:]}"
    stats = json.loads(m.group(0))

    af = (
        f"loudnorm=I={target_i}:TP={target_tp}:LRA=9:"
        f"measured_I={stats['input_i']}:measured_LRA={stats['input_lra']}:"
        f"measured_TP={stats['input_tp']}:measured_thresh={stats['input_thresh']}:"
        f"offset={stats['target_offset']}:linear=true"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(in_wav),
            "-af",
            af,
            "-ar",
            str(SR),
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(out_wav),
        ],
        check=True,
    )
    return stats


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    segments: List[Dict[str, Any]] = manifest["segments"]
    sfx_map: Dict[str, str] = manifest["sfx"]

    # Snap total duration to exact 60FPS frame boundary
    exact_frames = int(round(float(manifest["total_duration_sec"]) * 60.0))
    total_dur = exact_frames / 60.0
    total_samples = int(round(total_dur * SR))

    voice_bus = np.zeros((total_samples, 2), dtype=np.float64)
    sfx_bus = np.zeros((total_samples, 2), dtype=np.float64)
    speech_mask = np.zeros(total_samples, dtype=np.float64)

    seg_by_id: Dict[str, Dict[str, Any]] = {}
    for seg in segments:
        seg_by_id[seg["id"]] = seg
        wav = load_wav_stereo(Path(seg["wav_path"]))
        # Normalize each spoken line gently so creator and warden sit at balanced broadcast level
        rms = float(np.sqrt(np.mean(wav**2))) + 1e-9
        target_rms = 0.23 if seg["speaker"] == "warden" else 0.21
        wav = wav * min(2.2, target_rms / rms)
        add_clip(voice_bus, wav, float(seg["start_sec"]), gain=1.0)
        s0 = max(0, int(round((float(seg["start_sec"]) - 0.12) * SR)))
        s1 = min(total_samples, int(round((float(seg["end_sec"]) + 0.18) * SR)))
        speech_mask[s0:s1] = 1.0

    # Place crisp synced SFX events
    sfx_clips = {k: load_wav_stereo(Path(v)) for k, v in sfx_map.items()}
    events: List[Tuple[str, float, float]] = [
        ("whoosh", seg_by_id["s02_hook_reveal"]["start_sec"] - 0.25, 0.55),
        ("whoosh", seg_by_id["s03_tech_arch"]["start_sec"] - 0.28, 0.55),
        ("ui_click", seg_by_id["s04_tech_detect"]["start_sec"] - 0.15, 0.65),
        ("ui_click", seg_by_id["s05_tech_roast"]["start_sec"] - 0.15, 0.65),
        ("whoosh", seg_by_id["s06_demo_start"]["start_sec"] - 0.30, 0.55),
        ("ui_click", seg_by_id["s06_demo_start"]["start_sec"] + 1.80, 0.80),
        ("ui_click", seg_by_id["s06_demo_start"]["start_sec"] + 3.10, 0.80),
        ("ui_click", seg_by_id["s07_demo_switch1"]["start_sec"] + 0.80, 0.85),
        ("countdown_321", seg_by_id["s08_warden_lv1"]["start_sec"] - 1.15, 0.80),
        ("lv1_chime", seg_by_id["s08_warden_lv1"]["start_sec"] - 0.35, 0.85),
        ("ui_click", seg_by_id["s09_demo_switch2"]["start_sec"] + 2.60, 0.85),
        ("lv2_alert", seg_by_id["s10_warden_lv2"]["start_sec"] - 0.78, 0.85),
        ("ui_click", seg_by_id["s11_demo_switch3"]["start_sec"] + 3.20, 0.85),
        ("lv3_siren", seg_by_id["s12_warden_lv3"]["start_sec"] - 0.85, 0.82),
        ("receipt_printer", seg_by_id["s13_demo_receipt"]["start_sec"] - 0.68, 0.82),
        ("whoosh", seg_by_id["s14_opensource"]["start_sec"] - 0.30, 0.55),
        ("ui_click", seg_by_id["s14_opensource"]["start_sec"] + 2.20, 0.70),
        ("whoosh", seg_by_id["s15_outro_cta"]["start_sec"] - 0.25, 0.50),
    ]
    for name, ts, gain in events:
        add_clip(sfx_bus, sfx_clips[name], ts, gain=gain)

    # Smooth O(N) boxcar sidechain ducking envelope for CC0 BGM (0.28s smoothing, <0.02s runtime!)
    win = int(0.28 * SR)
    pad = win // 2
    padded = np.pad(speech_mask, (pad, win - pad), mode="edge")
    csum = np.cumsum(padded, dtype=np.float64)
    duck_env = (csum[win:] - csum[:-win]) / float(win)
    duck_env = duck_env[:total_samples]
    bgm_gain = 0.52 * (1.0 - duck_env) + 0.16 * duck_env

    assert BGM_PATH.exists(), f"Missing fetched CC0 BGM WAV: {BGM_PATH}"
    bgm_bus = build_looped_bgm(BGM_PATH, total_samples) * bgm_gain[:, None]

    mix = voice_bus + sfx_bus * 0.78 + bgm_bus
    # Soft safety limiter before loudnorm
    peak = float(np.max(np.abs(mix))) + 1e-9
    if peak > 0.92:
        mix = mix * (0.92 / peak)

    save_wav_stereo(OUT_RAW, mix)
    stats = two_pass_loudnorm(OUT_RAW, OUT_MASTER, target_i=-14.0, target_tp=-1.2)

    # Save exact synced frame count back to manifest
    manifest["exact_frames_60fps"] = exact_frames
    manifest["exact_duration_sec"] = round(total_dur, 6)
    manifest["master_audio_path"] = str(OUT_MASTER)
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Master audio mixed: {OUT_MASTER} | dur={total_dur:.3f}s ({exact_frames} frames @60fps)")
    print(f"Loudnorm input stats: I={stats['input_i']} LUFS, TP={stats['input_tp']} dBTP -> target -14.0 LUFS / -1.2 dBTP")


if __name__ == "__main__":
    main()
