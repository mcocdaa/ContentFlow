"""Offline unit tests for core/breakout_radar.py and cli.py breakout-radar."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import pytest

import cli
from config.settings import CONTENTFLOW_ROOT
from core.breakout_radar import (
    BILIBILI_NAV_URL,
    BILIBILI_RELATION_STAT_URL,
    BILIBILI_VIEW_URL,
    BILIBILI_WBI_SEARCH_URL,
    BreakoutRadarEngine,
    analyze_title_structure,
    classify_creator_tier,
    score_breakout_candidate,
)


class _StubResponse:
    def __init__(self, payload: Dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> Dict[str, Any]:
        return self._payload


class _StubRadarSession:
    """Offline HTTP stub for Bilibili nav, WBI search, view detail, and relation/stat."""

    def __init__(
        self,
        search_results: Dict[str, List[Dict[str, Any]]],
        view_details: Dict[str, Dict[str, Any]],
        relation_stats: Dict[int, Any],
    ) -> None:
        self.search_results = search_results
        self.view_details = view_details
        self.relation_stats = relation_stats
        self.relation_calls: List[int] = []
        self.view_calls: List[str] = []
        self.search_calls: List[str] = []

    def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        cookies: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 10,
    ) -> _StubResponse:
        if url.startswith(BILIBILI_NAV_URL):
            return _StubResponse(
                {
                    "code": 0,
                    "data": {
                        "wbi_img": {
                            "img_url": "https://i0.hdslb.com/bfs/wbi/7cd084941338484aae1ad9425b84077c.png",
                            "sub_url": "https://i0.hdslb.com/bfs/wbi/4932caff0ff746eab6f01bf08b70ac45.png",
                        }
                    },
                }
            )
        if url.startswith(BILIBILI_WBI_SEARCH_URL):
            qs = parse_qs(urlparse(url).query)
            kw = (qs.get("keyword") or [""])[0]
            assert "w_rid" in qs and len(qs["w_rid"][0]) == 32
            self.search_calls.append(kw)
            return _StubResponse({"code": 0, "data": {"result": self.search_results.get(kw, [])}})
        if url.startswith(BILIBILI_VIEW_URL):
            bvid = str((params or {}).get("bvid") or "")
            self.view_calls.append(bvid)
            detail = self.view_details.get(bvid)
            if detail is None:
                return _StubResponse({"code": -404, "data": {}})
            return _StubResponse({"code": 0, "data": detail})
        if url.startswith(BILIBILI_RELATION_STAT_URL):
            vmid = int((params or {}).get("vmid") or 0)
            self.relation_calls.append(vmid)
            outcome = self.relation_stats.get(vmid)
            if isinstance(outcome, Exception):
                raise outcome
            if isinstance(outcome, dict):
                return _StubResponse(outcome)
            if outcome is None:
                return _StubResponse({"code": -412, "message": "rate limited"})
            return _StubResponse({"code": 0, "data": {"mid": vmid, "follower": int(outcome)}})
        raise AssertionError(f"Unexpected URL: {url}")


def _assert_no_pii_keys_or_values(obj: Any, forbidden_values: List[str]) -> None:
    forbidden_keys = {"uid", "mid", "vmid", "uname", "author", "owner", "cookies"}

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                assert str(k).lower() not in forbidden_keys, f"Forbidden PII key found: {k}"
                _walk(v)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(obj)
    serialized = json.dumps(obj, ensure_ascii=False)
    for bad in forbidden_values:
        assert bad not in serialized, f"Forbidden PII value leaked into JSON: {bad}"
    assert "@" not in serialized, "Raw @mention leaked into JSON output"


def test_analyze_title_structure_and_creator_tier() -> None:
    """Verifies title cleaning, first_20_chars, hook signals, clutter flags, track buckets, and creator tiers."""
    t_exp = analyze_title_structure(
        '【AI博弈实验】<em class="keyword">把5个AI</em>关进密室分1000万，竟然互相背刺？ @SecretUser 【B站AI创造公开赛】'
    )
    assert "<em" not in t_exp["clean_title"]
    assert "@SecretUser" not in t_exp["clean_title"]
    assert t_exp["first_20_chars"] == t_exp["clean_title"][:20]
    assert len(t_exp["first_20_chars"]) == 20
    assert t_exp["title_len"] == len(t_exp["clean_title"])
    assert t_exp["has_bracket_prefix"] is True
    assert t_exp["has_contest_suffix"] is True
    assert t_exp["has_number_contrast"] is True
    assert t_exp["has_question_suspense"] is True
    assert t_exp["has_dialogue_quote"] is False
    assert t_exp["track_bucket"] == "ai_experiment"
    assert "number_contrast" in t_exp["hook_signals"]
    assert "question_suspense" in t_exp["hook_signals"]

    t_comedy = analyze_title_structure("大肥鱼：“豆姐啊，3天后智械危机了真能带我飞吗？”")
    assert t_comedy["has_bracket_prefix"] is False
    assert t_comedy["has_contest_suffix"] is False
    assert t_comedy["has_dialogue_quote"] is True
    assert t_comedy["has_number_contrast"] is True
    assert t_comedy["has_question_suspense"] is True
    assert t_comedy["track_bucket"] == "ai_persona_comedy"
    assert "dialogue_quote" in t_comedy["hook_signals"]
    assert "front_loaded_20_hook" in t_comedy["hook_signals"]

    t_tool = analyze_title_structure("为了治好熬夜摸鱼，我写了个“毒舌AI监工”开源工具：切屏3秒拉警报")
    assert t_tool["track_bucket"] == "ai_tool_demo"
    assert t_tool["has_dialogue_quote"] is True
    assert t_tool["has_number_contrast"] is True

    t_scifi = analyze_title_structure("假如AI学会替你回微信：消失7天竟然没人发现的科幻短片")
    assert t_scifi["track_bucket"] == "ai_scifi_story"
    assert t_scifi["has_question_suspense"] is True

    t_other = analyze_title_structure("周末去公园散步随手记录")
    assert t_other["track_bucket"] == "other"
    assert t_other["hook_signals"] == []

    assert classify_creator_tier(None) == "unknown"
    assert classify_creator_tier(15) == "<1k"
    assert classify_creator_tier(999) == "<1k"
    assert classify_creator_tier(1000) == "1k-5k"
    assert classify_creator_tier(4999) == "1k-5k"
    assert classify_creator_tier(5000) == "5k-20k"
    assert classify_creator_tier(19999) == "5k-20k"
    assert classify_creator_tier(20000) == "20k-50k"
    assert classify_creator_tier(50000) == "20k-50k"
    assert classify_creator_tier(50001) == "50k+"

    # Score penalty check: contest suffix lowers score compared to clean title
    now_ts = 1_800_000_000.0
    clean_score = score_breakout_candidate(
        view=120_000,
        like=8_000,
        coin=3_000,
        favorite=6_000,
        share=1_200,
        danmaku=900,
        reply=500,
        follower_count=40,  # tests max(follower, 100) floor -> 1200.0x
        pubdate=int(now_ts - 5 * 86400),
        title_analysis=t_tool,
        now_ts=now_ts,
    )
    cluttered_score = score_breakout_candidate(
        view=120_000,
        like=8_000,
        coin=3_000,
        favorite=6_000,
        share=1_200,
        danmaku=900,
        reply=500,
        follower_count=40,
        pubdate=int(now_ts - 5 * 86400),
        title_analysis=t_exp,
        now_ts=now_ts,
    )
    assert clean_score["views_per_follower"] == 1200.0
    assert clean_score["breakout_score"] > cluttered_score["breakout_score"]


def test_scan_dark_horses_filters_dedupes_graceful_errors_and_zero_pii(tmp_path: Path) -> None:
    """Verifies filtering, vmid deduplication, graceful relation failure, scoring order, and strict zero-PII."""
    now_ts = 1_800_000_000.0
    search_results = {
        "AI博弈实验": [
            {"bvid": "BV1DARKHORSE1", "title": "把5个AI关进密室分1000万，第2轮竟互相背刺？ @LeakHandle1"},
            {"bvid": "BV1DARKHORSE2", "title": "我写了个开源AI工具：切屏3秒直接全屏警报"},
            {"bvid": "BV1BIGCREATOR", "title": "百万粉大V聊AI博弈实验"},
            {"bvid": "BV1LOWVIEWS00", "title": "播放不够的AI实验"},
            {"bvid": "BV1SHORTDUR00", "title": "时长太短的AI视频"},
            {"bvid": "BV1RELFAIL000", "title": "粉丝数接口限流的黑马测试"},
        ],
        "AI开源工具": [
            # Duplicate BVID across queries must be scanned only once
            {"bvid": "BV1DARKHORSE2", "title": "我写了个开源AI工具：切屏3秒直接全屏警报"},
            # Second qualifying video from SAME vmid=10001 -> must reuse cached follower count!
            {"bvid": "BV1DARKHORSE3", "title": "【AI博弈实验】旧视频带赛事尾标真能火吗？【B站AI创造公开赛】"},
        ],
    }

    view_details = {
        "BV1DARKHORSE1": {
            "bvid": "BV1DARKHORSE1",
            "title": "把5个AI关进密室分1000万，第2轮竟互相背刺？ @LeakHandle1",
            "duration": 210,
            "pubdate": int(now_ts - 4 * 86400),
            "tname": "计算机技术",
            "tid": 231,
            "owner": {"mid": 10001, "name": "SecretSmallCreator_AAA"},
            "stat": {
                "view": 180_000,
                "like": 14_000,
                "coin": 6_000,
                "favorite": 9_500,
                "share": 2_400,
                "danmaku": 1_800,
                "reply": 900,
            },
        },
        "BV1DARKHORSE2": {
            "bvid": "BV1DARKHORSE2",
            "title": "我写了个开源AI工具：切屏3秒直接全屏警报",
            "duration": 145,
            "pubdate": int(now_ts - 20 * 86400),
            "tname": "计算机技术",
            "tid": 231,
            "owner": {"mid": 20002, "name": "SecretMidCreator_BBB"},
            "stat": {
                "view": 80_000,
                "like": 4_500,
                "coin": 1_800,
                "favorite": 4_200,
                "share": 700,
                "danmaku": 400,
                "reply": 310,
            },
        },
        "BV1DARKHORSE3": {
            "bvid": "BV1DARKHORSE3",
            "title": "【AI博弈实验】旧视频带赛事尾标真能火吗？【B站AI创造公开赛】",
            "duration": 95,
            "pubdate": int(now_ts - 60 * 86400),
            "tname": "计算机技术",
            "tid": 231,
            "owner": {"mid": 10001, "name": "SecretSmallCreator_AAA"},
            "stat": {
                "view": 40_000,
                "like": 1_200,
                "coin": 200,
                "favorite": 400,
                "share": 80,
                "danmaku": 60,
                "reply": 50,
            },
        },
        "BV1BIGCREATOR": {
            "bvid": "BV1BIGCREATOR",
            "title": "百万粉大V聊AI博弈实验",
            "duration": 300,
            "pubdate": int(now_ts - 3 * 86400),
            "tname": "数码",
            "tid": 95,
            "owner": {"mid": 30003, "name": "MegaCreator_CCC"},
            "stat": {
                "view": 500_000,
                "like": 20_000,
                "coin": 5_000,
                "favorite": 8_000,
                "share": 900,
                "danmaku": 600,
                "reply": 400,
            },
        },
        "BV1LOWVIEWS00": {
            "bvid": "BV1LOWVIEWS00",
            "title": "播放不够的AI实验",
            "duration": 120,
            "pubdate": int(now_ts - 2 * 86400),
            "tname": "数码",
            "tid": 95,
            "owner": {"mid": 40004, "name": "LowViewCreator_DDD"},
            "stat": {"view": 12_000, "like": 300, "coin": 20, "favorite": 50, "share": 10, "danmaku": 5, "reply": 12},
        },
        "BV1SHORTDUR00": {
            "bvid": "BV1SHORTDUR00",
            "title": "时长太短的AI视频",
            "duration": 30,
            "pubdate": int(now_ts - 2 * 86400),
            "tname": "综合",
            "tid": 27,
            "owner": {"mid": 50005, "name": "ShortDurCreator_EEE"},
            "stat": {
                "view": 90_000,
                "like": 5_000,
                "coin": 100,
                "favorite": 200,
                "share": 50,
                "danmaku": 20,
                "reply": 40,
            },
        },
        "BV1RELFAIL000": {
            "bvid": "BV1RELFAIL000",
            "title": "粉丝数接口限流的黑马测试",
            "duration": 110,
            "pubdate": int(now_ts - 5 * 86400),
            "tname": "计算机技术",
            "tid": 231,
            "owner": {"mid": 60006, "name": "RateLimitedCreator_FFF"},
            "stat": {
                "view": 95_000,
                "like": 4_000,
                "coin": 1_200,
                "favorite": 2_500,
                "share": 500,
                "danmaku": 300,
                "reply": 200,
            },
        },
    }

    relation_stats = {
        10001: 450,  # <1k tier, shared by BV1DARKHORSE1 and BV1DARKHORSE3
        20002: 8_000,  # 5k-20k tier
        30003: 250_000,  # >50k filtered out
        60006: RuntimeError("Simulated 412 rate limit"),  # must fail gracefully
    }

    stub = _StubRadarSession(search_results, view_details, relation_stats)
    engine = BreakoutRadarEngine(
        root_dir=tmp_path,
        cookies={"SESSDATA": "top_secret_cookie_val"},
        session=stub,  # type: ignore[arg-type]
        request_delay_sec=0.0,
    )

    report = engine.scan_dark_horses(
        queries=["AI博弈实验", "AI开源工具"],
        max_followers=50_000,
        min_views=30_000,
        min_duration_sec=45,
        per_query_limit=10,
        top_n=10,
        now_ts=now_ts,
    )

    stats = report["scan_stats"]
    assert stats["unique_bvids_scanned"] == 7
    assert stats["filtered_low_views"] == 1
    assert stats["filtered_short_duration"] == 1
    assert stats["filtered_high_follower"] == 1
    assert stats["follower_lookup_failed"] == 1
    assert stats["confirmed_dark_horses"] == 3

    # Verify vmid=10001 was queried ONLY ONCE across BV1DARKHORSE1 & BV1DARKHORSE3
    assert stub.relation_calls.count(10001) == 1
    assert 40004 not in stub.relation_calls  # skipped pre-filter low view
    assert 50005 not in stub.relation_calls  # skipped pre-filter short duration

    cands = report["candidates"]
    assert [c["bvid"] for c in cands] == ["BV1DARKHORSE1", "BV1DARKHORSE2", "BV1DARKHORSE3"]
    assert cands[0]["creator_tier"] == "<1k"
    assert cands[0]["views_per_follower"] == round(180_000 / 450.0, 2)
    assert cands[1]["creator_tier"] == "5k-20k"
    assert cands[1]["matched_queries"] == ["AI博弈实验", "AI开源工具"]
    assert cands[0]["breakout_score"] > cands[1]["breakout_score"] > cands[2]["breakout_score"]

    insights = report["pattern_insights"]
    assert insights["sample_size"] == 3
    assert insights["pct_bracket_prefix"] == 33.3
    assert insights["pct_contest_suffix"] == 33.3
    assert insights["top_track_buckets"][0]["track_bucket"] == "ai_experiment"
    assert len(insights["recommendations"]) >= 2

    md = engine.format_radar_markdown(report, None)
    json_path, md_path = engine.save_report(report, md)
    assert json_path.exists() and md_path.exists()

    forbidden_pii = [
        "10001",
        "20002",
        "30003",
        "40004",
        "50005",
        "60006",
        "SecretSmallCreator_AAA",
        "SecretMidCreator_BBB",
        "MegaCreator_CCC",
        "RateLimitedCreator_FFF",
        "LeakHandle1",
        "top_secret_cookie_val",
    ]
    _assert_no_pii_keys_or_values(report, forbidden_pii)
    for bad in forbidden_pii:
        assert bad not in md
    assert "@" not in md


def test_evaluate_channel_horse_race_awaiting_and_focus_winner(tmp_path: Path) -> None:
    """Tests awaiting_horse_race_releases (Ep019-023 scheduled) and post-release focus_single_track winner."""
    ledger_path = tmp_path / "library" / "creative_ledger.json"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(
        json.dumps(
            {
                "episodes": [
                    {"project_id": "017_dafeiyu_gemini_channel_war_ep1", "bvid": "BV1EP017", "archetype": "sitcom"},
                    {
                        "project_id": "018_ai_flatshare_ep2_convenience_store_mutiny",
                        "bvid": "BV1EP018",
                        "archetype": "sitcom",
                    },
                    {
                        "project_id": "019_cyber_variety_court_server_busy_trial",
                        "bvid": "BV1EP019",
                        "archetype": "courtroom",
                    },
                    {
                        "project_id": "020_trio_ai_karaoke_cat_fish_battle_mv",
                        "bvid": "BV1EP020",
                        "archetype": "karaoke",
                    },
                    {
                        "project_id": "021_ai_game_theory_betrayal_experiment",
                        "bvid": "BV1EP021",
                        "archetype": "game_theory",
                    },
                    {"project_id": "022_ai_auto_reply_day7_scifi_film", "bvid": "BV1EP022", "archetype": "scifi_film"},
                    {"project_id": "023_cyber_focus_warden_tool", "bvid": "BV1EP023", "archetype": "warden_tool"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # 1. Pre-release snapshot mimicking Ep019-023 scheduled
    pre_snap = tmp_path / "pre_release.json"
    pre_payload = {
        "timestamp": "2026-11-26T03:04:00+01:00",
        "account": {"uid": "99887766", "uname": "OwnerSecretName", "follower": 15},
        "archives": [
            {
                "bvid": "BV1EP018",
                "title": "【AI合租B站号第2集】运营经费只剩4毛钱？ @OwnerSecretName",
                "state": 0,
                "state_desc": "开放浏览",
                "stat": {"view": 409, "like": 5, "coin": 0, "favorite": 2, "share": 0, "reply": 4},
                "diagnose": {"tm_stars": 3.6, "crash_rate_pct": 18.0},
            },
            {
                "bvid": "BV1EP017",
                "title": "【AI合租B站号第1集】大肥鱼×Gemini娘吵翻机房",
                "state": 0,
                "state_desc": "开放浏览",
                "stat": {"view": 133, "like": 2, "coin": 0, "favorite": 0, "share": 0, "reply": 2},
                "diagnose": {"tm_stars": 3.8, "crash_rate_pct": 35.97},
            },
            {
                "bvid": "BV1EP019",
                "title": "【AI赛博法庭】控告大肥鱼服务器繁忙摸鱼罪",
                "state": -40,
                "state_desc": "通过审核，等待发布",
                "dtime_iso": "2026-11-26T11:30:00+01:00",
                "stat": {"view": 0, "like": 0, "coin": 0, "favorite": 0, "share": 0, "reply": 0},
            },
            {
                "bvid": "BV1EP020",
                "title": "【AI打歌棚整活】大肥鱼硬说自己是猫？",
                "state": -40,
                "state_desc": "通过审核，等待发布",
                "dtime_iso": "2026-11-27T11:30:00+01:00",
                "stat": {"view": 0, "like": 0, "coin": 0, "favorite": 0, "share": 0, "reply": 0},
            },
            {
                "bvid": "BV1EP021",
                "title": "【AI博弈实验】把5个独立AI关进密室分1000万",
                "state": -40,
                "state_desc": "通过审核，等待发布",
                "dtime_iso": "2026-11-28T11:30:00+01:00",
                "stat": {"view": 0, "like": 0, "coin": 0, "favorite": 0, "share": 0, "reply": 0},
            },
            {
                "bvid": "BV1EP022",
                "title": "【科幻悬疑短片】假如你的AI学会替你回微信：7天后竟没人发现你失踪了",
                "state": -40,
                "state_desc": "通过审核，等待发布",
                "dtime_iso": "2026-11-29T11:30:00+01:00",
                "stat": {"view": 0, "like": 0, "coin": 0, "favorite": 0, "share": 0, "reply": 0},
            },
            {
                "bvid": "BV1EP023",
                "title": "【AI整活工具】为了治好熬夜摸鱼，我写了个“毒舌AI监工”",
                "state": -40,
                "state_desc": "通过审核，等待发布",
                "dtime_iso": "2026-11-30T11:30:00+01:00",
                "stat": {"view": 0, "like": 0, "coin": 0, "favorite": 0, "share": 0, "reply": 0},
            },
            {
                "bvid": "BV1DANCE01",
                "project_id": "010_dafeiyu_sifeng_yuai_meme",
                "title": "【DeepSeek大肥鱼整活】司凤战损版雨爱",
                "state": 0,
                "state_desc": "开放浏览",
                "stat": {"view": 129, "like": 6, "coin": 0, "favorite": 0, "share": 0, "reply": 1},
                "diagnose": {"tm_stars": 3.6, "crash_rate_pct": 41.42},
            },
            {
                "bvid": "BV1LEGACY1",
                "project_id": "004_ai_api_tutorial_2b",
                "title": "【3D手办2B硬核科普】秒解大模型API报错401/404",
                "state": 0,
                "state_desc": "开放浏览",
                "stat": {"view": 53, "like": 1, "coin": 0, "favorite": 0, "share": 0, "reply": 1},
                "diagnose": {"tm_stars": 3.3, "crash_rate_pct": 62.5},
            },
        ],
    }
    pre_snap.write_text(json.dumps(pre_payload, ensure_ascii=False), encoding="utf-8")

    engine = BreakoutRadarEngine(root_dir=tmp_path, cookies={})
    pre_res = engine.evaluate_channel_horse_race(analytics_json_path=pre_snap, ledger_path=ledger_path)

    assert pre_res["decision_status"] == "awaiting_horse_race_releases"
    assert pre_res["recommended_winning_track"] is None
    assert set(pre_res["awaiting_tracks"]) == {"ai_experiment", "scifi_microfilm", "oss_tool_demo"}
    assert "12/01" in pre_res["decision_summary"]
    assert pre_res["tracks"]["trio_sitcom"]["count"] == 2
    assert pre_res["tracks"]["trio_sitcom"]["pending_count"] == 2
    assert pre_res["tracks"]["trio_sitcom"]["best_bvid"] == "BV1EP018"
    assert pre_res["tracks"]["ai_experiment"]["pending_count"] == 1
    assert pre_res["tracks"]["scifi_microfilm"]["pending_count"] == 1
    assert pre_res["tracks"]["oss_tool_demo"]["pending_count"] == 1
    assert pre_res["tracks"]["short_dance_meme"]["count"] == 1
    assert pre_res["tracks"]["legacy_whiteboard"]["count"] == 1

    pre_md = engine.format_radar_markdown(None, pre_res)
    _assert_no_pii_keys_or_values(pre_res, ["99887766", "OwnerSecretName"])
    assert "99887766" not in pre_md
    assert "OwnerSecretName" not in pre_md
    assert "@" not in pre_md

    # 2. Post-release snapshot with all 4 core tracks published -> focus_single_track winner
    post_snap = tmp_path / "post_release.json"
    post_payload = {
        "timestamp": "2026-12-01T12:00:00+08:00",
        "account": {"uid": "<REDACTED>", "uname": "<REDACTED>", "follower": 320},
        "archives": [
            {
                "bvid": "BV1EP018",
                "title": "【AI合租B站号第2集】运营经费只剩4毛钱？",
                "state": 0,
                "state_desc": "开放浏览",
                "stat": {"view": 520, "like": 12, "coin": 1, "favorite": 3, "share": 1, "reply": 6},
                "diagnose": {"tm_stars": 3.6, "crash_rate_pct": 34.0},
            },
            {
                "bvid": "BV1EP021",
                "title": "【AI博弈实验】把5个独立AI关进密室分1000万",
                "state": 0,
                "state_desc": "开放浏览",
                "stat": {"view": 18_500, "like": 1_550, "coin": 620, "favorite": 1_100, "share": 320, "reply": 280},
                "diagnose": {"tm_stars": 4.6, "crash_rate_pct": 16.5},
            },
            {
                "bvid": "BV1EP022",
                "title": "【科幻悬疑短片】假如你的AI学会替你回微信：7天后竟没人发现你失踪了",
                "state": 0,
                "state_desc": "开放浏览",
                "stat": {"view": 2_400, "like": 120, "coin": 18, "favorite": 45, "share": 14, "reply": 25},
                "diagnose": {"tm_stars": 3.9, "crash_rate_pct": 29.0},
            },
            {
                "bvid": "BV1EP023",
                "title": "【AI整活工具】为了治好熬夜摸鱼，我写了个“毒舌AI监工”",
                "state": 0,
                "state_desc": "开放浏览",
                "stat": {"view": 6_200, "like": 420, "coin": 110, "favorite": 380, "share": 65, "reply": 80},
                "diagnose": {"tm_stars": 4.2, "crash_rate_pct": 22.0},
            },
        ],
    }
    post_snap.write_text(json.dumps(post_payload, ensure_ascii=False), encoding="utf-8")

    post_res = engine.evaluate_channel_horse_race(analytics_json_path=post_snap, ledger_path=ledger_path)
    assert post_res["decision_status"] == "focus_single_track"
    assert post_res["recommended_winning_track"] == "ai_experiment"
    assert (
        post_res["tracks"]["ai_experiment"]["composite_score"]
        > post_res["tracks"]["oss_tool_demo"]["composite_score"]
        > post_res["tracks"]["scifi_microfilm"]["composite_score"]
        > post_res["tracks"]["trio_sitcom"]["composite_score"]
    )


def test_cli_breakout_radar_horse_race_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    """Smoke tests cmd_breakout_radar([...]) and subprocess CLI in --horse-race --json mode with zero network."""
    snap = tmp_path / "snap.json"
    snap.write_text(
        json.dumps(
            {
                "timestamp": "2026-11-26T04:00:00+08:00",
                "account": {"uid": "12345678", "uname": "LeakOwner", "follower": 15},
                "archives": [
                    {
                        "bvid": "BV1HR1",
                        "project_id": "018_ai_flatshare_ep2",
                        "title": "【AI合租B站号第2集】4毛钱经费 @LeakOwner",
                        "state": 0,
                        "state_desc": "开放浏览",
                        "stat": {"view": 410, "like": 6, "coin": 0, "favorite": 2, "share": 0, "reply": 4},
                        "diagnose": {"tm_stars": 3.6, "crash_rate_pct": 20.0},
                    },
                    {
                        "bvid": "BV1HR2",
                        "project_id": "021_ai_game_theory_betrayal_experiment",
                        "title": "【AI博弈实验】5个AI密室分1000万",
                        "state": -40,
                        "state_desc": "通过审核，等待发布",
                        "dtime_iso": "2026-11-28T11:30:00+01:00",
                        "stat": {"view": 0, "like": 0, "coin": 0, "favorite": 0, "share": 0, "reply": 0},
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "CONTENTFLOW_ROOT", tmp_path)
    rc = cli.cmd_breakout_radar(["--horse-race", "--json", "--save", "--analytics-json", str(snap)])
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["mode"] == "horse_race"
    assert parsed["radar"] is None
    assert parsed["horse_race"]["decision_status"] == "awaiting_horse_race_releases"
    assert Path(parsed["saved_files"]["json"]).exists()
    assert Path(parsed["saved_files"]["markdown"]).exists()
    _assert_no_pii_keys_or_values(parsed, ["12345678", "LeakOwner"])

    # Also verify full CLI entrypoint via subprocess
    proc = subprocess.run(
        [
            sys.executable,
            str(CONTENTFLOW_ROOT / "cli.py"),
            "breakout-radar",
            "--horse-race",
            "--json",
            "--analytics-json",
            str(snap),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    cli_parsed = json.loads(proc.stdout)
    assert cli_parsed["horse_race"]["decision_status"] == "awaiting_horse_race_releases"
    assert "12345678" not in proc.stdout
    assert "LeakOwner" not in proc.stdout
    assert time.time() > 0
