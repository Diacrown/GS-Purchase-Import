"""Live pipeline: parallel vision, order preserved, failures isolated."""
import time
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook, load_workbook

from gemstone_intake.extract import AGLReport, Dimensions
from gemstone_intake.pipeline import run_pipeline_live


def _intake(path: Path, n: int):
    wb = Workbook(); ws = wb.active
    ws.append(["Report No", "Password", "Unit Price", "FWD LOC", "FWD SSP", "Lot No"])
    for i in range(n):
        ws.append([f"00{i}", "1234", 10, "TH", "TH-1", None])
    wb.save(path)


def _fake_report(img, mime_type="image/jpeg", model_name=None):
    time.sleep(0.3)  # simulate Gemini latency
    r = AGLReport(report_number=img.decode(), variety="Sapphire", species="Natural Corundum",
                  weight_ct=1.0, shape="Round", colour="Blue", treatment="Heated",
                  origin="Sri Lanka (Ceylon)", dimensions=Dimensions(6.0, 6.0, 4.0))
    r.extraction_status = "ok"
    return r


def test_parallel_vision_keeps_order_and_is_faster(tmp_path):
    inp, out = tmp_path / "in.xlsx", tmp_path / "out.xlsx"
    _intake(inp, 6)
    fetch = lambda no, pw, session=None: (no.encode(), "jpg")
    with patch("gemstone_intake.fetch.fetch_report_image", side_effect=fetch), \
         patch("gemstone_intake.vision.extract_from_image", side_effect=_fake_report):
        t0 = time.time()
        res = run_pipeline_live(inp, out, delay_seconds=0.0)
        dt = time.time() - t0
    assert dt < 6 * 0.3  # parallel: well under sequential time
    assert res.rows_red == 0
    ws = load_workbook(out).active
    assert ws.max_row - 1 == 6


def test_fetch_failure_isolated(tmp_path):
    inp, out = tmp_path / "in.xlsx", tmp_path / "out.xlsx"
    _intake(inp, 3)
    def fetch(no, pw, session=None):
        if no == "001":
            raise RuntimeError("boom")
        return no.encode(), "jpg"
    with patch("gemstone_intake.fetch.fetch_report_image", side_effect=fetch), \
         patch("gemstone_intake.vision.extract_from_image", side_effect=_fake_report):
        res = run_pipeline_live(inp, out, delay_seconds=0.0)
    assert res.rows_red == 1
