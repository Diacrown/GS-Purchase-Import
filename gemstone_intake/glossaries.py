"""
Glossaries — AGL cert wording → EZ JEMS values.

These are the mapping tables Sonesh / the ERP stock export will finalise.
Shipped here as EDITABLE Python dicts (no network, no DB) so the user can
patch them in one place as master-data decisions come in.

Every lookup function returns a `GlossaryHit`:

    hit.ok    — True if the input matched a known entry
    hit.value — the mapped value (or the raw input, if no match)
    hit.raw   — the untouched AGL input, preserved for amber-flag side cols

Unmatched inputs never crash the pipeline; they come back `ok=False` and
the pipeline flags that row amber.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class GlossaryHit:
    ok: bool
    value: str
    raw: str
    prefix: Optional[str] = None  # for stone types — also used as Item# prefix
    shape_2digit: Optional[str] = None  # for shapes — used in Item#


def _norm(s: Optional[str]) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip().lower()


# ===========================================================================
# STONE TYPE — AGL `variety` → ERP `ST` + Item# prefix
# ===========================================================================
# Confirmed from BULK PI (Ruby → RUB) and the sample row (RUB10RED35).
# Rest are sensible defaults per common jewellery-industry 3-letter codes;
# every "??" needs Sonesh confirmation.

STONE_TYPE_MAP: dict[str, tuple[str, str]] = {
    # key (lowercase)             → (ERP ST label, Item# prefix)
    "ruby":                         ("Ruby",       "RUB"),
    "sapphire":                     ("Sapphire",   "SAP"),
    "corundum sapphire":            ("Sapphire",   "SAP"),
    "pink sapphire":                ("Sapphire",   "SAP"),
    "yellow sapphire":              ("Sapphire",   "SAP"),
    "padparadscha sapphire":        ("Sapphire",   "SAP"),  # confirm — may be own SKU
    "star sapphire":                ("Sapphire",   "SAP"),
    "emerald":                      ("Emerald",    "EME"),
    "beryl emerald":                ("Emerald",    "EME"),
    "garnet":                       ("Garnet",     "GAR"),
    "spessartite garnet":           ("Garnet",     "GAR"),
    "rhodolite garnet":             ("Garnet",     "GAR"),
    "tsavorite garnet":             ("Garnet",     "GAR"),  # confirm
    "almandine garnet":             ("Garnet",     "GAR"),
    "tourmaline":                   ("Tourmaline", "TOU"),
    "paraiba tourmaline":           ("Tourmaline", "TOU"),  # confirm — may be own SKU
    "rubellite":                    ("Tourmaline", "TOU"),
    "indicolite":                   ("Tourmaline", "TOU"),
    "topaz":                        ("Topaz",      "TPZ"),
    "spinel":                       ("Spinel",     "SPI"),
    "tanzanite":                    ("Tanzanite",  "TAN"),
    "aquamarine":                   ("Aquamarine", "AQM"),
    "peridot":                      ("Peridot",    "PER"),
    "alexandrite":                  ("Alexandrite","ALX"),
    "chrysoberyl":                  ("Chrysoberyl","CBL"),
    "zircon":                       ("Zircon",     "ZIR"),
    "citrine":                      ("Citrine",    "CIT"),
    "amethyst":                     ("Amethyst",   "AMY"),
    "morganite":                    ("Morganite",  "MRG"),
    "quartz":                       ("Quartz",     "QTZ"),
    "iolite":                       ("Iolite",     "IOL"),
    "kyanite":                      ("Kyanite",    "KYN"),
    "opal":                         ("Opal",       "OPL"),
    "turquoise":                    ("Turquoise",  "TRQ"),
    "lapis lazuli":                 ("Lapis",      "LAP"),
    "jade":                         ("Jade",       "JAD"),
    "pearl":                        ("Pearl",      "PRL"),
}


def lookup_stone_type(variety: str, species: Optional[str] = None) -> GlossaryHit:
    """Match AGL variety (+ species fallback) to ERP ST and Item# prefix."""
    for candidate in (variety, species):
        if not candidate:
            continue
        key = _norm(candidate)
        # exact match
        if key in STONE_TYPE_MAP:
            st, prefix = STONE_TYPE_MAP[key]
            return GlossaryHit(ok=True, value=st, raw=variety or species or "",
                               prefix=prefix)
        # substring match — catches "Natural Corundum Sapphire", etc.
        for k, (st, prefix) in STONE_TYPE_MAP.items():
            if k in key:
                return GlossaryHit(ok=True, value=st, raw=variety or species or "",
                                   prefix=prefix)
    return GlossaryHit(ok=False, value=variety or "", raw=variety or "", prefix=None)


# ===========================================================================
# SHAPE — AGL shape → ERP `Shape` 3-letter code + 2-digit Item# code
# ===========================================================================
# Sourced from BULK PI's shape code table. OCT→EME override is deliberate
# (gemstones treat octagonal as emerald shape per BULK PI convention).

SHAPE_MAP: dict[str, tuple[str, str]] = {
    # key               → (ERP 3-letter, 2-digit)
    "round":              ("RND", "10"),
    "princess":           ("PRN", "11"),
    "pear":               ("PSH", "12"),
    "pear shape":         ("PSH", "12"),
    "marquise":           ("MQS", "13"),
    "oval":               ("OVL", "14"),
    "emerald":            ("EME", "15"),
    "asscher":            ("ASC", "16"),
    "cushion":            ("CUS", "17"),
    "square cushion":     ("SCU", "18"),
    "radiant":            ("RAD", "19"),
    "square radiant":     ("SRT", "20"),
    "heart":              ("HRT", "21"),
    "baguette":           ("BAG", "22"),
    "taper baguette":     ("TAP", "23"),
    "trilliant":          ("TRN", "24"),
    "trillion":           ("TRN", "24"),
    "triangle":           ("TRG", "25"),
    "carre":              ("CAR", "30"),
    "rose cut":           ("RSC", "31"),
    "rosecut":            ("RSC", "31"),
    "cabochon":           ("CBN", "84"),
    "octagonal":          ("EME", "15"),  # BULK PI override — OCT treated as EME
    "octagon":            ("EME", "15"),
    "hexagonal":          ("HEX", "46"),
    "pentagonal":         ("PNT", "41"),
    "half moon":          ("HMN", "34"),
    "shield":             ("SHC", "35"),
    "kite":               ("KTE", "36"),
    "lozenge":            ("LOZ", "38"),
    "briolette":          ("BRI", "63"),
    "bullet":             ("BLT", "64"),
    "fancy":              ("FCUT","98"),
    "mix":                ("MIX", "99"),
}


def lookup_shape(shape_word: str) -> GlossaryHit:
    key = _norm(shape_word)
    if key in SHAPE_MAP:
        three, two = SHAPE_MAP[key]
        return GlossaryHit(ok=True, value=three, raw=shape_word,
                           shape_2digit=two)
    # first-word fallback — "Oval Mixed" / "Round Brilliant"
    first = key.split(" ", 1)[0]
    if first in SHAPE_MAP:
        three, two = SHAPE_MAP[first]
        return GlossaryHit(ok=True, value=three, raw=shape_word,
                           shape_2digit=two)
    return GlossaryHit(ok=False, value=shape_word or "", raw=shape_word or "",
                       shape_2digit=None)


# ===========================================================================
# COLOUR — AGL colour phrase → ERP 3-letter code
# ===========================================================================
# BULK PI's COL_COLORS map: BLU RED PPL YLO PNK GRN WHT BLK ORG BRN.
# Premium descriptive grades (Pigeon Blood, Cornflower, Royal Blue) collapse
# to their base family by default — if Sonesh wants them preserved separately,
# add them here.

COLOUR_MAP: dict[str, str] = {
    "blue": "BLU",
    "cornflower blue": "BLU",
    "cornflower": "BLU",
    "royal blue": "BLU",
    "vivid blue": "BLU",
    "intense blue": "BLU",
    "greenish blue": "BLU",
    "violetish blue": "BLU",
    "red": "RED",
    "pigeon blood red": "RED",
    "pigeon blood": "RED",
    "vivid red": "RED",
    "pinkish red": "RED",
    "purplish red": "RED",
    "pink": "PNK",
    "pinkish": "PNK",
    "purplish pink": "PNK",
    "orangish pink": "PNK",
    "yellow": "YLO",
    "yellowish": "YLO",
    "vivid yellow": "YLO",
    "greenish yellow": "YLO",
    "orangish yellow": "YLO",
    "green": "GRN",
    "vivid green": "GRN",
    "bluish green": "GRN",
    "yellowish green": "GRN",
    "purple": "PPL",
    "violet": "PPL",
    "violetish": "PPL",
    "white": "WHT",
    "colourless": "WHT",
    "colorless": "WHT",
    "near colourless": "WHT",
    "near colorless": "WHT",
    "black": "BLK",
    "orange": "ORG",
    "orangish": "ORG",
    "brown": "BRN",
    "brownish": "BRN",
    "champagne": "BRN",
}


def lookup_colour(colour_phrase: str) -> GlossaryHit:
    if not colour_phrase:
        return GlossaryHit(ok=False, value="", raw="")
    key = _norm(colour_phrase)
    if key in COLOUR_MAP:
        return GlossaryHit(ok=True, value=COLOUR_MAP[key], raw=colour_phrase)
    # longest-suffix match — strip modifiers one word at a time from the left
    words = key.split()
    for i in range(len(words)):
        tail = " ".join(words[i:])
        if tail in COLOUR_MAP:
            return GlossaryHit(ok=True, value=COLOUR_MAP[tail], raw=colour_phrase)
    # single-word base match — last word
    if words and words[-1] in COLOUR_MAP:
        return GlossaryHit(ok=True, value=COLOUR_MAP[words[-1]], raw=colour_phrase)
    return GlossaryHit(ok=False, value=colour_phrase, raw=colour_phrase)


# ===========================================================================
# TREATMENT — AGL treatment phrase → short code
# ===========================================================================
# Lands in Remarks until Sonesh confirms a dedicated column exists.

TREATMENT_MAP: dict[str, str] = {
    "no indication of heating": "NH",
    "no indication of treatment": "NH",
    "no heat": "NH",
    "unheated": "NH",
    "heated": "H",
    "heat": "H",
    "oil": "MO",
    "insignificant": "MO",
    "insignificant oil": "MO",
    "minor oil": "MO",
    "moderate oil": "MoO",
    "significant oil": "SO",
    "fracture filled": "FF",
    "glass filled": "GF",
    "diffusion": "DF",
    "irradiated": "IR",
}


def lookup_treatment(phrase: str) -> GlossaryHit:
    if not phrase:
        return GlossaryHit(ok=False, value="", raw="")
    key = _norm(phrase)
    if key in TREATMENT_MAP:
        return GlossaryHit(ok=True, value=TREATMENT_MAP[key], raw=phrase)
    for k, v in TREATMENT_MAP.items():
        if k in key:
            return GlossaryHit(ok=True, value=v, raw=phrase)
    return GlossaryHit(ok=False, value=phrase, raw=phrase)


# ===========================================================================
# ORIGIN — AGL origin → canonical short form
# ===========================================================================

ORIGIN_MAP: dict[str, str] = {
    "burma": "Burma",
    "burma (myanmar)": "Burma",
    "myanmar": "Burma",
    "myanmar (burma)": "Burma",
    "sri lanka": "Ceylon",
    "ceylon": "Ceylon",
    "sri lanka (ceylon)": "Ceylon",
    "ceylon (sri lanka)": "Ceylon",
    "madagascar": "Madagascar",
    "mozambique": "Mozambique",
    "thailand": "Thailand",
    "cambodia": "Cambodia",
    "tanzania": "Tanzania",
    "kenya": "Kenya",
    "vietnam": "Vietnam",
    "colombia": "Colombia",
    "zambia": "Zambia",
    "ethiopia": "Ethiopia",
    "afghanistan": "Afghanistan",
    "pakistan": "Pakistan",
    "brazil": "Brazil",
    "russia": "Russia",
    "australia": "Australia",
    "nigeria": "Nigeria",
}


def lookup_origin(phrase: str) -> GlossaryHit:
    if not phrase:
        return GlossaryHit(ok=False, value="", raw="")
    key = _norm(phrase)
    if key in ORIGIN_MAP:
        return GlossaryHit(ok=True, value=ORIGIN_MAP[key], raw=phrase)
    for k, v in ORIGIN_MAP.items():
        if k in key:
            return GlossaryHit(ok=True, value=v, raw=phrase)
    return GlossaryHit(ok=False, value=phrase, raw=phrase)
