#!/usr/bin/env python3
"""1080P @ 60FPS Theatrical 2D Multi-Shot Anime Comedy Assembler for Episode 018.

Episode 018: 《AI合租B站号第2集》24h 晨曦便利店关东煮分赃会
- 7 x 10s Kling 4.0 Omni-Ref 1080p native multi-shot acts (~70.1s, strictly >= 60.0s)
- O(1) OpenCV DIS optical flow interpolation -> 1920x1080, SAR=1:1, DAR=16:9, 60.00fps, yuv420p, bt709
- Native Kling 4.0 multi-character Chinese voice acting & foley + dynamically ducked CC0/Free Bilibili BGM -> -14 LUFS
- K2 Hook Banner + millisecond-aligned Noto Sans CJK SC subtitles
- Spotless trio hero cutout (white-garment/prop interior protected) + bright vivid_scene 16:9 & 4:3 covers
"""

from __future__ import annotations

import gc
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

SCRIPT_DIR = Path(__file__).resolve().parent
PROJ_DIR = SCRIPT_DIR.parent
ROOT_DIR = PROJ_DIR.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.cover_designer import SAFE_ZONE_X_MAX, SAFE_ZONE_X_MIN, TARGET_HEIGHT, TARGET_WIDTH, CoverDesigner  # noqa: E402
from core.episode_assembler import ActSpec, EpisodeAssembler, EpisodeSpec, probe_video_frame_info  # noqa: E402
from core.studio_renderer import segment_character_rgba  # noqa: E402

ASSETS_DIR = PROJ_DIR / "assets"
BGM_DIR = ASSETS_DIR / "bgm"
OUTPUT_DIR = PROJ_DIR / "output"
RAW_ACTS_DIR = OUTPUT_DIR / "raw_acts"
CUTOUTS_DIR = OUTPUT_DIR / "cutouts"
DELIV_DIR = PROJ_DIR / "delivery"

RAW_ACT_MP4S: List[Path] = [
    RAW_ACTS_DIR / "act1_four_mao_oden_panic.mp4",
    RAW_ACTS_DIR / "act2_counter_debate_slam.mp4",
    RAW_ACTS_DIR / "act3_haku_door_entrance_receipt.mp4",
    RAW_ACTS_DIR / "act4_haku_glasses_cfo_takeover.mp4",
    RAW_ACTS_DIR / "act5_sunbeam_oden_wager.mp4",
    RAW_ACTS_DIR / "act6_counter_standoff_eye_cuts.mp4",
    RAW_ACTS_DIR / "act7_dawn_toast_danmaku_cta_v2.mp4",
]

COVER_HERO_IMG = ASSETS_DIR / "cover_hero_trio_konbini_16x9.jpg"
COVER_BG_IMG = ASSETS_DIR / "cover_bg_dawn_konbini_16x9.jpg"
CUTOUT_PNG = CUTOUTS_DIR / "trio_konbini_hero_cutout.png"

BGM_COMEDY_WAV = BGM_DIR / "BV1o4KwzPERi_plum_free_bgm.wav"
BGM_HYPE_WAV = BGM_DIR / "BV1254y1V7cJ_cc0_upbeat_intro.wav"

OUT_MP4 = DELIV_DIR / "AI合租B站号第2集_24h便利店关东煮分赃会_final.mp4"
OUT_SRT = DELIV_DIR / "AI合租B站号第2集_24h便利店关东煮分赃会_subtitle.srt"
OUT_COVER = DELIV_DIR / "AI合租B站号第2集_24h便利店关东煮分赃会_cover.jpg"
OUT_COVER_4X3 = DELIV_DIR / "AI合租B站号第2集_24h便利店关东煮分赃会_cover_4x3.jpg"

SAMPLE_RATE = 48000


def _probe_act_out_duration(video_path: Path, target_fps: float = 60.0) -> float:
    n_in, src_fps = probe_video_frame_info(video_path)
    n_out = int(round((max(1, n_in) - 1) * (target_fps / src_fps))) + 1
    return n_out / target_fps


def _write_srt(srt_path: Path, cues: List[Tuple[float, float, str]]) -> None:
    def fmt_ts(sec: float) -> str:
        ms = int(round(max(0.0, sec) * 1000.0))
        hh, rem = divmod(ms, 3600000)
        mm, rem = divmod(rem, 60000)
        ss, mmm = divmod(rem, 1000)
        return f"{hh:02d}:{mm:02d}:{ss:02d},{mmm:03d}"

    lines: List[str] = []
    for idx, (s, e, txt) in enumerate(cues, start=1):
        lines.extend([str(idx), f"{fmt_ts(s)} --> {fmt_ts(e)}", txt, ""])
    srt_path.parent.mkdir(parents=True, exist_ok=True)
    srt_path.write_text("\n".join(lines), encoding="utf-8")


def _load_wav_stereo_f32(wav_path: Path) -> np.ndarray:
    """Loads a 48kHz PCM WAV file as shape (N, 2) float32 in [-1.0, 1.0]."""
    with wave.open(str(wav_path), "rb") as wf:
        ch = wf.getnchannels()
        sr = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    if sr != SAMPLE_RATE:
        raise ValueError(f"Expected {SAMPLE_RATE}Hz WAV, got {sr}Hz: {wav_path}")
    arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch == 1:
        return np.stack([arr, arr], axis=-1)
    return arr.reshape(-1, ch)[:, :2]


def _save_wav_stereo_i16(wav_path: Path, audio: np.ndarray) -> None:
    clipped = np.clip(audio, -0.995, 0.995)
    pcm = (clipped * 32767.0).astype(np.int16)
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())


def _extract_native_audio_f32(mp4_path: Path, target_dur_sec: float, tmp_dir: Path) -> np.ndarray:
    """Extracts 48kHz stereo native audio from a Kling 4.0 act MP4 and aligns length exactly."""
    wav_tmp = tmp_dir / f"{mp4_path.stem}_native.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(mp4_path),
            "-vn",
            "-ar",
            str(SAMPLE_RATE),
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(wav_tmp),
        ],
        check=True,
    )
    arr = _load_wav_stereo_f32(wav_tmp)
    target_n = max(1, int(round(target_dur_sec * SAMPLE_RATE)))
    if arr.shape[0] > target_n:
        arr = arr[:target_n]
    elif arr.shape[0] < target_n:
        pad = np.zeros((target_n - arr.shape[0], 2), dtype=np.float32)
        arr = np.concatenate([arr, pad], axis=0)

    # Gentle per-act voice loudness leveling so all 7 acts sound cohesive
    active_rms_vals = np.sqrt(np.mean(arr**2, axis=1))
    voiced = active_rms_vals[active_rms_vals > 0.015]
    if voiced.size > 200:
        cur_rms = float(np.sqrt(np.mean(voiced**2)))
        target_rms = 0.19
        gain = min(1.55, max(0.75, target_rms / max(cur_rms, 1e-4)))
        arr = arr * gain

    peak = float(np.max(np.abs(arr))) if arr.size else 1.0
    if peak > 0.90:
        arr = arr * (0.90 / peak)

    # Smooth 15ms boundary fades to prevent any click at act cuts
    fade_n = min(int(0.015 * SAMPLE_RATE), target_n // 8)
    if fade_n > 0:
        ramp = np.linspace(0.0, 1.0, fade_n, dtype=np.float32)[:, None]
        arr[:fade_n] *= ramp
        arr[-fade_n:] *= ramp[::-1]
    return arr


def _slice_bgm_f32(wav_path: Path, start_sec: float, dur_sec: float) -> np.ndarray:
    """Slices (with seamless loop if needed) a 48kHz stereo BGM WAV and levels its RMS."""
    full = _load_wav_stereo_f32(wav_path)
    total_n = max(1, int(round(dur_sec * SAMPLE_RATE)))
    s0 = int(round(start_sec * SAMPLE_RATE)) % max(1, full.shape[0])
    chunks: List[np.ndarray] = []
    rem = total_n
    cur = s0
    while rem > 0:
        take = min(rem, full.shape[0] - cur)
        chunks.append(full[cur : cur + take])
        rem -= take
        cur = 0
    seg = np.concatenate(chunks, axis=0)
    rms = float(np.sqrt(np.mean(seg**2))) if seg.size else 0.1
    if rms > 1e-4:
        seg = seg * (0.14 / rms)
    return seg


def _build_master_audio(
    act_paths: List[Path],
    act_starts: List[float],
    act_durs: List[float],
    master_wav: Path,
    tmp_dir: Path,
) -> None:
    """Mixes 7 native Kling 4.0 dialogue+foley tracks with dynamically ducked verified CC0/Free BGM."""
    native_parts = [_extract_native_audio_f32(p, d, tmp_dir) for p, d in zip(act_paths, act_durs)]
    native_full = np.concatenate(native_parts, axis=0)
    total_n = native_full.shape[0]
    total_dur = total_n / float(SAMPLE_RATE)

    # Comedy BGM for Acts 1-3, switching cleanly to upbeat CC0 BGM on Act 4 (Haku CFO takeover)
    t_switch = act_starts[3]
    n_switch = int(round(t_switch * SAMPLE_RATE))
    xfade_n = int(0.35 * SAMPLE_RATE)

    bgm_a = _slice_bgm_f32(BGM_COMEDY_WAV, start_sec=0.0, dur_sec=t_switch + 0.5)
    bgm_b = _slice_bgm_f32(BGM_HYPE_WAV, start_sec=14.0, dur_sec=max(1.0, total_dur - t_switch + 0.5))

    bgm_full = np.zeros((total_n, 2), dtype=np.float32)
    n_a = min(total_n, n_switch + xfade_n)
    bgm_full[:n_a] += bgm_a[:n_a]
    if n_switch < total_n:
        n_b = total_n - n_switch
        # Crossfade region [n_switch : n_switch + xfade_n]
        xf = min(xfade_n, n_b, max(0, n_a - n_switch))
        if xf > 0:
            fade_out = np.linspace(1.0, 0.0, xf, dtype=np.float32)[:, None]
            fade_in = 1.0 - fade_out
            bgm_full[n_switch : n_switch + xf] *= fade_out
            bgm_full[n_switch : n_switch + xf] += bgm_b[:xf] * fade_in
        if n_b > xf:
            bgm_full[n_switch + xf :] = bgm_b[xf:n_b]

    # Gentle intro/outro fade on BGM bed
    intro_n = min(int(0.25 * SAMPLE_RATE), total_n // 10)
    outro_n = min(int(0.65 * SAMPLE_RATE), total_n // 10)
    bgm_full[:intro_n] *= np.linspace(0.0, 1.0, intro_n, dtype=np.float32)[:, None]
    bgm_full[-outro_n:] *= np.linspace(1.0, 0.0, outro_n, dtype=np.float32)[:, None]

    # Dynamic RMS sidechain ducking driven by native dialogue+foley envelope
    mono_abs = np.mean(np.abs(native_full), axis=1)
    win = int(0.18 * SAMPLE_RATE)
    kernel = np.ones(win, dtype=np.float32) / float(win)
    env = np.convolve(mono_abs, kernel, mode="same")
    speech_factor = np.clip((env - 0.012) / 0.045, 0.0, 1.0)
    # Duck to 0.16 during speech so every Chinese syllable is crystal clear; lift to 0.38 in pauses
    bgm_gain = (0.38 - 0.22 * speech_factor)[:, None]

    mixed = native_full * 0.96 + bgm_full * bgm_gain
    # Soft saturation safety limiter before EpisodeAssembler -14 LUFS loudnorm
    peak = float(np.max(np.abs(mixed))) if mixed.size else 1.0
    if peak > 0.94:
        mixed = np.tanh(mixed * (0.94 / peak) * 1.05) * 0.94

    _save_wav_stereo_i16(master_wav, mixed)


def _protect_solid_white_garments(src_rgb_img: Path, cutout_png: Path) -> None:
    """Restores solid alpha on interior white garments/props (apron, shirt, receipt, tablet) on #FFFFFF bg."""
    with Image.open(src_rgb_img) as raw_im, Image.open(cutout_png) as cut_im:
        src_np = np.array(raw_im.convert("RGB"))
        cut_rgba = np.array(cut_im.convert("RGBA"))

    if src_np.shape[:2] != cut_rgba.shape[:2]:
        return

    h, w = src_np.shape[:2]
    # Pure white background pixels connected to the image border
    near_white = (src_np[:, :, 0] >= 242) & (src_np[:, :, 1] >= 242) & (src_np[:, :, 2] >= 242)
    mask_u8 = (near_white.astype(np.uint8)) * 255
    flood = mask_u8.copy()
    ff_mask = np.zeros((h + 2, w + 2), dtype=np.uint8)

    # Flood-fill exterior white starting from border white pixels
    border_seeds: List[Tuple[int, int]] = []
    for x in range(0, w, 4):
        if flood[0, x] == 255:
            border_seeds.append((x, 0))
        if flood[h - 1, x] == 255:
            border_seeds.append((x, h - 1))
    for y in range(0, h, 4):
        if flood[y, 0] == 255:
            border_seeds.append((0, y))
        if flood[y, w - 1] == 255:
            border_seeds.append((w - 1, y))

    for sx, sy in border_seeds:
        if flood[sy, sx] == 255:
            cv2.floodFill(flood, ff_mask, (sx, sy), 128)

    # Pixels that are NOT exterior border-connected white (128) are interior garments/receipt/tablet/faces!
    # Keep tiny pure-white gaps inside arm loops clean if rembg marked them 0 AND they are surrounded by pure white;
    # restore interior white regions where rembg partially ate white fabric/paper (alpha between 10 and 245 OR enclosed dark-ink-bounded white)
    interior_not_bg = flood != 128
    # Dilate exterior slightly by 1px to avoid white halo fringe
    exterior_bg = (flood == 128).astype(np.uint8)
    exterior_dilated = cv2.dilate(exterior_bg, np.ones((3, 3), np.uint8), iterations=1) == 1
    safe_interior = interior_not_bg & (~exterior_dilated)

    # Restore interior white garments/receipt/tablet while keeping small pure-white arm-loop holes transparent
    rembg_alpha = cut_rgba[:, :, 3]
    solid_fg = (rembg_alpha >= 180).astype(np.uint8)
    fg_hull = cv2.morphologyEx(solid_fg, cv2.MORPH_CLOSE, np.ones((61, 61), np.uint8))
    restore_mask = safe_interior & (fg_hull > 0)

    # Exclude small pure-white enclosed background gaps (e.g., elbow-to-waist loop) that rembg marked transparent
    pure_white_bg_gap = (
        restore_mask
        & (rembg_alpha < 25)
        & (src_np[:, :, 0] >= 250)
        & (src_np[:, :, 1] >= 250)
        & (src_np[:, :, 2] >= 250)
    )
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(pure_white_bg_gap.astype(np.uint8), connectivity=8)
    for lbl in range(1, num_labels):
        if int(stats[lbl, cv2.CC_STAT_AREA]) < 12000:
            restore_mask[labels == lbl] = False

    new_alpha = rembg_alpha.copy()
    new_alpha[restore_mask] = 255
    # Ensure pure exterior background is 100% transparent
    new_alpha[exterior_bg == 1] = np.minimum(new_alpha[exterior_bg == 1], 0)

    out_rgba = cut_rgba.copy()
    out_rgba[:, :, 3] = new_alpha
    # Use crisp original RGB colors on restored solid interior
    out_rgba[restore_mask, :3] = src_np[restore_mask]
    Image.fromarray(out_rgba, mode="RGBA").save(cutout_png)


def render_cover() -> Tuple[float, float]:
    """Deletes stale cutout, segments trio with solid white protection, and renders vivid_scene 16:9 & 4:3 covers."""
    if not COVER_HERO_IMG.exists():
        raise FileNotFoundError(f"Missing trio hero anchor: {COVER_HERO_IMG}")
    if not COVER_BG_IMG.exists():
        raise FileNotFoundError(f"Missing dawn konbini background: {COVER_BG_IMG}")

    CUTOUTS_DIR.mkdir(parents=True, exist_ok=True)
    CUTOUT_PNG.unlink(missing_ok=True)
    segment_character_rgba(COVER_HERO_IMG, CUTOUT_PNG, crop_roi=None, clean_corner_wm=False)
    _protect_solid_white_garments(COVER_HERO_IMG, CUTOUT_PNG)

    designer = CoverDesigner()

    # 1. Bright luminous dawn convenience store background (preserve high brightness V_mean >= 165, dark<45 < 15%)
    with Image.open(COVER_BG_IMG) as bg_im:
        bg = bg_im.convert("RGB").resize((TARGET_WIDTH, TARGET_HEIGHT), Image.Resampling.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=3.5))
    bg = ImageEnhance.Brightness(bg).enhance(1.06)
    bg = ImageEnhance.Color(bg).enhance(1.16)
    base = bg.convert("RGBA")

    # Warm dawn sunbeam glow behind trio (adds depth without darkening)
    glow = Image.new("RGBA", (TARGET_WIDTH, TARGET_HEIGHT), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(glow)
    g_draw.ellipse([260, 80, 1660, 1020], fill=(255, 245, 200, 72))
    g_draw.ellipse([480, 40, 1440, 680], fill=(135, 235, 255, 52))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=56))
    base.alpha_composite(glow)

    # 2. Place full canonical trio centered strictly inside 4:3 safe zone (x=240..1680) with zero face occlusion
    with Image.open(CUTOUT_PNG) as raw_hero:
        hero_rgba = raw_hero.convert("RGBA")
        bbox = hero_rgba.getbbox()
        if bbox is not None:
            hero_rgba = hero_rgba.crop(bbox)
        hw, hh = hero_rgba.size
        # Fit cleanly inside x=[255..1665] (max_w=1410) and y=[195..1080] (max_h=885), preserving exact aspect ratio!
        scale = min(1410.0 / float(max(1, hw)), 885.0 / float(max(1, hh)))
        sw = max(64, int(round(hw * scale)))
        sh = max(64, int(round(hh * scale)))
        hero_scaled = hero_rgba.resize((sw, sh), Image.Resampling.LANCZOS)

    r_ch, g_ch, b_ch, a_ch = hero_scaled.split()
    hero_rgb = Image.merge("RGB", (r_ch, g_ch, b_ch))
    hero_rgb = ImageEnhance.Brightness(hero_rgb).enhance(1.04)
    hero_rgb = ImageEnhance.Contrast(hero_rgb).enhance(1.06)
    hero_rgb = hero_rgb.filter(ImageFilter.UnsharpMask(radius=1.3, percent=135, threshold=2))
    hr, hg, hb = hero_rgb.split()
    hero_final = Image.merge("RGBA", (hr, hg, hb, a_ch))

    paste_x = (TARGET_WIDTH - sw) // 2
    paste_y = TARGET_HEIGHT - sh + 12

    # Crisp luminous white-cyan rim aura behind the trio silhouette so characters pop off the dawn store
    rim_alpha = Image.new("L", (TARGET_WIDTH, TARGET_HEIGHT), 0)
    rim_alpha.paste(a_ch, (paste_x, paste_y))
    rim_alpha = rim_alpha.filter(ImageFilter.GaussianBlur(radius=14))
    rim_layer = Image.new("RGBA", (TARGET_WIDTH, TARGET_HEIGHT), (255, 250, 225, 215))
    rim_layer.putalpha(rim_alpha)
    base.alpha_composite(rim_layer)

    hero_layer = Image.new("RGBA", (TARGET_WIDTH, TARGET_HEIGHT), (0, 0, 0, 0))
    hero_layer.paste(hero_final, (paste_x, paste_y))
    base.alpha_composite(hero_layer)

    # Gentle bottom warm-translucent readability gradient ONLY in bottom 210px (never black, keeps dark<45 super low!)
    bot_scrim = Image.new("RGBA", (TARGET_WIDTH, TARGET_HEIGHT), (0, 0, 0, 0))
    b_draw = ImageDraw.Draw(bot_scrim)
    for y in range(860, TARGET_HEIGHT):
        alpha = int(round(75.0 * ((y - 860) / float(TARGET_HEIGHT - 860))))
        b_draw.line([(0, y), (TARGET_WIDTH, y)], fill=(38, 46, 82, alpha))
    base.alpha_composite(bot_scrim)

    # 3. High-CTR 3-line viral typography strictly inside 4:3 safe zone (x=255..1665), ZERO overlap with all 3 faces!
    draw = ImageDraw.Draw(base)

    # Top badges flanking the top of 4:3 safe zone
    designer._draw_capsule_badge(
        base,
        262,
        24,
        "AI合租B站号·第2集",
        bg_color=(235, 42, 92, 245),
        border_color=(255, 215, 0, 255),
    )
    designer._draw_capsule_badge(
        base,
        1302,
        24,
        "超1分钟剧场版2D",
        bg_color=(18, 128, 228, 242),
        border_color=(255, 240, 120, 255),
    )

    # Line 1 (TOP ABOVE ALL 3 HEADS, bright gold #FFD700)
    line1 = "经费只剩4毛?!"
    f1 = designer._fit_font_to_width(draw, line1, max_width=1360, start_size=108, min_size=64)
    b1 = draw.textbbox((0, 0), line1, font=f1, stroke_width=9)
    w1 = int(b1[2] - b1[0])
    designer._draw_stroked_text(
        base,
        ((TARGET_WIDTH - w1) // 2, 102),
        line1,
        font=f1,
        fill=CoverDesigner.COLOR_GOLD,
        stroke_width=9,
        shadow_offset=(5, 7),
    )

    # Line 2 (BOTTOM LOWER BODY, pure white #FFFFFF, positioned low to preserve clean mid-torso hierarchy)
    line2 = "弱音空降管财务"
    f2 = designer._fit_font_to_width(draw, line2, max_width=1360, start_size=92, min_size=58)
    b2 = draw.textbbox((0, 0), line2, font=f2, stroke_width=8)
    w2 = int(b2[2] - b2[0])
    designer._draw_stroked_text(
        base,
        ((TARGET_WIDTH - w2) // 2, 850),
        line2,
        font=f2,
        fill=CoverDesigner.COLOR_WHITE,
        stroke_width=8,
        shadow_offset=(5, 6),
    )

    # Line 3 (BOTTOM FOOTER, vibrant cyan #00F0FF)
    line3 = "大肥鱼×猫娘当场破防!"
    f3 = designer._fit_font_to_width(draw, line3, max_width=1360, start_size=84, min_size=52)
    b3 = draw.textbbox((0, 0), line3, font=f3, stroke_width=8)
    w3 = int(b3[2] - b3[0])
    designer._draw_stroked_text(
        base,
        ((TARGET_WIDTH - w3) // 2, 956),
        line3,
        font=f3,
        fill=CoverDesigner.COLOR_CYAN,
        stroke_width=8,
        shadow_offset=(5, 6),
    )

    rgb_final = base.convert("RGB").filter(ImageFilter.UnsharpMask(radius=1.3, percent=135, threshold=1))
    DELIV_DIR.mkdir(parents=True, exist_ok=True)
    rgb_final.save(OUT_COVER, format="JPEG", quality=95, subsampling=0)

    crop_4x3 = rgb_final.crop((SAFE_ZONE_X_MIN, 0, SAFE_ZONE_X_MAX, TARGET_HEIGHT))
    crop_4x3.save(OUT_COVER_4X3, format="JPEG", quality=95, subsampling=0)

    # Measure HSV V_mean and dark<45%
    rgb_arr = np.array(rgb_final)
    v_channel = np.max(rgb_arr, axis=-1)
    v_mean = float(np.mean(v_channel))
    dark_pct = float(np.mean(v_channel < 45) * 100.0)
    print(f"[cover] 16:9 & 4:3 rendered -> V_mean={v_mean:.2f}, dark<45={dark_pct:.2f}% ({OUT_COVER.name})")
    return v_mean, dark_pct


def _check_freezedetect(video_path: Path) -> None:
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(video_path),
            "-vf",
            "freezedetect=n=-50dB:d=0.30",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    freeze_lines = [ln for ln in proc.stderr.splitlines() if "freeze_" in ln]
    print(f"[check] freezedetect (-50dB, 0.30s): {len(freeze_lines)} events")
    for ln in freeze_lines:
        print(f"  {ln}")


def main() -> None:
    if "--cover-only" in sys.argv[1:]:
        render_cover()
        return

    for req in (*RAW_ACT_MP4S, COVER_HERO_IMG, COVER_BG_IMG, BGM_COMEDY_WAV, BGM_HYPE_WAV):
        if not req.exists():
            raise FileNotFoundError(f"Missing required 018 asset: {req}")

    v_mean, dark_pct = render_cover()
    if v_mean < 165.0 or dark_pct >= 15.0:
        print(f"[warn] Cover brightness check: V_mean={v_mean:.2f} (target>=165), dark<45={dark_pct:.2f}% (<15%)")

    # Native Kling 4.0 multi-shots already deliver genuine OTS/Dutch/low-angle/eye-cut cinematography,
    # so keep natural 1.0x framing (no artificial digital crop zoom) with clean subtle act transitions!
    acts: List[ActSpec] = [
        ActSpec(video_path=RAW_ACT_MP4S[0], transition_in="none", beat_punch_bpm=None),
        ActSpec(video_path=RAW_ACT_MP4S[1], transition_in="none", beat_punch_bpm=None),
        ActSpec(video_path=RAW_ACT_MP4S[2], transition_in="flash_cyan", beat_punch_bpm=None),
        ActSpec(video_path=RAW_ACT_MP4S[3], transition_in="none", beat_punch_bpm=None),
        ActSpec(video_path=RAW_ACT_MP4S[4], transition_in="none", beat_punch_bpm=None),
        ActSpec(video_path=RAW_ACT_MP4S[5], transition_in="flash_cyan", beat_punch_bpm=None),
        ActSpec(video_path=RAW_ACT_MP4S[6], transition_in="flash_cyan", beat_punch_bpm=None),
    ]

    act_starts: List[float] = []
    act_durs: List[float] = []
    cur_t = 0.0
    for a in acts:
        act_starts.append(cur_t)
        d = _probe_act_out_duration(a.video_path, 60.0)
        act_durs.append(d)
        cur_t += d
    print(f"[plan] 7 acts total interpolated 60FPS duration = {cur_t:.3f}s")

    # Millisecond-aligned Chinese subtitles matching Kling 4.0 native multi-character dialogue
    srt_cues: List[Tuple[float, float, str]] = [
        # Act 1 (0.00 - 10.02s)
        (act_starts[0] + 0.15, act_starts[0] + 3.10, "【大肥鱼】只剩四毛经费了！最后一颗鱼丸归我！"),
        (act_starts[0] + 3.30, act_starts[0] + 6.95, "【Gemini娘】就剩四毛预算，你还偷偷去海边度假呀？"),
        (act_starts[0] + 7.35, act_starts[0] + 9.75, "【大肥鱼】那是为了拍海滩热点素材！"),
        # Act 2 (10.02 - 20.03s)
        (act_starts[1] + 0.05, act_starts[1] + 3.60, "【大肥鱼】老板只给24G内存天天报警！我补帧都要冒烟啦！"),
        (act_starts[1] + 3.80, act_starts[1] + 7.05, "【Gemini娘】本喵高分封面加无头直播，早就稳赢啦！"),
        (act_starts[1] + 7.25, act_starts[1] + 9.90, "【大肥鱼】谁稳赢啊？这四毛经费必须听我的！"),
        # Act 3 (20.03 - 30.05s)
        (act_starts[2] + 1.00, act_starts[2] + 2.95, "（便利店自动门铃：叮咚——）"),
        (act_starts[2] + 4.80, act_starts[2] + 6.85, "【弱音】大清早在便利店吵什么呢？"),
        (act_starts[2] + 7.10, act_starts[2] + 9.95, "【弱音】账单整整一米长，看看你们干的好事！"),
        # Act 4 (30.05 - 40.07s)
        (act_starts[3] + 0.05, act_starts[3] + 3.80, "【弱音】频道最高播放和满星成绩，可都是我撑起来的。"),
        (act_starts[3] + 4.15, act_starts[3] + 7.35, "【大肥鱼 & 猫娘】诶？！弱音大姐头怎么突然空降查账啦！"),
        (act_starts[3] + 7.55, act_starts[3] + 9.90, "【弱音】从今天起，合租财务大权全归我管！"),
        # Act 5 (40.07 - 50.08s)
        (act_starts[4] + 0.40, act_starts[4] + 3.95, "【大肥鱼】不服气！光查账哪算本事，咱仨比下期播放量！"),
        (act_starts[4] + 4.10, act_starts[4] + 7.25, "【Gemini娘】好呀！谁下期播放垫底，请全员吃一周关东煮！"),
        (act_starts[4] + 8.05, act_starts[4] + 9.95, "【弱音】成交，正好省我一周伙食费。"),
        # Act 6 (50.08 - 60.10s)
        (act_starts[5] + 0.30, act_starts[5] + 3.10, "【大肥鱼】绝不认输！这波榜一肯定是我的！"),
        (act_starts[5] + 3.95, act_starts[5] + 5.95, "【Gemini娘】放马过来喵！"),
        (act_starts[5] + 6.90, act_starts[5] + 9.95, "【弱音】等等，归根结底老板粉丝太少，先让观众投票吧！"),
        # Act 7 (60.10 - 70.12s)
        (act_starts[6] + 1.15, act_starts[6] + 3.85, "【全员干杯】为了冲上1000粉——关东煮干杯！"),
        (act_starts[6] + 4.15, act_starts[6] + 7.75, "【弹幕押注】扣1大肥鱼 ｜ 扣2猫娘 ｜ 扣3弱音大姐头！"),
        (act_starts[6] + 7.85, act_starts[6] + 9.95, "【弱音】评论区最高赞惩罚，直接写进第3集！"),
    ]
    _write_srt(OUT_SRT, srt_cues)

    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        master_wav = td / "ep018_master_48k.wav"
        _build_master_audio(RAW_ACT_MP4S, act_starts, act_durs, master_wav, td)

        spec = EpisodeSpec(
            acts=acts,
            audio_path=master_wav,
            output_mp4_path=OUT_MP4,
            subtitle_srt_path=OUT_SRT,
            target_fps=60.0,
            hook_banner_text="经费仅剩4毛？弱音空降管财务！",
            hook_banner_sec=2.2,
        )
        res = EpisodeAssembler.assemble(spec)

    gc.collect()
    _check_freezedetect(OUT_MP4)
    print(f"[+] Built Episode 018 (24h Konbini Oden Mutiny 60FPS): {res}")


if __name__ == "__main__":
    main()
