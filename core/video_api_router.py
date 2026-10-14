"""Video Generation API Router for Pipeline 3.
Provides a unified abstraction across multiple cloud video generation providers:
- VolcEngine Seedance 2.5 / 2.0 (ARK_API_KEY)
- Kuaishou Kling AI (KLING_ACCESS_KEY / KLING_SECRET_KEY)
- MiniMax Hailuo Video (MINIMAX_API_KEY)
- Local Mock/Simulation Provider (for pipeline verification without burning API credits)
"""

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Optional

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
            "kling_ai": False,
            "minimax": False,
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

        resolved_output = Path(output_path) if output_path else None
        providers = self.get_available_providers()

        # Select provider if auto (do not auto-select unimplemented kling/minimax stubs)
        if provider == "auto":
            if providers.get("volcengine_seedance"):
                provider = "volcengine_seedance"
            else:
                provider = "local_simulator"

        logger.info(f"Dispatching video generation to provider: {provider}")

        if provider == "volcengine_seedance":
            return self._dispatch_seedance(image_path, prompt, duration, resolution, ratio, resolved_output)
        elif provider == "kling_ai":
            return self._dispatch_kling(image_path, prompt, duration, resolved_output)
        elif provider == "minimax":
            return self._dispatch_minimax(image_path, prompt, duration, resolved_output)
        elif provider == "local_simulator":
            return self._dispatch_simulator(image_path, duration, resolved_output, resolution, ratio)
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
        """Call VolcEngine Seedance skill script with model fallback and simulator recovery."""
        skill_wrapper = Path(__file__).resolve().parent.parent / ".agents" / "skills" / "byted-ark-seedance-skill" / "scripts" / "seedance.js"
        if not skill_wrapper.exists():
            raise RuntimeError("byted-ark-seedance-skill not installed.")

        candidate_models = ["doubao-seedance-2.0", "doubao-seedance-1.5-pro", "doubao-seedance-2.5"]
        last_error = None
        download_dir = str(output_path.parent) if output_path else "seedance_raw"

        for model in candidate_models:
            logger.info(f"Attempting Seedance generation with model: {model}")
            cmd = [
                "node", str(skill_wrapper), "run",
                "--model", model,
                "--prompt", prompt,
                "--image-file", str(image_path),
                "--duration", str(duration),
                "--resolution", resolution,
                "--ratio", ratio,
                "--download-dir", download_dir,
                "--wait"
            ]

            env = os.environ.copy()
            if self.ark_api_key and "ARK_API_KEY" not in env:
                env["ARK_API_KEY"] = self.ark_api_key

            res = subprocess.run(cmd, capture_output=True, text=True, env=env)
            if res.returncode == 0:
                logger.info(f"Seedance task succeeded with model {model}")
                # Check for downloaded video file
                video_candidates = list(Path(download_dir).glob("*.mp4"))
                if video_candidates:
                    if output_path and Path(video_candidates[0]) != Path(output_path):
                        shutil.copy2(video_candidates[0], output_path)
                    return Path(output_path) if output_path else video_candidates[0]
                return Path(output_path) if output_path else Path(download_dir) / "output.mp4"

            last_error = res.stderr or res.stdout
            if "UnsupportedModel" in last_error:
                logger.warning(f"Model {model} unsupported on this account tier. Trying next candidate...")
                continue
            else:
                logger.error(f"Seedance call failed: {last_error}")
                break

        logger.warning(f"All Seedance models failed ({last_error}). Gracefully falling back to local simulator.")
        return self._dispatch_simulator(image_path, duration, output_path, resolution, ratio)

    def _dispatch_kling(self, image_path: Path, prompt: str, duration: int, output_path: Optional[Path]) -> Path:
        """Placeholder adapter for Kling AI API (invoked when KLING_ACCESS_KEY is set)."""
        raise NotImplementedError("Kling AI API integration: keys detected but endpoint calling in progress.")

    def _dispatch_minimax(self, image_path: Path, prompt: str, duration: int, output_path: Optional[Path]) -> Path:
        """Placeholder adapter for MiniMax API (invoked when MINIMAX_API_KEY is set)."""
        raise NotImplementedError("MiniMax API integration: keys detected but endpoint calling in progress.")

    def _dispatch_simulator(
        self,
        image_path: Path,
        duration: int,
        output_path: Optional[Path],
        resolution: str = "720p",
        ratio: str = "16:9"
    ) -> Path:
        """Generates a smooth simulated camera push and subtle rhythm sway from input image.
        Allows validating downstream RIFE/Audio/Assembly pipelines without an active API key.
        """
        output_path = Path(output_path or "simulated_output.mp4").resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        fps = 30
        total_frames = int(duration * fps)

        if ratio == "9:16":
            w, h = (720, 1280) if resolution == "720p" else (1080, 1920)
        else:
            w, h = (1280, 720) if resolution == "720p" else (1920, 1080)

        # Dynamic breathing camera push & subtle rhythm sway for dance figure
        vf = (
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"zoompan=z='min(zoom+0.0006,1.05)':x='iw/2-(iw/zoom/2)+sin(in/15)*10':y='ih/2-(ih/zoom/2)+cos(in/15)*6':d={total_frames}:s={w}x{h}:fps={fps}"
        )

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", str(image_path),
            "-vf", vf,
            "-t", str(duration),
            "-c:v", "libx264",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            str(output_path)
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path

