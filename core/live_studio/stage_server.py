"""Pure `aiohttp.web` stage overlay server and runtime coordinator for OBS Browser Source.

Serves:
- `GET /`: 1920x1080 bright anime broadcast overlay (`stage.html`)
- `GET /ws`: live WebSocket push for dialogue turns, sanitized danmaku, and highlights
- `GET /api/status`: JSON telemetry & compliance status (zero PII / zero secrets)
- `GET /assets/characters/{name}`: allowlisted canonical character portraits
- `POST /api/mock-danmaku`: rehearsal injection hook (enabled only in mock mode)
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Final, Literal, Optional, Protocol, Set

from aiohttp import WSMsgType, web

from core.live_studio.danmaku import DanmakuEvent
from core.live_studio.director import PERSONAS, DualAILiveDirector, PersonaTurn
from core.live_studio.safety import AI_DISCLOSURE_BANNER

logger = logging.getLogger(__name__)

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent.parent
STAGE_HTML_PATH: Final[Path] = Path(__file__).resolve().with_name("stage.html")

CHARACTER_ASSETS: Final[Dict[str, str]] = {
    "dafeiyu": "library/characters/deepseek_dafeiyu/master_reference.jpg",
    "deepseek_dafeiyu": "library/characters/deepseek_dafeiyu/master_reference.jpg",
    "gemini": "library/characters/gemini_neko/gemini_canonical_full.png",
    "gemini_neko": "library/characters/gemini_neko/gemini_canonical_full.png",
}


class DanmakuEventSource(Protocol):
    """Minimal protocol shared by `BilibiliDanmakuClient` and `MockDanmakuSource`."""

    def events(self) -> Any: ...

    async def close(self) -> None: ...


class StageServer:
    """State holder and HTTP/WebSocket handler suite for the OBS broadcast stage."""

    def __init__(
        self,
        director: Optional[DualAILiveDirector] = None,
        *,
        mode: Literal["mock", "live"] = "mock",
        room_id: Optional[int] = None,
        repo_root: Optional[Path] = None,
        allow_mock_inject: Optional[bool] = None,
    ) -> None:
        self.director = director or DualAILiveDirector()
        self.mode: Literal["mock", "live"] = mode
        self.room_id = room_id
        self.repo_root = Path(repo_root) if repo_root is not None else REPO_ROOT
        self.allow_mock_inject = (mode == "mock") if allow_mock_inject is None else allow_mock_inject
        self.started_at = time.time()
        self.active_speaker: Optional[str] = None
        self._ws_clients: Set[web.WebSocketResponse] = set()

    def resolve_character_asset(self, name: str) -> Optional[Path]:
        """Resolve an allowlisted character asset key without allowing path traversal."""
        rel_path = CHARACTER_ASSETS.get(name.strip().lower())
        if rel_path is None:
            return None
        candidate = (self.repo_root / rel_path).resolve()
        try:
            candidate.relative_to(self.repo_root.resolve())
        except ValueError:
            return None
        if not candidate.is_file():
            return None
        return candidate

    def build_status(self) -> Dict[str, Any]:
        """Build a privacy-safe JSON status payload for `/api/status` and WS init."""
        return {
            "status": "running",
            "mode": self.mode,
            "room_id": self.room_id,
            "uptime_sec": round(max(0.0, time.time() - self.started_at), 2),
            "connected_clients": len(self._ws_clients),
            "active_speaker": self.active_speaker,
            "turn_count": len(self.director.history),
            "pending_events": self.director.pending_count(),
            "danmaku_count": self.director.danmaku_count,
            "gift_count": self.director.gift_count,
            "highlight_count": len(self.director.highlight_tracker.moments),
            "follower_count": self.director.follower_count,
            "follower_goal": self.director.follower_goal,
            "llm_mode": self.director.responder.backend_name,
            "ai_disclosure_banner": AI_DISCLOSURE_BANNER,
            "safety": self.director.safety_guard.get_stats(),
            "assets": {
                "dafeiyu": "/assets/characters/dafeiyu",
                "gemini": "/assets/characters/gemini",
            },
        }

    def build_init_payload(self) -> Dict[str, Any]:
        """Initial state snapshot sent to newly connected OBS Browser Source clients."""
        return {
            "type": "init",
            "status": self.build_status(),
            "personas": {
                sid: {
                    "speaker_id": profile.speaker_id,
                    "display_name": profile.display_name,
                    "short_name": profile.short_name,
                    "accent_color": profile.accent_color,
                    "tagline": profile.tagline,
                    "asset_url": f"/assets/characters/{profile.asset_key}",
                }
                for sid, profile in PERSONAS.items()
            },
            "recent_turns": [t.to_dict() for t in self.director.history],
            "recent_danmaku": list(self.director.recent_danmaku),
            "recent_highlights": [m.to_dict() for m in self.director.highlight_tracker.moments[-6:]],
        }

    async def broadcast(self, payload: Dict[str, Any]) -> int:
        """Broadcast a JSON message to all connected WebSocket clients."""
        if not self._ws_clients:
            return 0
        encoded = json.dumps(payload, ensure_ascii=False)
        stale: list[web.WebSocketResponse] = []
        sent = 0
        for ws in list(self._ws_clients):
            if ws.closed:
                stale.append(ws)
                continue
            try:
                await ws.send_str(encoded)
                sent += 1
            except Exception:
                stale.append(ws)
        for ws in stale:
            self._ws_clients.discard(ws)
        return sent

    async def ingest_event(self, event: DanmakuEvent) -> Optional[DanmakuEvent]:
        """Sanitize, queue, and broadcast a viewer event to the overlay ticker."""
        sanitized = self.director.enqueue_event(event)
        if sanitized is None:
            return None
        await self.broadcast(
            {
                "type": "danmaku",
                "event": sanitized.model_dump(),
                "status": self.build_status(),
            }
        )
        return sanitized

    async def emit_turn(self, turn: PersonaTurn) -> None:
        """Record active speaker and broadcast a spoken turn (and highlight if tagged)."""
        self.active_speaker = turn.speaker_id
        await self.broadcast(
            {
                "type": "turn",
                "turn": turn.to_dict(),
                "status": self.build_status(),
            }
        )
        if turn.is_highlight and self.director.highlight_tracker.moments:
            latest = self.director.highlight_tracker.moments[-1]
            await self.broadcast({"type": "highlight", "highlight": latest.to_dict()})

    async def close_websockets(self) -> None:
        """Close all connected stage overlay WebSocket clients cleanly."""
        clients = list(self._ws_clients)
        self._ws_clients.clear()
        for ws in clients:
            if not ws.closed:
                with contextlib.suppress(Exception):
                    await ws.close()

    async def handle_index(self, request: web.Request) -> web.StreamResponse:
        if not STAGE_HTML_PATH.is_file():
            raise web.HTTPNotFound(text="stage.html not found")
        return web.FileResponse(STAGE_HTML_PATH, headers={"Cache-Control": "no-cache"})

    async def handle_status(self, request: web.Request) -> web.Response:
        return web.json_response(self.build_status())

    async def handle_character_asset(self, request: web.Request) -> web.StreamResponse:
        name = request.match_info.get("name", "")
        asset_path = self.resolve_character_asset(name)
        if asset_path is None:
            raise web.HTTPNotFound(text="Character asset not found")
        return web.FileResponse(asset_path, headers={"Cache-Control": "public, max-age=3600"})

    async def handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=25.0)
        await ws.prepare(request)
        self._ws_clients.add(ws)
        try:
            await ws.send_str(json.dumps(self.build_init_payload(), ensure_ascii=False))
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(data, dict) and data.get("type") == "ping":
                        await ws.send_str(json.dumps({"type": "pong", "ts": time.time()}))
                elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                    break
        finally:
            self._ws_clients.discard(ws)
        return ws

    async def handle_mock_danmaku(self, request: web.Request) -> web.Response:
        if not self.allow_mock_inject:
            return web.json_response({"accepted": False, "reason": "disabled_in_live_mode"}, status=403)
        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"accepted": False, "reason": "invalid_json"}, status=400)
        if not isinstance(payload, dict):
            return web.json_response({"accepted": False, "reason": "invalid_payload"}, status=400)

        try:
            event = DanmakuEvent(
                event_type=payload.get("event_type", "danmaku"),
                user_alias=str(payload.get("user_alias") or "彩排观众"),
                text=str(payload.get("text") or ""),
                gift_name=str(payload.get("gift_name") or ""),
                gift_count=int(payload.get("gift_count") or 0),
            )
        except Exception:
            return web.json_response({"accepted": False, "reason": "schema_validation_failed"}, status=400)

        sanitized = await self.ingest_event(event)
        if sanitized is None:
            return web.json_response({"accepted": False, "reason": "blocked_by_compliance_guard"}, status=422)
        return web.json_response({"accepted": True, "event": sanitized.model_dump()})


STAGE_SERVER_KEY: Final[web.AppKey[StageServer]] = web.AppKey("stage_server", StageServer)


def create_stage_app(stage_server: Optional[StageServer] = None) -> web.Application:
    """Create the `aiohttp.web.Application` wired to `StageServer` routes."""
    server = stage_server or StageServer()
    app = web.Application()
    app[STAGE_SERVER_KEY] = server
    app.router.add_get("/", server.handle_index)
    app.router.add_get("/ws", server.handle_websocket)
    app.router.add_get("/api/status", server.handle_status)
    app.router.add_get("/assets/characters/{name}", server.handle_character_asset)
    app.router.add_post("/api/mock-danmaku", server.handle_mock_danmaku)

    async def _on_shutdown(_app: web.Application) -> None:
        await server.close_websockets()

    app.on_shutdown.append(_on_shutdown)
    return app


class LiveStageRuntime:
    """Full async runtime combining `StageServer`, `DanmakuEventSource`, and `DualAILiveDirector`."""

    def __init__(
        self,
        *,
        stage_server: StageServer,
        danmaku_source: DanmakuEventSource,
        host: str = "127.0.0.1",
        port: int = 8765,
        idle_interval_sec: float = 5.5,
        turn_pacing_sec: float = 2.2,
    ) -> None:
        self.stage_server = stage_server
        self.danmaku_source = danmaku_source
        self.host = host
        self.port = port
        self.idle_interval_sec = max(0.2, idle_interval_sec)
        self.turn_pacing_sec = max(0.05, turn_pacing_sec)
        self.app = create_stage_app(stage_server)
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._tasks: list[asyncio.Task[None]] = []
        self._stop_event = asyncio.Event()
        self.bound_port: int = port

    async def _danmaku_pump(self) -> None:
        try:
            async for event in self.danmaku_source.events():
                if self._stop_event.is_set():
                    break
                await self.stage_server.ingest_event(event)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.warning("Danmaku source loop stopped: %s", exc)

    async def _director_loop(self) -> None:
        try:
            # Immediately emit opening line so OBS Browser Source is lively on load
            opening_turn = await self.stage_server.director.next_turn(wait_timeout=0.0)
            await self.stage_server.emit_turn(opening_turn)
            while not self._stop_event.is_set():
                await asyncio.sleep(self.turn_pacing_sec)
                if self._stop_event.is_set():
                    break
                turn = await self.stage_server.director.next_turn(wait_timeout=self.idle_interval_sec)
                await self.stage_server.emit_turn(turn)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.warning("Director loop error: %s", exc)

    async def start(self) -> None:
        """Start the HTTP/WS server and background danmaku/director tasks."""
        self._stop_event.clear()
        self._runner = web.AppRunner(self.app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, host=self.host, port=self.port)
        await self._site.start()

        # Resolve actual bound port (helpful when port=0 in tests)
        internal_server = getattr(self._site, "_server", None)
        sockets = getattr(internal_server, "sockets", None)
        if sockets:
            sockname = sockets[0].getsockname()
            if isinstance(sockname, tuple) and len(sockname) >= 2:
                self.bound_port = int(sockname[1])

        self._tasks = [
            asyncio.create_task(self._danmaku_pump(), name="live-danmaku-pump"),
            asyncio.create_task(self._director_loop(), name="live-director-loop"),
        ]

    async def wait_until_stopped(self, *, duration_sec: Optional[float] = None) -> None:
        """Wait until `request_stop()` is called or `duration_sec` elapses."""
        if duration_sec is not None and duration_sec > 0:
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._stop_event.wait(), timeout=duration_sec)
        else:
            await self._stop_event.wait()

    async def stop(self) -> None:
        """Gracefully cancel tasks, close danmaku source, and shut down aiohttp server."""
        self._stop_event.set()
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()

        with contextlib.suppress(Exception):
            await self.danmaku_source.close()

        await self.stage_server.close_websockets()

        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
            self._site = None

    async def run(self, *, duration_sec: Optional[float] = None) -> None:
        """Run the livestream studio until stopped or `duration_sec` elapses."""
        await self.start()
        try:
            if duration_sec is not None and duration_sec > 0:
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(self._stop_event.wait(), timeout=duration_sec)
            else:
                await self._stop_event.wait()
        finally:
            await self.stop()

    def request_stop(self) -> None:
        """Signal `run()` to exit cleanly."""
        self._stop_event.set()
