from gemstone_intake.extract import (
    AGLReport, Dimensions, extract_from_html,
    parse_weight, parse_dimensions, split_shape_and_cut, parse_iso_date,
)


# --- parse_weight -------------------------------------------------------

def test_weight_plain_ct():
    assert parse_weight("0.78 ct") == 0.78

def test_weight_with_period_and_cts():
    assert parse_weight("12.34 cts.") == 12.34

def test_weight_carat_word():
    assert parse_weight("5 carat") == 5.0

def test_weight_none_when_missing():
    assert parse_weight("no number here") is None


# --- parse_dimensions ----------------------------------------------------

def test_dimensions_standard():
    d = parse_dimensions("6.52 x 4.48 x 3.21 mm")
    assert d.length_mm == 6.52 and d.width_mm == 4.48 and d.height_mm == 3.21

def test_dimensions_unicode_times():
    d = parse_dimensions("6.52 × 4.48 × 3.21 mm")
    assert (d.length_mm, d.width_mm, d.height_mm) == (6.52, 4.48, 3.21)

def test_dimensions_no_match_preserves_raw():
    d = parse_dimensions("approx 6mm round")
    assert d.length_mm is None and d.raw == "approx 6mm round"


# --- split_shape_and_cut -------------------------------------------------

def test_shape_cut_two_words():
    assert split_shape_and_cut("Oval Mixed") == ("Oval", "Mixed")

def test_shape_cut_three_words():
    assert split_shape_and_cut("Round Brilliant Cut") == ("Round", "Brilliant Cut")

def test_shape_only():
    assert split_shape_and_cut("Cushion") == ("Cushion", None)


# --- parse_iso_date ------------------------------------------------------

def test_date_iso_passthrough():
    assert parse_iso_date("2026-04-18") == "2026-04-18"

def test_date_dmy_slash():
    assert parse_iso_date("18/04/2026") == "2026-04-18"

def test_date_dmy_dash():
    assert parse_iso_date("18-04-2026") == "2026-04-18"

def test_date_long_form():
    assert parse_iso_date("18 April 2026") == "2026-04-18"


# --- end-to-end against synthetic HTML -----------------------------------

def test_label_value_in_flow_text():
    html = """
    <html><body>
      <p>Report No: 0063138</p>
      <p>Date of Issue: 18 April 2026</p>
      <p>Species: Natural Corundum</p>
      <p>Variety: Sapphire</p>
      <p>Weight: 0.78 ct</p>
      <p>Shape and Cut: Oval Mixed</p>
      <p>Colour: Cornflower Blue</p>
      <p>Measurements: 6.52 x 4.48 x 3.21 mm</p>
      <p>Indication of Heating: No Indication of Heating</p>
      <p>Origin: Sri Lanka (Ceylon)</p>
    </body></html>
    """
    r = extract_from_html(html)
    assert r.report_number == "0063138"
    assert r.date_of_issue == "2026-04-18"
    assert r.variety == "Sapphire"
    assert r.weight_ct == 0.78
    assert r.shape == "Oval" and r.cut == "Mixed"
    assert r.colour == "Cornflower Blue"
    assert r.dimensions.length_mm == 6.52
    assert r.treatment == "No Indication of Heating"
    assert r.origin == "Sri Lanka (Ceylon)"
    assert r.extraction_status == "ok"
    assert r.missing_fields == []


def test_table_form_html():
    """AGL Thai typically uses a two-column table — exercise that path."""
    html = """
    <table>
      <tr><td>Report No.</td><td>AGL-0063138</td></tr>
      <tr><td>Variety</td><td>Ruby</td></tr>
      <tr><td>Weight</td><td>1.50 ct</td></tr>
      <tr><td>Shape &amp; Cut</td><td>Cushion Mixed</td></tr>
      <tr><td>Color</td><td>Pigeon Blood Red</td></tr>
      <tr><td>Measurements</td><td>7.10 x 6.50 x 4.20 mm</td></tr>
      <tr><td>Indication of Heating</td><td>No Indication of Heating</td></tr>
      <tr><td>Origin</td><td>Burma (Myanmar)</td></tr>
    </table>
    """
    r = extract_from_html(html)
    assert r.report_number == "AGL-0063138"
    assert r.variety == "Ruby"
    assert r.weight_ct == 1.5
    assert r.shape == "Cushion"
    assert r.colour == "Pigeon Blood Red"
    assert r.origin == "Burma (Myanmar)"
    assert r.extraction_status == "ok"


def test_empty_html_fails_cleanly():
    r = extract_from_html("")
    assert r.extraction_status == "failed"


def test_report_roundtrip_dict():
    r = AGLReport(report_number="X", variety="Ruby", weight_ct=1.0,
                  dimensions=Dimensions(6, 4, 3, "6 x 4 x 3"))
    r2 = AGLReport.from_dict(r.to_dict())
    assert r2.report_number == "X"
    assert r2.dimensions.length_mm == 6
