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


def _ok(have_flute=True, woke=False, bike=False, woke16=None):
    woke16 = woke if woke16 is None else woke16

    def ok(req):
        flags = {0x253: woke, 0x080: woke16}
        if req.alt_flag in flags and flags[req.alt_flag]:
            return True
        if req.kind == "flag":
            return flags.get(req.value, False)
        if req.kind == "key_item":
            return (req.value == POKE_FLUTE and have_flute) or (req.value == BICYCLE and bike)
        if req.kind == "hm":
            return req.value == "Cut"                      # the Cut tree on Route 16 is fine; the sea (Surf) is not
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
    c._gate_ok = _ok(woke=True, woke16=False)         # Route 16's Snorlax still asleep, Route 12's awake, no bike: the answer is the Route 12 road, never a Surf message
    out, why = c._respect_gates(ROUTE_16, FUCHSIA, route_to(ROUTE_16, FUCHSIA), set())
    assert why is None and not any(tuple(s[2][:2]) in {(3, 35), (3, 39), (3, 40)} for s in out), (out, why)
    assert [s for s in out if s[0] == "snorlax"], out


NODE_CELADON = node_for(3, 6, 48, 12)


def test_celadon_to_fuchsia_is_the_cycling_road_through_route_16s_snorlax_and_the_gate_house():
    route = route_to(NODE_CELADON, FUCHSIA)
    assert len(route) <= 10 and "snorlax" in kinds(route), route
    assert [tuple(s[2][:2]) for s in route if s[0] == "connection"][:3] == [(3, 34), (3, 35), (3, 36)], route        # Route 16 -> 17 -> 18
    ok = _ok(woke=True, bike=True)
    assert not unmet_gates(route, lambda req: ok(req) or req.alt_flag == 0x080)                                          # Snorlax gone + Bicycle: nothing in the way
    asleep = unmet_gates(route, lambda req: ok(req) and req.alt_flag != 0x080)
    assert asleep and "quest('snorlax_16')" in asleep[0][1].hint, asleep
    nobike = unmet_gates(route, _ok(woke=True, bike=False))
    assert any("Bicycle" in r.hint for _i, r in nobike)


def test_the_cycling_road_is_one_way_so_fuchsia_to_celadon_goes_round_it():
    route = route_to(node_for(3, 7, 25, 32), (3, 6))
    assert route and not any(tuple(s[2][:2]) in {(3, 35), (3, 36)} for s in route), route
