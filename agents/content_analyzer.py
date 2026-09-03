"""Content quality analysis module for videos."""

from google import genai
from config.settings import validate_config


def analyze_transcript_quality(transcript: str, video_title: str, video_description: str) -> dict:
    """
    Evaluate the quality of transcript and supporting content.
    
    Args:
        transcript: Video transcript text
        video_title: Video title
        video_description: Video description
    
    Returns:
        dict with keys:
            - transcript_length: int (character count)
            - transcript_quality: str ("HIGH", "MEDIUM", "LOW")
            - has_meaningful_info: bool
            - reason: str (explanation)
    """
    # Basic quality checks
    transcript_length = len(transcript) if transcript else 0
    
    # Minimum viable transcript length
    MIN_GOOD_LENGTH = 500
    MIN_ACCEPTABLE_LENGTH = 200
    
    if transcript_length < MIN_ACCEPTABLE_LENGTH:
        return {
            "transcript_length": transcript_length,
            "transcript_quality": "LOW",
            "has_meaningful_info": False,
            "reason": f"Transcript too short ({transcript_length} chars, minimum {MIN_ACCEPTABLE_LENGTH})",
        }
    
    # Check for meaningful content (not just filler)
    word_count = len(transcript.split())
    if word_count < 50:
        return {
            "transcript_length": transcript_length,
            "transcript_quality": "LOW",
            "has_meaningful_info": False,
            "reason": f"Transcript has insufficient word count ({word_count} words)",
        }
    
    # Check if title and description provide context
    has_title = bool(video_title and len(video_title.strip()) > 5)
    has_description = bool(video_description and len(video_description.strip()) > 20)
    
    if transcript_length >= MIN_GOOD_LENGTH:
        quality = "HIGH"
    else:
        quality = "MEDIUM"
    
    return {
        "transcript_length": transcript_length,
        "transcript_quality": quality,
        "has_meaningful_info": True,
        "has_title": has_title,
        "has_description": has_description,
        "word_count": word_count,
        "reason": f"Transcript quality: {quality} ({transcript_length} chars, {word_count} words)",
    }


def analyze_video_content(
    transcript: str,
    video_title: str,
    video_description: str,
    visual_info: str | None = None,
) -> dict:
    """
    Use Gemini to UNDERSTAND the video's central idea before any post is written.

    The transcript is treated as evidence for understanding, not as text to
    extract and rewrite. The returned dict is the understanding layer that the
    LinkedIn post generator consumes.

    Args:
        transcript: Video transcript text
        video_title: Video title
        video_description: Video description
        visual_info: Optional visual analysis from video frames

    Returns:
        dict with keys:
            - main_theme: str
            - core_message: str
            - central_idea: str
            - underlying_insight: str
            - problem_or_change: str
            - product_or_company: str
            - product_role: str
            - key_facts: list[str]
            - important_numbers: list[str]
            - visual_information: str
            - what_video_demonstrates: str
            - has_sufficient_info: bool
            - info_gaps: str
            - content_quality: str ("GOOD", "POOR")
            - confidence: str ("HIGH", "MEDIUM", "LOW")
            - reason: str (explanation)
            - recommendation: str ("PROCESS", "SKIP")
            - main_topic: str (alias of main_theme, backward compatible)
    """
    config = validate_config()
    api_key = config["GEMINI_API_KEY"]

    # Build analysis prompt
    visual_section = ""
    if visual_info:
        visual_section = f"\n\nVIDEO FRAME ANALYSIS:\n{visual_info}"

    prompt = f"""You watched a YouTube video. Your job is to UNDERSTAND what the video actually means BEFORE anyone writes about it.

Treat the transcript as EVIDENCE for understanding, not as text to extract and rewrite.
Use the title, description, transcript, and frame analysis together.

VIDEO TITLE:
{video_title}

VIDEO DESCRIPTION:
{video_description}

TRANSCRIPT:
{transcript}{visual_section}

First UNDERSTAND, then report. Provide analysis in this exact JSON format (NO markdown, NO code fence, ONLY JSON):
{{
    "main_theme": "the main subject or theme of the video in one sentence",
    "core_message": "what the creator is actually trying to communicate in one or two sentences",
    "central_idea": "the single most important idea the viewer should understand after watching",
    "underlying_insight": "the interesting insight, lesson, change, or observation derived from the video (interpretation, clearly grounded in facts)",
    "problem_or_change": "the problem, shift, trend, opportunity, or change the video is discussing",
    "product_or_company": "product/company/tool discussed, or empty string if none",
    "product_role": "how the product relates to the central idea in one sentence; empty string if no product",
    "key_facts": ["fact explicitly supported by the video", "another supporting fact"],
    "important_numbers": ["only genuinely important numbers, or empty array"],
    "visual_information": "important information visible in frames that may not appear in the transcript",
    "what_video_demonstrates": "what the video actually shows or demonstrates",
    "has_sufficient_info": true/false,
    "info_gaps": "description of missing critical information (if any)",
    "content_quality": "GOOD or POOR",
    "confidence": "HIGH, MEDIUM, or LOW",
    "reason": "explanation of quality assessment and suitability for a LinkedIn post"
}}

Rules:
- UNDERSTAND THEN WRITE, not EXTRACT then REWRITE. Do not just list product features from the transcript.
- Do NOT automatically make the product the main theme. The product is only the main theme if the video is genuinely about the product itself rather than a broader shift it illustrates.
- Distinguish FACT (explicitly supported by the video) from INTERPRETATION (insight derived from facts). Never invent facts.
- key_facts and important_numbers must come from the video only.
- underlying_insight and central_idea may interpret, but must be grounded in the facts above.
- GOOD quality means the central idea is clear, factually supported, and suitable for professional LinkedIn publishing.
- POOR quality means the content is incomplete, unclear, lacks sufficient detail, or contains contradictions.
- Only mark GOOD if you are confident the main idea has been correctly understood with enough supporting information.
- Be strict: if information seems incomplete or unclear, mark as POOR.
- Do NOT invent facts not explicitly stated in the transcript, title, description, or frame analysis.
"""

    try:
        client = genai.Client(api_key=api_key)
        response = client.interactions.create(
            model="gemini-3.6-flash",
            input=prompt,
        )
    except Exception as exc:
        raise RuntimeError(f"Gemini API failure during content analysis: {exc}") from exc
    
    output = getattr(response, "output_text", None)
    if not output:
        raise ValueError("Gemini returned no content during analysis.")
    
    # Clean output - remove markdown fences if present
    output = output.strip()
    if output.startswith("```json"):
        output = output[7:]
    if output.startswith("```"):
        output = output[3:]
    if output.endswith("```"):
        output = output[:-3]
    output = output.strip()
    
    # Parse JSON response
    import json
    try:
        result = json.loads(output)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to parse Gemini response as JSON: {output}") from exc
    
    # Add recommendation based on content_quality
    recommendation = "PROCESS" if result.get("content_quality") == "GOOD" else "SKIP"
    result["recommendation"] = recommendation

    # Backward-compatible alias: older callers expect "main_topic"
    if not result.get("main_topic") and result.get("main_theme"):
        result["main_topic"] = result["main_theme"]

    return result
