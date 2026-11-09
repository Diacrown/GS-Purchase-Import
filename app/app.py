"""
Flask web app — one upload in, one file out.

Endpoints:
    GET  /                       upload UI
    GET  /health                 health check (always public)
    GET  /template/intake        download empty intake Excel (headers + 1 example row)
    POST /run                    process intake → fetch certs from AGL → Gemini → import file

Auth:
    If env var INTAKE_API_KEY is set, every /run request must include a
    matching `X-API-Key` header (or `api_key` form field). If unset, no auth
    required (dev / local).

Required env vars for /run:
    GEMINI_API_KEY   — Google Gemini API key (https://aistudio.google.com)
"""
from __future__ import annotations

import base64
import io
import os
import tempfile
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file
from openpyxl import Workbook

from gemstone_intake.pipeline import run_pipeline_live, INTAKE_COLUMNS


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB — intake Excels are tiny

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
        "gemini_configured": bool(os.environ.get("GEMINI_API_KEY")),
    })


@app.route("/")
def index():
    return render_template(
        "index.html",
        auth_required=bool(API_KEY),
        gemini_configured=bool(os.environ.get("GEMINI_API_KEY")),
    )


@app.errorhandler(413)
def too_large(_err):
    return jsonify({"error": "file too large; intake Excel limit is 8 MB"}), 413


@app.route("/template/intake")
def template_intake():
    """Download a ready-to-fill intake Excel: headers + one example row."""
    buf = io.BytesIO()
    wb = Workbook()
    ws = wb.active
    ws.title = "Intake"
    ws.append(INTAKE_COLUMNS)
    ws.append(["AGL-100001", "see AGL cert", 300.00, "T", "DDX", ""])
    for col, width in zip("ABCDEF", [14, 14, 12, 10, 10, 12]):
        ws.column_dimensions[col].width = width
    wb.save(buf)
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name="gs_purchase_intake_template.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/run", methods=["POST"])
def run():
    if not _authed():
        return jsonify({"error": "unauthorized (bad or missing X-API-Key)"}), 401

    if not os.environ.get("GEMINI_API_KEY"):
        return jsonify({
            "error": "server missing GEMINI_API_KEY — set the secret before use",
        }), 500

    intake = request.files.get("intake")
    if not intake:
        return jsonify({
            "error": "'intake' (.xlsx) file is required",
        }), 400

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        intake_path = tmp_path / "intake.xlsx"
        intake.save(intake_path)

        out_path = tmp_path / "ezjems_bulk_import.xlsx"

        try:
            delay = float(os.environ.get("AGL_LOOKUP_DELAY", "2.0"))
            result = run_pipeline_live(
                intake_path,
                out_path,
                delay_seconds=delay,
            )
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
    # Local dev — Fly.io uses gunicorn via the Dockerfile.
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=False)
