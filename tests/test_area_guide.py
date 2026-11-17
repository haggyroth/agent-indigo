"""Area guidance (#240): every dungeon / puzzle gym / late-game stretch has text, grounded in the decomp's facts (pure)."""
import re

from knowledge.area_facts import AREA_FACTS, MAP_IDS
from knowledge.area_guide import AREAS, area_for, facts_line, guide_for
from knowledge.map_graph import MAP_KIND
from knowledge.navigation import MAP_NAMES


def test_every_named_map_exists_in_the_decomp_and_belongs_to_one_area():
    seen = {}
    for a in AREAS:
        for m in a.maps:
            assert m in MAP_IDS, (a.key, m)
            assert MAP_IDS[m] not in seen, f"{m} is in both {seen[MAP_IDS[m]]} and {a.key}"
            seen[MAP_IDS[m]] = a.key
    assert len({a.key for a in AREAS}) == len(AREAS)


def test_the_areas_issue_240_asks_for_are_all_covered():
    keys = {a.key for a in AREAS}
    assert {"mt_moon", "rock_tunnel", "diglett_cave", "power_plant", "pokemon_mansion", "seafoam", "victory_road", "cerulean_cave", "safari",
            "rocket_hideout", "silph_co", "pokemon_tower", "ss_anne", "sabrina_gym", "koga_gym", "blaine_gym", "giovanni_gym", "kanto_east",
            "cycling_road", "saffron_access", "sea_route", "league_approach", "elite_four"} <= keys


def test_every_dungeon_the_game_names_has_a_guide_on_every_floor():
    for name in ("Mt. Moon", "Victory Road", "Rocket Hideout", "Silph Co.", "Pokemon Tower", "Seafoam"):
        floors = [k for k, v in MAP_NAMES.items() if v.startswith(name)]
        assert floors, name
        assert all(area_for(k) for k in floors), (name, [MAP_NAMES[k] for k in floors if not area_for(k)])
    assert all(area_for(MAP_IDS[g]) for g in ("SaffronCity_Gym", "FuchsiaCity_Gym", "CinnabarIsland_Gym", "ViridianCity_Gym"))
    assert MAP_KIND.get(MAP_IDS["SaffronCity_Gym"]) == "gym"


def test_facts_come_from_the_decomp():
    assert "Card Key (22,21)" in facts_line(MAP_IDS["SilphCo_5F"])
    assert "Secret Key" in facts_line(MAP_IDS["PokemonMansion_B1F"])
    assert "warp pads" in facts_line(MAP_IDS["SaffronCity_Gym"]) and "(18,20)→(28,23)" in facts_line(MAP_IDS["SaffronCity_Gym"])
    assert re.search(r"TM\d\d \w", facts_line(MAP_IDS["VictoryRoad_2F"]))


def test_the_text_is_short_enough_for_an_observation_and_names_the_goal():
    for a in AREAS:
        for m in a.maps:
            t = guide_for(MAP_IDS[m])
            assert t.startswith(f"AREA — {a.title}:") and len(t) < 1500, (m, len(t))


def test_unrelated_maps_get_no_area_text():
    assert guide_for(MAP_IDS["PalletTown"]) == "" and guide_for((3, 0)) == ""
    assert sum(1 for f in AREA_FACTS.values() if f[2]) > 100


def test_the_observation_shows_the_guide_on_arrival_then_only_as_a_reminder():
    import pytest
    pytest.importorskip("openai")
    from types import SimpleNamespace as NS

    from agent.observation import _area
    from game.state import GameContext
    run = NS(area_shown=None, step_count=1)
    here = MAP_IDS["VictoryRoad_1F"]
    t = NS(in_battle=False, overworld=True, here=here, run=run)
    assert _area(t)[0].startswith("AREA — Victory Road")                 # arrival
    run.step_count = 2
    assert _area(t) == []                                                # same map, not a reminder tick
    run.step_count = 25
    assert len(_area(t)) == 1                                            # the 25-tick reminder
    t.here = MAP_IDS["PalletTown"]
    assert _area(t) == [] and run.area_shown is None                     # leaving forgets it, so coming back shows it again
    assert GameContext.OVERWORLD is not None
    t.in_battle = True
    assert _area(t) == []
