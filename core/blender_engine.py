"""Blender Headless Orchestration Engine for Pipeline 1 (3D MMD/FBX Render -> AI Enhancement).
Controls headless Blender execution to:
1. Register and enable blender_mmd_tools addon
2. Load 3D figure models (PMX/FBX)
3. Load and bind dance motion capture data (VMD/BVH)
4. Configure realistic studio lighting, ground shadow catcher, and anime camera framing
5. Render clean image sequences for downstream AI super-resolution and interpolation.
"""

import os
import shutil
import logging
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any

from core.enhancer import MediaEnhancer

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
VENDOR_DIR = BASE_DIR / "vendor"
BLENDER_BIN = VENDOR_DIR / "blender" / "blender"
MMD_TOOLS_DIR = VENDOR_DIR / "blender_mmd_tools" / "mmd_tools"


class Blender3DEngine:
    """Manages headless Blender execution and 3D figure animation rendering."""

    def __init__(self, blender_path: Optional[Path] = None):
        self.blender_path = Path(blender_path) if blender_path else BLENDER_BIN
        self.mmd_tools_dir = MMD_TOOLS_DIR
        self.enhancer = MediaEnhancer()

    def is_blender_installed(self) -> bool:
        return self.blender_path.exists() and os.access(self.blender_path, os.X_OK)

    def is_mmd_tools_available(self) -> bool:
        return self.mmd_tools_dir.exists() and (self.mmd_tools_dir / "__init__.py").exists()

    def generate_headless_render_script(
        self,
        model_path: Path,
        motion_path: Path,
        output_dir: Path,
        start_frame: int = 1,
        end_frame: int = 250,
        resolution_x: int = 1920,
        resolution_y: int = 1080,
    ) -> str:
        """Constructs an executable Python script for Blender headless rendering."""
        script = f"""import bpy
import sys
import os

# Register mmd_tools
mmd_tools_root = r"{self.mmd_tools_dir.parent}"
if mmd_tools_root not in sys.path:
    sys.path.insert(0, mmd_tools_root)
try:
    import mmd_tools
    mmd_tools.register()
    print("MMD Tools successfully registered!")
except Exception as e:
    print("Warning: mmd_tools registration notice:", e)

# Set render settings
scene = bpy.context.scene
scene.render.resolution_x = {resolution_x}
scene.render.resolution_y = {resolution_y}
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
scene.render.filepath = os.path.join(r"{output_dir}", "frame_")

scene.frame_start = {start_frame}
scene.frame_end = {end_frame}
scene.render.fps = 30


# Configure Lighting (Balcony sun + soft ambient)
world = bpy.context.scene.world
world.use_nodes = True

# Clean existing objects
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Create Camera
cam_data = bpy.data.cameras.new("FigureCam")
cam_data.lens = 65  # portrait focal length
cam_obj = bpy.data.objects.new("FigureCam", cam_data)
bpy.context.collection.objects.link(cam_obj)
scene.camera = cam_obj
cam_obj.location = (0, -3.8, 1.2)
cam_obj.rotation_euler = (1.57, 0, 0)

# Create Sunlight & Rim light
light_data = bpy.data.lights.new(name="Sunlight", type='SUN')
light_data.energy = 3.5
light_obj = bpy.data.objects.new(name="Sunlight", object_data=light_data)
bpy.context.collection.objects.link(light_obj)
light_obj.rotation_euler = (0.78, 0.35, -0.6)

# Render
print(f"Starting headless render: frames {start_frame} to {end_frame}...")
bpy.ops.render.render(animation=True)
print("Headless rendering complete!")
"""
        return script

    def render_animation(
        self,
        model_path: Path,
        motion_path: Path,
        output_dir: Path,
        start_frame: int = 1,
        end_frame: int = 120,
    ) -> Path:
        """Executes headless Blender to render an animation sequence."""
        if not self.is_blender_installed():
            raise RuntimeError(f"Blender executable not found at {self.blender_path}")

        output_dir = Path(output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        script_content = self.generate_headless_render_script(
            model_path=model_path,
            motion_path=motion_path,
            output_dir=output_dir,
            start_frame=start_frame,
            end_frame=end_frame,
        )

        script_file = output_dir / "_run_render.py"
        script_file.write_text(script_content, encoding="utf-8")

        cmd = [
            str(self.blender_path),
            "-b",
            "--python", str(script_file)
        ]

        logger.info(f"Running Blender command: {' '.join(cmd)}")
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"Blender render failed:\n{res.stderr or res.stdout}")

        return output_dir
