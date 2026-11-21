"""Where to grind (pure): wild levels that fit AND close to a Pokémon Center / the next objective — a watched run trained on Route 13, ~190 tiles from the nearest Center, and healed at Lavender every time."""
from knowledge.distance import pokecenter_tiles, route_tiles, tiles_between
from knowledge.grind_routes import best_grass, site_cost
from knowledge.map_graph import route_to

FUCHSIA_PC, LAVENDER_PC, SAFFRON = (11, 5), (8, 0), (3, 10)
ROUTE_12, ROUTE_13, ROUTE_15, ROUTE_14 = (3, 30), (3, 31), (3, 33), (3, 32)


def test_tiles_count_the_length_of_the_maps_crossed_not_the_hops():
    assert route_tiles([]) == 0
    # Route 12 is a 120-tile pier: one hop through it costs far more than Route 15's 72 east-west tiles
    assert route_tiles(route_to((3, 4), ROUTE_13), (3, 4)) > route_tiles(route_to((3, 33), (3, 32)), (3, 33)) * 0.8
    assert tiles_between(LAVENDER_PC, ROUTE_13) > tiles_between(LAVENDER_PC, ROUTE_12)


def test_route_13_is_far_from_any_pokemon_center_and_route_15_is_near_fuchsia():
    assert pokecenter_tiles(ROUTE_13) > 150
    assert pokecenter_tiles(ROUTE_15) < 100 and pokecenter_tiles(ROUTE_12) < 100


def test_the_watched_case_trains_near_a_center_not_in_the_route_13_maze():
    for start in (FUCHSIA_PC, LAVENDER_PC, ROUTE_13):
        site, _steps = best_grass(start, 24, objective=SAFFRON)
        assert site != ROUTE_13 and site != ROUTE_14, (start, site)


def test_a_far_better_fit_still_beats_a_nearby_misfit():
    assert site_cost(ROUTE_15, 24, 80, 84) < site_cost((3, 25), 24, 40, 49)       # Route 7 (L17-22) is 6 levels too cold for a L24 even next to a Center


def test_the_objective_pulls_the_choice_along_the_way():
    near_obj, _ = best_grass(LAVENDER_PC, 24, objective=SAFFRON)
    assert near_obj in ((3, 30), (3, 26), (3, 25), (3, 16), (3, 33)), near_obj        # a route on the Lavender / Saffron side, not the far Fuchsia end


def test_no_level_still_means_the_nearest_grass():
    assert best_grass(FUCHSIA_PC, 0) is not None
