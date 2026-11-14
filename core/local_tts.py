"""Local Neural TTS engine for ContentFlow using Kokoro-82M-v1.1-zh with edge-tts fallback.

Synthesizes natural Mandarin speech with English tech-term support on local GPU/CPU,
concatenates scene tracks with controlled breath pauses, encodes 48kHz stereo MP3 audio,
and outputs frame-accurate SRT subtitles + act timeline boundaries.
"""

from __future__ import annotations

import asyncio
import logging
import re
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_KOKORO_REPO = "hexgrad/Kokoro-82M-v1.1-zh"
KOKORO_SAMPLE_RATE = 24000


def format_srt_timestamp(seconds: float) -> str:
    """Formats fractional seconds as SRT timestamp `HH:MM:SS,mmm`."""
    total_ms = max(0, int(round(seconds * 1000.0)))
    ms = total_ms % 1000
    total_s = total_ms // 1000
    s = total_s % 60
    total_m = total_s // 60
    m = total_m % 60
    h = total_m // 60
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _split_subtitle_cues(
    subtitle_text: str, start: float, end: float, max_chars: int = 24
) -> List[Tuple[float, float, str]]:
    """Splits a scene subtitle into short readable timed captions proportional to text length."""
    text = re.sub(r"\s+", " ", subtitle_text).strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [(start, end, text)]

    # Split on Chinese/English sentence & clause punctuation first
    raw_parts = [p.strip() for p in re.split(r"(?<=[，。！？；：,!?;])", text) if p.strip()]
    merged: List[str] = []
    cur = ""
    for part in raw_parts:
        clean_part = part.rstrip("，。！？；：,!?;") if len(merged) >= 0 else part
        if cur and len(cur) + len(clean_part) > max_chars:
            merged.append(cur.rstrip("，。；：,;"))
            cur = clean_part
        else:
            cur = f"{cur}{clean_part}"
    if cur:
        merged.append(cur.rstrip("，。；：,;"))

    if not merged:
        merged = [text]

    total_chars = max(1, sum(len(m) for m in merged))
    dur = max(0.2, end - start)
    cues: List[Tuple[float, float, str]] = []
    t_cur = start
    for idx, chunk in enumerate(merged):
        frac = len(chunk) / float(total_chars)
        t_next = end if idx == len(merged) - 1 else min(end, t_cur + dur * frac)
        cues.append((t_cur, max(t_cur + 0.15, t_next), chunk))
        t_cur = t_next
    return cues


class LocalNeuralTTS:
    """Zero-quota local neural TTS synthesizer backed by Kokoro-82M-v1.1-zh + edge-tts fallback."""

    def __init__(
        self,
        repo_id: str = DEFAULT_KOKORO_REPO,
        sample_rate: int = KOKORO_SAMPLE_RATE,
        device: Optional[str] = None,
    ) -> None:
        self.repo_id = repo_id
        self.sample_rate = sample_rate
        self.device = device
        self._pipelines: Dict[str, Any] = {}

    def _get_kokoro_pipeline(self, lang_code: str = "z") -> Any:
        if lang_code not in self._pipelines:
            from kokoro import KPipeline

            en_callable = None
            if lang_code == "z":
                try:
                    from misaki import en

                    en_g2p = en.G2P(trf=False, british=False)

                    def _en_fn(txt: str) -> str:
                        res = en_g2p(txt)[0]
                        return str(res) if res else ""

                    en_callable = _en_fn
                except Exception:
                    en_callable = None

            kwargs: Dict[str, Any] = {"lang_code": lang_code, "repo_id": self.repo_id}
            if en_callable is not None:
                kwargs["en_callable"] = en_callable
            if self.device:
                kwargs["device"] = self.device
            self._pipelines[lang_code] = KPipeline(**kwargs)
        return self._pipelines[lang_code]

    def _synth_kokoro(self, text: str, voice: str, speed: float) -> np.ndarray:
        pipeline = self._get_kokoro_pipeline("z")
        chunks: List[np.ndarray] = []
        for _gs, _ps, audio in pipeline(text, voice=voice, speed=speed, split_pattern=r"[。！？!?；;\n]+"):
            if audio is not None:
                arr = np.asarray(audio, dtype=np.float32).reshape(-1)
                if arr.size > 0:
                    chunks.append(arr)
        if not chunks:
            raise RuntimeError(f"Kokoro returned empty audio for text: {text[:40]!r}")
        combined = np.concatenate(chunks)
        # Trim leading/trailing near-silence so scene cuts stay snappy
        thresh = 0.008
        active = np.where(np.abs(combined) > thresh)[0]
        if active.size > 0:
            i0 = max(0, int(active[0]) - int(0.05 * self.sample_rate))
            i1 = min(combined.size, int(active[-1]) + int(0.08 * self.sample_rate))
            combined = combined[i0:i1]
        return combined

    def _synth_edge_tts(self, text: str, edge_voice: str, speed: float) -> np.ndarray:
        import edge_tts

        rate_pct = int(round((speed - 1.0) * 100.0))
        rate_str = f"{rate_pct:+d}%"

        async def _run(mp3_path: Path) -> None:
            comm = edge_tts.Communicate(text, voice=edge_voice, rate=rate_str)
            await comm.save(str(mp3_path))

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_mp3 = Path(tmpdir) / "edge.mp3"
            tmp_wav = Path(tmpdir) / "edge.wav"
            asyncio.run(_run(tmp_mp3))
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(tmp_mp3), "-ac", "1", "-ar", str(self.sample_rate), str(tmp_wav)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            with wave.open(str(tmp_wav), "rb") as wf:
                raw = wf.readframes(wf.getnframes())
            return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

    def synthesize_text(
        self,
        text: str,
        voice: str = "zf_001",
        speed: float = 1.03,
        edge_voice: str = "zh-CN-XiaoxiaoNeural",
    ) -> np.ndarray:
        """Synthesizes a single utterance into a mono float32 numpy waveform at `self.sample_rate`."""
        try:
            return self._synth_kokoro(text, voice=voice, speed=speed)
        except Exception as exc:
            logger.warning("Kokoro TTS failed (%s); falling back to edge-tts (%s)", exc, edge_voice)
            return self._synth_edge_tts(text, edge_voice=edge_voice, speed=speed)

    def synthesize_scenes(
        self,
        scenes: List[Dict[str, str]],
        output_mp3: Path,
        output_srt: Path,
        voice: str = "zf_001",
        speed: float = 1.03,
        pause_sec: float = 0.22,
        tail_pad_sec: float = 0.30,
        edge_voice: str = "zh-CN-XiaoxiaoNeural",
    ) -> List[Dict[str, Any]]:
        """Synthesizes multi-scene audio MP3 + SRT captions and returns exact scene timestamps."""
        if not scenes:
            raise ValueError("scenes list must not be empty")

        output_mp3 = Path(output_mp3)
        output_srt = Path(output_srt)
        output_mp3.parent.mkdir(parents=True, exist_ok=True)
        output_srt.parent.mkdir(parents=True, exist_ok=True)

        pause_samples = int(round(pause_sec * self.sample_rate))
        tail_samples = int(round(tail_pad_sec * self.sample_rate))
        lead_samples = int(round(0.10 * self.sample_rate))

        audio_parts: List[np.ndarray] = [np.zeros(lead_samples, dtype=np.float32)]
        cursor_sec = lead_samples / float(self.sample_rate)
        timeline: List[Dict[str, Any]] = []
        srt_lines: List[str] = []
        cue_idx = 1

        for idx, sc in enumerate(scenes):
            tts_text = str(sc.get("tts_text") or sc.get("subtitle_text") or "").strip()
            sub_text = str(sc.get("subtitle_text") or sc.get("tts_text") or "").strip()
            wav_samples = self.synthesize_text(tts_text, voice=voice, speed=speed, edge_voice=edge_voice)

            # Peak-normalize each segment gently so loudness stays uniform across acts
            peak = float(np.max(np.abs(wav_samples))) if wav_samples.size else 1.0
            if peak > 1e-4:
                wav_samples = np.clip(wav_samples * (0.88 / peak), -0.98, 0.98)

            speech_dur = wav_samples.size / float(self.sample_rate)
            act_start = 0.0 if idx == 0 else cursor_sec
            speech_start = cursor_sec
            speech_end = cursor_sec + speech_dur

            audio_parts.append(wav_samples)
            if idx < len(scenes) - 1:
                pad_len = pause_samples
                act_end = speech_end + pause_sec
            else:
                pad_len = tail_samples
                act_end = speech_end + tail_pad_sec

            audio_parts.append(np.zeros(pad_len, dtype=np.float32))
            cursor_sec = act_end

            timeline.append(
                {
                    "index": idx + 1,
                    "start": round(act_start, 3),
                    "end": round(act_end, 3),
                    "duration": round(act_end - act_start, 3),
                    "speech_duration": round(speech_dur, 3),
                    "subtitle_text": sub_text,
                }
            )

            for c_start, c_end, c_text in _split_subtitle_cues(sub_text, speech_start, speech_end):
                srt_lines.append(str(cue_idx))
                srt_lines.append(f"{format_srt_timestamp(c_start)} --> {format_srt_timestamp(c_end)}")
                srt_lines.append(c_text)
                srt_lines.append("")
                cue_idx += 1

        master_wav = np.concatenate(audio_parts)
        pcm16 = (np.clip(master_wav, -1.0, 1.0) * 32767.0).astype(np.int16)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_wav = Path(tmpdir) / "master.wav"
            with wave.open(str(tmp_wav), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
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
                    "48000",
                    "-c:a",
                    "libmp3lame",
                    "-b:a",
                    "192k",
                    str(output_mp3),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )

        output_srt.write_text("\n".join(srt_lines), encoding="utf-8")
        return timeline
