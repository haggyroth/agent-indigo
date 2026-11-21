"""Route 20's sea is two sealed halves (no emulator): the planner must not plan the direct Fuchsia -> Cinnabar crossing a watched run kept failing at."""
from knowledge.map_graph import node_for, region_at, route20_west, route_to

FUCHSIA, CINNABAR, ROUTE_19, ROUTE_20 = (3, 7), (3, 8), (3, 37), (3, 38)


def maps(route):
    return [tuple(s[2][:2]) for s in route]


def test_the_zones_follow_the_walls_the_game_enforces():
    assert region_at(ROUTE_20, 119, 5) == "E" and region_at(ROUTE_20, 90, 8) == "E"             # Route 19's side: the east sea
    assert region_at(ROUTE_20, 30, 10) == "W" and region_at(ROUTE_20, 50, 9) == "W" and region_at(ROUTE_20, 65, 16) == "W"   # Cinnabar's: the corridor
    assert region_at(ROUTE_20, 70, 5) == "0" and region_at(ROUTE_20, 72, 15) == "1"                # the island, the sandbar (land)
    assert route20_west(0, 0) and not route20_west(100, 15) and route20_west(79, 14) and not route20_west(80, 14)


def test_fuchsia_to_cinnabar_never_enters_route_20():
    route = route_to(node_for(3, 7, 25, 32), CINNABAR)
    assert route and ROUTE_20 not in maps(route), maps(route)
    assert (3, 39) in maps(route) and maps(route)[-1] == CINNABAR                              # round by Pallet and Route 21's sea instead


def test_standing_at_route_20s_east_end_the_way_on_is_back_east_not_west():
    route = route_to(node_for(3, 38, 119, 5), CINNABAR)
    assert route and maps(route)[0] == ROUTE_19 and ROUTE_20 not in maps(route)


def test_the_west_corridor_reaches_cinnabar_and_the_two_seas_do_not_meet():
    assert maps(route_to(node_for(3, 38, 30, 10), CINNABAR)) == [CINNABAR]
    east_to_corridor = route_to(node_for(3, 38, 119, 5), node_for(3, 38, 30, 10))
    assert east_to_corridor is None or all(tuple(s[2][:3]) != (3, 38, "W") for s in east_to_corridor[:1])


def test_route_19_to_cinnabar_is_the_long_way_too():
    route = route_to(ROUTE_19, CINNABAR)
    assert route and ROUTE_20 not in maps(route)
