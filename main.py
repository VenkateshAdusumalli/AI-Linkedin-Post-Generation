from agents.image_agent import generate_linkedin_image
from agents.linkedin_agent import generate_linkedin_post
from youtube.transcript import extract_transcript
from youtube.youtube_client import get_latest_video


def main() -> None:
    try:
        print("Checking YouTube channel...")
        latest_video = get_latest_video()

        video_id = latest_video["video_id"]
        title = latest_video["title"]

        print("New/latest video found:")
        print(title)
        print()

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

    except ValueError as exc:
        print(f"Configuration error: {exc}")
        print("Update the values in .env with your real API keys, then run: python main.py")
    except Exception as exc:
        print(f"Runtime error: {exc}")


if __name__ == "__main__":
    main()
