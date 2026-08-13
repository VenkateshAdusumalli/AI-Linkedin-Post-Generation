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
    # Instruct Gemini to output a strict JSON object with the analysis fields we need.
    prompt = f"""
Analyze the following LinkedIn post and return a JSON object ONLY (no extra text) with these keys:

- main_subject: short phrase describing the primary real-world subject
- real_subject: if the post uses metaphors/pop-culture comparisons, name the actual real-world subject (otherwise repeat main_subject)
- main_technology: short phrase for the technology/research/product
- main_action: short phrase describing the primary action/process
- important_objects: array of short phrases for visible physical objects
- environment: short phrase for the scene/context (e.g., lab, clinic, operating room, cleanroom)
- visual_concept: one concise paragraph describing how to visualize the REAL SUBJECT (no metaphors, no fictional characters)
- contains: an object with boolean flags for movie_references, fictional_characters, metaphors, sensational_headlines, comparisons, jokes
- recommended_style: suggested style keywords for a professional LinkedIn/technical image

Rules:
- ALWAYS prioritize the real_subject and visual_concept; do not describe or suggest fictional characters or copyrighted characters.
- Do NOT include any image generation model-specific syntax; just plain values.
- Keep arrays of strings for lists.

LinkedIn post:\n""" + linkedin_post

    response = client.interactions.create(
        model="gemini-3.6-flash",
        input=prompt,
    )

    output = getattr(response, "output_text", None)
    if not output:
        raise RuntimeError("Gemini returned no content during analysis.")

    return output.strip()


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
    """Build a Cloudflare-ready image prompt from Gemini analysis or fallback to conservative prompt.

    The prompt enforces professional, non-fictional visual rules and prioritizes the real-world subject.
    """
    rules = (
        "Do not depict fictional characters, movie characters, copyrighted characters, or cartoons. "
        "No logos, watermarks, or large text. Keep composition professional and suitable for LinkedIn."
    )

    if not analysis:
        return (
            "Create a professional, realistic LinkedIn-style technology/science visualization. "
            "Show the real-world subject described in the LinkedIn post below; avoid any pop-culture characters or metaphors. "
            "Use clean composition, high detail, and realistic materials. "
            "Keep lighting professional and background minimal (lab or clinical environment). "
            f"{rules}\n\nLinkedIn post:\n{linkedin_post}"
        )

    subject = identify_real_subject(analysis, linkedin_post)
    action = analysis.get("main_action") or "show the device in use"
    environment = analysis.get("environment") or "laboratory or clinical setting"
    objects: List[str] = analysis.get("important_objects") or []
    visual_concept = analysis.get("visual_concept")
    style = analysis.get("recommended_style") or "realistic, high-detail scientific visualization"

    composition = (
        "Center the device in the frame; show close-up detail and a secondary view demonstrating deformation or movement. "
    )

    prompt_parts = [
        "Create a professional scientific/technology visualization for LinkedIn.",
        f"SUBJECT: {subject}.",
        f"ACTION: {action}.",
        f"ENVIRONMENT: {environment}.",
        f"COMPOSITION: {composition}",
        f"STYLE: {style}. Clean, modern, premium, scientific aesthetic—realistic or high-quality 3D render.",
        "LIGHTING: soft, even, studio-style lighting emphasizing material detail.",
        "QUALITY: high resolution, photorealistic detail, minimal clutter.",
        f"AUDIENCE: professional LinkedIn / technology / research audience.",
        "VISUAL RULES: " + (
            "No fictional characters, no movie references, no cartoons, no logos, no watermarks, minimal text."
        ),
    ]

    if visual_concept:
        prompt_parts.insert(3, f"VISUAL_CONCEPT: {visual_concept}")

    if objects:
        prompt_parts.append("VISIBLE OBJECTS: " + ", ".join(objects))

    prompt_parts.append(rules)
    prompt_parts.append("Keep image crop landscape 16:9, with negative space for post copy.")

    return "\n\n".join(prompt_parts)
