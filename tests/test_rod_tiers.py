"""Fishing spots name the rod they need (generated from the decomp's ten fishing slots: 0-1 Old, 2-4 Good, 5-9 Super)."""
from knowledge.dex_plan import dex_line, sources, wild_spot
from knowledge.team import where_to_find
from knowledge.wild_locations import WILD_LOCATIONS

MAGIKARP, GYARADOS, GOLDEEN, POLIWAG = 129, 130, 118, 60


def methods(sid):
    return {m for _b, _i, m, _lo, _hi in WILD_LOCATIONS[sid]}


def test_no_row_is_just_fish_any_more():
    assert not any(m == "fish" for rows in WILD_LOCATIONS.values() for _b, _i, m, _lo, _hi in rows)
    assert {"old rod", "good rod", "super rod"} <= {m for rows in WILD_LOCATIONS.values() for _b, _i, m, _lo, _hi in rows}


def test_magikarp_bites_on_the_old_rod_and_gyarados_needs_the_super_rod():
    assert "old rod" in methods(MAGIKARP)
    assert methods(GYARADOS) == {"super rod"}                                  # slots 5-9 only


def test_where_to_find_says_which_rod():
    assert "super rod" in where_to_find(GYARADOS)


def test_the_dex_plan_points_at_the_quest_that_gets_the_rod():
    assert any(q == "super_rod" for _p, _t, q in sources(GYARADOS, set())), sources(GYARADOS, set())
    assert any(q == "old_rod" for _p, _t, q in sources(MAGIKARP, set()))
    assert "(super rod" in wild_spot(GYARADOS)


def test_grass_and_surf_rows_are_untouched():
    assert "grass" in methods(16) and "fish" not in dex_line(set())
