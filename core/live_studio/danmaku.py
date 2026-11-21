"""Bilibili live WebSocket binary protocol codec, async client, and mock danmaku source.

Implements the 16-byte big-endian Bilibili live framing specification including `proto_ver=2`
zlib decompression and JSON event parsing for `DANMU_MSG`, `SEND_GIFT`, and `INTERACT_WORD`.
Uses only stdlib + aiohttp + pydantic and discards raw viewer UIDs for PII safety.
"""

from __future__ import annotations

import asyncio
import json
import logging
import struct
import time
import zlib
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, Final, List, Literal, Optional, Sequence

import aiohttp
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

HEADER_STRUCT: Final[struct.Struct] = struct.Struct(">IHHII")
HEADER_SIZE: Final[int] = HEADER_STRUCT.size  # 16 bytes

PROTO_PLAIN_JSON: Final[int] = 0
PROTO_HEARTBEAT_INT: Final[int] = 1
PROTO_ZLIB: Final[int] = 2
PROTO_BROTLI: Final[int] = 3

OP_HEARTBEAT: Final[int] = 2
OP_HEARTBEAT_REPLY: Final[int] = 3
OP_MESSAGE: Final[int] = 5
OP_AUTH: Final[int] = 7
OP_AUTH_REPLY: Final[int] = 8

DEFAULT_WS_URL: Final[str] = "wss://broadcastlv.chat.bilibili.com:443/sub"
MAX_INFLATE_BYTES: Final[int] = 4 * 1024 * 1024
MAX_UNPACK_DEPTH: Final[int] = 4


class DanmakuEvent(BaseModel):
    """Normalized livestream event with zero raw UIDs."""

    event_type: Literal["danmaku", "gift", "enter", "system"]
    user_alias: str = "热心观众"
    text: str = ""
    gift_name: str = ""
    gift_count: int = 0
    timestamp: float = Field(default_factory=time.time)


@dataclass(frozen=True)
class DecodedPacket:
    """Single decoded Bilibili live WebSocket binary frame."""

    proto_ver: int
    operation: int
    seq_id: int
    body: bytes
    json_payload: Optional[Dict[str, Any]] = None
    popularity: Optional[int] = None


def pack_packet(
    body: bytes | str | Dict[str, Any],
    operation: int,
    proto_ver: int = PROTO_HEARTBEAT_INT,
    seq_id: int = 1,
    *,
    compress_if_zlib: bool = True,
) -> bytes:
    """Encode a Bilibili live binary frame with a 16-byte big-endian header.

    When `proto_ver == 2` and `compress_if_zlib=True`, `body` is automatically
    zlib-compressed so callers can wrap one or more concatenated inner frames.
    """
    if isinstance(body, dict):
        raw = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    elif isinstance(body, str):
        raw = body.encode("utf-8")
    else:
        raw = bytes(body)

    if proto_ver == PROTO_ZLIB and compress_if_zlib:
        raw = zlib.compress(raw)

    packet_len = HEADER_SIZE + len(raw)
    header = HEADER_STRUCT.pack(packet_len, HEADER_SIZE, proto_ver, operation, seq_id)
    return header + raw


def _safe_zlib_decompress(payload: bytes, max_bytes: int = MAX_INFLATE_BYTES) -> bytes:
    decompressor = zlib.decompressobj()
    inflated = decompressor.decompress(payload, max_bytes)
    if decompressor.unconsumed_tail:
        raise ValueError(f"Compressed packet exceeded safety cap of {max_bytes} bytes")
    return inflated


def unpack_packets(data: bytes, *, _depth: int = 0) -> List[DecodedPacket]:
    """Decode one or more concatenated Bilibili live binary frames.

    Recursively inflates `proto_ver == 2` zlib payloads while enforcing size and depth limits.
    """
    if _depth > MAX_UNPACK_DEPTH or not data:
        return []

    packets: List[DecodedPacket] = []
    offset = 0
    total_len = len(data)

    while offset + HEADER_SIZE <= total_len:
        packet_len, header_len, proto_ver, operation, seq_id = HEADER_STRUCT.unpack_from(data, offset)
        if header_len < HEADER_SIZE or packet_len < header_len or offset + packet_len > total_len:
            logger.debug(
                "Stopping unpack on malformed/truncated frame (packet_len=%s, header_len=%s, remaining=%s)",
                packet_len,
                header_len,
                total_len - offset,
            )
            break

        body = data[offset + header_len : offset + packet_len]
        offset += packet_len

        if proto_ver == PROTO_ZLIB:
            try:
                inflated = _safe_zlib_decompress(body)
            except (zlib.error, ValueError) as exc:
                logger.warning("Skipping corrupt or oversized zlib frame: %s", exc)
                continue
            packets.extend(unpack_packets(inflated, _depth=_depth + 1))
            continue

        if proto_ver == PROTO_BROTLI:
            try:
                import brotli

                inflated = brotli.decompress(body)
                if len(inflated) <= MAX_INFLATE_BYTES:
                    packets.extend(unpack_packets(inflated, _depth=_depth + 1))
            except Exception:
                logger.debug("Brotli frame skipped (optional brotli codec unavailable or invalid payload)")
            continue

        popularity: Optional[int] = None
        json_payload: Optional[Dict[str, Any]] = None

        if operation == OP_HEARTBEAT_REPLY and len(body) >= 4:
            popularity = struct.unpack(">I", body[:4])[0]
        elif body:
            stripped = body.lstrip()
            if stripped.startswith(b"{"):
                try:
                    parsed = json.loads(stripped.decode("utf-8", errors="replace"))
                    if isinstance(parsed, dict):
                        json_payload = parsed
                except json.JSONDecodeError:
                    logger.debug("Non-JSON payload in op=%s frame", operation)

        packets.append(
            DecodedPacket(
                proto_ver=proto_ver,
                operation=operation,
                seq_id=seq_id,
                body=body,
                json_payload=json_payload,
                popularity=popularity,
            )
        )

    return packets


def parse_bilibili_command(payload: Dict[str, Any], *, now: Optional[float] = None) -> Optional[DanmakuEvent]:
    """Convert a Bilibili `OP_MESSAGE` JSON command into a privacy-safe `DanmakuEvent`."""
    if not isinstance(payload, dict):
        return None
    cmd = str(payload.get("cmd", ""))
    ts = time.time() if now is None else now

    if cmd == "DANMU_MSG" or cmd.startswith("DANMU_MSG:"):
        info = payload.get("info")
        if not isinstance(info, list) or len(info) < 3:
            return None
        text = str(info[1]).strip()
        user_info = info[2] if isinstance(info[2], list) else []
        # Strictly ignore user_info[0] (raw numeric UID)
        user_alias = str(user_info[1]).strip() if len(user_info) > 1 and user_info[1] else "热心观众"
        return DanmakuEvent(
            event_type="danmaku",
            user_alias=user_alias,
            text=text,
            timestamp=ts,
        )

    if cmd == "SEND_GIFT":
        data = payload.get("data")
        if not isinstance(data, dict):
            return None
        user_alias = str(data.get("uname") or "神秘投喂官").strip()
        gift_name = str(data.get("giftName") or data.get("gift_name") or "小心心").strip()
        raw_count = data.get("num")
        if raw_count is None:
            raw_count = data.get("gift_count", 1)
        try:
            gift_count = max(1, int(raw_count)) if raw_count is not None else 1
        except (TypeError, ValueError):
            gift_count = 1
        action = str(data.get("action") or "投喂").strip()
        return DanmakuEvent(
            event_type="gift",
            user_alias=user_alias,
            text=f"{action}了 {gift_name} x{gift_count}",
            gift_name=gift_name,
            gift_count=gift_count,
            timestamp=ts,
        )

    if cmd == "INTERACT_WORD":
        data = payload.get("data")
        if not isinstance(data, dict):
            return None
        user_alias = str(data.get("uname") or "路过小伙伴").strip()
        raw_msg_type = data.get("msg_type", 1)
        try:
            msg_type = int(raw_msg_type)
        except (TypeError, ValueError):
            msg_type = 1
        action_text = {
            1: "进入了直播间",
            2: "关注了直播间",
            3: "分享了直播间",
        }.get(msg_type, "进入了直播间")
        return DanmakuEvent(
            event_type="enter",
            user_alias=user_alias,
            text=action_text,
            timestamp=ts,
        )

    return None


class BilibiliDanmakuClient:
    """Async anonymous Bilibili live danmaku client built on `aiohttp.ClientSession.ws_connect`."""

    def __init__(
        self,
        room_id: int,
        *,
        ws_url: Optional[str] = None,
        auth_token: str = "",
        heartbeat_interval: float = 30.0,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        if room_id <= 0:
            raise ValueError("room_id must be a positive integer")
        self.room_id = room_id
        self.real_room_id = room_id
        self.ws_url = ws_url
        self.auth_token = auth_token
        self.heartbeat_interval = max(1.0, heartbeat_interval)
        self._external_session = session
        self._session: Optional[aiohttp.ClientSession] = session
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._heartbeat_task: Optional[asyncio.Task[None]] = None
        self._closed = False
        self.popularity: int = 0
        self.authenticated: bool = False

    def build_auth_packet(self) -> bytes:
        """Build anonymous guest auth packet (`uid=0`, `protover=2`)."""
        payload: Dict[str, Any] = {
            "uid": 0,
            "roomid": self.real_room_id,
            "protover": PROTO_ZLIB,
            "platform": "web",
            "type": 2,
        }
        if self.auth_token:
            payload["key"] = self.auth_token
        return pack_packet(payload, operation=OP_AUTH, proto_ver=PROTO_HEARTBEAT_INT)

    @staticmethod
    def build_heartbeat_packet() -> bytes:
        """Build standard Bilibili live heartbeat frame."""
        return pack_packet(b"[object Object]", operation=OP_HEARTBEAT, proto_ver=PROTO_HEARTBEAT_INT)

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=15)
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
                ),
                "Origin": "https://live.bilibili.com",
            }
            self._session = aiohttp.ClientSession(timeout=timeout, headers=headers)
        return self._session

    async def _resolve_connection_info(self) -> tuple[str, str]:
        """Resolve real room ID and danmaku WebSocket host when no custom `ws_url` was passed."""
        if self.ws_url:
            return self.ws_url, self.auth_token

        session = await self._ensure_session()
        resolved_url = DEFAULT_WS_URL
        token = self.auth_token

        try:
            async with session.get(
                "https://api.live.bilibili.com/room/v1/Room/room_init",
                params={"id": str(self.room_id)},
            ) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    real_id = (data.get("data") or {}).get("room_id")
                    if isinstance(real_id, int) and real_id > 0:
                        self.real_room_id = real_id
        except Exception as exc:
            logger.debug("room_init fallback to raw room_id=%s: %s", self.room_id, exc)

        try:
            async with session.get(
                "https://api.live.bilibili.com/xlive/web-room/v1/index/getDanmuInfo",
                params={"id": str(self.real_room_id), "type": "0"},
            ) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    info = data.get("data") or {}
                    if isinstance(info.get("token"), str) and info["token"]:
                        token = info["token"]
                    host_list = info.get("host_list") or []
                    if host_list and isinstance(host_list[0], dict):
                        host = host_list[0].get("host")
                        wss_port = host_list[0].get("wss_port", 443)
                        if host:
                            resolved_url = f"wss://{host}:{wss_port}/sub"
        except Exception as exc:
            logger.debug("getDanmuInfo fallback to default WS endpoint: %s", exc)

        return resolved_url, token

    async def connect(self) -> None:
        """Open the WebSocket connection, send auth handshake, and launch heartbeat task."""
        self._closed = False
        session = await self._ensure_session()
        url, token = await self._resolve_connection_info()
        self.auth_token = token
        self._ws = await session.ws_connect(url, autoping=True, heartbeat=None)
        await self._ws.send_bytes(self.build_auth_packet())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(), name="bili-live-heartbeat")

    async def _heartbeat_loop(self) -> None:
        try:
            while not self._closed and self._ws is not None and not self._ws.closed:
                await asyncio.sleep(self.heartbeat_interval)
                if self._closed or self._ws is None or self._ws.closed:
                    break
                await self._ws.send_bytes(self.build_heartbeat_packet())
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.debug("Heartbeat loop ended: %s", exc)

    async def events(self) -> AsyncIterator[DanmakuEvent]:
        """Yield parsed `DanmakuEvent` objects from the live WebSocket stream."""
        if self._ws is None or self._ws.closed:
            await self.connect()
        assert self._ws is not None

        try:
            async for msg in self._ws:
                if self._closed:
                    break
                if msg.type == aiohttp.WSMsgType.BINARY:
                    for pkt in unpack_packets(msg.data):
                        if pkt.operation == OP_AUTH_REPLY:
                            self.authenticated = True
                        elif pkt.operation == OP_HEARTBEAT_REPLY and pkt.popularity is not None:
                            self.popularity = pkt.popularity
                        elif pkt.operation == OP_MESSAGE and pkt.json_payload is not None:
                            event = parse_bilibili_command(pkt.json_payload)
                            if event is not None:
                                yield event
                elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSED):
                    break
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.warning("WebSocket stream error: %s", self._ws.exception())
                    break
        finally:
            await self.close()

    async def close(self) -> None:
        """Stop heartbeat loop and cleanly disconnect WebSocket and owned HTTP session."""
        self._closed = True
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        self._ws = None

        if self._external_session is None and self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None


DEFAULT_MOCK_EVENTS: Final[tuple[tuple[Literal["danmaku", "gift", "enter", "system"], str, str, str, int], ...]] = (
    ("enter", "熬夜写代码的小蓝", "进入了直播间", "", 0),
    ("danmaku", "二次元策划师", "哈哈哈老板真的只有15个粉丝吗？第018期拍什么！", "", 0),
    ("danmaku", "封面颜控", "Gemini娘的4.9星高明度封面太亮眼了，大肥鱼不服气快反击！", "", 0),
    ("gift", "机房投喂官", "投喂了 小心心 x3", "小心心", 3),
    ("danmaku", "热舞观察员", "投票！018集拍大肥鱼和Gemini娘争夺账号主控权！", "", 0),
    ("danmaku", "剪辑学徒", "60FPS光流补帧顺滑吗，直播完切片能不能直接发B站？", "", 0),
    ("gift", "冲千粉赞助商", "投喂了 牛哇牛哇 x1", "牛哇牛哇", 1),
    ("danmaku", "早八打工人", "大肥鱼快别卷黑屏课件了，多来点双人整活小剧场！", "", 0),
)


class MockDanmakuSource:
    """Deterministic offline danmaku generator for OBS rehearsal and automated tests."""

    def __init__(
        self,
        *,
        interval_sec: float = 4.0,
        max_events: Optional[int] = None,
        custom_events: Optional[Sequence[DanmakuEvent]] = None,
    ) -> None:
        self.interval_sec = max(0.0, interval_sec)
        self.max_events = max_events
        self._custom_events = list(custom_events) if custom_events is not None else None
        self._closed = False

    async def events(self) -> AsyncIterator[DanmakuEvent]:
        """Yield rehearsal events at `interval_sec` cadence until closed or `max_events` reached."""
        emitted = 0
        idx = 0
        while not self._closed:
            if self.max_events is not None and emitted >= self.max_events:
                break
            if self._custom_events is not None:
                if not self._custom_events:
                    break
                template = self._custom_events[idx % len(self._custom_events)]
                event = template.model_copy(update={"timestamp": time.time()})
            else:
                etype, alias, text, gift_name, gift_count = DEFAULT_MOCK_EVENTS[idx % len(DEFAULT_MOCK_EVENTS)]
                event = DanmakuEvent(
                    event_type=etype,
                    user_alias=alias,
                    text=text,
                    gift_name=gift_name,
                    gift_count=gift_count,
                    timestamp=time.time(),
                )
            emitted += 1
            idx += 1
            yield event
            if self.max_events is not None and emitted >= self.max_events:
                break
            if self.interval_sec > 0:
                await asyncio.sleep(self.interval_sec)

    async def close(self) -> None:
        """Stop emitting mock events."""
        self._closed = True
