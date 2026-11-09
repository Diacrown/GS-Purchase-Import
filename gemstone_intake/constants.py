"""
ERP constants for the GS BULK IMPORT template.

Row-level constants that apply to every intake row. All values confirmed
from the sample row in the real template; location/supplier values flagged
because they may vary by office.
"""
from __future__ import annotations
from dataclasses import dataclass


# --- Constants populating the EZ JEMS import columns -----------------------

CLARITY = "EC0"   # constant for colored gemstones (diamonds will have their own)
SBK     = "A"     # matches BULK PI SBK=A rule
IT      = "PP"    # matches BULK PI IT=PP rule (parcel/piece)
INV_EFFECT = 1    # inventory effect flag — confirmed constant (Sonesh, 2026-11-09)

# FWD LOC and FWD SSP are NOT constants — they vary per stone and are
# supplied in the manager's intake Excel (confirmed with Sonesh 2026-11-09).

# Lab identifier for the Lab column; tool is extensible to multi-lab later
LAB_AGL = "AGL"


# --- Column order — must match the GS_BULK_IMPORT template exactly --------
#
# Any mismatch here breaks the ERP import, so we ship these column names
# verbatim from the template header row and the writer always emits them
# in this order.

GS_BULK_IMPORT_COLUMNS: list[str] = [
    "Clarity", "Color", "Cut", "D%", "D", "Fluo",
    "FWD LOC", "FWD SSP", "Inv Effect", "IT", "Item #",
    "L", "Lab", "Lot No",
    "MEDIA1", "MEDIA2", "MEDIA3", "MEDIA4",
    "Pol", "Remarks", "Report No", "SBK", "Shape", "ST",
    "Sym", "T%", "Unit Price", "W", "Wt",
]

# Diamond-only columns — always left blank for gemstone intake
DIAMOND_ONLY_COLUMNS = {"Cut", "D%", "Fluo", "Pol", "Sym", "T%"}

# Yellow-highlighted (likely-mandatory) columns on the template header
MANDATORY_COLUMNS = {"Clarity", "Color", "Inv Effect", "IT", "SBK", "Shape"}


@dataclass
class ConstantsProfile:
    """
    Per-run constants bundle. These apply to every intake row.

    FWD LOC and FWD SSP are deliberately NOT here — they vary per stone
    and are read from the manager's intake Excel.
    """
    clarity: str = CLARITY
    sbk: str = SBK
    it: str = IT
    inv_effect: int = INV_EFFECT
    lab: str = LAB_AGL
