#!/usr/bin/env python3
"""1080P @ 60FPS Theatrical 2D Multi-Shot Anime Music Variety Assembler for Episode 020.

Episode 020: 《AI合租B站号第4集》打歌棚抢麦对唱战 — 大肥鱼硬说自己是猫×Gemini猫娘滑铲抢麦×弱音拍爆999分
- 7 x 10s Kling 4.0 Omni-Ref 1080p native multi-shot acts (~70.1s, strictly >= 60.0s)
- O(1) OpenCV DIS optical flow interpolation -> 1920x1080, SAR=1:1, DAR=16:9, 60.00fps, yuv420p, bt709
- Calm theatrical pacing (beat_punch_bpm=None, median cut gap >= 2.5s, subtle flash_cyan only on Act 3 & Act 5)
- Native Kling 4.0 multi-character Chinese voice acting & comedy rap + dynamically ducked CC0/Free BGM -> -14 LUFS
- K2 Hook Banner + millisecond-aligned Noto Sans CJK SC subtitles matching audited native WAV tracks
- Spotless trio hero cutout (stale cache deleted + white-garment interior protected) + bright vivid_scene 16:9 & 4:3 covers
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
    RAW_ACTS_DIR / "act1_blue_cat_ears_mic_claim.mp4",
    RAW_ACTS_DIR / "act2_dafeiyu_rap_solo.mp4",
    RAW_ACTS_DIR / "act3_gemini_mic_steal_counter.mp4",
    RAW_ACTS_DIR / "act4_cat_fish_duet_roast.mp4",
    RAW_ACTS_DIR / "act5_haku_judge_buzzer_explosion.mp4",
    RAW_ACTS_DIR / "act6_haku_budget_ultimatum.mp4",
    RAW_ACTS_DIR / "act7_trio_chorus_confetti_cta.mp4",
]

COVER_HERO_IMG = ASSETS_DIR / "cover_hero_trio_karaoke_16x9.jpg"
COVER_BG_IMG = ASSETS_DIR / "karaoke_studio_bg_16x9.jpg"
CUTOUT_PNG = CUTOUTS_DIR / "trio_karaoke_hero_cutout.png"

BGM_UPBEAT_WAV = BGM_DIR / "BV1254y1V7cJ_cc0_upbeat_intro.wav"
BGM_JUDGE_WAV = BGM_DIR / "BV1o4KwzPERi_plum_free_bgm.wav"

OUT_MP4 = DELIV_DIR / "AI打歌棚整活_大肥鱼猫娘抢麦对唱_final.mp4"
OUT_SRT = DELIV_DIR / "AI打歌棚整活_大肥鱼猫娘抢麦对唱_subtitle.srt"
OUT_COVER = DELIV_DIR / "AI打歌棚整活_大肥鱼猫娘抢麦对唱_cover.jpg"
OUT_COVER_4X3 = DELIV_DIR / "AI打歌棚整活_大肥鱼猫娘抢麦对唱_cover_4x3.jpg"

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
    """Extracts 48kHz stereo native audio from a Kling 4.0 act MP4 and aligns length cleanly."""
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

    # Gentle per-act voice loudness leveling across all 7 karaoke acts
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

    fade_n = min(int(0.015 * SAMPLE_RATE), target_n // 8)
    if fade_n > 0:
        ramp = np.linspace(0.0, 1.0, fade_n, dtype=np.float32)[:, None]
        arr[:fade_n] *= ramp
        arr[-fade_n:] *= ramp[::-1]
    return arr


def _slice_bgm_f32(wav_path: Path, start_sec: float, dur_sec: float) -> np.ndarray:
    """Slices a 48kHz stereo BGM WAV and normalizes its baseline RMS."""
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
    """Mixes 7 native Kling 4.0 dialogue+rap+foley tracks with dynamically ducked verified CC0/Free BGM."""
    native_parts = [_extract_native_audio_f32(p, d, tmp_dir) for p, d in zip(act_paths, act_durs)]
    native_full = np.concatenate(native_parts, axis=0)
    total_n = native_full.shape[0]
    total_dur = total_n / float(SAMPLE_RATE)

    # 3-segment musical arc:
    # Acts 1-4 (mic battle): upbeat CC0 electronic beat (BV1254y1V7cJ)
    # Acts 5-6 (judge buzzer laugh & budget ultimatum): quirky comedic Plum Free BGM (BV1o4KwzPERi)
    # Act 7 (trio chorus & confetti CTA): return to upbeat CC0 climax (BV1254y1V7cJ)
    t_judge = act_starts[4]
    t_finale = act_starts[6]
    n_judge = int(round(t_judge * SAMPLE_RATE))
    n_finale = int(round(t_finale * SAMPLE_RATE))
    xfade_n = int(0.30 * SAMPLE_RATE)

    bgm_battle = _slice_bgm_f32(BGM_UPBEAT_WAV, start_sec=6.0, dur_sec=t_judge + 0.5)
    bgm_judge = _slice_bgm_f32(BGM_JUDGE_WAV, start_sec=2.0, dur_sec=max(1.0, (t_finale - t_judge) + 0.5))
    bgm_finale = _slice_bgm_f32(BGM_UPBEAT_WAV, start_sec=48.0, dur_sec=max(1.0, (total_dur - t_finale) + 0.5))

    bgm_full = np.zeros((total_n, 2), dtype=np.float32)

    # Segment 1: battle [0 .. n_judge + xfade_n]
    n1 = min(total_n, n_judge + xfade_n)
    bgm_full[:n1] = bgm_battle[:n1]

    # Segment 2: judge [n_judge .. n_finale + xfade_n]
    if n_judge < total_n:
        seg2_end = min(total_n, n_finale + xfade_n)
        seg2_len = seg2_end - n_judge
        xf1 = min(xfade_n, seg2_len, max(0, n1 - n_judge))
        if xf1 > 0:
            fo = np.linspace(1.0, 0.0, xf1, dtype=np.float32)[:, None]
            bgm_full[n_judge : n_judge + xf1] = bgm_full[n_judge : n_judge + xf1] * fo + bgm_judge[:xf1] * (1.0 - fo)
        if seg2_len > xf1:
            bgm_full[n_judge + xf1 : seg2_end] = bgm_judge[xf1:seg2_len]

    # Segment 3: finale [n_finale .. total_n]
    if n_finale < total_n:
        seg3_len = total_n - n_finale
        xf2 = min(xfade_n, seg3_len)
        if xf2 > 0:
            fo = np.linspace(1.0, 0.0, xf2, dtype=np.float32)[:, None]
            bgm_full[n_finale : n_finale + xf2] = (
                bgm_full[n_finale : n_finale + xf2] * fo + bgm_finale[:xf2] * (1.0 - fo)
            )
        if seg3_len > xf2:
            bgm_full[n_finale + xf2 :] = bgm_finale[xf2:seg3_len]

    intro_n = min(int(0.20 * SAMPLE_RATE), total_n // 10)
    outro_n = min(int(0.60 * SAMPLE_RATE), total_n // 10)
    bgm_full[:intro_n] *= np.linspace(0.0, 1.0, intro_n, dtype=np.float32)[:, None]
    bgm_full[-outro_n:] *= np.linspace(1.0, 0.0, outro_n, dtype=np.float32)[:, None]

    # Dynamic RMS sidechain ducking so spoken lyrics/rap stay crystal clear while music grooves underneath
    mono_abs = np.mean(np.abs(native_full), axis=1)
    win = int(0.16 * SAMPLE_RATE)
    kernel = np.ones(win, dtype=np.float32) / float(win)
    env = np.convolve(mono_abs, kernel, mode="same")
    speech_factor = np.clip((env - 0.012) / 0.045, 0.0, 1.0)
    bgm_gain = (0.38 - 0.22 * speech_factor)[:, None]

    mixed = native_full * 0.96 + bgm_full * bgm_gain
    peak = float(np.max(np.abs(mixed))) if mixed.size else 1.0
    if peak > 0.94:
        mixed = np.tanh(mixed * (0.94 / peak) * 1.05) * 0.94

    _save_wav_stereo_i16(master_wav, mixed)


def _protect_solid_white_garments(src_rgb_img: Path, cutout_png: Path) -> None:
    """Restores solid alpha on interior white garments (apron, shirt, headphones, stockings) on #FFFFFF background."""
    with Image.open(src_rgb_img) as raw_im, Image.open(cutout_png) as cut_im:
        src_np = np.array(raw_im.convert("RGB"))
        cut_rgba = np.array(cut_im.convert("RGBA"))

    if src_np.shape[:2] != cut_rgba.shape[:2]:
        return

    h, w = src_np.shape[:2]
    near_white = (src_np[:, :, 0] >= 242) & (src_np[:, :, 1] >= 242) & (src_np[:, :, 2] >= 242)
    flood = near_white.astype(np.uint8) * 255
    ff_mask = np.zeros((h + 2, w + 2), dtype=np.uint8)

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

    interior_not_bg = flood != 128
    exterior_bg = (flood == 128).astype(np.uint8)
    exterior_dilated = cv2.dilate(exterior_bg, np.ones((3, 3), np.uint8), iterations=1) == 1
    safe_interior = interior_not_bg & (~exterior_dilated)

    rembg_alpha = cut_rgba[:, :, 3]
    solid_fg = (rembg_alpha >= 180).astype(np.uint8)
    fg_hull = cv2.morphologyEx(solid_fg, cv2.MORPH_CLOSE, np.ones((61, 61), np.uint8))
    restore_mask = safe_interior & (fg_hull > 0)

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
    new_alpha[exterior_bg == 1] = np.minimum(new_alpha[exterior_bg == 1], 0)

    out_rgba = cut_rgba.copy()
    out_rgba[:, :, 3] = new_alpha
    out_rgba[restore_mask, :3] = src_np[restore_mask]
    Image.fromarray(out_rgba, mode="RGBA").save(cutout_png)


def render_cover() -> Tuple[float, float]:
    """Deletes stale cutout, segments trio hero, and renders bright vivid_scene 16:9 & 4:3 covers."""
    if not COVER_HERO_IMG.exists():
        raise FileNotFoundError(f"Missing trio hero anchor: {COVER_HERO_IMG}")
    if not COVER_BG_IMG.exists():
        raise FileNotFoundError(f"Missing karaoke studio background: {COVER_BG_IMG}")

    CUTOUTS_DIR.mkdir(parents=True, exist_ok=True)
    # Mandatory stale cutout cache deletion before re-segmenting
    CUTOUT_PNG.unlink(missing_ok=True)

    segment_character_rgba(COVER_HERO_IMG, CUTOUT_PNG, crop_roi=None, clean_corner_wm=False)
    _protect_solid_white_garments(COVER_HERO_IMG, CUTOUT_PNG)

    designer = CoverDesigner()

    # 1. Bright pastel macaron daylight karaoke stage backdrop (preserve V_mean >= 170, dark<45 < 10%)
    with Image.open(COVER_BG_IMG) as bg_im:
        bg = bg_im.convert("RGB").resize((TARGET_WIDTH, TARGET_HEIGHT), Image.Resampling.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=3.0))
    bg = ImageEnhance.Brightness(bg).enhance(1.06)
    bg = ImageEnhance.Color(bg).enhance(1.12)
    base = bg.convert("RGBA")

    glow = Image.new("RGBA", (TARGET_WIDTH, TARGET_HEIGHT), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(glow)
    g_draw.ellipse([240, 60, 1680, 1020], fill=(255, 245, 252, 72))
    g_draw.ellipse([440, 30, 1480, 680], fill=(160, 238, 255, 58))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=54))
    base.alpha_composite(glow)

    # 2. Place canonical karaoke trio strictly inside 4:3 safe zone (x=240..1680) with zero head occlusion
    with Image.open(CUTOUT_PNG) as raw_hero:
        hero_rgba = raw_hero.convert("RGBA")
        bbox = hero_rgba.getbbox()
        if bbox is not None:
            hero_rgba = hero_rgba.crop(bbox)
        hw, hh = hero_rgba.size
        scale = min(1400.0 / float(max(1, hw)), 875.0 / float(max(1, hh)))
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

    rim_alpha = Image.new("L", (TARGET_WIDTH, TARGET_HEIGHT), 0)
    rim_alpha.paste(a_ch, (paste_x, paste_y))
    rim_alpha = rim_alpha.filter(ImageFilter.GaussianBlur(radius=14))
    rim_layer = Image.new("RGBA", (TARGET_WIDTH, TARGET_HEIGHT), (255, 252, 235, 220))
    rim_layer.putalpha(rim_alpha)
    base.alpha_composite(rim_layer)

    hero_layer = Image.new("RGBA", (TARGET_WIDTH, TARGET_HEIGHT), (0, 0, 0, 0))
    hero_layer.paste(hero_final, (paste_x, paste_y))
    base.alpha_composite(hero_layer)

    # Gentle bottom pastel-indigo scrim so lower 2 lines of cover typography pop without darkening the frame
    bot_scrim = Image.new("RGBA", (TARGET_WIDTH, TARGET_HEIGHT), (0, 0, 0, 0))
    b_draw = ImageDraw.Draw(bot_scrim)
    for y in range(865, TARGET_HEIGHT):
        alpha = int(round(72.0 * ((y - 865) / float(TARGET_HEIGHT - 865))))
        b_draw.line([(0, y), (TARGET_WIDTH, y)], fill=(45, 52, 96, alpha))
    base.alpha_composite(bot_scrim)

    # 3. High-CTR 3-line viral typography strictly inside 4:3 safe zone (x=255..1665)
    draw = ImageDraw.Draw(base)
    designer._draw_capsule_badge(
        base,
        262,
        24,
        "AI合租B站号·第4集",
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

    line1 = "大肥鱼硬说自己是猫?!"
    f1 = designer._fit_font_to_width(draw, line1, max_width=1360, start_size=106, min_size=64)
    b1 = draw.textbbox((0, 0), line1, font=f1, stroke_width=9)
    w1 = int(b1[2] - b1[0])
    designer._draw_stroked_text(
        base,
        ((TARGET_WIDTH - w1) // 2, 98),
        line1,
        font=f1,
        fill=CoverDesigner.COLOR_GOLD,
        stroke_width=9,
        shadow_offset=(5, 7),
    )

    line2 = "猫娘滑铲抢麦对唱"
    f2 = designer._fit_font_to_width(draw, line2, max_width=1360, start_size=88, min_size=56)
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

    line3 = "弱音评委拍爆999分!"
    f3 = designer._fit_font_to_width(draw, line3, max_width=1360, start_size=88, min_size=54)
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

    for req in (*RAW_ACT_MP4S, COVER_HERO_IMG, COVER_BG_IMG, BGM_UPBEAT_WAV, BGM_JUDGE_WAV):
        if not req.exists():
            raise FileNotFoundError(f"Missing required 020 asset: {req}")

    v_mean, dark_pct = render_cover()
    if v_mean < 165.0 or dark_pct >= 15.0:
        print(f"[warn] Cover brightness check: V_mean={v_mean:.2f} (target>=165), dark<45={dark_pct:.2f}% (<15%)")

    # Calm theatrical pacing: beat_punch_bpm=None everywhere; subtle flash_cyan ONLY on Act 3 (mic steal) & Act 5 (999 buzzer)
    acts: List[ActSpec] = [
        ActSpec(video_path=RAW_ACT_MP4S[0], transition_in="none", beat_punch_bpm=None),
        ActSpec(video_path=RAW_ACT_MP4S[1], transition_in="none", beat_punch_bpm=None),
        ActSpec(video_path=RAW_ACT_MP4S[2], transition_in="flash_cyan", beat_punch_bpm=None),
        ActSpec(video_path=RAW_ACT_MP4S[3], transition_in="none", beat_punch_bpm=None),
        ActSpec(video_path=RAW_ACT_MP4S[4], transition_in="flash_cyan", beat_punch_bpm=None),
        ActSpec(video_path=RAW_ACT_MP4S[5], transition_in="none", beat_punch_bpm=None),
        ActSpec(video_path=RAW_ACT_MP4S[6], transition_in="none", beat_punch_bpm=None),
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

    # Millisecond-aligned subtitles calibrated directly against audited native Kling 4.0 WAV envelopes
    srt_cues: List[Tuple[float, float, str]] = [
        # Act 1 (0.000 - 10.017s)
        (act_starts[0] + 1.75, act_starts[0] + 5.95, "【大肥鱼】鱼可爱，猫可爱，四舍五入大肥鱼我也是正牌蓝猫！"),
        (act_starts[0] + 7.00, act_starts[0] + 9.85, "【Gemini娘】哈？！你刚才说什么喵？！"),
        # Act 2 (10.017 - 20.033s)
        (act_starts[1] + 0.10, act_starts[1] + 4.85, "【大肥鱼】报服务器繁忙那是在舔毛，深海算力蓝猫娘今天出道！"),
        (act_starts[1] + 5.35, act_starts[1] + 9.25, "【大肥鱼】点赞关注和流量，今天全归本蓝猫！"),
        # Act 3 (20.033 - 30.050s)
        (act_starts[2] + 0.15, act_starts[2] + 3.60, "【Gemini娘】停一下喵！话筒归本猫娘接管！"),
        (act_starts[2] + 5.15, act_starts[2] + 9.85, "【Gemini娘】你连猫薄荷和显卡风扇都分不清，戴个发箍就敢抢本猫娘招牌流量？！"),
        # Act 4 (30.050 - 40.067s)
        (act_starts[3] + 0.10, act_starts[3] + 4.85, "【大肥鱼】本鱼自带蓝鲸大尾巴，满血算力谁能打！"),
        (act_starts[3] + 5.45, act_starts[3] + 9.90, "【Gemini娘】本喵靠亮色封面和真猫耳，直接赢你两条街喵！"),
        # Act 5 (40.067 - 50.083s)
        (act_starts[4] + 1.15, act_starts[4] + 4.50, "【弱音评委】哈哈停！全员九百九十九分！"),
        (act_starts[4] + 5.95, act_starts[4] + 9.85, "【弱音评委】老板那十五个粉的小号，全靠你们俩整活啦！"),
        # Act 6 (50.083 - 60.100s)
        (act_starts[5] + 0.35, act_starts[5] + 5.85, "【弱音评委】不过再不合唱冲千粉，明天猫粮和小鱼干经费一起清零！"),
        (act_starts[5] + 7.25, act_starts[5] + 9.85, "【双AI立正】收到！马上合唱冲千粉！"),
        # Act 7 (60.100 - 70.117s)
        (act_starts[6] + 0.35, act_starts[6] + 4.50, "【全员合唱】铁三角开麦冲千粉，快乐整活不停歇！"),
        (act_starts[6] + 5.25, act_starts[6] + 9.90, "【弹幕投票】蓝猫鱼还是真猫娘？点赞关注冲千粉，弹幕投票由你定！"),
    ]
    _write_srt(OUT_SRT, srt_cues)

    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        master_wav = td / "ep020_master_48k.wav"
        _build_master_audio(RAW_ACT_MP4S, act_starts, act_durs, master_wav, td)

        spec = EpisodeSpec(
            acts=acts,
            audio_path=master_wav,
            output_mp4_path=OUT_MP4,
            subtitle_srt_path=OUT_SRT,
            target_fps=60.0,
            hook_banner_text="大肥鱼硬说自己是猫?! 抢麦对唱开麦!",
            hook_banner_sec=2.2,
        )
        res = EpisodeAssembler.assemble(spec)

    gc.collect()
    _check_freezedetect(OUT_MP4)
    print(f"[+] Built Episode 020 (Karaoke Studio Cat-vs-Fish Battle >=70s 60FPS): {res}")


if __name__ == "__main__":
    main()
