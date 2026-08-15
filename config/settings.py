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
CLOUDFLARE_ACCOUNT_ID = get_setting("CLOUDFLARE_ACCOUNT_ID")
CLOUDFLARE_API_TOKEN = get_setting("CLOUDFLARE_API_TOKEN")


def get_channels() -> list[dict]:
    """
    Load YouTube channels from environment variables in priority order.
    
    Expected format:
        CHANNEL_1_NAME=Channel Name
        CHANNEL_1_ID=ChannelID
        CHANNEL_2_NAME=Another Channel
        CHANNEL_2_ID=AnotherID
        ...
    
    Returns list of channels in priority order.
    """
    channels = []
    channel_num = 1
    
    while True:
        name = get_setting(f"CHANNEL_{channel_num}_NAME")
        channel_id = get_setting(f"CHANNEL_{channel_num}_ID")
        
        if not name or not channel_id:
            break
        
        channels.append({
            "name": name,
            "id": channel_id,
            "priority": channel_num,
        })
        channel_num += 1
    
    return channels


def validate_config() -> dict:
    """Validate required settings and return them as a dictionary."""
    config = {
        "YOUTUBE_API_KEY": get_setting("YOUTUBE_API_KEY"),
        "GEMINI_API_KEY": get_setting("GEMINI_API_KEY"),
        "CLOUDFLARE_ACCOUNT_ID": get_setting("CLOUDFLARE_ACCOUNT_ID"),
        "CLOUDFLARE_API_TOKEN": get_setting("CLOUDFLARE_API_TOKEN"),
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

    # Check that at least one channel is configured
    channels = get_channels()
    if not channels:
        raise ValueError(
            "No YouTube channels configured. Add CHANNEL_1_NAME, CHANNEL_1_ID, etc. to .env"
        )

    return config
