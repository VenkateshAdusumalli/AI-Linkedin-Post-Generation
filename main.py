from agents.linkedin_agent import generate_linkedin_post
from youtube.transcript import extract_transcript
from youtube.youtube_client import get_latest_video


def main() -> None:
    print("Checking YouTube channel...")

    try:
        latest_video = get_latest_video()
    except Exception as exc:
        raise RuntimeError(f"Could not fetch latest video: {exc}") from exc

    video_id = latest_video["video_id"]
    title = latest_video["title"]

    print("New/latest video found:")
    print(title)
    print()

    print("Getting transcript...")
    try:
        transcript = extract_transcript(video_id)
        print("Transcript retrieved successfully.")
    except Exception as exc:
        raise RuntimeError(f"Transcript extraction failed: {exc}") from exc

    print()
    print("Generating LinkedIn post...")
    try:
        linkedin_post = generate_linkedin_post(transcript)
        print("LinkedIn post generated successfully.")
    except Exception as exc:
        raise RuntimeError(f"LinkedIn post generation failed: {exc}") from exc

    print()
    print("-" * 30)
    print("GENERATED LINKEDIN POST")
    print("-" * 30)
    print(linkedin_post)


if __name__ == "__main__":
    main()
