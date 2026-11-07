"""Unit tests for Bilibili & Social Matrix AuthVault, BilibiliUploader, MatrixPublisher, WeChatMPPublisher, and CLI."""

from __future__ import annotations

import json
import stat
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest
from PIL import Image

import cli
from core.auth_vault import (
    SUPPORTED_PLATFORMS,
    AuthVault,
    encode_qr_matrix,
    generate_bilibili_qr,
    poll_bilibili_qr,
    render_qr_png,
    render_qr_terminal_halfblock,
)
from core.publisher import (
    BILIBILI_MIN_SCHEDULE_LEAD_SECONDS,
    BilibiliUploader,
    MatrixPublisher,
    WeChatMPPublisher,
    compute_bilibili_dtime,
)


class _DummyResponse:
    def __init__(
        self,
        json_data: Dict[str, Any],
        cookies: Dict[str, str] | None = None,
        headers: Dict[str, str] | None = None,
        status_code: int = 200,
    ) -> None:
        self._json = json_data
        self.cookies = cookies or {}
        self.headers = headers or {}
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> Dict[str, Any]:
        return self._json


def test_qr_dual_renderer_png_and_terminal_halfblocks(tmp_path: Path) -> None:
    qr_url = "https://passport.bilibili.com/h5-app/passport/login/scan?navhide=1&qrcode_key=testkey1234567890"
    matrix = encode_qr_matrix(qr_url)
    assert len(matrix) >= 21
    assert len(matrix) == len(matrix[0])

    png_path = tmp_path / "output" / "auth" / "bilibili_qr.png"
    render_qr_png(matrix, png_path)
    assert png_path.exists()
    with Image.open(png_path) as im:
        assert im.format == "PNG"
        assert im.size[0] == im.size[1] and im.size[0] > 100

    try:
        import cv2

        cv_img = cv2.imread(str(png_path))
        assert cv_img is not None
        decoded, _, _ = cv2.QRCodeDetector().detectAndDecode(cv_img)
        assert decoded == qr_url
    except ImportError:
        pass

    term_str = render_qr_terminal_halfblock(matrix)
    assert any(ch in term_str for ch in ("▀", "▄", "█"))


def test_bilibili_qr_generate_poll_and_verify_0600_vault(tmp_path: Path) -> None:
    vault_dir = tmp_path / "vault"
    vault = AuthVault(vault_dir=vault_dir)
    qr_png = tmp_path / "output" / "auth" / "bilibili_qr.png"

    mock_session = MagicMock()
    mock_session.get.return_value = _DummyResponse(
        {
            "code": 0,
            "message": "0",
            "ttl": 1,
            "data": {
                "url": "https://passport.bilibili.com/h5-app/passport/login/scan?qrcode_key=bili_key_abc",
                "qrcode_key": "bili_key_abc",
            },
        }
    )

    gen_info = generate_bilibili_qr(qr_image_path=qr_png, session=mock_session, print_terminal=False)
    assert gen_info["qrcode_key"] == "bili_key_abc"
    assert Path(gen_info["qr_image_path"]).exists()
    assert "█" in gen_info["terminal_qr"]

    poll_responses: List[_DummyResponse] = [
        _DummyResponse({"code": 0, "data": {"code": 86101, "message": "未扫码"}}),
        _DummyResponse({"code": 0, "data": {"code": 86090, "message": "二维码已扫码未确认"}}),
        _DummyResponse(
            {
                "code": 0,
                "data": {
                    "code": 0,
                    "message": "",
                    "url": (
                        "https://passport.biligame.com/crossDomain?"
                        "DedeUserID=34567890&DedeUserID__ckMd5=md5val123&"
                        "SESSDATA=sessdata_secret_val&bili_jct=csrf_jct_val&sid=sid_val_99"
                    ),
                    "refresh_token": "refresh_tok_xyz",
                },
            },
            cookies={"SESSDATA": "sessdata_secret_val", "bili_jct": "csrf_jct_val", "DedeUserID": "34567890"},
        ),
        _DummyResponse(
            {
                "code": 0,
                "data": {
                    "isLogin": True,
                    "uname": "NoshiroCommander",
                    "mid": 34567890,
                    "level_info": {"current_level": 6},
                },
            }
        ),
    ]
    mock_session.get.side_effect = poll_responses

    res = poll_bilibili_qr(
        qrcode_key="bili_key_abc",
        timeout=30,
        interval=0.01,
        vault=vault,
        session=mock_session,
        sleep_fn=lambda _: None,
    )
    assert res["status"] == "confirmed"
    assert res["refresh_token"] == "refresh_tok_xyz"
    assert res["cookies"]["SESSDATA"] == "sessdata_secret_val"
    assert res["cookies"]["bili_jct"] == "csrf_jct_val"
    assert res["cookies"]["DedeUserID"] == "34567890"
    assert res["cookies"]["DedeUserID__ckMd5"] == "md5val123"
    assert res["cookies"]["sid"] == "sid_val_99"
    assert res["profile"]["logged_in"] is True
    assert res["profile"]["uname"] == "NoshiroCommander"
    assert res["profile"]["level"] == 6

    cookies_path = Path(res["cookies_path"])
    storage_path = Path(res["storage_state_path"])
    assert cookies_path.exists()
    assert storage_path.exists()

    assert stat.S_IMODE(cookies_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(storage_path.stat().st_mode) == 0o600

    storage_json = json.loads(storage_path.read_text(encoding="utf-8"))
    assert any(c["name"] == "SESSDATA" and c["domain"] == ".bilibili.com" for c in storage_json["cookies"])

    statuses = vault.get_all_statuses(verify_online=False)
    assert set(statuses.keys()) == set(SUPPORTED_PLATFORMS)
    assert statuses["bilibili"]["logged_in"] is True
    assert statuses["bilibili"]["uname"] == "NoshiroCommander"
    assert statuses["bilibili"]["mid"] == "34567890"


def test_bilibili_uploader_upos_cover_and_scheduled_add_v3(tmp_path: Path) -> None:
    now_ts = int(time.time())
    dtime_val = compute_bilibili_dtime("+5h", now_ts=now_ts)
    assert dtime_val >= now_ts + BILIBILI_MIN_SCHEDULE_LEAD_SECONDS

    # Also verify HH:MM rolls forward so it's always >= 4h10m in the future
    dtime_hhmm = compute_bilibili_dtime("23:50", now_ts=now_ts)
    assert dtime_hhmm >= now_ts + BILIBILI_MIN_SCHEDULE_LEAD_SECONDS

    video_file = tmp_path / "demo_video.mp4"
    video_file.write_bytes(b"0123456789abcdef" * 1024)
    cover_file = tmp_path / "demo_cover.jpg"
    Image.new("RGB", (640, 360), color=(20, 60, 120)).save(cover_file)

    mock_session = MagicMock()
    # GET /preupload
    mock_session.get.return_value = _DummyResponse(
        {
            "OK": 1,
            "upos_uri": "upos://ugcupos/n261107abc123.mp4",
            "endpoint": "//upos-sz-upcdnbda2.bilivideo.com",
            "auth": "ak=test_auth_token",
            "chunk_size": 8192,
            "biz_id": 987654321,
        }
    )
    # PUT chunk (2 chunks of 8192 bytes)
    mock_session.put.return_value = _DummyResponse({"OK": 1})
    # POST sequence: 1) cover/up, 2) UPOS init upload_id, 3) UPOS finalize, 4) add/v3
    mock_session.post.side_effect = [
        _DummyResponse({"code": 0, "data": {"url": "https://archive.biliimg.com/bfs/archive/cover123.jpg"}}),
        _DummyResponse({"OK": 1, "upload_id": "up_id_777"}),
        _DummyResponse({"OK": 1}),
        _DummyResponse({"code": 0, "message": "0", "data": {"aid": 11223344, "bvid": "BV1TestSchedule99"}}),
    ]

    uploader = BilibiliUploader(
        cookies={"SESSDATA": "sess_ok", "bili_jct": "csrf_ok", "DedeUserID": "10000001"},
        session=mock_session,
    )
    res = uploader.upload_to_bilibili_API(
        video_path=video_file,
        cover_path=cover_file,
        title="【手办科普】Transformer 原理解析",
        tid=231,
        tags=["大模型", "Transformer", "科技科普"],
        description="深度解析 Transformer QKV 与多头注意力",
        mode="schedule",
        schedule_at="+6h",
    )

    assert res["status"] == "scheduled_on_bilibili"
    assert res["bvid"] == "BV1TestSchedule99"
    assert res["aid"] == 11223344
    assert res["cover_url"] == "https://archive.biliimg.com/bfs/archive/cover123.jpg"
    assert res["bili_filename"] == "n261107abc123"
    assert res["upos"]["chunks"] == 2
    assert res["dtime"] is not None and res["dtime"] >= now_ts + BILIBILI_MIN_SCHEDULE_LEAD_SECONDS
    assert mock_session.put.call_count == 2


def test_matrix_publisher_draft_remains_local_and_schedule_uploads(tmp_path: Path) -> None:
    vault = AuthVault(vault_dir=tmp_path / "vault")
    vault.save_bilibili_session(
        cookies={"SESSDATA": "s1", "bili_jct": "j1", "DedeUserID": "10000001"},
        refresh_token="rt1",
        profile={"uname": "demo_creator", "mid": 10000001, "level": 5},
    )

    projects_dir = tmp_path / "projects"
    proj_dir = projects_dir / "005_transformer_noshiro_tutorial"
    delivery_dir = proj_dir / "delivery"
    delivery_dir.mkdir(parents=True)

    video_file = delivery_dir / "noshiro_final.mp4"
    video_file.write_bytes(b"\x00\x00\x00\x18ftypmp42")

    bili_md = (
        "# Bilibili (B站) 视频发布配置与运营脚本\n\n"
        "## 一、 视频基础信息\n"
        "* **主选分区**：知识 -> 计算机技术 / 科技综合\n"
        "* **视频标题 (建议3选1)**：\n"
        "  1. 【手办讲解】能代带你彻底搞懂大模型心脏！Transformer 原理全景拆解 (首选)\n"
        "* **简介 (Description)**：\n"
        "  本期视频由能代出镜，带你 3 分钟穿透 Transformer 核心黑盒。\n"
        "* **标签 (Tags)**：\n"
        "  大模型, Transformer, 人工智能, 深度学习, 能代\n"
    )
    (delivery_dir / "bilibili.md").write_text(bili_md, encoding="utf-8")

    mock_session = MagicMock()
    publisher = MatrixPublisher(vault=vault, projects_dir=projects_dir, session=mock_session)

    # 1. mode="draft" must stay local without making any HTTP calls
    draft_res = publisher.publish_project(
        project="005",
        platforms=["bilibili", "douyin"],
        mode="draft",
    )
    assert draft_res["safety_mode"] == "draft"
    assert mock_session.post.call_count == 0
    assert mock_session.get.call_count == 0
    bili_manifest = draft_res["platforms"]["bilibili"]
    assert bili_manifest["title"] == "【手办讲解】能代带你彻底搞懂大模型心脏！Transformer 原理全景拆解"
    assert bili_manifest["tid"] == 231
    assert Path(bili_manifest["cover_path"]).exists()
    assert bili_manifest["advisor_receipt"]["status"] == "staged_for_advisor_review"

    # 2. mode="schedule" triggers real UPOS + add/v3 upload via session
    mock_session.get.return_value = _DummyResponse(
        {
            "OK": 1,
            "upos_uri": "upos://ugcupos/sched999.mp4",
            "endpoint": "//upos-sz-upcdnbda2.bilivideo.com",
            "auth": "ak=sched_auth",
            "chunk_size": 1048576,
            "biz_id": 555666,
        }
    )
    mock_session.put.return_value = _DummyResponse({"OK": 1})
    mock_session.post.side_effect = [
        _DummyResponse({"code": 0, "data": {"url": "https://archive.biliimg.com/bfs/archive/c999.jpg"}}),
        _DummyResponse({"OK": 1, "upload_id": "uid_999"}),
        _DummyResponse({"OK": 1}),
        _DummyResponse({"code": 0, "data": {"aid": 778899, "bvid": "BV1Sched999"}}),
    ]

    sched_res = publisher.publish_project(
        project="005",
        platforms=["bilibili"],
        mode="schedule",
        schedule_at="20:30",
    )
    sched_receipt = sched_res["platforms"]["bilibili"]["advisor_receipt"]
    assert sched_receipt["status"] == "scheduled_on_bilibili"
    assert sched_receipt["bvid"] == "BV1Sched999"


def test_wechat_mp_publisher_draft_box(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WECHAT_MP_APPID", "wx_test_appid_123")
    monkeypatch.setenv("WECHAT_MP_APPSECRET", "wx_test_secret_456")

    cover_path = tmp_path / "cover.jpg"
    Image.new("RGB", (640, 360), color=(10, 40, 80)).save(cover_path)

    mock_session = MagicMock()
    mock_session.get.return_value = _DummyResponse({"access_token": "wx_tok_999", "expires_in": 7200})
    mock_session.post.side_effect = [
        _DummyResponse({"media_id": "thumb_media_id_001"}),
        _DummyResponse({"media_id": "draft_media_id_888"}),
    ]

    mp_pub = WeChatMPPublisher(session=mock_session)
    assert mp_pub.is_configured is True

    res = mp_pub.push_draft(
        title="DeepSeek 架构深度解析",
        html_content="<section><h1>DeepSeek</h1><p>Inline CSS body</p></section>",
        digest="3分钟读懂 DeepSeek 核心原理",
        cover_path=cover_path,
    )
    assert res["status"] == "draft_pushed"
    assert res["media_id"] == "draft_media_id_888"
    assert res["thumb_media_id"] == "thumb_media_id_001"


def test_cli_auth_status_and_publish_subcommands(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    projects_dir = tmp_path / "projects"
    proj_dir = projects_dir / "001_demo_video"
    (proj_dir / "delivery").mkdir(parents=True)
    (proj_dir / "delivery" / "demo_final.mp4").write_bytes(b"mp4data")
    (proj_dir / "brief.json").write_text(
        json.dumps(
            {
                "project_id": "001_demo_video",
                "name": "DemoEngine",
                "tagline": "Next-gen automation",
                "category": "计算机技术",
                "description": "Fast video automation pipeline",
                "tech_stack": ["Python", "FFmpeg"],
                "highlights": ["100% deterministic"],
                "call_to_action": "Try DemoEngine now!",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr("core.auth_vault.DEFAULT_VAULT_DIR", tmp_path / "vault")

    monkeypatch.setattr("sys.argv", ["cli.py", "auth", "status"])
    assert cli.main() == 0

    monkeypatch.setattr(
        "sys.argv",
        ["cli.py", "publish", "--project", "001", "--platforms", "bilibili", "--mode", "draft"],
    )
    assert cli.main() == 0
    staged_manifest = proj_dir / "delivery" / "staged_bilibili" / "publish_manifest.json"
    assert staged_manifest.exists()
    data = json.loads(staged_manifest.read_text(encoding="utf-8"))
    assert data["project_id"] == "001_demo_video"
    assert data["safety_mode"] == "draft"


def test_bilibili_analytics_report_and_tracks(tmp_path: Path) -> None:
    from core.analytics import BilibiliAnalytics

    vault = AuthVault(vault_dir=tmp_path / "vault")
    vault.save_bilibili_session(
        cookies={"SESSDATA": "s_ok", "bili_jct": "j_ok", "DedeUserID": "10000001"},
        refresh_token="rt_ok",
        profile={"uname": "demo_creator", "mid": 10000001, "level": 5},
    )

    mock_session = MagicMock()
    mock_session.get.side_effect = [
        _DummyResponse({"code": 0, "data": {"follower": 13, "following": 48, "dynamic_count": 2}}),
        _DummyResponse(
            {
                "code": 0,
                "data": {
                    "class": {"pubed": 1, "is_pubing": 1, "not_pubed": 0},
                    "arc_audits": [
                        {
                            "bvid": "BV1TestDafeiyu01",
                            "Archive": {
                                "aid": 998877,
                                "bvid": "BV1TestDafeiyu01",
                                "title": "当我把B站账号交给AI：蓝色大肥鱼热舞",
                                "typeid": 25,
                                "state": 0,
                                "state_desc": "开放浏览",
                                "ptime": 1794030000,
                                "dtime": 0,
                            },
                            "stat": {
                                "view": 1500,
                                "like": 210,
                                "coin": 85,
                                "favorite": 120,
                                "danmaku": 34,
                                "reply": 28,
                                "share": 15,
                            },
                        }
                    ],
                },
            }
        ),
        _DummyResponse(
            {"code": 0, "data": {"list": [{"bvid": "BV1Pop", "title": "大肥鱼接入MC", "stat": {"view": 23000}}]}}
        ),
        _DummyResponse({"code": 0, "data": {"list": []}}),
        _DummyResponse({"code": 0, "data": {"list": []}}),
        _DummyResponse({"code": 0, "data": {"list": []}}),
    ]

    analytics = BilibiliAnalytics(
        vault=vault,
        session=mock_session,
        analytics_dir=tmp_path / "analytics",
    )
    report = analytics.generate_report(save_snapshot=True)
    assert report["account"]["follower"] == 13
    assert report["totals"]["view"] == 1500
    assert report["totals"]["coin"] == 85
    assert len(report["archives"]) == 1
    assert report["archives"][0]["bvid"] == "BV1TestDafeiyu01"
    assert len(report["recommended_tracks"]) >= 3
    assert Path(report["snapshot_json"]).exists()
    assert Path(report["snapshot_md"]).exists()
