"""Bilibili Dark-Horse Breakout Radar & Channel Horse-Race Evaluator for ContentFlow.

Provides two core capabilities with a strict Zero-PII guarantee:
  1. `BreakoutRadarEngine.scan_dark_horses`: Discovers small/mid-tier Bilibili creators
     (<= max_followers) whose videos achieve breakout views & strong-intent engagement
     (coin/favorite/share/danmaku), analyzes their mobile 20-char title hooks, and
     synthesizes repeatable pattern insights.
  2. `BreakoutRadarEngine.evaluate_channel_horse_race`: Evaluates our own channel's
     multi-track horse-race (trio_sitcom, ai_experiment, scifi_microfilm, oss_tool_demo)
     using the redacted analytics snapshot and `library/creative_ledger.json`, enforcing
     decision readiness before consolidating onto a single winning track.

Zero-PII Contract:
  Output JSON, Markdown, and logs NEVER contain raw `uid`, `mid`, `vmid`, `uname`,
  `author`, cookies, or `@username` handles. Creators are represented strictly as
  anonymized follower tiers (`<1k`, `1k-5k`, `5k-20k`, `20k-50k`, `50k+`) with numeric
  `follower_count`.
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import math
import re
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

import requests

from config.settings import CONTENTFLOW_ROOT
from core.auth_vault import STANDARD_USER_AGENT, AuthVault
from core.bgm_hunter import MIXIN_KEY_ENC_TAB

logger = logging.getLogger(__name__)

BILIBILI_NAV_URL = "https://api.bilibili.com/x/web-interface/nav"
BILIBILI_WBI_SEARCH_URL = "https://api.bilibili.com/x/web-interface/wbi/search/type"
BILIBILI_VIEW_URL = "https://api.bilibili.com/x/web-interface/view"
BILIBILI_RELATION_STAT_URL = "https://api.bilibili.com/x/relation/stat"

DEFAULT_RADAR_QUERIES: Tuple[str, ...] = (
    "AI博弈实验",
    "AI开源工具",
    "DeepSeek大肥鱼",
    "AI科幻短片",
)
DEFAULT_ANALYTICS_SNAPSHOT = Path("/home/mcocdaa/.contentflow/accounts/analytics/bilibili_latest.json")

HORSE_RACE_CORE_TRACKS: Tuple[str, ...] = (
    "trio_sitcom",
    "ai_experiment",
    "scifi_microfilm",
    "oss_tool_demo",
)

ALL_HORSE_RACE_TRACKS: Tuple[str, ...] = (
    "trio_sitcom",
    "ai_experiment",
    "scifi_microfilm",
    "oss_tool_demo",
    "short_dance_meme",
    "legacy_whiteboard",
)

TRACK_DISPLAY_LABELS: Dict[str, str] = {
    "trio_sitcom": "铁三角AI合租情景剧 (trio_sitcom)",
    "ai_experiment": "真实多AI博弈实验 (ai_experiment)",
    "scifi_microfilm": "高概念AI科幻微电影 (scifi_microfilm)",
    "oss_tool_demo": "开源AI工具实机演示 (oss_tool_demo)",
    "short_dance_meme": "早期热梗短舞/双人整活 (short_dance_meme)",
    "legacy_whiteboard": "旧静态白板硬核科普 (legacy_whiteboard)",
}

_TRACK_BUCKET_RULES: Tuple[Tuple[str, Tuple[str, ...], Tuple[str, ...]], ...] = (
    (
        "ai_experiment",
        ("博弈", "实验", "密室", "囚徒", "淘汰赛", "狼人杀", "社会实验", "背刺", "模拟实验", "多智能体"),
        ("实测", "对抗", "评测", "测试", "agent", "分1000万", "关进", "演进"),
    ),
    (
        "ai_tool_demo",
        ("开源", "工具", "监工", "写了个", "做了个", "自制", "插件", "github", "源码", "工作流", "防摸鱼"),
        ("脚本", "部署", "效率", "自动化", "软件", "代码", "cli", "demo", "教程", "神器", "编程"),
    ),
    (
        "ai_scifi_story",
        ("科幻", "微电影", "悬疑短片", "科幻短片", "失踪", "末日", "废土", "赛博朋克"),
        ("悬疑", "短片", "电影", "消失", "智械危机", "接管", "未来", "宇宙", "记忆", "替代"),
    ),
    (
        "ai_persona_comedy",
        ("大肥鱼", "猫娘", "弱音", "龙娘", "豆姐", "合租", "法庭", "抢麦", "情景剧", "热舞", "宅舞", "鬼畜"),
        ("deepseek", "gemini", "整活", "搞笑", "吐槽", "吵架", "吵翻", "抽象", "打歌", "面试", "喜剧"),
    ),
)

_MENTION_RE = re.compile(r"@[\w\-\.\u4e00-\u9fff]+")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_BRACKET_PREFIX_RE = re.compile(r"^【")
_CONTEST_SUFFIX_RE = re.compile(r"公开赛|创作营|征稿")
_DIALOGUE_QUOTE_RE = re.compile(r'[“”「」"]')
_NUMBER_CONTRAST_RE = re.compile(r"\d+")
_QUESTION_SUSPENSE_RE = re.compile(r"？|\?|竟|居然|竟然|真能|还是")
_PREMISE_HOOK_RE = re.compile(r"我写了个|我做了|我把|把\d*个|假如|如果")


def _sanitize_text(text: str, extra_sensitive: Optional[Set[str]] = None) -> str:
    """Strips HTML tags, @mentions, and optional sensitive tokens while collapsing whitespace."""
    cleaned = html.unescape(str(text or ""))
    cleaned = _HTML_TAG_RE.sub("", cleaned)
    cleaned = _MENTION_RE.sub("", cleaned)
    if extra_sensitive:
        for tok in extra_sensitive:
            if tok and tok != "<REDACTED>":
                cleaned = cleaned.replace(tok, "<REDACTED>")
    return re.sub(r"\s+", " ", cleaned).strip()


def analyze_title_structure(title: str) -> Dict[str, Any]:
    """Analyzes a Bilibili video title for mobile 20-char hook strength and track bucket."""
    clean_title = _sanitize_text(title)
    first_20_chars = clean_title[:20]
    title_len = len(clean_title)

    has_bracket_prefix = bool(_BRACKET_PREFIX_RE.match(clean_title))
    has_contest_suffix = bool(_CONTEST_SUFFIX_RE.search(clean_title))
    has_dialogue_quote = bool(_DIALOGUE_QUOTE_RE.search(clean_title))
    has_number_contrast = bool(_NUMBER_CONTRAST_RE.search(clean_title))
    has_question_suspense = bool(_QUESTION_SUSPENSE_RE.search(clean_title))

    lower_title = clean_title.lower()
    best_bucket = "other"
    best_score = 0
    for bucket_name, strong_kws, weak_kws in _TRACK_BUCKET_RULES:
        score = 0
        for kw in strong_kws:
            if kw in lower_title:
                score += 3
        for kw in weak_kws:
            if kw in lower_title:
                score += 1
        if score > best_score:
            best_score = score
            best_bucket = bucket_name

    hook_signals: List[str] = []
    if has_dialogue_quote:
        hook_signals.append("dialogue_quote")
    if has_number_contrast:
        hook_signals.append("number_contrast")
    if has_question_suspense:
        hook_signals.append("question_suspense")
    if _PREMISE_HOOK_RE.search(clean_title):
        hook_signals.append("premise_hook")
    if not has_bracket_prefix and (
        _DIALOGUE_QUOTE_RE.search(first_20_chars)
        or _NUMBER_CONTRAST_RE.search(first_20_chars)
        or _QUESTION_SUSPENSE_RE.search(first_20_chars)
    ):
        hook_signals.append("front_loaded_20_hook")

    return {
        "clean_title": clean_title,
        "first_20_chars": first_20_chars,
        "title_len": title_len,
        "has_bracket_prefix": has_bracket_prefix,
        "has_contest_suffix": has_contest_suffix,
        "has_dialogue_quote": has_dialogue_quote,
        "has_number_contrast": has_number_contrast,
        "has_question_suspense": has_question_suspense,
        "track_bucket": best_bucket,
        "hook_signals": hook_signals,
    }


def classify_creator_tier(followers: Optional[int]) -> str:
    """Maps a numeric follower count into an anonymized creator scale tier."""
    if followers is None:
        return "unknown"
    count = max(0, int(followers))
    if count < 1000:
        return "<1k"
    if count < 5000:
        return "1k-5k"
    if count < 20000:
        return "5k-20k"
    if count <= 50000:
        return "20k-50k"
    return "50k+"


def score_breakout_candidate(
    view: int,
    like: int,
    coin: int,
    favorite: int,
    share: int,
    danmaku: int,
    reply: int,
    follower_count: Optional[int],
    pubdate: Optional[int] = None,
    title_analysis: Optional[Dict[str, Any]] = None,
    now_ts: Optional[float] = None,
) -> Dict[str, Any]:
    """Computes dark-horse leverage, strong-intent engagement rates, and 0..100 breakout_score."""
    views_i = max(0, int(view or 0))
    likes_i = max(0, int(like or 0))
    coins_i = max(0, int(coin or 0))
    favs_i = max(0, int(favorite or 0))
    shares_i = max(0, int(share or 0))
    danmaku_i = max(0, int(danmaku or 0))
    replies_i = max(0, int(reply or 0))

    if follower_count is not None:
        followers_val = max(0, int(follower_count))
        followers_clean: Optional[int] = followers_val
        views_per_follower = round(views_i / float(max(followers_val, 100)), 2)
    else:
        followers_clean = None
        views_per_follower = 0.0

    if views_i > 0:
        denom = float(views_i)
        like_rate = round(likes_i / denom, 4)
        coin_rate = round(coins_i / denom, 4)
        fav_rate = round(favs_i / denom, 4)
        share_rate = round(shares_i / denom, 4)
        danmaku_rate = round(danmaku_i / denom, 4)
        reply_rate = round(replies_i / denom, 4)
    else:
        like_rate = 0.0
        coin_rate = 0.0
        fav_rate = 0.0
        share_rate = 0.0
        danmaku_rate = 0.0
        reply_rate = 0.0

    age_days: Optional[float] = None
    if pubdate is not None and int(pubdate) > 0:
        eff_now = float(now_ts) if now_ts is not None else time.time()
        age_days = round(max(0.0, (eff_now - float(pubdate)) / 86400.0), 2)

    # 1. Small-account leverage (0..45 pts)
    leverage_pts = min(45.0, math.log1p(max(0.0, views_per_follower)) * 6.0)

    # 2. Strong-intent engagement (0..40 pts)
    weighted_intent = coin_rate * 3.0 + fav_rate * 2.5 + share_rate * 4.0 + danmaku_rate * 2.0
    engagement_pts = min(40.0, weighted_intent * 120.0 + min(5.0, like_rate * 40.0))

    # 3. Recency boost (0..15 pts)
    recency_pts = 0.0
    if age_days is not None:
        if age_days <= 14.0:
            recency_pts = 15.0
        elif age_days <= 30.0:
            recency_pts = 9.0
        elif age_days <= 90.0:
            recency_pts = 4.0

    # 4. Title clutter penalty
    penalty_pts = 0.0
    if title_analysis:
        if title_analysis.get("has_contest_suffix"):
            penalty_pts += 6.0
        if title_analysis.get("has_bracket_prefix") and int(title_analysis.get("title_len") or 0) > 32:
            penalty_pts += 2.0

    breakout_score = round(max(0.0, min(100.0, leverage_pts + engagement_pts + recency_pts - penalty_pts)), 2)

    return {
        "creator_tier": classify_creator_tier(followers_clean),
        "follower_count": followers_clean,
        "views_per_follower": views_per_follower,
        "like_rate": like_rate,
        "coin_rate": coin_rate,
        "fav_rate": fav_rate,
        "share_rate": share_rate,
        "danmaku_rate": danmaku_rate,
        "reply_rate": reply_rate,
        "weighted_intent_rate": round(weighted_intent, 4),
        "age_days": age_days,
        "breakout_score": breakout_score,
    }


def _extract_ep_number(project_id: str) -> Optional[int]:
    prefix = str(project_id or "").strip().split("_", 1)[0]
    if prefix.isdigit():
        return int(prefix)
    return None


def _classify_horse_race_track(
    arc: Dict[str, Any],
    ledger_info: Optional[Dict[str, Any]] = None,
    manifest_info: Optional[Dict[str, Any]] = None,
) -> str:
    """Maps a channel archive into its strategic horse-race track."""
    explicit_track = str(arc.get("track") or "").strip().lower()
    if explicit_track in ALL_HORSE_RACE_TRACKS:
        return explicit_track

    proj_id = str(
        arc.get("project_id") or (ledger_info or {}).get("project_id") or (manifest_info or {}).get("project_id") or ""
    ).strip()
    archetype = str((ledger_info or {}).get("archetype") or "").strip().lower()
    meme_source = str((ledger_info or {}).get("meme_source") or "").strip()
    title = str(arc.get("title") or "").strip()

    ep_num = _extract_ep_number(proj_id)
    if ep_num is not None:
        if ep_num in (17, 18, 19, 20, 24):
            return "trio_sitcom"
        if ep_num == 21:
            return "ai_experiment"
        if ep_num == 22:
            return "scifi_microfilm"
        if ep_num == 23:
            return "oss_tool_demo"
        if 7 <= ep_num <= 16:
            return "short_dance_meme"
        if 1 <= ep_num <= 6:
            return "legacy_whiteboard"

    combined_low = f"{proj_id} {archetype} {meme_source} {title}".lower()

    if "dafeiyu_openai_dragon" in combined_low:
        return "short_dance_meme"
    if any(k in combined_low for k in ("game_theory", "博弈实验", "betrayal_experiment", "密室分1000万")):
        return "ai_experiment"
    if any(k in combined_low for k in ("scifi_film", "消失7天", "科幻悬疑", "科幻微电影", "科幻短片", "科幻")):
        return "scifi_microfilm"
    if any(k in combined_low for k in ("warden_tool", "毒舌ai监工", "防摸鱼", "ai整活工具", "开源")):
        return "oss_tool_demo"
    if any(
        k in combined_low
        for k in (
            "sitcom",
            "courtroom",
            "karaoke",
            "flatshare",
            "interview",
            "ai合租",
            "赛博法庭",
            "打歌棚",
            "便利店",
            "关东煮",
            "抢麦",
        )
    ):
        return "trio_sitcom"
    if any(
        k in combined_low
        for k in (
            "whiteboard",
            "hologram_lecture",
            "硬核科普",
            "3d手办",
            "3d能代",
            "全息",
            "ci/cd",
            "transformer",
            "api报错",
        )
    ):
        return "legacy_whiteboard"
    return "short_dance_meme"


class BreakoutRadarEngine:
    """Zero-PII Bilibili dark-horse breakout scanner and channel horse-race evaluator."""

    def __init__(
        self,
        root_dir: Optional[Union[str, Path]] = None,
        vault: Optional[AuthVault] = None,
        cookies: Optional[Dict[str, str]] = None,
        session: Optional[requests.Session] = None,
        request_delay_sec: float = 0.25,
    ) -> None:
        self.root_dir = Path(root_dir) if root_dir is not None else CONTENTFLOW_ROOT
        if cookies is not None:
            self.vault: Optional[AuthVault] = vault
            self.cookies: Dict[str, str] = dict(cookies)
        else:
            self.vault = vault or AuthVault()
            try:
                self.cookies = self.vault.load_bilibili_cookies()
            except Exception:
                self.cookies = {}
        self.session = session or requests.Session()
        self.request_delay_sec = max(0.0, float(request_delay_sec))
        self._mixin_key: Optional[str] = None

    @staticmethod
    def _headers(referer: str = "https://www.bilibili.com/") -> Dict[str, str]:
        return {
            "User-Agent": STANDARD_USER_AGENT,
            "Referer": referer,
            "Accept": "application/json, text/plain, */*",
        }

    def _pause(self) -> None:
        if self.request_delay_sec > 0.0:
            time.sleep(self.request_delay_sec)

    def _get_wbi_mixin_key(self) -> str:
        """Fetches and caches Bilibili WBI mixin key via /x/web-interface/nav."""
        if self._mixin_key:
            return self._mixin_key
        resp = self.session.get(
            BILIBILI_NAV_URL,
            cookies=self.cookies,
            headers=self._headers(),
            timeout=10,
        )
        resp.raise_for_status()
        payload = resp.json()
        wbi_img = ((payload.get("data") or {}).get("wbi_img")) or {}
        img_url = str(wbi_img.get("img_url") or "")
        sub_url = str(wbi_img.get("sub_url") or "")
        if not img_url or not sub_url:
            raise RuntimeError("Failed to fetch Bilibili WBI keys from /x/web-interface/nav")
        raw_wbi = Path(img_url).stem + Path(sub_url).stem
        self._mixin_key = "".join(raw_wbi[i] for i in MIXIN_KEY_ENC_TAB)[:32]
        return self._mixin_key

    def _wbi_search_videos(
        self,
        keyword: str,
        limit: int = 12,
        order: str = "click",
    ) -> List[Dict[str, Any]]:
        """Executes a WBI-signed Bilibili video search returning strictly non-PII summaries."""
        mixin_key = self._get_wbi_mixin_key()
        params: Dict[str, Any] = {
            "search_type": "video",
            "keyword": keyword,
            "order": order,
            "page": 1,
            "page_size": max(1, min(50, int(limit))),
            "wts": int(time.time()),
        }
        filtered = {k: "".join(c for c in str(v) if c not in "!'()*") for k, v in sorted(params.items())}
        query = urllib.parse.urlencode(filtered)
        w_rid = hashlib.md5((query + mixin_key).encode("utf-8")).hexdigest()
        url = f"{BILIBILI_WBI_SEARCH_URL}?{query}&w_rid={w_rid}"
        resp = self.session.get(
            url,
            cookies=self.cookies,
            headers=self._headers(),
            timeout=15,
        )
        resp.raise_for_status()
        body = resp.json()
        if int(body.get("code") or 0) != 0:
            raise RuntimeError(f"WBI search error code={body.get('code')}")
        raw_items = ((body.get("data") or {}).get("result")) or []
        results: List[Dict[str, Any]] = []
        for item in raw_items[:limit]:
            bvid = str(item.get("bvid") or "").strip()
            if not bvid:
                continue
            results.append(
                {
                    "bvid": bvid,
                    "title": _sanitize_text(str(item.get("title") or "")),
                    "play": int(item.get("play") or 0),
                }
            )
        return results

    def _fetch_view_detail(self, bvid: str) -> Optional[Dict[str, Any]]:
        """Fetches /x/web-interface/view for exact stats & internal vmid (never serialized)."""
        try:
            resp = self.session.get(
                BILIBILI_VIEW_URL,
                params={"bvid": bvid},
                cookies=self.cookies,
                headers=self._headers(f"https://www.bilibili.com/video/{bvid}/"),
                timeout=12,
            )
            if resp.status_code != 200:
                return None
            body = resp.json()
            if int(body.get("code") or 0) != 0:
                return None
            data = body.get("data") or {}
            if not isinstance(data, dict) or not data:
                return None
            stat = data.get("stat") or {}
            owner = data.get("owner") or {}
            raw_mid = owner.get("mid")
            internal_vmid: Optional[int] = None
            if raw_mid is not None:
                try:
                    internal_vmid = int(raw_mid)
                except (TypeError, ValueError):
                    internal_vmid = None
            return {
                "bvid": str(data.get("bvid") or bvid).strip(),
                "title": _sanitize_text(str(data.get("title") or "")),
                "stat": {
                    "view": int(stat.get("view") or 0),
                    "like": int(stat.get("like") or 0),
                    "coin": int(stat.get("coin") or 0),
                    "favorite": int(stat.get("favorite") or 0),
                    "share": int(stat.get("share") or 0),
                    "danmaku": int(stat.get("danmaku") or 0),
                    "reply": int(stat.get("reply") or 0),
                },
                "duration": int(data.get("duration") or 0),
                "pubdate": int(data.get("pubdate") or 0),
                "tname": _sanitize_text(str(data.get("tname") or "")),
                "tid": int(data.get("tid") or 0),
                "_internal_vmid": internal_vmid,
            }
        except Exception:
            logger.debug("View detail lookup failed for bvid=%s", bvid)
            return None

    def _fetch_follower_count(
        self,
        vmid: int,
        cache: Dict[int, Optional[int]],
    ) -> Optional[int]:
        """Fetches creator follower count via /x/relation/stat with per-vmid deduplication."""
        if vmid in cache:
            return cache[vmid]
        self._pause()
        try:
            resp = self.session.get(
                BILIBILI_RELATION_STAT_URL,
                params={"vmid": vmid},
                cookies=self.cookies,
                headers=self._headers(),
                timeout=10,
            )
            if resp.status_code != 200:
                cache[vmid] = None
                return None
            body = resp.json()
            if int(body.get("code") or 0) != 0:
                cache[vmid] = None
                return None
            follower_raw = (body.get("data") or {}).get("follower")
            if follower_raw is None:
                cache[vmid] = None
                return None
            follower_val = max(0, int(follower_raw))
            cache[vmid] = follower_val
            return follower_val
        except Exception:
            logger.debug("Creator relation stat lookup failed gracefully")
            cache[vmid] = None
            return None

    @staticmethod
    def _compute_pattern_insights(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregates title-hook and engagement patterns across confirmed dark-horse candidates."""
        n = len(candidates)
        if n == 0:
            return {
                "sample_size": 0,
                "avg_title_len": 0.0,
                "pct_bracket_prefix": 0.0,
                "pct_contest_suffix": 0.0,
                "pct_dialogue_quote": 0.0,
                "pct_number_contrast": 0.0,
                "pct_question_suspense": 0.0,
                "pct_any_hook": 0.0,
                "avg_coin_rate": 0.0,
                "avg_fav_rate": 0.0,
                "avg_share_rate": 0.0,
                "avg_danmaku_rate": 0.0,
                "avg_views_per_follower": 0.0,
                "top_track_buckets": [],
                "creator_tier_distribution": {},
                "recommendations": ["当前筛选条件下未命中黑马样本，可放宽 --min-views 或 --max-followers 后重试。"],
            }

        title_lens = [int(c["title_analysis"]["title_len"]) for c in candidates]
        bracket_cnt = sum(1 for c in candidates if c["title_analysis"]["has_bracket_prefix"])
        contest_cnt = sum(1 for c in candidates if c["title_analysis"]["has_contest_suffix"])
        quote_cnt = sum(1 for c in candidates if c["title_analysis"]["has_dialogue_quote"])
        number_cnt = sum(1 for c in candidates if c["title_analysis"]["has_number_contrast"])
        question_cnt = sum(1 for c in candidates if c["title_analysis"]["has_question_suspense"])
        any_hook_cnt = sum(
            1
            for c in candidates
            if (
                c["title_analysis"]["has_dialogue_quote"]
                or c["title_analysis"]["has_number_contrast"]
                or c["title_analysis"]["has_question_suspense"]
            )
        )

        pct_bracket = round((bracket_cnt / float(n)) * 100.0, 1)
        pct_contest = round((contest_cnt / float(n)) * 100.0, 1)
        pct_quote = round((quote_cnt / float(n)) * 100.0, 1)
        pct_number = round((number_cnt / float(n)) * 100.0, 1)
        pct_question = round((question_cnt / float(n)) * 100.0, 1)
        pct_any_hook = round((any_hook_cnt / float(n)) * 100.0, 1)

        avg_coin = round(sum(float(c["coin_rate"]) for c in candidates) / float(n), 4)
        avg_fav = round(sum(float(c["fav_rate"]) for c in candidates) / float(n), 4)
        avg_share = round(sum(float(c["share_rate"]) for c in candidates) / float(n), 4)
        avg_danmaku = round(sum(float(c["danmaku_rate"]) for c in candidates) / float(n), 4)
        avg_vpf = round(sum(float(c["views_per_follower"]) for c in candidates) / float(n), 2)
        avg_tlen = round(sum(title_lens) / float(n), 1)

        bucket_groups: Dict[str, List[float]] = {}
        tier_dist: Dict[str, int] = {}
        for c in candidates:
            b = str(c["title_analysis"]["track_bucket"])
            bucket_groups.setdefault(b, []).append(float(c["breakout_score"]))
            tier = str(c["creator_tier"])
            tier_dist[tier] = tier_dist.get(tier, 0) + 1

        top_buckets: List[Dict[str, Any]] = [
            {
                "track_bucket": b,
                "count": len(scores),
                "avg_breakout_score": round(sum(scores) / float(len(scores)), 2),
            }
            for b, scores in bucket_groups.items()
        ]
        top_buckets.sort(key=lambda x: (-int(x["count"]), -float(x["avg_breakout_score"]), str(x["track_bucket"])))

        recs: List[str] = []
        if pct_bracket <= 40.0:
            recs.append(
                f"仅 {pct_bracket:.1f}% 黑马使用【前缀】标签：移动端双列首屏仅展示前 20 字，优先去掉公式化【角色/剧集】前缀，直接把核心冲突或台词前移。"
            )
        else:
            recs.append(
                f"有 {pct_bracket:.1f}% 黑马带【前缀】标签，但须将前缀压缩在 6 字以内，确保前 20 字仍完整露出数字反差或悬念。"
            )
        if pct_contest <= 30.0:
            recs.append(
                f"仅 {pct_contest:.1f}% 黑马在主标题带赛事后缀（公开赛/创作营/征稿）：非强绑活动期尽量移除冗长赛事尾标，避免拉低自然推荐 CTR。"
            )
        if pct_any_hook >= 50.0:
            recs.append(
                f"{pct_any_hook:.1f}% 黑马标题包含对话引号/数字反差/悬念问句（引号 {pct_quote:.1f}% / 数字 {pct_number:.1f}% / 悬念 {pct_question:.1f}%），立项标题至少组合其中 2 项。"
            )
        top_b = top_buckets[0]
        recs.append(
            f"当前最强黑马题材桶为 `{top_b['track_bucket']}`（命中 {top_b['count']} 篇，均值 {top_b['avg_breakout_score']} 分）；"
            f"黑马均值投币率 {avg_coin * 100:.2f}% / 收藏率 {avg_fav * 100:.2f}% / 分享率 {avg_share * 100:.2f}%，脚本中必须设计明确的收藏/投币/弹幕押注钩子。"
        )

        return {
            "sample_size": n,
            "avg_title_len": avg_tlen,
            "pct_bracket_prefix": pct_bracket,
            "pct_contest_suffix": pct_contest,
            "pct_dialogue_quote": pct_quote,
            "pct_number_contrast": pct_number,
            "pct_question_suspense": pct_question,
            "pct_any_hook": pct_any_hook,
            "avg_coin_rate": avg_coin,
            "avg_fav_rate": avg_fav,
            "avg_share_rate": avg_share,
            "avg_danmaku_rate": avg_danmaku,
            "avg_views_per_follower": avg_vpf,
            "top_track_buckets": top_buckets,
            "creator_tier_distribution": tier_dist,
            "recommendations": recs,
        }

    def scan_dark_horses(
        self,
        queries: Optional[Sequence[str]] = None,
        max_followers: int = 50000,
        min_views: int = 30000,
        min_duration_sec: int = 45,
        per_query_limit: int = 12,
        top_n: int = 15,
        now_ts: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Scans Bilibili WBI search for small-account breakout videos with strict Zero-PII output."""
        raw_queries = queries if queries is not None else DEFAULT_RADAR_QUERIES
        eff_queries = [str(q).strip() for q in raw_queries if str(q).strip()]
        if not eff_queries:
            eff_queries = list(DEFAULT_RADAR_QUERIES)

        bvid_queries: Dict[str, List[str]] = {}
        total_search_hits = 0
        query_errors: List[Dict[str, str]] = []

        for idx, kw in enumerate(eff_queries):
            if idx > 0:
                self._pause()
            try:
                hits = self._wbi_search_videos(kw, limit=per_query_limit)
            except Exception as exc:
                query_errors.append({"query": kw, "error": _sanitize_text(str(exc))[:160]})
                continue
            total_search_hits += len(hits)
            for item in hits:
                bvid = str(item.get("bvid") or "").strip()
                if not bvid:
                    continue
                q_list = bvid_queries.setdefault(bvid, [])
                if kw not in q_list:
                    q_list.append(kw)

        vmid_cache: Dict[int, Optional[int]] = {}
        view_fetch_failed = 0
        follower_lookup_failed = 0
        filtered_high_follower = 0
        filtered_low_views = 0
        filtered_short_duration = 0
        confirmed: List[Dict[str, Any]] = []

        eff_now = float(now_ts) if now_ts is not None else time.time()

        for b_idx, (bvid, matched_queries) in enumerate(bvid_queries.items()):
            if b_idx > 0:
                self._pause()
            detail = self._fetch_view_detail(bvid)
            if detail is None:
                view_fetch_failed += 1
                continue

            stat = detail["stat"]
            view_cnt = int(stat["view"])
            duration_sec = int(detail["duration"])
            if view_cnt < min_views:
                filtered_low_views += 1
                continue
            if duration_sec < min_duration_sec:
                filtered_short_duration += 1
                continue

            vmid = detail.get("_internal_vmid")
            if vmid is None:
                follower_lookup_failed += 1
                continue

            follower_count = self._fetch_follower_count(int(vmid), vmid_cache)
            if follower_count is None:
                follower_lookup_failed += 1
                continue

            if follower_count > max_followers:
                filtered_high_follower += 1
                continue

            title_info = analyze_title_structure(str(detail["title"]))
            pubdate = int(detail["pubdate"])
            score_info = score_breakout_candidate(
                view=view_cnt,
                like=int(stat["like"]),
                coin=int(stat["coin"]),
                favorite=int(stat["favorite"]),
                share=int(stat["share"]),
                danmaku=int(stat["danmaku"]),
                reply=int(stat["reply"]),
                follower_count=follower_count,
                pubdate=pubdate,
                title_analysis=title_info,
                now_ts=eff_now,
            )

            pubdate_iso = datetime.fromtimestamp(pubdate, tz=timezone.utc).isoformat() if pubdate > 0 else None

            confirmed.append(
                {
                    "bvid": detail["bvid"],
                    "title": title_info["clean_title"],
                    "first_20_chars": title_info["first_20_chars"],
                    "matched_queries": matched_queries,
                    "tname": detail["tname"],
                    "tid": detail["tid"],
                    "duration_sec": duration_sec,
                    "pubdate": pubdate,
                    "pubdate_iso": pubdate_iso,
                    "view": view_cnt,
                    "like": int(stat["like"]),
                    "coin": int(stat["coin"]),
                    "favorite": int(stat["favorite"]),
                    "share": int(stat["share"]),
                    "danmaku": int(stat["danmaku"]),
                    "reply": int(stat["reply"]),
                    "creator_tier": score_info["creator_tier"],
                    "follower_count": score_info["follower_count"],
                    "views_per_follower": score_info["views_per_follower"],
                    "like_rate": score_info["like_rate"],
                    "coin_rate": score_info["coin_rate"],
                    "fav_rate": score_info["fav_rate"],
                    "share_rate": score_info["share_rate"],
                    "danmaku_rate": score_info["danmaku_rate"],
                    "reply_rate": score_info["reply_rate"],
                    "weighted_intent_rate": score_info["weighted_intent_rate"],
                    "age_days": score_info["age_days"],
                    "breakout_score": score_info["breakout_score"],
                    "title_analysis": title_info,
                }
            )

        confirmed.sort(
            key=lambda row: (
                -float(row["breakout_score"]),
                -float(row["views_per_follower"]),
                -int(row["view"]),
                str(row["bvid"]),
            )
        )
        top_candidates = confirmed[: max(1, int(top_n))]
        pattern_insights = self._compute_pattern_insights(top_candidates)

        return {
            "generated_at": datetime.fromtimestamp(eff_now, tz=timezone.utc).isoformat(),
            "queries": eff_queries,
            "filters": {
                "max_followers": int(max_followers),
                "min_views": int(min_views),
                "min_duration_sec": int(min_duration_sec),
                "per_query_limit": int(per_query_limit),
                "top_n": int(top_n),
            },
            "scan_stats": {
                "total_search_hits": total_search_hits,
                "unique_bvids_scanned": len(bvid_queries),
                "unique_creators_queried": len(vmid_cache),
                "confirmed_dark_horses": len(confirmed),
                "returned_count": len(top_candidates),
                "view_fetch_failed": view_fetch_failed,
                "follower_lookup_failed": follower_lookup_failed,
                "filtered_high_follower": filtered_high_follower,
                "filtered_low_views": filtered_low_views,
                "filtered_short_duration": filtered_short_duration,
                "query_errors": query_errors,
            },
            "candidates": top_candidates,
            "pattern_insights": pattern_insights,
        }

    def _load_ledger_bvid_map(self, ledger_path: Optional[Union[str, Path]] = None) -> Dict[str, Dict[str, Any]]:
        """Indexes library/creative_ledger.json episodes by BVID."""
        lpath = Path(ledger_path) if ledger_path is not None else (self.root_dir / "library" / "creative_ledger.json")
        if not lpath.exists():
            return {}
        try:
            data = json.loads(lpath.read_text(encoding="utf-8"))
        except Exception:
            return {}
        mapping: Dict[str, Dict[str, Any]] = {}
        for ep in data.get("episodes") or []:
            bvid = str(ep.get("bvid") or "").strip()
            if bvid:
                mapping[bvid] = {
                    "project_id": str(ep.get("project_id") or "").strip(),
                    "archetype": str(ep.get("archetype") or "").strip(),
                    "meme_source": str(ep.get("meme_source") or "").strip(),
                    "date": str(ep.get("date") or "").strip(),
                }
        return mapping

    def _build_manifest_bvid_map(self) -> Dict[str, Dict[str, Any]]:
        """Maps BVID -> local project_id using staged publish manifests when available."""
        mapping: Dict[str, Dict[str, Any]] = {}
        projects_dir = self.root_dir / "projects"
        if not projects_dir.exists():
            return mapping
        for mf in sorted(projects_dir.glob("*/delivery/staged_bilibili/publish_manifest.json")):
            try:
                mdata = json.loads(mf.read_text(encoding="utf-8"))
                bvid = str((mdata.get("advisor_receipt") or {}).get("bvid") or mdata.get("bvid") or "").strip()
                proj_id = str(mdata.get("project_id") or mf.parents[2].name).strip()
                if bvid:
                    mapping[bvid] = {"project_id": proj_id}
            except Exception:
                continue
        return mapping

    @staticmethod
    def _summarize_track(
        track_key: str,
        published_eps: List[Dict[str, Any]],
        pending_items: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Aggregates published performance and scheduled queue for a single horse-race track."""
        count = len(published_eps)
        sorted_pending = sorted(pending_items, key=lambda x: (str(x.get("dtime_iso") or "9999"), str(x.get("bvid"))))

        if count == 0:
            return {
                "track": track_key,
                "label": TRACK_DISPLAY_LABELS.get(track_key, track_key),
                "is_core_horse_race": track_key in HORSE_RACE_CORE_TRACKS,
                "count": 0,
                "total_views": 0,
                "avg_views": 0.0,
                "like_rate_pct": 0.0,
                "coin_rate_pct": 0.0,
                "fav_rate_pct": 0.0,
                "share_rate_pct": 0.0,
                "reply_rate_pct": 0.0,
                "avg_tm_stars": 0.0,
                "avg_crash_rate_pct": 0.0,
                "best_bvid": None,
                "best_views": 0,
                "composite_score": 0.0,
                "pending_count": len(sorted_pending),
                "pending_items": sorted_pending,
            }

        total_views = sum(int(ep["view"]) for ep in published_eps)
        total_likes = sum(int(ep["like"]) for ep in published_eps)
        total_coins = sum(int(ep["coin"]) for ep in published_eps)
        total_favs = sum(int(ep["favorite"]) for ep in published_eps)
        total_shares = sum(int(ep["share"]) for ep in published_eps)
        total_replies = sum(int(ep["reply"]) for ep in published_eps)

        avg_views = total_views / float(count)
        denom = float(max(total_views, 1)) if total_views > 0 else 1.0
        like_rate_pct = (total_likes / denom) * 100.0 if total_views > 0 else 0.0
        coin_rate_pct = (total_coins / denom) * 100.0 if total_views > 0 else 0.0
        fav_rate_pct = (total_favs / denom) * 100.0 if total_views > 0 else 0.0
        share_rate_pct = (total_shares / denom) * 100.0 if total_views > 0 else 0.0
        reply_rate_pct = (total_replies / denom) * 100.0 if total_views > 0 else 0.0

        tm_vals = [float(ep["tm_stars"]) for ep in published_eps if ep.get("tm_stars") is not None]
        crash_vals = [float(ep["crash_rate_pct"]) for ep in published_eps if ep.get("crash_rate_pct") is not None]
        avg_tm_stars = sum(tm_vals) / float(len(tm_vals)) if tm_vals else 0.0
        avg_crash_rate_pct = sum(crash_vals) / float(len(crash_vals)) if crash_vals else 0.0

        best_ep = max(published_eps, key=lambda ep: (int(ep["view"]), int(ep["coin"]), int(ep["favorite"])))

        # Composite horse-race score (0..100): views + strong intent (coin/fav/share) + low 3s crash + tm_stars
        views_pts = min(40.0, math.log1p(max(0.0, avg_views)) * 4.0)
        intent_pts = min(
            45.0,
            coin_rate_pct * 4.0
            + fav_rate_pct * 3.0
            + share_rate_pct * 5.0
            + like_rate_pct * 0.8
            + reply_rate_pct * 1.2,
        )
        retention_pts = max(0.0, min(12.0, (50.0 - avg_crash_rate_pct) * 0.28)) if crash_vals else 0.0
        tm_pts = min(5.0, avg_tm_stars * 1.0)
        composite_score = round(max(0.0, min(100.0, views_pts + intent_pts + retention_pts + tm_pts)), 2)

        return {
            "track": track_key,
            "label": TRACK_DISPLAY_LABELS.get(track_key, track_key),
            "is_core_horse_race": track_key in HORSE_RACE_CORE_TRACKS,
            "count": count,
            "total_views": total_views,
            "avg_views": round(avg_views, 2),
            "like_rate_pct": round(like_rate_pct, 2),
            "coin_rate_pct": round(coin_rate_pct, 2),
            "fav_rate_pct": round(fav_rate_pct, 2),
            "share_rate_pct": round(share_rate_pct, 2),
            "reply_rate_pct": round(reply_rate_pct, 2),
            "avg_tm_stars": round(avg_tm_stars, 2),
            "avg_crash_rate_pct": round(avg_crash_rate_pct, 2),
            "best_bvid": str(best_ep["bvid"]),
            "best_views": int(best_ep["view"]),
            "composite_score": composite_score,
            "pending_count": len(sorted_pending),
            "pending_items": sorted_pending,
        }

    def evaluate_channel_horse_race(
        self,
        analytics_json_path: Optional[Union[str, Path]] = None,
        ledger_path: Optional[Union[str, Path]] = None,
    ) -> Dict[str, Any]:
        """Evaluates our channel's multi-track horse race with zero PII and zero network calls."""
        apath = Path(analytics_json_path) if analytics_json_path is not None else DEFAULT_ANALYTICS_SNAPSHOT
        if not apath.exists():
            raise FileNotFoundError(f"Analytics snapshot not found: {apath}")

        payload = json.loads(apath.read_text(encoding="utf-8"))
        account_obj = payload.get("account") or {}
        sensitive_tokens: Set[str] = {
            str(account_obj.get(k) or "").strip()
            for k in ("uid", "mid", "uname", "dede_userid")
            if str(account_obj.get(k) or "").strip() and str(account_obj.get(k) or "").strip() != "<REDACTED>"
        }

        raw_follower = account_obj.get("follower")
        follower_count: Optional[int] = int(raw_follower) if raw_follower is not None else None
        creator_tier = classify_creator_tier(follower_count)

        ledger_map = self._load_ledger_bvid_map(ledger_path)
        manifest_map = self._build_manifest_bvid_map()

        published_by_track: Dict[str, List[Dict[str, Any]]] = {t: [] for t in ALL_HORSE_RACE_TRACKS}
        pending_by_track: Dict[str, List[Dict[str, Any]]] = {t: [] for t in ALL_HORSE_RACE_TRACKS}

        published_count = 0
        scheduled_count = 0
        latest_dtime_iso: Optional[str] = None

        for arc in payload.get("archives") or []:
            bvid = _sanitize_text(str(arc.get("bvid") or ""), sensitive_tokens)
            clean_title = _sanitize_text(str(arc.get("title") or ""), sensitive_tokens)
            state_desc = _sanitize_text(str(arc.get("state_desc") or ""), sensitive_tokens)
            raw_state = arc.get("state")
            state = int(raw_state) if raw_state is not None else 0

            track = _classify_horse_race_track(arc, ledger_map.get(bvid), manifest_map.get(bvid))

            if state < 0:
                if "退回" in state_desc or bool(arc.get("reject_reason")):
                    continue
                scheduled_count += 1
                dtime_iso_raw = arc.get("dtime_iso")
                dtime_iso = _sanitize_text(str(dtime_iso_raw), sensitive_tokens) if dtime_iso_raw else None
                if dtime_iso and (latest_dtime_iso is None or dtime_iso > latest_dtime_iso):
                    latest_dtime_iso = dtime_iso
                pending_by_track[track].append(
                    {
                        "bvid": bvid,
                        "title_head": clean_title[:24],
                        "dtime_iso": dtime_iso,
                        "state_desc": state_desc or "等待发布",
                    }
                )
                continue

            published_count += 1
            stat = arc.get("stat") or {}
            diag = arc.get("diagnose") or {}
            published_by_track[track].append(
                {
                    "bvid": bvid,
                    "title": clean_title,
                    "view": int(stat.get("view") or 0),
                    "like": int(stat.get("like") or 0),
                    "coin": int(stat.get("coin") or 0),
                    "favorite": int(stat.get("favorite") or 0),
                    "share": int(stat.get("share") or 0),
                    "reply": int(stat.get("reply") or 0),
                    "tm_stars": float(diag["tm_stars"]) if diag.get("tm_stars") is not None else None,
                    "crash_rate_pct": (
                        float(diag["crash_rate_pct"]) if diag.get("crash_rate_pct") is not None else None
                    ),
                }
            )

        tracks: Dict[str, Dict[str, Any]] = {
            t: self._summarize_track(t, published_by_track[t], pending_by_track[t]) for t in ALL_HORSE_RACE_TRACKS
        }

        awaiting_tracks = [
            t for t in HORSE_RACE_CORE_TRACKS if tracks[t]["count"] == 0 and tracks[t]["pending_count"] > 0
        ]
        missing_unscheduled = [
            t for t in HORSE_RACE_CORE_TRACKS if tracks[t]["count"] == 0 and tracks[t]["pending_count"] == 0
        ]

        recommended_winning_track: Optional[str] = None
        next_actions: List[str] = []

        if awaiting_tracks:
            decision_status = "awaiting_horse_race_releases"
            awaiting_str = ", ".join(awaiting_tracks)
            latest_note = f"（最晚定时稿件释放时间：{latest_dtime_iso}）" if latest_dtime_iso else ""
            decision_summary = (
                f"四大赛道赛马尚未收官：仍有 `{awaiting_str}` 处于定时待发队列（已发布=0、待发>0）{latest_note}。"
                "请耐心等待至 12/01（2026-12-01）完成 Ep019–023 全赛道 24h+ 数据回收后，再按播放量+投币/收藏/分享率+低3秒划走率锁定单一主攻赛道。"
            )
            next_actions = [
                "继续执行 11/26–11/30 既有定时排期（Ep019–Ep023），暂不新增第五条分支赛道。",
                "12/01 运行 `cli.py analytics` 与 `cli.py breakout-radar --horse-race` 收口四赛道实测对比。",
                "若 `ai_experiment` 或 `oss_tool_demo` 跑出显著更高投币/收藏率，优先走零可灵积分高杠杆路线连拍 5 期。",
            ]
        elif not missing_unscheduled:
            decision_status = "focus_single_track"
            ranked_core = sorted(
                HORSE_RACE_CORE_TRACKS,
                key=lambda t: (
                    float(tracks[t]["composite_score"]),
                    float(tracks[t]["avg_views"]),
                    float(tracks[t]["coin_rate_pct"]) + float(tracks[t]["fav_rate_pct"]),
                ),
                reverse=True,
            )
            recommended_winning_track = ranked_core[0]
            win = tracks[recommended_winning_track]
            runner = tracks[ranked_core[1]]
            decision_summary = (
                f"四大赛道均已产出实测数据，综合胜出赛道为 `{recommended_winning_track}`"
                f"（综合分 {win['composite_score']:.2f} vs 次名 `{ranked_core[1]}` {runner['composite_score']:.2f}；"
                f"均播 {win['avg_views']:.1f} / 投币率 {win['coin_rate_pct']:.2f}% / 收藏率 {win['fav_rate_pct']:.2f}% / "
                f"分享率 {win['share_rate_pct']:.2f}% / 3秒划走率 {win['avg_crash_rate_pct']:.2f}%）。"
                "建议未来连续 5 期 All-In 该单一赛道并持续迭代前 20 字强钩子标题。"
            )
            next_actions = [
                f"将接下来 5 期新企划全部聚焦在 `{recommended_winning_track}` 赛道，停止多线分散试错。",
                "复盘胜出赛道标杆稿件的前 20 字标题结构、首 3 秒画面与投币/收藏触发点，固化为下 5 期模板基线。",
                "每期发布前运行 `cli.py breakout-radar` 检索同赛道 <5万粉黑马，持续吸纳新鲜冲突与互动钩子。",
            ]
        else:
            decision_status = "insufficient_horse_race_coverage"
            missing_str = ", ".join(missing_unscheduled)
            decision_summary = (
                f"四大赛道覆盖不足（缺失未排期赛道：`{missing_str}`），尚无法做出赛马收口决策；"
                "请补齐各核心赛道样本或在 12/01 后重新导入完整遥测快照。"
            )
            next_actions = [
                f"检查并补齐缺失赛道样本：{missing_str}。",
                "更新脱敏遥测快照后重新运行 `cli.py breakout-radar --horse-race`。",
            ]

        snap_ts = _sanitize_text(str(payload.get("timestamp") or "unknown"), sensitive_tokens)

        return {
            "snapshot_timestamp": snap_ts,
            "follower_count": follower_count,
            "creator_tier": creator_tier,
            "published_count": published_count,
            "scheduled_count": scheduled_count,
            "core_tracks": list(HORSE_RACE_CORE_TRACKS),
            "tracks": tracks,
            "awaiting_tracks": awaiting_tracks,
            "readout_target_date": "2026-12-01",
            "decision_status": decision_status,
            "recommended_winning_track": recommended_winning_track,
            "decision_summary": decision_summary,
            "next_actions": next_actions,
        }

    @staticmethod
    def format_radar_markdown(
        radar_report: Optional[Dict[str, Any]],
        horse_race_report: Optional[Dict[str, Any]],
    ) -> str:
        """Formats dark-horse radar and/or channel horse-race reports into Zero-PII Markdown."""
        lines: List[str] = [
            "# Bilibili Dark-Horse Breakout Radar & Channel Horse-Race Report",
            "",
            "> **Zero-PII Compliance**: Creator identities are strictly anonymized into follower tiers (`<1k`..`50k+`) with numeric follower counts only.",
            "",
        ]

        if radar_report is not None:
            stats = radar_report.get("scan_stats") or {}
            filt = radar_report.get("filters") or {}
            queries = radar_report.get("queries") or []
            lines.extend(
                [
                    "## 1. Dark-Horse Breakout Scan",
                    f"- **Generated At**: `{radar_report.get('generated_at', 'unknown')}`",
                    f"- **Queries**: {', '.join(f'`{q}`' for q in queries)}",
                    (
                        f"- **Filters**: `followers <= {filt.get('max_followers', 50000)}`, "
                        f"`views >= {filt.get('min_views', 30000)}`, "
                        f"`duration >= {filt.get('min_duration_sec', 45)}s`"
                    ),
                    (
                        f"- **Scan Funnel**: `{stats.get('total_search_hits', 0)}` hits -> "
                        f"`{stats.get('unique_bvids_scanned', 0)}` unique BVIDs -> "
                        f"`{stats.get('confirmed_dark_horses', 0)}` confirmed dark horses "
                        f"(high_follower={stats.get('filtered_high_follower', 0)}, "
                        f"low_views={stats.get('filtered_low_views', 0)}, "
                        f"short_dur={stats.get('filtered_short_duration', 0)}, "
                        f"follower_lookup_failed={stats.get('follower_lookup_failed', 0)})"
                    ),
                    "",
                ]
            )

            candidates = radar_report.get("candidates") or []
            if candidates:
                lines.extend(
                    [
                        "| Rank | BVID | Tier (Followers) | Views | V/F | Coin% | Fav% | Share% | Score | Bucket | First 20 Chars |",
                        "| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- | :--- |",
                    ]
                )
                for idx, c in enumerate(candidates, start=1):
                    first20 = str(c.get("first_20_chars") or "").replace("|", "\\|")
                    lines.append(
                        f"| {idx} | `{c['bvid']}` | {c['creator_tier']} ({c['follower_count']}) | "
                        f"{int(c['view']):,} | {float(c['views_per_follower']):.1f}x | "
                        f"{float(c['coin_rate']) * 100:.2f}% | {float(c['fav_rate']) * 100:.2f}% | "
                        f"{float(c['share_rate']) * 100:.2f}% | **{float(c['breakout_score']):.1f}** | "
                        f"`{c['title_analysis']['track_bucket']}` | {first20} |"
                    )
                lines.append("")
            else:
                lines.extend(["*No confirmed dark-horse candidates matched the current filter thresholds.*", ""])

            insights = radar_report.get("pattern_insights") or {}
            if insights:
                lines.extend(
                    [
                        "### Pattern Insights & Title Hook Audit",
                        (
                            f"- **Title Structure (n={insights.get('sample_size', 0)})**: "
                            f"avg_len=`{insights.get('avg_title_len', 0.0)}`, "
                            f"bracket_prefix=`{insights.get('pct_bracket_prefix', 0.0)}%`, "
                            f"contest_suffix=`{insights.get('pct_contest_suffix', 0.0)}%`, "
                            f"quote=`{insights.get('pct_dialogue_quote', 0.0)}%`, "
                            f"number=`{insights.get('pct_number_contrast', 0.0)}%`, "
                            f"question/suspense=`{insights.get('pct_question_suspense', 0.0)}%`"
                        ),
                        (
                            f"- **Engagement Benchmarks**: "
                            f"avg_V/F=`{insights.get('avg_views_per_follower', 0.0)}x`, "
                            f"coin=`{float(insights.get('avg_coin_rate', 0.0)) * 100:.2f}%`, "
                            f"fav=`{float(insights.get('avg_fav_rate', 0.0)) * 100:.2f}%`, "
                            f"share=`{float(insights.get('avg_share_rate', 0.0)) * 100:.2f}%`, "
                            f"danmaku=`{float(insights.get('avg_danmaku_rate', 0.0)) * 100:.2f}%`"
                        ),
                    ]
                )
                for rec in insights.get("recommendations") or []:
                    lines.append(f"- **Recommendation**: {rec}")
                lines.append("")

        if horse_race_report is not None:
            sec_num = "2" if radar_report is not None else "1"
            winner = horse_race_report.get("recommended_winning_track") or "Pending (awaiting releases)"
            lines.extend(
                [
                    f"## {sec_num}. Channel Horse-Race Evaluation",
                    (
                        f"- **Snapshot**: `{horse_race_report.get('snapshot_timestamp', 'unknown')}` | "
                        f"**Channel Tier**: `{horse_race_report.get('creator_tier', 'unknown')}` "
                        f"(`{horse_race_report.get('follower_count')}` followers) | "
                        f"**Published**: `{horse_race_report.get('published_count', 0)}` | "
                        f"**Scheduled**: `{horse_race_report.get('scheduled_count', 0)}`"
                    ),
                    f"- **Decision Status**: `{horse_race_report.get('decision_status')}` | **Recommended Track**: `{winner}`",
                    f"- **Summary**: {horse_race_report.get('decision_summary', '')}",
                    "",
                    "| Track | Published | Pending | Avg Views | Like% | Coin% | Fav% | Share% | Reply% | Avg Stars | 3s Crash% | Score | Best BVID |",
                    "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |",
                ]
            )
            tracks_map = horse_race_report.get("tracks") or {}
            pending_rows: List[Tuple[str, Dict[str, Any]]] = []
            for tkey in ALL_HORSE_RACE_TRACKS:
                tinfo = tracks_map.get(tkey)
                if not tinfo:
                    continue
                core_tag = "★ " if tinfo.get("is_core_horse_race") else ""
                best_str = f"`{tinfo['best_bvid']}` ({tinfo['best_views']})" if tinfo.get("best_bvid") else "—"
                lines.append(
                    f"| {core_tag}`{tkey}` | {tinfo['count']} | {tinfo['pending_count']} | "
                    f"{float(tinfo['avg_views']):.1f} | {float(tinfo['like_rate_pct']):.2f}% | "
                    f"{float(tinfo['coin_rate_pct']):.2f}% | {float(tinfo['fav_rate_pct']):.2f}% | "
                    f"{float(tinfo['share_rate_pct']):.2f}% | {float(tinfo['reply_rate_pct']):.2f}% | "
                    f"{float(tinfo['avg_tm_stars']):.2f} | {float(tinfo['avg_crash_rate_pct']):.2f}% | "
                    f"{float(tinfo['composite_score']):.1f} | {best_str} |"
                )
                for pitem in tinfo.get("pending_items") or []:
                    pending_rows.append((tkey, pitem))

            if pending_rows:
                pending_rows.sort(key=lambda pair: (str(pair[1].get("dtime_iso") or "9999"), pair[0]))
                lines.extend(
                    [
                        "",
                        "### Scheduled Horse-Race Queue",
                        "| Track | BVID | Scheduled Time | State | Title Head |",
                        "| :--- | :--- | :--- | :--- | :--- |",
                    ]
                )
                for tkey, pitem in pending_rows:
                    thead = str(pitem.get("title_head") or "").replace("|", "\\|")
                    lines.append(
                        f"| `{tkey}` | `{pitem['bvid']}` | `{pitem.get('dtime_iso') or 'TBD'}` | "
                        f"{pitem.get('state_desc', '')} | {thead} |"
                    )

            actions = horse_race_report.get("next_actions") or []
            if actions:
                lines.extend(["", "### Next Actions"])
                for act in actions:
                    lines.append(f"- {act}")
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def save_report(
        self,
        payload: Dict[str, Any],
        markdown_text: str,
    ) -> Tuple[Path, Path]:
        """Writes breakout_radar_latest.json and breakout_radar_latest.md to library/benchmarks/."""
        out_dir = self.root_dir / "library" / "benchmarks"
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = out_dir / "breakout_radar_latest.json"
        md_path = out_dir / "breakout_radar_latest.md"
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        md_path.write_text(markdown_text, encoding="utf-8")
        return json_path, md_path
