from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter


def extract_transcript(video_id: str) -> str:
    """Fetch and clean transcript text for a YouTube video."""
    if not video_id:
        raise ValueError("Video ID is required to fetch transcript.")

    try:
        transcript = YouTubeTranscriptApi().fetch(video_id)
    except Exception as exc:
        raise RuntimeError(f"Transcript unavailable for video {video_id}: {exc}") from exc

    formatted = TextFormatter().format_transcript(transcript)
    cleaned = " ".join(formatted.split())
    if not cleaned:
        raise ValueError(f"Transcript is empty for video {video_id}")

    return cleaned
