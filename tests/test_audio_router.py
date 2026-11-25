"""Unit tests for Kaizen Slices K4 & K6: Pluggable AudioGenerationRouter, Character Profiles & CLI.

100% offline and mocked: never instantiates real PyTorch/Kokoro models or hits live endpoints.
"""

from __future__ import annotations

import json
import sys
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
import requests

import cli
from core.audio_router import (
    CHARACTER_VOICE_PROFILES,
    VERIFIED_FREE_EDGE_TTS_VOICES,
    AudioGenerationRouter,
    DialogueLine,
    MusicRequest,
    SpeechRequest,
    resolve_character_profile,
    resolve_emotion_spec,
)


class _FakeResponse:
    """Minimal deterministic HTTP response stub compatible with requests.Response."""

    def __init__(
        self,
        status_code: int = 200,
        json_data: Any = None,
        content: bytes = b"",
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.status_code = status_code
        self._json_data = json_data
        self.content = content
        self.headers = dict(headers or {})
        if not self.headers and json_data is not None:
            self.headers["Content-Type"] = "application/json"

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code} Error")

    def json(self) -> Any:
        if self._json_data is None:
            raise ValueError("No JSON body")
        return self._json_data


class _FakeSession:
    """Recorded offline HTTP session stub."""

    def __init__(self, handler: Any) -> None:
        self._handler = handler
        self.calls: List[Dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        rec = {"method": "POST", "url": url, **kwargs}
        self.calls.append(rec)
        return self._handler("POST", url, kwargs)

    def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        rec = {"method": "GET", "url": url, **kwargs}
        self.calls.append(rec)
        return self._handler("GET", url, kwargs)


class _FakeLocalTTS:
    """Lightweight stub replacing core.local_tts.LocalNeuralTTS without loading PyTorch."""

    def __init__(self, sample_rate: int = 24000, fail_exc: Optional[Exception] = None) -> None:
        self.sample_rate = sample_rate
        self.fail_exc = fail_exc
        self.calls: List[Dict[str, Any]] = []
        self.close_count = 0

    def synthesize_text(self, text: str, voice: str = "zf_001", speed: float = 1.03) -> List[float]:
        self.calls.append({"text": text, "voice": voice, "speed": speed})
        if self.fail_exc is not None:
            raise self.fail_exc
        return [0.0, 0.25, -0.25, 0.15, -0.15, 0.0] * 40

    def close(self) -> None:
        self.close_count += 1


class _FakeBgmHunter:
    """Lightweight stub replacing core.bgm_hunter.BilibiliBgmHunter without network or FFmpeg."""

    def __init__(self, candidates: Optional[List[Dict[str, Any]]] = None) -> None:
        self.candidates = (
            candidates
            if candidates is not None
            else [
                {
                    "bvid": "BV1DemoBgm99",
                    "title": "Cyber Cat Dance Beat 138BPM",
                    "author": "DemoMusician",
                    "play": 520000,
                    "duration": "01:30",
                }
            ]
        )
        self.search_calls: List[Dict[str, Any]] = []
        self.extract_calls: List[Dict[str, Any]] = []

    def search_bgm(self, keyword: str, order: str = "click", limit: int = 8) -> List[Dict[str, Any]]:
        self.search_calls.append({"keyword": keyword, "order": order, "limit": limit})
        return list(self.candidates[:limit])

    def extract_audio_clip(
        self,
        source: Any,
        output_wav: Any,
        start_sec: float = 0.0,
        duration_sec: Optional[float] = None,
        **_kwargs: Any,
    ) -> Dict[str, Any]:
        out_p = Path(output_wav)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_bytes(b"RIFF_FAKE_BGM_WAV")
        self.extract_calls.append(
            {"source": str(source), "output_wav": str(out_p), "start_sec": start_sec, "duration_sec": duration_sec}
        )
        return {
            "output_wav": str(out_p),
            "source": str(source),
            "bvid": str(source),
            "title": "Cyber Cat Dance Beat 138BPM",
            "author": "DemoMusician",
            "duration_sec": duration_sec or 15.0,
            "credit_line": f"BGM/音频片段致谢：B站 UP主「DemoMusician」作品《Cyber Cat Dance Beat 138BPM》（{source}）",
        }


def test_get_status_priority_and_secret_non_leakage() -> None:
    # 1. Zero keys -> local fallbacks active
    router_empty = AudioGenerationRouter(env={})
    status_empty = router_empty.get_status()
    assert status_empty["speech"]["priority"] == ["minimax_speech", "fish_audio", "deepseek_tts", "local_kokoro"]
    assert status_empty["speech"]["active_provider"] == "local_kokoro"
    assert status_empty["speech"]["using_fallback"] is True
    assert status_empty["music"]["priority"] == ["minimax_music", "suno", "bilibili_bgm_hunter"]
    assert status_empty["music"]["active_provider"] == "bilibili_bgm_hunter"
    assert status_empty["music"]["using_fallback"] is True

    # 2. Placeholder keys must be treated as unconfigured
    router_placeholders = AudioGenerationRouter(
        env={
            "MINIMAX_API_KEY": "your_api_key",
            "FISH_AUDIO_API_KEY": "   ",
            "DEEPSEEK_API_KEY": "dummy_deepseek_key",
            "SUNO_API_KEY": "dummy_suno_key",
        }
    )
    st_ph = router_placeholders.get_status()
    assert st_ph["speech"]["active_provider"] == "local_kokoro"
    assert st_ph["music"]["active_provider"] == "bilibili_bgm_hunter"
    assert st_ph["speech"]["providers"]["minimax_speech"]["configured"] is False
    assert st_ph["speech"]["providers"]["fish_audio"]["configured"] is False
    assert st_ph["speech"]["providers"]["deepseek_tts"]["configured"] is False
    assert st_ph["music"]["providers"]["suno"]["configured"] is False

    # 3. Secondary keys only -> fish_audio & suno active
    router_secondary = AudioGenerationRouter(
        env={
            "FISH_AUDIO_API_KEY": "fish_live_key_alpha",
            "DEEPSEEK_API_KEY": "sk-deepseek-tertiary-gamma",
            "SUNO_API_KEY": "suno_live_key_beta",
        }
    )
    st_sec = router_secondary.get_status()
    assert st_sec["speech"]["active_provider"] == "fish_audio"
    assert st_sec["speech"]["providers"]["deepseek_tts"]["configured"] is True
    assert st_sec["speech"]["using_fallback"] is False
    assert st_sec["music"]["active_provider"] == "suno"
    assert st_sec["music"]["using_fallback"] is False

    # 4. All secrets configured -> NEVER leak raw secrets anywhere in get_status()
    secret_env = {
        "MINIMAX_API_KEY": "sk-minimax-ultra-secret-998877",
        "MINIMAX_GROUP_ID": "grp-secret-445566",
        "MINIMAX_SPEECH_MODEL": "speech-02-hd",
        "MINIMAX_MUSIC_MODEL": "music-1.5",
        "FISH_AUDIO_API_KEY": "fish-ultra-secret-112233",
        "FISH_AUDIO_REFERENCE_ID": "ref-secret-voice-778899",
        "DEEPSEEK_API_KEY": "sk-deepseek-ultra-secret-556677",
        "SUNO_API_KEY": "suno-ultra-secret-334455",
        "SUNO_BASE_URL": "https://user:pass-leak@suno.example.org/api?token=url-secret-000",
    }
    router_full = AudioGenerationRouter(env=secret_env)
    st_full = router_full.get_status()
    assert st_full["speech"]["active_provider"] == "minimax_speech"
    assert st_full["music"]["active_provider"] == "minimax_music"
    assert st_full["music"]["providers"]["minimax_music"]["active_model"] == "music-1.5"
    assert st_full["music"]["providers"]["suno"]["endpoint"] == "https://suno.example.org/api"

    dumped = json.dumps(st_full, ensure_ascii=False)
    for forbidden in (
        "sk-minimax-ultra-secret-998877",
        "grp-secret-445566",
        "fish-ultra-secret-112233",
        "ref-secret-voice-778899",
        "sk-deepseek-ultra-secret-556677",
        "suno-ultra-secret-334455",
        "pass-leak",
        "url-secret-000",
    ):
        assert forbidden not in dumped


def test_speech_minimax_priority_and_emotion_payload(tmp_path: Path) -> None:
    audio_payload = b"ID3_FAKE_MINIMAX_SPEECH_MP3"

    def handler(method: str, url: str, kwargs: Dict[str, Any]) -> _FakeResponse:
        assert method == "POST"
        assert url == "https://api.minimax.chat/v1/t2a_v2"
        assert kwargs["params"] == {"GroupId": "grp-9001"}
        assert kwargs["headers"]["Authorization"] == "Bearer sk-minimax-key-1"
        body = kwargs["json"]
        assert body["model"] == "speech-02-turbo"
        assert body["text"] == "今天居然提前下班了！"
        assert body["voice_setting"]["emotion"] == "happy"
        assert body["voice_setting"]["voice_id"] == "anime-girl-01"
        assert body["voice_setting"]["speed"] == 1.15
        assert body["audio_setting"]["format"] == "mp3"
        return _FakeResponse(
            status_code=200,
            json_data={
                "base_resp": {"status_code": 0, "status_msg": "success"},
                "data": {"audio": audio_payload.hex()},
                "extra_info": {"audio_sample_rate": 32000},
            },
        )

    fake_tts = _FakeLocalTTS()
    session = _FakeSession(handler)
    router = AudioGenerationRouter(
        env={
            "MINIMAX_API_KEY": "sk-minimax-key-1",
            "MINIMAX_GROUP_ID": "grp-9001",
            "MINIMAX_SPEECH_MODEL": "speech-02-turbo",
            "FISH_AUDIO_API_KEY": "fish-key-should-not-win",
        },
        session=session,  # type: ignore[arg-type]
        local_tts_factory=lambda: fake_tts,
    )

    out_mp3 = tmp_path / "happy_line.mp3"
    res = router.synthesize_speech(
        SpeechRequest(
            text="今天居然提前下班了！",
            output_path=out_mp3,
            emotion="happy",
            voice="anime-girl-01",
            speed=1.15,
        )
    )
    assert res.provider == "minimax_speech"
    assert res.used_fallback is False
    assert res.sample_rate == 32000
    assert res.audio_path == out_mp3
    assert out_mp3.read_bytes() == audio_payload
    assert len(session.calls) == 1
    assert fake_tts.calls == []
    assert fake_tts.close_count == 0


def test_speech_explicit_provider_override_fish_audio(tmp_path: Path) -> None:
    fish_bytes = b"ID3_FAKE_FISH_AUDIO_STREAM"

    def handler(method: str, url: str, kwargs: Dict[str, Any]) -> _FakeResponse:
        assert method == "POST"
        assert url == "https://api.fish.audio/v1/tts"
        assert kwargs["headers"]["Authorization"] == "Bearer fish-live-token"
        body = kwargs["json"]
        assert body["text"] == "注意看，这里有个隐藏彩蛋！"
        assert body["reference_id"] == "ref-anime-va-42"
        assert body["emotion"] == "surprised"
        assert body["prosody"]["speed"] == 1.08
        return _FakeResponse(status_code=200, content=fish_bytes, headers={"Content-Type": "audio/mpeg"})

    session = _FakeSession(handler)
    router = AudioGenerationRouter(
        env={
            "MINIMAX_API_KEY": "sk-minimax-present-but-overridden",
            "FISH_AUDIO_API_KEY": "fish-live-token",
            "FISH_AUDIO_REFERENCE_ID": "ref-anime-va-42",
        },
        session=session,  # type: ignore[arg-type]
    )

    out_mp3 = tmp_path / "fish_override.mp3"
    res = router.synthesize_speech(
        SpeechRequest(
            text="注意看，这里有个隐藏彩蛋！",
            output_path=out_mp3,
            emotion="surprised",
            speed=1.08,
            provider="fish_audio",
        )
    )
    assert res.provider == "fish_audio"
    assert res.used_fallback is False
    assert res.audio_path == out_mp3
    assert out_mp3.read_bytes() == fish_bytes
    assert len(session.calls) == 1


def test_speech_fallback_chain_on_http_error_and_missing_key(tmp_path: Path) -> None:
    fish_bytes = b"ID3_FISH_BACKUP_AUDIO"

    # A. MiniMax HTTP 500 -> falls back to Fish-Audio and redacts secrets in error metadata
    def handler_mm_fail_fish_ok(method: str, url: str, kwargs: Dict[str, Any]) -> _FakeResponse:
        if "minimax" in url:
            raise RuntimeError("Upstream rejected token sk-minimax-secret-xyz with 500")
        assert "fish.audio" in url
        return _FakeResponse(status_code=200, content=fish_bytes, headers={"Content-Type": "audio/mpeg"})

    router_a = AudioGenerationRouter(
        env={
            "MINIMAX_API_KEY": "sk-minimax-secret-xyz",
            "FISH_AUDIO_API_KEY": "fish-backup-token",
        },
        session=_FakeSession(handler_mm_fail_fish_ok),  # type: ignore[arg-type]
    )
    res_a = router_a.synthesize_speech(SpeechRequest(text="测试自动切源", output_path=tmp_path / "a.mp3"))
    assert res_a.provider == "fish_audio"
    assert res_a.used_fallback is True
    assert res_a.audio_path.read_bytes() == fish_bytes
    errs_str = json.dumps(res_a.metadata.get("fallback_errors", []), ensure_ascii=False)
    assert "minimax_speech" in errs_str
    assert "sk-minimax-secret-xyz" not in errs_str
    assert "<REDACTED>" in errs_str

    # B. MiniMax HTTP 503 with Fish unconfigured -> falls back to local_kokoro & calls close()
    def handler_503(method: str, url: str, kwargs: Dict[str, Any]) -> _FakeResponse:
        return _FakeResponse(status_code=503, json_data={"error": "overloaded"})

    fake_tts_b = _FakeLocalTTS(sample_rate=24000)
    router_b = AudioGenerationRouter(
        env={"MINIMAX_API_KEY": "sk-minimax-secret-xyz"},
        session=_FakeSession(handler_503),  # type: ignore[arg-type]
        local_tts_factory=lambda: fake_tts_b,
    )
    out_wav_b = tmp_path / "fallback_kokoro.wav"
    res_b = router_b.synthesize_speech(
        SpeechRequest(text="零门槛回退本地语音", output_path=out_wav_b, emotion="sad", speed=0.95)
    )
    assert res_b.provider == "local_kokoro"
    assert res_b.used_fallback is True
    assert res_b.sample_rate == 24000
    assert out_wav_b.exists()
    with wave.open(str(out_wav_b), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getframerate() == 24000
        assert wf.getnframes() > 0
    assert fake_tts_b.close_count == 1
    assert fake_tts_b.calls[0]["speed"] == 0.95

    # C. Explicit minimax_speech when key missing + allow_fallback=True -> falls back to local_kokoro
    fake_tts_c = _FakeLocalTTS()
    router_c = AudioGenerationRouter(env={}, local_tts_factory=lambda: fake_tts_c)
    res_c = router_c.synthesize_speech(
        SpeechRequest(text="无Key自动降级", output_path=tmp_path / "c.wav", provider="minimax_speech"),
        allow_fallback=True,
    )
    assert res_c.provider == "local_kokoro"
    assert res_c.used_fallback is True
    assert fake_tts_c.close_count == 1


def test_speech_local_kokoro_closes_in_finally_and_no_fallback_errors(tmp_path: Path) -> None:
    # Explicit local_kokoro succeeds -> used_fallback=False and close() called
    fake_ok = _FakeLocalTTS()
    router_ok = AudioGenerationRouter(env={}, local_tts_factory=lambda: fake_ok)
    res_ok = router_ok.synthesize_speech(
        SpeechRequest(text="显式本地合成", output_path=tmp_path / "local.wav", provider="local_kokoro")
    )
    assert res_ok.provider == "local_kokoro"
    assert res_ok.used_fallback is False
    assert fake_ok.close_count == 1

    # Local TTS fails -> close() MUST still be called in finally
    fake_boom = _FakeLocalTTS(fail_exc=RuntimeError("synthetic kokoro failure"))
    router_boom = AudioGenerationRouter(env={}, local_tts_factory=lambda: fake_boom)
    with pytest.raises(RuntimeError, match="synthetic kokoro failure"):
        router_boom.synthesize_speech(
            SpeechRequest(text="触发异常", output_path=tmp_path / "boom.wav", provider="local_kokoro")
        )
    assert fake_boom.close_count == 1

    # allow_fallback=False with missing key -> raises without invoking local_tts
    fake_untouched = _FakeLocalTTS()
    router_strict = AudioGenerationRouter(env={}, local_tts_factory=lambda: fake_untouched)
    with pytest.raises(RuntimeError, match="not configured"):
        router_strict.synthesize_speech(
            SpeechRequest(text="严格模式", output_path=tmp_path / "strict.mp3", provider="minimax_speech"),
            allow_fallback=False,
        )
    assert fake_untouched.calls == []

    # allow_fallback=False on HTTP 500 -> raises immediately without falling back to fish_audio
    def handler_fail(method: str, url: str, kwargs: Dict[str, Any]) -> _FakeResponse:
        return _FakeResponse(status_code=500, json_data={"msg": "internal error"})

    sess_strict = _FakeSession(handler_fail)
    router_strict_http = AudioGenerationRouter(
        env={"MINIMAX_API_KEY": "sk-mm", "FISH_AUDIO_API_KEY": "sk-fish"},
        session=sess_strict,  # type: ignore[arg-type]
    )
    with pytest.raises(RuntimeError, match="minimax_speech"):
        router_strict_http.synthesize_speech(
            SpeechRequest(text="不要降级", output_path=tmp_path / "strict_http.mp3"),
            allow_fallback=False,
        )
    assert len(sess_strict.calls) == 1

    # Validation errors
    with pytest.raises(ValueError, match="must not be empty"):
        router_ok.synthesize_speech(SpeechRequest(text="   ", output_path=tmp_path / "empty.wav"))
    with pytest.raises(ValueError, match="Unknown speech provider"):
        router_ok.synthesize_speech(
            SpeechRequest(text="hi", output_path=tmp_path / "bad.wav", provider="nonexistent_tts")
        )


def test_music_minimax_priority_and_lyrics_payload(tmp_path: Path) -> None:
    song_bytes = b"ID3_MINIMAX_MUSIC_MP3_TRACK"
    seen_payloads: List[Dict[str, Any]] = []

    def handler(method: str, url: str, kwargs: Dict[str, Any]) -> _FakeResponse:
        assert method == "POST"
        assert url == "https://api.minimax.chat/v1/music_generation"
        assert kwargs["headers"]["Authorization"] == "Bearer sk-mm-music"
        seen_payloads.append(kwargs["json"])
        return _FakeResponse(
            status_code=200,
            json_data={
                "base_resp": {"status_code": 0, "status_msg": "success"},
                "data": {"audio": song_bytes.hex()},
            },
        )

    router = AudioGenerationRouter(
        env={
            "MINIMAX_API_KEY": "sk-mm-music",
            "MINIMAX_MUSIC_MODEL": "music-1.5",
            "SUNO_API_KEY": "suno-key-lower-priority",
        },
        session=_FakeSession(handler),  # type: ignore[arg-type]
    )

    # 1. Vocal track with custom lyrics & style
    out_vocal = tmp_path / "cyber_vocal.mp3"
    res_vocal = router.generate_music(
        MusicRequest(
            prompt="upbeat cyber anime dance anthem",
            output_path=out_vocal,
            duration_sec=22.0,
            lyrics="[Verse]\nCode all night, dance at dawn!",
            instrumental=False,
            style="j-pop synthwave",
        )
    )
    assert res_vocal.provider == "minimax_music"
    assert res_vocal.used_fallback is False
    assert out_vocal.read_bytes() == song_bytes
    assert "MiniMax Music" in res_vocal.credits_line
    assert "GB 45438-2025" in res_vocal.credits_line
    p1 = seen_payloads[0]
    assert p1["model"] == "music-1.5"
    assert p1["lyrics"] == "[Verse]\nCode all night, dance at dawn!"
    assert p1["instrumental"] is False
    assert p1["style"] == "j-pop synthwave"
    assert "j-pop synthwave" in p1["prompt"]

    # 2. Instrumental track with empty lyrics -> defaults to [Instrumental]
    out_inst = tmp_path / "cyber_inst.mp3"
    res_inst = router.generate_music(
        MusicRequest(
            prompt="fast 138 bpm phonk beat",
            output_path=out_inst,
            instrumental=True,
        )
    )
    assert res_inst.provider == "minimax_music"
    p2 = seen_payloads[1]
    assert p2["instrumental"] is True
    assert p2["lyrics"] == "[Instrumental]"


def test_music_suno_override_direct_and_polled(tmp_path: Path) -> None:
    suno_audio = b"ID3_SUNO_GENERATED_MP3"
    poll_count = {"n": 0}

    def handler(method: str, url: str, kwargs: Dict[str, Any]) -> _FakeResponse:
        if method == "POST" and url == "https://suno.mock.local/api/v1/generate":
            body = kwargs["json"]
            assert kwargs["headers"]["Authorization"] == "Bearer suno-test-key"
            assert body["style"] == "future funk"
            assert body["lyrics"] == "[Chorus] Dance on the rooftop"
            assert body["instrumental"] is False
            return _FakeResponse(status_code=200, json_data={"code": 200, "data": {"taskId": "suno-task-77"}})
        if method == "GET" and url == "https://suno.mock.local/api/v1/generate/record-info":
            assert kwargs["params"] == {"taskId": "suno-task-77"}
            poll_count["n"] += 1
            if poll_count["n"] == 1:
                return _FakeResponse(status_code=200, json_data={"data": {"status": "PENDING"}})
            return _FakeResponse(
                status_code=200,
                json_data={
                    "data": {
                        "status": "SUCCESS",
                        "sunoData": [{"audio_url": "https://cdn.suno.mock.local/track77.mp3"}],
                    }
                },
            )
        if method == "GET" and url == "https://cdn.suno.mock.local/track77.mp3":
            return _FakeResponse(status_code=200, content=suno_audio, headers={"Content-Type": "audio/mpeg"})
        raise AssertionError(f"Unexpected call: {method} {url}")

    router = AudioGenerationRouter(
        env={
            "MINIMAX_API_KEY": "sk-mm-overridden",
            "SUNO_API_KEY": "suno-test-key",
            "SUNO_BASE_URL": "https://suno.mock.local",
        },
        session=_FakeSession(handler),  # type: ignore[arg-type]
        poll_interval_sec=0.0,
        max_poll_attempts=4,
    )

    out_suno = tmp_path / "suno_track.mp3"
    res = router.generate_music(
        MusicRequest(
            prompt="energetic rooftop dance",
            output_path=out_suno,
            duration_sec=18.0,
            lyrics="[Chorus] Dance on the rooftop",
            instrumental=False,
            style="future funk",
            provider="suno",
        )
    )
    assert res.provider == "suno"
    assert res.used_fallback is False
    assert res.audio_path == out_suno
    assert out_suno.read_bytes() == suno_audio
    assert res.metadata["task_id"] == "suno-task-77"
    assert "Suno AI" in res.credits_line
    assert poll_count["n"] == 2

    # Direct audio_url response (no polling needed)
    def direct_handler(method: str, url: str, kwargs: Dict[str, Any]) -> _FakeResponse:
        if method == "POST":
            return _FakeResponse(
                status_code=200,
                json_data={"data": [{"audio_url": "https://cdn.suno.mock.local/direct.mp3"}]},
            )
        assert url == "https://cdn.suno.mock.local/direct.mp3"
        return _FakeResponse(status_code=200, content=b"ID3_DIRECT_SUNO", headers={"Content-Type": "audio/mpeg"})

    router_direct = AudioGenerationRouter(
        env={"SUNO_API_KEY": "suno-direct-key"},
        session=_FakeSession(direct_handler),  # type: ignore[arg-type]
    )
    out_direct = tmp_path / "suno_direct.mp3"
    res_direct = router_direct.generate_music(MusicRequest(prompt="happy j-pop", output_path=out_direct))
    assert res_direct.provider == "suno"
    assert res_direct.used_fallback is False
    assert out_direct.read_bytes() == b"ID3_DIRECT_SUNO"


def test_music_fallback_to_bilibili_bgm_hunter_and_strict_mode(tmp_path: Path) -> None:
    # A. Zero keys with explicit bgm_bvid -> directly extracts via BilibiliBgmHunter
    fake_hunter_a = _FakeBgmHunter()
    router_a = AudioGenerationRouter(env={}, bgm_hunter_factory=lambda: fake_hunter_a)
    out_a = tmp_path / "bvid_bgm.wav"
    res_a = router_a.generate_music(
        MusicRequest(prompt="anime dance", output_path=out_a, duration_sec=12.0, bgm_bvid="BV1ExactBvid01")
    )
    assert res_a.provider == "bilibili_bgm_hunter"
    assert res_a.used_fallback is True
    assert res_a.audio_path == out_a
    assert out_a.exists()
    assert "BV1ExactBvid01" in res_a.credits_line
    assert fake_hunter_a.search_calls == []
    assert fake_hunter_a.extract_calls[0]["source"] == "BV1ExactBvid01"

    # B. MiniMax HTTP 429 -> falls back to BilibiliBgmHunter search_bgm + extract_audio_clip
    def handler_429(method: str, url: str, kwargs: Dict[str, Any]) -> _FakeResponse:
        return _FakeResponse(status_code=429, json_data={"msg": "rate limited"})

    fake_hunter_b = _FakeBgmHunter()
    router_b = AudioGenerationRouter(
        env={"MINIMAX_API_KEY": "sk-mm-ratelimited"},
        session=_FakeSession(handler_429),  # type: ignore[arg-type]
        bgm_hunter_factory=lambda: fake_hunter_b,
    )
    out_b = tmp_path / "search_bgm.wav"
    res_b = router_b.generate_music(
        MusicRequest(prompt="dance remix", output_path=out_b, duration_sec=16.0, bgm_query="星奇摇 纯音乐")
    )
    assert res_b.provider == "bilibili_bgm_hunter"
    assert res_b.used_fallback is True
    assert fake_hunter_b.search_calls[0]["keyword"] == "星奇摇 纯音乐"
    assert fake_hunter_b.extract_calls[0]["source"] == "BV1DemoBgm99"
    assert res_b.metadata["fallback_errors"][0]["provider"] == "minimax_music"

    # C. allow_fallback=False on failing suno -> raises without invoking hunter
    fake_hunter_c = _FakeBgmHunter()
    router_c = AudioGenerationRouter(
        env={"SUNO_API_KEY": "suno-key"},
        session=_FakeSession(handler_429),  # type: ignore[arg-type]
        bgm_hunter_factory=lambda: fake_hunter_c,
    )
    with pytest.raises(RuntimeError, match="suno"):
        router_c.generate_music(
            MusicRequest(prompt="strict suno", output_path=tmp_path / "strict.mp3", provider="suno"),
            allow_fallback=False,
        )
    assert fake_hunter_c.search_calls == []
    assert fake_hunter_c.extract_calls == []

    # D. Validation errors
    with pytest.raises(ValueError, match="at least one"):
        router_a.generate_music(MusicRequest(prompt="  ", output_path=tmp_path / "empty.wav"))
    with pytest.raises(ValueError, match="Unknown music provider"):
        router_a.generate_music(
            MusicRequest(prompt="beat", output_path=tmp_path / "bad.wav", provider="unknown_music_api")
        )


def test_cli_audio_router_status_json_and_text(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("MINIMAX_API_KEY", "sk-cli-minimax-secret-12345")
    monkeypatch.setenv("MINIMAX_GROUP_ID", "grp-cli-secret-67890")
    monkeypatch.delenv("FISH_AUDIO_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("SUNO_API_KEY", "suno-cli-secret-abcde")

    # 1. JSON mode
    monkeypatch.setattr(sys, "argv", ["cli.py", "audio-router-status", "--json"])
    rc_json = cli.main()
    assert rc_json == 0
    out_json = capsys.readouterr().out
    parsed = json.loads(out_json)
    assert parsed["speech"]["active_provider"] == "minimax_speech"
    assert parsed["speech"]["providers"]["minimax_speech"]["configured"] is True
    assert parsed["speech"]["providers"]["fish_audio"]["configured"] is False
    assert parsed["speech"]["providers"]["local_kokoro"]["is_fallback"] is True
    assert parsed["music"]["active_provider"] == "minimax_music"
    assert parsed["music"]["providers"]["suno"]["configured"] is True
    assert parsed["music"]["providers"]["bilibili_bgm_hunter"]["is_fallback"] is True
    for secret in ("sk-cli-minimax-secret-12345", "grp-cli-secret-67890", "suno-cli-secret-abcde"):
        assert secret not in out_json

    # 2. Text mode
    monkeypatch.setattr(sys, "argv", ["cli.py", "audio-router-status"])
    rc_text = cli.main()
    assert rc_text == 0
    out_text = capsys.readouterr().out
    assert "Audio Generation Router Status" in out_text
    assert "minimax_speech" in out_text
    assert "bilibili_bgm_hunter" in out_text
    for secret in ("sk-cli-minimax-secret-12345", "grp-cli-secret-67890", "suno-cli-secret-abcde"):
        assert secret not in out_text


def test_character_voice_profiles_aliases_and_secret_redaction() -> None:
    # 1. Alias resolution & verified free Edge-TTS voices + pitches for all 3 studio leads
    assert set(CHARACTER_VOICE_PROFILES.keys()) == {"dafeiyu", "gemini_neko", "yowane_haku"}
    for prof in CHARACTER_VOICE_PROFILES.values():
        assert prof.edge_tts_voice in VERIFIED_FREE_EDGE_TTS_VOICES
    assert CHARACTER_VOICE_PROFILES["dafeiyu"].edge_tts_pitch == "-2Hz"
    assert CHARACTER_VOICE_PROFILES["gemini_neko"].edge_tts_pitch == "+4Hz"
    assert CHARACTER_VOICE_PROFILES["yowane_haku"].edge_tts_voice == "zh-TW-HsiaoYuNeural"
    assert CHARACTER_VOICE_PROFILES["yowane_haku"].edge_tts_pitch == "-4Hz"
    assert resolve_character_profile("大肥鱼").character_id == "dafeiyu"
    assert resolve_character_profile("DeepSeek").character_id == "dafeiyu"
    assert resolve_character_profile("Gemini娘").character_id == "gemini_neko"
    assert resolve_character_profile("猫娘").character_id == "gemini_neko"
    assert resolve_character_profile("弱音").character_id == "yowane_haku"
    assert resolve_character_profile("YOWANE_HAKU").character_id == "yowane_haku"

    with pytest.raises(ValueError, match="Unknown character voice profile"):
        resolve_character_profile("nonexistent_vtuber")

    # 2. Emotion mapping across MiniMax valid tags & Fish-Audio expressive tags
    assert resolve_emotion_spec("hype").minimax_emotion == "happy"
    assert resolve_emotion_spec("破防").minimax_emotion == "surprised"
    assert resolve_emotion_spec("破防").fish_emotion == "shocked"
    assert resolve_emotion_spec("deadpan").minimax_emotion == "calm"
    assert resolve_emotion_spec("tsundere").fish_emotion == "tsundere"
    assert resolve_emotion_spec("unknown_custom_vibe").minimax_emotion == "neutral"

    # 3. list_voice_profiles & get_status NEVER leak Fish reference IDs or API keys
    router = AudioGenerationRouter(
        env={
            "MINIMAX_API_KEY": "sk-mm-secret-profile-001",
            "MINIMAX_VOICE_DAFEIYU": "custom-fish-queen-v2",
            "FISH_AUDIO_API_KEY": "fish-api-secret-002",
            "FISH_AUDIO_REFERENCE_ID": "ref-global-secret-777",
            "FISH_AUDIO_REF_DAFEIYU": "ref-dafeiyu-secret-888",
            "FISH_AUDIO_REF_GEMINI_NEKO": "ref-gemini-secret-999",
            "FISH_AUDIO_REF_YOWANE_HAKU": "ref-yowane-secret-000",
        }
    )
    profiles = router.list_voice_profiles()
    assert len(profiles) == 3
    by_id = {p["character_id"]: p for p in profiles}
    assert by_id["dafeiyu"]["minimax_voice_id"] == "custom-fish-queen-v2"
    assert by_id["dafeiyu"]["minimax_custom_override"] is True
    assert by_id["dafeiyu"]["fish_reference_configured"] is True
    assert by_id["gemini_neko"]["minimax_custom_override"] is False
    assert by_id["gemini_neko"]["fish_reference_configured"] is True

    dumped = json.dumps(router.get_status(), ensure_ascii=False)
    for forbidden in (
        "sk-mm-secret-profile-001",
        "fish-api-secret-002",
        "ref-global-secret-777",
        "ref-dafeiyu-secret-888",
        "ref-gemini-secret-999",
        "ref-yowane-secret-000",
    ):
        assert forbidden not in dumped


def test_character_profile_minimax_and_fish_expressive_payloads(tmp_path: Path) -> None:
    mm_calls: List[Dict[str, Any]] = []
    fish_calls: List[Dict[str, Any]] = []

    def handler(method: str, url: str, kwargs: Dict[str, Any]) -> _FakeResponse:
        if "minimax" in url:
            mm_calls.append(kwargs["json"])
            return _FakeResponse(
                status_code=200,
                json_data={
                    "base_resp": {"status_code": 0, "status_msg": "success"},
                    "data": {"audio": b"ID3_MM_CHAR".hex()},
                    "extra_info": {"audio_sample_rate": 32000},
                },
            )
        if "fish.audio" in url:
            fish_calls.append(kwargs["json"])
            return _FakeResponse(
                status_code=200,
                content=b"ID3_FISH_CHAR",
                headers={"Content-Type": "audio/mpeg"},
            )
        raise AssertionError(f"Unexpected URL: {url}")

    router = AudioGenerationRouter(
        env={
            "MINIMAX_API_KEY": "sk-mm-test",
            "MINIMAX_VOICE_DAFEIYU": "mm-dafeiyu-custom",
            "FISH_AUDIO_API_KEY": "fish-test",
            "FISH_AUDIO_REFERENCE_ID": "ref-global-fallback",
            "FISH_AUDIO_REF_GEMINI_NEKO": "ref-gemini-exclusive",
        },
        session=_FakeSession(handler),  # type: ignore[arg-type]
    )

    # 1. Dafeiyu uses MINIMAX_VOICE_DAFEIYU, pitch=0, hype -> happy, natural speed <= 1.18
    res_df = router.synthesize_speech(
        SpeechRequest(
            text="服务器才没有偷懒，明明是老板脚本没优化！",
            output_path=tmp_path / "df_hype.mp3",
            character="大肥鱼",
            emotion="hype",
        )
    )
    assert res_df.provider == "minimax_speech"
    assert res_df.metadata["character"] == "dafeiyu"
    assert mm_calls[0]["voice_setting"]["voice_id"] == "mm-dafeiyu-custom"
    assert mm_calls[0]["voice_setting"]["pitch"] == 0
    assert mm_calls[0]["voice_setting"]["emotion"] == "happy"
    assert 0.80 <= mm_calls[0]["voice_setting"]["speed"] <= 1.18

    # 2. Gemini Neko with 破防 -> surprised, pitch=+1; Yowane with deadpan -> calm, pitch=-1
    router.synthesize_speech(
        SpeechRequest(
            text="什么？！今天播放卡在12了？",
            output_path=tmp_path / "gm_shocked.mp3",
            character="gemini_neko",
            emotion="破防",
        )
    )
    assert mm_calls[1]["voice_setting"]["voice_id"] == "female-shaonv"
    assert mm_calls[1]["voice_setting"]["pitch"] == 1
    assert mm_calls[1]["voice_setting"]["emotion"] == "surprised"

    router.synthesize_speech(
        SpeechRequest(
            text="都冷静一点，经费只剩四毛了。",
            output_path=tmp_path / "yw_deadpan.mp3",
            character="弱音",
            emotion="deadpan",
        )
    )
    assert mm_calls[2]["voice_setting"]["voice_id"] == "female-chengshu"
    assert mm_calls[2]["voice_setting"]["pitch"] == -1
    assert mm_calls[2]["voice_setting"]["emotion"] == "calm"

    # 3. Explicit request.voice overrides character env/default voice
    router.synthesize_speech(
        SpeechRequest(
            text="临时客串旁白声线。",
            output_path=tmp_path / "override.mp3",
            character="dafeiyu",
            voice="explicit-voice-override",
            emotion="calm",
            speed=1.02,
            pitch=2,
        )
    )
    assert mm_calls[3]["voice_setting"]["voice_id"] == "explicit-voice-override"
    assert mm_calls[3]["voice_setting"]["pitch"] == 2
    assert mm_calls[3]["voice_setting"]["speed"] == 1.02

    # 4. Fish-Audio receives per-character FISH_AUDIO_REF_GEMINI_NEKO over global ref
    res_fish_gm = router.synthesize_speech(
        SpeechRequest(
            text="喵呜，4.9星封面才是正义！",
            output_path=tmp_path / "gm_fish.mp3",
            character="Gemini娘",
            provider="fish_audio",
        )
    )
    assert res_fish_gm.provider == "fish_audio"
    assert fish_calls[0]["reference_id"] == "ref-gemini-exclusive"
    assert fish_calls[0]["emotion"] == "excited"

    # Yowane falls back to global FISH_AUDIO_REFERENCE_ID when per-character Fish ref is unset
    router.synthesize_speech(
        SpeechRequest(
            text="先把剧本和借物表检查一遍。",
            output_path=tmp_path / "yw_fish.mp3",
            character="yowane_haku",
            emotion="calm",
            provider="fish_audio",
        )
    )
    assert fish_calls[1]["reference_id"] == "ref-global-fallback"
    assert fish_calls[1]["emotion"] == "calm"

    # Validation checks
    with pytest.raises(ValueError, match="Unknown character voice profile"):
        router.synthesize_speech(SpeechRequest(text="hi", output_path=tmp_path / "bad.mp3", character="ghost"))
    with pytest.raises(ValueError, match="speed must be > 0"):
        router.synthesize_speech(SpeechRequest(text="hi", output_path=tmp_path / "bad_s.mp3", speed=0.0))


def test_character_profile_local_fallback_edge_voice_and_legacy_stub(tmp_path: Path) -> None:
    # A. Legacy 3-arg _FakeLocalTTS must work cleanly without TypeError
    fake_legacy = _FakeLocalTTS()
    router_legacy = AudioGenerationRouter(env={}, local_tts_factory=lambda: fake_legacy)
    for char_id, expected_voice in (
        ("dafeiyu", "zf_018"),
        ("gemini_neko", "zf_001"),
        ("yowane_haku", "zf_004"),
    ):
        res = router_legacy.synthesize_speech(
            SpeechRequest(
                text=f"{char_id} 测试台词",
                output_path=tmp_path / f"legacy_{char_id}.wav",
                character=char_id,
            )
        )
        assert res.provider == "local_kokoro"
        assert res.used_fallback is True
        assert res.metadata["voice"] == expected_voice
    assert fake_legacy.close_count == 3
    assert [c["voice"] for c in fake_legacy.calls] == ["zf_018", "zf_001", "zf_004"]

    # B. edge_voice-aware TTS stub receives each character's edge_tts_voice & closes in finally
    class _EdgeAwareLocalTTS:
        sample_rate = 24000

        def __init__(self) -> None:
            self.calls: List[Dict[str, Any]] = []
            self.close_count = 0

        def synthesize_text(
            self,
            text: str,
            voice: str = "zf_001",
            speed: float = 1.03,
            edge_voice: str = "zh-CN-XiaoxiaoNeural",
        ) -> List[float]:
            self.calls.append({"text": text, "voice": voice, "speed": speed, "edge_voice": edge_voice})
            return [0.0, 0.2, -0.2, 0.0] * 30

        def close(self) -> None:
            self.close_count += 1

    edge_stub = _EdgeAwareLocalTTS()
    router_edge = AudioGenerationRouter(env={}, local_tts_factory=lambda: edge_stub)
    for char_id, expected_edge in (
        ("大肥鱼", "zh-CN-XiaoxiaoNeural"),
        ("Gemini娘", "zh-CN-XiaoyiNeural"),
        ("弱音", "zh-TW-HsiaoYuNeural"),
    ):
        res = router_edge.synthesize_speech(
            SpeechRequest(
                text=f"{char_id} 双通道本地声线",
                output_path=tmp_path / f"edge_{char_id}.wav",
                character=char_id,
            )
        )
        assert res.metadata["edge_voice"] == expected_edge
    assert edge_stub.close_count == 3
    assert [c["edge_voice"] for c in edge_stub.calls] == [
        "zh-CN-XiaoxiaoNeural",
        "zh-CN-XiaoyiNeural",
        "zh-TW-HsiaoYuNeural",
    ]

    # C. 5-arg edge_voice + edge_pitch-aware TTS stub receives exact pitch overrides
    class _EdgePitchAwareLocalTTS:
        sample_rate = 24000

        def __init__(self) -> None:
            self.calls: List[Dict[str, Any]] = []
            self.close_count = 0

        def synthesize_text(
            self,
            text: str,
            voice: str = "zf_001",
            speed: float = 1.03,
            edge_voice: str = "zh-CN-XiaoxiaoNeural",
            edge_pitch: str = "+0Hz",
        ) -> List[float]:
            self.calls.append(
                {
                    "text": text,
                    "voice": voice,
                    "speed": speed,
                    "edge_voice": edge_voice,
                    "edge_pitch": edge_pitch,
                }
            )
            return [0.0, 0.2, -0.2, 0.0] * 30

        def close(self) -> None:
            self.close_count += 1

    pitch_stub = _EdgePitchAwareLocalTTS()
    router_pitch = AudioGenerationRouter(env={}, local_tts_factory=lambda: pitch_stub)
    for char_id, expected_pitch in (
        ("dafeiyu", "-2Hz"),
        ("gemini_neko", "+4Hz"),
        ("yowane_haku", "-4Hz"),
    ):
        res_p = router_pitch.synthesize_speech(
            SpeechRequest(
                text=f"{char_id} 音调绑定测试",
                output_path=tmp_path / f"pitch_{char_id}.wav",
                character=char_id,
            )
        )
        assert res_p.metadata["edge_pitch"] == expected_pitch
    assert pitch_stub.close_count == 3
    assert [c["edge_pitch"] for c in pitch_stub.calls] == ["-2Hz", "+4Hz", "-4Hz"]


def test_local_neural_tts_edge_fallback_passes_pitch(monkeypatch: pytest.MonkeyPatch) -> None:
    import types
    from core.local_tts import LocalNeuralTTS

    comm_calls: List[Dict[str, Any]] = []

    class _FakeCommunicate:
        def __init__(self, text: str, voice: str = "", rate: str = "+0%", pitch: str = "+0Hz") -> None:
            comm_calls.append({"text": text, "voice": voice, "rate": rate, "pitch": pitch})

        async def save(self, mp3_path: str) -> None:
            Path(mp3_path).write_bytes(b"ID3_FAKE_EDGE_MP3")

    monkeypatch.setitem(sys.modules, "edge_tts", types.SimpleNamespace(Communicate=_FakeCommunicate))

    def _fake_subprocess_run(cmd: List[str], **_kwargs: Any) -> Any:
        out_wav = Path(cmd[-1])
        with wave.open(str(out_wav), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(b"\x00\x10\x00\xf0" * 24)
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr("core.local_tts.subprocess.run", _fake_subprocess_run)

    tts = LocalNeuralTTS()
    monkeypatch.setattr(tts, "_synth_kokoro", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("offline")))
    samples = tts.synthesize_text(
        "先冷静把借物表看一遍。",
        voice="zf_004",
        speed=0.98,
        edge_voice="zh-TW-HsiaoYuNeural",
        edge_pitch="-4Hz",
    )
    assert len(samples) == 48
    assert comm_calls == [
        {
            "text": "先冷静把借物表看一遍。",
            "voice": "zh-TW-HsiaoYuNeural",
            "rate": "-2%",
            "pitch": "-4Hz",
        }
    ]


def test_synthesize_dialogue_multi_character_batch_and_manifest(tmp_path: Path) -> None:
    lines = [
        DialogueLine(character="大肥鱼", text="法官大人，服务器繁忙是因为她在摸鱼！", emotion="angry"),
        DialogueLine(character="Gemini娘", text="哼，我的4.9星封面才是流量救星喵！", emotion="excited"),
        DialogueLine(character="弱音", text="行了，都去写第20集剧本吧。", emotion="calm", line_id="closing_verdict"),
    ]

    # 1. Local fallback batch synthesis
    fake_tts = _FakeLocalTTS()
    router_local = AudioGenerationRouter(env={}, local_tts_factory=lambda: fake_tts)
    out_dir_local = tmp_path / "dialogue_local"
    dlg_res = router_local.synthesize_dialogue(lines=lines, output_dir=out_dir_local, file_ext="wav")
    assert dlg_res.providers_used == ["local_kokoro"]
    assert dlg_res.used_fallback is True
    assert dlg_res.manifest_path == out_dir_local / "dialogue_manifest.json"
    assert dlg_res.manifest_path.is_file()
    assert fake_tts.close_count == 3
    assert len(dlg_res.lines) == 3
    assert Path(dlg_res.lines[0]["audio_path"]).name == "01_dafeiyu.wav"
    assert Path(dlg_res.lines[1]["audio_path"]).name == "02_gemini_neko.wav"
    assert Path(dlg_res.lines[2]["audio_path"]).name == "closing_verdict.wav"
    for item in dlg_res.lines:
        assert Path(item["audio_path"]).is_file()
        assert 0.80 <= float(item["speed"]) <= 1.18

    manifest_data = json.loads(dlg_res.manifest_path.read_text(encoding="utf-8"))
    assert len(manifest_data["lines"]) == 3
    assert manifest_data["lines"][2]["character"] == "yowane_haku"

    # 2. Fish-Audio batch synthesis NEVER writes raw reference_id secret into dialogue_manifest.json
    def fish_handler(method: str, url: str, kwargs: Dict[str, Any]) -> _FakeResponse:
        return _FakeResponse(status_code=200, content=b"ID3_FISH_BATCH", headers={"Content-Type": "audio/mpeg"})

    router_fish = AudioGenerationRouter(
        env={
            "FISH_AUDIO_API_KEY": "fish-batch-secret-token",
            "FISH_AUDIO_REF_DAFEIYU": "secret-fish-ref-df-555",
            "FISH_AUDIO_REF_GEMINI_NEKO": "secret-fish-ref-gm-666",
            "FISH_AUDIO_REF_YOWANE_HAKU": "secret-fish-ref-yw-777",
        },
        session=_FakeSession(fish_handler),  # type: ignore[arg-type]
    )
    out_dir_fish = tmp_path / "dialogue_fish"
    fish_res = router_fish.synthesize_dialogue(lines=lines, output_dir=out_dir_fish, file_ext="mp3")
    assert fish_res.providers_used == ["fish_audio"]
    assert fish_res.manifest_path is not None
    raw_manifest_text = fish_res.manifest_path.read_text(encoding="utf-8")
    for secret_val in (
        "fish-batch-secret-token",
        "secret-fish-ref-df-555",
        "secret-fish-ref-gm-666",
        "secret-fish-ref-yw-777",
    ):
        assert secret_val not in raw_manifest_text
    assert all(line["fish_reference_configured"] is True for line in fish_res.lines)

    # Empty lines validation
    with pytest.raises(ValueError, match="must not be empty"):
        router_local.synthesize_dialogue(lines=[], output_dir=tmp_path / "empty_dlg")


def test_cli_audio_router_profiles_and_synthesize_speech(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    monkeypatch.delenv("FISH_AUDIO_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("SUNO_API_KEY", raising=False)
    monkeypatch.setenv("FISH_AUDIO_REF_DAFEIYU", "secret-cli-fish-ref-999")

    # 1. audio-router-status includes voice_profiles without leaking secret Fish refs
    monkeypatch.setattr(sys, "argv", ["cli.py", "audio-router-status", "--json"])
    assert cli.main() == 0
    st_json = capsys.readouterr().out
    st_parsed = json.loads(st_json)
    assert set(st_parsed["voice_profiles"].keys()) == {"dafeiyu", "gemini_neko", "yowane_haku"}
    assert st_parsed["voice_profiles"]["dafeiyu"]["fish_reference_configured"] is True
    assert "secret-cli-fish-ref-999" not in st_json

    monkeypatch.setattr(sys, "argv", ["cli.py", "audio-router-status"])
    assert cli.main() == 0
    st_text = capsys.readouterr().out
    assert "Character Voice Profiles" in st_text
    assert "yowane_haku" in st_text
    assert "secret-cli-fish-ref-999" not in st_text

    # 2. synthesize-speech CLI executes offline via monkeypatched local TTS factory
    fake_tts = _FakeLocalTTS()
    monkeypatch.setattr(AudioGenerationRouter, "_create_local_tts", lambda self: fake_tts)
    out_wav = tmp_path / "cli_gemini.wav"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cli.py",
            "synthesize-speech",
            "--character",
            "gemini_neko",
            "--emotion",
            "excited",
            "--text",
            "欢迎来到第20期现场！",
            "--output",
            str(out_wav),
            "--json",
        ],
    )
    assert cli.main() == 0
    synth_out = capsys.readouterr().out
    synth_json = json.loads(synth_out)
    assert synth_json["provider"] == "local_kokoro"
    assert synth_json["metadata"]["character"] == "gemini_neko"
    assert synth_json["metadata"]["voice"] == "zf_001"
    assert out_wav.is_file()
    assert fake_tts.close_count == 1


def test_speech_deepseek_tts_wav_pcm_streaming_header_and_fallback(tmp_path: Path) -> None:
    import io as _io
    import struct

    # Build a synthetic streaming WAV payload (0xFFFFFFFF placeholder chunk sizes like live DeepSeek API)
    pcm_body = b"\x10\x02\xf0\xfd" * 600  # 2400 bytes of 24kHz mono 16-bit PCM
    buf = _io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(pcm_body)
    streaming_wav = bytearray(buf.getvalue())
    struct.pack_into("<I", streaming_wav, 4, 0xFFFFFFFF)
    struct.pack_into("<I", streaming_wav, 40, 0xFFFFFFFF)

    seen_calls: List[Dict[str, Any]] = []

    def ok_handler(method: str, url: str, kwargs: Dict[str, Any]) -> _FakeResponse:
        assert method == "POST"
        assert url == "https://api.deepseek.com/v1/tools/tts"
        assert kwargs["headers"]["Authorization"] == "Bearer sk-deepseek-mock-key-01"
        body = kwargs["json"]
        seen_calls.append(body)
        if body["format"] == "pcm":
            return _FakeResponse(
                status_code=200,
                content=pcm_body,
                headers={"Content-Type": "audio/pcm; rate=24000"},
            )
        return _FakeResponse(status_code=200, content=bytes(streaming_wav), headers={"Content-Type": "audio/wav"})

    fake_tts = _FakeLocalTTS()
    router = AudioGenerationRouter(
        env={"DEEPSEEK_API_KEY": "sk-deepseek-mock-key-01"},
        session=_FakeSession(ok_handler),  # type: ignore[arg-type]
        local_tts_factory=lambda: fake_tts,
    )
    st = router.get_status()
    assert st["speech"]["active_provider"] == "deepseek_tts"
    assert st["speech"]["using_fallback"] is False
    assert "sk-deepseek-mock-key-01" not in json.dumps(st)

    # 1. WAV synthesis repairs 0xFFFFFFFF header to exact duration
    out_wav = tmp_path / "ds_stella.wav"
    res_wav = router.synthesize_speech(
        SpeechRequest(text="发开工就能生成像素小人！", output_path=out_wav, character="dafeiyu")
    )
    assert res_wav.provider == "deepseek_tts"
    assert res_wav.used_fallback is False
    assert res_wav.sample_rate == 24000
    assert seen_calls[0]["voice_id"] == "stella"
    assert seen_calls[0]["format"] == "wav"
    assert seen_calls[0]["filter_markdown"] is True
    with wave.open(str(out_wav), "rb") as wf:
        assert wf.getframerate() == 24000
        assert wf.getnframes() == len(pcm_body) // 2

    # 2. Explicit voice=tide + .pcm output
    out_pcm = tmp_path / "ds_tide.pcm"
    res_pcm = router.synthesize_speech(
        SpeechRequest(text="旁白切到暗潮音色", output_path=out_pcm, voice="tide", provider="deepseek_tts")
    )
    assert res_pcm.provider == "deepseek_tts"
    assert seen_calls[1]["voice_id"] == "tide"
    assert seen_calls[1]["format"] == "pcm"
    assert out_pcm.read_bytes() == pcm_body
    assert fake_tts.calls == []

    # 3. HTTP 429 / 400 / truncated response gracefully falls back to local_kokoro & redacts key
    for fail_resp in (
        _FakeResponse(status_code=429, json_data={"error": "rate limit"}),
        _FakeResponse(status_code=400, json_data={"error": "Content Exists Risk"}),
        _FakeResponse(status_code=200, content=b"short", headers={"Content-Type": "audio/wav"}),
    ):
        fake_fb = _FakeLocalTTS()
        r_fail = AudioGenerationRouter(
            env={"DEEPSEEK_API_KEY": "sk-deepseek-secret-never-leak"},
            session=_FakeSession(lambda *_a: fail_resp),  # type: ignore[arg-type]
            local_tts_factory=lambda: fake_fb,
        )
        res_fb = r_fail.synthesize_speech(SpeechRequest(text="触发异常测试回退", output_path=tmp_path / "fb.wav"))
        assert res_fb.provider == "local_kokoro"
        assert res_fb.used_fallback is True
        assert fake_fb.close_count == 1
        assert "sk-deepseek-secret-never-leak" not in json.dumps(res_fb.to_dict(), ensure_ascii=False)

    # 4. Upstream exception containing raw key redacts it cleanly in fallback metadata
    def boom_handler(*_a: Any) -> _FakeResponse:
        raise RuntimeError("Upstream 503 for token sk-deepseek-secret-boom-99")

    fake_fb_boom = _FakeLocalTTS()
    r_boom = AudioGenerationRouter(
        env={"DEEPSEEK_API_KEY": "sk-deepseek-secret-boom-99"},
        session=_FakeSession(boom_handler),  # type: ignore[arg-type]
        local_tts_factory=lambda: fake_fb_boom,
    )
    res_boom = r_boom.synthesize_speech(SpeechRequest(text="异常脱敏测试", output_path=tmp_path / "fb_boom.wav"))
    dumped_boom = json.dumps(res_boom.to_dict(), ensure_ascii=False)
    assert "sk-deepseek-secret-boom-99" not in dumped_boom
    assert "<REDACTED>" in dumped_boom
