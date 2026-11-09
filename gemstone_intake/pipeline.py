"""
Pipeline — reads the manager's intake Excel and a folder of AGL responses,
produces the EZ JEMS import Excel.

Intake Excel shape (manager fills this):
    | Report No | Password | Unit Price | Lot No (optional) |

AGL responses folder:
    Each row's Report No matches a file named `<ReportNo>.html` or
    `<ReportNo>.json` in the given folder. HTML is parsed on the fly;
    JSON is treated as an already-extracted `AGLReport.to_dict()`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from openpyxl import Workbook, load_workbook

from .constants import (
    ConstantsProfile, DIAMOND_ONLY_COLUMNS, GS_BULK_IMPORT_COLUMNS,
    MANDATORY_COLUMNS,
)
from .extract import AGLReport, extract_from_html
from .mapping import MappingResult, agl_to_erp_row


@dataclass
class PipelineResult:
    rows_written: int = 0
    rows_amber: int = 0
    rows_red: int = 0
    per_row: list[dict] = field(default_factory=list)   # {report_no, status, warnings}
    output_path: Optional[Path] = None

    def summary(self) -> str:
        return (f"{self.rows_written} rows written "
                f"({self.rows_amber} amber, {self.rows_red} red); "
                f"output → {self.output_path}")


# ---------------------------------------------------------------------------
# Intake reader
# ---------------------------------------------------------------------------

# Required intake columns; Lot No is the only optional column.
INTAKE_COLUMNS = ["Report No", "Password", "Unit Price",
                  "FWD LOC", "FWD SSP", "Lot No"]
REQUIRED_INTAKE_COLUMNS = ["Report No", "Password", "Unit Price",
                           "FWD LOC", "FWD SSP"]


def read_intake(path: Path) -> list[dict]:
    """
    Read the manager's intake workbook. Expects the INTAKE_COLUMNS above as
    the header row. `Lot No` is optional.
    """
    wb = load_workbook(path, data_only=True)
    ws = wb.active
    headers = [c.value for c in ws[1]]
    missing = [h for h in REQUIRED_INTAKE_COLUMNS if h not in headers]
    if missing:
        raise ValueError(f"intake file missing required columns: {missing}; "
                         f"got: {headers}")

    idx = {h: headers.index(h) for h in headers if h in INTAKE_COLUMNS}
    rows: list[dict] = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        if all(v in (None, "") for v in r):
            continue
        rows.append({
            "Report No":  r[idx["Report No"]],
            "Password":   r[idx["Password"]],
            "Unit Price": r[idx["Unit Price"]],
            "FWD LOC":    r[idx["FWD LOC"]],
            "FWD SSP":    r[idx["FWD SSP"]],
            "Lot No":     r[idx["Lot No"]] if "Lot No" in idx else None,
        })
    return rows


# ---------------------------------------------------------------------------
# AGL response loader
# ---------------------------------------------------------------------------

def _load_agl_response(agl_dir: Path, report_no: str) -> Optional[AGLReport]:
    if not report_no:
        return None
    rn = str(report_no).strip()

    json_path = agl_dir / f"{rn}.json"
    if json_path.exists():
        with open(json_path, encoding="utf-8") as fh:
            return AGLReport.from_dict(json.load(fh))

    html_path = agl_dir / f"{rn}.html"
    if html_path.exists():
        with open(html_path, encoding="utf-8") as fh:
            return extract_from_html(fh.read())

    return None


# ---------------------------------------------------------------------------
# Output writer
# ---------------------------------------------------------------------------

# Extra side columns for operator visibility (NOT imported into EZ JEMS).
# The ERP reads GS_BULK_IMPORT_COLUMNS only; extra columns after column 29
# are safely ignored by the importer per System Plus's own template shape.

SIDE_COLUMNS = ["__Status", "__Warnings", "__Raw AGL Shape", "__Raw AGL Colour",
                "__Raw AGL Variety", "__Raw AGL Treatment", "__Raw AGL Origin"]


def _amber_fill():
    from openpyxl.styles import PatternFill
    return PatternFill(start_color="FFFFF2CC", end_color="FFFFF2CC", fill_type="solid")


def _red_fill():
    from openpyxl.styles import PatternFill
    return PatternFill(start_color="FFF8CBAD", end_color="FFF8CBAD", fill_type="solid")


def _mandatory_fill():
    from openpyxl.styles import PatternFill
    return PatternFill(start_color="FFFFFF00", end_color="FFFFFF00", fill_type="solid")


def write_output(
    mapping_results: list[tuple[dict, MappingResult]],
    out_path: Path,
) -> PipelineResult:
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet"

    header_row = GS_BULK_IMPORT_COLUMNS + SIDE_COLUMNS
    ws.append(header_row)
    # Yellow-fill the mandatory headers to mirror the real template
    for col_idx, name in enumerate(header_row, start=1):
        if name in MANDATORY_COLUMNS:
            ws.cell(row=1, column=col_idx).fill = _mandatory_fill()

    result = PipelineResult()
    for intake, mr in mapping_results:
        report_no = intake.get("Report No")
        # red = skip from export
        if mr.status == "failed":
            result.rows_red += 1
            result.per_row.append({"report_no": report_no, "status": "red",
                                   "warnings": mr.warnings})
            continue

        row_values = [mr.row.get(col) for col in GS_BULK_IMPORT_COLUMNS]
        side = [
            mr.status,
            "; ".join(mr.warnings) if mr.warnings else "",
            mr.raw_values.get("shape", ""),
            mr.raw_values.get("colour", ""),
            mr.raw_values.get("stone_type", ""),
            mr.raw_values.get("treatment", ""),
            mr.raw_values.get("origin", ""),
        ]
        ws.append(row_values + side)
        excel_row = ws.max_row

        # Color-tint amber rows in the __Status column so the manager spots them
        if mr.status == "partial":
            result.rows_amber += 1
            status_col = len(GS_BULK_IMPORT_COLUMNS) + 1
            ws.cell(row=excel_row, column=status_col).fill = _amber_fill()
        result.rows_written += 1
        result.per_row.append({"report_no": report_no, "status": mr.status,
                               "warnings": mr.warnings})

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    result.output_path = out_path
    return result


# ---------------------------------------------------------------------------
# Top-level entry
# ---------------------------------------------------------------------------

def run_pipeline(
    intake_path: Path,
    agl_dir: Path,
    out_path: Path,
    constants: Optional[ConstantsProfile] = None,
) -> PipelineResult:
    intake_rows = read_intake(intake_path)
    pairs: list[tuple[dict, MappingResult]] = []

    for intake in intake_rows:
        report = _load_agl_response(agl_dir, str(intake["Report No"]))
        if report is None:
            # Treat as hard failure — row red, written to the per-row log
            mr = MappingResult(
                status="failed",
                row={},
                warnings=[f"no AGL response file for Report No {intake['Report No']}"],
            )
            pairs.append((intake, mr))
            continue

        mr = agl_to_erp_row(
            report,
            unit_price=intake.get("Unit Price"),
            fwd_loc=intake.get("FWD LOC"),
            fwd_ssp=intake.get("FWD SSP"),
            lot_no=intake.get("Lot No"),
            constants=constants,
        )
        pairs.append((intake, mr))

    return write_output(pairs, out_path)
