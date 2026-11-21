"""Bilibili Live Room Lifecycle Controller with strict secret & PII redaction.

Manages authenticated Bilibili livestream room operations via `AuthVault`:
- `get_my_room_info()` (`GET /xlive/app-blink/v1/room/GetInfo?platform=pc`)
- `update_room_title()` (`POST /room/v1/Room/update`)
- `upload_live_cover()` (optional non-fatal cover upload/update)
- `start_live()` (`POST /room/v1/Room/startLive`, with `code == 60024` face-auth QR PNG export)
- `stop_live()` (`POST /room/v1/Room/stopLive`, idempotent shutdown helper)

Security & Privacy Invariants:
- RTMP push URLs, stream keys, `room_id`, `uid`, `DedeUserID`, `SESSDATA`, and `bili_jct`
  are NEVER printed, logged, or serialized unredacted in `__repr__`, manifests, or errors.
- Face authentication (`code == 60024`) is NEVER bypassed; instead a crisp scannable QR PNG
  is generated via `core.auth_vault.encode_qr_matrix` + `render_qr_png`.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Final, Optional, Tuple

import requests

from config.settings import OUTPUT_DIR
from core.auth_vault import STANDARD_USER_AGENT, AuthVault, encode_qr_matrix, render_qr_png
from core.live_studio.safety import REDACTED_TOKEN, redact_pii

logger = logging.getLogger(__name__)

REDACTED_RTMP_TOKEN: Final[str] = "<REDACTED_RTMP_URL>"

BILIBILI_LIVE_GET_INFO_URL: Final[str] = "https://api.live.bilibili.com/xlive/app-blink/v1/room/GetInfo"
BILIBILI_LIVE_ROOM_UPDATE_URL: Final[str] = "https://api.live.bilibili.com/room/v1/Room/update"
BILIBILI_LIVE_START_URL: Final[str] = "https://api.live.bilibili.com/room/v1/Room/startLive"
BILIBILI_LIVE_STOP_URL: Final[str] = "https://api.live.bilibili.com/room/v1/Room/stopLive"
BILIBILI_LIVE_IMAGE_UPLOAD_URL: Final[str] = "https://api.bilibili.com/x/upload/web/image"
BILIBILI_LIVE_PRELIVE_UPDATE_URL: Final[str] = (
    "https://api.live.bilibili.com/xlive/app-blink/v1/preLive/UpdatePreLiveInfo"
)

DEFAULT_LIVE_AREA_V2: Final[int] = 1062
FACE_AUTH_REQUIRED_CODE: Final[int] = 60024
DEFAULT_FACE_AUTH_QR_PATH: Final[Path] = OUTPUT_DIR / "live_face_auth_qr.png"

_RTMP_SCHEME_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b(?:rtmps?|srt)://[^\s'\"<>\]\)]+",
)
_LIVE_PUSH_HOST_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)(?:[A-Za-z0-9-]+\.)*live-push[A-Za-z0-9.-]*(?::\d+)?(?:/[^\s'\"<>\]\)]*)?",
)
_STREAM_QUERY_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)(?:\?|&)?(?:streamname|txSecret|txTime|rtmp_code|rtmp_addr|stream_key|live_key|key)=[^\s&'\"<>\]\)]+",
)
_ROOM_AND_CSRF_PATTERNS: Final[Tuple[re.Pattern[str], ...]] = (
    re.compile(r"(?i)(?<![A-Za-z0-9_])(?:room_?id)\s*[:=：]\s*['\"]?\d{3,}['\"]?"),
    re.compile(r"(?i)(?<![A-Za-z0-9_])(?:csrf_token|csrf)\s*[:=]\s*[^\s&;,'\"<>\]\)]+"),
)


def scrub_rtmp_secrets(text: str) -> str:
    """Redact RTMP URLs, stream keys, room IDs, UIDs, CSRF tokens, and cookies from text."""
    if not text:
        return ""
    scrubbed = _RTMP_SCHEME_RE.sub(REDACTED_RTMP_TOKEN, str(text))
    scrubbed = _LIVE_PUSH_HOST_RE.sub(REDACTED_RTMP_TOKEN, scrubbed)
    scrubbed = _STREAM_QUERY_RE.sub(REDACTED_RTMP_TOKEN, scrubbed)
    for pattern in _ROOM_AND_CSRF_PATTERNS:
        scrubbed = pattern.sub(REDACTED_TOKEN, scrubbed)
    scrubbed = redact_pii(scrubbed)
    # Collapse consecutive duplicate RTMP redaction tokens
    scrubbed = re.sub(
        rf"(?:{re.escape(REDACTED_RTMP_TOKEN)})(?:\s*[&/?]*\s*{re.escape(REDACTED_RTMP_TOKEN)})+",
        REDACTED_RTMP_TOKEN,
        scrubbed,
    )
    return scrubbed


@dataclass
class RoomStatus:
    """Bilibili live room metadata with safe redacted serialization."""

    room_id: int
    title: str = ""
    area_v2_id: int = 0
    area_v2_name: str = ""
    live_status: int = 0
    uid: int = 0
    cover_url: str = ""
    raw_code: int = 0
    message: str = ""

    def __repr__(self) -> str:
        safe_room = REDACTED_TOKEN if self.room_id else ""
        safe_uid = REDACTED_TOKEN if self.uid else ""
        return (
            f"RoomStatus(room_id={safe_room!r}, title={self.title!r}, "
            f"area_v2_id={self.area_v2_id!r}, area_v2_name={self.area_v2_name!r}, "
            f"live_status={self.live_status!r}, uid={safe_uid!r})"
        )

    __str__ = __repr__

    def to_redacted_dict(self) -> Dict[str, Any]:
        """Return a strictly PII-free dictionary representation of this room status."""
        return {
            "room_id": REDACTED_TOKEN if self.room_id else "",
            "has_room_id": bool(self.room_id),
            "uid": REDACTED_TOKEN if self.uid else "",
            "title": scrub_rtmp_secrets(self.title),
            "area_v2_id": self.area_v2_id,
            "area_v2_name": self.area_v2_name,
            "live_status": self.live_status,
            "has_cover": bool(self.cover_url),
            "code": self.raw_code,
            "message": scrub_rtmp_secrets(self.message),
        }

    def to_safe_dict(self) -> Dict[str, Any]:
        """Alias of `to_redacted_dict()`."""
        return self.to_redacted_dict()


@dataclass
class StartLiveResult:
    """Result of `BilibiliLiveController.start_live()` with masked RTMP & room secrets."""

    ok: bool
    status: str
    code: int = 0
    room_id: int = 0
    rtmp_addr: str = field(default="", repr=False)
    rtmp_code: str = field(default="", repr=False)
    rtmp_url: str = field(default="", repr=False)
    face_auth_qr_path: Optional[Path] = None
    message: str = ""

    def __repr__(self) -> str:
        safe_room = REDACTED_TOKEN if self.room_id else ""
        safe_rtmp = REDACTED_RTMP_TOKEN if (self.rtmp_url or self.rtmp_addr or self.rtmp_code) else ""
        qr_str = str(self.face_auth_qr_path) if self.face_auth_qr_path is not None else None
        return (
            f"StartLiveResult(ok={self.ok!r}, status={self.status!r}, code={self.code!r}, "
            f"room_id={safe_room!r}, rtmp_url={safe_rtmp!r}, "
            f"face_auth_qr_path={qr_str!r}, message={scrub_rtmp_secrets(self.message)!r})"
        )

    __str__ = __repr__

    def to_safe_dict(self) -> Dict[str, Any]:
        """Return a strictly secret-free & PII-free dict safe for JSON logs and stdout."""
        has_rtmp = bool(self.rtmp_url or self.rtmp_addr or self.rtmp_code)
        return {
            "ok": self.ok,
            "status": self.status,
            "code": self.code,
            "room_id": REDACTED_TOKEN if self.room_id else "",
            "rtmp_url": REDACTED_RTMP_TOKEN if has_rtmp else "",
            "has_rtmp": has_rtmp,
            "face_auth_qr_path": str(self.face_auth_qr_path) if self.face_auth_qr_path is not None else None,
            "message": scrub_rtmp_secrets(self.message),
        }

    def to_redacted_dict(self) -> Dict[str, Any]:
        """Alias of `to_safe_dict()`."""
        return self.to_safe_dict()


def _assemble_rtmp_url(addr: str, code_token: str) -> str:
    """Assemble full RTMP push URL strictly in memory."""
    clean_addr = addr.strip()
    clean_code = code_token.strip()
    if not clean_addr or not clean_code:
        return ""
    if clean_addr.endswith("/") or clean_code.startswith(("?", "/")):
        return f"{clean_addr}{clean_code}"
    return f"{clean_addr}/{clean_code}"


class BilibiliLiveController:
    """Authenticated Bilibili Live room controller backed by `AuthVault` cookies."""

    def __init__(
        self,
        *,
        vault: Optional[AuthVault] = None,
        session: Optional[requests.Session] = None,
        face_auth_qr_path: Optional[Path] = None,
        timeout_sec: float = 15.0,
    ) -> None:
        self.vault = vault or AuthVault()
        self._session = session or requests.Session()
        self.face_auth_qr_path = Path(face_auth_qr_path) if face_auth_qr_path is not None else DEFAULT_FACE_AUTH_QR_PATH
        self.timeout_sec = max(1.0, float(timeout_sec))

    def __repr__(self) -> str:
        return f"BilibiliLiveController(face_auth_qr_path={str(self.face_auth_qr_path)!r}, timeout_sec={self.timeout_sec!r})"

    @staticmethod
    def _headers() -> Dict[str, str]:
        return {
            "User-Agent": STANDARD_USER_AGENT,
            "Referer": "https://link.bilibili.com/p/center/index",
            "Origin": "https://link.bilibili.com",
            "Accept": "application/json, text/plain, */*",
        }

    def _load_cookies_and_csrf(self) -> Tuple[Dict[str, str], str]:
        cookies = self.vault.load_bilibili_cookies()
        if not cookies or not cookies.get("SESSDATA"):
            raise RuntimeError("Bilibili session cookies not found in AuthVault (SESSDATA missing)")
        csrf = str(cookies.get("bili_jct") or "").strip()
        if not csrf:
            raise RuntimeError("Bilibili CSRF token not found in AuthVault")
        return cookies, csrf

    def get_my_room_info(self) -> RoomStatus:
        """Fetch authenticated streamer's live room info without exposing raw IDs in logs."""
        cookies, _ = self._load_cookies_and_csrf()
        resp = self._session.get(
            BILIBILI_LIVE_GET_INFO_URL,
            params={"platform": "pc"},
            cookies=cookies,
            headers=self._headers(),
            timeout=self.timeout_sec,
        )
        resp.raise_for_status()
        payload = resp.json()
        code = int(payload.get("code", -1))
        msg = str(payload.get("message") or payload.get("msg") or "")
        if code != 0:
            raise RuntimeError(f"Failed to fetch Bilibili live room info (code={code}): {scrub_rtmp_secrets(msg)}")

        data = payload.get("data") or {}
        room_id = int(data.get("room_id") or 0)
        if room_id <= 0:
            raise RuntimeError("Bilibili live room not initialized or missing room_id")

        return RoomStatus(
            room_id=room_id,
            title=str(data.get("title") or "").strip(),
            area_v2_id=int(data.get("area_v2_id") or 0),
            area_v2_name=str(data.get("area_v2_name") or "").strip(),
            live_status=int(data.get("live_status") or 0),
            uid=int(data.get("uid") or 0),
            cover_url=str(data.get("cover") or data.get("keyframe") or "").strip(),
            raw_code=code,
            message=msg,
        )

    def update_room_title(self, room_id: int, title: str) -> Dict[str, Any]:
        """Update live room title via `POST /room/v1/Room/update`."""
        if room_id <= 0:
            raise ValueError("room_id must be a positive integer")
        clean_title = scrub_rtmp_secrets(title).replace("@", "").strip()
        if not clean_title:
            raise ValueError("title must not be empty after sanitization")

        cookies, csrf = self._load_cookies_and_csrf()
        form_data = {
            "room_id": str(room_id),
            "title": clean_title,
            "csrf": csrf,
            "csrf_token": csrf,
        }
        resp = self._session.post(
            BILIBILI_LIVE_ROOM_UPDATE_URL,
            data=form_data,
            cookies=cookies,
            headers=self._headers(),
            timeout=self.timeout_sec,
        )
        resp.raise_for_status()
        payload = resp.json()
        code = int(payload.get("code", -1))
        msg = scrub_rtmp_secrets(str(payload.get("message") or payload.get("msg") or ""))
        return {
            "ok": code == 0,
            "code": code,
            "room_id": REDACTED_TOKEN,
            "title": clean_title,
            "message": msg,
        }

    def upload_live_cover(self, cover_path: Path, room_id: Optional[int] = None) -> Dict[str, Any]:
        """Optional non-fatal live room cover upload & update; never crashes start flow."""
        target = Path(cover_path)
        if not target.is_file():
            return {
                "ok": False,
                "non_fatal": True,
                "skipped": True,
                "reason": "cover_file_not_found",
            }
        try:
            cookies, csrf = self._load_cookies_and_csrf()
            mime = "image/png" if target.suffix.lower() == ".png" else "image/jpeg"
            with target.open("rb") as fh:
                upload_resp = self._session.post(
                    BILIBILI_LIVE_IMAGE_UPLOAD_URL,
                    data={"bucket": "live", "dir": "new_room_cover", "csrf": csrf},
                    files={"file": (target.name, fh, mime)},
                    cookies=cookies,
                    headers=self._headers(),
                    timeout=self.timeout_sec,
                )
            upload_resp.raise_for_status()
            up_payload = upload_resp.json()
            up_code = int(up_payload.get("code", -1))
            if up_code != 0:
                return {
                    "ok": False,
                    "non_fatal": True,
                    "code": up_code,
                    "message": scrub_rtmp_secrets(str(up_payload.get("message") or up_payload.get("msg") or "")),
                }
            cover_url = str((up_payload.get("data") or {}).get("location") or "").strip()
            if not cover_url:
                return {
                    "ok": False,
                    "non_fatal": True,
                    "code": -1,
                    "message": "Cover upload succeeded without returning an image URL",
                }

            update_data: Dict[str, str] = {
                "platform": "pc",
                "mobi_app": "pc",
                "build": "1",
                "cover": cover_url,
                "csrf": csrf,
                "csrf_token": csrf,
            }
            if room_id is not None and room_id > 0:
                update_data["room_id"] = str(room_id)
            upd_resp = self._session.post(
                BILIBILI_LIVE_PRELIVE_UPDATE_URL,
                data=update_data,
                cookies=cookies,
                headers=self._headers(),
                timeout=self.timeout_sec,
            )
            upd_resp.raise_for_status()
            upd_payload = upd_resp.json()
            upd_code = int(upd_payload.get("code", -1))
            return {
                "ok": upd_code == 0,
                "non_fatal": True,
                "code": upd_code,
                "cover_updated": upd_code == 0,
                "message": scrub_rtmp_secrets(str(upd_payload.get("message") or upd_payload.get("msg") or "")),
            }
        except Exception as exc:
            safe_err = scrub_rtmp_secrets(str(exc))
            logger.warning("Non-fatal live cover upload skipped (%s): %s", type(exc).__name__, safe_err)
            return {
                "ok": False,
                "non_fatal": True,
                "error": safe_err,
            }

    def start_live(
        self,
        room_id: int,
        *,
        area_v2: int = DEFAULT_LIVE_AREA_V2,
        platform: str = "pc_link",
        qr_output_path: Optional[Path] = None,
    ) -> StartLiveResult:
        """Start Bilibili live broadcast (`POST /room/v1/Room/startLive`).

        - On `code == 60024`, generates a QR PNG for official Bilibili mobile face verification
          and returns `StartLiveResult(ok=False, status="face_auth_required", code=60024, ...)`.
        - On `code == 0`, assembles `rtmp_url` strictly in memory and returns a result whose
          `repr()` and `to_safe_dict()` mask all secrets.
        """
        if room_id <= 0:
            raise ValueError("room_id must be a positive integer")
        cookies, csrf = self._load_cookies_and_csrf()
        form_data = {
            "room_id": str(room_id),
            "area_v2": str(area_v2),
            "platform": platform,
            "csrf": csrf,
            "csrf_token": csrf,
        }
        resp = self._session.post(
            BILIBILI_LIVE_START_URL,
            data=form_data,
            cookies=cookies,
            headers=self._headers(),
            timeout=self.timeout_sec,
        )
        resp.raise_for_status()
        payload = resp.json()
        code = int(payload.get("code", -1))
        data = payload.get("data") or {}
        raw_msg = str(payload.get("message") or payload.get("msg") or "")

        if code == FACE_AUTH_REQUIRED_CODE:
            qr_content = str(data.get("qr") or data.get("qr_url") or "").strip()
            qr_path: Optional[Path] = None
            if qr_content:
                target_qr = Path(qr_output_path) if qr_output_path is not None else self.face_auth_qr_path
                matrix = encode_qr_matrix(qr_content)
                qr_path = render_qr_png(matrix, target_qr)
            return StartLiveResult(
                ok=False,
                status="face_auth_required",
                code=FACE_AUTH_REQUIRED_CODE,
                room_id=room_id,
                face_auth_qr_path=qr_path,
                message=(
                    "Bilibili face authentication required (code=60024). "
                    "Scan the generated QR PNG with the official Bilibili mobile app, then retry."
                ),
            )

        if code == 0:
            rtmp_info = data.get("rtmp") or {}
            rtmp_addr = str(rtmp_info.get("addr") or "").strip()
            rtmp_code = str(rtmp_info.get("code") or "").strip()
            rtmp_url = _assemble_rtmp_url(rtmp_addr, rtmp_code)
            if not rtmp_url:
                return StartLiveResult(
                    ok=False,
                    status="error",
                    code=code,
                    room_id=room_id,
                    message="Bilibili startLive returned code=0 but RTMP addr/code was empty",
                )
            return StartLiveResult(
                ok=True,
                status="live",
                code=0,
                room_id=room_id,
                rtmp_addr=rtmp_addr,
                rtmp_code=rtmp_code,
                rtmp_url=rtmp_url,
                message="Bilibili live session started",
            )

        return StartLiveResult(
            ok=False,
            status="error",
            code=code,
            room_id=room_id,
            message=scrub_rtmp_secrets(raw_msg) or f"startLive failed with code={code}",
        )

    def stop_live(self, room_id: int, *, platform: str = "pc_link") -> Dict[str, Any]:
        """Stop Bilibili live broadcast (`POST /room/v1/Room/stopLive`). Idempotent and safe for `finally:`."""
        if room_id <= 0:
            return {
                "ok": False,
                "code": -1,
                "room_id": "",
                "message": "Invalid room_id",
            }
        try:
            cookies, csrf = self._load_cookies_and_csrf()
            form_data = {
                "room_id": str(room_id),
                "platform": platform,
                "csrf": csrf,
                "csrf_token": csrf,
            }
            resp = self._session.post(
                BILIBILI_LIVE_STOP_URL,
                data=form_data,
                cookies=cookies,
                headers=self._headers(),
                timeout=self.timeout_sec,
            )
            resp.raise_for_status()
            payload = resp.json()
            code = int(payload.get("code", -1))
            msg = scrub_rtmp_secrets(str(payload.get("message") or payload.get("msg") or ""))
            return {
                "ok": code == 0,
                "code": code,
                "room_id": REDACTED_TOKEN,
                "message": msg or ("Live session stopped" if code == 0 else f"stopLive code={code}"),
            }
        except Exception as exc:
            safe_err = scrub_rtmp_secrets(str(exc))
            logger.warning("stop_live encountered an error (%s): %s", type(exc).__name__, safe_err)
            return {
                "ok": False,
                "code": -1,
                "room_id": REDACTED_TOKEN,
                "message": safe_err,
            }
