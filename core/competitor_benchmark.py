"""Market research and head-to-head competitor benchmarking engine for ContentFlow.

Codifies the shared comparative diagnostic loop across episodes:
  1. Measure cover luminance, saturation, and dark-area ratio against high-CTR Bilibili hits.
  2. Measure video pacing, scene-cut frequency per 10s, and luma dynamics.
  3. Fetch live Bilibili partition rankings (Dance, Kichiku/Meme, Douga, Tech) for viral benchmarks.
  4. Identify actionable perceptual gaps between our project deliverables and top-performing peers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import cv2
import numpy as np
import requests
from PIL import Image

from config.settings import CONTENTFLOW_ROOT
from core.auth_vault import STANDARD_USER_AGENT
from core.quality_gate import VideoQualityGate

BILIBILI_RANKING_V2_URL = "https://api.bilibili.com/x/web-interface/ranking/v2"

DEFAULT_BENCHMARK_RIDS: Dict[str, int] = {
    "dance": 129,
    "kichiku": 119,
    "douga": 1,
    "tech": 188,
}

INNOVATION_LOOP_STEPS: List[str] = [
    "1_telemetry_bottleneck_diagnosis",
    "2_live_competitor_deconstruction",
    "3_fresh_concept_and_novelty_ledger_check",
    "4_multi_shot_60fps_assembly_and_vivid_cover",
    "5_post_publish_retention_review",
]


class CompetitorBenchmarkEngine:
    """Measures objective visual/pacing competitiveness against viral Bilibili benchmarks."""

    def __init__(
        self,
        root_dir: Optional[Union[str, Path]] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.root_dir = Path(root_dir or CONTENTFLOW_ROOT)
        self.session = session or requests.Session()
        self.gate = VideoQualityGate(root_dir=self.root_dir)

    @staticmethod
    def measure_cover(cover_path: Union[str, Path]) -> Dict[str, float]:
        """Measures cover brightness (HSV V), saturation (HSV S), and near-black ratio (<45)."""
        cpath = Path(cover_path)
        if not cpath.exists():
            raise FileNotFoundError(f"Cover file not found: {cpath}")

        with Image.open(cpath) as img:
            rgb = np.array(img.convert("RGB"))
            w, h = img.size

        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        saturation = float(hsv[..., 1].mean())
        mean_brightness = float(hsv[..., 2].mean())
        dark_area_ratio = float((rgb.max(axis=-1) < 45).mean())

        return {
            "width": float(w),
            "height": float(h),
            "mean_brightness": round(mean_brightness, 2),
            "saturation": round(saturation, 2),
            "dark_area_ratio": round(dark_area_ratio, 4),
        }

    @staticmethod
    def measure_video_pacing(video_path: Union[str, Path]) -> Dict[str, float]:
        """Samples ~4 fps to measure duration, scene cuts/10s, and brightness dynamics."""
        vpath = Path(video_path)
        if not vpath.exists():
            raise FileNotFoundError(f"Video file not found: {vpath}")

        cap = cv2.VideoCapture(str(vpath))
        if not cap.isOpened():
            raise RuntimeError(f"Unable to open video for pacing audit: {vpath}")

        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        if fps <= 1.0:
            fps = 30.0
        n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration_sec = n_frames / fps if n_frames > 0 else 0.0

        step = max(1, int(round(fps / 4.0)))
        prev_hist: Optional[np.ndarray] = None
        scene_cuts = 0
        luma_means: List[float] = []
        sampled = 0
        idx = 0

        try:
            while True:
                ok, frm = cap.read()
                if not ok:
                    break
                if idx % step == 0:
                    small = cv2.resize(frm, (160, 90))
                    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
                    luma_means.append(float(hsv[..., 2].mean()))
                    hist = cv2.calcHist([hsv], [0, 1], None, [16, 16], [0, 180, 0, 256])
                    cv2.normalize(hist, hist)
                    if prev_hist is not None:
                        corr = float(cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL))
                        if corr < 0.68:
                            scene_cuts += 1
                    prev_hist = hist
                    sampled += 1
                idx += 1
        finally:
            cap.release()

        if duration_sec <= 0.0 and sampled > 0:
            duration_sec = (idx) / fps

        cuts_per_10s = scene_cuts / max(duration_sec / 10.0, 0.1)
        return {
            "duration_sec": round(duration_sec, 2),
            "scene_cuts": float(scene_cuts),
            "cuts_per_10s": round(cuts_per_10s, 2),
            "mean_brightness": round(float(np.mean(luma_means)) if luma_means else 0.0, 2),
            "brightness_std": round(float(np.std(luma_means)) if luma_means else 0.0, 2),
        }

    def fetch_live_partition_benchmarks(
        self,
        rids: Optional[Dict[str, int]] = None,
        top_k: int = 5,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Queries Bilibili ranking/v2 across partitions and summarizes engagement rates."""
        target_rids = rids or DEFAULT_BENCHMARK_RIDS
        headers = {
            "User-Agent": STANDARD_USER_AGENT,
            "Referer": "https://www.bilibili.com/",
            "Accept": "application/json, text/plain, */*",
        }
        benchmarks: Dict[str, List[Dict[str, Any]]] = {}
        for label, rid in target_rids.items():
            rows: List[Dict[str, Any]] = []
            try:
                resp = self.session.get(
                    BILIBILI_RANKING_V2_URL,
                    params={"rid": str(rid), "type": "all"},
                    headers=headers,
                    timeout=10,
                )
                if resp.status_code == 200:
                    raw_items = (resp.json().get("data") or {}).get("list") or []
                    for item in raw_items[:top_k]:
                        stat = item.get("stat") or {}
                        views = max(1, int(stat.get("view") or 1))
                        likes = int(stat.get("like") or 0)
                        favs = int(stat.get("favorite") or 0)
                        coins = int(stat.get("coin") or 0)
                        owner = item.get("owner") or {}
                        rows.append(
                            {
                                "bvid": item.get("bvid", ""),
                                "title": item.get("title", ""),
                                "author": owner.get("name", ""),
                                "duration": int(item.get("duration") or 0),
                                "view": int(stat.get("view") or 0),
                                "like_rate": round(likes / float(views), 4),
                                "fav_rate": round(favs / float(views), 4),
                                "coin_rate": round(coins / float(views), 4),
                                "pic": item.get("pic", ""),
                            }
                        )
            except Exception:
                rows = []
            benchmarks[label] = rows
        return benchmarks

    def compare_project_against_benchmarks(
        self,
        project: Union[str, Path],
        competitor_video_path: Optional[Union[str, Path]] = None,
        competitor_cover_path: Optional[Union[str, Path]] = None,
        fetch_online: bool = False,
        save_report: bool = False,
    ) -> Dict[str, Any]:
        """Compares a project's cover & video pacing against empirical Bilibili viral baselines."""
        proj_dir = self.gate.resolve_project_dir(project)
        video_path, cover_path = self.gate._find_project_video_and_cover(proj_dir)

        cover_metrics = self.measure_cover(cover_path) if (cover_path and cover_path.exists()) else {}
        video_metrics = self.measure_video_pacing(video_path) if (video_path and video_path.exists()) else {}

        competitor_metrics: Dict[str, Any] = {}
        if competitor_cover_path and Path(competitor_cover_path).exists():
            competitor_metrics["cover"] = self.measure_cover(competitor_cover_path)
        if competitor_video_path and Path(competitor_video_path).exists():
            competitor_metrics["video"] = self.measure_video_pacing(competitor_video_path)

        gaps: List[Dict[str, str]] = []
        if cover_metrics:
            cov_bright = cover_metrics["mean_brightness"]
            dark_ratio = cover_metrics["dark_area_ratio"]
            if cov_bright < 105.0 or dark_ratio > 0.25:
                gaps.append(
                    {
                        "area": "cover",
                        "severity": "P0",
                        "detail": (
                            f"brightness={cov_bright:.1f}, dark_area_ratio={dark_ratio:.1%}: "
                            "封面暗部面积过大（课件感黑底），在B站亮底双列信息流中易被视线跳过，建议启用 vivid_scene 满幅高明度封面"
                        ),
                    }
                )

        if video_metrics:
            dur = video_metrics["duration_sec"]
            cuts_10s = video_metrics["cuts_per_10s"]
            if dur >= 8.0 and cuts_10s < 1.8:
                gaps.append(
                    {
                        "area": "video_pacing",
                        "severity": "P1",
                        "detail": (
                            f"duration={dur:.1f}s, cuts_per_10s={cuts_10s:.2f}: "
                            "单机位固定景别持续过长，缺少2-3秒一次的鼓点近景切镜（Beat Punch-In），易造成中段审美疲劳"
                        ),
                    }
                )

        online_benchmarks = self.fetch_live_partition_benchmarks() if fetch_online else {}

        report: Dict[str, Any] = {
            "project_id": proj_dir.name,
            "project_dir": str(proj_dir),
            "cover_path": str(cover_path) if cover_path else None,
            "video_path": str(video_path) if video_path else None,
            "cover_metrics": cover_metrics,
            "video_metrics": video_metrics,
            "competitor_metrics": competitor_metrics,
            "gaps": gaps,
            "online_benchmarks": online_benchmarks,
            "innovation_loop_steps": list(INNOVATION_LOOP_STEPS),
        }

        if save_report:
            bench_dir = self.root_dir / "library" / "benchmarks"
            bench_dir.mkdir(parents=True, exist_ok=True)
            out_json = bench_dir / f"{proj_dir.name}_benchmark.json"
            out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            report["report_path"] = str(out_json)

        return report
