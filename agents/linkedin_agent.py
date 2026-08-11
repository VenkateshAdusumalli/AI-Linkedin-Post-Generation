from google import genai

from config.settings import validate_config


def build_linkedin_prompt(transcript: str) -> str:
    return f"""
You are a professional LinkedIn content strategist.

Create a polished LinkedIn post based only on the transcript below.

Rules:
- Use a strong hook in the first 1-2 lines.
- Summarize the main idea clearly.
- Extract the most useful insights.
- Keep paragraphs short and easy to read.
- Do not invent any facts, examples, or claims.
- Add 3 to 5 relevant hashtags at the end.
- Keep the tone professional, insightful, and engaging for LinkedIn.
- Do not mention that you are an AI.

Transcript:
{transcript}
"""


def generate_linkedin_post(transcript: str) -> str:
    """Generate a LinkedIn post from transcript text using Gemini API."""
    config = validate_config()
    api_key = config["GEMINI_API_KEY"]

    try:
        client = genai.Client(api_key=api_key)
        prompt = build_linkedin_prompt(transcript)
        response = client.interactions.create(
            model="gemini-3.6-flash",
            input=prompt,
        )
    except Exception as exc:
        raise RuntimeError(f"Gemini API failure: {exc}") from exc

    output = getattr(response, "output_text", None)
    if not output:
        raise ValueError("Gemini returned no content.")

    return output.strip()
