"""Tests for the AGL fetch module. Network calls are stubbed."""
from unittest.mock import MagicMock, patch

import pytest

from gemstone_intake.fetch import (
    fetch_report_image, mime_for_ext, parse_password,
)


# --- parse_password ------------------------------------------------------

def test_parse_password_digits_only():
    assert parse_password("PASS 0998") == "0998"

def test_parse_password_plain_number():
    assert parse_password("12345") == "12345"

def test_parse_password_mixed():
    assert parse_password("abc 42 def") == "42"

def test_parse_password_none():
    assert parse_password(None) is None

def test_parse_password_no_digits():
    assert parse_password("no digits here") is None


# --- mime_for_ext --------------------------------------------------------

def test_mime_jpg():
    assert mime_for_ext("jpg") == "image/jpeg"
    assert mime_for_ext("jpeg") == "image/jpeg"
    assert mime_for_ext(".JPG") == "image/jpeg"

def test_mime_png():
    assert mime_for_ext("png") == "image/png"

def test_mime_pdf():
    assert mime_for_ext("pdf") == "application/pdf"

def test_mime_unknown_defaults_jpeg():
    assert mime_for_ext("xyz") == "image/jpeg"


# --- fetch_report_image (mocked) -----------------------------------------

def _mock_session(html_body: str, image_bytes: bytes = b"\xff\xd8\xff\xe0JPEGDATA"):
    """Build a requests.Session mock returning the given HTML then image."""
    session = MagicMock()
    post_resp = MagicMock()
    post_resp.text = html_body
    post_resp.raise_for_status = MagicMock()
    session.post.return_value = post_resp

    get_resp = MagicMock()
    get_resp.content = image_bytes
    get_resp.headers = {"Content-Type": "image/jpeg"}
    get_resp.raise_for_status = MagicMock()
    session.get.return_value = get_resp
    return session


def test_fetch_happy_path_extracts_image():
    html = '<html><body><img src="upload/0063138.jpg" /></body></html>'
    session = _mock_session(html)
    data, ext = fetch_report_image("0063138", "0998", session=session)
    assert ext == "jpg"
    assert data.startswith(b"\xff\xd8\xff")
    session.post.assert_called_once()
    # Confirm the form fields the real AGL endpoint expects
    call_kwargs = session.post.call_args
    assert call_kwargs.kwargs["data"] == {
        "agl_number": "0063138", "password": "0998", "type": "1",
    }


def test_fetch_png_extension():
    html = '<html><img src="/upload/stuff/x.PNG"></html>'
    session = _mock_session(html)
    _, ext = fetch_report_image("R", "P", session=session)
    assert ext == "png"


def test_fetch_no_image_in_response():
    html = "<html><body>Wrong password</body></html>"
    session = _mock_session(html)
    with pytest.raises(RuntimeError, match="no report image"):
        fetch_report_image("R", "bad", session=session)


def test_fetch_ignores_non_upload_images():
    html = '<img src="/logo.png"><img src="/upload/the-cert.jpg">'
    session = _mock_session(html)
    _, ext = fetch_report_image("R", "P", session=session)
    assert ext == "jpg"


def test_fetch_rejects_non_image_response():
    html = '<img src="upload/x.jpg">'
    session = _mock_session(html)
    session.get.return_value.headers = {"Content-Type": "text/html"}
    with pytest.raises(RuntimeError, match="non-image"):
        fetch_report_image("R", "P", session=session)
