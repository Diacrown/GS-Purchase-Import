"""
Flask web app — background job pattern so long-running batches don't trip
Fly's proxy timeout.

Endpoints:
    GET  /                       upload UI
    GET  /health                 health check (public)
    GET  /template/intake        download empty intake Excel
    POST /run                    start a job; returns {job_id} immediately
    GET  /jobs/<id>              poll job progress / fetch result

Auth: optional X-API-Key via INTAKE_API_KEY env var.
Vision: requires GEMINI_API_KEY env var (not exposed to clients).
"""
from __future__ import annotations

import base64
import io
import os
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file
from openpyxl import Workbook

from gemstone_intake.pipeline import run_pipeline_live, INTAKE_COLUMNS


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

API_KEY = os.environ.get("INTAKE_API_KEY") or None
JOB_TTL_SECONDS = int(os.environ.get("JOB_TTL_SECONDS", "600"))


# ---------------------------------------------------------------------------
# Job store (in-memory; fine for a single-worker container)
# ---------------------------------------------------------------------------

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def _reap_old_jobs() -> None:
    now = time.time()
    with JOBS_LOCK:
        stale = [jid for jid, j in JOBS.items()
                 if now - j.get("updated_at", 0) > JOB_TTL_SECONDS]
        for jid in stale:
            tmp = JOBS[jid].get("tmp_dir")
            if tmp and Path(tmp).exists():
                shutil.rmtree(tmp, ignore_errors=True)
            del JOBS[jid]


def _run_job(job_id: str, intake_path: Path, out_path: Path) -> None:
    def on_progress(current: int, total: int, report_no: str) -> None:
        with JOBS_LOCK:
            j = JOBS.get(job_id)
            if j is not None:
                j["progress"] = {"current": current, "total": total,
                                 "report_no": report_no}
                j["updated_at"] = time.time()

    try:
        delay = float(os.environ.get("AGL_LOOKUP_DELAY", "2.0"))
        result = run_pipeline_live(
            intake_path, out_path,
            delay_seconds=delay, progress=on_progress,
        )
        file_bytes = out_path.read_bytes()
        with JOBS_LOCK:
            j = JOBS.get(job_id)
            if j is None:
                return
            j["status"] = "done"
            j["result"] = {
                "summary":      result.summary(),
                "rows_written": result.rows_written,
                "rows_amber":   result.rows_amber,
                "rows_red":     result.rows_red,
                "per_row":      result.per_row,
                "file_name":    "ezjems_bulk_import.xlsx",
                "file_b64":     base64.b64encode(file_bytes).decode("ascii"),
            }
            j["updated_at"] = time.time()
    except Exception as e:
        with JOBS_LOCK:
            j = JOBS.get(job_id)
            if j is not None:
                j["status"] = "failed"
                j["error"] = f"{type(e).__name__}: {e}"
                j["updated_at"] = time.time()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _authed() -> bool:
    if not API_KEY:
        return True
    provided = (
        request.headers.get("X-API-Key")
        or request.form.get("api_key")
        or request.args.get("api_key")
        or ""
    )
    return provided == API_KEY


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "gemstone-intake",
        "auth_required": bool(API_KEY),
        "gemini_configured": bool(os.environ.get("GEMINI_API_KEY")),
        "active_jobs": sum(1 for j in JOBS.values() if j.get("status") == "running"),
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
        buf, as_attachment=True,
        download_name="gs_purchase_intake_template.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/run", methods=["POST"])
def run():
    """Start a background job. Returns {job_id} immediately."""
    if not _authed():
        return jsonify({"error": "unauthorized (bad or missing X-API-Key)"}), 401

    if not os.environ.get("GEMINI_API_KEY"):
        return jsonify({
            "error": "server missing GEMINI_API_KEY — set the secret before use",
        }), 500

    intake = request.files.get("intake")
    if not intake:
        return jsonify({"error": "'intake' (.xlsx) file is required"}), 400

    _reap_old_jobs()

    job_id = uuid.uuid4().hex[:12]
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"gs_{job_id}_"))
    intake_path = tmp_dir / "intake.xlsx"
    out_path = tmp_dir / "ezjems_bulk_import.xlsx"
    intake.save(intake_path)

    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "running",
            "progress": {"current": 0, "total": 0, "report_no": ""},
            "created_at": time.time(),
            "updated_at": time.time(),
            "tmp_dir": str(tmp_dir),
        }

    t = threading.Thread(target=_run_job, args=(job_id, intake_path, out_path),
                         daemon=True)
    t.start()

    return jsonify({"job_id": job_id, "status": "running"}), 202


@app.route("/jobs/<job_id>")
def job_status(job_id: str):
    if not _authed():
        return jsonify({"error": "unauthorized (bad or missing X-API-Key)"}), 401

    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if job is None:
        return jsonify({"error": "job not found or expired"}), 404

    resp = {
        "job_id": job_id,
        "status": job["status"],
        "progress": job.get("progress"),
    }
    if job["status"] == "done":
        resp.update(job["result"])
    elif job["status"] == "failed":
        resp["error"] = job.get("error", "unknown error")
    return jsonify(resp)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=False)
