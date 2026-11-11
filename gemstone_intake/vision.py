"""
Vision extraction — send an AGL cert image to Google Gemini, get a
structured AGLReport back.

Requires `GEMINI_API_KEY` in the environment. Model is configurable via
`GEMINI_MODEL` (default: gemini-3.8-flash). Google retires old models, so if
you see a 404 "model no longer available" error, set GEMINI_MODEL to the
replacement it names.

Speed: "thinking" is switched off (it adds many seconds per call and is not
needed to read printed text). Uses the current `google-genai` SDK.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from .extract import AGLReport, Dimensions, REQUIRED_FIELDS


GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

EXTRACTION_PROMPT = """You are reading an AGL (Asian Gemmological Institute & Laboratory) gemstone certificate image.

Extract the following fields and return ONLY a single valid JSON object with these exact keys.
Use null for any field that is not visible on the certificate. Do not invent values.

Keys:
- report_number:  string, the Report Number as shown
- date_of_issue:  string in ISO 8601 format YYYY-MM-DD (convert from the cert's date format)
- species:        string, e.g. "Natural Corundum", "Natural Beryl"
- variety:        string, e.g. "Ruby", "Sapphire", "Emerald"
- weight_ct:      number, weight in carats
- shape:          string, the shape only, e.g. "Round", "Oval", "Cushion"
- cut:            string, the cutting style, e.g. "Brilliant", "Mixed", "Step"
- colour:         string, exactly as on cert e.g. "Blue", "Cornflower Blue", "Pigeon Blood Red"
- transparency:   string, e.g. "Transparent", "Translucent"
- length_mm:      number, first measurement in millimetres
- width_mm:       number, second measurement in millimetres
- height_mm:      number, third measurement (depth) in millimetres
- treatment:      string exactly as the cert phrases it, e.g. "No Indication of Heating", "Heated", "Minor Oil"
- origin:         string, country of origin as shown, e.g. "Burma (Myanmar)", "Sri Lanka (Ceylon)"
- comments:       string, any additional remarks, else null

Return the JSON only. No markdown fences, no explanation.
"""


def _coerce_number(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _coerce_string(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


# --- client + thinking-mode handling ---------------------------------------
import threading
import time as _t

_LOCK = threading.Lock()
_CLIENT = None
_THINK_MODE_IDX: Optional[int] = None  # cached index of the mode that worked

# Tried in order until one is accepted by the model. None = no thinking config.
_THINK_MODES = [{"thinking_budget": 0}, {"thinking_level": "minimal"},
                {"thinking_level": "low"}, None]


def _get_client(api_key: str):
    global _CLIENT
    with _LOCK:
        if _CLIENT is None:
            from google import genai
            from google.genai import types
            _CLIENT = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(timeout=60_000),  # ms
            )
        return _CLIENT


def _is_transient(e: Exception) -> bool:
    code = getattr(e, "code", None)
    if code in (429, 500, 502, 503, 504):
        return True
    n = type(e).__name__
    return n in ("ReadTimeout", "ConnectTimeout", "TimeoutException", "DeadlineExceeded",
                 "ConnectError", "RemoteProtocolError") or "429" in str(e)


def _is_thinking_rejection(e: Exception) -> bool:
    m = str(e).lower()
    return getattr(e, "code", None) == 400 and ("thinking" in m or "budget" in m)


def _generate(client, model: str, image_bytes: bytes, mime_type: str):
    """One Gemini call with thinking off; walks the thinking-mode ladder."""
    global _THINK_MODE_IDX
    from google.genai import types

    start = _THINK_MODE_IDX if _THINK_MODE_IDX is not None else 0
    last: Optional[Exception] = None
    for idx in range(start, len(_THINK_MODES)):
        mode = _THINK_MODES[idx]
        cfg = dict(response_mime_type="application/json", temperature=0.0,
                   max_output_tokens=2048)
        if mode:
            cfg["thinking_config"] = types.ThinkingConfig(**mode)
        try:
            resp = client.models.generate_content(
                model=model,
                contents=[types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                          EXTRACTION_PROMPT],
                config=types.GenerateContentConfig(**cfg),
            )
            _THINK_MODE_IDX = idx
            return resp
        except Exception as e:
            last = e
            if _is_thinking_rejection(e) and idx < len(_THINK_MODES) - 1:
                print(f"[vision] thinking mode {mode} rejected, trying next", flush=True)
                continue
            raise
    raise last  # pragma: no cover


def extract_from_image(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    model_name: Optional[str] = None,
) -> AGLReport:
    """
    Send image_bytes to Gemini, return a filled AGLReport.

    On any error (missing API key, Gemini failure, non-JSON response), the
    returned AGLReport has extraction_status='failed' and missing_fields
    names the reason. Callers should flag the row red rather than crash.
    """
    report = AGLReport()

    try:
        import google.genai  # noqa: F401
    except ImportError:
        report.extraction_status = "failed"
        report.missing_fields = ["<google-genai not installed>"]
        return report

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        report.extraction_status = "failed"
        report.missing_fields = ["<GEMINI_API_KEY not set>"]
        return report

    model_to_use = model_name or os.environ.get("GEMINI_MODEL", GEMINI_MODEL)
    print(f"[vision] calling {model_to_use} on {len(image_bytes)}-byte {mime_type}", flush=True)
    _t0 = _t.time()

    response = None
    last_err: Optional[Exception] = None
    for attempt in range(1, 4):  # retry rate-limit / transient errors
        try:
            response = _generate(_get_client(api_key), model_to_use, image_bytes, mime_type)
            break
        except Exception as e:
            last_err = e
            print(f"[vision] attempt {attempt} failed: {type(e).__name__}: {e}", flush=True)
            if _is_transient(e) and attempt < 3:
                _t.sleep(4 * attempt)
                continue
            break
    if response is None:
        e = last_err
        report.extraction_status = "failed"
        report.missing_fields = [f"<gemini error: {type(e).__name__}: {e}>"]
        return report

    print(f"[vision] gemini returned in {_t.time() - _t0:.1f}s", flush=True)

    # Extract the text payload defensively — response.text can raise on blocked content
    text = None
    try:
        text = response.text
    except Exception as e:
        print(f"[vision] response.text raised: {type(e).__name__}: {e}", flush=True)
        # Try to get useful info from candidates
        candidates_info = ""
        try:
            if hasattr(response, "candidates") and response.candidates:
                c = response.candidates[0]
                candidates_info = f" finish_reason={getattr(c, 'finish_reason', '?')}"
        except Exception:
            pass
        report.extraction_status = "failed"
        report.missing_fields = [f"<response.text raised: {type(e).__name__}{candidates_info}>"]
        return report

    if not text:
        print(f"[vision] empty gemini response; prompt_feedback={getattr(response, 'prompt_feedback', '?')}", flush=True)
        report.extraction_status = "failed"
        report.missing_fields = ["<empty gemini response>"]
        return report

    print(f"[vision] got {len(text)}-char response, first 200: {text[:200]!r}", flush=True)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to salvage: strip markdown fences if present
        cleaned = text.strip().strip("`").lstrip("json").strip()
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            report.extraction_status = "failed"
            report.missing_fields = ["<gemini returned non-JSON>"]
            report.raw_html_excerpt = text[:2000]
            return report

    # Populate report fields.
    report.report_number = _coerce_string(data.get("report_number"))
    report.date_of_issue = _coerce_string(data.get("date_of_issue"))
    report.species       = _coerce_string(data.get("species"))
    report.variety       = _coerce_string(data.get("variety"))
    report.weight_ct     = _coerce_number(data.get("weight_ct"))
    report.shape         = _coerce_string(data.get("shape"))
    report.cut           = _coerce_string(data.get("cut"))
    report.colour        = _coerce_string(data.get("colour"))
    report.transparency  = _coerce_string(data.get("transparency"))
    report.treatment     = _coerce_string(data.get("treatment"))
    report.origin        = _coerce_string(data.get("origin"))
    report.comments      = _coerce_string(data.get("comments"))

    l = _coerce_number(data.get("length_mm"))
    w = _coerce_number(data.get("width_mm"))
    h = _coerce_number(data.get("height_mm"))
    report.dimensions = Dimensions(length_mm=l, width_mm=w, height_mm=h)

    # Status.
    missing = [f for f in REQUIRED_FIELDS if not getattr(report, f, None)]
    report.missing_fields = missing
    if len(missing) == len(REQUIRED_FIELDS):
        report.extraction_status = "failed"
    elif missing:
        report.extraction_status = "partial"
    else:
        report.extraction_status = "ok"
    return report
