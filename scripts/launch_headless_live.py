#!/usr/bin/env python3
"""100% Headless Zero-Mic Autonomous Bilibili Livestream CLI Launcher.

Streams a 1920x1080 @ 30 FPS Pillow+NumPy Dual-AI stage (`DeepSeek 蓝色大肥鱼 × Gemini娘`)
paired with 100% synthetic 48 kHz stereo `s16le` audio (`edge-tts` + ducked lo-fi ambient BGM)
directly into a single dual-pipe `ffmpeg` encoder — with ZERO microphone or hardware audio input
and ZERO PII / RTMP stream key exposure.

Examples:
    # 20-second headless zero-mic dry stream proof to local MP4
    ./.venv/bin/python scripts/launch_headless_live.py \
        --mode dry-stream --duration-sec 20 \
        --output-mp4 /tmp/k8_dry_stream_test.mp4 \
        --frame-dump-path /tmp/k8_dry_stream_frame.png

    # Autonomous Bilibili go-live (automatically calls stopLive in finally:)
    ./.venv/bin/python scripts/launch_headless_live.py \
        --mode go-live --duration-sec 600 --area-id 1062 \
        --title "【双AI合租直播】大肥鱼×Gemini娘现场策划018期！15粉冲1000粉" \
        --record-dir output/live_sessions/ep018
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.live_studio.bilibili_live_api import (
    DEFAULT_LIVE_AREA_V2,
    BilibiliLiveController,
    scrub_rtmp_secrets,
)
from core.live_studio.director import DualAILiveDirector, HighlightTracker
from core.live_studio.headless_streamer import (
    DEFAULT_FPS,
    HeadlessLiveStreamer,
    HeadlessStageRenderer,
    StatusCallback,
    SyntheticAudioMixer,
)

logger = logging.getLogger("contentflow.headless_live")

DEFAULT_SHOW_TITLE = "【双AI合租直播】大肥鱼×Gemini娘现场策划018期！15粉冲1000粉"


def get_available_ram_mib() -> Optional[int]:
    """Read Linux `MemAvailable` from `/proc/meminfo` without spawning subprocesses."""
    meminfo = Path("/proc/meminfo")
    if not meminfo.is_file():
        return None
    try:
        for line in meminfo.read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                parts = line.split()
                if len(parts) >= 2:
                    return int(parts[1]) // 1024
    except Exception:
        return None
    return None


def _sanitize_payload(obj: Any) -> Any:
    """Recursively scrub any accidental RTMP tokens, room IDs, or PII before printing status JSON."""
    if isinstance(obj, str):
        return scrub_rtmp_secrets(obj)
    if isinstance(obj, dict):
        return {str(k): _sanitize_payload(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_payload(item) for item in obj]
    return obj


def emit_status_line(tag: str, payload: Dict[str, Any]) -> str:
    """Emit a single-line grep-friendly JSON status event to stdout with zero PII/secrets."""
    safe = _sanitize_payload(payload)
    line = f"{tag} {json.dumps(safe, ensure_ascii=False, separators=(',', ':'))}"
    print(line, flush=True)
    return line


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Launch ContentFlow 100% Headless Zero-Mic Autonomous Bilibili Livestream Engine",
    )
    parser.add_argument(
        "--mode",
        choices=("dry-stream", "go-live"),
        default="dry-stream",
        help="Run local MP4 verification (`dry-stream`) or live Bilibili RTMP broadcast (`go-live`).",
    )
    parser.add_argument(
        "--duration-sec",
        type=float,
        default=600.0,
        help="Broadcast duration in seconds before clean automatic shutdown (default: 600).",
    )
    parser.add_argument(
        "--area-id",
        type=int,
        default=DEFAULT_LIVE_AREA_V2,
        help="Bilibili live area_v2 partition ID (default: 1062; virtual daily: 371).",
    )
    parser.add_argument(
        "--title",
        type=str,
        default=DEFAULT_SHOW_TITLE,
        help="Live room broadcast title (sanitized, zero @ mentions).",
    )
    parser.add_argument(
        "--output-mp4",
        type=str,
        default=None,
        help="Output MP4 path for `--mode dry-stream` (default: output/live_dry_stream.mp4).",
    )
    parser.add_argument(
        "--record-dir",
        type=str,
        default=None,
        help="Optional directory for highlight JSONL, ffmpeg clip plan JSON, and local go-live `.mkv` copy.",
    )
    parser.add_argument(
        "--cover-path",
        type=str,
        default=None,
        help="Optional live room cover image path for non-fatal pre-live upload.",
    )
    parser.add_argument(
        "--bgm-path",
        type=str,
        default=None,
        help="Optional BGM audio path decoded via ffmpeg (defaults to built-in synthetic lo-fi pad).",
    )
    parser.add_argument(
        "--follower-count",
        type=int,
        default=15,
        help="Current channel follower count shown on the milestone bar (default: 15).",
    )
    parser.add_argument(
        "--follower-goal",
        type=int,
        default=1000,
        help="Target channel follower milestone shown on the milestone bar (default: 1000).",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=DEFAULT_FPS,
        help="Output video framerate (default: 30).",
    )
    parser.add_argument(
        "--frame-dump-path",
        type=str,
        default=None,
        help="Optional PNG path to capture a mid-stream stage frame for visual inspection.",
    )
    parser.add_argument(
        "--no-edge-tts",
        action="store_true",
        help="Force pure-NumPy melodic synthetic voice fallback without contacting edge-tts.",
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
        help="Console logging verbosity (default: INFO).",
    )
    return parser


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.duration_sec <= 0:
        parser.error("--duration-sec must be positive.")
    if args.area_id <= 0:
        parser.error("--area-id must be a positive integer.")
    if args.fps <= 0 or args.fps > 60:
        parser.error("--fps must be between 1 and 60.")
    if args.follower_count < 0:
        parser.error("--follower-count must be non-negative.")
    if args.follower_goal <= 0:
        parser.error("--follower-goal must be positive.")
    return args


async def run_headless_live(
    args: argparse.Namespace,
    *,
    controller: Optional[BilibiliLiveController] = None,
    status_callback: Optional[StatusCallback] = None,
) -> Dict[str, Any]:
    """Assemble and execute the headless zero-mic livestream session."""
    avail_mib = get_available_ram_mib()
    if avail_mib is not None and avail_mib < 5000:
        logger.warning(
            "Low available RAM detected (%d MiB < 5000 MiB). Avoid concurrent local rendering.",
            avail_mib,
        )

    record_dir = Path(args.record_dir) if args.record_dir else None
    hl_jsonl = (record_dir / "live_highlights.jsonl") if record_dir is not None else None
    tracker = HighlightTracker(jsonl_path=hl_jsonl)
    director = DualAILiveDirector(
        highlight_tracker=tracker,
        follower_count=args.follower_count,
        follower_goal=args.follower_goal,
    )
    renderer = HeadlessStageRenderer(
        fps=args.fps,
        follower_count=args.follower_count,
        follower_goal=args.follower_goal,
        show_title=args.title,
    )
    mixer = SyntheticAudioMixer(
        fps=args.fps,
        bgm_path=Path(args.bgm_path) if args.bgm_path else None,
        use_edge_tts=not bool(args.no_edge_tts),
    )

    cb = status_callback if status_callback is not None else emit_status_line
    streamer = HeadlessLiveStreamer(
        renderer=renderer,
        audio_mixer=mixer,
        director=director,
        controller=controller,
        fps=args.fps,
        status_callback=cb,
    )

    loop = asyncio.get_running_loop()
    installed_signals: list[signal.Signals] = []
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, streamer.request_stop)
            installed_signals.append(sig)
        except (NotImplementedError, RuntimeError):
            pass

    frame_dump = Path(args.frame_dump_path) if args.frame_dump_path else None

    try:
        if args.mode == "dry-stream":
            out_mp4 = Path(args.output_mp4) if args.output_mp4 else (REPO_ROOT / "output" / "live_dry_stream.mp4")
            return await streamer.run_dry_stream(
                output_mp4=out_mp4,
                duration_sec=args.duration_sec,
                record_dir=record_dir,
                frame_dump_path=frame_dump,
            )

        return await streamer.run_go_live(
            duration_sec=args.duration_sec,
            area_id=args.area_id,
            title=args.title,
            cover_path=Path(args.cover_path) if args.cover_path else None,
            record_dir=record_dir,
            frame_dump_path=frame_dump,
        )
    finally:
        for sig in installed_signals:
            try:
                loop.remove_signal_handler(sig)
            except (NotImplementedError, RuntimeError):
                pass


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )
    try:
        result = asyncio.run(run_headless_live(args))
    except Exception as exc:
        emit_status_line("LIVE_ERROR", {"ok": False, "error": scrub_rtmp_secrets(str(exc))})
        return 1

    if result.get("status") == "face_auth_required":
        return 2
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
