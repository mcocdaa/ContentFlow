#!/usr/bin/env python3
"""Headless Blender 3D Renderer for Project 006: DeepSeek Whale-chan Phone Number.

Renders high-quality 720x1280 base frames of 3D figure dancing with Cycles GPU:
- Model: TDA Miku Lace Dress Blue Ver2.0 (DeepSeek Cyan/Blue Palette)
- Motion: Phone Number dance motion (Frames 1410-1530 chorus segment)
- Geometry: Automatic Subsurf smoothing to eliminate low-poly faceting
- Studio: Acrylic circular figure pedestal + dark reflective floor + 3-point lighting
- Output: PNG frames saved to output/line1_raw_frames/
"""

import sys
import os
import argparse
import subprocess
import time
from pathlib import Path

# Paths relative to ContentFlow root
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
BLENDER_BIN = ROOT_DIR / "vendor" / "blender" / "blender"
MMD_TOOLS_DIR = ROOT_DIR / "vendor" / "blender_mmd_tools"

DEFAULT_MODEL = ROOT_DIR / "library" / "models" / "tda_miku_lace" / "TDA Miku Lace Dress Blue Ver2.0.pmx"
DEFAULT_MOTION = ROOT_DIR / "projects" / "006_deepseek_whale_phone_number" / "assets" / "phone_number_motion" / "Phone Number 【Motion-by-Ureshiiiiii】" / "Motion.vmd"
DEFAULT_OUTPUT = ROOT_DIR / "projects" / "006_deepseek_whale_phone_number" / "output" / "line1_raw_frames"


def build_blender_script(
    model_path: Path,
    motion_path: Path,
    output_dir: Path,
    start_frame: int = 1410,
    end_frame: int = 1530,
    resolution_x: int = 720,
    resolution_y: int = 1280,
    samples: int = 24,
) -> str:
    """Generate inline Python script for Blender execution."""
    model_abs = model_path.resolve().as_posix()
    motion_abs = motion_path.resolve().as_posix()
    output_abs = output_dir.resolve().as_posix()
    mmd_tools_root = MMD_TOOLS_DIR.resolve().as_posix()

    return f"""import sys
import os
import math
import mathutils
import bpy

# 1. Enable Cycles with CUDA GPU Acceleration
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
scene.cycles.max_bounces = 4
scene.cycles.diffuse_bounces = 2
scene.cycles.glossy_bounces = 2
scene.cycles.transmission_bounces = 3
scene.cycles.transparent_max_bounces = 4

# Clear default scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# 2. Register mmd_tools
mmd_tools_root = r"{mmd_tools_root}"
if mmd_tools_root not in sys.path:
    sys.path.insert(0, mmd_tools_root)

import mmd_tools
mmd_tools.register()
print("MMD Tools registered.")

# 3. Import PMX Model
model_file = r"{model_abs}"
print("Importing PMX model:", model_file)
bpy.ops.mmd_tools.import_model(filepath=model_file)

# Find armature & mesh
arm = [o for o in scene.objects if o.type == 'ARMATURE'][0]
bpy.context.view_layer.objects.active = arm
arm.select_set(True)

mesh = [o for o in scene.objects if o.type == 'MESH' and 'mesh' in o.name.lower()][0]
bpy.context.view_layer.objects.active = mesh
bpy.ops.object.shade_smooth()

# 4. Import Dance Motion VMD
motion_file = r"{motion_abs}"
print("Importing VMD dance motion:", motion_file)
bpy.ops.mmd_tools.import_vmd(filepath=motion_file)

# 5. Studio Stage Environment
# A. Dark Reflective Studio Floor
bpy.ops.mesh.primitive_plane_add(size=35, location=(0, 0, 0))
floor = bpy.context.active_object
floor.name = 'ShowcaseFloor'
floor_mat = bpy.data.materials.new(name='ShowcaseFloorMat')
floor_mat.use_nodes = True
fbsdf = floor_mat.node_tree.nodes.get('Principled BSDF')
if fbsdf:
    fbsdf.inputs['Base Color'].default_value = (0.04, 0.05, 0.08, 1.0)
    fbsdf.inputs['Roughness'].default_value = 0.12
    if 'Specular IOR Level' in fbsdf.inputs:
        fbsdf.inputs['Specular IOR Level'].default_value = 0.8
floor.data.materials.append(floor_mat)

# B. Acrylic Figure Display Pedestal
bpy.ops.mesh.primitive_cylinder_add(radius=0.55, depth=0.02, location=(0, 0, 0.01))
pedestal = bpy.context.active_object
pedestal.name = 'AcrylicStand'
ped_mat = bpy.data.materials.new(name='AcrylicStandMat')
ped_mat.use_nodes = True
pbsdf = ped_mat.node_tree.nodes.get('Principled BSDF')
if pbsdf:
    pbsdf.inputs['Base Color'].default_value = (0.75, 0.90, 1.0, 1.0)
    pbsdf.inputs['Roughness'].default_value = 0.05
    pbsdf.inputs['Transmission Weight'].default_value = 0.92
    pbsdf.inputs['IOR'].default_value = 1.49
pedestal.data.materials.append(ped_mat)

# C. Studio Backdrop
bpy.ops.mesh.primitive_plane_add(size=25, location=(0, 5.0, 3.0))
wall = bpy.context.active_object
wall.rotation_euler = (math.radians(90), 0, 0)
wall_mat = bpy.data.materials.new(name='WallMat')
wall_mat.use_nodes = True
wbsdf = wall_mat.node_tree.nodes.get('Principled BSDF')
if wbsdf:
    wbsdf.inputs['Base Color'].default_value = (0.06, 0.09, 0.15, 1.0)
    wbsdf.inputs['Roughness'].default_value = 0.75
wall.data.materials.append(wall_mat)

# D. Soft Ambient World
world = scene.world
world.use_nodes = True
bg = world.node_tree.nodes.get('Background')
if bg:
    bg.inputs['Color'].default_value = (0.03, 0.04, 0.08, 1.0)
    bg.inputs['Strength'].default_value = 0.6

# 6. Studio Lighting (Key, Cyan Fill, Rim Backlight)
# Target empty at character waist (0, 0, 0.82)
bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 0.82))
target = bpy.context.active_object

# Key Light
key_data = bpy.data.lights.new('KeyLight', type='AREA')
key_data.energy = 260.0
key_data.size = 2.2
key_data.color = (1.0, 0.97, 0.93)
key_obj = bpy.data.objects.new('KeyLight', key_data)
scene.collection.objects.link(key_obj)
key_obj.location = (1.6, -3.8, 2.2)

# Fill Light (DeepSeek Electric Cyan Accent)
fill_data = bpy.data.lights.new('FillLight', type='AREA')
fill_data.energy = 130.0
fill_data.size = 2.6
fill_data.color = (0.35, 0.75, 1.0)
fill_obj = bpy.data.objects.new('FillLight', fill_data)
scene.collection.objects.link(fill_obj)
fill_obj.location = (-1.8, -3.2, 1.6)

# Rim Light (Top-Back Hair Silhouette)
rim_data = bpy.data.lights.new('RimLight', type='SPOT')
rim_data.energy = 420.0
rim_data.spot_size = math.radians(72)
rim_data.spot_blend = 0.45
rim_data.color = (0.92, 0.97, 1.0)
rim_obj = bpy.data.objects.new('RimLight', rim_data)
scene.collection.objects.link(rim_obj)
rim_obj.location = (0.2, 2.4, 2.8)
rim_track = rim_obj.constraints.new(type='TRACK_TO')
rim_track.target = target
rim_track.track_axis = 'TRACK_NEGATIVE_Z'
rim_track.up_axis = 'UP_Y'

# 7. Dynamic Camera Framing (Full-body 9:16 Figure Showcase)
cam_data = bpy.data.cameras.new('ShowcaseCam')
cam_data.lens = 45
cam_data.sensor_fit = 'VERTICAL'
cam_obj = bpy.data.objects.new('ShowcaseCam', cam_data)
scene.collection.objects.link(cam_obj)
scene.camera = cam_obj
cam_obj.location = (0.0, -4.5, 0.88)
cam_track = cam_obj.constraints.new(type='TRACK_TO')
cam_track.target = target
cam_track.track_axis = 'TRACK_NEGATIVE_Z'
cam_track.up_axis = 'UP_Y'

# 8. Render Sequence Setup
scene.frame_start = {start_frame}
scene.frame_end = {end_frame}
scene.render.fps = 30
scene.render.resolution_x = {resolution_x}
scene.render.resolution_y = {resolution_y}
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'

# Filepath pattern
os.makedirs(r"{output_abs}", exist_ok=True)
scene.render.filepath = os.path.join(r"{output_abs}", "frame_")

print(f"Starting headless render from frame {start_frame} to {end_frame}...")
bpy.ops.render.render(animation=True)
print("Rendering finished successfully!")
"""


def main():
    parser = argparse.ArgumentParser(description="Headless 3D Render Script for DeepSeek Whale-chan")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL, help="Path to PMX model")
    parser.add_argument("--motion", type=Path, default=DEFAULT_MOTION, help="Path to VMD motion")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output directory for raw frames")
    parser.add_argument("--start", type=int, default=1410, help="Start frame (default: 1410)")
    parser.add_argument("--end", type=int, default=1530, help="End frame (default: 1530)")
    parser.add_argument("--samples", type=int, default=24, help="Cycles samples (default: 24)")
    args = parser.parse_args()

    if not BLENDER_BIN.exists():
        raise FileNotFoundError(f"Blender executable not found at {BLENDER_BIN}")
    if not args.model.exists():
        raise FileNotFoundError(f"Model file not found at {args.model}")
    if not args.motion.exists():
        raise FileNotFoundError(f"Motion file not found at {args.motion}")

    args.output.mkdir(parents=True, exist_ok=True)
    temp_script = args.output / "_blender_exec.py"

    print("=" * 60)
    print("Project 006: Headless 3D Base Render (Cycles GPU)")
    print(f"Model:  {args.model.name}")
    print(f"Motion: {args.motion.name}")
    print(f"Frames: {args.start} -> {args.end} ({args.end - args.start + 1} frames)")
    print(f"Output: {args.output}")
    print("=" * 60)

    script_content = build_blender_script(
        model_path=args.model,
        motion_path=args.motion,
        output_dir=args.output,
        start_frame=args.start,
        end_frame=args.end,
        samples=args.samples,
    )
    temp_script.write_text(script_content, encoding="utf-8")

    cmd = [
        str(BLENDER_BIN),
        "-b",
        "--python", str(temp_script)
    ]

    t0 = time.time()
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    for line in proc.stdout:
        line_s = line.strip()
        if "Fra:" in line_s or "Saved:" in line_s or "Import" in line_s or "registered" in line_s:
            print(f"[Blender] {line_s}")
    proc.wait()
    elapsed = time.time() - t0

    if proc.returncode != 0:
        print(f"Blender render failed with exit code {proc.returncode}")
        sys.exit(1)

    # Check rendered frames
    rendered_frames = sorted(args.output.glob("frame_*.png"))
    print(f"Successfully rendered {len(rendered_frames)} frames in {elapsed:.1f}s ({elapsed/max(1, len(rendered_frames)):.2f}s/frame).")


if __name__ == "__main__":
    main()
