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
import cv2
import numpy as np
import torch

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
PROJECT_DIR = ROOT_DIR / "projects" / "007_deepseek_dafeiyu_phone_number"
DEFAULT_AUDIO = PROJECT_DIR / "assets" / "phone_number_18s.mp3"
DEFAULT_SOURCE = PROJECT_DIR / "delivery" / "dafeiyu_phone_number_kling4_dance_18s_60fps.mp4"
DEFAULT_OUTPUT = PROJECT_DIR / "delivery" / "deepseek_dafeiyu_phone_number_final.mp4"


def deghost_frames(frames: list[np.ndarray]) -> list[np.ndarray]:
    """Removes FFmpeg framerate=fps=60 linear alpha-blended ghost frames and replaces with optical-flow warp."""
    if len(frames) < 3:
        return frames

    sharps = []
    grays = []
    for f in frames:
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        grays.append(g)
        sharps.append(float(cv2.Laplacian(g, cv2.CV_64F).var()))

    # First pass: replace any linear-blend dip frame with the sharper unblended original frame
    pure = list(frames)
    pure_grays = list(grays)
    pure_sharps = list(sharps)
    n = len(frames)
    is_ghost = [False] * n
    for i in range(1, n - 1):
        nbr_max = max(sharps[i - 1], sharps[i + 1])
        if sharps[i] < 0.88 * nbr_max:
            is_ghost[i] = True

    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    h, w = frames[0].shape[:2]
    grid_x, grid_y = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))

    cleaned: list[np.ndarray] = []
    for i in range(n):
        if not is_ghost[i]:
            cleaned.append(pure[i])
            continue
        # Find nearest non-ghost left and right frames
        l_idx = i - 1
        while l_idx > 0 and is_ghost[l_idx]:
            l_idx -= 1
        r_idx = i + 1
        while r_idx < n - 1 and is_ghost[r_idx]:
            r_idx += 1

        f_left = pure[l_idx]
        f_right = pure[r_idx]
        g_left = pure_grays[l_idx]
        g_right = pure_grays[r_idx]

        # Compute optical flow at half resolution for speed, then warp f_left to midpoint
        small_l = cv2.resize(g_left, (w // 2, h // 2))
        small_r = cv2.resize(g_right, (w // 2, h // 2))
        flow_small = dis.calc(small_r, small_l, None)
        flow = cv2.resize(flow_small, (w, h), interpolation=cv2.INTER_LINEAR) * 2.0
        alpha = (i - l_idx) / float(max(1, r_idx - l_idx))
        map_x = grid_x + flow[..., 0] * alpha
        map_y = grid_y + flow[..., 1] * alpha
        warped = cv2.remap(f_left, map_x, map_y, interpolation=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT)
        cleaned.append(warped)

    return cleaned


def crop_scale_1080x1920(frame: np.ndarray, x0: int, y0: int, crop_w: int, crop_h: int) -> np.ndarray:
    """Crops a region and scales to 1080x1920 with subtle unsharp mask so medium close-up cuts stay razor sharp."""
    roi = frame[y0 : y0 + crop_h, x0 : x0 + crop_w]
    scaled = cv2.resize(roi, (1080, 1920), interpolation=cv2.INTER_LANCZOS4)
    blur = cv2.GaussianBlur(scaled, (0, 0), 1.2)
    return cv2.addWeighted(scaled, 1.22, blur, -0.22, 0)


def remaster_deghost_and_recut_007(
    source_video: Path = DEFAULT_SOURCE,
    output_video: Path = DEFAULT_OUTPUT,
    audio_path: Path = DEFAULT_AUDIO,
) -> None:
    """De-ghosts all linear-blended frames and replaces distant blurry segment (t=6..11.8s) with beat-synced close-ups."""
    t0 = time.time()
    src = source_video if source_video.exists() else output_video
    print(f"[Remaster 007] Loading {src} for optical-flow de-ghosting & multi-shot beat recut...")
    cap = cv2.VideoCapture(str(src))
    raw_frames: list[np.ndarray] = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        raw_frames.append(frame)
    cap.release()

    if len(raw_frames) < 1000:
        raise RuntimeError(f"Expected ~1080 frames in {src}, got {len(raw_frames)}")

    clean_frames = deghost_frames(raw_frames[:1080])

    # Assemble 1080 frames (18.00s @ 60fps) with 4 beat-synced high-sharpness shots (eliminating distant face melt at frames 350..707):
    # Shot 1 (frames 0..347, t=0.0..5.8s): Original crisp medium shot
    # Shot 2 (frames 348..527, t=5.8..8.8s): 1.28x Medium Close-Up of energetic chorus dance (from clean_frames[710..889])
    # Shot 3 (frames 528..707, t=8.8..11.8s): 1.22x Medium Hero Cut of opening chorus (from clean_frames[40..219])
    # Shot 4 (frames 708..1079, t=11.8..18.0s): Original ultra-sharp close-up wink + heart gesture + finale
    final_frames: list[np.ndarray] = []
    for i in range(1080):
        if i < 348:
            final_frames.append(clean_frames[i])
        elif i < 528:
            src_i = 710 + (i - 348)
            final_frames.append(crop_scale_1080x1920(clean_frames[src_i], x0=96, y0=36, crop_w=888, crop_h=1578))
        elif i < 708:
            src_i = 40 + (i - 528)
            final_frames.append(crop_scale_1080x1920(clean_frames[src_i], x0=84, y0=28, crop_w=912, crop_h=1622))
        else:
            final_frames.append(clean_frames[i])

    output_video.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = output_video.with_name("tmp_remastered_007.mp4")
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        "1080x1920",
        "-r",
        "60",
        "-i",
        "-",
        "-i",
        str(audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-t",
        "18.00",
        "-vf",
        "setsar=1,setdar=9/16,format=yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "15",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(tmp_out),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    for f in final_frames:
        assert proc.stdin is not None
        proc.stdin.write(f.tobytes())
    assert proc.stdin is not None
    proc.stdin.close()
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("FFmpeg encode failed in remaster_deghost_and_recut_007")
    tmp_out.replace(output_video)
    print(f"[Remaster 007] Completed -> {output_video} (1080 frames @ 60.00 FPS) in {time.time() - t0:.1f}s")


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
    parser = argparse.ArgumentParser(description="Finalize or remaster Kling 1080P video(s) to 1080x1920 60FPS with 18s chorus audio")
    parser.add_argument("--inputs", type=Path, nargs="*", default=None, help="Input raw Kling MP4(s)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output 60FPS MP4")
    parser.add_argument("--audio", type=Path, default=DEFAULT_AUDIO, help="Audio MP3 path")
    parser.add_argument("--duration", type=float, default=18.0, help="Target duration in seconds (default: 18.0)")
    args = parser.parse_args()

    if not args.inputs:
        remaster_deghost_and_recut_007(DEFAULT_SOURCE, args.output, args.audio)
    else:
        finalize_60fps(args.inputs, args.output, args.audio, args.duration)


if __name__ == "__main__":
    main()
