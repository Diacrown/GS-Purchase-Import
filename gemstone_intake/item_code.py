"""
Item # generation — ports BULK PI GENERATOR's gemstone code logic.

Format:  {ST_prefix}{shape_2digit}{colour}{measurement_code}
Sample:  RUB10RED35  →  Ruby + Round(10) + Red + size-code-35

Measurement-code encoding
-------------------------
BULK PI's existing `buildGemstoneCode` uses "different measurement-encoding
rules for round vs. non-round shapes" (per project memo). This module ships
a defensible first implementation plus a clear seam so the exact rule can
be ported from BULK PI's index.html in one place without touching callers.

- Round shapes:      take the LARGEST stated mm dimension, multiply by 10,
                     floor to int, format as 2–3 digits. If dimensions are
                     missing, fall back to a weight-bucket (ct × 100).
- Non-round shapes:  encode length + width as 2-digit mm×10 pairs, e.g.
                     6.52 × 4.48 → "6544".

If you have the canonical BULK PI rule in hand, replace `_measurement_code`
and the rest of the module still works — same signature.
"""
from __future__ import annotations

from typing import Callable, Optional

from .extract import Dimensions


# Shapes considered "round" for measurement-encoding purposes.
# The 2-digit shape code "10" is the authoritative check.
_ROUND_SHAPE_CODES = {"10"}


def _is_round(shape_2digit: str) -> bool:
    return shape_2digit in _ROUND_SHAPE_CODES


def _measurement_code_round(weight_ct: Optional[float], dims: Dimensions) -> str:
    """
    Default round-shape measurement encoding.

    PORT FROM BULK PI if you have the canonical rule. The structure here is:
      - prefer dimension-based (largest mm × 10, floor)
      - fall back to weight-based bucket (ct × 100, 3 digits)
    """
    # Dimension path — largest of L, W, (H)
    candidates = [d for d in (dims.length_mm, dims.width_mm, dims.height_mm) if d]
    if candidates:
        largest = max(candidates)
        return f"{int(largest * 10):02d}"

    if weight_ct is not None:
        # 0.78 ct → 078
        return f"{int(round(weight_ct * 100)):03d}"

    return "00"


def _measurement_code_fancy(weight_ct: Optional[float], dims: Dimensions) -> str:
    """
    Default non-round-shape measurement encoding.

    PORT FROM BULK PI if you have the canonical rule. Default here:
      - "LLWW" where LL = int(L*10), WW = int(W*10)
      - if dimensions missing, fall back to weight × 100 (3 digits)
    """
    if dims.length_mm and dims.width_mm:
        l = int(dims.length_mm * 10)
        w = int(dims.width_mm * 10)
        return f"{l:02d}{w:02d}"

    if weight_ct is not None:
        return f"{int(round(weight_ct * 100)):03d}"

    return "0000"


def default_measurement_code(
    shape_2digit: str,
    weight_ct: Optional[float],
    dims: Dimensions,
) -> str:
    if _is_round(shape_2digit):
        return _measurement_code_round(weight_ct, dims)
    return _measurement_code_fancy(weight_ct, dims)


MeasurementCodeFn = Callable[[str, Optional[float], Dimensions], str]


def build_gemstone_item_code(
    stone_prefix: str,
    shape_2digit: str,
    colour_3letter: str,
    weight_ct: Optional[float] = None,
    dims: Optional[Dimensions] = None,
    measurement_code_fn: MeasurementCodeFn = default_measurement_code,
) -> str:
    """
    Compose a gemstone Item #.

    Any missing input is replaced by a placeholder ("?") so the caller can
    detect and flag the row instead of shipping a silently-wrong code.
    """
    dims = dims or Dimensions()
    sp = (stone_prefix or "???").upper()
    sh = (shape_2digit or "??")
    co = (colour_3letter or "???").upper()
    meas = measurement_code_fn(sh, weight_ct, dims)
    return f"{sp}{sh}{co}{meas}"
