"""Asset Builder for ContentFlow.
Generates clean, aesthetic presentation graphics and converts static assets
into video clips using accelerated ffmpeg pipelines for maximum performance.
"""

from pathlib import Path
import subprocess
import os
from typing import List, Tuple, Optional
try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image, ImageDraw, ImageFont = None, None, None


class AssetBuilder:
    """Creates visual assets and converts images to video clips."""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def create_scene_slide(
        self,
        scene_id: int,
        title: str,
        subtitle: str,
        bullets: List[str],
        size: Tuple[int, int] = (1920, 1080),
        accent_color: Tuple[int, int, int] = (59, 130, 246),
        bg_color: Tuple[int, int, int] = (15, 23, 42),
    ) -> Path:
        """Draws a clean, dark-mode presentation slide."""
        width, height = size
        img = Image.new("RGB", (width, height), color=bg_color)
        draw = ImageDraw.Draw(img)

        # Subtle gradient / card overlay
        card_margin_x = int(width * 0.08)
        card_margin_y = int(height * 0.1)
        card_rect = [
            card_margin_x,
            card_margin_y,
            width - card_margin_x,
            height - card_margin_y,
        ]
        draw.rounded_rectangle(
            card_rect,
            radius=24,
            fill=(30, 41, 59),
            outline=(51, 65, 85),
            width=2,
        )

        # Scene badge
        badge_x = card_margin_x + 50
        badge_y = card_margin_y + 50
        draw.rounded_rectangle(
            [badge_x, badge_y, badge_x + 140, badge_y + 40],
            radius=12,
            fill=accent_color,
        )
        draw.text(
            (badge_x + 24, badge_y + 10),
            f"SCENE 0{scene_id}",
            fill=(255, 255, 255),
        )

        # Title
        title_y = badge_y + 60
        draw.text(
            (badge_x, title_y),
            title,
            fill=(255, 255, 255),
        )

        # Subtitle
        sub_y = title_y + 60
        draw.text(
            (badge_x, sub_y),
            subtitle,
            fill=(148, 163, 184),
        )

        # Horizontal separator
        sep_y = sub_y + 50
        draw.line(
            [(badge_x, sep_y), (width - card_margin_x - 50, sep_y)],
            fill=(51, 65, 85),
            width=2,
        )

        # Bullet points
        start_bullet_y = sep_y + 40
        for i, bullet in enumerate(bullets[:4]):
            by = start_bullet_y + i * 55
            # Bullet dot
            draw.ellipse([badge_x + 4, by + 6, badge_x + 16, by + 18], fill=accent_color)
            draw.text((badge_x + 36, by), bullet, fill=(226, 232, 240))

        # Brand / Watermark footer
        footer_text = "ContentFlow • Automated Multi-Modal Production"
        draw.text(
            (badge_x, height - card_margin_y - 45),
            footer_text,
            fill=(100, 116, 139),
        )

        slide_path = self.output_dir / f"slide_{scene_id:02d}.png"
        img.save(slide_path, quality=95)
        return slide_path

    def convert_image_to_mp4_fast(
        self,
        image_path: Path,
        duration: float = 5.0,
        size: Tuple[int, int] = (1920, 1080),
        fps: int = 30,
    ) -> Path:
        """Converts an image into an MP4 video clip using native ffmpeg in <0.3s.
        This bypasses MoviePy's slow CPU frame-by-frame resize while delivering
        broadcast-grade H.264 video.
        """
        image_path = Path(image_path)
        output_mp4 = self.output_dir / f"{image_path.stem}.mp4"
        w, h = size

        cmd = [
            "ffmpeg",
            "-y",
            "-loop", "1",
            "-i", str(image_path),
            "-t", str(duration),
            "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
            "-r", str(fps),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "stillimage",
            "-pix_fmt", "yuv420p",
            str(output_mp4),
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg conversion failed: {result.stderr.decode('utf-8', errors='ignore')}")

        return output_mp4
