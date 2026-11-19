"""ContentFlow configuration settings.
Centralizes paths, default voice configs, channels, and integration with MoneyPrinterTurbo.
"""

from pathlib import Path
import os

CONTENTFLOW_ROOT = Path(__file__).resolve().parent.parent


# Auto-load .env configuration if present
def _load_env_file(dotenv_path: Path):
    if not dotenv_path.exists():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(dotenv_path)
    except ImportError:
        with open(dotenv_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v


_load_env_file(CONTENTFLOW_ROOT / ".env")

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
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]

DEFAULT_ASPECT_RATIOS = {
    "landscape": "16:9",  # Bilibili, YouTube, Web, Presentation
    "portrait": "9:16",  # Douyin, TikTok, Xiaohongshu video, WeChat Channels
    "square": "1:1",  # Instagram, Feed
}

# External Audio Generation Router defaults (K4: MiniMax Speech/Music, Fish-Audio, Suno)
# Only non-secret env variable names, default endpoints, and default model IDs live here.
AUDIO_ROUTER_ENV_VARS = {
    "minimax_api_key": "MINIMAX_API_KEY",
    "minimax_group_id": "MINIMAX_GROUP_ID",
    "minimax_base_url": "MINIMAX_BASE_URL",
    "minimax_speech_model": "MINIMAX_SPEECH_MODEL",
    "minimax_music_model": "MINIMAX_MUSIC_MODEL",
    "fish_audio_api_key": "FISH_AUDIO_API_KEY",
    "fish_audio_base_url": "FISH_AUDIO_BASE_URL",
    "fish_audio_reference_id": "FISH_AUDIO_REFERENCE_ID",
    "suno_api_key": "SUNO_API_KEY",
    "suno_base_url": "SUNO_BASE_URL",
}

DEFAULT_MINIMAX_BASE_URL = "https://api.minimax.chat"
DEFAULT_MINIMAX_SPEECH_MODEL = "speech-02-hd"
DEFAULT_MINIMAX_SPEECH_VOICE = "female-shaonv"
DEFAULT_MINIMAX_MUSIC_MODEL = "music-01"
DEFAULT_FISH_AUDIO_BASE_URL = "https://api.fish.audio"
DEFAULT_SUNO_BASE_URL = "https://api.sunoapi.org"

AUDIO_SPEECH_PROVIDER_PRIORITY = ("minimax_speech", "fish_audio", "local_kokoro")
AUDIO_MUSIC_PROVIDER_PRIORITY = ("minimax_music", "suno", "bilibili_bgm_hunter")
