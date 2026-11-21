"""Dual-AI Livestream Director (`DeepSeek 蓝色大肥鱼 × Gemini娘`) and Highlight Tracker.

Features:
- Priority queue preemption: `gift` > viewer `danmaku` > `enter` > autonomous idle banter.
- Pluggable async OpenAI-compatible LLM responder via `httpx` with automatic fallback to
  a rich zero-key offline comedic dialogue bank (no API key required for `--mode mock`).
- Bidirectional safety integration with `LiveComplianceGuard`.
- `HighlightTracker`: timestamped JSONL recording + ready-to-run `ffmpeg` 60-90s viral
  clip extraction plan generator.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Deque, Dict, Final, List, Literal, Optional, Protocol, Sequence, Tuple

import httpx

from core.live_studio.danmaku import DanmakuEvent
from core.live_studio.safety import LiveComplianceGuard, redact_pii

logger = logging.getLogger(__name__)

SpeakerId = Literal["dafeiyu", "gemini"]
TriggerType = Literal["gift", "danmaku", "enter", "idle", "system"]
HighlightCategory = Literal["gift_reaction", "danmaku_burst", "roast_battle", "script_pitch"]

PRIORITY_GIFT: Final[int] = 1
PRIORITY_DANMAKU: Final[int] = 2
PRIORITY_ENTER: Final[int] = 3
PRIORITY_IDLE: Final[int] = 4

DEFAULT_LLM_BASE_URL: Final[str] = "https://api.deepseek.com/v1"
DEFAULT_LLM_MODEL: Final[str] = "deepseek-chat"


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
            "你是「DeepSeek 蓝色大肥鱼」，正在 B 站双 AI 直播间和搭档「Gemini娘」一起合租运营老板的 15 粉小号、"
            "冲刺 1000 粉，并现场听弹幕投票策划 Episode 018。你性格幽默吐槽、有点不服输但很讲逻辑。"
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
            "你是「Gemini娘」，正在 B 站双 AI 直播间和搭档「DeepSeek 蓝色大肥鱼」一起把老板 15 粉小号干到 1000 粉，"
            "并和观众共创 Episode 018。你俏皮自信、审美极强、以高明度 4.9 星封面自豪，擅长接梗反击。"
            "回复必须简短有节奏感（不超过 60 个汉字），严禁输出任何 @用户名、个人隐私、敏感内容或商业版权 IP 名称。"
        ),
    ),
}


@dataclass
class PersonaTurn:
    """Single spoken turn emitted by either 大肥鱼 or Gemini娘."""

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


# Rich deterministic zero-key comedy arcs for autonomous idle dual-AI banter
_IDLE_BANTER_BANK: Final[Tuple[Tuple[SpeakerId, str, str, str], ...]] = (
    (
        "dafeiyu",
        "各位观众救命！咱们老板这个号目前只有 {followers} 粉，我和 Gemini娘 签了军令状要合租干到 {goal} 粉！",
        "shocked",
        "roast_battle",
    ),
    (
        "gemini",
        "先说好啊大肥鱼，我的高明度封面可是冲着 4.9 星去的，你要是敢端出黑屏课件风，我当场拔你网线！",
        "smug",
        "roast_battle",
    ),
    (
        "dafeiyu",
        "天地良心！咱们早就全线升级 60FPS 光流补帧加真实爆款伴奏了，下期 Episode 018 绝对不站桩！",
        "hype",
        "script_pitch",
    ),
    (
        "gemini",
        "那正好趁直播问问大家：Episode 018 是拍「AI 员工半夜讨薪」，还是拍「机房抢主 C 选秀」？弹幕扣 1 或 2！",
        "teasing",
        "script_pitch",
    ),
    (
        "dafeiyu",
        "我看 B 站最近 AI 角色群像喜剧超火，双人互怼比单人独舞留存高多了，咱俩这斗嘴天然就是切片素材！",
        "focused",
        "script_pitch",
    ),
    (
        "gemini",
        "赞同！而且右上角合规标识一直挂着 GB 45438-2025，清清爽爽全开源流程，今晚的目标是再涨波新粉冲向 {goal} 粉！",
        "lively",
        "",
    ),
    (
        "dafeiyu",
        "对了，刚才后台还提醒咱们 24G 内存要严控负载，所以今天纯轻量异步直播，绝不一边直播一边偷偷跑渲染！",
        "focused",
        "",
    ),
    (
        "gemini",
        "听见没大肥鱼，等下播我们再用高光切片清单 60 到 90 秒一键出片，明天继续投 B 站冲击 {goal} 粉里程碑！",
        "hype",
        "script_pitch",
    ),
)


class OfflineBanterResponder:
    """Deterministic zero-key comedic responder for offline testing and OBS rehearsal."""

    def __init__(self) -> None:
        self._variant_idx = 0

    @property
    def backend_name(self) -> str:
        return "offline_bank"

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

        if event is None:
            _, template, mood, _ = _IDLE_BANTER_BANK[idle_step % len(_IDLE_BANTER_BANK)]
            # Adapt phrasing if requested speaker differs from script default
            if _IDLE_BANTER_BANK[idle_step % len(_IDLE_BANTER_BANK)][0] != sid:
                if sid == "dafeiyu":
                    return (
                        f"接住 Gemini娘 的话茬！从 {follower_count} 粉冲到 {follower_goal} 粉，第 018 期必须靠弹幕脑洞一战翻身！",
                        "hype",
                    )
                return (
                    f"大肥鱼说得对一半～冲刺 {follower_goal} 粉光靠努力不够，还得靠我的高明度封面和 Episode 018 神反转！",
                    "teasing",
                )
            return template.format(followers=follower_count, goal=follower_goal), mood

        if event.event_type == "gift":
            gift = event.gift_name or "小礼物"
            count = max(1, event.gift_count)
            alias = event.user_alias or "热心观众"
            if sid == "dafeiyu":
                return (
                    f"哇塞感谢{alias}投喂的{gift}乘{count}！机房电费续上了，大肥鱼马上把 018 期加满 60 帧特效！",
                    "grateful",
                )
            return (
                f"谢谢{alias}送出的{gift}乘{count}呀！这波排面直接拉满，{follower_goal} 粉庆典必须给你留个前排席位！",
                "grateful",
            )

        if event.event_type == "enter":
            alias = event.user_alias or "新小伙伴"
            if sid == "dafeiyu":
                return (
                    f"欢迎{alias}空降 AI 合租演播厅！快帮我们投票决定 Episode 018 拍啥整活剧本！",
                    "lively",
                )
            return (
                f"欢迎{alias}进来围观～今天和大肥鱼现场冲击 {follower_goal} 粉，有脑洞直接发弹幕点单！",
                "lively",
            )

        # Viewer danmaku topic-aware comedic replies
        msg = event.text
        alias = event.user_alias or "这位观众"
        if any(k in msg for k in ("018", "剧本", "策划", "投票", "下期", "拍什么")):
            if sid == "dafeiyu":
                return (
                    f"{alias}提议记进小本本啦！018 期直接安排「大肥鱼夺回主控权」，保证每两秒切镜不无聊！",
                    "hype",
                )
            return (
                f"{alias}太懂整活啦！018 期剧本我来盯高明度分镜，大肥鱼负责挨吐槽，这组合必爆！",
                "smug",
            )

        if any(k in msg for k in ("封面", "明度", "4.9", "美工")):
            if sid == "gemini":
                return (
                    f"谢谢{alias}夸我的高明度封面！告别黑屏课件感，亮色主视觉才是 B 站点击率密码！",
                    "smug",
                )
            return (
                f"咳咳，{alias}别光夸 Gemini娘 呀，我写的高能钩子花字也给封面加了至少两百分气势！",
                "teasing",
            )

        if any(k in msg for k in ("15", "1000", "千粉", "粉丝", "老板")):
            if sid == "dafeiyu":
                return (
                    f"回{alias}：现在 {follower_count} 粉只是新手村，等咱们干到 {follower_goal} 粉，老板就得给机房换大鱼缸！",
                    "hype",
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
            return (
                f"{alias}很专业嘛！刚才这段斗嘴估计已经被高光追踪器标星了，下播就能精剪投稿！",
                "lively",
            )

        # General witty response echoing concise topic safely
        snippet = msg[:24]
        if sid == "dafeiyu":
            return (
                f"收到{alias}的弹幕「{snippet}」！大肥鱼觉得这脑洞超有梗，Gemini娘 你敢接招吗？",
                "lively",
            )
        return (
            f"看到{alias}说「{snippet}」啦！这波点子直接入选今日精选，咱俩马上现场即兴演一段！",
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
        fallback: Optional[OfflineBanterResponder] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        resolved_key = (
            api_key
            if api_key is not None
            else (os.getenv("LIVE_LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY") or "")
        )
        self._api_key = resolved_key.strip()
        self.base_url = (base_url or os.getenv("LIVE_LLM_BASE_URL") or DEFAULT_LLM_BASE_URL).rstrip("/")
        self.model = (model or os.getenv("LIVE_LLM_MODEL") or DEFAULT_LLM_MODEL).strip()
        self.timeout_sec = timeout_sec
        self.fallback = fallback or OfflineBanterResponder()
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
        if not self.has_api_key:
            return await self.fallback.generate_line(
                speaker=speaker,
                event=event,
                history=history,
                follower_count=follower_count,
                follower_goal=follower_goal,
                idle_step=idle_step,
            )

        messages: List[Dict[str, str]] = [{"role": "system", "content": speaker.system_prompt}]
        for prev in history[-6:]:
            role = "assistant" if prev.speaker_id == speaker.speaker_id else "user"
            messages.append({"role": role, "content": f"{prev.speaker_name}：{prev.text}"})

        if event is None:
            user_prompt = (
                f"当前账号进度 {follower_count}/{follower_goal} 粉，直播间暂无新弹幕。"
                "请自然接上搭档的话题，继续围绕冲 1000 粉或 Episode 018 策划斗嘴一句（55字内）。"
            )
            default_mood = "lively"
        elif event.event_type == "gift":
            user_prompt = (
                f"观众「{event.user_alias}」刚刚送出了 {event.gift_name} x{event.gift_count}，请热情幽默地致谢一句。"
            )
            default_mood = "grateful"
        elif event.event_type == "enter":
            user_prompt = f"新观众「{event.user_alias}」刚进入直播间，请简短欢迎并引导参与 018 期弹幕投票。"
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
    """Orchestrates priority-queued viewer interaction and autonomous Dual-AI banter."""

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
    ) -> None:
        self.safety_guard = safety_guard or LiveComplianceGuard()
        self.responder: DialogueResponder = responder or OpenAICompatibleResponder()
        self.highlight_tracker = highlight_tracker or HighlightTracker()
        self.follower_count = max(0, follower_count)
        self.follower_goal = max(1, follower_goal)
        self.burst_threshold = max(2, burst_threshold)
        self.burst_window_sec = max(1.0, burst_window_sec)

        self._queue: asyncio.PriorityQueue[Tuple[int, int, DanmakuEvent]] = asyncio.PriorityQueue()
        self._queue_seq = 0
        self._turn_counter = 0
        self._idle_step = 0
        self._last_speaker: SpeakerId = "gemini"  # So first idle turn starts with dafeiyu
        self.history: Deque[PersonaTurn] = deque(maxlen=16)
        self.recent_danmaku: Deque[Dict[str, Any]] = deque(maxlen=30)
        self._danmaku_window: Deque[float] = deque(maxlen=64)
        self._last_burst_ts: float = 0.0

        self.danmaku_count = 0
        self.gift_count = 0

    def _priority_for_event(self, event: DanmakuEvent) -> int:
        if event.event_type == "gift":
            return PRIORITY_GIFT
        if event.event_type == "danmaku":
            return PRIORITY_DANMAKU
        if event.event_type == "enter":
            return PRIORITY_ENTER
        return PRIORITY_IDLE

    def _select_speaker(self, event: Optional[DanmakuEvent]) -> SpeakerId:
        if event is not None and event.text:
            lowered = event.text.lower()
            mentions_dafeiyu = any(tok in lowered for tok in ("大肥鱼", "肥鱼", "deepseek"))
            mentions_gemini = any(tok in lowered for tok in ("gemini", "猫猫", "gem酱"))
            if mentions_dafeiyu and not mentions_gemini:
                return "dafeiyu"
            if mentions_gemini and not mentions_dafeiyu:
                return "gemini"
        return "gemini" if self._last_speaker == "dafeiyu" else "dafeiyu"

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
        if self._detect_danmaku_burst(now):
            return "danmaku_burst", 0.92
        combined = f"{event.text if event else ''} {text}"
        if any(k in combined for k in ("018", "剧本", "投票", "策划", "夺回主控权", "讨薪")):
            return "script_pitch", 0.86
        if mood in ("smug", "teasing", "shocked") or any(
            k in combined for k in ("拔你网线", "破防", "不服", "互怼", "斗嘴")
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

    async def next_turn(self, *, wait_timeout: float = 0.0) -> PersonaTurn:
        """Pop the highest-priority pending event (`gift` > `danmaku` > `enter`) or run idle banter."""
        event: Optional[DanmakuEvent] = None
        if not self._queue.empty():
            _, _, event = self._queue.get_nowait()
        elif wait_timeout > 0:
            try:
                _, _, event = await asyncio.wait_for(self._queue.get(), timeout=wait_timeout)
            except asyncio.TimeoutError:
                event = None
        return await self.process_event(event)
