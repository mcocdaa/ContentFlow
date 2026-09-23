"""Unified Figure Video Orchestrator for ContentFlow.
Exposes a unified high-level pipeline for producing 3D anime figure dance videos
across all 3 architectural lines:
1. '3d': 3D MMD/Blender Rigging & Rendering + AI Super-Resolution & 60FPS
2. 'keyframe': AI Dense Keyframe Generation + Optical Flow RIFE Interpolation
3. 'api': Cloud Video Generation Model (Seedance / Kling) + Post-Processing
"""

import os
import shutil
import logging
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any

from core.enhancer import MediaEnhancer
from core.motion_interpolator import MotionInterpolator
from core.video_api_router import VideoApiRouter
from core.blender_engine import Blender3DEngine

logger = logging.getLogger(__name__)


class FigurePipelineMode(str, Enum):
    THREE_D = "3d"
    KEYFRAME = "keyframe"
    API = "api"


class FigureVideoOrchestrator:
    """Master orchestrator for figure anime dance/motion video creation."""

    def __init__(self):
        self.enhancer = MediaEnhancer()
        self.interpolator = MotionInterpolator()
        self.api_router = VideoApiRouter()
        self.blender_engine = Blender3DEngine()

    def get_pipeline_readiness(self) -> Dict[str, Dict[str, Any]]:
        """Reports the hardware, software, and API readiness for each of the 3 lines."""
        return {
            "mode_1_3d": {
                "name": "3D 建模渲染 + AI 插帧优化流",
                "blender_ready": self.blender_engine.is_blender_installed(),
                "mmd_tools_ready": self.blender_engine.is_mmd_tools_available(),
                "rife_ready": self.enhancer.is_rife_available(),
                "realesrgan_ready": self.enhancer.is_realesrgan_available(),
                "status": "ready" if (self.blender_engine.is_blender_installed() and self.enhancer.is_rife_available()) else "pending_engine",
            },
            "mode_2_keyframe": {
                "name": "2D 关键帧生成 + 动作插帧平滑流",
                "seedream_ready": bool(os.environ.get("ARK_API_KEY")),
                "rife_ready": self.enhancer.is_rife_available(),
                "realesrgan_ready": self.enhancer.is_realesrgan_available(),
                "status": "ready" if bool(os.environ.get("ARK_API_KEY")) else "missing_api_key",
            },
            "mode_3_api": {
                "name": "单图手办 -> 视频大模型 API 生成流",
                "providers": self.api_router.get_available_providers(),
                "rife_ready": self.enhancer.is_rife_available(),
                "realesrgan_ready": self.enhancer.is_realesrgan_available(),
                "status": "ready" if any(self.api_router.get_available_providers().values()) else "missing_video_api",
            },
        }

    def run_pipeline(
        self,
        mode: FigurePipelineMode | str,
        project_dir: Path,
        character_image: Optional[Path] = None,
        audio_file: Optional[Path] = None,
        prompt: str = "3d figure girl dancing gracefully, sunlit wooden floor",
        output_name: str = "figure_dance_final.mp4",
        model: Optional[str | Path] = None,
        motion: Optional[str | Path] = None,
        frames: int = 60,
    ) -> Path:
        """Executes the chosen pipeline and produces a 1080P/60FPS final video."""
        project_dir = Path(project_dir).resolve()
        output_dir = project_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        final_output = output_dir / output_name

        mode_str = str(mode.value if isinstance(mode, FigurePipelineMode) else mode).lower()
        logger.info(f"Starting Figure Video Orchestrator in mode: {mode_str}")

        if mode_str == "3d":
            # 1. 3D Headless Pipeline
            logger.info("Executing 3D Blender Headless Render...")
            raw_frames_dir = output_dir / "3d_raw_frames"
            
            # Resolve model: explicit param -> project assets -> central library
            all_pmx = list(Path("library/models").rglob("*.pmx")) + list((project_dir / "assets").glob("*.pmx"))
            if model:
                model_str = str(model).lower()
                matched = [p for p in all_pmx if model_str in p.name.lower() or model_str in str(p).lower()]
                model_file = matched[0] if matched else Path(model).resolve()
            elif (project_dir / "assets" / "model.pmx").exists():
                model_file = project_dir / "assets" / "model.pmx"
            elif all_pmx:
                model_file = all_pmx[0]
            else:
                raise FileNotFoundError("No PMX model found in project assets or library/models.")

            # Resolve motion: explicit param -> project assets -> central library
            all_vmd = [c for c in Path("library/motions").rglob("*.vmd") if "camera" not in c.name.lower()]
            if motion:
                motion_str = str(motion).lower()
                matched = [m for m in all_vmd if motion_str in m.name.lower()]
                motion_file = matched[0] if matched else Path(motion).resolve()
            elif (project_dir / "assets" / "dance.vmd").exists():
                motion_file = project_dir / "assets" / "dance.vmd"
            elif all_vmd:
                motion_file = all_vmd[0]
            else:
                raise FileNotFoundError("No VMD dance motion found in project assets or library/motions.")

            logger.info(f"Using 3D model: {model_file}")
            logger.info(f"Using dance motion: {motion_file}")
            logger.info(f"Rendering {frames} frames...")

            self.blender_engine.render_animation(
                model_path=model_file,
                motion_path=motion_file,
                output_dir=raw_frames_dir,
                start_frame=1,
                end_frame=frames,
                resolution_x=720,
                resolution_y=1280,
            )
            # Assemble & enhance to 60fps
            raw_video = output_dir / "3d_rendered_30fps.mp4"
            self.interpolator.assemble_sequence_to_video(raw_frames_dir, raw_video, fps=30, audio_file=audio_file)
            return self.enhancer.interpolate_video_to_60fps(raw_video, final_output)

        elif mode_str == "keyframe":
            # 2. Keyframe Interpolation Pipeline
            logger.info("Executing 2D Keyframe Interpolation Pipeline...")
            staged_frames_dir = output_dir / "interpolated_frames"
            # Collect keyframes from project assets (scenes, poses, or general images)
            assets_dir = project_dir / "assets"
            matched_candidates = []
            for pat in ("*scene*.jpg", "*scene*.png", "*pose*.png", "*pose*.jpg", "*keyframe*.png", "*keyframe*.jpg"):
                matched_candidates.extend(assets_dir.glob(pat))
            # Deduplicate preserving order
            seen = set()
            keyframe_images = []
            for p in sorted(matched_candidates):
                if p not in seen:
                    seen.add(p)
                    keyframe_images.append(p)

            if not keyframe_images and character_image:
                keyframe_images = [character_image]

            if len(keyframe_images) < 2:
                logger.warning("Fewer than 2 keyframes found. Using camera push simulation fallback.")
                raw_video = self.api_router.generate_video_from_image(
                    image_path=character_image or keyframe_images[0],
                    prompt=prompt,
                    provider="local_simulator",
                    duration=5,
                    output_path=output_dir / "simulated_base.mp4"
                )
                return self.enhancer.interpolate_video_to_60fps(raw_video, final_output)

            self.interpolator.interpolate_keyframes_to_sequence(
                keyframe_paths=keyframe_images,
                output_dir=staged_frames_dir,
                frames_per_transition=20
            )
            raw_video = output_dir / "keyframe_raw.mp4"
            self.interpolator.assemble_sequence_to_video(staged_frames_dir, raw_video, fps=30, audio_file=audio_file)
            return self.enhancer.interpolate_video_to_60fps(raw_video, final_output)

        elif mode_str == "api":
            # 3. Cloud Video API Pipeline
            logger.info("Executing Cloud Video Generation API Pipeline...")
            raw_video = output_dir / "api_generated_raw.mp4"
            self.api_router.generate_video_from_image(
                image_path=character_image or (project_dir / "assets" / "character_anchor.jpg"),
                prompt=prompt,
                provider="auto",
                duration=5,
                output_path=raw_video
            )
            # Boost to 60FPS using local RIFE
            return self.enhancer.interpolate_video_to_60fps(raw_video, final_output)

        else:
            raise ValueError(f"Unknown pipeline mode: {mode}")
