"""Online & local human-perception visual/audio preference scorer for ContentFlow.

Combines free live online human-preference inference APIs (with strict timeouts and
deterministic local fallbacks so CI/offline tests never break) with local RTX 4060
TOPIQ-IAA / HyperIQA models:
1. Visual Anime Appeal: `skytnt-anime-aesthetic-predict.hf.space` evaluated on both
   full frames and hero portrait crops (isolating character quality from banner text).
2. Audio Production & Enjoyment: `facebook-audiobox-aesthetics.hf.space` (Meta Audiobox
   Aesthetics MOS: Production Quality, Production Complexity, Content Enjoyment,
   Content Usefulness), paired with local dead-air & warm-bed spectral richness analysis.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import wave
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import requests
from PIL import Image

from config.settings import CONTENTFLOW_ROOT

SKYTNT_SPACE_URL = "https://skytnt-anime-aesthetic-predict.hf.space"
AUDIOBOX_SPACE_URL = "https://facebook-audiobox-aesthetics.hf.space"


def _parse_gradio_sse_complete_data(sse_text: str) -> Optional[Any]:
    """Extracts JSON payload from a Gradio v4/v5 SSE stream following `event: complete`."""
    lines = sse_text.splitlines()
    saw_complete = False
    last_data: Optional[str] = None
    for raw_line in lines:
        line = raw_line.strip()
        if line.startswith("event:"):
            ev = line.split(":", 1)[1].strip()
            saw_complete = ev == "complete"
        elif line.startswith("data:"):
            payload_str = line.split(":", 1)[1].strip()
            last_data = payload_str
            if saw_complete:
                try:
                    return json.loads(payload_str)
                except Exception:
                    return None
    if last_data and not saw_complete:
        try:
            return json.loads(last_data)
        except Exception:
            return None
    return None


def _call_gradio_file_space(
    space_url: str,
    file_path: Path,
    mime_type: str,
    api_name: str = "predict",
    timeout: float = 25.0,
    session: Optional[requests.Session] = None,
) -> Optional[Any]:
    """Uploads a file to a public Gradio Space and invokes `gradio_api/call/{api_name}`."""
    sess = session or requests.Session()
    base = space_url.rstrip("/")
    try:
        with open(file_path, "rb") as fh:
            up_resp = sess.post(
                f"{base}/gradio_api/upload",
                files={"files": (file_path.name, fh, mime_type)},
                timeout=timeout,
            )
        if not up_resp.ok:
            return None
        up_json = up_resp.json()
        if not isinstance(up_json, list) or not up_json:
            return None
        remote_path = str(up_json[0])

        call_resp = sess.post(
            f"{base}/gradio_api/call/{api_name}",
            json={"data": [{"path": remote_path, "meta": {"_type": "gradio.FileData"}}]},
            timeout=timeout,
        )
        if not call_resp.ok:
            return None
        event_id = (call_resp.json() or {}).get("event_id")
        if not event_id:
            return None

        sse_resp = sess.get(f"{base}/gradio_api/call/{api_name}/{event_id}", timeout=timeout)
        if not sse_resp.ok:
            return None
        return _parse_gradio_sse_complete_data(sse_resp.text)
    except Exception:
        return None


def _extract_skytnt_score(payload: Any) -> Optional[float]:
    """Parses scalar 0..1 anime aesthetic score from `skytnt-anime-aesthetic-predict` output."""
    if not isinstance(payload, list) or not payload:
        return None
    first = payload[0]
    if isinstance(first, (int, float)):
        return round(float(first), 4)
    if isinstance(first, dict):
        confs = first.get("confidences")
        if isinstance(confs, list) and confs and isinstance(confs[0], dict) and "confidence" in confs[0]:
            return round(float(confs[0]["confidence"]), 4)
        for key in ("confidence", "score", "value"):
            if key in first and isinstance(first[key], (int, float)):
                return round(float(first[key]), 4)
    return None


def score_anime_visual_online(
    image_path: Path,
    crop_box: Optional[Tuple[int, int, int, int]] = None,
    timeout: float = 25.0,
    session: Optional[requests.Session] = None,
) -> Optional[float]:
    """Scores an anime cover or keyframe (or cropped hero region) via live HuggingFace Space."""
    image_path = Path(image_path)
    if not image_path.exists():
        return None

    with tempfile.TemporaryDirectory() as tmpdir:
        target_path = image_path
        if crop_box is not None:
            with Image.open(image_path) as im:
                rgb = im.convert("RGB")
                w, h = rgb.size
                x0 = max(0, min(w - 2, int(crop_box[0])))
                y0 = max(0, min(h - 2, int(crop_box[1])))
                x1 = max(x0 + 2, min(w, int(crop_box[2])))
                y1 = max(y0 + 2, min(h, int(crop_box[3])))
                cropped = rgb.crop((x0, y0, x1, y1))
                target_path = Path(tmpdir) / "hero_crop.jpg"
                cropped.save(target_path, format="JPEG", quality=92)
        raw = _call_gradio_file_space(
            SKYTNT_SPACE_URL,
            target_path,
            mime_type="image/jpeg",
            api_name="predict",
            timeout=timeout,
            session=session,
        )
    return _extract_skytnt_score(raw)


def _extract_audiobox_metrics(payload: Any) -> Optional[Dict[str, float]]:
    """Extracts 4 Meta Audiobox Aesthetics MOS metrics (1..10) from Plotly Gradio JSON output."""
    if not isinstance(payload, list) or not payload:
        return None
    item = payload[0]
    plot_raw = item.get("plot") if isinstance(item, dict) else item
    if isinstance(plot_raw, str):
        try:
            plot_obj = json.loads(plot_raw)
        except Exception:
            return None
    elif isinstance(plot_raw, dict):
        plot_obj = plot_raw
    else:
        return None

    traces = plot_obj.get("data") or []
    if not traces or not isinstance(traces[0], dict):
        return None
    xs = traces[0].get("x") or []
    ys = traces[0].get("y") or []
    mapping = {
        "Production Quality": "production_quality",
        "Production Complexity": "production_complexity",
        "Content Enjoyment": "content_enjoyment",
        "Content Usefulness": "content_usefulness",
    }
    out: Dict[str, float] = {}
    for label, val in zip(xs, ys):
        key = mapping.get(str(label).strip())
        if key is not None:
            out[key] = round(float(val), 3)
    return out if out else None


def score_audio_enjoyment_online(
    media_path: Path,
    timeout: float = 35.0,
    max_clip_sec: float = 25.0,
    session: Optional[requests.Session] = None,
) -> Optional[Dict[str, float]]:
    """Scores speech+BGM/video audio track via Meta Audiobox Aesthetics Space (PQ/PC/CE/CU)."""
    media_path = Path(media_path)
    if not media_path.exists():
        return None

    with tempfile.TemporaryDirectory() as tmpdir:
        upload_audio = media_path
        mime = "audio/mpeg" if media_path.suffix.lower() == ".mp3" else "audio/wav"
        if (
            media_path.suffix.lower() not in (".mp3", ".wav") or media_path.stat().st_size > 1_200_000
        ) and shutil.which("ffmpeg") is not None:
            clipped_mp3 = Path(tmpdir) / "clip.mp3"
            proc = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-t",
                    f"{max_clip_sec:.1f}",
                    "-i",
                    str(media_path),
                    "-vn",
                    "-ac",
                    "2",
                    "-ar",
                    "44100",
                    "-b:a",
                    "128k",
                    str(clipped_mp3),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if proc.returncode == 0 and clipped_mp3.exists():
                upload_audio = clipped_mp3
                mime = "audio/mpeg"

        raw = _call_gradio_file_space(
            AUDIOBOX_SPACE_URL,
            upload_audio,
            mime_type=mime,
            api_name="predict",
            timeout=timeout,
            session=session,
        )
    return _extract_audiobox_metrics(raw)


def compute_local_audio_richness(media_path: Path) -> Dict[str, float]:
    """Computes deterministic dead-air ratio, warm-bed presence, and low-end BGM balance offline."""
    media_path = Path(media_path)
    default_res = {
        "dead_air_ratio": 0.0,
        "noise_floor_p15_dbfs": -60.0,
        "bgm_bed_presence_ratio": 0.0,
        "low_warmth_ratio": 0.0,
        "audio_richness_10": 5.0,
    }
    if not media_path.exists():
        return default_res

    wav_samples: Optional[np.ndarray] = None
    sr = 24000
    if media_path.suffix.lower() == ".wav":
        try:
            with wave.open(str(media_path), "rb") as wf:
                sr = wf.getframerate()
                raw = wf.readframes(wf.getnframes())
                arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                if wf.getnchannels() > 1:
                    arr = arr.reshape(-1, wf.getnchannels()).mean(axis=1)
                wav_samples = arr
        except Exception:
            wav_samples = None

    if wav_samples is None:
        if shutil.which("ffmpeg") is None:
            return default_res
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_wav = Path(tmpdir) / "analyze.wav"
            proc = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-t",
                    "45",
                    "-i",
                    str(media_path),
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    str(sr),
                    "-sample_fmt",
                    "s16",
                    str(tmp_wav),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if proc.returncode != 0 or not tmp_wav.exists():
                return default_res
            with wave.open(str(tmp_wav), "rb") as wf:
                sr = wf.getframerate()
                raw = wf.readframes(wf.getnframes())
                wav_samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

    if wav_samples is None or wav_samples.size < max(sr // 4, 256):
        return default_res

    hop = max(1, int(0.05 * sr))
    n_frames = wav_samples.size // hop
    if n_frames < 4:
        return default_res
    frames = wav_samples[: n_frames * hop].reshape(n_frames, hop)
    rms = np.sqrt(np.mean(frames**2, axis=1) + 1e-10)
    rms_db = 20.0 * np.log10(np.maximum(rms, 1e-5))

    dead_air_ratio = float(np.mean(rms_db < -50.0))
    noise_floor_p15 = float(np.percentile(rms_db, 15))
    # Frames with audible gentle ambient bed (not dead silence and not peak speech)
    bed_mask = (rms_db >= -46.0) & (rms_db <= -18.0)
    bgm_bed_presence = float(np.mean(bed_mask)) if noise_floor_p15 > -48.0 else max(0.0, 1.0 - dead_air_ratio) * 0.25

    # Low-end bass/pad spectral warmth ratio (55..320 Hz vs total 55..6000 Hz)
    n_fft = min(len(wav_samples), sr * 8)
    spec = np.abs(np.fft.rfft(wav_samples[:n_fft])) ** 2
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / sr)
    warm_mask = (freqs >= 55.0) & (freqs <= 320.0)
    band_mask = (freqs >= 55.0) & (freqs <= 6000.0)
    low_warmth = float(np.sum(spec[warm_mask]) / (float(np.sum(spec[band_mask])) + 1e-9))

    # Map cleanly to 1..10 local richness score
    richness = 4.2
    richness += (1.0 - min(1.0, dead_air_ratio * 2.5)) * 2.4
    richness += min(1.0, max(0.0, (noise_floor_p15 + 56.0) / 20.0)) * 2.0
    richness += min(1.0, low_warmth * 3.5) * 1.4

    return {
        "dead_air_ratio": round(dead_air_ratio, 3),
        "noise_floor_p15_dbfs": round(noise_floor_p15, 2),
        "bgm_bed_presence_ratio": round(bgm_bed_presence, 3),
        "low_warmth_ratio": round(low_warmth, 3),
        "audio_richness_10": round(min(10.0, max(1.0, richness)), 2),
    }


@dataclass
class HumanPreferenceReport:
    project_id: str
    online_enabled: bool = True
    full_cover_anime_score: Optional[float] = None
    hero_portrait_anime_score: Optional[float] = None
    keyframe_hero_anime_score: Optional[float] = None
    audiobox_pq: Optional[float] = None
    audiobox_pc: Optional[float] = None
    audiobox_ce: Optional[float] = None
    audiobox_cu: Optional[float] = None
    local_cover_aesthetic_10: float = 0.0
    local_video_aesthetic_10: float = 0.0
    local_audio_richness_10: float = 0.0
    dead_air_ratio: float = 0.0
    human_appeal_index: float = 0.0
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class HumanPreferenceScorer:
    """Unified multimodal human-perception evaluator (Online HuggingFace + Local IQA + Audio Bed)."""

    def __init__(self, root_dir: Path = CONTENTFLOW_ROOT) -> None:
        self.root_dir = Path(root_dir)

    def resolve_project_dir(self, project: str) -> Path:
        cand = Path(project)
        if cand.exists():
            return cand
        projects_dir = self.root_dir / "projects"
        exact = projects_dir / project
        if exact.exists():
            return exact
        if projects_dir.exists():
            matches = sorted(p for p in projects_dir.iterdir() if p.is_dir() and project in p.name)
            if matches:
                return matches[0]
        return exact

    @staticmethod
    def _discover_assets(proj_dir: Path) -> Tuple[Optional[Path], Optional[Path]]:
        delivery = proj_dir / "delivery"
        vid: Optional[Path] = None
        cov: Optional[Path] = None
        for d in (delivery, proj_dir / "output" / "video"):
            if d.exists():
                mp4s = sorted(d.glob("*.mp4"), key=lambda p: ("_final" not in p.stem, p.name))
                if mp4s:
                    vid = mp4s[0]
                    break
        if delivery.exists():
            covs = [p for p in sorted(delivery.glob("*_cover.jpg")) if not p.stem.endswith("_4x3")]
            if covs:
                cov = covs[0]
        return vid, cov

    @staticmethod
    def _extract_character_keyframe(video_path: Path, t_sec: float, out_jpg: Path) -> Optional[Path]:
        if shutil.which("ffmpeg") is None or not video_path.exists():
            return None
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{t_sec:.2f}",
                "-i",
                str(video_path),
                "-vframes",
                "1",
                "-q:v",
                "3",
                str(out_jpg),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return out_jpg if proc.returncode == 0 and out_jpg.exists() else None

    def evaluate_project(
        self,
        project: str | Path,
        video_path: Optional[Path] = None,
        cover_path: Optional[Path] = None,
        allow_online: bool = True,
        session: Optional[requests.Session] = None,
    ) -> HumanPreferenceReport:
        """Evaluates a project across visual anime appeal, Meta Audiobox MOS, and local IQA/audio physics."""
        from core.aesthetic_evaluator import LocalAestheticEvaluator

        proj_dir = project if isinstance(project, Path) and project.exists() else self.resolve_project_dir(str(project))
        auto_vid, auto_cov = self._discover_assets(proj_dir)
        v_path = Path(video_path) if video_path else auto_vid
        c_path = Path(cover_path) if cover_path else auto_cov

        rep = HumanPreferenceReport(project_id=proj_dir.name, online_enabled=allow_online)
        recs: List[str] = []

        # 1. Local IQA + Audio Richness (works offline & in CI)
        local_eval = LocalAestheticEvaluator(allow_weight_download=False)
        aes = local_eval.evaluate_aesthetics_and_contact_sheet(video_path=v_path, cover_path=c_path)
        rep.local_cover_aesthetic_10 = aes.cover_aesthetic_10
        rep.local_video_aesthetic_10 = aes.video_aesthetic_10

        audio_target: Optional[Path] = v_path if (v_path and v_path.exists()) else None
        if audio_target is None and (proj_dir / "delivery").exists():
            mp3s = sorted((proj_dir / "delivery").glob("*.mp3"))
            if mp3s:
                audio_target = mp3s[0]

        if audio_target is not None:
            rich = compute_local_audio_richness(audio_target)
            rep.local_audio_richness_10 = rich["audio_richness_10"]
            rep.dead_air_ratio = rich["dead_air_ratio"]
            if rep.dead_air_ratio > 0.20:
                recs.append(
                    f"检测到干声静默片段占比过高 (dead_air={rep.dead_air_ratio:.1%})，建议混入低电平 cyber-lofi BGM 与切镜音效降低前3秒划走率"
                )

        # 2. Online HuggingFace Human-Perception APIs
        if allow_online:
            if c_path and c_path.exists():
                with Image.open(c_path) as cim:
                    cw, ch = cim.size
                rep.full_cover_anime_score = score_anime_visual_online(c_path, session=session)
                hero_box = (
                    (cw // 2, 0, cw, ch)
                    if cw >= ch
                    else (int(cw * 0.15), int(ch * 0.08), int(cw * 0.85), int(ch * 0.78))
                )
                rep.hero_portrait_anime_score = score_anime_visual_online(c_path, crop_box=hero_box, session=session)

            if v_path and v_path.exists():
                with tempfile.TemporaryDirectory() as tmpdir:
                    kf = self._extract_character_keyframe(v_path, 0.55, Path(tmpdir) / "kf_hook.jpg")
                    if kf is not None:
                        with Image.open(kf) as kim:
                            kw, kh = kim.size
                        char_box = (0, 0, int(kw * 0.48), kh) if kw >= kh else (0, 0, kw, kh)
                        rep.keyframe_hero_anime_score = score_anime_visual_online(
                            kf, crop_box=char_box, session=session
                        )

            if audio_target is not None:
                ab = score_audio_enjoyment_online(audio_target, session=session)
                if ab:
                    rep.audiobox_pq = ab.get("production_quality")
                    rep.audiobox_pc = ab.get("production_complexity")
                    rep.audiobox_ce = ab.get("content_enjoyment")
                    rep.audiobox_cu = ab.get("content_usefulness")

        # 3. Synthesize 0..100 Human Appeal Index
        vis_parts: List[float] = []
        if rep.local_cover_aesthetic_10 > 0:
            vis_parts.append(rep.local_cover_aesthetic_10 * 10.0)
        if rep.local_video_aesthetic_10 > 0:
            vis_parts.append(rep.local_video_aesthetic_10 * 10.0)
        if rep.hero_portrait_anime_score is not None:
            # skytnt raw anime score typically 0.15..0.85 -> map 0.45+ to 80..98 range
            vis_parts.append(min(100.0, max(25.0, 45.0 + rep.hero_portrait_anime_score * 75.0)))
        if rep.keyframe_hero_anime_score is not None:
            vis_parts.append(min(100.0, max(25.0, 45.0 + rep.keyframe_hero_anime_score * 75.0)))

        aud_parts: List[float] = []
        if rep.local_audio_richness_10 > 0:
            aud_parts.append(rep.local_audio_richness_10 * 10.0)
        if rep.audiobox_ce is not None and rep.audiobox_pq is not None:
            ab_mix = (rep.audiobox_ce * 0.45 + rep.audiobox_pq * 0.35 + (rep.audiobox_cu or 6.5) * 0.20) * 10.0
            aud_parts.append(ab_mix)

        vis_score = float(np.mean(vis_parts)) if vis_parts else 70.0
        aud_score = float(np.mean(aud_parts)) if aud_parts else 65.0
        rep.human_appeal_index = round(vis_score * 0.58 + aud_score * 0.42, 1)

        if rep.hero_portrait_anime_score is not None and rep.hero_portrait_anime_score < 0.28:
            recs.append(
                f"封面右侧角色特写二次元美感偏低 (hero_anime={rep.hero_portrait_anime_score:.3f})，建议放大胸腰以上高精度人物并增强光影层次"
            )
        if rep.audiobox_pc is not None and rep.audiobox_pc < 2.2:
            recs.append(
                f"Meta Audiobox 音频层次复杂度偏低 (PC={rep.audiobox_pc:.2f}/10)，建议增加侧链闪避背景音乐与转场音效"
            )
        if rep.audiobox_ce is not None and rep.audiobox_ce < 6.4:
            recs.append(f"Meta Audiobox 音频愉悦度有提升空间 (CE={rep.audiobox_ce:.2f}/10)")

        rep.recommendations = recs
        return rep
