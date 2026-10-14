#!/usr/bin/env python3
"""Composite clean classroom background, holographic whiteboard HUD, and character cutout."""

import argparse
import json
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
FONT_REG = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"


def get_font(size: int, bold: bool = False):
    path = FONT_BOLD if bold else FONT_REG
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def draw_status_icon(d, center_x: int, center_y: int, status: str = "pass", radius: int = 10) -> None:
    if status == "pass":
        d.ellipse([center_x - radius, center_y - radius, center_x + radius, center_y + radius], fill=(30, 180, 80, 255))
        d.line([(center_x - 5, center_y), (center_x - 1, center_y + 4), (center_x + 6, center_y - 4)], fill=(255, 255, 255, 255), width=2)
    elif status == "fail":
        d.ellipse([center_x - radius, center_y - radius, center_x + radius, center_y + radius], fill=(220, 40, 40, 255))
        d.line([(center_x - 4, center_y - 4), (center_x + 4, center_y + 4)], fill=(255, 255, 255, 255), width=2)
        d.line([(center_x + 4, center_y - 4), (center_x - 4, center_y + 4)], fill=(255, 255, 255, 255), width=2)
    elif status == "warn":
        d.ellipse([center_x - radius, center_y - radius, center_x + radius, center_y + radius], fill=(230, 140, 20, 255))
        d.line([(center_x, center_y - 5), (center_x, center_y + 1)], fill=(255, 255, 255, 255), width=2)
        d.ellipse([center_x - 1, center_y + 3, center_x + 1, center_y + 5], fill=(255, 255, 255, 255))


def render_scene(
    bg_path: Path,
    board_chassis_path: Path,
    char_cutout_path: Optional[Path],
    output_path: Path,
    title: str = "CI/CD PIPELINE STATUS",
    badge: str = "ALL GREEN",
    subtitle: str = "自动化质量门禁与容器标准化交付",
    char_x: int = 180,
    target_char_height: int = 1180,
) -> Path:
    bg = Image.open(bg_path).convert("RGBA")
    board_chassis = Image.open(board_chassis_path).convert("RGBA")

    # Render whiteboard inner content (1389x781)
    content = Image.new("RGBA", board_chassis.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(content)

    # Shift content to x >= 340 to prevent any character occlusion
    d.text((340, 95), title, font=get_font(28, True), fill=(100, 240, 160, 255))

    # Badge
    font_badge = get_font(20, True)
    bbox = font_badge.getbbox(badge)
    bw = bbox[2] - bbox[0]
    bx1 = 340 + int(len(title) * 16.5) + 30
    d.rounded_rectangle([bx1, 93, bx1 + bw + 28, 131], radius=6, fill=(20, 140, 70, 220), outline=(80, 255, 150, 255), width=2)
    d.text((bx1 + 14, 98), badge, font=font_badge, fill=(255, 255, 255, 255))

    d.text((340, 140), subtitle, font=get_font(17), fill=(200, 230, 215, 220))

    # Main HUD Container
    d.rounded_rectangle([340, 185, 1280, 600], radius=10, fill=(16, 26, 36, 235), outline=(80, 220, 160, 160), width=2)

    # Merge content onto whiteboard chassis
    board = board_chassis.copy()
    board.alpha_composite(content)

    # Place whiteboard onto background at (585, 78)
    scene = bg.copy()
    scene.alpha_composite(board, (585, 78))

    # Process character cutout
    if char_cutout_path and char_cutout_path.exists():
        char_img = Image.open(char_cutout_path).convert("RGBA")
        char_bbox = char_img.getbbox()
        if char_bbox:
            char_crop = char_img.crop(char_bbox)
            scale = target_char_height / char_crop.height
            tw = int(char_crop.width * scale)
            char_scaled = char_crop.resize((tw, target_char_height), Image.Resampling.LANCZOS)
            char_y = 1380 - target_char_height

            # Pedestal contact shadow
            shadow = Image.new("RGBA", scene.size, (0, 0, 0, 0))
            sdraw = ImageDraw.Draw(shadow)
            pw = int(tw * 0.72)
            pcx = char_x + tw // 2
            pcy = char_y + target_char_height - 15
            sdraw.ellipse([pcx - pw // 2, pcy - 18, pcx + pw // 2, pcy + 18], fill=(10, 15, 25, 130))
            shadow = shadow.filter(ImageFilter.GaussianBlur(12))

            scene.alpha_composite(shadow)
            scene.alpha_composite(char_scaled, (char_x, char_y))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    scene.convert("RGB").save(output_path, quality=95)
    print(f"[+] Successfully composited scene: {output_path} ({scene.size})")
    return output_path


def _find_contentflow_root(start: Path) -> Path:
    for parent in [start, *start.parents]:
        if (parent / "library").is_dir():
            return parent
    return Path(__file__).resolve().parents[3]


def batch_composite_project(
    project_dir: Path,
    bg_override: Optional[str] = None,
    board_override: Optional[str] = None,
    title: str = "CI/CD PIPELINE STATUS",
    badge: str = "ALL GREEN",
    subtitle: str = "自动化质量门禁与容器标准化交付",
) -> list[Path]:
    """Batch composite scenes for a project directory."""
    project_dir = project_dir.resolve()
    root_dir = _find_contentflow_root(project_dir)
    assets_dir = project_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    bg_path = (
        Path(bg_override)
        if bg_override
        else (
            assets_dir / "decomposed_layers" / "layer_0_z0_background.jpg"
            if (assets_dir / "decomposed_layers" / "layer_0_z0_background.jpg").exists()
            else root_dir / "library" / "scenes" / "cyber_classroom_clean_bg.jpg"
        )
    )
    board_path = (
        Path(board_override)
        if board_override
        else (
            assets_dir / "decomposed_layers" / "layer_1_z1_全息大屏底板.png"
            if (assets_dir / "decomposed_layers" / "layer_1_z1_全息大屏底板.png").exists()
            else root_dir / "library" / "props" / "holographic_whiteboard_chassis.png"
        )
    )

    cutouts = sorted(assets_dir.glob("*transparent*.png"))
    if not cutouts:
        cutouts = [p for p in sorted(assets_dir.glob("*.png")) if p.name != board_path.name]

    storyboard_scenes = []
    for sb_candidate in (
        project_dir / "output" / "copy" / "storyboard.json",
        project_dir / "delivery" / "storyboard.json",
    ):
        if sb_candidate.exists():
            try:
                storyboard_scenes = json.loads(sb_candidate.read_text(encoding="utf-8"))
                break
            except Exception:
                pass

    outputs: list[Path] = []
    if cutouts:
        for idx, char_p in enumerate(cutouts, 1):
            sc_meta = storyboard_scenes[idx - 1] if idx - 1 < len(storyboard_scenes) else {}
            sc_title = sc_meta.get("title", title)
            sc_sub = sc_meta.get("narration", subtitle)[:40] if sc_meta.get("narration") else subtitle
            out_p = assets_dir / f"composited_scene_{idx:02d}.jpg"
            outputs.append(
                render_scene(
                    bg_path=bg_path,
                    board_chassis_path=board_path,
                    char_cutout_path=char_p,
                    output_path=out_p,
                    title=sc_title,
                    badge=badge,
                    subtitle=sc_sub,
                )
            )
    else:
        out_p = assets_dir / "composited_scene_01.jpg"
        outputs.append(
            render_scene(
                bg_path=bg_path,
                board_chassis_path=board_path,
                char_cutout_path=None,
                output_path=out_p,
                title=title,
                badge=badge,
                subtitle=subtitle,
            )
        )
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Composite cyber classroom scene with whiteboard and character standee")
    parser.add_argument("--project-dir", default=None, help="Project directory for batch scene compositing")
    parser.add_argument("--bg", default=None, help="Path to clean classroom background (2560x1440)")
    parser.add_argument("--board", default=None, help="Path to whiteboard chassis (1389x781)")
    parser.add_argument("--char", default=None, help="Path to transparent character cutout")
    parser.add_argument("--output", default=None, help="Path to save composited scene image")
    parser.add_argument("--title", default="CI/CD PIPELINE STATUS", help="Whiteboard title")
    parser.add_argument("--badge", default="ALL GREEN", help="Whiteboard status badge")
    parser.add_argument("--subtitle", default="自动化质量门禁与容器标准化交付", help="Whiteboard subtitle")
    args = parser.parse_args()

    if args.project_dir:
        batch_composite_project(
            project_dir=Path(args.project_dir),
            bg_override=args.bg,
            board_override=args.board,
            title=args.title,
            badge=args.badge,
            subtitle=args.subtitle,
        )
        return

    if not (args.bg and args.board and args.char and args.output):
        parser.error("Either --project-dir or all of --bg, --board, --char, --output are required.")

    render_scene(
        bg_path=Path(args.bg),
        board_chassis_path=Path(args.board),
        char_cutout_path=Path(args.char),
        output_path=Path(args.output),
        title=args.title,
        badge=args.badge,
        subtitle=args.subtitle,
    )


if __name__ == "__main__":
    main()

