"""Job-description fallback fetchers: TinyFish Fetch API, then Jina Reader.

Used when a board's own detail page yields no description (JS-rendered pages,
anti-bot blocks). Both services return page text as markdown.

TinyFish: POST https://api.fetch.tinyfish.ai  (X-API-Key header; up to 10 URLs)
Jina:     GET  https://r.jina.ai/<url>        (Authorization: Bearer key, optional)

Every function degrades to "" on failure and never raises, so a missing key or
an outage just leaves the row for the judge to flag as "Needs review".
"""

import re
import time

import requests

from config import JINA_API_KEY, TINYFISH_API_KEY

TINYFISH_ENDPOINT = "https://api.fetch.tinyfish.ai"
JINA_ENDPOINT = "https://r.jina.ai/"
MAX_DESCRIPTION_CHARS = 20000
MIN_DESCRIPTION_CHARS = 200

# A fetched page only counts as a job description when it contains at least one
# of these section markers; this rejects login walls and cookie banners.
_JD_MARKERS = re.compile(
    r"(responsibilit|requirement|qualification|your profile|your tasks|what you|"
    r"about the role|about you|we offer|aufgaben|profil|anforderungen|"
    r"wir bieten|ihre aufgaben|dein profil|ihr profil|deine aufgaben)",
    re.IGNORECASE,
)
_BLOCKED_MARKERS = re.compile(
    r"(sign in to view|join linkedin|authwall|captcha|access denied|"
    r"enable javascript|verify you are human)",
    re.IGNORECASE,
)


def looks_like_job_description(text: str) -> bool:
    """True for text long enough, with JD section markers and no wall markers."""
    if not isinstance(text, str) or len(text.strip()) < MIN_DESCRIPTION_CHARS:
        return False
    if not _JD_MARKERS.search(text):
        return False
    # A wall marker only disqualifies short pages; real JDs may mention "sign in".
    return not (_BLOCKED_MARKERS.search(text) and len(text) < 1500)


def fetch_tinyfish(urls: list[str], timeout: int = 150) -> dict[str, str]:
    """Fetch up to 10 URLs per request via TinyFish. Returns {url: markdown}."""
    if not TINYFISH_API_KEY or not urls:
        return {}
    found: dict[str, str] = {}
    for start in range(0, len(urls), 10):
        chunk = urls[start:start + 10]
        try:
            response = requests.post(
                TINYFISH_ENDPOINT,
                headers={"X-API-Key": TINYFISH_API_KEY, "Content-Type": "application/json"},
                json={"urls": chunk, "format": "markdown"},
                timeout=timeout,
            )
            if response.status_code == 429:
                # Per-minute limit: wait once and retry; a daily-allowance 429 just fails.
                time.sleep(20)
                response = requests.post(
                    TINYFISH_ENDPOINT,
                    headers={"X-API-Key": TINYFISH_API_KEY, "Content-Type": "application/json"},
                    json={"urls": chunk, "format": "markdown"},
                    timeout=timeout,
                )
            if response.status_code != 200:
                continue
            for item in response.json().get("results", []):
                text = item.get("text")
                original = item.get("url")
                if isinstance(text, str) and original:
                    found[original] = text[:MAX_DESCRIPTION_CHARS]
        except (requests.RequestException, ValueError):
            continue
    return found


def fetch_jina(url: str, timeout: int = 45) -> str:
    """Fetch one URL via Jina Reader and return markdown text ("" on failure)."""
    headers = {"Accept": "text/plain", "X-Return-Format": "markdown"}
    if JINA_API_KEY:
        headers["Authorization"] = f"Bearer {JINA_API_KEY}"
    try:
        response = requests.get(JINA_ENDPOINT + url, headers=headers, timeout=timeout)
        if response.status_code in (401, 402, 403) and "Authorization" in headers:
            # Bad key or empty balance: Jina still serves keyless at a lower rate limit.
            headers.pop("Authorization")
            response = requests.get(JINA_ENDPOINT + url, headers=headers, timeout=timeout)
        if response.status_code == 200:
            return response.text[:MAX_DESCRIPTION_CHARS]
    except requests.RequestException:
        pass
    return ""


def fetch_job_description(url: str) -> str:
    """Return a job description for ``url`` via TinyFish then Jina, or "" if neither works."""
    if not url:
        return ""
    text = fetch_tinyfish([url]).get(url, "")
    if looks_like_job_description(text):
        return text
    text = fetch_jina(url)
    return text if looks_like_job_description(text) else ""
