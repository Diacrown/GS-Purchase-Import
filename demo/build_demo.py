"""
Build a working end-to-end demo:
  1. Writes a synthetic intake Excel (3 rows: a Ruby, a Sapphire, an Emerald)
  2. Writes three AGL HTML responses in `agl_responses/`
  3. Runs the pipeline
  4. Writes the output EZ JEMS import Excel

Run from the project root:
    python -I demo/build_demo.py
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from gemstone_intake.pipeline import run_pipeline


HERE = Path(__file__).parent


# ---------------------------------------------------------------------------
# 1. intake Excel
# ---------------------------------------------------------------------------

INTAKE = [
    # Report No, Password, Unit Price (per-ct, per Sonesh 2026-11-09),
    # FWD LOC, FWD SSP, Lot No
    ("0063138",  "pw1",  300.00, "T", "DDX",  None),
    ("0063245",  "pw2", 1200.00, "T", "RJS",  "LOT-A1"),
    ("0063888",  "pw3",  850.50, "I", "CGEM", None),
]


def build_intake(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Intake"
    ws.append(["Report No", "Password", "Unit Price",
               "FWD LOC", "FWD SSP", "Lot No"])
    for row in INTAKE:
        ws.append(row)
    wb.save(path)


# ---------------------------------------------------------------------------
# 2. synthetic AGL HTML responses
# ---------------------------------------------------------------------------

RUBY_HTML = """
<html><body>
  <p>Report No: 0063138</p>
  <p>Date of Issue: 18 April 2026</p>
  <p>Species: Natural Corundum</p>
  <p>Variety: Ruby</p>
  <p>Weight: 0.78 ct</p>
  <p>Shape and Cut: Round Brilliant</p>
  <p>Colour: Pigeon Blood Red</p>
  <p>Measurements: 5.50 x 5.50 x 3.40 mm</p>
  <p>Transparency: Transparent</p>
  <p>Indication of Heating: No Indication of Heating</p>
  <p>Origin: Burma (Myanmar)</p>
</body></html>
"""

SAPPHIRE_HTML = """
<html><body>
  <table>
    <tr><td>Report No.</td><td>0063245</td></tr>
    <tr><td>Date of Issue</td><td>22/04/2026</td></tr>
    <tr><td>Species</td><td>Natural Corundum</td></tr>
    <tr><td>Variety</td><td>Sapphire</td></tr>
    <tr><td>Weight</td><td>2.15 cts</td></tr>
    <tr><td>Shape &amp; Cut</td><td>Oval Mixed</td></tr>
    <tr><td>Color</td><td>Cornflower Blue</td></tr>
    <tr><td>Measurements</td><td>8.20 x 6.40 x 4.15 mm</td></tr>
    <tr><td>Indication of Heating</td><td>Heated</td></tr>
    <tr><td>Origin</td><td>Sri Lanka (Ceylon)</td></tr>
  </table>
</body></html>
"""

EMERALD_HTML = """
<html><body>
  <dl>
    <dt>Report No</dt><dd>0063888</dd>
    <dt>Date of Issue</dt><dd>2026-05-02</dd>
    <dt>Species</dt><dd>Natural Beryl</dd>
    <dt>Variety</dt><dd>Emerald</dd>
    <dt>Weight</dt><dd>1.42 ct</dd>
    <dt>Shape and Cut</dt><dd>Emerald Step</dd>
    <dt>Colour</dt><dd>Green</dd>
    <dt>Measurements</dt><dd>7.10 x 5.20 x 3.80 mm</dd>
    <dt>Treatment</dt><dd>Minor Oil</dd>
    <dt>Origin</dt><dd>Colombia</dd>
  </dl>
</body></html>
"""


def build_agl_responses(dir_path: Path) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / "0063138.html").write_text(RUBY_HTML, encoding="utf-8")
    (dir_path / "0063245.html").write_text(SAPPHIRE_HTML, encoding="utf-8")
    (dir_path / "0063888.html").write_text(EMERALD_HTML, encoding="utf-8")


# ---------------------------------------------------------------------------
# 3. run the pipeline
# ---------------------------------------------------------------------------

def main() -> None:
    intake_path = HERE / "sample_intake.xlsx"
    agl_dir     = HERE / "agl_responses"
    out_path    = HERE / "out_ezjems_import.xlsx"

    build_intake(intake_path)
    build_agl_responses(agl_dir)

    result = run_pipeline(intake_path, agl_dir, out_path)
    print(result.summary())
    for row in result.per_row:
        tag = {"ok": "OK ", "partial": "AMB", "red": "RED", "failed": "RED"}.get(row["status"], "?")
        print(f"  [{tag}] {row['report_no']}: {row['status']}"
              f"{' | ' + '; '.join(row['warnings']) if row['warnings'] else ''}")


if __name__ == "__main__":
    main()
