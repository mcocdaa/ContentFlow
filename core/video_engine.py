"""MoneyPrinterTurbo Integration Engine for ContentFlow.
Encapsulates headless CLI execution, material staging, subtitle alignment,
and video packaging.
"""

from pathlib import Path
import subprocess
import json
import shutil
import logging
from typing import List, Optional, Dict, Any
from config.settings import (
    MONEYPRINTER_DIR,
    MONEYPRINTER_VENV_PYTHON,
)
from .asset_builder import AssetBuilder

logger = logging.getLogger("ContentFlow.VideoEngine")


class VideoRenderResult:
    def __init__(
        self,
        success: bool,
        task_id: str,
        video_path: Optional[Path] = None,
        audio_path: Optional[Path] = None,
        subtitle_path: Optional[Path] = None,
        cover_path: Optional[Path] = None,
        error: Optional[str] = None,
    ):
        self.success = success
        self.task_id = task_id
        self.video_path = video_path
        self.audio_path = audio_path
        self.subtitle_path = subtitle_path
        self.cover_path = cover_path
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "task_id": self.task_id,
            "video_path": str(self.video_path) if self.video_path else None,
            "audio_path": str(self.audio_path) if self.audio_path else None,
            "subtitle_path": str(self.subtitle_path) if self.subtitle_path else None,
            "cover_path": str(self.cover_path) if self.cover_path else None,
            "error": self.error,
        }


class VideoEngine:
    """Orchestrates headless video rendering via MoneyPrinterTurbo."""

    def __init__(self, mpt_dir: Optional[Path] = None, python_bin: Optional[Path] = None):
        self.mpt_dir = Path(mpt_dir or MONEYPRINTER_DIR)
        self.python_bin = Path(python_bin or MONEYPRINTER_VENV_PYTHON)
        self.cli_script = self.mpt_dir / "cli.py"

        if not self.mpt_dir.exists():
            raise FileNotFoundError(f"MoneyPrinterTurbo not found at {self.mpt_dir}")
        if not self.python_bin.exists():
            raise FileNotFoundError(f"Python venv not found at {self.python_bin}")

    def render(
        self,
        subject: str,
        script: str,
        materials: List[Path],
        output_dir: Path,
        aspect: str = "16:9",
        voice_name: str = "zh-CN-YunxiNeural",
        bgm_type: str = "random",
        font_name: str = "STHeitiMedium.ttc",
        fast_image_convert: bool = True,
    ) -> VideoRenderResult:
        """Executes end-to-end video rendering."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if not materials:
            raise ValueError("At least one material (image or video) is required.")

        processed_materials: List[str] = []
        builder = AssetBuilder(output_dir / "staged_clips")

        # Fast pre-conversion: static images converted via native ffmpeg in 0.3s
        # avoids MoviePy's 45s CPU software resize per image
        for mat in materials:
            mat_path = Path(mat).resolve()
            ext = mat_path.suffix.lower()
            if fast_image_convert and ext in {".png", ".jpg", ".jpeg", ".webp"}:
                w, h = (1920, 1080) if aspect == "16:9" else ((1080, 1920) if aspect == "9:16" else (1080, 1080))
                fast_mp4 = builder.convert_image_to_mp4_fast(mat_path, duration=5.0, size=(w, h))
                processed_materials.append(str(fast_mp4))
            else:
                processed_materials.append(str(mat_path))

        materials_arg = ",".join(processed_materials)

        cmd = [
            str(self.python_bin),
            str(self.cli_script),
            "--video-subject", subject,
            "--video-script", script,
            "--video-source", "local",
            "--video-materials", materials_arg,
            "--video-aspect", aspect,
            "--voice-name", voice_name,
            "--bgm-type", bgm_type,
            "--font-name", font_name,
            "--stop-at", "video",
        ]

        logger.info(f"Running MoneyPrinterTurbo CLI: {' '.join(cmd[:6])} ...")
        proc = subprocess.run(
            cmd,
            cwd=str(self.mpt_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if proc.returncode != 0:
            error_msg = proc.stderr or proc.stdout
            logger.error(f"Render failed with exit code {proc.returncode}: {error_msg[-500:]}")
            return VideoRenderResult(
                success=False,
                task_id="",
                error=error_msg,
            )

        # Parse JSON output from stdout
        try:
            # MoneyPrinterTurbo prints one JSON object on stdout
            stdout_clean = proc.stdout.strip()
            # In case there are log lines preceding the JSON, find the JSON block
            json_start = stdout_clean.find("{")
            json_end = stdout_clean.rfind("}")
            if json_start != -1 and json_end != -1:
                result_json = json.loads(stdout_clean[json_start : json_end + 1])
            else:
                result_json = {}
        except Exception as e:
            return VideoRenderResult(
                success=False,
                task_id="",
                error=f"Failed to parse CLI output: {e}\nStdout: {proc.stdout[-500:]}",
            )

        task_id = result_json.get("task_id", "")
        mpt_task_dir = self.mpt_dir / "storage" / "tasks" / task_id

        import re
        safe_subject = re.sub(r'[\\/*?:"<>|\s]+', "_", subject).strip("_")

        dest_video = output_dir / f"{safe_subject}_final.mp4"
        dest_audio = output_dir / f"{safe_subject}_audio.mp3"
        dest_sub = output_dir / f"{safe_subject}_subtitle.srt"
        dest_cover = output_dir / f"{safe_subject}_cover.jpg"

        # Locate generated files
        src_video = mpt_task_dir / "final-1.mp4"
        if not src_video.exists():
            # fallback to result_json video_file if present
            v_file = result_json.get("video_file")
            if v_file and Path(v_file).exists():
                src_video = Path(v_file)

        if src_video.exists():
            shutil.copy2(src_video, dest_video)

        src_audio = mpt_task_dir / "audio.mp3"
        if src_audio.exists():
            shutil.copy2(src_audio, dest_audio)

        src_sub = mpt_task_dir / "subtitle.srt"
        if src_sub.exists():
            shutil.copy2(src_sub, dest_sub)

        # Generate cover from video at 1.0s mark
        if dest_video.exists():
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-ss", "00:00:01",
                    "-i", str(dest_video),
                    "-vframes", "1",
                    "-q:v", "2",
                    str(dest_cover),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        return VideoRenderResult(
            success=True,
            task_id=task_id,
            video_path=dest_video if dest_video.exists() else None,
            audio_path=dest_audio if dest_audio.exists() else None,
            subtitle_path=dest_sub if dest_sub.exists() else None,
            cover_path=dest_cover if dest_cover.exists() else None,
        )
