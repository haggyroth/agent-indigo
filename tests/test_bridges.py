"""Bridge decks (Safari Zone East / North…): walkable only through ramps, never straight from floor (pure)."""
from game.pathfinding import find_path
from game.tilemap_reader import bridge_tiles, deck_step_ok

F, D, R, W = 0x3000, 0x4000, 0x0000, 0x0400           # floor, deck, ramp (elevation 0), wall (collision bit)


def layout(rows):
    h, w = len(rows), len(rows[0])
    sym = {".": F, "B": D, "r": R, "#": W}
    return (lambda x, y: sym[rows[y][x]]), w, h


def test_a_deck_with_a_ramp_to_floor_is_walkable_and_its_ramp_too():
    entry, w, h = layout(["....#",
                          ".rBB#",
                          "....#"])
    decks, ramps = bridge_tiles(entry, w, h)
    assert decks == {(2, 1), (3, 1)} and ramps == {(1, 1)}


def test_a_deck_without_a_ramp_to_floor_stays_a_wall():
    entry, w, h = layout(["....",
                          "BBBB",
                          "...."])
    assert bridge_tiles(entry, w, h) == (set(), set())          # raised platform, no ramp: not a shortcut


def test_a_plain_elevation_zero_wall_is_not_a_ramp():
    entry, w, h = layout(["..r..",
                          "..#.."])                              # a lone elevation-0 tile touches no deck
    assert bridge_tiles(entry, w, h) == (set(), set())


def test_paths_use_the_ramp_and_never_step_from_floor_straight_onto_the_deck():
    rows = ["..........",
            ".rBBBBBBB.",
            ".........."]
    entry, w, h = layout(rows)
    decks, ramps = bridge_tiles(entry, w, h)
    walk = decks | ramps | {(x, y) for y in range(h) for x in range(w) if rows[y][x] == "."}
    ok = deck_step_ok(decks, ramps)
    # onto the far end of the deck from the floor above it: the only legal way is up the ramp and along
    path = find_path((8, 0), (8, 1), lambda x, y: (x, y) in walk, w, h, edge_ok=ok)
    assert path is not None and path != ["Down"] and path[:2] == ["Left", "Left"] and "Right" in path    # round by the ramp
    # the step floor→deck is vetoed, the step floor→ramp and ramp→deck are not
    assert not ok((8, 0), (8, 1)) and ok((1, 0), (1, 1)) and ok((1, 1), (2, 1))
    # without the veto, the straight step would be taken (this is the bug it prevents)
    assert find_path((8, 0), (8, 1), lambda x, y: (x, y) in walk, w, h) == ["Down"]
    assert find_path((8, 0), (8, 1), lambda x, y: (x, y) in walk, w, h, edge_ok=ok) != ["Down"]
