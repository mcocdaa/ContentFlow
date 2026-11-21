#!/usr/bin/env python3
"""Runnable CLI launcher for the Dual-AI Interactive Livestream MVP (`DeepSeek 蓝色大肥鱼 × Gemini娘`).

Examples:
    # Offline rehearsal for OBS Browser Source (zero API keys required)
    ./.venv/bin/python scripts/launch_live_mvp.py --mode mock --host 127.0.0.1 --port 8765

    # Bounded rehearsal with highlight JSONL + ffmpeg 60-90s clip plan export
    ./.venv/bin/python scripts/launch_live_mvp.py --mode mock --duration-sec 15 \
        --record-highlights output/live_highlights.jsonl

    # Connect to a real Bilibili live room (anonymous guest danmaku reader, zero cookies)
    ./.venv/bin/python scripts/launch_live_mvp.py --mode live --room-id 12345678 \
        --record-highlights output/live_highlights.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path
from typing import Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.live_studio.danmaku import BilibiliDanmakuClient, MockDanmakuSource
from core.live_studio.director import DualAILiveDirector, HighlightTracker
from core.live_studio.safety import AI_DISCLOSURE_BANNER
from core.live_studio.stage_server import DanmakuEventSource, LiveStageRuntime, StageServer

logger = logging.getLogger("contentflow.live_mvp")


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Launch ContentFlow Dual-AI Interactive Livestream MVP (DeepSeek 蓝色大肥鱼 × Gemini娘)",
    )
    parser.add_argument(
        "--mode",
        choices=("mock", "live"),
        default="mock",
        help="Run with offline mock danmaku (`mock`) or real Bilibili live WebSocket (`live`).",
    )
    parser.add_argument(
        "--room-id",
        type=int,
        default=None,
        help="Bilibili live room ID (required when `--mode live`).",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Stage overlay HTTP/WebSocket bind host (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Stage overlay HTTP/WebSocket bind port (default: 8765).",
    )
    parser.add_argument(
        "--record-highlights",
        type=str,
        default=None,
        help="Optional JSONL path to record highlight timestamps and export an adjacent ffmpeg clip plan.",
    )
    parser.add_argument(
        "--duration-sec",
        type=float,
        default=None,
        help="Optional bounded runtime in seconds (useful for OBS rehearsals and smoke tests).",
    )
    parser.add_argument(
        "--idle-interval-sec",
        type=float,
        default=5.5,
        help="Seconds to wait before triggering autonomous dual-AI banter when queue is idle (default: 5.5).",
    )
    parser.add_argument(
        "--mock-interval-sec",
        type=float,
        default=4.0,
        help="Seconds between synthetic danmaku/gift events in `--mode mock` (default: 4.0).",
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
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
        help="Console log verbosity (default: INFO).",
    )
    return parser


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.mode == "live" and (args.room_id is None or args.room_id <= 0):
        parser.error("--room-id must be a positive integer when --mode live is selected.")
    if args.duration_sec is not None and args.duration_sec <= 0:
        parser.error("--duration-sec must be positive when provided.")
    return args


async def run_live_mvp(args: argparse.Namespace) -> dict[str, object]:
    """Assemble and run the Dual-AI Livestream runtime, returning a session summary."""
    avail_mib = get_available_ram_mib()
    if avail_mib is not None and avail_mib < 5000:
        logger.warning(
            "Low available RAM detected (%d MiB < 5000 MiB). Avoid running local video rendering during live broadcast.",
            avail_mib,
        )

    highlights_path = Path(args.record_highlights) if args.record_highlights else None
    tracker = HighlightTracker(jsonl_path=highlights_path)
    director = DualAILiveDirector(
        highlight_tracker=tracker,
        follower_count=args.follower_count,
        follower_goal=args.follower_goal,
    )
    stage_server = StageServer(
        director=director,
        mode=args.mode,
        room_id=args.room_id,
    )

    source: DanmakuEventSource
    if args.mode == "live":
        assert args.room_id is not None
        source = BilibiliDanmakuClient(room_id=args.room_id)
    else:
        source = MockDanmakuSource(interval_sec=args.mock_interval_sec)

    runtime = LiveStageRuntime(
        stage_server=stage_server,
        danmaku_source=source,
        host=args.host,
        port=args.port,
        idle_interval_sec=args.idle_interval_sec,
    )

    loop = asyncio.get_running_loop()
    installed_signals: list[signal.Signals] = []
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, runtime.request_stop)
            installed_signals.append(sig)
        except (NotImplementedError, RuntimeError):
            pass

    await runtime.start()
    bound_url = f"http://{args.host}:{runtime.bound_port}/"
    logger.info(
        "Dual-AI Livestream MVP running at %s (mode=%s, llm=%s)", bound_url, args.mode, director.responder.backend_name
    )
    logger.info("OBS Browser Source URL: %s | Status API: %sapi/status", bound_url, bound_url)
    logger.info("Compliance Banner: %s", AI_DISCLOSURE_BANNER)

    try:
        await runtime.wait_until_stopped(duration_sec=args.duration_sec)
    finally:
        for sig in installed_signals:
            try:
                loop.remove_signal_handler(sig)
            except (NotImplementedError, RuntimeError):
                pass
        await runtime.stop()

    clip_plan_path: Optional[Path] = None
    clip_plan_count = 0
    if highlights_path is not None:
        clip_plan_path = highlights_path.with_name(f"{highlights_path.stem}_ffmpeg_clip_plan.json")
        plan = tracker.save_clip_plan(clip_plan_path)
        clip_plan_count = int(plan["planned_clip_count"])
        logger.info(
            "Exported %d highlights to %s and %d ffmpeg clip commands to %s",
            len(tracker.moments),
            highlights_path,
            clip_plan_count,
            clip_plan_path,
        )

    return {
        "mode": args.mode,
        "room_id": args.room_id,
        "bound_port": runtime.bound_port,
        "turns_emitted": len(director.history),
        "danmaku_count": director.danmaku_count,
        "gift_count": director.gift_count,
        "highlights_recorded": len(tracker.moments),
        "clip_plan_path": str(clip_plan_path) if clip_plan_path else None,
        "clip_plan_count": clip_plan_count,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    summary = asyncio.run(run_live_mvp(args))
    logger.info(
        "Session finished: turns=%s, danmaku=%s, gifts=%s, highlights=%s",
        summary["turns_emitted"],
        summary["danmaku_count"],
        summary["gift_count"],
        summary["highlights_recorded"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
