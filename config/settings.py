import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def get_setting(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    if value is None:
        return None
    return value.strip() if isinstance(value, str) else value


YOUTUBE_API_KEY = get_setting("YOUTUBE_API_KEY")
GEMINI_API_KEY = get_setting("GEMINI_API_KEY")
YOUTUBE_CHANNEL_ID = get_setting("YOUTUBE_CHANNEL_ID", "UClXAalunTPaX1YV185DWUeg")


def validate_config() -> dict:
    """Validate required settings and return them as a dictionary."""
    config = {
        "YOUTUBE_API_KEY": get_setting("YOUTUBE_API_KEY"),
        "GEMINI_API_KEY": get_setting("GEMINI_API_KEY"),
        "YOUTUBE_CHANNEL_ID": get_setting("YOUTUBE_CHANNEL_ID", "UClXAalunTPaX1YV185DWUeg"),
    }

    missing = [name for name, value in config.items() if not value]
    if missing:
        raise ValueError(
            "Missing required environment variables: " + ", ".join(missing)
        )

    return config
