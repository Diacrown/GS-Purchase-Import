"""Tests for the Gemini vision extractor. The Gemini SDK is stubbed."""
import json

import pytest

from gemstone_intake.vision import extract_from_image


class _Err(Exception):
    def __init__(self, msg, code):
        super().__init__(msg)
        self.code = code


class _FakeResp:
    def __init__(self, text):
        self.text = text


class _FakeClient:
    """Stands in for google.genai.Client; `script` is a list of text | Exception."""
    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        outer = self

        class _Models:
            def generate_content(self, model, contents, config):
                outer.calls.append(config)
                item = outer.script.pop(0) if len(outer.script) > 1 else outer.script[0]
                if isinstance(item, Exception):
                    raise item
                return _FakeResp(item)
        self.models = _Models()


def _install_fake_genai(response_text, script=None):
    import gemstone_intake.vision as v
    v._THINK_MODE_IDX = None
    v._CLIENT = _FakeClient(script if script is not None else [response_text])
    return v._CLIENT


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("VISION_CACHE_DIR", str(tmp_path / "cache"))


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


_OK = json.dumps({"report_number": "X", "variety": "Ruby", "weight_ct": 1.0,
                  "shape": "Round", "colour": "Red",
                  "treatment": "Heated", "origin": "Burma"})


def test_thinking_mode_falls_back_when_rejected(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    client = _install_fake_genai(None, script=[
        _Err("400 thinking_budget not supported for this model", 400), _OK])
    report = extract_from_image(b"img")
    assert report.extraction_status == "ok"
    assert len(client.calls) == 2  # first mode rejected, second accepted


def test_retries_rate_limit(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.setattr("gemstone_intake.vision._t.sleep", lambda s: None)
    client = _install_fake_genai(None, script=[_Err("429 quota", 429), _OK])
    report = extract_from_image(b"img")
    assert report.extraction_status == "ok"
    assert len(client.calls) == 2


def test_non_retryable_error_reported(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    _install_fake_genai(None, script=[_Err("404 model gone", 404)])
    report = extract_from_image(b"img")
    assert report.extraction_status == "failed"
    assert "404" in report.missing_fields[0]


def test_daily_quota_not_retried_and_message_is_clear(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    client = _install_fake_genai(None, script=[_Err(
        "429 RESOURCE_EXHAUSTED GenerateRequestsPerDayPerProjectPerModel-FreeTier", 429)])
    report = extract_from_image(b"img")
    assert len(client.calls) == 1  # no retries
    assert report.extraction_status == "failed"
    assert "daily quota" in report.missing_fields[0]


def test_cache_avoids_second_gemini_call(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    client = _install_fake_genai(_OK)
    r1 = extract_from_image(b"same-image")
    r2 = extract_from_image(b"same-image")
    assert r1.extraction_status == r2.extraction_status == "ok"
    assert len(client.calls) == 1  # second read served from cache


def test_failures_are_not_cached(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    client = _install_fake_genai(None, script=[_Err("404 gone", 404), _OK])
    assert extract_from_image(b"img-x").extraction_status == "failed"
    assert extract_from_image(b"img-x").extraction_status == "ok"
    assert len(client.calls) == 2


def test_no_credits_clear_message_and_no_retry(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    client = _install_fake_genai(None, script=[_Err(
        "402 RESOURCE_EXHAUSTED Your prepayment credits are depleted", 402)])
    report = extract_from_image(b"img-credits")
    assert len(client.calls) == 1
    assert "credits are $0" in report.missing_fields[0]
