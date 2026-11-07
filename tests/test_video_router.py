"""Unit tests for Scheme B Cloud Video API Router (VolcEngine Ark /api/v3 + Kuaishou Kling AI CLI & HTTP API)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from core.video_api_router import (
    SEEDANCE_V3_CANDIDATE_MODELS,
    VideoApiRouter,
    _b64url_encode,
    _encode_kling_media_base64,
    generate_kling_jwt,
)


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def _create_sample_image(path: Path) -> Path:
    Image.new("RGB", (64, 64), color=(120, 80, 200)).save(path)
    return path


def test_kling_jwt_hs256_generation_and_signature() -> None:
    ak = "kling_test_ak_998877"
    sk = "kling_test_sk_super_secret_112233"
    fixed_now = 1700000000

    token = generate_kling_jwt(access_key=ak, secret_key=sk, ttl_seconds=1800, now=fixed_now)
    parts = token.split(".")
    assert len(parts) == 3

    header = json.loads(_b64url_decode(parts[0]).decode("utf-8"))
    payload = json.loads(_b64url_decode(parts[1]).decode("utf-8"))

    assert header == {"alg": "HS256", "typ": "JWT"}
    assert payload["iss"] == ak
    assert payload["exp"] == fixed_now + 1800
    assert payload["nbf"] == fixed_now - 5

    signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
    expected_sig = _b64url_encode(hmac.new(sk.encode("utf-8"), signing_input, hashlib.sha256).digest())
    assert parts[2] == expected_sig


def test_provider_detection_and_verify_credentials(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    monkeypatch.delenv("ARK_PAYG_API_KEY", raising=False)
    monkeypatch.delenv("KLING_ACCESS_KEY", raising=False)
    monkeypatch.delenv("KLING_SECRET_KEY", raising=False)
    monkeypatch.delenv("KLING_API_KEY", raising=False)
    monkeypatch.setenv("KLING_CREDENTIALS_PATH", str(tmp_path / "missing_kling_creds"))

    # 1. No cloud keys or CLI credentials configured
    router_empty = VideoApiRouter()
    avail_empty = router_empty.get_available_providers()
    assert router_empty.kling_cli_ready is False
    assert avail_empty["volcengine_seedance"] is False
    assert avail_empty["kling_ai"] is False
    assert avail_empty["local_simulator"] is True

    # 2. VolcEngine PAYG key + Kling AK/SK configured via .env
    env_file = tmp_path / ".env.test"
    env_file.write_text(
        "ARK_PAYG_API_KEY=a1b2c3d4-e5f6-7890-abcd-ef1234567890\n"
        "KLING_ACCESS_KEY=ak_live_12345678\n"
        "KLING_SECRET_KEY=sk_live_87654321\n",
        encoding="utf-8",
    )
    router = VideoApiRouter(dotenv_path=env_file)
    avail = router.get_available_providers()
    assert avail["volcengine_seedance"] is True
    assert avail["kling_ai"] is True

    creds = router.verify_credentials(check_remote=False)
    assert creds["volcengine_seedance"]["configured"] is True
    assert creds["volcengine_seedance"]["valid_format"] is True
    assert creds["volcengine_seedance"]["using_payg_key"] is True
    assert creds["volcengine_seedance"]["mode"] == "payg_v3"
    assert (
        creds["volcengine_seedance"]["endpoint"]
        == "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks"
    )
    assert creds["kling_ai"]["configured"] is True
    assert creds["kling_ai"]["valid_format"] is True
    assert creds["kling_ai"]["auth_mode"] == "jwt_hs256"
    assert creds["ready"] is True

    # 3. Direct KLING_API_KEY Bearer token fallback
    monkeypatch.delenv("KLING_ACCESS_KEY", raising=False)
    monkeypatch.delenv("KLING_SECRET_KEY", raising=False)
    monkeypatch.setenv("KLING_API_KEY", "kling_direct_bearer_token_xyz")
    router_bearer = VideoApiRouter()
    assert router_bearer.get_available_providers()["kling_ai"] is True
    assert router_bearer.get_kling_auth_token() == "kling_direct_bearer_token_xyz"
    assert router_bearer.verify_credentials()["kling_ai"]["auth_mode"] == "bearer_token"


def test_kling_cli_oauth_detection_and_motion_control_and_image_to_video(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("KLING_ACCESS_KEY", raising=False)
    monkeypatch.delenv("KLING_SECRET_KEY", raising=False)
    monkeypatch.delenv("KLING_API_KEY", raising=False)
    monkeypatch.setenv("ARK_API_KEY", "ark-coding-plan-key")
    monkeypatch.delenv("ARK_PAYG_API_KEY", raising=False)

    fake_cli_bin = tmp_path / "kling"
    fake_cli_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    fake_creds = tmp_path / ".credentials"
    fake_creds.write_text("[mcp-cn.klingai.com]\nACCESS_TOKEN=ssvip_diamond_oauth_token_600\n", encoding="utf-8")

    router = VideoApiRouter(kling_cli_bin=fake_cli_bin, kling_credentials_path=fake_creds)
    assert router.kling_cli_ready is True
    providers = router.get_available_providers()
    assert providers["kling_ai"] is True
    creds = router.verify_credentials(check_remote=False)
    assert creds["kling_ai"]["auth_mode"] == "kling_cli_oauth"
    assert creds["kling_ai"]["kling_cli_ready"] is True

    img = _create_sample_image(tmp_path / "character_anchor.jpg")
    ref_video = tmp_path / "dance_ref.mp4"
    ref_video.write_bytes(b"FAKE_DANCE_MP4")
    out_motion = tmp_path / "kling_cli_motion_out.mp4"
    out_i2v = tmp_path / "kling_cli_i2v_out.mp4"

    invoked_cmds: List[List[str]] = []

    def fake_subproc_run(cmd: List[str], capture_output: bool = True, text: bool = True, env: Any = None, **kwargs):
        invoked_cmds.append(list(cmd))
        subcommand = cmd[1]
        if subcommand == "motion_control":
            # Simulate returning generationId so query_tasks fallback is also exercised
            stdout_json = json.dumps({"ok": True, "status": 200, "body": {"generationId": "gen-mc-3001"}})
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=stdout_json, stderr="")
        elif subcommand == "query_tasks":
            assert cmd[2] == "gen-mc-3001"
            stdout_json = json.dumps(
                {
                    "ok": True,
                    "status": 200,
                    "body": {
                        "status": "succeed",
                        "works": [
                            {
                                "url": "https://cdn.klingai.com/v3/gen-mc-3001-wm.mp4",
                                "urlWithoutWatermark": "https://cdn.klingai.com/v3/gen-mc-3001-clean.mp4",
                            }
                        ],
                    },
                }
            )
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=stdout_json, stderr="")
        elif subcommand == "image_to_video":
            stdout_json = json.dumps(
                {
                    "ok": True,
                    "status": 200,
                    "body": {
                        "polled": True,
                        "timedOut": False,
                        "generations": [
                            {
                                "generationId": "gen-i2v-3002",
                                "status": "succeed",
                                "result": {
                                    "status": "succeed",
                                    "works": [{"url": "https://cdn.klingai.com/v3/gen-i2v-3002.mp4"}],
                                },
                            }
                        ],
                    },
                }
            )
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=stdout_json, stderr="")
        raise AssertionError(f"Unexpected CLI command: {cmd}")

    def fake_download_get(url: str, stream: bool = True, timeout: float = 60):
        resp = MagicMock()
        resp.status_code = 200
        if "gen-mc-3001-clean.mp4" in url:
            resp.iter_content.return_value = [b"KLING_V3_MOTION_CONTROL_MP4"]
        elif "gen-i2v-3002.mp4" in url:
            resp.iter_content.return_value = [b"KLING_V3_IMAGE_TO_VIDEO_MP4"]
        else:
            raise AssertionError(f"Unexpected download URL: {url}")
        return resp

    with (
        patch("core.video_api_router.subprocess.run", side_effect=fake_subproc_run),
        patch("core.video_api_router.requests.get", side_effect=fake_download_get),
    ):
        # 1. Motion Control via generate_dance_motion_transfer
        res_mc = router.generate_dance_motion_transfer(
            image_path=img,
            reference_video_path=ref_video,
            prompt="3D figure girl dancing smoothly",
            output_path=out_motion,
        )
        assert res_mc == out_motion.resolve()
        assert out_motion.read_bytes() == b"KLING_V3_MOTION_CONTROL_MP4"
        assert invoked_cmds[0] == [
            str(fake_cli_bin),
            "motion_control",
            "--model",
            "kling-video-v3_0",
            "--image",
            str(img.resolve()),
            "--video",
            str(ref_video.resolve()),
            "--motionDirection",
            "motion_direction",
            "--resolution",
            "1080p",
            "--keepOriginalSound",
            "true",
            "--prompt",
            "3D figure girl dancing smoothly",
            "--poll",
            "600",
            "-q",
        ]
        assert invoked_cmds[1] == [str(fake_cli_bin), "query_tasks", "gen-mc-3001", "-q"]

        # 2. Image-to-Video with provider="auto" preferring kling_ai when kling_cli_ready is True
        res_i2v = router.generate_video_from_image(
            image_path=img,
            prompt="anime figure camera push",
            provider="auto",
            duration=5,
            resolution="1080p",
            output_path=out_i2v,
        )
        assert res_i2v == out_i2v.resolve()
        assert out_i2v.read_bytes() == b"KLING_V3_IMAGE_TO_VIDEO_MP4"
        assert invoked_cmds[2][1] == "image_to_video"
        assert "--model" in invoked_cmds[2]
        assert "kling-video-v3_0" in invoked_cmds[2]


def test_seedance_v3_payload_formatting(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ARK_PAYG_API_KEY", "payg-uuid-key-12345678")
    monkeypatch.setenv("KLING_CREDENTIALS_PATH", str(tmp_path / "no_kling_creds"))
    router = VideoApiRouter()

    img = _create_sample_image(tmp_path / "character_anchor.jpg")
    ref_vid = tmp_path / "dance_ref.mp4"
    ref_vid.write_bytes(b"\x00\x00\x00\x18ftypmp42fake_video_bytes")

    # Image-only payload (first_frame)
    payload_img = router._build_seedance_v3_payload(
        model="doubao-seedance-1-5-pro-250528",
        image_path=img,
        prompt="anime figure dancing",
        duration=5,
        resolution="720p",
        ratio="9:16",
    )
    assert payload_img["model"] == "doubao-seedance-1-5-pro-250528"
    assert payload_img["duration"] == 5
    assert payload_img["resolution"] == "720p"
    assert payload_img["ratio"] == "9:16"
    assert len(payload_img["content"]) == 2
    assert payload_img["content"][0] == {"type": "text", "text": "anime figure dancing"}
    assert payload_img["content"][1]["type"] == "image_url"
    assert payload_img["content"][1]["role"] == "first_frame"
    assert payload_img["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")

    # Multimodal payload with reference video (reference_image + reference_video)
    payload_mm = router._build_seedance_v3_payload(
        model="doubao-seedance-2.0",
        image_path=img,
        prompt="motion transfer dance",
        duration=5,
        resolution="720p",
        ratio="9:16",
        reference_video_path=ref_vid,
    )
    assert len(payload_mm["content"]) == 3
    assert payload_mm["content"][1]["role"] == "reference_image"
    assert payload_mm["content"][2]["type"] == "video_url"
    assert payload_mm["content"][2]["role"] == "reference_video"
    assert payload_mm["content"][2]["video_url"]["url"].startswith("data:video/mp4;base64,")


def test_seedance_dual_key_bypasses_seedance_js_for_payg_and_polls_v3(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ARK_API_KEY", "ark-coding-plan-key")
    monkeypatch.setenv("ARK_PAYG_API_KEY", "uuid-payg-standard-key-9999")
    monkeypatch.setenv("KLING_CREDENTIALS_PATH", str(tmp_path / "no_kling_creds"))
    router = VideoApiRouter()
    router.poll_interval = 0.01

    img = _create_sample_image(tmp_path / "anchor.jpg")
    out_mp4 = tmp_path / "seedance_v3_out.mp4"

    posted_models = []

    def fake_post(url: str, headers: Dict[str, str], json: Dict[str, Any], timeout: float):
        assert url == "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks"
        assert headers["Authorization"] == "Bearer uuid-payg-standard-key-9999"
        model = json["model"]
        posted_models.append(model)
        resp = MagicMock()
        if model == SEEDANCE_V3_CANDIDATE_MODELS[0]:
            resp.status_code = 404
            resp.text = '{"error":{"code":"InvalidEndpointOrModel.NotFound"}}'
        else:
            resp.status_code = 200
            resp.json.return_value = {"id": "cgt-payg-20261107"}
        return resp

    def fake_get(url: str, headers: Optional[Dict[str, str]] = None, stream: bool = False, timeout: float = 60):
        resp = MagicMock()
        if url.endswith("/contents/generations/tasks/cgt-payg-20261107"):
            resp.status_code = 200
            resp.json.return_value = {
                "id": "cgt-payg-20261107",
                "status": "succeeded",
                "content": {"video_url": "https://cdn.volces.com/video/cgt-payg-20261107.mp4"},
            }
        elif url == "https://cdn.volces.com/video/cgt-payg-20261107.mp4":
            resp.status_code = 200
            resp.iter_content.return_value = [b"FAKE_MP4_STREAM_BYTES"]
        else:
            raise AssertionError(f"Unexpected GET URL: {url}")
        return resp

    with (
        patch("core.video_api_router.subprocess.run") as mock_subproc,
        patch("core.video_api_router.requests.post", side_effect=fake_post),
        patch("core.video_api_router.requests.get", side_effect=fake_get),
    ):
        result_path = router.generate_video_from_image(
            image_path=img,
            prompt="3d figure dance",
            provider="volcengine_seedance",
            output_path=out_mp4,
        )
        mock_subproc.assert_not_called()
        assert posted_models == [
            "doubao-seedance-1-5-pro-250528",
            "doubao-seedance-1-0-pro-250528",
        ]
        assert result_path == out_mp4.resolve()
        assert out_mp4.read_bytes() == b"FAKE_MP4_STREAM_BYTES"


def test_seedance_ark_prefix_tries_skill_then_falls_back_to_v3(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ARK_PAYG_API_KEY", raising=False)
    monkeypatch.setenv("ARK_API_KEY", "ark-agentplan-only-key")
    monkeypatch.setenv("KLING_CREDENTIALS_PATH", str(tmp_path / "no_kling_creds"))
    router = VideoApiRouter()

    img = _create_sample_image(tmp_path / "anchor.jpg")
    out_mp4 = tmp_path / "fallback_v3.mp4"

    failed_proc = subprocess.CompletedProcess(
        args=["node", "seedance.js"], returncode=1, stdout="", stderr="Error: 403 Forbidden"
    )

    with (
        patch("core.video_api_router.subprocess.run", return_value=failed_proc) as mock_subproc,
        patch.object(router, "_dispatch_seedance_v3", return_value=out_mp4) as mock_v3,
    ):
        res = router.generate_video_from_image(
            image_path=img,
            prompt="test fallback",
            provider="volcengine_seedance",
            output_path=out_mp4,
        )
        assert res == out_mp4
        assert mock_subproc.called
        mock_v3.assert_called_once()


def test_kling_http_image2video_and_motion_transfer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    monkeypatch.delenv("ARK_PAYG_API_KEY", raising=False)
    monkeypatch.setenv("KLING_CREDENTIALS_PATH", str(tmp_path / "no_kling_creds"))
    monkeypatch.setenv("KLING_ACCESS_KEY", "kling_ak_prod_01")
    monkeypatch.setenv("KLING_SECRET_KEY", "kling_sk_prod_02")
    monkeypatch.setenv("KLING_BASE_URL", "https://api.klingai.com")

    router = VideoApiRouter()
    router.poll_interval = 0.01

    img = _create_sample_image(tmp_path / "character_anchor.jpg")
    ref_video = tmp_path / "reference_dance.mp4"
    ref_video.write_bytes(b"FAKE_REF_VIDEO_CONTENT")
    out_i2v = tmp_path / "kling_i2v.mp4"
    out_motion = tmp_path / "kling_motion.mp4"

    assert _encode_kling_media_base64("data:image/jpeg;base64,QUJDRA==") == "QUJDRA=="
    img_b64 = _encode_kling_media_base64(img)
    assert not img_b64.startswith("data:")

    captured_posts = []

    def fake_kling_post(url: str, headers: Dict[str, str], json: Dict[str, Any], timeout: float):
        assert headers["Authorization"].startswith("Bearer ")
        assert len(headers["Authorization"].split(" ")[1].split(".")) == 3
        captured_posts.append((url, json))
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "code": 0,
            "message": "SUCCEED",
            "data": {"task_id": "kling-task-888", "task_status": "submitted"},
        }
        return resp

    def fake_kling_get(url: str, headers: Optional[Dict[str, str]] = None, stream: bool = False, timeout: float = 60):
        resp = MagicMock()
        if url.endswith("/kling-task-888"):
            resp.status_code = 200
            resp.json.return_value = {
                "code": 0,
                "data": {
                    "task_id": "kling-task-888",
                    "task_status": "succeed",
                    "task_result": {"videos": [{"id": "v1", "url": "https://cdn.klingai.com/out/kling-task-888.mp4"}]},
                },
            }
        elif url == "https://cdn.klingai.com/out/kling-task-888.mp4":
            resp.status_code = 200
            resp.iter_content.return_value = [b"KLING_MP4_DATA"]
        else:
            raise AssertionError(f"Unexpected Kling GET URL: {url}")
        return resp

    with (
        patch("core.video_api_router.requests.post", side_effect=fake_kling_post),
        patch("core.video_api_router.requests.get", side_effect=fake_kling_get),
    ):
        res1 = router.generate_video_from_image(
            image_path=img,
            prompt="anime figure swaying",
            provider="auto",
            duration=5,
            output_path=out_i2v,
        )
        assert res1 == out_i2v.resolve()
        assert out_i2v.read_bytes() == b"KLING_MP4_DATA"
        assert captured_posts[0][0] == "https://api.klingai.com/v1/videos/image2video"
        assert captured_posts[0][1]["model_name"] == "kling-v1-6"
        assert captured_posts[0][1]["duration"] == "5"
        assert captured_posts[0][1]["mode"] == "pro"
        assert not captured_posts[0][1]["image"].startswith("data:")

        res2 = router.generate_dance_motion_transfer(
            character_image=img,
            reference_video=ref_video,
            prompt="anime figure full dance motion transfer",
            duration=10,
            output_path=out_motion,
        )
        assert res2 == out_motion.resolve()
        assert out_motion.read_bytes() == b"KLING_MP4_DATA"
        assert captured_posts[1][0] == "https://api.klingai.com/v1/videos/video2video"
        assert captured_posts[1][1]["duration"] == "10"
        assert "video" in captured_posts[1][1]
        assert not captured_posts[1][1]["video"].startswith("data:")


def test_non_ark_prefix_api_key_calls_v3_directly_and_falls_back_to_simulator(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("ARK_PAYG_API_KEY", raising=False)
    monkeypatch.setenv("ARK_API_KEY", "12345678-abcd-1234-ef00-987654321000")
    monkeypatch.delenv("KLING_ACCESS_KEY", raising=False)
    monkeypatch.delenv("KLING_SECRET_KEY", raising=False)
    monkeypatch.delenv("KLING_API_KEY", raising=False)
    monkeypatch.setenv("KLING_CREDENTIALS_PATH", str(tmp_path / "no_kling_creds"))

    router = VideoApiRouter()
    img = _create_sample_image(tmp_path / "anchor.jpg")
    sim_out = tmp_path / "sim_fallback.mp4"

    fail_resp = MagicMock()
    fail_resp.status_code = 403
    fail_resp.text = "ModelNotOpen"

    with (
        patch("core.video_api_router.subprocess.run") as mock_subproc,
        patch("core.video_api_router.requests.post", return_value=fail_resp) as mock_post,
        patch.object(router, "_dispatch_simulator", return_value=sim_out) as mock_sim,
    ):
        res = router.generate_video_from_image(
            image_path=img,
            prompt="test non-ark prefix",
            provider="auto",
            output_path=sim_out,
        )
        assert res == sim_out
        mock_subproc.assert_not_called()
        assert mock_post.call_count == len(SEEDANCE_V3_CANDIDATE_MODELS)
        mock_sim.assert_called_once()
