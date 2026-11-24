"""Victory Road as a grind site (pure: knowledge only)."""
from knowledge.distance import PLATEAU_CENTER, pokecenter_tiles
from knowledge.grind_routes import best_grass
from knowledge.map_graph import CAVE_GRIND_MAPS, GRASS_MAPS, VICTORY_ROAD_MAPS, node_for

VR_1F, VR_2F = (1, 39), (1, 40)


def test_victory_road_floors_are_cave_grind_ground():
    assert VICTORY_ROAD_MAPS <= CAVE_GRIND_MAPS <= GRASS_MAPS


def test_a_team_at_route_23_or_the_plateau_trains_in_victory_road_not_in_cinnabars_mansion():
    """A watched run walked from Route 23 to Cinnabar's Mansion (309 tiles + a Surf) for a L45-52 team while the cave's wild L32-48 were next door."""
    for start in (node_for(3, 42, 5, 29), node_for(3, 42, 10, 72), (3, 9), (3, 1)):
        for level in (45, 52):
            assert best_grass(start, level)[0] == VR_1F, (start, level)


def test_the_cave_floors_behind_the_puzzles_are_only_a_site_from_inside_the_cave():
    assert best_grass(node_for(3, 42, 5, 29), 45)[0] == VR_1F
    assert best_grass(VR_2F, 45)[0] == VR_2F                    # already on 2F: train where you stand


def test_no_heal_trip_is_counted_to_the_plateaus_center():
    """From the cave's floors the Plateau's Center looked 63-104 tiles away (through the puzzles); the walk that is open is Viridian's."""
    assert PLATEAU_CENTER == (13, 0)
    assert pokecenter_tiles(VR_1F) > 110


def test_from_floor_one_the_floors_behind_the_puzzles_are_not_offered_and_a_flight_makes_a_far_site_cheaper():
    """A watched run's relocation tried 'go_to Victory Road 2F' from 1F twelve times — it ended 'blocked' every time (the warp graph cannot push the boulders)."""
    assert best_grass(VR_1F, 52, exclude_current=True)[0] != VR_2F
    far = (3, 10)                                                # Saffron: a few hundred tiles from the cave
    from knowledge.grind_routes import _with_fly
    walking = _with_fly(900.0, VR_1F, ())
    flying = _with_fly(900.0, VR_1F, [(3, 1)])                   # Fly can take the party to Viridian first
    assert walking == 900.0 and flying < 300
    assert _with_fly(None, VR_1F, [(3, 1)]) is not None and _with_fly(None, VR_1F, []) is None
    assert best_grass(far, 52, fly_towns=[(3, 1)])[0] in GRASS_MAPS
