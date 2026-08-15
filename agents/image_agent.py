import base64
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import requests
from google import genai

from config.settings import validate_config


CLOUDFLARE_MODEL = "@cf/black-forest-labs/flux-1-schnell"


def _call_gemini_analyze(api_key: str, linkedin_post: str) -> str:
    client = genai.Client(api_key=api_key)
    # Instruct Gemini to output a strict JSON object with enhanced infographic design analysis.
    prompt = f"""
Analyze the following LinkedIn post and return a JSON object ONLY (no extra text) with these keys:

- main_subject: short phrase describing the primary real-world subject
- real_subject: if the post uses metaphors/pop-culture comparisons, name the actual real-world subject (otherwise repeat main_subject)
- main_technology: short phrase for the technology/research/product
- main_action: short phrase describing the primary action/process
- important_objects: array of short phrases for visible physical objects
- environment: short phrase for the scene/context (e.g., lab, clinic, operating room, cleanroom, office)
- visual_concept: one concise paragraph describing how to visualize the REAL SUBJECT (no metaphors, no fictional characters)
- image_heading: SHORT, POWERFUL HEADING (2-4 words max per line, capitalize key words). Should summarize the main idea. Format as: "WORD1.\\nWORD2.\\nWORD3." Example: "MONETIZE AI.\\nSOLVE PROBLEMS.\\nCREATE VALUE."
- visual_flow: array of 3-5 steps showing the main workflow/process/progression (e.g., ["Problem", "Solution", "Implementation", "Result"])
- key_concepts: array of 2-4 key ideas or metrics to highlight in the image
- infographic_elements: array of suggested visual elements (e.g., ["flow arrows", "numbered steps", "process diagram", "icons", "charts"] - only what's truly relevant)
- layout_suggestion: recommended layout style (e.g., "horizontal flow", "vertical progression", "central concept with supporting points", "pyramid", "cycle")
- color_palette: suggested professional colors or tone (e.g., "navy and white with blue accents", "dark theme with gold highlights", "clean minimalist")
- contains: an object with boolean flags for movie_references, fictional_characters, metaphors, sensational_headlines, comparisons, jokes
- recommended_style: suggested style keywords for a professional LinkedIn/technical image (e.g., "editorial infographic, modern, premium")

Rules:
- ALWAYS prioritize the real_subject and visual_concept; do not describe or suggest fictional characters or copyrighted characters.
- The image_heading must be SHORT and POWERFUL - max 3 lines, each line ideally 1-2 words. Make it visually impactful.
- visual_flow should show the progression or workflow inherent in the post.
- Only suggest infographic_elements that truly help explain the topic - don't force all elements into every image.
- Do NOT include any image generation model-specific syntax; just plain values.
- Keep arrays of strings for lists.
- Return ONLY the JSON object, no markdown formatting, no extra text.

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
    """Build a premium professional infographic-style image prompt for Cloudflare.
    
    Creates a focused prompt that emphasizes:
    - Strong main heading
    - Professional infographic layout
    - Clear visual hierarchy
    - Relevant infographic elements
    - Process/workflow visualization
    - Premium LinkedIn-suitable design
    """
    rules = (
        "Do not depict fictional characters, movie characters, copyrighted characters, or cartoons. "
        "No logos, watermarks, or large distracting text. Ensure text/headings are clearly readable and professional."
    )

    if not analysis:
        return (
            "Create a premium professional LinkedIn infographic. "
            "Show the main idea clearly with strong visual hierarchy, relevant illustrations, and clean typography. "
            "Use a structured layout: main heading at top, central visual concept, supporting elements below. "
            "Show the real-world subject described in the post; avoid any pop-culture characters or metaphors. "
            "Use professional colors, balanced composition, and sophisticated design. "
            f"{rules}\n\nLinkedIn post:\n{linkedin_post}"
        )

    # Extract all enhanced analysis fields
    subject = identify_real_subject(analysis, linkedin_post)
    action = analysis.get("main_action", "demonstrate the concept")
    environment = analysis.get("environment", "professional setting")
    objects: List[str] = analysis.get("important_objects", [])
    visual_concept = analysis.get("visual_concept")
    
    # NEW: Extract enhanced infographic elements
    heading = analysis.get("image_heading", "")
    visual_flow: List[str] = analysis.get("visual_flow", [])
    key_concepts: List[str] = analysis.get("key_concepts", [])
    infographic_elements: List[str] = analysis.get("infographic_elements", [])
    layout_suggestion = analysis.get("layout_suggestion", "balanced professional layout")
    color_palette = analysis.get("color_palette", "professional navy, white, and accent colors")
    style = analysis.get("recommended_style", "professional editorial infographic")

    # Build optimized prompt with infographic design guidance
    prompt_parts = [
        "Create a PREMIUM PROFESSIONAL LINKEDIN INFOGRAPHIC.",
        f"Style: {style}. Premium corporate appearance with strong visual hierarchy.",
        "",
    ]

    # Add main heading section with emphasis
    if heading:
        prompt_parts.append(f'MAIN HEADING (TEXT): "{heading}"')
        prompt_parts.append("Display prominently at top in large, bold, professional typography.")
        prompt_parts.append("")

    # Add main subject/topic section
    prompt_parts.append("PRIMARY TOPIC:")
    prompt_parts.append(f"Subject: {subject} | Action: {action} | Context: {environment}")
    if visual_concept:
        prompt_parts.append(f"Visual Narrative: {visual_concept}")
    prompt_parts.append("")

    # Add visual flow/process section if available
    if visual_flow:
        prompt_parts.append("VISUAL FLOW/PROCESS:")
        flow_str = " → ".join(visual_flow[:4])  # Limit to 4 steps for brevity
        prompt_parts.append(f"Show progression: {flow_str}")
        prompt_parts.append("")

    # Add key concepts section (condensed)
    if key_concepts:
        prompt_parts.append("KEY CONCEPTS (as short labels in image):")
        prompt_parts.append(", ".join(key_concepts[:3]))  # Limit to 3 concepts
        prompt_parts.append("")

    # Add infographic elements suggestion (condensed)
    if infographic_elements:
        prompt_parts.append("SUGGESTED VISUAL ELEMENTS:")
        elements_str = ", ".join(infographic_elements[:3])  # Limit to 3 elements
        prompt_parts.append(f"Use when relevant: {elements_str}")
        prompt_parts.append("")

    # Add layout guidance (condensed)
    prompt_parts.append("LAYOUT:")
    prompt_parts.append(f"Structure: {layout_suggestion}")
    prompt_parts.append("Hierarchy: Main heading → Central visual → Supporting details")
    prompt_parts.append("Aspect: Landscape 16:9 with space for external post copy")
    prompt_parts.append("")

    # Add visual objects (condensed)
    if objects:
        prompt_parts.append("VISUAL ELEMENTS: " + ", ".join(objects[:3]))
        prompt_parts.append("")

    # Add color and styling guidance (condensed)
    prompt_parts.append("STYLE & COLORS:")
    prompt_parts.append(f"Colors: {color_palette}")
    prompt_parts.append("Typography: Clean, professional fonts with strong contrast")
    prompt_parts.append("Aesthetic: Sophisticated, intentional, carefully designed professional composition")
    prompt_parts.append("")

    # Add critical rules
    prompt_parts.append(f"CRITICAL RULES: {rules}")
    prompt_parts.append("Viewer should understand main topic within 2-3 seconds.")
    prompt_parts.append("Image must be specific to this content, NOT generic AI art.")

    return "\n".join(prompt_parts)
