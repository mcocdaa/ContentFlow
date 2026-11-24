#!/usr/bin/env python3
"""Cyber Focus Warden (赛博防摸鱼毒舌监工) — Zero-Dependency Local Web App.

Pure Python standard library HTTP server + modern dark-glass web UI.
- 100% offline out of the box (48+ curated 3-tier savage roast lines).
- Optional OPENAI_API_KEY support for live LLM roasts (with seamless offline fallback).
- Zero microphone, zero camera, zero external telemetry.

Usage:
    python3 app.py                 # Starts on http://127.0.0.1:8780
    python3 app.py --port 0        # Binds a free ephemeral port and prints URL
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import signal
import sys
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Tuple

APP_DIR = Path(__file__).resolve().parent
INDEX_HTML_PATH = APP_DIR / "index.html"

# ---------------------------------------------------------------------------
# 3-Tier Built-In Offline Roast Library (48 lines total, zero API key needed)
# ---------------------------------------------------------------------------
OFFLINE_ROAST_BANK: Dict[int, List[str]] = {
    1: [
        "检测到切屏去刷摸鱼网页了，快回来！你的任务进度条还没动呢。",
        "才专注了这么几秒手就痒了？把鼠标从视频网页上拿开！",
        "友情提示：切屏 3 秒已经触发初级警报，趁我还没发火赶紧滚回来。",
        "你的大脑正在试图逃避现实，但我已经锁定你的浏览器标签页了。",
        "就这？刚立下的学习 Flag 还没立稳，你就先溜去摸鱼了？",
        "叮咚！监工雷达扫到你分心了，立刻切回专注界面还能从轻发落。",
        "先别急着刷短视频，等你干完手头这点活再看也不迟啊。",
        "警告 Lv.1：页面失焦超过 3 秒，再不回来马上启动弹幕公开处刑。",
        "你以为切个窗口我就看不见？浏览器 visibilitychange 早就把你卖了。",
        "摸鱼窗口点开得比写代码还快，手速用对地方行不行？",
        "专注倒计时还在跑呢，你怎么先跑路了？麻溜回来坐好！",
        "三秒已到！给你最后一次体面回归的机会，快切回来。",
        "嘴上说着“就看五分钟”，上一次说这话的时候天都亮了。",
        "注意！检测到注意力逃逸，赛博监工正在加载毒舌语音包……",
        "别装了，窗口 blur 事件已经把你抓个现行，立刻归位！",
        "快回来！你欠下的任务不会因为你切屏就自己写完。",
    ],
    2: [
        "二次犯案！还敢切屏？赛博功德 -1，全屏毒舌弹幕立刻伺候！",
        "好家伙，你是来专注的还是来给浏览器做切换压力测试的？",
        "切屏速度堪比职业电竞选手，干正事的时候怎么不见你这么积极？",
        "算算时间：你刚刚又浪费了一大截黄金专注期，今晚准备熬到几点？",
        "赛博功德 -1！再这么摸下去，你的拖延症都能拿年度全勤奖了。",
        "别人是在番茄钟里高效输出，你是在番茄钟里极限摸鱼打卡。",
        "我都拉 Lv.1 警告了你还敢顶风作案？胆子比你的完成率大十倍！",
        "温馨拷问：刚才刷的那个视频，能帮你把明天的截止日期往后推吗？",
        "进度条纹丝不动，摸鱼记录节节攀升，你可真是个时间管理鬼才。",
        "警告升级 Lv.2！继续切屏将立刻拉响全屏红蓝警报并打印罪证小票！",
        "你的注意力保质期只有八秒吗？连金鱼看了都要摇摇头。",
        "刚才是不是又点开了“再刷一条就学”？全人类最大的谎言就是这句。",
        "监工日志已记黑账：累犯摸鱼，拖延指数飙升，功德余额告急！",
        "醒醒！你已经把“五分钟放松”成功拖成了“半小时失踪”。",
        "弹幕全体起立围观！这位选手在任务期间公然翘班刷网页！",
        "再切一次屏幕试试？红蓝警灯和强制复盘弹窗已经架在门口等你了。",
    ],
    3: [
        "【摸鱼通缉令生效】屡教不改！全屏红蓝警报拉响，立刻接受强制复盘！",
        "终极铁证如山！连续切屏累犯，赛博功德暴扣，立刻打印今日罪证小票！",
        "恭喜触发 Lv.3 最高级别处刑！不写完认错复盘，今天别想关掉警报！",
        "我已经忍你三次了！任务没写两行，切屏先刷出个连击 Combo？",
        "全员戒备！检测到特级摸鱼惯犯，正在为您加急打印《赛博罪证小票》！",
        "别挣扎了，你的切屏次数和浪费秒数已经被铁面监工永久钉在耻辱柱上。",
        "凌晨两点后悔的眼泪，就是此刻你一次次切屏时亲手埋下的雷！",
        "触发红色警戒！你的拖延症正式进入晚期，请立刻深呼吸并坦白交代。",
        "三次切屏成就达成：获得称号《键盘摸鱼侠》，功德扣分直接拉满！",
        "警告拉满！你离完成目标只差管住自己这双老想点开摸鱼网页的手。",
        "全屏警报已接管！想解除锁定？先老老实实确认回归当前任务！",
        "赛博法庭宣判：本轮专注彻底翻车，罪证小票已生成，请签收留念。",
        "你以为关掉静音就听不见良心的谴责吗？红蓝警灯照亮你的桌面！",
        "摸鱼一时爽，赶工火葬场！现在立刻、马上、原地滚回去干正事！",
        "系统崩溃式吐槽：写这个监工软件都没花你今天摸鱼一半的时间！",
        "最终通牒：收起摸鱼小票，点击认错回归，把剩下的倒计时一口气打完！",
    ],
}

DANMAKU_POOL: List[str] = [
    "抓到了！又在偷偷切屏摸鱼！",
    "赛博功德 -1 -1 -1",
    "嘴上说看5分钟，结果看到凌晨2点",
    "进度条：我真的会谢",
    "快滚回去干活！！！",
    "visibilitychange：这锅我帮你背不动了",
    "明日复明日，明日何其多",
    "前方高能：Lv.3 红蓝警报正在路上",
    "这手速不去敲代码可惜了",
    "监工正在记录你的摸鱼犯罪证据",
    "停止自我欺骗，立刻回到番茄钟！",
    "警告！摸鱼小票打印机已预热完毕",
]

LEVEL_META: Dict[int, Dict[str, Any]] = {
    1: {"badge": "Lv.1 初级切屏警告", "merit_delta": -5, "severity": "amber"},
    2: {"badge": "Lv.2 毒舌弹幕拷问", "merit_delta": -15, "severity": "orange"},
    3: {"badge": "Lv.3 摸鱼通缉令 · 最高警戒", "merit_delta": -30, "severity": "crimson"},
}


def compute_sin_rank(blur_count: int, wasted_seconds: float, merit: int) -> Tuple[str, str]:
    """Computes a humorous cyber-receipt rank and savage final verdict."""
    if blur_count == 0 and wasted_seconds < 3:
        return "自律圣人 S+", "滴水不漏！今天连赛博监工都找不到你的茬，请继续保持。"
    if blur_count <= 1 and wasted_seconds < 15:
        return "轻度走神 B", "稍微手滑切了一次屏，尚有挽救余地，快收心冲刺！"
    if blur_count <= 2 and wasted_seconds < 45:
        return "资深摸鱼选手 A+", "嘴上喊着冲刺，身体诚实切屏，赛博功德已亮黄灯！"
    if merit <= 40 or blur_count >= 4 or wasted_seconds >= 90:
        return "特级摸鱼通缉犯 SSS", "铁证如山！熬夜赶工警告生效，建议把这张罪证小票贴在屏幕正中央反省。"
    return "惯犯拖延大师 SS", "连续触发三次警报，成功解锁全屏红蓝处刑，立刻停手回归任务！"


def call_openai_roast(
    level: int,
    blur_count: int,
    wasted_seconds: float,
    task: str,
    merit: int,
) -> str | None:
    """Optionally calls an OpenAI-compatible API if OPENAI_API_KEY is configured."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"

    level_desc = {
        1: "Lv.1 轻度提醒（切屏超过3秒，语气带点无奈和调侃，35字以内）",
        2: "Lv.2 毒舌拷问（多次切屏，犀利幽默吐槽拖延症，45字以内）",
        3: "Lv.3 全屏红蓝警报终极审判（累犯摸鱼，气势拉满的法庭宣判口吻，50字以内）",
    }.get(level, "毒舌提醒")

    payload = {
        "model": model,
        "temperature": 0.9,
        "max_tokens": 90,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是“赛博防摸鱼毒舌监工”，性格犀利搞笑、幽默但不带脏字辱骂。"
                    "请只输出一句简短有力的中文吐槽台词，不要加引号或前后缀。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"等级：{level_desc}；用户原定任务：{task or '专注学习/工作'}；"
                    f"已切屏次数：{blur_count} 次；累计摸鱼：{wasted_seconds:.1f} 秒；剩余赛博功德：{merit}。"
                ),
            },
        ],
    }

    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            text = body["choices"][0]["message"]["content"].strip()
            return text[:140] if text else None
    except (urllib.error.URLError, KeyError, IndexError, ValueError, TimeoutError):
        return None


def pick_offline_roast(level: int, history: List[str] | None = None) -> str:
    """Picks a non-repeating offline roast line for the requested alarm level."""
    tier = OFFLINE_ROAST_BANK.get(level, OFFLINE_ROAST_BANK[1])
    seen = set(history or [])
    candidates = [line for line in tier if line not in seen] or tier
    return random.choice(candidates)


def build_receipt_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """Builds structured + plain-text thermal receipt data for 《今日摸鱼罪证小票》."""
    task = str(data.get("task") or "未命名专注任务").strip()[:48]
    blur_count = max(0, int(data.get("blur_count") or 0))
    wasted_seconds = max(0.0, float(data.get("wasted_seconds") or 0.0))
    merit = int(data.get("merit") if data.get("merit") is not None else 100)
    merit_lost = max(0, 100 - merit)
    now_str = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    receipt_no = f"CFW-{dt.datetime.now().strftime('%H%M%S')}-{random.randint(100, 999)}"
    rank, verdict = compute_sin_rank(blur_count, wasted_seconds, merit)

    lines = [
        "====================================",
        "      CYBER FOCUS WARDEN v1.0       ",
        "         《今日摸鱼罪证小票》        ",
        "====================================",
        f"单号 NO.   : {receipt_no}",
        f"签发时间   : {now_str}",
        f"原定任务   : {task}",
        "------------------------------------",
        f"切屏累犯   : {blur_count} 次",
        f"摸鱼失焦   : {wasted_seconds:.1f} 秒",
        f"赛博功德   : {merit} (累计扣除 -{merit_lost})",
        f"罪名评级   : {rank}",
        "------------------------------------",
        f"终审判决   : {verdict}",
        "====================================",
        "  * 100% 本地离线监工 · 零隐私外传 *",
        "====================================",
    ]
    return {
        "receipt_no": receipt_no,
        "issued_at": now_str,
        "task": task,
        "blur_count": blur_count,
        "wasted_seconds": round(wasted_seconds, 1),
        "merit": merit,
        "merit_lost": merit_lost,
        "rank": rank,
        "verdict": verdict,
        "plain_text": "\n".join(lines),
    }


class WardenRequestHandler(BaseHTTPRequestHandler):
    """Minimal threaded HTTP handler serving index.html and JSON APIs."""

    server_version = "CyberFocusWarden/1.0"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        if os.environ.get("WARDEN_QUIET") == "1":
            return
        super().log_message(format, *args)

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 65536:
            return {}
        raw = self.rfile.read(length)
        try:
            parsed = json.loads(raw.decode("utf-8"))
            return parsed if isinstance(parsed, dict) else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            if not INDEX_HTML_PATH.exists():
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "index.html not found"})
                return
            html_bytes = INDEX_HTML_PATH.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html_bytes)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(html_bytes)
            return

        if path == "/api/health":
            has_key = bool(os.environ.get("OPENAI_API_KEY", "").strip())
            total_lines = sum(len(v) for v in OFFLINE_ROAST_BANK.values())
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "app": "Cyber Focus Warden",
                    "version": "1.0.0",
                    "mode": "openai_with_offline_fallback" if has_key else "offline_builtin",
                    "roast_bank_size": total_lines,
                    "privacy": "100% local, zero mic, zero camera, zero telemetry",
                },
            )
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": f"Unknown endpoint: {path}"})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        body = self._read_json_body()

        if path == "/api/roast":
            raw_level = int(body.get("level") or 1)
            level = max(1, min(3, raw_level))
            blur_count = max(0, int(body.get("blur_count") or level))
            wasted_seconds = max(0.0, float(body.get("wasted_seconds") or 3.0))
            task = str(body.get("task") or "专注学习与工作").strip()[:60]
            merit = int(body.get("merit") if body.get("merit") is not None else 100)
            history = body.get("history") if isinstance(body.get("history"), list) else []

            roast_text = call_openai_roast(level, blur_count, wasted_seconds, task, merit)
            source = "openai"
            if not roast_text:
                roast_text = pick_offline_roast(level, [str(x) for x in history])
                source = "offline"

            meta = LEVEL_META[level]
            danmaku = random.sample(DANMAKU_POOL, k=min(5, len(DANMAKU_POOL))) if level >= 2 else []
            rank, verdict = compute_sin_rank(blur_count, wasted_seconds, merit + meta["merit_delta"])

            self._send_json(
                HTTPStatus.OK,
                {
                    "level": level,
                    "badge": meta["badge"],
                    "severity": meta["severity"],
                    "roast": roast_text,
                    "danmaku_burst": danmaku,
                    "merit_delta": meta["merit_delta"],
                    "rank": rank,
                    "verdict": verdict,
                    "source": source,
                    "zero_telemetry": True,
                },
            )
            return

        if path == "/api/receipt":
            self._send_json(HTTPStatus.OK, build_receipt_payload(body))
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": f"Unknown endpoint: {path}"})


def run_server(host: str = "127.0.0.1", port: int = 8780) -> None:
    """Starts the local HTTP server and handles graceful shutdown."""
    httpd = ThreadingHTTPServer((host, port), WardenRequestHandler)
    actual_host, actual_port = httpd.server_address[:2]

    def _shutdown_handler(signum: int, _frame: Any) -> None:
        print(f"\n[CyberFocusWarden] Signal {signum} received, shutting down cleanly...", flush=True)
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _shutdown_handler)
    signal.signal(signal.SIGINT, _shutdown_handler)

    mode = "OpenAI API (with offline fallback)" if os.environ.get("OPENAI_API_KEY") else "100% Offline Built-in Bank"
    total_roasts = sum(len(v) for v in OFFLINE_ROAST_BANK.values())
    print(f"[CyberFocusWarden] Running at http://{actual_host}:{actual_port}/", flush=True)
    print(f"[CyberFocusWarden] Engine: {mode} | Built-in roasts: {total_roasts} | Zero Mic / Zero Cam", flush=True)

    try:
        httpd.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        print("[CyberFocusWarden] Server stopped.", flush=True)


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cyber Focus Warden — Anti-procrastination savage AI supervisor (100% local)."
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8780, help="Bind port (default: 8780; use 0 for random free port)")
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    run_server(host=args.host, port=args.port)
