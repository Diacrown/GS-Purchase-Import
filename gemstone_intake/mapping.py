"""
Mapping layer — AGL JSON + manual intake inputs → EZ JEMS row (dict).

Row-level failure policy (matches BULK PI GENERATOR convention)
---------------------------------------------------------------
- ok       : every required field present and every glossary matched
- partial  : something missing or unmatched — row still written, flagged
             amber, raw AGL values preserved on the side
- failed   : extraction itself failed — row not written, flagged red
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .constants import ConstantsProfile
from .extract import AGLReport
from .glossaries import (
    lookup_colour, lookup_origin, lookup_shape,
    lookup_stone_type, lookup_treatment,
)
from .item_code import build_gemstone_item_code


@dataclass
class MappingResult:
    status: str                 # ok | partial | failed
    row: dict                   # keyed by EZ JEMS column name
    warnings: list[str] = field(default_factory=list)
    raw_values: dict = field(default_factory=dict)  # for side-column debug

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def agl_to_erp_row(
    report: AGLReport,
    unit_price: Optional[float] = None,
    fwd_loc: Optional[str] = None,
    fwd_ssp: Optional[str] = None,
    lot_no: Optional[str] = None,
    constants: Optional[ConstantsProfile] = None,
) -> MappingResult:
    """
    Produce one EZ JEMS-ready row dict from one AGLReport + manual inputs.

    All four manual inputs come from the manager's intake Excel:
      - unit_price  — per carat (per Sonesh 2026-11-09)
      - fwd_loc     — per stone
      - fwd_ssp     — per stone
      - lot_no      — optional
    """
    c = constants or ConstantsProfile()
    warnings: list[str] = []
    raw: dict = {}

    # --- Hard-stop: extraction already failed -----------------------------
    if report.extraction_status == "failed":
        return MappingResult(
            status="failed",
            row={},
            warnings=[f"AGL extraction failed: missing={report.missing_fields}"],
        )

    # --- Glossary lookups -------------------------------------------------
    st_hit    = lookup_stone_type(report.variety or "", report.species)
    shape_hit = lookup_shape(report.shape or "")
    col_hit   = lookup_colour(report.colour or "")
    treat_hit = lookup_treatment(report.treatment or "")
    orig_hit  = lookup_origin(report.origin or "")

    # Treatment and origin lookups are performed but NOT required for the
    # intake file — per Sonesh (2026-11-09), EZ JEMS doesn't track them at
    # intake. They're preserved in the AGL JSON for future reference only,
    # and unmatched values here do NOT flag the row.
    for name, hit in [
        ("stone_type", st_hit), ("shape", shape_hit), ("colour", col_hit),
    ]:
        if not hit.ok and hit.raw:
            warnings.append(f"unmatched {name}: {hit.raw!r}")
            raw[name] = hit.raw
    # Treatment and origin still go into raw_values for the side columns, but
    # a miss doesn't warn — they don't reach the ERP.
    if treat_hit.raw:
        raw["treatment"] = treat_hit.raw
    if orig_hit.raw:
        raw["origin"] = orig_hit.raw

    # --- Item # ----------------------------------------------------------
    item_number = build_gemstone_item_code(
        stone_prefix=st_hit.prefix or "???",
        shape_2digit=shape_hit.shape_2digit or "??",
        colour_3letter=col_hit.value or "???",
        weight_ct=report.weight_ct,
        dims=report.dimensions,
    )

    # --- Assemble row -----------------------------------------------------
    # Per Sonesh (2026-11-09):
    #   - ST holds the 3-letter short code (Item# prefix), not the long name.
    #   - Treatment and Origin do NOT go to EZ JEMS at intake — Remarks stays
    #     empty unless the manager supplies something explicit later.
    #   - FWD LOC and FWD SSP are per-stone inputs from the intake Excel.
    row: dict = {
        "Clarity":    c.clarity,
        "Color":      col_hit.value or None,
        "Cut":        None,            # diamond-only
        "D%":         None,            # diamond-only
        "D":          report.dimensions.height_mm,
        "Fluo":       None,            # diamond-only
        "FWD LOC":    fwd_loc,
        "FWD SSP":    fwd_ssp,
        "Inv Effect": c.inv_effect,
        "IT":         c.it,
        "Item #":     item_number,
        "L":          report.dimensions.length_mm,
        "Lab":        c.lab,
        "Lot No":     lot_no,
        "MEDIA1":     None,
        "MEDIA2":     None,
        "MEDIA3":     None,
        "MEDIA4":     None,
        "Pol":        None,            # diamond-only
        "Remarks":    None,
        "Report No":  report.report_number,
        "SBK":        c.sbk,
        "Shape":      shape_hit.value or None,
        "ST":         st_hit.prefix or None,
        "Sym":        None,            # diamond-only
        "T%":         None,            # diamond-only
        "Unit Price": unit_price,
        "W":          report.dimensions.width_mm,
        "Wt":         report.weight_ct,
    }

    # --- Classify status --------------------------------------------------
    status = "ok"
    # extraction said "partial" → that's at least amber
    if report.extraction_status == "partial":
        status = "partial"
        warnings.append(f"AGL partial: missing={report.missing_fields}")
    # any unmatched glossary → amber
    if warnings:
        status = "partial"
    # critical fields missing from the row itself → amber
    critical = ("Color", "Shape", "ST", "Item #", "Report No", "Wt",
                "FWD LOC", "FWD SSP")
    missing_critical = [k for k in critical if row.get(k) in (None, "", "???")]
    if missing_critical:
        status = "partial"
        warnings.append(f"missing critical field(s): {missing_critical}")

    return MappingResult(status=status, row=row, warnings=warnings, raw_values=raw)
