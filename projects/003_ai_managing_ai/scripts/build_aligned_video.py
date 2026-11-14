#!/usr/bin/env python3
"""1080P @ 60FPS Decoupled-Layer Studio Builder for Project 003 (AI管理AI四大死穴 · 3D手办2B)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

SCRIPT_DIR = Path(__file__).resolve().parent
PROJ_DIR = SCRIPT_DIR.parent
ROOT_DIR = PROJ_DIR.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.local_tts import LocalNeuralTTS  # noqa: E402
from core.studio_renderer import (  # noqa: E402
    DEFAULT_STUDIO_BG,
    render_decoupled_60fps_episode,
    segment_character_rgba,
)

YO2B_DIR = ROOT_DIR / "library" / "characters" / "yorha_2b"
CUTOUTS_DIR = PROJ_DIR / "output" / "cutouts"
DELIV_DIR = PROJ_DIR / "delivery"
OUT_VIDEO_DIR = PROJ_DIR / "output" / "video"

AUDIO_MP3 = DELIV_DIR / "3D手办2B拆解AI管理AI四大死穴_audio.mp3"
SRT_FILE = DELIV_DIR / "3D手办2B拆解AI管理AI四大死穴_subtitle.srt"
FINAL_MP4 = DELIV_DIR / "3D手办2B拆解AI管理AI四大死穴_final.mp4"
OUT_FINAL_MP4 = OUT_VIDEO_DIR / "3D手办2B拆解AI管理AI四大死穴_final.mp4"

NARRATION_SCENES: List[Dict[str, str]] = [
    {
        "tts_text": "把服务器交给AI管理，网络一抖断连强杀进程，甚至AI幻觉误删全盘数据怎么办？今天二B老师六十帧拆解AI管理AI四大死穴！",
        "subtitle_text": "把服务器交给AI管理，断连SIGHUP强杀进程、甚至AI幻觉删库怎么办？2B老师60帧拆解四大死穴！",
    },
    {
        "tts_text": "第一死穴是执行黑盒与断网雪崩。TermFlow用T mux原生虚拟化托管，哪怕S S H断开，底层训练与编译依然在后台零掉线跑完！",
        "subtitle_text": "死穴一｜断网雪崩：TermFlow 用 tmux 原生保活，SSH 断开后台训练编译照样零掉线跑完！",
    },
    {
        "tts_text": "第二与第三死穴是内网穿透裸奔与权限失控。零公网端口的W S S主动反向隧道，搭配原生M C P白名单网关，把工具锁进安全沙箱！",
        "subtitle_text": "死穴二&三｜穿透与越权：0公网端口 WSS 反向隧道 + 原生 MCP 工具白名单，严格沙箱隔离！",
    },
    {
        "tts_text": "第四死穴是高危指令无人兜底。所有写命令触发第四级门禁强制挂起，生成代码差异对比图，必须人类确认通过才放行！",
        "subtitle_text": "死穴四｜误操作兜底：写命令触发 Level 4 强制挂起，生成 Unified Diff 必须人类拍板才放行！",
    },
    {
        "tts_text": "手机端还能单手一键接管救火！感谢赛博股东白的黑板与小咩先生，明天蕾姆带你拆解G U I智能体架构，三连入股不迷路！",
        "subtitle_text": "手机端单手接管救火！鸣谢股东 @白的黑板 · @小咩先生，明日蕾姆拆解 GUI 智能体，三连入股！",
    },
]


def main() -> None:
    DELIV_DIR.mkdir(parents=True, exist_ok=True)
    OUT_VIDEO_DIR.mkdir(parents=True, exist_ok=True)

    two_b_warn = segment_character_rgba(
        YO2B_DIR / "warning" / "2b_warning_api_key.jpg",
        CUTOUTS_DIR / "2b_warning_cutout.png",
        crop_roi=(0.11, 0.05, 0.44, 0.99),
    )
    two_b_teach = segment_character_rgba(
        YO2B_DIR / "teaching" / "2b_teaching_base_url.jpg",
        CUTOUTS_DIR / "2b_teaching_cutout.png",
        crop_roi=(0.11, 0.04, 0.49, 0.99),
    )
    two_b_explain = segment_character_rgba(
        YO2B_DIR / "explaining" / "2b_explaining_model_name.jpg",
        CUTOUTS_DIR / "2b_explaining_cutout.png",
        crop_roi=(0.06, 0.04, 0.49, 0.99),
    )
    two_b_ok = segment_character_rgba(
        YO2B_DIR / "thumbs_up" / "2b_thumbs_up_success.jpg",
        CUTOUTS_DIR / "2b_thumbs_up_cutout.png",
        crop_roi=(0.17, 0.04, 0.54, 0.99),
    )

    tts = LocalNeuralTTS()
    timeline = tts.synthesize_scenes(
        NARRATION_SCENES,
        output_mp3=AUDIO_MP3,
        output_srt=SRT_FILE,
        voice="zf_018",
        speed=1.04,
    )

    scene_configs: List[Dict[str, Any]] = [
        {
            "index": 1,
            "start": timeline[0]["start"],
            "end": timeline[0]["end"],
            "char_png": two_b_warn,
            "char_target_h": 1160,
            "char_cx": 335,
            "head_center": (255, 240),
            "arm_center": (315, 395),
            "act_tag": "ACT 01 · 高危警报",
            "board_title": "把服务器交给 AI，为什么生产环境频频翻车？",
            "board_subtitle": "从认知编排走向 TermFlow 物理控制舱架构破局",
            "accent_rgb": (255, 115, 115),
            "footer_note": "警报复盘：无状态 HTTP + 裸权限 Shell = AI 运维四大生产灾难根源",
            "cards": [
                {
                    "badge": "DEADLOCK 01",
                    "headline": "断网 SIGHUP 强杀",
                    "accent": (255, 115, 115),
                    "bullets": ["网络抖动立刻掐断父子进程树", "训练微调跑两小时直接前功尽弃"],
                    "status": "进程掉线暴毙",
                    "status_color": (255, 115, 115),
                },
                {
                    "badge": "DEADLOCK 02",
                    "headline": "幻觉删库爆炸半径",
                    "accent": (255, 165, 85),
                    "bullets": ["模型报错失控执行 rm -rf / 清盘", "或将 .env 数据库密钥打进公网日志"],
                    "status": "高危越权风险",
                    "status_color": (255, 165, 85),
                },
                {
                    "badge": "TERMFLOW FIX",
                    "headline": "物理控制舱四重护栏",
                    "accent": (0, 235, 255),
                    "bullets": ["tmux 保活 + 零端口反向穿透", "MCP 白名单沙箱 + Diff 人工审批"],
                    "status": "生产级确定性",
                    "status_color": (0, 235, 255),
                },
            ],
        },
        {
            "index": 2,
            "start": timeline[1]["start"],
            "end": timeline[1]["end"],
            "char_png": two_b_teach,
            "char_target_h": 1160,
            "char_cx": 340,
            "head_center": (255, 240),
            "arm_center": (360, 380),
            "act_tag": "ACT 02 · 会话保活",
            "board_title": "死穴一破解：tmux 原生虚拟化保活架构",
            "board_subtitle": "将控制链与计算寿命彻底解耦，断网不杀后台任务",
            "accent_rgb": (0, 235, 255),
            "footer_note": "POSIX 系统级持久会话：控制端随时断开重连，显卡算力零浪费",
            "cards": [
                {
                    "badge": "NAIVE HTTP",
                    "headline": "普通 SSH / HTTP 脆弱",
                    "accent": (255, 115, 115),
                    "bullets": ["连接句柄绑定前台终端 PTY", "超时即发 SIGHUP 终止子进程"],
                    "status": "极易中途夭折",
                    "status_color": (255, 115, 115),
                },
                {
                    "badge": "TMUX ENGINE",
                    "headline": "TermFlow 持久化托管",
                    "accent": (0, 235, 255),
                    "bullets": ["每个 Agent 独占命名 tmux 窗口", "重连秒级拉取完整 ANSI 输出历史"],
                    "status": "7×24 零掉线",
                    "status_color": (80, 250, 175),
                },
                {
                    "badge": "ZERO LOSS",
                    "headline": "长编译与微调稳如磐石",
                    "accent": (90, 245, 160),
                    "bullets": ["手机切换基站也能丝滑续接终端", "状态回放严格对齐进程退出码"],
                    "status": "高可用调度",
                    "status_color": (90, 245, 160),
                },
            ],
        },
        {
            "index": 3,
            "start": timeline[2]["start"],
            "end": timeline[2]["end"],
            "char_png": two_b_explain,
            "char_target_h": 1160,
            "char_cx": 340,
            "head_center": (255, 240),
            "arm_center": (355, 395),
            "act_tag": "ACT 03 · 零信任沙箱",
            "board_title": "死穴二&三破解：零公网端口穿透 + MCP 白名单",
            "board_subtitle": "防暴破 + 防越权双保险：算力在内网安全即插即用",
            "accent_rgb": (95, 215, 255),
            "footer_note": "遵守零信任最小权限原则：Agent 永远拿不到裸 root Token",
            "cards": [
                {
                    "badge": "REVERSE WSS",
                    "headline": "0 公网端口反向穿透",
                    "accent": (0, 235, 255),
                    "bullets": ["内网主机主动出站加密建连", "防火墙无需开任何入站端口防扫描"],
                    "status": "零攻击面暴露",
                    "status_color": (0, 235, 255),
                },
                {
                    "badge": "MCP BROKER",
                    "headline": "原生 MCP 能力白名单",
                    "accent": (140, 200, 255),
                    "bullets": ["仅开放声明式工具给外部大模型", "只读探查默认自动放行提效"],
                    "status": "行业标准互通",
                    "status_color": (140, 200, 255),
                },
                {
                    "badge": "SECRET VAULT",
                    "headline": "生产凭据隔离注入",
                    "accent": (90, 245, 160),
                    "bullets": ["密钥驻留宿主 Vault 不进 Prompt", "彻底杜绝大模型把密码写进日志"],
                    "status": "凭据零泄露",
                    "status_color": (90, 245, 160),
                },
            ],
        },
        {
            "index": 4,
            "start": timeline[3]["start"],
            "end": timeline[3]["end"],
            "char_png": two_b_teach,
            "char_target_h": 1160,
            "char_cx": 340,
            "head_center": (255, 240),
            "arm_center": (360, 380),
            "act_tag": "ACT 04 · Level 4 护栏",
            "board_title": "死穴四破解：Level 4 写操作冻结 + Diff 审批",
            "board_subtitle": "高危改写强制阻塞等待人类签字，AI 永远无法私自删库",
            "accent_rgb": (80, 250, 175),
            "footer_note": "人机协同终极防线：AI 负责 99% 排查写补丁，人类守住最终执行键",
            "cards": [
                {
                    "badge": "DANGER INTERCEPT",
                    "headline": "破坏命令毫秒级熔断",
                    "accent": (255, 115, 115),
                    "bullets": ["自动识别 rm / DROP / force push", "命即触发挂起并推送手机告警"],
                    "status": "高危拦截已激活",
                    "status_color": (255, 115, 115),
                },
                {
                    "badge": "UNIFIED DIFF",
                    "headline": "可视化代码差异预览",
                    "accent": (255, 215, 80),
                    "bullets": ["文件修改前先生成高亮 Diff 视图", "增删行一目了然无需盲猜黑盒"],
                    "status": "人类审查签字",
                    "status_color": (255, 215, 80),
                },
                {
                    "badge": "AUDIT TRAIL",
                    "headline": "全链路操作可回溯",
                    "accent": (80, 250, 175),
                    "bullets": ["每一步终端执行均记录时间线审计", "支持异常时一键回退至安全快照"],
                    "status": "生产安全闭环",
                    "status_color": (80, 250, 175),
                },
            ],
        },
        {
            "index": 5,
            "start": timeline[4]["start"],
            "end": timeline[4]["end"],
            "char_png": two_b_ok,
            "char_target_h": 1160,
            "char_cx": 340,
            "head_center": (260, 250),
            "arm_center": (320, 405),
            "act_tag": "ACT 05 · 移动救火 & 致谢",
            "board_title": "手机 18 键触觉救火坞 & 赛博股东致谢榜",
            "board_subtitle": "开源 TermFlow 控制舱护航 · 明日 18:30 蕾姆接棒登场",
            "accent_rgb": (255, 215, 75),
            "footer_note": "三连+关注自动进入下期片尾致谢榜！评论区投票决定你想看的下一期主角！",
            "cards": [
                {
                    "badge": "MOBILE TACTILE",
                    "headline": "地铁单手接管终端",
                    "accent": (0, 235, 255),
                    "bullets": ["内置 18 键触觉快捷键精准控场", "Ctrl+C 中断与重启服务一步到位"],
                    "status": "随时随地兜底",
                    "status_color": (0, 235, 255),
                },
                {
                    "badge": "NEXT EPISODE · 11/17",
                    "headline": "明日预告：蕾姆 GUI Agent",
                    "accent": (130, 195, 255),
                    "bullets": ["AI 如何不抢物理鼠标自动操作桌面", "60 帧全息拆解虚拟视口闭环架构"],
                    "status": "明日 18:30 上线",
                    "status_color": (130, 195, 255),
                },
                {
                    "badge": "SHAREHOLDERS",
                    "headline": "★ 赛博股东致谢榜",
                    "accent": (255, 215, 75),
                    "bullets": ["特别鸣谢 @白的黑板 · @小咩先生", "三连+关注留言点菜即可写入致谢！"],
                    "status": "三连关注入股",
                    "status_color": (255, 215, 75),
                },
            ],
        },
    ]

    render_decoupled_60fps_episode(
        scenes=scene_configs,
        audio_mp3=AUDIO_MP3,
        srt_file=SRT_FILE,
        final_mp4=FINAL_MP4,
        out_copy_mp4=OUT_FINAL_MP4,
        bg_path=DEFAULT_STUDIO_BG,
        darken_bg=0.86,
        shareholder_pill_text="★ 赛博股东致谢榜：@白的黑板 · @小咩先生",
        closeup_hook_sec=1.20,
        hip_guard_y=640.0,
    )


if __name__ == "__main__":
    main()
