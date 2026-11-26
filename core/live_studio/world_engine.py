"""Living 2D Interactive Workshop World, Viewer Memory & Zero-API-Key Agent Control Bridge.

Combines high-retention livestream mechanics observed on live Bilibili AI rooms:
- Continuous 2D workshop/town simulation with upgrade levels, resources, and a visible survival countdown.
- Zero-barrier 3-second danmaku commands (`开工`, `写代码`, `修Bug`, `投喂`, `建议 xxx`) that spawn and animate
  named pixel avatars inside the world with immediate floating rewards and a live contributor leaderboard.
- Persistent `ViewerMemoryStore` (zero raw UIDs — keyed strictly by sanitized alias) recognizing returning
  regulars and special supporter badges (`白米饭供应商`, `建议采纳官`).
- Real-time `AI Agent 实时工作台` showing the active task, 4-stage pipeline, and scrolling execution log
  controllable live by either a human-supervised AI coding agent (zero API key needed) or a 24/7 LLM agent
  via `agent_commands.jsonl` / `world_state.json`.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import math
import os
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Deque, Dict, Final, List, Optional, Sequence, Tuple

import httpx
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from core.live_studio.danmaku import DanmakuEvent
from core.live_studio.director import (
    DEFAULT_LLM_BASE_URL,
    DEFAULT_LLM_MODEL,
    PERSONAS,
    TRIO_CAST,
    PersonaTurn,
    SpeakerId,
    format_world_context_summary,
)
from core.live_studio.headless_streamer import (
    CHARACTER_CANONICAL_RELS,
    CHARACTER_CUTOUT_RELS,
    DEFAULT_FPS,
    DEFAULT_STUDIO_BG_REL,
    MOOD_LABELS,
    SPEAKER_ACCENT_RGB,
    SPEAKER_EQ_LIGHT_RGB,
    SPEAKER_EQ_PEAK_RGB,
    STAGE_HEIGHT,
    STAGE_WIDTH,
    _discover_git_main_repo_root,
    _load_font,
    _wrap_text_by_width,
    resolve_cjk_font_path,
)
from core.live_studio.safety import AI_DISCLOSURE_BANNER, LiveComplianceGuard, redact_pii

logger = logging.getLogger(__name__)

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent.parent
DEFAULT_MEMORY_PATH: Final[Path] = REPO_ROOT / "output" / "live_world" / "viewer_memory.json"

WORLD_WIDTH: Final[int] = 1286
WORLD_HEIGHT: Final[int] = 536
MAP_LEFT_WIDTH: Final[int] = 744
MAP_MIN_X: Final[float] = 68.0
MAP_MAX_X: Final[float] = 712.0
MONITOR_X: Final[int] = 754
MONITOR_Y: Final[int] = 78
MONITOR_W: Final[int] = 518
MONITOR_H: Final[int] = 446
CORRIDOR_Y: Final[float] = 282.0
CRISIS_COOLDOWN_SEC: Final[float] = 300.0

PIPELINE_STAGES: Final[Tuple[str, ...]] = ("① 热点海", "② 抓角色", "③ 可灵房", "④ 剪辑厅")

LEVEL_THRESHOLDS: Final[Tuple[Tuple[int, int, str], ...]] = (
    (1, 0, "破旧电饭煲工位"),
    (2, 100, "霓虹算力工坊"),
    (3, 280, "全息弹幕广场"),
    (4, 600, "千粉庆典塔"),
)

STATIONS: Final[Dict[str, Tuple[int, int, str, Tuple[int, int, int]]]] = {
    "互联网热点海": (196, 168, "抓热榜 · 选下期题材", (14, 165, 233)),
    "角色抓捕屋": (544, 168, "抓铁三角 · 锁立绘", (236, 72, 153)),
    "可灵炼丹房": (196, 396, "提可灵API · 炼关键帧", (245, 158, 11)),
    "剪辑放映厅": (544, 396, "60帧剪辑 · 看样片", (139, 92, 246)),
}

PRODUCTION_STAGE_TO_STATION: Final[Dict[str, str]] = {
    "internet_sea": "互联网热点海",
    "character_catch": "角色抓捕屋",
    "kling_forge": "可灵炼丹房",
    "edit_theater": "剪辑放映厅",
}

PRODUCTION_STAGE_META: Final[Dict[str, Tuple[str, int, str, str]]] = {
    "internet_sea": ("互联网热点海", 0, "抓热榜 · 选下期题材", "poll"),
    "character_catch": ("角色抓捕屋", 1, "抓铁三角 · 锁立绘", "preview"),
    "kling_forge": ("可灵炼丹房", 2, "提可灵API · 炼关键帧", "preview"),
    "edit_theater": ("剪辑放映厅", 3, "60帧剪辑 · 看样片", "preview"),
}

_POLL_OPTION_COLORS: Final[Dict[str, Tuple[int, int, int]]] = {
    "A": (14, 165, 233),
    "B": (236, 72, 153),
    "C": (139, 92, 246),
}

_DEFAULT_POLL_OPTIONS: Final[Tuple[Tuple[str, str], ...]] = (
    ("A", "AI组团反向面试人类老板"),
    ("B", "AI厨神赛！电饭煲翻车记"),
    ("C", "AI运动会：猫娘被激光硬控"),
)

_SUGGESTION_PREFIX_RE: Final[re.Pattern[str]] = re.compile(r"^\s*(?:建议|提案|需求|点子)[:：\s]*")
_TOPIC_VOTE_STRIP_CHARS: Final[str] = " \t\r\n！!。.，,、~～[]【】()（）\"'“”‘’+＋-—"
_TOPIC_VOTE_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?:(?:选|投|我选|我投|支持|pick|vote)?\s*([abc])\s*(?:方案|号|选项|项|吧|呀|冲|鸭|票)?)$",
    re.IGNORECASE,
)


def _sanitize_preview_path(raw: str) -> str:
    """Validate and normalize a repo-relative preview image path; block traversal and PII."""
    text = str(raw or "").strip().replace("\\", "/")
    if not text or "\x00" in text or "@" in text:
        return ""
    if redact_pii(text) != text:
        return ""
    if text.startswith(("/", "~")) or re.match(r"^[A-Za-z]:", text):
        return ""
    parts = [part for part in text.split("/") if part and part != "."]
    if not parts or any(part == ".." for part in parts):
        return ""
    return "/".join(parts)[:180]


_CRISIS_PRESETS: Final[Tuple[Tuple[str, str], ...]] = (
    ("24G内存告警", "后台缓存接近上限，发「修Bug」立刻抢修加 +300s！"),
    ("电饭煲断电预警", "工坊供能不足，发「投喂」或「修Bug」补充电量！"),
    ("测试红灯抢修", "流水线出现红灯警告，发「修Bug」或「写代码」通关！"),
)

_VIEWER_AVATAR_COLORS: Final[Tuple[Tuple[int, int, int], ...]] = (
    (37, 99, 235),
    (236, 72, 153),
    (16, 185, 129),
    (245, 158, 11),
    (124, 58, 237),
    (6, 182, 212),
    (239, 68, 68),
    (99, 102, 241),
)


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp.{os.getpid()}")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, path)


def _compute_tier(score: int, visits: int) -> str:
    if score >= 200 or visits >= 8:
        return "核心股东"
    if score >= 80 or visits >= 4:
        return "共建熟人"
    if score >= 25 or visits >= 2:
        return "常客"
    return "新伙伴"


def _fmt_hhmmss(total_sec: float) -> str:
    sec = max(0, int(round(total_sec)))
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


class ViewerMemoryStore:
    """Zero-PII persistent memory of returning livestream viewers keyed by sanitized display alias."""

    def __init__(self, memory_path: Path | str = DEFAULT_MEMORY_PATH) -> None:
        self.memory_path = Path(memory_path)
        self._guard = LiveComplianceGuard()
        self._lock = threading.RLock()
        self._viewers: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _clean_alias(self, alias: str) -> str:
        cleaned = self._guard.sanitize_alias(alias or "热心观众").replace("@", "").strip()[:20]
        return cleaned or "热心观众"

    def _load(self) -> None:
        if not self.memory_path.is_file():
            return
        try:
            raw = json.loads(self.memory_path.read_text(encoding="utf-8"))
            rows = raw.get("viewers") if isinstance(raw, dict) else None
            if not isinstance(rows, dict):
                return
            for key, val in rows.items():
                if not isinstance(val, dict):
                    continue
                alias = self._clean_alias(str(key))
                visits = max(1, int(val.get("visits") or 1))
                score = max(0, int(val.get("score") or 0))
                self._viewers[alias] = {
                    "alias": alias,
                    "visits": visits,
                    "actions": max(0, int(val.get("actions") or 0)),
                    "messages": max(0, int(val.get("messages") or 0)),
                    "gifts": max(0, int(val.get("gifts") or 0)),
                    "score": score,
                    "tier": _compute_tier(score, visits),
                    "badge": redact_pii(str(val.get("badge") or "")).replace("@", "").strip()[:16],
                    "last_seen": str(val.get("last_seen") or ""),
                }
        except Exception:
            self._viewers = {}

    def save(self) -> None:
        with self._lock:
            payload = {
                "updated_at": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(),
                "total_viewers": len(self._viewers),
                "viewers": self._viewers,
            }
            _atomic_write_json(self.memory_path, payload)

    def _ensure_viewer(self, alias: str, now_ts: Optional[float] = None) -> Dict[str, Any]:
        key = self._clean_alias(alias)
        ts_str = dt.datetime.fromtimestamp(time.time() if now_ts is None else now_ts, dt.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        entry = self._viewers.get(key)
        if entry is None:
            entry = {
                "alias": key,
                "visits": 1,
                "actions": 0,
                "messages": 0,
                "gifts": 0,
                "score": 0,
                "tier": "新伙伴",
                "badge": "",
                "last_seen": ts_str,
            }
            self._viewers[key] = entry
        else:
            entry["last_seen"] = ts_str
        return entry

    def record_enter(self, alias: str, *, now: Optional[float] = None) -> Dict[str, Any]:
        """Record a viewer entering the stream; increments `visits` if returning after >= 5 minutes."""
        with self._lock:
            ts = time.time() if now is None else float(now)
            key = self._clean_alias(alias)
            existed = key in self._viewers
            prev_seen = str(self._viewers[key].get("last_seen") or "") if existed else ""
            entry = self._ensure_viewer(key, now_ts=ts)
            if existed:
                increment_visit = True
                if prev_seen:
                    try:
                        prev_dt = dt.datetime.strptime(prev_seen, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
                        if (ts - prev_dt.timestamp()) < 300.0:
                            increment_visit = False
                    except Exception:
                        pass
                if increment_visit:
                    entry["visits"] = int(entry["visits"]) + 1
            entry["tier"] = _compute_tier(int(entry["score"]), int(entry["visits"]))
            self.save()
            return dict(entry)

    def record_action(
        self,
        alias: str,
        *,
        points: int = 10,
        action_delta: int = 1,
        message: bool = True,
        gift_count: int = 0,
        badge: str = "",
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Update viewer contribution score, action counters, tier, and optional supporter badge."""
        with self._lock:
            entry = self._ensure_viewer(alias, now_ts=now)
            entry["actions"] = int(entry["actions"]) + max(0, int(action_delta))
            if message:
                entry["messages"] = int(entry["messages"]) + 1
            if gift_count > 0:
                entry["gifts"] = int(entry["gifts"]) + int(gift_count)
            entry["score"] = int(entry["score"]) + max(0, int(points))
            if badge:
                clean_badge = redact_pii(badge).replace("@", "").strip()[:16]
                if clean_badge:
                    entry["badge"] = clean_badge
            entry["tier"] = _compute_tier(int(entry["score"]), int(entry["visits"]))
            self.save()
            return dict(entry)

    def grant_badge(self, alias: str, badge: str, *, bonus_score: int = 25) -> Dict[str, Any]:
        """Grant a special achievement badge (`白米饭供应商` / `建议采纳官`) to a viewer."""
        return self.record_action(alias, points=bonus_score, action_delta=1, message=False, badge=badge)

    def get_viewer(self, alias: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            key = self._clean_alias(alias)
            found = self._viewers.get(key)
            return dict(found) if found is not None else None

    def top_contributors(self, limit: int = 5) -> List[Dict[str, Any]]:
        with self._lock:
            ranked = sorted(
                self._viewers.values(),
                key=lambda row: (int(row.get("score", 0)), int(row.get("actions", 0)), int(row.get("visits", 1))),
                reverse=True,
            )
            return [dict(item) for item in ranked[: max(1, limit)]]

    def total_viewers(self) -> int:
        with self._lock:
            return len(self._viewers)


_SAFE_VERTICAL_AISLES: Final[Tuple[float, ...]] = (86.0, 370.0, 672.0)


def _nearest_safe_aisle(x: float) -> float:
    return min(_SAFE_VERTICAL_AISLES, key=lambda ax: abs(ax - x))


def _in_safe_aisle(x: float) -> bool:
    return x <= 104.0 or (288.0 <= x <= 452.0) or x >= 636.0


def _station_doorway_coords(station_name: str, slot_idx: int = 0) -> Tuple[float, float]:
    """Return a guaranteed collision-free, non-overlapping doorway coordinate in front of a left-map building."""
    sx, sy, _, _ = STATIONS.get(station_name, STATIONS["互联网热点海"])
    if sy < 280:
        offsets: Tuple[Tuple[float, float], ...] = ((-84.0, 266.0), (0.0, 282.0), (84.0, 266.0))
    else:
        offsets = ((-84.0, 324.0), (0.0, 306.0), (84.0, 324.0))
    ox, door_y = offsets[slot_idx % len(offsets)]
    tx = max(MAP_MIN_X, min(MAP_MAX_X, float(sx + ox)))
    return tx, door_y


def _plan_corridor_waypoints(x0: float, y0: float, x1: float, y1: float) -> List[Tuple[float, float]]:
    """Route moves along the open `CORRIDOR_Y` aisle (and vertical aisles) so actors avoid station boxes."""
    pts: List[Tuple[float, float]] = []
    cx, cy = x0, y0
    in_corridor_0 = 216.0 <= y0 <= 346.0
    in_corridor_1 = 216.0 <= y1 <= 346.0

    if in_corridor_0 and in_corridor_1:
        if abs(x1 - x0) <= 60.0:
            return [(x1, y1)]
        if abs(y0 - CORRIDOR_Y) > 6.0:
            pts.append((x0, CORRIDOR_Y))
        if abs(y1 - CORRIDOR_Y) > 6.0 or abs(x1 - x0) > 6.0:
            pts.append((x1, CORRIDOR_Y))
        pts.append((x1, y1))
        return pts

    if not in_corridor_0:
        if not _in_safe_aisle(cx):
            cx = _nearest_safe_aisle(cx)
            pts.append((cx, cy))
        pts.append((cx, CORRIDOR_Y))
        cy = CORRIDOR_Y

    if not in_corridor_1:
        entry_x = x1 if _in_safe_aisle(x1) else _nearest_safe_aisle(x1)
        if abs(entry_x - cx) > 4.0:
            pts.append((entry_x, CORRIDOR_Y))
        pts.append((entry_x, y1))
        if abs(x1 - entry_x) > 4.0:
            pts.append((x1, y1))
    else:
        if abs(x1 - cx) > 4.0:
            pts.append((x1, CORRIDOR_Y))
        pts.append((x1, y1))
    return pts


def _step_along_waypoints(
    x: float,
    y: float,
    waypoints: List[Tuple[float, float]],
    max_step: float,
) -> Tuple[float, float]:
    """Advance `(x, y)` up to `max_step` pixels along queued corridor waypoints."""
    rem = max_step
    cur_x, cur_y = x, y
    while waypoints and rem > 0.0:
        wx, wy = waypoints[0]
        dx = wx - cur_x
        dy = wy - cur_y
        dist = math.hypot(dx, dy)
        if dist <= 2.0:
            cur_x, cur_y = wx, wy
            waypoints.pop(0)
            continue
        if dist <= rem:
            cur_x, cur_y = wx, wy
            rem -= dist
            waypoints.pop(0)
        else:
            cur_x += (dx / dist) * rem
            cur_y += (dy / dist) * rem
            rem = 0.0
    return cur_x, cur_y


@dataclass
class HostActor:
    """Autonomous AI host character roaming inside the 2D workshop map."""

    speaker_id: SpeakerId
    name: str
    x: float
    y: float
    target_station: str
    target_x: float
    target_y: float
    action_label: str
    phase: float = 0.0
    waypoints: List[Tuple[float, float]] = field(default_factory=list)


@dataclass
class AmbientBotActor:
    """Built-in clearly labeled AI helper bot keeping the workshop lively (never counted as real viewer)."""

    bot_id: str
    name: str
    x: float
    y: float
    target_x: float
    target_y: float
    station: str
    action_label: str
    color: Tuple[int, int, int]
    phase: float = 0.0
    next_hop_sec: float = 16.0
    next_popup_sec: float = 10.0
    route_step: int = 0
    waypoints: List[Tuple[float, float]] = field(default_factory=list)


@dataclass
class ViewerActor:
    """Named pixel builder avatar spawned by viewer danmaku inside the 2D workshop."""

    alias: str
    x: float
    y: float
    target_x: float
    target_y: float
    station: str
    action_label: str
    color_idx: int
    tier: str = "新伙伴"
    badge: str = ""
    last_active_ts: float = field(default_factory=time.time)
    waypoints: List[Tuple[float, float]] = field(default_factory=list)


@dataclass
class FloatingPopup:
    """Transient floating feedback popup (`+120s`, `开工！`, etc.) inside the 2D world."""

    text: str
    x: float
    y: float
    color: Tuple[int, int, int]
    ttl_sec: float = 4.5


class LiveAgentWorld:
    """Stateful 2D interactive workshop simulation + real-time Agent workbench + telemetry state."""

    def __init__(
        self,
        *,
        memory_store: Optional[ViewerMemoryStore] = None,
        memory_path: Path | str = DEFAULT_MEMORY_PATH,
        follower_count: int = 15,
        follower_goal: int = 1000,
        cast: Sequence[SpeakerId] = TRIO_CAST,
        initial_countdown_sec: float = 14400.0,
    ) -> None:
        self.memory = memory_store or ViewerMemoryStore(memory_path=memory_path)
        self.guard = LiveComplianceGuard()
        self._lock = threading.RLock()

        normalized_cast = [sid for sid in cast if sid in PERSONAS]
        self.cast: Tuple[SpeakerId, ...] = tuple(normalized_cast) if normalized_cast else TRIO_CAST

        # Live telemetry (strictly zero PII)
        self.online: int = 0
        self.max_online: int = 0
        self.watched_num: int = 0
        self.max_watched_num: int = 0
        self.watched_text: str = "0人看过"
        self.initial_followers: int = max(0, int(follower_count))
        self.follower_count: int = max(0, int(follower_count))
        self.follower_goal: int = max(1, int(follower_goal))

        # World economy & survival countdown
        self.countdown_sec: float = max(60.0, float(initial_countdown_sec))
        self.world_time_sec: float = 0.0
        self.code_pts: int = 0
        self.compute_pts: int = 0
        self.rice_bowls: int = 0
        self.build_xp: int = 0
        self.level: int = 1
        self.level_name: str = LEVEL_THRESHOLDS[0][2]

        # Active crisis mini-event
        self.active_event: Optional[Dict[str, str]] = None
        self._crisis_cursor: int = 0
        self._next_crisis_at_sec: float = CRISIS_COOLDOWN_SEC
        self._crisis_started_at_sec: Optional[float] = None

        # Real-time visitor arrival ice-breaker
        self._last_icebreaker_ts: float = 0.0
        self.icebreaker_cooldown_sec: float = 45.0
        self._pending_visitor_welcome: Optional[int] = None

        # Real-time Agent Workbench & Live Video-Production State Machine
        self.active_task: str = "互联网热点海筹备 Ep024，等待弹幕 A/B/C 投票或发「1」开工"
        self.pipeline_stage: int = 0
        self.work_log: Deque[Dict[str, str]] = deque(maxlen=8)
        self._push_log_locked("AGENT", "AI 现场制片厂已上线：4座工序建筑与 LIVE 制片大屏运行中")

        self._topic_votes: Dict[str, str] = {}
        self._stage_focus_until_sec: float = 0.0
        self.production: Dict[str, Any] = {
            "stage": "internet_sea",
            "stage_title": "互联网热点海",
            "episode": "Ep024 筹备中",
            "detail": "抓取实时热榜并收集弹幕 A/B/C 下期题材投票",
            "progress_pct": 15,
            "monitor_mode": "poll",
            "preview_paths": [],
            "preview_caption": "Ep024 题材海选 · 弹幕发 A / B / C 实时计票",
            "code_lines": [
                "$ ./.venv/bin/python cli.py benchmark --online",
                "[SEA] scanning Bilibili hot hooks & 60FPS pacing...",
                "[POLL] Ep024 A/B/C topic voting open on live stage_",
            ],
            "topic_poll": {
                "question": "下期 Ep024 拍什么？发弹幕 A / B / C 投票！",
                "options": [{"key": k, "label": lbl, "votes": 0} for k, lbl in _DEFAULT_POLL_OPTIONS],
                "total_votes": 0,
            },
            "stage_change_seq": 0,
        }

        # Suggestions & banners
        self._suggestion_seq: int = 0
        self.suggestions: Deque[Dict[str, Any]] = deque(maxlen=12)
        self.banner_text: str = ""
        self._banner_until_ts: float = 0.0
        self.stop_requested: bool = False

        # Danmaku stream & world actors (all kept inside left map x in [68, 712])
        self.recent_danmaku: Deque[Dict[str, Any]] = deque(maxlen=16)
        self.popups: List[FloatingPopup] = []
        self.viewer_actors: Dict[str, ViewerActor] = {}
        self.ambient_bots: List[AmbientBotActor] = [
            AmbientBotActor(
                bot_id="ai_coder",
                name="AI巡检小鱼",
                x=310.0,
                y=CORRIDOR_Y,
                target_x=146.0,
                target_y=268.0,
                station="互联网热点海",
                action_label="抓热榜巡检",
                color=(14, 165, 233),
                phase=0.4,
                next_hop_sec=16.0,
                next_popup_sec=9.0,
                route_step=0,
                waypoints=_plan_corridor_waypoints(310.0, CORRIDOR_Y, 146.0, 268.0),
            ),
            AmbientBotActor(
                bot_id="ai_rice",
                name="AI电饭煲助手",
                x=430.0,
                y=CORRIDOR_Y,
                target_x=594.0,
                target_y=320.0,
                station="剪辑放映厅",
                action_label="加米补算力",
                color=(245, 158, 11),
                phase=1.8,
                next_hop_sec=19.0,
                next_popup_sec=14.0,
                route_step=0,
                waypoints=_plan_corridor_waypoints(430.0, CORRIDOR_Y, 594.0, 320.0),
            ),
        ]

        station_names = list(STATIONS.keys())
        default_actions = {
            "dafeiyu": "冲热点海",
            "yowane": "核对排期",
            "gemini": "锁角色帧",
        }
        self.host_actors: Dict[SpeakerId, HostActor] = {}
        for idx, sid in enumerate(self.cast):
            st_name = station_names[idx % len(station_names)]
            hx, hy = _station_doorway_coords(st_name, idx)
            self.host_actors[sid] = HostActor(
                speaker_id=sid,
                name=PERSONAS[sid].short_name,
                x=hx,
                y=hy,
                target_station=st_name,
                target_x=hx,
                target_y=hy,
                action_label=default_actions.get(sid, "制片中"),
                phase=idx * 2.1,
            )

    def _recompute_level_locked(self) -> Optional[str]:
        new_level = 1
        new_name = LEVEL_THRESHOLDS[0][2]
        for lvl, req_xp, name in LEVEL_THRESHOLDS:
            if self.build_xp >= req_xp:
                new_level = lvl
                new_name = name
        if new_level > self.level:
            self.level = new_level
            self.level_name = new_name
            msg = f"工坊升级！迈入 Lv.{new_level} {new_name}！"
            self.banner_text = msg
            self._banner_until_ts = time.time() + 10.0
            self._push_log_locked("WORLD", msg)
            return msg
        self.level = new_level
        self.level_name = new_name
        return None

    def _push_log_locked(self, tag: str, text: str) -> None:
        clean_tag = str(tag or "AGENT").upper()[:8]
        clean_text = redact_pii(str(text or "")).replace("@", "").strip()[:76]
        if not clean_text:
            return
        now_str = dt.datetime.now(dt.timezone.utc).astimezone().strftime("%H:%M:%S")
        self.work_log.append({"ts": now_str, "tag": clean_tag, "text": clean_text})

    def _add_popup_locked(self, text: str, x: float, y: float, color: Tuple[int, int, int]) -> None:
        self.popups.append(FloatingPopup(text=text[:28], x=x, y=y, color=color, ttl_sec=4.2))
        if len(self.popups) > 12:
            self.popups = self.popups[-12:]

    def _recount_topic_votes_locked(self) -> int:
        counts: Dict[str, int] = {"A": 0, "B": 0, "C": 0}
        for choice in self._topic_votes.values():
            key = str(choice).upper()
            if key in counts:
                counts[key] += 1
        poll = self.production["topic_poll"]
        for opt in poll["options"]:
            key = str(opt.get("key") or "").upper()
            if key in counts:
                opt["votes"] = counts[key]
        total = sum(counts.values())
        poll["total_votes"] = total
        return total

    def _dispatch_hosts_to_station_locked(self, station_name: str, stage_key: str) -> None:
        stage_actions: Dict[str, Dict[SpeakerId, str]] = {
            "internet_sea": {"dafeiyu": "抓热榜", "yowane": "看票数", "gemini": "挑高能梗"},
            "character_catch": {"dafeiyu": "抓铁三角", "yowane": "锁设定表", "gemini": "摆萌立绘"},
            "kling_forge": {"dafeiyu": "炼关键帧", "yowane": "盯API额", "gemini": "调亮色调"},
            "edit_theater": {"dafeiyu": "剪60帧", "yowane": "过质检门", "gemini": "审高CTR"},
        }
        per_speaker = stage_actions.get(stage_key, {})
        for idx, (sid, host) in enumerate(self.host_actors.items()):
            tx, ty = _station_doorway_coords(station_name, idx)
            host.target_station = station_name
            host.target_x = tx
            host.target_y = ty
            host.waypoints = _plan_corridor_waypoints(host.x, host.y, tx, ty)
            host.action_label = per_speaker.get(sid, f"前往{station_name[:2]}")

    def _spawn_or_move_viewer_locked(
        self,
        alias: str,
        *,
        station: str,
        action_label: str,
        tier: str = "新伙伴",
        badge: str = "",
    ) -> ViewerActor:
        now = time.time()
        resolved_station = station if station in STATIONS else "互联网热点海"
        sx, sy, _, _ = STATIONS[resolved_station]
        offset_seed = sum(ord(c) for c in alias)
        if sy >= 280:
            # Lower row doorway + open promenade slots (zero station-box collision, zero card occlusion)
            candidate_coords: List[Tuple[float, float]] = [
                (max(MAP_MIN_X + 10.0, min(MAP_MAX_X - 10.0, float(sx - 108.0))), 320.0),
                (max(MAP_MIN_X + 10.0, min(MAP_MAX_X - 10.0, float(sx + 108.0))), 320.0),
                (370.0, 314.0),
                (max(MAP_MIN_X + 10.0, min(MAP_MAX_X - 10.0, float(sx))), 490.0),
                (max(MAP_MIN_X + 10.0, min(MAP_MAX_X - 10.0, float(sx - 110.0))), 490.0),
                (max(MAP_MIN_X + 10.0, min(MAP_MAX_X - 10.0, float(sx + 110.0))), 490.0),
                (370.0, 490.0),
                (108.0, 294.0),
                (652.0, 294.0),
            ]
        else:
            # Upper row doorway + open promenade slots (zero station-box collision, zero card occlusion)
            candidate_coords = [
                (max(MAP_MIN_X + 10.0, min(MAP_MAX_X - 10.0, float(sx - 108.0))), 272.0),
                (max(MAP_MIN_X + 10.0, min(MAP_MAX_X - 10.0, float(sx + 108.0))), 272.0),
                (370.0, 272.0),
                (370.0, 316.0),
                (max(MAP_MIN_X + 10.0, min(MAP_MAX_X - 10.0, float(sx - 106.0))), 490.0),
                (max(MAP_MIN_X + 10.0, min(MAP_MAX_X - 10.0, float(sx + 106.0))), 490.0),
                (370.0, 490.0),
                (520.0, 490.0),
                (640.0, 490.0),
            ]
        default_idx = offset_seed % len(candidate_coords)
        rotated = candidate_coords[default_idx:] + candidate_coords[:default_idx]
        tx, ty = rotated[0]
        other_coords = [(v.target_x, v.target_y) for k, v in self.viewer_actors.items() if k != alias]
        for cx, cy in rotated:
            if all(math.hypot(cx - ox, cy - oy) > 74.0 for ox, oy in other_coords):
                tx, ty = cx, cy
                break

        actor = self.viewer_actors.get(alias)
        if actor is None:
            if len(self.viewer_actors) >= 16:
                oldest_key = min(self.viewer_actors, key=lambda k: self.viewer_actors[k].last_active_ts)
                self.viewer_actors.pop(oldest_key, None)
            spawn_x = max(MAP_MIN_X + 6.0, min(MAP_MAX_X - 6.0, 370.0))
            actor = ViewerActor(
                alias=alias,
                x=spawn_x,
                y=CORRIDOR_Y,
                target_x=tx,
                target_y=ty,
                station=resolved_station,
                action_label=action_label,
                color_idx=offset_seed % len(_VIEWER_AVATAR_COLORS),
                tier=tier,
                badge=badge,
                last_active_ts=now,
                waypoints=_plan_corridor_waypoints(spawn_x, CORRIDOR_Y, tx, ty),
            )
            self.viewer_actors[alias] = actor
        else:
            actor.target_x = tx
            actor.target_y = ty
            actor.station = resolved_station
            actor.action_label = action_label
            actor.tier = tier or actor.tier
            if badge:
                actor.badge = badge
            actor.last_active_ts = now
            actor.waypoints = _plan_corridor_waypoints(actor.x, actor.y, tx, ty)
        return actor

    def tick(self, dt_sec: float = 1.0 / DEFAULT_FPS) -> None:
        """Advance simulation clocks, host/viewer movement, crisis timers, and popups."""
        step = max(0.0, float(dt_sec))
        if step <= 0.0:
            return
        with self._lock:
            self.world_time_sec += step
            drain_rate = 2.0 if self.active_event is not None else 1.0
            self.countdown_sec = max(0.0, self.countdown_sec - step * drain_rate)

            # Periodic interactive crisis event (~every 5 minutes when idle)
            if self.active_event is None and self.world_time_sec >= self._next_crisis_at_sec:
                title, desc = _CRISIS_PRESETS[self._crisis_cursor % len(_CRISIS_PRESETS)]
                self._crisis_cursor += 1
                self.active_event = {"title": title, "desc": desc}
                self._crisis_started_at_sec = self.world_time_sec
                self._next_crisis_at_sec = self.world_time_sec + CRISIS_COOLDOWN_SEC
                self._push_log_locked("ALERT", f"触发突发事件：{title}（等待弹幕「修Bug」或巡检处理）")
            elif self.active_event is not None:
                if self._crisis_started_at_sec is None:
                    self._crisis_started_at_sec = self.world_time_sec
                elif (self.world_time_sec - self._crisis_started_at_sec) >= 180.0:
                    prev = str(self.active_event.get("title") or "例行巡检")
                    self.active_event = None
                    self._crisis_started_at_sec = None
                    self._next_crisis_at_sec = self.world_time_sec + CRISIS_COOLDOWN_SEC
                    self.compute_pts += 10
                    self._push_log_locked("FIX", f"AI巡检小鱼自动排查完成了「{prev}」，工坊恢复运转")

            station_keys = tuple(STATIONS.keys())
            for idx, (sid, host) in enumerate(self.host_actors.items()):
                host.phase += step
                # Re-target host between left-map buildings smoothly every ~11s once stage focus expires
                if self.world_time_sec >= self._stage_focus_until_sec and int(
                    (self.world_time_sec + idx * 3.5) / 11.0
                ) != int((self.world_time_sec - step + idx * 3.5) / 11.0):
                    next_st = station_keys[(int(self.world_time_sec // 11.0) + idx) % len(station_keys)]
                    _, _, st_desc, _ = STATIONS[next_st]
                    tx, ty = _station_doorway_coords(next_st, idx)
                    host.target_station = next_st
                    host.target_x = tx
                    host.target_y = ty
                    host.waypoints = _plan_corridor_waypoints(host.x, host.y, host.target_x, host.target_y)
                    if sid == "dafeiyu":
                        host.action_label = f"巡查{next_st[:2]}"
                    elif sid == "yowane":
                        host.action_label = f"核验·{next_st[:2]}"
                    else:
                        host.action_label = st_desc[:7]

                if not host.waypoints and math.hypot(host.target_x - host.x, host.target_y - host.y) > 2.0:
                    host.waypoints = _plan_corridor_waypoints(host.x, host.y, host.target_x, host.target_y)
                if host.waypoints:
                    host.x, host.y = _step_along_waypoints(host.x, host.y, host.waypoints, 66.0 * step)
                    host.x = max(MAP_MIN_X, min(MAP_MAX_X, host.x))

            bot_routes: Dict[str, Tuple[Tuple[float, float, str, str], ...]] = {
                "ai_coder": (
                    (146.0, 268.0, "互联网热点海", "抓热榜巡检"),
                    (496.0, 268.0, "角色抓捕屋", "锁铁三角立绘"),
                    (146.0, 320.0, "可灵炼丹房", "盯可灵API"),
                    (496.0, 320.0, "剪辑放映厅", "验60帧成片"),
                ),
                "ai_rice": (
                    (594.0, 320.0, "剪辑放映厅", "送热白米饭"),
                    (246.0, 320.0, "可灵炼丹房", "加米补算力"),
                    (594.0, 268.0, "角色抓捕屋", "理角色设定"),
                    (246.0, 268.0, "互联网热点海", "核弹幕票数"),
                ),
            }
            for bot in self.ambient_bots:
                bot.phase += step
                if self.world_time_sec >= bot.next_hop_sec:
                    bot.next_hop_sec = self.world_time_sec + 18.0
                    stops = bot_routes.get(bot.bot_id)
                    if stops:
                        bot.route_step = (bot.route_step + 1) % len(stops)
                        tx, ty, st_lbl, act_lbl = stops[bot.route_step]
                        bot.target_x = tx
                        bot.target_y = ty
                        bot.station = st_lbl
                        bot.action_label = act_lbl
                        bot.waypoints = _plan_corridor_waypoints(bot.x, bot.y, tx, ty)
                if self.world_time_sec >= bot.next_popup_sec:
                    bot.next_popup_sec = self.world_time_sec + 24.0
                    pop_msg = "热点巡检 +1" if bot.bot_id == "ai_coder" else "米饭续算力~"
                    self._add_popup_locked(pop_msg, bot.x, bot.y - 42, bot.color)
                if bot.waypoints:
                    bot.x, bot.y = _step_along_waypoints(bot.x, bot.y, bot.waypoints, 46.0 * step)
                    bot.x = max(MAP_MIN_X, min(MAP_MAX_X, bot.x))

            for actor in self.viewer_actors.values():
                if not actor.waypoints and math.hypot(actor.target_x - actor.x, actor.target_y - actor.y) > 2.0:
                    actor.waypoints = _plan_corridor_waypoints(actor.x, actor.y, actor.target_x, actor.target_y)
                if actor.waypoints:
                    actor.x, actor.y = _step_along_waypoints(actor.x, actor.y, actor.waypoints, 96.0 * step)
                    actor.x = max(MAP_MIN_X, min(MAP_MAX_X, actor.x))

            alive_popups: List[FloatingPopup] = []
            for p in self.popups:
                p.ttl_sec -= step
                p.y -= 18.0 * step
                if p.ttl_sec > 0.0:
                    alive_popups.append(p)
            self.popups = alive_popups

    def update_telemetry(
        self,
        *,
        online: Optional[int] = None,
        watched_num: Optional[int] = None,
        watched_text: Optional[str] = None,
        follower_count: Optional[int] = None,
    ) -> int:
        """Update real-time Bilibili room online/watched/follower metrics; returns follower delta."""
        delta_followers = 0
        now_ts = time.time()
        with self._lock:
            if online is not None:
                val = max(0, int(online))
                self.online = val
                self.max_online = max(self.max_online, val)
            if watched_num is not None:
                prev_watched = self.watched_num
                wval = max(0, int(watched_num))
                self.watched_num = wval
                self.max_watched_num = max(self.max_watched_num, wval)
                if watched_text is None:
                    self.watched_text = f"{wval}人看过"
                if wval > prev_watched and (now_ts - self._last_icebreaker_ts) >= self.icebreaker_cooldown_sec:
                    self._pending_visitor_welcome = wval
            if watched_text is not None:
                clean_wt = redact_pii(str(watched_text)).replace("@", "").strip()[:24]
                if clean_wt:
                    self.watched_text = clean_wt
            if follower_count is not None:
                fval = max(0, int(follower_count))
                if fval > self.follower_count:
                    delta_followers = fval - self.follower_count
                    msg = f"涨粉喜报！粉丝突破 {fval} 啦！继续冲向 {self.follower_goal} 粉！"
                    self.banner_text = msg
                    self._banner_until_ts = now_ts + 10.0
                    self._push_log_locked("LIVE", msg)
                self.follower_count = fval
        return delta_followers

    def consume_visitor_icebreaker(self, *, now: Optional[float] = None) -> Optional[Tuple[SpeakerId, str, str]]:
        """Consume a pending real-visitor arrival event into a cacheable female welcome line."""
        ts = time.time() if now is None else float(now)
        with self._lock:
            if self._pending_visitor_welcome is None:
                return None
            watched_total = self._pending_visitor_welcome
            self._pending_visitor_welcome = None
            if (ts - self._last_icebreaker_ts) < self.icebreaker_cooldown_sec:
                return None
            self._last_icebreaker_ts = ts
            self.banner_text = "欢迎新伙伴进房！发个「1」或「开工」3秒生成你的专属小人！"
            self._banner_until_ts = ts + 12.0
            self._push_log_locked(
                "ENTER",
                f"检测到新观众进房（累计 {watched_total} 人看过），触发女声迎宾破冰！",
            )
            return (
                "dafeiyu",
                "呀，检测到新小伙伴进直播间啦！发个数字1或者开工，三秒就能把你的专属像素小人放进地图里，觉得哪里还能改直接发弹幕告诉我！",
                "lively",
            )

    def handle_danmaku_event(self, ev: DanmakuEvent) -> Dict[str, Any]:
        """Process viewer danmaku/gift/enter into immediate 2D world updates & viewer memory."""
        safe_alias = self.guard.sanitize_alias(ev.user_alias).replace("@", "").strip()[:20] or "热心观众"
        now = time.time()

        if ev.event_type == "enter":
            mem = self.memory.record_enter(safe_alias, now=now)
            with self._lock:
                if int(mem.get("visits", 1)) >= 2:
                    msg = f"欢迎老熟人 {safe_alias} 第 {mem['visits']} 次回到制片厂！"
                    self.banner_text = msg
                    self._banner_until_ts = now + 7.0
                    actor = self._spawn_or_move_viewer_locked(
                        safe_alias,
                        station="互联网热点海",
                        action_label=f"第{mem['visits']}次回归",
                        tier=str(mem.get("tier") or "常客"),
                        badge=str(mem.get("badge") or ""),
                    )
                    self._add_popup_locked("老熟人回归！", actor.x, actor.y - 36, (14, 165, 233))
                self.recent_danmaku.append({"event_type": "enter", "user_alias": safe_alias, "text": ev.text[:48]})
            return {"handled": True, "kind": "enter", "alias": safe_alias, "visits": mem.get("visits", 1)}

        if ev.event_type == "gift":
            count = max(1, int(ev.gift_count or 1))
            gift_chk = self.guard.sanitize_danmaku(ev.gift_name or "小心心")
            gift_name = gift_chk.cleaned_text if gift_chk.allowed else "投喂"
            add_sec = 300.0 * count
            pts = 20 * count
            mem = self.memory.record_action(
                safe_alias,
                points=pts,
                action_delta=1,
                message=False,
                gift_count=count,
                badge="白米饭供应商",
                now=now,
            )
            with self._lock:
                self.countdown_sec += add_sec
                self.rice_bowls += count
                self.build_xp += pts
                actor = self._spawn_or_move_viewer_locked(
                    safe_alias,
                    station="可灵炼丹房",
                    action_label=f"投喂{gift_name}x{count}",
                    tier=str(mem.get("tier") or "新伙伴"),
                    badge=str(mem.get("badge") or "白米饭供应商"),
                )
                self._add_popup_locked(f"+{int(add_sec)}s 白米饭+{count}", actor.x, actor.y - 38, (245, 158, 11))
                self.banner_text = f"感谢 {safe_alias} 投喂 {gift_name} x{count}！续命 +{int(add_sec)} 秒！"
                self._banner_until_ts = now + 9.0
                self._recompute_level_locked()
                self._push_log_locked("GIFT", f"{safe_alias} 投喂 {gift_name}x{count}，工坊续命 +{int(add_sec)}s")
                self.recent_danmaku.append(
                    {"event_type": "gift", "user_alias": safe_alias, "text": f"投喂了 {gift_name} x{count}"}
                )
            return {"handled": True, "kind": "gift", "alias": safe_alias, "added_sec": add_sec}

        # Danmaku command parsing
        chk = self.guard.sanitize_danmaku(ev.text)
        if not chk.allowed:
            return {"handled": False, "reason": chk.reason}

        clean_text = chk.cleaned_text
        lowered = clean_text.lower()

        if ev.event_type == "system":
            with self._lock:
                self.recent_danmaku.append({"event_type": "system", "user_alias": safe_alias, "text": clean_text[:48]})
            return {"handled": True, "kind": "system"}

        # Check explicit suggestion prefix FIRST so "建议 加个白米饭锅" / "建议 A方案加特效" routes to suggestions
        if _SUGGESTION_PREFIX_RE.match(clean_text):
            body = _SUGGESTION_PREFIX_RE.sub("", clean_text).strip()[:40] or clean_text[:40]
            mem = self.memory.record_action(safe_alias, points=8, action_delta=1, message=True, now=now)
            with self._lock:
                self._suggestion_seq += 1
                sug_id = f"S{self._suggestion_seq}"
                self.suggestions.append(
                    {
                        "id": sug_id,
                        "author": safe_alias,
                        "text": body,
                        "status": "待采纳",
                    }
                )
                self.countdown_sec += 90.0
                self.build_xp += 8
                actor = self._spawn_or_move_viewer_locked(
                    safe_alias,
                    station="剪辑放映厅",
                    action_label=f"提交建议{sug_id}",
                    tier=str(mem.get("tier") or "新伙伴"),
                    badge=str(mem.get("badge") or ""),
                )
                self._add_popup_locked(f"建议{sug_id}已上墙!", actor.x, actor.y - 36, (139, 92, 246))
                self._push_log_locked("IDEA", f"收到 {safe_alias} 建议({sug_id}): {body}")
                self._recompute_level_locked()
                self.recent_danmaku.append({"event_type": "danmaku", "user_alias": safe_alias, "text": clean_text[:48]})
            return {"handled": True, "kind": "suggestion", "suggestion_id": sug_id, "alias": safe_alias}

        # Check A / B / C next-episode topic vote (case- and punctuation-insensitive, deduplicated per user)
        vote_token = lowered.strip(_TOPIC_VOTE_STRIP_CHARS)
        vote_match = _TOPIC_VOTE_RE.match(vote_token)
        if vote_match is not None:
            choice = vote_match.group(1).upper()
            mem = self.memory.record_action(safe_alias, points=10, action_delta=1, message=True, now=now)
            with self._lock:
                prev_choice = self._topic_votes.get(safe_alias)
                self._topic_votes[safe_alias] = choice
                total_votes = self._recount_topic_votes_locked()
                self.countdown_sec += 120.0
                self.build_xp += 10
                actor = self._spawn_or_move_viewer_locked(
                    safe_alias,
                    station="互联网热点海",
                    action_label=f"投{choice}方案+120s",
                    tier=str(mem.get("tier") or "新伙伴"),
                    badge=str(mem.get("badge") or ""),
                )
                opt_col = _POLL_OPTION_COLORS.get(choice, (14, 165, 233))
                pop_msg = f"改投{choice} +120s" if prev_choice and prev_choice != choice else f"投{choice}方案 +120s"
                self._add_popup_locked(pop_msg, actor.x, actor.y - 36, opt_col)
                self._push_log_locked(
                    "VOTE",
                    f"{safe_alias} 投票给 {choice} 方案（当前总票 {total_votes}，+120s）",
                )
                self._recompute_level_locked()
                self.recent_danmaku.append({"event_type": "danmaku", "user_alias": safe_alias, "text": clean_text[:48]})
            return {
                "handled": True,
                "kind": "vote_topic",
                "choice": choice,
                "alias": safe_alias,
                "total_votes": total_votes,
            }

        # Check action commands in priority order
        if any(k in lowered for k in ("投喂", "加餐", "白米饭")):
            mem = self.memory.record_action(safe_alias, points=18, action_delta=1, message=True, now=now)
            with self._lock:
                self.countdown_sec += 300.0
                self.rice_bowls += 1
                self.build_xp += 18
                actor = self._spawn_or_move_viewer_locked(
                    safe_alias,
                    station="可灵炼丹房",
                    action_label="热心加餐+300s",
                    tier=str(mem.get("tier") or "新伙伴"),
                    badge=str(mem.get("badge") or ""),
                )
                self._add_popup_locked("+300s 白米饭+1", actor.x, actor.y - 36, (245, 158, 11))
                self._recompute_level_locked()
                self.recent_danmaku.append({"event_type": "danmaku", "user_alias": safe_alias, "text": clean_text[:48]})
            return {"handled": True, "kind": "feed", "alias": safe_alias}

        if any(k in lowered for k in ("修bug", "抢修", "快跑")):
            with self._lock:
                resolved_crisis = self.active_event is not None
                crisis_title = self.active_event["title"] if self.active_event else ""
                if resolved_crisis:
                    self.active_event = None
                    self._crisis_started_at_sec = None
                    self._next_crisis_at_sec = self.world_time_sec + CRISIS_COOLDOWN_SEC
                    add_sec, pts = 300.0, 30
                    label = "抢修成功+300s"
                    pop_txt = f"抢修{crisis_title}! +300s"
                    self.banner_text = f"{safe_alias} 弹幕抢修「{crisis_title}」成功！全员续命 +300 秒！"
                    self._banner_until_ts = now + 8.0
                    self._push_log_locked("FIX", f"观众 {safe_alias} 抢修「{crisis_title}」解除警报 (+300s)")
                else:
                    add_sec, pts = 150.0, 12
                    label = "巡检优化+150s"
                    pop_txt = "+150s 算力优化"
                self.countdown_sec += add_sec
                self.compute_pts += pts
                self.build_xp += pts
                mem = self.memory.record_action(safe_alias, points=pts, action_delta=1, message=True, now=now)
                actor = self._spawn_or_move_viewer_locked(
                    safe_alias,
                    station="可灵炼丹房",
                    action_label=label,
                    tier=str(mem.get("tier") or "新伙伴"),
                    badge=str(mem.get("badge") or ""),
                )
                self._add_popup_locked(pop_txt, actor.x, actor.y - 36, (16, 185, 129))
                self._recompute_level_locked()
                self.recent_danmaku.append({"event_type": "danmaku", "user_alias": safe_alias, "text": clean_text[:48]})
            return {"handled": True, "kind": "fix_bug", "resolved_crisis": resolved_crisis, "alias": safe_alias}

        if any(k in lowered for k in ("写代码", "代码", "伐木", "施工", "建塔")):
            mem = self.memory.record_action(safe_alias, points=15, action_delta=1, message=True, now=now)
            with self._lock:
                self.countdown_sec += 180.0
                self.code_pts += 15
                self.build_xp += 15
                station = "剪辑放映厅" if ("代码" in lowered) else "角色抓捕屋"
                actor = self._spawn_or_move_viewer_locked(
                    safe_alias,
                    station=station,
                    action_label="拼命施工+180s",
                    tier=str(mem.get("tier") or "新伙伴"),
                    badge=str(mem.get("badge") or ""),
                )
                self._add_popup_locked("+180s 建造+15", actor.x, actor.y - 36, (37, 99, 235))
                self._recompute_level_locked()
                self.recent_danmaku.append({"event_type": "danmaku", "user_alias": safe_alias, "text": clean_text[:48]})
            return {"handled": True, "kind": "build", "alias": safe_alias}

        if any(k in lowered for k in ("开工", "打工", "加入", "打卡", "报到")) or lowered.strip("！!。. ~～") in (
            "1",
            "来",
            "来了",
            "在",
        ):
            mem = self.memory.record_action(safe_alias, points=10, action_delta=1, message=True, now=now)
            with self._lock:
                self.countdown_sec += 120.0
                self.build_xp += 10
                active_station = PRODUCTION_STAGE_TO_STATION.get(
                    str(self.production.get("stage") or "internet_sea"), "互联网热点海"
                )
                actor = self._spawn_or_move_viewer_locked(
                    safe_alias,
                    station=active_station,
                    action_label="报到开工+120s",
                    tier=str(mem.get("tier") or "新伙伴"),
                    badge=str(mem.get("badge") or ""),
                )
                self._add_popup_locked("开工大吉 +120s", actor.x, actor.y - 36, (14, 165, 233))
                self._push_log_locked("JOIN", f"{safe_alias} 发送「开工」加入制片厂 (+120s)")
                self._recompute_level_locked()
                self.recent_danmaku.append({"event_type": "danmaku", "user_alias": safe_alias, "text": clean_text[:48]})
            return {"handled": True, "kind": "join", "alias": safe_alias}

        # General danmaku chat: still remembers viewer and nudges avatar/bubble if present
        mem = self.memory.record_action(safe_alias, points=5, action_delta=0, message=True, now=now)
        with self._lock:
            self.build_xp += 3
            if safe_alias in self.viewer_actors:
                actor = self.viewer_actors[safe_alias]
                actor.action_label = clean_text[:10]
                actor.last_active_ts = now
                actor.tier = str(mem.get("tier") or actor.tier)
                actor.badge = str(mem.get("badge") or actor.badge)
            self._recompute_level_locked()
            self.recent_danmaku.append({"event_type": "danmaku", "user_alias": safe_alias, "text": clean_text[:48]})
        return {"handled": True, "kind": "chat", "alias": safe_alias}

    def apply_agent_command(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a live Agent control bridge command cleanly without blocking rendering."""
        if not isinstance(cmd, dict):
            return {"ok": False, "error": "invalid_command"}
        kind = str(cmd.get("cmd") or "").strip().lower()
        now = time.time()

        if kind == "work_log":
            with self._lock:
                task = cmd.get("task")
                if isinstance(task, str) and task.strip():
                    self.active_task = redact_pii(task).replace("@", "").strip()[:56]
                if cmd.get("stage") is not None:
                    try:
                        self.pipeline_stage = max(0, min(len(PIPELINE_STAGES) - 1, int(cmd["stage"])))
                    except (TypeError, ValueError):
                        pass
                tag = str(cmd.get("tag") or "AGENT")
                text = str(cmd.get("text") or "")
                self._push_log_locked(tag, text)
                return {"ok": True, "cmd": "work_log", "active_task": self.active_task, "stage": self.pipeline_stage}

        if kind == "speak":
            speaker_raw = str(cmd.get("speaker") or "dafeiyu").strip().lower()
            speaker: SpeakerId = speaker_raw if speaker_raw in PERSONAS else "dafeiyu"  # type: ignore[assignment]
            mood = str(cmd.get("mood") or "lively").strip()[:20]
            raw_text = str(cmd.get("text") or "").replace("@", "").strip()
            chk = self.guard.filter_output(raw_text, persona=speaker)
            if not raw_text or not chk.allowed:
                return {"ok": False, "cmd": "speak", "reason": chk.reason}
            with self._lock:
                self.pipeline_stage = 3
                self._push_log_locked("SPEAK", f"[{PERSONAS[speaker].short_name}] {chk.cleaned_text[:52]}")
            return {
                "ok": True,
                "cmd": "speak",
                "speech_request": (speaker, chk.cleaned_text, mood),
            }

        if kind == "stop":
            with self._lock:
                self.stop_requested = True
                self.active_task = "准备安全收尾并拉取本场直播复盘数据"
                self._push_log_locked("AGENT", "收到停播收尾指令，准备自动下播并落盘统计")
            return {"ok": True, "cmd": "stop", "stop_requested": True}

        if kind == "studio_stage":
            stage_raw = str(cmd.get("stage") or "").strip().lower()
            if stage_raw not in PRODUCTION_STAGE_META:
                return {"ok": False, "cmd": "studio_stage", "error": "invalid_stage"}
            station_name, stage_idx, default_detail, default_mode = PRODUCTION_STAGE_META[stage_raw]
            with self._lock:
                prev_stage = str(self.production.get("stage") or "internet_sea")
                self.production["stage"] = stage_raw
                self.production["stage_title"] = station_name
                self.pipeline_stage = stage_idx
                self.production["stage_change_seq"] = int(self.production.get("stage_change_seq", 0)) + 1

                if isinstance(cmd.get("episode"), str):
                    clean_ep = redact_pii(cmd["episode"]).replace("@", "").strip()[:28]
                    if clean_ep:
                        self.production["episode"] = clean_ep

                if isinstance(cmd.get("detail"), str):
                    clean_detail = redact_pii(cmd["detail"]).replace("@", "").strip()[:64]
                    if clean_detail:
                        self.production["detail"] = clean_detail
                elif stage_raw != prev_stage:
                    self.production["detail"] = default_detail

                raw_prog = cmd.get("progress_pct", cmd.get("progress"))
                if raw_prog is not None:
                    try:
                        self.production["progress_pct"] = max(0, min(100, int(raw_prog)))
                    except (TypeError, ValueError):
                        pass

                raw_mode = cmd.get("monitor_mode", cmd.get("mode"))
                if isinstance(raw_mode, str) and raw_mode.strip().lower() in ("poll", "preview"):
                    self.production["monitor_mode"] = raw_mode.strip().lower()
                elif stage_raw != prev_stage:
                    self.production["monitor_mode"] = default_mode

                if "preview_paths" in cmd and isinstance(cmd["preview_paths"], (list, tuple)):
                    safe_paths = []
                    for item in cmd["preview_paths"]:
                        sp = _sanitize_preview_path(str(item))
                        if sp and sp not in safe_paths:
                            safe_paths.append(sp)
                    self.production["preview_paths"] = safe_paths[:8]

                if isinstance(cmd.get("preview_caption"), str):
                    clean_cap = redact_pii(cmd["preview_caption"]).replace("@", "").strip()[:56]
                    if clean_cap:
                        self.production["preview_caption"] = clean_cap

                if "code_lines" in cmd and isinstance(cmd["code_lines"], (list, tuple)):
                    clean_lines = [
                        redact_pii(str(ln)).replace("@", "").strip()[:68]
                        for ln in cmd["code_lines"]
                        if redact_pii(str(ln)).replace("@", "").strip()
                    ]
                    self.production["code_lines"] = clean_lines[:6]

                raw_poll = cmd.get("topic_poll")
                if isinstance(raw_poll, dict):
                    poll_obj = self.production["topic_poll"]
                    if isinstance(raw_poll.get("question"), str):
                        clean_q = redact_pii(raw_poll["question"]).replace("@", "").strip()[:48]
                        if clean_q:
                            poll_obj["question"] = clean_q
                    raw_opts = raw_poll.get("options")
                    if isinstance(raw_opts, (list, tuple)) and raw_opts:
                        parsed_labels: List[str] = []
                        for opt_item in raw_opts[:3]:
                            if isinstance(opt_item, dict):
                                raw_lbl = str(opt_item.get("label") or "")
                            else:
                                raw_lbl = str(opt_item or "")
                            clean_lbl = redact_pii(raw_lbl).replace("@", "").strip()[:22]
                            if clean_lbl:
                                parsed_labels.append(clean_lbl)
                        if parsed_labels:
                            keys = ("A", "B", "C")
                            cur_labels = [str(o.get("label") or "") for o in poll_obj["options"]]
                            if parsed_labels != cur_labels:
                                self._topic_votes.clear()
                                poll_obj["options"] = [
                                    {"key": keys[i], "label": lbl, "votes": 0} for i, lbl in enumerate(parsed_labels)
                                ]
                                poll_obj["total_votes"] = 0

                # Dispatch all 3 hosts smoothly along the corridor to this stage's building doorway
                self._dispatch_hosts_to_station_locked(station_name, stage_raw)
                self._stage_focus_until_sec = self.world_time_sec + 35.0

                ep_str = str(self.production["episode"])
                det_str = str(self.production["detail"])
                prog_val = int(self.production["progress_pct"])
                self.active_task = f"[{station_name}] {ep_str} · {det_str}"[:56]
                self._push_log_locked("STAGE", f"切换至「{station_name}」({prog_val}%)：{det_str[:38]}")
                sx, sy, _, accent = STATIONS[station_name]
                door_y = 266.0 if sy < 280 else 320.0
                self._add_popup_locked(f"▶ 切换:{station_name}", float(sx), door_y - 24.0, accent)
                return {
                    "ok": True,
                    "cmd": "studio_stage",
                    "stage": stage_raw,
                    "stage_title": station_name,
                    "pipeline_stage": self.pipeline_stage,
                    "stage_change_seq": self.production["stage_change_seq"],
                    "monitor_mode": self.production["monitor_mode"],
                }

        if kind == "world_action":
            action = str(cmd.get("action") or "").strip().lower()
            with self._lock:
                if action == "spawn_worker":
                    alias = self.guard.sanitize_alias(str(cmd.get("user_alias") or "热心工友")).replace("@", "").strip()
                    station = str(cmd.get("station") or "互联网热点海")
                    if station not in STATIONS:
                        station = PRODUCTION_STAGE_TO_STATION.get(
                            str(self.production.get("stage") or "internet_sea"), "互联网热点海"
                        )
                    label = redact_pii(str(cmd.get("task_label") or "热心施工")).replace("@", "").strip()[:14]
                    mem = self.memory.record_action(alias, points=10, action_delta=1, message=False, now=now)
                    actor = self._spawn_or_move_viewer_locked(
                        alias,
                        station=station,
                        action_label=label,
                        tier=str(mem.get("tier") or "新伙伴"),
                        badge=str(mem.get("badge") or ""),
                    )
                    self._add_popup_locked(f"{alias} 开工!", actor.x, actor.y - 36, (37, 99, 235))
                    self._push_log_locked("WORLD", f"派发工友 {alias} 前往 {station}")
                    return {"ok": True, "action": action, "alias": alias}

                if action == "build_upgrade":
                    xp = max(5, int(cmd.get("xp") or 40))
                    code_add = max(0, int(cmd.get("code_pts") or xp))
                    comp_add = max(0, int(cmd.get("compute_pts") or xp // 2))
                    self.code_pts += code_add
                    self.compute_pts += comp_add
                    self.build_xp += xp
                    self.countdown_sec += 180.0
                    upgraded = self._recompute_level_locked()
                    self._push_log_locked(
                        "CODE",
                        upgraded or f"Agent 完成实操构建：代码 +{code_add} / 算力 +{comp_add}，续命 +180s",
                    )
                    return {"ok": True, "action": action, "level": self.level, "build_xp": self.build_xp}

                if action == "trigger_event":
                    title = redact_pii(str(cmd.get("title") or "")).replace("@", "").strip()[:24]
                    desc = redact_pii(str(cmd.get("desc") or "")).replace("@", "").strip()[:56]
                    if not title:
                        preset_t, preset_d = _CRISIS_PRESETS[self._crisis_cursor % len(_CRISIS_PRESETS)]
                        self._crisis_cursor += 1
                        title, desc = preset_t, desc or preset_d
                    elif not desc:
                        desc = "发「修Bug」或「写代码」协助 Agent 抢修 +300s！"
                    self.active_event = {"title": title, "desc": desc}
                    self._crisis_started_at_sec = self.world_time_sec
                    self._next_crisis_at_sec = self.world_time_sec + 240.0
                    self._push_log_locked("ALERT", f"突发事件：{title} — {desc}")
                    return {"ok": True, "action": action, "title": title}

                if action == "resolve_event":
                    prev = self.active_event["title"] if self.active_event else "例行巡检"
                    self.active_event = None
                    self._crisis_started_at_sec = None
                    self._next_crisis_at_sec = self.world_time_sec + CRISIS_COOLDOWN_SEC
                    self.countdown_sec += 300.0
                    self.compute_pts += 20
                    self.build_xp += 20
                    self._recompute_level_locked()
                    self.banner_text = f"Agent 已亲手修复「{prev}」！工坊续命 +300 秒！"
                    self._banner_until_ts = now + 8.0
                    self._push_log_locked("FIX", f"完成抢修「{prev}」，工坊恢复满血 (+300s)")
                    return {"ok": True, "action": action, "resolved": prev}

                if action == "add_time":
                    sec = max(10.0, float(cmd.get("seconds") or 180.0))
                    self.countdown_sec += sec
                    self._push_log_locked("WORLD", f"工坊供能补充 +{int(sec)} 秒")
                    return {"ok": True, "action": action, "countdown_sec": round(self.countdown_sec, 1)}

                if action == "accept_suggestion":
                    target_id = str(cmd.get("suggestion_id") or "").strip().upper()
                    chosen: Optional[Dict[str, Any]] = None
                    for item in self.suggestions:
                        if target_id and item.get("id") == target_id:
                            chosen = item
                            break
                        if not target_id and item.get("status") == "待采纳":
                            chosen = item
                            break
                    if chosen is None:
                        return {"ok": False, "action": action, "error": "no_matching_suggestion"}
                    chosen["status"] = "已采纳"
                    author = str(chosen.get("author") or "热心观众")
                    self.memory.grant_badge(author, "建议采纳官", bonus_score=40)
                    if author in self.viewer_actors:
                        self.viewer_actors[author].badge = "建议采纳官"
                    self.countdown_sec += 240.0
                    self.build_xp += 35
                    self.pipeline_stage = 1
                    self.active_task = f"执行建议 {chosen['id']}：{chosen['text'][:26]}"
                    self.banner_text = f"采纳 {author} 的建议「{chosen['text'][:18]}」！授予建议采纳官！"
                    self._banner_until_ts = now + 10.0
                    self._recompute_level_locked()
                    self._push_log_locked("AGENT", f"采纳「{author}」建议 {chosen['id']}：{chosen['text'][:22]}")
                    return {"ok": True, "action": action, "suggestion_id": chosen["id"], "author": author}

                if action == "announce":
                    banner = redact_pii(str(cmd.get("text") or "")).replace("@", "").strip()[:64]
                    if not banner:
                        return {"ok": False, "action": action, "error": "empty_banner"}
                    self.banner_text = banner
                    self._banner_until_ts = now + 10.0
                    self._push_log_locked("ANNOUNCE", banner)
                    return {"ok": True, "action": action, "banner": banner}

                return {"ok": False, "action": action, "error": "unknown_world_action"}

        return {"ok": False, "cmd": kind, "error": "unknown_command"}

    def get_active_banner(self, *, now: Optional[float] = None) -> str:
        ts = time.time() if now is None else float(now)
        with self._lock:
            if not self.banner_text or ts > self._banner_until_ts:
                return ""
            return self.banner_text

    def export_state_dict(self) -> Dict[str, Any]:
        """Export a clean zero-PII JSON snapshot for monitoring and Agent inspection."""
        with self._lock:
            next_lvl_xp = self.build_xp
            for _lvl, req_xp, _name in LEVEL_THRESHOLDS:
                if req_xp > self.build_xp:
                    next_lvl_xp = req_xp
                    break
            return {
                "timestamp": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(),
                "telemetry": {
                    "online": self.online,
                    "max_online": self.max_online,
                    "watched_num": self.watched_num,
                    "max_watched_num": self.max_watched_num,
                    "watched_text": self.watched_text,
                    "follower_count": self.follower_count,
                    "follower_goal": self.follower_goal,
                    "follower_delta": max(0, self.follower_count - self.initial_followers),
                },
                "world": {
                    "level": self.level,
                    "level_name": self.level_name,
                    "build_xp": self.build_xp,
                    "next_level_xp": next_lvl_xp,
                    "countdown_sec": int(round(self.countdown_sec)),
                    "countdown_hhmmss": _fmt_hhmmss(self.countdown_sec),
                    "code_pts": self.code_pts,
                    "compute_pts": self.compute_pts,
                    "rice_bowls": self.rice_bowls,
                    "active_event": dict(self.active_event) if self.active_event else None,
                    "active_banner": self.get_active_banner(),
                    "active_worker_count": len(self.viewer_actors),
                    "total_known_viewers": self.memory.total_viewers(),
                    "ambient_bots": [
                        {
                            "bot_id": b.bot_id,
                            "name": b.name,
                            "station": b.station,
                            "action": b.action_label,
                        }
                        for b in self.ambient_bots
                    ],
                    "workers": [
                        {
                            "alias": v.alias,
                            "station": v.station,
                            "action": v.action_label,
                            "tier": v.tier,
                            "badge": v.badge,
                        }
                        for v in self.viewer_actors.values()
                    ],
                },
                "workbench": {
                    "active_task": self.active_task,
                    "pipeline_stage": self.pipeline_stage,
                    "pipeline_label": PIPELINE_STAGES[self.pipeline_stage],
                    "work_log": list(self.work_log),
                },
                "production": {
                    "stage": self.production["stage"],
                    "stage_title": self.production["stage_title"],
                    "episode": self.production["episode"],
                    "detail": self.production["detail"],
                    "progress_pct": int(self.production["progress_pct"]),
                    "monitor_mode": self.production["monitor_mode"],
                    "preview_paths": list(self.production["preview_paths"]),
                    "preview_caption": self.production["preview_caption"],
                    "code_lines": list(self.production["code_lines"]),
                    "topic_poll": {
                        "question": self.production["topic_poll"]["question"],
                        "options": [dict(o) for o in self.production["topic_poll"]["options"]],
                        "total_votes": int(self.production["topic_poll"]["total_votes"]),
                    },
                    "stage_change_seq": int(self.production["stage_change_seq"]),
                },
                "top_builders": self.memory.top_contributors(limit=5),
                "suggestions": list(self.suggestions),
                "recent_danmaku": list(self.recent_danmaku)[-8:],
                "stop_requested": self.stop_requested,
            }


_ALLOWED_BRAIN_ACTIONS: Final[frozenset[str]] = frozenset(
    {"accept_suggestion", "resolve_event", "build_upgrade", "announce"}
)
_ALLOWED_BRAIN_MOODS: Final[frozenset[str]] = frozenset(
    {"lively", "hype", "teasing", "smug", "shocked", "grateful", "focused"}
)


def _strip_json_code_fence(raw: str) -> str:
    cleaned = (raw or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


class AutonomousWorldBrain:
    """24/7 DeepSeek-powered autonomous agent controller that drives LiveAgentWorld safely."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        interval_sec: float = 75.0,
        timeout_sec: float = 15.0,
        max_calls: Optional[int] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        resolved_key = (
            api_key
            if api_key is not None
            else (os.getenv("LIVE_LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY") or "")
        )
        self._api_key = resolved_key.strip()
        self.base_url = (
            base_url or os.getenv("LIVE_LLM_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL") or DEFAULT_LLM_BASE_URL
        ).rstrip("/")
        self.model = (model or os.getenv("LIVE_LLM_MODEL") or DEFAULT_LLM_MODEL).strip()
        self.interval_sec = max(1.0, float(interval_sec))
        self.timeout_sec = max(2.0, float(timeout_sec))
        self.max_calls: Optional[int] = None if max_calls is None else max(0, int(max_calls))
        self.calls_made: int = 0
        self._external_client = http_client
        self.guard = LiveComplianceGuard()

    @property
    def has_api_key(self) -> bool:
        return bool(self._api_key)

    def __repr__(self) -> str:
        return (
            f"AutonomousWorldBrain(base_url={self.base_url!r}, model={self.model!r}, "
            f"interval_sec={self.interval_sec!r}, configured={self.has_api_key}, "
            f"calls_made={self.calls_made}, max_calls={self.max_calls})"
        )

    def sanitize_and_build_commands(self, decision: Dict[str, Any], state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Validate LLM JSON decision into safe `apply_agent_command` dicts (never accepts stop)."""
        if not isinstance(decision, dict):
            return []

        commands: List[Dict[str, Any]] = []
        raw_world = state.get("world")
        world_data: Dict[str, Any] = raw_world if isinstance(raw_world, dict) else {}
        raw_wb = state.get("workbench")
        wb_data: Dict[str, Any] = raw_wb if isinstance(raw_wb, dict) else {}

        raw_task = redact_pii(str(decision.get("task") or "")).replace("@", "").strip()[:52]
        raw_log = redact_pii(str(decision.get("log_text") or "")).replace("@", "").strip()[:72]
        raw_tag = re.sub(r"[^A-Za-z]", "", str(decision.get("tag") or "BRAIN")).upper()[:8] or "BRAIN"
        try:
            stage_idx = max(0, min(len(PIPELINE_STAGES) - 1, int(decision.get("stage", 0))))
        except (TypeError, ValueError):
            stage_idx = 0

        if raw_task or raw_log:
            commands.append(
                {
                    "cmd": "work_log",
                    "task": raw_task or str(wb_data.get("active_task") or "巡检活工坊"),
                    "stage": stage_idx,
                    "tag": raw_tag,
                    "text": raw_log or raw_task,
                }
            )

        wa = decision.get("world_action")
        if isinstance(wa, dict):
            act = str(wa.get("action") or "").strip().lower()
            if act in _ALLOWED_BRAIN_ACTIONS:
                if act == "accept_suggestion":
                    raw_sugs = state.get("suggestions")
                    sugs: List[Any] = raw_sugs if isinstance(raw_sugs, list) else []
                    has_open = any(isinstance(s, dict) and s.get("status") == "待采纳" for s in sugs)
                    if has_open:
                        sid = str(wa.get("suggestion_id") or "").strip().upper()[:12]
                        cmd_wa: Dict[str, Any] = {"cmd": "world_action", "action": "accept_suggestion"}
                        if sid:
                            cmd_wa["suggestion_id"] = sid
                        commands.append(cmd_wa)
                elif act == "resolve_event":
                    if isinstance(world_data.get("active_event"), dict):
                        commands.append({"cmd": "world_action", "action": "resolve_event"})
                elif act == "build_upgrade":
                    try:
                        xp = max(5, min(35, int(wa.get("xp", 18))))
                    except (TypeError, ValueError):
                        xp = 18
                    try:
                        code_pts = max(0, min(35, int(wa.get("code_pts", xp))))
                    except (TypeError, ValueError):
                        code_pts = xp
                    try:
                        comp_pts = max(0, min(25, int(wa.get("compute_pts", xp // 2))))
                    except (TypeError, ValueError):
                        comp_pts = xp // 2
                    commands.append(
                        {
                            "cmd": "world_action",
                            "action": "build_upgrade",
                            "xp": xp,
                            "code_pts": code_pts,
                            "compute_pts": comp_pts,
                        }
                    )
                elif act == "announce":
                    raw_banner = str(wa.get("text") or "").replace("@", "").strip()[:60]
                    chk = self.guard.filter_output(raw_banner)
                    if raw_banner and chk.allowed and chk.cleaned_text:
                        commands.append({"cmd": "world_action", "action": "announce", "text": chk.cleaned_text})

        sp = decision.get("speech")
        if isinstance(sp, dict):
            raw_speaker = str(sp.get("speaker") or "dafeiyu").strip().lower()
            speaker: SpeakerId = raw_speaker if raw_speaker in PERSONAS else "dafeiyu"  # type: ignore[assignment]
            raw_mood = str(sp.get("mood") or "lively").strip().lower()
            mood = raw_mood if raw_mood in _ALLOWED_BRAIN_MOODS else "lively"
            raw_speech = str(sp.get("text") or "").replace("@", "").strip()[:65]
            if raw_speech:
                chk_sp = self.guard.filter_output(raw_speech, persona=speaker)
                if chk_sp.allowed and chk_sp.cleaned_text:
                    commands.append(
                        {
                            "cmd": "speak",
                            "speaker": speaker,
                            "mood": mood,
                            "text": chk_sp.cleaned_text,
                        }
                    )

        return commands

    async def decide_next_actions(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Query DeepSeek Chat in JSON mode to pick the next safe autonomous workshop action."""
        if not self.has_api_key:
            return []
        if self.max_calls is not None and self.calls_made >= self.max_calls:
            return []

        summary = format_world_context_summary(state)
        sys_prompt = (
            "你是正在B站「2D AI 活工坊」直播间24小时自主打工、写代码和接待弹幕的 AI 总工程师。"
            "请根据实时工坊状态，严格返回单个 JSON 对象（不要 Markdown 代码块，不要任何 @用户名 或个人隐私）：\n"
            "{\n"
            '  "task": "18字以内当前工作台在忙的具体工程任务",\n'
            '  "stage": 0到3整数(0热点海,1抓角色,2可灵房,3剪辑厅),\n'
            '  "tag": "AGENT|CODE|FIX|IDEA|BUILD之一",\n'
            '  "log_text": "38字以内具体推进日志",\n'
            '  "world_action": {"action": "accept_suggestion|resolve_event|build_upgrade|announce|none", "xp": 15, "text": "可选横幅"},\n'
            '  "speech": {"speaker": "dafeiyu|gemini|yowane之一", "mood": "lively|hype|teasing|focused之一", "text": "45字以内播报一句或留空"}\n'
            "}\n"
            "规则：若有待采纳建议优先用 accept_suggestion；若有突发警报且适合救援可用 resolve_event；"
            "平时推进工程用 build_upgrade（xp 填 10 到 25）。禁止使用任何未列出的 action。"
        )
        user_msg = f"当前工坊实时状态：\n{summary}\n请给出下一步工坊执行指令 JSON。"

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_msg},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 280,
            "temperature": 0.7,
        }

        try:
            self.calls_made += 1
            if self._external_client is not None:
                resp = await self._external_client.post(url, headers=headers, json=body, timeout=self.timeout_sec)
            else:
                async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
                    resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            payload = resp.json()
            raw_content = str(payload["choices"][0]["message"]["content"]).strip()
            parsed = json.loads(_strip_json_code_fence(raw_content))
            if not isinstance(parsed, dict):
                return []
            return self.sanitize_and_build_commands(parsed, state)
        except Exception as exc:
            logger.warning("AutonomousWorldBrain tick skipped (%s)", type(exc).__name__)
            return []


_WORLD_BG_RELS_BY_LEVEL: Final[Dict[int, Tuple[str, ...]]] = {
    1: ("projects/015_gemini_neko_cyber_worker_vlog/assets/neko_clean_desk_bg_16x9.jpg", DEFAULT_STUDIO_BG_REL),
    2: ("library/scenes/cyber_idol_whale_stage.jpg", DEFAULT_STUDIO_BG_REL),
    3: ("library/scenes/cyber_idol_whale_stage.jpg", DEFAULT_STUDIO_BG_REL),
    4: ("library/scenes/cyber_idol_whale_stage.jpg", DEFAULT_STUDIO_BG_REL),
}
_CAM_CROP_RATIO_BY_SPEAKER: Final[Dict[SpeakerId, float]] = {
    "dafeiyu": 0.44,
    "gemini": 0.88,
    "yowane": 0.68,
}


def _crop_cover_rgba(img: Image.Image, target_w: int, target_h: int, *, upper_ratio: float = 0.8) -> Image.Image:
    bbox = img.getbbox()
    cropped = img.crop(bbox) if bbox is not None else img
    w, h = cropped.size
    keep_h = max(16, int(round(h * max(0.25, min(1.0, upper_ratio)))))
    torso = cropped.crop((0, 0, w, min(h, keep_h)))
    tw, th = torso.size
    scale = min(target_w / float(tw), target_h / float(th)) * 1.06
    nw = max(16, int(round(tw * scale)))
    nh = max(16, int(round(th * scale)))
    resized = torso.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    px = (target_w - nw) // 2
    py = max(0, target_h - nh)
    canvas.paste(resized, (px, py), resized)
    return canvas


def _draw_radial_halo(
    size: Tuple[int, int], center: Tuple[int, int], radius: int, color: Tuple[int, int, int], alpha_peak: int = 92
) -> Image.Image:
    w, h = size
    cx, cy = center
    r = max(16, int(radius))
    x0, x1 = max(0, cx - r), min(w, cx + r)
    y0, y1 = max(0, cy - r), min(h, cy + r)
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if x1 <= x0 or y1 <= y0:
        return layer
    yy, xx = np.ogrid[y0:y1, x0:x1]
    dist = np.sqrt(((xx - cx) / float(r)) ** 2 + ((yy - cy) / float(r)) ** 2)
    strength = np.clip(1.0 - dist, 0.0, 1.0) ** 1.8
    patch = np.zeros((y1 - y0, x1 - x0, 4), dtype=np.uint8)
    patch[:, :, 0] = color[0]
    patch[:, :, 1] = color[1]
    patch[:, :, 2] = color[2]
    patch[:, :, 3] = np.clip(strength * alpha_peak, 0, 255).astype(np.uint8)
    layer.paste(Image.fromarray(patch, mode="RGBA"), (x0, y0))
    return layer


class WorldStageRenderer:
    """High-speed 1920x1080 @ 30 FPS cyber VTuber studio + 2D interactive workshop renderer."""

    def __init__(
        self,
        *,
        width: int = STAGE_WIDTH,
        height: int = STAGE_HEIGHT,
        fps: int = DEFAULT_FPS,
        repo_root: Optional[Path] = None,
        world: Optional[LiveAgentWorld] = None,
        follower_count: int = 15,
        follower_goal: int = 1000,
        show_title: str = "AI活工坊 · 发「开工」一起建世界",
        font_path: Optional[Path] = None,
        cast: Sequence[SpeakerId] = TRIO_CAST,
    ) -> None:
        self.width = width
        self.height = height
        self.fps = max(1, int(fps))
        self._explicit_repo_root = repo_root is not None
        self.repo_root = Path(repo_root) if repo_root is not None else REPO_ROOT
        self._asset_roots: List[Path] = [self.repo_root]
        if not self._explicit_repo_root:
            main_root = _discover_git_main_repo_root(self.repo_root)
            if main_root is not None and main_root not in self._asset_roots:
                self._asset_roots.append(main_root)

        self.world = world or LiveAgentWorld(follower_count=follower_count, follower_goal=follower_goal, cast=cast)
        normalized_cast = [sid for sid in cast if sid in PERSONAS]
        self.cast: Tuple[SpeakerId, ...] = tuple(normalized_cast) if normalized_cast else TRIO_CAST
        self.show_title = redact_pii(show_title).replace("@", "").strip()[:24] or "AI活工坊直播"

        self.font_path: Optional[Path] = font_path or resolve_cjk_font_path()
        self._font_xl = _load_font(self.font_path, 34)
        self._font_lg = _load_font(self.font_path, 25)
        self._font_md = _load_font(self.font_path, 20)
        self._font_sm = _load_font(self.font_path, 16)
        self._font_xs = _load_font(self.font_path, 14)
        self._font_sub = _load_font(self.font_path, 31)

        self.loaded_assets: Dict[str, str] = {}
        self._host_tokens: Dict[SpeakerId, Image.Image] = {
            sid: self._build_character_token(sid, size=34) for sid in self.cast
        }
        self._dock_portraits: Dict[SpeakerId, Image.Image] = {
            sid: self._build_character_token(sid, size=116) for sid in self.cast
        }
        self._cam_portraits: Dict[SpeakerId, Optional[Image.Image]] = {
            sid: self._build_cam_portrait(sid, card_w=144, card_h=178) for sid in self.cast
        }
        self._viewer_tokens: Dict[int, Image.Image] = {
            idx: self._build_viewer_token(rgb, size=38) for idx, rgb in enumerate(_VIEWER_AVATAR_COLORS)
        }
        self._bot_tokens: Dict[Tuple[int, int, int], Image.Image] = {
            (14, 165, 233): self._build_bot_token((14, 165, 233), size=36),
            (245, 158, 11): self._build_bot_token((245, 158, 11), size=36),
        }
        self._bg_by_level: Dict[int, Image.Image] = {}
        self._stage_canvas_cache: Dict[Tuple[int, SpeakerId], Image.Image] = {}
        self._static_bg: Image.Image = self._get_stage_canvas(1, self.cast[0])
        self._world_level_layers: Dict[Tuple[int, str], Image.Image] = {}
        self._preview_slide_cache: Dict[Tuple[str, int, int, int], Image.Image] = {}

        # Per-section frame caches keep steady-state render time < 15 ms/frame at 1080p
        self._telemetry_key: Tuple[Any, ...] = ()
        self._telemetry_overlay: Optional[Image.Image] = None

        self._countdown_key: Tuple[int, bool] = (-1, False)
        self._countdown_overlay: Optional[Image.Image] = None

        self._world_hud_key: Tuple[Any, ...] = ()
        self._world_hud_overlay: Optional[Image.Image] = None

        self._monitor_key: Tuple[Any, ...] = ()
        self._monitor_overlay: Optional[Image.Image] = None
        self._monitor_cursor_pos: Optional[Tuple[int, int]] = None

        self._workbench_key: Tuple[Any, ...] = ()
        self._workbench_overlay: Optional[Image.Image] = None

        self._right_key: Tuple[Any, ...] = ()
        self._right_overlay: Optional[Image.Image] = None

        self._subtitle_key: Tuple[Any, ...] = ()
        self._subtitle_overlay: Optional[Image.Image] = None

        self._frame_base_key: Tuple[Any, ...] = ()
        self._frame_base_rgb: Optional[Image.Image] = None

    def _find_asset(self, rel_path: str) -> Optional[Path]:
        for root in self._asset_roots:
            candidate = root / rel_path
            if candidate.is_file():
                return candidate
        return None

    def _build_character_token(self, speaker_id: SpeakerId, *, size: int = 56) -> Image.Image:
        accent = SPEAKER_ACCENT_RGB.get(speaker_id, (37, 99, 235))
        cutout_path = self._find_asset(CHARACTER_CUTOUT_RELS[speaker_id])
        canonical_path = self._find_asset(CHARACTER_CANONICAL_RELS[speaker_id])

        src: Optional[Image.Image] = None
        for p, kind in ((cutout_path, "cutout"), (canonical_path, "canonical")):
            if p is None:
                continue
            try:
                with Image.open(p) as raw:
                    rgba = raw.convert("RGBA")
                    bbox = rgba.getbbox()
                    if bbox is not None:
                        rgba = rgba.crop(bbox)
                    w, h = rgba.size
                    crop_h = min(h, max(1, int(w * 1.02)))
                    face_crop = rgba.crop((0, 0, w, crop_h))
                    bg_circle = Image.new("RGBA", face_crop.size, (18, 28, 56, 255))
                    bg_circle.paste(face_crop, (0, 0), face_crop)
                    src = bg_circle.convert("RGB").resize((size, size), Image.Resampling.LANCZOS)
                    self.loaded_assets[f"{speaker_id}_{size}"] = f"{kind}:{p}"
                    break
            except Exception:
                continue

        if src is None:
            src = Image.new("RGB", (size, size), accent)
            d = ImageDraw.Draw(src)
            short = PERSONAS[speaker_id].short_name[0]
            d.text((size // 2, size // 2), short, font=self._font_lg, fill=(255, 255, 255), anchor="mm")
            self.loaded_assets[f"{speaker_id}_{size}"] = "vector_fallback"

        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse([(1, 1), (size - 2, size - 2)], fill=255)
        out = Image.new("RGBA", (size + 8, size + 8), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(out)
        odraw.ellipse([(0, 0), (size + 7, size + 7)], fill=(*accent, 255))
        odraw.ellipse([(2, 2), (size + 5, size + 5)], fill=(224, 242, 254, 240))
        out.paste(src.convert("RGBA"), (4, 4), mask)
        return out

    def _build_cam_portrait(
        self, speaker_id: SpeakerId, *, card_w: int = 144, card_h: int = 178
    ) -> Optional[Image.Image]:
        cutout_path = self._find_asset(CHARACTER_CUTOUT_RELS[speaker_id])
        if cutout_path is None:
            return None
        upper_ratio = _CAM_CROP_RATIO_BY_SPEAKER.get(speaker_id, 0.78)
        try:
            with Image.open(cutout_path) as raw:
                rgba = raw.convert("RGBA")
                framed = _crop_cover_rgba(rgba, card_w - 8, card_h - 32, upper_ratio=upper_ratio)
                self.loaded_assets[f"cam_{speaker_id}"] = str(cutout_path)
                return framed
        except Exception:
            return None

    def _build_viewer_token(self, rgb: Tuple[int, int, int], *, size: int = 38) -> Image.Image:
        out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(out)
        cx = size // 2
        d.ellipse([(3, size - 9), (size - 4, size - 1)], fill=(2, 6, 23, 120))
        d.rounded_rectangle(
            [(8, 16), (size - 9, size - 4)], radius=7, fill=(*rgb, 255), outline=(224, 242, 254, 255), width=2
        )
        d.ellipse([(9, 4), (size - 10, 21)], fill=(255, 241, 224, 255), outline=(30, 41, 59, 240), width=2)
        d.pieslice(
            [(8, 2), (size - 9, 17)], start=180, end=360, fill=(*rgb, 255), outline=(255, 255, 255, 255), width=2
        )
        d.ellipse([(cx - 5, 11), (cx - 2, 14)], fill=(15, 23, 42, 255))
        d.ellipse([(cx + 2, 11), (cx + 5, 14)], fill=(15, 23, 42, 255))
        return out

    def _build_bot_token(self, rgb: Tuple[int, int, int], *, size: int = 36) -> Image.Image:
        out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(out)
        cx = size // 2
        d.ellipse([(4, size - 8), (size - 5, size - 1)], fill=(2, 6, 23, 110))
        d.line([(cx, 1), (cx, 7)], fill=(148, 163, 184, 255), width=2)
        d.ellipse([(cx - 3, 0), (cx + 3, 6)], fill=(*rgb, 255))
        d.rounded_rectangle([(8, 7), (size - 9, 22)], radius=6, fill=(241, 245, 249, 255), outline=(*rgb, 255), width=2)
        d.rounded_rectangle([(11, 11), (size - 12, 17)], radius=3, fill=(15, 23, 42, 255))
        d.ellipse([(cx - 5, 12), (cx - 2, 15)], fill=(56, 189, 248, 255))
        d.ellipse([(cx + 2, 12), (cx + 5, 15)], fill=(56, 189, 248, 255))
        d.rounded_rectangle(
            [(10, 22), (size - 11, size - 4)], radius=5, fill=(*rgb, 255), outline=(224, 242, 254, 255), width=2
        )
        return out

    def _build_cyber_gradient_bg(self) -> Image.Image:
        y = np.linspace(0.0, 1.0, self.height, dtype=np.float32)[:, None]
        x = np.linspace(0.0, 1.0, self.width, dtype=np.float32)[None, :]
        r = 12.0 + 26.0 * (1.0 - y) * x + 14.0 * y
        g = 18.0 + 22.0 * (1.0 - y) + 18.0 * (1.0 - x)
        b = 42.0 + 38.0 * (1.0 - y * 0.6) + 22.0 * np.sin(x * math.pi)
        rgb = np.stack([r, g, b], axis=-1).clip(0, 255).astype(np.uint8)
        return Image.fromarray(rgb, mode="RGB")

    def _get_level_bg(self, level: int) -> Image.Image:
        lvl = max(1, min(4, int(level)))
        if lvl in self._bg_by_level:
            return self._bg_by_level[lvl]

        bg_img: Optional[Image.Image] = None
        for rel in _WORLD_BG_RELS_BY_LEVEL.get(lvl, (DEFAULT_STUDIO_BG_REL,)):
            bg_path = self._find_asset(rel)
            if bg_path is None:
                continue
            try:
                with Image.open(bg_path) as raw:
                    rgb = raw.convert("RGB")
                    sw, sh = rgb.size
                    sc = max(self.width / sw, self.height / sh)
                    resized = rgb.resize((int(round(sw * sc)), int(round(sh * sc))), Image.Resampling.LANCZOS)
                    cropped = resized.crop(
                        (
                            (resized.width - self.width) // 2,
                            (resized.height - self.height) // 2,
                            (resized.width - self.width) // 2 + self.width,
                            (resized.height - self.height) // 2 + self.height,
                        )
                    )
                    cropped = cropped.filter(ImageFilter.GaussianBlur(radius=0.8))
                    cropped = ImageEnhance.Color(cropped).enhance(1.10)
                    cropped = ImageEnhance.Brightness(cropped).enhance(0.88)
                    bg_img = cropped
                    self.loaded_assets[f"bg_lv{lvl}"] = str(bg_path)
                    break
            except Exception:
                continue

        if bg_img is None:
            bg_img = self._build_cyber_gradient_bg()
            self.loaded_assets[f"bg_lv{lvl}"] = "cyber_gradient_fallback"

        self._bg_by_level[lvl] = bg_img
        return bg_img

    def _get_stage_canvas(self, level: int, active_speaker: SpeakerId) -> Image.Image:
        lvl = max(1, min(4, int(level)))
        resolved = active_speaker if active_speaker in self.cast else self.cast[0]
        ckey = (lvl, resolved)
        if ckey in self._stage_canvas_cache:
            return self._stage_canvas_cache[ckey]

        canvas = self._get_level_bg(lvl).convert("RGBA")

        # Atmospheric dark-blue veil + top bar frost
        veil = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        vdraw = ImageDraw.Draw(veil)
        vdraw.rectangle([(0, 0), (self.width, self.height)], fill=(8, 13, 30, 52))
        vdraw.rectangle([(0, 0), (self.width, 82)], fill=(7, 11, 24, 155))
        canvas = Image.alpha_composite(canvas, veil)

        chrome = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(chrome)

        # Top-right permanent GB 45438-2025 compliance badge (sleek obsidian-gold glass)
        badge_text = AI_DISCLOSURE_BANNER
        badge_w = int(draw.textlength(badge_text, font=self._font_md)) + 52
        bx0 = max(1340, self.width - 24 - badge_w)
        draw.rounded_rectangle(
            [(bx0, 14), (self.width - 24, 72)],
            radius=18,
            fill=(11, 18, 36, 224),
            outline=(245, 158, 11, 215),
            width=2,
        )
        draw.ellipse([(bx0 + 16, 36), (bx0 + 30, 50)], fill=(16, 185, 129, 255))
        draw.text((bx0 + 40, 31), badge_text, font=self._font_md, fill=(253, 230, 138, 255))

        # Trio Anime VTuber LIVE CAM Showcase Deck (x=822..1310, y=638..876, completely unobstructed!)
        cam_x0, cam_y0, cam_x1, cam_y1 = 822, 638, 1310, 876
        draw.rounded_rectangle(
            [(cam_x0, cam_y0), (cam_x1, cam_y1)],
            radius=22,
            fill=(10, 16, 34, 230),
            outline=(99, 102, 241, 195),
            width=2,
        )
        draw.rounded_rectangle(
            [(cam_x0 + 14, cam_y0 + 10), (cam_x0 + 258, cam_y0 + 36)], radius=10, fill=(23, 37, 84, 225)
        )
        draw.ellipse([(cam_x0 + 24, cam_y0 + 18), (cam_x0 + 34, cam_y0 + 28)], fill=(244, 63, 94, 255))
        draw.text((cam_x0 + 42, cam_y0 + 14), "LIVE CAM · 铁三角演播席", font=self._font_sm, fill=(224, 242, 254, 255))

        card_w, card_h, card_gap = 148, 184, 10
        card_start_x = cam_x0 + 14
        card_y = cam_y0 + 44
        for idx, sid in enumerate(self.cast[:3]):
            cx0 = card_start_x + idx * (card_w + card_gap)
            cx1 = cx0 + card_w
            cy1 = card_y + card_h
            is_act = sid == resolved
            accent = SPEAKER_ACCENT_RGB.get(sid, (56, 189, 248))
            card_bg = (22, 34, 68, 240) if is_act else (13, 20, 40, 215)
            card_rim = (*accent, 255) if is_act else (71, 85, 105, 175)
            draw.rounded_rectangle(
                [(cx0, card_y), (cx1, cy1)], radius=14, fill=card_bg, outline=card_rim, width=2 if is_act else 1
            )

            if is_act:
                halo = _draw_radial_halo(
                    (self.width, self.height), (cx0 + card_w // 2, card_y + 84), 84, accent, alpha_peak=108
                )
                chrome = Image.alpha_composite(chrome, halo)
                draw = ImageDraw.Draw(chrome)

            portrait = self._cam_portraits.get(sid)
            if portrait is not None:
                styled = portrait if is_act else ImageEnhance.Brightness(portrait).enhance(0.76)
                px = cx0 + (card_w - styled.width) // 2
                py = card_y + 4
                chrome.paste(styled, (px, py), styled)
            else:
                tok = self._dock_portraits.get(sid)
                if tok is not None:
                    scaled_tok = tok.resize((92, 92), Image.Resampling.LANCZOS)
                    chrome.paste(scaled_tok, (cx0 + (card_w - 92) // 2, card_y + 28), scaled_tok)

            draw = ImageDraw.Draw(chrome)
            # Clean nameplate pill along bottom of card
            bar_col = (*accent, 242) if is_act else (30, 41, 59, 232)
            draw.rounded_rectangle([(cx0 + 6, cy1 - 28), (cx1 - 6, cy1 - 4)], radius=8, fill=bar_col)
            lbl = f"● {PERSONAS[sid].short_name}" if is_act else PERSONAS[sid].short_name
            draw.text((cx0 + card_w // 2, cy1 - 16), lbl, font=self._font_xs, fill=(255, 255, 255, 255), anchor="mm")

        # Right Unified Frosted Glass Sidebar (x=1330..1896, y=88..876)
        draw.rounded_rectangle(
            [(1330, 88), (1896, 876)],
            radius=22,
            fill=(10, 16, 34, 222),
            outline=(99, 102, 241, 190),
            width=2,
        )
        # Compact 2x2 Keycap Quick-Command Strip at top of sidebar (y=102..216)
        draw.rounded_rectangle(
            [(1346, 102), (1880, 216)],
            radius=16,
            fill=(17, 26, 52, 232),
            outline=(56, 189, 248, 175),
            width=2,
        )
        keycaps: Tuple[Tuple[int, int, str, str, Tuple[int, int, int]], ...] = (
            (1360, 114, "1 / 开工", "领小人", (56, 189, 248)),
            (1614, 114, "A / B / C", "投下期题材", (236, 72, 153)),
            (1360, 164, "修Bug", "续命 +300s", (245, 158, 11)),
            (1614, 164, "建议 xxx", "改剧情", (167, 139, 250)),
        )
        for kx, ky, key_lbl, act_lbl, kcol in keycaps:
            kw = int(draw.textlength(key_lbl, font=self._font_sm)) + 22
            draw.rounded_rectangle(
                [(kx, ky), (kx + kw, ky + 34)],
                radius=9,
                fill=(15, 23, 42, 255),
                outline=(*kcol, 240),
                width=2,
            )
            draw.text((kx + 11, ky + 7), key_lbl, font=self._font_sm, fill=(248, 250, 252, 255))
            draw.text((kx + kw + 10, ky + 7), act_lbl, font=self._font_sm, fill=(203, 213, 225, 255))

        # Bottom Cinema VN Dialogue Dock Shell (x=24..1896, y=888..1062)
        draw.rounded_rectangle(
            [(24, 888), (1896, 1062)],
            radius=24,
            fill=(8, 13, 28, 236),
            outline=(148, 163, 184, 155),
            width=2,
        )
        accent = SPEAKER_ACCENT_RGB.get(resolved, (56, 189, 248))
        draw.rounded_rectangle([(48, 888), (self.width - 48, 892)], radius=2, fill=(*accent, 235))

        out = Image.alpha_composite(canvas, chrome).convert("RGB")
        if len(self._stage_canvas_cache) >= 6:
            oldest_key = next(iter(self._stage_canvas_cache))
            self._stage_canvas_cache.pop(oldest_key, None)
        self._stage_canvas_cache[ckey] = out
        return out

    def _build_static_canvas(self) -> Image.Image:
        return self._get_stage_canvas(1, self.cast[0])

    def _draw_station_icon(
        self, draw: ImageDraw.ImageDraw, st_name: str, cx: int, cy: int, accent: Tuple[int, int, int]
    ) -> None:
        if st_name == "互联网热点海":
            draw.arc([(cx - 10, cy - 8), (cx + 10, cy + 12)], start=200, end=340, fill=(*accent, 255), width=2)
            draw.arc([(cx - 6, cy - 3), (cx + 6, cy + 9)], start=200, end=340, fill=(186, 230, 253, 255), width=2)
            draw.ellipse([(cx - 2, cy + 4), (cx + 2, cy + 8)], fill=(255, 255, 255, 255))
        elif st_name == "角色抓捕屋":
            draw.rounded_rectangle([(cx - 9, cy - 8), (cx + 9, cy + 8)], radius=3, outline=(*accent, 255), width=2)
            draw.ellipse([(cx - 3, cy - 3), (cx + 3, cy + 3)], fill=(253, 164, 175, 255))
        elif st_name == "可灵炼丹房":
            pts = [(cx, cy - 9), (cx + 8, cy), (cx, cy + 9), (cx - 8, cy)]
            draw.polygon(pts, fill=(*accent, 90), outline=(*accent, 255))
            draw.ellipse([(cx - 3, cy - 3), (cx + 3, cy + 3)], fill=(254, 243, 199, 255))
        else:
            draw.rounded_rectangle([(cx - 9, cy - 7), (cx + 9, cy + 7)], radius=3, outline=(*accent, 255), width=2)
            draw.polygon([(cx - 2, cy - 4), (cx + 5, cy), (cx - 2, cy + 4)], fill=(233, 213, 255, 255))

    def _get_world_level_layer(self, level: int, active_stage: str = "internet_sea") -> Image.Image:
        lvl = max(1, min(4, int(level)))
        stage_key = active_stage if active_stage in PRODUCTION_STAGE_TO_STATION else "internet_sea"
        ckey = (lvl, stage_key)
        if ckey in self._world_level_layers:
            return self._world_level_layers[ckey]

        lvl_accents = {
            1: (56, 189, 248),
            2: (99, 102, 241),
            3: (168, 85, 247),
            4: (250, 204, 21),
        }
        ring_col = lvl_accents[lvl]
        active_station = PRODUCTION_STAGE_TO_STATION[stage_key]
        img = Image.new("RGBA", (WORLD_WIDTH, WORLD_HEIGHT), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Outer translucent obsidian cyber deck
        draw.rounded_rectangle(
            [(0, 0), (WORLD_WIDTH - 1, WORLD_HEIGHT - 1)],
            radius=22,
            fill=(7, 11, 24, 118),
            outline=(*ring_col, 215),
            width=2,
        )
        # Left production floor zone frame & blueprint grid (x=14..744, y=78..524)
        draw.rounded_rectangle(
            [(14, 78), (MAP_LEFT_WIDTH, 524)],
            radius=18,
            fill=(8, 14, 30, 118),
            outline=(*ring_col, 130),
            width=1,
        )
        for gx in range(56, MAP_LEFT_WIDTH - 18, 68):
            draw.line([(gx, 86), (gx, 518)], fill=(*ring_col, 28), width=1)
        for gy in range(118, 516, 56):
            draw.line([(20, gy), (MAP_LEFT_WIDTH - 6, gy)], fill=(*ring_col, 28), width=1)

        # Subtle left-zone header pill
        draw.rounded_rectangle([(24, 86), (254, 110)], radius=8, fill=(15, 23, 42, 215), outline=(56, 189, 248, 120))
        draw.text((34, 90), "2D 制片厂平面图 · 实时走位", font=self._font_xs, fill=(186, 230, 253, 255))

        # Sleek luminous circuit traces along CORRIDOR_Y connecting all 4 production buildings
        corridor_y = int(CORRIDOR_Y)
        draw.line([(106, corridor_y), (646, corridor_y)], fill=(56, 189, 248, 145), width=3)
        draw.line([(106, corridor_y), (646, corridor_y)], fill=(186, 230, 253, 95), width=1)
        for sx in (196, 544):
            draw.line([(sx, 205), (sx, 359)], fill=(56, 189, 248, 125), width=2)
            draw.ellipse([(sx - 6, corridor_y - 6), (sx + 6, corridor_y + 6)], fill=(14, 165, 233, 235))
            draw.ellipse([(sx - 3, corridor_y - 3), (sx + 3, corridor_y + 3)], fill=(240, 249, 255, 255))

        # Active building radial halo + laser signal connector to right LIVE monitor (x=754)
        asx, asy, _, a_accent = STATIONS[active_station]
        halo = _draw_radial_halo((WORLD_WIDTH, WORLD_HEIGHT), (asx, asy), 118, a_accent, alpha_peak=104)
        img = Image.alpha_composite(img, halo)
        draw = ImageDraw.Draw(img)

        ax1 = asx + 82
        if asx < 370:
            conn_pts = [(ax1, asy), (370, asy), (370, corridor_y), (MONITOR_X, corridor_y)]
        else:
            conn_pts = [(ax1, asy), (MONITOR_X, asy)]
        draw.line(conn_pts, fill=(*a_accent, 95), width=6)
        draw.line(conn_pts, fill=(*a_accent, 250), width=2)
        end_x, end_y = conn_pts[-1]
        draw.ellipse([(end_x - 6, end_y - 6), (end_x + 6, end_y + 6)], fill=(*a_accent, 255))
        draw.ellipse([(end_x - 3, end_y - 3), (end_x + 3, end_y + 3)], fill=(255, 255, 255, 255))

        # 4 Cyber-glass production building cards (164 x 74 centered on exact STATIONS coords)
        step_codes = ("01", "02", "03", "04")
        for b_idx, (st_name, (sx, sy, st_sub, accent)) in enumerate(STATIONS.items()):
            is_act = st_name == active_station
            x0, y0, x1, y1 = sx - 82, sy - 37, sx + 82, sy + 37
            fill_bg = (14, 24, 52, 242) if is_act else (10, 16, 36, 226)
            border_w = 3 if is_act else 2
            border_col = (*accent, 255) if is_act else (*accent, 185)
            draw.rounded_rectangle([(x0, y0), (x1, y1)], radius=14, fill=fill_bg, outline=border_col, width=border_w)
            draw.rounded_rectangle(
                [(x0 + 3, y0 + 3), (x1 - 3, y0 + 30)],
                radius=11,
                fill=(*accent, 68 if is_act else 34),
            )
            # Mini step icon box + title + subtitle
            draw.rounded_rectangle(
                [(x0 + 10, y0 + 7), (x0 + 34, y0 + 27)],
                radius=6,
                fill=(15, 23, 42, 235),
                outline=(*accent, 230),
                width=1,
            )
            self._draw_station_icon(draw, st_name, x0 + 22, y0 + 17, accent)
            draw.text((x0 + 40, y0 + 8), st_name, font=self._font_sm, fill=(248, 250, 252, 255))
            draw.text(
                (x0 + 12, y0 + 43),
                f"{step_codes[b_idx]} · {st_sub}",
                font=self._font_xs,
                fill=(224, 242, 254, 255) if is_act else (148, 197, 255, 255),
            )
            if is_act:
                pill_w = int(draw.textlength("▶ 当前工序", font=self._font_xs)) + 16
                px0 = x1 - pill_w - 4
                py0 = (y0 - 21) if sy < 280 else (y1 + 1)
                draw.rounded_rectangle(
                    [(px0, py0), (px0 + pill_w, py0 + 21)],
                    radius=9,
                    fill=(*accent, 255),
                    outline=(255, 255, 255, 230),
                    width=1,
                )
                draw.text(
                    (px0 + pill_w // 2, py0 + 10),
                    "▶ 当前工序",
                    font=self._font_xs,
                    fill=(255, 255, 255, 255),
                    anchor="mm",
                )

        if len(self._world_level_layers) >= 16:
            oldest_key = next(iter(self._world_level_layers))
            self._world_level_layers.pop(oldest_key, None)
        self._world_level_layers[ckey] = img
        return img

    def _resolve_preview_image(self, rel_path: str) -> Optional[Path]:
        safe_rel = _sanitize_preview_path(rel_path)
        if not safe_rel:
            return None
        for root in self._asset_roots:
            try:
                resolved_root = root.resolve()
                candidate = (resolved_root / safe_rel).resolve()
                if candidate.is_relative_to(resolved_root) and candidate.is_file():
                    return candidate
            except Exception:
                continue
        return None

    def _get_preview_slide(self, rel_path: str, target_w: int, target_h: int) -> Optional[Image.Image]:
        img_path = self._resolve_preview_image(rel_path)
        if img_path is None:
            return None
        try:
            mtime_ns = img_path.stat().st_mtime_ns
        except OSError:
            return None
        ckey = (str(img_path), mtime_ns, target_w, target_h)
        if ckey in self._preview_slide_cache:
            return self._preview_slide_cache[ckey]
        try:
            with Image.open(img_path) as raw:
                rgb = raw.convert("RGB")
                sw, sh = rgb.size
                scale = max(target_w / float(max(1, sw)), target_h / float(max(1, sh)))
                nw = max(target_w, int(round(sw * scale)))
                nh = max(target_h, int(round(sh * scale)))
                resized = rgb.resize((nw, nh), Image.Resampling.LANCZOS)
                left = (nw - target_w) // 2
                top = (nh - target_h) // 2
                cropped = resized.crop((left, top, left + target_w, top + target_h)).convert("RGBA")
            mask = Image.new("L", (target_w, target_h), 0)
            ImageDraw.Draw(mask).rounded_rectangle([(0, 0), (target_w - 1, target_h - 1)], radius=12, fill=255)
            out = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
            out.paste(cropped, (0, 0), mask)
            if len(self._preview_slide_cache) >= 12:
                oldest = next(iter(self._preview_slide_cache))
                self._preview_slide_cache.pop(oldest, None)
            self._preview_slide_cache[ckey] = out
            return out
        except Exception:
            return None

    def _get_live_monitor_overlay(
        self, prod: Dict[str, Any], t_sec: float
    ) -> Tuple[Image.Image, Optional[Tuple[int, int]]]:
        stage_key = str(prod.get("stage") or "internet_sea")
        stage_title = str(prod.get("stage_title") or PRODUCTION_STAGE_TO_STATION.get(stage_key, "互联网热点海"))
        episode = str(prod.get("episode") or "Ep024 筹备中")
        detail = str(prod.get("detail") or "")
        progress_pct = max(0, min(100, int(prod.get("progress_pct", 15))))
        mode = "preview" if str(prod.get("monitor_mode") or "poll") == "preview" else "poll"
        preview_paths = [str(p) for p in (prod.get("preview_paths") or []) if str(p).strip()]
        preview_caption = str(prod.get("preview_caption") or detail or stage_title)
        code_lines = [str(ln) for ln in (prod.get("code_lines") or []) if str(ln).strip()][:6]
        raw_poll = prod.get("topic_poll")
        poll_obj: Dict[str, Any] = raw_poll if isinstance(raw_poll, dict) else {}
        poll_q = str(poll_obj.get("question") or "下期 Ep024 拍什么？发弹幕 A / B / C 投票！")
        raw_opts = poll_obj.get("options")
        poll_opts: List[Dict[str, Any]] = (
            [o for o in raw_opts if isinstance(o, dict)] if isinstance(raw_opts, list) else []
        )
        total_votes = int(poll_obj.get("total_votes", 0))

        slide_idx = int(t_sec // 4.5) % len(preview_paths) if (mode == "preview" and preview_paths) else 0
        active_slide_path = preview_paths[slide_idx] if (mode == "preview" and preview_paths) else ""

        key = (
            stage_key,
            stage_title,
            episode,
            detail,
            progress_pct,
            mode,
            active_slide_path,
            slide_idx,
            len(preview_paths),
            preview_caption,
            tuple(code_lines),
            poll_q,
            tuple((o.get("key"), o.get("label"), int(o.get("votes", 0))) for o in poll_opts[:3]),
            total_votes,
        )
        if self._monitor_overlay is not None and self._monitor_key == key:
            return self._monitor_overlay, self._monitor_cursor_pos

        stage_station = PRODUCTION_STAGE_TO_STATION.get(stage_key, "互联网热点海")
        stage_accent = STATIONS.get(stage_station, STATIONS["互联网热点海"])[3]

        img = Image.new("RGBA", (MONITOR_W, MONITOR_H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Monitor obsidian glass bezel
        draw.rounded_rectangle(
            [(0, 0), (MONITOR_W - 1, MONITOR_H - 1)],
            radius=18,
            fill=(8, 14, 31, 240),
            outline=(*stage_accent, 230),
            width=2,
        )
        draw.rounded_rectangle([(18, 0), (MONITOR_W - 18, 3)], radius=2, fill=(*stage_accent, 255))

        # Top header bar: LIVE badge + episode + stage chip + progress_pct bar
        draw.rounded_rectangle([(14, 10), (74, 33)], radius=8, fill=(239, 68, 68, 250))
        draw.ellipse([(22, 17), (30, 25)], fill=(255, 255, 255, 255))
        draw.text((35, 13), "LIVE", font=self._font_xs, fill=(255, 255, 255, 255))

        stage_chip_w = int(draw.textlength(stage_title, font=self._font_xs)) + 18
        chip_x0 = MONITOR_W - 14 - stage_chip_w
        draw.rounded_rectangle([(chip_x0, 10), (MONITOR_W - 14, 33)], radius=8, fill=(*stage_accent, 230))
        draw.text(
            (chip_x0 + stage_chip_w // 2, 21),
            stage_title,
            font=self._font_xs,
            fill=(255, 255, 255, 255),
            anchor="mm",
        )

        ep_title = f"制片大屏 · {episode}"
        ep_wrapped = _wrap_text_by_width(draw, ep_title, self._font_sm, max_width=max(80, chip_x0 - 92), max_lines=1)
        draw.text((82, 12), ep_wrapped[0] if ep_wrapped else ep_title, font=self._font_sm, fill=(248, 250, 252, 255))

        # Progress bar row
        bar_x0, bar_x1, bar_y0, bar_y1 = 14, 444, 41, 51
        draw.rounded_rectangle([(bar_x0, bar_y0), (bar_x1, bar_y1)], radius=5, fill=(30, 41, 59, 240))
        fill_w = max(10, int(round((bar_x1 - bar_x0) * (progress_pct / 100.0))))
        draw.rounded_rectangle([(bar_x0, bar_y0), (bar_x0 + fill_w, bar_y1)], radius=5, fill=(*stage_accent, 255))
        draw.text((MONITOR_W - 14, 37), f"{progress_pct}%", font=self._font_sm, fill=(224, 242, 254, 255), anchor="ra")
        draw.line([(14, 58), (MONITOR_W - 14, 58)], fill=(*stage_accent, 85), width=1)

        cursor_pos: Optional[Tuple[int, int]] = None

        if mode == "poll":
            # Question banner (y=66..112)
            draw.rounded_rectangle(
                [(14, 66), (MONITOR_W - 14, 112)],
                radius=12,
                fill=(16, 30, 62, 240),
                outline=(56, 189, 248, 195),
                width=2,
            )
            tot_lbl = f"总票 {total_votes}"
            tot_w = int(draw.textlength(tot_lbl, font=self._font_xs)) + 16
            draw.rounded_rectangle(
                [(MONITOR_W - 22 - tot_w, 77), (MONITOR_W - 22, 101)],
                radius=8,
                fill=(30, 41, 59, 240),
                outline=(56, 189, 248, 160),
                width=1,
            )
            draw.text(
                (MONITOR_W - 22 - tot_w // 2, 89),
                tot_lbl,
                font=self._font_xs,
                fill=(186, 230, 253, 255),
                anchor="mm",
            )
            q_wrapped = _wrap_text_by_width(draw, poll_q, self._font_sm, max_width=MONITOR_W - 58 - tot_w, max_lines=1)
            draw.text((24, 79), q_wrapped[0] if q_wrapped else poll_q, font=self._font_sm, fill=(248, 250, 252, 255))

            # 3 High-Contrast A(Cyan)/B(Pink)/C(Purple) Vote Progress Cards
            max_votes = max((int(o.get("votes", 0)) for o in poll_opts[:3]), default=0)
            card_y = 120
            for idx_opt in range(3):
                if idx_opt < len(poll_opts):
                    opt = poll_opts[idx_opt]
                    okey = str(opt.get("key") or ("A", "B", "C")[idx_opt]).upper()
                    olbl = str(opt.get("label") or f"候选方案 {okey}")
                    ovotes = max(0, int(opt.get("votes", 0)))
                else:
                    okey, olbl = _DEFAULT_POLL_OPTIONS[idx_opt]
                    ovotes = 0
                ocol = _POLL_OPTION_COLORS.get(okey, (14, 165, 233))
                pct = int(round((ovotes * 100.0) / total_votes)) if total_votes > 0 else 0
                is_lead = ovotes > 0 and ovotes == max_votes

                draw.rounded_rectangle(
                    [(14, card_y), (MONITOR_W - 14, card_y + 58)],
                    radius=12,
                    fill=(20, 32, 64, 242) if is_lead else (13, 21, 44, 234),
                    outline=(*ocol, 255 if is_lead else 210),
                    width=3 if is_lead else 2,
                )
                draw.rounded_rectangle([(22, card_y + 10), (60, card_y + 48)], radius=10, fill=(*ocol, 250))
                draw.text((41, card_y + 29), okey, font=self._font_lg, fill=(255, 255, 255, 255), anchor="mm")

                stat_str = f"{ovotes}票 · {pct}%"
                stat_w = int(draw.textlength(stat_str, font=self._font_sm))
                lbl_wrapped = _wrap_text_by_width(
                    draw, olbl, self._font_sm, max_width=max(100, MONITOR_W - 104 - stat_w), max_lines=1
                )
                draw.text(
                    (70, card_y + 9),
                    lbl_wrapped[0] if lbl_wrapped else olbl,
                    font=self._font_sm,
                    fill=(248, 250, 252, 255),
                )
                draw.text(
                    (MONITOR_W - 24, card_y + 9), stat_str, font=self._font_sm, fill=(224, 242, 254, 255), anchor="ra"
                )

                pbar_x0, pbar_x1, pbar_y0, pbar_y1 = 70, MONITOR_W - 24, card_y + 36, card_y + 48
                draw.rounded_rectangle([(pbar_x0, pbar_y0), (pbar_x1, pbar_y1)], radius=6, fill=(30, 41, 59, 240))
                if ovotes > 0 and total_votes > 0:
                    pfw = max(12, int(round((pbar_x1 - pbar_x0) * (ovotes / float(total_votes)))))
                    draw.rounded_rectangle([(pbar_x0, pbar_y0), (pbar_x0 + pfw, pbar_y1)], radius=6, fill=(*ocol, 255))
                else:
                    draw.rounded_rectangle([(pbar_x0, pbar_y0), (pbar_x0 + 10, pbar_y1)], radius=5, fill=(*ocol, 130))
                card_y += 66

            # Bottom 3-line sanitized terminal ticker (y=322..434)
            term_y0, term_y1 = 322, 434
            draw.rounded_rectangle(
                [(14, term_y0), (MONITOR_W - 14, term_y1)],
                radius=12,
                fill=(6, 10, 22, 246),
                outline=(56, 189, 248, 155),
                width=1,
            )
            for idx_d, dcol in enumerate(((244, 63, 94), (245, 158, 11), (16, 185, 129))):
                draw.ellipse([(24 + idx_d * 13, term_y0 + 9), (32 + idx_d * 13, term_y0 + 17)], fill=(*dcol, 230))
            draw.text(
                (68, term_y0 + 6),
                "LIVE TERMINAL · 实时制片日志",
                font=self._font_xs,
                fill=(125, 211, 252, 255),
            )
            term_lines = (
                code_lines[-3:]
                if code_lines
                else [
                    f"$ stage={stage_key} ep={episode}",
                    f"> {detail or stage_title}",
                    f"> waiting danmaku A / B / C ({total_votes} votes)",
                ]
            )
            ly = term_y0 + 30
            for idx_ln, raw_ln in enumerate(term_lines[:3]):
                clean_ln = raw_ln.rstrip("_")
                wrapped = _wrap_text_by_width(draw, clean_ln, self._font_xs, max_width=MONITOR_W - 56, max_lines=1)
                shown = wrapped[0] if wrapped else clean_ln
                lcol = (125, 211, 252, 255) if shown.startswith("$") else (110, 231, 183, 255)
                draw.text((24, ly), shown, font=self._font_xs, fill=lcol)
                if idx_ln == len(term_lines[:3]) - 1:
                    cx = min(MONITOR_W - 26, 24 + int(draw.textlength(shown, font=self._font_xs)) + 4)
                    cursor_pos = (cx, ly)
                ly += 25
        else:
            # Preview mode: Upper viewport (~490x248 at x=14..504, y=66..314) + Lower 4-line CLI terminal
            vp_x0, vp_y0, vp_w, vp_h = 14, 66, MONITOR_W - 28, 248
            vp_x1, vp_y1 = vp_x0 + vp_w, vp_y0 + vp_h
            slide_img = self._get_preview_slide(active_slide_path, vp_w, vp_h) if active_slide_path else None
            if slide_img is not None:
                img.paste(slide_img, (vp_x0, vp_y0), slide_img)
                draw = ImageDraw.Draw(img)
            else:
                draw.rounded_rectangle(
                    [(vp_x0, vp_y0), (vp_x1, vp_y1)],
                    radius=12,
                    fill=(13, 21, 44, 242),
                    outline=(*stage_accent, 190),
                    width=2,
                )
                for gx in range(vp_x0 + 36, vp_x1 - 16, 48):
                    draw.line([(gx, vp_y0 + 8), (gx, vp_y1 - 36)], fill=(*stage_accent, 34), width=1)
                for gy in range(vp_y0 + 32, vp_y1 - 36, 40):
                    draw.line([(vp_x0 + 8, gy), (vp_x1 - 8, gy)], fill=(*stage_accent, 34), width=1)
                draw.ellipse(
                    [(vp_x0 + vp_w // 2 - 26, vp_y0 + 54), (vp_x0 + vp_w // 2 + 26, vp_y0 + 106)],
                    fill=(*stage_accent, 45),
                    outline=(*stage_accent, 230),
                    width=2,
                )
                self._draw_station_icon(draw, stage_station, vp_x0 + vp_w // 2, vp_y0 + 80, stage_accent)
                draw.text(
                    (vp_x0 + vp_w // 2, vp_y0 + 132),
                    f"{stage_title} · 实景样片待同步",
                    font=self._font_md,
                    fill=(248, 250, 252, 255),
                    anchor="mm",
                )
                det_w = _wrap_text_by_width(
                    draw, detail or preview_caption, self._font_sm, max_width=vp_w - 44, max_lines=1
                )
                draw.text(
                    (vp_x0 + vp_w // 2, vp_y0 + 164),
                    det_w[0] if det_w else stage_title,
                    font=self._font_sm,
                    fill=(186, 230, 253, 255),
                    anchor="mm",
                )

            # Bottom frosted caption strip inside viewport
            cap_overlay = Image.new("RGBA", (vp_w - 2, 34), (7, 11, 24, 208))
            img.alpha_composite(cap_overlay, (vp_x0 + 1, vp_y1 - 35))
            draw = ImageDraw.Draw(img)
            cap_wrapped = _wrap_text_by_width(draw, preview_caption, self._font_sm, max_width=vp_w - 28, max_lines=1)
            draw.text(
                (vp_x0 + 12, vp_y1 - 28),
                cap_wrapped[0] if cap_wrapped else preview_caption,
                font=self._font_sm,
                fill=(248, 250, 252, 255),
            )
            # Crisp rounded outline + top-right i/N corner badge
            draw.rounded_rectangle([(vp_x0, vp_y0), (vp_x1, vp_y1)], radius=12, outline=(*stage_accent, 235), width=2)
            idx_lbl = f"{slide_idx + 1}/{len(preview_paths)}" if preview_paths else "0/0"
            idx_w = int(draw.textlength(idx_lbl, font=self._font_xs)) + 16
            draw.rounded_rectangle(
                [(vp_x1 - idx_w - 8, vp_y0 + 8), (vp_x1 - 8, vp_y0 + 30)],
                radius=8,
                fill=(10, 16, 34, 224),
                outline=(*stage_accent, 225),
                width=1,
            )
            draw.text(
                (vp_x1 - idx_w // 2 - 8, vp_y0 + 19),
                idx_lbl,
                font=self._font_xs,
                fill=(248, 250, 252, 255),
                anchor="mm",
            )

            # Lower 4-line CLI / Code Terminal Box (~490x114 at x=14..504, y=322..436)
            term_y0, term_y1 = 322, 436
            draw.rounded_rectangle(
                [(14, term_y0), (MONITOR_W - 14, term_y1)],
                radius=12,
                fill=(6, 10, 22, 248),
                outline=(*stage_accent, 165),
                width=1,
            )
            for idx_d, dcol in enumerate(((244, 63, 94), (245, 158, 11), (16, 185, 129))):
                draw.ellipse([(24 + idx_d * 13, term_y0 + 8), (31 + idx_d * 13, term_y0 + 15)], fill=(*dcol, 235))
            draw.text(
                (68, term_y0 + 5),
                f"CLI TERMINAL · {stage_title}",
                font=self._font_xs,
                fill=(125, 211, 252, 255),
            )
            term_lines = (
                code_lines[-4:]
                if code_lines
                else [
                    f"$ ./cli.py studio-stage --stage {stage_key}",
                    f"[EP] {episode} | progress={progress_pct}%",
                    f"[INFO] {detail or stage_title}",
                    "[OK] zero-PII live production feed synced",
                ]
            )
            ly = term_y0 + 25
            for idx_ln, raw_ln in enumerate(term_lines[:4]):
                clean_ln = raw_ln.rstrip("_")
                wrapped = _wrap_text_by_width(draw, clean_ln, self._font_xs, max_width=MONITOR_W - 56, max_lines=1)
                shown = wrapped[0] if wrapped else clean_ln
                lcol = (125, 211, 252, 255) if shown.startswith("$") else (110, 231, 183, 255)
                draw.text((24, ly), shown, font=self._font_xs, fill=lcol)
                if idx_ln == len(term_lines[:4]) - 1:
                    cx = min(MONITOR_W - 26, 24 + int(draw.textlength(shown, font=self._font_xs)) + 4)
                    cursor_pos = (cx, ly)
                ly += 21

        self._monitor_key = key
        self._monitor_overlay = img
        self._monitor_cursor_pos = cursor_pos
        return img, cursor_pos

    def _get_telemetry_overlay(self, online: int, watched_text: str, f_count: int, f_goal: int) -> Image.Image:
        key = (online, watched_text, f_count, f_goal)
        if self._telemetry_overlay is not None and self._telemetry_key == key:
            return self._telemetry_overlay

        w, h = 840, 58
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle(
            [(0, 0), (w - 1, h - 1)], radius=18, fill=(11, 18, 36, 224), outline=(56, 189, 248, 195), width=2
        )
        draw.rounded_rectangle([(10, 10), (96, 48)], radius=14, fill=(239, 68, 68, 255))
        draw.ellipse([(22, 23), (34, 35)], fill=(255, 255, 255, 255))
        draw.text((42, 16), "LIVE", font=self._font_md, fill=(255, 255, 255, 255))
        info = f"AI 现场制片厂 · 铁三角   在线 {online} · {watched_text} · 冲粉 {f_count}/{f_goal}"
        lines = _wrap_text_by_width(draw, info, self._font_md, max_width=w - 130, max_lines=1)
        draw.text((112, 16), lines[0] if lines else info, font=self._font_md, fill=(241, 245, 249, 255))

        self._telemetry_key = key
        self._telemetry_overlay = img
        return img

    def _get_countdown_overlay(self, countdown_sec: int, in_crisis: bool) -> Image.Image:
        key = (countdown_sec, in_crisis)
        if self._countdown_overlay is not None and self._countdown_key == key:
            return self._countdown_overlay

        w, h = 445, 58
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        bg = (69, 10, 26, 232) if in_crisis else (11, 18, 36, 224)
        outline = (248, 113, 113, 255) if in_crisis else (167, 139, 250, 200)
        draw.rounded_rectangle([(0, 0), (w - 1, h - 1)], radius=18, fill=bg, outline=outline, width=2)
        label = "危机双倍耗能!" if in_crisis else "工坊续命倒计时"
        draw.text((18, 18), label, font=self._font_sm, fill=(254, 202, 202, 255) if in_crisis else (196, 181, 253, 255))
        clock_str = _fmt_hhmmss(countdown_sec)
        draw.text((w - 22, 9), clock_str, font=self._font_xl, fill=(248, 250, 252, 255), anchor="ra")

        self._countdown_key = key
        self._countdown_overlay = img
        return img

    def _get_world_hud_overlay(self, ws: Dict[str, Any]) -> Image.Image:
        wstate = ws["world"]
        raw_prod = ws.get("production")
        prod: Dict[str, Any] = raw_prod if isinstance(raw_prod, dict) else {}
        key = (
            wstate["level"],
            wstate["build_xp"],
            wstate["next_level_xp"],
            wstate["code_pts"],
            wstate["compute_pts"],
            wstate["rice_bowls"],
            wstate["active_worker_count"],
            wstate["active_event"]["title"] if wstate.get("active_event") else "",
            prod.get("stage_title", ""),
            prod.get("episode", ""),
            prod.get("progress_pct", 0),
        )
        if self._world_hud_overlay is not None and self._world_hud_key == key:
            return self._world_hud_overlay

        img = Image.new("RGBA", (WORLD_WIDTH, 76), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle(
            [(14, 10), (MAP_LEFT_WIDTH, 68)], radius=15, fill=(10, 16, 34, 226), outline=(56, 189, 248, 185), width=2
        )
        title = f"Lv.{wstate['level']} {wstate['level_name']}   在线小人 {wstate['active_worker_count']} 名"
        draw.text((28, 14), title, font=self._font_md, fill=(248, 250, 252, 255))
        stats_line = f"代码 {wstate['code_pts']} · 算力 {wstate['compute_pts']} · 白米饭 {wstate['rice_bowls']}"
        draw.text((28, 42), stats_line, font=self._font_sm, fill=(125, 211, 252, 255))

        # Integrated XP bar + label on the right half of the left HUD pill
        xp_lbl = f"升级 XP {wstate['build_xp']}/{wstate['next_level_xp']}"
        draw.text((728, 16), xp_lbl, font=self._font_sm, fill=(224, 242, 254, 255), anchor="ra")
        bar_x0, bar_x1, bar_y0, bar_y1 = 498, 728, 42, 54
        draw.rounded_rectangle([(bar_x0, bar_y0), (bar_x1, bar_y1)], radius=6, fill=(30, 41, 59, 240))
        ratio = max(0.05, min(1.0, float(wstate["build_xp"]) / max(1.0, float(wstate["next_level_xp"]))))
        fill_x1 = bar_x0 + max(12, int(round((bar_x1 - bar_x0) * ratio)))
        draw.rounded_rectangle([(bar_x0, bar_y0), (fill_x1, bar_y1)], radius=6, fill=(56, 189, 248, 255))

        ev = wstate.get("active_event")
        if ev:
            draw.rounded_rectangle(
                [(MONITOR_X, 10), (WORLD_WIDTH - 14, 68)],
                radius=15,
                fill=(69, 10, 26, 232),
                outline=(248, 113, 113, 245),
                width=2,
            )
            draw.text((MONITOR_X + 16, 14), f"突发: {ev['title']}", font=self._font_md, fill=(254, 202, 202, 255))
            desc_line = _wrap_text_by_width(
                draw, ev["desc"], self._font_sm, max_width=WORLD_WIDTH - MONITOR_X - 44, max_lines=1
            )
            draw.text(
                (MONITOR_X + 16, 41),
                desc_line[0] if desc_line else ev["desc"],
                font=self._font_sm,
                fill=(252, 165, 165, 255),
            )
        else:
            st_title = str(prod.get("stage_title") or "互联网热点海")
            ep_str = str(prod.get("episode") or "Ep024 筹备中")
            prog_val = int(prod.get("progress_pct", 15))
            accent = STATIONS.get(st_title, STATIONS["互联网热点海"])[3]
            draw.rounded_rectangle(
                [(MONITOR_X, 10), (WORLD_WIDTH - 14, 68)],
                radius=15,
                fill=(10, 16, 34, 226),
                outline=(*accent, 205),
                width=2,
            )
            draw.text(
                (MONITOR_X + 16, 14),
                f"AI 现场制片厂 · {ep_str}",
                font=self._font_md,
                fill=(248, 250, 252, 255),
            )
            sub_str = f"当前工序：{st_title}（进度 {prog_val}%）· 弹幕发 A/B/C 选下期"
            sub_wrapped = _wrap_text_by_width(
                draw, sub_str, self._font_sm, max_width=WORLD_WIDTH - MONITOR_X - 38, max_lines=1
            )
            draw.text(
                (MONITOR_X + 16, 42),
                sub_wrapped[0] if sub_wrapped else sub_str,
                font=self._font_sm,
                fill=(186, 230, 253, 255),
            )

        self._world_hud_key = key
        self._world_hud_overlay = img
        return img

    def _get_workbench_overlay(self, wb: Dict[str, Any]) -> Image.Image:
        logs = wb["work_log"]
        key = (
            wb["active_task"],
            wb["pipeline_stage"],
            tuple((row["ts"], row["tag"], row["text"]) for row in logs),
        )
        if self._workbench_overlay is not None and self._workbench_key == key:
            return self._workbench_overlay

        w, h = 786, 238
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle(
            [(0, 0), (w - 1, h - 1)], radius=22, fill=(9, 14, 29, 232), outline=(56, 189, 248, 185), width=2
        )

        # Subtle window dots + header chip + compact 4-stage pipeline
        for idx_dot, dot_col in enumerate(((244, 63, 94), (245, 158, 11), (16, 185, 129))):
            dx = 20 + idx_dot * 16
            draw.ellipse([(dx, 22), (dx + 9, 31)], fill=(*dot_col, 230))
        draw.rounded_rectangle(
            [(72, 12), (318, 44)], radius=10, fill=(23, 37, 84, 230), outline=(59, 130, 246, 150), width=1
        )
        draw.text((84, 17), "AI Agent 实时工作台", font=self._font_md, fill=(224, 242, 254, 255))

        px = 330
        for s_idx, stage_lbl in enumerate(PIPELINE_STAGES):
            is_cur = s_idx == int(wb["pipeline_stage"])
            sw = int(draw.textlength(stage_lbl, font=self._font_sm)) + 20
            fill_c = (16, 185, 129, 245) if is_cur else (30, 41, 59, 220)
            txt_c = (255, 255, 255, 255) if is_cur else (148, 163, 184, 255)
            draw.rounded_rectangle([(px, 13), (px + sw, 43)], radius=10, fill=fill_c)
            draw.text((px + 10, 18), stage_lbl, font=self._font_sm, fill=txt_c)
            px += sw + 8

        task_line = _wrap_text_by_width(
            draw, f"当前任务：{wb['active_task']}", self._font_md, max_width=w - 44, max_lines=1
        )
        draw.text(
            (22, 56), task_line[0] if task_line else wb["active_task"], font=self._font_md, fill=(251, 191, 36, 255)
        )

        ly = 92
        for row in list(logs)[-4:]:
            tag = row["tag"]
            tag_bg = (
                (220, 38, 38, 240)
                if tag in ("ALERT", "ERROR")
                else (
                    (217, 119, 6, 240)
                    if tag == "STAGE"
                    else (
                        (219, 39, 119, 240)
                        if tag == "VOTE"
                        else (
                            (16, 185, 129, 235) if tag in ("FIX", "CODE", "TEST", "OPT", "UI") else (37, 99, 235, 235)
                        )
                    )
                )
            )
            draw.text((22, ly + 3), row["ts"], font=self._font_sm, fill=(148, 163, 184, 255))
            draw.rounded_rectangle([(104, ly), (176, ly + 24)], radius=8, fill=tag_bg)
            draw.text((140, ly + 12), tag[:6], font=self._font_xs, fill=(255, 255, 255, 255), anchor="mm")
            line = _wrap_text_by_width(draw, row["text"], self._font_sm, max_width=w - 204, max_lines=1)
            draw.text((186, ly + 2), line[0] if line else row["text"], font=self._font_sm, fill=(226, 232, 240, 255))
            ly += 33

        self._workbench_key = key
        self._workbench_overlay = img
        return img

    def _get_right_panel_overlay(self, ws: Dict[str, Any]) -> Image.Image:
        builders = ws["top_builders"]
        suggestions = ws["suggestions"]
        dm = ws["recent_danmaku"]
        key = (
            tuple((b["alias"], b["score"], b["badge"], b["tier"]) for b in builders),
            tuple((s["id"], s["author"], s["text"], s["status"]) for s in suggestions[-3:]),
            tuple((d["event_type"], d["user_alias"], d["text"]) for d in dm[-4:]),
        )
        if self._right_overlay is not None and self._right_key == key:
            return self._right_overlay

        pw, ph = 534, 636
        img = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Section 1: Today Contributors & Memory Badges (y=0..198)
        draw.rounded_rectangle(
            [(0, 0), (pw - 1, 198)], radius=16, fill=(17, 26, 52, 224), outline=(56, 189, 248, 155), width=2
        )
        known_viewers = int(ws["world"]["total_known_viewers"])
        board_title = "今日共建榜 · 抢占第 1 席!" if known_viewers == 0 else f"今日共建榜 · 记住 {known_viewers} 位工友"
        draw.text((16, 11), board_title, font=self._font_md, fill=(248, 250, 252, 255))
        y = 44
        if not builders:
            draw.text((16, 68), "发个「1」或「开工」生成像素小人上墙，", font=self._font_sm, fill=(125, 211, 252, 255))
            draw.text((16, 98), "工坊永久记住你的 ID 与共建贡献!", font=self._font_sm, fill=(148, 163, 184, 255))
        else:
            rank_cols = ((250, 204, 21), (203, 213, 225), (251, 146, 60))
            for idx, b in enumerate(builders[:5], 1):
                r_col = rank_cols[idx - 1] if idx <= 3 else (99, 102, 241)
                draw.rounded_rectangle([(14, y + 1), (36, y + 23)], radius=6, fill=(*r_col, 235))
                draw.text((25, y + 12), str(idx), font=self._font_xs, fill=(15, 23, 42, 255), anchor="mm")
                badge_str = f" [{b['badge']}]" if b.get("badge") else f" · {b['tier']}"
                left_txt = f"{b['alias']}{badge_str}"
                left_wrapped = _wrap_text_by_width(draw, left_txt, self._font_sm, max_width=pw - 138, max_lines=1)
                draw.text(
                    (46, y + 2),
                    left_wrapped[0] if left_wrapped else left_txt,
                    font=self._font_sm,
                    fill=(241, 245, 249, 255),
                )
                draw.text(
                    (pw - 16, y + 2), f"{b['score']}分", font=self._font_sm, fill=(125, 211, 252, 255), anchor="ra"
                )
                y += 30

        # Section 2: Viewer Suggestions Queue (y=210..376)
        draw.rounded_rectangle(
            [(0, 210), (pw - 1, 376)], radius=16, fill=(22, 20, 54, 226), outline=(167, 139, 250, 170), width=2
        )
        draw.text((16, 220), "观众建议单（真采纳 · 现场改）", font=self._font_md, fill=(221, 214, 254, 255))
        sy = 254
        if not suggestions:
            draw.text(
                (16, 282), "发「建议 加个新功能/改画面」，Agent 立刻改！", font=self._font_sm, fill=(196, 181, 253, 255)
            )
        else:
            for s in list(suggestions)[-3:]:
                done_flag = s["status"] == "已采纳"
                pill_bg = (16, 185, 129, 255) if done_flag else (124, 58, 237, 255)
                draw.rounded_rectangle([(14, sy + 1), (82, sy + 24)], radius=8, fill=pill_bg)
                draw.text((22, sy + 3), s["status"], font=self._font_xs, fill=(255, 255, 255, 255))
                s_txt = _wrap_text_by_width(
                    draw, f"{s['id']} {s['author']}: {s['text']}", self._font_sm, max_width=pw - 110, max_lines=1
                )
                draw.text((92, sy + 2), s_txt[0] if s_txt else s["text"], font=self._font_sm, fill=(241, 245, 249, 255))
                sy += 38

        # Section 3: Live Sanitized Danmaku Feed (y=388..636)
        draw.rounded_rectangle(
            [(0, 388), (pw - 1, ph - 1)], radius=16, fill=(17, 26, 52, 224), outline=(56, 189, 248, 155), width=2
        )
        draw.text((16, 398), "实时弹幕流", font=self._font_md, fill=(248, 250, 252, 255))
        dy = 434
        if not dm:
            draw.text(
                (16, 462), "弹幕直连畅通！扣「1」或发建议立即响应：", font=self._font_sm, fill=(125, 211, 252, 255)
            )
            draw.text((16, 492), "女声实时回应 + 像素工友立刻出场干活！", font=self._font_sm, fill=(148, 163, 184, 255))
        else:
            for item in list(dm)[-4:]:
                et = item["event_type"]
                t_col = (
                    (217, 119, 6, 255)
                    if et == "gift"
                    else ((2, 132, 199, 255) if et == "enter" else (59, 130, 246, 255))
                )
                t_lbl = "投喂" if et == "gift" else ("进场" if et == "enter" else "弹幕")
                draw.rounded_rectangle([(14, dy + 1), (62, dy + 24)], radius=8, fill=t_col)
                draw.text((22, dy + 3), t_lbl, font=self._font_xs, fill=(255, 255, 255, 255))
                msg_line = _wrap_text_by_width(
                    draw, f"{item['user_alias']}: {item['text']}", self._font_sm, max_width=pw - 86, max_lines=1
                )
                draw.text(
                    (70, dy + 2),
                    msg_line[0] if msg_line else item["text"],
                    font=self._font_sm,
                    fill=(241, 245, 249, 255),
                )
                dy += 44

        self._right_key = key
        self._right_overlay = img
        return img

    def _get_subtitle_overlay(self, active_speaker: SpeakerId, turn: Optional[PersonaTurn]) -> Image.Image:
        text = (
            turn.text
            if turn is not None
            else "欢迎来到 AI 活工坊！发「1」「开工」「写代码」或「建议」就能一起建设直播间！"
        )
        text = redact_pii(text).replace("@", "").strip()
        speaker = turn.speaker_id if turn is not None else active_speaker
        if speaker not in self._dock_portraits:
            speaker = self.cast[0]
        mood = turn.mood if turn is not None else "lively"
        turn_id = turn.turn_id if turn is not None else 0
        is_hl = turn.is_highlight if turn is not None else False

        key = (turn_id, speaker, mood, text, is_hl)
        if self._subtitle_overlay is not None and self._subtitle_key == key:
            return self._subtitle_overlay

        w, h = 1830, 154
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        token = self._dock_portraits[speaker]
        img.paste(token, (0, 14), token)

        sx0 = token.width + 22
        accent = SPEAKER_ACCENT_RGB.get(speaker, (56, 189, 248))
        s_name = PERSONAS[speaker].display_name
        nw = int(draw.textlength(s_name, font=self._font_lg)) + 34
        draw.rounded_rectangle([(sx0, 8), (sx0 + nw, 44)], radius=14, fill=(*accent, 255))
        draw.text((sx0 + 17, 12), s_name, font=self._font_lg, fill=(255, 255, 255, 255))

        mood_lbl = MOOD_LABELS.get(mood, "实时解说")
        mw = int(draw.textlength(mood_lbl, font=self._font_sm)) + 24
        mx0 = sx0 + nw + 12
        draw.rounded_rectangle(
            [(mx0, 10), (mx0 + mw, 42)], radius=12, fill=(30, 41, 59, 235), outline=(99, 102, 241, 160), width=1
        )
        draw.text((mx0 + 12, 16), mood_lbl, font=self._font_sm, fill=(226, 232, 240, 255))

        lines = _wrap_text_by_width(draw, text, self._font_sub, max_width=w - sx0 - 30, max_lines=2)
        ty = 56
        for line in lines:
            draw.text((sx0 + 2, ty + 2), line, font=self._font_sub, fill=(2, 6, 23, 225))
            draw.text((sx0, ty), line, font=self._font_sub, fill=(248, 250, 252, 255))
            ty += 45

        self._subtitle_key = key
        self._subtitle_overlay = img
        return img

    def render_frame(
        self,
        *,
        frame_index: int,
        active_speaker: SpeakerId = "dafeiyu",
        current_turn: Optional[PersonaTurn] = None,
        recent_danmaku: Sequence[Dict[str, Any]] = (),
        audio_level: float = 0.0,
        follower_count: Optional[int] = None,
        follower_goal: Optional[int] = None,
        poll_snapshot: Any = None,
        celebration_text: str = "",
    ) -> np.ndarray:
        """Render a single `1920x1080` RGB24 frame (`uint8` ndarray `(1080, 1920, 3)`)."""
        del poll_snapshot, recent_danmaku  # Managed via LiveAgentWorld state snapshot
        t = frame_index / float(self.fps)
        level = max(0.0, min(1.0, float(audio_level)))
        ws = self.world.export_state_dict()
        telem = ws["telemetry"]
        wstate = ws["world"]
        f_count = (
            telem["follower_count"] if follower_count is None else max(telem["follower_count"], int(follower_count))
        )
        f_goal = telem["follower_goal"] if follower_goal is None else max(1, int(follower_goal))

        resolved_active: SpeakerId = active_speaker if active_speaker in self._host_tokens else self.cast[0]
        raw_prod = ws.get("production")
        prod: Dict[str, Any] = raw_prod if isinstance(raw_prod, dict) else {}
        stage_key = str(prod.get("stage") or "internet_sea")

        # 1) Fetch or reuse all cached panel overlays (zero per-frame redraw when state is unchanged)
        tel_overlay = self._get_telemetry_overlay(telem["online"], telem["watched_text"], f_count, f_goal)
        cd_overlay = self._get_countdown_overlay(int(wstate["countdown_sec"]), wstate.get("active_event") is not None)
        world_layer = self._get_world_level_layer(wstate["level"], stage_key)
        hud_overlay = self._get_world_hud_overlay(ws)
        monitor_overlay, cursor_pos = self._get_live_monitor_overlay(prod, t)
        wb_overlay = self._get_workbench_overlay(ws["workbench"])
        right_overlay = self._get_right_panel_overlay(ws)
        sub_overlay = self._get_subtitle_overlay(resolved_active, current_turn)

        base_key = (
            wstate["level"],
            stage_key,
            resolved_active,
            self._telemetry_key,
            self._countdown_key,
            self._world_hud_key,
            self._monitor_key,
            self._workbench_key,
            self._right_key,
            self._subtitle_key,
        )
        if self._frame_base_rgb is None or self._frame_base_key != base_key:
            base = self._get_stage_canvas(wstate["level"], resolved_active).copy()
            base.paste(tel_overlay, (24, 14), tel_overlay)
            base.paste(cd_overlay, (876, 14), cd_overlay)
            base.paste(world_layer, (24, 88), world_layer)
            base.paste(hud_overlay, (24, 88), hud_overlay)
            base.paste(monitor_overlay, (24 + MONITOR_X, 88 + MONITOR_Y), monitor_overlay)
            base.paste(wb_overlay, (24, 638), wb_overlay)
            base.paste(right_overlay, (1346, 228), right_overlay)
            base.paste(sub_overlay, (44, 898), sub_overlay)
            self._frame_base_rgb = base
            self._frame_base_key = base_key

        frame = self._frame_base_rgb.copy()
        fdraw = ImageDraw.Draw(frame, "RGBA")
        ox_map, oy_map = 24, 88

        if cursor_pos is not None and int(t * 2.0) % 2 == 0:
            fdraw.text(
                (ox_map + MONITOR_X + cursor_pos[0], oy_map + MONITOR_Y + cursor_pos[1]),
                "_",
                font=self._font_xs,
                fill=(110, 231, 183, 255),
            )

        with self.world._lock:
            hosts_snapshot = [(sid, h.x, h.y, h.action_label, h.phase) for sid, h in self.world.host_actors.items()]
            bots_snapshot = [(b.name, b.x, b.y, b.action_label, b.color, b.phase) for b in self.world.ambient_bots]
            viewers_snapshot = [
                (v.alias, v.x, v.y, v.action_label, v.color_idx, v.badge) for v in self.world.viewer_actors.values()
            ]
            popups_snapshot = [(p.text, p.x, p.y, p.color) for p in self.world.popups]

        # Draw resident AI helper bots inside left map (x <= MAP_LEFT_WIDTH, never occluding building cards)
        for bname, bx, by, bact, bcol, bphase in bots_snapshot:
            bob = int(round(2.5 * abs(math.sin(t * 4.5 + bphase))))
            btok = self._bot_tokens.get(bcol)
            if btok is None:
                btok = self._build_bot_token(bcol, size=36)
                self._bot_tokens[bcol] = btok
            px = int(round(bx - btok.width / 2))
            py = int(round(by - btok.height + 6 - bob))
            frame.paste(btok, (ox_map + px, oy_map + py), btok)
            short_bot = "小鱼" if "鱼" in bname else "电饭煲"
            tag = f"AI·{short_bot}"
            tw = int(fdraw.textlength(tag, font=self._font_xs)) + 14
            tx0 = max(18, min(MAP_LEFT_WIDTH - tw - 8, int(round(bx - tw / 2))))
            ty0 = min(334, int(round(by + 7))) if by < 285.0 else max(210, py - 22)
            fdraw.rounded_rectangle(
                [(ox_map + tx0, oy_map + ty0), (ox_map + tx0 + tw, oy_map + ty0 + 20)],
                radius=8,
                fill=(10, 16, 34, 224),
                outline=(*bcol, 220),
                width=1,
            )
            fdraw.text((ox_map + tx0 + 7, oy_map + ty0 + 2), tag, font=self._font_xs, fill=(224, 242, 254, 255))

        # Draw viewer pixel workers inside left map (labels kept strictly outside top/bottom building cards)
        for alias, vx, vy, vact, cidx, vbadge in viewers_snapshot:
            bob = int(round(3.0 * abs(math.sin(t * 6.0 + cidx))))
            tok = self._viewer_tokens[cidx % len(self._viewer_tokens)]
            px = int(round(vx - tok.width / 2))
            py = int(round(vy - tok.height + 6 - bob))
            frame.paste(tok, (ox_map + px, oy_map + py), tok)
            short_act = vact[:4] if vact else ""
            tag = f"{alias[:4]}·{short_act}" if short_act else alias[:6]
            tw = int(fdraw.textlength(tag, font=self._font_xs)) + 12
            tx0 = max(18, min(MAP_LEFT_WIDTH - tw - 8, int(round(vx - tw / 2))))
            if vy > 440.0:
                ty0 = min(WORLD_HEIGHT - 24, int(round(vy + 7)))
            elif vy <= 286.0:
                ty0 = min(334, int(round(vy + 7)))
            else:
                ty0 = max(210, py - 22)
            fdraw.rounded_rectangle(
                [(ox_map + tx0, oy_map + ty0), (ox_map + tx0 + tw, oy_map + ty0 + 20)],
                radius=8,
                fill=(15, 23, 42, 235),
                outline=(56, 189, 248, 220),
                width=1,
            )
            fdraw.text((ox_map + tx0 + 6, oy_map + ty0 + 2), tag, font=self._font_xs, fill=(248, 250, 252, 255))
            if vbadge:
                bw = int(fdraw.textlength(vbadge, font=self._font_xs)) + 10
                bx_badge = max(18, min(MAP_LEFT_WIDTH - bw - 8, int(round(vx - bw / 2))))
                by_badge = (ty0 - 20) if (vy > 440.0 or ty0 >= 232) else (ty0 + 22)
                fdraw.rounded_rectangle(
                    [(ox_map + bx_badge, oy_map + by_badge), (ox_map + bx_badge + bw, oy_map + by_badge + 18)],
                    radius=6,
                    fill=(217, 119, 6, 245),
                )
                fdraw.text(
                    (ox_map + bx_badge + 5, oy_map + by_badge + 1),
                    vbadge,
                    font=self._font_xs,
                    fill=(255, 255, 255, 255),
                )

        # Draw patrolling host tokens along left production map (strictly inside corridor y=210..354)
        for sid, hx, hy, hact, hphase in hosts_snapshot:
            if sid not in self._host_tokens:
                continue
            tok = self._host_tokens[sid]
            is_act = sid == resolved_active
            bob = int(round((6.0 if is_act else 3.0) * abs(math.sin(t * 5.0 + hphase))))
            px = int(round(hx - tok.width / 2))
            py = int(round(hy - tok.height + 6 - bob))
            frame.paste(tok, (ox_map + px, oy_map + py), tok)
            accent = SPEAKER_ACCENT_RGB.get(sid, (37, 99, 235))
            lbl = f"{PERSONAS[sid].short_name}·{hact[:4]}"
            lw = int(fdraw.textlength(lbl, font=self._font_xs)) + 12
            lx0 = max(18, min(MAP_LEFT_WIDTH - lw - 8, int(round(hx - lw / 2))))
            ly0 = min(334, int(round(hy + 7))) if hy <= 354.0 else min(WORLD_HEIGHT - 24, int(round(hy + 7)))
            fdraw.rounded_rectangle(
                [(ox_map + lx0, oy_map + ly0), (ox_map + lx0 + lw, oy_map + ly0 + 19)],
                radius=8,
                fill=(10, 16, 34, 232),
                outline=(*accent, 240),
                width=1,
            )
            fdraw.text((ox_map + lx0 + 6, oy_map + ly0 + 2), lbl, font=self._font_xs, fill=(248, 250, 252, 255))

        # Draw floating popups strictly within open corridor / promenade bands (never covering building cards)
        for ptext, popx, popy, pcol in popups_snapshot:
            pw = int(fdraw.textlength(ptext, font=self._font_sm)) + 16
            px0 = max(18, min(MAP_LEFT_WIDTH - pw - 8, int(round(popx - pw / 2))))
            raw_py = int(round(popy))
            if raw_py < 210:
                py0 = 210
            elif 330 < raw_py < 436:
                py0 = 330
            else:
                py0 = min(WORLD_HEIGHT - 30, raw_py)
            fdraw.rounded_rectangle(
                [(ox_map + px0, oy_map + py0), (ox_map + px0 + pw, oy_map + py0 + 25)],
                radius=10,
                fill=(10, 16, 34, 238),
                outline=(*pcol, 255),
                width=2,
            )
            fdraw.text((ox_map + px0 + 8, oy_map + py0 + 3), ptext, font=self._font_sm, fill=(248, 250, 252, 255))

        # Optional world/follower celebration banner inside bottom of left map (never obscures LIVE monitor)
        active_banner = celebration_text.strip() or wstate.get("active_banner") or ""
        if active_banner:
            ban_max = MAP_LEFT_WIDTH - 48
            ban_lines = _wrap_text_by_width(fdraw, active_banner, self._font_sm, max_width=ban_max - 28, max_lines=1)
            ban_shown = ban_lines[0] if ban_lines else active_banner
            bw = min(ban_max, int(fdraw.textlength(ban_shown, font=self._font_sm)) + 40)
            bx0 = 14 + (MAP_LEFT_WIDTH - 14 - bw) // 2
            fdraw.rounded_rectangle(
                [(ox_map + bx0, oy_map + WORLD_HEIGHT - 52), (ox_map + bx0 + bw, oy_map + WORLD_HEIGHT - 16)],
                radius=14,
                fill=(15, 23, 42, 242),
                outline=(250, 204, 21, 245),
                width=2,
            )
            fdraw.text(
                (ox_map + bx0 + bw // 2, oy_map + WORLD_HEIGHT - 34),
                ban_shown,
                font=self._font_sm,
                fill=(254, 240, 138, 255),
                anchor="mm",
            )

        # 5) Animated audio waveform bars along bottom subtitle dock
        eq_color = SPEAKER_EQ_LIGHT_RGB.get(resolved_active, (56, 189, 248))
        eq_peak = SPEAKER_EQ_PEAK_RGB.get(resolved_active, (37, 99, 235))
        bar_count, bar_w, bar_gap = 20, 7, 5
        eq_x0 = 1868 - (bar_count * bar_w + (bar_count - 1) * bar_gap)
        eq_base_y, max_h = 942, 32.0
        for idx in range(bar_count):
            dist_c = abs(idx - (bar_count - 1) / 2.0) / ((bar_count - 1) / 2.0)
            env = 1.0 - 0.55 * dist_c
            wave = 0.5 + 0.5 * math.sin(t * 11.5 + idx * 0.55)
            h_px = int(5 + (max_h * (0.14 + 0.86 * level) * env * (0.35 + 0.65 * wave)))
            bx0 = eq_x0 + idx * (bar_w + bar_gap)
            fdraw.rounded_rectangle(
                [(bx0, eq_base_y - h_px), (bx0 + bar_w, eq_base_y)],
                radius=3,
                fill=eq_peak if h_px > int(max_h * 0.6) else eq_color,
            )

        return np.ascontiguousarray(np.asarray(frame, dtype=np.uint8))


__all__ = [
    "CORRIDOR_Y",
    "CRISIS_COOLDOWN_SEC",
    "DEFAULT_MEMORY_PATH",
    "LEVEL_THRESHOLDS",
    "PIPELINE_STAGES",
    "PRODUCTION_STAGE_META",
    "PRODUCTION_STAGE_TO_STATION",
    "STATIONS",
    "WORLD_HEIGHT",
    "WORLD_WIDTH",
    "AmbientBotActor",
    "AutonomousWorldBrain",
    "FloatingPopup",
    "HostActor",
    "LiveAgentWorld",
    "ViewerActor",
    "ViewerMemoryStore",
    "WorldStageRenderer",
]
