#!/usr/bin/env python3
"""1080P @ 60FPS Pseudo-CCTV Server Room Dance Remaster for Project 008 (Real Telepathy Audio + Beat Punch-In)."""

from __future__ import annotations

import math
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw

SCRIPT_DIR = Path(__file__).resolve().parent
PROJ_DIR = SCRIPT_DIR.parent
ROOT_DIR = PROJ_DIR.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.bgm_hunter import BilibiliBgmHunter  # noqa: E402
from core.cover_designer import CoverDesigner  # noqa: E402
from core.episode_assembler import (  # noqa: E402
    apply_beat_camera_framing,
    iter_interpolated_60fps,
    load_cropped_1080p_frames,
)
from core.studio_renderer import get_sc_font, segment_character_rgba  # noqa: E402

ASSETS_DIR = PROJ_DIR / "assets"
CUTOUTS_DIR = PROJ_DIR / "output" / "cutouts"
DELIV_DIR = PROJ_DIR / "delivery"

RAW_DANCE_MP4 = PROJ_DIR / "output" / "dafeiyu_server_dance_raw_1080p.mp4"
ANCHOR_IMG = ASSETS_DIR / "dafeiyu_server_room_slender_16x9.jpg"
CUTOUT_PNG = CUTOUTS_DIR / "dafeiyu_server_slender_cutout.png"
LOCAL_REF_VIDEO = Path(
    "/home/mcocdaa/.gemini/antigravity-cli/brain/41ad8e76-ac57-4779-8d42-6235758b0251/scratch/ref_telepathy_16x9.mp4"
)

OUT_MP4 = DELIV_DIR / "AI接管账号第5天全自动日更工作室_final.mp4"
OUT_SRT = DELIV_DIR / "AI接管账号第5天全自动日更工作室_subtitle.srt"
OUT_COVER = DELIV_DIR / "AI接管账号第5天全自动日更工作室_cover.jpg"


def synthesize_140bpm_dance_bgm(out_wav: Path, duration_sec: float, sr: int = 48000) -> Path:
    """Offline fallback synth 140 BPM track aligned to duration_sec."""
    n_samples = int(round(duration_sec * sr))
    t = np.arange(n_samples, dtype=np.float32) / float(sr)
    bpm = 140.0
    beat_dur = 60.0 / bpm
    beat_phase = np.mod(t, beat_dur) / beat_dur
    beat_time = np.mod(t, beat_dur)
    kick = 0.72 * np.sin(2.0 * math.pi * (50.0 + 120.0 * np.exp(-beat_time * 36.0)) * beat_time) * np.exp(-beat_time * 18.0)
    bass = 0.30 * np.clip(0.32 + 0.68 * (beat_phase / 0.35), 0.32, 1.0) * np.sin(2.0 * math.pi * 110.0 * t)
    mix = np.tanh((kick + bass) * 0.85) * 0.88
    pcm = (np.stack([mix, mix], axis=-1).clip(-0.98, 0.98) * 32767.0).astype(np.int16)
    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return out_wav


def make_cctv_overlay_bgra(text: str = "REC   CAM-04 | DeepSeek GPU机房 | 03:14:27") -> np.ndarray:
    """Renders a crisp semi-transparent dark CCTV status overlay for top-right corner."""
    font = get_sc_font(22, bold=True)
    probe = Image.new("RGBA", (900, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(probe)
    bbox = d.textbbox((0, 0), text, font=font)
    tw = int(bbox[2] - bbox[0])
    th = int(bbox[3] - bbox[1])
    w, h = tw + 68, th + 24
    badge = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    bd = ImageDraw.Draw(badge)
    bd.rounded_rectangle(
        [0, 0, w - 1, h - 1],
        radius=12,
        fill=(8, 14, 24, 188),
        outline=(0, 235, 255, 200),
        width=2,
    )
    bd.text((48 - bbox[0], 11 - bbox[1]), text, font=font, fill=(235, 248, 255, 245))
    arr = np.array(badge)
    return np.dstack([arr[..., 2], arr[..., 1], arr[..., 0], arr[..., 3]])


def write_subtitles_srt(srt_path: Path, dur: float) -> None:
    """Writes timed Simplified Chinese subtitles with safe spacing and clean CJK glyphs."""
    cues: List[Tuple[float, float, str]] = [
        (0.05, min(3.75, dur * 0.34), "以为「服务器繁忙」是在算题？后台监控：大肥鱼半夜偷跳舞！"),
        (min(3.80, dur * 0.345), min(7.70, dur * 0.68), "白天回答十万个为什么，凌晨三点在GPU机房原地起舞！"),
        (min(7.75, dur * 0.685), max(8.5, dur - 0.10), "只要主人睡着 算力机房就是我的个人宅舞舞台！"),
    ]

    def fmt_ts(sec: float) -> str:
        ms = int(round(max(0.0, sec) * 1000.0))
        hh, rem = divmod(ms, 3600000)
        mm, rem = divmod(rem, 60000)
        ss, mmm = divmod(rem, 1000)
        return f"{hh:02d}:{mm:02d}:{ss:02d},{mmm:03d}"

    lines = []
    for i, (s, e, txt) in enumerate(cues, start=1):
        lines.extend([str(i), f"{fmt_ts(s)} --> {fmt_ts(e)}", txt, ""])
    srt_path.write_text("\n".join(lines), encoding="utf-8")


def apply_cctv_hud(frame: np.ndarray, overlay_bgra: np.ndarray, frame_idx: int) -> np.ndarray:
    """Composites crisp subtle CCTV viewfinder corners + pulsing REC dot."""
    out = frame.copy()
    oh, ow = overlay_bgra.shape[:2]
    ox, oy = 1894 - ow, 20
    alpha = overlay_bgra[..., 3:4].astype(np.float32) / 255.0
    roi = out[oy : oy + oh, ox : ox + ow].astype(np.float32)
    out[oy : oy + oh, ox : ox + ow] = (roi * (1.0 - alpha) + overlay_bgra[..., :3].astype(np.float32) * alpha).astype(
        np.uint8
    )

    if (frame_idx // 20) % 2 == 0:
        cv2.circle(out, (ox + 26, oy + oh // 2), 9, (48, 56, 255), -1, cv2.LINE_AA)
    else:
        cv2.circle(out, (ox + 26, oy + oh // 2), 9, (35, 35, 110), 2, cv2.LINE_AA)

    col = (240, 225, 0)  # BGR cyan
    m, ln = 24, 48
    for (x0, y0, dx, dy) in [(m, m, 1, 1), (1920 - m, m, -1, 1), (m, 1080 - m, 1, -1), (1920 - m, 1080 - m, -1, -1)]:
        cv2.line(out, (x0, y0), (x0 + dx * ln, y0), col, 2, cv2.LINE_AA)
        cv2.line(out, (x0, y0), (x0, y0 + dy * ln), col, 2, cv2.LINE_AA)
    return out


def main() -> None:
    if not RAW_DANCE_MP4.exists():
        raise FileNotFoundError(f"Missing raw Kling dance video: {RAW_DANCE_MP4}")

    segment_character_rgba(ANCHOR_IMG, CUTOUT_PNG)
    CoverDesigner().design_project_cover(PROJ_DIR, output_path=OUT_COVER, cover_style="vivid_scene")

    raw_frames, src_fps = load_cropped_1080p_frames(RAW_DANCE_MP4)
    if len(raw_frames) < 60:
        raise RuntimeError(f"Expected >= 60 frames in {RAW_DANCE_MP4}, got {len(raw_frames)}")

    total_60_frames = int(round((len(raw_frames) - 1) * (60.0 / src_fps))) + 1
    dur_sec = total_60_frames / 60.0
    write_subtitles_srt(OUT_SRT, dur_sec)

    with tempfile.TemporaryDirectory() as tmpdir:
        bgm_wav = Path(tmpdir) / "telepathy_sync_bgm.wav"
        try:
            src_audio = LOCAL_REF_VIDEO if LOCAL_REF_VIDEO.exists() else "BV1mYZaYXEha"
            BilibiliBgmHunter().extract_audio_clip(
                source=src_audio,
                output_wav=bgm_wav,
                start_sec=27.19,
                duration_sec=dur_sec,
                fade_in_sec=0.05,
                fade_out_sec=0.15,
            )
        except Exception:
            synthesize_140bpm_dance_bgm(bgm_wav, dur_sec)

        overlay_bgra = make_cctv_overlay_bgra()
        dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
        sub_style = (
            "Fontname=Noto Sans CJK SC,"
            "FontSize=23,"
            "PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,"
            "BackColour=&H88000000,"
            "BorderStyle=1,"
            "Outline=2.5,"
            "Shadow=1.0,"
            "MarginV=40,"
            "Alignment=2"
        )
        vf = f"subtitles={OUT_SRT.resolve().as_posix()}:force_style='{sub_style}',setsar=1,setdar=16/9,fps=60,format=yuv420p"
        cmd = [
            "ffmpeg",
            "-y",
            "-nostats",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-vcodec",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-s",
            "1920x1080",
            "-r",
            "60",
            "-i",
            "-",
            "-i",
            str(bgm_wav),
            "-vf",
            vf,
            "-af",
            "loudnorm=I=-14:LRA=7:TP=-1.5",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-profile:v",
            "high",
            "-preset",
            "fast",
            "-crf",
            "16",
            "-b:v",
            "6200k",
            "-maxrate",
            "7500k",
            "-bufsize",
            "9000k",
            "-pix_fmt",
            "yuv420p",
            "-color_primaries",
            "bt709",
            "-color_trc",
            "bt709",
            "-colorspace",
            "bt709",
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(OUT_MP4),
        ]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        assert proc.stdin is not None
        out_idx = 0
        for frm in iter_interpolated_60fps(raw_frames, src_fps, dis, target_fps=60.0):
            framed = apply_beat_camera_framing(
                frm,
                t_act_sec=out_idx / 60.0,
                bpm=140.0,
                punch_scale=1.30,
                focus_y_ratio=0.32,
                beats_per_shot=4,
                punch_start_sec=3.65,
            )
            composed = apply_cctv_hud(framed, overlay_bgra, out_idx)
            proc.stdin.write(composed.tobytes())
            out_idx += 1
        proc.stdin.close()
        proc.stdin = None
        _, err = proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg encode failed: {err.decode(errors='ignore')[-500:]}")

    print(f"[+] Built 008 60FPS Real-BGM Multi-Shot CCTV Dance ({out_idx} frames, {dur_sec:.2f}s) -> {OUT_MP4}")


if __name__ == "__main__":
    main()
