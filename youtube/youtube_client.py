from googleapiclient.discovery import build

from config.settings import YOUTUBE_API_KEY, validate_config


def get_channel_details(channel_id: str) -> dict:
    """Return basic channel metadata from YouTube Data API."""
    if not channel_id:
        raise ValueError("channel_id is required")
    
    config = validate_config()

    try:
        youtube = build("youtube", "v3", developerKey=config["YOUTUBE_API_KEY"])
        response = youtube.channels().list(
            part="snippet,statistics",
            id=channel_id,
        ).execute()
    except Exception as exc:
        raise RuntimeError(f"YouTube API failure: {exc}") from exc

    items = response.get("items", [])
    if not items:
        raise LookupError(f"Channel not found: {channel_id}")

    channel = items[0]
    return {
        "channel_id": channel["id"],
        "title": channel["snippet"]["title"],
        "subscriber_count": channel["statistics"].get("subscriberCount", "0"),
        "video_count": channel["statistics"].get("videoCount", "0"),
        "view_count": channel["statistics"].get("viewCount", "0"),
    }


def get_candidate_videos(channel_id: str, max_results: int = 5) -> list[dict]:
    """Return multiple recent videos for the specified channel (newest first).
    
    Args:
        channel_id: YouTube channel ID to check for videos
        max_results: Maximum number of videos to return (default 5)
    
    Returns:
        list of dicts with keys: video_id, title, published_at, description
    
    Raises:
        ValueError: if channel_id is not provided
        RuntimeError: if YouTube API call fails
        ValueError: if no videos found for channel
    """
    if not channel_id:
        raise ValueError("channel_id is required")
    
    config = validate_config()

    try:
        youtube = build("youtube", "v3", developerKey=config["YOUTUBE_API_KEY"])
        response = youtube.search().list(
            part="snippet",
            channelId=channel_id,
            type="video",
            order="date",
            maxResults=max_results,
        ).execute()
    except Exception as exc:
        raise RuntimeError(f"YouTube API failure: {exc}") from exc

    items = response.get("items", [])
    if not items:
        raise ValueError(f"No videos found for channel: {channel_id}")

    videos = []
    for video in items:
        videos.append({
            "video_id": video["id"]["videoId"],
            "title": video["snippet"]["title"],
            "description": video["snippet"].get("description", ""),
            "published_at": video["snippet"].get("publishedAt"),
        })
    
    return videos


def get_latest_video(channel_id: str) -> dict:
    """Return the newest public video for the specified channel.
    
    Args:
        channel_id: YouTube channel ID to check for latest video
    
    Returns:
        dict with keys: video_id, title, published_at
    
    Raises:
        ValueError: if channel_id is not provided
        RuntimeError: if YouTube API call fails
        ValueError: if no videos found for channel
    """
    if not channel_id:
        raise ValueError("channel_id is required")
    
    config = validate_config()

    try:
        youtube = build("youtube", "v3", developerKey=config["YOUTUBE_API_KEY"])
        response = youtube.search().list(
            part="snippet",
            channelId=channel_id,
            type="video",
            order="date",
            maxResults=1,
        ).execute()
    except Exception as exc:
        raise RuntimeError(f"YouTube API failure: {exc}") from exc

    items = response.get("items", [])
    if not items:
        raise ValueError(f"No videos found for channel: {channel_id}")

    video = items[0]
    return {
        "video_id": video["id"]["videoId"],
        "title": video["snippet"]["title"],
        "published_at": video["snippet"].get("publishedAt"),
    }
