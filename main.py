from pathlib import Path

from database.database import init_database, is_video_processed, save_processed_video
from agents.image_agent import generate_linkedin_image
from agents.linkedin_agent import generate_linkedin_post
from agents.content_analyzer import analyze_transcript_quality, analyze_video_content
from agents.frame_extractor import get_visual_analysis
from config.settings import get_channels, validate_config
from linkedin.linkedin_client import publish_linkedin_post
from youtube.transcript import extract_transcript
from youtube.youtube_client import get_candidate_videos


MAX_CANDIDATE_VIDEOS = 5

# HIGH-transcript videos still need frames when the content is visual/demo-like
# or the transcript is short (common for Shorts). Avoids extra YouTube quota calls.
VISUAL_KEYWORDS = {
    "short", "shorts", "demo", "demonstration", "workflow", "robot",
    "inside", "look", "shows", "show", "build", "farm", "factory",
    "test", "review", "unboxing", "tour",
}


def needs_visual_analysis(transcript: str | None, title: str, transcript_quality: str) -> bool:
    """Decide whether frame analysis is worth the download cost."""
    if transcript_quality in ["LOW", "MEDIUM"]:
        return True
    if len(transcript or "") < 1400:
        return True
    lowered = (title or "").lower()
    return any(keyword in lowered for keyword in VISUAL_KEYWORDS)


def get_candidate_videos_for_channel(channel: dict, max_candidates: int = MAX_CANDIDATE_VIDEOS) -> list[dict]:
    """
    Get candidate videos from a channel, filtering out already-processed ones.
    
    Args:
        channel: dict with 'name' and 'id' keys
        max_candidates: Maximum number of unprocessed videos to return
    
    Returns:
        list of unprocessed video dicts, newest first
    
    Raises:
        ValueError: if no videos found
    """
    try:
        all_videos = get_candidate_videos(channel["id"], max_results=max_candidates + 5)
    except ValueError as exc:
        raise ValueError(f"No videos found for {channel['name']}: {exc}") from exc
    except RuntimeError as exc:
        raise RuntimeError(f"YouTube lookup failed for {channel['name']}: {exc}") from exc
    
    # Filter out already-processed videos
    unprocessed = [v for v in all_videos if not is_video_processed(v["video_id"])]
    
    return unprocessed[:max_candidates]


def evaluate_video_quality(video: dict) -> dict:
    """
    Evaluate the quality of a video's content.
    
    Args:
        video: dict with 'video_id', 'title', 'description' keys
    
    Returns:
        dict with evaluation results:
            - quality: str ("GOOD", "POOR")
            - reason: str
            - transcript_quality: str ("HIGH", "MEDIUM", "LOW")
            - analysis: dict (Gemini analysis results)
    """
    video_id = video["video_id"]
    title = video["title"]
    description = video.get("description", "")
    
    print(f"  Evaluating: {title}")
    
    try:
        # Step 1: Get transcript
        print("    Checking transcript quality...")
        transcript = extract_transcript(video_id)
        
        # Step 2: Analyze transcript quality
        transcript_analysis = analyze_transcript_quality(transcript, title, description)
        transcript_quality = transcript_analysis.get("transcript_quality", "LOW")
        
        print(f"    Transcript quality: {transcript_quality}")
        
        # Step 3: Extract visual information when transcript is weak
        # or the video looks visual/demo-like even with a HIGH transcript
        visual_info = None
        if needs_visual_analysis(transcript, title, transcript_quality):
            print("    Analyzing selected video frames...")
            visual_info = get_visual_analysis(video_id, transcript)
            if visual_info:
                print("    Frames analyzed.")
        
        # Step 4: Use Gemini to analyze overall content
        print("    Analyzing content with Gemini...")
        content_analysis = analyze_video_content(transcript, title, description, visual_info)
        
        quality = content_analysis.get("content_quality", "POOR")
        reason = content_analysis.get("reason", "Content analysis inconclusive")
        
        print(f"    Content quality: {quality}")
        if reason:
            print(f"    Reason: {reason}")
        
        return {
            "quality": quality,
            "reason": reason,
            "transcript_quality": transcript_quality,
            "analysis": content_analysis,
            "transcript": transcript,
            "visual_info": visual_info,
            "title": title,
            "description": description,
        }

    except Exception as exc:
        print(f"    Error evaluating video: {exc}")
        return {
            "quality": "POOR",
            "reason": f"Evaluation failed: {exc}",
            "transcript_quality": "UNKNOWN",
            "analysis": None,
            "transcript": None,
            "visual_info": None,
            "title": title,
            "description": description,
        }


def find_suitable_video_in_channel(channel: dict, max_candidates: int = MAX_CANDIDATE_VIDEOS) -> dict | None:
    """
    Find a suitable video in the channel by evaluating candidates.
    
    Args:
        channel: Channel dict with 'name' and 'id'
        max_candidates: Max videos to evaluate per channel
    
    Returns:
        dict with video and quality info, or None if no suitable video found
    """
    try:
        candidates = get_candidate_videos_for_channel(channel, max_candidates)
    except (ValueError, RuntimeError) as exc:
        print(f"  {exc}")
        return None
    except Exception as exc:
        print(f"  Unexpected error checking channel {channel.get('name')}: {exc}")
        return None
    
    if not candidates:
        print(f"  No new unprocessed videos found.")
        return None
    
    print(f"  Found {len(candidates)} new unprocessed video(s).")
    print()
    
    # Evaluate each candidate from newest to oldest
    for candidate in candidates:
        evaluation = evaluate_video_quality(candidate)
        
        if evaluation["quality"] == "GOOD":
            print()
            print(f"  [OK] Selected video: {candidate['title']}")
            return {
                "video": candidate,
                "evaluation": evaluation,
            }
        else:
            print(f"  [SKIP] Skipping due to poor content quality.")
            print()
    
    return None


def process_video(video: dict, evaluation: dict) -> None:
    """
    Process a single video through the entire pipeline.
    
    This should only be called after video quality has been verified as GOOD.
    
    Args:
        video: dict with 'video_id' and 'title' keys
        evaluation: dict with quality evaluation results
    
    Raises:
        Exception: if any step in the pipeline fails
    """
    video_id = video["video_id"]
    title = video["title"]
    
    # Use transcript and understanding from evaluation if available
    transcript = evaluation.get("transcript")
    if not transcript:
        print("Getting transcript...")
        transcript = extract_transcript(video_id)
        print("Transcript retrieved successfully.")

    understanding = evaluation.get("analysis")
    visual_info = evaluation.get("visual_info")
    video_title = evaluation.get("title") or video.get("title", "")
    video_description = evaluation.get("description") or video.get("description", "")

    print()
    print("Generating LinkedIn post from video understanding...")
    linkedin_post = generate_linkedin_post(
        transcript,
        understanding=understanding,
        video_title=video_title,
        video_description=video_description,
        visual_info=visual_info,
    )
    print("LinkedIn post generated successfully.")

    print()
    print("Generating image...")
    image_path = generate_linkedin_image(linkedin_post, understanding)
    print("Image generated successfully.")

    print()
    print("Publishing to LinkedIn...")
    post_urn = publish_linkedin_post(linkedin_post, image_path)
    print(f"LinkedIn post published successfully. Post URN: {post_urn}")

    try:
        Path(image_path).unlink(missing_ok=True)
    except OSError as exc:
        print(f"Warning: could not remove temporary image: {exc}")

    print()
    print("-" * 30)
    print("GENERATED LINKEDIN POST")
    print("-" * 30)
    print(linkedin_post)
    print()
    print("Temporary Image:")
    print(image_path)


def main() -> None:
    """
    Main pipeline with smart video selection and content quality evaluation.
    
    Flow:
    1. Check Priority 1 for new suitable videos (newest to oldest)
    2. If suitable video found in Priority 1, process it
    3. If no suitable video in Priority 1, check Priority 2
    4. Only mark video as PROCESSED after complete pipeline success
    """
    try:
        init_database()
        validate_config()
        channels = get_channels()

        print("=" * 60)
        print("YouTube Multi-Channel Priority Check")
        print("Smart Video Selection + Content Quality Evaluation")
        print("=" * 60)
        print()

        video_processed = False

        for channel in channels:
            print(f"Checking Priority {channel['priority']}: {channel['name']}")
            print()

            # Find a suitable video in this channel
            result = find_suitable_video_in_channel(channel, max_candidates=MAX_CANDIDATE_VIDEOS)

            if not result:
                print(f"Priority {channel['priority']}: No suitable new video found.")
                print()
                continue

            video = result["video"]
            evaluation = result["evaluation"]
            video_id = video["video_id"]

            print()
            print("=" * 60)
            print("PROCESSING VIDEO")
            print("=" * 60)
            print(f"Title: {video['title']}")
            print(f"Video ID: {video_id}")
            print()

            try:
                # Process the video through the full pipeline
                process_video(video, evaluation)

                print()
                print("=" * 60)
                print("Saving video to database...")
                save_processed_video(
                    channel_id=channel["id"],
                    video_id=video_id,
                    video_title=video["title"],
                    published_at=video.get("published_at"),
                    understanding=evaluation.get("analysis"),
                )
                print("[OK] Video successfully processed and saved.")
                print()
                video_processed = True
                print(f"Priority {channel['priority']} had a suitable video. Stopping here.")
                break

            except Exception as exc:
                print()
                print(f"[FAIL] Error during processing: {exc}")
                print(f"Video NOT marked as processed. Will retry on next run.")
                print()
                # Continue to next channel if processing fails
                continue

        if not video_processed:
            print()
            print("=" * 60)
            print("No suitable videos found on any channel.")
            print("=" * 60)

    except ValueError as exc:
        print(f"Configuration error: {exc}")
        print("Update the values in .env with your real API keys, then run: python main.py")
    except Exception as exc:
        print(f"Runtime error: {exc}")


if __name__ == "__main__":
    main()
