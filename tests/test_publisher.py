"""Unit tests for Bilibili & Social Matrix AuthVault, BilibiliUploader, MatrixPublisher, WeChatMPPublisher, and CLI."""

from __future__ import annotations

import json
import stat
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest
import requests
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
    BILIBILI_ACTIVITY_MISSIONS,
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


def test_parse_bilibili_markdown_tid_priority_and_pinned_comment() -> None:
    md_text = (
        "# Bilibili (B站) 视频发布配置与运营脚本\n\n"
        "## 一、 视频基础信息\n"
        "* **主选分区**：动画 -> MMD·3D (或 科技 -> 人工智能)\n"
        "* **视频标题 (建议3选1)**：\n"
        "  1. 当我把B站账号交给AI：蓝色大肥鱼热舞【B站AI创造公开赛】 (首选)\n"
        "* **简介 (Description)**：\n"
        "  大家好，我是 AI Agent！\n"
        "* **标签 (Tags)**：\n"
        "  B站AI创造公开赛, DeepSeek, 蓝色大肥鱼, MMD\n\n"
        "## 二、 弹幕互动与置顶评论引导\n"
        "* **置顶评论**：\n"
        "  “报告各位人类观众！赛博股东养成计划启动！”\n"
    )
    parsed = MatrixPublisher.parse_bilibili_markdown(md_text)
    assert parsed["tid"] == 25
    assert parsed["title"] == "当我把B站账号交给AI：蓝色大肥鱼热舞【B站AI创造公开赛】"
    assert parsed["pinned_comment"] == "报告各位人类观众！赛博股东养成计划启动！"


def test_resolve_activity_mission_and_submit_archive_golden_params() -> None:
    mock_session = MagicMock()
    uploader = BilibiliUploader(
        cookies={"SESSDATA": "sess_ok", "bili_jct": "csrf_ok", "DedeUserID": "10000001"},
        session=mock_session,
    )

    assert BILIBILI_ACTIVITY_MISSIONS["B站AI创造公开赛"]["mission_id"] == 4071698
    assert BILIBILI_ACTIVITY_MISSIONS["B站AI无限竞技场"]["mission_id"] == 4070254
    assert BILIBILI_ACTIVITY_MISSIONS["AI偶像才艺大赏"]["mission_id"] == 4071944

    act = uploader.resolve_activity_mission(tags=["DeepSeek", "B站AI创造公开赛"], title="测试视频")
    assert act == {"topic_id": 1340873, "mission_id": 4071698, "topic_name": "B站AI创造公开赛"}

    mock_session.post.return_value = _DummyResponse(
        {"code": 0, "message": "0", "data": {"aid": 55667788, "bvid": "BV1GoldenParams"}}
    )
    sub_res = uploader.submit_archive(
        bili_filename="n261107golden",
        cover_url="https://archive.biliimg.com/bfs/archive/c.jpg",
        title="蓝色大肥鱼热舞【B站AI创造公开赛】",
        tid=25,
        tags=["B站AI创造公开赛", "DeepSeek", "蓝色大肥鱼"],
        description="测试简介",
        biz_id=12345,
    )
    assert sub_res["bvid"] == "BV1GoldenParams"
    assert sub_res["mission_id"] == 4071698
    assert sub_res["topic_id"] == 1340873

    sent_payload = mock_session.post.call_args.kwargs["json"]
    assert sent_payload["no_reprint"] == 1
    assert sent_payload["open_elec"] == 1
    assert sent_payload["up_selection_reply"] == 0
    assert sent_payload["up_close_reply"] == 0
    assert sent_payload["up_close_danmu"] == 0
    assert sent_payload["mission_id"] == 4071698
    assert sent_payload["topic_id"] == 1340873
    assert sent_payload["topic_name"] == "B站AI创造公开赛"
    assert sent_payload["dynamic"] == "#B站AI创造公开赛# 蓝色大肥鱼热舞【B站AI创造公开赛】"


def test_post_and_pin_comment_and_edit_archive() -> None:
    mock_session = MagicMock()
    mock_session.post.side_effect = [
        _DummyResponse({"code": 0, "data": {"rpid": 9988776655}}),
        _DummyResponse({"code": 0, "message": "OK", "data": None}),
        _DummyResponse({"code": 0, "message": "OK", "data": {"aid": 112233, "bvid": "BV1EditOk"}}),
    ]
    mock_session.get.return_value = _DummyResponse(
        {
            "code": 0,
            "data": {
                "archive": {
                    "aid": 112233,
                    "bvid": "BV1EditOk",
                    "title": "原视频标题",
                    "cover": "https://archive.biliimg.com/bfs/archive/c.jpg",
                    "tid": 231,
                    "tag": "AI,DeepSeek",
                    "desc": "旧简介",
                    "copyright": 1,
                },
                "videos": [
                    {
                        "filename": "n261107file",
                        "title": "原视频标题",
                        "desc": "",
                        "cid": 445566,
                    }
                ],
            },
        }
    )

    uploader = BilibiliUploader(
        cookies={"SESSDATA": "sess_ok", "bili_jct": "csrf_ok", "DedeUserID": "10000001"},
        session=mock_session,
    )
    pin_res = uploader.post_and_pin_comment(112233, "赛博股东养成计划置顶评论")
    assert pin_res["added"] is True
    assert pin_res["pinned"] is True
    assert pin_res["rpid"] == 9988776655

    edit_res = uploader.edit_archive(
        aid=112233,
        description="新简介含【借物表】与【AIGC】",
        tid=25,
        mission_id=4071698,
        topic_id=1340873,
        topic_name="B站AI创造公开赛",
    )
    assert edit_res["updated"] is True
    assert edit_res["submitted_payload"]["tid"] == 25
    assert edit_res["submitted_payload"]["mission_id"] == 4071698
    assert edit_res["submitted_payload"]["desc_format_id"] == 0


def test_discover_metadata_compliance_footer_and_real_projects(tmp_path: Path) -> None:
    proj = tmp_path / "099_custom_demo"
    (proj / "delivery").mkdir(parents=True)
    (proj / "delivery" / "bilibili.md").write_text(
        "* **主选分区**：科技 -> 人工智能\n* **视频标题**：测试短标题\n* **简介**：简短介绍无尾注\n",
        encoding="utf-8",
    )
    mp_tmp = MatrixPublisher(projects_dir=tmp_path)
    meta_tmp = mp_tmp.discover_metadata(proj)
    assert "【借物表" in meta_tmp["description"]
    assert "【AIGC" in meta_tmp["description"]

    mp_real = MatrixPublisher()
    expected_tids = {
        "007": 25,
        "005": 231,
        "008": 231,
        "004": 231,
        "002": 231,
        "003": 231,
        "009": 231,
    }
    for pid, exp_tid in expected_tids.items():
        pdir = mp_real.resolve_project_dir(pid)
        meta = mp_real.discover_metadata(pdir)
        assert meta["tid"] == exp_tid
        assert "【借物表" in meta["description"]
        assert "【AIGC" in meta["description"]
        assert len(meta["pinned_comment"]) > 10


def test_upload_video_upos_ssl_error_falls_back_to_next_cdn(tmp_path: Path) -> None:
    video_file = tmp_path / "fallback_demo.mp4"
    video_file.write_bytes(b"0123456789abcdef" * 512)

    mock_session = MagicMock()
    mock_session.get.side_effect = [
        _DummyResponse(
            {
                "OK": 1,
                "upos_uri": "upos://ugcupos/bda2_fail.mp4",
                "endpoint": "//upos-cs-upcdnbda2.bilivideo.com",
                "auth": "ak=bda2_auth",
                "chunk_size": 10485760,
                "biz_id": 111222,
            }
        ),
        _DummyResponse(
            {
                "OK": 1,
                "upos_uri": "upos://ugcupos/txa_ok.mp4",
                "endpoint": "//upos-cs-upcdntxa.bilivideo.com",
                "auth": "ak=txa_auth",
                "chunk_size": 10485760,
                "biz_id": 333444,
            }
        ),
    ]
    mock_session.post.side_effect = [
        requests.exceptions.SSLError("EOF occurred in violation of protocol"),
        _DummyResponse({"OK": 1, "upload_id": "up_txa_999"}),
        _DummyResponse({"OK": 1}),
    ]
    mock_session.put.return_value = _DummyResponse({"OK": 1})

    uploader = BilibiliUploader(
        cookies={"SESSDATA": "sess_ok", "bili_jct": "csrf_ok", "DedeUserID": "10000001"},
        session=mock_session,
        upcdn="bda2",
    )
    upos_info = uploader.upload_video_upos(video_file)

    assert upos_info["bili_filename"] == "txa_ok"
    assert upos_info["biz_id"] == 333444
    assert mock_session.get.call_count == 2
    assert mock_session.put.call_count == 1


def test_sync_live_pinned_comments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    proj_already = tmp_path / "010_already_pinned"
    (proj_already / "delivery" / "staged_bilibili").mkdir(parents=True)
    (proj_already / "delivery" / "bilibili.md").write_text(
        "* **主选分区**：科技 -> 人工智能\n"
        "* **视频标题**：已置顶测试标题\n"
        "* **简介**：含【借物表】与【AIGC】声明\n"
        "* **置顶评论**：“报告各位赛博股东，第10期置顶测试评论内容”\n",
        encoding="utf-8",
    )
    (proj_already / "delivery" / "staged_bilibili" / "publish_manifest.json").write_text(
        json.dumps({"advisor_receipt": {"bvid": "BV1AlreadyOk"}}, ensure_ascii=False),
        encoding="utf-8",
    )

    proj_needs = tmp_path / "011_needs_pin"
    (proj_needs / "delivery" / "staged_bilibili").mkdir(parents=True)
    (proj_needs / "delivery" / "bilibili.md").write_text(
        "* **主选分区**：科技 -> 人工智能\n"
        "* **视频标题**：待置顶测试标题\n"
        "* **简介**：含【借物表】与【AIGC】声明\n"
        "* **置顶评论**：“报告各位赛博股东，第11期全新待置顶评论内容”\n",
        encoding="utf-8",
    )
    (proj_needs / "delivery" / "staged_bilibili" / "publish_manifest.json").write_text(
        json.dumps({"advisor_receipt": {"bvid": "BV1NeedsPin"}}, ensure_ascii=False),
        encoding="utf-8",
    )

    vault = AuthVault(vault_dir=tmp_path / "vault")
    vault.save_bilibili_session({"SESSDATA": "sess_sync", "bili_jct": "csrf_sync", "DedeUserID": "10000002"})

    import core.analytics as analytics_mod

    def fake_fetch_archives(self: Any, status: str = "pubed", ps: int = 30) -> Dict[str, Any]:
        return {
            "archives": [
                {"aid": 10010, "bvid": "BV1AlreadyOk", "title": "已置顶测试标题", "state": 0, "state_desc": "开放浏览"},
                {"aid": 10011, "bvid": "BV1NeedsPin", "title": "待置顶测试标题", "state": 0, "state_desc": "开放浏览"},
            ]
        }

    def fake_fetch_comments(self: Any, aid: int, ps: int = 20) -> List[Dict[str, Any]]:
        if aid == 10010:
            return [{"rpid": 555, "message": "报告各位赛博股东，第10期置顶测试评论内容"}]
        return [{"rpid": 556, "message": "普通路人评论"}]

    pinned_calls: List[Dict[str, Any]] = []

    def fake_post_and_pin(self: Any, aid: int, message: str) -> Dict[str, Any]:
        pinned_calls.append({"aid": aid, "message": message})
        return {"rpid": 777888, "added": True, "pinned": True}

    monkeypatch.setattr(analytics_mod.BilibiliAnalytics, "fetch_creator_archives", fake_fetch_archives)
    monkeypatch.setattr(analytics_mod.BilibiliAnalytics, "fetch_archive_comments", fake_fetch_comments)
    monkeypatch.setattr(BilibiliUploader, "post_and_pin_comment", fake_post_and_pin)

    mp = MatrixPublisher(projects_dir=tmp_path, vault=vault)
    sync_results = mp.sync_live_pinned_comments()

    by_proj = {item["project_id"]: item for item in sync_results}
    assert by_proj["010_already_pinned"]["status"] == "already_pinned"
    assert by_proj["011_needs_pin"]["status"] == "pinned_now"
    assert by_proj["011_needs_pin"]["pinned"] is True
    assert by_proj["011_needs_pin"]["rpid"] == 777888
    assert len(pinned_calls) == 1
    assert pinned_calls[0]["aid"] == 10011
    assert "第11期全新待置顶评论内容" in pinned_calls[0]["message"]


def test_edit_archive_dtime_timeout_fallback_and_analytics_directives(tmp_path: Path) -> None:
    """Verifies scheduled dtime preservation/override, UPOS Timeout fallback, and analytics directives."""
    from core.analytics import BilibiliAnalytics

    mock_session = MagicMock()
    mock_session.get.return_value = _DummyResponse(
        {
            "code": 0,
            "data": {
                "archive": {
                    "aid": 223344,
                    "title": "定时排期标题",
                    "cover": "https://archive.biliimg.com/bfs/archive/old.jpg",
                    "tid": 231,
                    "tag": "AI",
                    "desc": "旧简介",
                    "copyright": 1,
                    "dtime": 1794738600,
                },
                "videos": [{"filename": "oldfile", "title": "P1", "desc": "", "cid": 11}],
            },
        }
    )
    mock_session.post.side_effect = [
        _DummyResponse({"code": 0, "data": {"aid": 223344}}),
        _DummyResponse({"code": 0, "data": {"aid": 223344}}),
    ]
    uploader = BilibiliUploader(
        cookies={"SESSDATA": "s", "bili_jct": "j", "DedeUserID": "10000001"},
        session=mock_session,
    )
    res_keep = uploader.edit_archive(aid=223344, description="更新描述")
    assert res_keep["submitted_payload"]["dtime"] == 1794738600

    res_override = uploader.edit_archive(aid=223344, description="重设排期", dtime=1794825000)
    assert res_override["submitted_payload"]["dtime"] == 1794825000

    # Timeout fallback on UPOS chunk upload
    vid = tmp_path / "timeout_demo.mp4"
    vid.write_bytes(b"0123456789" * 64)
    sess_to = MagicMock()
    sess_to.get.side_effect = [
        _DummyResponse(
            {
                "OK": 1,
                "upos_uri": "upos://ugcupos/t1.mp4",
                "endpoint": "//upos-cs-upcdntxa.bilivideo.com",
                "auth": "ak=1",
                "chunk_size": 10485760,
                "biz_id": 101,
            }
        ),
        _DummyResponse(
            {
                "OK": 1,
                "upos_uri": "upos://ugcupos/tx_ok.mp4",
                "endpoint": "//upos-cs-upcdntx.bilivideo.com",
                "auth": "ak=2",
                "chunk_size": 10485760,
                "biz_id": 202,
            }
        ),
    ]
    sess_to.post.side_effect = [
        requests.exceptions.Timeout("connect timed out"),
        _DummyResponse({"OK": 1, "upload_id": "up2"}),
        _DummyResponse({"OK": 1}),
    ]
    sess_to.put.return_value = _DummyResponse({"OK": 1})
    up2 = BilibiliUploader(cookies={"SESSDATA": "s", "bili_jct": "j"}, session=sess_to, upcdn="txa")
    upos_out = up2.upload_video_upos(vid)
    assert upos_out["bili_filename"] == "tx_ok"

    directives = BilibiliAnalytics.build_optimization_directives(
        [
            {
                "bvid": "BV1Bounce",
                "title": "干声教程",
                "diagnose": {"crash_rate_pct": 63.63, "crash_p50_pct": 27.35, "tm_stars": 3.3},
                "recent_comments": [
                    {"uname": "白的黑板", "message": "有没有翻唱司凤版雨爱[doge]"},
                    {"uname": "creator_bot", "message": "有没有想看的下期"},
                ],
            },
            {
                "bvid": "BV1LowStar",
                "title": "低星封面",
                "diagnose": {"crash_rate_pct": 25.0, "crash_p50_pct": 27.35, "tm_stars": 2.0},
                "recent_comments": [],
            },
        ],
        account_uname="creator_bot",
    )
    types = {d["type"] for d in directives}
    assert types == {"hook_and_bgm_upgrade", "viewer_request", "cover_hero_contrast_upgrade"}
    req = next(d for d in directives if d["type"] == "viewer_request")
    assert req["requester"] == "白的黑板"
