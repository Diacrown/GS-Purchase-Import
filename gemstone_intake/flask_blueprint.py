"""
Flask blueprint to wire the intake pipeline into the existing AGL Report
Fetcher (Diacrown/Certificate-Scrapper).

Usage in your Flask app:
    from gemstone_intake.flask_blueprint import bp as intake_bp
    app.register_blueprint(intake_bp, url_prefix="/intake")

Endpoints:
    POST /intake/run
        multipart/form-data:
            intake:  the manager's intake .xlsx
            responses_zip: zip of {ReportNo}.html (or .json) files produced
                           by the fetcher
        returns: the EZ JEMS import .xlsx

This is a bridge only. The actual AGL login/fetch stays in the existing
Flask app — this endpoint picks up its output.
"""
from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path

from flask import Blueprint, abort, request, send_file  # type: ignore[import-not-found]

from .pipeline import run_pipeline


bp = Blueprint("gemstone_intake", __name__)


@bp.route("/run", methods=["POST"])
def run_intake():
    intake = request.files.get("intake")
    responses_zip = request.files.get("responses_zip")
    if not intake or not responses_zip:
        abort(400, "both 'intake' and 'responses_zip' are required")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        intake_path = tmp_path / "intake.xlsx"
        intake.save(intake_path)

        agl_dir = tmp_path / "agl"
        agl_dir.mkdir()
        with zipfile.ZipFile(responses_zip.stream) as zf:
            # Flatten — ignore any folder structure inside the zip
            for name in zf.namelist():
                if name.endswith("/"):
                    continue
                basename = Path(name).name
                if not basename:
                    continue
                with zf.open(name) as src, (agl_dir / basename).open("wb") as dst:
                    dst.write(src.read())

        out_path = tmp_path / "ezjems_import.xlsx"
        result = run_pipeline(intake_path, agl_dir, out_path)

        buf = io.BytesIO(out_path.read_bytes())
        buf.seek(0)
        resp = send_file(
            buf,
            as_attachment=True,
            download_name=out_path.name,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        # Expose summary via headers so the caller can log without parsing
        resp.headers["X-Intake-Summary"] = result.summary()
        return resp
