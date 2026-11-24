"""Offline mocked unit & integration tests for Kaizen Slice K8.

Verifies:
- Absolute Zero-Mic Guarantee across all live_studio sources, CLI launcher, Dockerfile.live,
  and generated FFmpeg commands (zero `/dev/snd`, `alsa`, `pulse`, `pyaudio`, `sounddevice`).
- Absolute Zero-PII / Zero-Secret Exposure in `scrub_rtmp_secrets()`, `RoomStatus`,
  `StartLiveResult`, `BilibiliLiveController`, FFmpeg stderr scrubbing, and CLI status lines.
- `BilibiliLiveController`: `get_my_room_info`, `update_room_title`, non-fatal `upload_live_cover`,
  `start_live` (`code == 60024` generates face-auth QR PNG without bypassing; `code == 0` builds
  in-memory RTMP URL), and idempotent `stop_live`.
- `HeadlessStageRenderer`: 1920x1080 RGB24 output, active-speaker toggle, canonical/vector fallback,
  compliance banner & sanitized danmaku rendering.
- `SyntheticAudioMixer`: exact 6400-byte 48kHz stereo `s16le` video-frame PCM slices, offline
  dual-pitch synth fallback when `edge-tts` fails, speech+BGM ducking, and custom `--bgm-path`.
- `HeadlessLiveStreamer`: `go-live` calls `stop_live` inside `finally:` even on mid-stream errors,
  `code == 60024` never spawns FFmpeg, stderr scrubs RTMP secrets, and `HighlightTracker` exports
  clip plans cleanly.
- `scripts/launch_headless_live.py`: CLI argument parsing and single-line grep-friendly status JSON.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import re
import subprocess
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from core.audio_router import VERIFIED_FREE_EDGE_TTS_VOICES
from core.auth_vault import AuthVault
from core.live_studio import (
    AI_DISCLOSURE_BANNER,
    BYTES_PER_VIDEO_FRAME,
    DUAL_CAST,
    FACE_AUTH_REQUIRED_CODE,
    REDACTED_RTMP_TOKEN,
    REDACTED_TOKEN,
    TRIO_CAST,
    BilibiliLiveController,
    DualAILiveDirector,
    HeadlessLiveStreamer,
    HeadlessStageRenderer,
    HighlightTracker,
    LivePollState,
    OfflineBanterResponder,
    PersonaTurn,
    RoomStatus,
    StartLiveResult,
    SyntheticAudioMixer,
    scrub_rtmp_secrets,
    synthesize_offline_fallback_pcm,
)
from core.live_studio.headless_streamer import VOICE_MAP, VOICE_STYLE_MAP
from scripts import launch_headless_live

REPO_ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN_MIC_RE = re.compile(r"/dev/snd|alsa|pulse|pyaudio|sounddevice", re.IGNORECASE)


class _FakeResponse:
    def __init__(self, payload: Dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> Dict[str, Any]:
        return self._payload


class _FakeSession:
    def __init__(
        self,
        *,
        get_map: Optional[Dict[str, _FakeResponse]] = None,
        post_map: Optional[Dict[str, _FakeResponse | Exception]] = None,
    ) -> None:
        self.get_map = get_map or {}
        self.post_map = post_map or {}
        self.calls: List[Tuple[str, str, Dict[str, Any]]] = []

    def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append(("GET", url, kwargs))
        for key, resp in self.get_map.items():
            if key in url:
                return resp
        raise AssertionError(f"Unexpected GET {url}")

    def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append(("POST", url, kwargs))
        for key, resp in self.post_map.items():
            if key in url:
                if isinstance(resp, Exception):
                    raise resp
                return resp
        raise AssertionError(f"Unexpected POST {url}")


def _make_vault_with_cookies(tmp_path: Path) -> AuthVault:
    vault = AuthVault(vault_dir=tmp_path / "vault")
    vault.save_bilibili_session(
        cookies={
            "SESSDATA": "fake_sessdata_super_secret_value",
            "bili_jct": "fake_csrf_jct_token_999",
            "DedeUserID": "987654321",
        }
    )
    return vault


# ---------------------------------------------------------------------------
# 1. Absolute Zero-Mic Source, Dockerfile & FFmpeg Command Invariants
# ---------------------------------------------------------------------------


def test_zero_mic_guarantee_across_sources_and_dockerfile() -> None:
    targets: List[Path] = [
        *sorted((REPO_ROOT / "core" / "live_studio").glob("*")),
        REPO_ROOT / "scripts" / "launch_headless_live.py",
        REPO_ROOT / "Dockerfile.live",
    ]
    checked = 0
    for path in targets:
        if not path.is_file():
            continue
        checked += 1
        content = path.read_text(encoding="utf-8")
        match = FORBIDDEN_MIC_RE.search(content)
        assert match is None, f"Forbidden hardware-audio token {match.group(0)!r} found in {path}"
    assert checked >= 8

    dockerfile_text = (REPO_ROOT / "Dockerfile.live").read_text(encoding="utf-8")
    assert "python:3.12-slim" in dockerfile_text
    assert "fonts-noto-cjk" in dockerfile_text
    assert "ffmpeg" in dockerfile_text
    assert "USER liveuser" in dockerfile_text
    assert "launch_headless_live.py" in dockerfile_text


def test_ffmpeg_command_uses_dual_os_pipes_and_zero_mic(tmp_path: Path) -> None:
    renderer = HeadlessStageRenderer(repo_root=tmp_path)
    mixer = SyntheticAudioMixer(use_edge_tts=False)
    streamer = HeadlessLiveStreamer(renderer=renderer, audio_mixer=mixer, video_encoder="h264_nvenc")

    dry_cmd = streamer.build_ffmpeg_command(
        video_fd=11,
        audio_fd=12,
        mode="dry-stream",
        output_mp4=tmp_path / "out.mp4",
    )
    joined_dry = " ".join(dry_cmd)
    assert FORBIDDEN_MIC_RE.search(joined_dry) is None
    assert "-f rawvideo -pix_fmt rgb24 -s 1920x1080 -r 30 -i pipe:11" in joined_dry
    assert "-f s16le -ar 48000 -ac 2 -i pipe:12" in joined_dry
    assert "-c:v h264_nvenc" in joined_dry
    assert "-b:v 4500k" in joined_dry
    assert "-g 60" in joined_dry
    assert "-preset p4" in joined_dry
    assert "-pix_fmt yuv420p" in joined_dry

    live_cmd_x264 = streamer.build_ffmpeg_command(
        video_fd=13,
        audio_fd=14,
        mode="go-live",
        rtmp_url="rtmp://live-push.bilivideo.com/live-bvc/?streamname=live_1&key=secret123",
        record_path=tmp_path / "rec.mkv",
        video_encoder="libx264",
    )
    joined_live = " ".join(live_cmd_x264)
    assert FORBIDDEN_MIC_RE.search(joined_live) is None
    assert "-c:v libx264" in joined_live
    assert "-f tee" in joined_live
    assert "[f=flv:onfail=ignore]" in joined_live


# ---------------------------------------------------------------------------
# 2. Zero-PII & RTMP Secret Redaction (`bilibili_live_api.py`)
# ---------------------------------------------------------------------------


def test_scrub_rtmp_secrets_and_redacted_models() -> None:
    secret_url = (
        "rtmp://live-push.bilivideo.com/live-bvc/?streamname=live_555666_999&key=my_ultra_secret_key_888&schedule=rtmp"
    )
    raw_log = (
        f"Error writing trailer to {secret_url} room_id=31415926 uid=987654321 "
        "DedeUserID=987654321 SESSDATA=secret_cookie bili_jct=secret_csrf "
        "host=live-push.bilivideo.com/live-bvc/?key=anothersecret"
    )
    scrubbed = scrub_rtmp_secrets(raw_log)
    for forbidden in (
        "live_555666_999",
        "my_ultra_secret_key_888",
        "anothersecret",
        "31415926",
        "987654321",
        "secret_cookie",
        "secret_csrf",
        "rtmp://",
        "live-push.bilivideo.com",
    ):
        assert forbidden not in scrubbed, f"Secret leaked after scrubbing: {forbidden}"
    assert REDACTED_RTMP_TOKEN in scrubbed
    assert REDACTED_TOKEN in scrubbed

    room = RoomStatus(
        room_id=31415926,
        title="双AI策划直播",
        area_v2_id=1062,
        area_v2_name="AI互动",
        live_status=0,
        uid=987654321,
    )
    room_repr = repr(room)
    room_dict = room.to_redacted_dict()
    assert "31415926" not in room_repr
    assert "987654321" not in room_repr
    assert REDACTED_TOKEN in room_repr
    assert room_dict["room_id"] == REDACTED_TOKEN
    assert room_dict["uid"] == REDACTED_TOKEN
    assert room_dict["title"] == "双AI策划直播"

    start_res = StartLiveResult(
        ok=True,
        status="live",
        code=0,
        room_id=31415926,
        rtmp_addr="rtmp://live-push.bilivideo.com/live-bvc/",
        rtmp_code="?streamname=live_555666_999&key=my_ultra_secret_key_888",
        rtmp_url=secret_url,
        message=f"Connected to {secret_url}",
    )
    res_repr = repr(start_res)
    res_dict = start_res.to_safe_dict()
    for secret in ("31415926", "live_555666_999", "my_ultra_secret_key_888", "live-push.bilivideo.com"):
        assert secret not in res_repr
        assert secret not in json.dumps(res_dict, ensure_ascii=False)
    assert REDACTED_RTMP_TOKEN in res_repr
    assert REDACTED_TOKEN in res_repr
    assert res_dict["rtmp_url"] == REDACTED_RTMP_TOKEN
    assert res_dict["room_id"] == REDACTED_TOKEN


# ---------------------------------------------------------------------------
# 3. `BilibiliLiveController` Mocked API Behavior
# ---------------------------------------------------------------------------


def test_bilibili_live_controller_room_info_title_and_nonfatal_cover(tmp_path: Path) -> None:
    vault = _make_vault_with_cookies(tmp_path)
    fake_session = _FakeSession(
        get_map={
            "GetInfo": _FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "room_id": 22334455,
                        "uid": 987654321,
                        "title": "旧标题",
                        "area_v2_id": 1062,
                        "area_v2_name": "AI互动实验",
                        "live_status": 0,
                    },
                }
            )
        },
        post_map={
            "Room/update": _FakeResponse({"code": 0, "message": "ok"}),
            "upload/web/image": RuntimeError("network down with SESSDATA=secret_leak"),
        },
    )
    ctrl = BilibiliLiveController(vault=vault, session=fake_session)  # type: ignore[arg-type]
    assert "fake_sessdata" not in repr(ctrl)

    info = ctrl.get_my_room_info()
    assert info.room_id == 22334455
    assert info.area_v2_id == 1062
    assert info.to_redacted_dict()["room_id"] == REDACTED_TOKEN

    upd = ctrl.update_room_title(info.room_id, "双AI合租直播 @股东 测试")
    assert upd["ok"] is True
    assert upd["room_id"] == REDACTED_TOKEN
    assert "@" not in upd["title"]

    # Non-fatal cover upload when file missing
    missing_res = ctrl.upload_live_cover(tmp_path / "does_not_exist.jpg", room_id=info.room_id)
    assert missing_res["ok"] is False
    assert missing_res["non_fatal"] is True

    # Non-fatal cover upload when network throws exception (must scrub secret and not crash!)
    cover_file = tmp_path / "cover.jpg"
    Image.new("RGB", (64, 36), (120, 180, 255)).save(cover_file, format="JPEG")
    err_res = ctrl.upload_live_cover(cover_file, room_id=info.room_id)
    assert err_res["ok"] is False
    assert err_res["non_fatal"] is True
    assert "secret_leak" not in json.dumps(err_res)


def test_bilibili_live_controller_face_auth_60024_generates_qr_without_bypass(tmp_path: Path) -> None:
    vault = _make_vault_with_cookies(tmp_path)
    qr_target = tmp_path / "output" / "live_face_auth_qr.png"
    fake_session = _FakeSession(
        post_map={
            "startLive": _FakeResponse(
                {
                    "code": FACE_AUTH_REQUIRED_CODE,
                    "message": "需要人脸认证",
                    "data": {
                        "qr": "https://www.bilibili.com/blackboard/live/face-auth-middle.html?source=live&token=demo123",
                    },
                }
            )
        }
    )
    ctrl = BilibiliLiveController(
        vault=vault,
        session=fake_session,  # type: ignore[arg-type]
        face_auth_qr_path=qr_target,
    )
    res = ctrl.start_live(22334455, area_v2=1062)
    assert res.ok is False
    assert res.status == "face_auth_required"
    assert res.code == 60024
    assert res.rtmp_url == ""
    assert res.face_auth_qr_path == qr_target
    assert qr_target.is_file()
    with Image.open(qr_target) as qr_img:
        assert qr_img.size[0] >= 200
        assert qr_img.size[0] == qr_img.size[1]
    assert "22334455" not in repr(res)
    assert res.to_safe_dict()["room_id"] == REDACTED_TOKEN


def test_bilibili_live_controller_start_and_stop_live_success(tmp_path: Path) -> None:
    vault = _make_vault_with_cookies(tmp_path)
    fake_session = _FakeSession(
        post_map={
            "startLive": _FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "rtmp": {
                            "addr": "rtmp://live-push.bilivideo.com/live-bvc/",
                            "code": "?streamname=live_999_001&key=supersecretstreamkey",
                        }
                    },
                }
            ),
            "stopLive": _FakeResponse({"code": 0, "message": "ok"}),
        }
    )
    ctrl = BilibiliLiveController(vault=vault, session=fake_session)  # type: ignore[arg-type]
    res = ctrl.start_live(22334455, area_v2=1062)
    assert res.ok is True
    assert res.status == "live"
    assert res.rtmp_url == "rtmp://live-push.bilivideo.com/live-bvc/?streamname=live_999_001&key=supersecretstreamkey"
    assert "supersecretstreamkey" not in repr(res)
    assert "supersecretstreamkey" not in json.dumps(res.to_safe_dict())
    assert res.to_safe_dict()["rtmp_url"] == REDACTED_RTMP_TOKEN

    stop_res = ctrl.stop_live(22334455)
    assert stop_res["ok"] is True
    assert stop_res["room_id"] == REDACTED_TOKEN
    assert "22334455" not in json.dumps(stop_res)


# ---------------------------------------------------------------------------
# 4. `HeadlessStageRenderer` & `SyntheticAudioMixer`
# ---------------------------------------------------------------------------


def test_headless_stage_renderer_valid_1080p_rgb_and_fallbacks(tmp_path: Path) -> None:
    # 1) Empty repo_root tests gradient + vector fallback without crashing
    fallback_renderer = HeadlessStageRenderer(repo_root=tmp_path, follower_count=15, follower_goal=1000)
    assert fallback_renderer.loaded_assets["background"] == "gradient_fallback"
    assert fallback_renderer.loaded_assets["dafeiyu"] == "vector_fallback"
    assert fallback_renderer.loaded_assets["gemini"] == "vector_fallback"

    turn_fish = PersonaTurn(
        turn_id=1,
        speaker_id="dafeiyu",
        speaker_name="DeepSeek 蓝色大肥鱼",
        text="各位观众救命！老板15粉小号靠我们冲到1000粉啦！",
        mood="shocked",
        is_highlight=True,
        highlight_category="roast_battle",
    )
    turn_gem = PersonaTurn(
        turn_id=2,
        speaker_id="gemini",
        speaker_name="Gemini娘",
        text="高明度4.9星封面登场，Episode 018 弹幕公投马上开始！",
        mood="smug",
    )
    sample_dm = [
        {"event_type": "danmaku", "user_alias": "策划粉", "text": "支持018期双AI互怼！"},
        {"event_type": "gift", "user_alias": "投喂官", "text": "投喂了 小心心 x3"},
    ]

    frame1 = fallback_renderer.render_frame(
        frame_index=0,
        active_speaker="dafeiyu",
        current_turn=turn_fish,
        recent_danmaku=sample_dm,
        audio_level=0.75,
    )
    frame2 = fallback_renderer.render_frame(
        frame_index=15,
        active_speaker="gemini",
        current_turn=turn_gem,
        recent_danmaku=sample_dm,
        audio_level=0.45,
    )

    assert frame1.shape == (1080, 1920, 3)
    assert frame1.dtype == np.uint8
    assert frame2.shape == (1080, 1920, 3)
    assert float(frame1.mean()) > 90.0  # Bright daylight stage, not black
    assert not np.array_equal(frame1, frame2)  # Active speaker highlight + subtitle + animation changed

    # 2) Default repo assets resolve real background & canonical/cutout portraits
    repo_renderer = HeadlessStageRenderer(follower_count=15, follower_goal=1000)
    assert repo_renderer.loaded_assets["background"] != "gradient_fallback"
    assert repo_renderer.loaded_assets["dafeiyu"].startswith(("cutout:", "canonical:"))
    assert repo_renderer.loaded_assets["gemini"].startswith(("cutout:", "canonical:"))
    assert repo_renderer.font_path is not None and repo_renderer.font_path.is_file()
    frame_real = repo_renderer.render_frame(
        frame_index=5,
        active_speaker="dafeiyu",
        current_turn=turn_fish,
        recent_danmaku=sample_dm,
        audio_level=0.6,
    )
    assert frame_real.shape == (1080, 1920, 3)
    assert frame_real.dtype == np.uint8


def test_synthetic_audio_mixer_exact_6400_bytes_fallback_and_ducking(tmp_path: Path) -> None:
    mixer = SyntheticAudioMixer(use_edge_tts=False)
    assert mixer.bytes_per_frame == BYTES_PER_VIDEO_FRAME == 6400

    # Idle frames: exact 6400 bytes, non-silent warm lo-fi ambient BGM, full idle gain
    idle_chunks: List[bytes] = []
    for _ in range(10):
        pcm, level, speaking = mixer.next_video_frame_pcm()
        assert len(pcm) == 6400
        assert speaking is False
        assert level > 0.0
        idle_chunks.append(pcm)
    idle_gain = mixer.last_bgm_gain
    assert idle_gain > 0.65

    # Offline fallback synthesis produces distinct non-silent stereo arrays for each persona
    fish_pcm = synthesize_offline_fallback_pcm("冲刺一千粉，大肥鱼全速开播！", "dafeiyu")
    gem_pcm = synthesize_offline_fallback_pcm("高明度封面登场，Gemini娘接招啦！", "gemini")
    assert fish_pcm.ndim == 2 and fish_pcm.shape[1] == 2
    assert gem_pcm.ndim == 2 and gem_pcm.shape[1] == 2
    assert float(np.sqrt(np.mean(fish_pcm * fish_pcm))) > 0.05
    assert float(np.sqrt(np.mean(gem_pcm * gem_pcm))) > 0.05
    assert not np.allclose(fish_pcm[:4800], gem_pcm[:4800])

    # Simulated edge-tts network error cleanly falls back to pure-NumPy synth
    turn = PersonaTurn(turn_id=1, speaker_id="gemini", speaker_name="Gemini娘", text="测试离线旋律回退")
    failing_mixer = SyntheticAudioMixer(use_edge_tts=True)
    with patch("edge_tts.Communicate", side_effect=RuntimeError("offline_no_network")):
        fallback_pcm = asyncio.run(failing_mixer.synthesize_turn_pcm(turn))
    assert fallback_pcm.ndim == 2 and fallback_pcm.shape[1] == 2
    assert len(fallback_pcm) >= 48000

    # Enqueue speech -> BGM ducks smoothly during speech while frames stay exactly 6400 bytes
    mixer.enqueue_speech(fish_pcm, pad_silence_sec=0.0)
    ducked_gains: List[float] = []
    speaking_flags: List[bool] = []
    for _ in range(15):
        pcm, level, speaking = mixer.next_video_frame_pcm()
        assert len(pcm) == 6400
        assert level > 0.05
        ducked_gains.append(mixer.last_bgm_gain)
        speaking_flags.append(speaking)
    assert any(speaking_flags)
    assert min(ducked_gains) < idle_gain * 0.55

    # Optional --bgm-path decoding via ffmpeg works on a synthetic WAV file
    wav_path = tmp_path / "custom_bgm.wav"
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(48000)
        t = np.arange(48000, dtype=np.float32) / 48000.0
        tone = (np.sin(2.0 * np.pi * 220.0 * t) * 12000.0).astype("<i2")
        stereo_i16 = np.stack([tone, tone], axis=-1).tobytes()
        wf.writeframes(stereo_i16)
    wav_path.write_bytes(buf.getvalue())

    custom_mixer = SyntheticAudioMixer(bgm_path=wav_path, use_edge_tts=False)
    pcm_custom, lvl_custom, _ = custom_mixer.next_video_frame_pcm()
    assert len(pcm_custom) == 6400
    assert lvl_custom > 0.01


# ---------------------------------------------------------------------------
# 5. `HeadlessLiveStreamer` Lifecycle (`finally: stop_live` + `60024` + scrub)
# ---------------------------------------------------------------------------


def test_go_live_calls_stop_live_in_finally_even_on_midstream_error(tmp_path: Path) -> None:
    vault = _make_vault_with_cookies(tmp_path)
    secret_key = "ultra_secret_stream_key_xyz987"
    fake_session = _FakeSession(
        get_map={
            "GetInfo": _FakeResponse(
                {
                    "code": 0,
                    "data": {"room_id": 55667788, "uid": 11223344, "title": "Init", "area_v2_id": 1062},
                }
            )
        },
        post_map={
            "Room/update": _FakeResponse({"code": 0}),
            "startLive": _FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "rtmp": {
                            "addr": "rtmp://live-push.bilivideo.com/live-bvc/",
                            "code": f"?streamname=live_55667788&key={secret_key}",
                        }
                    },
                }
            ),
            "stopLive": _FakeResponse({"code": 0, "message": "stopped"}),
        },
    )
    ctrl = BilibiliLiveController(vault=vault, session=fake_session)  # type: ignore[arg-type]
    record_dir = tmp_path / "rec"
    tracker = HighlightTracker(jsonl_path=record_dir / "live_highlights.jsonl")
    director = DualAILiveDirector(responder=OfflineBanterResponder(), highlight_tracker=tracker)
    renderer = HeadlessStageRenderer(repo_root=tmp_path)
    mixer = SyntheticAudioMixer(use_edge_tts=False)

    emitted_events: List[Tuple[str, Dict[str, Any]]] = []
    streamer = HeadlessLiveStreamer(
        renderer=renderer,
        audio_mixer=mixer,
        director=director,
        controller=ctrl,
        video_encoder="libx264",
        status_callback=lambda tag, payload: emitted_events.append((tag, payload)),
    )

    # Mock subprocess.Popen so ffmpeg fails immediately with RTMP secret in stderr!
    fake_proc = MagicMock(spec=subprocess.Popen)
    fake_proc.poll.return_value = 1
    fake_proc.returncode = 1
    fake_proc.wait.return_value = 1
    fake_proc.stderr = io.BytesIO(
        f"rtmp://live-push.bilivideo.com/live-bvc/?streamname=live_55667788&key={secret_key}: Connection reset\n".encode(
            "utf-8"
        )
    )

    class _DummyDanmaku:
        async def events(self) -> Any:
            if False:
                yield None

        async def close(self) -> None:
            return

    def _fake_popen(cmd: List[str], **kwargs: Any) -> MagicMock:
        # Close inherited pipe read FDs just like child exit would
        for fd in kwargs.get("pass_fds", ()):
            os.close(fd)
        return fake_proc

    with patch("core.live_studio.headless_streamer.subprocess.Popen", side_effect=_fake_popen):
        res = asyncio.run(
            streamer.run_go_live(
                duration_sec=2.0,
                area_id=1062,
                title="双AI无头首播测试",
                record_dir=record_dir,
                danmaku_client_factory=lambda _rid: _DummyDanmaku(),
                realtime_pacing=False,
            )
        )

    # stopLive MUST have been called in finally despite mid-stream failure!
    post_urls = [url for method, url, _ in fake_session.calls if method == "POST"]
    assert any("startLive" in u for u in post_urls)
    assert any("stopLive" in u for u in post_urls)
    assert res["stop_result"]["ok"] is True

    # Highlight clip plan exported cleanly
    assert res["clip_plan_path"] is not None
    assert Path(str(res["clip_plan_path"])).is_file()

    # ZERO secret leakage anywhere in result, stderr buffer, or emitted status tags
    all_text = (
        json.dumps(res, ensure_ascii=False)
        + json.dumps(emitted_events, ensure_ascii=False)
        + "\n".join(streamer.get_scrubbed_stderr())
    )
    assert secret_key not in all_text
    assert "55667788" not in all_text
    assert "11223344" not in all_text
    assert "live-push.bilivideo.com" not in all_text
    assert REDACTED_RTMP_TOKEN in all_text

    tags = [t for t, _ in emitted_events]
    assert "LIVE_STARTED" in tags
    assert "LIVE_STOPPED" in tags


def test_go_live_60024_stops_before_spawning_ffmpeg(tmp_path: Path) -> None:
    vault = _make_vault_with_cookies(tmp_path)
    qr_path = tmp_path / "face_auth.png"
    fake_session = _FakeSession(
        get_map={
            "GetInfo": _FakeResponse({"code": 0, "data": {"room_id": 44556677, "uid": 778899, "area_v2_id": 1062}})
        },
        post_map={
            "startLive": _FakeResponse(
                {
                    "code": 60024,
                    "data": {"qr": "https://www.bilibili.com/blackboard/live/face-auth-middle.html?t=abc"},
                }
            )
        },
    )
    ctrl = BilibiliLiveController(vault=vault, session=fake_session, face_auth_qr_path=qr_path)  # type: ignore[arg-type]
    emitted: List[Tuple[str, Dict[str, Any]]] = []
    streamer = HeadlessLiveStreamer(
        renderer=HeadlessStageRenderer(repo_root=tmp_path),
        audio_mixer=SyntheticAudioMixer(use_edge_tts=False),
        director=DualAILiveDirector(responder=OfflineBanterResponder()),
        controller=ctrl,
        video_encoder="libx264",
        status_callback=lambda tag, payload: emitted.append((tag, payload)),
    )

    with patch("core.live_studio.headless_streamer.subprocess.Popen") as popen_mock:
        res = asyncio.run(streamer.run_go_live(duration_sec=5.0, area_id=1062))

    popen_mock.assert_not_called()
    assert res["ok"] is False
    assert res["status"] == "face_auth_required"
    assert res["code"] == 60024
    assert qr_path.is_file()
    assert emitted[0][0] == "FACE_AUTH_REQUIRED"
    assert "44556677" not in json.dumps(res)


# ---------------------------------------------------------------------------
# 6. `scripts/launch_headless_live.py` CLI & Status Line Tests
# ---------------------------------------------------------------------------


def test_launch_headless_live_cli_parsing_and_redacted_status(capsys: pytest.CaptureFixture[str]) -> None:
    args = launch_headless_live.parse_args(
        [
            "--mode",
            "go-live",
            "--duration-sec",
            "600",
            "--area-id",
            "371",
            "--title",
            "双AI日常直播",
            "--output-mp4",
            "/tmp/out.mp4",
            "--record-dir",
            "/tmp/rec",
            "--cover-path",
            "/tmp/cover.jpg",
            "--bgm-path",
            "/tmp/bgm.mp3",
            "--follower-count",
            "15",
            "--follower-goal",
            "1000",
        ]
    )
    assert args.mode == "go-live"
    assert args.duration_sec == 600.0
    assert args.area_id == 371
    assert args.title == "双AI日常直播"
    assert args.output_mp4 == "/tmp/out.mp4"
    assert args.record_dir == "/tmp/rec"
    assert args.cover_path == "/tmp/cover.jpg"
    assert args.bgm_path == "/tmp/bgm.mp3"
    assert args.follower_count == 15
    assert args.follower_goal == 1000

    with pytest.raises(SystemExit):
        launch_headless_live.parse_args(["--duration-sec", "-5"])

    line = launch_headless_live.emit_status_line(
        "LIVE_STARTED",
        {
            "ok": True,
            "room_id": REDACTED_TOKEN,
            "note": "rtmp://live-push.bilivideo.com/live-bvc/?key=must_never_print SESSDATA=secret99",
            "banner": AI_DISCLOSURE_BANNER,
        },
    )
    captured = capsys.readouterr().out.strip()
    assert captured == line
    assert captured.startswith("LIVE_STARTED ")
    assert "must_never_print" not in captured
    assert "secret99" not in captured
    assert REDACTED_RTMP_TOKEN in captured
    parsed = json.loads(captured.split(" ", 1)[1])
    assert parsed["ok"] is True
    assert parsed["banner"] == AI_DISCLOSURE_BANNER


# ---------------------------------------------------------------------------
# 7. Trio Voice Alignment, Offline Yowane Synth, Trio Stage & CLI Options
# ---------------------------------------------------------------------------


def test_voice_map_subset_of_verified_edge_tts_and_yowane_offline_distinct() -> None:
    assert set(VOICE_MAP.keys()) == {"dafeiyu", "gemini", "yowane"}
    assert set(VOICE_STYLE_MAP.keys()) == {"dafeiyu", "gemini", "yowane"}
    assert set(VOICE_MAP.values()).issubset(VERIFIED_FREE_EDGE_TTS_VOICES)
    assert VOICE_MAP["dafeiyu"] == "zh-CN-XiaoxiaoNeural"
    assert VOICE_MAP["gemini"] == "zh-CN-XiaoyiNeural"
    assert VOICE_MAP["yowane"] == "zh-TW-HsiaoYuNeural"
    assert VOICE_STYLE_MAP["yowane"] == ("+0%", "-4Hz")

    sample_text = "弱音大姐头冷面查账，请观众扣一扣二扣三投票决定下期主控！"
    fish_pcm = synthesize_offline_fallback_pcm(sample_text, "dafeiyu")
    gem_pcm = synthesize_offline_fallback_pcm(sample_text, "gemini")
    yow_pcm = synthesize_offline_fallback_pcm(sample_text, "yowane")

    assert yow_pcm.ndim == 2 and yow_pcm.shape[1] == 2
    assert float(np.sqrt(np.mean(yow_pcm * yow_pcm))) > 0.05
    # Distinct lower-mid harmonic profile from both dafeiyu and gemini
    min_len = min(len(fish_pcm), len(gem_pcm), len(yow_pcm), 9600)
    assert not np.allclose(yow_pcm[:min_len], fish_pcm[:min_len])
    assert not np.allclose(yow_pcm[:min_len], gem_pcm[:min_len])
    # Centered stereo panning for Yowane vs asymmetric left/right for dafeiyu/gemini
    assert np.allclose(yow_pcm[:min_len, 0], yow_pcm[:min_len, 1], atol=1e-5)


def test_trio_headless_stage_renderer_1080p_poll_widget_and_celebration() -> None:
    renderer = HeadlessStageRenderer(cast=TRIO_CAST, follower_count=18, follower_goal=1000)
    assert renderer.cast == TRIO_CAST
    assert renderer.loaded_assets["background"] != "gradient_fallback"
    assert renderer.loaded_assets["dafeiyu"].startswith(("cutout:", "canonical:"))
    assert renderer.loaded_assets["gemini"].startswith(("cutout:", "canonical:"))
    assert renderer.loaded_assets["yowane"].startswith(("cutout:", "canonical:"))
    # Main repo cutout discovery should resolve Yowane solo rooftop cutout inside share worktree
    assert "yowane_rooftop_hero_cutout.png" in renderer.loaded_assets["yowane"]

    poll = LivePollState(topic="下期主控弹幕公投", options=("大肥鱼", "Gemini娘", "弱音大姐头"))
    poll.record_vote("观众1", "扣1", now=10.0)
    poll.record_vote("观众2", "扣2", now=11.0)
    poll.record_vote("观众3", "扣3", now=12.0)
    poll.record_vote("观众4", "扣3", now=13.0)
    snap = poll.snapshot(now=13.0)

    turn_yowane = PersonaTurn(
        turn_id=3,
        speaker_id="yowane",
        speaker_name="弱音ハク",
        text="推了推眼镜：目前弱音大姐头票数领先，四毛钱经费归我统筹。",
        mood="focused",
        is_highlight=True,
        highlight_category="script_pitch",
    )
    sample_dm = [
        {"event_type": "danmaku", "user_alias": "观众3", "text": "扣3 弱音大姐头冲鸭！"},
        {"event_type": "gift", "user_alias": "投喂官", "text": "投喂了 小心心 x3"},
    ]

    frame_base = renderer.render_frame(
        frame_index=10,
        active_speaker="yowane",
        current_turn=turn_yowane,
        recent_danmaku=sample_dm,
        audio_level=0.72,
        poll_snapshot=snap,
    )
    frame_celeb = renderer.render_frame(
        frame_index=10,
        active_speaker="yowane",
        current_turn=turn_yowane,
        recent_danmaku=sample_dm,
        audio_level=0.72,
        poll_snapshot=snap,
        celebration_text="涨粉喜报！新添 +3 位小伙伴，冲千粉进度 18 / 1,000 粉！",
    )
    assert frame_base.shape == (1080, 1920, 3)
    assert frame_base.dtype == np.uint8
    assert float(frame_base.mean()) > 90.0
    assert not np.array_equal(frame_base, frame_celeb)

    # Dual cast layout remains supported
    dual_renderer = HeadlessStageRenderer(cast=DUAL_CAST)
    assert dual_renderer.cast == DUAL_CAST
    dual_frame = dual_renderer.render_frame(frame_index=0, active_speaker="dafeiyu")
    assert dual_frame.shape == (1080, 1920, 3)


def test_launch_headless_live_cli_cast_and_poll_args() -> None:
    default_args = launch_headless_live.parse_args([])
    assert default_args.cast == "trio"
    assert default_args.resolved_cast == TRIO_CAST
    assert default_args.parsed_poll_options == ("大肥鱼", "Gemini娘", "弱音大姐头")
    assert "@" not in default_args.title

    custom_args = launch_headless_live.parse_args(
        [
            "--cast",
            "dual",
            "--poll-topic",
            "下期去哪拍",
            "--poll-options",
            "赛博法庭，打歌摄影棚",
        ]
    )
    assert custom_args.cast == "dual"
    assert custom_args.resolved_cast == DUAL_CAST
    assert custom_args.poll_topic == "下期去哪拍"
    assert custom_args.parsed_poll_options == ("赛博法庭", "打歌摄影棚")

    with pytest.raises(SystemExit):
        launch_headless_live.parse_args(["--poll-options", "只有一个选项"])
