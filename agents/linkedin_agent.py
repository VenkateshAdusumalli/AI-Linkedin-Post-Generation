import re

from google import genai

from config.settings import validate_config


BANNED_PHRASES = [
    "delve",
    "game-changer",
    "game changer",
    "revolutionary",
    "cutting-edge",
    "cutting edge",
    "unlock the",
    "unlocking the",
    "in today's fast-paced world",
    "in todays fast-paced world",
]


def _sanitize_plain_text(text: str) -> str:
    """Enforce plain-text LinkedIn output (no Markdown/HTML/bold)."""
    cleaned = text.strip()
    # Remove bold/italic markers but keep inner text
    cleaned = re.sub(r"\*\*(.+?)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"__(.+?)__", r"\1", cleaned)
    cleaned = cleaned.replace("`", "")
    # Remove HTML tags
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    # Remove Markdown heading markers at line start, preserving hashtags (#Word)
    lines = []
    for line in cleaned.splitlines():
        lines.append(re.sub(r"^\s*#{1,6}\s+", "", line))
    cleaned = "\n".join(lines)
    # Collapse 3+ blank lines to max 2
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _format_understanding(understanding: dict | None) -> str:
    """Render the understanding layer as prompt context."""
    if not understanding:
        return ""

    def get(key: str, default: str = "") -> str:
        value = understanding.get(key, default)
        if isinstance(value, list):
            return "; ".join(str(v) for v in value)
        return str(value) if value else default

    return f"""VIDEO UNDERSTANDING (use this as the primary source of meaning):
- MAIN THEME: {get("main_theme") or get("main_topic")}
- CORE MESSAGE: {get("core_message")}
- CENTRAL IDEA: {get("central_idea")}
- UNDERLYING INSIGHT: {get("underlying_insight")}
- PROBLEM / CHANGE / TREND: {get("problem_or_change")}
- PRODUCT OR COMPANY: {get("product_or_company")}
- PRODUCT ROLE (how the product relates to the central idea): {get("product_role")}
- KEY FACTS (only factual claims you may use): {get("key_facts")}
- IMPORTANT NUMBERS (use only if genuinely relevant): {get("important_numbers")}
- WHAT THE VIDEO ACTUALLY DEMONSTRATES: {get("what_video_demonstrates")}
- VISUAL INFORMATION (may not be in transcript): {get("visual_information") or get("visual_info", "")}
"""


STYLE_RULES = """Rules:
- First line is the hook: under 150 characters, concrete and specific. No clickbait question, no "In today's fast-paced world".
- Target 150-250 words. Keep paragraphs short (1-3 sentences) and easy to scan.
- Write around the MAIN THEME, CENTRAL IDEA, and UNDERLYING INSIGHT, not around a list of transcript details.
- Use KEY FACTS and PRODUCT CONTEXT only to support the central idea. Do NOT turn the post into a product feature summary.
- Do NOT automatically make the product the main theme. Respect PRODUCT ROLE.
- Treat the transcript as EVIDENCE only. Do NOT copy any phrase longer than 8 words from it. Write original wording.
- Do not invent any facts, examples, numbers, or claims beyond KEY FACTS / IMPORTANT NUMBERS.
- Never use these phrases: delve, game-changer/game changer, revolutionary, cutting-edge/cutting edge, unlock the/unlocking the.
- End with a one-line takeaway, then one discussion question (CTA), then 3 to 5 hashtags (mix of niche + broad).
- Keep the tone professional, insightful, and engaging for LinkedIn.
- Do not mention that you are an AI.
- Output plain text ONLY. No Markdown, no **bold**, no *italic*, no # headings, no HTML. Normal line breaks are fine. Simple bullets only when genuinely useful."""


def build_linkedin_prompt(
    transcript: str,
    understanding: dict | None = None,
    video_title: str = "",
    video_description: str = "",
    visual_info: str | None = None,
) -> str:
    if not understanding:
        # Fallback: legacy transcript-only path (kept for backward compatibility)
        return f"""
You are a professional LinkedIn content strategist.

Create a polished LinkedIn post based only on the transcript below.

Rules:
- First line is the hook: under 150 characters, concrete and specific.
- Target 150-250 words with short paragraphs.
- Extract the most useful insights without inventing facts.
- Never use: delve, game-changer, revolutionary, cutting-edge, unlock the.
- End with a one-line takeaway, one discussion question, then 3 to 5 hashtags.
- Do not mention that you are an AI.
- Output plain text ONLY. No Markdown, no **bold**, no *italic*, no headings, no HTML.

Transcript:
{transcript}
"""

    visual_section = f"\nAdditional visual context:\n{visual_info}" if visual_info else ""
    title_section = f"\nVideo title: {video_title}" if video_title else ""
    understanding_section = _format_understanding(understanding)

    return f"""
You are a professional LinkedIn content strategist.

Someone watched a YouTube video, understood its central idea, thought about why it matters, and now writes an original LinkedIn post. Write like that person.

{understanding_section}{title_section}{visual_section}

{STYLE_RULES}

Transcript (evidence only, do not rewrite it):
{transcript}
"""


def validate_and_repair_post(post: str, understanding: dict | None = None) -> str:
    """Second Gemini pass: grounding, style, and plain-text check.

    Returns a repaired post, or the sanitized original if validation fails
    (never breaks the pipeline).
    """
    config = validate_config()
    api_key = config["GEMINI_API_KEY"]
    facts = ""
    if understanding:
        key_facts = understanding.get("key_facts", [])
        numbers = understanding.get("important_numbers", [])
        facts = f"Allowed facts: {key_facts}. Allowed numbers: {numbers}."

    prompt = f"""You are a strict LinkedIn editor. Fix the draft below with minimal edits.

{facts}

Checks:
1. Every factual claim/number must come from the allowed facts above. Remove or soften anything else.
2. No copied phrase longer than 8 words from a transcript. Reword if needed.
3. Plain text only: no **bold**, no markdown headings, no HTML.
4. No banned phrases: delve, game-changer, revolutionary, cutting-edge, unlock the, "In today's fast-paced world".
5. First line under 150 chars, concrete hook. End with takeaway + one question + 3-5 hashtags.
6. Keep the author's voice and structure. Do not rewrite from scratch.

Return ONLY the fixed post, plain text, no explanations.

Draft:
{post}
"""
    try:
        client = genai.Client(api_key=api_key)
        response = client.interactions.create(
            model="gemini-3.6-flash",
            input=prompt,
        )
        output = getattr(response, "output_text", None)
        if not output:
            return _sanitize_plain_text(post)
        return _sanitize_plain_text(output)
    except Exception as exc:
        print(f"Warning: post validation skipped: {type(exc).__name__}: {exc}")
        return _sanitize_plain_text(post)


def generate_linkedin_post(
    transcript: str,
    understanding: dict | None = None,
    video_title: str = "",
    video_description: str = "",
    visual_info: str | None = None,
    validate: bool = True,
) -> str:
    """Generate a LinkedIn post from video understanding + transcript evidence."""
    config = validate_config()
    api_key = config["GEMINI_API_KEY"]

    try:
        client = genai.Client(api_key=api_key)
        prompt = build_linkedin_prompt(
            transcript,
            understanding=understanding,
            video_title=video_title,
            video_description=video_description,
            visual_info=visual_info,
        )
        response = client.interactions.create(
            model="gemini-3.6-flash",
            input=prompt,
        )
    except Exception as exc:
        raise RuntimeError(f"Gemini API failure: {exc}") from exc

    output = getattr(response, "output_text", None)
    if not output:
        raise ValueError("Gemini returned no content.")

    draft = _sanitize_plain_text(output)
    if not validate:
        return draft
    return validate_and_repair_post(draft, understanding=understanding)
