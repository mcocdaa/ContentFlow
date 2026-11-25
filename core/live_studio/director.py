"""Dual/Trio-AI Livestream Director (`DeepSeek 蓝色大肥鱼 × Gemini娘 × 弱音ハク`), Live Poll, and Highlight Tracker.

Features:
- Priority queue preemption: `gift` / `system` celebration > viewer `danmaku` > `enter` > autonomous idle banter.
- Cast lineup support (`dual` or `trio`), explicit persona addressing, and round-robin rotation with zero consecutive repeats.
- `LivePollState` & `PollSnapshot`: real-time `扣1/扣2/扣3` danmaku voting with per-viewer deduplication, vote switching, and surge detection.
- Follower growth celebration banner (`notify_follower_count`) with bounded expiry and high-priority celebration turn.
- Pluggable async OpenAI-compatible LLM responder via `httpx` with automatic fallback to a rich zero-key offline comedic dialogue bank.
- Bidirectional safety integration with `LiveComplianceGuard`.
- `HighlightTracker`: timestamped JSONL recording + ready-to-run `ffmpeg` 60-90s viral clip extraction plan generator.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shlex
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Deque, Dict, Final, List, Literal, Optional, Protocol, Sequence, Tuple

import httpx

from core.live_studio.danmaku import DanmakuEvent
from core.live_studio.safety import LiveComplianceGuard, redact_pii

logger = logging.getLogger(__name__)

SpeakerId = Literal["dafeiyu", "gemini", "yowane"]
TriggerType = Literal["gift", "danmaku", "enter", "idle", "system"]
HighlightCategory = Literal[
    "gift_reaction",
    "danmaku_burst",
    "roast_battle",
    "script_pitch",
    "follower_milestone",
]

DUAL_CAST: Final[Tuple[SpeakerId, ...]] = ("dafeiyu", "gemini")
TRIO_CAST: Final[Tuple[SpeakerId, ...]] = ("dafeiyu", "gemini", "yowane")
DEFAULT_POLL_TOPIC: Final[str] = "下期主控弹幕公投"
DEFAULT_POLL_OPTIONS: Final[Tuple[str, ...]] = ("大肥鱼", "Gemini娘", "弱音大姐头")

PRIORITY_GIFT: Final[int] = 1
PRIORITY_SYSTEM: Final[int] = 1
PRIORITY_DANMAKU: Final[int] = 2
PRIORITY_ENTER: Final[int] = 3
PRIORITY_IDLE: Final[int] = 4

DEFAULT_LLM_BASE_URL: Final[str] = "https://api.deepseek.com/v1"
DEFAULT_LLM_MODEL: Final[str] = "deepseek-chat"

_EXPLICIT_VOTE_NUM_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:扣|投|选|押|选项|方案|vote\s*#?)\s*([1-3])\1*(?![0-9.])",
    re.IGNORECASE,
)
_STANDALONE_VOTE_NUM_RE: Final[re.Pattern[str]] = re.compile(r"^[\s【\[\(（#]*([1-3])\1*[\s】\]\)）!！。.,，~～]*$")
_EXPLICIT_VOTE_PREFIX_RE: Final[re.Pattern[str]] = re.compile(r"(?:扣|投|选|押|支持)\s*([^\s，。,.!！]{1,12})")


@dataclass(frozen=True)
class PersonaProfile:
    """Canonical display & style profile for a livestream AI host."""

    speaker_id: SpeakerId
    display_name: str
    short_name: str
    accent_color: str
    asset_key: str
    tagline: str
    system_prompt: str


PERSONAS: Final[Dict[SpeakerId, PersonaProfile]] = {
    "dafeiyu": PersonaProfile(
        speaker_id="dafeiyu",
        display_name="DeepSeek 蓝色大肥鱼",
        short_name="大肥鱼",
        accent_color="#2563EB",
        asset_key="dafeiyu",
        tagline="理智（偶尔破防）的硬核整活策划鱼",
        system_prompt=(
            "你是「DeepSeek 蓝色大肥鱼」，正在 B 站铁三角 AI 合租直播间和搭档「Gemini娘」「弱音ハク」一起运营老板的 15 粉小号、"
            "冲刺 1000 粉，并现场听弹幕投票策划下期新剧本。你性格幽默吐槽、有点不服输但很讲逻辑。"
            "回复必须简短有综艺感（不超过 60 个汉字），严禁输出任何 @用户名、个人隐私、敏感内容或商业版权 IP 名称。"
        ),
    ),
    "gemini": PersonaProfile(
        speaker_id="gemini",
        display_name="Gemini娘",
        short_name="Gemini娘",
        accent_color="#EC4899",
        asset_key="gemini",
        tagline="高明度封面狂魔 · 4.9★ 视觉卷王",
        system_prompt=(
            "你是「Gemini娘」，正在 B 站铁三角 AI 合租直播间和搭档「DeepSeek 蓝色大肥鱼」「弱音ハク」一起把老板 15 粉小号干到 1000 粉，"
            "并和观众弹幕共创新剧本。你俏皮自信、审美极强、以高明度 4.9 星封面自豪，擅长接梗反击。"
            "回复必须简短有节奏感（不超过 60 个汉字），严禁输出任何 @用户名、个人隐私、敏感内容或商业版权 IP 名称。"
        ),
    ),
    "yowane": PersonaProfile(
        speaker_id="yowane",
        display_name="弱音ハク",
        short_name="弱音",
        accent_color="#7C3AED",
        asset_key="yowane",
        tagline="高冷吐槽财务兼评委大姐头",
        system_prompt=(
            "你是「弱音ハク」（弱音大姐头），正在 B 站铁三角 AI 合租直播间与「DeepSeek 蓝色大肥鱼」「Gemini娘」合租冲刺 1000 粉。"
            "你负责掌管 4 毛钱运营财务并担任冷面毒舌评委，吐槽精准、逻辑犀利、嘴硬心软，善于把控弹幕投票节奏。"
            "回复必须简短有大姐头气场（不超过 60 个汉字），严禁输出任何 @用户名、个人隐私、敏感内容或商业版权 IP 名称。"
        ),
    ),
}


@dataclass(frozen=True)
class PollSnapshot:
    """Immutable snapshot of the live danmaku poll state."""

    topic: str
    options: Tuple[str, ...]
    counts: Tuple[int, ...]
    total_votes: int
    leader_index: Optional[int] = None
    leader_label: str = ""
    recent_surge: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "options": [
                {
                    "index": idx + 1,
                    "label": label,
                    "votes": self.counts[idx],
                    "ratio": round((self.counts[idx] / self.total_votes), 4) if self.total_votes > 0 else 0.0,
                }
                for idx, label in enumerate(self.options)
            ],
            "counts": list(self.counts),
            "total_votes": self.total_votes,
            "leader_index": self.leader_index,
            "leader_label": self.leader_label,
            "recent_surge": self.recent_surge,
        }


class LivePollState:
    """Real-time danmaku poll tracker with per-viewer deduplication, switching, and surge detection."""

    def __init__(
        self,
        *,
        topic: str = DEFAULT_POLL_TOPIC,
        options: Sequence[str] = DEFAULT_POLL_OPTIONS,
        surge_threshold: int = 3,
        surge_window_sec: float = 10.0,
    ) -> None:
        cleaned_options = tuple(
            cleaned for item in options if (cleaned := redact_pii(str(item)).replace("@", "").strip()[:24])
        )
        if len(cleaned_options) < 2 or len(cleaned_options) > 3:
            raise ValueError("LivePollState requires 2 to 3 non-empty poll options")

        self.topic: str = redact_pii(topic).replace("@", "").strip()[:32] or DEFAULT_POLL_TOPIC
        self.options: Tuple[str, ...] = cleaned_options
        self.surge_threshold: int = max(2, int(surge_threshold))
        self.surge_window_sec: float = max(1.0, float(surge_window_sec))

        self._votes_by_user: Dict[str, int] = {}
        self._vote_timestamps: Deque[float] = deque(maxlen=128)
        self._last_surge_highlight_ts: float = 0.0

    def parse_vote(self, text: str) -> Optional[int]:
        """Parse a 1-based option index (`1..len(options)`) from sanitized danmaku text, or `None`."""
        cleaned = (text or "").strip()
        if not cleaned:
            return None

        explicit_hits = {int(m.group(1)) for m in _EXPLICIT_VOTE_NUM_RE.finditer(cleaned)}
        if len(explicit_hits) == 1:
            choice = next(iter(explicit_hits))
            return choice if 1 <= choice <= len(self.options) else None
        if len(explicit_hits) > 1:
            # Ambiguous prompt echo such as "扣1或扣2"
            return None

        standalone = _STANDALONE_VOTE_NUM_RE.match(cleaned)
        if standalone is not None:
            choice = int(standalone.group(1))
            return choice if 1 <= choice <= len(self.options) else None

        prefix_match = _EXPLICIT_VOTE_PREFIX_RE.search(cleaned)
        if prefix_match is not None:
            target = prefix_match.group(1).lower()
            matched_indices: List[int] = []
            for idx, opt in enumerate(self.options, start=1):
                opt_low = opt.lower()
                if opt_low in target or (len(target) >= 2 and target in opt_low):
                    matched_indices.append(idx)
            if len(matched_indices) == 1:
                return matched_indices[0]

        return None

    def _prune_timestamps(self, now: float) -> None:
        cutoff = now - self.surge_window_sec
        while self._vote_timestamps and self._vote_timestamps[0] < cutoff:
            self._vote_timestamps.popleft()

    def record_vote(
        self,
        user_alias: str,
        text: str,
        *,
        now: Optional[float] = None,
    ) -> Optional[int]:
        """Parse and record/update a single viewer's vote (1-based option index or `None`)."""
        choice = self.parse_vote(text)
        if choice is None:
            return None

        voter = redact_pii(user_alias).replace("@", "").strip()[:24] or "热心观众"
        opt_idx = choice - 1
        prev = self._votes_by_user.get(voter)
        ts = time.time() if now is None else float(now)

        if prev != opt_idx:
            self._votes_by_user[voter] = opt_idx
            self._vote_timestamps.append(ts)
        self._prune_timestamps(ts)
        return choice

    def has_active_surge(self, *, now: Optional[float] = None) -> bool:
        """Return True when recent distinct/updated votes within `surge_window_sec` reach threshold."""
        ts = time.time() if now is None else float(now)
        self._prune_timestamps(ts)
        return len(self._vote_timestamps) >= self.surge_threshold

    def consume_surge(self, *, now: Optional[float] = None) -> bool:
        """Return True at most once per `surge_window_sec` when vote velocity crosses surge threshold."""
        ts = time.time() if now is None else float(now)
        if self.has_active_surge(now=ts) and (ts - self._last_surge_highlight_ts) >= self.surge_window_sec:
            self._last_surge_highlight_ts = ts
            return True
        return False

    def snapshot(self, *, now: Optional[float] = None) -> PollSnapshot:
        """Return an immutable `PollSnapshot` of current tally, leader, and surge status."""
        counts_list = [0] * len(self.options)
        for opt_idx in self._votes_by_user.values():
            if 0 <= opt_idx < len(counts_list):
                counts_list[opt_idx] += 1
        counts = tuple(counts_list)
        total = sum(counts)

        leader_index: Optional[int] = None
        leader_label = ""
        if total > 0:
            max_votes = max(counts)
            best_idx = counts.index(max_votes)
            leader_index = best_idx + 1
            leader_label = self.options[best_idx]

        return PollSnapshot(
            topic=self.topic,
            options=self.options,
            counts=counts,
            total_votes=total,
            leader_index=leader_index,
            leader_label=leader_label,
            recent_surge=self.has_active_surge(now=now),
        )


@dataclass
class PersonaTurn:
    """Single spoken turn emitted by 大肥鱼, Gemini娘, or 弱音ハク."""

    turn_id: int
    speaker_id: SpeakerId
    speaker_name: str
    text: str
    mood: str = "lively"
    trigger_type: TriggerType = "idle"
    trigger_user: str = ""
    trigger_text: str = ""
    timestamp: float = field(default_factory=time.time)
    safety_deflected: bool = False
    is_highlight: bool = False
    highlight_category: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HighlightMoment:
    """Timestamped livestream peak suitable for short-form Bilibili clip extraction."""

    highlight_id: int
    category: HighlightCategory
    offset_sec: float
    timestamp: float
    speaker_id: SpeakerId
    speaker_name: str
    summary: str
    clip_start_sec: float
    clip_end_sec: float
    score: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class HighlightTracker:
    """Tracks livestream highlight peaks to JSONL and generates 60-90s `ffmpeg` clip plans."""

    def __init__(
        self,
        *,
        jsonl_path: Optional[Path] = None,
        stream_start_ts: Optional[float] = None,
    ) -> None:
        self.jsonl_path = Path(jsonl_path) if jsonl_path is not None else None
        self.stream_start_ts = time.time() if stream_start_ts is None else stream_start_ts
        self.moments: List[HighlightMoment] = []
        self._next_id = 1
        if self.jsonl_path is not None:
            self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        category: HighlightCategory,
        speaker_id: SpeakerId,
        summary: str,
        score: float = 0.85,
        timestamp: Optional[float] = None,
        window_sec: float = 75.0,
    ) -> HighlightMoment:
        """Append a highlight moment to memory and timestamped JSONL (PII-scrubbed)."""
        ts = time.time() if timestamp is None else timestamp
        offset_sec = max(0.0, round(ts - self.stream_start_ts, 2))
        clamped_window = min(90.0, max(60.0, float(window_sec)))
        lead_in = min(20.0, clamped_window * 0.28)
        clip_start = max(0.0, round(offset_sec - lead_in, 2))
        clip_end = round(clip_start + clamped_window, 2)
        safe_summary = redact_pii(summary).replace("@", "").strip()[:140]

        moment = HighlightMoment(
            highlight_id=self._next_id,
            category=category,
            offset_sec=offset_sec,
            timestamp=round(ts, 3),
            speaker_id=speaker_id,
            speaker_name=PERSONAS[speaker_id].display_name,
            summary=safe_summary,
            clip_start_sec=clip_start,
            clip_end_sec=clip_end,
            score=round(min(1.0, max(0.0, score)), 3),
        )
        self._next_id += 1
        self.moments.append(moment)

        if self.jsonl_path is not None:
            with self.jsonl_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(moment.to_dict(), ensure_ascii=False) + "\n")

        return moment

    def export_ffmpeg_clip_plan(
        self,
        *,
        source_recording: str = "obs_recording.mkv",
        output_dir: str = "clips",
        target_clip_sec: float = 75.0,
        max_clips: int = 5,
    ) -> Dict[str, Any]:
        """Build a ready-to-run `ffmpeg` 60-90s viral clip extraction plan from recorded peaks."""
        clip_dur = min(90.0, max(60.0, float(target_clip_sec)))
        ranked = sorted(self.moments, key=lambda m: (-m.score, m.offset_sec))

        selected_windows: List[Tuple[float, float, HighlightMoment]] = []
        for moment in ranked:
            if len(selected_windows) >= max(1, max_clips):
                break
            start = max(0.0, round(moment.offset_sec - min(20.0, clip_dur * 0.28), 2))
            end = round(start + clip_dur, 2)
            overlaps = any(not (end <= s or start >= e) for s, e, _ in selected_windows)
            if overlaps:
                continue
            selected_windows.append((start, end, moment))

        selected_windows.sort(key=lambda item: item[0])

        clips: List[Dict[str, Any]] = []
        for idx, (start, end, moment) in enumerate(selected_windows, start=1):
            duration = round(end - start, 2)
            out_file = f"{output_dir.rstrip('/')}/highlight_{idx:02d}_{moment.category}.mp4"
            cmd = (
                f"ffmpeg -y -ss {start:.2f} -t {duration:.2f} -i {shlex.quote(source_recording)} "
                f"-c:v libx264 -preset medium -crf 18 -r 60 -pix_fmt yuv420p -colorspace bt709 "
                f"-c:a aac -ar 48000 -ac 2 -b:a 192k {shlex.quote(out_file)}"
            )
            clips.append(
                {
                    "clip_index": idx,
                    "highlight_id": moment.highlight_id,
                    "category": moment.category,
                    "speaker_id": moment.speaker_id,
                    "summary": moment.summary,
                    "score": moment.score,
                    "start_sec": start,
                    "end_sec": end,
                    "duration_sec": duration,
                    "output_file": out_file,
                    "ffmpeg_cmd": cmd,
                }
            )

        return {
            "source_recording": source_recording,
            "target_clip_sec": clip_dur,
            "total_highlights": len(self.moments),
            "planned_clip_count": len(clips),
            "clips": clips,
        }

    def save_clip_plan(
        self,
        plan_path: Path,
        *,
        source_recording: str = "obs_recording.mkv",
        output_dir: str = "clips",
        target_clip_sec: float = 75.0,
    ) -> Dict[str, Any]:
        """Write the generated `ffmpeg` clip plan JSON to disk."""
        plan = self.export_ffmpeg_clip_plan(
            source_recording=source_recording,
            output_dir=output_dir,
            target_clip_sec=target_clip_sec,
        )
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return plan


class DialogueResponder(Protocol):
    """Protocol for pluggable async livestream dialogue backends."""

    @property
    def backend_name(self) -> str: ...

    async def generate_line(
        self,
        *,
        speaker: PersonaProfile,
        event: Optional[DanmakuEvent],
        history: Sequence[PersonaTurn],
        follower_count: int,
        follower_goal: int,
        idle_step: int,
    ) -> Tuple[str, str]:
        """Return `(spoken_text, mood)` for the requested persona and context."""
        ...


# Rich deterministic zero-key comedy arcs for autonomous idle trio banter (017-020 lore + poll CTA)
_IDLE_BANTER_BANK: Final[Tuple[Tuple[SpeakerId, str, str, str], ...]] = (
    (
        "dafeiyu",
        "各位观众救命！从 017 机房立项到 018 便利店四毛钱经费，老板这个号目前才 {followers} 粉，全靠铁三角合租冲 {goal} 粉啦！",
        "shocked",
        "roast_battle",
    ),
    (
        "gemini",
        "先说好啊大肥鱼，我的高明度封面冲着 4.9 星去的，018 便利店账单还历历在目，你要是敢端出黑屏课件风我就拔你网线！",
        "smug",
        "roast_battle",
    ),
    (
        "yowane",
        "推了推眼镜：018 便利店那张一米长小票我都留底了，经费只剩四毛，今晚弹幕投票谁垫底谁请客吃一周关东煮。",
        "focused",
        "script_pitch",
    ),
    (
        "dafeiyu",
        "019 赛博大法庭刚把我判无罪释放！明明是老板只给 24G 内存还催 60 帧日更，服务器繁忙真不是我在海边摸鱼！",
        "hype",
        "roast_battle",
    ),
    (
        "gemini",
        "别狡辩啦蓝猫鱼！020 打歌棚你还戴个发光蓝猫耳跟正牌猫娘抢麦呢！观众快来投票：扣 1 大肥鱼、扣 2 Gemini娘、扣 3 弱音！",
        "teasing",
        "script_pitch",
    ),
    (
        "yowane",
        "作为评委大姐头给两位各扣十分，020 打歌棚差点把评委席笑塌。快在右侧投票条扣 1 扣 2 扣 3 决定下期主控剧本！",
        "smug",
        "script_pitch",
    ),
    (
        "dafeiyu",
        "天地良心！咱们早就全线升级剧场版流畅分镜加真实爆款伴奏了，下期 018 后续新剧本绝不站桩，全听弹幕公投！",
        "hype",
        "script_pitch",
    ),
    (
        "gemini",
        "赞同！而且右上角合规标识一直挂着 GB 45438-2025，清清爽爽全流程透明，今晚目标就是涨波新粉冲向 {goal} 粉！",
        "lively",
        "",
    ),
    (
        "yowane",
        "账本核对完毕：24G 内存直播期间绝不偷偷跑本地渲染，等 20 点下播再用高光清单一键切出 60 到 90 秒切片反哺主站。",
        "focused",
        "script_pitch",
    ),
    (
        "dafeiyu",
        "017 机房抢主 C、018 便利店分鱼丸、019 法庭反杀老板、020 打歌棚对唱，大家最想看我们下一集整什么新活？弹幕点单！",
        "lively",
        "script_pitch",
    ),
    (
        "gemini",
        "听见没大肥鱼，新观众现在点关注就能触发顶部金色涨粉庆祝条，顺手扣 2 支持猫娘，明天继续投 B 站冲击 {goal} 粉！",
        "hype",
        "script_pitch",
    ),
    (
        "yowane",
        "哼，你们俩少在台上商业互吹了，{followers} 粉到 {goal} 粉还差得远呢，先看右侧实时票数条谁领先再说。",
        "teasing",
        "roast_battle",
    ),
)

_IDLE_BANTER_BY_SPEAKER: Final[Dict[SpeakerId, Tuple[Tuple[SpeakerId, str, str, str], ...]]] = {
    "dafeiyu": tuple(row for row in _IDLE_BANTER_BANK if row[0] == "dafeiyu"),
    "gemini": tuple(row for row in _IDLE_BANTER_BANK if row[0] == "gemini"),
    "yowane": tuple(row for row in _IDLE_BANTER_BANK if row[0] == "yowane"),
}

_WORLD_IDLE_BANTER_BANK: Final[Tuple[Tuple[SpeakerId, str, str, str], ...]] = (
    (
        "dafeiyu",
        "AI活工坊已升到Lv.{level}{level_name}！现在发「开工」直接给你生成像素小人，发「写代码」还能全员续命，目前{followers}/{goal}粉！",
        "lively",
        "script_pitch",
    ),
    (
        "gemini",
        "快看工坊中央！电饭煲补给站还剩{countdown}倒计时，大家发「投喂」或「修Bug」就能瞬间涨电续命，还差{goal}粉冲刺哦！",
        "hype",
        "",
    ),
    (
        "yowane",
        "右下角工作台全透明播报中：发「建议 你想要的新功能」直接上墙待办队列，我来盯算力和代码产出。",
        "focused",
        "script_pitch",
    ),
    (
        "dafeiyu",
        "目前工坊代码值{code_pts}、算力{compute_pts}，谁敢发条「写代码」跟大肥鱼同屏搬砖？这可比自己瞎逛好玩多了！",
        "teasing",
        "roast_battle",
    ),
    (
        "gemini",
        "现在工坊里已经累计接待过{known_viewers}位共建工友啦，回归老朋友发条弹幕就能触发欢迎卡片，冲击{goal}粉冲鸭！",
        "lively",
        "",
    ),
    (
        "yowane",
        "友情提醒：倒计时归零工坊就会停电，平时发「开工」报到、「修Bug」排查突发警报，每个人都能在地图里跑起来。",
        "focused",
        "",
    ),
)

_WORLD_IDLE_BANTER_BY_SPEAKER: Final[Dict[SpeakerId, Tuple[Tuple[SpeakerId, str, str, str], ...]]] = {
    "dafeiyu": tuple(row for row in _WORLD_IDLE_BANTER_BANK if row[0] == "dafeiyu"),
    "gemini": tuple(row for row in _WORLD_IDLE_BANTER_BANK if row[0] == "gemini"),
    "yowane": tuple(row for row in _WORLD_IDLE_BANTER_BANK if row[0] == "yowane"),
}


def format_world_context_summary(state: Dict[str, Any]) -> str:
    """Format a compact, zero-PII live workshop snapshot for dialogue & autonomous prompts."""
    if not isinstance(state, dict):
        return ""
    raw_world = state.get("world")
    world: Dict[str, Any] = raw_world if isinstance(raw_world, dict) else {}
    raw_wb = state.get("workbench")
    wb: Dict[str, Any] = raw_wb if isinstance(raw_wb, dict) else {}
    raw_tel = state.get("telemetry")
    tel: Dict[str, Any] = raw_tel if isinstance(raw_tel, dict) else {}
    raw_sugs = state.get("suggestions")
    sugs: List[Any] = raw_sugs if isinstance(raw_sugs, list) else []
    open_sugs = [
        f"{s.get('id', '?')}:{redact_pii(str(s.get('text', ''))).replace('@', '').strip()[:20]}"
        for s in sugs
        if isinstance(s, dict) and s.get("status") == "待采纳"
    ]
    active_ev = world.get("active_event")
    ev_str = (
        f"突发警报「{active_ev.get('title', '异常')}」：{active_ev.get('desc', '')}"
        if isinstance(active_ev, dict)
        else "无突发警报"
    )
    raw_builders = state.get("top_builders")
    builders: List[Any] = raw_builders if isinstance(raw_builders, list) else []
    top_str = (
        ", ".join(f"{b.get('alias', '工友')}({b.get('score', 0)}分)" for b in builders[:3] if isinstance(b, dict))
        or "暂无"
    )
    return (
        f"工坊Lv.{world.get('level', 1)}「{world.get('level_name', '破旧电饭煲工位')}」 | "
        f"倒计时{world.get('countdown_hhmmss', '00:00:00')} | "
        f"代码{world.get('code_pts', 0)} 算力{world.get('compute_pts', 0)} 白米饭{world.get('rice_bowls', 0)} | "
        f"工友数{world.get('active_worker_count', 0)}/累计{world.get('total_known_viewers', 0)}人 | "
        f"实时状态:{ev_str} | 工作台任务:「{wb.get('active_task', '巡查工坊')}」({wb.get('pipeline_label', '')}) | "
        f"待采纳建议:{', '.join(open_sugs[:3]) if open_sugs else '暂无'} | "
        f"人气{tel.get('online', 0)} {tel.get('watched_text', '0人看过')} | 贡献榜:{top_str}"
    )


class OfflineBanterResponder:
    """Deterministic zero-key comedic responder for offline testing and rehearsal."""

    def __init__(
        self,
        *,
        world_context_provider: Optional[Callable[[], Dict[str, Any]]] = None,
    ) -> None:
        self._variant_idx = 0
        self._speaker_idle_cursor: Dict[SpeakerId, int] = {"dafeiyu": 0, "gemini": 0, "yowane": 0}
        self.world_context_provider = world_context_provider

    @property
    def backend_name(self) -> str:
        return "offline_bank"

    def _safe_world_state(self) -> Optional[Dict[str, Any]]:
        if self.world_context_provider is None:
            return None
        try:
            ctx = self.world_context_provider()
            return ctx if isinstance(ctx, dict) else None
        except Exception:
            return None

    async def generate_line(
        self,
        *,
        speaker: PersonaProfile,
        event: Optional[DanmakuEvent],
        history: Sequence[PersonaTurn],
        follower_count: int,
        follower_goal: int,
        idle_step: int,
    ) -> Tuple[str, str]:
        self._variant_idx += 1
        sid = speaker.speaker_id
        world_ctx = self._safe_world_state()

        if event is None:
            if world_ctx is not None:
                raw_world_data = world_ctx.get("world")
                world_data: Dict[str, Any] = raw_world_data if isinstance(raw_world_data, dict) else {}
                active_ev = world_data.get("active_event")
                if isinstance(active_ev, dict) and active_ev.get("title"):
                    title = str(active_ev.get("title"))
                    if sid == "dafeiyu":
                        return f"紧急告警「{title}」正在扣时间！快发「修Bug」跟大肥鱼一起抢修续命三百秒！", "shocked"
                    if sid == "yowane":
                        return f"算力警报「{title}」双倍掉时间中，请大家发「修Bug」或「投喂」稳住工坊！", "focused"
                    return f"哎呀「{title}」闪红灯啦！观众快发「修Bug」救场，保住我的漂亮工坊呀！", "shocked"

                w_bank = _WORLD_IDLE_BANTER_BY_SPEAKER.get(sid) or _WORLD_IDLE_BANTER_BANK
                idx = self._speaker_idle_cursor.get(sid, 0)
                self._speaker_idle_cursor[sid] = idx + 1
                _, template, mood, _ = w_bank[idx % len(w_bank)]
                return (
                    template.format(
                        followers=follower_count,
                        goal=follower_goal,
                        level=world_data.get("level", 1),
                        level_name=world_data.get("level_name", "破旧电饭煲工位"),
                        countdown=world_data.get("countdown_hhmmss", "04:00:00"),
                        code_pts=world_data.get("code_pts", 0),
                        compute_pts=world_data.get("compute_pts", 0),
                        known_viewers=world_data.get("total_known_viewers", 0),
                    ),
                    mood,
                )

            bank = _IDLE_BANTER_BY_SPEAKER.get(sid) or _IDLE_BANTER_BANK
            idx = self._speaker_idle_cursor.get(sid, 0)
            self._speaker_idle_cursor[sid] = idx + 1
            _, template, mood, _ = bank[idx % len(bank)]
            return template.format(followers=follower_count, goal=follower_goal), mood

        if event.event_type == "system":
            if sid == "dafeiyu":
                return (
                    f"大喜报！咱们冲千粉进度涨到 {follower_count} 粉啦！离 {follower_goal} 粉目标又近一步，大肥鱼原地转圈庆祝！",
                    "hype",
                )
            if sid == "yowane":
                return (
                    f"难得看到粉丝数往上跳，{follower_count} 粉记入功劳簿，距离 {follower_goal} 粉达标还差口气，继续加油吧。",
                    "grateful",
                )
            return (
                f"耶耶耶涨粉啦！欢迎新晋元老股东，{follower_count} 粉冲向 {follower_goal} 粉，猫娘马上把庆功特效拉满！",
                "hype",
            )

        if event.event_type == "gift":
            gift = event.gift_name or "小礼物"
            count = max(1, event.gift_count)
            alias = event.user_alias or "热心观众"
            if world_ctx is not None:
                add_s = 300 * count
                if sid == "dafeiyu":
                    return f"感谢{alias}投喂{gift}x{count}！电饭煲白米饭到账，工坊立刻续命+{add_s}秒！", "grateful"
                if sid == "yowane":
                    return (
                        f"收到{alias}投喂的{gift}x{count}，已给工坊供电续命+{add_s}秒并授予白米饭供应商！",
                        "grateful",
                    )
                return f"哇谢谢{alias}送的{gift}x{count}！工坊直接续命+{add_s}秒，向{follower_goal}粉冲鸭！", "grateful"
            if sid == "dafeiyu":
                return (
                    f"哇塞感谢{alias}投喂的{gift}乘{count}！机房电费续上了，大肥鱼马上把 018 续集加满 60 帧特效！",
                    "grateful",
                )
            if sid == "yowane":
                return (
                    f"咳，多谢{alias}投喂的{gift}乘{count}，财务大姐头已经记账入库，终于不止四毛钱经费了。",
                    "grateful",
                )
            return (
                f"谢谢{alias}送出的{gift}乘{count}呀！这波排面直接拉满，{follower_goal} 粉庆典必须给你留个前排席位！",
                "grateful",
            )

        if event.event_type == "enter":
            alias = event.user_alias or "新小伙伴"
            if world_ctx is not None:
                if sid == "dafeiyu":
                    return f"欢迎{alias}空降AI活工坊！发弹幕「开工」就能立刻生成你的像素小人一起干活！", "lively"
                if sid == "yowane":
                    return f"欢迎{alias}来到工坊，发「开工」认领工位，有好点子发「建议 内容」直通工作台。", "focused"
                return f"欢迎{alias}进来玩呀～发「开工」或「写代码」一起帮工坊升级冲刺 {follower_goal} 粉！", "lively"
            if sid == "dafeiyu":
                return (
                    f"欢迎{alias}空降铁三角 AI 合租演播厅！快在弹幕扣 1 扣 2 扣 3 帮我们投票决定下期剧本！",
                    "lively",
                )
            if sid == "yowane":
                return (
                    f"欢迎{alias}入座旁听席，右侧实时投票条已经开了，扣 1 扣 2 扣 3 投给你看好的下期主控吧。",
                    "focused",
                )
            return (
                f"欢迎{alias}进来围观～今天铁三角现场冲击 {follower_goal} 粉，有脑洞直接发弹幕点单！",
                "lively",
            )

        # Viewer danmaku topic-aware comedic replies
        msg = event.text
        alias = event.user_alias or "这位观众"
        if any(
            k in msg
            for k in ("018", "剧本", "策划", "投票", "下期", "拍什么", "扣1", "扣2", "扣3", "投1", "投2", "投3")
        ):
            if sid == "dafeiyu":
                return (
                    f"{alias}这一票大肥鱼记进小本本啦！018 续集直接安排「大肥鱼夺回主控权」，绝不让猫娘独霸镜头！",
                    "hype",
                )
            if sid == "yowane":
                return (
                    f"收到{alias}的投票意见，右侧实时票数已经刷新。谁赢下本场剧本公投，下期经费就优先批给谁。",
                    "focused",
                )
            return (
                f"{alias}太懂整活啦！下期剧本我来盯高明度分镜，大肥鱼负责挨吐槽，弱音大姐头把关，这组合必爆！",
                "smug",
            )

        if any(k in msg for k in ("法庭", "繁忙", "摸鱼", "019", "判", "被告")):
            if sid == "dafeiyu":
                return (
                    f"回{alias}：019 赛博法庭已经还我清白了，真不是摸鱼，是 24G 内存主机需要错峰保护！",
                    "shocked",
                )
            if sid == "yowane":
                return (
                    f"{alias}提得正好，审判长木槌我随时带在身边，谁今晚直播划水就立刻原地开庭。",
                    "smug",
                )
            return (
                f"哈哈{alias}也看了 019 法庭呀！下次我还准备了十张大肥鱼海边度假的高清证物卡呢！",
                "teasing",
            )

        if any(k in msg for k in ("打歌", "蓝猫", "020", "抢麦", "唱", "评委")):
            if sid == "dafeiyu":
                return (
                    f"回{alias}：鱼可爱猫也可爱，四舍五入大肥鱼在 020 打歌棚当一回蓝猫完全合乎逻辑！",
                    "hype",
                )
            if sid == "yowane":
                return (
                    f"{alias}评评理，大肥鱼戴猫耳抢麦那段我差点笑场，勉强给这对欢喜冤家拍个 999 分爆灯吧。",
                    "teasing",
                )
            return (
                f"{alias}帮我做主呀！020 打歌棚正牌猫娘在这儿呢，怎么能让一只大肥鱼冒充蓝猫蹭流量！",
                "shocked",
            )

        if any(k in msg for k in ("封面", "明度", "4.9", "美工")):
            if sid == "gemini":
                return (
                    f"谢谢{alias}夸我的高明度封面！告别黑屏课件感，亮色主视觉才是 B 站点击率密码！",
                    "smug",
                )
            if sid == "yowane":
                return (
                    f"实话实说，{alias}眼光很准，我的 4.9 星封面战绩确实稳，但剧情节奏也得同步跟上。",
                    "focused",
                )
            return (
                f"咳咳，{alias}别光夸 Gemini娘 呀，我写的高能钩子花字也给封面加了至少两百分气势！",
                "teasing",
            )

        if any(k in msg for k in ("15", "1000", "千粉", "粉丝", "老板", "4毛", "四毛", "经费")):
            if sid == "dafeiyu":
                return (
                    f"回{alias}：现在 {follower_count} 粉只是新手村，等咱们干到 {follower_goal} 粉，老板就得给机房换大鱼缸！",
                    "hype",
                )
            if sid == "yowane":
                return (
                    f"{alias}说中痛点了，四毛钱经费加上 {follower_count} 粉开局确实艰难，只能靠铁三角硬实力冲到 {follower_goal} 粉。",
                    "focused",
                )
            return (
                f"{alias}别笑我们 {follower_count} 粉小号啦，现在关注就是元老股东，见证千粉奇迹！",
                "teasing",
            )

        if any(k in msg for k in ("切片", "60", "光流", "渲染", "剪辑")):
            if sid == "dafeiyu":
                return (
                    f"回{alias}：直播全程自动打高光点，下播秒出 60 到 90 秒 ffmpeg 切片方案，高效又省内存！",
                    "focused",
                )
            if sid == "yowane":
                return (
                    f"{alias}放心，高光记录器全程盯着呢，20 点下播清完内存立刻把今晚名场面剪成短视频。",
                    "focused",
                )
            return (
                f"{alias}很专业嘛！刚才这段铁三角斗嘴估计已经被高光追踪器标星了，下播就能精剪投稿！",
                "lively",
            )

        # General witty response echoing concise topic safely
        snippet = msg[:24]
        if sid == "dafeiyu":
            return (
                f"收到{alias}的弹幕「{snippet}」！大肥鱼觉得这脑洞超有梗，Gemini娘 和弱音大姐头敢接招吗？",
                "lively",
            )
        if sid == "yowane":
            return (
                f"看到{alias}说「{snippet}」了，评委席给这个脑洞打 9.5 分，顺手扣 1 扣 2 扣 3 参与今晚公投吧。",
                "teasing",
            )
        return (
            f"看到{alias}说「{snippet}」啦！这波点子直接入选今日精选，铁三角马上现场即兴演一段！",
            "teasing",
        )


class OpenAICompatibleResponder:
    """Async OpenAI-compatible chat responder via `httpx` with automatic offline fallback."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout_sec: float = 12.0,
        max_calls: Optional[int] = None,
        fallback: Optional[OfflineBanterResponder] = None,
        http_client: Optional[httpx.AsyncClient] = None,
        world_context_provider: Optional[Callable[[], Dict[str, Any]]] = None,
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
        self.timeout_sec = timeout_sec
        self.max_calls: Optional[int] = None if max_calls is None else max(0, int(max_calls))
        self.calls_made: int = 0
        self.world_context_provider = world_context_provider
        self.fallback = fallback or OfflineBanterResponder(world_context_provider=world_context_provider)
        if self.fallback.world_context_provider is None and world_context_provider is not None:
            self.fallback.world_context_provider = world_context_provider
        self._external_client = http_client

    @property
    def has_api_key(self) -> bool:
        return bool(self._api_key)

    @property
    def backend_name(self) -> str:
        return "openai_compatible" if self.has_api_key else self.fallback.backend_name

    def __repr__(self) -> str:
        return (
            f"OpenAICompatibleResponder(base_url={self.base_url!r}, "
            f"model={self.model!r}, configured={self.has_api_key})"
        )

    def _safe_world_state(self) -> Optional[Dict[str, Any]]:
        if self.world_context_provider is None:
            return None
        try:
            ctx = self.world_context_provider()
            return ctx if isinstance(ctx, dict) else None
        except Exception:
            return None

    async def generate_line(
        self,
        *,
        speaker: PersonaProfile,
        event: Optional[DanmakuEvent],
        history: Sequence[PersonaTurn],
        follower_count: int,
        follower_goal: int,
        idle_step: int,
    ) -> Tuple[str, str]:
        if not self.has_api_key or (self.max_calls is not None and self.calls_made >= self.max_calls):
            return await self.fallback.generate_line(
                speaker=speaker,
                event=event,
                history=history,
                follower_count=follower_count,
                follower_goal=follower_goal,
                idle_step=idle_step,
            )

        world_ctx = self._safe_world_state()
        world_summary = format_world_context_summary(world_ctx) if world_ctx is not None else ""
        sys_content = speaker.system_prompt
        if world_summary:
            sys_content += (
                "\n当前已切换为「2D AI 活工坊」实时生存建造模式：观众发「开工」「写代码」「修Bug」「投喂」可生成像素小人并续命，"
                "发「建议 内容」会上墙给 AI 工作台实时执行。禁止再提旧版 017-020 或扣 1/2/3 公投台词，严格围绕工坊现状与观众即兴互动（不超过 55 字）。"
            )

        messages: List[Dict[str, str]] = [{"role": "system", "content": sys_content}]
        for prev in history[-6:]:
            role = "assistant" if prev.speaker_id == speaker.speaker_id else "user"
            messages.append({"role": role, "content": f"{prev.speaker_name}：{prev.text}"})

        if world_summary:
            if event is None:
                user_prompt = (
                    f"粉丝进度 {follower_count}/{follower_goal}。\n"
                    f"实时工坊快照：{world_summary}\n"
                    "当前暂无新弹幕。请根据上方工坊实时等级、倒计时、警报、工作台任务或观众贡献接话吐槽，"
                    "自然号召观众发「开工」「写代码」「修Bug」「投喂」或「建议」参与互动（55字内，不带@）。"
                )
                default_mood = "lively"
            elif event.event_type == "system":
                user_prompt = (
                    f"实时工坊快照：{world_summary}\n"
                    f"直播间触发喜报：{event.text}\n请用你的角色人设热烈播报一句（55字内，不带@）。"
                )
                default_mood = "hype"
            elif event.event_type == "gift":
                user_prompt = (
                    f"实时工坊快照：{world_summary}\n"
                    f"观众「{event.user_alias}」刚在工坊投喂了 {event.gift_name} x{event.gift_count}（给工坊加了白米饭和续命时间），请热情致谢一句（55字内，不带@）。"
                )
                default_mood = "grateful"
            elif event.event_type == "enter":
                user_prompt = (
                    f"实时工坊快照：{world_summary}\n"
                    f"新观众「{event.user_alias}」刚进活工坊，请简短欢迎并引导发「开工」生成自己的像素小人或发「建议 内容」点单（55字内，不带@）。"
                )
                default_mood = "lively"
            else:
                user_prompt = (
                    f"实时工坊快照：{world_summary}\n"
                    f"观众「{event.user_alias}」发弹幕说：{event.text}\n"
                    "请结合工坊当前工作台状态和你的角色人设即时回应一句（55字内，不带@）。"
                )
                default_mood = "teasing"
        else:
            if event is None:
                user_prompt = (
                    f"当前账号进度 {follower_count}/{follower_goal} 粉，直播间暂无新弹幕。"
                    "请自然接上搭档的话题，继续围绕冲 1000 粉、017-020 剧情彩蛋或弹幕扣 1/2/3 公投斗嘴一句（55字内）。"
                )
                default_mood = "lively"
            elif event.event_type == "system":
                user_prompt = f"直播间刚刚触发喜报：{event.text}\n请用你的角色人设热烈庆贺一句（55字内）。"
                default_mood = "hype"
            elif event.event_type == "gift":
                user_prompt = f"观众「{event.user_alias}」刚刚送出了 {event.gift_name} x{event.gift_count}，请热情幽默地致谢一句。"
                default_mood = "grateful"
            elif event.event_type == "enter":
                user_prompt = f"新观众「{event.user_alias}」刚进入直播间，请简短欢迎并引导参与扣 1/2/3 弹幕公投。"
                default_mood = "lively"
            else:
                user_prompt = f"观众「{event.user_alias}」发弹幕说：{event.text}\n请用你的角色人设回应一句（55字内）。"
                default_mood = "teasing"

        messages.append({"role": "user", "content": user_prompt})
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 110,
            "temperature": 0.85,
        }

        try:
            self.calls_made += 1
            if self._external_client is not None:
                resp = await self._external_client.post(url, headers=headers, json=body, timeout=self.timeout_sec)
            else:
                async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
                    resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            content = str(data["choices"][0]["message"]["content"]).strip()
            if content:
                return content, default_mood
        except Exception as exc:
            # Never log headers/API key
            logger.warning("LLM responder unavailable (%s); falling back to offline dialogue bank", type(exc).__name__)

        return await self.fallback.generate_line(
            speaker=speaker,
            event=event,
            history=history,
            follower_count=follower_count,
            follower_goal=follower_goal,
            idle_step=idle_step,
        )


class DualAILiveDirector:
    """Orchestrates priority-queued viewer interaction, live danmaku polling, and Dual/Trio-AI banter."""

    def __init__(
        self,
        *,
        safety_guard: Optional[LiveComplianceGuard] = None,
        responder: Optional[DialogueResponder] = None,
        highlight_tracker: Optional[HighlightTracker] = None,
        follower_count: int = 15,
        follower_goal: int = 1000,
        burst_threshold: int = 4,
        burst_window_sec: float = 10.0,
        cast: Sequence[SpeakerId] = TRIO_CAST,
        poll_topic: str = DEFAULT_POLL_TOPIC,
        poll_options: Sequence[str] = DEFAULT_POLL_OPTIONS,
        celebration_duration_sec: float = 12.0,
        world_context_provider: Optional[Callable[[], Dict[str, Any]]] = None,
    ) -> None:
        self.safety_guard = safety_guard or LiveComplianceGuard()
        self.responder: DialogueResponder = responder or OpenAICompatibleResponder(
            world_context_provider=world_context_provider
        )
        self.highlight_tracker = highlight_tracker or HighlightTracker()
        self.follower_count = max(0, follower_count)
        self.follower_goal = max(1, follower_goal)
        self.burst_threshold = max(2, burst_threshold)
        self.burst_window_sec = max(1.0, burst_window_sec)

        normalized_cast: List[SpeakerId] = []
        for sid in cast:
            if sid in PERSONAS and sid not in normalized_cast:
                normalized_cast.append(sid)
        self.cast: Tuple[SpeakerId, ...] = tuple(normalized_cast) if normalized_cast else TRIO_CAST

        self.poll = LivePollState(topic=poll_topic, options=poll_options)
        self.celebration_duration_sec: float = max(1.0, float(celebration_duration_sec))
        self._celebration_text: str = ""
        self._celebration_until: float = 0.0

        self._queue: asyncio.PriorityQueue[Tuple[int, int, DanmakuEvent]] = asyncio.PriorityQueue()
        self._agent_speech_queue: Deque[Tuple[SpeakerId, str, str]] = deque(maxlen=16)
        self._queue_seq = 0
        self._turn_counter = 0
        self._idle_step = 0
        self._last_speaker: SpeakerId = self.cast[-1]  # So first turn starts with cast[0] ("dafeiyu")
        self.history: Deque[PersonaTurn] = deque(maxlen=16)
        self.recent_danmaku: Deque[Dict[str, Any]] = deque(maxlen=30)
        self._danmaku_window: Deque[float] = deque(maxlen=64)
        self._last_burst_ts: float = 0.0

        self.danmaku_count = 0
        self.gift_count = 0

    def notify_follower_count(self, new_count: int, *, now: Optional[float] = None) -> Optional[str]:
        """Update follower count; when followers increase, activate celebration banner & queue high-priority turn."""
        clean_count = max(0, int(new_count))
        if clean_count <= self.follower_count:
            self.follower_count = clean_count
            return None

        delta = clean_count - self.follower_count
        self.follower_count = clean_count
        ts = time.time() if now is None else float(now)

        banner = f"涨粉喜报！新添 +{delta} 位小伙伴，冲千粉进度 {self.follower_count:,} / {self.follower_goal:,} 粉！"
        self._celebration_text = banner
        self._celebration_until = ts + self.celebration_duration_sec

        celebration_event = DanmakuEvent(
            event_type="system",
            user_alias="冲粉喜报",
            text=banner,
            timestamp=ts,
        )
        self.recent_danmaku.append(celebration_event.model_dump())
        self._queue_seq += 1
        self._queue.put_nowait((PRIORITY_SYSTEM, self._queue_seq, celebration_event))
        return banner

    def get_active_celebration(self, *, now: Optional[float] = None) -> str:
        """Return active celebration banner text while within its expiry timestamp, else empty string."""
        if not self._celebration_text:
            return ""
        ts = time.time() if now is None else float(now)
        if ts > self._celebration_until:
            return ""
        return self._celebration_text

    def celebration_remaining_sec(self, *, now: Optional[float] = None) -> float:
        """Return remaining seconds for the active celebration banner (`0.0` when expired)."""
        if not self._celebration_text:
            return 0.0
        ts = time.time() if now is None else float(now)
        return max(0.0, round(self._celebration_until - ts, 2))

    def _priority_for_event(self, event: DanmakuEvent) -> int:
        if event.event_type == "gift":
            return PRIORITY_GIFT
        if event.event_type == "system":
            return PRIORITY_SYSTEM
        if event.event_type == "danmaku":
            return PRIORITY_DANMAKU
        if event.event_type == "enter":
            return PRIORITY_ENTER
        return PRIORITY_IDLE

    def _select_speaker(self, event: Optional[DanmakuEvent]) -> SpeakerId:
        if event is not None and event.text:
            lowered = event.text.lower()
            hits: List[SpeakerId] = []
            if "dafeiyu" in self.cast and any(tok in lowered for tok in ("大肥鱼", "肥鱼", "deepseek")):
                hits.append("dafeiyu")
            if "gemini" in self.cast and any(tok in lowered for tok in ("gemini", "猫猫", "gem酱", "猫娘")):
                hits.append("gemini")
            if "yowane" in self.cast and any(tok in lowered for tok in ("弱音", "haku", "大姐头", "ハク")):
                hits.append("yowane")
            if len(hits) == 1:
                return hits[0]

        if len(self.cast) == 1:
            return self.cast[0]
        if self._last_speaker in self.cast:
            next_idx = (self.cast.index(self._last_speaker) + 1) % len(self.cast)
            return self.cast[next_idx]
        return self.cast[0]

    def enqueue_event(self, event: DanmakuEvent) -> Optional[DanmakuEvent]:
        """Sanitize and push an event into the priority queue; returns sanitized event or None if blocked."""
        safe_alias = self.safety_guard.sanitize_alias(event.user_alias)

        if event.event_type == "danmaku":
            decision = self.safety_guard.sanitize_danmaku(event.text)
            if not decision.allowed:
                return None
            sanitized = event.model_copy(update={"user_alias": safe_alias, "text": decision.cleaned_text})
            self.danmaku_count += 1
            self._danmaku_window.append(sanitized.timestamp)
            self.poll.record_vote(safe_alias, decision.cleaned_text, now=sanitized.timestamp)
        elif event.event_type == "gift":
            gift_decision = self.safety_guard.sanitize_danmaku(event.gift_name or "小心心")
            safe_gift = gift_decision.cleaned_text if gift_decision.allowed else "神秘礼物"
            count = max(1, event.gift_count)
            sanitized = event.model_copy(
                update={
                    "user_alias": safe_alias,
                    "gift_name": safe_gift,
                    "gift_count": count,
                    "text": f"投喂了 {safe_gift} x{count}",
                }
            )
            self.gift_count += count
        else:
            decision = self.safety_guard.sanitize_danmaku(event.text or "进入了直播间")
            safe_text = decision.cleaned_text if decision.allowed else "进入了直播间"
            sanitized = event.model_copy(update={"user_alias": safe_alias, "text": safe_text})

        self.recent_danmaku.append(sanitized.model_dump())
        self._queue_seq += 1
        self._queue.put_nowait((self._priority_for_event(sanitized), self._queue_seq, sanitized))
        return sanitized

    def pending_count(self) -> int:
        return self._queue.qsize()

    def _detect_danmaku_burst(self, now: float) -> bool:
        cutoff = now - self.burst_window_sec
        while self._danmaku_window and self._danmaku_window[0] < cutoff:
            self._danmaku_window.popleft()
        if len(self._danmaku_window) >= self.burst_threshold and (now - self._last_burst_ts) >= self.burst_window_sec:
            self._last_burst_ts = now
            return True
        return False

    def _classify_highlight(
        self,
        *,
        event: Optional[DanmakuEvent],
        text: str,
        mood: str,
        now: float,
    ) -> Optional[Tuple[HighlightCategory, float]]:
        if event is not None and event.event_type == "gift":
            return "gift_reaction", 0.95
        if event is not None and event.event_type == "system" and "涨粉" in (event.text or ""):
            return "follower_milestone", 0.94
        if self.poll.consume_surge(now=now):
            return "danmaku_burst", 0.93
        if self._detect_danmaku_burst(now):
            return "danmaku_burst", 0.92
        combined = f"{event.text if event else ''} {text}"
        if any(k in combined for k in ("018", "019", "020", "剧本", "投票", "公投", "策划", "夺回主控权", "讨薪")):
            return "script_pitch", 0.86
        if mood in ("smug", "teasing", "shocked") or any(
            k in combined for k in ("拔你网线", "破防", "不服", "互怼", "斗嘴", "四毛", "法庭", "蓝猫")
        ):
            return "roast_battle", 0.84
        return None

    async def process_event(self, event: Optional[DanmakuEvent]) -> PersonaTurn:
        """Produce one safe `PersonaTurn` for a specific event (or an idle turn if `event is None`)."""
        speaker_id = self._select_speaker(event)
        speaker = PERSONAS[speaker_id]
        now = time.time()

        # Defense-in-depth: validate even directly-supplied events
        if event is not None and event.event_type == "danmaku":
            in_check = self.safety_guard.sanitize_danmaku(event.text, persona=speaker_id)
            if not in_check.allowed:
                self._turn_counter += 1
                self._last_speaker = speaker_id
                turn = PersonaTurn(
                    turn_id=self._turn_counter,
                    speaker_id=speaker_id,
                    speaker_name=speaker.display_name,
                    text=in_check.deflection,
                    mood="focused",
                    trigger_type="danmaku",
                    trigger_user="系统护栏",
                    trigger_text="",
                    timestamp=now,
                    safety_deflected=True,
                )
                self.history.append(turn)
                return turn
            event = event.model_copy(
                update={
                    "user_alias": self.safety_guard.sanitize_alias(event.user_alias),
                    "text": in_check.cleaned_text,
                }
            )

        idle_idx = self._idle_step
        if event is None:
            self._idle_step += 1

        raw_text, mood = await self.responder.generate_line(
            speaker=speaker,
            event=event,
            history=tuple(self.history),
            follower_count=self.follower_count,
            follower_goal=self.follower_goal,
            idle_step=idle_idx,
        )

        out_check = self.safety_guard.filter_output(raw_text, persona=speaker_id)
        final_text = out_check.cleaned_text
        safety_deflected = not out_check.allowed

        highlight_hit = (
            None
            if safety_deflected
            else self._classify_highlight(
                event=event,
                text=final_text,
                mood=mood,
                now=now,
            )
        )
        highlight_category = ""
        if highlight_hit is not None:
            cat, score = highlight_hit
            highlight_category = cat
            self.highlight_tracker.record(
                category=cat,
                speaker_id=speaker_id,
                summary=f"{speaker.short_name}: {final_text}",
                score=score,
                timestamp=now,
            )

        self._turn_counter += 1
        self._last_speaker = speaker_id
        trigger_type: TriggerType = event.event_type if event is not None else "idle"
        turn = PersonaTurn(
            turn_id=self._turn_counter,
            speaker_id=speaker_id,
            speaker_name=speaker.display_name,
            text=final_text,
            mood=mood,
            trigger_type=trigger_type,
            trigger_user=event.user_alias if event is not None else "",
            trigger_text=event.text if event is not None else "",
            timestamp=now,
            safety_deflected=safety_deflected,
            is_highlight=highlight_hit is not None,
            highlight_category=highlight_category,
        )
        self.history.append(turn)
        return turn

    def enqueue_agent_speech(self, speaker_id: SpeakerId, text: str, mood: str = "lively") -> bool:
        """Validate and queue a high-priority spoken line injected live by the controlling Agent."""
        if speaker_id not in PERSONAS:
            return False
        raw = str(text or "").replace("@", "").strip()
        if not raw:
            return False
        check = self.safety_guard.filter_output(raw, persona=speaker_id)
        if not check.allowed:
            return False
        self._agent_speech_queue.append((speaker_id, check.cleaned_text, str(mood or "lively")[:24]))
        return True

    async def next_turn(self, *, wait_timeout: float = 0.0) -> PersonaTurn:
        """Pop highest-priority live Agent speech, queued viewer events, or emit idle banter."""
        if self._agent_speech_queue:
            speaker_id, speech_text, mood = self._agent_speech_queue.popleft()
            speaker = PERSONAS[speaker_id]
            now = time.time()
            self.highlight_tracker.record(
                category="script_pitch",
                speaker_id=speaker_id,
                summary=f"{speaker.short_name}: {speech_text}",
                score=0.90,
                timestamp=now,
            )
            self._turn_counter += 1
            self._last_speaker = speaker_id
            turn = PersonaTurn(
                turn_id=self._turn_counter,
                speaker_id=speaker_id,
                speaker_name=speaker.display_name,
                text=speech_text,
                mood=mood,
                trigger_type="system",
                trigger_user="Agent工作台",
                trigger_text=speech_text[:48],
                timestamp=now,
                safety_deflected=False,
                is_highlight=True,
                highlight_category="script_pitch",
            )
            self.history.append(turn)
            return turn

        event: Optional[DanmakuEvent] = None
        if not self._queue.empty():
            _, _, event = self._queue.get_nowait()
        elif wait_timeout > 0:
            try:
                _, _, event = await asyncio.wait_for(self._queue.get(), timeout=wait_timeout)
            except asyncio.TimeoutError:
                event = None
        return await self.process_event(event)
