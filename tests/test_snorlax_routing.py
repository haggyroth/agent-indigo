"""Fuchsia is reached by land over Route 12's Snorlax — the planner used to see its square as a wall, plan a 24-step sea trip via Pallet and blame Surf (watched runs 163742 / 172153)."""
import pytest

from knowledge.gates import BICYCLE, POKE_FLUTE, unmet_gates
from knowledge.map_graph import node_for, route_to

LAVENDER, FUCHSIA, ROUTE_12 = (3, 4), (3, 7), (3, 30)
SAFFRON = node_for(3, 10, 8, 27)
ROUTE_16 = node_for(3, 34, 41, 7)


def kinds(route):
    return [s[0] for s in route]


@pytest.mark.parametrize("start", [LAVENDER, SAFFRON, ROUTE_16])
def test_the_land_route_over_the_snorlax_beats_the_sea_trip(start):
    route = route_to(start, FUCHSIA)
    assert route and not any(tuple(s[2][:2]) in {(3, 39), (3, 40), (3, 37), (3, 38)} for s in route), route     # no Route 19-21 water
    assert len(route) <= 20


def test_from_lavender_the_route_goes_through_the_gatehouse_and_over_the_snorlax():
    route = route_to(LAVENDER, FUCHSIA)
    assert "snorlax" in kinds(route) and "surf" not in kinds(route) and len(route) <= 10


def _ok(have_flute=True, woke=False, bike=False):
    def ok(req):
        if req.alt_flag == 0x253 and woke:
            return True
        if req.kind == "flag":
            return woke
        if req.kind == "key_item":
            return (req.value == POKE_FLUTE and have_flute) or (req.value == BICYCLE and bike)
        return True
    return ok


def test_a_sleeping_snorlax_is_the_gate_and_its_hint_says_to_wake_it():
    route = route_to(LAVENDER, FUCHSIA)
    unmet = unmet_gates(route, _ok(woke=False))
    assert unmet and "quest('snorlax')" in unmet[0][1].hint
    assert not unmet_gates(route, _ok(woke=True))


def test_the_cycling_road_needs_the_bicycle():
    route = route_to(ROUTE_16, FUCHSIA)
    via17 = [(i, r) for i, r in unmet_gates([("connection", "South", (3, 35))], _ok(bike=False))]
    assert via17 and "Bicycle" in via17[0][1].hint
    assert not unmet_gates([("connection", "South", (3, 35))], _ok(bike=True))
    assert route


def test_the_gate_loop_from_route_16_ends_on_route_12_not_on_a_surf_message():
    pytest.importorskip("openai")
    from agent.lm_studio_client import AgentClient
    c = AgentClient.__new__(AgentClient)
    c._gate_ok = _ok(woke=True)                       # Snorlax awake, flute in the bag, no bike
    route = route_to(ROUTE_16, FUCHSIA)
    out, why = c._respect_gates(ROUTE_16, FUCHSIA, route, set())
    assert why is None and "snorlax" in kinds(out) and not any(tuple(s[2][:2]) == (3, 35) for s in out), (out, why)
    c._gate_ok = _ok(woke=False)                      # still asleep: the hint names the Snorlax
    out, why = c._respect_gates(ROUTE_16, FUCHSIA, route_to(ROUTE_16, FUCHSIA), set())
    assert why and "Snorlax" in why and "Surf" not in why, why
