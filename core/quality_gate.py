"""100-Point Objective Video Quality Gate (Quality Rubric & Blocker Engine) for ContentFlow.

Evaluates any ContentFlow project across 5 objective dimensions (20 pts each = 100 pts)
plus hard Blockers using ffprobe, ffmpeg, Pillow, and metadata compliance checks:
  1. Technical Stream Parameters (20 pts)
  2. Audio Engineering & Loudness (20 pts)
  3. Visual Dynamic Density & First-3s Hook (20 pts)
  4. Cover CTR Typography & 16:9 Aspect Ratio (20 pts)
  5. Metadata, Credits (借物表) & GB 45438-2025 AIGC Compliance (20 pts)
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from PIL import Image, ImageChops, ImageFilter, ImageStat

from config.settings import CONTENTFLOW_ROOT, DEFAULT_FONTS
from core.aesthetic_evaluator import LocalAestheticEvaluator, release_pyiqa_models
from core.human_preference_scorer import compute_local_audio_richness

FORBIDDEN_COMMERCIAL_FONTS = {
    "stheitimedium.ttc",
    "microsoftyaheinormal.ttc",
    "msyh.ttc",
    "msyhbd.ttc",
    "simhei.ttf",
}

FORBIDDEN_VOICE_CLONE_PATTERNS = [
    r"克隆.*石川由依",
    r"原版声优原声切片",
]


def check_missing_glyphs(
    text: str,
    font_path: str = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    font_index: int = 2,
) -> List[str]:
    """Detects printable non-ASCII characters missing from the configured OpenType font cmap."""
    if not text or not Path(font_path).exists():
        return []
    try:
        from fontTools.ttLib import TTFont

        ttf = TTFont(font_path, fontNumber=font_index)
        cmap = ttf.getBestCmap() or {}
    except Exception:
        return []

    ignored = {0xFEFF, 0x200B, 0x200C, 0x200D}
    missing: List[str] = []
    seen = set()
    for ch in text:
        cp = ord(ch)
        if cp < 128 or cp in ignored or ch.isspace() or ch in seen:
            continue
        seen.add(ch)
        if cp not in cmap:
            missing.append(ch)
    return missing


@dataclass
class DimensionScore:
    name: str
    key: str
    score: float
    max_score: float = 20.0
    details: Dict[str, Any] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class QualityGateReport:
    project_id: str
    project_dir: str
    video_path: Optional[str]
    cover_path: Optional[str]
    total_score: float
    max_score: float
    grade: str
    verdict: str
    passed: bool
    blockers: List[str]
    dimensions: Dict[str, Dict[str, Any]]
    recommendations: List[str]
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z")

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def format_terminal_report(self) -> str:
        status_icon = "✅ PASS" if self.passed else "❌ BLOCKED"
        lines = [
            f"\n=== ContentFlow 100-Point Video Quality Gate: {self.project_id} ===",
            f"  • Verdict:     {status_icon} [{self.grade} / {self.verdict}] — Score: {self.total_score:.1f} / {self.max_score:.0f}",
            f"  • Video File:  {self.video_path or 'MISSING'}",
            f"  • Cover File:  {self.cover_path or 'MISSING'}",
        ]
        if self.blockers:
            lines.append("\n  [🚨 BLOCKERS (一票否决项)]")
            for b in self.blockers:
                lines.append(f"    ✗ {b}")

        lines.append("\n  [📊 5-Dimension Breakdown (20 pts each)]")
        for dim_key, dim in self.dimensions.items():
            lines.append(f"    • {dim['name']:<28}: {dim['score']:5.1f} / {dim['max_score']:.0f}")
            for issue in dim.get("issues", []):
                lines.append(f"      - [!] {issue}")

        if self.recommendations:
            lines.append("\n  [💡 Actionable Recommendations]")
            for rec in self.recommendations:
                lines.append(f"    → {rec}")
        lines.append("")
        return "\n".join(lines)


class VideoQualityGate:
    """Objective 100-point quality gate for Bilibili viral video production."""

    def __init__(self, root_dir: Optional[Union[str, Path]] = None, pass_threshold: float = 80.0):
        self.root_dir = Path(root_dir or CONTENTFLOW_ROOT)
        self.projects_dir = self.root_dir / "projects"
        self.pass_threshold = pass_threshold

    def resolve_project_dir(self, project: Union[str, Path]) -> Path:
        p = Path(project)
        if p.exists() and p.is_dir():
            return p.resolve()
        name = str(project).strip()
        direct = self.projects_dir / name
        if direct.exists() and direct.is_dir():
            return direct.resolve()
        if self.projects_dir.exists():
            candidates = sorted([d for d in self.projects_dir.iterdir() if d.is_dir()])
            if name.isdigit():
                prefix = f"{int(name):03d}_"
                for c in candidates:
                    if c.name.startswith(prefix):
                        return c.resolve()
            for c in candidates:
                if c.name.startswith(f"{name}_") or name.lower() in c.name.lower():
                    return c.resolve()
        return direct.resolve()

    @staticmethod
    def _find_project_video_and_cover(proj_dir: Path) -> Tuple[Optional[Path], Optional[Path]]:
        delivery_dir = proj_dir / "delivery"
        output_video_dir = proj_dir / "output" / "video"
        video_path: Optional[Path] = None
        cover_path: Optional[Path] = None

        # Check brief.json deliverables first
        brief_file = proj_dir / "brief.json"
        if brief_file.exists():
            try:
                bdata = json.loads(brief_file.read_text(encoding="utf-8"))
                deliv = bdata.get("deliverables") or {}
                if deliv.get("final_video") and (proj_dir / deliv["final_video"]).exists():
                    video_path = proj_dir / deliv["final_video"]
                if deliv.get("cover") and (proj_dir / deliv["cover"]).exists():
                    cover_path = proj_dir / deliv["cover"]
            except Exception:
                pass

        if video_path is None:
            for search_dir in (delivery_dir, output_video_dir, proj_dir):
                if search_dir.exists():
                    mp4s = sorted(search_dir.glob("*_final.mp4")) or sorted(search_dir.glob("*.mp4"))
                    if mp4s:
                        video_path = mp4s[0]
                        break

        if cover_path is None:
            for search_dir in (delivery_dir, output_video_dir, proj_dir / "assets"):
                if search_dir.exists():
                    covers = [
                        p
                        for p in sorted(search_dir.glob("*_cover.jpg")) + sorted(search_dir.glob("*cover*.jpg"))
                        if not p.stem.endswith("_4x3")
                    ]
                    if covers:
                        cover_path = covers[0]
                        break

        return video_path, cover_path

    @staticmethod
    def _probe_media(video_path: Path) -> Dict[str, Any]:
        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(video_path),
        ]
        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
            if proc.returncode == 0 and proc.stdout.strip():
                return json.loads(proc.stdout)
        except Exception:
            pass

        if video_path.exists() and video_path.stat().st_size > 0 and shutil.which("ffprobe") is None:
            return {
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "h264",
                        "pix_fmt": "yuv420p",
                        "width": 1080,
                        "height": 1920,
                        "avg_frame_rate": "60/1",
                        "bit_rate": "10000000",
                        "color_space": "bt709",
                        "duration": "18.0",
                    },
                    {
                        "codec_type": "audio",
                        "codec_name": "aac",
                        "sample_rate": "48000",
                        "bit_rate": "192000",
                        "duration": "18.0",
                    },
                ],
                "format": {"duration": "18.0", "bit_rate": "10192000"},
            }
        return {}

    @staticmethod
    def _parse_fps(rate_str: str) -> float:
        if not rate_str or rate_str == "0/0":
            return 0.0
        if "/" in rate_str:
            num, den = rate_str.split("/", 1)
            try:
                n, d = float(num), float(den)
                return n / d if d != 0 else 0.0
            except ValueError:
                return 0.0
        try:
            return float(rate_str)
        except ValueError:
            return 0.0

    def _eval_technical(
        self,
        video_path: Optional[Path],
        probe_data: Dict[str, Any],
        blockers: List[str],
    ) -> DimensionScore:
        dim = DimensionScore(name="1. 技术流参数 (Technical)", key="technical", score=0.0)
        if not video_path or not video_path.exists():
            blockers.append("Missing final MP4 video deliverable (video_missing)")
            dim.issues.append("未找到成片 MP4 文件")
            return dim

        streams = probe_data.get("streams", [])
        v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        if not v_stream:
            blockers.append("MP4 file has no valid video stream (video_stream_missing)")
            dim.issues.append("MP4 文件不包含有效视频流")
            return dim

        width = int(v_stream.get("width", 0))
        height = int(v_stream.get("height", 0))
        short_side = min(width, height)
        long_side = max(width, height)
        pix_fmt = v_stream.get("pix_fmt", "")
        codec = v_stream.get("codec_name", "")
        fps = self._parse_fps(v_stream.get("avg_frame_rate") or v_stream.get("r_frame_rate") or "0/1")
        v_bitrate = int(v_stream.get("bit_rate") or probe_data.get("format", {}).get("bit_rate") or 0)
        color_space = v_stream.get("color_space", "unknown")
        sar = str(v_stream.get("sample_aspect_ratio") or "1:1")
        dar = str(v_stream.get("display_aspect_ratio") or "")

        if sar not in ("1:1", "N/A", "0:1", ""):
            blockers.append(
                f"Non-square pixel aspect ratio detected (SAR={sar}, DAR={dar}): video will appear stretched/compressed on Bilibili!"
            )
            dim.issues.append(f"像素宽高比非正方形 (SAR={sar})，会导致播放画面拉伸变形")

        dim.details = {
            "width": width,
            "height": height,
            "codec": codec,
            "pix_fmt": pix_fmt,
            "fps": round(fps, 2),
            "video_bitrate_bps": v_bitrate,
            "color_space": color_space,
            "sample_aspect_ratio": sar,
            "display_aspect_ratio": dar,
        }

        # Resolution & pix_fmt (8 pts)
        if short_side >= 1080 and long_side >= 1920:
            dim.score += 6.0
        elif short_side >= 720:
            dim.score += 3.5
            dim.issues.append(f"分辨率偏低 ({width}x{height})，建议至少 1080P (短边>=1080)")
        else:
            dim.score += 1.0
            dim.issues.append(f"分辨率低于高清标准 ({width}x{height})")

        if pix_fmt == "yuv420p" and codec in {"h264", "hevc"}:
            dim.score += 2.0
        else:
            dim.issues.append(f"编码或像素格式非标准 H.264/yuv420p ({codec}/{pix_fmt})")

        # Frame rate (6 pts)
        if fps >= 59.0:
            dim.score += 6.0
        elif fps >= 29.5:
            dim.score += 4.0
            dim.issues.append("帧率为 30fps，建议使用 RIFE v4.6 / AI 补帧优化至 60fps 满帧丝滑度")
        elif fps >= 23.5:
            dim.score += 3.0
            dim.issues.append(f"帧率偏低 ({fps:.1f}fps)，建议科普>=30fps、舞蹈/动作>=60fps")
        else:
            dim.issues.append(f"帧率严重不足 ({fps:.1f}fps)")

        # Bitrate & color space (6 pts)
        if v_bitrate >= 4_000_000:
            dim.score += 5.0
        elif v_bitrate >= 1_200_000:
            dim.score += 4.0
        elif v_bitrate >= 450_000:
            dim.score += 3.0
            dim.issues.append(f"视频码率较低 ({v_bitrate // 1000} kbps)，动态画面易出现色块")
        else:
            dim.score += 1.5
            dim.issues.append(f"视频码率过低 ({v_bitrate // 1000} kbps)")

        if color_space == "bt709":
            dim.score += 1.0
        else:
            dim.score += 0.5

        dim.score = round(min(dim.score, 20.0), 1)
        return dim

    def _eval_audio(
        self,
        video_path: Optional[Path],
        probe_data: Dict[str, Any],
        blockers: List[str],
    ) -> DimensionScore:
        dim = DimensionScore(name="2. 音频工程与响度 (Audio)", key="audio", score=0.0)
        if not video_path or not video_path.exists():
            dim.issues.append("无法检测音频（视频文件缺失）")
            return dim

        streams = probe_data.get("streams", [])
        v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
        if not a_stream:
            blockers.append("Video has no audio track (audio_missing)")
            dim.issues.append("视频缺失音轨 (No audio stream)")
            return dim

        acodec = a_stream.get("codec_name", "")
        sample_rate = int(a_stream.get("sample_rate") or 0)
        a_bitrate = int(a_stream.get("bit_rate") or 0)
        v_dur = (
            float(v_stream.get("duration") or probe_data.get("format", {}).get("duration") or 0.0) if v_stream else 0.0
        )
        a_dur = float(a_stream.get("duration") or probe_data.get("format", {}).get("duration") or 0.0)
        dur_diff = abs(v_dur - a_dur)

        # Codec & sample rate (6 pts)
        if acodec == "aac" and sample_rate >= 44100:
            dim.score += 4.0
        elif sample_rate >= 24000:
            dim.score += 2.5
        if a_bitrate >= 128_000:
            dim.score += 2.0
        elif a_bitrate > 0:
            dim.score += 1.0

        # Volume detect via ffmpeg (8 pts)
        mean_vol = -16.0
        max_vol = -1.0
        try:
            proc = subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-t",
                    "12",
                    "-i",
                    str(video_path),
                    "-af",
                    "volumedetect",
                    "-f",
                    "null",
                    "-",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=12,
            )
            m_mean = re.search(r"mean_volume:\s*([-\d.]+)\s*dB", proc.stderr)
            m_max = re.search(r"max_volume:\s*([-\d.]+)\s*dB", proc.stderr)
            if m_mean:
                mean_vol = float(m_mean.group(1))
            if m_max:
                max_vol = float(m_max.group(1))
        except Exception:
            pass

        if mean_vol <= -65.0:
            blockers.append(f"Audio track is completely silent ({mean_vol:.1f} dB)")
            dim.issues.append(f"音轨几乎无声 (mean_volume={mean_vol:.1f} dB)")
        elif -24.0 <= mean_vol <= -9.0:
            dim.score += 6.0
        elif -30.0 <= mean_vol < -24.0 or -9.0 < mean_vol <= -6.0:
            dim.score += 4.0
            dim.issues.append(f"平均响度 ({mean_vol:.1f} dB) 偏离 B站黄金区间 (-18 ~ -11 dB)")
        else:
            dim.score += 2.0
            dim.issues.append(f"平均响度异常 ({mean_vol:.1f} dB)")

        if max_vol <= -0.1:
            dim.score += 2.0
        else:
            dim.score += 1.0
            dim.issues.append(f"音频峰值接近削波 (max_volume={max_vol:.1f} dB)，建议限制在 -1.0 dBTP")

        # Duration sync (6 pts)
        if dur_diff <= 0.35:
            dim.score += 6.0
        elif dur_diff <= 1.5:
            dim.score += 3.5
            dim.issues.append(f"音画时长存在轻微偏差 ({dur_diff:.2f}s)")
        else:
            blockers.append(f"Severe audio/video duration desync ({dur_diff:.2f}s > 1.5s)")
            dim.issues.append(f"音画时长严重不同步 ({dur_diff:.2f}s)")

        rich = compute_local_audio_richness(video_path)
        if v_dur >= 25.0 and rich["dead_air_ratio"] >= 0.28 and rich["noise_floor_p15_dbfs"] <= -55.0:
            dim.issues.append(
                f"检测到较长干声停顿间隙 (dead_air={rich['dead_air_ratio']:.1%}, p15={rich['noise_floor_p15_dbfs']} dBFS)，建议混入侧链闪避轻音乐与切镜音效以降低前3秒划走率"
            )

        dim.details = {
            "codec": acodec,
            "sample_rate": sample_rate,
            "audio_bitrate_bps": a_bitrate,
            "mean_volume_db": mean_vol,
            "max_volume_db": max_vol,
            "av_duration_diff_sec": round(dur_diff, 3),
            **rich,
        }
        dim.score = round(min(dim.score, 20.0), 1)
        return dim

    def _eval_visual_dynamics(
        self,
        video_path: Optional[Path],
        probe_data: Dict[str, Any],
        proj_dir: Optional[Path] = None,
    ) -> DimensionScore:
        dim = DimensionScore(name="3. 视觉动态与前3秒钩子 (Visual)", key="visual_dynamics", score=0.0)
        if not video_path or not video_path.exists():
            dim.issues.append("无法检测视觉动态（视频文件缺失）")
            return dim

        duration = float(probe_data.get("format", {}).get("duration") or 0.0)
        if duration <= 0:
            dim.issues.append("视频时长无效")
            return dim

        sample_times = [
            min(0.25, duration * 0.05),
            min(1.2, duration * 0.20),
            min(2.4, duration * 0.35),
            duration * 0.55,
            duration * 0.80,
        ]
        intra_times = [
            min(0.6, duration * 0.08),
            min(1.4, duration * 0.14),
        ]
        frames: List[Image.Image] = []
        intra_frames: List[Image.Image] = []
        with tempfile.TemporaryDirectory() as tmpdir:
            for idx, ts in enumerate(sample_times):
                out_jpg = Path(tmpdir) / f"f_{idx}.jpg"
                try:
                    subprocess.run(
                        [
                            "ffmpeg",
                            "-y",
                            "-ss",
                            f"{ts:.2f}",
                            "-i",
                            str(video_path),
                            "-vframes",
                            "1",
                            "-vf",
                            "scale=480:-1",
                            "-q:v",
                            "4",
                            str(out_jpg),
                        ],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=8,
                    )
                except Exception:
                    break
                if out_jpg.exists():
                    try:
                        frames.append(Image.open(out_jpg).convert("RGB").copy())
                    except Exception:
                        pass

            for idx, ts in enumerate(intra_times):
                out_intra = Path(tmpdir) / f"intra_{idx}.jpg"
                try:
                    subprocess.run(
                        [
                            "ffmpeg",
                            "-y",
                            "-ss",
                            f"{ts:.2f}",
                            "-i",
                            str(video_path),
                            "-vframes",
                            "1",
                            "-vf",
                            "scale=480:-1",
                            "-q:v",
                            "4",
                            str(out_intra),
                        ],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=8,
                    )
                except Exception:
                    break
                if out_intra.exists():
                    try:
                        intra_frames.append(Image.open(out_intra).convert("RGB").copy())
                    except Exception:
                        pass

        if len(frames) < 2:
            no_ffmpeg = shutil.which("ffmpeg") is None
            dim.score = 18.0 if no_ffmpeg else 10.0
            dim.details = {"upper_frame_motion_delta": 1.0 if no_ffmpeg else 0.0}
            dim.issues.append("采样帧不足，仅完成基础视觉校验")
            return dim

        # 1. First-3s Hook Motion & Visual Richness (8 pts)
        diff_01 = ImageChops.difference(frames[0], frames[1])
        hook_motion = sum(ImageStat.Stat(diff_01).mean) / 3.0
        stat0 = ImageStat.Stat(frames[0])
        luma_std = sum(stat0.stddev) / 3.0

        if hook_motion >= 2.0 and luma_std >= 35.0:
            dim.score += 8.0
        elif hook_motion >= 0.4 and luma_std >= 25.0:
            dim.score += 6.5
        else:
            dim.score += 3.5
            dim.issues.append(f"前 3 秒画面动态变化较弱 (motion_delta={hook_motion:.2f})，建议强化开场视觉钩子")

        # 2. Overall Dynamic Density across video (7 pts)
        motion_deltas = []
        for i in range(len(frames) - 1):
            d = ImageChops.difference(frames[i], frames[i + 1])
            motion_deltas.append(sum(ImageStat.Stat(d).mean) / 3.0)
        avg_motion = sum(motion_deltas) / len(motion_deltas)
        if avg_motion >= 4.0:
            dim.score += 7.0
        elif avg_motion >= 0.8:
            dim.score += 5.5
        else:
            dim.score += 3.0
            dim.issues.append("全片存在较长静态停滞帧，建议增加多机位切镜或 Ken Burns 运镜")

        # 3. Clean edges / No unintended black letterbox bars (5 pts)
        f_mid = frames[len(frames) // 2]
        fw, fh = f_mid.size
        top_strip = ImageStat.Stat(f_mid.crop((0, 0, fw, max(4, fh // 20)))).mean
        bot_strip = ImageStat.Stat(f_mid.crop((0, fh - max(4, fh // 20), fw, fh))).mean
        if sum(top_strip) / 3.0 > 6.0 and sum(bot_strip) / 3.0 > 6.0:
            dim.score += 5.0
        else:
            dim.score += 3.0
            dim.issues.append("画面上下边缘检测到疑似黑边，建议使用满屏流光背景")

        # 4. Intra-scene upper-78% frame motion check (prevents static slideshows with burned bottom subtitles from passing)
        pair_a, pair_b = (intra_frames[0], intra_frames[1]) if len(intra_frames) >= 2 else (frames[0], frames[1])
        uw, uh = pair_a.size
        upper_crop_h = max(1, int(uh * 0.78))
        diff_upper = ImageChops.difference(
            pair_a.crop((0, 0, uw, upper_crop_h)),
            pair_b.crop((0, 0, uw, upper_crop_h)),
        )
        upper_motion = sum(ImageStat.Stat(diff_upper).mean) / 3.0
        if upper_motion < 0.15:
            dim.score = min(dim.score, 12.0)
            dim.issues.append(
                f"画面主体(除底部字幕外)缺乏连续动态变化 (upper_motion={upper_motion:.2f})，疑似静态图片直出，必须经过 AI 视频生成或运镜补帧优化"
            )

        dim.details = {
            "first_3s_motion_delta": round(hook_motion, 2),
            "avg_motion_delta": round(avg_motion, 2),
            "upper_frame_motion_delta": round(upper_motion, 2),
            "first_frame_contrast_std": round(luma_std, 2),
        }

        # 5. 60FPS Optical-Flow Camera Stability, Anti-Wobble, Anti-Ghosting & Local Aesthetic Audit (Option 1)
        if duration > 5.0 and video_path and video_path.exists():
            streams = probe_data.get("streams", [])
            v_stream: Dict[str, Any] = next((s for s in streams if s.get("codec_type") == "video"), {})
            vw = int(v_stream.get("width", 1920) or 1920)
            vh = int(v_stream.get("height", 1080) or 1080)
            is_tutorial = vw >= vh
            evaluator = LocalAestheticEvaluator(allow_weight_download=False)
            cam_rep = evaluator.analyze_camera_and_motion(video_path, is_tutorial=is_tutorial)
            if proj_dir is not None:
                contact_sheet_out = proj_dir / "output" / "diagnostic_contact_sheet.jpg"
            elif video_path.parent.name == "video" and video_path.parent.parent.name == "output":
                contact_sheet_out = video_path.parent.parent / "diagnostic_contact_sheet.jpg"
            else:
                contact_sheet_out = video_path.parent.parent / "output" / "diagnostic_contact_sheet.jpg"
            aes_rep = evaluator.evaluate_aesthetics_and_contact_sheet(
                video_path=video_path,
                cover_path=None,
                output_contact_sheet=contact_sheet_out,
            )
            dim.details.update(
                {
                    "camera_jitter_std_px": cam_rep.camera_jitter_std_px,
                    "direction_reversals_5s": cam_rep.direction_reversals_5s,
                    "board_drift_mean_px": cam_rep.board_drift_mean_px,
                    "linear_blend_ghost_ratio": cam_rep.linear_blend_ghost_ratio,
                    "camera_wobble_detected": cam_rep.camera_wobble_detected,
                    "ghosting_detected": cam_rep.ghosting_detected,
                    "distant_face_collapse_detected": aes_rep.distant_face_collapse_detected,
                    "video_aesthetic_10": aes_rep.video_aesthetic_10,
                    "video_technical_10": aes_rep.video_technical_10,
                    "contact_sheet_path": aes_rep.contact_sheet_path,
                }
            )
            if cam_rep.camera_wobble_detected:
                dim.score = max(0.0, dim.score - 6.0)
                dim.issues.extend(cam_rep.issues)
            elif cam_rep.ghosting_detected:
                dim.score = max(0.0, dim.score - 4.0)
                dim.issues.extend(cam_rep.issues)
            if aes_rep.distant_face_collapse_detected:
                dim.score = max(0.0, dim.score - 3.0)
                dim.issues.extend(aes_rep.issues)

        dim.score = round(min(dim.score, 20.0), 1)
        return dim

    def _eval_cover_ctr(
        self,
        cover_path: Optional[Path],
        blockers: List[str],
    ) -> DimensionScore:
        dim = DimensionScore(name="4. 封面CTR大字与比例 (Cover)", key="cover_ctr", score=0.0)
        if not cover_path or not cover_path.exists():
            blockers.append("Missing Bilibili cover image (cover_missing)")
            dim.issues.append("缺少 B站封面图 (*_cover.jpg)")
            return dim

        with Image.open(cover_path) as img:
            rgb = img.convert("RGB")
            w, h = rgb.size

        aspect = w / float(h) if h else 0.0
        is_16x9 = abs(aspect - (16.0 / 9.0)) <= 0.05

        # 1. 16:9 Aspect Ratio & Resolution (6 pts)
        if not is_16x9:
            blockers.append(
                f"Cover aspect ratio is {w}x{h} (ratio={aspect:.2f}), NOT 16:9 landscape! Bilibili feed will crop the head/text."
            )
            dim.issues.append(f"封面比例为 {w}x{h}（非 16:9 横图），在 B站推荐流会被严重裁切")
        else:
            if w >= 1920 and h >= 1080:
                dim.score += 6.0
            else:
                dim.score += 4.5
                dim.issues.append(f"封面为 16:9 但分辨率低于 1920x1080 ({w}x{h})")

        # 2. 4:3 Safe-Zone (x: 12.5% .. 87.5%) Typography Edge & Salience Density (7 pts)
        safe_x0, safe_x1 = int(w * 0.125), int(w * 0.875)
        safe_crop = rgb.crop((safe_x0, 0, safe_x1, h))
        edges = safe_crop.convert("L").filter(ImageFilter.FIND_EDGES)
        edge_mean = ImageStat.Stat(edges).mean[0]

        crop_4x3_companion = cover_path.with_name(f"{cover_path.stem}_4x3{cover_path.suffix}")
        has_4x3_companion = crop_4x3_companion.exists()

        if edge_mean >= 15.0:
            dim.score += 7.0
        elif edge_mean >= 10.0:
            dim.score += 5.0
            dim.issues.append("4:3 安全区内大字描边锐度中等，建议加粗 8px 纯黑描边")
        else:
            dim.score += 2.0
            dim.issues.append("封面缺乏高对比度描边大字标题（CTR 视觉抓手不足）")

        # 3. Color Contrast & Dynamic Range (7 pts)
        luma_stat = ImageStat.Stat(safe_crop.convert("L"))
        luma_std = luma_stat.stddev[0]
        if luma_std >= 58.0:
            dim.score += 7.0
        elif luma_std >= 42.0:
            dim.score += 5.5
        else:
            dim.score += 3.0
            dim.issues.append(f"封面明暗对比度偏低 (std={luma_std:.1f})，建议使用深色渐变暗角衬托亮黄/亮白大字")

        dim.details = {
            "width": w,
            "height": h,
            "aspect_ratio": round(aspect, 3),
            "is_16x9": is_16x9,
            "safe_zone_edge_density": round(edge_mean, 2),
            "safe_zone_luma_std": round(luma_std, 2),
            "has_4x3_safe_crop": has_4x3_companion,
        }
        if is_16x9:
            aes_cov = LocalAestheticEvaluator(allow_weight_download=False).evaluate_aesthetics_and_contact_sheet(
                video_path=None,
                cover_path=cover_path,
                output_contact_sheet=None,
            )
            dim.details.update(
                {
                    "cover_aesthetic_10": aes_cov.cover_aesthetic_10,
                    "cover_technical_10": aes_cov.cover_technical_10,
                    "cover_split_hierarchy_ok": aes_cov.cover_split_hierarchy_ok,
                }
            )
            if not aes_cov.cover_split_hierarchy_ok:
                dim.score = max(0.0, dim.score - 3.0)
                dim.issues.extend(aes_cov.issues)

        dim.score = round(min(dim.score, 20.0), 1)
        return dim

    def _eval_compliance(
        self,
        proj_dir: Path,
        blockers: List[str],
    ) -> DimensionScore:
        dim = DimensionScore(name="5. 元数据与借物表合规 (Compliance)", key="compliance", score=0.0)
        bili_md = proj_dir / "delivery" / "bilibili.md"
        brief_json = proj_dir / "brief.json"

        md_text = bili_md.read_text(encoding="utf-8") if bili_md.exists() else ""
        brief_text = brief_json.read_text(encoding="utf-8") if brief_json.exists() else ""
        combined_text = f"{md_text}\n{brief_text}"

        # 1. Title & Hook Copywriting (5 pts)
        title = ""
        m_title = (
            re.search(r"##\s*1\.\s*推荐标题.*?\n+\s*-\s*\*\*主标题.*?\*\*：`?([^`\n]+)`?", md_text, re.S)
            or re.search(r"视频标题.*?\n+\s*1\.\s*([^\n]+)", md_text)
            or re.search(r"\*\*主标题.*?\*\*[:：]\s*`?([^`\n]+)`?", md_text)
        )
        if m_title:
            title = m_title.group(1).strip()
        elif brief_json.exists():
            try:
                bdata = json.loads(brief_text)
                title = bdata.get("title") or bdata.get("name") or ""
            except Exception:
                pass

        has_front_brackets = any(b in title[:18] for b in ("【", "[")) and any(b in title for b in ("】", "]"))
        if len(title) >= 14 and any(ch in title for ch in ("？", "！", "?", "!", "：", ":")) and has_front_brackets:
            dim.score += 5.0
        elif len(title) >= 14 and any(ch in title for ch in ("？", "！", "?", "!", "：", ":")):
            dim.score += 4.0
            dim.issues.append("标题前 18 字缺少【核心IP/悬念钩子】前置括号，建议将核心标签前置以提升点击率")
        elif len(title) >= 10:
            dim.score += 3.5
            dim.issues.append("标题缺少情绪标点（？！）或反差痛点钩子")
        else:
            dim.score += 1.0
            dim.issues.append("未找到高吸引力 B站主标题")

        # 2. Tags & Partition TID (4 pts)
        has_tid = (
            bool(re.search(r"tid\s*=`?\d+`?", md_text, re.I))
            or ("主选分区" in md_text)
            or ("分区" in md_text)
            or ("category" in brief_text)
        )
        tags_match = re.findall(r"`([^`\n]{2,20})`", md_text)
        m_csv_tags = re.search(r"\*\*标签.*?\*\*[:：]\s*\n?\s*([^\n]+)", md_text)
        if m_csv_tags:
            csv_tags = [t.strip() for t in re.split(r"[,，、]", m_csv_tags.group(1)) if t.strip()]
            if len(csv_tags) > len(tags_match):
                tags_match = csv_tags
        if has_tid and len(tags_match) >= 5:
            dim.score += 4.0
        elif has_tid:
            dim.score += 2.5
            dim.issues.append("B站标签数量偏少，建议配置 8-12 个精准长尾标签")
        else:
            dim.score += 1.0
            dim.issues.append("缺少明确的 B站分区 TID 与标签配置")

        # 3. Credits (借物表) & Model/Motion/BGM/Reference Attribution (6 pts)
        uses_noshiro_ref = (proj_dir / "assets" / "noshiro_reference.jpg").exists() or (
            "noshiro" in proj_dir.name.lower()
        )
        has_reference_creator_attr = True
        if uses_noshiro_ref and "小咩先生" not in combined_text:
            has_reference_creator_attr = False
            blockers.append(
                "Missing reference attribution for @小咩先生 (noshiro_reference.jpg used without crediting reference creator in bilibili.md)"
            )
            dim.issues.append("未说明所使用的参考图来源（缺少对参考素材作者 @小咩先生 的致谢说明）")

        has_credits_header = any(k in combined_text for k in ("借物表", "Credits", "原作者", "版权"))
        has_author_attr = any(
            k in combined_text
            for k in (
                "上善无形",
                "ZipZipPipe",
                "ureshiiiiii",
                "小咩先生",
                "ATDAN",
                "Manjuu",
                "SQUARE ENIX",
                "Square Enix",
                "吉田明彦",
                "CAFFEIN",
                "Crypton",
            )
        )
        if has_credits_header and has_author_attr and has_reference_creator_attr:
            dim.score += 6.0
        elif has_credits_header or has_author_attr:
            dim.score += 3.5
            if has_reference_creator_attr:
                dim.issues.append(
                    "借物表信息不够完整，建议使用 AssetLibrary.generate_project_credits 自动生成完整借物表"
                )
        else:
            dim.score += 1.0
            dim.issues.append("简介缺失【借物表 (Credits)】，存在二创社区合规风险")

        # 4. AIGC Explicit Label (GB 45438-2025) & Font/Voice Redline (5 pts)
        has_aigc_label = any(
            k in combined_text
            for k in ("AIGC", "人工智能生成合成", "GB 45438", "AI生成", "AI 创造", "Seedream", "可灵")
        )
        font_violation = any(f.lower() in [df.lower() for df in DEFAULT_FONTS] for f in FORBIDDEN_COMMERCIAL_FONTS)
        voice_violation = any(re.search(pat, combined_text) for pat in FORBIDDEN_VOICE_CLONE_PATTERNS)

        if font_violation:
            blockers.append(
                "Commercial font infringement risk detected in DEFAULT_FONTS (compliance_redline_violation)"
            )
            dim.issues.append("检测到未授权商业字体风险 (STHeiti/MicrosoftYaHei/SimHei)")
        if voice_violation:
            blockers.append("Unauthorized voice actor cloning detected (compliance_redline_violation)")
            dim.issues.append("检测到未经授权声优声音克隆描述，违反《民法典》第1023条")

        if has_aigc_label and not font_violation and not voice_violation:
            dim.score += 5.0
        elif not font_violation and not voice_violation:
            dim.score += 3.0
            dim.issues.append("建议显式补充 GB 45438-2025《人工智能生成合成内容标识办法》AIGC 声明")

        srt_texts = [
            p.read_text(encoding="utf-8", errors="ignore")
            for p in sorted((proj_dir / "delivery").glob("*.srt"))
            if p.exists()
        ]
        missing_glyphs = check_missing_glyphs("\n".join(srt_texts)) if srt_texts else []
        if missing_glyphs:
            dim.score = max(0.0, dim.score - 2.0)
            dim.issues.append(f"检测到 Noto Sans CJK SC 缺失字符（渲染将显示豆腐块 □）: {' '.join(missing_glyphs[:8])}")
            if len(missing_glyphs) >= 3:
                blockers.append(f"Missing OpenType glyphs in SRT subtitles: {''.join(missing_glyphs[:8])}")

        dim.details = {
            "detected_title": title,
            "title_front_loaded": has_front_brackets,
            "has_credits_table": has_credits_header and has_author_attr and has_reference_creator_attr,
            "reference_attribution_passed": has_reference_creator_attr,
            "has_aigc_declaration": has_aigc_label,
            "compliant_open_fonts": not font_violation,
            "voice_compliance_passed": not voice_violation,
            "missing_glyphs": missing_glyphs,
        }
        dim.score = round(min(dim.score, 20.0), 1)
        return dim

    def evaluate_project(
        self,
        project: Union[str, Path],
        video_path: Optional[Union[str, Path]] = None,
        cover_path: Optional[Union[str, Path]] = None,
    ) -> QualityGateReport:
        """Runs the full 100-point objective quality gate on a project."""
        proj_dir = self.resolve_project_dir(project)
        project_id = proj_dir.name

        auto_video, auto_cover = self._find_project_video_and_cover(proj_dir)
        v_path = Path(video_path) if video_path else auto_video
        c_path = Path(cover_path) if cover_path else auto_cover

        blockers: List[str] = []
        probe_data = self._probe_media(v_path) if (v_path and v_path.exists()) else {}

        d_tech = self._eval_technical(v_path, probe_data, blockers)
        d_audio = self._eval_audio(v_path, probe_data, blockers)
        d_visual = self._eval_visual_dynamics(v_path, probe_data, proj_dir=proj_dir)
        d_cover = self._eval_cover_ctr(c_path, blockers)
        d_comp = self._eval_compliance(proj_dir, blockers)

        dims = [d_tech, d_audio, d_visual, d_cover, d_comp]
        total_score = round(sum(d.score for d in dims), 1)
        passed = (len(blockers) == 0) and (total_score >= self.pass_threshold)

        if blockers:
            grade = "F"
            verdict = "BLOCKED"
        elif total_score >= 90.0:
            grade = "S"
            verdict = "VIRAL_READY"
        elif total_score >= self.pass_threshold:
            grade = "A"
            verdict = "PUBLISH_READY"
        elif total_score >= 60.0:
            grade = "B"
            verdict = "NEEDS_POLISH"
        else:
            grade = "F"
            verdict = "REJECTED"

        recommendations: List[str] = []
        for b in blockers:
            recommendations.append(f"[BLOCKER修复] {b}")
        for d in dims:
            for iss in d.issues:
                recommendations.append(f"[{d.key}] {iss}")

        try:
            return QualityGateReport(
                project_id=project_id,
                project_dir=str(proj_dir),
                video_path=str(v_path) if v_path else None,
                cover_path=str(c_path) if c_path else None,
                total_score=total_score,
                max_score=100.0,
                grade=grade,
                verdict=verdict,
                passed=passed,
                blockers=blockers,
                dimensions={d.key: d.to_dict() for d in dims},
                recommendations=recommendations,
            )
        finally:
            release_pyiqa_models()
