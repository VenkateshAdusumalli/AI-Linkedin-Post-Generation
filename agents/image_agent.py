import base64
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import requests
from google import genai

from config.settings import validate_config


CLOUDFLARE_MODEL = "@cf/black-forest-labs/flux-1-schnell"
CLOUDFLARE_PROMPT_MAX_LENGTH = 2048


def _format_video_understanding(understanding: Dict[str, Any] | None) -> str:
    """Render video understanding as image-concept context."""
    if not understanding:
        return ""
    def get(key: str, default: str = "") -> str:
        value = understanding.get(key, default)
        if isinstance(value, list):
            return "; ".join(str(v) for v in value[:4])
        return str(value) if value else default

    return f"""
VIDEO THEME (ground the visual in this, not just post wording):
- Main theme: {get("main_theme") or get("main_topic")}
- Central idea: {get("central_idea")}
- Product/company and role: {get("product_or_company")} — {get("product_role")}
- What the video demonstrates: {get("what_video_demonstrates")}
- Visual info from frames: {get("visual_information")}
"""


def _call_gemini_analyze(
    api_key: str,
    linkedin_post: str,
    understanding: Dict[str, Any] | None = None,
) -> str:
    client = genai.Client(api_key=api_key)
    theme_section = _format_video_understanding(understanding)
    prompt = f"""
Understand the following LinkedIn post before designing its image. Return a JSON object ONLY (no extra text) with these keys:{theme_section}

- main_subject: short phrase naming the primary real-world subject
- real_subject: the literal subject when metaphors, hype, or pop-culture comparisons appear; never name the reference
- core_message: one sentence stating the post's central claim
- main_takeaway: one short sentence stating what the viewer should understand
- main_technology: short phrase for the relevant technology, research, product, or business concept
- main_action: short phrase describing the real action or process
- important_objects: array of no more than 4 relevant visible objects
- environment: short phrase for the real context, such as lab, clinic, office, factory, or data center
- visual_story: concise description of the clearest text-free visual narrative for the core message, told only through objects, actions, composition, environment, and visual metaphor
- visual_style: one best-fit style from: professional infographic, business editorial visual, scientific visualization, medical/healthcare visualization, technology visualization, product visualization, realistic professional scene, process/workflow diagram, hybrid infographic + realistic scene
- image_heading: always an empty string; images must contain no text of any kind
- visual_flow: array of 3-5 short visual stages only when a process is central, described as pure imagery with no text; otherwise an empty array
- key_concepts: array of no more than 4 short visual concepts, each 1-3 words, for internal visual guidance only; never rendered as text in the image
- infographic_elements: array of no more than 4 relevant text-free visual elements; do not force infographic elements into scenes; never use text labels, numbers, or captions
- layout_suggestion: concise composition suited to the selected visual style
- color_palette: restrained professional palette suited to the subject
- contains: an object with boolean flags for movie_references, fictional_characters, metaphors, sensational_headlines, comparisons, jokes

Rules:
- Identify the real subject and core message, not random nouns from the post.
- Translate metaphors and sensational language into the literal real-world subject. For example, "AI is taking over" means automation/workflow, not attacking robots.
- Choose the visual_style dynamically from the list; do not default to an infographic.
- Strictly no text in the image: no headings, labels, captions, words, letters, numbers, paragraphs, logos, brands, or watermarks. Communicate the main theme entirely through visual storytelling, objects, actions, composition, environment, and visual metaphor.
- Every visual element must support the core message through pure imagery.
- Do not include image-model-specific syntax. Keep arrays as arrays of strings.
- Return only valid JSON, with no markdown formatting or extra text.

LinkedIn post:\n""" + linkedin_post

    response = client.interactions.create(
        model="gemini-3.6-flash",
        input=prompt,
    )

    output = getattr(response, "output_text", None)
    if not output:
        raise RuntimeError("Gemini returned no content during analysis.")

    # Strip markdown code fence if present
    output = output.strip()
    if output.startswith("```json"):
        output = output[7:]  # Remove ```json
    if output.startswith("```"):
        output = output[3:]  # Remove ```
    if output.endswith("```"):
        output = output[:-3]  # Remove trailing ```
    output = output.strip()
    
    return output


def _extract_image_data(response_json: dict) -> tuple[str, str]:
    """Extract Base64 image data and mime type from Cloudflare AI JSON response."""
    result = response_json.get("result") or response_json.get("results")

    if isinstance(result, dict):
        image_data = result.get("image")
        if isinstance(image_data, str) and image_data:
            return image_data, "image/png"
        if isinstance(image_data, dict):
            data = image_data.get("data") or image_data.get("image") or image_data.get("image_data")
            mime_type = image_data.get("mime_type") or image_data.get("format")
            if data:
                return data, mime_type or "image/png"

    if isinstance(result, list):
        for item in result:
            if not isinstance(item, dict):
                continue

            if item.get("type") == "image":
                image_info = item.get("image") or item.get("output_image")
                if isinstance(image_info, dict):
                    data = image_info.get("data") or image_info.get("image_data")
                    mime_type = image_info.get("mime_type") or image_info.get("format")
                    if data:
                        return data, mime_type or "image/png"

            content = item.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "image":
                        image_info = block.get("image")
                        if isinstance(image_info, dict):
                            data = image_info.get("data") or image_info.get("image_data")
                            mime_type = image_info.get("mime_type") or image_info.get("format")
                            if data:
                                return data, mime_type or "image/png"

    if response_json.get("image"):
        image_info = response_json["image"]
        if isinstance(image_info, str):
            return image_info, "image/png"
        if isinstance(image_info, dict):
            data = image_info.get("data") or image_info.get("image_data")
            mime_type = image_info.get("mime_type") or image_info.get("format")
            if data:
                return data, mime_type or "image/png"

    raise ValueError("Cloudflare response did not contain image data.")


def _save_temporary_image(image_bytes: bytes, mime_type: str) -> str:
    suffix = ".png"
    if "jpeg" in mime_type.lower() or "jpg" in mime_type.lower():
        suffix = ".jpg"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix="linkedin-image-", mode="wb") as temp_file:
        temp_file.write(image_bytes)
        temp_path = Path(temp_file.name)

    return str(temp_path)


def _validate_image_dimensions(image_bytes: bytes) -> None:
    """Log a warning if the image is far from LinkedIn landscape (~1.91:1). Never fails."""
    try:
        from PIL import Image
        import io

        with Image.open(io.BytesIO(image_bytes)) as img:
            width, height = img.size
            if not height:
                return
            aspect = width / height
            print(f"  Image size: {width}x{height} (aspect {aspect:.2f}, target ~1.91 landscape).")
            if aspect < 1.2:
                print("  Warning: image looks square/portrait; LinkedIn prefers landscape ~1.91:1.")
    except Exception as exc:
        print(f"  Warning: image dimension check skipped: {type(exc).__name__}: {exc}")


def generate_linkedin_image(
    linkedin_post: str,
    understanding: Dict[str, Any] | None = None,
) -> str:
    """Generate a temporary image for a LinkedIn post using Cloudflare Workers AI."""
    config = validate_config()
    account_id = config["CLOUDFLARE_ACCOUNT_ID"]
    api_token = config["CLOUDFLARE_API_TOKEN"]

    if not linkedin_post:
        raise ValueError("LinkedIn post content is required to generate an image prompt.")

    # Analyze the post (+ video theme when available) to produce a visual concept
    gemini_key = config.get("GEMINI_API_KEY")
    analysis: Dict[str, Any] = {}
    if gemini_key:
        try:
            analysis_text = _call_gemini_analyze(gemini_key, linkedin_post, understanding)
            analysis = json.loads(analysis_text)
        except Exception as exc:
            print(f"  Warning: image concept analysis failed, using fallback: {exc}")
            analysis = {}

    prompt = build_image_prompt(linkedin_post, analysis)
    endpoint = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{CLOUDFLARE_MODEL}"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }
    payload = {"prompt": prompt}

    try:
        response = requests.post(endpoint, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
    except Exception as exc:
        details = ""
        if "response" in locals():
            try:
                details = response.text.strip()[:500]
            except Exception:
                details = ""
        if details:
            raise RuntimeError(
                f"Cloudflare image generation failed: {exc}. Response: {details}"
            ) from exc
        raise RuntimeError(f"Cloudflare image generation failed: {exc}") from exc

    # FLUX via /ai/run may return raw image bytes (Content-Type: image/*)
    # or a JSON envelope with base64 data. Handle both.
    content_type = (response.headers.get("Content-Type") or "").lower()
    if content_type.startswith("image/"):
        image_bytes = response.content
        if not image_bytes:
            raise RuntimeError("Cloudflare returned empty image bytes.")
        mime_type = content_type.split(";")[0].strip() or "image/png"
        _validate_image_dimensions(image_bytes)
        return _save_temporary_image(image_bytes, mime_type)

    try:
        response_json = response.json()
    except ValueError as exc:
        raise RuntimeError("Invalid JSON response from Cloudflare.") from exc

    if not response_json.get("success"):
        raise RuntimeError(
            "Cloudflare returned success=false: "
            + str(response_json.get("errors") or response_json)
        )

    try:
        image_base64, mime_type = _extract_image_data(response_json)
    except Exception as exc:
        raise RuntimeError(f"Cloudflare did not return valid image data: {exc}") from exc

    try:
        image_bytes = base64.b64decode(image_base64)
    except Exception as exc:
        raise RuntimeError(f"Image decoding failed: {exc}") from exc

    _validate_image_dimensions(image_bytes)

    return _save_temporary_image(image_bytes, mime_type)


def identify_real_subject(analysis: Dict[str, Any], linkedin_post: str) -> str:
    if not analysis:
        return linkedin_post.split("\n")[0][:200]
    real = analysis.get("real_subject") or analysis.get("main_subject")
    if isinstance(real, str) and real:
        return real
    return analysis.get("main_subject") or linkedin_post.split("\n")[0][:200]


def build_image_prompt(linkedin_post: str, analysis: Dict[str, Any] | None = None) -> str:
    """Build a concise, topic-specific text-free prompt for Cloudflare FLUX (aim ~400-600 chars)."""
    negative = "Strictly no text, no words, no letters, no numbers, no labels, no captions, no headings. No cartoons, pop-culture, clutter, logos, watermarks, or distorted faces. Pure visual storytelling only."

    def short_text(value: Any, limit: int, default: str = "") -> str:
        if not isinstance(value, str):
            return default
        return " ".join(value.split())[:limit].strip()

    def short_items(values: Any, limit: int) -> List[str]:
        if not isinstance(values, list):
            return []
        return [short_text(value, 24) for value in values[:limit] if short_text(value, 24)]

    if not analysis:
        return (
            "Wordless premium professional LinkedIn visual, landscape 16:9, completely text-free. "
            "Show the post's literal real-world subject entirely through visual storytelling, objects, "
            "actions, composition, environment, and visual metaphor. Clean hierarchy, white space, restrained colors. "
            f"{negative} Post theme: {short_text(linkedin_post, 200)}"
        )[:CLOUDFLARE_PROMPT_MAX_LENGTH]

    subject = short_text(
        identify_real_subject(analysis, linkedin_post), 100, "the real-world subject"
    )
    core_message = short_text(
        analysis.get("core_message", analysis.get("visual_concept", "show the central idea")),
        140,
        "the central idea",
    )
    story = short_text(analysis.get("visual_story", analysis.get("visual_concept", "")), 140)
    environment = short_text(analysis.get("environment", ""), 60)
    action = short_text(analysis.get("main_action", ""), 60)
    style = short_text(
        analysis.get("visual_style", analysis.get("recommended_style", "professional editorial visual")),
        60,
        "professional editorial visual",
    )
    concepts = short_items(analysis.get("key_concepts", []), 4)
    objects = short_items(analysis.get("important_objects", []), 4)
    flow = short_items(analysis.get("visual_flow", []), 4)

    parts = [f"Wordless premium LinkedIn visual, {style}, landscape 16:9, completely text-free. Subject: {subject}. Central theme to convey purely visually: {core_message}."]
    if environment or action:
        parts.append(f"Environment and action: {action} in {environment}, told through composition and interaction.".strip())
    if story:
        parts.append(f"Visual narrative: {story}")
    if objects:
        parts.append(f"Key visual elements: {', '.join(objects)}.")
    if flow:
        parts.append(f"Visual progression shown as sequential wordless imagery: {', '.join(flow)}.")
    if concepts:
        parts.append(f"Reinforce theme with visual metaphors for: {', '.join(concepts)}.")
    parts.append("Communicate the main theme entirely through visual storytelling, objects, actions, composition, environment, and visual metaphor.")
    parts.append("Clean hierarchy, white space, restrained professional colors.")
    parts.append(negative)

    return " ".join(parts)[:CLOUDFLARE_PROMPT_MAX_LENGTH]
