"""
Flask web app — host wrapper around the gemstone_intake pipeline.

Endpoints:
    GET  /         upload UI
    GET  /health   health check (always public)
    POST /run      process intake + AGL responses → JSON {summary, per_row, file_b64}

Auth:
    If env var INTAKE_API_KEY is set, every /run request must include a
    matching `X-API-Key` header (or `api_key` form field). If unset, no auth
    required (useful for dev / local). / and /health stay public either way.
"""
from __future__ import annotations

import base64
import io
import os
import tempfile
import zipfile
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from gemstone_intake.pipeline import run_pipeline


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32 MB upper bound

API_KEY = os.environ.get("INTAKE_API_KEY") or None


def _authed() -> bool:
    if not API_KEY:
        return True
    provided = (
        request.headers.get("X-API-Key")
        or request.form.get("api_key")
        or ""
    )
    return provided == API_KEY


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "gemstone-intake",
        "auth_required": bool(API_KEY),
    })


@app.route("/")
def index():
    return render_template("index.html", auth_required=bool(API_KEY))


@app.errorhandler(413)
def too_large(_err):
    return jsonify({"error": "file too large; max combined upload is 32 MB"}), 413


@app.route("/run", methods=["POST"])
def run():
    if not _authed():
        return jsonify({"error": "unauthorized (bad or missing X-API-Key)"}), 401

    intake = request.files.get("intake")
    responses = request.files.get("responses")
    if not intake or not responses:
        return jsonify({
            "error": "both 'intake' (.xlsx) and 'responses' (.zip) files required",
        }), 400

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        intake_path = tmp_path / "intake.xlsx"
        intake.save(intake_path)

        agl_dir = tmp_path / "agl"
        agl_dir.mkdir()
        try:
            with zipfile.ZipFile(responses.stream) as zf:
                for name in zf.namelist():
                    if name.endswith("/"):
                        continue
                    basename = Path(name).name
                    if not basename:
                        continue
                    with zf.open(name) as src, (agl_dir / basename).open("wb") as dst:
                        dst.write(src.read())
        except zipfile.BadZipFile:
            return jsonify({"error": "'responses' is not a valid zip file"}), 400

        out_path = tmp_path / "ezjems_bulk_import.xlsx"

        try:
            result = run_pipeline(intake_path, agl_dir, out_path)
        except ValueError as e:
            # read_intake raises ValueError on missing required intake columns
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            return jsonify({
                "error": f"pipeline failed: {type(e).__name__}: {e}",
            }), 500

        file_bytes = out_path.read_bytes()
        return jsonify({
            "summary":      result.summary(),
            "rows_written": result.rows_written,
            "rows_amber":   result.rows_amber,
            "rows_red":     result.rows_red,
            "per_row":      result.per_row,
            "file_name":    "ezjems_bulk_import.xlsx",
            "file_b64":     base64.b64encode(file_bytes).decode("ascii"),
        })


if __name__ == "__main__":
    # Local dev — do NOT use this in production; Fly.io uses gunicorn.
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=False)
