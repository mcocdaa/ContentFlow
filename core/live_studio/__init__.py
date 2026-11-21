"""ContentFlow Dual-AI Interactive Livestream MVP (`DeepSeek 蓝色大肥鱼 × Gemini娘`).

Lightweight async package built exclusively on stdlib + aiohttp + httpx + pydantic
(zero PyTorch/GPU overhead) so OBS NVENC livestreaming stays safely within the
24 GiB RAM / 8 GiB VRAM studio hardware envelope.
"""

from __future__ import annotations

from core.live_studio.danmaku import (
    HEADER_SIZE,
    OP_AUTH,
    OP_AUTH_REPLY,
    OP_HEARTBEAT,
    OP_HEARTBEAT_REPLY,
    OP_MESSAGE,
    BilibiliDanmakuClient,
    DanmakuEvent,
    DecodedPacket,
    MockDanmakuSource,
    pack_packet,
    parse_bilibili_command,
    unpack_packets,
)
from core.live_studio.director import (
    PERSONAS,
    DialogueResponder,
    DualAILiveDirector,
    HighlightMoment,
    HighlightTracker,
    OfflineBanterResponder,
    OpenAICompatibleResponder,
    PersonaProfile,
    PersonaTurn,
)
from core.live_studio.safety import (
    AI_DISCLOSURE_BANNER,
    REDACTED_TOKEN,
    GuardDecision,
    LiveComplianceGuard,
    redact_pii,
)
from core.live_studio.stage_server import (
    CHARACTER_ASSETS,
    LiveStageRuntime,
    StageServer,
    create_stage_app,
)

__all__ = [
    "AI_DISCLOSURE_BANNER",
    "CHARACTER_ASSETS",
    "HEADER_SIZE",
    "OP_AUTH",
    "OP_AUTH_REPLY",
    "OP_HEARTBEAT",
    "OP_HEARTBEAT_REPLY",
    "OP_MESSAGE",
    "PERSONAS",
    "REDACTED_TOKEN",
    "BilibiliDanmakuClient",
    "DanmakuEvent",
    "DecodedPacket",
    "DialogueResponder",
    "DualAILiveDirector",
    "GuardDecision",
    "HighlightMoment",
    "HighlightTracker",
    "LiveComplianceGuard",
    "LiveStageRuntime",
    "MockDanmakuSource",
    "OfflineBanterResponder",
    "OpenAICompatibleResponder",
    "PersonaProfile",
    "PersonaTurn",
    "StageServer",
    "create_stage_app",
    "pack_packet",
    "parse_bilibili_command",
    "redact_pii",
    "unpack_packets",
]
