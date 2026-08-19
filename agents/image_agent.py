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


def _call_gemini_analyze(api_key: str, linkedin_post: str) -> str:
    client = genai.Client(api_key=api_key)
    prompt = f"""
Understand the following LinkedIn post before designing its image. Return a JSON object ONLY (no extra text) with these keys:

- main_subject: short phrase naming the primary real-world subject
- real_subject: the literal subject when metaphors, hype, or pop-culture comparisons appear; never name the reference
- core_message: one sentence stating the post's central claim
- main_takeaway: one short sentence stating what the viewer should understand
- main_technology: short phrase for the relevant technology, research, product, or business concept
- main_action: short phrase describing the real action or process
- important_objects: array of no more than 4 relevant visible objects
- environment: short phrase for the real context, such as lab, clinic, office, factory, or data center
- visual_story: concise description of the clearest visual narrative for the core message
- visual_style: one best-fit style from: professional infographic, business editorial visual, scientific visualization, medical/healthcare visualization, technology visualization, product visualization, realistic professional scene, process/workflow diagram, hybrid infographic + realistic scene
- image_heading: short heading, maximum 3 short lines and 6 words total; use an empty string when text would not help
- visual_flow: array of 3-5 short stages only when a process is central; otherwise an empty array
- key_concepts: array of no more than 4 short labels, each 1-3 words; use only labels that materially support the visual
- infographic_elements: array of no more than 4 relevant visual elements; do not force infographic elements into scenes
- layout_suggestion: concise composition suited to the selected visual style
- color_palette: restrained professional palette suited to the subject
- contains: an object with boolean flags for movie_references, fictional_characters, metaphors, sensational_headlines, comparisons, jokes

Rules:
- Identify the real subject and core message, not random nouns from the post.
- Translate metaphors and sensational language into the literal real-world subject. For example, "AI is taking over" means automation/workflow, not attacking robots.
- Choose the visual_style dynamically from the list; do not default to an infographic.
- Use one heading and at most 4 short supporting labels. Never request paragraphs, explanations, the full post, logos, brands, or watermarks as image text.
- Every visual element must support the core message. Prefer no text beyond the heading when labels are unnecessary.
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


def generate_linkedin_image(linkedin_post: str) -> str:
    """Generate a temporary image for a LinkedIn post using Cloudflare Workers AI."""
    config = validate_config()
    account_id = config["CLOUDFLARE_ACCOUNT_ID"]
    api_token = config["CLOUDFLARE_API_TOKEN"]

    if not linkedin_post:
        raise ValueError("LinkedIn post content is required to generate an image prompt.")

    # Analyze the post with Gemini to produce a safe, accurate visual concept
    gemini_key = config.get("GEMINI_API_KEY")
    analysis: Dict[str, Any] = {}
    if gemini_key:
        try:
            analysis_text = _call_gemini_analyze(gemini_key, linkedin_post)
            analysis = json.loads(analysis_text)
        except Exception:
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
        details = response.text.strip() if "response" in locals() else ""
        if details:
            raise RuntimeError(
                f"Cloudflare image generation failed: {exc}. Response: {details}"
            ) from exc
        raise RuntimeError(f"Cloudflare image generation failed: {exc}") from exc

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

    return _save_temporary_image(image_bytes, mime_type)


def identify_real_subject(analysis: Dict[str, Any], linkedin_post: str) -> str:
    if not analysis:
        return linkedin_post.split("\n")[0][:200]
    real = analysis.get("real_subject") or analysis.get("main_subject")
    if isinstance(real, str) and real:
        return real
    return analysis.get("main_subject") or linkedin_post.split("\n")[0][:200]


def build_image_prompt(linkedin_post: str, analysis: Dict[str, Any] | None = None) -> str:
    """Build a focused, topic-specific prompt for Cloudflare FLUX."""
    rules = (
        "Avoid cartoon or fictional/movie/superhero characters, pop-culture references, misleading metaphors, "
        "random objects, generic AI artwork, gaming or fantasy aesthetics, meme styling, clutter, excessive effects, "
        "paragraphs, long explanations, tiny or malformed text, logos, brand names, watermarks, and distorted faces."
    )

    if not analysis:
        return (
            "Create a premium professional LinkedIn visual based on the core message of the post. "
            "First identify the literal real-world subject and show it clearly in a suitable editorial, "
            "scientific, product, scene, or workflow composition. Use strong hierarchy, generous white space, "
            "restrained colors, professional typography, balanced composition, and high-quality lighting. "
            "Use one short heading plus at most 4 short labels when text genuinely helps; never use paragraphs. "
            f"{rules}\n\nLinkedIn post:\n{linkedin_post[:900]}"
        )[:CLOUDFLARE_PROMPT_MAX_LENGTH]

    subject = identify_real_subject(analysis, linkedin_post)
    core_message = analysis.get("core_message", analysis.get("visual_concept", "show the central idea clearly"))
    takeaway = analysis.get("main_takeaway", "")
    action = analysis.get("main_action", "")
    environment = analysis.get("environment", "")
    visual_story = analysis.get("visual_story", analysis.get("visual_concept", ""))
    heading = analysis.get("image_heading", "")
    visual_flow: List[str] = analysis.get("visual_flow", []) or []
    key_concepts: List[str] = analysis.get("key_concepts", []) or []
    objects: List[str] = analysis.get("important_objects", []) or []
    infographic_elements: List[str] = analysis.get("infographic_elements", []) or []
    layout_suggestion = analysis.get("layout_suggestion", "balanced composition")
    color_palette = analysis.get("color_palette", "restrained professional colors")
    style = analysis.get("visual_style", analysis.get("recommended_style", "professional editorial visual"))

    def short_text(value: Any, limit: int, default: str = "") -> str:
        if not isinstance(value, str):
            return default
        return " ".join(value.split())[:limit].strip()

    def short_items(values: Any, limit: int) -> List[str]:
        if not isinstance(values, list):
            return []
        return [short_text(value, 60) for value in values[:limit] if short_text(value, 60)]

    visual_flow = short_items(visual_flow, 5)
    labels = short_items(key_concepts, 4)
    objects = short_items(objects, 4)
    infographic_elements = short_items(infographic_elements, 4)
    subject = short_text(subject, 160, "the real-world subject")
    core_message = short_text(core_message, 260, "the central idea")
    takeaway = short_text(takeaway, 160)
    action = short_text(action, 120)
    environment = short_text(environment, 100)
    visual_story = short_text(visual_story, 320)
    heading = short_text(heading, 100)
    layout_suggestion = short_text(layout_suggestion, 140, "balanced composition")
    color_palette = short_text(color_palette, 120, "restrained professional colors")
    style = short_text(style, 120, "professional editorial visual")

    prompt_parts = [
        "Create a PREMIUM PROFESSIONAL LINKEDIN VISUAL.",
        f"Selected visual style: {style}. Do not force an infographic if this style is a scene, product, scientific, or editorial visual.",
        "The image must communicate the post's core message within a few seconds.",
        "",
    ]

    if heading:
        prompt_parts.append(f'MAIN HEADING (TEXT, maximum 3 short lines): "{heading}"')
        prompt_parts.append("Render it large, crisp, and readable with professional typography; do not add any other heading.")
        prompt_parts.append("")

    prompt_parts.extend([
        "REAL SUBJECT AND MESSAGE:",
        f"Literal subject: {subject}",
        f"Core message: {core_message}",
        f"Main takeaway: {takeaway}",
        f"Real action/process: {action}; context: {environment}",
        f"Visual story: {visual_story}",
        "Ignore metaphors, hype, and pop-culture references; depict the literal subject and message.",
        "",
    ])

    if visual_flow:
        prompt_parts.append("PROCESS STAGES (use only if visually relevant): " + " -> ".join(visual_flow))
    prompt_parts.append("")

    if labels:
        prompt_parts.append("SUPPORTING TEXT LABELS (use only these, maximum 4; keep each very short): " + ", ".join(labels))
        prompt_parts.append("")

    if infographic_elements:
        prompt_parts.append("RELEVANT VISUAL ELEMENTS (use only when they support the story): " + ", ".join(infographic_elements))
        prompt_parts.append("")

    prompt_parts.extend([
        "COMPOSITION AND FINISH:",
        f"Composition: {layout_suggestion}",
        f"Palette: {color_palette}",
        "Use clear hierarchy, generous white space, strong contrast, sophisticated lighting, and polished professional typography.",
        "Landscape 16:9 LinkedIn composition; keep the main subject prominent and every element intentional.",
    ])
    if objects:
        prompt_parts.append("Relevant physical elements only: " + ", ".join(objects))
    prompt_parts.append("")

    prompt_parts.extend([
        "TEXT LIMIT: one short heading plus at most 4 short labels. No paragraphs, explanations, full-post text, or tiny text.",
        f"NEGATIVE INSTRUCTIONS: {rules}",
        "Final quality check: accurately represent the real subject and core message, use the selected style, avoid clutter, and make the topic understandable at a glance.",
    ])

    return "\n".join(prompt_parts)[:CLOUDFLARE_PROMPT_MAX_LENGTH]
