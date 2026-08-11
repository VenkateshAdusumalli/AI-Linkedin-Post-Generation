import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

PLACEHOLDER_KEYS = {
    "your_youtube_key",
    "your_gemini_key",
    "your_api_key",
    "your_key",
    "changeme",
    "replace_me",
}


def get_setting(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    if value is None:
        return None
    return value.strip() if isinstance(value, str) else value


def is_placeholder(value: str | None) -> bool:
    if not value:
        return True
    normalized = value.strip().lower()
    return normalized in PLACEHOLDER_KEYS or normalized.startswith("your_")


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

    placeholder_names = [
        name for name, value in config.items() if is_placeholder(value)
    ]
    if placeholder_names:
        raise ValueError(
            "Replace placeholder values in .env with your real API keys: "
            + ", ".join(placeholder_names)
        )

    return config
