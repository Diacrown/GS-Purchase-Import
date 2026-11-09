"""
Vision extraction — send an AGL cert image to Google Gemini, get a
structured AGLReport back.

Requires `GEMINI_API_KEY` in the environment. Model is configurable via
`GEMINI_MODEL` (default: gemini-2.0-flash) — Flash is cheap, fast, and good
enough for structured lab-cert reads. For fallback or higher accuracy,
switch to gemini-1.5-pro.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from .extract import AGLReport, Dimensions, REQUIRED_FIELDS


GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

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
        import google.generativeai as genai
    except ImportError:
        report.extraction_status = "failed"
        report.missing_fields = ["<google-generativeai not installed>"]
        return report

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        report.extraction_status = "failed"
        report.missing_fields = ["<GEMINI_API_KEY not set>"]
        return report

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name or GEMINI_MODEL)
        response = model.generate_content(
            [
                {"mime_type": mime_type, "data": image_bytes},
                EXTRACTION_PROMPT,
            ],
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.0,
                "max_output_tokens": 1024,
            },
        )
    except Exception as e:
        report.extraction_status = "failed"
        report.missing_fields = [f"<gemini error: {type(e).__name__}: {e}>"]
        return report

    # Extract the text payload.
    text = getattr(response, "text", None)
    if not text:
        report.extraction_status = "failed"
        report.missing_fields = ["<empty gemini response>"]
        return report

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
