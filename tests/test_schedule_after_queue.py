"""Mock the transport beneath the real archive submitter; every HTTP request stays local."""

import argparse
import importlib.util
import io
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import requests
from PIL import Image

from core.publisher import BILIBILI_AI_NEUTRAL_MARK

SOURCE = Path(__file__).resolve().parents[1] / ".agents/skills/bilibili-viral-studio/scripts/schedule_after_queue.py"
spec = importlib.util.spec_from_file_location("schedule_after_queue", SOURCE)
assert spec is not None and spec.loader is not None
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def response(body, status=200):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(body).encode()
    return result


@pytest.fixture
def studio(tmp_path, monkeypatch):
    project = tmp_path / "001_test"
    path = project / "delivery/bilibili_schedule_receipt.json"
    path.parent.mkdir(parents=True)
    pub = MagicMock()
    pub.projects_dir = tmp_path
    pub.resolve_project_dir.return_value = project
    pub.vault.load_bilibili_cookies.return_value = {"SESSDATA": "test", "bili_jct": "test"}
    meta = {"title": "测试稿", "tid": 231, "tags": ["教程"], "description": "非商业测试"}
    pub.discover_metadata.return_value = meta
    rows: list[dict[str, Any]] = []
    wire = MagicMock()
    inventory = MagicMock(side_effect=lambda uploader: rows.copy())
    monkeypatch.setattr(guard, "inventory", inventory)
    monkeypatch.setattr(guard, "check_gate", lambda *_: None)
    monkeypatch.setattr(guard.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        guard, "verify", lambda up, aid, bvid, *args: dict(status="verified", title_verified=True, aid=aid, bvid=bvid)
    )
    monkeypatch.setattr(requests.Session, "send", lambda self, req, **kwargs: wire(req))
    # The core submitter normally performs a 21001 retry (eventually dropping the AI declaration).
    # Exercise that real code and count requests at the transport boundary.
    when = "2099-12-10T18:30:00+08:00"

    def run(*, submit=True, retry=False, after_accept_error=False, bad_header=False):
        with guard.GuardedSession() as session:
            up = guard.BilibiliUploader(vault=pub.vault, session=session)
            if bad_header:
                up._web_headers = lambda: {"Invalid Header": "invalid\nheader"}

            def publish(**kwargs):
                assert kwargs["mode"] == "schedule" and kwargs["ai_declaration"] is True
                stamp = int(guard.dt.datetime.fromisoformat(kwargs["schedule_at"]).timestamp())
                up.submit_archive("test", "cover", dtime=stamp, **meta)
                if after_accept_error:
                    raise OSError("simulated staging write failure")

            pub.publish_project.side_effect = publish
            args = argparse.Namespace(
                project=project.name,
                bvid=None,
                schedule_at=when,
                noncommercial=False,
                submit=submit,
                retry_rejected=retry,
            )
            guard.run(args, pub, session)

    return run, wire, path, rows, inventory


ARCHIVE = {"title": "测试稿", "aid": 9, "bvid": "BV1test00000", "state": -40, "dtime": 0}


def test_timeout_then_indexed_is_reconciled_without_reposting(studio):
    run, wire, path, _, inventory = studio

    def timeout(req):
        assert json.loads(path.read_text())["status"] == "pending"
        raise requests.Timeout()

    wire.side_effect = timeout
    inventory.side_effect = [[], [], [], [ARCHIVE]]
    run()
    result = json.loads(path.read_text())
    assert (result["status"], result["bvid"]) == ("verified", ARCHIVE["bvid"])
    assert wire.call_count == 1


def test_unindexed_timeout_stays_locked_on_later_invocations(studio):
    run, wire, path, *_ = studio
    wire.side_effect = requests.Timeout("synthetic secret URL")
    with pytest.raises(guard.GuardError, match="只读"):
        run()
    pending = json.loads(path.read_text())
    assert pending["status"] == "pending" and pending["reason"] == "等待平台回包超时"
    for retry in (False, True):
        with pytest.raises(guard.GuardError, match="只读"):
            run(retry=retry)
    assert wire.call_count == 1 and "secret" not in path.read_text()


def test_rejected_21001_durable_single_attempt_then_explicit_repaired_retry(studio):
    run, wire, path, _, inventory = studio
    wire.side_effect = [
        response({"code": 21001, "message": "参数错误 @untrusted-name https://invalid.test/?secret=private"}),
        response({"code": 0, "data": {"aid": ARCHIVE["aid"], "bvid": ARCHIVE["bvid"]}}),
    ]
    with pytest.raises(guard.AddRejected, match="21001"):
        run()
    rejection = json.loads(path.read_text())
    assert (rejection["status"], rejection["code"], rejection["reason"]) == (
        "rejected",
        21001,
        "投稿参数未通过平台校验",
    )
    assert "untrusted" not in path.read_text() and "secret" not in path.read_text()
    run(submit=False)
    with pytest.raises(guard.GuardError, match="retry-rejected"):
        run()
    assert wire.call_count == 1
    calls = inventory.call_count
    run(retry=True, after_accept_error=True)
    assert inventory.call_count == calls + 2 and wire.call_count == 2
    verified = json.loads(path.read_text())
    assert verified["status"] == "verified" and verified["code"] == 0 and verified["last_rejection"]["code"] == 21001
    for call in wire.call_args_list:
        payload = json.loads(call.args[0].body)
        assert payload["neutral_mark"] == BILIBILI_AI_NEUTRAL_MARK and payload["dtime"] > 0
        assert payload["open_elec"] == payload["no_reprint"] == 0


def test_invalid_local_headers_never_record_a_submission(studio):
    run, wire, path, *_ = studio
    with pytest.raises(guard.GuardError, match="未进入发送"):
        run(bad_header=True)
    assert not path.exists() and wire.call_count == 0


@pytest.mark.parametrize("valid", [True, False])
def test_current_submission_options_preserve_legacy_partition_and_single_post(studio, valid):
    run, wire, receipt, *_ = studio
    project = receipt.parent.parent
    Image.new("RGB", (40, 30), "blue").save(receipt.parent / "cover43.jpg")
    (project / "brief.json").write_text(
        json.dumps({"bilibili_web_category": "科技数码", "deliverables": {"cover_4x3": "delivery/cover43.jpg"}})
    )
    sent = []

    def transport(req):
        if req.method == "GET" and "/human/type2/list" in req.url:
            return response({"code": 0, "data": {"type_list": [{"id": 1012, "name": "科技数码"}]}})
        if req.method == "GET" and "/archive/pre?" in req.url:
            return response(
                {
                    "code": 0,
                    "data": {
                        "neutral_mark": {"mark_list": [{"id": 1, "content": "含AI生成内容" if valid else "其它声明"}]}
                    },
                }
            )
        if req.method == "POST" and "/cover/up" in req.url:
            return response({"code": 0, "data": {"url": "https://i0.hdslb.com/bfs/archive/example-43.jpg"}})
        assert req.method == "POST" and "/add/v3?" in req.url
        sent.append(json.loads(req.body))
        return response({"code": 0, "data": {"aid": ARCHIVE["aid"], "bvid": ARCHIVE["bvid"]}})

    wire.side_effect = transport
    if not valid:
        with pytest.raises(guard.GuardError, match="创作声明菜单"):
            run()
        assert all(call.args[0].method == "GET" for call in wire.call_args_list) and not receipt.exists()
        return
    run(submit=False)
    assert all(call.args[0].method == "GET" for call in wire.call_args_list)
    run()
    assert len(sent) == 1
    q = sent[0]
    assert (q["tid"], q["human_type2"], q["creation_statement"]) == (231, 1012, {"id": 1})
    assert q["cover43"].endswith("example-43.jpg") and q["cover"] == "cover"
    assert q["open_elec"] == q["no_reprint"] == 0 and q["neutral_mark"] == BILIBILI_AI_NEUTRAL_MARK
    assert json.loads(receipt.read_text())["submitted_native"]["human_type2"] == 1012


def test_412_requires_official_creator_center_and_allows_only_readback(studio, capsys):
    run, wire, path, rows, _ = studio
    wire.return_value = response({"code": -412, "message": "private message"}, status=412)
    with pytest.raises(guard.AddRejected, match="官方创作中心"):
        run()
    saved = json.loads(path.read_text())
    assert (saved["status"], saved["http_status"], saved["code"]) == ("rejected", 412, -412)
    assert saved["reason"] == guard.OFFICIAL_REVIEW
    run(submit=False)
    assert "官方创作中心" in capsys.readouterr().out
    with pytest.raises(guard.GuardError, match="官方创作中心"):
        run(retry=True)
    rows.append(ARCHIVE)
    run()
    assert json.loads(path.read_text())["status"] == "verified" and wire.call_count == 1


def test_retry_checks_for_archive_again_before_post(studio):
    run, wire, path, _, inventory = studio
    wire.return_value = response({"code": 21001, "message": "参数错误"})
    with pytest.raises(guard.AddRejected):
        run()
    inventory.side_effect = [[], [ARCHIVE]]
    with pytest.raises(guard.GuardError, match="已有同题稿"):
        run(retry=True)
    assert wire.call_count == 1 and json.loads(path.read_text())["status"] == "rejected"


@pytest.mark.parametrize(
    ("http", "body"),
    [
        (502, {"code": 21001}),
        (200, {"code": -500}),
        (200, {"code": 7, "message": "稿件已存在"}),
        (200, {"code": 21001, "data": {"aid": 9}}),
        (200, {"message": "empty"}),
        (200, {"code": 0, "data": {}}),
    ],
)
def test_inconclusive_envelopes_stay_pending(http, body):
    assert guard.add_outcome(response(body, http))["status"] == "pending"


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({}, True),
        ({"human_type2": {"id": 1010, "name": "生活"}}, False),
        ({"human_type2": {"id": 999, "name": "知识"}}, False),
        ({"creation_statement": {"id": 1, "content": ""}}, False),
        ({"desc": "被改写的简介 【借物表】 【AIGC 标识】"}, False),
        ({"no_reprint": 1}, False),
    ],
)
def test_native_form_verified_against_live_fields(tmp_path, monkeypatch, change, expected):
    (tmp_path / "brief.json").write_text(json.dumps({"bilibili_web_category": "知识"}))
    up = guard.BilibiliUploader(cookies={"SESSDATA": "fake", "bili_jct": "fake"})
    meta = {"tid": 231, "title": "示例", "description": "原文\n\n【借物表】\n【AIGC 标识】", "tags": ["A", "B"]}
    arc = dict(
        ARCHIVE,
        title="示例",
        tid=47,
        human_type2={"id": 1010, "name": "知识"},
        state_desc="通过审核，等待发布",
        desc="原文 【借物表】  【AIGC 标识】",
        tag="B,A",
        dtime=100,
        no_reprint=0,
        cover="cover",
        cover43="cover43",
        creation_statement={"id": 1, "content": "含AI生成内容"},
        neutral_mark="含AI生成内容",
    )
    arc.update(change)
    monkeypatch.setattr(
        up, "get_archive_view", lambda _: {"code": 0, "data": {"archive": arc, "arc_elec": {"state": 0}}}
    )
    monkeypatch.setattr(
        guard, "compare_web_cover", lambda *args: {"cover43_verified" if len(args) == 4 else "cover_verified": True}
    )
    form = {**ARCHIVE, "http": 200, "code": 0, "category": 47, "human_type2": 1010, "requested_dtime": 100}
    result = guard.verify(up, ARCHIVE["aid"], ARCHIVE["bvid"], meta, 100, True, form, tmp_path)
    assert (result["status"] == "verified") is expected
    assert result["tid"] == 47 and result["legacy_tid_expected"] == 231


def test_web_cover_recompression_and_wrong_image(tmp_path, monkeypatch):
    (tmp_path / "delivery").mkdir()
    (tmp_path / "output").mkdir()
    cover = tmp_path / "delivery/cover.jpg"
    source = Image.new("RGB", (320, 180), "white")
    source.save(cover)
    (tmp_path / "output/quality_check.json").write_text(json.dumps({"cover_path": str(cover)}))
    for image, expected in [(source, True), (Image.new("RGB", source.size, "black"), False)]:
        output = io.BytesIO()
        image.save(output, "JPEG", quality=78)
        res = requests.Response()
        res.status_code = 200
        res._content = output.getvalue()
        monkeypatch.setattr(guard.requests, "get", lambda *args, **kwargs: res)
        result = guard.compare_web_cover("https://i0.hdslb.com/bfs/archive/fake.jpg", tmp_path, False)
        assert result["cover_verified"] is expected
