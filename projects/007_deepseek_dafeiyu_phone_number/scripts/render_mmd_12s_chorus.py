#!/usr/bin/env python3
"""Fast Headless Blender MMD Chorus Reference Renderer for Project 007.

Renders frames 1440..1919 (16.00 seconds of active Phone Number chorus dance)
and encodes a 720x1280 30fps reference video for Kling 3.0 motion_control.
"""

import argparse
import subprocess
import tempfile
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
PROJECT_DIR = ROOT_DIR / "projects" / "007_deepseek_dafeiyu_phone_number"
BLENDER_BIN = ROOT_DIR / "vendor" / "blender" / "blender"
MMD_TOOLS_DIR = ROOT_DIR / "vendor" / "blender_mmd_tools"

DEFAULT_MODEL = ROOT_DIR / "library" / "models" / "tda_luka_dress" / "TDA Luka Dress.pmx"
DEFAULT_MOTION = (
    PROJECT_DIR
    / "assets"
    / "phone_number_motion"
    / "Phone Number 【Motion-by-Ureshiiiiii】"
    / "Motion.vmd"
)
DEFAULT_OUTPUT_MP4 = PROJECT_DIR / "assets" / "mmd_16s_chorus_ref.mp4"


def build_blender_script(
    model_path: Path,
    motion_path: Path,
    frames_dir: Path,
    start_frame: int = 1440,
    end_frame: int = 1919,
    frame_step: int = 2,
    resolution_x: int = 360,
    resolution_y: int = 640,
    samples: int = 2,
) -> str:
    model_abs = model_path.resolve().as_posix()
    motion_abs = motion_path.resolve().as_posix()
    frames_abs = frames_dir.resolve().as_posix()
    mmd_tools_root = MMD_TOOLS_DIR.resolve().as_posix()

    return f"""import sys
import os
import math
import bpy
import bmesh

cpref = bpy.context.preferences.addons['cycles'].preferences
cpref.compute_device_type = 'CUDA'
cpref.get_devices()
for d in cpref.devices:
    d.use = (d.type == 'CUDA')

scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'GPU'
scene.cycles.samples = {samples}
scene.cycles.use_denoising = False
scene.cycles.max_bounces = 1
scene.cycles.diffuse_bounces = 1
scene.cycles.glossy_bounces = 0
scene.cycles.transmission_bounces = 0
scene.cycles.transparent_max_bounces = 1

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

mmd_tools_root = r"{mmd_tools_root}"
if mmd_tools_root not in sys.path:
    sys.path.insert(0, mmd_tools_root)

import mmd_tools
mmd_tools.register()

bpy.ops.mmd_tools.import_model(filepath=r"{model_abs}")

arm = [o for o in scene.objects if o.type == 'ARMATURE'][0]
bpy.context.view_layer.objects.active = arm
arm.select_set(True)

mesh = [o for o in scene.objects if o.type == 'MESH' and 'mesh' in o.name.lower()][0]
bpy.context.view_layer.objects.active = mesh
bpy.ops.object.shade_smooth()

bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(mesh.data)
hide_keywords = ["ドレス・スカート", "ドレス・エッジ", "スカート裏", "パニエ", "ダイヤモンド", "薔薇腰飾り", "リボン", "リボン裏", "リストレット", "メガネ", "レンズ"]
hide_indices = set(i for i, m in enumerate(mesh.data.materials) if any(k in m.name for k in hide_keywords))
faces_to_delete = [f for f in bm.faces if f.material_index in hide_indices]
bmesh.ops.delete(bm, geom=faces_to_delete, context='FACES')
bmesh.update_edit_mesh(mesh.data)
bpy.ops.object.mode_set(mode='OBJECT')

bpy.ops.mmd_tools.import_vmd(filepath=r"{motion_abs}")

world = scene.world
world.use_nodes = True
bg = world.node_tree.nodes.get('Background')
if bg:
    bg.inputs['Color'].default_value = (0.06, 0.09, 0.16, 1.0)
    bg.inputs['Strength'].default_value = 1.2

bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 0.82))
target = bpy.context.active_object

key_data = bpy.data.lights.new('KeyLight', type='SUN')
key_data.energy = 3.5
key_obj = bpy.data.objects.new('KeyLight', key_data)
scene.collection.objects.link(key_obj)
key_obj.rotation_euler = (math.radians(55), 0, math.radians(25))

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

scene.frame_start = {start_frame}
scene.frame_end = {end_frame}
scene.frame_step = {frame_step}
scene.render.fps = 30
scene.render.resolution_x = {resolution_x}
scene.render.resolution_y = {resolution_y}
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'JPEG'
scene.render.image_settings.quality = 90

os.makedirs(r"{frames_abs}", exist_ok=True)
scene.render.filepath = os.path.join(r"{frames_abs}", "frame_")

bpy.ops.render.render(animation=True)
"""


def main():
    parser = argparse.ArgumentParser(description="Render 16.0s MMD Chorus Reference Video")
    parser.add_argument("--start", type=int, default=1440, help="Start frame (default: 1440)")
    parser.add_argument("--end", type=int, default=1919, help="End frame (default: 1919, 480 frames = 16.0s)")
    parser.add_argument("--step", type=int, default=2, help="Frame step (default: 2 -> 15fps interpolated to 30fps)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_MP4, help="Output MP4 path")
    args = parser.parse_args()

    t0 = time.time()
    total_frames = (args.end - args.start) // args.step + 1
    in_fps = 30.0 / args.step

    with tempfile.TemporaryDirectory(prefix="mmd_fast_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        script_file = tmp_path / "render_job.py"
        script_file.write_text(
            build_blender_script(
                model_path=DEFAULT_MODEL,
                motion_path=DEFAULT_MOTION,
                frames_dir=tmp_path,
                start_frame=args.start,
                end_frame=args.end,
                frame_step=args.step,
            ),
            encoding="utf-8",
        )

        print(f"[1/2] Rendering {total_frames} keyframes ({args.start}..{args.end} step {args.step})...")
        proc = subprocess.Popen(
            [str(BLENDER_BIN), "-b", "--python", str(script_file)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        saved_count = 0
        for line in proc.stdout:
            if "Saved:" in line:
                saved_count += 1
                if saved_count % 20 == 0 or saved_count == total_frames:
                    print(f"  Rendered {saved_count}/{total_frames} frames ({time.time() - t0:.1f}s)")
        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"Blender exited with code {proc.returncode}")

        args.output.parent.mkdir(parents=True, exist_ok=True)
        print(f"[2/2] Encoding 720x1280 30fps MP4 -> {args.output}")
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-framerate",
                f"{in_fps}",
                "-pattern_type",
                "glob",
                "-i",
                str(tmp_path / "frame_*.jpg"),
                "-vf",
                "scale=720:1280:flags=lanczos,framerate=fps=30",
                "-r",
                "30",
                "-c:v",
                "libx264",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                str(args.output),
            ],
            check=True,
        )

    print(f"Done in {time.time() - t0:.1f}s -> {args.output}")


if __name__ == "__main__":
    main()
