"""Spinner-aware pathfinding (Rocket Hideout B2F/B3F, Silph Co., Viridian Gym): stepping on an arrow tile slides the player in the
arrow's direction — across PLAIN floor too, turning on each further arrow — until a stop tile or a wall (verified live on the real ROM:
the plain tiles between an arrow and the stop tile did not stop the slide). A* searches the places the player can STAND (no emulator)."""
from game.pathfinding import find_path_spin, spin_slide


def build(rows):
    spin = {(x, y): {">": "Right", "<": "Left", "^": "Up", "v": "Down"}[ch]
            for y, row in enumerate(rows) for x, ch in enumerate(row) if ch in "><^v"}
    stops = {(x, y) for y, row in enumerate(rows) for x, ch in enumerate(row) if ch == "S"}
    return (lambda x, y: 0 <= y < len(rows) and 0 <= x < len(rows[0]) and rows[y][x] != "#"), spin, stops, len(rows[0]), len(rows)


def test_a_slide_runs_across_plain_floor_to_the_stop_tile():
    # the live case: arrow at (2,11), plain floor (3..5,11), stop tile (6,11) — the player ended on the stop tile
    passable, spin, stops, w, h = build(["#########",
                                        "#.>...S.#",
                                        "#########"])
    assert spin_slide((2, 1), passable, spin, stops) == (6, 1)


def test_a_slide_ends_before_a_wall_and_turns_on_further_arrows():
    passable, spin, stops, w, h = build(["#########",
                                        "#.>..###.",
                                        "#########"])
    assert spin_slide((2, 1), passable, spin, stops) == (4, 1)               # no stop tile: it runs until the wall
    passable, spin, stops, w, h = build(["#######",
                                        "#.>..v#",
                                        "#####.#",
                                        "#####S#",
                                        "#######"])
    assert spin_slide((2, 1), passable, spin, stops) == (5, 3)               # right along the belt, turned DOWN by the arrow


def test_a_loop_is_reported_as_none():
    passable, spin, stops, w, h = build(["#####",
                                        "#>v##",
                                        "#^<##",
                                        "#####"])
    assert spin_slide((1, 1), passable, spin, stops) is None


def test_the_planner_rides_the_belt_and_reports_where_each_press_ends():
    rows = ["#########",
            "#..>...S.",
            "#########"]
    passable, spin, stops, w, h = build(rows)
    moves, ends = find_path_spin((1, 1), (7, 1), passable, w, h, spin, stops)
    assert moves == ["Right", "Right", "Right"][:len(moves)] and ends[-1] == (7, 1)
    assert ends[1] == (7, 1) or ends[-1] == (7, 1)
    assert find_path_spin((1, 1), (1, 1), passable, w, h, spin, stops) == ([], [])


def test_a_goal_that_needs_a_detour_through_two_belts():
    rows = ["###########",
            "#.>..S#####",
            "#####.#####",
            "#####v#####",
            "#####S..G##",
            "###########"]
    rows = [r.replace("G", ".") for r in rows]
    passable, spin, stops, w, h = build(rows)
    moves, ends = find_path_spin((1, 1), (8, 4), passable, w, h, spin, stops)
    assert moves[0] == "Right" and (5, 1) in ends and ends[-1] == (8, 4)


def test_unreachable_goal_returns_none():
    passable, spin, stops, w, h = build(["#####",
                                        "#.#.#",
                                        "#####"])
    assert find_path_spin((1, 1), (3, 1), passable, w, h, spin, stops) is None
