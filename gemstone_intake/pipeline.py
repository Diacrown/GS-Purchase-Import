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
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import requests
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

    Finds the FIRST sheet whose header row contains all required columns —
    multi-sheet workbooks (with a readme tab etc.) work fine.
    """
    wb = load_workbook(path, data_only=True)
    ws = None
    for candidate in wb.worksheets:
        headers = [c.value for c in candidate[1]]
        if all(h in headers for h in REQUIRED_INTAKE_COLUMNS):
            ws = candidate
            break
    if ws is None:
        # Fall back to the active sheet so the error message is informative
        ws = wb.active
    headers = [c.value for c in ws[1]]
    missing = [h for h in REQUIRED_INTAKE_COLUMNS if h not in headers]
    if missing:
        raise ValueError(f"no sheet in the workbook has the required intake columns: "
                         f"{missing} missing; sheets tried: {wb.sheetnames}")

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
    """
    File-based pipeline (kept for offline tests / backward compatibility).

    Each intake row's Report No must match an AGL response file at
    `<agl_dir>/<ReportNo>.html` or `.json`.
    """
    intake_rows = read_intake(intake_path)
    pairs: list[tuple[dict, MappingResult]] = []

    for intake in intake_rows:
        report = _load_agl_response(agl_dir, str(intake["Report No"]))
        if report is None:
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


ProgressFn = Callable[[int, int, str], None]


def run_pipeline_live(
    intake_path: Path,
    out_path: Path,
    constants: Optional[ConstantsProfile] = None,
    delay_seconds: float = 2.0,
    progress: Optional[ProgressFn] = None,
) -> PipelineResult:
    """
    Live pipeline — one upload in, one file out.

    For each row of the intake Excel:
      1. Fetch the cert image from aglthai.com (needs network egress to that host).
      2. Send the image to Google Gemini for structured field extraction
         (needs GEMINI_API_KEY env var).
      3. Map to EZ JEMS row, flag ok/amber/red.

    Rate-limited to one AGL call every `delay_seconds` (default 2s, matches
    Certificate-Scrapper's convention) to stay polite with aglthai.com.
    """
    from .fetch import fetch_report_image, mime_for_ext, parse_password
    from .vision import extract_from_image

    intake_rows = read_intake(intake_path)
    pairs: list[tuple[dict, MappingResult]] = []
    session = requests.Session()
    total = len(intake_rows)

    # AGL lookups stay sequential (polite 2s spacing); Gemini reads run in
    # parallel in a thread pool so total time ~ AGL spacing, not AGL + Gemini
    # latency per row. Results are collected back in original row order.
    workers = max(1, int(os.environ.get("VISION_CONCURRENCY", "8")))
    # slots[i] = ("done", intake, MappingResult) | ("future", intake, Future)
    slots: list[tuple] = []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, intake in enumerate(intake_rows, start=1):
            report_no_raw = intake.get("Report No")
            password_raw = intake.get("Password")
            report_no = str(report_no_raw).strip() if report_no_raw else ""
            password = parse_password(password_raw) or (
                str(password_raw).strip() if password_raw else ""
            )

            if progress:
                progress(i, 2 * total, f"Fetching certificate {i}/{total} from AGL — {report_no or '<blank>'}")

            if not report_no or not password:
                slots.append(("done", intake, MappingResult(
                    status="failed", row={},
                    warnings=["missing Report No or Password in intake row"],
                )))
                continue

            # --- 1. Fetch cert image (sequential, rate-limited) ------------
            print(f"[pipeline] row {i}/{total}: fetching AGL report {report_no!r}", flush=True)
            try:
                img_bytes, ext = fetch_report_image(report_no, password, session=session)
                print(f"[pipeline] fetched {len(img_bytes)} bytes, ext={ext}", flush=True)
            except Exception as e:
                print(f"[pipeline] AGL fetch FAILED for {report_no}: {type(e).__name__}: {e}", flush=True)
                slots.append(("done", intake, MappingResult(
                    status="failed", row={},
                    warnings=[f"AGL fetch failed: {type(e).__name__}: {e}"],
                )))
                if i < total and delay_seconds > 0:
                    time.sleep(delay_seconds)
                continue

            # --- 2. Gemini read (parallel) ---------------------------------
            fut = pool.submit(extract_from_image, img_bytes, mime_for_ext(ext))
            slots.append(("future", intake, fut))

            if i < total and delay_seconds > 0:
                time.sleep(delay_seconds)

        # --- 3. Wait for Gemini reads (progress counts completions) --------
        pending = [p for k, _, p in slots if k == "future"]
        done_n = 0
        for _ in as_completed(pending):
            done_n += 1
            if progress:
                progress(total + done_n, 2 * total,
                         f"Reading certificates with Gemini: {done_n}/{len(pending)} done")

        # --- 4. Collect in original order, map + flag ----------------------
        for kind, intake, payload in slots:
            if kind == "done":
                pairs.append((intake, payload))
                continue
            try:
                report = payload.result()
                print(f"[pipeline] vision status={report.extraction_status} missing={report.missing_fields}", flush=True)
            except Exception as e:
                print(f"[pipeline] vision call RAISED: {type(e).__name__}: {e}", flush=True)
                pairs.append((intake, MappingResult(
                    status="failed", row={},
                    warnings=[f"vision extract failed: {type(e).__name__}: {e}"],
                )))
                continue
            pairs.append((intake, agl_to_erp_row(
                report,
                unit_price=intake.get("Unit Price"),
                fwd_loc=intake.get("FWD LOC"),
                fwd_ssp=intake.get("FWD SSP"),
                lot_no=intake.get("Lot No"),
                constants=constants,
            )))

    return write_output(pairs, out_path)
