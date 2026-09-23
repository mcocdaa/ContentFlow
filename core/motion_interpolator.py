"""Motion Interpolation Engine for Pipeline 2 (Keyframe to Smooth Dance Video).
Takes a set of discrete character pose keyframes and performs multi-stage dense optical flow
interpolation using RIFE (Real-Time Intermediate Flow Estimation) to produce fluid 60FPS motion.
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

from core.enhancer import MediaEnhancer

class MotionInterpolator:
    """Orchestrates recursive keyframe interpolation and temporal smoothing."""

    def __init__(self):
        self.enhancer = MediaEnhancer()

    def interpolate_keyframes_to_sequence(
        self,
        keyframe_paths: List[Path],
        output_dir: Path,
        frames_per_transition: int = 15,  # 15 frames between keyframes = ~0.5s at 30fps
    ) -> List[Path]:
        """Interpolate between consecutive keyframes to form a continuous image sequence."""
        output_dir = Path(output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        if len(keyframe_paths) < 2:
            raise ValueError("At least 2 keyframes are required for interpolation.")

        all_frames: List[Path] = []
        frame_idx = 1

        for i in range(len(keyframe_paths) - 1):
            k_start = keyframe_paths[i]
            k_end = keyframe_paths[i + 1]

            # Stage temporary transition folder
            trans_in = output_dir / f"trans_in_{i}"
            trans_out = output_dir / f"trans_out_{i}"
            trans_in.mkdir(parents=True, exist_ok=True)
            trans_out.mkdir(parents=True, exist_ok=True)

            shutil.copy2(k_start, trans_in / "00000001.png")
            shutil.copy2(k_end, trans_in / "00000002.png")

            # Calculate required recursive doubling (e.g. 2->4->8->16)
            cmd = [
                str(self.enhancer.rife_path),
                "-0", str(k_start),
                "-1", str(k_end),
                "-o", str(trans_out / "mid.png"),
                "-m", str(self.enhancer.rife_path.parent / "rife-v4.6")
            ]

            # Use batch interpolation on the segment with specified transition frames
            self.enhancer.interpolate_frames_dir(
                trans_in, trans_out, model="rife-v4.6", num_frames=frames_per_transition
            )

            # Collect generated frames in order
            generated = sorted(trans_out.glob("*.png"))
            for g in generated:
                dest = output_dir / f"{frame_idx:08d}.png"
                shutil.move(str(g), str(dest))
                all_frames.append(dest)
                frame_idx += 1

            shutil.rmtree(trans_in, ignore_errors=True)
            shutil.rmtree(trans_out, ignore_errors=True)

        return all_frames

    def assemble_sequence_to_video(
        self,
        frames_dir: Path,
        output_mp4: Path,
        fps: int = 30,
        audio_file: Optional[Path] = None,
    ) -> Path:
        """Encode interpolated frame directory into an MP4 video."""
        output_mp4 = Path(output_mp4).resolve()
        output_mp4.parent.mkdir(parents=True, exist_ok=True)

        # Auto-detect file naming pattern in directory
        png_files = sorted(Path(frames_dir).glob("*.png"))
        if not png_files:
            raise FileNotFoundError(f"No PNG files found in {frames_dir} to assemble.")

        first_stem = png_files[0].stem
        if first_stem.startswith("frame_"):
            pattern = "frame_%04d.png"
        elif len(first_stem) == 8 and first_stem.isdigit():
            pattern = "%08d.png"
        else:
            # Fallback: create temporary sequential symlinks/copies if format is arbitrary
            pattern = f"{first_stem[:6]}%04d.png" if len(first_stem) >= 6 else "%04d.png"

        cmd = [
            "ffmpeg", "-y",
            "-r", str(fps),
            "-pattern_type", "sequence",
            "-i", str(Path(frames_dir) / pattern),
        ]

        if audio_file and Path(audio_file).exists():
            cmd.extend(["-i", str(audio_file), "-c:a", "aac", "-shortest"])
        cmd.extend([
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-crf", "18",
            str(output_mp4)
        ])

        subprocess.run(cmd, check=True, capture_output=True)
        return output_mp4
