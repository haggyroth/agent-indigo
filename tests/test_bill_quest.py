"""Bill's SS-ticket quest plumbing + the routing fixes found while building it (#185 item 5b)."""
from types import SimpleNamespace

import pytest

from knowledge import map_graph
from knowledge.gates import MAP_GATES, unmet_gates
from knowledge.navigation import MAP_NAMES


def test_route_names_match_the_decomp():
    # FRLG splits Route 21; every id after it is one higher than the route number.
    assert MAP_NAMES[(3, 43)] == "Route 24" and MAP_NAMES[(3, 44)] == "Route 25"
    assert MAP_NAMES[(3, 41)] == "Route 22" and MAP_NAMES[(3, 42)] == "Route 23"
    assert MAP_NAMES[(30, 0)] == "Bill's Sea Cottage"


def test_route_23_badge_gate_is_on_route_23_not_22():
    assert (3, 42) in MAP_GATES and (3, 41) not in MAP_GATES


def test_cerulean_exits_are_gated_on_the_ss_ticket():
    route = [("connection", "South", (3, 23))]
    unmet = unmet_gates(route, lambda req: False)
    assert unmet and "quest('ss_ticket')" in unmet[0][1].hint
    assert unmet_gates(route, lambda req: True) == []


def test_routing_never_crosses_saffrons_walled_shell_map():
    route = map_graph.route_to((3, 3), (3, 5))             # Cerulean → Vermilion
    assert route and all(tuple(step[2][:2]) != (3, 11) for step in route)


def test_get_ss_ticket_is_idempotent_when_you_already_have_it():
    pytest.importorskip("openai")
    from agent.lm_studio_client import AgentClient
    c = AgentClient.__new__(AgentClient)
    c.reader = SimpleNamespace(read_key_items=lambda: [265], read_flag=lambda n: False)
    assert c._has_ss_ticket()
    assert "already have" in c._get_ss_ticket()


def test_vermilion_gym_is_gated_on_cut():
    route = [("warp", (13, 28), (9, 6))]
    unmet = unmet_gates(route, lambda req: False)
    assert unmet and "Cut" in unmet[0][1].hint and "S.S. Anne" in unmet[0][1].hint


def test_victory_road_is_gated_on_fly_until_the_plateau_has_been_visited():
    """Victory Road 1F needs Strength AND Fly (the way home from the Plateau); a visit to the Plateau (FLAG_VISITED_INDIGO_PLATEAU) lifts the Fly gate."""
    route = [("warp", (1, 1), (1, 39, "0"))]
    reqs = MAP_GATES[(1, 39)]
    assert [r.value for r in reqs] == ["Strength", "Fly"]
    fly = reqs[1]
    assert fly.alt_flag == 0x899 and "quest('fly')" in fly.hint
    assert [r.value for _i, r in unmet_gates(route, lambda req: req.value != "Fly")] == ["Fly"]
    assert unmet_gates(route, lambda req: True) == []
