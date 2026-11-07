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
    def build_autonomous_track_strategy() -> List[Dict[str, Any]]:
        """Synthesizes high-conversion Bilibili content tracks for autonomous studio iteration."""
        return [
            {
                "track_id": "track_1_ai_self_operating_meta",
                "name": "【整活/元叙事】我的 Gemini 接管了我的 B站账号自己发视频赚流量",
                "target_tid": 231,
                "target_partition": "科技 -> 计算机技术 / 人工智能",
                "viral_hook": (
                    "号主只负责扫码授权 B站 + 可灵会员，AI Agent 自己上网查 DeepSeek 鲸鱼娘设定、"
                    "自己重绘 2K 深海舞台、自己算帧率卡点、自己发视频并盯盘播放量！"
                ),
                "title_templates": [
                    "当我把B站账号和可灵会员交给AI：它连夜自己肝出了这条DeepSeek鲸鱼娘热舞？！",
                    "大家好，我是号主的AI：他让我自己找赛道把流量搞起来，这是我发的第一条视频",
                ],
                "why_it_works": (
                    "兼具『AI Agent 真实自主干活』的猎奇感与『高颜值二次元成片』的视觉留存，"
                    "极易引发评论区玩梗互动（弹幕/评论率翻倍），触发 B站跨区推流。"
                ),
            },
            {
                "track_id": "track_2_deepseek_dafeiyu_idol_dance",
                "name": "【顶流AI娘×洗脑神曲】DeepSeek 鲸鱼娘（蓝色大肥鱼）18s 满屏舞台热舞",
                "target_tid": 25,
                "target_partition": "动画 -> MMD·3D",
                "viral_hook": (
                    "100% 还原 B站正统『蓝色大肥鱼』设定（蓝渐变卷发+呆毛+下垂鲸鱼头鳍+喷水鲸鱼围裙+大鲸鱼尾巴），"
                    "搭配《Phone Number》洗脑副歌与 🤙 Call Me 手势杀，18秒黄金完播时长。"
                ),
                "title_templates": [
                    "【DeepSeek娘】当我的AI自己学会了整活：先给你们摇一段18秒蓝色大肥鱼Phone Number！",
                    "【DeepSeek鲸鱼娘】蓝色大肥鱼跳 Phone Number！深海全息舞台 60帧丝滑卡点",
                ],
                "why_it_works": (
                    "15-20秒竖屏高密度卡点视频完播率极高（常超 50%），同时命中 DeepSeek 技术热词与二次元 MMD 核心受众。"
                ),
            },
            {
                "track_id": "track_3_figure_hard_tech_tutorial",
                "name": "【二次元手办×硬核科普】3D 虚拟偶像学姐 120秒讲透 AI 核心架构",
                "target_tid": 231,
                "target_partition": "科技 -> 计算机技术",
                "viral_hook": (
                    "高颜值 3D 手办角色（能代/大肥鱼）+ 全息毛玻璃白板公式拆解，"
                    "把枯燥的 Transformer / QKV / Agent 原理变成赏心悦目的视觉大片。"
                ),
                "title_templates": [
                    "【硬核科普】能代学姐用全息白板 2分钟带你彻底看懂 Transformer 自注意力机制！",
                    "当二次元手办开始讲大模型底层源码：收藏率 20% 的硬核视觉课",
                ],
                "why_it_works": (
                    "B站科技区与知识区对『高收藏率』视频给流极其慷慨，1个收藏权重约等于4个赞，"
                    "适合作为账号长尾涨粉与技术口碑基石。"
                ),
            },
        ]

    def generate_report(self, save_snapshot: bool = True) -> Dict[str, Any]:
        """Collects full account telemetry, archive stats, trending radar, and track strategy."""
        now_iso = dt.datetime.now(dt.timezone.utc).astimezone().isoformat()
        account = self.fetch_account_stats()
        archives_data = self.fetch_creator_archives()
        radar = self.fetch_trending_radar(limit=5)
        tracks = self.build_autonomous_track_strategy()

        report: Dict[str, Any] = {
            "timestamp": now_iso,
            "account": account,
            "archives_summary": archives_data["counts"],
            "totals": archives_data["totals"],
            "archives": archives_data["archives"],
            "trending_radar": radar,
            "recommended_tracks": tracks,
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

        lines.extend(["", "## 2. Autonomous Viral Track Matrix"])
        for t in report.get("recommended_tracks") or []:
            lines.append(f"### {t['name']}")
            lines.append(f"- **Target Partition**: {t['target_partition']} (`tid={t['target_tid']}`)")
            lines.append(f"- **Viral Hook**: {t['viral_hook']}")
            lines.append(f"- **Why It Works**: {t['why_it_works']}")
            lines.append("")

        return "\n".join(lines) + "\n"
