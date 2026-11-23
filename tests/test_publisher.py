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
    BILIBILI_AI_NEUTRAL_MARK,
    BILIBILI_MIN_SCHEDULE_LEAD_SECONDS,
    BilibiliUploader,
    MatrixPublisher,
    WeChatMPPublisher,
    compute_bilibili_dtime,
    redact_auth_status,
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
    assert res["neutral_mark"] == BILIBILI_AI_NEUTRAL_MARK
    assert mock_session.post.call_args_list[-1].kwargs["json"]["neutral_mark"] == BILIBILI_AI_NEUTRAL_MARK
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
    assert report["account"]["uid"] == "<REDACTED>"
    assert report["account"]["uname"] == "<REDACTED>"
    assert report["account"]["follower"] == 13
    assert report["totals"]["view"] == 1500
    assert report["totals"]["coin"] == 85
    assert len(report["archives"]) == 1
    assert report["archives"][0]["bvid"] == "BV1TestDafeiyu01"
    assert len(report["recommended_tracks"]) >= 3
    snapshot_json_path = Path(report["snapshot_json"])
    snapshot_md_path = Path(report["snapshot_md"])
    assert snapshot_json_path.exists()
    assert snapshot_md_path.exists()
    snapshot_json_text = snapshot_json_path.read_text(encoding="utf-8")
    snapshot_md_text = snapshot_md_path.read_text(encoding="utf-8")
    assert "10000001" not in snapshot_json_text
    assert "demo_creator" not in snapshot_json_text
    assert "demo_creator" not in snapshot_md_text


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
        "008": 20,
        "004": 231,
        "002": 231,
        "003": 231,
        "009": 231,
        "010": 20,
        "011": 20,
        "012": 20,
        "013": 20,
        "014": 20,
        "015": 20,
    }
    for pid, exp_tid in expected_tids.items():
        pdir = mp_real.resolve_project_dir(pid)
        meta = mp_real.discover_metadata(pdir)
        assert meta["tid"] == exp_tid
        assert "【借物表" in meta["description"]
        assert "【AIGC" in meta["description"]
        assert len(meta["pinned_comment"]) > 10
        assert "@" not in meta["pinned_comment"]


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


def test_bilibili_analytics_redacts_mid_and_self_comments_after_directives(tmp_path: Path, monkeypatch) -> None:
    """Verifies directives filter creator comments before redaction and snapshots hide uid/mid/uname."""
    from core.analytics import BilibiliAnalytics

    vault = AuthVault(vault_dir=tmp_path / "vault")
    analytics = BilibiliAnalytics(vault=vault, cookies={}, analytics_dir=tmp_path / "analytics")

    monkeypatch.setattr(
        analytics,
        "fetch_account_stats",
        lambda: {
            "uid": "99887766",
            "mid": 99887766,
            "uname": "secret_creator_name",
            "level": 6,
            "logged_in": True,
            "follower": 42,
            "following": 5,
            "dynamic_count": 3,
        },
    )
    monkeypatch.setattr(
        analytics,
        "fetch_creator_archives",
        lambda: {
            "counts": {"pubed": 1, "is_pubing": 0, "not_pubed": 0, "total": 1},
            "totals": {"view": 100, "like": 10, "coin": 2, "favorite": 3, "danmaku": 1, "reply": 2, "share": 0},
            "archives": [
                {
                    "bvid": "BV1RedactionTest",
                    "aid": 123456,
                    "title": "测试稿件",
                    "tid": 20,
                    "state": 0,
                    "state_desc": "开放浏览",
                    "stat": {"view": 100, "like": 10, "coin": 2, "favorite": 3, "danmaku": 1, "reply": 2, "share": 0},
                    "diagnose": {},
                    "recent_comments": [
                        {"rpid": 1, "uname": "secret_creator_name", "message": "下期想看什么整活？", "is_sub": False},
                        {"rpid": 2, "uname": "热心观众A", "message": "想看下期整活", "is_sub": False},
                    ],
                }
            ],
        },
    )
    monkeypatch.setattr(analytics, "fetch_trending_radar", lambda limit=5: {})

    report = analytics.generate_report(save_snapshot=True)
    assert report["account"]["uid"] == "<REDACTED>"
    assert report["account"]["mid"] == "<REDACTED>"
    assert report["account"]["uname"] == "<REDACTED>"

    # Only the non-creator viewer comment should generate a viewer_request directive
    viewer_reqs = [d for d in report["optimization_directives"] if d["type"] == "viewer_request"]
    assert len(viewer_reqs) == 1
    assert viewer_reqs[0]["requester"] == "热心观众A"

    # Creator's own comment uname must be redacted in report and saved snapshots
    comments = report["archives"][0]["recent_comments"]
    assert comments[0]["uname"] == "<REDACTED>"
    assert comments[1]["uname"] == "热心观众A"

    json_text = Path(report["snapshot_json"]).read_text(encoding="utf-8")
    md_text = Path(report["snapshot_md"]).read_text(encoding="utf-8")
    assert "99887766" not in json_text
    assert "secret_creator_name" not in json_text
    assert "99887766" not in md_text
    assert "secret_creator_name" not in md_text


def test_submit_archive_neutral_mark_and_21001_fallback() -> None:
    """Verifies native AI declaration neutral_mark on add/v3, disable/override, and two-stage 21001 fallback."""
    # 1. Default ai_declaration=True includes BILIBILI_AI_NEUTRAL_MARK
    mock_session = MagicMock()
    mock_session.post.return_value = _DummyResponse(
        {"code": 0, "message": "0", "data": {"aid": 30001, "bvid": "BV1AiDeclOn"}}
    )
    uploader = BilibiliUploader(
        cookies={"SESSDATA": "sess_ok", "bili_jct": "csrf_ok", "DedeUserID": "10000001"},
        session=mock_session,
    )
    res_on = uploader.submit_archive(
        bili_filename="n261121ai",
        cover_url="https://archive.biliimg.com/bfs/archive/ai.jpg",
        title="测试 AI 原生声明",
        tid=47,
        tags=["动画短片"],
        description="含【借物表】与【AIGC】",
    )
    assert res_on["neutral_mark"] == BILIBILI_AI_NEUTRAL_MARK
    assert mock_session.post.call_args.kwargs["json"]["neutral_mark"] == BILIBILI_AI_NEUTRAL_MARK

    # 2. ai_declaration=False omits neutral_mark
    mock_session.reset_mock()
    mock_session.post.return_value = _DummyResponse(
        {"code": 0, "message": "0", "data": {"aid": 30002, "bvid": "BV1AiDeclOff"}}
    )
    res_off = uploader.submit_archive(
        bili_filename="n261121noai",
        cover_url="https://archive.biliimg.com/bfs/archive/noai.jpg",
        title="测试关闭 AI 声明",
        tid=47,
        ai_declaration=False,
    )
    assert res_off["neutral_mark"] is None
    assert "neutral_mark" not in mock_session.post.call_args.kwargs["json"]

    # 3. Custom neutral_mark overrides default
    mock_session.reset_mock()
    mock_session.post.return_value = _DummyResponse(
        {"code": 0, "message": "0", "data": {"aid": 30003, "bvid": "BV1AiCustom"}}
    )
    res_custom = uploader.submit_archive(
        bili_filename="n261121custom",
        cover_url="https://archive.biliimg.com/bfs/archive/c.jpg",
        title="测试自定义声明",
        tid=47,
        ai_declaration=False,
        neutral_mark="作者声明：自定义AI标识",
    )
    assert res_custom["neutral_mark"] == "作者声明：自定义AI标识"
    assert mock_session.post.call_args.kwargs["json"]["neutral_mark"] == "作者声明：自定义AI标识"

    # 4. First 21001 strips mission/topic keys while PRESERVING neutral_mark
    mock_session.reset_mock()
    mock_session.post.side_effect = [
        _DummyResponse({"code": 21001, "message": "mission rejected"}),
        _DummyResponse({"code": 0, "message": "0", "data": {"aid": 30004, "bvid": "BV1KeepMark"}}),
    ]
    res_keep = uploader.submit_archive(
        bili_filename="n261121fb1",
        cover_url="https://archive.biliimg.com/bfs/archive/fb1.jpg",
        title="测试21001保留声明【B站AI创造公开赛】",
        tid=47,
        tags=["B站AI创造公开赛"],
    )
    assert mock_session.post.call_count == 2
    first_payload = mock_session.post.call_args_list[0].kwargs["json"]
    second_payload = mock_session.post.call_args_list[1].kwargs["json"]
    assert "mission_id" in first_payload and first_payload["neutral_mark"] == BILIBILI_AI_NEUTRAL_MARK
    assert "mission_id" not in second_payload
    assert second_payload["neutral_mark"] == BILIBILI_AI_NEUTRAL_MARK
    assert res_keep["neutral_mark"] == BILIBILI_AI_NEUTRAL_MARK

    # 5. Subsequent 21001 strips neutral_mark only on the second retry
    mock_session.reset_mock()
    mock_session.post.side_effect = [
        _DummyResponse({"code": 21001, "message": "mission rejected"}),
        _DummyResponse({"code": 21001, "message": "neutral_mark rejected"}),
        _DummyResponse({"code": 0, "message": "0", "data": {"aid": 30005, "bvid": "BV1DropMark"}}),
    ]
    res_drop = uploader.submit_archive(
        bili_filename="n261121fb2",
        cover_url="https://archive.biliimg.com/bfs/archive/fb2.jpg",
        title="测试二次21001回退【B站AI创造公开赛】",
        tid=47,
        tags=["B站AI创造公开赛"],
    )
    assert mock_session.post.call_count == 3
    assert mock_session.post.call_args_list[1].kwargs["json"]["neutral_mark"] == BILIBILI_AI_NEUTRAL_MARK
    assert "neutral_mark" not in mock_session.post.call_args_list[2].kwargs["json"]
    assert res_drop["neutral_mark"] is None


def test_edit_archive_neutral_mark_preserve_enable_disable_and_override() -> None:
    """Verifies edit_archive preserves existing neutral_mark, enables, clears, or overrides it."""

    def _make_view(existing_mark: str) -> _DummyResponse:
        return _DummyResponse(
            {
                "code": 0,
                "data": {
                    "archive": {
                        "aid": 445566,
                        "bvid": "BV1EditMark",
                        "title": "标题",
                        "cover": "https://archive.biliimg.com/bfs/archive/c.jpg",
                        "tid": 47,
                        "tag": "AI",
                        "desc": "简介",
                        "copyright": 1,
                        "neutral_mark": existing_mark,
                    },
                    "videos": [{"filename": "fn1", "title": "P1", "desc": "", "cid": 77}],
                },
            }
        )

    mock_session = MagicMock()
    mock_session.post.return_value = _DummyResponse({"code": 0, "data": {"aid": 445566}})
    uploader = BilibiliUploader(
        cookies={"SESSDATA": "s", "bili_jct": "j", "DedeUserID": "10000001"},
        session=mock_session,
    )

    # Preserve existing neutral_mark when ai_declaration=None and neutral_mark=None
    mock_session.get.return_value = _make_view(BILIBILI_AI_NEUTRAL_MARK)
    res_preserve = uploader.edit_archive(aid=445566, description="更新简介")
    assert res_preserve["submitted_payload"]["neutral_mark"] == BILIBILI_AI_NEUTRAL_MARK

    # Explicitly clear when ai_declaration=False
    res_clear = uploader.edit_archive(aid=445566, ai_declaration=False)
    assert res_clear["submitted_payload"]["neutral_mark"] == ""

    # Explicit custom neutral_mark override
    res_override = uploader.edit_archive(aid=445566, neutral_mark="作者声明：自定义AI标注")
    assert res_override["submitted_payload"]["neutral_mark"] == "作者声明：自定义AI标注"

    # Existing empty neutral_mark: default omits key, ai_declaration=True sets BILIBILI_AI_NEUTRAL_MARK
    mock_session.get.return_value = _make_view("")
    res_keep_empty = uploader.edit_archive(aid=445566, description="仅改描述")
    assert "neutral_mark" not in res_keep_empty["submitted_payload"]

    res_enable = uploader.edit_archive(aid=445566, ai_declaration=True)
    assert res_enable["submitted_payload"]["neutral_mark"] == BILIBILI_AI_NEUTRAL_MARK


def test_verify_archive_submission_verified_unverified_and_zero_pii() -> None:
    """Verifies verify_archive_submission handles verified/unverified states, CST formatting, and leaks zero PII."""
    mock_session = MagicMock()
    uploader = BilibiliUploader(
        cookies={"SESSDATA": "s", "bili_jct": "j", "DedeUserID": "99887766"},
        session=mock_session,
    )

    # Case 1: Verified archive (modeled on BV1PyyWzqE38) with injected PII in raw response
    mock_session.get.return_value = _DummyResponse(
        {
            "code": 0,
            "data": {
                "archive": {
                    "aid": 117629999999999,
                    "bvid": "BV1PyyWzqE38",
                    "state": -40,
                    "state_desc": "通过审核，等待发布",
                    "tid": 47,
                    "dtime": 1795516200,
                    "cover": "https://archive.biliimg.com/bfs/archive/verified_cover.jpg",
                    "desc": "双角色剧情短片\n\n【借物表 (Credits)】\n...\n【AIGC 标识】\n符合 GB 45438-2025",
                    "neutral_mark": BILIBILI_AI_NEUTRAL_MARK,
                    "creation_statement": {
                        "id": 101,
                        "content": BILIBILI_AI_NEUTRAL_MARK,
                    },
                    "mid": 99887766,
                    "uid": "99887766",
                    "author": "secret_creator_handle",
                    "uname": "secret_creator_handle",
                }
            },
        }
    )
    verified = uploader.verify_archive_submission(117629999999999)
    assert verified == {
        "code": 0,
        "aid": 117629999999999,
        "bvid": "BV1PyyWzqE38",
        "state": -40,
        "state_desc": "通过审核，等待发布",
        "tid": 47,
        "dtime": 1795516200,
        "dtime_cst": "2026-11-24 18:30:00 CST",
        "neutral_mark": BILIBILI_AI_NEUTRAL_MARK,
        "creation_statement_id": 101,
        "ai_declaration_verified": True,
        "cover_url_present": True,
        "credits_present": True,
        "aigc_present": True,
    }
    serialized = json.dumps(verified, ensure_ascii=False)
    assert "99887766" not in serialized
    assert "secret_creator_handle" not in serialized
    for pii_key in ("mid", "uid", "uname", "author", "dede_userid"):
        assert pii_key not in verified

    # Case 2: Unverified archive (modeled on BV1AWsh6sEQF)
    mock_session.get.return_value = _DummyResponse(
        {
            "code": 0,
            "data": {
                "archive": {
                    "aid": 117628888888888,
                    "bvid": "BV1AWsh6sEQF",
                    "state": 0,
                    "state_desc": "开放浏览",
                    "tid": 20,
                    "dtime": 0,
                    "cover": "",
                    "desc": "普通简介无尾注",
                    "neutral_mark": "",
                    "creation_statement": {"id": -1, "content": ""},
                }
            },
        }
    )
    unverified = uploader.verify_archive_submission(117628888888888)
    assert unverified["code"] == 0
    assert unverified["bvid"] == "BV1AWsh6sEQF"
    assert unverified["state"] == 0
    assert unverified["dtime"] == 0
    assert unverified["dtime_cst"] is None
    assert unverified["neutral_mark"] == ""
    assert unverified["creation_statement_id"] == -1
    assert unverified["ai_declaration_verified"] is False
    assert unverified["cover_url_present"] is False
    assert unverified["credits_present"] is False
    assert unverified["aigc_present"] is False

    # Case 3: Verified via creation_statement.content alone when neutral_mark is empty
    mock_session.get.return_value = _DummyResponse(
        {
            "code": 0,
            "data": {
                "archive": {
                    "aid": 117627777777777,
                    "bvid": "BV1StmtContentOnly",
                    "state": -40,
                    "state_desc": "通过审核，等待发布",
                    "tid": 47,
                    "dtime": 0,
                    "cover": "https://archive.biliimg.com/bfs/archive/ok.jpg",
                    "desc": "【借物表】与【AIGC】",
                    "neutral_mark": "",
                    "creation_statement": {"id": 999, "content": "含人工智能合成"},
                }
            },
        }
    )
    stmt_only = uploader.verify_archive_submission(117627777777777)
    assert stmt_only["ai_declaration_verified"] is True


def test_redact_auth_status_and_publisher_receipt_zero_pii(tmp_path: Path) -> None:
    """Verifies redact_auth_status and MatrixPublisher never write raw mid/uid/uname/dede_userid to receipts."""
    raw_auth = {
        "platform": "bilibili",
        "logged_in": True,
        "mid": "88776655",
        "uid": "88776655",
        "uname": "super_secret_creator",
        "dede_userid": "88776655",
        "level": 6,
    }
    redacted = redact_auth_status(raw_auth)
    assert redacted["mid"] == "<REDACTED>"
    assert redacted["uid"] == "<REDACTED>"
    assert redacted["uname"] == "<REDACTED>"
    assert redacted["dede_userid"] == "<REDACTED>"
    assert redacted["logged_in"] is True
    assert redacted["level"] == 6
    # Must not mutate caller dict
    assert raw_auth["mid"] == "88776655"
    # Falsy PII values stay falsy
    empty_redacted = redact_auth_status({"logged_in": False, "mid": None, "uid": "", "uname": None})
    assert empty_redacted["mid"] is None
    assert empty_redacted["uid"] == ""
    assert empty_redacted["uname"] is None

    vault = AuthVault(vault_dir=tmp_path / "vault")
    vault.save_bilibili_session(
        cookies={"SESSDATA": "s_priv", "bili_jct": "j_priv", "DedeUserID": "88776655"},
        refresh_token="rt_priv",
        profile={"uname": "super_secret_creator", "mid": 88776655, "level": 6},
    )

    projects_dir = tmp_path / "projects"
    proj_dir = projects_dir / "017_privacy_check"
    (proj_dir / "delivery").mkdir(parents=True)
    (proj_dir / "delivery" / "final.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
    (proj_dir / "delivery" / "bilibili.md").write_text(
        "* **主选分区**：动画 -> 短片·手书\n* **视频标题**：隐私脱敏测试\n* **简介**：测试简介\n* **标签**：AI, 动画\n",
        encoding="utf-8",
    )

    mock_session = MagicMock()
    publisher = MatrixPublisher(vault=vault, projects_dir=projects_dir, session=mock_session)
    res = publisher.publish_project(project="017", platforms=["bilibili"], mode="draft")

    bili_manifest = res["platforms"]["bilibili"]
    assert bili_manifest["auth_status"]["mid"] == "<REDACTED>"
    assert bili_manifest["auth_status"]["uname"] == "<REDACTED>"
    assert bili_manifest["advisor_receipt"]["dede_userid"] == "<REDACTED>"
    assert bili_manifest["ai_declaration"] is True
    assert bili_manifest["neutral_mark"] == BILIBILI_AI_NEUTRAL_MARK

    manifest_text = Path(bili_manifest["manifest_path"]).read_text(encoding="utf-8")
    receipt_md_text = Path(bili_manifest["receipt_md_path"]).read_text(encoding="utf-8")
    studio_json = json.loads(Path(bili_manifest["advisor_receipt"]["studio_config_path"]).read_text(encoding="utf-8"))
    assert "88776655" not in manifest_text
    assert "super_secret_creator" not in manifest_text
    assert "88776655" not in receipt_md_text
    assert "super_secret_creator" not in receipt_md_text
    assert "<REDACTED>" in manifest_text
    assert "<REDACTED>" in receipt_md_text
    assert BILIBILI_AI_NEUTRAL_MARK in receipt_md_text
    assert studio_json["streamers"]["隐私脱敏测试"]["neutral_mark"] == BILIBILI_AI_NEUTRAL_MARK


def test_cli_publish_dry_run_remote_schedule_zero_upload_and_ai_declaration_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verifies --dry-run --remote-schedule NEVER uploads and --no-ai-declaration propagates end-to-end."""
    vault_dir = tmp_path / "vault"
    vault = AuthVault(vault_dir=vault_dir)
    vault.save_bilibili_session(
        cookies={"SESSDATA": "s_live", "bili_jct": "j_live", "DedeUserID": "55443322"},
        refresh_token="rt_live",
        profile={"uname": "private_owner", "mid": 55443322, "level": 6},
    )

    projects_dir = tmp_path / "projects"
    proj_dir = projects_dir / "018_dry_run_safety"
    (proj_dir / "delivery").mkdir(parents=True)
    (proj_dir / "delivery" / "dryrun_final.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
    (proj_dir / "delivery" / "bilibili.md").write_text(
        "* **主选分区**：动画 -> 短片·手书\n* **视频标题**：干跑防误传测试\n* **简介**：简介内容\n* **标签**：测试\n",
        encoding="utf-8",
    )

    upload_spy = MagicMock(side_effect=AssertionError("upload_to_bilibili_api must NEVER run under --dry-run"))
    monkeypatch.setattr(BilibiliUploader, "upload_to_bilibili_api", upload_spy)
    monkeypatch.setattr(cli, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr("core.auth_vault.DEFAULT_VAULT_DIR", vault_dir)

    # 1. CLI --dry-run --remote-schedule in schedule mode must NOT upload, and keeps default ai_declaration=True
    monkeypatch.setattr(
        "sys.argv",
        [
            "cli.py",
            "publish",
            "--project",
            "018",
            "--platforms",
            "bilibili",
            "--mode",
            "schedule",
            "--schedule-at",
            "+6h",
            "--dry-run",
            "--remote-schedule",
            "--execute-upload",
        ],
    )
    assert cli.main() == 0
    assert upload_spy.call_count == 0

    staged_dir = proj_dir / "delivery" / "staged_bilibili"
    manifest_text = (staged_dir / "publish_manifest.json").read_text(encoding="utf-8")
    receipt_md_text = (staged_dir / "advisor_receipt.md").read_text(encoding="utf-8")
    manifest_data = json.loads(manifest_text)
    assert manifest_data["ai_declaration"] is True
    assert manifest_data["neutral_mark"] == BILIBILI_AI_NEUTRAL_MARK
    assert manifest_data["advisor_receipt"]["status"] == "scheduled_in_staging_queue"
    assert manifest_data["advisor_receipt"]["dede_userid"] == "<REDACTED>"
    assert "55443322" not in manifest_text
    assert "private_owner" not in manifest_text
    assert "55443322" not in receipt_md_text
    assert "private_owner" not in receipt_md_text

    # 2. CLI --no-ai-declaration disables neutral_mark in manifest, receipt, and biliup_studio.json
    monkeypatch.setattr(
        "sys.argv",
        [
            "cli.py",
            "publish",
            "--project",
            "018",
            "--platforms",
            "bilibili",
            "--mode",
            "draft",
            "--dry-run",
            "--remote-schedule",
            "--no-ai-declaration",
        ],
    )
    assert cli.main() == 0
    assert upload_spy.call_count == 0

    manifest_off = json.loads((staged_dir / "publish_manifest.json").read_text(encoding="utf-8"))
    studio_off = json.loads((staged_dir / "biliup_studio.json").read_text(encoding="utf-8"))
    assert manifest_off["ai_declaration"] is False
    assert manifest_off["neutral_mark"] is None
    assert manifest_off["advisor_receipt"]["neutral_mark"] is None
    assert "neutral_mark" not in studio_off["streamers"]["干跑防误传测试"]

    # 3. Direct MatrixPublisher.publish_project(execute_upload=False, remote_schedule=True) also never uploads
    mock_session = MagicMock()
    pub = MatrixPublisher(vault=vault, projects_dir=projects_dir, session=mock_session)
    pub.publish_project(
        project="018",
        platforms=["bilibili"],
        mode="schedule",
        schedule_at="+6h",
        execute_upload=False,
        remote_schedule=True,
    )
    assert upload_spy.call_count == 0
    assert mock_session.post.call_count == 0
    assert mock_session.get.call_count == 0


def test_verify_archive_submission_retries_on_transient_rate_limit_and_batch_pacing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies transient retry backoff and inter-request batch pacing in BilibiliUploader."""
    sleeps: List[float] = []
    monkeypatch.setattr("core.publisher.time.sleep", lambda sec: sleeps.append(float(sec)))

    mock_session = MagicMock()
    uploader = BilibiliUploader(
        cookies={"SESSDATA": "s_retry", "bili_jct": "j_retry", "DedeUserID": "77665544"},
        session=mock_session,
    )

    # Case 1: Transient rate-limit (-509) + empty archive (code=0, no archive) -> succeeds on 3rd attempt
    mock_session.get.side_effect = [
        _DummyResponse({"code": -509, "data": {}}),
        _DummyResponse({"code": 0, "data": {}}),
        _DummyResponse(
            {
                "code": 0,
                "data": {
                    "archive": {
                        "aid": 117664521460304,
                        "bvid": "BV1hsyHzrEzW",
                        "state": -40,
                        "state_desc": "通过审核，等待发布",
                        "tid": 47,
                        "dtime": 1795689000,
                        "cover": "https://archive.biliimg.com/bfs/archive/019.jpg",
                        "desc": "赛博法庭\n\n【借物表 (Credits)】\n...\n【AIGC 标识】\n符合 GB 45438-2025",
                        "neutral_mark": BILIBILI_AI_NEUTRAL_MARK,
                        "creation_statement": {"id": 101, "content": BILIBILI_AI_NEUTRAL_MARK},
                        "mid": 77665544,
                        "uname": "secret_user",
                    }
                },
            }
        ),
    ]
    res_retry = uploader.verify_archive_submission(117664521460304, max_retries=3, retry_backoff_sec=0.5)
    assert sleeps == [0.5, 1.0]
    assert res_retry["code"] == 0
    assert res_retry["bvid"] == "BV1hsyHzrEzW"
    assert res_retry["state"] == -40
    assert res_retry["ai_declaration_verified"] is True
    serialized_retry = json.dumps(res_retry, ensure_ascii=False)
    assert "77665544" not in serialized_retry
    assert "secret_user" not in serialized_retry

    # Case 2: Repeated ConnectionError -> returns sanitized dict without leaking credentials
    sleeps.clear()
    mock_session.get.side_effect = requests.ConnectionError("upstream reset for s_retry")
    res_fail = uploader.verify_archive_submission(117664521460304, max_retries=2, retry_backoff_sec=0.1)
    assert sleeps == [0.1]
    assert res_fail["code"] == -1
    assert res_fail["state"] is None
    assert res_fail["ai_declaration_verified"] is False
    assert "s_retry" not in json.dumps(res_fail, ensure_ascii=False)

    # Case 3: verify_archives_batch paces consecutive requests once and preserves order
    sleeps.clear()
    mock_session.get.side_effect = [
        _DummyResponse(
            {
                "code": 0,
                "data": {
                    "archive": {
                        "aid": 1001,
                        "bvid": "BV1Batch0001",
                        "state": 0,
                        "state_desc": "开放浏览",
                        "tid": 47,
                        "neutral_mark": BILIBILI_AI_NEUTRAL_MARK,
                    }
                },
            }
        ),
        _DummyResponse(
            {
                "code": 0,
                "data": {
                    "archive": {
                        "aid": 1002,
                        "bvid": "BV1Batch0002",
                        "state": -40,
                        "state_desc": "通过审核，等待发布",
                        "tid": 47,
                        "neutral_mark": BILIBILI_AI_NEUTRAL_MARK,
                    }
                },
            }
        ),
    ]
    batch_res = uploader.verify_archives_batch([1001, 1002], pause_sec=0.5, max_retries=1)
    assert [r["aid"] for r in batch_res] == [1001, 1002]
    assert [r["bvid"] for r in batch_res] == ["BV1Batch0001", "BV1Batch0002"]
    assert sleeps == [0.5]
