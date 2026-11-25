#!/usr/bin/env python3
"""Zero-dependency CLI control bridge for ContentFlow's live 2D Interactive Workshop (`--stage-mode world`).

Enables either a hands-on AI coding assistant (zero external API keys required) or a future 24/7
autonomous agent to inspect live viewer danmaku/telemetry (`status`, `inbox`) and inject real-time
work logs, world events, spoken host lines, or graceful shutdown (`work-log`, `world-action`,
`speak`, `stop`) with strict PII & `@mention` scrubbing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.live_studio.safety import redact_pii

WORLD_ACTIONS: tuple[str, ...] = (
    "spawn_worker",
    "build_upgrade",
    "trigger_event",
    "resolve_event",
    "add_time",
    "accept_suggestion",
    "announce",
)


def _scrub_clean(text: str) -> str:
    return redact_pii(str(text or "")).replace("@", "").strip()


def _append_command(record_dir: Path, payload: Dict[str, Any]) -> Path:
    record_dir.mkdir(parents=True, exist_ok=True)
    cmd_path = record_dir / "agent_commands.jsonl"
    with cmd_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return cmd_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Live control bridge for ContentFlow world livestream mode")
    parser.add_argument(
        "--record-dir",
        type=str,
        default="output/live_world_01",
        help="Livestream session record directory holding world_state.json / agent_commands.jsonl",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Read current world_state.json snapshot")

    p_inbox = sub.add_parser("inbox", help="Read recent sanitized lines from danmaku_inbox.jsonl")
    p_inbox.add_argument("--tail", type=int, default=20, help="Number of trailing inbox entries to print")

    p_speak = sub.add_parser("speak", help="Inject a high-priority spoken line via a live AI host")
    p_speak.add_argument("--speaker", choices=("dafeiyu", "gemini", "yowane"), default="dafeiyu")
    p_speak.add_argument("--text", type=str, required=True)
    p_speak.add_argument("--mood", type=str, default="lively")

    p_log = sub.add_parser("work-log", help="Update real-time Agent Workbench task, stage, and log")
    p_log.add_argument("--tag", type=str, default="AGENT")
    p_log.add_argument("--text", type=str, required=True)
    p_log.add_argument("--task", type=str, default=None)
    p_log.add_argument("--stage", type=int, default=None, choices=(0, 1, 2, 3))

    p_act = sub.add_parser("world-action", help="Dispatch a world simulation action")
    p_act.add_argument("--action", choices=WORLD_ACTIONS, required=True)
    p_act.add_argument("--payload-json", type=str, default="{}")

    sub.add_parser("stop", help="Request clean live stream shutdown and StopLiveData collection")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    record_dir = Path(args.record_dir)

    if args.command == "status":
        state_path = record_dir / "world_state.json"
        if not state_path.is_file():
            print(
                json.dumps({"ok": False, "error": "world_state_not_found", "path": str(state_path)}, ensure_ascii=False)
            )
            return 1
        print(state_path.read_text(encoding="utf-8"))
        return 0

    if args.command == "inbox":
        inbox_path = record_dir / "danmaku_inbox.jsonl"
        if not inbox_path.is_file():
            print(json.dumps({"ok": True, "count": 0, "events": []}, ensure_ascii=False))
            return 0
        lines = [ln.strip() for ln in inbox_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        tail_n = max(1, int(args.tail))
        events = []
        for ln in lines[-tail_n:]:
            try:
                events.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
        print(json.dumps({"ok": True, "count": len(events), "events": events}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "speak":
        speak_payload: Dict[str, Any] = {
            "cmd": "speak",
            "speaker": args.speaker,
            "text": _scrub_clean(args.text),
            "mood": _scrub_clean(args.mood) or "lively",
        }
        cmd_path = _append_command(record_dir, speak_payload)
        print(json.dumps({"ok": True, "queued": speak_payload, "cmd_path": str(cmd_path)}, ensure_ascii=False))
        return 0

    if args.command == "work-log":
        work_payload: Dict[str, Any] = {
            "cmd": "work_log",
            "tag": _scrub_clean(args.tag)[:8] or "AGENT",
            "text": _scrub_clean(args.text),
        }
        if args.task is not None:
            work_payload["task"] = _scrub_clean(args.task)
        if args.stage is not None:
            work_payload["stage"] = int(args.stage)
        cmd_path = _append_command(record_dir, work_payload)
        print(json.dumps({"ok": True, "queued": work_payload, "cmd_path": str(cmd_path)}, ensure_ascii=False))
        return 0

    if args.command == "world-action":
        try:
            extra = json.loads(args.payload_json or "{}")
            if not isinstance(extra, dict):
                raise ValueError("payload-json must decode to an object")
        except Exception as exc:
            print(json.dumps({"ok": False, "error": f"invalid_payload_json: {exc}"}, ensure_ascii=False))
            return 2
        act_payload: Dict[str, Any] = {"cmd": "world_action", "action": args.action}
        for k, v in extra.items():
            act_payload[str(k)] = _scrub_clean(v) if isinstance(v, str) else v
        cmd_path = _append_command(record_dir, act_payload)
        print(json.dumps({"ok": True, "queued": act_payload, "cmd_path": str(cmd_path)}, ensure_ascii=False))
        return 0

    if args.command == "stop":
        stop_payload: Dict[str, Any] = {"cmd": "stop"}
        cmd_path = _append_command(record_dir, stop_payload)
        print(json.dumps({"ok": True, "queued": stop_payload, "cmd_path": str(cmd_path)}, ensure_ascii=False))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
