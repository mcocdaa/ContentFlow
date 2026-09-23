"""AI Video & Image Enhancer for ContentFlow.
Provides GPU-accelerated frame interpolation (RIFE) and super-resolution (Real-ESRGAN).
Shared across all 3 production pipelines:
- Pipeline 1: 3D Blender/MMD Render -> AI Enhancement
- Pipeline 2: 2D Keyframes -> Motion Interpolation
- Pipeline 3: AI Image-to-Video API -> Upscale & 60fps Interpolation
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
VENDOR_BIN = BASE_DIR / "vendor" / "bin"
RIFE_EXE = VENDOR_BIN / "rife" / "rife-ncnn-vulkan"
REALESRGAN_EXE = VENDOR_BIN / "realesrgan" / "realesrgan-ncnn-vulkan"


class MediaEnhancer:
    """GPU-accelerated enhancement utilities using ncnn-vulkan."""

    def __init__(self):
        self.rife_path = RIFE_EXE
        self.realesrgan_path = REALESRGAN_EXE

    def is_rife_available(self) -> bool:
        return self.rife_path.exists() and os.access(self.rife_path, os.X_OK)

    def is_realesrgan_available(self) -> bool:
        return self.realesrgan_path.exists() and os.access(self.realesrgan_path, os.X_OK)

    def upscale_image(
        self,
        input_path: str | Path,
        output_path: str | Path,
        scale: int = 2,
        model_name: str = "realesr-animevideov3"
    ) -> Path:
        """Upscale a single image (e.g. figure character anchor or render frame)."""
        input_path = Path(input_path).resolve()
        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.is_realesrgan_available():
            raise RuntimeError(f"Real-ESRGAN executable not found at {self.realesrgan_path}")

        model_dir = (self.realesrgan_path.parent / "models").resolve()
        cmd = [
            str(self.realesrgan_path),
            "-i", str(input_path),
            "-o", str(output_path),
            "-s", str(scale),
            "-m", str(model_dir),
            "-n", model_name,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"Real-ESRGAN failed: {res.stderr or res.stdout}")
        return output_path

    def interpolate_frames_dir(
        self,
        input_dir: str | Path,
        output_dir: str | Path,
        model: str = "rife-v4.6",
        num_frames: Optional[int] = None,
    ) -> Path:
        """Interpolate an image sequence directory (e.g. 00000001.png, 00000002.png)."""
        input_dir = Path(input_dir).resolve()
        output_dir = Path(output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        if not self.is_rife_available():
            raise RuntimeError(f"RIFE executable not found at {self.rife_path}")

        model_dir = (self.rife_path.parent / model).resolve()
        cmd = [
            str(self.rife_path),
            "-i", str(input_dir),
            "-o", str(output_dir),
            "-m", str(model_dir),
            "-f", "%08d.png",
        ]
        if num_frames:
            cmd.extend(["-n", str(num_frames)])

        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"RIFE interpolation failed: {res.stderr or res.stdout}")
        return output_dir


    def interpolate_video_to_60fps(
        self,
        input_video: str | Path,
        output_video: str | Path,
        target_fps: int = 60,
    ) -> Path:
        """Boost video frame rate to 60fps using RIFE interpolation with audio preservation."""
        input_video = Path(input_video).resolve()
        output_video = Path(output_video).resolve()
        output_video.parent.mkdir(parents=True, exist_ok=True)

        if not self.is_rife_available():
            raise RuntimeError(f"RIFE executable not found at {self.rife_path}")

        with tempfile.TemporaryDirectory(prefix="cf_rife_") as tmp_dir:
            tmp_path = Path(tmp_dir)
            frames_in = tmp_path / "in"
            frames_out = tmp_path / "out"
            audio_track = tmp_path / "audio.aac"
            frames_in.mkdir()
            frames_out.mkdir()

            # 1. Extract audio if present
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(input_video), "-vn", "-c:a", "copy", str(audio_track)],
                capture_output=True
            )

            # 2. Extract frames
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(input_video), "-qscale:v", "1", "-qmin", "1", "-qmax", "1",
                 str(frames_in / "%08d.png")],
                check=True, capture_output=True
            )

            # 3. Run RIFE
            self.interpolate_frames_dir(frames_in, frames_out)

            # 4. Normalize RIFE fractional filenames to sequential integers (e.g. seq_00000001.png)
            rife_frames = sorted(frames_out.glob("*.png"))
            seq_dir = tmp_path / "seq"
            seq_dir.mkdir(parents=True, exist_ok=True)
            for idx, img_p in enumerate(rife_frames, 1):
                shutil.move(str(img_p), str(seq_dir / f"{idx:08d}.png"))

            # 5. Re-encode video at target FPS with audio
            mux_cmd = [
                "ffmpeg", "-y",
                "-r", str(target_fps),
                "-pattern_type", "sequence",
                "-i", str(seq_dir / "%08d.png"),
            ]

            if audio_track.exists() and audio_track.stat().st_size > 0:
                mux_cmd.extend(["-i", str(audio_track), "-c:a", "aac", "-shortest"])
            mux_cmd.extend([
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-crf", "18",
                str(output_video)
            ])
            res = subprocess.run(mux_cmd, capture_output=True, text=True)
            if res.returncode != 0:
                raise RuntimeError(f"FFmpeg muxing failed: {res.stderr or res.stdout}")


        return output_video
