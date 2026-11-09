from gemstone_intake.extract import Dimensions
from gemstone_intake.item_code import (
    build_gemstone_item_code, default_measurement_code,
)


def test_round_largest_dim_times_ten():
    # 5.5 mm round → "55"
    code = default_measurement_code("10", 0.78, Dimensions(5.5, 5.5, 3.4))
    assert code == "55"


def test_round_weight_fallback_when_no_dims():
    # 0.78 ct → 078
    code = default_measurement_code("10", 0.78, Dimensions())
    assert code == "078"


def test_non_round_lwww_encoding():
    code = default_measurement_code("14", None, Dimensions(6.52, 4.48, 3.21))
    # L=65, W=44
    assert code == "6544"


def test_build_item_code_full():
    code = build_gemstone_item_code(
        stone_prefix="RUB", shape_2digit="10", colour_3letter="RED",
        weight_ct=0.78, dims=Dimensions(5.5, 5.5, 3.4),
    )
    assert code == "RUB10RED55"


def test_build_item_code_placeholder_on_missing():
    code = build_gemstone_item_code(
        stone_prefix="", shape_2digit="", colour_3letter="",
        weight_ct=None, dims=Dimensions(),
    )
    assert code.startswith("???")
