"""
Bulk demo:

  1. Synthesises 15 AGL cert responses covering the glossary spread —
     different stone types (including sub-varieties that collapse to parent),
     different shapes (including the OCT->EME override), premium colour phrases
     (Cornflower Blue, Pigeon Blood Red), varied treatments and origins.

  2. Writes a realistic intake Excel with all 15 rows + the new FWD LOC /
     FWD SSP per-row columns (per Sonesh 2026-11-09).

  3. Runs the full pipeline end-to-end against the synthesised data.

  4. Produces the EZ JEMS-shaped bulk purchase import file.

Run:
    PYTHONPATH=. python demo/build_bulk_demo.py
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from gemstone_intake.pipeline import run_pipeline


HERE = Path(__file__).parent
OUT_DIR = HERE / "bulk"


# ---------------------------------------------------------------------------
# The 15 stones. Each row carries the AGL cert fields + the manager's intake
# inputs (unit price, FWD LOC, FWD SSP). A "html_shape" of 'p', 'table' or
# 'dl' decides which HTML shape the cert is rendered as — exercises all
# three extraction strategies.
# ---------------------------------------------------------------------------

STONES = [
    # --- Classic three — the demo canonical ------------------------------
    dict(report="AGL-100001", password="pw01", unit_price=350.00,
         fwd_loc="T", fwd_ssp="DDX", lot_no=None,
         variety="Ruby", species="Natural Corundum",
         weight="0.78 ct", shape_cut="Round Brilliant",
         colour="Pigeon Blood Red",
         meas="5.50 x 5.50 x 3.40 mm",
         treatment="No Indication of Heating",
         origin="Burma (Myanmar)",
         html_shape="p"),

    dict(report="AGL-100002", password="pw02", unit_price=1200.00,
         fwd_loc="T", fwd_ssp="RJS", lot_no="LOT-A1",
         variety="Sapphire", species="Natural Corundum",
         weight="2.15 cts", shape_cut="Oval Mixed",
         colour="Cornflower Blue",
         meas="8.20 x 6.40 x 4.15 mm",
         treatment="Heated",
         origin="Sri Lanka (Ceylon)",
         html_shape="table"),

    dict(report="AGL-100003", password="pw03", unit_price=850.50,
         fwd_loc="I", fwd_ssp="CGEM", lot_no=None,
         variety="Emerald", species="Natural Beryl",
         weight="1.42 ct", shape_cut="Emerald Step",
         colour="Green",
         meas="7.10 x 5.20 x 3.80 mm",
         treatment="Minor Oil",
         origin="Colombia",
         html_shape="dl"),

    # --- Garnet sub-varieties — collapse to parent GAR -------------------
    dict(report="AGL-100004", password="pw04", unit_price=180.00,
         fwd_loc="I", fwd_ssp="JCS", lot_no=None,
         variety="Spessartite Garnet", species="Natural Garnet",
         weight="2.10 cts", shape_cut="Oval Mixed",
         colour="Orange",
         meas="8.60 x 6.80 x 4.20 mm",
         treatment="No Indication of Heating",
         origin="Mozambique",
         html_shape="p"),

    dict(report="AGL-100005", password="pw05", unit_price=420.00,
         fwd_loc="I", fwd_ssp="JCS", lot_no=None,
         variety="Tsavorite Garnet", species="Natural Garnet",
         weight="1.80 ct", shape_cut="Trilliant",
         colour="Vivid Green",
         meas="7.50 x 7.50 x 4.60 mm",
         treatment="No Indication of Heating",
         origin="Kenya",
         html_shape="table"),

    # --- Premium sapphires -----------------------------------------------
    dict(report="AGL-100006", password="pw06", unit_price=2800.00,
         fwd_loc="T", fwd_ssp="RJS", lot_no="LOT-A2",
         variety="Padparadscha Sapphire", species="Natural Corundum",
         weight="1.70 ct", shape_cut="Cushion Mixed",
         colour="Pinkish Orange",
         meas="7.00 x 6.20 x 4.00 mm",
         treatment="No Indication of Heating",
         origin="Sri Lanka (Ceylon)",
         html_shape="dl"),

    dict(report="AGL-100007", password="pw07", unit_price=380.00,
         fwd_loc="T", fwd_ssp="RJS", lot_no=None,
         variety="Yellow Sapphire", species="Natural Corundum",
         weight="2.80 cts", shape_cut="Oval Mixed",
         colour="Vivid Yellow",
         meas="9.10 x 7.20 x 4.80 mm",
         treatment="Heated",
         origin="Sri Lanka (Ceylon)",
         html_shape="p"),

    dict(report="AGL-100008", password="pw08", unit_price=900.00,
         fwd_loc="T", fwd_ssp="DDX", lot_no=None,
         variety="Pink Sapphire", species="Natural Corundum",
         weight="3.20 cts", shape_cut="Pear Mixed",
         colour="Pink",
         meas="11.00 x 7.80 x 5.20 mm",
         treatment="Heated",
         origin="Madagascar",
         html_shape="table"),

    # --- Rare / sub-variety stones ---------------------------------------
    dict(report="AGL-100009", password="pw09", unit_price=5500.00,
         fwd_loc="I", fwd_ssp="PRB", lot_no="LOT-B1",
         variety="Paraiba Tourmaline", species="Natural Tourmaline",
         weight="1.25 ct", shape_cut="Cushion Mixed",
         colour="Blue",
         meas="6.50 x 6.00 x 4.10 mm",
         treatment="Heated",
         origin="Mozambique",
         html_shape="dl"),

    dict(report="AGL-100010", password="pw10", unit_price=280.00,
         fwd_loc="I", fwd_ssp="TNZ", lot_no=None,
         variety="Tanzanite", species="Natural Zoisite",
         weight="4.50 cts", shape_cut="Oval Mixed",
         colour="Violet",
         meas="12.00 x 8.50 x 5.80 mm",
         treatment="Heated",
         origin="Tanzania",
         html_shape="p"),

    dict(report="AGL-100011", password="pw11", unit_price=320.00,
         fwd_loc="T", fwd_ssp="DDX", lot_no=None,
         variety="Spinel", species="Natural Spinel",
         weight="1.95 ct", shape_cut="Round Brilliant",
         colour="Red",
         meas="7.10 x 7.10 x 4.50 mm",
         treatment="No Indication of Heating",
         origin="Burma (Myanmar)",
         html_shape="table"),

    # --- Shape edge cases ------------------------------------------------
    # Star Sapphire + Cabochon shape (3-letter CBN, 2-digit 84)
    dict(report="AGL-100012", password="pw12", unit_price=150.00,
         fwd_loc="T", fwd_ssp="RJS", lot_no=None,
         variety="Star Sapphire", species="Natural Corundum",
         weight="5.20 cts", shape_cut="Cabochon",
         colour="Blue",
         meas="10.50 x 8.80 x 5.50 mm",
         treatment="No Indication of Heating",
         origin="Burma (Myanmar)",
         html_shape="p"),

    # Octagonal shape — exercises the OCT->EME BULK PI override
    dict(report="AGL-100013", password="pw13", unit_price=650.00,
         fwd_loc="I", fwd_ssp="CGEM", lot_no=None,
         variety="Emerald", species="Natural Beryl",
         weight="2.05 cts", shape_cut="Octagonal Step",
         colour="Green",
         meas="8.40 x 6.20 x 4.00 mm",
         treatment="Minor Oil",
         origin="Zambia",
         html_shape="dl"),

    # Heart shape ruby (HRT / 21)
    dict(report="AGL-100014", password="pw14", unit_price=1100.00,
         fwd_loc="T", fwd_ssp="DDX", lot_no=None,
         variety="Ruby", species="Natural Corundum",
         weight="1.10 ct", shape_cut="Heart Mixed",
         colour="Red",
         meas="6.80 x 6.50 x 3.90 mm",
         treatment="Heated",
         origin="Mozambique",
         html_shape="table"),

    # --- Deliberate amber case — unusual colour phrase -------------------
    dict(report="AGL-100015", password="pw15", unit_price=450.00,
         fwd_loc="I", fwd_ssp="JCS", lot_no="LOT-C1",
         variety="Rhodolite Garnet", species="Natural Garnet",
         weight="1.65 ct", shape_cut="Oval Mixed",
         colour="Raspberry",     # intentionally unmapped — should flag amber
         meas="7.80 x 6.20 x 4.00 mm",
         treatment="No Indication of Heating",
         origin="Tanzania",
         html_shape="p"),
]


# ---------------------------------------------------------------------------
# AGL response HTML renderers — three shapes to exercise all extraction paths
# ---------------------------------------------------------------------------

def _render_p(s: dict) -> str:
    return f"""
<html><body>
  <p>Report No: {s['report']}</p>
  <p>Date of Issue: 2026-11-09</p>
  <p>Species: {s['species']}</p>
  <p>Variety: {s['variety']}</p>
  <p>Weight: {s['weight']}</p>
  <p>Shape and Cut: {s['shape_cut']}</p>
  <p>Colour: {s['colour']}</p>
  <p>Measurements: {s['meas']}</p>
  <p>Transparency: Transparent</p>
  <p>Indication of Heating: {s['treatment']}</p>
  <p>Origin: {s['origin']}</p>
</body></html>
""".strip()


def _render_table(s: dict) -> str:
    return f"""
<html><body>
  <table>
    <tr><td>Report No.</td><td>{s['report']}</td></tr>
    <tr><td>Date of Issue</td><td>09/11/2026</td></tr>
    <tr><td>Species</td><td>{s['species']}</td></tr>
    <tr><td>Variety</td><td>{s['variety']}</td></tr>
    <tr><td>Weight</td><td>{s['weight']}</td></tr>
    <tr><td>Shape &amp; Cut</td><td>{s['shape_cut']}</td></tr>
    <tr><td>Color</td><td>{s['colour']}</td></tr>
    <tr><td>Measurements</td><td>{s['meas']}</td></tr>
    <tr><td>Indication of Heating</td><td>{s['treatment']}</td></tr>
    <tr><td>Origin</td><td>{s['origin']}</td></tr>
  </table>
</body></html>
""".strip()


def _render_dl(s: dict) -> str:
    return f"""
<html><body>
  <dl>
    <dt>Report No</dt><dd>{s['report']}</dd>
    <dt>Date of Issue</dt><dd>9 November 2026</dd>
    <dt>Species</dt><dd>{s['species']}</dd>
    <dt>Variety</dt><dd>{s['variety']}</dd>
    <dt>Weight</dt><dd>{s['weight']}</dd>
    <dt>Shape and Cut</dt><dd>{s['shape_cut']}</dd>
    <dt>Colour</dt><dd>{s['colour']}</dd>
    <dt>Measurements</dt><dd>{s['meas']}</dd>
    <dt>Treatment</dt><dd>{s['treatment']}</dd>
    <dt>Origin</dt><dd>{s['origin']}</dd>
  </dl>
</body></html>
""".strip()


RENDERERS = {"p": _render_p, "table": _render_table, "dl": _render_dl}


# ---------------------------------------------------------------------------
# Build + run
# ---------------------------------------------------------------------------

def build_intake(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Intake"
    ws.append(["Report No", "Password", "Unit Price",
               "FWD LOC", "FWD SSP", "Lot No"])
    for s in STONES:
        ws.append([s["report"], s["password"], s["unit_price"],
                   s["fwd_loc"], s["fwd_ssp"], s["lot_no"]])
    wb.save(path)


def build_responses(dir_path: Path) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    for s in STONES:
        renderer = RENDERERS[s["html_shape"]]
        (dir_path / f"{s['report']}.html").write_text(renderer(s), encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    intake_path = OUT_DIR / "bulk_intake.xlsx"
    agl_dir     = OUT_DIR / "agl_responses"
    out_path    = OUT_DIR / "ezjems_bulk_import.xlsx"

    build_intake(intake_path)
    build_responses(agl_dir)

    result = run_pipeline(intake_path, agl_dir, out_path)
    print(result.summary())
    print()
    print(f"{'Report No':<12}  {'Status':<8}  Warnings")
    print("-" * 80)
    for row in result.per_row:
        warnings = "; ".join(row["warnings"]) if row["warnings"] else ""
        print(f"{row['report_no']:<12}  {row['status']:<8}  {warnings}")


if __name__ == "__main__":
    main()
