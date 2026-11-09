"""Tests for the Gemini vision extractor. The Gemini SDK is stubbed."""
import json
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from gemstone_intake.vision import extract_from_image


def _install_fake_genai(response_text: str):
    """Install a fake google.generativeai module that returns response_text."""
    fake = types.ModuleType("google")
    fake_gen = types.ModuleType("google.generativeai")

    def configure(api_key):
        pass

    class _FakeResp:
        def __init__(self, text):
            self.text = text

    class _FakeModel:
        def __init__(self, name):
            self.name = name
        def generate_content(self, parts, generation_config=None):
            return _FakeResp(response_text)

    fake_gen.configure = configure
    fake_gen.GenerativeModel = _FakeModel
    fake.generativeai = fake_gen
    sys.modules["google"] = fake
    sys.modules["google.generativeai"] = fake_gen


def test_extract_happy_path(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    payload = {
        "report_number": "AGL-100001",
        "date_of_issue": "2026-11-09",
        "species": "Natural Corundum",
        "variety": "Ruby",
        "weight_ct": 0.78,
        "shape": "Round",
        "cut": "Brilliant",
        "colour": "Pigeon Blood Red",
        "transparency": "Transparent",
        "length_mm": 5.5,
        "width_mm": 5.5,
        "height_mm": 3.4,
        "treatment": "No Indication of Heating",
        "origin": "Burma (Myanmar)",
        "comments": None,
    }
    _install_fake_genai(json.dumps(payload))

    report = extract_from_image(b"fake-image-bytes", mime_type="image/jpeg")
    assert report.extraction_status == "ok"
    assert report.report_number == "AGL-100001"
    assert report.variety == "Ruby"
    assert report.weight_ct == 0.78
    assert report.shape == "Round" and report.cut == "Brilliant"
    assert report.colour == "Pigeon Blood Red"
    assert report.dimensions.length_mm == 5.5
    assert report.dimensions.width_mm == 5.5
    assert report.dimensions.height_mm == 3.4
    assert report.treatment == "No Indication of Heating"
    assert report.origin == "Burma (Myanmar)"
    assert report.missing_fields == []


def test_extract_missing_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    report = extract_from_image(b"img")
    assert report.extraction_status == "failed"
    assert "GEMINI_API_KEY" in report.missing_fields[0]


def test_extract_non_json_response(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    _install_fake_genai("I cannot read this image.")
    report = extract_from_image(b"img")
    assert report.extraction_status == "failed"
    assert "non-JSON" in report.missing_fields[0]


def test_extract_markdown_fenced_json(monkeypatch):
    """Gemini sometimes wraps JSON in ```json fences — we strip them."""
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    payload = {"report_number": "X", "variety": "Ruby", "weight_ct": 1.0,
               "shape": "Round", "colour": "Red",
               "treatment": "Heated", "origin": "Burma"}
    _install_fake_genai("```json\n" + json.dumps(payload) + "\n```")
    report = extract_from_image(b"img")
    assert report.extraction_status == "ok"
    assert report.variety == "Ruby"


def test_extract_partial_when_fields_missing(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    payload = {"report_number": "X", "variety": "Ruby", "weight_ct": 1.0}
    _install_fake_genai(json.dumps(payload))
    report = extract_from_image(b"img")
    assert report.extraction_status == "partial"
    assert set(report.missing_fields) >= {"shape", "colour", "treatment", "origin"}
