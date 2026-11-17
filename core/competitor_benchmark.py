"""Market research and head-to-head competitor benchmarking engine for ContentFlow.

Codifies the shared comparative diagnostic loop across episodes:
  1. Measure cover luminance, saturation, and dark-area ratio against high-CTR Bilibili hits.
  2. Measure video pacing, scene-cut frequency per 10s, and luma dynamics.
  3. Fetch live Bilibili partition rankings (Dance, Kichiku/Meme, Douga, Tech) for viral benchmarks.
  4. Identify actionable perceptual gaps between our project deliverables and top-performing peers.
"""

from __future__ import annotations

import json
import re
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
DEFAULT_ANALYTICS_SNAPSHOT = Path("/home/mcocdaa/.contentflow/accounts/analytics/bilibili_latest.json")

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
        """Samples ~4 fps to measure duration, scene cuts/10s (HS hist + center/edge zoom MAD), and luma dynamics."""
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
        prev_small: Optional[np.ndarray] = None
        baseline_spatial_mad: Optional[float] = None
        baseline_center_mad: Optional[float] = None
        last_cut_sec = -10.0
        scene_cuts = 0
        spatial_zoom_cuts = 0
        luma_means: List[float] = []
        sampled = 0
        idx = 0

        try:
            while True:
                ok, frm = cap.read()
                if not ok:
                    break
                if idx % step == 0:
                    t_sec = idx / fps
                    small = cv2.resize(frm, (160, 90))
                    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
                    luma_means.append(float(hsv[..., 2].mean()))
                    hist = cv2.calcHist([hsv], [0, 1], None, [16, 16], [0, 180, 0, 256])
                    cv2.normalize(hist, hist)
                    if prev_hist is not None and prev_small is not None:
                        corr = float(cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL))
                        diff = np.abs(small.astype(np.float32) - prev_small.astype(np.float32))
                        center_slice = diff[18:72, 40:120]
                        center_mad = float(center_slice.mean())
                        edge_mad = float((diff.sum() - center_slice.sum()) / float(diff.size - center_slice.size))
                        spatial_mad = 0.55 * center_mad + 0.45 * edge_mad

                        if baseline_spatial_mad is None or baseline_center_mad is None:
                            is_hist_cut = corr < 0.68
                            is_zoom_cut = center_mad >= 20.0 and edge_mad >= 14.0
                        else:
                            is_hist_cut = corr < 0.68
                            is_zoom_cut = (
                                (
                                    center_mad >= 14.0
                                    and edge_mad >= 9.0
                                    and spatial_mad >= max(12.5, baseline_spatial_mad * 1.65)
                                )
                                or (
                                    center_mad >= 18.0
                                    and edge_mad >= 5.0
                                    and center_mad >= max(18.0, baseline_center_mad * 2.0)
                                )
                                or (
                                    baseline_center_mad <= 8.0
                                    and center_mad >= max(15.0, baseline_center_mad * 2.8 + 8.0)
                                )
                            )

                        if (is_hist_cut or is_zoom_cut) and (t_sec - last_cut_sec) >= 0.35:
                            scene_cuts += 1
                            if is_zoom_cut and not is_hist_cut:
                                spatial_zoom_cuts += 1
                            last_cut_sec = t_sec
                        else:
                            if baseline_spatial_mad is None or baseline_center_mad is None:
                                baseline_spatial_mad = spatial_mad
                                baseline_center_mad = center_mad
                            else:
                                baseline_spatial_mad = 0.65 * baseline_spatial_mad + 0.35 * spatial_mad
                                baseline_center_mad = 0.65 * baseline_center_mad + 0.35 * center_mad

                    prev_hist = hist
                    prev_small = small
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
            "zoom_or_spatial_cuts": float(spatial_zoom_cuts),
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

    def _build_bvid_project_map(self) -> Dict[str, Dict[str, Any]]:
        """Maps BVID -> local project metadata using staged Bilibili manifests when present."""
        mapping: Dict[str, Dict[str, Any]] = {}
        projects_dir = self.root_dir / "projects"
        if not projects_dir.exists():
            return mapping
        for mf in sorted(projects_dir.glob("*/delivery/staged_bilibili/publish_manifest.json")):
            try:
                mdata = json.loads(mf.read_text(encoding="utf-8"))
                bvid = str((mdata.get("advisor_receipt") or {}).get("bvid") or mdata.get("bvid") or "").strip()
                proj_id = str(mdata.get("project_id") or mf.parents[2].name).strip()
                tid = mdata.get("tid")
                if bvid:
                    mapping[bvid] = {
                        "project_id": proj_id,
                        "tid": int(tid) if tid is not None else None,
                    }
            except Exception:
                continue
        return mapping

    @staticmethod
    def _classify_archive_cohort(
        arc: Dict[str, Any],
        manifest_info: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Classifies an archive into 'vivid_entertainment' or 'legacy_whiteboard_tech'."""
        explicit_cohort = str(arc.get("cohort") or "").strip().lower()
        if explicit_cohort in ("vivid_entertainment", "entertainment", "vivid", "dance", "meme"):
            return "vivid_entertainment"
        if explicit_cohort in ("legacy_whiteboard_tech", "whiteboard", "legacy", "tech"):
            return "legacy_whiteboard_tech"

        proj_id = str(arc.get("project_id") or (manifest_info or {}).get("project_id") or "").strip()
        if proj_id:
            prefix = proj_id.split("_", 1)[0]
            if prefix.isdigit():
                ep_num = int(prefix)
                if ep_num >= 7:
                    return "vivid_entertainment"
                if 1 <= ep_num <= 6:
                    return "legacy_whiteboard_tech"
            low_pid = proj_id.lower()
            if any(k in low_pid for k in ("meme", "dance", "dafeiyu", "takeover", "march", "villa")):
                return "vivid_entertainment"
            if any(k in low_pid for k in ("tutorial", "whiteboard", "api", "transformer", "cicd")):
                return "legacy_whiteboard_tech"

        raw_tid = arc.get("tid") if arc.get("tid") is not None else (manifest_info or {}).get("tid")
        if raw_tid is not None:
            try:
                tid_val = int(raw_tid)
                if tid_val in (20, 25, 119, 129, 1, 198, 47):
                    return "vivid_entertainment"
                if tid_val in (188, 201, 231, 95, 122, 208):
                    return "legacy_whiteboard_tech"
            except (TypeError, ValueError):
                pass

        title = str(arc.get("title") or "")
        tech_kw = ("科普", "拆解", "原理", "报错", "避坑", "教程", "白板", "API", "CI/CD", "Transformer")
        ent_kw = (
            "整活",
            "热舞",
            "跳舞",
            "潮舞",
            "蹦迪",
            "星奇摇",
            "大展鸿图",
            "进行曲",
            "女仆",
            "宅舞",
            "狂跳",
            "开摇",
        )
        if any(k in title for k in ent_kw):
            return "vivid_entertainment"
        if any(k in title for k in tech_kw):
            return "legacy_whiteboard_tech"
        return "vivid_entertainment"

    @staticmethod
    def _summarize_cohort_metrics(label: str, episodes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregates view, like-rate, tm_stars, crash_rate_pct, and full_play_ratio_pct for a cohort."""
        count = len(episodes)
        if count == 0:
            return {
                "label": label,
                "count": 0,
                "total_views": 0,
                "total_likes": 0,
                "avg_views": 0.0,
                "like_rate_pct": 0.0,
                "mean_like_rate_pct": 0.0,
                "avg_tm_stars": 0.0,
                "avg_crash_rate_pct": 0.0,
                "avg_full_play_ratio_pct": 0.0,
                "episodes": [],
            }

        total_views = sum(int(ep["view"]) for ep in episodes)
        total_likes = sum(int(ep["like"]) for ep in episodes)
        avg_views = total_views / float(count)
        like_rate_pct = (total_likes / float(max(total_views, 1))) * 100.0 if total_views > 0 else 0.0
        mean_like_rate_pct = float(np.mean([float(ep["like_rate_pct"]) for ep in episodes]))

        tm_vals = [float(ep["tm_stars"]) for ep in episodes if ep.get("tm_stars") is not None]
        crash_vals = [float(ep["crash_rate_pct"]) for ep in episodes if ep.get("crash_rate_pct") is not None]
        full_vals = [float(ep["full_play_ratio_pct"]) for ep in episodes if ep.get("full_play_ratio_pct") is not None]

        return {
            "label": label,
            "count": count,
            "total_views": total_views,
            "total_likes": total_likes,
            "avg_views": round(avg_views, 2),
            "like_rate_pct": round(like_rate_pct, 2),
            "mean_like_rate_pct": round(mean_like_rate_pct, 2),
            "avg_tm_stars": round(float(np.mean(tm_vals)) if tm_vals else 0.0, 2),
            "avg_crash_rate_pct": round(float(np.mean(crash_vals)) if crash_vals else 0.0, 2),
            "avg_full_play_ratio_pct": round(float(np.mean(full_vals)) if full_vals else 0.0, 2),
            "episodes": episodes,
        }

    def analyze_telemetry_attribution(
        self,
        analytics_json_path: Optional[Union[str, Path]] = None,
    ) -> Dict[str, Any]:
        """Compares post-publish telemetry cohorts (vivid entertainment vs legacy whiteboard) with zero PII."""
        apath = Path(analytics_json_path) if analytics_json_path is not None else DEFAULT_ANALYTICS_SNAPSHOT
        if not apath.exists():
            raise FileNotFoundError(f"Analytics snapshot not found: {apath}")

        payload = json.loads(apath.read_text(encoding="utf-8"))
        account_obj = payload.get("account") or {}
        sensitive_tokens = {
            str(account_obj.get(k) or "").strip()
            for k in ("uid", "mid", "uname", "dede_userid")
            if str(account_obj.get(k) or "").strip() and str(account_obj.get(k) or "").strip() != "<REDACTED>"
        }

        def _scrub_text(val: str) -> str:
            cleaned = re.sub(r"@[\w\-\u4e00-\u9fff]+", "", val)
            for tok in sensitive_tokens:
                if tok:
                    cleaned = cleaned.replace(tok, "<REDACTED>")
            return cleaned.strip()

        bvid_map = self._build_bvid_project_map()
        raw_archives = payload.get("archives") or []

        vivid_eps: List[Dict[str, Any]] = []
        legacy_eps: List[Dict[str, Any]] = []
        scheduled_count = 0

        for arc in raw_archives:
            raw_state = arc.get("state")
            state = int(raw_state) if raw_state is not None else 0
            if state < 0:
                scheduled_count += 1
                continue

            bvid = _scrub_text(str(arc.get("bvid") or ""))
            m_info = bvid_map.get(bvid)
            cohort = self._classify_archive_cohort(arc, m_info)
            stat = arc.get("stat") or {}
            diag = arc.get("diagnose") or {}
            views = int(stat.get("view") or 0)
            likes = int(stat.get("like") or 0)
            ep_like_rate_pct = round((likes / float(max(views, 1))) * 100.0, 2) if views > 0 else 0.0

            ep_entry: Dict[str, Any] = {
                "bvid": bvid,
                "project_id": _scrub_text(str(arc.get("project_id") or (m_info or {}).get("project_id") or "")),
                "title": _scrub_text(str(arc.get("title") or "")),
                "cohort": cohort,
                "view": views,
                "like": likes,
                "like_rate_pct": ep_like_rate_pct,
                "tm_stars": round(float(diag["tm_stars"]), 2) if diag.get("tm_stars") is not None else None,
                "crash_rate_pct": (
                    round(float(diag["crash_rate_pct"]), 2) if diag.get("crash_rate_pct") is not None else None
                ),
                "full_play_ratio_pct": (
                    round(float(diag["full_play_ratio_pct"]), 2)
                    if diag.get("full_play_ratio_pct") is not None
                    else None
                ),
            }
            if cohort == "vivid_entertainment":
                vivid_eps.append(ep_entry)
            else:
                legacy_eps.append(ep_entry)

        vivid_summary = self._summarize_cohort_metrics("新娱乐高明度热舞/整活赛道", vivid_eps)
        legacy_summary = self._summarize_cohort_metrics("旧静态白板硬核科普赛道", legacy_eps)

        views_diff = round(vivid_summary["avg_views"] - legacy_summary["avg_views"], 2)
        views_ratio = (
            round(vivid_summary["avg_views"] / float(legacy_summary["avg_views"]), 2)
            if legacy_summary["avg_views"] > 0
            else 0.0
        )
        like_diff = round(vivid_summary["like_rate_pct"] - legacy_summary["like_rate_pct"], 2)
        stars_diff = round(vivid_summary["avg_tm_stars"] - legacy_summary["avg_tm_stars"], 2)
        crash_diff = round(vivid_summary["avg_crash_rate_pct"] - legacy_summary["avg_crash_rate_pct"], 2)
        full_diff = round(vivid_summary["avg_full_play_ratio_pct"] - legacy_summary["avg_full_play_ratio_pct"], 2)

        all_pub = vivid_eps + legacy_eps
        top_ep = max(all_pub, key=lambda x: (int(x["view"]), int(x["like"]))) if all_pub else None
        snap_ts = _scrub_text(str(payload.get("timestamp") or "unknown"))

        md_lines = [
            "### 发布后流水归因对比报告（Telemetry Cohort Attribution）",
            f"- 快照时间：`{snap_ts}`（已发布稿件 `{len(all_pub)}` 篇，定时待发 `{scheduled_count}` 篇）",
            "",
            "| 赛道分群 (Cohort) | 样本数 | 平均播放量 | 点赞率 | 平均封标星级 (`tm_stars`) | 平均 3 秒划走率 (`crash_rate_pct`) | 平均完播率 (`full_play_ratio_pct`) |",
            "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
            (
                f"| {vivid_summary['label']} | {vivid_summary['count']} | {vivid_summary['avg_views']:.2f} | "
                f"{vivid_summary['like_rate_pct']:.2f}% | {vivid_summary['avg_tm_stars']:.2f} | "
                f"{vivid_summary['avg_crash_rate_pct']:.2f}% | {vivid_summary['avg_full_play_ratio_pct']:.2f}% |"
            ),
            (
                f"| {legacy_summary['label']} | {legacy_summary['count']} | {legacy_summary['avg_views']:.2f} | "
                f"{legacy_summary['like_rate_pct']:.2f}% | {legacy_summary['avg_tm_stars']:.2f} | "
                f"{legacy_summary['avg_crash_rate_pct']:.2f}% | {legacy_summary['avg_full_play_ratio_pct']:.2f}% |"
            ),
            (
                f"| **差值 (新娱乐 - 旧白板)** | — | **{views_diff:+.2f}** | **{like_diff:+.2f}%** | "
                f"**{stars_diff:+.2f}** | **{crash_diff:+.2f}%** | **{full_diff:+.2f}%** |"
            ),
        ]
        if top_ep is not None:
            top_crash = f"{top_ep['crash_rate_pct']:.2f}%" if top_ep["crash_rate_pct"] is not None else "N/A"
            top_stars = f"{top_ep['tm_stars']:.1f}" if top_ep["tm_stars"] is not None else "N/A"
            md_lines.extend(
                [
                    "",
                    (
                        f"- **头部标杆单篇**：`{top_ep['bvid']}`（{top_ep['title'][:36]}）— "
                        f"`{top_ep['view']}` 播放 / 点赞率 `{top_ep['like_rate_pct']:.2f}%` / "
                        f"封标 `{top_stars}` 星 / 3 秒划走率 `{top_crash}`"
                    ),
                ]
            )
        md_lines.append(
            f"- **归因结论**：新娱乐高明度赛道平均播放量为旧白板赛道的 `{views_ratio:.2f}x`（`{views_diff:+.2f}`），"
            f"点赞率 `{like_diff:+.2f}%`，封标星级 `{stars_diff:+.2f}` 星，3 秒划走率变化 `{crash_diff:+.2f}%`。"
        )
        markdown_summary = "\n".join(md_lines)

        return {
            "snapshot_timestamp": snap_ts,
            "published_count": len(all_pub),
            "scheduled_count": scheduled_count,
            "cohorts": {
                "vivid_entertainment": vivid_summary,
                "legacy_whiteboard_tech": legacy_summary,
            },
            "deltas": {
                "avg_views_diff": views_diff,
                "avg_views_ratio": views_ratio,
                "like_rate_pct_diff": like_diff,
                "tm_stars_diff": stars_diff,
                "crash_rate_pct_diff": crash_diff,
                "full_play_ratio_pct_diff": full_diff,
            },
            "top_episode": top_ep,
            "markdown_summary": markdown_summary,
        }
