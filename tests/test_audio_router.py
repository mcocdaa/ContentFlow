"""Unit tests for Kaizen Slice K4: Pluggable AudioGenerationRouter & `cli.py audio-router-status`.

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
    AudioGenerationRouter,
    MusicRequest,
    SpeechRequest,
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
    assert status_empty["speech"]["priority"] == ["minimax_speech", "fish_audio", "local_kokoro"]
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
            "SUNO_API_KEY": "dummy_suno_key",
        }
    )
    st_ph = router_placeholders.get_status()
    assert st_ph["speech"]["active_provider"] == "local_kokoro"
    assert st_ph["music"]["active_provider"] == "bilibili_bgm_hunter"
    assert st_ph["speech"]["providers"]["minimax_speech"]["configured"] is False
    assert st_ph["speech"]["providers"]["fish_audio"]["configured"] is False
    assert st_ph["music"]["providers"]["suno"]["configured"] is False

    # 3. Secondary keys only -> fish_audio & suno active
    router_secondary = AudioGenerationRouter(
        env={
            "FISH_AUDIO_API_KEY": "fish_live_key_alpha",
            "SUNO_API_KEY": "suno_live_key_beta",
        }
    )
    st_sec = router_secondary.get_status()
    assert st_sec["speech"]["active_provider"] == "fish_audio"
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
