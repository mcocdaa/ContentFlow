"""Social Matrix Publisher & Advisor Staging Engine for ContentFlow.

Supports Advisor Review mode (`--mode draft`), Scheduled mode (`--mode schedule`),
and Direct mode (`--mode direct`) across Bilibili, Douyin, Xiaohongshu, and
WeChat Official Account (`wechat_mp`).

Key features:
- Automatic discovery of project `.mp4` video (in `delivery/` or `output/`), cover image,
  and copywriting metadata (`delivery/bilibili.md`, `delivery/release.md`, `brief.json`).
- Automatic high-res cover frame extraction via `ffmpeg` (with Pillow fallback) when a
  dedicated cover image is missing.
- Native `BilibiliUploader` implementing Bilibili Creator Center cover upload
  (`/x/vu/web/cover/up`), UPOS preupload (`/preupload`), chunked UPOS binary streaming,
  and archive submission (`/x/vu/web/add/v3`) with >= 4h future `dtime` scheduling.
- Structured Advisor Review & Staging Package generation in
  `projects/<project>/delivery/staged_<platform>/publish_manifest.json` + `advisor_receipt.md`.
- `WeChatMPPublisher` integration with official WeChat MP Draft Box API (`cgi-bin/draft/add`).
"""

from __future__ import annotations

import base64
import datetime as dt
import io
import json
import math
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from PIL import Image, ImageDraw

from config.settings import PROJECTS_DIR
from core.auth_vault import STANDARD_USER_AGENT, SUPPORTED_PLATFORMS, AuthVault
from core.html_formatter import HTMLFormatter
from core.models import FactSheet

SAFETY_MODES: Tuple[str, ...] = ("draft", "schedule", "direct")

# Bilibili Partition (tid) Mapping
BILIBILI_TID_MAP: Dict[str, int] = {
    "计算机技术": 231,
    "科技综合": 231,
    "科学科普": 201,
    "社科·法律·心理": 124,
    "校园学习": 208,
    "野生技术协会": 122,
    "数码": 95,
    "软件应用": 230,
    "人工智能": 231,
    "宅舞": 20,
    "MMD·3D": 25,
    "手办·模玩": 210,
    "短片·手书": 47,
}
DEFAULT_BILIBILI_TID = 231

# High-frequency Official Bilibili Activity & Mission Mapping
BILIBILI_ACTIVITY_MISSIONS: Dict[str, Dict[str, Any]] = {
    "B站AI创造公开赛": {
        "topic_id": 1340873,
        "mission_id": 4071698,
        "topic_name": "B站AI创造公开赛",
    },
    "B站AI无限竞技场": {
        "topic_id": 1346854,
        "mission_id": 4070254,
        "topic_name": "B站AI无限竞技场",
    },
    "AI偶像才艺大赏": {
        "topic_id": 1345301,
        "mission_id": 4071944,
        "topic_name": "AI偶像才艺大赏",
    },
}

DEFAULT_CREDITS_FALLBACK = "📋 【借物表 (Credits) 与开源致谢】角色设定、动作数据、配音与算力管线详见项目开源文档，严格遵循相应开源与二创授权协议。"
DEFAULT_AIGC_COMPLIANCE_FALLBACK = "⚠️ 【AIGC 生成合成内容合规声明】本视频包含 AI 生成合成画面与语音（符合 GB 45438-2025 标识规范），仅供技术科普与非商业交流。"

BILIBILI_COVER_UP_URL = "https://member.bilibili.com/x/vu/web/cover/up"
BILIBILI_PREUPLOAD_URL = "https://member.bilibili.com/preupload"
BILIBILI_ADD_V3_URL = "https://member.bilibili.com/x/vu/web/add/v3"
BILIBILI_EDIT_ARCHIVE_URL = "https://member.bilibili.com/x/vu/web/edit"
BILIBILI_ARCHIVE_VIEW_URL = "https://member.bilibili.com/x/vupre/web/archive/view"
BILIBILI_TOPIC_SEARCH_URL = "https://member.bilibili.com/x/vupre/web/topic/search"
BILIBILI_REPLY_ADD_URL = "https://api.bilibili.com/x/v2/reply/add"
BILIBILI_REPLY_TOP_URL = "https://api.bilibili.com/x/v2/reply/top"
BILIBILI_CREATOR_MANAGER_URL = "https://member.bilibili.com/platform/upload-manager/article"


def resolve_bilibili_tid(category_str: str) -> int:
    """Resolves Bilibili partition `tid` from a category string.

    Strips parenthetical fallback notes like `(或 ...)` / `（或 ...）` first,
    then picks the earliest matching keyword in the string by `.find()` index.
    """
    if not category_str:
        return DEFAULT_BILIBILI_TID

    primary_str = re.sub(r"[\(（]\s*或[^\)）]*[\)）]", "", category_str).strip()
    for target in (primary_str, category_str):
        matches: List[Tuple[int, int, int]] = []
        for key_name, mapped_tid in BILIBILI_TID_MAP.items():
            pos = target.find(key_name)
            if pos != -1:
                matches.append((pos, -len(key_name), mapped_tid))
        if matches:
            matches.sort()
            return matches[0][2]

    return DEFAULT_BILIBILI_TID


def ensure_compliance_and_credits_footer(description: str) -> str:
    """Appends concise Credits / AIGC compliance footer if missing from description."""
    desc = (description or "").rstrip()
    additions: List[str] = []
    if "【借物表" not in desc:
        additions.append(DEFAULT_CREDITS_FALLBACK)
    if "【AIGC" not in desc:
        additions.append(DEFAULT_AIGC_COMPLIANCE_FALLBACK)
    if additions:
        sep = "\n\n" if desc else ""
        desc = f"{desc}{sep}" + "\n".join(additions)
    return desc


# Minimum Bilibili scheduled publish lead time: 4 hours + 10 min safety buffer
BILIBILI_MIN_SCHEDULE_LEAD_SECONDS = 4 * 3600 + 600
BILIBILI_DEFAULT_SCHEDULE_LEAD_SECONDS = 6 * 3600

WECHAT_TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
WECHAT_MATERIAL_UPLOAD_URL = "https://api.weixin.qq.com/cgi-bin/material/add_material"
WECHAT_DRAFT_ADD_URL = "https://api.weixin.qq.com/cgi-bin/draft/add"


def compute_bilibili_dtime(schedule_at: Optional[str] = None, now_ts: Optional[int] = None) -> int:
    """Computes a valid Bilibili scheduled publish timestamp (`dtime`) at least 4h10m in the future.

    Accepts:
      - None: defaults to now + 6 hours
      - Unix epoch seconds string (e.g. "1794000000")
      - "+Nh" / "+Nm" relative offset (e.g. "+5h")
      - "HH:MM" 24-hour time (rolls to next day if < now + 4h10m)
      - ISO datetime string "YYYY-MM-DDTHH:MM..." or "YYYY-MM-DD HH:MM"
    """
    base_now = int(now_ts if now_ts is not None else time.time())
    min_dtime = base_now + BILIBILI_MIN_SCHEDULE_LEAD_SECONDS

    if not schedule_at:
        return base_now + BILIBILI_DEFAULT_SCHEDULE_LEAD_SECONDS

    raw = schedule_at.strip()
    if raw.isdigit():
        return max(int(raw), min_dtime)

    m_rel = re.match(r"^\+(\d+)\s*([hmHM])$", raw)
    if m_rel:
        val = int(m_rel.group(1))
        unit = m_rel.group(2).lower()
        offset = val * 3600 if unit == "h" else val * 60
        return max(base_now + offset, min_dtime)

    m_hhmm = re.match(r"^(\d{1,2}):(\d{2})$", raw)
    if m_hhmm:
        hh, mm = int(m_hhmm.group(1)), int(m_hhmm.group(2))
        local_now = dt.datetime.fromtimestamp(base_now)
        candidate_dt = local_now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        candidate_ts = int(candidate_dt.timestamp())
        while candidate_ts < min_dtime:
            candidate_ts += 86400
        return candidate_ts

    try:
        parsed_dt = dt.datetime.fromisoformat(raw)
        return max(int(parsed_dt.timestamp()), min_dtime)
    except ValueError:
        return base_now + BILIBILI_DEFAULT_SCHEDULE_LEAD_SECONDS


class BilibiliUploader:
    """Native Bilibili Creator Center uploader (Cover Base64 + UPOS Chunked Video + add/v3)."""

    def __init__(
        self,
        vault: Optional[AuthVault] = None,
        cookies: Optional[Dict[str, str]] = None,
        session: Optional[requests.Session] = None,
        upcdn: str = "bda2",
    ) -> None:
        self.vault = vault or AuthVault()
        if cookies is not None:
            nested = cookies.get("cookies")
            raw_c: Dict[str, Any] = nested if isinstance(nested, dict) else dict(cookies)
            self.cookies = {
                str(k): str(v)
                for k, v in raw_c.items()
                if isinstance(v, (str, int, float)) and k not in ("updated_at", "profile", "refresh_token")
            }
        else:
            self.cookies = self.vault.load_bilibili_cookies()
        self.session = session or requests.Session()
        self.upcdn = upcdn

    @property
    def bili_jct(self) -> str:
        return str(self.cookies.get("bili_jct", "")).strip()

    @property
    def is_authenticated(self) -> bool:
        return bool(self.cookies.get("SESSDATA") and self.bili_jct)

    def _web_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": STANDARD_USER_AGENT,
            "Referer": "https://member.bilibili.com/platform/upload/video/frame",
            "Origin": "https://member.bilibili.com",
            "Accept": "application/json, text/plain, */*",
        }

    def upload_cover(self, cover_path: Path) -> str:
        """Uploads a cover image to Bilibili Creator Center (`POST /x/vu/web/cover/up`)."""
        if not self.is_authenticated:
            raise RuntimeError("Bilibili SESSDATA and bili_jct cookies are required for cover upload")

        cover_path = Path(cover_path)
        if not cover_path.exists():
            raise FileNotFoundError(f"Cover file not found: {cover_path}")

        with Image.open(cover_path) as im:
            rgb_im = im.convert("RGB")
            buf = io.BytesIO()
            rgb_im.save(buf, format="JPEG", quality=92)
            jpeg_bytes = buf.getvalue()

        data_uri = "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode("ascii")
        resp = self.session.post(
            BILIBILI_COVER_UP_URL,
            data={"cover": data_uri, "csrf": self.bili_jct},
            cookies=self.cookies,
            headers=self._web_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != 0 or "data" not in payload or "url" not in payload["data"]:
            raise RuntimeError(f"Bilibili cover upload failed: {payload}")
        return str(payload["data"]["url"])

    def upload_video_upos(self, video_path: Path) -> Dict[str, Any]:
        """Preuploads and streams video chunks via Bilibili UPOS (`ugcupos/bup`)."""
        if not self.is_authenticated:
            raise RuntimeError("Bilibili SESSDATA and bili_jct cookies are required for video preupload")

        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        file_size = video_path.stat().st_size

        # 1. Preupload request
        pre_params = {
            "name": video_path.name,
            "size": str(file_size),
            "r": "upos",
            "profile": "ugcupos/bup",
            "ssl": "0",
            "version": "2.14.0",
            "build": "2140000",
            "upcdn": self.upcdn,
            "probe_version": "20221109",
        }
        pre_resp = self.session.get(
            BILIBILI_PREUPLOAD_URL,
            params=pre_params,
            cookies=self.cookies,
            headers=self._web_headers(),
            timeout=20,
        )
        pre_resp.raise_for_status()
        pre_data = pre_resp.json()
        if pre_data.get("OK") != 1 and "upos_uri" not in pre_data:
            raise RuntimeError(f"Bilibili UPOS preupload failed: {pre_data}")

        upos_uri = str(pre_data["upos_uri"])
        upos_path = upos_uri.removeprefix("upos://").lstrip("/")
        bili_filename = Path(upos_path).stem
        endpoint = str(pre_data["endpoint"])
        if endpoint.startswith("//"):
            base_endpoint = f"https:{endpoint}"
        elif not endpoint.startswith("http"):
            base_endpoint = f"https://{endpoint.lstrip('/')}"
        else:
            base_endpoint = endpoint
        upos_target_url = f"{base_endpoint.rstrip('/')}/{upos_path}"

        upos_auth = str(pre_data["auth"])
        chunk_size = int(pre_data.get("chunk_size") or 10 * 1024 * 1024)
        biz_id = int(pre_data.get("biz_id") or 0)

        upos_headers = {
            "User-Agent": STANDARD_USER_AGENT,
            "X-Upos-Auth": upos_auth,
            "Referer": "https://member.bilibili.com/",
            "Origin": "https://member.bilibili.com",
        }

        # 2. Initiate multipart UPOS upload_id
        init_url = (
            f"{upos_target_url}?uploads&output=json&profile=ugcupos%2Fbup"
            f"&filesize={file_size}&partsize={chunk_size}&biz_id={biz_id}"
        )
        init_resp = self.session.post(init_url, headers=upos_headers, timeout=20)
        init_resp.raise_for_status()
        init_data = init_resp.json()
        if "upload_id" not in init_data:
            raise RuntimeError(f"Bilibili UPOS upload_id init failed: {init_data}")
        upload_id = str(init_data["upload_id"])

        # 3. Upload chunks via PUT
        total_chunks = max(1, math.ceil(file_size / chunk_size))
        parts: List[Dict[str, Any]] = []

        with open(video_path, "rb") as f:
            for chunk_idx in range(total_chunks):
                chunk_bytes = f.read(chunk_size)
                cur_len = len(chunk_bytes)
                start_byte = chunk_idx * chunk_size
                end_byte = start_byte + cur_len

                put_params = {
                    "partNumber": str(chunk_idx + 1),
                    "uploadId": upload_id,
                    "chunk": str(chunk_idx),
                    "chunks": str(total_chunks),
                    "size": str(cur_len),
                    "start": str(start_byte),
                    "end": str(end_byte),
                    "total": str(file_size),
                }
                chunk_headers = {
                    **upos_headers,
                    "Content-Type": "application/octet-stream",
                    "Content-Length": str(cur_len),
                }
                put_resp = self.session.put(
                    upos_target_url,
                    params=put_params,
                    data=chunk_bytes,
                    headers=chunk_headers,
                    timeout=120,
                )
                put_resp.raise_for_status()
                parts.append({"partNumber": chunk_idx + 1, "eTag": "etag"})

        # 4. Finalize multipart UPOS upload
        fin_params = {
            "output": "json",
            "name": video_path.name,
            "profile": "ugcupos/bup",
            "uploadId": upload_id,
            "biz_id": str(biz_id),
        }
        fin_resp = self.session.post(
            upos_target_url,
            params=fin_params,
            json={"parts": parts},
            headers={**upos_headers, "Content-Type": "application/json"},
            timeout=30,
        )
        fin_resp.raise_for_status()
        fin_data = fin_resp.json()
        if fin_data.get("OK") != 1:
            raise RuntimeError(f"Bilibili UPOS finalize failed: {fin_data}")

        return {
            "bili_filename": bili_filename,
            "biz_id": biz_id,
            "upos_uri": upos_uri,
            "upload_id": upload_id,
            "chunks": total_chunks,
            "file_size": file_size,
        }

    def resolve_activity_mission(
        self,
        tags: Optional[List[str]] = None,
        title: str = "",
        lookup_online: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Resolves official Bilibili activity `mission_id`, `topic_id`, and `topic_name`.

        Checks built-in `BILIBILI_ACTIVITY_MISSIONS` first across `tags` and `title`.
        Optionally queries `/x/vupre/web/topic/search` when `lookup_online=True`.
        """
        candidate_tags = [re.sub(r"^[#【\s]+|[#】\s]+$", "", t) for t in (tags or []) if t and t.strip()]

        # 1. Match tags in order against built-in activity mission dictionary
        for ctag in candidate_tags:
            if ctag in BILIBILI_ACTIVITY_MISSIONS:
                return dict(BILIBILI_ACTIVITY_MISSIONS[ctag])
            for act_name, act_info in BILIBILI_ACTIVITY_MISSIONS.items():
                if act_name in ctag:
                    return dict(act_info)

        # 2. Match title against built-in activity mission dictionary by earliest position
        if title:
            title_matches: List[Tuple[int, Dict[str, Any]]] = []
            for act_name, act_info in BILIBILI_ACTIVITY_MISSIONS.items():
                pos = title.find(act_name)
                if pos != -1:
                    title_matches.append((pos, dict(act_info)))
            if title_matches:
                title_matches.sort(key=lambda x: x[0])
                return title_matches[0][1]

        # 3. Optional online lookup via /x/vupre/web/topic/search
        if lookup_online and self.is_authenticated:
            search_keywords = candidate_tags[:3] or ([title[:20]] if title else [])
            for kw in search_keywords:
                try:
                    resp = self.session.get(
                        BILIBILI_TOPIC_SEARCH_URL,
                        params={"keywords": kw, "page_size": "20", "offset": "0"},
                        cookies=self.cookies,
                        headers=self._web_headers(),
                        timeout=10,
                    )
                    resp.raise_for_status()
                    payload = resp.json()
                    topics = ((payload.get("data") or {}).get("topics")) or []
                    for item in topics:
                        m_id = int(item.get("mission_id") or 0)
                        t_id = int(item.get("topic_id") or 0)
                        t_name = str(item.get("topic_name") or kw)
                        if m_id > 0 and t_id > 0:
                            return {
                                "topic_id": t_id,
                                "mission_id": m_id,
                                "topic_name": t_name,
                            }
                except Exception:
                    continue

        return None

    def submit_archive(
        self,
        bili_filename: str,
        cover_url: str,
        title: str,
        tid: int = DEFAULT_BILIBILI_TID,
        tags: Optional[List[str]] = None,
        description: str = "",
        biz_id: int = 0,
        dtime: Optional[int] = None,
        copyright_type: int = 1,
        dynamic: Optional[str] = None,
        mission_id: Optional[int] = None,
        topic_id: Optional[int] = None,
        topic_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Submits an uploaded UPOS video to Bilibili Creator Center (`POST /x/vu/web/add/v3`)."""
        if not self.is_authenticated:
            raise RuntimeError("Bilibili SESSDATA and bili_jct cookies are required for archive submission")

        clean_tags = [t.strip() for t in (tags or ["科技科普", "人工智能"]) if t.strip()][:12]
        resolved_dynamic = dynamic if dynamic is not None else (f"#{clean_tags[0]}# {title}" if clean_tags else title)

        activity_info = self.resolve_activity_mission(tags=clean_tags, title=title)
        eff_mission_id = mission_id if mission_id is not None else (activity_info or {}).get("mission_id")
        eff_topic_id = topic_id if topic_id is not None else (activity_info or {}).get("topic_id")
        eff_topic_name = topic_name if topic_name is not None else (activity_info or {}).get("topic_name")

        payload: Dict[str, Any] = {
            "copyright": copyright_type,
            "videos": [
                {
                    "filename": bili_filename,
                    "title": title[:80],
                    "desc": "",
                    "cid": biz_id,
                }
            ],
            "cover": cover_url,
            "title": title[:80],
            "tid": int(tid),
            "tag": ",".join(clean_tags),
            "desc_format_id": 0,
            "desc": description[:2000],
            "dynamic": resolved_dynamic,
            "interactive": 0,
            "no_reprint": 1,
            "open_elec": 1,
            "up_selection_reply": 0,
            "up_close_reply": 0,
            "up_close_danmu": 0,
            "act_reserve_create": 0,
            "no_disturbance": 0,
            "csrf": self.bili_jct,
        }
        if eff_mission_id:
            payload["mission_id"] = int(eff_mission_id)
        if eff_topic_id:
            payload["topic_id"] = int(eff_topic_id)
        if eff_topic_name:
            payload["topic_name"] = str(eff_topic_name)
        if dtime is not None:
            payload["dtime"] = int(dtime)

        resp = self.session.post(
            BILIBILI_ADD_V3_URL,
            params={"t": str(int(time.time() * 1000)), "csrf": self.bili_jct},
            json=payload,
            cookies=self.cookies,
            headers=self._web_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        res_json = resp.json()
        if res_json.get("code") != 0:
            raise RuntimeError(f"Bilibili add/v3 submission error: {res_json}")

        data = res_json.get("data") or {}
        result: Dict[str, Any] = {
            "status": "scheduled_on_bilibili" if dtime else "published_on_bilibili",
            "aid": data.get("aid"),
            "bvid": data.get("bvid"),
            "dtime": dtime,
            "dtime_iso": (
                dt.datetime.fromtimestamp(dtime, tz=dt.timezone.utc).astimezone().isoformat() if dtime else None
            ),
            "cover_url": cover_url,
            "bili_filename": bili_filename,
            "manage_url": BILIBILI_CREATOR_MANAGER_URL,
            "mission_id": eff_mission_id,
            "topic_id": eff_topic_id,
            "topic_name": eff_topic_name,
        }
        return result

    def post_and_pin_comment(self, aid: int, message: str) -> Dict[str, Any]:
        """Posts a comment on a Bilibili video (`POST /x/v2/reply/add`) and pins it (`POST /x/v2/reply/top`)."""
        if not self.is_authenticated:
            raise RuntimeError("Bilibili SESSDATA and bili_jct cookies are required for posting comments")

        api_headers = {
            "User-Agent": STANDARD_USER_AGENT,
            "Referer": f"https://www.bilibili.com/video/av{int(aid)}",
            "Origin": "https://www.bilibili.com",
            "Accept": "application/json, text/plain, */*",
        }

        add_resp = self.session.post(
            BILIBILI_REPLY_ADD_URL,
            data={
                "oid": str(int(aid)),
                "type": "1",
                "message": message,
                "plat": "1",
                "csrf": self.bili_jct,
            },
            cookies=self.cookies,
            headers=api_headers,
            timeout=20,
        )
        add_resp.raise_for_status()
        add_json = add_resp.json()
        add_ok = add_json.get("code") == 0
        rpid = (add_json.get("data") or {}).get("rpid") if add_ok else None

        top_json: Optional[Dict[str, Any]] = None
        top_ok = False
        if add_ok and rpid is not None:
            for attempt in range(3):
                top_resp = self.session.post(
                    BILIBILI_REPLY_TOP_URL,
                    data={
                        "oid": str(int(aid)),
                        "type": "1",
                        "rpid": str(rpid),
                        "action": "1",
                        "csrf": self.bili_jct,
                    },
                    cookies=self.cookies,
                    headers=api_headers,
                    timeout=20,
                )
                top_resp.raise_for_status()
                top_json = top_resp.json()
                top_ok = top_json.get("code") == 0
                if top_ok or top_json.get("code") != -404:
                    break
                if attempt < 2:
                    time.sleep(1.5)

        return {
            "aid": int(aid),
            "rpid": rpid,
            "added": add_ok,
            "pinned": top_ok,
            "add_response": add_json,
            "top_response": top_json,
        }

    def get_archive_view(self, aid: int) -> Dict[str, Any]:
        """Fetches full archive metadata and video parts (`GET /x/vupre/web/archive/view?aid=...`)."""
        if not self.is_authenticated:
            raise RuntimeError("Bilibili SESSDATA and bili_jct cookies are required for archive view")

        resp = self.session.get(
            BILIBILI_ARCHIVE_VIEW_URL,
            params={"aid": str(int(aid))},
            cookies=self.cookies,
            headers=self._web_headers(),
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()

    def edit_archive(
        self,
        aid: int,
        description: Optional[str] = None,
        tid: Optional[int] = None,
        tags: Optional[List[str]] = None,
        title: Optional[str] = None,
        cover_url: Optional[str] = None,
        cover_path: Optional[Path] = None,
        mission_id: Optional[int] = None,
        topic_id: Optional[int] = None,
        topic_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Updates an existing Bilibili archive via Creator Center (`/x/vu/web/edit`)."""
        view_json = self.get_archive_view(aid)
        if view_json.get("code") != 0 or not view_json.get("data"):
            return {"aid": int(aid), "updated": False, "view_response": view_json}

        data = view_json["data"]
        arc = data.get("archive") or {}
        raw_videos = data.get("videos") or []

        videos_payload = [
            {
                "filename": v.get("filename", ""),
                "title": v.get("title", arc.get("title", ""))[:80],
                "desc": v.get("desc", ""),
                "cid": v.get("cid", 0),
            }
            for v in raw_videos
        ]

        eff_cover = cover_url
        if not eff_cover and cover_path is not None and Path(cover_path).exists():
            eff_cover = self.upload_cover(Path(cover_path))
        eff_cover = eff_cover or str(arc.get("cover") or "")

        eff_title = (title or arc.get("title") or "")[:80]
        eff_tid = int(tid if tid is not None else (arc.get("tid") or DEFAULT_BILIBILI_TID))
        eff_tags = (
            ",".join([t.strip() for t in tags if t.strip()][:12]) if tags is not None else str(arc.get("tag") or "")
        )
        eff_desc = (description if description is not None else str(arc.get("desc") or ""))[:2000]

        payload: Dict[str, Any] = {
            "aid": int(aid),
            "copyright": int(arc.get("copyright") or 1),
            "videos": videos_payload,
            "cover": eff_cover,
            "title": eff_title,
            "tid": eff_tid,
            "tag": eff_tags,
            "desc_format_id": 0,
            "desc": eff_desc,
            "dynamic": str(arc.get("dynamic") or ""),
            "interactive": int(arc.get("interactive") or 0),
            "no_reprint": int(arc["no_reprint"]) if arc.get("no_reprint") is not None else 1,
            "open_elec": 1,
            "csrf": self.bili_jct,
        }
        if arc.get("dtime"):
            payload["dtime"] = int(arc["dtime"])

        eff_mission = mission_id if mission_id is not None else arc.get("mission_id")
        eff_topic = topic_id if topic_id is not None else arc.get("topic_id")
        if eff_mission:
            payload["mission_id"] = int(eff_mission)
        if eff_topic:
            payload["topic_id"] = int(eff_topic)
        if topic_name:
            payload["topic_name"] = str(topic_name)

        edit_resp = self.session.post(
            BILIBILI_EDIT_ARCHIVE_URL,
            params={"t": str(int(time.time() * 1000)), "csrf": self.bili_jct},
            json=payload,
            cookies=self.cookies,
            headers=self._web_headers(),
            timeout=30,
        )
        edit_resp.raise_for_status()
        edit_json = edit_resp.json()
        return {
            "aid": int(aid),
            "updated": edit_json.get("code") == 0,
            "edit_response": edit_json,
            "submitted_payload": payload,
        }

    def upload_to_bilibili_api(
        self,
        video_path: Path,
        cover_path: Path,
        title: str,
        tid: int = DEFAULT_BILIBILI_TID,
        tags: Optional[List[str]] = None,
        description: str = "",
        mode: str = "schedule",
        schedule_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        """End-to-end Bilibili cover upload + UPOS video upload + add/v3 archive submission."""
        cover_url = self.upload_cover(cover_path)
        upos_info = self.upload_video_upos(video_path)

        dtime: Optional[int] = None
        if mode in ("schedule", "draft") or schedule_at:
            dtime = compute_bilibili_dtime(schedule_at)

        sub_info = self.submit_archive(
            bili_filename=upos_info["bili_filename"],
            cover_url=cover_url,
            title=title,
            tid=tid,
            tags=tags,
            description=description,
            biz_id=upos_info["biz_id"],
            dtime=dtime,
        )
        return {
            **sub_info,
            "upos": upos_info,
        }

    # Alias matching exact casing in prompt
    upload_to_bilibili_API = upload_to_bilibili_api


class WeChatMPPublisher:
    """Publishes inline-CSS HTML articles to WeChat Official Account Draft Box (`cgi-bin/draft/add`)."""

    def __init__(
        self,
        appid: Optional[str] = None,
        appsecret: Optional[str] = None,
        vault: Optional[AuthVault] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.vault = vault or AuthVault()
        self.session = session or requests.Session()
        self.appid = (appid or os.environ.get("WECHAT_MP_APPID", "")).strip()
        self.appsecret = (appsecret or os.environ.get("WECHAT_MP_APPSECRET", "")).strip()

        if not self.appid or not self.appsecret:
            cred_file = self.vault.get_platform_dir("wechat_mp", create=False) / "credentials.json"
            if cred_file.exists():
                try:
                    data = json.loads(cred_file.read_text(encoding="utf-8"))
                    self.appid = self.appid or str(data.get("appid", "")).strip()
                    self.appsecret = self.appsecret or str(data.get("appsecret", "")).strip()
                except Exception:
                    pass

    @property
    def is_configured(self) -> bool:
        return bool(self.appid and self.appsecret)

    def get_access_token(self) -> str:
        """Obtains WeChat Official Account access_token via client_credential grant."""
        if not self.is_configured:
            raise RuntimeError("WECHAT_MP_APPID and WECHAT_MP_APPSECRET are required for WeChat MP API")

        resp = self.session.get(
            WECHAT_TOKEN_URL,
            params={
                "grant_type": "client_credential",
                "appid": self.appid,
                "secret": self.appsecret,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if "access_token" not in data:
            raise RuntimeError(f"WeChat MP token error: {data}")
        return str(data["access_token"])

    def upload_thumb_material(self, access_token: str, cover_path: Path) -> str:
        """Uploads a permanent thumb/image material to WeChat MP and returns media_id."""
        with open(cover_path, "rb") as f:
            files = {"media": (cover_path.name, f, "image/jpeg")}
            resp = self.session.post(
                WECHAT_MATERIAL_UPLOAD_URL,
                params={"access_token": access_token, "type": "image"},
                files=files,
                timeout=30,
            )
        resp.raise_for_status()
        data = resp.json()
        if "media_id" not in data:
            raise RuntimeError(f"WeChat MP thumb upload error: {data}")
        return str(data["media_id"])

    def push_draft(
        self,
        title: str,
        html_content: str,
        digest: str = "",
        author: str = "ContentFlow",
        cover_path: Optional[Path] = None,
        thumb_media_id: Optional[str] = None,
        content_source_url: str = "",
    ) -> Dict[str, Any]:
        """Pushes an HTML article into WeChat Official Account Draft Box (`cgi-bin/draft/add`)."""
        if not self.is_configured:
            return {
                "status": "staged_offline",
                "reason": "WECHAT_MP_APPID / WECHAT_MP_APPSECRET not configured",
                "media_id": None,
            }

        access_token = self.get_access_token()
        resolved_thumb_id = thumb_media_id
        if not resolved_thumb_id and cover_path and Path(cover_path).exists():
            resolved_thumb_id = self.upload_thumb_material(access_token, Path(cover_path))

        article_item: Dict[str, Any] = {
            "title": title[:64],
            "author": author[:16],
            "digest": (digest or title)[:120],
            "content": html_content,
            "content_source_url": content_source_url,
            "need_open_comment": 1,
            "only_fans_can_comment": 0,
        }
        if resolved_thumb_id:
            article_item["thumb_media_id"] = resolved_thumb_id

        payload = {"articles": [article_item]}
        body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        resp = self.session.post(
            WECHAT_DRAFT_ADD_URL,
            params={"access_token": access_token},
            data=body_bytes,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        if "media_id" not in data and data.get("errcode", 0) != 0:
            raise RuntimeError(f"WeChat MP draft/add failed: {data}")

        return {
            "status": "draft_pushed",
            "media_id": data.get("media_id"),
            "thumb_media_id": resolved_thumb_id,
            "raw_response": data,
        }


class MatrixPublisher:
    """Discovers project media/copywriting and builds Advisor Review & Staging packages."""

    def __init__(
        self,
        vault: Optional[AuthVault] = None,
        projects_dir: Optional[Path] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.vault = vault or AuthVault()
        self.projects_dir = Path(projects_dir) if projects_dir is not None else PROJECTS_DIR
        self.session = session

    def resolve_project_dir(self, project_id_or_name: str) -> Path:
        """Resolves a project directory by exact name, numeric prefix, or substring."""
        candidate_path = Path(project_id_or_name)
        if candidate_path.is_absolute() and candidate_path.exists() and candidate_path.is_dir():
            return candidate_path

        direct = self.projects_dir / project_id_or_name
        if direct.exists() and direct.is_dir():
            return direct

        if not self.projects_dir.exists():
            return direct

        candidates = sorted([p for p in self.projects_dir.iterdir() if p.is_dir()])
        if project_id_or_name.isdigit():
            prefix = f"{int(project_id_or_name):03d}_"
            for c in candidates:
                if c.name.startswith(prefix):
                    return c

        for c in candidates:
            if c.name.startswith(f"{project_id_or_name}_"):
                return c

        matched = [c for c in candidates if project_id_or_name.lower() in c.name.lower()]
        if len(matched) == 1:
            return matched[0]
        if len(matched) > 1:
            for m in matched:
                if m.name.endswith(f"_{project_id_or_name.lower()}"):
                    return m
            return matched[0]

        return direct

    def discover_video(self, project_dir: Path) -> Optional[Path]:
        """Discovers the best ready-to-publish .mp4 file in delivery/ or output/."""
        search_dirs = [
            project_dir / "delivery",
            project_dir / "output" / "video",
            project_dir / "output",
        ]
        all_mp4s: List[Path] = []
        for sdir in search_dirs:
            if sdir.exists() and sdir.is_dir():
                all_mp4s.extend([p for p in sdir.glob("*.mp4") if p.is_file()])

        if not all_mp4s:
            return None

        def _score_mp4(p: Path) -> Tuple[int, int, int, int]:
            name = p.name.lower()
            in_delivery = 1 if p.parent.name == "delivery" else 0
            is_final = 1 if ("final" in name or "full_chorus" in name) else 0
            is_polished = 1 if ("polished" in name or "enhanced" in name or "rendered" in name) else 0
            try:
                size = p.stat().st_size
            except OSError:
                size = 0
            return (in_delivery, is_final, is_polished, size)

        all_mp4s.sort(key=_score_mp4, reverse=True)
        return all_mp4s[0]

    def discover_or_extract_cover(
        self,
        project_dir: Path,
        video_path: Optional[Path] = None,
        aspect: str = "16:9",
        title: str = "",
    ) -> Path:
        """Discovers an existing cover image or auto-extracts a high-res frame via ffmpeg."""
        delivery_dir = project_dir / "delivery"
        delivery_dir.mkdir(parents=True, exist_ok=True)

        search_dirs = [
            delivery_dir,
            project_dir / "output" / "video",
            project_dir / "output",
            project_dir / "assets",
        ]
        for sdir in search_dirs:
            if not sdir.exists():
                continue
            for pattern in ("*_cover.jpg", "*_cover.png", "*_cover.jpeg", "cover.jpg", "cover.png", "*preview*.jpg"):
                matches = sorted(sdir.glob(pattern))
                if matches:
                    return matches[0]

        out_cover = delivery_dir / f"{project_dir.name}_cover.jpg"

        # Auto-extract frame from video via ffmpeg if video exists
        if video_path is not None and video_path.exists():
            scale_filter = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2"
            if aspect == "9:16":
                scale_filter = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2"

            for seek_ts in ("00:00:01.000", "00:00:00.000"):
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-ss",
                    seek_ts,
                    "-i",
                    str(video_path),
                    "-frames:v",
                    "1",
                    "-vf",
                    scale_filter,
                    "-q:v",
                    "2",
                    str(out_cover),
                ]
                try:
                    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20, check=False)
                    if proc.returncode == 0 and out_cover.exists() and out_cover.stat().st_size > 0:
                        return out_cover
                except Exception:
                    pass

        # Fallback: generate a high-res cover image via Pillow
        width, height = (1080, 1920) if aspect == "9:16" else (1920, 1080)
        img = Image.new("RGB", (width, height), color=(18, 28, 48))
        draw = ImageDraw.Draw(img)
        draw.rectangle([40, 40, width - 40, height - 40], outline=(0, 190, 255), width=6)
        label = title or project_dir.name
        draw.text((80, height // 2 - 20), f"ContentFlow Cover: {label[:40]}", fill=(240, 248, 255))
        img.save(out_cover, format="JPEG", quality=92)
        return out_cover

    @staticmethod
    def parse_bilibili_markdown(md_text: str) -> Dict[str, Any]:
        """Parses title, category, tid, description, tags, and pinned_comment from delivery/bilibili.md."""
        title = ""
        category_str = "知识 -> 计算机技术"
        tid = DEFAULT_BILIBILI_TID
        description_lines: List[str] = []
        tags: List[str] = []
        pinned_comment_lines: List[str] = []

        lines = md_text.splitlines()
        mode: Optional[str] = None

        for raw_line in lines:
            stripped = raw_line.strip()

            if "**主选分区**" in stripped or "**分区**" in stripped:
                parts = re.split(r"[：:]", stripped, maxsplit=1)
                if len(parts) == 2:
                    category_str = parts[1].strip()
                    tid = resolve_bilibili_tid(category_str)
                mode = None
                continue

            if "**视频标题" in stripped or "**标题" in stripped:
                parts = re.split(r"[：:]", stripped, maxsplit=1)
                if len(parts) == 2 and parts[1].strip():
                    candidate = parts[1].strip().strip("`")
                    if candidate:
                        title = candidate
                        mode = None
                        continue
                mode = "title"
                continue

            if "**简介" in stripped:
                parts = re.split(r"[：:]", stripped, maxsplit=1)
                if len(parts) == 2 and parts[1].strip():
                    description_lines.append(parts[1].strip())
                mode = "description"
                continue

            if "**标签" in stripped:
                parts = re.split(r"[：:]", stripped, maxsplit=1)
                if len(parts) == 2 and parts[1].strip():
                    raw_tags = re.split(r"[,，#]+", parts[1])
                    tags.extend([t.strip() for t in raw_tags if t.strip()])
                mode = "tags"
                continue

            if "**置顶评论" in stripped:
                parts = re.split(r"[：:]", stripped, maxsplit=1)
                if len(parts) == 2 and parts[1].strip():
                    pinned_comment_lines.append(parts[1].strip())
                mode = "pinned_comment"
                continue

            if stripped.startswith("## ") or (
                stripped.startswith("* **") and mode in ("description", "tags", "title", "pinned_comment")
            ):
                mode = None
                continue

            if mode == "title" and not title:
                m = re.match(r"^(?:\d+\.\s*|\-\s*|\*\s*)(.+)$", stripped)
                if m:
                    candidate = m.group(1).strip()
                    candidate = re.sub(r"\s*[\(（]首选[\)）]\s*$", "", candidate).strip()
                    title = candidate
            elif mode == "description":
                clean_desc_line = raw_line[2:] if raw_line.startswith("  ") else raw_line
                description_lines.append(clean_desc_line.rstrip())
            elif mode == "tags":
                if stripped:
                    raw_tags = re.split(r"[,，#]+", stripped)
                    tags.extend([t.strip() for t in raw_tags if t.strip()])
            elif mode == "pinned_comment":
                clean_pin_line = raw_line[2:] if raw_line.startswith("  ") else raw_line
                if clean_pin_line.strip():
                    pinned_comment_lines.append(clean_pin_line.rstrip())

        description = "\n".join(description_lines).strip()
        pinned_comment = "\n".join(pinned_comment_lines).strip().strip("“”\"'")
        return {
            "title": title[:80],
            "category": category_str,
            "tid": tid,
            "description": description,
            "tags": tags[:12],
            "pinned_comment": pinned_comment,
        }

    def discover_metadata(self, project_dir: Path, platform: str = "bilibili") -> Dict[str, Any]:
        """Discovers title, tid, category, tags, description, and pinned_comment from project copywriting and brief.json."""
        delivery_dir = project_dir / "delivery"
        copy_dir = project_dir / "output" / "copy"
        brief_file = project_dir / "brief.json"

        facts: Optional[FactSheet] = None
        if brief_file.exists():
            try:
                facts = FactSheet.from_dict(json.loads(brief_file.read_text(encoding="utf-8")))
            except Exception:
                facts = None

        bili_md_file = delivery_dir / "bilibili.md"
        if bili_md_file.exists():
            parsed = self.parse_bilibili_markdown(bili_md_file.read_text(encoding="utf-8"))
            if parsed["title"]:
                parsed["description"] = ensure_compliance_and_credits_footer(parsed.get("description", ""))
                return parsed

        release_md = delivery_dir / "release.md"
        if not release_md.exists():
            release_md = copy_dir / "release.md"

        title = ""
        description = ""
        tags: List[str] = []
        category = facts.category if facts else "计算机技术"

        if release_md.exists():
            rel_text = release_md.read_text(encoding="utf-8")
            m_title = re.search(r"\*\*视频标题\*\*[：:]\s*`?([^`\n]+)`?", rel_text)
            if m_title:
                title = m_title.group(1).strip()
            else:
                m_h1 = re.search(r"^#\s+(.+)$", rel_text, flags=re.MULTILINE)
                if m_h1:
                    title = m_h1.group(1).strip()
            description = rel_text.strip()[:800]

        if facts:
            if not title:
                title = f"{facts.name}: {facts.tagline}"[:80]
            if not description:
                bullets = "\n".join(f"- {h}" for h in facts.highlights)
                description = f"{facts.description}\n\n{bullets}\n\n{facts.call_to_action}".strip()
            if not tags:
                tags = [t.strip() for t in [*facts.tech_stack, facts.name, "AI", "开源", "科技科普"] if t.strip()][:10]

        if not title:
            title = f"ContentFlow 精选视频：{project_dir.name}"[:80]
        if not description:
            description = f"本期视频为您带来 {project_dir.name} 的深度解析与实战演示。"
        if not tags:
            tags = ["人工智能", "大模型", "科技科普", "深度学习", "ContentFlow"]

        tid = resolve_bilibili_tid(category)
        description = ensure_compliance_and_credits_footer(description)

        return {
            "title": title[:80],
            "category": category,
            "tid": tid,
            "description": description,
            "tags": tags[:12],
            "pinned_comment": "",
        }

    def _stage_bilibili_submission(
        self,
        staged_dir: Path,
        manifest: Dict[str, Any],
        safety_mode: str,
        execute_upload: bool = False,
        remote_schedule: bool = False,
    ) -> Dict[str, Any]:
        """Stages biliup studio config & optionally performs real UPOS + add/v3 upload to Bilibili."""
        computed_dtime: Optional[int] = None
        if safety_mode == "schedule" or remote_schedule or manifest.get("schedule_at"):
            computed_dtime = compute_bilibili_dtime(manifest.get("schedule_at"))

        bili_studio_config = {
            "line": "bda2",
            "limit": 3,
            "streamers": {
                manifest["title"]: {
                    "title": manifest["title"],
                    "tid": manifest["tid"],
                    "tag": ",".join(manifest["tags"]),
                    "desc": manifest["description"],
                    "cover": manifest["cover_path"],
                    "copyright": 1,
                    "dtime": computed_dtime,
                }
            },
        }
        studio_cfg_path = staged_dir / "biliup_studio.json"
        studio_cfg_path.write_text(json.dumps(bili_studio_config, ensure_ascii=False, indent=2), encoding="utf-8")

        cookies = self.vault.load_bilibili_cookies()
        has_cookies = bool(cookies.get("SESSDATA") and cookies.get("bili_jct"))
        biliup_bin = shutil.which("biliup")

        action_state = "staged_for_advisor_review"
        if safety_mode == "schedule":
            action_state = "scheduled_in_staging_queue"
        elif safety_mode == "direct" and has_cookies:
            action_state = "ready_for_direct_upload"

        receipt: Dict[str, Any] = {
            "status": action_state,
            "platform": "bilibili",
            "safety_mode": safety_mode,
            "dtime": computed_dtime,
            "auth_cookies_present": has_cookies,
            "dede_userid": cookies.get("DedeUserID"),
            "biliup_cli_detected": bool(biliup_bin),
            "studio_config_path": str(studio_cfg_path),
            "creator_center_url": BILIBILI_CREATOR_MANAGER_URL,
            "one_click_verify_cmd": (
                f"python cli.py publish --project {manifest['project_id']} "
                f"--platforms bilibili --mode {safety_mode} --execute-upload"
            ),
        }

        if (execute_upload or remote_schedule) and has_cookies and manifest.get("video_path"):
            uploader = BilibiliUploader(vault=self.vault, cookies=cookies, session=self.session)
            upload_mode = "schedule" if (safety_mode in ("schedule", "draft") or remote_schedule) else "direct"
            api_res = uploader.upload_to_bilibili_api(
                video_path=Path(manifest["video_path"]),
                cover_path=Path(manifest["cover_path"]),
                title=manifest["title"],
                tid=manifest["tid"],
                tags=manifest["tags"],
                description=manifest["description"],
                mode=upload_mode,
                schedule_at=manifest.get("schedule_at"),
            )
            receipt.update(api_res)

        return receipt

    def publish_project(
        self,
        project: str,
        platforms: Optional[List[str]] = None,
        mode: str = "draft",
        schedule_at: Optional[str] = None,
        execute_upload: Optional[bool] = None,
        remote_schedule: bool = False,
    ) -> Dict[str, Any]:
        """Stages or publishes a project across one or more target platforms and returns Advisor Receipts."""
        if mode not in SAFETY_MODES:
            raise ValueError(f"Invalid publish mode '{mode}'. Choose from: {SAFETY_MODES}")

        should_execute_upload = (
            bool(execute_upload)
            if execute_upload is not None
            else (mode in ("schedule", "direct") or bool(remote_schedule))
        )

        target_platforms = [p.strip().lower() for p in (platforms or ["bilibili"]) if p.strip()]
        for p in target_platforms:
            if p not in SUPPORTED_PLATFORMS:
                raise ValueError(f"Unsupported platform '{p}'. Supported: {SUPPORTED_PLATFORMS}")

        project_dir = self.resolve_project_dir(project)
        if not project_dir.exists():
            raise FileNotFoundError(f"Project directory not found for '{project}' (resolved: {project_dir})")

        project_id = project_dir.name
        video_path = self.discover_video(project_dir)

        results_by_platform: Dict[str, Dict[str, Any]] = {}
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

        for platform in target_platforms:
            aspect = "9:16" if platform in ("douyin", "xiaohongshu") else "16:9"
            meta = self.discover_metadata(project_dir, platform=platform)
            cover_path = self.discover_or_extract_cover(
                project_dir=project_dir,
                video_path=video_path,
                aspect=aspect,
                title=meta["title"],
            )

            staged_dir = project_dir / "delivery" / f"staged_{platform}"
            staged_dir.mkdir(parents=True, exist_ok=True)

            auth_info = self.vault.get_platform_status(platform, verify_online=False)

            manifest: Dict[str, Any] = {
                "project_id": project_id,
                "platform": platform,
                "title": meta["title"],
                "tid": meta["tid"],
                "category": meta["category"],
                "tags": meta["tags"],
                "description": meta["description"],
                "pinned_comment": meta.get("pinned_comment", ""),
                "cover_path": str(cover_path),
                "video_path": str(video_path) if video_path else None,
                "safety_mode": mode,
                "schedule_at": schedule_at,
                "timestamp": now_iso,
                "auth_status": auth_info,
            }

            if platform == "bilibili":
                submission_receipt = self._stage_bilibili_submission(
                    staged_dir=staged_dir,
                    manifest=manifest,
                    safety_mode=mode,
                    execute_upload=should_execute_upload,
                    remote_schedule=remote_schedule,
                )
            elif platform == "wechat_mp":
                wechat_html_path = project_dir / "delivery" / "wechat.html"
                if not wechat_html_path.exists():
                    wechat_html_path = project_dir / "output" / "copy" / "wechat.html"
                if wechat_html_path.exists():
                    html_content = wechat_html_path.read_text(encoding="utf-8")
                else:
                    wechat_md_path = project_dir / "delivery" / "wechat.md"
                    if not wechat_md_path.exists():
                        wechat_md_path = project_dir / "output" / "copy" / "wechat.md"
                    raw_md = (
                        wechat_md_path.read_text(encoding="utf-8") if wechat_md_path.exists() else meta["description"]
                    )
                    html_content = HTMLFormatter.format_text_to_html(raw_md, title=meta["title"])

                staged_html = staged_dir / "wechat_article.html"
                staged_html.write_text(html_content, encoding="utf-8")

                mp_pub = WeChatMPPublisher(vault=self.vault, session=self.session)
                if mp_pub.is_configured and mode in ("draft", "direct"):
                    try:
                        submission_receipt = mp_pub.push_draft(
                            title=meta["title"],
                            html_content=html_content,
                            digest=meta["description"][:110],
                            cover_path=cover_path,
                        )
                    except Exception as exc:
                        submission_receipt = {
                            "status": "draft_push_error",
                            "error": str(exc),
                            "staged_html_path": str(staged_html),
                        }
                else:
                    submission_receipt = {
                        "status": "staged_for_advisor_review",
                        "platform": "wechat_mp",
                        "safety_mode": mode,
                        "staged_html_path": str(staged_html),
                        "wechat_mp_configured": mp_pub.is_configured,
                    }
            else:
                submission_receipt = {
                    "status": "staged_for_advisor_review" if mode == "draft" else f"staged_{mode}",
                    "platform": platform,
                    "safety_mode": mode,
                    "auth_cookies_present": auth_info.get("logged_in", False),
                }

            manifest["advisor_receipt"] = submission_receipt

            manifest_path = staged_dir / "publish_manifest.json"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

            receipt_md_path = staged_dir / "advisor_receipt.md"
            receipt_md_lines = [
                f"# ContentFlow Advisor Review Receipt — `{platform.upper()}`",
                "",
                f"- **Project**: `{project_id}`",
                f"- **Safety Mode**: `{mode}`" + (f" (Scheduled at `{schedule_at}`)" if schedule_at else ""),
                f"- **Timestamp**: `{now_iso}`",
                f"- **Title**: {manifest['title']}",
                f"- **Category / TID**: {manifest['category']} (`tid={manifest['tid']}`)",
                f"- **Tags**: `{', '.join(manifest['tags'])}`",
                f"- **Video Path**: `{manifest['video_path']}`",
                f"- **Cover Path**: `{manifest['cover_path']}`",
                f"- **Auth Logged In**: `{auth_info.get('logged_in')}` (UID: `{auth_info.get('mid')}`)",
                f"- **Submission Status**: `{submission_receipt.get('status')}`",
            ]
            if submission_receipt.get("bvid"):
                receipt_md_lines.append(
                    f"- **Bilibili BVID / AID**: `{submission_receipt.get('bvid')}` (`aid={submission_receipt.get('aid')}`)"
                )
            if submission_receipt.get("dtime_iso"):
                receipt_md_lines.append(f"- **Scheduled Publish Time**: `{submission_receipt.get('dtime_iso')}`")
            receipt_md_lines.extend(
                [
                    f"- **Manifest JSON**: `{manifest_path}`",
                    "",
                    "## Description Preview",
                    "```text",
                    manifest["description"],
                    "```",
                ]
            )
            receipt_md_path.write_text("\n".join(receipt_md_lines) + "\n", encoding="utf-8")

            manifest["manifest_path"] = str(manifest_path)
            manifest["receipt_md_path"] = str(receipt_md_path)
            results_by_platform[platform] = manifest

        return {
            "project_id": project_id,
            "project_dir": str(project_dir),
            "safety_mode": mode,
            "schedule_at": schedule_at,
            "platforms": results_by_platform,
        }
