"""Escape Rope / Dig / Teleport rules (pure) — from the decomp's allow_escaping and map types."""
from knowledge.escape import DIG_ID, ROPE_ID, TELEPORT_ID, can_escape, can_teleport, hint, why_not

PALLET = (3, 0)


def _by_name(name):
    from knowledge.navigation import MAP_NAMES
    return next(k for k, v in MAP_NAMES.items() if v == name)


def test_caves_allow_escaping_towns_do_not():
    assert can_escape(_by_name("Mt. Moon 1F")) and can_escape(_by_name("Viridian Forest"))
    assert not can_escape(PALLET) and not can_escape(_by_name("Route 1"))


def test_teleport_is_outdoors_only():
    assert can_teleport(PALLET) and can_teleport(_by_name("Route 1"))
    assert not can_teleport(_by_name("Mt. Moon 1F"))


def test_refusal_text_names_the_rule():
    assert "cave" in why_not("Dig", PALLET) and why_not("Escape Rope", _by_name("Mt. Moon 1F")) == ""
    assert "outdoors" in why_not("Teleport", _by_name("Mt. Moon 1F"))


def test_hint_only_when_something_applies():
    cave = _by_name("Mt. Moon 1F")
    assert "Dig" in hint(cave, {DIG_ID}, 0) and "Escape Rope" in hint(cave, set(), 2)
    assert hint(cave, set(), 0) == "" and hint(PALLET, {DIG_ID}, 3) == ""
    assert "Teleport" in hint(PALLET, {TELEPORT_ID}, 0) and hint(cave, {TELEPORT_ID}, 0) == ""
    assert ROPE_ID == 85
