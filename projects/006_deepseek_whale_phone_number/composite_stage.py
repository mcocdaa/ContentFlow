#!/usr/bin/env python3
"""Composite transparent character keyframes onto Cyber Idol Stage background.
Includes contact shadow, circular acrylic base, and stage lighting integration.
Guarantees rock-solid alignment of the acrylic base and shadows to eliminate sliding/floating.
"""

import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
import numpy as np

KEYFRAMES_DIR = Path("projects/006_deepseek_whale_phone_number/assets/keyframes")
COMPOSITE_DIR = Path("projects/006_deepseek_whale_phone_number/assets/composite_keyframes")
STAGE_BG_PATH = Path("projects/006_deepseek_whale_phone_number/assets/cyber_stage_vertical.jpg")
SCALED_DIR = COMPOSITE_DIR / "scaled_720x1280"

COMPOSITE_DIR.mkdir(parents=True, exist_ok=True)
SCALED_DIR.mkdir(parents=True, exist_ok=True)

# Fixed stage geometry: Stage canvas 1584 x 2816
STAGE_W = 1584
STAGE_H = 2816
FIXED_BASE_X = STAGE_W // 2  # 792
FIXED_BASE_Y = 2620
FIXED_RADIUS_X = 490
FIXED_RADIUS_Y = 135
TARGET_CHAR_HEIGHT = 2420
TARGET_FOOT_Y = 2615

POSES_ORDER = [
    ("pose1", "pose1_call_me_sway_right_transparent.png"),
    ("pose2", "pose2_seductive_hip_left_transparent.png"),
    ("pose3", "pose3_rhythmic_double_pulse_transparent.png"),
    ("pose3b", "pose3b_quarter_turn_45deg_transparent.png"),
    ("pose3c", "profile_turn_90deg_transparent.png"),
    ("pose4", "pose4_turn_back_swirling_tails_transparent.png"),
    ("pose5", "pose5_final_wink_dynamic_idol_transparent.png"),
]

def create_circular_acrylic_base(width, height, center_x, center_y, radius_x=490, radius_y=135):
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

def create_contact_shadow(width, height, center_x, center_y, radius_x=500, radius_y=130):
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

def create_acrylic_feet_reflection(fg_layer, width, height, center_x, center_y, radius_x, radius_y, foot_plane_y):
    """Generates a soft glossy mirror reflection of the character feet within the acrylic disc."""
    refl_canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    
    # Crop bottom portion of character (lower legs & shoes)
    crop_top = max(0, foot_plane_y - 450)
    crop_bottom = min(height, foot_plane_y + 30)
    legs = fg_layer.crop((0, crop_top, width, crop_bottom))
    legs_flipped = legs.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    
    # Fade reflection downward
    w_crop, h_crop = legs.size
    fade_mask = Image.new("L", (w_crop, h_crop), 0)
    draw_fade = ImageDraw.Draw(fade_mask)
    for row in range(h_crop):
        alpha_val = int(50 * (1.0 - (row / h_crop) ** 0.8))
        draw_fade.line([(0, row), (w_crop, row)], fill=alpha_val)
    
    legs_flipped.putalpha(ImageEnhance.Brightness(fade_mask).enhance(1.0))
    legs_flipped = legs_flipped.filter(ImageFilter.GaussianBlur(3))
    
    # Paste reflection right below foot contact plane
    refl_paste_y = foot_plane_y - 15
    refl_canvas.paste(legs_flipped, (0, refl_paste_y), mask=legs_flipped.split()[-1])
    
    # Mask strictly to the acrylic disc ellipse
    disc_mask = Image.new("L", (width, height), 0)
    draw_mask = ImageDraw.Draw(disc_mask)
    draw_mask.ellipse([
        center_x - int(radius_x * 0.95), center_y - int(radius_y * 0.92),
        center_x + int(radius_x * 0.95), center_y + int(radius_y * 0.92)
    ], fill=255)
    disc_mask = disc_mask.filter(ImageFilter.GaussianBlur(4))
    
    final_refl = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    final_refl.paste(refl_canvas, (0, 0), mask=disc_mask)
    return final_refl

def prepare_stage_base(w, h):
    """Pre-renders the static cyber stage with fixed contact shadow, acrylic base, and atmospheric lighting."""
    bg = Image.open(STAGE_BG_PATH).convert("RGBA")
    if bg.size != (w, h):
        bg = bg.resize((w, h), Image.Resampling.LANCZOS)
    
    stage_base = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    stage_base.paste(bg, (0, 0))

    # Add rock-solid fixed contact shadow
    shadow = create_contact_shadow(w, h, FIXED_BASE_X, FIXED_BASE_Y + 20, radius_x=500, radius_y=130)
    stage_base.alpha_composite(shadow)

    # Add rock-solid fixed circular acrylic base
    acrylic_base = create_circular_acrylic_base(w, h, FIXED_BASE_X, FIXED_BASE_Y, radius_x=FIXED_RADIUS_X, radius_y=FIXED_RADIUS_Y)
    stage_base.alpha_composite(acrylic_base)

    return stage_base

def align_and_scale_cutout(fg: Image.Image, w: int, h: int):
    """Aligns character cutout height and foot plane so feet precisely touch the acrylic base."""
    alpha = np.array(fg.split()[-1])
    row_counts = np.sum(alpha > 50, axis=1)
    dense_rows = np.where(row_counts >= 15)[0]
    if len(dense_rows) == 0:
        return fg
    
    head_y = dense_rows.min()
    foot_y = dense_rows.max()
    actual_h = foot_y - head_y
    
    scale = TARGET_CHAR_HEIGHT / float(actual_h)
    new_w = int(fg.width * scale)
    new_h = int(fg.height * scale)
    
    fg_resized = fg.resize((new_w, new_h), Image.Resampling.LANCZOS)
    
    # Calculate offsets
    dx = (w - new_w) // 2
    dy = int(TARGET_FOOT_Y - foot_y * scale)
    
    aligned_fg = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    aligned_fg.paste(fg_resized, (dx, dy), mask=fg_resized.split()[-1])
    return aligned_fg

def composite_pose(fg_path: Path, static_stage: Image.Image, out_path_2k: Path, out_path_720p: Path):
    w, h = STAGE_W, STAGE_H
    fg_orig = Image.open(fg_path).convert("RGBA")
    
    # Ensure 1584 x 2816
    if fg_orig.size != (w, h):
        fg_orig = fg_orig.resize((w, h), Image.Resampling.LANCZOS)
    
    # Align figure height and foot plane to the acrylic disc
    fg = align_and_scale_cutout(fg_orig, w, h)
    
    # Start with stationary stage background & acrylic base
    composite = static_stage.copy()
    
    # Subtle acrylic surface feet reflection
    feet_refl = create_acrylic_feet_reflection(fg, w, h, FIXED_BASE_X, FIXED_BASE_Y, FIXED_RADIUS_X, FIXED_RADIUS_Y, TARGET_FOOT_Y)
    composite.alpha_composite(feet_refl)
    
    # Place aligned character figure
    composite.alpha_composite(fg)
    
    # Subtle stage cyan atmosphere & spotlights rim pass
    lighting_overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw_light = ImageDraw.Draw(lighting_overlay)
    # Spotlights beam intersection gradient at upper center
    draw_light.ellipse([w//2 - 500, -100, w//2 + 500, 1200], fill=(0, 180, 255, 18))
    # Stage floor reflection tint
    draw_light.rectangle([0, h - 600, w, h], fill=(0, 100, 220, 15))
    lighting_overlay = lighting_overlay.filter(ImageFilter.GaussianBlur(40))
    composite.alpha_composite(lighting_overlay)
    
    # Save 1584 x 2816 master
    final_rgb = composite.convert("RGB")
    final_rgb.save(out_path_2k, quality=98)
    
    # Save 720 x 1280 for assembly / optical flow
    scaled_720 = final_rgb.resize((720, 1280), Image.Resampling.LANCZOS)
    scaled_720.save(out_path_720p, quality=98)
    
    print(f"[+] Composited: {out_path_2k.name} (2K: {out_path_2k.stat().st_size} B, 720p: {out_path_720p.stat().st_size} B)")

def main():
    print("[*] Preparing stationary Cyber Stage & Acrylic Base...")
    static_stage = prepare_stage_base(STAGE_W, STAGE_H)
    
    print(f"[*] Compositing {len(POSES_ORDER)} keyframes in strict choreography order...")
    for idx, (pose_key, fname) in enumerate(POSES_ORDER, 1):
        fg_path = KEYFRAMES_DIR / fname
        if not fg_path.exists():
            raise FileNotFoundError(f"Missing cutout: {fg_path}")
        
        out_2k = COMPOSITE_DIR / f"composite_keyframe_{idx:02d}.jpg"
        out_720p = SCALED_DIR / f"composite_keyframe_{idx:02d}.png"
        composite_pose(fg_path, static_stage, out_2k, out_720p)
    
    print("[+] All 7 composite keyframes successfully created with 100% stationary acrylic base!")

if __name__ == "__main__":
    main()
