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
from PIL import Image, ImageDraw, ImageEnhance

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

PIPELINE_STAGES: Final[Tuple[str, ...]] = ("① 读建议", "② 改世界", "③ 跑验证", "④ 播报")

LEVEL_THRESHOLDS: Final[Tuple[Tuple[int, int, str], ...]] = (
    (1, 0, "破旧电饭煲工位"),
    (2, 100, "霓虹算力工坊"),
    (3, 280, "全息弹幕广场"),
    (4, 600, "千粉庆典塔"),
)

STATIONS: Final[Dict[str, Tuple[int, int, str, Tuple[int, int, int]]]] = {
    "代码工位": (245, 168, "写代码 · 修逻辑", (37, 99, 235)),
    "算力机柜": (643, 168, "24G算力巡检", (14, 116, 144)),
    "电饭煲补给": (1040, 168, "白米饭续命站", (217, 119, 6)),
    "弹幕公告塔": (643, 386, "灵感与共建榜", (124, 58, 237)),
}

_SUGGESTION_PREFIX_RE: Final[re.Pattern[str]] = re.compile(r"^\s*(?:建议|提案|需求|点子)[:：\s]*")

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
        self._next_crisis_at_sec: float = 240.0

        # Real-time Agent Workbench
        self.active_task: str = "巡查工坊，等待弹幕「开工」与「建议」"
        self.pipeline_stage: int = 0
        self.work_log: Deque[Dict[str, str]] = deque(maxlen=8)
        self._push_log_locked("AGENT", "AI 主控已上线：2D 共建工坊与实时弹幕网关运行中")

        # Suggestions & banners
        self._suggestion_seq: int = 0
        self.suggestions: Deque[Dict[str, Any]] = deque(maxlen=12)
        self.banner_text: str = ""
        self._banner_until_ts: float = 0.0
        self.stop_requested: bool = False

        # Danmaku stream & world actors
        self.recent_danmaku: Deque[Dict[str, Any]] = deque(maxlen=16)
        self.popups: List[FloatingPopup] = []
        self.viewer_actors: Dict[str, ViewerActor] = {}

        station_names = list(STATIONS.keys())
        default_actions = {
            "dafeiyu": "巡检工位",
            "yowane": "核对账本",
            "gemini": "调优画面",
        }
        self.host_actors: Dict[SpeakerId, HostActor] = {}
        top_host_offsets = ((150.0, 12.0), (-150.0, 72.0), (0.0, 122.0))
        bottom_host_offsets = ((-178.0, 4.0), (178.0, 4.0), (0.0, -90.0))
        for idx, sid in enumerate(self.cast):
            st_name = station_names[idx % len(station_names)]
            sx, sy, _, _ = STATIONS[st_name]
            offsets = bottom_host_offsets if sy >= 250 else top_host_offsets
            ox, oy = offsets[idx % len(offsets)]
            hx = max(90.0, min(WORLD_WIDTH - 90.0, float(sx + ox)))
            hy = max(125.0, min(WORLD_HEIGHT - 74.0, float(sy + oy)))
            self.host_actors[sid] = HostActor(
                speaker_id=sid,
                name=PERSONAS[sid].short_name,
                x=hx,
                y=hy,
                target_station=st_name,
                target_x=hx,
                target_y=hy,
                action_label=default_actions.get(sid, "工作中"),
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
        sx, sy, _, _ = STATIONS.get(station, STATIONS["代码工位"])
        offset_seed = sum(ord(c) for c in alias)
        if sy >= 250:
            slots: Tuple[Tuple[float, float], ...] = (
                (-195.0, 14.0),
                (195.0, 14.0),
                (-210.0, 74.0),
                (210.0, 74.0),
                (-125.0, 84.0),
                (125.0, 84.0),
            )
            min_y, max_y = 286.0, float(WORLD_HEIGHT - 66)
        else:
            slots = (
                (-118.0, 128.0),
                (118.0, 128.0),
                (-150.0, 182.0),
                (150.0, 182.0),
                (-150.0, 228.0),
                (150.0, 228.0),
            )
            min_y, max_y = 286.0, float(WORLD_HEIGHT - 66)

        candidate_coords = [
            (
                max(115.0, min(WORLD_WIDTH - 115.0, float(sx + ox))),
                max(min_y, min(max_y, float(sy + oy))),
            )
            for ox, oy in slots
        ]
        default_idx = offset_seed % len(candidate_coords)
        rotated = candidate_coords[default_idx:] + candidate_coords[:default_idx]
        tx, ty = rotated[0]
        other_coords = [(v.target_x, v.target_y) for k, v in self.viewer_actors.items() if k != alias]
        for cx, cy in rotated:
            if all(math.hypot(cx - ox, cy - oy) > 48.0 for ox, oy in other_coords):
                tx, ty = cx, cy
                break

        actor = self.viewer_actors.get(alias)
        if actor is None:
            if len(self.viewer_actors) >= 16:
                oldest_key = min(self.viewer_actors, key=lambda k: self.viewer_actors[k].last_active_ts)
                self.viewer_actors.pop(oldest_key, None)
            actor = ViewerActor(
                alias=alias,
                x=max(85.0, min(WORLD_WIDTH - 95.0, tx + 35.0)),
                y=min(WORLD_HEIGHT - 50.0, ty + 28.0),
                target_x=tx,
                target_y=ty,
                station=station,
                action_label=action_label,
                color_idx=offset_seed % len(_VIEWER_AVATAR_COLORS),
                tier=tier,
                badge=badge,
                last_active_ts=now,
            )
            self.viewer_actors[alias] = actor
        else:
            actor.target_x = tx
            actor.target_y = ty
            actor.station = station
            actor.action_label = action_label
            actor.tier = tier or actor.tier
            if badge:
                actor.badge = badge
            actor.last_active_ts = now
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

            # Periodic interactive crisis event (~every 4 minutes when idle)
            if self.active_event is None and self.world_time_sec >= self._next_crisis_at_sec:
                title, desc = _CRISIS_PRESETS[self._crisis_cursor % len(_CRISIS_PRESETS)]
                self._crisis_cursor += 1
                self.active_event = {"title": title, "desc": desc}
                self._next_crisis_at_sec = self.world_time_sec + 240.0
                self._push_log_locked("ALERT", f"触发突发事件：{title}（等待弹幕「修Bug」或巡检处理）")

            station_keys = tuple(STATIONS.keys())
            for idx, (sid, host) in enumerate(self.host_actors.items()):
                host.phase += step
                # Re-target host between stations smoothly every ~11s
                if int((self.world_time_sec + idx * 3.5) / 11.0) != int(
                    (self.world_time_sec - step + idx * 3.5) / 11.0
                ):
                    next_st = station_keys[(int(self.world_time_sec // 11.0) + idx) % len(station_keys)]
                    sx, sy, st_desc, _ = STATIONS[next_st]
                    top_host_offsets = ((150.0, 12.0), (-150.0, 72.0), (0.0, 122.0))
                    bottom_host_offsets = ((-178.0, 4.0), (178.0, 4.0), (0.0, -90.0))
                    offsets = bottom_host_offsets if sy >= 250 else top_host_offsets
                    ox, oy = offsets[idx % len(offsets)]
                    host.target_station = next_st
                    host.target_x = max(90.0, min(WORLD_WIDTH - 90.0, float(sx + ox)))
                    host.target_y = max(125.0, min(WORLD_HEIGHT - 74.0, float(sy + oy)))
                    if sid == "dafeiyu":
                        host.action_label = f"巡查{next_st[:2]}"
                    elif sid == "yowane":
                        host.action_label = f"查账·{next_st[:2]}"
                    else:
                        host.action_label = st_desc[:8]

                dx = host.target_x - host.x
                dy = host.target_y - host.y
                dist = math.hypot(dx, dy)
                if dist > 2.0:
                    move = min(dist, 58.0 * step)
                    host.x += (dx / dist) * move
                    host.y += (dy / dist) * move

            for actor in self.viewer_actors.values():
                dx = actor.target_x - actor.x
                dy = actor.target_y - actor.y
                dist = math.hypot(dx, dy)
                if dist > 2.0:
                    move = min(dist, 92.0 * step)
                    actor.x += (dx / dist) * move
                    actor.y += (dy / dist) * move

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
        with self._lock:
            if online is not None:
                val = max(0, int(online))
                self.online = val
                self.max_online = max(self.max_online, val)
            if watched_num is not None:
                wval = max(0, int(watched_num))
                self.watched_num = wval
                self.max_watched_num = max(self.max_watched_num, wval)
                if watched_text is None:
                    self.watched_text = f"{wval}人看过"
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
                    self._banner_until_ts = time.time() + 10.0
                    self._push_log_locked("LIVE", msg)
                self.follower_count = fval
        return delta_followers

    def handle_danmaku_event(self, ev: DanmakuEvent) -> Dict[str, Any]:
        """Process viewer danmaku/gift/enter into immediate 2D world updates & viewer memory."""
        safe_alias = self.guard.sanitize_alias(ev.user_alias).replace("@", "").strip()[:20] or "热心观众"
        now = time.time()

        if ev.event_type == "enter":
            mem = self.memory.record_enter(safe_alias, now=now)
            with self._lock:
                if int(mem.get("visits", 1)) >= 2:
                    msg = f"欢迎老熟人 {safe_alias} 第 {mem['visits']} 次回到工坊！"
                    self.banner_text = msg
                    self._banner_until_ts = now + 7.0
                    actor = self._spawn_or_move_viewer_locked(
                        safe_alias,
                        station="弹幕公告塔",
                        action_label=f"第{mem['visits']}次回归",
                        tier=str(mem.get("tier") or "常客"),
                        badge=str(mem.get("badge") or ""),
                    )
                    self._add_popup_locked("老熟人回归！", actor.x, actor.y - 36, (124, 58, 237))
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
                    station="电饭煲补给",
                    action_label=f"投喂{gift_name}x{count}",
                    tier=str(mem.get("tier") or "新伙伴"),
                    badge=str(mem.get("badge") or "白米饭供应商"),
                )
                self._add_popup_locked(f"+{int(add_sec)}s 白米饭+{count}", actor.x, actor.y - 38, (217, 119, 6))
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

        # Check explicit suggestion prefix FIRST so "建议 加个白米饭锅" / "建议 改代码工位" routes to suggestions
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
                    station="弹幕公告塔",
                    action_label=f"提交建议{sug_id}",
                    tier=str(mem.get("tier") or "新伙伴"),
                    badge=str(mem.get("badge") or ""),
                )
                self._add_popup_locked(f"建议{sug_id}已上墙!", actor.x, actor.y - 36, (124, 58, 237))
                self._push_log_locked("IDEA", f"收到 {safe_alias} 建议({sug_id}): {body}")
                self._recompute_level_locked()
                self.recent_danmaku.append({"event_type": "danmaku", "user_alias": safe_alias, "text": clean_text[:48]})
            return {"handled": True, "kind": "suggestion", "suggestion_id": sug_id, "alias": safe_alias}

        # Check action commands in priority order
        if any(k in lowered for k in ("投喂", "加餐", "白米饭")):
            mem = self.memory.record_action(safe_alias, points=18, action_delta=1, message=True, now=now)
            with self._lock:
                self.countdown_sec += 300.0
                self.rice_bowls += 1
                self.build_xp += 18
                actor = self._spawn_or_move_viewer_locked(
                    safe_alias,
                    station="电饭煲补给",
                    action_label="热心加餐+300s",
                    tier=str(mem.get("tier") or "新伙伴"),
                    badge=str(mem.get("badge") or ""),
                )
                self._add_popup_locked("+300s 白米饭+1", actor.x, actor.y - 36, (217, 119, 6))
                self._recompute_level_locked()
                self.recent_danmaku.append({"event_type": "danmaku", "user_alias": safe_alias, "text": clean_text[:48]})
            return {"handled": True, "kind": "feed", "alias": safe_alias}

        if any(k in lowered for k in ("修bug", "抢修", "快跑")):
            with self._lock:
                resolved_crisis = self.active_event is not None
                crisis_title = self.active_event["title"] if self.active_event else ""
                if resolved_crisis:
                    self.active_event = None
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
                    station="算力机柜",
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
                station = "代码工位" if ("代码" in lowered) else "算力机柜"
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

        if any(k in lowered for k in ("开工", "打工", "加入")):
            mem = self.memory.record_action(safe_alias, points=10, action_delta=1, message=True, now=now)
            with self._lock:
                self.countdown_sec += 120.0
                self.build_xp += 10
                actor = self._spawn_or_move_viewer_locked(
                    safe_alias,
                    station="代码工位",
                    action_label="报到开工+120s",
                    tier=str(mem.get("tier") or "新伙伴"),
                    badge=str(mem.get("badge") or ""),
                )
                self._add_popup_locked("开工大吉 +120s", actor.x, actor.y - 36, (37, 99, 235))
                self._push_log_locked("JOIN", f"{safe_alias} 发送「开工」加入工坊建设 (+120s)")
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

        if kind == "world_action":
            action = str(cmd.get("action") or "").strip().lower()
            with self._lock:
                if action == "spawn_worker":
                    alias = self.guard.sanitize_alias(str(cmd.get("user_alias") or "热心工友")).replace("@", "").strip()
                    station = str(cmd.get("station") or "代码工位")
                    if station not in STATIONS:
                        station = "代码工位"
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
                    self._next_crisis_at_sec = self.world_time_sec + 240.0
                    self._push_log_locked("ALERT", f"突发事件：{title} — {desc}")
                    return {"ok": True, "action": action, "title": title}

                if action == "resolve_event":
                    prev = self.active_event["title"] if self.active_event else "例行巡检"
                    self.active_event = None
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
            '  "stage": 0到3整数(0读建议,1改世界,2跑验证,3播报),\n'
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


class WorldStageRenderer:
    """High-speed 1920x1080 @ 30 FPS Pillow+NumPy renderer for the living 2D interactive workshop."""

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
        self._font_lg = _load_font(self.font_path, 26)
        self._font_md = _load_font(self.font_path, 21)
        self._font_sm = _load_font(self.font_path, 17)
        self._font_xs = _load_font(self.font_path, 15)
        self._font_sub = _load_font(self.font_path, 32)

        self.loaded_assets: Dict[str, str] = {}
        self._host_tokens: Dict[SpeakerId, Image.Image] = {
            sid: self._build_character_token(sid, size=56) for sid in self.cast
        }
        self._dock_portraits: Dict[SpeakerId, Image.Image] = {
            sid: self._build_character_token(sid, size=128) for sid in self.cast
        }
        self._viewer_tokens: Dict[int, Image.Image] = {
            idx: self._build_viewer_token(rgb, size=40) for idx, rgb in enumerate(_VIEWER_AVATAR_COLORS)
        }
        self._static_bg: Image.Image = self._build_static_canvas()
        self._world_level_layers: Dict[int, Image.Image] = {}

        # Per-section frame caches keep steady-state render time < 10 ms/frame at 1080p
        self._telemetry_key: Tuple[Any, ...] = ()
        self._telemetry_overlay: Optional[Image.Image] = None

        self._countdown_key: Tuple[int, bool] = (-1, False)
        self._countdown_overlay: Optional[Image.Image] = None

        self._world_hud_key: Tuple[Any, ...] = ()
        self._world_hud_overlay: Optional[Image.Image] = None

        self._workbench_key: Tuple[Any, ...] = ()
        self._workbench_overlay: Optional[Image.Image] = None

        self._right_key: Tuple[Any, ...] = ()
        self._right_overlay: Optional[Image.Image] = None

        self._subtitle_key: Tuple[Any, ...] = ()
        self._subtitle_overlay: Optional[Image.Image] = None

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
                    crop_h = min(h, max(1, int(w * 1.05)))
                    face_crop = rgba.crop((0, 0, w, crop_h))
                    bg_circle = Image.new("RGBA", face_crop.size, (240, 249, 255, 255))
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
        ImageDraw.Draw(mask).ellipse([(2, 2), (size - 3, size - 3)], fill=255)
        out = Image.new("RGBA", (size + 8, size + 8), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(out)
        odraw.ellipse([(0, 0), (size + 7, size + 7)], fill=(*accent, 255))
        odraw.ellipse([(2, 2), (size + 5, size + 5)], fill=(255, 255, 255, 255))
        out.paste(src.convert("RGBA"), (4, 4), mask)
        return out

    def _build_viewer_token(self, rgb: Tuple[int, int, int], *, size: int = 40) -> Image.Image:
        out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(out)
        # Cute pixel chibi builder helmet + body
        cx = size // 2
        d.ellipse([(3, size - 10), (size - 4, size - 1)], fill=(15, 23, 42, 70))
        d.rounded_rectangle(
            [(8, 17), (size - 9, size - 4)], radius=7, fill=(*rgb, 255), outline=(255, 255, 255, 255), width=2
        )
        d.ellipse([(9, 4), (size - 10, 22)], fill=(255, 241, 224, 255), outline=(30, 41, 59, 240), width=2)
        d.pieslice(
            [(8, 2), (size - 9, 18)], start=180, end=360, fill=(*rgb, 255), outline=(255, 255, 255, 255), width=2
        )
        d.ellipse([(cx - 5, 11), (cx - 2, 14)], fill=(15, 23, 42, 255))
        d.ellipse([(cx + 2, 11), (cx + 5, 14)], fill=(15, 23, 42, 255))
        return out

    def _build_static_canvas(self) -> Image.Image:
        bg_path = self._find_asset(DEFAULT_STUDIO_BG_REL)
        if bg_path is not None:
            try:
                with Image.open(bg_path) as raw:
                    rgb = raw.convert("RGB")
                    sw, sh = rgb.size
                    sc = max(self.width / sw, self.height / sh)
                    resized = rgb.resize((int(round(sw * sc)), int(round(sh * sc))), Image.Resampling.LANCZOS)
                    bg = resized.crop(
                        (
                            (resized.width - self.width) // 2,
                            (resized.height - self.height) // 2,
                            (resized.width - self.width) // 2 + self.width,
                            (resized.height - self.height) // 2 + self.height,
                        )
                    )
                    bg = ImageEnhance.Brightness(bg).enhance(1.06)
                    self.loaded_assets["background"] = str(bg_path)
            except Exception:
                bg = Image.new("RGB", (self.width, self.height), (224, 242, 254))
                self.loaded_assets["background"] = "gradient_fallback"
        else:
            bg = Image.new("RGB", (self.width, self.height), (224, 242, 254))
            self.loaded_assets["background"] = "gradient_fallback"

        canvas = bg.convert("RGBA")
        overlay = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Top subtle header frost
        draw.rectangle([(0, 0), (self.width, 86)], fill=(255, 255, 255, 110))

        # Top-right permanent GB 45438-2025 compliance badge
        badge_text = AI_DISCLOSURE_BANNER
        badge_w = int(draw.textlength(badge_text, font=self._font_md)) + 52
        bx0 = max(1340, self.width - 24 - badge_w)
        draw.rounded_rectangle(
            [(bx0, 14), (self.width - 24, 76)],
            radius=22,
            fill=(255, 251, 235, 244),
            outline=(217, 119, 6, 235),
            width=3,
        )
        draw.ellipse([(bx0 + 16, 38), (bx0 + 30, 52)], fill=(16, 185, 129, 255))
        draw.text((bx0 + 40, 33), badge_text, font=self._font_md, fill=(120, 53, 15, 255))

        # Right panel shell + static 3-second guide header
        draw.rounded_rectangle(
            [(1326, 92), (1896, 880)],
            radius=24,
            fill=(255, 255, 255, 224),
            outline=(148, 163, 184, 210),
            width=3,
        )
        draw.rounded_rectangle(
            [(1342, 106), (1880, 216)], radius=18, fill=(239, 246, 255, 248), outline=(59, 130, 246, 210), width=2
        )
        draw.rounded_rectangle([(1356, 116), (1492, 144)], radius=12, fill=(37, 99, 235, 255))
        draw.text((1370, 120), "3秒参与玩法", font=self._font_sm, fill=(255, 255, 255, 255))
        draw.text((1504, 120), "无门槛弹幕直接操控世界", font=self._font_sm, fill=(30, 64, 175, 255))
        draw.text(
            (1358, 152), "发「开工 / 写代码 / 修Bug / 投喂」生小人续命！", font=self._font_sm, fill=(15, 23, 42, 255)
        )
        draw.text(
            (1358, 180), "发「建议 你的点子」直接交给后台 Agent 执行！", font=self._font_sm, fill=(124, 58, 237, 255)
        )

        # Bottom subtitle dock shell
        draw.rounded_rectangle(
            [(24, 892), (1896, 1064)],
            radius=26,
            fill=(15, 23, 42, 232),
            outline=(255, 255, 255, 195),
            width=3,
        )
        return Image.alpha_composite(canvas, overlay).convert("RGB")

    def _get_world_level_layer(self, level: int) -> Image.Image:
        lvl = max(1, min(4, int(level)))
        if lvl in self._world_level_layers:
            return self._world_level_layers[lvl]

        # Cozy warm-bright isometric/pixel workshop backdrop
        palettes = {
            1: ((248, 250, 252), (226, 232, 240)),
            2: ((239, 246, 255), (219, 234, 254)),
            3: ((245, 243, 255), (237, 233, 254)),
            4: ((255, 251, 235), (254, 243, 199)),
        }
        floor_c, tile_c = palettes[lvl]
        img = Image.new("RGBA", (WORLD_WIDTH, WORLD_HEIGHT), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        draw.rounded_rectangle(
            [(0, 0), (WORLD_WIDTH - 1, WORLD_HEIGHT - 1)],
            radius=24,
            fill=(*floor_c, 246),
            outline=(59, 130, 246, 220),
            width=3,
        )
        # Soft sky wall strip across top of workshop
        draw.rounded_rectangle([(3, 3), (WORLD_WIDTH - 4, 112)], radius=20, fill=(219, 234, 254, 210))
        # Subtle floor grid tiles
        for gx in range(28, WORLD_WIDTH - 24, 56):
            draw.line([(gx, 118), (gx, WORLD_HEIGHT - 18)], fill=(*tile_c, 190), width=1)
        for gy in range(118, WORLD_HEIGHT - 18, 56):
            draw.line([(20, gy), (WORLD_WIDTH - 20, gy)], fill=(*tile_c, 190), width=1)

        # Draw the 4 interactive pixel workshop stations
        for st_name, (sx, sy, st_sub, accent) in STATIONS.items():
            # Station pad
            draw.rounded_rectangle(
                [(sx - 92, sy - 46), (sx + 92, sy + 44)],
                radius=18,
                fill=(255, 255, 255, 235),
                outline=(*accent, 230),
                width=3,
            )
            # Small pixel landmark illustration per station
            if st_name == "代码工位":
                draw.rectangle([(sx - 44, sy - 34), (sx + 44, sy - 6)], fill=(15, 23, 42, 255))
                draw.rectangle([(sx - 38, sy - 30), (sx + 38, sy - 10)], fill=(56, 189, 248, 255))
                draw.rectangle([(sx - 20, sy - 24), (sx + 16, sy - 20)], fill=(255, 255, 255, 255))
            elif st_name == "算力机柜":
                draw.rounded_rectangle([(sx - 28, sy - 38), (sx + 28, sy - 2)], radius=5, fill=(30, 41, 59, 255))
                for ry in (-32, -22, -12):
                    draw.rectangle([(sx - 20, sy + ry), (sx + 20, sy + ry + 5)], fill=(16, 185, 129, 255))
            elif st_name == "电饭煲补给":
                draw.rounded_rectangle(
                    [(sx - 26, sy - 32), (sx + 26, sy - 2)],
                    radius=10,
                    fill=(254, 243, 199, 255),
                    outline=(217, 119, 6, 255),
                    width=2,
                )
                draw.ellipse([(sx - 12, sy - 22), (sx + 12, sy - 10)], fill=(245, 158, 11, 255))
            else:
                draw.polygon([(sx, sy - 42), (sx - 24, sy - 4), (sx + 24, sy - 4)], fill=(124, 58, 237, 230))
                draw.ellipse([(sx - 8, sy - 46), (sx + 8, sy - 30)], fill=(250, 204, 21, 255))

            nw = draw.textlength(st_name, font=self._font_sm)
            draw.text((sx - nw / 2, sy - 2), st_name, font=self._font_sm, fill=(15, 23, 42, 255))
            sw = draw.textlength(st_sub, font=self._font_xs)
            draw.text((sx - sw / 2, sy + 20), st_sub, font=self._font_xs, fill=(71, 85, 105, 255))

        self._world_level_layers[lvl] = img
        return img

    def _get_telemetry_overlay(self, online: int, watched_text: str, f_count: int, f_goal: int) -> Image.Image:
        key = (online, watched_text, f_count, f_goal)
        if self._telemetry_overlay is not None and self._telemetry_key == key:
            return self._telemetry_overlay

        w, h = 840, 62
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle(
            [(0, 0), (w - 1, h - 1)], radius=20, fill=(255, 255, 255, 240), outline=(59, 130, 246, 225), width=3
        )
        draw.rounded_rectangle([(12, 11), (100, 51)], radius=16, fill=(239, 68, 68, 255))
        draw.ellipse([(24, 25), (36, 37)], fill=(255, 255, 255, 255))
        draw.text((44, 18), "LIVE", font=self._font_md, fill=(255, 255, 255, 255))
        short_brand = "AI活工坊 · 铁三角"
        info = f"{short_brand}   在线 {online} · {watched_text} · {f_count}/{f_goal}粉"
        lines = _wrap_text_by_width(draw, info, self._font_md, max_width=w - 130, max_lines=1)
        draw.text((114, 18), lines[0] if lines else info, font=self._font_md, fill=(15, 23, 42, 255))

        self._telemetry_key = key
        self._telemetry_overlay = img
        return img

    def _get_countdown_overlay(self, countdown_sec: int, in_crisis: bool) -> Image.Image:
        key = (countdown_sec, in_crisis)
        if self._countdown_overlay is not None and self._countdown_key == key:
            return self._countdown_overlay

        w, h = 445, 62
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        bg = (254, 226, 226, 246) if in_crisis else (255, 255, 255, 242)
        outline = (220, 38, 38, 255) if in_crisis else (124, 58, 237, 230)
        draw.rounded_rectangle([(0, 0), (w - 1, h - 1)], radius=20, fill=bg, outline=outline, width=3)
        label = "危机耗能加倍!" if in_crisis else "工坊续命倒计时"
        draw.text((18, 19), label, font=self._font_sm, fill=(185, 28, 28, 255) if in_crisis else (109, 40, 217, 255))
        clock_str = _fmt_hhmmss(countdown_sec)
        draw.text((w - 22, 11), clock_str, font=self._font_xl, fill=(15, 23, 42, 255), anchor="ra")

        self._countdown_key = key
        self._countdown_overlay = img
        return img

    def _get_world_hud_overlay(self, ws: Dict[str, Any]) -> Image.Image:
        wstate = ws["world"]
        key = (
            wstate["level"],
            wstate["build_xp"],
            wstate["code_pts"],
            wstate["compute_pts"],
            wstate["rice_bowls"],
            wstate["active_worker_count"],
            wstate["active_event"]["title"] if wstate.get("active_event") else "",
        )
        if self._world_hud_overlay is not None and self._world_hud_key == key:
            return self._world_hud_overlay

        img = Image.new("RGBA", (WORLD_WIDTH, 88), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle(
            [(14, 10), (770, 74)], radius=16, fill=(255, 255, 255, 236), outline=(59, 130, 246, 200), width=2
        )
        title = f"Lv.{wstate['level']} {wstate['level_name']}  |  在线小人 {wstate['active_worker_count']} 名"
        draw.text((28, 16), title, font=self._font_md, fill=(15, 23, 42, 255))
        stats_line = (
            f"代码 {wstate['code_pts']} · 算力 {wstate['compute_pts']} · 白米饭 {wstate['rice_bowls']} · "
            f"建造经验 {wstate['build_xp']}/{wstate['next_level_xp']}"
        )
        draw.text((28, 44), stats_line, font=self._font_sm, fill=(37, 99, 235, 255))

        ev = wstate.get("active_event")
        if ev:
            draw.rounded_rectangle(
                [(786, 10), (WORLD_WIDTH - 14, 74)],
                radius=16,
                fill=(254, 226, 226, 246),
                outline=(220, 38, 38, 255),
                width=2,
            )
            draw.text((804, 15), f"告警: {ev['title']}", font=self._font_md, fill=(185, 28, 28, 255))
            desc_line = _wrap_text_by_width(draw, ev["desc"], self._font_sm, max_width=WORLD_WIDTH - 835, max_lines=1)
            draw.text((804, 44), desc_line[0] if desc_line else ev["desc"], font=self._font_sm, fill=(127, 29, 29, 255))

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

        w, h = WORLD_WIDTH, 240
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle(
            [(0, 0), (w - 1, h - 1)], radius=22, fill=(15, 23, 42, 238), outline=(56, 189, 248, 210), width=3
        )

        # Header + 4-stage pipeline pills
        draw.rounded_rectangle([(18, 14), (448, 50)], radius=12, fill=(30, 58, 138, 240))
        draw.text((32, 20), "AI Agent 实时工作台 · 此刻正在工作", font=self._font_md, fill=(224, 242, 254, 255))

        px = 470
        for s_idx, stage_lbl in enumerate(PIPELINE_STAGES):
            is_cur = s_idx == int(wb["pipeline_stage"])
            sw = int(draw.textlength(stage_lbl, font=self._font_sm)) + 26
            fill_c = (16, 185, 129, 255) if is_cur else (51, 65, 85, 220)
            txt_c = (255, 255, 255, 255) if is_cur else (148, 163, 184, 255)
            draw.rounded_rectangle([(px, 15), (px + sw, 49)], radius=12, fill=fill_c)
            draw.text((px + 13, 21), stage_lbl, font=self._font_sm, fill=txt_c)
            px += sw + 10

        task_line = _wrap_text_by_width(
            draw, f"当前任务：{wb['active_task']}", self._font_md, max_width=w - 52, max_lines=1
        )
        draw.text(
            (24, 60), task_line[0] if task_line else wb["active_task"], font=self._font_md, fill=(250, 204, 21, 255)
        )

        ly = 94
        for row in list(logs)[-5:]:
            tag = row["tag"]
            tag_bg = (
                (220, 38, 38, 240)
                if tag in ("ALERT", "ERROR")
                else ((16, 185, 129, 235) if tag in ("FIX", "CODE", "TEST") else (37, 99, 235, 235))
            )
            draw.text((24, ly + 2), row["ts"], font=self._font_sm, fill=(148, 163, 184, 255))
            draw.rounded_rectangle([(112, ly), (186, ly + 24)], radius=8, fill=tag_bg)
            draw.text((120, ly + 2), tag[:6], font=self._font_xs, fill=(255, 255, 255, 255))
            line = _wrap_text_by_width(draw, row["text"], self._font_sm, max_width=w - 220, max_lines=1)
            draw.text((198, ly + 1), line[0] if line else row["text"], font=self._font_sm, fill=(226, 232, 240, 255))
            ly += 28

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

        pw, ph = 538, 636
        img = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Section 1: Today Contributors & Memory Badges (y=0..202)
        draw.rounded_rectangle(
            [(0, 0), (pw - 1, 198)], radius=16, fill=(248, 250, 252, 238), outline=(148, 163, 184, 185), width=2
        )
        draw.text(
            (16, 10),
            f"今日共建榜 · 记住 {ws['world']['total_known_viewers']} 位小伙伴",
            font=self._font_md,
            fill=(15, 23, 42, 255),
        )
        y = 42
        if not builders:
            draw.text(
                (18, 68), "虚位以待！发「开工」成为工坊第 1 号建设者", font=self._font_sm, fill=(100, 116, 139, 255)
            )
        else:
            for idx, b in enumerate(builders[:5], 1):
                badge_str = f" [{b['badge']}]" if b.get("badge") else f" · {b['tier']}"
                left_txt = f"{idx}. {b['alias']}{badge_str}"
                left_wrapped = _wrap_text_by_width(draw, left_txt, self._font_sm, max_width=pw - 120, max_lines=1)
                draw.text(
                    (16, y), left_wrapped[0] if left_wrapped else left_txt, font=self._font_sm, fill=(30, 41, 59, 255)
                )
                draw.text((pw - 16, y), f"{b['score']}分", font=self._font_sm, fill=(37, 99, 235, 255), anchor="ra")
                y += 30

        # Section 2: Viewer Suggestions Queue (y=210..378)
        draw.rounded_rectangle(
            [(0, 210), (pw - 1, 376)], radius=16, fill=(245, 243, 255, 238), outline=(167, 139, 250, 195), width=2
        )
        draw.text((16, 220), "观众建议单（真采纳 · 署名上墙）", font=self._font_md, fill=(91, 33, 182, 255))
        sy = 252
        if not suggestions:
            draw.text(
                (16, 282),
                "发「建议 加个新建筑/功能」，Agent 现场看弹幕就改！",
                font=self._font_sm,
                fill=(107, 114, 128, 255),
            )
        else:
            for s in list(suggestions)[-3:]:
                done_flag = s["status"] == "已采纳"
                pill_bg = (16, 185, 129, 255) if done_flag else (124, 58, 237, 255)
                draw.rounded_rectangle([(14, sy + 2), (82, sy + 24)], radius=8, fill=pill_bg)
                draw.text((22, sy + 3), s["status"], font=self._font_xs, fill=(255, 255, 255, 255))
                s_txt = _wrap_text_by_width(
                    draw, f"{s['id']} {s['author']}: {s['text']}", self._font_sm, max_width=pw - 110, max_lines=1
                )
                draw.text((92, sy + 2), s_txt[0] if s_txt else s["text"], font=self._font_sm, fill=(30, 41, 59, 255))
                sy += 38

        # Section 3: Live Sanitized Danmaku Feed (y=388..636)
        draw.rounded_rectangle(
            [(0, 388), (pw - 1, ph - 1)], radius=16, fill=(241, 245, 249, 235), outline=(148, 163, 184, 185), width=2
        )
        draw.text((16, 398), "实时弹幕流", font=self._font_md, fill=(15, 23, 42, 255))
        dy = 430
        if not dm:
            draw.text(
                (16, 466),
                "弹幕监听已接通，发送「开工」试试 3 秒出小人！",
                font=self._font_sm,
                fill=(100, 116, 139, 255),
            )
        else:
            for item in list(dm)[-4:]:
                et = item["event_type"]
                t_col = (
                    (217, 119, 6, 255)
                    if et == "gift"
                    else ((2, 132, 199, 255) if et == "enter" else (37, 99, 235, 255))
                )
                t_lbl = "投喂" if et == "gift" else ("进场" if et == "enter" else "弹幕")
                draw.rounded_rectangle([(14, dy + 2), (62, dy + 24)], radius=8, fill=t_col)
                draw.text((21, dy + 3), t_lbl, font=self._font_xs, fill=(255, 255, 255, 255))
                msg_line = _wrap_text_by_width(
                    draw, f"{item['user_alias']}: {item['text']}", self._font_sm, max_width=pw - 86, max_lines=1
                )
                draw.text(
                    (70, dy + 2), msg_line[0] if msg_line else item["text"], font=self._font_sm, fill=(15, 23, 42, 255)
                )
                dy += 44

        self._right_key = key
        self._right_overlay = img
        return img

    def _get_subtitle_overlay(self, active_speaker: SpeakerId, turn: Optional[PersonaTurn]) -> Image.Image:
        text = (
            turn.text
            if turn is not None
            else "欢迎来到 AI 活工坊！发「开工」「写代码」「修Bug」就能在地图里生成你的专属小人一起建设！"
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

        w, h = 1830, 160
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        token = self._dock_portraits[speaker]
        img.paste(token, (0, 12), token)

        sx0 = token.width + 20
        accent = SPEAKER_ACCENT_RGB.get(speaker, (37, 99, 235))
        s_name = PERSONAS[speaker].display_name
        nw = int(draw.textlength(s_name, font=self._font_lg)) + 36
        draw.rounded_rectangle([(sx0, 8), (sx0 + nw, 46)], radius=16, fill=(*accent, 255))
        draw.text((sx0 + 18, 12), s_name, font=self._font_lg, fill=(255, 255, 255, 255))

        mood_lbl = MOOD_LABELS.get(mood, "实时解说")
        mw = int(draw.textlength(mood_lbl, font=self._font_sm)) + 26
        mx0 = sx0 + nw + 12
        draw.rounded_rectangle([(mx0, 11), (mx0 + mw, 43)], radius=12, fill=(51, 65, 85, 240))
        draw.text((mx0 + 13, 16), mood_lbl, font=self._font_sm, fill=(226, 232, 240, 255))

        lines = _wrap_text_by_width(draw, text, self._font_sub, max_width=w - sx0 - 30, max_lines=2)
        ty = 58
        for line in lines:
            draw.text((sx0 + 2, ty + 2), line, font=self._font_sub, fill=(2, 6, 23, 210))
            draw.text((sx0, ty), line, font=self._font_sub, fill=(255, 255, 255, 255))
            ty += 46

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
        del poll_snapshot  # Unused in World mode; kept in signature for HeadlessLiveStreamer compatibility
        t = frame_index / float(self.fps)
        level = max(0.0, min(1.0, float(audio_level)))
        ws = self.world.export_state_dict()
        telem = ws["telemetry"]
        wstate = ws["world"]
        f_count = (
            telem["follower_count"] if follower_count is None else max(telem["follower_count"], int(follower_count))
        )
        f_goal = telem["follower_goal"] if follower_goal is None else max(1, int(follower_goal))

        frame = self._static_bg.copy()

        # 1) Top telemetry pill & giant countdown clock
        tel_overlay = self._get_telemetry_overlay(telem["online"], telem["watched_text"], f_count, f_goal)
        frame.paste(tel_overlay, (24, 14), tel_overlay)

        cd_overlay = self._get_countdown_overlay(int(wstate["countdown_sec"]), wstate.get("active_event") is not None)
        frame.paste(cd_overlay, (876, 14), cd_overlay)

        # 2) Upper-left 2D Living Workshop Map (x=24..1310, y=92..628)
        world_canvas = self._get_world_level_layer(wstate["level"]).copy()
        hud_overlay = self._get_world_hud_overlay(ws)
        world_canvas.paste(hud_overlay, (0, 0), hud_overlay)

        wdraw = ImageDraw.Draw(world_canvas)
        with self.world._lock:
            hosts_snapshot = [(sid, h.x, h.y, h.action_label, h.phase) for sid, h in self.world.host_actors.items()]
            viewers_snapshot = [
                (v.alias, v.x, v.y, v.action_label, v.color_idx, v.badge) for v in self.world.viewer_actors.values()
            ]
            popups_snapshot = [(p.text, p.x, p.y, p.color) for p in self.world.popups]

        # Draw viewer pixel workers
        for alias, vx, vy, vact, cidx, vbadge in viewers_snapshot:
            bob = int(round(3.0 * abs(math.sin(t * 6.0 + cidx))))
            tok = self._viewer_tokens[cidx % len(self._viewer_tokens)]
            px = int(round(vx - tok.width / 2))
            py = int(round(vy - tok.height + 6 - bob))
            world_canvas.paste(tok, (px, py), tok)
            tag = f"{alias[:7]}·{vact[:6]}" if vact else alias[:8]
            tw = int(wdraw.textlength(tag, font=self._font_xs)) + 12
            tx0 = max(6, min(WORLD_WIDTH - tw - 6, int(round(vx - tw / 2))))
            ty0 = max(78, py - 22)
            wdraw.rounded_rectangle([(tx0, ty0), (tx0 + tw, ty0 + 20)], radius=8, fill=(15, 23, 42, 215))
            wdraw.text((tx0 + 6, ty0 + 2), tag, font=self._font_xs, fill=(255, 255, 255, 255))
            if vbadge:
                bw = int(wdraw.textlength(vbadge, font=self._font_xs)) + 8
                wdraw.rounded_rectangle([(tx0, ty0 - 17), (tx0 + bw, ty0 - 1)], radius=6, fill=(217, 119, 6, 240))
                wdraw.text((tx0 + 4, ty0 - 16), vbadge, font=self._font_xs, fill=(255, 255, 255, 255))

        # Draw AI host actors
        resolved_active: SpeakerId = active_speaker if active_speaker in self._host_tokens else self.cast[0]
        for sid, hx, hy, hact, hphase in hosts_snapshot:
            if sid not in self._host_tokens:
                continue
            tok = self._host_tokens[sid]
            is_act = sid == resolved_active
            bob = int(round((8.0 if is_act else 3.0) * abs(math.sin(t * 5.0 + hphase))))
            px = int(round(hx - tok.width / 2))
            py = int(round(hy - tok.height + 8 - bob))
            world_canvas.paste(tok, (px, py), tok)
            accent = SPEAKER_ACCENT_RGB.get(sid, (37, 99, 235))
            lbl = f"{PERSONAS[sid].short_name}·{hact}"
            lw = int(wdraw.textlength(lbl, font=self._font_xs)) + 14
            lx0 = max(6, min(WORLD_WIDTH - lw - 6, int(round(hx - lw / 2))))
            ly0 = min(WORLD_HEIGHT - 24, int(round(hy + 10)))
            wdraw.rounded_rectangle(
                [(lx0, ly0), (lx0 + lw, ly0 + 22)], radius=9, fill=(*accent, 242), outline=(255, 255, 255, 255), width=1
            )
            wdraw.text((lx0 + 7, ly0 + 2), lbl, font=self._font_xs, fill=(255, 255, 255, 255))

        # Draw floating popups inside the 2D world
        for ptext, popx, popy, pcol in popups_snapshot:
            pw = int(wdraw.textlength(ptext, font=self._font_sm)) + 16
            px0 = max(8, min(WORLD_WIDTH - pw - 8, int(round(popx - pw / 2))))
            py0 = max(78, min(WORLD_HEIGHT - 30, int(round(popy))))
            wdraw.rounded_rectangle(
                [(px0, py0), (px0 + pw, py0 + 26)], radius=10, fill=(255, 255, 255, 245), outline=(*pcol, 255), width=2
            )
            wdraw.text((px0 + 8, py0 + 3), ptext, font=self._font_sm, fill=(*pcol, 255))

        # Optional world/follower celebration banner inside bottom of map
        active_banner = celebration_text.strip() or wstate.get("active_banner") or ""
        if active_banner:
            bw = min(WORLD_WIDTH - 40, int(wdraw.textlength(active_banner, font=self._font_md)) + 60)
            bx0 = (WORLD_WIDTH - bw) // 2
            wdraw.rounded_rectangle(
                [(bx0, WORLD_HEIGHT - 56), (bx0 + bw, WORLD_HEIGHT - 12)],
                radius=18,
                fill=(254, 243, 199, 248),
                outline=(245, 158, 11, 255),
                width=3,
            )
            wdraw.text(
                (WORLD_WIDTH // 2, WORLD_HEIGHT - 34),
                active_banner,
                font=self._font_md,
                fill=(120, 53, 15, 255),
                anchor="mm",
            )

        frame.paste(world_canvas, (24, 92), world_canvas)

        # 3) Lower-left Real-Time Agent Workbench (x=24..1310, y=640..880)
        wb_overlay = self._get_workbench_overlay(ws["workbench"])
        frame.paste(wb_overlay, (24, 640), wb_overlay)

        # 4) Right-side dynamic Builders / Suggestions / Live Danmaku (inside shell at y=228..864)
        right_overlay = self._get_right_panel_overlay(ws)
        frame.paste(right_overlay, (1342, 228), right_overlay)

        # 5) Bottom subtitle dock + animated audio waveform bars
        sub_overlay = self._get_subtitle_overlay(resolved_active, current_turn)
        frame.paste(sub_overlay, (46, 898), sub_overlay)

        eq_color = SPEAKER_EQ_LIGHT_RGB.get(resolved_active, (56, 189, 248))
        eq_peak = SPEAKER_EQ_PEAK_RGB.get(resolved_active, (37, 99, 235))
        fdraw = ImageDraw.Draw(frame)
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
    "DEFAULT_MEMORY_PATH",
    "LEVEL_THRESHOLDS",
    "PIPELINE_STAGES",
    "STATIONS",
    "WORLD_HEIGHT",
    "WORLD_WIDTH",
    "FloatingPopup",
    "HostActor",
    "LiveAgentWorld",
    "ViewerActor",
    "ViewerMemoryStore",
    "WorldStageRenderer",
]
