#!/usr/bin/env python3
"""100% Headless Zero-Mic Autonomous Bilibili Livestream CLI Launcher.

Streams a 1920x1080 @ 30 FPS Pillow+NumPy Dual/Trio-AI stage (`DeepSeek 蓝色大肥鱼 × 弱音ハク × Gemini娘`)
paired with 100% synthetic 48 kHz stereo `s16le` audio (`edge-tts` + ducked lo-fi ambient BGM)
directly into a single dual-pipe `ffmpeg` encoder — with ZERO microphone or hardware audio input
and ZERO PII / RTMP stream key exposure.

Examples:
    # 15-second headless zero-mic trio dry stream preview to local MP4
    ./.venv/bin/python scripts/launch_headless_live.py \
        --mode dry-stream --cast trio --duration-sec 15 \
        --output-mp4 /tmp/trio_live_preview.mp4 \
        --frame-dump-path /tmp/trio_live_stage_preview.png

    # Autonomous Bilibili go-live (automatically calls stopLive in finally:)
    ./.venv/bin/python scripts/launch_headless_live.py \
        --mode go-live --cast trio --duration-sec 3600 --area-id 1062 \
        --poll-topic "下期主控弹幕公投" \
        --poll-options "大肥鱼,Gemini娘,弱音大姐头" \
        --record-dir output/live_sessions/trio_show
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import signal
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.live_studio.bilibili_live_api import (
    DEFAULT_LIVE_AREA_V2,
    BilibiliLiveController,
    scrub_rtmp_secrets,
)
from core.live_studio.director import (
    DEFAULT_POLL_OPTIONS,
    DEFAULT_POLL_TOPIC,
    DUAL_CAST,
    TRIO_CAST,
    DualAILiveDirector,
    HighlightTracker,
    SpeakerId,
)
from core.live_studio.headless_streamer import (
    DEFAULT_FPS,
    HeadlessLiveStreamer,
    HeadlessStageRenderer,
    StatusCallback,
    SyntheticAudioMixer,
)

logger = logging.getLogger("contentflow.headless_live")

DEFAULT_SHOW_TITLE = "【铁三角AI合租直播】大肥鱼×Gemini娘×弱音现场弹幕公投！15粉冲1000粉"
_POLL_SPLIT_RE = re.compile(r"[,，|/]+")


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


def parse_poll_options(raw: str) -> Tuple[str, ...]:
    """Parse 2-3 comma/slash-separated poll option labels with sanitization."""
    parts = [
        scrub_rtmp_secrets(token).replace("@", "").strip()[:24]
        for token in _POLL_SPLIT_RE.split(raw or "")
        if token.strip()
    ]
    cleaned = tuple(p for p in parts if p)
    if len(cleaned) < 2 or len(cleaned) > 3:
        raise ValueError("--poll-options must specify 2 or 3 non-empty options separated by commas.")
    return cleaned


def resolve_cast(cast_mode: str) -> Tuple[SpeakerId, ...]:
    """Map `--cast` CLI value (`dual` / `trio`) to canonical speaker tuple."""
    return DUAL_CAST if cast_mode == "dual" else TRIO_CAST


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
        "--cast",
        choices=("dual", "trio"),
        default="trio",
        help="Broadcast lineup: `trio` (大肥鱼+Gemini娘+弱音ハク, default) or `dual` (大肥鱼+Gemini娘).",
    )
    parser.add_argument(
        "--poll-topic",
        type=str,
        default=DEFAULT_POLL_TOPIC,
        help="Live danmaku poll topic displayed in the right-side widget.",
    )
    parser.add_argument(
        "--poll-options",
        type=str,
        default=",".join(DEFAULT_POLL_OPTIONS),
        help="Comma-separated 2-3 option labels for 扣1/扣2/扣3 danmaku voting.",
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
    try:
        args.parsed_poll_options = parse_poll_options(args.poll_options)
    except ValueError as exc:
        parser.error(str(exc))
    args.resolved_cast = resolve_cast(args.cast)
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

    cast_tuple: Tuple[SpeakerId, ...] = getattr(args, "resolved_cast", resolve_cast(getattr(args, "cast", "trio")))
    poll_options: Tuple[str, ...] = getattr(
        args,
        "parsed_poll_options",
        parse_poll_options(getattr(args, "poll_options", ",".join(DEFAULT_POLL_OPTIONS))),
    )
    poll_topic: str = str(getattr(args, "poll_topic", DEFAULT_POLL_TOPIC) or DEFAULT_POLL_TOPIC)

    record_dir = Path(args.record_dir) if args.record_dir else None
    hl_jsonl = (record_dir / "live_highlights.jsonl") if record_dir is not None else None
    tracker = HighlightTracker(jsonl_path=hl_jsonl)
    director = DualAILiveDirector(
        highlight_tracker=tracker,
        follower_count=args.follower_count,
        follower_goal=args.follower_goal,
        cast=cast_tuple,
        poll_topic=poll_topic,
        poll_options=poll_options,
    )
    renderer = HeadlessStageRenderer(
        fps=args.fps,
        follower_count=args.follower_count,
        follower_goal=args.follower_goal,
        show_title=args.title,
        cast=cast_tuple,
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
