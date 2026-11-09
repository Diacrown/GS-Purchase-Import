"""
AGL Thai cert image fetcher — ported from Diacrown/Certificate-Scrapper's
`fetch_report_image()`. Submits Report No + Password to aglthai.com's public
Report Check form and returns the cert image bytes.

Respects the same rate limit (~2s between calls, caller-enforced) and the
same password sanitisation (digits only).
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import requests


BASE = "https://www.aglthai.com/"
FORM_URL = urljoin(BASE, "report_check.php")


class _ImgFinder(HTMLParser):
    def __init__(self):
        super().__init__()
        self.srcs: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            src = dict(attrs).get("src")
            if src:
                self.srcs.append(src)


def parse_password(raw) -> Optional[str]:
    """Extract digits from the Password cell (handles 'PASS 0998' → '0998')."""
    if raw is None:
        return None
    m = re.search(r"(\d+)", str(raw))
    return m.group(1) if m else None


def fetch_report_image(
    report_no: str,
    password: str,
    session: Optional[requests.Session] = None,
    timeout_post: int = 30,
    timeout_get: int = 60,
) -> tuple[bytes, str]:
    """
    Fetch the cert image for (report_no, password) from aglthai.com.

    Returns (image_bytes, extension_without_dot). Raises RuntimeError on any
    failure (wrong credentials, no image in response, non-image content type).
    """
    s = session or requests.Session()

    resp = s.post(
        FORM_URL,
        data={"agl_number": report_no, "password": password, "type": "1"},
        timeout=timeout_post,
    )
    resp.raise_for_status()

    finder = _ImgFinder()
    finder.feed(resp.text)
    candidates = [u for u in finder.srcs if "upload/" in u.lower()]
    if not candidates:
        raise RuntimeError(
            f"no report image for {report_no} — wrong Report No or Password?"
        )

    img_url = urljoin(BASE, candidates[0])
    ir = s.get(img_url, timeout=timeout_get)
    ir.raise_for_status()
    ctype = ir.headers.get("Content-Type", "")
    if not ctype.startswith("image/"):
        raise RuntimeError(f"AGL returned non-image content: {ctype!r}")

    # Extract extension (without leading dot). Default jpg.
    raw_path = img_url.split("?")[0]
    ext = Path(raw_path).suffix.lstrip(".").lower() or "jpg"
    return ir.content, ext


def mime_for_ext(ext: str) -> str:
    """Map a bare extension (jpg, png, pdf) to a MIME type for vision APIs."""
    ext = ext.lower().lstrip(".")
    return {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "webp": "image/webp",
        "pdf": "application/pdf",
    }.get(ext, "image/jpeg")
