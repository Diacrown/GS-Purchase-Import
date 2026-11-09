"""
AGL Thai lab-report structured extraction.

Pulls the fields the EZ JEMS intake needs out of an AGL Thai Report Check
response HTML. Status / parsers are complete; the DOM selectors use three
fallback strategies so the extractor works even before a real AGL HTML has
been captured. Once a real response is in hand, tighten FIELD_LOCATORS.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

@dataclass
class Dimensions:
    length_mm: Optional[float] = None
    width_mm: Optional[float] = None
    height_mm: Optional[float] = None
    raw: Optional[str] = None


@dataclass
class AGLReport:
    # Identification
    report_number: Optional[str] = None
    date_of_issue: Optional[str] = None

    # Classification (feeds ERP after glossary lookup)
    species: Optional[str] = None
    variety: Optional[str] = None
    weight_ct: Optional[float] = None
    shape: Optional[str] = None
    cut: Optional[str] = None
    colour: Optional[str] = None
    transparency: Optional[str] = None
    dimensions: Dimensions = field(default_factory=Dimensions)

    # Provenance / Treatment
    treatment: Optional[str] = None
    origin: Optional[str] = None

    # Freeform
    comments: Optional[str] = None

    # Extraction metadata
    extraction_status: str = "ok"
    missing_fields: list[str] = field(default_factory=list)
    raw_html_excerpt: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> "AGLReport":
        dims = d.get("dimensions") or {}
        report = cls(**{k: v for k, v in d.items() if k != "dimensions"})
        if dims:
            report.dimensions = Dimensions(**dims)
        return report


# ---------------------------------------------------------------------------
# Locators — (destination_field, label_regex)
# ---------------------------------------------------------------------------

FIELD_LOCATORS: list[tuple[str, str]] = [
    ("report_number", r"Report\s*(?:No\.?|Number)"),
    ("date_of_issue", r"Date\s*(?:of\s*Issue|Issued)"),
    ("species",       r"Species"),
    ("variety",       r"Variety"),
    ("transparency",  r"Transparency"),
    ("treatment",     r"(?:Indication\s*of\s*Heating|Treatment|Enhancement)"),
    ("origin",        r"Origin"),
    ("comments",      r"(?:Comments?|Remarks?)"),
]


# ---------------------------------------------------------------------------
# Value parsers (pure functions — unit-testable without BeautifulSoup)
# ---------------------------------------------------------------------------

_WS_RE = re.compile(r"\s+")


def _normalise(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s = _WS_RE.sub(" ", s).strip()
    return s or None


def parse_weight(s: str) -> Optional[float]:
    if not s:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:ct|cts|carat)", s, re.I)
    return float(m.group(1)) if m else None


def parse_dimensions(s: str) -> Dimensions:
    raw = _normalise(s)
    if not raw:
        return Dimensions()
    m = re.search(
        r"(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)",
        raw, re.I,
    )
    if not m:
        return Dimensions(raw=raw)
    return Dimensions(
        length_mm=float(m.group(1)),
        width_mm=float(m.group(2)),
        height_mm=float(m.group(3)),
        raw=raw,
    )


def split_shape_and_cut(s: str) -> tuple[Optional[str], Optional[str]]:
    raw = _normalise(s)
    if not raw:
        return None, None
    parts = raw.split(" ", 1)
    if len(parts) == 1:
        return parts[0], None
    return parts[0], parts[1]


def parse_iso_date(s: str) -> Optional[str]:
    """Normalise AGL date strings like '18 April 2026' / '18/04/2026' / '2026-04-18'."""
    if not s:
        return None
    s = s.strip()
    # Already ISO
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return s
    # DD/MM/YYYY or DD-MM-YYYY
    m = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", s)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    # DD Month YYYY
    months = {m: i for i, m in enumerate(
        ["january","february","march","april","may","june","july",
         "august","september","october","november","december"], start=1)}
    m = re.fullmatch(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", s)
    if m:
        d, mo, y = m.groups()
        mo_num = months.get(mo.lower())
        if mo_num:
            return f"{y}-{mo_num:02d}-{int(d):02d}"
    return s  # give up gracefully — pass through


# ---------------------------------------------------------------------------
# HTML walker — tries <tr>, <dt>/<dd>, and flow-text "label: value"
# ---------------------------------------------------------------------------

def _locate_label_value(soup, label_regex: str) -> Optional[str]:
    try:
        from bs4 import BeautifulSoup  # noqa
    except ImportError:
        return None

    pat = re.compile(label_regex, re.I)

    for tr in soup.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        label = _normalise(cells[0].get_text(" "))
        if label and pat.search(label):
            value = " ".join(c.get_text(" ") for c in cells[1:])
            return _normalise(value)

    for dt in soup.find_all("dt"):
        label = _normalise(dt.get_text(" "))
        if label and pat.search(label):
            dd = dt.find_next_sibling("dd")
            if dd is not None:
                return _normalise(dd.get_text(" "))

    text = soup.get_text("\n")
    m = re.search(rf"{label_regex}\s*[:：]\s*(.+)", text, re.I)
    if m:
        return _normalise(m.group(1).splitlines()[0])
    return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = [
    "report_number", "variety", "weight_ct",
    "shape", "colour", "treatment", "origin",
]


def extract_from_html(html: str) -> AGLReport:
    report = AGLReport()
    report.raw_html_excerpt = (html or "")[:2000]

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        report.extraction_status = "failed"
        report.missing_fields = ["<bs4 not installed>"]
        return report

    if not html:
        report.extraction_status = "failed"
        report.missing_fields = ["<empty html>"]
        return report

    soup = BeautifulSoup(html, "html.parser")

    for dest, label_regex in FIELD_LOCATORS:
        value = _locate_label_value(soup, label_regex)
        if value is not None:
            setattr(report, dest, value)

    if report.date_of_issue:
        report.date_of_issue = parse_iso_date(report.date_of_issue)

    weight_raw = _locate_label_value(soup, r"Weight")
    if weight_raw:
        report.weight_ct = parse_weight(weight_raw)

    shape_raw = _locate_label_value(soup, r"(?:Shape(?:\s*&?\s*Cut)?|Cut)")
    if shape_raw:
        report.shape, report.cut = split_shape_and_cut(shape_raw)

    colour_raw = _locate_label_value(soup, r"Colou?r")
    if colour_raw:
        report.colour = colour_raw

    dim_raw = _locate_label_value(soup, r"(?:Measurements?|Dimensions?)")
    if dim_raw:
        report.dimensions = parse_dimensions(dim_raw)

    missing = [f for f in REQUIRED_FIELDS if not getattr(report, f, None)]
    report.missing_fields = missing
    if len(missing) == len(REQUIRED_FIELDS):
        report.extraction_status = "failed"
    elif missing:
        report.extraction_status = "partial"
    else:
        report.extraction_status = "ok"
    return report


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("usage: python -m gemstone_intake.extract <path-to-agl-response.html>",
              file=sys.stderr)
        sys.exit(2)
    with open(sys.argv[1], encoding="utf-8") as fh:
        print(extract_from_html(fh.read()).to_json())
