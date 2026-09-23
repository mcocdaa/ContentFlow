#!/usr/bin/env python3
"""Deep AI Anti-Clipping & Material Luster Polisher for Project 006: DeepSeek Whale-chan.

Solves 3D figure rendering flaws:
1. Anti-Clipping (去穿模) & Seam Softening:
   - Identifies high-frequency mesh collision anomalies (skirt-leg, hair-body, facet creases)
   - Applies AI Telea/Navier-Stokes inpainting & edge-preserving bilateral smoothing
2. Persona-Specific Material Luster Injection (DeepSeek Whale-chan):
   - Skin Subsurface Scattering (SSS): Porcelain warm translucency, removes cold dead Cycles shadows
   - Silky Luminous Hair Specular: Anisotropic highlight bands with electric cyan luminescence (#00D2FF)
   - Patent Leather Sheen: Sharp micro-specular gloss on boots, corset trims, and acrylic pedestal
   - Starry Accent Glow: Subtle highlights on jewelry, tiara, and whale ribbons
3. Edge Defringing & Motion-Adaptive Temporal Stabilization:
   - Suppresses chromatic aberration / silhouette fringe
   - Dynamic motion-adaptive temporal filtering prevents inter-frame flicker while preserving fast dance sharpness
"""

import sys
import os
import argparse
import time
from pathlib import Path
import numpy as np
import cv2

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
RAW_FRAMES_DIR = ROOT_DIR / "projects" / "006_deepseek_whale_phone_number" / "output" / "line1_raw_frames"
POLISHED_FRAMES_DIR = ROOT_DIR / "projects" / "006_deepseek_whale_phone_number" / "output" / "line1_polished_frames"


class AIFigurePolisher:
    """End-to-end AI polish engine for 3D figure animation."""

    def __init__(
        self,
        enable_anti_clipping: bool = True,
        enable_luster: bool = True,
        enable_defringing: bool = True,
        enable_temporal: bool = True,
    ):
        self.enable_anti_clipping = enable_anti_clipping
        self.enable_luster = enable_luster
        self.enable_defringing = enable_defringing
        self.enable_temporal = enable_temporal
        self.prev_frame = None

    def detect_clipping_mask(self, frame_bgr: np.ndarray) -> np.ndarray:
        """Detect mesh clipping artifacts and harsh polygonal facet seams."""
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

        # 1. Dress region (light fabric)
        dress_mask = ((v > 120) & (s < 100)).astype(np.uint8) * 255

        # 2. Dark clipping puncture holes/intruders within the dress tiers
        # Clipping creates small dark holes (V < 75) surrounded by light dress
        dark_holes = ((v < 85) & (dress_mask > 0)).astype(np.uint8) * 255
        # Exclude large dark areas like the bottom underskirt or waist bow
        kernel_large = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (19, 19))
        large_dark = cv2.morphologyEx(dark_holes, cv2.MORPH_OPEN, kernel_large)
        clipping_holes = cv2.subtract(dark_holes, large_dark)

        # 3. High-contrast facet seams (Laplacian edges on smooth dress)
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        edge_energy = np.abs(laplacian)
        facet_seams = ((edge_energy > 30) & (edge_energy < 85) & (dress_mask > 0)).astype(np.uint8) * 255

        # Combine
        combined = cv2.bitwise_or(clipping_holes, facet_seams)
        kernel_dilate = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        clipping_mask = cv2.dilate(combined, kernel_dilate, iterations=1)
        return clipping_mask

    def repair_anti_clipping(self, frame_bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """Repair clipping anomalies using inpainting + edge-preserving bilateral filtering."""
        if cv2.countNonZero(mask) == 0:
            return frame_bgr

        # Inpaint clipping puncture holes
        inpainted = cv2.inpaint(frame_bgr, mask, inpaintRadius=4, flags=cv2.INPAINT_TELEA)

        # Edge-preserving bilateral filter on repaired regions to smooth polygonal facets
        smoothed = cv2.bilateralFilter(inpainted, d=5, sigmaColor=35, sigmaSpace=35)

        # Soft blending with distance transform
        dist = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
        max_dist = max(np.max(dist), 1.0)
        norm_dist = np.clip(dist / max_dist, 0.0, 1.0)[:, :, np.newaxis]

        result = (frame_bgr.astype(np.float32) * (1.0 - norm_dist * 0.85) +
                  smoothed.astype(np.float32) * (norm_dist * 0.85)).astype(np.uint8)
        return result

    def inject_material_luster(self, frame_bgr: np.ndarray) -> np.ndarray:
        """Inject persona-level material luster (DeepSeek Whale-chan):
        - Skin Subsurface Scattering (warm peach glow, removes grey Cycles shadows)
        - Silky Luminous Hair Specular (cyan #00D2FF highlight bands)
        - Patent Leather Gloss on boots & corset
        - Subtle figure bloom
        """
        img_f = frame_bgr.astype(np.float32) / 255.0
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)

        # ---------------------------------------------------------
        # A. Skin Subsurface Scattering (SSS)
        # ---------------------------------------------------------
        is_warm_hue = ((h <= 24) | (h >= 170))
        skin_mask = (is_warm_hue & (s >= 22) & (s <= 140) & (v >= 110)).astype(np.uint8) * 255
        kernel_skin = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        skin_mask = cv2.erode(skin_mask, kernel_skin, iterations=1)

        skin_f = skin_mask.astype(np.float32) / 255.0
        skin_glow = cv2.GaussianBlur(img_f, (11, 11), 3.5)
        
        sss_tint = np.zeros_like(img_f)
        sss_tint[:, :, 0] = skin_glow[:, :, 0] * 0.88   # Blue reduction
        sss_tint[:, :, 1] = skin_glow[:, :, 1] * 1.06   # Gentle green
        sss_tint[:, :, 2] = skin_glow[:, :, 2] * 1.20   # Warm red boost

        skin_alpha = skin_f[:, :, np.newaxis] * 0.38
        img_f = img_f * (1.0 - skin_alpha) + (img_f * 0.65 + sss_tint * 0.35) * skin_alpha

        # ---------------------------------------------------------
        # B. Silky Luminous Hair Specular (DeepSeek Cyan/Teal Luster)
        # ---------------------------------------------------------
        hair_mask = ((h >= 80) & (h <= 118) & (s >= 30) & (v >= 40)).astype(np.uint8) * 255
        hair_silver = ((h >= 75) & (h <= 125) & (s < 30) & (v >= 190)).astype(np.uint8) * 255
        full_hair_mask = cv2.bitwise_or(hair_mask, hair_silver)

        hair_v = v.astype(np.float32) / 255.0
        hair_v_masked = hair_v * (full_hair_mask.astype(np.float32) / 255.0)

        # Directional highlight band extraction
        spec_kernel = np.ones((1, 7), np.float32) / 7.0
        hair_spec = cv2.filter2D(hair_v_masked, -1, spec_kernel)
        hair_spec_band = np.clip((hair_spec - 0.65) * 2.8, 0.0, 1.0)
        
        # DeepSeek electric cyan: BGR [1.0, 0.82, 0.1]
        cyan_accent = np.zeros_like(img_f)
        cyan_accent[:, :, 0] = 0.95
        cyan_accent[:, :, 1] = 0.80
        cyan_accent[:, :, 2] = 0.10

        hair_spec_3d = hair_spec_band[:, :, np.newaxis] * 0.28
        img_f = 1.0 - (1.0 - img_f) * (1.0 - cyan_accent * hair_spec_3d)

        # ---------------------------------------------------------
        # C. Patent Leather & High-Sheen Reflections (Boots, Corset, Base)
        # ---------------------------------------------------------
        is_dark = (v < 110).astype(np.uint8) * 255
        spec_points = ((v > 190) & (is_dark == 0)).astype(np.uint8) * 255
        kernel_spec = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        spec_dilated = cv2.dilate(spec_points, kernel_spec, iterations=1)
        spec_bloom = cv2.GaussianBlur(spec_dilated.astype(np.float32)/255.0, (7, 7), 2.0)

        img_f = np.clip(img_f + spec_bloom[:, :, np.newaxis] * 0.12, 0.0, 1.0)

        # ---------------------------------------------------------
        # D. Controlled Subtle Bloom
        # ---------------------------------------------------------
        lum = 0.299 * img_f[:, :, 2] + 0.587 * img_f[:, :, 1] + 0.114 * img_f[:, :, 0]
        bright_mask = np.clip((lum - 0.88) / 0.12, 0.0, 1.0)
        bloom = cv2.GaussianBlur(bright_mask, (15, 15), 5.0)[:, :, np.newaxis]

        bloom_color = np.array([0.95, 0.92, 0.85], dtype=np.float32)
        img_f = np.clip(img_f + bloom * bloom_color * 0.10, 0.0, 1.0)

        return (img_f * 255.0).astype(np.uint8)

    def defringe_edges(self, frame_bgr: np.ndarray) -> np.ndarray:
        """Suppress color fringing and harsh dark seams along figure silhouette boundaries."""
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 60, 160)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        dilated_edges = cv2.dilate(edges, kernel, iterations=1)

        # Apply guided median filter only to boundary edge pixels
        median = cv2.medianBlur(frame_bgr, 3)
        edge_weight = (dilated_edges.astype(np.float32) / 255.0)[:, :, np.newaxis]

        defringed = (frame_bgr.astype(np.float32) * (1.0 - edge_weight * 0.45) +
                     median.astype(np.float32) * (edge_weight * 0.45)).astype(np.uint8)
        return defringed

    def stabilize_temporal(self, curr_frame: np.ndarray) -> np.ndarray:
        """Motion-adaptive temporal coherence filter to eliminate inter-frame flicker."""
        if self.prev_frame is None or not self.enable_temporal:
            self.prev_frame = curr_frame.copy()
            return curr_frame

        # Compute frame motion energy
        diff = cv2.absdiff(curr_frame, self.prev_frame)
        motion_energy = np.mean(diff, axis=2) / 255.0

        # In low-motion areas (background, torso), alpha=0.22 to eliminate render noise/flicker
        # In fast-motion areas (dancing hands/feet), alpha=0.04 to prevent ghosting
        alpha = np.clip(0.22 - motion_energy * 0.65, 0.04, 0.22)[:, :, np.newaxis]

        stabilized = (curr_frame.astype(np.float32) * (1.0 - alpha) +
                      self.prev_frame.astype(np.float32) * alpha).astype(np.uint8)
        self.prev_frame = stabilized.copy()
        return stabilized

    def polish_single_frame(self, frame_bgr: np.ndarray) -> np.ndarray:
        """Run full AI polish pipeline on a single frame."""
        # 1. Anti-Clipping & Seam Softening
        if self.enable_anti_clipping:
            clip_mask = self.detect_clipping_mask(frame_bgr)
            out = self.repair_anti_clipping(frame_bgr, clip_mask)
        else:
            out = frame_bgr

        # 2. Material Luster Injection (SSS + Silky Hair + Patent Leather)
        if self.enable_luster:
            out = self.inject_material_luster(out)

        # 3. Edge Defringing
        if self.enable_defringing:
            out = self.defringe_edges(out)

        # 4. Motion-Adaptive Temporal Stabilization
        if self.enable_temporal:
            out = self.stabilize_temporal(out)

        return out

    def process_sequence(self, input_dir: Path, output_dir: Path):
        """Process an entire image sequence directory."""
        input_dir = Path(input_dir).resolve()
        output_dir = Path(output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        frames = sorted(input_dir.glob("*.png"))
        if not frames:
            raise FileNotFoundError(f"No PNG frames found in {input_dir}")

        total = len(frames)
        print("=" * 60)
        print("Deep AI Anti-Clipping & Material Luster Polishing")
        print(f"Input Directory:  {input_dir} ({total} frames)")
        print(f"Output Directory: {output_dir}")
        print("Pipeline Stages:")
        print("  [x] Mesh Anti-Clipping (Telea inpainting + Bilateral smoothing)")
        print("  [x] Skin Subsurface Scattering (Warm porcelain translucency)")
        print("  [x] DeepSeek Silky Hair Specular (#00D2FF cyan flow)")
        print("  [x] Patent Leather & Acrylic Base Glint")
        print("  [x] Edge Defringing & Motion-Adaptive Temporal Smoothing")
        print("=" * 60)

        t0 = time.time()
        for idx, frame_path in enumerate(frames, 1):
            frame = cv2.imread(str(frame_path), cv2.IMREAD_COLOR)
            if frame is None:
                print(f"Warning: Failed to read {frame_path.name}, skipping.")
                continue

            polished = self.polish_single_frame(frame)
            out_path = output_dir / frame_path.name
            cv2.imwrite(str(out_path), polished)

            if idx % 10 == 0 or idx == total:
                elapsed = time.time() - t0
                fps = idx / max(1e-3, elapsed)
                print(f"[{idx:03d}/{total:03d}] Polished {frame_path.name} | Rate: {fps:.1f} fps")

        total_time = time.time() - t0
        print("=" * 60)
        print(f"Polishing complete! Processed {total} frames in {total_time:.2f}s ({total/total_time:.1f} fps).")
        print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="AI Polish & Anti-Clipping for 3D Figures")
    parser.add_argument("--input", type=Path, default=RAW_FRAMES_DIR, help="Input directory of raw frames")
    parser.add_argument("--output", type=Path, default=POLISHED_FRAMES_DIR, help="Output directory of polished frames")
    parser.add_argument("--no-clipping", action="store_true", help="Disable anti-clipping")
    parser.add_argument("--no-luster", action="store_true", help="Disable material luster injection")
    parser.add_argument("--no-temporal", action="store_true", help="Disable temporal stabilization")
    args = parser.parse_args()

    polisher = AIFigurePolisher(
        enable_anti_clipping=not args.no_clipping,
        enable_luster=not args.no_luster,
        enable_temporal=not args.no_temporal,
    )
    polisher.process_sequence(args.input, args.output)


if __name__ == "__main__":
    main()
