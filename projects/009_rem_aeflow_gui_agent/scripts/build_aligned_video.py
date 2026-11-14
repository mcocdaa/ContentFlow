#!/usr/bin/env python3
"""1080P @ 60FPS Decoupled-Layer Studio Builder for Project 009 (GUI智能体架构 · 3D手办蕾姆)."""

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

ASSETS_DIR = PROJ_DIR / "assets"
CUTOUTS_DIR = PROJ_DIR / "output" / "cutouts"
DELIV_DIR = PROJ_DIR / "delivery"
OUT_VIDEO_DIR = PROJ_DIR / "output" / "video"

AUDIO_MP3 = DELIV_DIR / "3D手办蕾姆拆解GUI智能体_audio.mp3"
SRT_FILE = DELIV_DIR / "3D手办蕾姆拆解GUI智能体_subtitle.srt"
FINAL_MP4 = DELIV_DIR / "3D手办蕾姆拆解GUI智能体_final.mp4"
OUT_FINAL_MP4 = OUT_VIDEO_DIR / "3D手办蕾姆拆解GUI智能体_final.mp4"

NARRATION_SCENES: List[Dict[str, str]] = [
    {
        "tts_text": "为什么传统桌面自动化脚本一改版就报错，普通AI操作电脑还会和你抢鼠标打架？今天蕾姆六十帧全息拆解G U I智能体核心架构！",
        "subtitle_text": "传统 RPA 改版就报错、普通 AI 还会抢你鼠标打架？蕾姆 60 帧全息拆解 GUI 智能体架构！",
    },
    {
        "tts_text": "第一招叫独立虚拟视口隔离。A E Flow让智能体在虚拟显示层后台操作窗口，人类在主桌面照常写代码看剧，键鼠焦点互不干扰！",
        "subtitle_text": "架构一｜独立虚拟视口隔离：AEFlow 在虚拟显示层后台执行操作，主桌面写代码看剧互不抢键鼠！",
    },
    {
        "tts_text": "第二招是视觉定位控制闭环。每一轮截图送给多模态模型锚定像素坐标，注入原子级点击后再次截图校验，彻底告别死板定位！",
        "subtitle_text": "架构二｜视觉闭环控制：截图 → 多模态坐标 Grounding → 原子输入 → 状态复核，彻底告别死板选择器！",
    },
    {
        "tts_text": "多窗口网页与桌面客户端统一编排，操作风险可控可审计。感谢赛博股东白的黑板与小咩先生，三连关注进致谢榜，下期你想看谁由你定！",
        "subtitle_text": "网页+桌面跨窗口协同编排！鸣谢股东 @白的黑板 · @小咩先生，三连+关注进致谢榜并投票下期！",
    },
]


def main() -> None:
    DELIV_DIR.mkdir(parents=True, exist_ok=True)
    OUT_VIDEO_DIR.mkdir(parents=True, exist_ok=True)

    rem_full = segment_character_rgba(
        ASSETS_DIR / "rem_crop.png",
        CUTOUTS_DIR / "rem_full_cutout.png",
        crop_roi=(0.06, 0.04, 0.82, 0.98),
    )
    rem_stage = segment_character_rgba(
        ASSETS_DIR / "rem_base_cover.jpg",
        CUTOUTS_DIR / "rem_stage_cutout.png",
        crop_roi=(0.51, 0.05, 0.86, 0.96),
    )
    yowane_cohost = ROOT_DIR / "projects" / "002_yowane_cicd" / "assets" / "yowane_pose5_transparent.png"
    cohost_cut = yowane_cohost if yowane_cohost.exists() else rem_full

    tts = LocalNeuralTTS()
    timeline = tts.synthesize_scenes(
        NARRATION_SCENES,
        output_mp3=AUDIO_MP3,
        output_srt=SRT_FILE,
        voice="zf_043",
        speed=1.04,
    )

    scene_configs: List[Dict[str, Any]] = [
        {
            "index": 1,
            "start": timeline[0]["start"],
            "end": timeline[0]["end"],
            "char_png": rem_stage,
            "char_target_h": 1160,
            "char_cx": 335,
            "head_center": (260, 250),
            "arm_center": (245, 415),
            "act_tag": "ACT 01 · 痛点引入",
            "board_title": "AI 自己点鼠标操作电脑，为什么以前总翻车？",
            "board_subtitle": "传统 RPA 与裸桌面脚本的两大致命工程死穴",
            "accent_rgb": (95, 200, 255),
            "footer_note": "GUI 智能体进化方向：像真人一样「看得见屏幕、不抢人类焦点、动作可验证」",
            "cards": [
                {
                    "badge": "PAIN POINT 01",
                    "headline": "传统 RPA 极其脆弱",
                    "accent": (255, 115, 115),
                    "bullets": ["死绑 CSS / XPath 或固定坐标", "按钮挪动 5 像素整条流程当场崩溃"],
                    "status": "维护成本极高",
                    "status_color": (255, 115, 115),
                },
                {
                    "badge": "PAIN POINT 02",
                    "headline": "物理键鼠焦点抢占",
                    "accent": (255, 165, 85),
                    "bullets": ["AI 一动手你就必须松开鼠标看着", "弹窗抢焦点直接误点进其他聊天框"],
                    "status": "人机互相打架",
                    "status_color": (255, 165, 85),
                },
                {
                    "badge": "AEFLOW SOLUTION",
                    "headline": "独立视口 + 视觉闭环",
                    "accent": (0, 235, 255),
                    "bullets": ["虚拟隔离桌面承载全套 GUI 动作", "多模态实时看屏自愈 UI 布局微调"],
                    "status": "工程级可用",
                    "status_color": (0, 235, 255),
                },
            ],
        },
        {
            "index": 2,
            "start": timeline[1]["start"],
            "end": timeline[1]["end"],
            "char_png": rem_full,
            "char_target_h": 1180,
            "char_cx": 335,
            "head_center": (255, 235),
            "arm_center": (235, 390),
            "act_tag": "ACT 02 · 视口隔离",
            "board_title": "核心架构一：AEFlow 独立虚拟视口契约",
            "board_subtitle": "物理显示器与 AI 虚拟显示器彻底分道扬镳",
            "accent_rgb": (0, 235, 255),
            "footer_note": "Viewport Isolation：人类主桌面专注创作，Agent 虚拟屏静默流水线交付",
            "cards": [
                {
                    "badge": "ISOLATED DISPLAY",
                    "headline": "虚拟帧缓冲独占沙箱",
                    "accent": (0, 235, 255),
                    "bullets": ["基于独立虚拟视口托管应用进程", "DPI 缩放与分辨率契约 100% 锁定"],
                    "status": "坐标零漂移",
                    "status_color": (0, 235, 255),
                },
                {
                    "badge": "ZERO HIJACK",
                    "headline": "键鼠事件无侵入注入",
                    "accent": (80, 250, 175),
                    "bullets": ["虚拟光标独立分发 Click 与按键", "再也不怕聊天误触或打断打游戏"],
                    "status": "物理零抢占",
                    "status_color": (80, 250, 175),
                },
                {
                    "badge": "MULTI TARGET",
                    "headline": "多窗口并行不串台",
                    "accent": (140, 200, 255),
                    "bullets": ["浏览器 + Electron + 终端各走各通道", "单任务失败隔离清理不波及宿主"],
                    "status": "状态洁净可控",
                    "status_color": (140, 200, 255),
                },
            ],
        },
        {
            "index": 3,
            "start": timeline[2]["start"],
            "end": timeline[2]["end"],
            "char_png": rem_stage,
            "char_target_h": 1160,
            "char_cx": 335,
            "head_center": (260, 250),
            "arm_center": (245, 415),
            "act_tag": "ACT 03 · 视觉闭环",
            "board_title": "核心架构二：视觉 Grounding → 原子动作 → 复核",
            "board_subtitle": "不靠脆皮 DOM 选择器，靠多模态『眼-脑-手-眼』实时闭环",
            "accent_rgb": (80, 250, 175),
            "footer_note": "闭环自愈原则：动作不盲打、每次点击必须拿到后置画面变化证据",
            "cards": [
                {
                    "badge": "STEP 01 · VISION",
                    "headline": "截图 + VLM 视觉定位",
                    "accent": (0, 235, 255),
                    "bullets": ["先读取高清画面而非盲猜控件树", "输出精确边界框与中心点击像素坐标"],
                    "status": "无视前端改版",
                    "status_color": (0, 235, 255),
                },
                {
                    "badge": "STEP 02 · ATOMIC",
                    "headline": "原子动作精准投递",
                    "accent": (255, 215, 80),
                    "bullets": ["Move / Click / Scroll / Paste 解耦", "低级别安全动作严格受白名单约束"],
                    "status": "轨迹精准可控",
                    "status_color": (255, 215, 80),
                },
                {
                    "badge": "STEP 03 · VERIFY",
                    "headline": "后置状态截帧校验",
                    "accent": (80, 250, 175),
                    "bullets": ["确认弹窗消失或目标页跳转才过关", "遇异常立即触发局部重试与人工挂起"],
                    "status": "闭环零盲区",
                    "status_color": (80, 250, 175),
                },
            ],
        },
        {
            "index": 4,
            "start": timeline[3]["start"],
            "end": timeline[3]["end"],
            "char_png": cohost_cut,
            "char_target_h": 1180,
            "char_cx": 345,
            "head_center": (265, 235),
            "arm_center": (220, 355),
            "act_tag": "ACT 04 · 协同 & 致谢",
            "board_title": "跨应用协同工作流 & 【赛博股东致谢榜】",
            "board_subtitle": "60FPS 全息技术科普周持续营业 · 评论区投出下期选题",
            "accent_rgb": (255, 215, 75),
            "footer_note": "三连+关注自动锁定下期致谢名额！你的高赞建议 AI 代理会直接立项排期！",
            "cards": [
                {
                    "badge": "ORCHESTRATION",
                    "headline": "网页 × 桌面协同交付",
                    "accent": (0, 235, 255),
                    "bullets": ["打通浏览器、IDE 与本地桌面流程", "把繁琐重复表单操作交还后台"],
                    "status": "跨端统一协议",
                    "status_color": (0, 235, 255),
                },
                {
                    "badge": "NEXT TOPIC VOTE",
                    "headline": "第 8 期选题评论区公投",
                    "accent": (130, 195, 255),
                    "bullets": ["A：GUI 智能体防错与人工接管实录", "B：开源本地语音+60帧剪辑管线全开源"],
                    "status": "高赞直接立项",
                    "status_color": (130, 195, 255),
                },
                {
                    "badge": "SHAREHOLDERS",
                    "headline": "★ 赛博股东致谢榜",
                    "accent": (255, 215, 75),
                    "bullets": ["特别鸣谢 @白的黑板 · @小咩先生", "三连+关注解锁专属片尾荣誉席位！"],
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
        darken_bg=0.88,
        shareholder_pill_text="★ 赛博股东致谢榜：@白的黑板 · @小咩先生",
        closeup_hook_sec=1.20,
        hip_guard_y=640.0,
    )


if __name__ == "__main__":
    main()
