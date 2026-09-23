"""Video Generation API Router for Pipeline 3.
Provides a unified abstraction across multiple cloud video generation providers:
- VolcEngine Seedance 2.5 / 2.0 (ARK_API_KEY)
- Kuaishou Kling AI (KLING_ACCESS_KEY / KLING_SECRET_KEY)
- MiniMax Hailuo Video (MINIMAX_API_KEY)
- Local Mock/Simulation Provider (for pipeline verification without burning API credits)
"""

import os
import time
import json
import logging
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class VideoGenerationTask:
    """Represents an ongoing or completed video generation task."""
    def __init__(self, provider: str, task_id: str, status: str = "pending", video_url: Optional[str] = None):
        self.provider = provider
        self.task_id = task_id
        self.status = status
        self.video_url = video_url


class VideoApiRouter:
    """Unified router and client for cloud video generation models."""

    def __init__(self):
        self.ark_api_key = os.environ.get("ARK_API_KEY")
        self.kling_access_key = os.environ.get("KLING_ACCESS_KEY")
        self.kling_secret_key = os.environ.get("KLING_SECRET_KEY")
        self.minimax_api_key = os.environ.get("MINIMAX_API_KEY")

    def get_available_providers(self) -> Dict[str, bool]:
        """Check which video generation backends have valid credentials configured."""
        return {
            "volcengine_seedance": bool(self.ark_api_key),
            "kling_ai": bool(self.kling_access_key and self.kling_secret_key),
            "minimax": bool(self.minimax_api_key),
            "local_simulator": True,
        }

    def generate_video_from_image(
        self,
        image_path: str | Path,
        prompt: str,
        provider: str = "auto",
        duration: int = 5,
        resolution: str = "720p",
        ratio: str = "16:9",
        output_path: Optional[str | Path] = None,
    ) -> Path:
        """High-level dispatch to generate video from an image using the best available provider."""
        image_path = Path(image_path).resolve()
        if not image_path.exists():
            raise FileNotFoundError(f"Source image not found: {image_path}")

        providers = self.get_available_providers()

        # Select provider if auto
        if provider == "auto":
            if providers["volcengine_seedance"]:
                provider = "volcengine_seedance"
            elif providers["kling_ai"]:
                provider = "kling_ai"
            elif providers["minimax"]:
                provider = "minimax"
            else:
                provider = "local_simulator"

        logger.info(f"Dispatching video generation to provider: {provider}")

        if provider == "volcengine_seedance":
            return self._dispatch_seedance(image_path, prompt, duration, resolution, ratio, output_path)
        elif provider == "kling_ai":
            return self._dispatch_kling(image_path, prompt, duration, output_path)
        elif provider == "minimax":
            return self._dispatch_minimax(image_path, prompt, duration, output_path)
        elif provider == "local_simulator":
            return self._dispatch_simulator(image_path, duration, output_path)
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    def _dispatch_seedance(
        self,
        image_path: Path,
        prompt: str,
        duration: int,
        resolution: str,
        ratio: str,
        output_path: Optional[Path],
    ) -> Path:
        """Call VolcEngine Seedance 2.5 skill script."""
        skill_wrapper = Path(__file__).resolve().parent.parent / ".agents" / "skills" / "byted-ark-seedance-skill" / "scripts" / "seedance.js"
        if not skill_wrapper.exists():
            raise RuntimeError("byted-ark-seedance-skill not installed.")

        cmd = [
            "node", str(skill_wrapper), "create",
            "--model", "doubao-seedance-2.5",
            "--prompt", prompt,
            "--image-file", str(image_path),
            "--duration", str(duration),
            "--resolution", resolution,
            "--ratio", ratio,
            "--wait"
        ]
        if output_path:
            cmd.extend(["--download-dir", str(Path(output_path).parent)])

        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"Seedance API call failed: {res.stderr or res.stdout}")

        # The downloaded file or result
        return Path(output_path) if output_path else Path("output.mp4")

    def _dispatch_kling(self, image_path: Path, prompt: str, duration: int, output_path: Optional[Path]) -> Path:
        """Placeholder adapter for Kling AI API (invoked when KLING_ACCESS_KEY is set)."""
        raise NotImplementedError("Kling AI API integration: keys detected but endpoint calling in progress.")

    def _dispatch_minimax(self, image_path: Path, prompt: str, duration: int, output_path: Optional[Path]) -> Path:
        """Placeholder adapter for MiniMax API (invoked when MINIMAX_API_KEY is set)."""
        raise NotImplementedError("MiniMax API integration: keys detected but endpoint calling in progress.")

    def _dispatch_simulator(self, image_path: Path, duration: int, output_path: Optional[Path]) -> Path:
        """Generates a smooth simulated camera push from the input image using FFmpeg zoompan.
        Allows validating downstream RIFE/Audio/Assembly pipelines without an active API key.
        """
        output_path = Path(output_path or "simulated_output.mp4").resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        fps = 30
        total_frames = int(duration * fps)

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", str(image_path),
            "-vf", f"scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,zoompan=z='min(zoom+0.0008,1.06)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={total_frames}:s=1920x1080:fps={fps}",
            "-t", str(duration),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            str(output_path)
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path
