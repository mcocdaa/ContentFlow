"""Check a creator's full queue, submit one scheduled archive, or reconcile its receipt."""

import argparse
import datetime as dt
import fcntl
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlsplit

import requests
from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from core.analytics import BILIBILI_MEMBER_ARCHIVES_URL
from core.publisher import (
    BILIBILI_ADD_V3_URL,
    BILIBILI_MIN_SCHEDULE_LEAD_SECONDS,
    BILIBILI_PREUPLOAD_URL,
    BilibiliUploader,
    MatrixPublisher,
)

BJ = dt.timezone(dt.timedelta(hours=8))
OFFICIAL_REVIEW = "平台返回 -412。请由账号持有人在 B 站官方创作中心查看稿件管理及页面提示，本脚本仅支持回查。"


class GuardError(Exception):
    """A safe, publicly printable reason for halting."""


class ReadUnavailable(Exception):
    """A transient read failure or creator-center indexing delay."""


class AddRejected(GuardError):
    """The platform returned a definitive application rejection for this POST."""


def add_outcome(response):
    """Return only platform identifiers, the numeric code, and fixed, privacy-safe reasons."""
    status = response.status_code
    outcome = {"status": "pending", "http_status": status, "reason": "平台回包未能确认受理结果"}
    try:
        body = response.json()
    except ValueError:
        return outcome
    if not isinstance(body, dict) or type(body.get("code")) is not int:
        return outcome
    code = outcome["code"] = body["code"]
    if status < 200 or 300 <= status < 400 or status == 408 or status >= 500:
        return outcome
    data = body.get("data")
    if isinstance(data, dict):
        aid = data.get("aid")
        if isinstance(aid, (str, int)) and re.fullmatch(r"[1-9][0-9]{0,18}", str(aid)):
            outcome["aid"] = int(aid)
        if isinstance(data.get("bvid"), str) and re.fullmatch(r"BV[0-9A-Za-z]{10}", data["bvid"]):
            outcome["bvid"] = data["bvid"]
    if code == 0:
        if 200 <= status < 300 and "aid" in outcome and "bvid" in outcome:
            outcome.update(status="accepted", reason="平台已返回稿号")
        return outcome
    if "aid" in outcome or "bvid" in outcome:
        outcome["reason"] = "非零返回码同时附有稿号，需要核对原稿"
        return outcome
    if code == -412:
        return dict(outcome, status="rejected", reason=OFFICIAL_REVIEW)
    message = body.get("message") or body.get("msg")
    message = message if isinstance(message, str) else ""
    if code in {-500, -502, -503, -504} or re.search(
        r"重复|已存在|已提交|已投稿|已投过|超时|服务异常|duplicate|timeout", message, re.I
    ):
        outcome["reason"] = "平台提示可能重复提交或服务未确定结果"
        return outcome
    labels = (
        (r"定时|发布时间|排期", "定时设置未通过平台校验"),
        (r"标题|简介|标签|分区|封面", "稿件字段未通过平台校验"),
        (r"参数|格式|parameter|invalid", "投稿参数未通过平台校验"),
        (r"频繁|频率|稍后再试", "平台限制本次投稿频率"),
        (r"登录|登陆|权限|认证|csrf", "登录或权限校验未通过"),
    )
    reason = next((label for pattern, label in labels if re.search(pattern, message, re.I)), "平台明确拒绝本次投稿")
    return dict(outcome, status="rejected", reason=reason)


def require(condition, message):
    if not condition:
        raise GuardError(message)


def read_only(operation):
    for attempt in range(3):
        try:
            return operation()
        except (requests.RequestException, ReadUnavailable, ValueError):
            if attempt == 2:
                raise GuardError("创作中心只读查询未能确认。稍后用同一参数回查。") from None
            time.sleep(2**attempt)


def checked(response):
    if response.get("code") != 0 or not isinstance(response.get("data"), dict):
        raise ReadUnavailable()
    return response["data"]


def inventory(up):
    """Keep only submission fields. Check platform totals and unique IDs across every page."""

    def fetch():
        rows = {}
        total = None
        page = 1
        while True:
            result = up.session.get(
                BILIBILI_MEMBER_ARCHIVES_URL,
                params={"status": "is_pubing,pubed,not_pubed", "ps": 50, "pn": page},
                cookies=up.cookies,
                headers=up._web_headers(),
                timeout=20,
            )
            result.raise_for_status()
            data = checked(result.json())
            counts = data.get("class") or {}
            batch = data.get("arc_audits")
            if not isinstance(batch, list) or not {"pubed", "is_pubing", "not_pubed"} <= counts.keys():
                raise ReadUnavailable()
            current = sum(int(counts[k]) for k in ("pubed", "is_pubing", "not_pubed"))
            if total is not None and current != total:
                raise ReadUnavailable()
            total = current
            for item in batch:
                arc = item.get("Archive") or {}
                aid = int(arc.get("aid") or 0)
                if not aid or aid in rows or not arc.get("title"):
                    raise ReadUnavailable()
                rows[aid] = {
                    "aid": aid,
                    "bvid": item.get("bvid") or arc.get("bvid"),
                    "title": arc["title"],
                    "dtime": arc.get("dtime"),
                    "state": arc.get("state"),
                }
            if len(rows) == total:
                return list(rows.values())
            if not batch or len(rows) > total:
                raise ReadUnavailable()
            page += 1

    return read_only(fetch)


def check_slot(rows, up, stamp):
    require(stamp >= time.time() + BILIBILI_MIN_SCHEDULE_LEAD_SECONDS, "目标过近或已经过去。请指定新的北京时间。")
    tail = 0
    for arc in rows:
        scheduled = int(arc.get("dtime") or 0)
        if int(arc["state"]) < 0 and not scheduled:
            details = read_only(lambda: checked(up.get_archive_view(arc["aid"]))).get("archive") or {}
            require("dtime" in details or int(arc["state"]) not in (-40, -30, -1), "有待发或审核稿的档期未查明。")
            scheduled = int(details.get("dtime") or 0)
            require(scheduled > 0 or int(arc["state"]) != -40, "过审待发稿缺少排期。")
        tail = max(tail, scheduled)
    require(
        dt.datetime.fromtimestamp(stamp, BJ).date() > dt.datetime.fromtimestamp(tail, BJ).date(),
        "目标日期未晚于队尾北京时间日期。",
    )
    return dt.datetime.fromtimestamp(tail, BJ).isoformat() if tail else None


def save(path, data):
    """Atomic durable receipt, including the pending marker before add/v3."""
    temp = path.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)
    parent = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)


def optional_json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def title_hash(title):
    return hashlib.sha256(title.encode("utf-8")).hexdigest()


def match_project(rows, titles, aids, bvids):
    found = [r for r in rows if title_hash(r["title"]) in titles or r["aid"] in aids or r["bvid"] in bvids]
    require(len(found) <= 1 and len(aids) <= 1 and len(bvids) <= 1, "本地标识或同标题稿件不唯一。")
    if not found:
        return None
    row = found[0]
    require(
        (not aids or row["aid"] in aids) and (not bvids or row["bvid"] in bvids), "标题与已知 BVID/AID 指向不同稿件。"
    )
    return row


def check_unlisted_pending(project, rows, titles, stamp):
    known = {row["bvid"] for row in rows if row["bvid"]}
    target_day = dt.datetime.fromtimestamp(stamp, BJ).date()
    for path in project.parent.glob("*/delivery/bilibili_schedule_receipt.json"):
        record = optional_json(path)
        if record.get("status") not in {"pending", "accepted"} or record.get("bvid") in known:
            continue
        when = record.get("requested_dtime")
        require(record.get("title_sha256") not in titles, "另一项目有相同标题的待核实投稿。")
        require(when and dt.datetime.fromtimestamp(when, BJ).date() < target_day, "另有未确认排期占用队尾。")


def check_gate(pub, project, meta):
    report = optional_json(project / "output/quality_check.json")
    require(
        report.get("passed") is True and report.get("total_score", 0) >= 90 and report.get("blockers") == [],
        "质量报告须通过 90 分且没有阻断。",
    )
    files = [Path(report[k]).resolve() for k in ("video_path", "cover_path")]
    require(
        all(p.is_file() for p in files) and files[1].parent == project / "delivery", "门禁媒体文件缺失或封面位置错误。"
    )
    require(
        files[0] == pub.discover_video(project) and files[1] == pub.discover_or_extract_cover(project),
        "投稿器选中的媒体与门禁报告不符。",
    )
    reviewed = dt.datetime.fromisoformat(report["evaluated_at"]).timestamp()
    require(max(p.stat().st_mtime for p in files) <= reviewed, "媒体在门禁检查后改动。")
    desc = meta["description"]
    require(
        "【借物表" in desc and "【AIGC" in desc and "GB 45438-2025" in desc and len(desc) <= 2000,
        "实际简介的借物表或 AI 声明不完整，或简介超过 2000 字。",
    )
    require(meta["tags"] and len(meta["tags"]) <= 10 and meta["pinned_comment"], "请核对标签和置顶评论。")
    require(not re.search(r"@[\w-]+", " ".join([desc, *meta["tags"], meta["pinned_comment"]])), "文案内含账号提及。")


def submission_options(up, project):
    """Resolve the official form's current business options before uploading any media."""
    brief = optional_json(project / "brief.json")
    name = brief.get("bilibili_web_category")
    if not name:
        return {}, None

    def config(endpoint, params=None):
        r = up.session.get(
            f"https://member.bilibili.com/x/vupre/web/archive/{endpoint}",
            params=params,
            cookies=up.cookies,
            headers=up._web_headers(),
            timeout=15,
        )
        r.raise_for_status()
        return checked(r.json())

    categories = read_only(lambda: config("human/type2/list")).get("type_list") or []
    matches = [c.get("id") for c in categories if isinstance(c, dict) and c.get("name") == name]
    require(len(matches) == 1 and type(matches[0]) is int and matches[0] > 0, "官方人选分区列表未找到唯一的预期分类。")
    options = (read_only(lambda: config("pre", {"lang": "ch"})).get("neutral_mark") or {}).get("mark_list") or []
    require(
        any(isinstance(s, dict) and s.get("id") == 1 and s.get("content") == "含AI生成内容" for s in options),
        "官方创作声明菜单未确认含 AI 生成内容的选项。",
    )
    file = (project / (brief.get("deliverables") or {}).get("cover_4x3", "")).resolve()
    require(file.is_file() and file.parent == project / "delivery", "制作稿缺少已交付的 4:3 封面。")
    with Image.open(file) as cover:
        require(cover.width * 3 == cover.height * 4, "独立封面尺寸不符合 4:3。")
    return {"human_type2": matches[0], "creation_statement": {"id": 1}}, file


class GuardedSession(requests.Session):
    before_add = None
    record_add = None
    attempted = False

    def request(self, method, url, **kwargs):
        mutation = method.upper() not in ("GET", "HEAD") or url == BILIBILI_PREUPLOAD_URL
        if mutation:
            require(self.before_add is not None, "只读模式拦截了写请求。")
            kwargs["allow_redirects"] = False
        if url == BILIBILI_ADD_V3_URL:
            require(
                method.upper() == "POST" and self.record_add is not None and not self.attempted,
                "该次提交只允许一个 POST。",
            )
            self.before_add(kwargs["json"])
        try:
            result = super().request(method, url, **kwargs)
        except requests.RequestException:
            if url == BILIBILI_ADD_V3_URL and not self.attempted:
                raise GuardError("稿件请求未进入发送步骤，请检查请求配置。") from None
            if mutation:
                raise GuardError("传输结果未确认。请只读回查。") from None
            raise
        require(not (mutation and result.is_redirect), "写请求被重定向，已暂停。")
        return result

    def send(self, request, **kwargs):
        if request.url.partition("?")[0] != BILIBILI_ADD_V3_URL:
            return super().send(request, **kwargs)
        # JSON, headers and cookies have been prepared. Persist before handing the POST to the adapter.
        require(request.method == "POST" and self.record_add is not None and not self.attempted, "禁止重复投稿。")
        self.record_add({"status": "pending", "reason": "已准备发送，尚无有效平台回包"})
        self.attempted = True
        try:
            response = super().send(request, **kwargs)
        except requests.RequestException as exc:
            reason = "等待平台回包超时" if isinstance(exc, requests.Timeout) else "连接中断，未取得有效平台回包"
            self.record_add({"status": "pending", "reason": reason})
            raise GuardError(reason) from None
        outcome = add_outcome(response)
        self.record_add(outcome)
        if outcome["status"] == "rejected":
            raise AddRejected(f"平台拒绝投稿（{outcome['code']}）：{outcome['reason']}。") from None
        if outcome["status"] == "pending":
            raise GuardError(outcome["reason"])
        return response


def compare_web_cover(url, project, keep_file, alternate=False):
    """Fetch the public CDN without credentials and compare each cover in its own aspect ratio."""
    path = urlsplit(url if not url.startswith("//") else "https:" + url)
    require(
        path.scheme in {"https", "http"} and re.fullmatch(r"(?:[\w-]+\.)+(?:biliimg|hdslb)\.com", path.netloc),
        "线上封面来源无法核实。",
    )
    if alternate:
        name = (optional_json(project / "brief.json").get("deliverables") or {}).get("cover_4x3", "")
        local = (project / name).resolve()
    else:
        local = Path(optional_json(project / "output/quality_check.json").get("cover_path", "")).resolve()
    require(local.is_file() and local.parent == project / "delivery", "本地交付封面无法核实。")
    response = requests.get(f"https://{path.netloc}{path.path}", timeout=15, allow_redirects=False)
    require(response.status_code == 200 and 0 < len(response.content) <= 10_000_000, "线上封面获取失败。")
    with Image.open(io.BytesIO(response.content)) as remote, Image.open(local) as source:
        require(remote.format == "JPEG", "线上封面文件格式待人工确认。")
        rw, rh = remote.size
        sw, sh = source.size
        same_ratio = abs(rw / rh - sw / sh) < 0.01
        size = (288 if alternate else 384, 216)
        a, b = (im.convert("RGB").resize(size, Image.Resampling.LANCZOS) for im in (remote, source))
        mae = sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3
    if keep_file:
        out = project / "output/creator-reconciliation" / ("online-cover-4x3.jpg" if alternate else "online-cover.jpg")
        out.parent.mkdir(parents=True, exist_ok=True)
        temp = out.with_suffix(".tmp")
        temp.write_bytes(response.content)
        temp.replace(out)
    key = "cover43" if alternate else "cover"
    return {
        f"{key}_dimensions": [rw, rh],
        f"{key}_sha256": hashlib.sha256(response.content).hexdigest(),
        f"local_{key}_sha256": hashlib.sha256(local.read_bytes()).hexdigest(),
        f"{key}_rgb_mae_255": round(mae, 4),
        f"{key}_verified": same_ratio and mae <= 6,
    }


def verify(up, aid, bvid, meta, stamp, noncommercial, web_form=None, project=None, keep_cover=False):
    v = up.verify_archive_submission(aid)
    if v["code"] != 0 or not v.get("bvid"):
        raise ReadUnavailable()
    data = checked(up.get_archive_view(aid))
    arc = data.get("archive") or {}
    if not arc or arc.get("bvid") != v["bvid"]:
        raise ReadUnavailable()
    require(not bvid or v["bvid"] == bvid, "详情回读的 BVID 与预期不符。")
    record = {
        k: v[k]
        for k in (
            "aid",
            "bvid",
            "state",
            "tid",
            "dtime",
            "dtime_cst",
            "creation_statement_id",
            "cover_url_present",
            "ai_declaration_verified",
            "credits_present",
            "aigc_present",
        )
    }
    record.update(
        verified_at=dt.datetime.now(BJ).isoformat(timespec="seconds"),
        requested_dtime=stamp,
        title_verified=arc.get("title") == meta["title"],
        description_verified=" ".join((arc.get("desc") or "").split()) == " ".join(meta["description"].split()),
        tags_verified=sorted((arc.get("tag") or "").split(",")) == sorted(meta["tags"]),
        open_elec=(data.get("arc_elec") or {}).get("state"),
        no_reprint=arc.get("no_reprint"),
        schedule_verified=v["dtime"] == stamp if stamp else None,
    )
    checks = [
        record[k]
        for k in (
            "title_verified",
            "description_verified",
            "tags_verified",
            "cover_url_present",
            "ai_declaration_verified",
            "credits_present",
            "aigc_present",
        )
    ]
    record["legacy_tid_expected"] = meta["tid"]
    if web_form:
        require(
            web_form.get("aid") == v["aid"]
            and (
                web_form.get("bvid") == v["bvid"]
                or (web_form.get("source") == "guarded_native" and not web_form.get("bvid"))
            ),
            "受理稿号与回读不符。",
        )
        category = arc.get("human_type2")
        category = category if isinstance(category, dict) else {}
        expected = optional_json(project / "brief.json").get("bilibili_web_category")
        statement = arc.get("creation_statement") or data.get("creation_statement") or {}
        # Store only known public platform labels, never a free-form user statement.
        label = statement.get("content") if isinstance(statement, dict) else None
        allowed_labels = {"含AI生成内容", "作者声明：该视频使用人工智能合成技术"}
        record.update(
            submission_channel=web_form.get("source", "official_web"),
            submission_code=web_form.get("code"),
            submission_http=web_form.get("http"),
            state_desc=v["state_desc"],
            creation_statement_content=label if label in allowed_labels else None,
            human_type2_id=category.get("id"),
            human_type2_name=category.get("name"),
            web_category_expected=expected,
            legacy_tid_submitted=web_form.get("category"),
            cover43_url_present=bool(arc.get("cover43")),
        )
        record["web_statement_verified"] = (v["creation_statement_id"] == 1 and label == "含AI生成内容") or (
            v["creation_statement_id"] == 101 and v["ai_declaration_verified"]
        )
        record["category_verified"] = bool(
            expected
            and category.get("name") == expected
            and type(category.get("id")) is int
            and category["id"] == web_form.get("human_type2")
            and type(v["tid"]) is int
            and v["tid"] == web_form.get("category")
        )
        record.update(compare_web_cover(arc.get("cover") or "", project, keep_cover))
        if arc.get("cover43"):
            record.update(compare_web_cover(arc["cover43"], project, keep_cover, True))
        checks.extend(
            [
                record["cover_verified"],
                record.get("cover43_verified", False),
                record["web_statement_verified"],
                web_form.get("requested_dtime") == stamp and bool(stamp),
            ]
        )
    else:
        record["category_verified"] = v["tid"] == meta["tid"]
    checks.append(record["category_verified"])
    if stamp:
        checks.append(record["schedule_verified"])
    if noncommercial:
        checks.append(str(record["open_elec"]) == "0" and str(record["no_reprint"]) == "0")
    record["status"] = "verified" if all(checks) else "readback_mismatch"
    return record


def run(args, pub, session):
    if args.project.isdigit():
        matches = list(pub.projects_dir.glob(f"{int(args.project):03d}_*"))
        require(len(matches) == 1, "数字编号对应多个或零个目录。请指定完整项目名。")
    project = pub.resolve_project_dir(args.project).resolve()
    require(project.parent == pub.projects_dir and project.is_dir(), "没有找到唯一的项目目录。")
    meta = pub.discover_metadata(project)
    up = BilibiliUploader(vault=pub.vault, session=session)
    require(up.is_authenticated, "请先登录可访问创作中心的账号。")
    delivery = project / "delivery"
    receipt_path = delivery / "bilibili_schedule_receipt.json"
    prior = optional_json(receipt_path)
    web = optional_json(project / "output/creator-reconciliation/official-form.json")
    web_form = web if web.get("status") == "accepted" and web.get("code") == 0 and web.get("http") == 200 else {}
    record_readback = getattr(args, "record_readback", False)
    require(
        not record_readback or (args.bvid and not args.submit), "--record-readback 需指定已知 --bvid，并且仅允许回读。"
    )
    rejected = prior.get("status") == "rejected" and type(prior.get("code")) is int and prior["code"] != 0
    staged = optional_json(delivery / "staged_bilibili/publish_manifest.json").get("advisor_receipt", {})
    records = [prior, staged, web_form, optional_json(delivery / "bilibili_verify_receipt.json")]
    episodes = optional_json(ROOT / "library/creative_ledger.json").get("episodes", [])
    records.extend(e for e in episodes if e.get("project_id") == project.name)
    aids = {int(r["aid"]) for r in records if r.get("aid")}
    bvids = {r["bvid"] for r in records if r.get("bvid")}
    if args.bvid:
        bvids.add(args.bvid)
    titles = {title_hash(meta["title"])}
    if prior.get("title_sha256"):
        titles.add(prior["title_sha256"])
    stamp = web_form.get("requested_dtime") or prior.get("requested_dtime")
    if args.schedule_at:
        slot = dt.datetime.fromisoformat(args.schedule_at)
        require(
            slot.utcoffset() == dt.timedelta(hours=8) and not slot.microsecond,
            "排期必须是含 +08:00 的完整北京时间，精确至秒。",
        )
        requested = int(slot.timestamp())
        require(not stamp or stamp == requested or rejected, "指定时刻与本地受理或待核实记录不一致。请先按原时刻回读。")
        stamp = requested
    require(not record_readback or stamp, "保存定时回执需要已确认的目标时刻或 --schedule-at。")
    noncommercial = args.noncommercial or bool(re.search(r"BY[- ]NC|非商[业用]", meta["description"], re.I))
    rows = inventory(up)
    existing = match_project(rows, titles, aids, bvids)

    def read_receipt(aid, bvid=None):
        saved = optional_json(receipt_path)
        proof = web_form
        if not proof and saved.get("submitted_native") and saved.get("status") != "rejected":
            # A timed-out POST may later be identified through the complete account inventory.
            proof = dict(
                saved["submitted_native"],
                aid=aid,
                bvid=bvid,
                source="guarded_native",
                requested_dtime=saved["requested_dtime"],
                code=saved.get("code"),
                http=saved.get("http_status"),
            )
        record = read_only(
            lambda: verify(
                up, int(aid), bvid, meta, stamp, noncommercial, proof, project, args.submit or record_readback
            )
        )
        if saved.get("submitted_native") and not web_form:
            record["submitted_native"] = saved["submitted_native"]
        if saved.get("status") == "rejected":
            record["last_rejection"] = {k: saved[k] for k in ("code", "reason", "http_status") if k in saved}
        else:
            record.update({k: saved[k] for k in ("last_rejection", "code", "http_status") if k in saved})
        record["title_sha256"] = title_hash(meta["title"])
        print(json.dumps(record, ensure_ascii=False), flush=True)
        if (args.submit or record_readback) and record["title_verified"]:
            save(receipt_path, record)
            if record_readback:
                save(delivery / "bilibili_verify_receipt.json", record)
        require(record["status"] == "verified", "稿件已存在，部分回读字段不符。请复核该 BVID。")

    if existing or aids:
        return read_receipt(
            existing["aid"] if existing else next(iter(aids)), existing["bvid"] if existing else next(iter(bvids), None)
        )
    require(not record_readback and not web, "已有官网提交记录或只读请求，须在创作中心核实，禁止再次投稿。")
    require(not bvids and (not prior or rejected), "已有 BVID 或提交记录尚未出现在列表中。仅限只读回查。")
    if rejected:
        print(f"前次投稿已明确拒绝，平台码 {prior['code']}。已查完整稿件队列。", flush=True)
        if prior["code"] == -412:
            require(not args.submit, OFFICIAL_REVIEW)
            print(OFFICIAL_REVIEW, flush=True)
            return
        require(not args.submit or args.retry_rejected, "修正拒绝原因后可用 --submit --retry-rejected 明确重试一次。")
    require(not args.retry_rejected or (rejected and args.submit), "--retry-rejected 需要已明确拒绝的回执及 --submit。")
    require(stamp, "新排期需要 --schedule-at。")
    tail = check_slot(rows, up, stamp)
    check_unlisted_pending(project, rows, titles, stamp)
    check_gate(pub, project, meta)
    native, cover43_file = submission_options(up, project)
    print(f"队尾 {tail or '空'}；目标 {dt.datetime.fromtimestamp(stamp, BJ).isoformat()}；非商业设置 {noncommercial}")
    if native:
        print(f"官网配置已核实：人选分区 {native['human_type2']}，创作声明 1，沿用制作稿旧 tid {meta['tid']}。")
    if not args.submit:
        return

    def before_add(payload):
        if native:
            payload.update(native, cover43=up.upload_cover(cover43_file))
        fresh = inventory(up)
        require(not match_project(fresh, titles, aids, bvids), "上传期间已有同题稿出现。")
        check_slot(fresh, up, stamp)
        check_unlisted_pending(project, fresh, titles, stamp)
        require(
            payload.get("dtime") == stamp and payload.get("videos") and payload.get("cover"),
            "最终请求缺少目标档期或媒体。",
        )
        require(
            payload.get("title") == meta["title"]
            and payload.get("tid") == meta["tid"]
            and payload.get("desc") == meta["description"]
            and payload.get("tag") == ",".join(meta["tags"])
            and "人工智能" in str(payload.get("neutral_mark", "")),
            "最终请求与核对过的文案或 AI 声明不符。",
        )
        require(
            not native or payload.get("cover43") and payload["cover43"] != payload["cover"], "4:3 封面上传回包不符。"
        )
        if noncommercial:
            payload.update(open_elec=0, no_reprint=0)

    def record_add(outcome):
        record = dict(outcome, requested_dtime=stamp, title_sha256=title_hash(meta["title"]))
        if native:
            record["submitted_native"] = dict(
                human_type2=native["human_type2"], category=meta["tid"], creation_statement_id=1
            )
        if rejected:
            record["last_rejection"] = {k: prior[k] for k in ("code", "reason", "http_status") if k in prior}
        save(receipt_path, record)

    session.before_add = before_add
    session.record_add = record_add
    try:
        pub.publish_project(
            project=project.name,
            platforms=["bilibili"],
            mode="schedule",
            schedule_at=dt.datetime.fromtimestamp(stamp, BJ).isoformat(),
            execute_upload=True,
            ai_declaration=True,
        )
    except AddRejected:
        raise
    except Exception as exc:
        if not session.attempted:
            if isinstance(exc, GuardError):
                raise
            raise GuardError("传输在提交稿件前中断，请检查本地交付物和网络。") from None
    require(session.attempted, "没有发送稿件提交请求。请检查上传设置。")
    accepted = optional_json(receipt_path)
    if not accepted.get("aid"):
        if accepted.get("bvid"):
            bvids.add(accepted["bvid"])

        def locate_pending():
            found = match_project(inventory(up), titles, aids, bvids)
            if not found:
                raise ReadUnavailable()
            return found

        print("平台受理结果待核实，已保留 pending。正在只读回查。", flush=True)
        accepted = read_only(locate_pending)
        prior_outcome = optional_json(receipt_path)
        record_add(
            dict(
                prior_outcome,
                status="accepted",
                aid=accepted["aid"],
                bvid=accepted["bvid"],
                reason="完整稿件列表已找到同一投稿",
            )
        )
    read_receipt(accepted["aid"], accepted.get("bvid"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="仓库项目 ID 或目录名")
    parser.add_argument("--schedule-at", help="北京时间，例如 2026-12-04T18:30:00+08:00")
    parser.add_argument("--bvid", help="指定已知 BVID，只回读同一稿件")
    parser.add_argument("--record-readback", action="store_true", help="只读核对已知 BVID，保存脱敏回执和官网主封面")
    parser.add_argument("--noncommercial", action="store_true", help="该稿按非商业同人关闭充电并允许转载")
    parser.add_argument("--submit", action="store_true", help="允许提交一次或将已存在稿件的回读结果落盘")
    parser.add_argument("--retry-rejected", action="store_true", help="已修复明确拒绝原因，同意重查队列后再提交一次")
    args = parser.parse_args()
    os.chdir(ROOT)
    logging.disable(logging.CRITICAL)
    with GuardedSession() as session:
        pub = MatrixPublisher(projects_dir=ROOT / "projects", session=session)
        # All invocations using this account vault serialize without creating a lock file.
        fd = os.open(pub.vault.vault_dir, os.O_RDONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX if args.submit or args.record_readback else fcntl.LOCK_SH)
            run(args, pub, session)
        finally:
            os.close(fd)


if __name__ == "__main__":
    try:
        main()
    except GuardError as exc:
        sys.exit(str(exc))
    except Exception as exc:
        # API and transport exceptions can contain authenticated URLs or personal fields.
        sys.exit(f"未完成（{type(exc).__name__}）。核对本地配置和已有回执后只读回查。")
