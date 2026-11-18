"""Pokémon Mansion routing from the decomp data: one global statue switch, four floors (no emulator)."""
from knowledge import mansion_route as mr
from knowledge.mansion_data import FLOORS


def test_every_floor_has_a_grid_a_statue_and_press_overrides():
    assert set(FLOORS) == {(1, 59), (1, 60), (1, 61), (1, 62)}
    for key, f in FLOORS.items():
        assert f["rows"] and f["statues"], key
        assert all(0 <= y < len(f["rows"]) and 0 <= x < len(f["rows"][0]) for (x, y) in f["press"]), key
    assert FLOORS[(1, 62)]["statues"] == [(24, 29), (27, 5)] and FLOORS[(1, 59)]["statues"] == [(5, 5)]


def test_the_switch_really_changes_the_barriers():
    changed = [(k, t) for k, f in FLOORS.items() for t, blocked in f["press"].items() if blocked != (f["rows"][t[1]][t[0]] == "#")]
    assert changed, "pressing a statue must open or close some tiles"
    for k, (x, y) in changed[:5]:
        assert mr.is_blocked(k, x, y, 0) != mr.is_blocked(k, x, y, 1)


def test_the_secret_key_is_reachable_from_the_entrance_and_needs_the_switch():
    # arrive on 1F at the south door, switch clear
    plan = mr.plan((1, 59), (8, 32), 0)
    assert plan, "a route to the Secret Key's side exists"
    kinds = [a[0] for a in plan]
    assert "warp" in kinds                                              # at least the stairs down
    assert plan[-1][0] == "goto" and plan[-1][1] == (1, 62)
    gx, gy = plan[-1][2]
    assert abs(gx - 5) + abs(gy - 7) == 1                                # it ends BESIDE the item ball at (5,7)
    # the first action is always something the caller can execute from where it stands
    assert plan[0][0] in ("goto", "press", "warp")


def test_already_beside_the_key_needs_no_actions_and_unknown_floors_are_none():
    assert mr.plan((1, 62), (5, 8), 0) == []
    assert mr.plan((3, 8), (14, 12), 0) is None


def test_planning_from_the_other_switch_state_also_works():
    assert mr.plan((1, 59), (8, 32), 1)
    assert mr.plan((1, 61), (8, 3), 1)


def test_statues_are_pressed_from_the_south_facing_up():
    assert mr.statue_neighbours((1, 60), 2, 17) == (2, 16) and mr.statue_neighbours((1, 60), 3, 16) is None
    plan = mr.plan((1, 59), (8, 32), 0)
    presses = [a for a in plan if a[0] == "press"]
    assert presses and all(a[3] == "Up" for a in presses)
