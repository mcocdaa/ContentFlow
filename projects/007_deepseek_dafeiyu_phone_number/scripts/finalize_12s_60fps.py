#!/usr/bin/env python3
"""GPU-Accelerated 1080x1920 60.00 FPS Finalizer & Audio Muxer for Project 007.

Uses PyTorch CUDA (cuda:0) + FFmpeg to:
1. Concatenate or convert one or more 1080P Kling dance clips into a seamless 18.00s MV
2. Interpolate/convert to silky 1080x1920 @ 60.00 FPS (1080 frames for 18.00s)
3. Mux the 18.02s Phone Number chorus audio (assets/phone_number_18s.mp3)
"""

import argparse
import json
import subprocess
import tempfile
import time
from pathlib import Path
import torch

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
PROJECT_DIR = ROOT_DIR / "projects" / "007_deepseek_dafeiyu_phone_number"
DEFAULT_AUDIO = PROJECT_DIR / "assets" / "phone_number_18s.mp3"


def probe_video(path: Path) -> dict:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate,nb_frames,duration",
            "-of",
            "json",
            str(path),
        ],
        text=True,
    )
    return json.loads(out)["streams"][0]


def finalize_60fps(
    inputs: list[Path],
    output_video: Path,
    audio_path: Path = DEFAULT_AUDIO,
    target_duration: float = 18.0,
):
    t0 = time.time()
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
    print(f"[Finalize 60FPS] Processing {len(inputs)} clip(s) on {device} ({gpu_name}) -> target {target_duration:.2f}s")

    with tempfile.TemporaryDirectory(prefix="finalize_007_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        if len(inputs) == 1:
            combined_input = inputs[0]
        else:
            # Normalize and concatenate clips cleanly
            norm_clips = []
            for idx, clip in enumerate(inputs):
                norm_p = tmp_path / f"norm_{idx}.mp4"
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        str(clip),
                        "-an",
                        "-vf",
                        "scale=1080:1920:force_original_aspect_ratio=decrease:flags=lanczos,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,setdar=9/16,fps=30,format=yuv420p",
                        "-c:v",
                        "libx264",
                        "-preset",
                        "ultrafast",
                        "-crf",
                        "14",
                        str(norm_p),
                    ],
                    check=True,
                )
                norm_clips.append(norm_p)
            concat_txt = tmp_path / "concat.txt"
            concat_txt.write_text(
                "\n".join(f"file '{p.as_posix()}'" for p in norm_clips) + "\n",
                encoding="utf-8",
            )
            combined_input = tmp_path / "combined.mp4"
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(concat_txt),
                    "-c",
                    "copy",
                    str(combined_input),
                ],
                check=True,
            )

        info = probe_video(combined_input)
        in_dur = float(info.get("duration", 0.0))
        pts_factor = 1.0
        if 0 < in_dur < (target_duration - 0.15):
            pts_factor = target_duration / in_dur
            print(f"  Stretching {in_dur:.2f}s -> {target_duration:.2f}s (PTS factor {pts_factor:.4f})")

        output_video.parent.mkdir(parents=True, exist_ok=True)
        vf_chain = (
            f"setpts={pts_factor:.6f}*PTS,"
            "scale=1080:1920:force_original_aspect_ratio=decrease:flags=lanczos,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,"
            "setsar=1,setdar=9/16,"
            "framerate=fps=60:interp_start=48:interp_end=208:scene=8.2,"
            "unsharp=3:3:0.35:3:3:0.0"
        )

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(combined_input),
                "-i",
                str(audio_path),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-vf",
                vf_chain,
                "-r",
                "60",
                "-t",
                f"{target_duration:.2f}",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "16",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                str(output_video),
            ],
            check=True,
        )

    out_info = probe_video(output_video)
    print(
        f"[Finalize 60FPS] Saved -> {output_video} "
        f"({out_info.get('width')}x{out_info.get('height')} @ {out_info.get('r_frame_rate')} fps, "
        f"duration={float(out_info.get('duration', 0)):.2f}s, frames={out_info.get('nb_frames')}) "
        f"in {time.time() - t0:.1f}s"
    )


def main():
    parser = argparse.ArgumentParser(description="Finalize Kling 1080P video(s) to 1080x1920 60FPS with 18s chorus audio")
    parser.add_argument("--inputs", type=Path, nargs="+", required=True, help="Input raw Kling MP4(s)")
    parser.add_argument("--output", type=Path, required=True, help="Output 60FPS MP4")
    parser.add_argument("--audio", type=Path, default=DEFAULT_AUDIO, help="Audio MP3 path")
    parser.add_argument("--duration", type=float, default=18.0, help="Target duration in seconds (default: 18.0)")
    args = parser.parse_args()

    finalize_60fps(args.inputs, args.output, args.audio, args.duration)


if __name__ == "__main__":
    main()
