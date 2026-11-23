"""Pluggable External Audio Generation Router for ContentFlow (Kaizen Slices K4 & K6).

Provides a unified, zero-key-safe routing abstraction for:
- Expressive Speech (TTS) & Canonical Character Voice Profiles (K6):
  `minimax_speech` (MINIMAX_API_KEY) -> `fish_audio` (FISH_AUDIO_API_KEY) -> `local_kokoro` (LocalNeuralTTS)
  Supports multi-character persona profiles (`dafeiyu`, `gemini_neko`, `yowane_haku`),
  cross-provider emotion normalization, natural zero-chipmunk speed bounds (`<= 1.18x`),
  and serial multi-character dialogue batch synthesis (`synthesize_dialogue`).
- Background Music & Accompaniment (BGM):
  `minimax_music` (MINIMAX_API_KEY) -> `suno` (SUNO_API_KEY) -> `bilibili_bgm_hunter` (BilibiliBgmHunter)

Local fallback backends (`LocalNeuralTTS` and `BilibiliBgmHunter`) are strictly lazy-imported
so importing this module never pulls PyTorch/Kokoro into memory, and `LocalNeuralTTS.close()`
is always invoked inside a `finally` block per the 24 GiB RAM / 8 GiB VRAM rule.
"""

from __future__ import annotations

import base64
import inspect
import io
import json
import logging
import os
import re
import subprocess
import tempfile
import time
import urllib.parse
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

import requests

from config.settings import (
    AUDIO_MUSIC_PROVIDER_PRIORITY,
    AUDIO_SPEECH_PROVIDER_PRIORITY,
    DEFAULT_FISH_AUDIO_BASE_URL,
    DEFAULT_MINIMAX_BASE_URL,
    DEFAULT_MINIMAX_MUSIC_MODEL,
    DEFAULT_MINIMAX_SPEECH_MODEL,
    DEFAULT_MINIMAX_SPEECH_VOICE,
    DEFAULT_SUNO_BASE_URL,
)

logger = logging.getLogger(__name__)

_PLACEHOLDER_VALUES = {
    "",
    "dummy_minimax_key",
    "dummy_fish_audio_key",
    "dummy_suno_key",
    "your_api_key",
    "your_minimax_api_key",
    "your_fish_audio_api_key",
    "your_suno_api_key",
    "changeme",
    "replace_me",
}

_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")
_SECRET_ENV_KEYS = (
    "MINIMAX_API_KEY",
    "MINIMAX_GROUP_ID",
    "FISH_AUDIO_API_KEY",
    "FISH_AUDIO_REFERENCE_ID",
    "FISH_AUDIO_REF_DAFEIYU",
    "FISH_AUDIO_REF_GEMINI_NEKO",
    "FISH_AUDIO_REF_YOWANE_HAKU",
    "SUNO_API_KEY",
)

MIN_PROFILE_AUTO_SPEED = 0.80
MAX_PROFILE_AUTO_SPEED = 1.18
MINIMAX_VALID_EMOTIONS = frozenset({"happy", "sad", "angry", "fearful", "disgusted", "surprised", "neutral", "calm"})
VERIFIED_FREE_EDGE_TTS_VOICES: frozenset[str] = frozenset(
    {
        "zh-CN-XiaoxiaoNeural",
        "zh-CN-XiaoyiNeural",
        "zh-CN-YunjianNeural",
        "zh-CN-YunxiNeural",
        "zh-CN-YunxiaNeural",
        "zh-CN-YunyangNeural",
        "zh-CN-liaoning-XiaobeiNeural",
        "zh-CN-shaanxi-XiaoniNeural",
        "zh-HK-HiuGaaiNeural",
        "zh-HK-HiuMaanNeural",
        "zh-HK-WanLungNeural",
        "zh-TW-HsiaoChenNeural",
        "zh-TW-HsiaoYuNeural",
        "zh-TW-YunJheNeural",
    }
)


@dataclass(frozen=True)
class EmotionSpec:
    """Cross-provider expressive emotion normalization with subtle natural prosody multiplier."""

    canonical: str
    minimax_emotion: str
    fish_emotion: str
    speed_multiplier: float = 1.0


EMOTION_SPECS: Dict[str, EmotionSpec] = {
    "neutral": EmotionSpec(
        canonical="neutral", minimax_emotion="neutral", fish_emotion="neutral", speed_multiplier=1.00
    ),
    "happy": EmotionSpec(canonical="happy", minimax_emotion="happy", fish_emotion="happy", speed_multiplier=1.02),
    "excited": EmotionSpec(canonical="excited", minimax_emotion="happy", fish_emotion="excited", speed_multiplier=1.04),
    "sad": EmotionSpec(canonical="sad", minimax_emotion="sad", fish_emotion="sad", speed_multiplier=0.94),
    "angry": EmotionSpec(canonical="angry", minimax_emotion="angry", fish_emotion="angry", speed_multiplier=1.03),
    "surprised": EmotionSpec(
        canonical="surprised", minimax_emotion="surprised", fish_emotion="surprised", speed_multiplier=1.03
    ),
    "fearful": EmotionSpec(
        canonical="fearful", minimax_emotion="fearful", fish_emotion="fearful", speed_multiplier=1.01
    ),
    "disgusted": EmotionSpec(
        canonical="disgusted", minimax_emotion="disgusted", fish_emotion="disgusted", speed_multiplier=0.98
    ),
    "calm": EmotionSpec(canonical="calm", minimax_emotion="calm", fish_emotion="calm", speed_multiplier=0.96),
    "sarcastic": EmotionSpec(
        canonical="sarcastic", minimax_emotion="disgusted", fish_emotion="sarcastic", speed_multiplier=1.01
    ),
    "lively": EmotionSpec(canonical="lively", minimax_emotion="happy", fish_emotion="excited", speed_multiplier=1.03),
    "hype": EmotionSpec(canonical="hype", minimax_emotion="happy", fish_emotion="excited", speed_multiplier=1.05),
    "teasing": EmotionSpec(canonical="teasing", minimax_emotion="happy", fish_emotion="playful", speed_multiplier=1.02),
    "smug": EmotionSpec(canonical="smug", minimax_emotion="happy", fish_emotion="confident", speed_multiplier=1.00),
    "shocked": EmotionSpec(
        canonical="shocked", minimax_emotion="surprised", fish_emotion="shocked", speed_multiplier=1.04
    ),
    "grateful": EmotionSpec(
        canonical="grateful", minimax_emotion="happy", fish_emotion="grateful", speed_multiplier=0.98
    ),
    "focused": EmotionSpec(canonical="focused", minimax_emotion="calm", fish_emotion="serious", speed_multiplier=0.98),
    "deadpan": EmotionSpec(canonical="deadpan", minimax_emotion="calm", fish_emotion="deadpan", speed_multiplier=0.95),
    "tsundere": EmotionSpec(
        canonical="tsundere", minimax_emotion="angry", fish_emotion="tsundere", speed_multiplier=1.02
    ),
}

_EMOTION_ALIASES: Dict[str, str] = {
    "开心": "happy",
    "高兴": "happy",
    "元气": "lively",
    "兴奋": "excited",
    "高能": "hype",
    "生气": "angry",
    "傲娇": "tsundere",
    "破防": "shocked",
    "吐槽": "sarcastic",
    "难过": "sad",
    "委屈": "sad",
    "惊讶": "surprised",
    "平静": "calm",
    "清冷": "calm",
    "佛系": "calm",
    "淡定": "deadpan",
}


def resolve_emotion_spec(emotion: Optional[str], default: str = "neutral") -> EmotionSpec:
    """Normalizes English/Chinese/livestream emotion labels to provider-specific EmotionSpec."""
    raw = (emotion or "").strip()
    if not raw:
        raw = (default or "neutral").strip() or "neutral"
    norm = raw.lower()
    target_key = _EMOTION_ALIASES.get(raw) or _EMOTION_ALIASES.get(norm) or norm
    if target_key in EMOTION_SPECS:
        return EMOTION_SPECS[target_key]
    mm_emo = norm if norm in MINIMAX_VALID_EMOTIONS else "neutral"
    return EmotionSpec(canonical=norm, minimax_emotion=mm_emo, fish_emotion=norm, speed_multiplier=1.0)


@dataclass(frozen=True)
class CharacterVoiceProfile:
    """Canonical multi-provider expressive voice profile for a studio character (K6 & K9)."""

    character_id: str
    display_name: str
    aliases: Tuple[str, ...]
    persona_note: str
    default_emotion: str
    default_speed: float
    minimax_voice_id: str
    minimax_pitch: int
    minimax_env_var: str
    fish_env_var: str
    local_kokoro_voice: str
    edge_tts_voice: str
    edge_tts_pitch: str = "+0Hz"


CHARACTER_VOICE_PROFILES: Dict[str, CharacterVoiceProfile] = {
    "dafeiyu": CharacterVoiceProfile(
        character_id="dafeiyu",
        display_name="DeepSeek 蓝色大肥鱼",
        aliases=("dafeiyu", "deepseek_dafeiyu", "deepseek", "大肥鱼", "蓝色大肥鱼"),
        persona_note="理智犀利又容易被点破防的硬核吐槽少女鱼",
        default_emotion="happy",
        default_speed=1.04,
        minimax_voice_id="female-yujie",
        minimax_pitch=0,
        minimax_env_var="MINIMAX_VOICE_DAFEIYU",
        fish_env_var="FISH_AUDIO_REF_DAFEIYU",
        local_kokoro_voice="zf_018",
        edge_tts_voice="zh-CN-XiaoxiaoNeural",
        edge_tts_pitch="-2Hz",
    ),
    "gemini_neko": CharacterVoiceProfile(
        character_id="gemini_neko",
        display_name="Gemini娘",
        aliases=("gemini_neko", "gemini", "gemini娘", "gemini猫", "猫娘"),
        persona_note="元气自信、4.9★ 高明度视觉卷王猫娘",
        default_emotion="excited",
        default_speed=1.06,
        minimax_voice_id="female-shaonv",
        minimax_pitch=1,
        minimax_env_var="MINIMAX_VOICE_GEMINI_NEKO",
        fish_env_var="FISH_AUDIO_REF_GEMINI_NEKO",
        local_kokoro_voice="zf_001",
        edge_tts_voice="zh-CN-XiaoyiNeural",
        edge_tts_pitch="+4Hz",
    ),
    "yowane_haku": CharacterVoiceProfile(
        character_id="yowane_haku",
        display_name="弱音ハク",
        aliases=("yowane_haku", "yowane", "haku", "弱音", "弱音ハク"),
        persona_note="清冷佛系、关键时刻一锤定音的社畜御姐前辈",
        default_emotion="calm",
        default_speed=0.98,
        minimax_voice_id="female-chengshu",
        minimax_pitch=-1,
        minimax_env_var="MINIMAX_VOICE_YOWANE_HAKU",
        fish_env_var="FISH_AUDIO_REF_YOWANE_HAKU",
        local_kokoro_voice="zf_004",
        edge_tts_voice="zh-TW-HsiaoYuNeural",
        edge_tts_pitch="-4Hz",
    ),
}

_CHARACTER_ALIAS_INDEX: Dict[str, str] = {}
for _cid, _prof in CHARACTER_VOICE_PROFILES.items():
    _CHARACTER_ALIAS_INDEX[_cid.lower()] = _cid
    for _alias in _prof.aliases:
        _CHARACTER_ALIAS_INDEX[_alias.strip().lower()] = _cid


def resolve_character_profile(character: str) -> CharacterVoiceProfile:
    """Resolves a character ID or Chinese/English alias to its canonical CharacterVoiceProfile."""
    key = (character or "").strip().lower()
    if key in _CHARACTER_ALIAS_INDEX:
        return CHARACTER_VOICE_PROFILES[_CHARACTER_ALIAS_INDEX[key]]
    supported = ", ".join(CHARACTER_VOICE_PROFILES.keys())
    raise ValueError(f"Unknown character voice profile {character!r}. Supported: {supported}")


def _is_configured_secret(val: Optional[str]) -> bool:
    """Returns True when val is a non-empty, non-placeholder credential string."""
    if not val or not isinstance(val, str):
        return False
    cleaned = val.strip()
    return bool(cleaned) and cleaned.lower() not in _PLACEHOLDER_VALUES


def _sanitize_endpoint(url: Optional[str]) -> Optional[str]:
    """Removes query parameters and userinfo from an endpoint URL for safe status display."""
    if not url:
        return None
    stripped = url.strip()
    if not stripped:
        return None
    parsed = urllib.parse.urlsplit(stripped)
    if parsed.scheme and parsed.hostname:
        netloc = parsed.hostname
        if parsed.port:
            netloc = f"{netloc}:{parsed.port}"
        path = parsed.path.rstrip("/")
        return f"{parsed.scheme}://{netloc}{path}"
    return stripped.split("?", 1)[0].rstrip("/")


def _redact_secrets(message: str, secrets: Iterable[str]) -> str:
    """Replaces any accidental occurrence of configured secret values with '<REDACTED>'."""
    sanitized = message
    for secret in secrets:
        if secret and len(secret) >= 4:
            sanitized = sanitized.replace(secret, "<REDACTED>")
    return sanitized


def _decode_inline_audio(raw_audio: str) -> bytes:
    """Decodes hex-encoded (MiniMax default) or base64-encoded audio payload strings."""
    cleaned = raw_audio.strip()
    if not cleaned:
        raise RuntimeError("Empty inline audio payload")
    if cleaned.startswith("data:") and "," in cleaned:
        cleaned = cleaned.split(",", 1)[1].strip()
    if len(cleaned) % 2 == 0 and _HEX_RE.match(cleaned):
        return bytes.fromhex(cleaned)
    return base64.b64decode(cleaned)


def _detect_wav_sample_rate(audio_bytes: bytes, default_sr: int) -> int:
    """Reads sample rate from a WAV header if applicable, falling back to default_sr."""
    if len(audio_bytes) >= 44 and audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
        try:
            with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
                return int(wf.getframerate())
        except Exception:
            return default_sr
    return default_sr


def _write_pcm16_wav(samples: Any, output_wav: Path, sample_rate: int) -> None:
    """Writes a mono float waveform in [-1.0, 1.0] to a 16-bit PCM WAV file."""
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(samples, "clip") and hasattr(samples, "astype") and hasattr(samples, "tobytes"):
        pcm_bytes = (samples.clip(-1.0, 1.0) * 32767.0).astype("<i2").tobytes()
    else:
        from array import array

        pcm = array(
            "h",
            (max(-32767, min(32767, int(round(float(x) * 32767.0)))) for x in samples),
        )
        pcm_bytes = pcm.tobytes()

    with wave.open(str(output_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)


@dataclass
class SpeechRequest:
    """Unified request specification for expressive TTS synthesis."""

    text: str
    output_path: Union[str, Path]
    emotion: Optional[str] = None
    voice: Optional[str] = None
    speed: Optional[float] = None
    provider: Optional[str] = None
    character: Optional[str] = None
    pitch: Optional[int] = None


@dataclass
class DialogueLine:
    """Single scripted utterance in a multi-character ensemble dialogue batch (K6)."""

    character: str
    text: str
    emotion: Optional[str] = None
    voice: Optional[str] = None
    speed: Optional[float] = None
    pitch: Optional[int] = None
    provider: Optional[str] = None
    pause_after_sec: float = 0.25
    line_id: Optional[str] = None


@dataclass
class SpeechResult:
    """Result metadata returned by AudioGenerationRouter.synthesize_speech."""

    provider: str
    audio_path: Path
    sample_rate: int
    used_fallback: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "audio_path": str(self.audio_path),
            "sample_rate": self.sample_rate,
            "used_fallback": self.used_fallback,
            "metadata": dict(self.metadata),
        }


@dataclass
class DialogueResult:
    """Result bundle & manifest path returned by AudioGenerationRouter.synthesize_dialogue."""

    lines: List[Dict[str, Any]]
    providers_used: List[str]
    used_fallback: bool
    output_dir: Path
    manifest_path: Optional[Path] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lines": [dict(line) for line in self.lines],
            "providers_used": list(self.providers_used),
            "used_fallback": self.used_fallback,
            "output_dir": str(self.output_dir),
            "manifest_path": str(self.manifest_path) if self.manifest_path is not None else None,
        }


@dataclass
class MusicRequest:
    """Unified request specification for AI music generation or BGM extraction."""

    prompt: str
    output_path: Union[str, Path]
    duration_sec: float = 15.0
    lyrics: str = ""
    instrumental: bool = True
    style: str = ""
    provider: Optional[str] = None
    bgm_query: Optional[str] = None
    bgm_bvid: Optional[str] = None


@dataclass
class MusicResult:
    """Result metadata returned by AudioGenerationRouter.generate_music."""

    provider: str
    audio_path: Path
    credits_line: str
    used_fallback: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "audio_path": str(self.audio_path),
            "credits_line": self.credits_line,
            "used_fallback": self.used_fallback,
            "metadata": dict(self.metadata),
        }


@dataclass
class ProviderStatus:
    """Sanitized configuration and availability report for a single audio provider."""

    name: str
    kind: str
    configured: bool
    available: bool
    is_fallback: bool
    required_env: List[str] = field(default_factory=list)
    optional_env: List[str] = field(default_factory=list)
    env_configured: Dict[str, bool] = field(default_factory=dict)
    active_model: Optional[str] = None
    endpoint: Optional[str] = None
    status: str = "not_configured"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "configured": self.configured,
            "available": self.available,
            "is_fallback": self.is_fallback,
            "required_env": list(self.required_env),
            "optional_env": list(self.optional_env),
            "env_configured": dict(self.env_configured),
            "active_model": self.active_model,
            "endpoint": self.endpoint,
            "status": self.status,
        }


class AudioGenerationRouter:
    """Routes speech & music requests across pluggable external APIs with zero-key local fallbacks."""

    def __init__(
        self,
        env: Optional[Mapping[str, str]] = None,
        session: Optional[requests.Session] = None,
        local_tts_factory: Optional[Callable[[], Any]] = None,
        bgm_hunter_factory: Optional[Callable[[], Any]] = None,
        timeout_sec: float = 60.0,
        poll_interval_sec: float = 2.0,
        max_poll_attempts: int = 15,
    ) -> None:
        self._env: Mapping[str, str] = dict(env) if env is not None else os.environ
        self.session: requests.Session = session if session is not None else requests.Session()
        self._local_tts_factory = local_tts_factory
        self._bgm_hunter_factory = bgm_hunter_factory
        self.timeout_sec = float(timeout_sec)
        self.poll_interval_sec = float(poll_interval_sec)
        self.max_poll_attempts = max(1, int(max_poll_attempts))

    def _get_env(self, key: str) -> Optional[str]:
        val = self._env.get(key)
        if val is None:
            return None
        cleaned = str(val).strip()
        return cleaned if cleaned else None

    def _has_secret(self, key: str) -> bool:
        return _is_configured_secret(self._get_env(key))

    def _configured_secret_values(self) -> List[str]:
        values: List[str] = []
        for k in _SECRET_ENV_KEYS:
            v = self._get_env(k)
            if v and _is_configured_secret(v):
                values.append(v)
        return values

    def _sanitize_error(self, exc: Exception) -> str:
        return _redact_secrets(str(exc), self._configured_secret_values())

    def get_speech_provider_statuses(self) -> List[ProviderStatus]:
        """Returns sanitized status objects for all speech providers in priority order."""
        minimax_ok = self._has_secret("MINIMAX_API_KEY")
        minimax_model = self._get_env("MINIMAX_SPEECH_MODEL") or DEFAULT_MINIMAX_SPEECH_MODEL
        minimax_url = _sanitize_endpoint(self._get_env("MINIMAX_BASE_URL") or DEFAULT_MINIMAX_BASE_URL)

        fish_ok = self._has_secret("FISH_AUDIO_API_KEY")
        fish_url = _sanitize_endpoint(self._get_env("FISH_AUDIO_BASE_URL") or DEFAULT_FISH_AUDIO_BASE_URL)

        return [
            ProviderStatus(
                name="minimax_speech",
                kind="speech",
                configured=minimax_ok,
                available=minimax_ok,
                is_fallback=False,
                required_env=["MINIMAX_API_KEY"],
                optional_env=["MINIMAX_GROUP_ID", "MINIMAX_SPEECH_MODEL", "MINIMAX_BASE_URL"],
                env_configured={
                    "MINIMAX_API_KEY": minimax_ok,
                    "MINIMAX_GROUP_ID": self._has_secret("MINIMAX_GROUP_ID"),
                    "MINIMAX_SPEECH_MODEL": self._get_env("MINIMAX_SPEECH_MODEL") is not None,
                    "MINIMAX_BASE_URL": self._get_env("MINIMAX_BASE_URL") is not None,
                },
                active_model=minimax_model,
                endpoint=minimax_url,
                status="configured" if minimax_ok else "not_configured",
            ),
            ProviderStatus(
                name="fish_audio",
                kind="speech",
                configured=fish_ok,
                available=fish_ok,
                is_fallback=False,
                required_env=["FISH_AUDIO_API_KEY"],
                optional_env=["FISH_AUDIO_REFERENCE_ID", "FISH_AUDIO_BASE_URL"],
                env_configured={
                    "FISH_AUDIO_API_KEY": fish_ok,
                    "FISH_AUDIO_REFERENCE_ID": self._get_env("FISH_AUDIO_REFERENCE_ID") is not None,
                    "FISH_AUDIO_BASE_URL": self._get_env("FISH_AUDIO_BASE_URL") is not None,
                },
                active_model="fish-speech-v1",
                endpoint=fish_url,
                status="configured" if fish_ok else "not_configured",
            ),
            ProviderStatus(
                name="local_kokoro",
                kind="speech",
                configured=True,
                available=True,
                is_fallback=True,
                required_env=[],
                optional_env=[],
                env_configured={},
                active_model="hexgrad/Kokoro-82M-v1.1-zh",
                endpoint=None,
                status="local_builtin",
            ),
        ]

    def get_music_provider_statuses(self) -> List[ProviderStatus]:
        """Returns sanitized status objects for all music providers in priority order."""
        minimax_ok = self._has_secret("MINIMAX_API_KEY")
        minimax_model = self._get_env("MINIMAX_MUSIC_MODEL") or DEFAULT_MINIMAX_MUSIC_MODEL
        minimax_url = _sanitize_endpoint(self._get_env("MINIMAX_BASE_URL") or DEFAULT_MINIMAX_BASE_URL)

        suno_ok = self._has_secret("SUNO_API_KEY")
        suno_url = _sanitize_endpoint(self._get_env("SUNO_BASE_URL") or DEFAULT_SUNO_BASE_URL)

        return [
            ProviderStatus(
                name="minimax_music",
                kind="music",
                configured=minimax_ok,
                available=minimax_ok,
                is_fallback=False,
                required_env=["MINIMAX_API_KEY"],
                optional_env=["MINIMAX_MUSIC_MODEL", "MINIMAX_GROUP_ID", "MINIMAX_BASE_URL"],
                env_configured={
                    "MINIMAX_API_KEY": minimax_ok,
                    "MINIMAX_MUSIC_MODEL": self._get_env("MINIMAX_MUSIC_MODEL") is not None,
                    "MINIMAX_GROUP_ID": self._has_secret("MINIMAX_GROUP_ID"),
                    "MINIMAX_BASE_URL": self._get_env("MINIMAX_BASE_URL") is not None,
                },
                active_model=minimax_model,
                endpoint=minimax_url,
                status="configured" if minimax_ok else "not_configured",
            ),
            ProviderStatus(
                name="suno",
                kind="music",
                configured=suno_ok,
                available=suno_ok,
                is_fallback=False,
                required_env=["SUNO_API_KEY"],
                optional_env=["SUNO_BASE_URL"],
                env_configured={
                    "SUNO_API_KEY": suno_ok,
                    "SUNO_BASE_URL": self._get_env("SUNO_BASE_URL") is not None,
                },
                active_model="suno-v4",
                endpoint=suno_url,
                status="configured" if suno_ok else "not_configured",
            ),
            ProviderStatus(
                name="bilibili_bgm_hunter",
                kind="music",
                configured=True,
                available=True,
                is_fallback=True,
                required_env=[],
                optional_env=[],
                env_configured={},
                active_model="bilibili-dash-48khz",
                endpoint="https://api.bilibili.com",
                status="local_builtin",
            ),
        ]

    def list_voice_profiles(self) -> List[Dict[str, Any]]:
        """Returns sanitized character voice profiles without leaking Fish-Audio reference IDs or API keys."""
        profiles: List[Dict[str, Any]] = []
        global_fish_ok = self._has_secret("FISH_AUDIO_REFERENCE_ID")
        for prof in CHARACTER_VOICE_PROFILES.values():
            mm_override = self._get_env(prof.minimax_env_var)
            fish_char_ok = self._has_secret(prof.fish_env_var)
            profiles.append(
                {
                    "character_id": prof.character_id,
                    "display_name": prof.display_name,
                    "aliases": list(prof.aliases),
                    "persona_note": prof.persona_note,
                    "default_emotion": prof.default_emotion,
                    "default_speed": prof.default_speed,
                    "minimax_voice_id": mm_override or prof.minimax_voice_id,
                    "minimax_pitch": prof.minimax_pitch,
                    "minimax_env_var": prof.minimax_env_var,
                    "minimax_custom_override": mm_override is not None,
                    "fish_env_var": prof.fish_env_var,
                    "fish_reference_configured": bool(fish_char_ok or global_fish_ok),
                    "local_kokoro_voice": prof.local_kokoro_voice,
                    "edge_tts_voice": prof.edge_tts_voice,
                    "edge_tts_pitch": prof.edge_tts_pitch,
                }
            )
        return profiles

    def get_status(self) -> Dict[str, Any]:
        """Returns a sanitized dictionary describing active providers, priority, and env readiness.

        NEVER includes raw API key values or credentials.
        """
        speech_list = self.get_speech_provider_statuses()
        music_list = self.get_music_provider_statuses()
        active_speech = next((p.name for p in speech_list if p.available), "local_kokoro")
        active_music = next((p.name for p in music_list if p.available), "bilibili_bgm_hunter")
        return {
            "speech": {
                "priority": list(AUDIO_SPEECH_PROVIDER_PRIORITY),
                "active_provider": active_speech,
                "using_fallback": active_speech == "local_kokoro",
                "providers": {p.name: p.to_dict() for p in speech_list},
            },
            "music": {
                "priority": list(AUDIO_MUSIC_PROVIDER_PRIORITY),
                "active_provider": active_music,
                "using_fallback": active_music == "bilibili_bgm_hunter",
                "providers": {p.name: p.to_dict() for p in music_list},
            },
            "voice_profiles": {p["character_id"]: p for p in self.list_voice_profiles()},
        }

    def _is_provider_configured(self, provider: str) -> bool:
        if provider in ("minimax_speech", "minimax_music"):
            return self._has_secret("MINIMAX_API_KEY")
        if provider == "fish_audio":
            return self._has_secret("FISH_AUDIO_API_KEY")
        if provider == "suno":
            return self._has_secret("SUNO_API_KEY")
        if provider in ("local_kokoro", "bilibili_bgm_hunter"):
            return True
        return False

    def _resolve_candidates(
        self,
        priority: Tuple[str, ...],
        requested_provider: Optional[str],
        allow_fallback: bool,
        kind: str,
    ) -> List[str]:
        if requested_provider is not None:
            req_name = requested_provider.strip().lower()
            if req_name not in priority:
                raise ValueError(f"Unknown {kind} provider {requested_provider!r}. Supported: {', '.join(priority)}")
            if not allow_fallback:
                return [req_name]
            start_idx = priority.index(req_name)
            return list(priority[start_idx:])

        if not allow_fallback:
            first_ready = next((p for p in priority if self._is_provider_configured(p)), priority[-1])
            return [first_ready]
        return list(priority)

    def _download_audio_url(self, url: str, provider_name: str) -> bytes:
        dl = self.session.get(url, timeout=self.timeout_sec)
        if getattr(dl, "status_code", 200) >= 400:
            raise RuntimeError(f"{provider_name} audio download failed with HTTP {dl.status_code}")
        dl.raise_for_status()
        content = bytes(dl.content)
        if not content:
            raise RuntimeError(f"{provider_name} downloaded empty audio content")
        return content

    @staticmethod
    def _extract_audio_url_from_json(data: Any) -> Optional[str]:
        if not isinstance(data, dict):
            return None
        for key in ("audio_url", "audio_file", "url"):
            val = data.get(key)
            if isinstance(val, str) and val.startswith(("http://", "https://")):
                return val

        nested = data.get("data")
        if isinstance(nested, dict):
            for key in ("audio_url", "audio_file", "url"):
                val = nested.get(key)
                if isinstance(val, str) and val.startswith(("http://", "https://")):
                    return val
            for list_key in ("sunoData", "clips", "items", "songs"):
                arr = nested.get(list_key)
                if isinstance(arr, list):
                    for item in arr:
                        found = AudioGenerationRouter._extract_audio_url_from_json(item)
                        if found:
                            return found
        elif isinstance(nested, list):
            for item in nested:
                found = AudioGenerationRouter._extract_audio_url_from_json(item)
                if found:
                    return found

        for list_key in ("clips", "items", "songs"):
            arr = data.get(list_key)
            if isinstance(arr, list):
                for item in arr:
                    found = AudioGenerationRouter._extract_audio_url_from_json(item)
                    if found:
                        return found
        return None

    def _extract_audio_from_response(
        self,
        resp: requests.Response,
        provider_name: str,
    ) -> Tuple[bytes, Dict[str, Any]]:
        if getattr(resp, "status_code", 200) >= 400:
            raise RuntimeError(f"{provider_name} HTTP {resp.status_code}")
        resp.raise_for_status()

        headers = getattr(resp, "headers", None) or {}
        content_type = next(
            (str(v).lower() for k, v in headers.items() if str(k).lower() == "content-type"),
            "",
        )
        if content_type.startswith("audio/") or "application/octet-stream" in content_type:
            raw_bytes = bytes(resp.content)
            if not raw_bytes:
                raise RuntimeError(f"{provider_name} returned empty binary audio stream")
            return raw_bytes, {"content_type": content_type}

        data = resp.json()
        if not isinstance(data, dict):
            raise RuntimeError(f"{provider_name} returned unexpected JSON payload type")

        base_resp = data.get("base_resp")
        if isinstance(base_resp, dict):
            status_code = base_resp.get("status_code")
            if status_code not in (None, 0):
                status_msg = str(base_resp.get("status_msg") or "API error")
                raise RuntimeError(f"{provider_name} API error {status_code}: {status_msg}")

        nested = data.get("data")
        inline_audio: Optional[str] = None
        if isinstance(nested, dict) and isinstance(nested.get("audio"), str) and nested["audio"].strip():
            inline_audio = nested["audio"]
        elif isinstance(data.get("audio"), str) and data["audio"].strip():
            inline_audio = data["audio"]

        if inline_audio is not None:
            return _decode_inline_audio(inline_audio), data

        audio_url = self._extract_audio_url_from_json(data)
        if audio_url:
            return self._download_audio_url(audio_url, provider_name), data

        raise RuntimeError(f"{provider_name} response contained no audio payload or audio_url")

    def _create_local_tts(self) -> Any:
        if self._local_tts_factory is not None:
            return self._local_tts_factory()
        from core.local_tts import LocalNeuralTTS

        return LocalNeuralTTS()

    def _create_bgm_hunter(self) -> Any:
        if self._bgm_hunter_factory is not None:
            return self._bgm_hunter_factory()
        from core.bgm_hunter import BilibiliBgmHunter

        return BilibiliBgmHunter(session=self.session)

    def _resolve_speech_params(self, request: SpeechRequest, provider: str) -> Dict[str, Any]:
        profile = resolve_character_profile(request.character) if request.character else None
        emo_spec = resolve_emotion_spec(
            request.emotion,
            default=profile.default_emotion if profile is not None else "neutral",
        )
        if request.speed is not None:
            speed = float(request.speed)
        elif profile is not None:
            raw_speed = profile.default_speed * emo_spec.speed_multiplier
            speed = round(max(MIN_PROFILE_AUTO_SPEED, min(MAX_PROFILE_AUTO_SPEED, raw_speed)), 3)
        else:
            speed = 1.0

        if request.pitch is not None:
            pitch = max(-12, min(12, int(request.pitch)))
        elif profile is not None:
            pitch = profile.minimax_pitch
        else:
            pitch = 0

        explicit_voice = request.voice.strip() if request.voice and request.voice.strip() else None
        if provider == "minimax_speech":
            voice = (
                explicit_voice
                or (self._get_env(profile.minimax_env_var) if profile is not None else None)
                or (profile.minimax_voice_id if profile is not None else None)
                or self._get_env("MINIMAX_SPEECH_VOICE")
                or DEFAULT_MINIMAX_SPEECH_VOICE
            ).strip()
        elif provider == "fish_audio":
            voice = (
                explicit_voice
                or (self._get_env(profile.fish_env_var) if profile is not None else None)
                or self._get_env("FISH_AUDIO_REFERENCE_ID")
                or ""
            ).strip()
        elif provider == "local_kokoro":
            voice = (
                explicit_voice or (profile.local_kokoro_voice if profile is not None else None) or "zf_001"
            ).strip()
        else:
            voice = explicit_voice or ""

        return {
            "profile": profile,
            "character_id": profile.character_id if profile is not None else None,
            "display_name": profile.display_name if profile is not None else None,
            "emotion_spec": emo_spec,
            "speed": speed,
            "pitch": pitch,
            "voice": voice,
            "edge_voice": profile.edge_tts_voice if profile is not None else None,
            "edge_pitch": profile.edge_tts_pitch if profile is not None else None,
        }

    def _synth_minimax_speech(self, request: SpeechRequest, used_fallback: bool) -> SpeechResult:
        api_key = self._get_env("MINIMAX_API_KEY")
        if not _is_configured_secret(api_key):
            raise RuntimeError("Provider 'minimax_speech' is not configured (missing MINIMAX_API_KEY)")
        assert api_key is not None

        base_url = (self._get_env("MINIMAX_BASE_URL") or DEFAULT_MINIMAX_BASE_URL).rstrip("/")
        model = self._get_env("MINIMAX_SPEECH_MODEL") or DEFAULT_MINIMAX_SPEECH_MODEL
        group_id = self._get_env("MINIMAX_GROUP_ID")
        out_path = Path(request.output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        ext = out_path.suffix.lstrip(".").lower()
        audio_format = ext if ext in {"mp3", "wav", "pcm", "flac"} else "mp3"
        params_resolved = self._resolve_speech_params(request, "minimax_speech")
        emo_spec: EmotionSpec = params_resolved["emotion_spec"]
        emotion = emo_spec.minimax_emotion
        voice_id = str(params_resolved["voice"])
        speed = float(params_resolved["speed"])
        pitch = int(params_resolved["pitch"])

        url = f"{base_url}/v1/t2a_v2"
        params = {"GroupId": group_id} if _is_configured_secret(group_id) and group_id else None
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": model,
            "text": request.text,
            "stream": False,
            "voice_setting": {
                "voice_id": voice_id,
                "speed": speed,
                "vol": 1.0,
                "pitch": pitch,
                "emotion": emotion,
            },
            "audio_setting": {
                "sample_rate": 32000,
                "bitrate": 128000,
                "format": audio_format,
                "channel": 1,
            },
        }

        resp = self.session.post(url, params=params, headers=headers, json=payload, timeout=self.timeout_sec)
        audio_bytes, meta_json = self._extract_audio_from_response(resp, "minimax_speech")
        out_path.write_bytes(audio_bytes)

        extra_info = meta_json.get("extra_info") if isinstance(meta_json, dict) else None
        sr = 32000
        if isinstance(extra_info, dict) and extra_info.get("audio_sample_rate"):
            sr = int(extra_info["audio_sample_rate"])
        else:
            sr = _detect_wav_sample_rate(audio_bytes, default_sr=32000)

        return SpeechResult(
            provider="minimax_speech",
            audio_path=out_path,
            sample_rate=sr,
            used_fallback=used_fallback,
            metadata={
                "character": params_resolved["character_id"],
                "display_name": params_resolved["display_name"],
                "model": model,
                "voice": voice_id,
                "pitch": pitch,
                "emotion": emotion,
                "raw_emotion": request.emotion or emo_spec.canonical,
                "speed": speed,
                "format": audio_format,
                "bytes": len(audio_bytes),
            },
        )

    def _synth_fish_audio(self, request: SpeechRequest, used_fallback: bool) -> SpeechResult:
        api_key = self._get_env("FISH_AUDIO_API_KEY")
        if not _is_configured_secret(api_key):
            raise RuntimeError("Provider 'fish_audio' is not configured (missing FISH_AUDIO_API_KEY)")
        assert api_key is not None

        base_url = (self._get_env("FISH_AUDIO_BASE_URL") or DEFAULT_FISH_AUDIO_BASE_URL).rstrip("/")
        out_path = Path(request.output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        ext = out_path.suffix.lstrip(".").lower()
        audio_format = ext if ext in {"mp3", "wav", "pcm", "opus"} else "mp3"
        params_resolved = self._resolve_speech_params(request, "fish_audio")
        emo_spec: EmotionSpec = params_resolved["emotion_spec"]
        emotion = emo_spec.fish_emotion
        ref_id = str(params_resolved["voice"])
        speed = float(params_resolved["speed"])

        url = f"{base_url}/v1/tts"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "text": request.text,
            "format": audio_format,
            "prosody": {"speed": speed, "volume": 0},
            "emotion": emotion,
        }
        if ref_id:
            payload["reference_id"] = ref_id

        resp = self.session.post(url, headers=headers, json=payload, timeout=self.timeout_sec)
        audio_bytes, meta_json = self._extract_audio_from_response(resp, "fish_audio")
        out_path.write_bytes(audio_bytes)

        sr_from_meta = meta_json.get("sample_rate") if isinstance(meta_json, dict) else None
        sr = int(sr_from_meta) if sr_from_meta else _detect_wav_sample_rate(audio_bytes, default_sr=44100)

        return SpeechResult(
            provider="fish_audio",
            audio_path=out_path,
            sample_rate=sr,
            used_fallback=used_fallback,
            metadata={
                "character": params_resolved["character_id"],
                "display_name": params_resolved["display_name"],
                "reference_id": ref_id or None,
                "emotion": emotion,
                "raw_emotion": request.emotion or emo_spec.canonical,
                "speed": speed,
                "format": audio_format,
                "bytes": len(audio_bytes),
            },
        )

    def _synth_local_kokoro(self, request: SpeechRequest, used_fallback: bool) -> SpeechResult:
        out_path = Path(request.output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        params_resolved = self._resolve_speech_params(request, "local_kokoro")
        emo_spec: EmotionSpec = params_resolved["emotion_spec"]
        voice = str(params_resolved["voice"])
        speed = float(params_resolved["speed"])
        edge_voice = params_resolved["edge_voice"]
        edge_pitch = params_resolved["edge_pitch"]

        tts = self._create_local_tts()
        try:
            synth_kwargs: Dict[str, Any] = {
                "text": request.text,
                "voice": voice,
                "speed": speed,
            }
            if edge_voice is not None or edge_pitch is not None:
                try:
                    sig = inspect.signature(tts.synthesize_text)
                    has_varkw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
                    if edge_voice is not None and (has_varkw or "edge_voice" in sig.parameters):
                        synth_kwargs["edge_voice"] = edge_voice
                    if edge_pitch is not None and (has_varkw or "edge_pitch" in sig.parameters):
                        synth_kwargs["edge_pitch"] = edge_pitch
                except (TypeError, ValueError):
                    pass

            waveform = tts.synthesize_text(**synth_kwargs)
            sr = int(getattr(tts, "sample_rate", 24000))
            if out_path.suffix.lower() == ".wav":
                _write_pcm16_wav(waveform, out_path, sr)
            else:
                with tempfile.TemporaryDirectory() as tmpdir:
                    tmp_wav = Path(tmpdir) / "kokoro_tmp.wav"
                    _write_pcm16_wav(waveform, tmp_wav, sr)
                    subprocess.run(
                        [
                            "ffmpeg",
                            "-y",
                            "-nostats",
                            "-loglevel",
                            "error",
                            "-i",
                            str(tmp_wav),
                            "-ar",
                            str(sr),
                            str(out_path),
                        ],
                        check=True,
                    )
        finally:
            close_fn = getattr(tts, "close", None)
            if callable(close_fn):
                close_fn()

        return SpeechResult(
            provider="local_kokoro",
            audio_path=out_path,
            sample_rate=sr,
            used_fallback=used_fallback,
            metadata={
                "character": params_resolved["character_id"],
                "display_name": params_resolved["display_name"],
                "voice": voice,
                "edge_voice": edge_voice,
                "edge_pitch": edge_pitch,
                "emotion": emo_spec.canonical,
                "raw_emotion": request.emotion or emo_spec.canonical,
                "speed": speed,
            },
        )

    def synthesize_speech(self, request: SpeechRequest, allow_fallback: bool = True) -> SpeechResult:
        """Synthesizes speech using the highest-priority configured provider with optional fallback."""
        if not request.text or not request.text.strip():
            raise ValueError("SpeechRequest.text must not be empty")
        if request.character is not None:
            resolve_character_profile(request.character)
        if request.speed is not None and float(request.speed) <= 0:
            raise ValueError("SpeechRequest.speed must be > 0")

        candidates = self._resolve_candidates(
            priority=AUDIO_SPEECH_PROVIDER_PRIORITY,
            requested_provider=request.provider,
            allow_fallback=allow_fallback,
            kind="speech",
        )
        fallback_errors: List[Dict[str, str]] = []
        requested_norm = request.provider.strip().lower() if request.provider else None

        for provider in candidates:
            is_configured = self._is_provider_configured(provider)
            if not is_configured:
                err_msg = f"Provider '{provider}' is not configured"
                if not allow_fallback:
                    raise RuntimeError(err_msg)
                if requested_norm == provider:
                    fallback_errors.append({"provider": provider, "error": err_msg})
                continue

            used_fallback = bool(fallback_errors) or (provider == "local_kokoro" and requested_norm != "local_kokoro")
            try:
                if provider == "minimax_speech":
                    res = self._synth_minimax_speech(request, used_fallback=used_fallback)
                elif provider == "fish_audio":
                    res = self._synth_fish_audio(request, used_fallback=used_fallback)
                elif provider == "local_kokoro":
                    res = self._synth_local_kokoro(request, used_fallback=used_fallback)
                else:
                    raise ValueError(f"Unsupported speech provider: {provider}")
                if fallback_errors:
                    res.metadata["fallback_errors"] = fallback_errors
                return res
            except Exception as exc:
                safe_err = self._sanitize_error(exc)
                if not allow_fallback:
                    raise RuntimeError(f"Speech provider '{provider}' failed: {safe_err}") from exc
                logger.warning("Speech provider '%s' failed (%s); falling back to next provider.", provider, safe_err)
                fallback_errors.append({"provider": provider, "error": safe_err})

        details = "; ".join(f"{e['provider']}: {e['error']}" for e in fallback_errors) or "no providers available"
        raise RuntimeError(f"All speech providers failed ({details})")

    def synthesize_dialogue(
        self,
        lines: Sequence[DialogueLine],
        output_dir: Union[str, Path],
        file_ext: str = "wav",
        allow_fallback: bool = True,
        write_manifest: bool = True,
    ) -> DialogueResult:
        """Synthesizes a multi-character script serially into output_dir with optional manifest."""
        if not lines:
            raise ValueError("Dialogue lines must not be empty")

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        ext = file_ext.lstrip(".").lower() or "wav"

        rendered_lines: List[Dict[str, Any]] = []
        providers_used: List[str] = []
        any_fallback = False

        for idx, line in enumerate(lines, start=1):
            profile = resolve_character_profile(line.character)
            raw_line_id = (line.line_id or "").strip()
            safe_line_id = re.sub(r"[^A-Za-z0-9_-]+", "_", raw_line_id).strip("_") if raw_line_id else ""
            effective_id = safe_line_id or f"{idx:02d}_{profile.character_id}"
            audio_out = out_dir / f"{effective_id}.{ext}"

            res = self.synthesize_speech(
                SpeechRequest(
                    text=line.text,
                    output_path=audio_out,
                    emotion=line.emotion,
                    voice=line.voice,
                    speed=line.speed,
                    provider=line.provider,
                    character=profile.character_id,
                    pitch=line.pitch,
                ),
                allow_fallback=allow_fallback,
            )
            if res.provider not in providers_used:
                providers_used.append(res.provider)
            if res.used_fallback:
                any_fallback = True

            is_fish = res.provider == "fish_audio"
            fish_ref_set = bool(res.metadata.get("reference_id")) if is_fish else False
            voice_label = (
                f"{profile.character_id}:configured_ref" if (is_fish and fish_ref_set) else res.metadata.get("voice")
            )

            rendered_lines.append(
                {
                    "index": idx,
                    "line_id": effective_id,
                    "character": profile.character_id,
                    "display_name": profile.display_name,
                    "text": line.text,
                    "provider": res.provider,
                    "audio_path": str(res.audio_path),
                    "sample_rate": res.sample_rate,
                    "voice": voice_label,
                    "fish_reference_configured": fish_ref_set,
                    "emotion": res.metadata.get("emotion"),
                    "raw_emotion": res.metadata.get("raw_emotion"),
                    "speed": res.metadata.get("speed"),
                    "used_fallback": res.used_fallback,
                    "pause_after_sec": max(0.0, float(line.pause_after_sec)),
                }
            )

        manifest_path: Optional[Path] = None
        if write_manifest:
            manifest_path = out_dir / "dialogue_manifest.json"
            manifest_payload = {
                "line_count": len(rendered_lines),
                "providers_used": providers_used,
                "used_fallback": any_fallback,
                "lines": rendered_lines,
            }
            manifest_path.write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        return DialogueResult(
            lines=rendered_lines,
            providers_used=providers_used,
            used_fallback=any_fallback,
            output_dir=out_dir,
            manifest_path=manifest_path,
        )

    def _generate_minimax_music(self, request: MusicRequest, used_fallback: bool) -> MusicResult:
        api_key = self._get_env("MINIMAX_API_KEY")
        if not _is_configured_secret(api_key):
            raise RuntimeError("Provider 'minimax_music' is not configured (missing MINIMAX_API_KEY)")
        assert api_key is not None

        base_url = (self._get_env("MINIMAX_BASE_URL") or DEFAULT_MINIMAX_BASE_URL).rstrip("/")
        model = self._get_env("MINIMAX_MUSIC_MODEL") or DEFAULT_MINIMAX_MUSIC_MODEL
        group_id = self._get_env("MINIMAX_GROUP_ID")
        out_path = Path(request.output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        ext = out_path.suffix.lstrip(".").lower()
        audio_format = ext if ext in {"mp3", "wav", "pcm", "flac"} else "mp3"

        base_prompt = request.prompt.strip()
        style_str = request.style.strip()
        if style_str and style_str.lower() not in base_prompt.lower():
            effective_prompt = f"{style_str}, {base_prompt}" if base_prompt else style_str
        else:
            effective_prompt = base_prompt or style_str

        raw_lyrics = request.lyrics.strip()
        if raw_lyrics:
            effective_lyrics = raw_lyrics
        elif request.instrumental:
            effective_lyrics = "[Instrumental]"
        else:
            effective_lyrics = ""

        url = f"{base_url}/v1/music_generation"
        params = {"GroupId": group_id} if _is_configured_secret(group_id) and group_id else None
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": model,
            "prompt": effective_prompt,
            "lyrics": effective_lyrics,
            "instrumental": bool(request.instrumental),
            "duration_sec": float(request.duration_sec),
            "audio_setting": {
                "sample_rate": 44100,
                "bitrate": 256000,
                "format": audio_format,
            },
        }
        if style_str:
            payload["style"] = style_str

        resp = self.session.post(url, params=params, headers=headers, json=payload, timeout=self.timeout_sec)
        audio_bytes, _meta_json = self._extract_audio_from_response(resp, "minimax_music")
        out_path.write_bytes(audio_bytes)

        return MusicResult(
            provider="minimax_music",
            audio_path=out_path,
            credits_line=f"原创配乐由 MiniMax Music ({model}) 生成（AIGC 合规声明：GB 45438-2025）",
            used_fallback=used_fallback,
            metadata={
                "model": model,
                "style": style_str,
                "instrumental": bool(request.instrumental),
                "has_lyrics": bool(raw_lyrics),
                "duration_sec": float(request.duration_sec),
                "format": audio_format,
                "bytes": len(audio_bytes),
            },
        )

    def _poll_suno_task(self, base_url: str, headers: Dict[str, str], task_id: str) -> bytes:
        poll_url = f"{base_url}/api/v1/generate/record-info"
        for attempt in range(self.max_poll_attempts):
            resp = self.session.get(poll_url, params={"taskId": task_id}, headers=headers, timeout=self.timeout_sec)
            if getattr(resp, "status_code", 200) >= 400:
                raise RuntimeError(f"suno poll HTTP {resp.status_code}")
            resp.raise_for_status()
            data = resp.json()
            audio_url = self._extract_audio_url_from_json(data)
            if audio_url:
                return self._download_audio_url(audio_url, "suno")

            nested = data.get("data") if isinstance(data, dict) else None
            status_val = str(
                (nested.get("status") if isinstance(nested, dict) else None)
                or (data.get("status") if isinstance(data, dict) else "")
                or ""
            ).upper()
            if status_val in {"FAILED", "ERROR", "GENERATE_AUDIO_FAILED"}:
                raise RuntimeError(f"suno task {task_id} failed with status={status_val}")
            if attempt < self.max_poll_attempts - 1 and self.poll_interval_sec > 0:
                time.sleep(self.poll_interval_sec)

        raise RuntimeError(f"suno task {task_id} timed out after {self.max_poll_attempts} poll attempts")

    def _generate_suno_music(self, request: MusicRequest, used_fallback: bool) -> MusicResult:
        api_key = self._get_env("SUNO_API_KEY")
        if not _is_configured_secret(api_key):
            raise RuntimeError("Provider 'suno' is not configured (missing SUNO_API_KEY)")
        assert api_key is not None

        base_url = (self._get_env("SUNO_BASE_URL") or DEFAULT_SUNO_BASE_URL).rstrip("/")
        out_path = Path(request.output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        lyrics_str = request.lyrics.strip()
        style_str = request.style.strip()
        prompt_str = request.prompt.strip()

        url = f"{base_url}/api/v1/generate"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "prompt": lyrics_str if (lyrics_str and not request.instrumental) else (prompt_str or style_str),
            "style": style_str or prompt_str,
            "instrumental": bool(request.instrumental),
            "customMode": bool(lyrics_str or style_str),
            "duration": float(request.duration_sec),
        }
        if lyrics_str:
            payload["lyrics"] = lyrics_str

        resp = self.session.post(url, headers=headers, json=payload, timeout=self.timeout_sec)
        if getattr(resp, "status_code", 200) >= 400:
            raise RuntimeError(f"suno HTTP {resp.status_code}")
        resp.raise_for_status()

        resp_headers = getattr(resp, "headers", None) or {}
        content_type = next(
            (str(v).lower() for k, v in resp_headers.items() if str(k).lower() == "content-type"),
            "",
        )
        task_id: Optional[str] = None

        if content_type.startswith("audio/") or "application/octet-stream" in content_type:
            audio_bytes = bytes(resp.content)
        else:
            data = resp.json()
            if not isinstance(data, dict):
                raise RuntimeError("suno returned unexpected JSON payload type")
            if data.get("code") not in (None, 0, 200) and not data.get("data"):
                raise RuntimeError(f"suno API error {data.get('code')}: {data.get('msg') or data.get('message') or ''}")

            audio_url = self._extract_audio_url_from_json(data)
            nested = data.get("data")
            if audio_url:
                audio_bytes = self._download_audio_url(audio_url, "suno")
            elif isinstance(nested, dict) and isinstance(nested.get("audio"), str) and nested["audio"].strip():
                audio_bytes = _decode_inline_audio(nested["audio"])
            elif isinstance(data.get("audio"), str) and data["audio"].strip():
                audio_bytes = _decode_inline_audio(data["audio"])
            else:
                raw_tid = (
                    (nested.get("taskId") or nested.get("task_id"))
                    if isinstance(nested, dict)
                    else (data.get("taskId") or data.get("task_id"))
                )
                if not raw_tid:
                    raise RuntimeError("suno response contained no audio_url, inline audio, or taskId")
                task_id = str(raw_tid)
                audio_bytes = self._poll_suno_task(base_url=base_url, headers=headers, task_id=task_id)

        out_path.write_bytes(audio_bytes)
        return MusicResult(
            provider="suno",
            audio_path=out_path,
            credits_line="原创配乐由 Suno AI 生成（AIGC 合规声明：GB 45438-2025）",
            used_fallback=used_fallback,
            metadata={
                "style": style_str or prompt_str,
                "instrumental": bool(request.instrumental),
                "has_lyrics": bool(lyrics_str),
                "duration_sec": float(request.duration_sec),
                "task_id": task_id,
                "bytes": len(audio_bytes),
            },
        )

    def _generate_bilibili_bgm(self, request: MusicRequest, used_fallback: bool) -> MusicResult:
        out_path = Path(request.output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        hunter = self._create_bgm_hunter()

        source: str
        matched_candidate: Optional[Dict[str, Any]] = None
        if request.bgm_bvid and request.bgm_bvid.strip():
            source = request.bgm_bvid.strip()
        else:
            query = (request.bgm_query or request.style or request.prompt).strip()
            if not query:
                raise ValueError("MusicRequest must specify bgm_bvid, bgm_query, style, or prompt")
            is_local_file = False
            try:
                is_local_file = len(query) <= 240 and Path(query).is_file()
            except OSError:
                is_local_file = False
            if is_local_file:
                source = query
            else:
                candidates = hunter.search_bgm(keyword=query, limit=5)
                picked = next((c for c in candidates if str(c.get("bvid") or "").strip()), None)
                if picked is None:
                    raise RuntimeError(f"BilibiliBgmHunter found no BGM candidates for query: {query!r}")
                matched_candidate = dict(picked)
                source = str(picked["bvid"]).strip()

        info = hunter.extract_audio_clip(
            source=source,
            output_wav=out_path,
            duration_sec=float(request.duration_sec) if request.duration_sec > 0 else None,
        )
        return MusicResult(
            provider="bilibili_bgm_hunter",
            audio_path=Path(info["output_wav"]),
            credits_line=str(info.get("credit_line") or ""),
            used_fallback=used_fallback,
            metadata={
                "source": str(info.get("source") or source),
                "bvid": str(info.get("bvid") or ""),
                "title": str(info.get("title") or ""),
                "author": str(info.get("author") or ""),
                "duration_sec": info.get("duration_sec"),
                "matched_candidate": matched_candidate,
            },
        )

    def generate_music(self, request: MusicRequest, allow_fallback: bool = True) -> MusicResult:
        """Generates or fetches BGM using the highest-priority configured provider with optional fallback."""
        has_input = any((s or "").strip() for s in (request.prompt, request.style, request.bgm_query, request.bgm_bvid))
        if not has_input:
            raise ValueError("MusicRequest must provide at least one of prompt, style, bgm_query, or bgm_bvid")

        candidates = self._resolve_candidates(
            priority=AUDIO_MUSIC_PROVIDER_PRIORITY,
            requested_provider=request.provider,
            allow_fallback=allow_fallback,
            kind="music",
        )
        fallback_errors: List[Dict[str, str]] = []
        requested_norm = request.provider.strip().lower() if request.provider else None

        for provider in candidates:
            is_configured = self._is_provider_configured(provider)
            if not is_configured:
                err_msg = f"Provider '{provider}' is not configured"
                if not allow_fallback:
                    raise RuntimeError(err_msg)
                if requested_norm == provider:
                    fallback_errors.append({"provider": provider, "error": err_msg})
                continue

            used_fallback = bool(fallback_errors) or (
                provider == "bilibili_bgm_hunter" and requested_norm != "bilibili_bgm_hunter"
            )
            try:
                if provider == "minimax_music":
                    res = self._generate_minimax_music(request, used_fallback=used_fallback)
                elif provider == "suno":
                    res = self._generate_suno_music(request, used_fallback=used_fallback)
                elif provider == "bilibili_bgm_hunter":
                    res = self._generate_bilibili_bgm(request, used_fallback=used_fallback)
                else:
                    raise ValueError(f"Unsupported music provider: {provider}")
                if fallback_errors:
                    res.metadata["fallback_errors"] = fallback_errors
                return res
            except Exception as exc:
                safe_err = self._sanitize_error(exc)
                if not allow_fallback:
                    raise RuntimeError(f"Music provider '{provider}' failed: {safe_err}") from exc
                logger.warning("Music provider '%s' failed (%s); falling back to next provider.", provider, safe_err)
                fallback_errors.append({"provider": provider, "error": safe_err})

        details = "; ".join(f"{e['provider']}: {e['error']}" for e in fallback_errors) or "no providers available"
        raise RuntimeError(f"All music providers failed ({details})")
