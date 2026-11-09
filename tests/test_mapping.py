from gemstone_intake.extract import AGLReport, Dimensions
from gemstone_intake.mapping import agl_to_erp_row


def _ruby_report() -> AGLReport:
    return AGLReport(
        report_number="0063138",
        date_of_issue="2026-04-18",
        species="Natural Corundum",
        variety="Ruby",
        weight_ct=0.78,
        shape="Round",
        cut=None,
        colour="Red",
        dimensions=Dimensions(5.5, 5.5, 3.4, "5.5 x 5.5 x 3.4 mm"),
        treatment="No Indication of Heating",
        origin="Burma (Myanmar)",
        extraction_status="ok",
        missing_fields=[],
    )


def test_mapping_happy_path_ruby():
    mr = agl_to_erp_row(
        _ruby_report(), unit_price=300.0, fwd_loc="T", fwd_ssp="DDX",
    )
    assert mr.status == "ok"
    row = mr.row
    assert row["Report No"] == "0063138"
    # Per Sonesh (2026-11-09): ST is the 3-letter short code, not the long name.
    assert row["ST"] == "RUB"
    assert row["Shape"] == "RND"
    assert row["Color"] == "RED"
    assert row["Wt"] == 0.78
    assert row["L"] == 5.5 and row["W"] == 5.5 and row["D"] == 3.4
    assert row["Item #"] == "RUB10RED55"
    # Per-stone fields from intake
    assert row["FWD LOC"] == "T"
    assert row["FWD SSP"] == "DDX"
    # Constants
    assert row["Clarity"] == "EC0"
    assert row["SBK"] == "A"
    assert row["IT"] == "PP"
    assert row["Inv Effect"] == 1
    assert row["Lab"] == "AGL"
    # Per Sonesh (2026-11-09): treatment & origin NOT tracked at ERP intake.
    assert row["Remarks"] is None
    # But still available as side-column context
    assert mr.raw_values.get("treatment") == "No Indication of Heating"
    assert mr.raw_values.get("origin") == "Burma (Myanmar)"
    # Diamond-only fields stay empty
    for k in ("Cut", "D%", "Fluo", "Pol", "Sym", "T%"):
        assert row[k] is None


def test_mapping_partial_on_unknown_shape():
    report = _ruby_report()
    report.shape = "Totally Fake Shape"
    mr = agl_to_erp_row(report, unit_price=100.0, fwd_loc="T", fwd_ssp="DDX")
    assert mr.status == "partial"
    assert any("unmatched shape" in w for w in mr.warnings)
    assert mr.raw_values.get("shape") == "Totally Fake Shape"


def test_mapping_failed_passthrough_when_extraction_failed():
    report = _ruby_report()
    report.extraction_status = "failed"
    mr = agl_to_erp_row(report)
    assert mr.status == "failed"
    assert mr.row == {}


def test_mapping_partial_on_unknown_colour():
    report = _ruby_report()
    report.colour = "Argyle Pink Diamond Hue"
    mr = agl_to_erp_row(report, unit_price=1000.0, fwd_loc="T", fwd_ssp="DDX")
    assert mr.status == "partial"


def test_mapping_partial_when_fwd_fields_missing():
    """Per Sonesh: FWD LOC and FWD SSP are per-stone inputs. Missing => amber."""
    mr = agl_to_erp_row(_ruby_report(), unit_price=300.0)  # no fwd_loc / fwd_ssp
    assert mr.status == "partial"
    assert any("FWD" in w for w in mr.warnings)


def test_mapping_unmatched_treatment_does_not_flag():
    """Per Sonesh: treatment doesn't go to ERP, so a weird AGL phrase is fine."""
    report = _ruby_report()
    report.treatment = "Some unknown enhancement procedure"
    mr = agl_to_erp_row(report, unit_price=300.0, fwd_loc="T", fwd_ssp="DDX")
    assert mr.status == "ok"
    # Warnings should not include a treatment complaint
    assert not any("treatment" in w.lower() for w in mr.warnings)
