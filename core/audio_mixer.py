"""Copyright-safe procedural BGM synthesizer, studio SFX generator, and sidechain voice mixer.

Eliminates dry dead-air voiceovers that trigger early viewer bounce and low audio
Content Enjoyment (CE) / Production Complexity (PC) scores by layering:
1. Warm ambient cyber-lofi chord pads & subtle pulse (intentionally carved away from
   the 1-4 kHz vocal intelligibility band).
2. Crisp holographic scene-transition whooshes and progressive card-spotlight chimes.
3. Smooth sidechain ducking driven directly by the speech envelope.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

SAMPLE_RATE = 48000

# Warm Cmaj9 -> Am9 -> Fmaj9 -> G13 ambient chord voicings (fundamental frequencies in Hz)
_CHORD_PROGRESSION: List[Tuple[float, Tuple[float, ...]]] = [
    (65.41, (130.81, 196.00, 246.94, 293.66, 329.63)),  # Cmaj9
    (55.00, (110.00, 164.81, 220.00, 246.94, 311.13)),  # Am9 (warm color)
    (87.31, (174.61, 220.00, 261.63, 329.63, 392.00)),  # Fmaj9
    (98.00, (146.83, 196.00, 246.94, 329.63, 440.00)),  # G6/13
]


def _decode_audio_stereo_f32(audio_path: Path, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Decodes an MP3/WAV/MP4 media file to float32 stereo PCM shaped (N, 2)."""
    audio_path = Path(audio_path)
    if audio_path.suffix.lower() == ".wav":
        try:
            with wave.open(str(audio_path), "rb") as wf:
                if wf.getframerate() == sample_rate and wf.getnchannels() == 2 and wf.getsampwidth() == 2:
                    raw = wf.readframes(wf.getnframes())
                    arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                    return arr.reshape(-1, 2)
        except Exception:
            pass

    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required to decode non-WAV audio streams")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_wav = Path(tmpdir) / "decoded.wav"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(audio_path),
                "-vn",
                "-ac",
                "2",
                "-ar",
                str(sample_rate),
                "-sample_fmt",
                "s16",
                str(tmp_wav),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        with wave.open(str(tmp_wav), "rb") as wf:
            raw = wf.readframes(wf.getnframes())
            arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if arr.size == 0:
        return np.zeros((sample_rate, 2), dtype=np.float32)
    return arr.reshape(-1, 2)


def _encode_stereo_f32(samples: np.ndarray, output_path: Path, sample_rate: int = SAMPLE_RATE) -> Path:
    """Encodes (N, 2) float32 PCM samples to WAV or 192kbps MP3."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pcm16 = (np.clip(samples, -1.0, 1.0) * 32767.0).astype(np.int16)

    if output_path.suffix.lower() == ".wav":
        with wave.open(str(output_path), "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm16.tobytes())
        return output_path

    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required to encode compressed audio formats")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_wav = Path(tmpdir) / "mix.wav"
        with wave.open(str(tmp_wav), "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm16.tobytes())
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(tmp_wav),
                "-ac",
                "2",
                "-ar",
                str(sample_rate),
                "-c:a",
                "libmp3lame",
                "-b:a",
                "192k",
                str(output_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
    return output_path


def synthesize_cyber_lofi_bgm(duration_sec: float, sample_rate: int = SAMPLE_RATE, bpm: float = 88.0) -> np.ndarray:
    """Synthesizes copyright-free stereo cyber-lofi ambient BGM carved away from the vocal band."""
    n_samples = max(1, int(round(max(0.5, duration_sec) * sample_rate)))
    t = np.arange(n_samples, dtype=np.float32) / float(sample_rate)

    beat_dur = 60.0 / bpm
    bar_dur = 4.0 * beat_dur
    n_chords = len(_CHORD_PROGRESSION)

    left = np.zeros(n_samples, dtype=np.float32)
    right = np.zeros(n_samples, dtype=np.float32)

    bar_idx_arr = (t / bar_dur).astype(np.int32)
    bar_phase = (t % bar_dur) / bar_dur  # 0..1 within each bar

    # Smooth bar-level pad envelope so chord changes breathe organically
    pad_env = np.sin(np.clip(bar_phase, 0.0, 1.0) * np.pi) ** 0.35

    for c_i, (bass_hz, voices) in enumerate(_CHORD_PROGRESSION):
        mask = (bar_idx_arr % n_chords) == c_i
        if not np.any(mask):
            continue
        t_c = t[mask]
        env_c = pad_env[mask]

        # Warm rounded sub-bass with gentle beat-synced pulse
        beat_phase = (t_c % beat_dur) / beat_dur
        bass_pulse = 0.55 + 0.45 * np.exp(-3.2 * beat_phase)
        bass = np.sin(2.0 * np.pi * bass_hz * t_c) * 0.24 * bass_pulse
        left[mask] += bass
        right[mask] += bass

        # Gentle detuned stereo synth pad + pluck arpeggio notes (< 880Hz so voice clarity is untouched)
        for v_i, freq in enumerate(voices):
            pan_l = 0.65 - 0.08 * (v_i % 4) if (v_i % 2 == 0) else 0.35 + 0.08 * (v_i % 4)
            pan_r = 1.0 - pan_l
            osc = 0.72 * np.sin(2.0 * np.pi * freq * t_c) + 0.16 * np.sin(2.0 * np.pi * (freq * 1.003) * t_c)
            sig = osc * env_c * 0.075
            left[mask] += sig * pan_l
            right[mask] += sig * pan_r

            # Soft Rhodes-style arp shimmer on 8th beats inside each bar
            sub_idx = v_i % len(voices)
            arp_start = sub_idx * (beat_dur * 0.5)
            local_t = t_c % bar_dur
            note_dt = np.maximum(0.0, local_t - arp_start)
            arp_env = np.where(local_t >= arp_start, np.exp(-3.8 * note_dt), 0.0).astype(np.float32)
            arp_osc = np.sin(2.0 * np.pi * (freq * 2.0) * t_c) * 0.045 * arp_env
            left[mask] += arp_osc * pan_r
            right[mask] += arp_osc * pan_l

    # Ultra-soft airy cyber hi-hat brushed pulse (> 5.5 kHz, keeps 1-4 kHz clear)
    rng = np.random.default_rng(42)
    noise = rng.standard_normal(n_samples).astype(np.float32)
    # 1st-order high-pass differentiator emphasizes crisp high frequencies without harshness
    hp_noise = np.concatenate([[0.0], np.diff(noise)]) * 0.18
    eighth_dur = beat_dur * 0.5
    eighth_phase = (t % eighth_dur) / eighth_dur
    hat_env = np.exp(-18.0 * eighth_phase).astype(np.float32)
    hat_sig = hp_noise * hat_env * 0.045
    left += hat_sig * (0.85 + 0.15 * np.sin(t * 1.7))
    right += hat_sig * (0.85 - 0.15 * np.sin(t * 1.7))

    # Global fade-in (0.2s) and fade-out (0.6s)
    fade_in_n = min(n_samples, int(0.20 * sample_rate))
    fade_out_n = min(n_samples, int(0.60 * sample_rate))
    if fade_in_n > 1:
        fi = np.linspace(0.0, 1.0, fade_in_n, dtype=np.float32)
        left[:fade_in_n] *= fi
        right[:fade_in_n] *= fi
    if fade_out_n > 1:
        fo = np.linspace(1.0, 0.0, fade_out_n, dtype=np.float32)
        left[-fade_out_n:] *= fo
        right[-fade_out_n:] *= fo

    stereo = np.stack([left, right], axis=-1)
    peak = float(np.max(np.abs(stereo))) if stereo.size else 1.0
    if peak > 1e-5:
        stereo = stereo / peak
    return stereo.astype(np.float32)


def _add_bell_chime(
    buf: np.ndarray,
    start_sec: float,
    freqs: Sequence[float],
    dur_sec: float,
    amp: float,
    sample_rate: int = SAMPLE_RATE,
) -> None:
    """Adds a silky glass/hologram harmonic chime burst into stereo buffer `buf`."""
    i0 = max(0, int(round(start_sec * sample_rate)))
    length = min(buf.shape[0] - i0, int(round(dur_sec * sample_rate)))
    if length <= 16:
        return
    lt = np.arange(length, dtype=np.float32) / float(sample_rate)
    attack = np.minimum(1.0, lt / 0.008)
    decay = np.exp(-5.5 * (lt / max(0.08, dur_sec)))
    env = (attack * decay).astype(np.float32)

    wave_sig = np.zeros(length, dtype=np.float32)
    for k, hz in enumerate(freqs):
        wave_sig += (0.68**k) * np.sin(2.0 * np.pi * float(hz) * lt)
    wave_sig = wave_sig * env * float(amp)
    buf[i0 : i0 + length, 0] += wave_sig * 0.94
    buf[i0 : i0 + length, 1] += wave_sig * 1.06


def synthesize_studio_sfx(
    scenes: Optional[List[Dict[str, Any]]],
    duration_sec: float,
    sample_rate: int = SAMPLE_RATE,
) -> np.ndarray:
    """Places subtle cold-open hook chimes, scene whooshes, and card-spotlight ticks."""
    n_samples = max(1, int(round(max(0.5, duration_sec) * sample_rate)))
    sfx = np.zeros((n_samples, 2), dtype=np.float32)

    # 1. Signature crisp opening chord chime at t=0.02s for instant 0.5s audio hook
    _add_bell_chime(sfx, start_sec=0.02, freqs=(523.25, 659.25, 783.99, 1046.50), dur_sec=0.55, amp=0.22)

    if not scenes:
        return sfx

    for idx, sc in enumerate(scenes):
        st = float(sc.get("start", 0.0))
        en = float(sc.get("end", st))
        sc_dur = max(0.0, en - st)

        # Scene transition holographic shimmer on cuts (Act 2+)
        if idx > 0:
            _add_bell_chime(sfx, start_sec=max(0.0, st - 0.04), freqs=(440.0, 659.25, 880.0), dur_sec=0.42, amp=0.18)

        # Gentle progressive card-spotlight ticks at 1/3 and 2/3 of each scene
        if sc_dur >= 6.0:
            for step_frac, root_hz in ((1.0 / 3.0, 587.33), (2.0 / 3.0, 659.25)):
                _add_bell_chime(
                    sfx,
                    start_sec=st + sc_dur * step_frac,
                    freqs=(root_hz, root_hz * 1.5),
                    dur_sec=0.16,
                    amp=0.11,
                )

    peak = float(np.max(np.abs(sfx))) if sfx.size else 1.0
    if peak > 1e-5:
        sfx = sfx / max(peak, 1.0)
    return sfx.astype(np.float32)


def _box_smooth_1d(arr: np.ndarray, win: int) -> np.ndarray:
    """Computes O(N) centered uniform moving average matching `np.convolve(..., mode='same')`."""
    if win <= 1 or arr.size == 0:
        return arr.astype(np.float32, copy=False)
    n = arr.size
    pad_left = win // 2
    pad_right = win - 1 - pad_left
    padded = np.pad(arr, (pad_left, pad_right), mode="constant", constant_values=0.0)
    csum = np.empty(padded.size + 1, dtype=np.float64)
    csum[0] = 0.0
    np.cumsum(padded, dtype=np.float64, out=csum[1:])
    return ((csum[win : win + n] - csum[:n]) / float(win)).astype(np.float32)


def _compute_speech_activity_envelope(
    voice_stereo: np.ndarray,
    sample_rate: int = SAMPLE_RATE,
) -> np.ndarray:
    """Computes a smooth 0..1 vocal activity curve for sidechain ducking."""
    mono = 0.5 * (voice_stereo[:, 0] + voice_stereo[:, 1])
    abs_m = np.abs(mono)

    # Smooth over 80ms windows via O(N) prefix-sum filter, then fast-attack / gentle-release
    win = max(1, int(0.08 * sample_rate))
    fast_env = _box_smooth_1d(abs_m, win)

    rel_win = max(1, int(0.35 * sample_rate))
    broad_env = _box_smooth_1d(fast_env, rel_win)

    env = np.maximum(fast_env, broad_env * 0.92)
    ref = float(np.percentile(env, 92)) + 1e-6
    activity = np.clip(env / (0.35 * ref), 0.0, 1.0).astype(np.float32)
    return activity


def mix_voice_with_bgm_and_sfx(
    voice_mp3: Path,
    output_mp3: Path,
    scenes: Optional[List[Dict[str, Any]]] = None,
    bgm_db: float = -20.5,
    duck_db: float = -8.0,
    sfx_db: float = -17.5,
    sample_rate: int = SAMPLE_RATE,
) -> Path:
    """Mixes voiceover with procedural cyber-lofi BGM + SFX using smooth sidechain ducking."""
    voice = _decode_audio_stereo_f32(voice_mp3, sample_rate=sample_rate)
    n_samples = voice.shape[0]
    dur_sec = n_samples / float(sample_rate)

    bgm = synthesize_cyber_lofi_bgm(duration_sec=dur_sec, sample_rate=sample_rate)[:n_samples]
    sfx = synthesize_studio_sfx(scenes=scenes, duration_sec=dur_sec, sample_rate=sample_rate)[:n_samples]

    activity = _compute_speech_activity_envelope(voice, sample_rate=sample_rate)
    bgm_base_gain = 10.0 ** (bgm_db / 20.0)
    duck_factor = 10.0 ** (duck_db / 20.0)
    bgm_gain = bgm_base_gain * (1.0 - activity * (1.0 - duck_factor))

    sfx_gain = 10.0 ** (sfx_db / 20.0)
    mixed = voice + bgm * bgm_gain[:, None] + sfx * sfx_gain
    del voice, bgm, sfx, activity, bgm_gain

    # Soft analog limiting to protect transients without squashing dynamic warmth
    mixed = (np.tanh(mixed * 1.02) / np.tanh(1.02)).astype(np.float32)
    peak = float(np.max(np.abs(mixed))) if mixed.size else 1.0
    if peak > 0.94:
        mixed = mixed * (0.94 / peak)

    return _encode_stereo_f32(mixed, output_mp3, sample_rate=sample_rate)
