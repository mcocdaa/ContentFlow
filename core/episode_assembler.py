"""Reusable multi-act 60FPS optical-flow and beat-synced camera assembler for ContentFlow.

Codifies shared video engineering across episodes:
  - Aspect-preserving center crop to 1920x1080 (zero horizontal/vertical stretch).
  - Exact frame-rate resampling via cached symmetric DIS optical flow (24/25/30fps -> 60.00fps).
  - Beat-synced multi-shot framing (`apply_beat_camera_framing`) alternating wide shots with
    medium close-ups on musical downbeats so single-camera choreography never feels static.
  - Standardized 1920x1080 @ 60.00fps H.264/yuv420p/bt709 encoding with EBU R128 -14 LUFS audio
    and Noto Sans CJK SC subtitle burn-in.
"""

from __future__ import annotations

import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union, cast

import cv2
import numpy as np


@dataclass
class ActSpec:
    """Single act input video and optional post-processing camera/transition parameters."""

    video_path: Path
    transition_in: str = "none"  # "none" | "flash_cyan" | "flash_neon"
    beat_punch_bpm: Optional[float] = None
    punch_scale: float = 1.32
    focus_y_ratio: float = 0.34
    beats_per_shot: int = 4


@dataclass
class EpisodeSpec:
    """Complete multi-act episode assembly specification."""

    acts: List[ActSpec]
    audio_path: Path
    output_mp4_path: Path
    subtitle_srt_path: Optional[Path] = None
    target_fps: float = 60.0
    width: int = 1920
    height: int = 1080
    loudnorm_target_i: float = -14.0


def load_cropped_1080p_frames(
    video_path: Union[str, Path],
    target_w: int = 1920,
    target_h: int = 1080,
) -> Tuple[List[np.ndarray], float]:
    """Loads video frames and uniformly center-crops (never stretches) to target_w x target_h."""
    vpath = Path(video_path)
    cap = cv2.VideoCapture(str(vpath))
    if not cap.isOpened():
        raise RuntimeError(f"Unable to open video: {vpath}")

    src_fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    if src_fps <= 1.0 or math.isnan(src_fps):
        src_fps = 30.0

    frames: List[np.ndarray] = []
    try:
        while True:
            ok, frm = cap.read()
            if not ok:
                break
            h, w = frm.shape[:2]
            if w != target_w or h != target_h:
                if w >= target_w and h >= target_h and (w - target_w) <= 32 and (h - target_h) <= 32:
                    # Kling 1920x1088 / slightly padded outputs: center-crop exact pixels
                    y0 = max(0, (h - target_h) // 2)
                    x0 = max(0, (w - target_w) // 2)
                    frm = frm[y0 : y0 + target_h, x0 : x0 + target_w]
                else:
                    scale = max(target_w / float(w), target_h / float(h))
                    rw, rh = int(round(w * scale)), int(round(h * scale))
                    resized = cv2.resize(frm, (rw, rh), interpolation=cv2.INTER_LANCZOS4)
                    y0 = max(0, (rh - target_h) // 2)
                    x0 = max(0, (rw - target_w) // 2)
                    frm = resized[y0 : y0 + target_h, x0 : x0 + target_w]
            frames.append(frm)
    finally:
        cap.release()
    return frames, src_fps


def iter_interpolated_60fps(
    raw_frames: List[np.ndarray],
    src_fps: float,
    dis: cv2.DISOpticalFlow,
    target_fps: float = 60.0,
) -> Iterator[np.ndarray]:
    """Resamples raw_frames at src_fps -> target_fps via cached symmetric DIS optical flow."""
    n_in = len(raw_frames)
    if n_in == 0:
        return
    if n_in == 1:
        yield raw_frames[0]
        return

    out_count = int(round((n_in - 1) * (target_fps / src_fps))) + 1
    h, w = raw_frames[0].shape[:2]
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))

    cached_idx = -1
    cached_flow_f: Optional[np.ndarray] = None
    cached_flow_b: Optional[np.ndarray] = None

    for k in range(out_count):
        pos = k * (src_fps / target_fps)
        i0 = min(int(math.floor(pos)), n_in - 1)
        alpha = pos - i0
        if alpha < 1e-3 or i0 >= n_in - 1:
            yield raw_frames[i0]
            continue

        if cached_idx != i0:
            f0 = raw_frames[i0]
            f1 = raw_frames[i0 + 1]
            s0 = cv2.resize(cv2.cvtColor(f0, cv2.COLOR_BGR2GRAY), (max(8, w // 2), max(8, h // 2)))
            s1 = cv2.resize(cv2.cvtColor(f1, cv2.COLOR_BGR2GRAY), (max(8, w // 2), max(8, h // 2)))
            cached_flow_f = cv2.resize(dis.calc(s0, s1, cast(Any, None)), (w, h), interpolation=cv2.INTER_LINEAR) * 2.0
            cached_flow_b = cv2.resize(dis.calc(s1, s0, cast(Any, None)), (w, h), interpolation=cv2.INTER_LINEAR) * 2.0
            cached_idx = i0

        assert cached_flow_f is not None and cached_flow_b is not None
        f0 = raw_frames[i0]
        f1 = raw_frames[i0 + 1]
        w0 = cv2.remap(
            f0,
            gx - alpha * cached_flow_f[..., 0],
            gy - alpha * cached_flow_f[..., 1],
            cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
        w1 = cv2.remap(
            f1,
            gx - (1.0 - alpha) * cached_flow_b[..., 0],
            gy - (1.0 - alpha) * cached_flow_b[..., 1],
            cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
        yield cv2.addWeighted(w0, 1.0 - alpha, w1, alpha, 0)


def apply_beat_camera_framing(
    frame: np.ndarray,
    t_act_sec: float,
    bpm: float = 132.0,
    punch_scale: float = 1.32,
    focus_y_ratio: float = 0.34,
    beats_per_shot: int = 4,
) -> np.ndarray:
    """Alternates wide choreography shots (1.0x) with beat-synced medium close-ups (punch_scale)."""
    if bpm <= 0 or punch_scale <= 1.01:
        return frame
    beat_sec = 60.0 / float(bpm)
    shot_dur = beat_sec * max(1, int(beats_per_shot))
    shot_idx = int(max(0.0, t_act_sec) / shot_dur)
    if (shot_idx % 2) == 0:
        return frame

    h, w = frame.shape[:2]
    cw = max(64, min(w, int(round(w / float(punch_scale)))))
    ch = max(36, min(h, int(round(h / float(punch_scale)))))
    cx = w // 2
    cy = int(round(h * float(focus_y_ratio)))
    x0 = max(0, min(w - cw, cx - cw // 2))
    y0 = max(0, min(h - ch, cy - ch // 2))
    cropped = frame[y0 : y0 + ch, x0 : x0 + cw]
    return cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LANCZOS4)


def apply_transition_flash(frame: np.ndarray, mode: str, alpha: float) -> np.ndarray:
    """Applies a short flash overlay at act boundaries (`flash_cyan` or `flash_neon`)."""
    if mode == "none" or alpha <= 1e-3:
        return frame
    h, w = frame.shape[:2]
    flash = np.empty_like(frame)
    if mode == "flash_neon":
        flash[:, : w // 2] = (255, 230, 80)
        flash[:, w // 2 :] = (230, 90, 255)
    else:
        flash[:, :] = (255, 245, 200)
    return cv2.addWeighted(frame, 1.0 - alpha, flash, alpha, 0)


class EpisodeAssembler:
    """Stitches multi-act raw video clips into a 1080P @ 60FPS H.264 master with -14 LUFS audio."""

    @staticmethod
    def _parse_spec_dict(data: Dict[str, Any], base_dir: Path) -> EpisodeSpec:
        def _resolve(p: Union[str, Path]) -> Path:
            cand = Path(p)
            return cand if cand.is_absolute() else (base_dir / cand).resolve()

        acts = [
            ActSpec(
                video_path=_resolve(a["video_path"]),
                transition_in=str(a.get("transition_in") or "none"),
                beat_punch_bpm=float(a["beat_punch_bpm"]) if a.get("beat_punch_bpm") is not None else None,
                punch_scale=float(a.get("punch_scale") or 1.32),
                focus_y_ratio=float(a.get("focus_y_ratio") or 0.34),
                beats_per_shot=int(a.get("beats_per_shot") or 4),
            )
            for a in data["acts"]
        ]
        srt_raw = data.get("subtitle_srt_path")
        return EpisodeSpec(
            acts=acts,
            audio_path=_resolve(data["audio_path"]),
            output_mp4_path=_resolve(data["output_mp4_path"]),
            subtitle_srt_path=_resolve(srt_raw) if srt_raw else None,
            target_fps=float(data.get("target_fps") or 60.0),
            width=int(data.get("width") or 1920),
            height=int(data.get("height") or 1080),
            loudnorm_target_i=float(data.get("loudnorm_target_i") or -14.0),
        )

    @classmethod
    def assemble_from_json(cls, spec_path: Union[str, Path]) -> Dict[str, Any]:
        """Loads an EpisodeSpec JSON file and runs assembly."""
        spath = Path(spec_path).resolve()
        data = json.loads(spath.read_text(encoding="utf-8"))
        spec = cls._parse_spec_dict(data, spath.parent)
        return cls.assemble(spec)

    @classmethod
    def assemble(cls, spec: EpisodeSpec) -> Dict[str, Any]:
        """Executes optical-flow 60FPS interpolation, beat-synced camera framing, and FFmpeg encode."""
        if not spec.acts:
            raise ValueError("EpisodeSpec.acts must not be empty")
        if not spec.audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {spec.audio_path}")

        loaded_acts: List[Tuple[ActSpec, List[np.ndarray], float, int]] = []
        total_out_frames = 0
        for act in spec.acts:
            frames, src_fps = load_cropped_1080p_frames(act.video_path, target_w=spec.width, target_h=spec.height)
            if not frames:
                raise RuntimeError(f"Video has 0 frames: {act.video_path}")
            n_out = int(round((len(frames) - 1) * (spec.target_fps / src_fps))) + 1
            loaded_acts.append((act, frames, src_fps, n_out))
            total_out_frames += n_out

        spec.output_mp4_path.parent.mkdir(parents=True, exist_ok=True)
        vf_parts: List[str] = []
        if spec.subtitle_srt_path and spec.subtitle_srt_path.exists():
            sub_style = (
                "Fontname=Noto Sans CJK SC,"
                "FontSize=24,"
                "PrimaryColour=&H00FFFFFF,"
                "OutlineColour=&H00000000,"
                "BackColour=&H88000000,"
                "BorderStyle=1,"
                "Outline=2.6,"
                "Shadow=1.0,"
                "MarginV=40,"
                "Alignment=2"
            )
            vf_parts.append(f"subtitles={spec.subtitle_srt_path.resolve().as_posix()}:force_style='{sub_style}'")
        vf_parts.extend(["setsar=1", "setdar=16/9", f"fps={int(round(spec.target_fps))}", "format=yuv420p"])
        vf = ",".join(vf_parts)

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
            f"{spec.width}x{spec.height}",
            "-r",
            str(int(round(spec.target_fps))),
            "-i",
            "-",
            "-i",
            str(spec.audio_path),
            "-vf",
            vf,
            "-af",
            f"loudnorm=I={spec.loudnorm_target_i}:LRA=7:TP=-1.5",
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
            str(spec.output_mp4_path),
        ]

        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        assert proc.stdin is not None
        cv2_any = cast(Any, cv2)
        dis = cv2_any.DISOpticalFlow_create(cv2_any.DISOPTICAL_FLOW_PRESET_MEDIUM)

        out_idx = 0
        act_boundaries: List[float] = []
        for act_idx, (act, frames, src_fps, n_out) in enumerate(loaded_acts):
            act_boundaries.append(round(out_idx / spec.target_fps, 3))
            next_trans = loaded_acts[act_idx + 1][0].transition_in if act_idx + 1 < len(loaded_acts) else "none"
            for local_i, frm in enumerate(iter_interpolated_60fps(frames, src_fps, dis, target_fps=spec.target_fps)):
                cur = frm
                if act.beat_punch_bpm is not None:
                    cur = apply_beat_camera_framing(
                        cur,
                        t_act_sec=local_i / spec.target_fps,
                        bpm=act.beat_punch_bpm,
                        punch_scale=act.punch_scale,
                        focus_y_ratio=act.focus_y_ratio,
                        beats_per_shot=act.beats_per_shot,
                    )
                if next_trans != "none":
                    dist_end = (n_out - 1) - local_i
                    if dist_end < 4:
                        cur = apply_transition_flash(cur, next_trans, 0.62 * (1.0 - dist_end / 4.0))
                if act.transition_in != "none" and local_i < 5:
                    cur = apply_transition_flash(cur, act.transition_in, 0.62 * (1.0 - local_i / 5.0))
                proc.stdin.write(cur.tobytes())
                out_idx += 1

        proc.stdin.close()
        proc.stdin = None
        _, err = proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg encode failed: {err.decode(errors='ignore')[-500:]}")

        return {
            "output_mp4": str(spec.output_mp4_path),
            "frames": out_idx,
            "fps": spec.target_fps,
            "duration_sec": round(out_idx / spec.target_fps, 3),
            "act_start_times": act_boundaries,
        }
