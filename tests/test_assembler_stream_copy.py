import json
import math
import struct
import shutil
import subprocess
import wave
from pathlib import Path

import pytest

from core.episode_assembler import EpisodeAssembler


def test_copy_preserves_b_frame_packets_and_rejects_mismatched_source(tmp_path: Path) -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("requires ffmpeg and ffprobe")
    picture = tmp_path / "picture.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=30:duration=4",
            "-c:v",
            "libx264",
            "-threads",
            "1",
            "-bf",
            "2",
            "-pix_fmt",
            "yuv420p",
            "-color_primaries",
            "bt709",
            "-color_trc",
            "bt709",
            "-colorspace",
            "bt709",
            str(picture),
        ],
        check=True,
    )
    with wave.open(str(tmp_path / "sound.wav"), "wb") as wav:
        wav.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        cycle = struct.pack("<120h", *(round(5000 * math.sin(2 * math.pi * n / 120)) for n in range(120)))
        wav.writeframes(cycle * 1600)  # Four seconds of ordinary, measurable 400 Hz audio.

    spec = {
        "acts": [{"video_path": "picture.mp4"}],
        "audio_path": "sound.wav",
        "output_mp4_path": "master.mp4",
        "width": 320,
        "height": 180,
        "target_fps": 30,
        "copy_video_stream": True,
    }
    spec_path = tmp_path / "episode.json"
    spec_path.write_text(json.dumps(spec))
    master = tmp_path / "master.mp4"
    report = EpisodeAssembler.assemble_from_json(spec_path)
    assert report == {
        "output_mp4": str(master),
        "frames": 120,
        "fps": 30.0,
        "duration_sec": 4.0,
        "act_start_times": [0.0],
    }

    def hashes(path: Path) -> str:
        return subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_packets",
                "-show_entries",
                "packet=data_hash",
                "-show_data_hash",
                "sha256",
                "-of",
                "csv=p=0",
                str(path),
            ],
            text=True,
        )

    original = master.read_bytes()
    assert hashes(master) == hashes(picture)
    spec["width"] = 640
    spec_path.write_text(json.dumps(spec))
    with pytest.raises(ValueError, match="width"):
        EpisodeAssembler.assemble_from_json(spec_path)
    assert master.read_bytes() == original
    assert not list(tmp_path.glob(".assemble-*"))


def test_packet_duration_check_rejects_jitter_even_when_average_rate_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import MagicMock

    from core.episode_assembler import _check_packet_timeline

    # Total duration is 12 ticks for three packets, but each frame must occupy exactly four.
    result = MagicMock()
    result.__enter__.return_value = result
    result.stdout = iter(["pts=0|duration=3\n", "pts=3|duration=5\n", "pts=8|duration=4\n"])
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: result)
    with pytest.raises(ValueError, match="non-CFR"):
        _check_packet_timeline(Path("jitter.mp4"), "v:0", end=12, frame_ticks=4)
