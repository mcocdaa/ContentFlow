#!/usr/bin/env python3
"""Clean up AI-garbled hologram text and prepare 1920x1080 crisp base & HUD overlays for Project 004."""

import shutil
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from rembg import remove

PROJ_DIR = Path(__file__).resolve().parent
ROOT_DIR = PROJ_DIR.parent.parent
ASSETS_DIR = PROJ_DIR / "assets"
LIB_2B_DIR = ROOT_DIR / "library" / "characters" / "yorha_2b"
CLEAN_DIR = PROJ_DIR / "output" / "cleaned_scenes"
CLEAN_DIR.mkdir(parents=True, exist_ok=True)

FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
FONT_REG = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"

RAW_LIB_MAPPING = {
    "scene1_intro_troubled.jpg": LIB_2B_DIR / "troubled" / "2b_troubled_pose1.jpg",
    "scene2_base_url.jpg": LIB_2B_DIR / "teaching" / "2b_teaching_base_url.jpg",
    "scene3_api_key.jpg": LIB_2B_DIR / "warning" / "2b_warning_api_key.jpg",
    "scene4_model_name.jpg": LIB_2B_DIR / "explaining" / "2b_explaining_model_name.jpg",
    "scene5_error_triage.jpg": LIB_2B_DIR / "triage" / "2b_error_triage.jpg",
    "scene6_success_thumbsup.jpg": LIB_2B_DIR / "thumbs_up" / "2b_thumbs_up_success.jpg",
}


def load_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD if bold and Path(FONT_BOLD).exists() else FONT_REG
    return ImageFont.truetype(path, size=size)


def upscale_1080p_crisp(img_path: Path) -> Image.Image:
    with Image.open(img_path) as im:
        rgb = im.convert("RGB").resize((1920, 1080), Image.Resampling.LANCZOS)
    return rgb.filter(ImageFilter.UnsharpMask(radius=1.6, percent=145, threshold=2))


def clean_scene1(im: Image.Image) -> Image.Image:
    canvas = im.convert("RGBA")
    blur_patch = canvas.crop((1455, 455, 1825, 592)).filter(ImageFilter.GaussianBlur(radius=14))
    canvas.paste(blur_patch, (1455, 455))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        [1455, 455, 1825, 590],
        radius=8,
        fill=(32, 24, 14, 232),
        outline=(245, 165, 36, 225),
        width=2,
    )
    f_code = load_font(19, bold=True)
    f_sub = load_font(17, bold=False)
    draw.text((1472, 468), "ERROR: 404 Not Found (/v1 missing)", font=f_code, fill=(255, 195, 75, 255))
    draw.text((1472, 500), "• Base URL 漏写 /v1 路由后缀", font=f_sub, fill=(255, 235, 190, 255))
    draw.text((1472, 528), "• Model Name 模型代号拼写错误", font=f_sub, fill=(255, 235, 190, 255))
    draw.text((1472, 556), "• API Key 未配置环境变量 (.env)", font=f_sub, fill=(255, 130, 130, 255))
    return canvas.convert("RGB")


def clean_scene2(im: Image.Image) -> Image.Image:
    canvas = im.convert("RGBA")
    for box in [(990, 230, 1148, 412), (990, 588, 1148, 760)]:
        patch = canvas.crop(box).filter(ImageFilter.GaussianBlur(radius=12))
        canvas.paste(patch, (box[0], box[1]))
    draw = ImageDraw.Draw(canvas)
    f_hdr = load_font(16, bold=True)
    f_code = load_font(15, bold=False)

    draw.rounded_rectangle(
        [990, 230, 1148, 412],
        radius=6,
        fill=(8, 36, 56, 238),
        outline=(0, 235, 255, 235),
        width=2,
    )
    draw.text((1002, 244), "// 1. 云端官方接口", font=f_hdr, fill=(0, 240, 255, 255))
    draw.text((1002, 274), "base_url =", font=f_code, fill=(220, 245, 255, 255))
    draw.text((1002, 298), '"/v1" # 必带!', font=f_hdr, fill=(255, 215, 0, 255))
    draw.text((1002, 332), "POST /chat/", font=f_code, fill=(160, 230, 255, 255))
    draw.text((1002, 356), "completions", font=f_code, fill=(160, 230, 255, 255))

    draw.rounded_rectangle(
        [990, 588, 1148, 760],
        radius=6,
        fill=(8, 36, 56, 238),
        outline=(0, 235, 255, 235),
        width=2,
    )
    draw.text((1002, 602), "// 2. 本地 Ollama", font=f_hdr, fill=(0, 240, 255, 255))
    draw.text((1002, 632), "localhost:", font=f_code, fill=(220, 245, 255, 255))
    draw.text((1002, 656), "11434/v1", font=f_hdr, fill=(80, 255, 160, 255))
    draw.text((1002, 692), "自动路由至本地", font=f_code, fill=(190, 235, 255, 255))
    draw.text((1002, 718), "大模型推理引擎", font=f_code, fill=(190, 235, 255, 255))
    return canvas.convert("RGB")


def clean_scene3(im: Image.Image) -> Image.Image:
    canvas = im.convert("RGBA")
    box = (1176, 160, 1748, 490)
    patch = canvas.crop(box).filter(ImageFilter.GaussianBlur(radius=18))
    canvas.paste(patch, (box[0], box[1]))

    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        [1180, 164, 1746, 488],
        radius=12,
        fill=(28, 22, 18, 246),
        outline=(255, 208, 92, 245),
        width=2,
    )
    f_hdr = load_font(22, bold=True)
    f_title = load_font(19, bold=True)
    f_code = load_font(19, bold=True)
    f_desc = load_font(18, bold=False)

    draw.text((1202, 180), "KEY 2: API KEY (AUTHENTICATION & SECURITY)", font=f_hdr, fill=(255, 230, 130, 255))
    draw.line([(1202, 214), (1726, 214)], fill=(255, 208, 92, 140), width=1)
    draw.text((1202, 228), "HTTP 标准鉴权请求头 (Bearer Token):", font=f_title, fill=(255, 215, 90, 255))
    draw.rounded_rectangle(
        [1202, 262, 1726, 308],
        radius=8,
        fill=(14, 16, 24, 245),
        outline=(110, 220, 255, 200),
        width=1,
    )
    draw.text((1218, 273), "Authorization: Bearer sk-****************", font=f_code, fill=(80, 245, 180, 255))
    draw.text((1202, 326), "• 严禁将 sk- 密钥硬编码写入前端或提交 GitHub", font=f_desc, fill=(255, 235, 205, 255))
    draw.text((1202, 366), "• 务必通过 .env 环境变量隔离读取，防止额度被盗刷", font=f_desc, fill=(255, 150, 140, 255))
    draw.text((1202, 406), "• 报错 401 Unauthorized = 密钥填错 / 过期 / 欠费", font=f_desc, fill=(0, 235, 255, 255))
    return canvas.convert("RGB")


def clean_scene4(im: Image.Image) -> Image.Image:
    canvas = im.convert("RGBA")
    draw = ImageDraw.Draw(canvas)
    # Position cards strictly below 'deepseek-reasoner', 'gpt-4o', 'claude-3-7-sonnet' headers
    cards = [
        (
            (994, 482, 1184, 642),
            (12, 34, 64, 238),
            (70, 180, 255, 235),
            ["满血推理模型", "DeepSeek-R1", "思维链深度推理"],
        ),
        (
            (1230, 452, 1465, 624),
            (10, 48, 56, 238),
            (0, 255, 210, 245),
            ["OpenAI 旗舰模型", "多模态实时交互", "严格区分大小写"],
        ),
        (
            (1512, 418, 1802, 598),
            (10, 46, 38, 238),
            (80, 255, 165, 235),
            ["代码架构主力", "Claude 3.7 Sonnet", "横杠错一位即404"],
        ),
    ]
    f_line = load_font(19, bold=True)
    f_tag = load_font(16, bold=False)
    for (x0, y0, x1, y1), bg, border, lines in cards:
        patch = canvas.crop((x0, y0, x1, y1)).filter(ImageFilter.GaussianBlur(radius=14))
        canvas.paste(patch, (x0, y0))
        draw.rounded_rectangle([x0, y0, x1, y1], radius=10, fill=bg, outline=border, width=2)
        cx = (x0 + x1) // 2
        cy = y0 + 20
        for idx, text in enumerate(lines):
            font = f_line if idx < 2 else f_tag
            color = (255, 255, 255, 255) if idx == 0 else ((0, 245, 255, 255) if idx == 1 else (255, 220, 110, 255))
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            draw.text((cx - tw // 2, cy), text, font=font, fill=color)
            cy += 44
    return canvas.convert("RGB")


def clean_scene5(im: Image.Image) -> Image.Image:
    canvas = im.convert("RGBA")
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        [1055, 695, 1785, 760],
        radius=10,
        fill=(18, 20, 42, 238),
        outline=(0, 235, 255, 235),
        width=2,
    )
    f_bar = load_font(21, bold=True)
    draw.text(
        (1078, 714),
        "速查口诀：401 查 Key 与余额 ｜ 404 查 /v1 与模型名 ｜ 429 查并发限流",
        font=f_bar,
        fill=(255, 225, 100, 255),
    )
    return canvas.convert("RGB")


def clean_scene6(im: Image.Image) -> Image.Image:
    """Use rembg to preserve 2B's foreground thumb/arm, clean the blackboard behind her, and add Cyber Shareholder badge."""
    fg_2b = remove(im)  # RGBA with 2B cleanly segmented
    canvas = im.convert("RGBA")
    draw = ImageDraw.Draw(canvas)

    # Clean the blackboard region behind 2B's thumb (x: 755..1055, y: 268..478) with a clean dark telemetry grid (no text occluded by thumb)
    bx = (755, 268, 1055, 478)
    patch = canvas.crop(bx).filter(ImageFilter.GaussianBlur(radius=18))
    canvas.paste(patch, (bx[0], bx[1]))
    draw.rounded_rectangle(
        bx,
        radius=10,
        fill=(18, 32, 48, 235),
        outline=(0, 220, 255, 160),
        width=2,
    )
    for gy in range(290, 465, 28):
        draw.line([(770, gy), (1040, gy)], fill=(0, 190, 230, 45), width=1)
    f_hdr = load_font(16, bold=True)
    draw.text((772, 280), "HTTP/1.1 200 OK", font=f_hdr, fill=(80, 255, 165, 235))
    draw.text((772, 308), "TLS 1.3 Verified", font=f_hdr, fill=(0, 230, 255, 220))

    # Composite 2B foreground back over the cleaned blackboard so her thumb & glove sit naturally in front!
    canvas.alpha_composite(fg_2b)

    # Draw Cyber Shareholder Honor Badge at top-right (using Noto-safe ★ star symbol)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        [1055, 76, 1795, 160],
        radius=16,
        fill=(12, 38, 48, 242),
        outline=(255, 215, 0, 250),
        width=3,
    )
    f_badge_title = load_font(24, bold=True)
    f_badge_sub = load_font(18, bold=True)
    draw.text(
        (1082, 88),
        "★ 赛博股东养成计划：全息致谢屏",
        font=f_badge_title,
        fill=(255, 215, 0, 255),
    )
    draw.text(
        (1082, 124),
        "一键三连+评论区点单即可解锁下期视频专属股东致谢席位！",
        font=f_badge_sub,
        fill=(120, 255, 210, 255),
    )
    return canvas.convert("RGB")


def main():
    cleaners = [
        ("scene1_intro_troubled.jpg", clean_scene1),
        ("scene2_base_url.jpg", clean_scene2),
        ("scene3_api_key.jpg", clean_scene3),
        ("scene4_model_name.jpg", clean_scene4),
        ("scene5_error_triage.jpg", clean_scene5),
        ("scene6_success_thumbsup.jpg", clean_scene6),
    ]
    for fname, fn in cleaners:
        raw_lib_path = RAW_LIB_MAPPING[fname]
        up = upscale_1080p_crisp(raw_lib_path)
        cleaned = fn(up)
        out_path = CLEAN_DIR / fname
        cleaned.save(out_path, format="JPEG", quality=96, subsampling=0)
        cleaned.save(ASSETS_DIR / fname, format="JPEG", quality=96, subsampling=0)
        print(f"[+] Cleaned & upscaled 1920x1080 -> {ASSETS_DIR / fname}")


if __name__ == "__main__":
    main()
