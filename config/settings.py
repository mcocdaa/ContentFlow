"""ContentFlow configuration settings.
Centralizes paths, default voice configs, channels, and integration with MoneyPrinterTurbo.
"""

from pathlib import Path
import os

CONTENTFLOW_ROOT = Path(__file__).resolve().parent.parent
VENDOR_DIR = CONTENTFLOW_ROOT / "vendor"
MONEYPRINTER_DIR = VENDOR_DIR / "MoneyPrinterTurbo"
MONEYPRINTER_VENV_PYTHON = MONEYPRINTER_DIR / ".venv" / "bin" / "python"
MONEYPRINTER_CLI = MONEYPRINTER_DIR / "cli.py"

PROJECTS_DIR = CONTENTFLOW_ROOT / "projects"
TEMPLATES_DIR = CONTENTFLOW_ROOT / "templates"
OUTPUT_DIR = CONTENTFLOW_ROOT / "output"

# Video generation presets
DEFAULT_VOICES = {
    "chinese_female_warm": "zh-CN-XiaoxiaoNeural",
    "chinese_male_narrator": "zh-CN-YunxiNeural",
    "chinese_male_deep": "zh-CN-YunyangNeural",
    "chinese_female_news": "zh-CN-XiaoyiNeural",
    "english_female": "en-US-JennyNeural",
    "english_male": "en-US-GuyNeural",
}

DEFAULT_FONTS = [
    "STHeitiMedium.ttc",
    "MicrosoftYaHeiNormal.ttc",
    "SimHei.ttf",
]

DEFAULT_ASPECT_RATIOS = {
    "landscape": "16:9",  # Bilibili, YouTube, Web, Presentation
    "portrait": "9:16",    # Douyin, TikTok, Xiaohongshu video, WeChat Channels
    "square": "1:1",       # Instagram, Feed
}
