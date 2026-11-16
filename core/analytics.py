"""Bilibili Account Analytics, Archive Performance Tracker & Viral Track Radar.

Provides autonomous data feedback loops for the ContentFlow Studio:
1. Real-time account & follower telemetry (`/x/web-interface/nav/stat`, `/x/relation/stat`)
2. Creator Center archive status & per-video engagement metrics (`/x/web/archives`)
3. Real-time Bilibili Popular & Partition Ranking radar (`popular`, `douga`, `tech`, `dance`)
4. Autonomous Track & Topic Strategist recommendations (including AI-self-operating meta-narratives,
   DeepSeek Whale-Chan anime dance tracks, and 3D figure hard-tech tutorials).
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from core.auth_vault import STANDARD_USER_AGENT, AuthVault

BILIBILI_NAV_STAT_URL = "https://api.bilibili.com/x/web-interface/nav/stat"
BILIBILI_RELATION_STAT_URL = "https://api.bilibili.com/x/relation/stat"
BILIBILI_MEMBER_ARCHIVES_URL = "https://member.bilibili.com/x/web/archives"
BILIBILI_ARCHIVE_DIAGNOSE_URL = "https://member.bilibili.com/x/web/data/archive_diagnose/compare"
BILIBILI_REPLY_LIST_URL = "https://api.bilibili.com/x/v2/reply"
BILIBILI_VIEW_URL = "https://api.bilibili.com/x/web-interface/view"
BILIBILI_POPULAR_URL = "https://api.bilibili.com/x/web-interface/popular"
BILIBILI_RANKING_V2_URL = "https://api.bilibili.com/x/web-interface/ranking/v2"

PARTITION_RIDS: Dict[str, int] = {
    "douga": 1,  # 动画 / MMD·3D / 手书
    "tech": 188,  # 科技 / 计算机技术 / 人工智能
    "dance": 129,  # 舞蹈 / 宅舞
}


class BilibiliAnalytics:
    """Autonomous Bilibili account telemetry, archive performance, and trending track radar."""

    def __init__(
        self,
        vault: Optional[AuthVault] = None,
        cookies: Optional[Dict[str, str]] = None,
        session: Optional[requests.Session] = None,
        analytics_dir: Optional[Path] = None,
    ) -> None:
        self.vault = vault or AuthVault()
        self.cookies = dict(cookies) if cookies is not None else self.vault.load_bilibili_cookies()
        self.session = session or requests.Session()
        self.analytics_dir = Path(analytics_dir) if analytics_dir is not None else (self.vault.vault_dir / "analytics")

    def _headers(self, referer: str = "https://member.bilibili.com/platform/home") -> Dict[str, str]:
        return {
            "User-Agent": STANDARD_USER_AGENT,
            "Referer": referer,
            "Accept": "application/json, text/plain, */*",
        }

    def fetch_account_stats(self) -> Dict[str, Any]:
        """Fetches follower, following, and profile status for the authenticated Bilibili account."""
        uid = str(self.cookies.get("DedeUserID", "")).strip()
        status_info = self.vault.get_platform_status("bilibili", verify_online=True)

        follower = 0
        following = 0
        dynamic_count = 0

        try:
            r_nav = self.session.get(
                BILIBILI_NAV_STAT_URL,
                cookies=self.cookies,
                headers=self._headers(),
                timeout=10,
            )
            if r_nav.status_code == 200:
                d_nav = r_nav.json().get("data") or {}
                follower = int(d_nav.get("follower") or 0)
                following = int(d_nav.get("following") or 0)
                dynamic_count = int(d_nav.get("dynamic_count") or 0)
        except Exception:
            pass

        if uid and follower == 0:
            try:
                r_rel = self.session.get(
                    BILIBILI_RELATION_STAT_URL,
                    params={"vmid": uid},
                    cookies=self.cookies,
                    headers=self._headers(),
                    timeout=10,
                )
                if r_rel.status_code == 200:
                    d_rel = r_rel.json().get("data") or {}
                    follower = int(d_rel.get("follower") or follower)
                    following = int(d_rel.get("following") or following)
            except Exception:
                pass

        return {
            "uid": uid or status_info.get("mid"),
            "uname": status_info.get("uname"),
            "level": status_info.get("level"),
            "logged_in": status_info.get("logged_in", False),
            "follower": follower,
            "following": following,
            "dynamic_count": dynamic_count,
        }

    def fetch_creator_archives(
        self,
        status: str = "is_pubing,pubed,not_pubed",
        pn: int = 1,
        ps: int = 30,
    ) -> Dict[str, Any]:
        """Fetches submitted video archives and their real-time stats from Bilibili Creator Center."""
        resp = self.session.get(
            BILIBILI_MEMBER_ARCHIVES_URL,
            params={"status": status, "pn": str(pn), "ps": str(ps)},
            cookies=self.cookies,
            headers=self._headers(),
            timeout=15,
        )
        resp.raise_for_status()
        payload = resp.json()
        data = payload.get("data") or {}
        arc_classes = data.get("class") or {"pubed": 0, "is_pubing": 0, "not_pubed": 0}
        raw_arcs = data.get("arc_audits") or []

        archives: List[Dict[str, Any]] = []
        totals = {
            "view": 0,
            "like": 0,
            "coin": 0,
            "favorite": 0,
            "danmaku": 0,
            "reply": 0,
            "share": 0,
        }

        for item in raw_arcs:
            arc = item.get("Archive") or {}
            stat = item.get("stat") or {}
            bvid = item.get("bvid") or arc.get("bvid") or ""
            aid = arc.get("aid")

            v_cnt = int(stat.get("view") or 0)
            l_cnt = int(stat.get("like") or 0)
            c_cnt = int(stat.get("coin") or 0)
            f_cnt = int(stat.get("favorite") or 0)
            d_cnt = int(stat.get("danmaku") or 0)
            r_cnt = int(stat.get("reply") or 0)
            s_cnt = int(stat.get("share") or 0)

            totals["view"] += v_cnt
            totals["like"] += l_cnt
            totals["coin"] += c_cnt
            totals["favorite"] += f_cnt
            totals["danmaku"] += d_cnt
            totals["reply"] += r_cnt
            totals["share"] += s_cnt

            weighted_score = l_cnt + c_cnt * 3 + f_cnt * 3 + r_cnt * 2 + d_cnt * 2 + s_cnt * 4
            engagement_rate = round(weighted_score / max(v_cnt, 1), 4)

            ptime = int(arc.get("ptime") or 0)
            dtime = int(arc.get("dtime") or 0)
            diagnose = self.fetch_archive_diagnose(bvid) if (bvid and int(arc.get("state") or 0) >= 0) else {}
            recent_comments = self.fetch_archive_comments(int(aid)) if (aid and r_cnt > 0) else []

            archives.append(
                {
                    "bvid": bvid,
                    "aid": aid,
                    "title": arc.get("title", ""),
                    "tid": arc.get("typeid"),
                    "state": arc.get("state"),
                    "state_desc": arc.get("state_desc", ""),
                    "reject_reason": arc.get("reject_reason", ""),
                    "ptime": ptime,
                    "ptime_iso": (
                        dt.datetime.fromtimestamp(ptime, tz=dt.timezone.utc).astimezone().isoformat()
                        if ptime > 0
                        else None
                    ),
                    "dtime": dtime if dtime > 0 else None,
                    "dtime_iso": (
                        dt.datetime.fromtimestamp(dtime, tz=dt.timezone.utc).astimezone().isoformat()
                        if dtime > 0
                        else None
                    ),
                    "stat": {
                        "view": v_cnt,
                        "like": l_cnt,
                        "coin": c_cnt,
                        "favorite": f_cnt,
                        "danmaku": d_cnt,
                        "reply": r_cnt,
                        "share": s_cnt,
                    },
                    "weighted_engagement_rate": engagement_rate,
                    "diagnose": diagnose,
                    "recent_comments": recent_comments,
                }
            )

        return {
            "counts": {
                "pubed": int(arc_classes.get("pubed") or 0),
                "is_pubing": int(arc_classes.get("is_pubing") or 0),
                "not_pubed": int(arc_classes.get("not_pubed") or 0),
                "total": len(archives),
            },
            "totals": totals,
            "archives": archives,
        }

    def fetch_archive_diagnose(self, bvid: str) -> Dict[str, Any]:
        """Fetches Bilibili Creator Center official play analysis & CTR diagnostic (`archive_diagnose/compare`)."""
        if not bvid:
            return {}
        try:
            resp = self.session.get(
                BILIBILI_ARCHIVE_DIAGNOSE_URL,
                params={"bvid": str(bvid), "size": "10"},
                cookies=self.cookies,
                headers=self._headers("https://member.bilibili.com/platform/data-up/video/playAnalysis"),
                timeout=10,
            )
            if resp.status_code != 200:
                return {}
            data_obj = resp.json().get("data") or {}
            arc_list = data_obj.get("list") or []
            item = next((x for x in arc_list if x.get("bvid") == bvid), arc_list[0] if arc_list else {})
            d = item.get("stat") or data_obj.get("current_arc") or {}
            if not d:
                return {}
            tm_star_raw = int(d.get("tm_star") or 0)
            tm_stars = round(tm_star_raw / 10.0, 1)
            if tm_star_raw == 0:
                tm_advice = "计算中/待更新"
            elif tm_star_raw <= 25:
                tm_advice = f"封标有优化空间 ({tm_stars:g}星)"
            elif tm_star_raw <= 35:
                tm_advice = f"封标表现良好 ({tm_stars:g}星)"
            else:
                tm_advice = f"封标表现优秀 ({tm_stars:g}星)"
            return {
                "traffic_status": "受限" if (d.get("limit_state") or item.get("is_only_self")) else "正常",
                "tm_star_raw": tm_star_raw,
                "tm_stars": tm_stars,
                "tm_pass_rate_pct": round(int(d.get("tm_pass_rate") or d.get("tm_viewer_pass_rate") or 0) / 100.0, 2),
                "cover_title_advice": tm_advice,
                "crash_rate_pct": round(int(d.get("crash_rate") or 0) / 100.0, 2),
                "crash_p50_pct": round(int(d.get("crash_p50") or 0) / 100.0, 2),
                "full_play_ratio_pct": round(int(d.get("full_play_ratio") or 0) / 100.0, 2),
                "interact_rate_pct": round(int(d.get("interact_rate") or 0) / 100.0, 2),
                "interact_p50_pct": round(int(d.get("interact_p50") or 0) / 100.0, 2),
                "play_trans_fan_p50_pct": round(int(d.get("play_trans_fan_p50") or 0) / 100.0, 2),
            }
        except Exception:
            return {}

    def fetch_archive_comments(self, aid: int, ps: int = 10) -> List[Dict[str, Any]]:
        """Fetches recent comments and sub-replies on an archive (`/x/v2/reply`)."""
        if not aid:
            return []
        comments: List[Dict[str, Any]] = []
        try:
            resp = self.session.get(
                BILIBILI_REPLY_LIST_URL,
                params={"type": "1", "oid": str(int(aid)), "pn": "1", "ps": str(ps), "sort": "2"},
                cookies=self.cookies,
                headers=self._headers(f"https://www.bilibili.com/video/av{int(aid)}"),
                timeout=10,
            )
            if resp.status_code != 200:
                return []
            replies = ((resp.json().get("data") or {}).get("replies")) or []
            for r in replies:
                comments.append(
                    {
                        "rpid": r.get("rpid"),
                        "uname": (r.get("member") or {}).get("uname", ""),
                        "message": (r.get("content") or {}).get("message", ""),
                        "like": r.get("like", 0),
                        "is_sub": False,
                    }
                )
                for sr in r.get("replies") or []:
                    comments.append(
                        {
                            "rpid": sr.get("rpid"),
                            "root_rpid": r.get("rpid"),
                            "uname": (sr.get("member") or {}).get("uname", ""),
                            "message": (sr.get("content") or {}).get("message", ""),
                            "like": sr.get("like", 0),
                            "is_sub": True,
                        }
                    )
        except Exception:
            return []
        return comments

    def fetch_trending_radar(self, limit: int = 5) -> Dict[str, List[Dict[str, Any]]]:
        """Scans Bilibili Popular and Partition Rankings (Anime/MMD, Tech/AI, Dance)."""
        radar: Dict[str, List[Dict[str, Any]]] = {}

        # 1. All-station Popular
        try:
            r_pop = self.session.get(
                BILIBILI_POPULAR_URL,
                params={"ps": str(limit), "pn": "1"},
                cookies=self.cookies,
                headers=self._headers("https://www.bilibili.com"),
                timeout=10,
            )
            if r_pop.status_code == 200:
                raw_list = (r_pop.json().get("data") or {}).get("list") or []
                radar["popular"] = [self._compact_rank_item(x) for x in raw_list[:limit]]
        except Exception:
            radar["popular"] = []

        # 2. Key studio partitions
        for name, rid in PARTITION_RIDS.items():
            try:
                r_part = self.session.get(
                    BILIBILI_RANKING_V2_URL,
                    params={"rid": str(rid), "type": "all"},
                    cookies=self.cookies,
                    headers=self._headers("https://www.bilibili.com"),
                    timeout=10,
                )
                if r_part.status_code == 200:
                    raw_list = (r_part.json().get("data") or {}).get("list") or []
                    radar[name] = [self._compact_rank_item(x) for x in raw_list[:limit]]
                else:
                    radar[name] = []
            except Exception:
                radar[name] = []

        return radar

    @staticmethod
    def _compact_rank_item(item: Dict[str, Any]) -> Dict[str, Any]:
        stat = item.get("stat") or {}
        owner = item.get("owner") or {}
        return {
            "bvid": item.get("bvid"),
            "title": item.get("title"),
            "tname": item.get("tname"),
            "tid": item.get("tid"),
            "author": owner.get("name"),
            "duration": item.get("duration"),
            "view": stat.get("view", 0),
            "like": stat.get("like", 0),
            "coin": stat.get("coin", 0),
            "favorite": stat.get("favorite", 0),
            "danmaku": stat.get("danmaku", 0),
        }

    @staticmethod
    def build_autonomous_track_strategy(
        archives: Optional[List[Dict[str, Any]]] = None,
        radar: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> List[Dict[str, Any]]:
        """Synthesizes data-driven track diagnostics without hardcoding repetitive episode topics."""
        arc_list = archives or []
        radar_map = radar or {}

        ent_views, ent_likes, lec_views, lec_likes = 0, 0, 0, 0
        for a in arc_list:
            stat = a.get("stat") or {}
            v = int(stat.get("view") or 0)
            lk = int(stat.get("like") or 0)
            tid = int(a.get("tid") or 0)
            if tid in (20, 25, 119, 129, 1):
                ent_views += v
                ent_likes += lk
            else:
                lec_views += v
                lec_likes += lk

        ent_rate = (ent_likes / float(ent_views)) if ent_views > 0 else 0.0
        lec_rate = (lec_likes / float(lec_views)) if lec_views > 0 else 0.0

        def _top_radar_sample(key: str) -> str:
            items = radar_map.get(key) or []
            if not items:
                return "请运行 cli.py benchmark --online 获取实时榜首爆款"
            top = items[0]
            return f"榜首参照「{str(top.get('title') or '')[:24]}」({top.get('bvid', '')}, 播放 {int(top.get('view') or 0):,})"

        return [
            {
                "track_id": "track_1_viral_meme_reversal_dance",
                "name": "【主攻高留存赛道】热梗反差剧情 × 60FPS 跨形象热舞整活（每期独立新创）",
                "target_tid": 20,
                "target_partition": "舞蹈 -> 宅舞",
                "viral_hook": (
                    f"实测数据：娱乐向累计 {ent_views} 播放 / 点赞转化 {ent_rate:.1%}。"
                    f"每期必须先经 cli.py benchmark --online 拆解当下榜首（如 {_top_radar_sample('dance')}），"
                    "再结合 creative_ledger.json 防重，独立构思全新热梗反转 + Beat Punch-In 多景别卡点 + vivid_scene 高明度封面。"
                ),
                "why_it_works": (
                    "B站娱乐冷启动高度依赖前 0.5 秒明艳封面点击与前 3 秒强反差动作抓手；"
                    "严禁复用旧模板或静态站桩，必须每期保持题材新鲜度与高密度节奏切换。"
                ),
            },
            {
                "track_id": "track_2_agent_meta_and_viewer_cocreation",
                "name": "【互动共创赛道】AI 自主实验整活 × 评论区点单兑现剧场",
                "target_tid": 119,
                "target_partition": "鬼畜 / 整活 -> 宅舞跨界",
                "viral_hook": (
                    f"结合实时鬼畜热榜趋势（{_top_radar_sample('kichiku')}）与高赞评论点单，"
                    "以 12-20 秒高能剧情反转兑现观众脑洞；点单交作业仅在原评论下单点礼貌回复一次，绝不在简介/置顶群发艾特。"
                ),
                "why_it_works": (
                    "高质量单点宠粉与社会情绪热梗共鸣可显著拉升完播率与互动率，打破纯工具账号冷启动壁垒。"
                ),
            },
            {
                "track_id": "track_3_visual_storytelling_tech_upgrade",
                "name": "【长尾升级赛道】动态情景剧化硬核拆解（告别静态白板 PPT）",
                "target_tid": 231,
                "target_partition": "科技 -> 计算机技术",
                "viral_hook": (
                    f"实测警示：传统静态白板科普累计 {lec_views} 播放（点赞率 {lec_rate:.1%}），3秒划走率偏高。"
                    f"后续仅在配合真机运行画面、动态案例实拍或对比基准（{_top_radar_sample('tech')}）时立项，并同步升级生动视觉叙事。"
                ),
                "why_it_works": (
                    "避免在冷启动阶段陷入高跳出率同质化课件流水线，将工程干货包装为高信息密度的动态视觉作品。"
                ),
            },
        ]

    @staticmethod
    def build_optimization_directives(
        archives: List[Dict[str, Any]],
        account_uname: str = "",
    ) -> List[Dict[str, Any]]:
        """Synthesizes concrete studio optimization directives from Bilibili crowd telemetry & viewer requests."""
        directives: List[Dict[str, Any]] = []
        req_keywords = ("想看", "有没有", "翻唱", "求", "下期", "整活", "雨爱")
        for arc in archives:
            bvid = str(arc.get("bvid") or "")
            title = str(arc.get("title") or "")
            diag = arc.get("diagnose") or {}
            crash = float(diag.get("crash_rate_pct") or 0.0)
            crash_p50 = float(diag.get("crash_p50_pct") or 27.35)
            tm_stars = float(diag.get("tm_stars") or 0.0)

            if crash > max(35.0, crash_p50 + 8.0):
                directives.append(
                    {
                        "priority": "P0",
                        "type": "hook_and_bgm_upgrade",
                        "bvid": bvid,
                        "title": title,
                        "crash_rate_pct": crash,
                        "peer_p50_pct": crash_p50,
                        "reason": f"3-5s 划走率 {crash:.1f}% 显著高于同类中位数 {crash_p50:.1f}%",
                        "action": "移除公式化开场白，前1秒切入高动势近景钩子，并用 EpisodeAssembler 启用鼓点近景切镜与侧链混音",
                    }
                )

            if 0.0 < tm_stars < 3.5:
                directives.append(
                    {
                        "priority": "P1",
                        "type": "cover_hero_contrast_upgrade",
                        "bvid": bvid,
                        "title": title,
                        "tm_stars": tm_stars,
                        "reason": f"B站官方封面标题评分 {tm_stars:g} 星 (< 3.5 星)",
                        "action": "运行 cli.py benchmark 检查封面暗部占比并切换 vivid_scene 高明度实景封面",
                    }
                )

            for cm in arc.get("recent_comments") or []:
                uname = str(cm.get("uname") or "").strip()
                msg = str(cm.get("message") or "").strip()
                if not msg or (account_uname and uname == account_uname):
                    continue
                if any(k in msg for k in req_keywords):
                    directives.append(
                        {
                            "priority": "P0",
                            "type": "viewer_request",
                            "bvid": bvid,
                            "requester": uname,
                            "message": msg,
                            "reason": f"评论区观众「{uname}」点菜需求：「{msg[:40]}」",
                            "action": "独立策划全新一集兑现点单，发布后仅在该条原评论下单点礼貌回复一次（严禁群发艾特）",
                        }
                    )

        return directives

    def generate_report(self, save_snapshot: bool = True) -> Dict[str, Any]:
        """Collects full account telemetry, archive stats, trending radar, and track strategy."""
        now_iso = dt.datetime.now(dt.timezone.utc).astimezone().isoformat()
        account = self.fetch_account_stats()
        archives_data = self.fetch_creator_archives()
        radar = self.fetch_trending_radar(limit=5)
        tracks = self.build_autonomous_track_strategy(
            archives=archives_data["archives"],
            radar=radar,
        )
        directives = self.build_optimization_directives(
            archives_data["archives"],
            account_uname=str(account.get("uname") or ""),
        )

        report: Dict[str, Any] = {
            "timestamp": now_iso,
            "account": account,
            "archives_summary": archives_data["counts"],
            "totals": archives_data["totals"],
            "archives": archives_data["archives"],
            "trending_radar": radar,
            "recommended_tracks": tracks,
            "optimization_directives": directives,
        }

        if save_snapshot:
            self.analytics_dir.mkdir(parents=True, exist_ok=True)
            json_path = self.analytics_dir / "bilibili_latest.json"
            json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

            md_path = self.analytics_dir / "bilibili_growth_report.md"
            md_path.write_text(self.format_markdown_report(report), encoding="utf-8")
            report["snapshot_json"] = str(json_path)
            report["snapshot_md"] = str(md_path)

        return report

    @staticmethod
    def format_markdown_report(report: Dict[str, Any]) -> str:
        acc = report["account"]
        counts = report["archives_summary"]
        totals = report["totals"]
        lines = [
            "# ContentFlow Bilibili Autonomous Growth & Analytics Report",
            "",
            f"- **Updated At**: `{report['timestamp']}`",
            f"- **Account**: `{acc.get('uname')}` (UID: `{acc.get('uid')}`, Lv.{acc.get('level')})",
            f"- **Followers / Following**: `{acc.get('follower')}` followers | `{acc.get('following')}` following",
            f"- **Archives**: `{counts['pubed']}` published | `{counts['is_pubing']}` auditing/scheduled | `{counts['not_pubed']}` rejected",
            f"- **Total Views**: `{totals['view']}` | **Likes**: `{totals['like']}` | **Coins**: `{totals['coin']}` | **Favorites**: `{totals['favorite']}` | **Danmaku**: `{totals['danmaku']}` | **Replies**: `{totals['reply']}`",
            "",
            "## 1. Submitted Video Archives",
        ]

        arcs = report.get("archives") or []
        if not arcs:
            lines.append("- *(No video archives submitted yet)*")
        else:
            for a in arcs:
                s = a["stat"]
                lines.append(
                    f"- **`{a['bvid'] or a['aid']}`** [{a['state_desc']}] {a['title']}\n"
                    f"  - Views: `{s['view']}` | Likes: `{s['like']}` | Coins: `{s['coin']}` | Favs: `{s['favorite']}` | Danmaku: `{s['danmaku']}` | Replies: `{s['reply']}`"
                )
                diag = a.get("diagnose") or {}
                if diag:
                    lines.append(
                        f"  - Official Diagnose: Traffic `{diag.get('traffic_status')}` | Cover/Title CTR: **`{diag.get('cover_title_advice')}`** | Peer Benchmarks (P50): 3s Bounce `{diag.get('crash_p50_pct')}%`, Interact `{diag.get('interact_p50_pct')}%`"
                    )
                for cm in (a.get("recent_comments") or [])[:5]:
                    prefix = "    ↳ [Sub-reply]" if cm.get("is_sub") else "    • [Comment]"
                    lines.append(f"{prefix} 「{cm.get('uname')}」: {cm.get('message')[:80]}")

        lines.extend(["", "## 2. Autonomous Viral Track Matrix"])
        for t in report.get("recommended_tracks") or []:
            lines.append(f"### {t['name']}")
            lines.append(f"- **Target Partition**: {t['target_partition']} (`tid={t['target_tid']}`)")
            lines.append(f"- **Viral Hook**: {t['viral_hook']}")
            lines.append(f"- **Why It Works**: {t['why_it_works']}")
            lines.append("")

        directives = report.get("optimization_directives") or []
        if directives:
            lines.extend(["## 3. Crowd-Telemetry & Comment Optimization Directives", ""])
            for d in directives:
                lines.append(
                    f"- **[{d.get('priority', 'P1')}] `{d.get('type')}`** ({d.get('bvid', '')}): {d.get('reason')} -> {d.get('action')}"
                )
            lines.append("")

        return "\n".join(lines) + "\n"
