"""#293 — Cut trees as links in the region graph, the narrower Route 16 flute gate and Route 4's Magikarp house (no emulator)."""
from knowledge.gates import MAP_GATES, unmet_gates
from knowledge.map_graph import node_for, route_to
from knowledge.travel_rules import no_walk_reason


def test_the_route_16_fly_house_is_reached_through_the_tree_and_the_upper_gatehouse():
    east_end = node_for(3, 34, 47, 14)                                         # where Celadon's exit lands
    route = route_to(east_end, (25, 0))
    assert [s[0] for s in route] == ["cut", "warp", "warp", "warp"]            # tree → (27,6) gatehouse → (1,3) back out → (10,5) house
    assert route[0][1] == (41, 10) and route[-1][1] == (10, 5)                 # the cut step names the tile beyond the tree
    assert route[1][1] == (27, 6)                                              # the UPPER gatehouse, not the lower one the Snorlax guards


def test_a_route_without_a_cut_tree_is_unchanged_and_plain_maps_still_route():
    assert route_to((3, 3), (3, 2)) is not None
    assert all(s[0] in ("connection", "warp") for s in route_to((3, 0), (3, 3)))


def test_the_route_16_flute_gate_applies_to_the_road_south_not_to_the_fly_house():
    req = MAP_GATES[(3, 34)][0]
    assert req.only_exits == ("South",)
    no = lambda r: False                                                       # noqa: E731  (nothing satisfied)
    house = [("connection", "West", (3, 34, "4")), ("cut", (41, 10), (3, 34, "1")), ("warp", (27, 6), (25, 1, "0"))]
    assert unmet_gates(house, no) == []                                        # goes indoors from Route 16: not blocked by the Snorlax
    south = [("connection", "West", (3, 34, "4")), ("connection", "South", (3, 35))]
    assert [i for i, _r in unmet_gates(south, no)] == [0]                      # leaves outdoors toward Route 17: blocked
    assert unmet_gates([("connection", "West", (3, 34, "4"))], no) == []       # the route ENDS on Route 16: fine
    back = [("warp", (10, 5), (3, 34, "0")), ("warp", (20, 6), (25, 1, "0")), ("warp", (27, 6), (3, 34, "1")), ("cut", (41, 12), (3, 34, "4")), ("connection", "East", (3, 6))]
    assert unmet_gates(back, no) == []                                         # house → Celadon: leaves by the EAST edge, not toward Route 17


def test_route_4s_magikarp_house_cannot_be_walked_to_from_cerulean_but_can_from_the_pocket():
    assert "one way" in no_walk_reason((3, 22), (16, 0), (107, 10))            # the Cerulean end: say why instead of stalling
    assert no_walk_reason((3, 22), (16, 0), (12, 6)) is None                   # the Mt. Moon-side pocket: one hop
    assert "one way" in no_walk_reason((3, 3), (16, 0))
