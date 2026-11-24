"""go_to flies when that beats walking (no emulator) — from a watched run that had Fly and walked the whole way from the Plateau to Route 15 and back."""
from types import SimpleNamespace as NS

import pytest

from knowledge.flight import FLY_TILES, MIN_SAVING, best_flight

PALLET, VIRIDIAN, PEWTER, CERULEAN, VERMILION, FUCHSIA, PLATEAU = (3, 0), (3, 1), (3, 2), (3, 3), (3, 5), (3, 7), (3, 9)


def test_a_far_destination_picks_the_visited_town_nearest_it():
    town, saved = best_flight(900, FUCHSIA, [PALLET, VIRIDIAN, PEWTER, FUCHSIA])
    assert town == FUCHSIA and saved == pytest.approx(900 - FLY_TILES)


def test_a_short_walk_is_not_worth_the_menus():
    assert best_flight(FLY_TILES + MIN_SAVING - 1, PEWTER, [VIRIDIAN, PEWTER]) is None
    assert best_flight(FLY_TILES + MIN_SAVING + 1, PEWTER, [VIRIDIAN, PEWTER]) is not None


def test_no_walking_route_means_any_flight_wins_and_the_current_town_is_no_flight():
    town, saved = best_flight(None, CERULEAN, [PEWTER, CERULEAN])
    assert town == CERULEAN and saved == float("inf")
    assert best_flight(None, CERULEAN, [CERULEAN], here=CERULEAN) is None


def test_walking_out_of_a_building_first_counts_against_the_flight():
    near = best_flight(400, FUCHSIA, [FUCHSIA], leave=0)[1]
    far = best_flight(400, FUCHSIA, [FUCHSIA], leave=40)[1]
    assert near - far == pytest.approx(40)


pytest.importorskip("openai")
from game.state import GameContext   # noqa: E402


def _client(here=PLATEAU, pos=(10, 10), badges=0b111111, knows_fly=True, visited=(PALLET, VIRIDIAN, FUCHSIA, PLATEAU), ctx=GameContext.OVERWORLD):
    from agent.lm_studio_client import AgentClient
    from agent.skills.hm import FLY_SPOTS
    c = AgentClient.__new__(AgentClient)
    flags = {spot[2] for key, spot in FLY_SPOTS.items() if spot[0] in visited}
    state = {"map": here, "calls": []}
    c.reader = NS(detect_context=lambda: ctx, read_badges=lambda: (6, badges), read_flag=lambda n: n in flags,
                  read_party=lambda: [NS(move_names=["Fly"] if knows_fly else ["Tackle"], species_id=18, species_name="Pidgeot")],
                  read_current_map=lambda: state["map"], read_player_pos=lambda: pos)

    def fly(town):
        state["calls"].append(town)
        state["map"] = FLY_SPOTS[town][0]
        return f"Flew to {town.title()}."
    c._fly_to = fly
    return c, state


def test_it_flies_from_the_street_when_the_destination_is_far():
    c, st = _client(here=(3, 41), pos=(12, 12))                # Route 22 → Fuchsia City on foot is a few hundred tiles
    note = c._fly_ahead("Fuchsia City")
    assert st["calls"] == ["fuchsia city"] and "Flew to Fuchsia City" in note and "tiles of walking" in note


def test_it_walks_without_a_fly_user_the_badge_or_a_visited_town():
    for kwargs in ({"knows_fly": False}, {"badges": 0b11}, {"visited": ()}, {"ctx": GameContext.IN_BATTLE}):
        c, st = _client(here=(3, 41), pos=(12, 12), **kwargs)
        assert c._fly_ahead("Fuchsia City") == "" and st["calls"] == [], kwargs


def test_it_walks_when_already_there_or_when_the_flight_fails_and_never_retries_from_there():
    c, st = _client(here=FUCHSIA, pos=(5, 5))
    assert c._fly_ahead("Fuchsia City") == "" and st["calls"] == []
    c, st = _client(here=(3, 41), pos=(12, 12))
    c._fly_to = lambda town: st["calls"].append(town) or "Fly couldn't be used here (indoors / not allowed) — go outside first."
    assert c._fly_ahead("Fuchsia City") == "" and c._fly_ahead("Fuchsia City") == "" and len(st["calls"]) == 1


def test_the_travel_wrapper_appends_the_flight_note_and_survives_a_broken_planner():
    c, st = _client(here=(3, 41), pos=(12, 12))
    c._go_to_inner = lambda *a, **k: "Arrived at Fuchsia City."
    out = c._go_to("Fuchsia City")
    assert out.startswith("Arrived at Fuchsia City.") and "Flew to Fuchsia City" in out
    c._fly_ahead_inner = lambda d: 1 / 0
    assert c._go_to("Fuchsia City") == "Arrived at Fuchsia City."
