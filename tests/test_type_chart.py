"""Gen III type effectiveness."""
from knowledge.battle import effectiveness_vs
from knowledge.type_chart import get_effectiveness


def test_super_effective_and_resist():
    assert get_effectiveness("WAT", "FIR") == 2.0
    assert get_effectiveness("FIR", "WAT") == 0.5


def test_default_is_neutral():
    assert get_effectiveness("NOR", "NOR") == 1.0
    assert get_effectiveness("WAT", "PSY") == 1.0


def test_key_immunities():
    assert get_effectiveness("ELE", "GRD") == 0    # Ground grounds Electric
    assert get_effectiveness("NOR", "GHO") == 0    # Ghost immune to Normal
    assert get_effectiveness("FIG", "GHO") == 0
    assert get_effectiveness("PSY", "DRK") == 0    # Dark immune to Psychic
    assert get_effectiveness("POI", "STL") == 0    # Steel immune to Poison


def test_dual_type_multiplier_stacks():
    # Water vs Ground/Rock (e.g. Onix): 2 * 2 = 4x
    assert effectiveness_vs("WAT", ("GRD", "ROC")) == 4.0
