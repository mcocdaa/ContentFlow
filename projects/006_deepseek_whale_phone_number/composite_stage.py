#!/usr/bin/env python3
"""Composite transparent character keyframes onto Cyber Idol Stage background.
Includes contact shadow, circular acrylic base, and stage lighting integration.
"""

import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
import numpy as np

KEYFRAMES_DIR = Path("projects/006_deepseek_whale_phone_number/assets/keyframes")
COMPOSITE_DIR = Path("projects/006_deepseek_whale_phone_number/assets/composite_keyframes")
STAGE_BG_PATH = Path("projects/006_deepseek_whale_phone_number/assets/cyber_stage_vertical.jpg")

COMPOSITE_DIR.mkdir(parents=True, exist_ok=True)

def create_circular_acrylic_base(width, height, center_x, center_y, radius_x=480, radius_y=140):
    """Generates a realistic 3D transparent acrylic figure base with bevels, reflections, and glow."""
    base_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(base_layer)

    # 1. Subtle Outer Cyan Glow
    glow_box = [
        center_x - radius_x - 30, center_y - radius_y - 20,
        center_x + radius_x + 30, center_y + radius_y + 20
    ]
    draw.ellipse(glow_box, fill=(0, 210, 255, 45))
    base_layer = base_layer.filter(ImageFilter.GaussianBlur(15))
    draw = ImageDraw.Draw(base_layer)

    # 2. Main Clear Acrylic Disc Body (Glass refraction tint)
    main_box = [
        center_x - radius_x, center_y - radius_y,
        center_x + radius_x, center_y + radius_y
    ]
    draw.ellipse(main_box, fill=(200, 240, 255, 35), outline=(140, 220, 255, 160), width=3)

    # 3. Inner Bevel Highlight
    inner_box = [
        center_x - int(radius_x * 0.94), center_y - int(radius_y * 0.92),
        center_x + int(radius_x * 0.94), center_y + int(radius_y * 0.92)
    ]
    draw.ellipse(inner_box, outline=(255, 255, 255, 110), width=2)

    # 4. Center Concentric Tech Ring
    center_ring = [
        center_x - int(radius_x * 0.55), center_y - int(radius_y * 0.55),
        center_x + int(radius_x * 0.55), center_y + int(radius_y * 0.55)
    ]
    draw.ellipse(center_ring, outline=(0, 230, 255, 75), width=2)

    # 5. Acrylic Cylindrical Rim / Thickness (lower lip)
    lip_offset = 12
    lip_box = [
        center_x - radius_x, center_y - radius_y + lip_offset,
        center_x + radius_x, center_y + radius_y + lip_offset
    ]
    draw.arc(lip_box, start=0, end=180, fill=(100, 200, 255, 180), width=4)

    return base_layer

def create_contact_shadow(width, height, center_x, center_y, radius_x=440, radius_y=110):
    """Generates soft, realistic multi-layered ambient occlusion and contact shadows."""
    shadow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(shadow_layer)

    # Deep core contact shadow right beneath the base
    core_box = [
        center_x - int(radius_x * 0.75), center_y - int(radius_y * 0.65),
        center_x + int(radius_x * 0.75), center_y + int(radius_y * 0.65)
    ]
    draw.ellipse(core_box, fill=(2, 8, 25, 200))

    # Diffuse ambient shadow
    ambient_box = [
        center_x - radius_x, center_y - radius_y,
        center_x + radius_x, center_y + radius_y
    ]
    draw.ellipse(ambient_box, fill=(5, 15, 40, 130))

    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(18))
    return shadow_layer

def composite_keyframe(fg_path: Path, bg_path: Path, out_path: Path):
    """Composites a single character cutout onto the cyber stage."""
    bg = Image.open(bg_path).convert("RGBA")
    fg = Image.open(fg_path).convert("RGBA")

    w, h = bg.size

    # Ensure fg matches target dimensions (1584, 2816)
    if fg.size != (w, h):
        fg = fg.resize((w, h), Image.Resampling.LANCZOS)

    # Locate character foot contact plane
    alpha = np.array(fg.split()[-1])
    y_coords, x_coords = np.where(alpha > 20)
    foot_y = int(np.percentile(y_coords, 99)) if len(y_coords) > 0 else 2650
    center_x = int(np.mean(x_coords)) if len(x_coords) > 0 else (w // 2)

    base_center_y = foot_y + 10

    # 1. Create Stage Composite Canvas
    composite = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    composite.paste(bg, (0, 0))

    # 2. Add Contact Shadow
    shadow = create_contact_shadow(w, h, center_x, base_center_y + 20, radius_x=500, radius_y=130)
    composite.alpha_composite(shadow)

    # 3. Add Circular Acrylic Base
    acrylic_base = create_circular_acrylic_base(w, h, center_x, base_center_y, radius_x=490, radius_y=135)
    composite.alpha_composite(acrylic_base)

    # 4. Paste Character Cutout
    composite.alpha_composite(fg)

    # 5. Subtle Stage Atmosphere / Lighting Rim Pass
    # Soft light overlay to bind figure into the cyan-blue stage lighting
    lighting_overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw_light = ImageDraw.Draw(lighting_overlay)
    # Spotlights beam intersection gradient at upper center
    draw_light.ellipse([w//2 - 500, -100, w//2 + 500, 1200], fill=(0, 180, 255, 18))
    # Stage floor reflection tint
    draw_light.rectangle([0, h - 600, w, h], fill=(0, 100, 220, 15))
    lighting_overlay = lighting_overlay.filter(ImageFilter.GaussianBlur(40))

    composite.alpha_composite(lighting_overlay)

    # Convert to RGB and save as high-quality JPEG / PNG
    final_rgb = composite.convert("RGB")
    final_rgb.save(out_path, quality=98)
    print(f"[+] Composited: {out_path.name} ({out_path.stat().st_size} bytes)")
    return out_path

def main():
    cutout_files = sorted(KEYFRAMES_DIR.glob("*_transparent.png"))
    print(f"[*] Found {len(cutout_files)} transparent cutouts to composite.")

    for idx, fg_path in enumerate(cutout_files, 1):
        out_name = f"composite_keyframe_{idx:02d}.jpg"
        out_path = COMPOSITE_DIR / out_name
        composite_keyframe(fg_path, STAGE_BG_PATH, out_path)

    print("[+] All composite keyframes successfully created!")

if __name__ == "__main__":
    main()
