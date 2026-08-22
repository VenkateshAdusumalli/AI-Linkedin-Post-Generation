import mimetypes
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

from config.settings import validate_config


LINKEDIN_API_BASE = "https://api.linkedin.com/rest"
LINKEDIN_VERSION = "202601"
RESTLI_PROTOCOL_VERSION = "2.0.0"


def _headers(access_token: str, content_type: str = "application/json") -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": content_type,
        "LinkedIn-Version": LINKEDIN_VERSION,
        "X-Restli-Protocol-Version": RESTLI_PROTOCOL_VERSION,
    }


def _safe_url(url: str) -> str:
    """Hide query parameters because upload URLs may contain signed credentials."""
    parts = urlsplit(url)
    if not parts.query:
        return url
    safe_query = urlencode([(key, "[REDACTED]") for key, _ in parse_qsl(parts.query)])
    return urlunsplit((parts.scheme, parts.netloc, parts.path, safe_query, ""))


def _network_category(exc: BaseException) -> str:
    message = str(exc).lower()
    if isinstance(exc, requests.exceptions.SSLError) or "ssl" in message:
        return "SSL"
    if isinstance(exc, requests.exceptions.ConnectTimeout) or isinstance(exc, requests.exceptions.ReadTimeout):
        return "connection timeout"
    if isinstance(exc, requests.exceptions.ConnectionError):
        if any(term in message for term in ("getaddrinfo", "name or service", "nodename", "dns")):
            return "DNS"
        if "reset" in message:
            return "connection reset"
        return "other network error"
    return "other network error"


def _response_body(response: requests.Response) -> str:
    body = response.text.strip()
    return body if body else "<empty response body>"


def _raise_linkedin_error(
    response: requests.Response,
    operation: str,
    request_url: str,
) -> None:
    if response.ok:
        return

    print("LinkedIn API response received.")
    print(f"Stage: {operation}")
    print(f"Request URL: {_safe_url(request_url)}")
    print(f"Status: {response.status_code}")
    print(f"Response: {_response_body(response)}")

    if response.status_code == 401:
        raise RuntimeError(
            "LinkedIn authentication failed. Access token may have expired or been revoked. "
            "Re-authorize the LinkedIn application."
        )
    if response.status_code == 403:
        raise RuntimeError(
            f"LinkedIn authorization failed while {operation}. Check the app permissions."
        )
    if response.status_code == 429:
        raise RuntimeError(f"LinkedIn rate limit reached while {operation}. Try again later.")

    raise RuntimeError(f"LinkedIn {operation} failed with HTTP {response.status_code}.")


def _raise_request_error(operation: str, request_url: str, exc: BaseException) -> None:
    print("LinkedIn request failed.")
    print(f"Stage: {operation}")
    print(f"Request URL: {_safe_url(request_url)}")
    print(f"Failure category: {_network_category(exc)}")
    print(f"Exception type: {type(exc).__name__}")
    print(f"Exception: {exc}")
    raise RuntimeError(f"LinkedIn {operation} request failed: {type(exc).__name__}: {exc}") from exc


def _initialize_image_upload(access_token: str, owner_urn: str) -> tuple[str, str]:
    payload = {"initializeUploadRequest": {"owner": owner_urn}}
    request_url = f"{LINKEDIN_API_BASE}/images?action=initializeUpload"
    try:
        response = requests.post(
            request_url,
            json=payload,
            headers=_headers(access_token),
            timeout=30,
        )
    except requests.RequestException as exc:
        _raise_request_error("image upload initialization", request_url, exc)

    _raise_linkedin_error(response, "image upload initialization", request_url)
    try:
        value = response.json()["value"]
        return value["uploadUrl"], value["image"]
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError("LinkedIn returned an invalid image upload response.") from exc


def _upload_image(access_token: str, upload_url: str, image_path: Path) -> None:
    mime_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    try:
        with image_path.open("rb") as image_file:
            response = requests.put(
                upload_url,
                data=image_file,
                headers=_headers(access_token, mime_type),
                timeout=60,
            )
    except OSError as exc:
        print("LinkedIn request failed.")
        print("Stage: image upload")
        print(f"Request URL: {_safe_url(upload_url)}")
        print("Failure category: local image file error")
        print(f"Exception type: {type(exc).__name__}")
        print(f"Exception: {exc}")
        raise RuntimeError("LinkedIn image upload could not read the generated image file.") from exc
    except requests.RequestException as exc:
        _raise_request_error("image upload", upload_url, exc)

    _raise_linkedin_error(response, "image upload", upload_url)


def _create_image_post(access_token: str, author_urn: str, text: str, image_urn: str) -> None:
    payload = {
        "author": author_urn,
        "commentary": text,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "content": {"media": {"id": image_urn}},
    }
    request_url = f"{LINKEDIN_API_BASE}/posts"
    try:
        response = requests.post(
            request_url,
            json=payload,
            headers=_headers(access_token),
            timeout=30,
        )
    except requests.RequestException as exc:
        _raise_request_error("post creation", request_url, exc)

    _raise_linkedin_error(response, "post creation", request_url)


def publish_linkedin_post(text: str, image_path: str) -> None:
    """Upload the generated image and publish it with the generated text."""
    if not text or not text.strip():
        raise ValueError("LinkedIn post text is required.")

    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"Generated image file was not found: {path}")

    config = validate_config()
    access_token = config["LINKEDIN_ACCESS_TOKEN"]
    member_id = config["LINKEDIN_MEMBER_ID"]
    author_urn = f"urn:li:person:{member_id}"

    print("Uploading image to LinkedIn...")
    upload_url, image_urn = _initialize_image_upload(access_token, author_urn)
    _upload_image(access_token, upload_url, path)
    print("Image upload successful.")
    print("Creating LinkedIn post...")
    _create_image_post(access_token, author_urn, text.strip(), image_urn)
    print("Post creation successful.")