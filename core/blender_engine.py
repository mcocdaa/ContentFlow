"""Blender Headless Orchestration Engine for Pipeline 1 (3D MMD/FBX Render -> AI Enhancement).
Controls headless Blender execution to:
1. Register and enable blender_mmd_tools addon
2. Load 3D figure models (PMX/FBX)
3. Load and bind dance motion capture data (VMD/BVH)
4. Configure realistic studio lighting, glossy wooden floor reflections, and anime camera framing
5. Render clean image sequences for downstream AI super-resolution and interpolation.
"""

import os
import logging
import subprocess
from pathlib import Path
from typing import Optional

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
        end_frame: int = 60,
        resolution_x: int = 720,
        resolution_y: int = 1280,
        samples: int = 32,
    ) -> str:
        """Constructs an executable Python script for Blender headless rendering with Cycles GPU acceleration."""
        model_abs = Path(model_path).resolve()
        motion_abs = Path(motion_path).resolve()
        output_abs = Path(output_dir).resolve()
        mmd_parent = self.mmd_tools_dir.parent.resolve()

        script = f"""import sys
import os
import math
import mathutils
import bpy

# 1. Configure Cycles with GPU acceleration
cpref = bpy.context.preferences.addons['cycles'].preferences
cpref.compute_device_type = 'CUDA'
cpref.get_devices()
for d in cpref.devices:
    d.use = (d.type == 'CUDA')

scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'GPU'
scene.cycles.samples = {samples}
scene.cycles.use_denoising = True
scene.cycles.denoiser = 'OPENIMAGEDENOISE'

# Clear default objects
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# 2. Register mmd_tools
mmd_tools_root = r"{mmd_parent}"
if mmd_tools_root not in sys.path:
    sys.path.insert(0, mmd_tools_root)

import mmd_tools
mmd_tools.register()
print("MMD Tools registered successfully!")

# 3. Import PMX Model
model_file = r"{model_abs}"
print("Importing PMX model:", model_file)
bpy.ops.mmd_tools.import_model(filepath=model_file)

# Find armature
armatures = [o for o in scene.objects if o.type == 'ARMATURE']
if not armatures:
    raise RuntimeError("No armature found in imported MMD model!")
arm = armatures[0]
bpy.context.view_layer.objects.active = arm
arm.select_set(True)

# 4. Import Dance VMD Motion
motion_file = r"{motion_abs}"
print("Importing VMD dance motion:", motion_file)
bpy.ops.mmd_tools.import_vmd(filepath=motion_file)

# 5. Dynamic Camera Setup (50mm full-body figure framing)
scene.frame_set({start_frame})
bpy.context.view_layer.update()

# Determine initial center of character
target_height = 0.82  # waist/torso center of ~1.6m anime figure
center_x, center_y = 0.0, 0.0
p_bones = arm.pose.bones
if '全ての親' in p_bones:
    b = p_bones['全ての親']
    world_pos = arm.matrix_world @ b.matrix @ mathutils.Vector((0, 0, 0))
    center_x, center_y = world_pos.x, world_pos.y
elif 'センター' in p_bones:
    b = p_bones['センター']
    world_pos = arm.matrix_world @ b.matrix @ mathutils.Vector((0, 0, 0))
    center_x, center_y = world_pos.x, world_pos.y

# Camera positioned in front for full-body 9:16 framing
cam_distance = 3.8
cam_data = bpy.data.cameras.new('TrackingCam')
cam_data.lens = 50
cam_data.sensor_fit = 'VERTICAL'
cam_obj = bpy.data.objects.new('TrackingCam', cam_data)
scene.collection.objects.link(cam_obj)
scene.camera = cam_obj
cam_obj.location = (center_x, center_y - cam_distance, target_height + 0.1)

# Target empty for smooth tracking
bpy.ops.object.empty_add(type='PLAIN_AXES', location=(center_x, center_y, target_height))
target = bpy.context.active_object
track = cam_obj.constraints.new(type='TRACK_TO')
track.target = target
track.track_axis = 'TRACK_NEGATIVE_Z'
track.up_axis = 'UP_Y'

# 6. Warm Parquet Wooden Floor (High sheen PVC reflection)
bpy.ops.mesh.primitive_plane_add(size=40, location=(center_x, center_y, 0))
floor = bpy.context.active_object
floor.name = 'WoodBalconyFloor'
floor_mat = bpy.data.materials.new(name='WoodBalconyMat')
floor_mat.use_nodes = True
bsdf = floor_mat.node_tree.nodes.get('Principled BSDF')
if bsdf:
    bsdf.inputs['Base Color'].default_value = (0.76, 0.53, 0.36, 1.0)
    bsdf.inputs['Roughness'].default_value = 0.16
    if 'Specular IOR Level' in bsdf.inputs:
        bsdf.inputs['Specular IOR Level'].default_value = 0.7
floor.data.materials.append(floor_mat)

# 7. Studio Balcony Lighting (Sunlight + Hair Rim + Soft Ambient Fill)
sun_data = bpy.data.lights.new('BalconySun', type='SUN')
sun_data.energy = 4.5
sun_data.color = (1.0, 0.97, 0.92)
sun_obj = bpy.data.objects.new('BalconySun', sun_data)
scene.collection.objects.link(sun_obj)
sun_obj.rotation_euler = (0.75, 0.3, -0.6)

rim_data = bpy.data.lights.new('HairRim', type='POINT')
rim_data.energy = 220.0
rim_data.color = (0.95, 0.98, 1.0)
rim_obj = bpy.data.objects.new('HairRim', rim_data)
scene.collection.objects.link(rim_obj)
rim_obj.location = (center_x - 1.2, center_y + 1.8, target_height + 1.2)

fill_data = bpy.data.lights.new('FrontFill', type='AREA')
fill_data.energy = 80.0
fill_data.size = 3.0
fill_obj = bpy.data.objects.new('FrontFill', fill_data)
scene.collection.objects.link(fill_obj)
fill_obj.location = (center_x + 0.8, center_y - 2.5, target_height + 0.5)

# Room Wall behind figure
bpy.ops.mesh.primitive_plane_add(size=30, location=(center_x, center_y + 4.5, 4.0))
wall = bpy.context.active_object
wall.rotation_euler = (math.radians(90), 0, 0)
wall_mat = bpy.data.materials.new(name='WallMat')
wall_mat.use_nodes = True
wbsdf = wall_mat.node_tree.nodes.get('Principled BSDF')
if wbsdf:
    wbsdf.inputs['Base Color'].default_value = (0.94, 0.95, 0.98, 1.0)
    wbsdf.inputs['Roughness'].default_value = 0.9
wall.data.materials.append(wall_mat)

# World background daylight
world = scene.world
world.use_nodes = True
bg = world.node_tree.nodes.get('Background')
if bg:
    bg.inputs['Color'].default_value = (0.92, 0.95, 1.0, 1.0)
    bg.inputs['Strength'].default_value = 0.6

# 8. Render Frame Sequence
scene.frame_start = {start_frame}
scene.frame_end = {end_frame}
scene.render.fps = 30
scene.render.resolution_x = {resolution_x}
scene.render.resolution_y = {resolution_y}
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
scene.render.filepath = os.path.join(r"{output_abs}", "frame_")

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
        end_frame: int = 60,
        resolution_x: int = 720,
        resolution_y: int = 1280,
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
            resolution_x=resolution_x,
            resolution_y=resolution_y,
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
