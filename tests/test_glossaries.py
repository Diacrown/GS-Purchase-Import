from gemstone_intake.glossaries import (
    lookup_stone_type, lookup_shape, lookup_colour,
    lookup_treatment, lookup_origin,
)


# --- stone type ----------------------------------------------------------

def test_stone_type_exact_ruby():
    h = lookup_stone_type("Ruby")
    assert h.ok and h.value == "Ruby" and h.prefix == "RUB"

def test_stone_type_substring_corundum_sapphire():
    h = lookup_stone_type("Natural Corundum Sapphire")
    assert h.ok and h.value == "Sapphire" and h.prefix == "SAP"

def test_stone_type_species_fallback():
    h = lookup_stone_type(variety="Padparadscha", species="Corundum Sapphire")
    assert h.ok and h.prefix == "SAP"

def test_stone_type_unknown():
    h = lookup_stone_type("Moonstone Variety XYZ")
    assert not h.ok
    assert h.prefix is None


# --- shape ---------------------------------------------------------------

def test_shape_round():
    h = lookup_shape("Round")
    assert h.ok and h.value == "RND" and h.shape_2digit == "10"

def test_shape_oval_first_word_fallback():
    h = lookup_shape("Oval Mixed")
    assert h.ok and h.value == "OVL" and h.shape_2digit == "14"

def test_shape_octagonal_override_to_emerald():
    h = lookup_shape("Octagonal")
    assert h.ok and h.value == "EME" and h.shape_2digit == "15"

def test_shape_unknown():
    h = lookup_shape("Something Weird")
    assert not h.ok


# --- colour --------------------------------------------------------------

def test_colour_plain_blue():
    h = lookup_colour("Blue")
    assert h.ok and h.value == "BLU"

def test_colour_cornflower_blue_collapses_to_BLU():
    h = lookup_colour("Cornflower Blue")
    assert h.ok and h.value == "BLU"

def test_colour_pigeon_blood_red_collapses_to_RED():
    h = lookup_colour("Pigeon Blood Red")
    assert h.ok and h.value == "RED"

def test_colour_last_word_fallback():
    h = lookup_colour("slightly greenish Blue")
    # Not a known exact phrase; should fall back to BLU (last word)
    assert h.ok and h.value == "BLU"


# --- treatment -----------------------------------------------------------

def test_treatment_nh():
    h = lookup_treatment("No Indication of Heating")
    assert h.ok and h.value == "NH"

def test_treatment_heated_substring():
    h = lookup_treatment("Heated with residue")
    assert h.ok and h.value == "H"


# --- origin --------------------------------------------------------------

def test_origin_ceylon():
    h = lookup_origin("Sri Lanka (Ceylon)")
    assert h.ok and h.value == "Ceylon"

def test_origin_burma_from_myanmar():
    h = lookup_origin("Myanmar")
    assert h.ok and h.value == "Burma"
