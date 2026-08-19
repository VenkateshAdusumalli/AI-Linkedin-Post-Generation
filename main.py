from database.database import init_database, is_video_processed, save_processed_video
from agents.image_agent import generate_linkedin_image
from agents.linkedin_agent import generate_linkedin_post
from config.settings import get_channels, validate_config
from youtube.transcript import extract_transcript
from youtube.youtube_client import get_latest_video


def check_channel_for_new_video(channel: dict) -> dict | None:
    """
    Check a single channel for the latest video.
    
    Args:
        channel: dict with 'name' and 'id' keys
    
    Returns:
        dict with video info, or None if no video found or error occurs
    """
    try:
        video = get_latest_video(channel["id"])
        return video
    except (ValueError, RuntimeError) as exc:
        print(f"  Error checking {channel['name']}: {exc}")
        return None


def process_video(video: dict) -> None:
    """
    Process a single video through the entire pipeline.
    
    Args:
        video: dict with 'video_id' and 'title' keys
    """
    video_id = video["video_id"]
    title = video["title"]

    print(f"New video found: {title}")
    print()

    try:
        print("Getting transcript...")
        transcript = extract_transcript(video_id)
        print("Transcript retrieved successfully.")

        print()
        print("Generating LinkedIn post...")
        linkedin_post = generate_linkedin_post(transcript)
        print("LinkedIn post generated successfully.")

        print()
        print("Generating image prompt...")
        image_path = generate_linkedin_image(linkedin_post)
        print("Image generated successfully.")

        print()
        print("-" * 30)
        print("GENERATED LINKEDIN POST")
        print("-" * 30)
        print(linkedin_post)
        print()
        print("Temporary Image:")
        print(image_path)

    except Exception as exc:
        print(f"Error processing video: {exc}")
        raise


def main() -> None:
    try:
        init_database()
        validate_config()
        channels = get_channels()

        print("=" * 50)
        print("YouTube Multi-Channel Priority Check")
        print("=" * 50)
        print()

        # Check channels in priority order
        video_found = False

        for channel in channels:
            print(f"Checking Priority {channel['priority']}: {channel['name']}")

            video = check_channel_for_new_video(channel)

            if not video:
                print("  No new video found.")
                print()
                continue

            video_id = video["video_id"]
            print(f"  Latest video: {video['title']}")
            print(f"  Video ID: {video_id}")

            if is_video_processed(video_id):
                print("  Already processed. Skipping.")
                print()
                continue

            print("  New video found.")
            print()
            process_video(video)

            print()
            print("Saving video to database...")
            save_processed_video(
                channel_id=channel["id"],
                video_id=video_id,
                video_title=video["title"],
                published_at=video.get("published_at"),
            )
            print("Processing completed successfully.")
            video_found = True
            print()
            print(f"Priority {channel['priority']} had a new video. Stopping here.")
            break

        if not video_found:
            print("No new videos found on any channel.")

    except ValueError as exc:
        print(f"Configuration error: {exc}")
        print("Update the values in .env with your real API keys, then run: python main.py")
    except Exception as exc:
        print(f"Runtime error: {exc}")


if __name__ == "__main__":
    main()
