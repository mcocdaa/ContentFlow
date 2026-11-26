"""Voice timed HTML cues with local Kokoro. Run with python -m scripts.narrate_motion_cards."""

import argparse
import hashlib
import json
import wave
from pathlib import Path

import numpy as np
import torch

from core.local_tts import LocalNeuralTTS, format_srt_timestamp


def render(project: Path, duration: float, voice: str) -> None:
    source = project / "design/episode"
    cues = json.loads((source / "narration.json").read_text())
    cache = project / "output/speech"
    cache.mkdir(parents=True, exist_ok=True)
    tts = LocalNeuralTTS(device="cpu")
    rate = tts.sample_rate
    track = np.zeros(round(duration * rate), dtype="<i2")
    subtitles = []
    overruns = []
    try:
        for index, cue in enumerate(cues):
            text = cue.get("spoken", cue["text"])
            start, stop = cue["start"], cue["end"]
            previous_end = cues[index - 1]["end"] if index else 0
            if not previous_end <= start < stop <= duration:
                raise ValueError(f"Invalid timing for cue {index + 1}")
            speed = 1.00
            while True:
                key = hashlib.sha256(f"{voice}/{speed:.3f}/{text}".encode()).hexdigest()
                chunk = cache / f"{key}.npy"
                if chunk.exists():
                    samples = np.load(chunk)
                else:
                    samples = tts._synth_kokoro(text, voice, speed)
                    np.save(chunk, samples)
                seconds = len(samples) / rate
                if seconds <= stop - start or speed >= 1.18:
                    break
                speed = min(1.18, max(speed + 0.04, speed * seconds / (stop - start) * 1.015))
            if seconds > stop - start:
                overruns.append(f"{index + 1}: {seconds:.2f}s for {stop - start:.2f}s")
                continue
            begin = round(start * rate)
            track[begin : begin + len(samples)] = np.rint(np.clip(samples, -1, 1) * 30000).astype("<i2")
            subtitles.append(
                f"{index + 1}\n{format_srt_timestamp(start)} --> {format_srt_timestamp(start + seconds)}\n{cue['text']}\n"
            )
            print(f"Cue {index + 1} fits at {seconds:.2f}s", flush=True)
    finally:
        tts.close()
    if overruns:
        raise ValueError("Shorten these cues: " + ", ".join(overruns))
    dest = source / "assets"
    dest.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dest / "episode.wav"), "wb") as wav:
        wav.setparams((2, 2, rate, 0, "NONE", "not compressed"))
        wav.writeframes(np.repeat(track, 2).tobytes())
    (dest / "episode.srt").write_text("\n".join(subtitles), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("duration", type=float)
    parser.add_argument("--voice", default="zf_001")
    args = parser.parse_args()
    torch.set_num_threads(3)
    render(args.project, args.duration, args.voice)
