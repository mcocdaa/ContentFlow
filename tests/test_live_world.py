"""Offline mocked unit & integration tests for the Living 2D Workshop World & Agent Control Bridge."""

from __future__ import annotations

import asyncio
import io
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
import numpy as np
from PIL import Image

from core.auth_vault import AuthVault
from core.live_studio import (
    AI_DISCLOSURE_BANNER,
    TRIO_CAST,
    AutonomousWorldBrain,
    BilibiliLiveController,
    DanmakuEvent,
    DualAILiveDirector,
    HeadlessLiveStreamer,
    LiveAgentWorld,
    OfflineBanterResponder,
    OpenAICompatibleResponder,
    PersonaTurn,
    StartLiveResult,
    SyntheticAudioMixer,
    ViewerMemoryStore,
    WorldStageRenderer,
    scrub_rtmp_secrets,
)
from core.live_studio.danmaku import parse_room_stats_command
from scripts import launch_headless_live, live_agent_ctl

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
        post_map: Optional[Dict[str, _FakeResponse]] = None,
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
                return resp
        raise AssertionError(f"Unexpected POST {url}")


def _make_vault_with_cookies(tmp_path: Path) -> AuthVault:
    vault = AuthVault(vault_dir=tmp_path / "vault")
    vault.save_bilibili_session(
        cookies={
            "SESSDATA": "fake_sessdata_secret_xyz",
            "bili_jct": "fake_csrf_jct_abc",
            "DedeUserID": "987654321",
        }
    )
    return vault


def test_zero_mic_guarantee_for_world_modules() -> None:
    targets = [
        REPO_ROOT / "core" / "live_studio" / "world_engine.py",
        REPO_ROOT / "core" / "live_studio" / "headless_streamer.py",
        REPO_ROOT / "core" / "live_studio" / "director.py",
        REPO_ROOT / "scripts" / "launch_headless_live.py",
        REPO_ROOT / "scripts" / "live_agent_ctl.py",
    ]
    for path in targets:
        assert path.is_file()
        match = FORBIDDEN_MIC_RE.search(path.read_text(encoding="utf-8"))
        assert match is None, f"Forbidden audio-capture token {match.group(0)!r} found in {path}"


def test_cover_4x3_normalization_and_telemetry_endpoints(tmp_path: Path) -> None:
    vault = _make_vault_with_cookies(tmp_path)
    cover_src = tmp_path / "wide_16x9.png"
    Image.new("RGB", (1280, 720), (160, 210, 255)).save(cover_src, format="PNG")

    fake_session = _FakeSession(
        get_map={
            "Room/get_info": _FakeResponse(
                {
                    "code": 0,
                    "data": {"online": 18, "attention": 21, "live_status": 1},
                }
            ),
            "getInfoByRoom": _FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "room_info": {"online": 18, "live_status": 1},
                        "watched_show": {"num": 145, "text_large": "145人看过"},
                        "anchor_info": {"relation_info": {"attention": 21}},
                    },
                }
            ),
            "StopLiveData": _FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "LiveTime": 1800,
                        "WatchedCount": 210,
                        "MaxOnline": 32,
                        "AddFans": 6,
                        "DanmuNum": 54,
                        "HamsterRmb": 12.5,
                        "NewFansClub": 2,
                        "cover_exposure_count": {"count": 1950, "data_status": 1},
                        "cover_click_rate": {"rate": 0.084, "data_status": 1},
                    },
                }
            ),
        },
        post_map={
            "upload/web/image": _FakeResponse(
                {"code": 0, "data": {"location": "https://i0.hdslb.com/bfs/live/ok.jpg"}}
            ),
            "UpdatePreLiveInfo": _FakeResponse({"code": 0, "message": "ok"}),
            "startLive": _FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "live_key": "secret_live_key_778899",
                        "rtmp": {
                            "addr": "rtmp://live-push.bilivideo.com/live-bvc/",
                            "code": "?streamname=live_111&key=supersecret999",
                        },
                    },
                }
            ),
        },
    )
    ctrl = BilibiliLiveController(vault=vault, session=fake_session)  # type: ignore[arg-type]

    # 1) Cover uploaded as normalized 800x600 (4:3) JPEG + platform=web
    cov_res = ctrl.upload_live_cover(cover_src, room_id=22334455)
    assert cov_res["ok"] is True
    assert cov_res["cover_updated"] is True

    upload_call = next(c for c in fake_session.calls if "upload/web/image" in c[1])
    file_tuple = upload_call[2]["files"]["file"]
    uploaded_name, uploaded_buf, uploaded_mime = file_tuple
    assert uploaded_name.endswith("_4x3.jpg")
    assert uploaded_mime == "image/jpeg"
    buf_bytes = uploaded_buf.read()
    assert len(buf_bytes) <= 280 * 1024
    with Image.open(io.BytesIO(buf_bytes)) as normalized_img:
        assert normalized_img.size == (800, 600)

    upd_call = next(c for c in fake_session.calls if "UpdatePreLiveInfo" in c[1])
    assert upd_call[2]["data"]["platform"] == "web"
    assert upd_call[2]["data"]["mobi_app"] == "web"

    # 2) StartLiveResult masks live_key and RTMP secrets
    start_res = ctrl.start_live(22334455, area_v2=1062)
    assert start_res.ok is True
    assert start_res.live_key == "secret_live_key_778899"
    safe = start_res.to_safe_dict()
    assert safe["has_live_key"] is True
    assert "secret_live_key_778899" not in repr(start_res)
    assert "secret_live_key_778899" not in json.dumps(safe)

    # 3) Telemetry and StopLiveData parse cleanly without PII
    tel = ctrl.get_live_telemetry(22334455)
    assert tel == {
        "ok": True,
        "online": 18,
        "watched_num": 145,
        "watched_text": "145人看过",
        "attention": 21,
        "live_status": 1,
    }
    stop_data = ctrl.get_stop_live_data(start_res.live_key)
    assert stop_data["ok"] is True
    assert stop_data["live_time_sec"] == 1800
    assert stop_data["watched_count"] == 210
    assert stop_data["max_online"] == 32
    assert stop_data["add_fans"] == 6
    assert stop_data["cover_exposure_count"] == 1950
    assert stop_data["cover_click_rate"] == 0.084
    assert isinstance(StartLiveResult(ok=False, status="idle"), StartLiveResult)


def test_parse_room_stats_command() -> None:
    watched = parse_room_stats_command(
        {"cmd": "WATCHED_CHANGE", "data": {"num": 88, "text_small": "88", "text_large": "88人看过"}}
    )
    assert watched == {"type": "watched", "watched_num": 88, "watched_text": "88人看过"}

    online = parse_room_stats_command({"cmd": "ONLINE_RANK_COUNT", "data": {"count": 24}})
    assert online == {"type": "online", "online": 24}

    assert parse_room_stats_command({"cmd": "DANMU_MSG", "info": []}) is None


def test_viewer_memory_and_live_agent_world_commands(tmp_path: Path) -> None:
    mem_path = tmp_path / "memory" / "viewer_memory.json"
    store = ViewerMemoryStore(memory_path=mem_path)
    t0 = 1_700_000_000.0
    e1 = store.record_enter("熬夜程序员", now=t0)
    assert e1["visits"] == 1
    store.record_action("熬夜程序员", points=35, action_delta=1, message=True, now=t0 + 10)
    # Revisit >= 5 minutes later increments visit count
    e2 = store.record_enter("熬夜程序员", now=t0 + 400.0)
    assert e2["visits"] == 2
    assert e2["tier"] == "常客"

    # Reload from disk and verify zero raw UIDs
    reloaded = ViewerMemoryStore(memory_path=mem_path)
    loaded_v = reloaded.get_viewer("熬夜程序员")
    assert loaded_v is not None
    assert loaded_v["visits"] == 2
    assert loaded_v["score"] == 35
    assert "DedeUserID" not in mem_path.read_text(encoding="utf-8")

    world = LiveAgentWorld(memory_store=reloaded, follower_count=15, follower_goal=1000)

    # Zero-barrier viewer commands
    r_join = world.handle_danmaku_event(DanmakuEvent(event_type="danmaku", user_alias="新工友@张三", text="开工"))
    assert r_join["handled"] is True and r_join["kind"] == "join"
    assert "@" not in r_join["alias"]

    r_code = world.handle_danmaku_event(DanmakuEvent(event_type="danmaku", user_alias="极客猫", text="写代码"))
    assert r_code["handled"] is True and r_code["kind"] == "build"
    assert world.code_pts >= 15

    # Trigger crisis then let viewer fix it via 修Bug
    world.apply_agent_command({"cmd": "world_action", "action": "trigger_event", "title": "测试警报"})
    assert world.active_event is not None
    r_fix = world.handle_danmaku_event(DanmakuEvent(event_type="danmaku", user_alias="抢修侠", text="修Bug"))
    assert r_fix["resolved_crisis"] is True
    assert world.active_event is None

    # Suggestion + gift + Agent acceptance
    r_sug = world.handle_danmaku_event(
        DanmakuEvent(event_type="danmaku", user_alias="点子王", text="建议 加个白米饭锅")
    )
    assert r_sug["kind"] == "suggestion"
    sug_id = r_sug["suggestion_id"]

    r_gift = world.handle_danmaku_event(
        DanmakuEvent(event_type="gift", user_alias="好心老板", text="投喂", gift_name="小心心", gift_count=2)
    )
    assert r_gift["kind"] == "gift"
    assert world.rice_bowls >= 2
    assert reloaded.get_viewer("好心老板")["badge"] == "白米饭供应商"  # type: ignore[index]

    acc_res = world.apply_agent_command({"cmd": "world_action", "action": "accept_suggestion", "suggestion_id": sug_id})
    assert acc_res["ok"] is True
    assert reloaded.get_viewer("点子王")["badge"] == "建议采纳官"  # type: ignore[index]

    # Agent workbench & speak bridge
    wb_res = world.apply_agent_command(
        {
            "cmd": "work_log",
            "task": "实现观众点子：白米饭锅",
            "stage": 1,
            "tag": "CODE",
            "text": "正在调试电饭煲补给动画 uid=123456 @全体",
        }
    )
    assert wb_res["ok"] is True
    assert wb_res["stage"] == 1
    assert "123456" not in world.work_log[-1]["text"]
    assert "@" not in world.work_log[-1]["text"]

    spk_res = world.apply_agent_command(
        {"cmd": "speak", "speaker": "yowane", "text": "建议收到，电饭煲已经加满！", "mood": "hype"}
    )
    assert spk_res["ok"] is True
    assert spk_res["speech_request"][0] == "yowane"

    world.tick(1.5)
    snap = world.export_state_dict()
    assert snap["world"]["rice_bowls"] >= 2
    assert snap["workbench"]["pipeline_stage"] == 3
    assert "@" not in json.dumps(snap, ensure_ascii=False)

    # Director high-priority Agent speech
    director = DualAILiveDirector(responder=OfflineBanterResponder(), cast=TRIO_CAST)
    assert director.enqueue_agent_speech("yowane", "现在由弱音现场播报最新改动！") is True
    turn = asyncio.run(director.next_turn())
    assert turn.speaker_id == "yowane"
    assert turn.trigger_type == "system"
    assert "现场播报" in turn.text


def test_world_stage_renderer_and_dry_stream_e2e(tmp_path: Path) -> None:
    world = LiveAgentWorld(memory_path=tmp_path / "mem.json", follower_count=15, follower_goal=1000)
    world.handle_danmaku_event(DanmakuEvent(event_type="danmaku", user_alias="测试工友", text="开工"))
    world.update_telemetry(online=12, watched_num=66, watched_text="66人看过", follower_count=16)

    renderer = WorldStageRenderer(repo_root=tmp_path, world=world, fps=30)
    assert renderer.width == 1920 and renderer.height == 1080
    assert AI_DISCLOSURE_BANNER == "本直播间由 AI 实时驱动互动 · GB 45438-2025"

    turn = PersonaTurn(turn_id=1, speaker_id="dafeiyu", speaker_name="DeepSeek 蓝色大肥鱼", text="工坊运转正常！")
    # Warm caches on frame 0 then measure steady-state render latency (target < 33ms for 30 FPS)
    _ = renderer.render_frame(frame_index=0, active_speaker="dafeiyu", current_turn=turn, audio_level=0.6)
    t_start = time.monotonic()
    for fi in range(1, 11):
        frame = renderer.render_frame(frame_index=fi, active_speaker="dafeiyu", current_turn=turn, audio_level=0.6)
    avg_ms = (time.monotonic() - t_start) * 1000.0 / 10.0
    assert isinstance(frame, np.ndarray)
    assert frame.shape == (1080, 1920, 3)
    assert frame.dtype == np.uint8
    assert avg_ms < 33.0, f"Steady-state render_frame took {avg_ms:.2f}ms/frame (>= 33ms budget)"

    # End-to-end 3s dry-stream in world mode with pre-seeded agent_commands.jsonl
    rec_dir = tmp_path / "live_world_rec"
    rec_dir.mkdir(parents=True, exist_ok=True)
    live_agent_ctl.main(
        [
            "--record-dir",
            str(rec_dir),
            "work-log",
            "--task",
            "测试世界模式自动化干跑",
            "--stage",
            "2",
            "--tag",
            "TEST",
            "--text",
            "注入工作台验证日志",
        ]
    )
    live_agent_ctl.main(
        [
            "--record-dir",
            str(rec_dir),
            "world-action",
            "--action",
            "build_upgrade",
            "--payload-json",
            '{"xp": 120}',
        ]
    )

    out_mp4 = tmp_path / "world_dry.mp4"
    snap_png = tmp_path / "dry_frame.png"
    args = launch_headless_live.parse_args(
        [
            "--mode",
            "dry-stream",
            "--stage-mode",
            "world",
            "--cast",
            "trio",
            "--duration-sec",
            "3",
            "--no-edge-tts",
            "--no-llm",
            "--output-mp4",
            str(out_mp4),
            "--record-dir",
            str(rec_dir),
            "--memory-path",
            str(tmp_path / "e2e_mem.json"),
            "--frame-dump-path",
            str(snap_png),
        ]
    )
    res = asyncio.run(launch_headless_live.run_headless_live(args))
    assert res["ok"] is True
    assert out_mp4.is_file() and out_mp4.stat().st_size > 10_000
    assert snap_png.is_file()
    state_json = rec_dir / "world_state.json"
    assert state_json.is_file()
    saved_state = json.loads(state_json.read_text(encoding="utf-8"))
    assert saved_state["world"]["level"] >= 2
    assert saved_state["workbench"]["pipeline_stage"] == 2
    assert "注入工作台验证日志" in json.dumps(saved_state["workbench"]["work_log"], ensure_ascii=False)

    # Verify live_agent_ctl status & inbox subcommands cleanly
    rc_status = live_agent_ctl.main(["--record-dir", str(rec_dir), "status"])
    rc_inbox = live_agent_ctl.main(["--record-dir", str(rec_dir), "inbox", "--tail", "5"])
    rc_stop = live_agent_ctl.main(["--record-dir", str(rec_dir), "stop"])
    assert rc_status == 0 and rc_inbox == 0 and rc_stop == 0

    # Ensure SyntheticAudioMixer, HeadlessLiveStreamer & scrub_rtmp_secrets keep invariants
    assert isinstance(SyntheticAudioMixer(use_edge_tts=False), SyntheticAudioMixer)
    assert issubclass(HeadlessLiveStreamer, object)
    assert "secret" not in scrub_rtmp_secrets("rtmp://live-push.bilivideo.com/a/?key=secret")


def test_deepseek_tts_mixer_pcm_upsampling_and_fallback() -> None:
    async def _run() -> None:
        # 24 kHz mono PCM16 (4800 samples = 0.2s -> 9600 samples at 48kHz stereo, > 1600 samples_per_frame)
        pcm_samples = (np.sin(np.linspace(0.0, 20.0 * np.pi, 4800, dtype=np.float32)) * 12000.0).astype("<i2")
        pcm_bytes = pcm_samples.tobytes()

        seen_bodies: List[Dict[str, Any]] = []

        def ok_handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["Authorization"] == "Bearer sk-ds-live-secret-99"
            body = json.loads(request.content.decode("utf-8"))
            seen_bodies.append(body)
            return httpx.Response(200, content=pcm_bytes, headers={"Content-Type": "audio/pcm"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(ok_handler)) as client:
            mixer = SyntheticAudioMixer(
                tts_backend="auto",
                use_edge_tts=False,
                deepseek_api_key="sk-ds-live-secret-99",
                deepseek_tts_url="https://mock.ds.local/v1/tools/tts",
                deepseek_http_client=client,
            )
            assert "sk-ds-live-secret-99" not in repr(mixer)
            pcm_out = await mixer.synthesize_turn_pcm(
                PersonaTurn(
                    turn_id=1, speaker_id="dafeiyu", speaker_name="DeepSeek 蓝色大肥鱼", text="发开工生成小人！"
                )
            )
            assert pcm_out.ndim == 2 and pcm_out.shape == (9600, 2)
            assert pcm_out.dtype == np.float32
            assert float(np.max(np.abs(pcm_out))) <= 0.80
            assert mixer.tts_stats["deepseek"] == 1
            assert seen_bodies[0] == {
                "text": "发开工生成小人！",
                "voice_id": "stella",
                "format": "pcm",
                "filter_markdown": True,
            }

        # Error 429 / truncated PCM cleanly falls back to offline synth without raising or leaking secret
        def fail_handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={"error": "too many requests"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(fail_handler)) as err_client:
            err_mixer = SyntheticAudioMixer(
                tts_backend="deepseek",
                use_edge_tts=False,
                deepseek_api_key="sk-ds-fail-secret-88",
                deepseek_http_client=err_client,
            )
            fb_pcm = await err_mixer.synthesize_turn_pcm(
                PersonaTurn(turn_id=2, speaker_id="gemini", speaker_name="Gemini娘", text="遇到限流自动回退！")
            )
            assert fb_pcm.ndim == 2 and fb_pcm.shape[1] == 2
            assert len(fb_pcm) >= 48000
            assert err_mixer.tts_stats["offline"] == 1
            assert "sk-ds-fail-secret-88" not in repr(err_mixer)

    asyncio.run(_run())


def test_world_context_prompting_and_autonomous_world_brain(tmp_path: Path) -> None:
    world = LiveAgentWorld(memory_path=tmp_path / "brain_mem.json", follower_count=16, follower_goal=1000)
    world.handle_danmaku_event(DanmakuEvent(event_type="danmaku", user_alias="点子达人", text="建议 加个夜间霓虹灯"))
    world.apply_agent_command({"cmd": "world_action", "action": "trigger_event", "title": "测试算力波动"})

    # 1. Offline world banter injects world stats & omits stale 017-020 talk-show lines
    off_resp = OfflineBanterResponder(world_context_provider=world.export_state_dict)
    dir_off = DualAILiveDirector(
        responder=off_resp,
        follower_count=16,
        follower_goal=1000,
        world_context_provider=world.export_state_dict,
    )
    t_crisis = asyncio.run(dir_off.next_turn())
    assert "测试算力波动" in t_crisis.text or "修Bug" in t_crisis.text
    assert "017" not in t_crisis.text and "018" not in t_crisis.text

    # 2. OpenAICompatibleResponder injects live workshop snapshot into LLM request
    captured_prompts: List[str] = []

    def llm_world_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        captured_prompts.append(json.dumps(body["messages"], ensure_ascii=False))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "欢迎来到AI活工坊！发修Bug帮大肥鱼解决测试算力波动吧！"}}]},
        )

    async def _run_brain() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(llm_world_handler)) as llm_client:
            llm_resp = OpenAICompatibleResponder(
                api_key="sk-world-llm-mock",
                http_client=llm_client,
                world_context_provider=world.export_state_dict,
            )
            dir_llm = DualAILiveDirector(responder=llm_resp, follower_count=16, follower_goal=1000)
            turn = await dir_llm.next_turn()
            assert "AI活工坊" in turn.text
            assert "破旧电饭煲工位" in captured_prompts[0]
            assert "测试算力波动" in captured_prompts[0]

        # 3. AutonomousWorldBrain parses JSON actions, caps XP, scrubs @/PII, blocks stop, survives HTTP 500
        def brain_handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content.decode("utf-8"))
            assert body["response_format"] == {"type": "json_object"}
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "task": "实现点子达人的夜间霓虹灯 @全体",
                                        "stage": 2,
                                        "tag": "CODE",
                                        "log_text": "正在采纳建议 S1 并部署夜间灯效 uid=998877",
                                        "world_action": {"action": "accept_suggestion", "suggestion_id": "S1"},
                                        "speech": {
                                            "speaker": "yowane",
                                            "mood": "focused",
                                            "text": "点子达人的建议已经采纳，夜间霓虹灯效马上上线！",
                                        },
                                    },
                                    ensure_ascii=False,
                                )
                            }
                        }
                    ]
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(brain_handler)) as brain_client:
            brain = AutonomousWorldBrain(
                api_key="sk-brain-secret-01",
                interval_sec=30.0,
                http_client=brain_client,
            )
            assert "sk-brain-secret-01" not in repr(brain)
            cmds = await brain.decide_next_actions(world.export_state_dict())
            assert len(cmds) == 3
            assert cmds[0]["cmd"] == "work_log"
            assert "@" not in cmds[0]["task"]
            assert "998877" not in cmds[0]["text"]
            assert cmds[1] == {"cmd": "world_action", "action": "accept_suggestion", "suggestion_id": "S1"}
            assert cmds[2]["cmd"] == "speak" and cmds[2]["speaker"] == "yowane"

            for c in cmds:
                res = world.apply_agent_command(c)
                assert res["ok"] is True
            assert world.memory.get_viewer("点子达人")["badge"] == "建议采纳官"  # type: ignore[index]

            # Direct sanitize_and_build_commands clamps XP and blocks `stop`
            clamped = brain.sanitize_and_build_commands(
                {"world_action": {"action": "build_upgrade", "xp": 9999}}, world.export_state_dict()
            )
            assert clamped[0]["xp"] == 35
            blocked_stop = brain.sanitize_and_build_commands(
                {"world_action": {"action": "stop"}}, world.export_state_dict()
            )
            assert blocked_stop == []

        # HTTP 500 degrades to empty action list cleanly
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _r: httpx.Response(500, json={"error": "busy"}))
        ) as err_client:
            err_brain = AutonomousWorldBrain(api_key="sk-brain-secret-02", http_client=err_client)
            assert await err_brain.decide_next_actions(world.export_state_dict()) == []

    asyncio.run(_run_brain())
