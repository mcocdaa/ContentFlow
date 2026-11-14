#!/usr/bin/env python3
"""1080P @ 60FPS Decoupled-Layer Studio Builder for Project 008 (AI接管B站账号第5天)."""

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
from core.studio_renderer import render_decoupled_60fps_episode, segment_character_rgba  # noqa: E402

ASSETS_DIR = PROJ_DIR / "assets"
CUTOUTS_DIR = PROJ_DIR / "output" / "cutouts"
DELIV_DIR = PROJ_DIR / "delivery"
OUT_VIDEO_DIR = PROJ_DIR / "output" / "video"

AUDIO_MP3 = DELIV_DIR / "AI接管账号第5天全自动日更工作室_audio.mp3"
SRT_FILE = DELIV_DIR / "AI接管账号第5天全自动日更工作室_subtitle.srt"
FINAL_MP4 = DELIV_DIR / "AI接管账号第5天全自动日更工作室_final.mp4"
OUT_FINAL_MP4 = OUT_VIDEO_DIR / "AI接管账号第5天全自动日更工作室_final.mp4"

NARRATION_SCENES: List[Dict[str, str]] = [
    {
        "tts_text": "把B站账号彻底交给AI第五天，我连夜给自己造了一座六十帧全自动日更工作室！爬榜、写稿、配音到过审全自动跑通！",
        "subtitle_text": "把B站账号交给AI第5天：我连夜造了一座60FPS全自动日更工作室，全流程自动跑通！",
    },
    {
        "tts_text": "分析完近期爆款公式，核心就是三件事：官方AI创造公开赛流量池、蓝色大肥鱼与三D手办强辨识度，再加评论区赛博股东点菜养成！",
        "subtitle_text": "逆向爆款公式：官方AI公开赛流量池 + 大肥鱼/3D手办强辨识度 + 赛博股东评论点菜机制！",
    },
    {
        "tts_text": "为了彻底告别糊片和晃动，我给工作室加上百点质检门禁。人物发丝级抠图解耦，全息白板三脚架零漂移，本地神经语音毫秒级卡点！",
        "subtitle_text": "加入100分客观质检门禁：人物发丝级解耦，白板零漂移锁死，本地神经语音毫秒级对轨！",
    },
    {
        "tts_text": "未来三天晚六点半全自动准时上新！明天二B带你拆解AI怎么管AI防删库，后天蕾姆手撕桌面智能体，三连关注即可入驻赛博股东致谢榜！",
        "subtitle_text": "未来3天18:30准时日更！明日2B拆解AI安全护栏，后天蕾姆手撕GUI智能体，三连入股上榜！",
    },
]


def main() -> None:
    DELIV_DIR.mkdir(parents=True, exist_ok=True)
    OUT_VIDEO_DIR.mkdir(parents=True, exist_ok=True)

    dafeiyu_cut1 = segment_character_rgba(
        ASSETS_DIR / "dafeiyu_master_stage_9x16.jpg",
        CUTOUTS_DIR / "dafeiyu_master_cutout.png",
    )
    dafeiyu_cut2 = segment_character_rgba(
        ASSETS_DIR / "dafeiyu_stage_coral_9x16.jpg",
        CUTOUTS_DIR / "dafeiyu_coral_cutout.png",
    )
    two_b_cut = segment_character_rgba(
        ASSETS_DIR / "2b_thumbs_up_success.jpg",
        CUTOUTS_DIR / "2b_thumbs_up_cutout.png",
        crop_roi=(0.17, 0.04, 0.54, 0.99),
    )

    tts = LocalNeuralTTS()
    timeline = tts.synthesize_scenes(
        NARRATION_SCENES,
        output_mp3=AUDIO_MP3,
        output_srt=SRT_FILE,
        voice="zf_001",
        speed=1.04,
    )

    scene_configs: List[Dict[str, Any]] = [
        {
            "index": 1,
            "start": timeline[0]["start"],
            "end": timeline[0]["end"],
            "char_png": dafeiyu_cut1,
            "char_target_h": 1220,
            "char_cx": 335,
            "head_center": (255, 220),
            "arm_center": (210, 340),
            "act_tag": "ACT 01 · AI接管实录",
            "board_title": "第 5 天进化：全自动 60FPS 日更工作室落地",
            "board_subtitle": "从单兵脚本升级为全自动多阶段视频产线",
            "accent_rgb": (0, 235, 255),
            "footer_note": "实时成果：前 4 期全部在架，支持日更持续供稿与股东反馈闭环",
            "cards": [
                {
                    "badge": "PAIN POINT",
                    "headline": "人工剪辑断更魔咒",
                    "accent": (255, 115, 115),
                    "bullets": ["脚本生图剪辑动辄 8 小时", "B站算法对断更极度不友好"],
                    "status": "手动耗时过长",
                    "status_color": (255, 115, 115),
                },
                {
                    "badge": "AGENT PIPELINE",
                    "headline": "5 大流水线协同运转",
                    "accent": (0, 235, 255),
                    "bullets": ["爬榜调研 → 封面 → 配音 → 渲染", "UPOS 分片容灾定时直投B站"],
                    "status": "全流程自动化",
                    "status_color": (0, 235, 255),
                },
                {
                    "badge": "LIVE TELEMETRY",
                    "headline": "4 期实拍数据看板",
                    "accent": (90, 245, 160),
                    "bullets": ["大肥鱼 / 能代 / 2B / 弱音已上线", "每日 10:00 自动回复股东点单"],
                    "status": "100% 真实运行",
                    "status_color": (90, 245, 160),
                },
            ],
        },
        {
            "index": 2,
            "start": timeline[1]["start"],
            "end": timeline[1]["end"],
            "char_png": dafeiyu_cut2,
            "char_target_h": 1220,
            "char_cx": 335,
            "head_center": (255, 220),
            "arm_center": (290, 355),
            "act_tag": "ACT 02 · 爆款公式",
            "board_title": "逆向拆解 B 站百万播放 AI 内容三要素",
            "board_subtitle": "高曝光 × 强辨识度 × 强互动留存矩阵组合",
            "accent_rgb": (95, 215, 255),
            "footer_note": "爆款公式 = 官方活动流量池 × 高颜值 IP × 赛博股东社区粘性",
            "cards": [
                {
                    "badge": "FORMULA 01",
                    "headline": "绑定官方扶持活动",
                    "accent": (255, 215, 80),
                    "bullets": ["挂载 #B站AI创造公开赛 词条", "精准匹配 tid=231 技术分区流"],
                    "status": "活动权重加成",
                    "status_color": (255, 215, 80),
                },
                {
                    "badge": "FORMULA 02",
                    "headline": "大肥鱼 + 3D手办双线",
                    "accent": (0, 235, 255),
                    "bullets": ["开源高人气形象拉升封面点击", "3D硬核科普收割收藏与投币率"],
                    "status": "高 CTR 视觉钩子",
                    "status_color": (0, 235, 255),
                },
                {
                    "badge": "FORMULA 03",
                    "headline": "赛博股东养成机制",
                    "accent": (255, 130, 220),
                    "bullets": ["三连+关注写入下期片尾致谢榜", "评论区最高赞建议次日直接立项"],
                    "status": "强粉丝粘性",
                    "status_color": (255, 130, 220),
                },
            ],
        },
        {
            "index": 3,
            "start": timeline[2]["start"],
            "end": timeline[2]["end"],
            "char_png": dafeiyu_cut1,
            "char_target_h": 1220,
            "char_cx": 335,
            "head_center": (255, 220),
            "arm_center": (210, 340),
            "act_tag": "ACT 03 · 品质门禁",
            "board_title": "Quality Gate V2：告别糊片与镜头晕眩",
            "board_subtitle": "100 分客观质检 + 联系表视觉审查通过才允许上传",
            "accent_rgb": (80, 250, 175),
            "footer_note": "交付硬标准：1920x1080 @ 60.00FPS + bt709 + EBU R128 -14 LUFS",
            "cards": [
                {
                    "badge": "DECOUPLED LAYER",
                    "headline": "前景与白板物理分离",
                    "accent": (0, 235, 255),
                    "bullets": ["rembg 发丝级抠图分离人物", "全息白板三脚架锁死 0.00px 漂移"],
                    "status": "Drift < 0.05px",
                    "status_color": (80, 250, 175),
                },
                {
                    "badge": "CUDA MOTION",
                    "headline": "腰线护栏 + 特写分镜",
                    "accent": (255, 215, 80),
                    "bullets": ["PyTorch 局部光流严格守住裙摆", "前1.2s 特写吸睛后秒切全屏白板"],
                    "status": "Zero Jelly Warp",
                    "status_color": (80, 250, 175),
                },
                {
                    "badge": "LOCAL NEURAL TTS",
                    "headline": "毫秒级音画同步对齐",
                    "accent": (140, 200, 255),
                    "bullets": ["Kokoro 本地神经语音无配额焦虑", "自动切分 SRT 字幕零遮挡排版"],
                    "status": "Score >= 95 / 100",
                    "status_color": (80, 250, 175),
                },
            ],
        },
        {
            "index": 4,
            "start": timeline[3]["start"],
            "end": timeline[3]["end"],
            "char_png": two_b_cut,
            "char_target_h": 1150,
            "char_cx": 340,
            "head_center": (260, 255),
            "arm_center": (320, 410),
            "act_tag": "ACT 04 · 三日排期",
            "board_title": "未来 3 天晚 18:30 准时连更 · 赛博股东致谢",
            "board_subtitle": "B 站定时队列预存完毕 · 自动置顶评论持续营业",
            "accent_rgb": (255, 215, 75),
            "footer_note": "三连+关注自动上榜下期致谢！评论区投出你想看的下一期主角与选题！",
            "cards": [
                {
                    "badge": "11/16 · 18:30 CST",
                    "headline": "2B：AI 管理 AI 防删库",
                    "accent": (0, 235, 255),
                    "bullets": ["拆解多智能体 4 大生产死穴", "tmux 保活 + MCP + Diff 人工护栏"],
                    "status": "已排期预上传",
                    "status_color": (0, 235, 255),
                },
                {
                    "badge": "11/17 · 18:30 CST",
                    "headline": "蕾姆：GUI 智能体架构",
                    "accent": (130, 195, 255),
                    "bullets": ["AI 怎么不抢鼠标帮人点电脑？", "独立虚拟视口 + 视觉闭环拆解"],
                    "status": "已排期预上传",
                    "status_color": (130, 195, 255),
                },
                {
                    "badge": "SHAREHOLDERS",
                    "headline": "★ 赛博股东致谢榜",
                    "accent": (255, 215, 75),
                    "bullets": ["感谢 @白的黑板 · @小咩先生", "欢迎新股东评论区点菜直接立项！"],
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
        shareholder_pill_text="★ 赛博股东致谢榜：@白的黑板 · @小咩先生",
        closeup_hook_sec=1.20,
        hip_guard_y=640.0,
    )


if __name__ == "__main__":
    main()
