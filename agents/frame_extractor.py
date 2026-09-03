"""Video frame extraction module for content analysis."""

import tempfile
from pathlib import Path

import cv2
from google import genai
from google.genai import types

from config.settings import validate_config


def _download_video(video_id: str) -> str:
    """
    Download video from YouTube using yt-dlp.
    
    Args:
        video_id: YouTube video ID
    
    Returns:
        Path to downloaded video file
    
    Raises:
        RuntimeError: if download fails
    """
    try:
        import yt_dlp
    except ImportError:
        raise RuntimeError("yt-dlp not installed. Install with: pip install yt-dlp")
    
    temp_dir = tempfile.gettempdir()
    output_path = Path(temp_dir) / f"video_{video_id}.mp4"
    
    if output_path.exists():
        return str(output_path)
    
    url = f"https://www.youtube.com/watch?v={video_id}"
    
    ydl_opts = {
        "format": "best[height<=720]",
        "quiet": True,
        "no_warnings": True,
        "outtmpl": str(Path(temp_dir) / f"video_{video_id}"),
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as exc:
        raise RuntimeError(f"Failed to download video {video_id}: {exc}") from exc
    
    # Find the downloaded file (yt-dlp adds extension)
    for ext in [".mp4", ".webm", ".mkv"]:
        candidate = Path(temp_dir) / f"video_{video_id}{ext}"
        if candidate.exists():
            return str(candidate)
    
    raise RuntimeError(f"Downloaded video not found for {video_id}")


def extract_representative_frames(video_id: str, max_frames: int = 6) -> list[tuple[float, bytes]]:
    """
    Extract representative frames from a video at key percentages.
    
    Args:
        video_id: YouTube video ID
        max_frames: Maximum number of frames to extract (default 6)
    
    Returns:
        List of tuples (timestamp_seconds, frame_bytes_jpeg) for each frame
    
    Raises:
        RuntimeError: if frame extraction fails
    """
    try:
        video_path = _download_video(video_id)
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open video: {video_path}")
        
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        
        if total_frames <= 0:
            raise RuntimeError(f"Video has no frames: {video_path}")
        
        # Calculate frame positions as percentages
        percentages = [10, 25, 40, 55, 70, 85][:max_frames]
        frames = []
        
        for percentage in percentages:
            frame_num = int((percentage / 100.0) * total_frames)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            
            ret, frame = cap.read()
            if ret:
                # Resize frame for faster processing
                frame = cv2.resize(frame, (640, 360))
                
                # Encode as JPEG
                _, jpeg_bytes = cv2.imencode(".jpg", frame)
                frame_b64 = jpeg_bytes.tobytes()
                
                timestamp = frame_num / fps if fps > 0 else 0
                frames.append((timestamp, frame_b64))
        
        cap.release()
        
        return frames
    
    except cv2.error as exc:
        raise RuntimeError(f"OpenCV error during frame extraction: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"Frame extraction failed: {exc}") from exc
    finally:
        # Clean up temporary video file
        try:
            temp_dir = Path(tempfile.gettempdir())
            video_file = temp_dir / f"video_{video_id}.mp4"
            if video_file.exists():
                video_file.unlink()
        except Exception:
            pass


def analyze_frames_with_gemini(frames: list[tuple[float, bytes]]) -> str:
    """
    Send extracted frames to Gemini for visual analysis.
    
    Args:
        frames: List of tuples (timestamp_seconds, frame_bytes_jpeg)
    
    Returns:
        Text analysis of what the frames show
    
    Raises:
        RuntimeError: if Gemini analysis fails
    """
    if not frames:
        return ""

    config = validate_config()
    api_key = config["GEMINI_API_KEY"]

    prompt = f"""Analyze these {len(frames)} representative frames from a video and describe what they show.

Focus on:
1. Main subjects or objects visible (be specific: e.g. warehouse vertical farm, robotic grid, LED arrays)
2. Important visual information (charts, graphs, on-screen text, demonstrations)
3. Scene context (lab, office, warehouse, farm, outdoor, etc.)
4. Any processes or actions being demonstrated
5. Overall visual narrative

Return 2-4 concise sentences plus a final line: "Objects: <comma-separated visible objects>; Environment: <context>"."""

    try:
        client = genai.Client(api_key=api_key)

        image_parts = [
            types.Part.from_bytes(data=frame_bytes, mime_type="image/jpeg")
            for _, frame_bytes in frames
        ]
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=[prompt, *image_parts],
        )
        output = getattr(response, "text", "") or ""
        return output.strip() if output else ""
    except Exception as exc:
        print(f"  Warning: frame vision analysis failed: {type(exc).__name__}: {exc}")
        return ""


def get_visual_analysis(video_id: str, transcript: str | None = None) -> str:
    """
    Extract frames from video and analyze them visually.
    
    This is used when transcript quality is poor or visual information seems important.
    
    Args:
        video_id: YouTube video ID
        transcript: Optional transcript to assess if visual analysis is needed
    
    Returns:
        Text description of visual information from frames
    """
    try:
        print("  Extracting video frames...")
        frames = extract_representative_frames(video_id, max_frames=6)
        
        if not frames:
            print("  No frames extracted.")
            return ""
        
        print(f"  Analyzing {len(frames)} frames with Gemini...")
        analysis = analyze_frames_with_gemini(frames)
        
        return analysis
    
    except Exception as exc:
        print(f"  Warning: visual analysis skipped: {type(exc).__name__}: {exc}")
        return ""
