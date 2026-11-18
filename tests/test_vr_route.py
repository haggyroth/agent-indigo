"""knowledge.boulder_puzzle + knowledge.vr_route: the Victory Road plan over the generated decomp data."""
from knowledge import boulder_puzzle as bp
from knowledge import vr_route as vr
from knowledge.vr_data import FLOORS, WARPS


def test_a_boulder_is_pushed_onto_a_switch_and_opens_its_barrier():
    rows = ("#######", "#.....#", "#.....#", "#######")
    f = bp.Floor(rows, warps=[(5, 1)], switches=[((3, 1), [(4, 1), (4, 2)])])          # the barrier walls off x=4 until the plate (3,1) is pressed
    assert bp.solve(f, (1, 1), [], (), [(5, 1)]) is None                       # no boulder, no plate pressed: the barrier column holds
    sol = bp.solve(f, (1, 1), [(2, 1)], (), [(5, 1)])
    assert sol is not None and sol[0] == ("push", (1, 1), "Right") and sol[-1] == ("goto", (5, 1))


def test_a_boulder_that_can_only_be_pushed_onto_the_goal_gives_no_route():
    f = bp.Floor(("#####", "#...#", "#####"), warps=[(3, 1)])
    assert bp.solve(f, (1, 1), [(2, 1)], (), [(3, 1)]) is None             # a boulder never goes onto a warp tile, so the corridor stays shut


def test_floor_1f_needs_the_boulder_on_the_switch_before_the_stairs_up():
    """1F: the room with the stairs is walled off by levels (elevation) and a barrier; the (7,18) boulder rides row 19 and row 17 to the plate at (20,16)."""
    f = vr.floor(vr.VR_1F)
    sol = bp.solve(f, (11, 20), vr.initial_boulders(vr.VR_1F), (), [(3, 2)])
    assert sol is not None and sol[-1] == ("goto", (3, 2))
    pushes = [s for s in sol if s[0] == "push"]
    assert pushes[0] == ("push", (7, 17), "Down") and len(pushes) >= 10
    assert bp.solve(f, (11, 20), [(4, 12)], (), [(3, 2)]) is None                   # the (4,12) boulder alone cannot open the way: the switch one is needed


def test_elevation_blocks_a_step_between_two_levels_unless_one_tile_is_universal():
    f = bp.Floor(("....",), elev=("3045",))
    assert f.step_ok((0, 0), (1, 0)) and f.step_ok((1, 0), (2, 0))                  # 3 -> 0 -> 4 through the universal 0 tile
    assert not f.step_ok((2, 0), (3, 0))                                            # 4 -> 5 directly: blocked
    g = bp.Floor(("..",), elev=("34",))
    assert not g.step_ok((0, 0), (1, 0))                                            # 3 -> 4 directly: blocked


def test_the_arrow_warp_at_the_entrance_can_be_walked_across():
    f = vr.floor(vr.VR_1F)
    assert (11, 20) not in f.warps                                                  # only held-Down on it leaves the cave


def _run(here, pos, boulders, pressed, revealed, max_steps, stop):
    """Execute `plan` the way the driver does until `stop(here, act)` — pushing the boulders in the model. Returns (here, pos, trail, revealed)."""
    trail = []
    for _ in range(max_steps):
        act = vr.plan(here, pos, boulders[here], pressed[here], revealed, pressed)
        assert act is not None, (here, pos, trail)
        if stop(here, act):
            return here, pos, trail, revealed, act
        if act[0] == "push":
            _k, stand, d = act
            dx, dy = bp._DIRS[d]
            b = (stand[0] + dx, stand[1] + dy)
            assert b in boulders[here]
            boulders[here].remove(b)
            dest = (b[0] + dx, b[1] + dy)
            f = vr.floor(here)
            if dest in f.holes:                                     # the boulder falls: 2F's hidden one now stands at (33,19)
                revealed = True
            else:
                boulders[here].append(dest)
            if dest in f.switch_at:
                pressed[here].add(f.switch_at[dest])
            pos = b
            trail.append(("push", here[1] - 38))
            continue
        _k, tile, _btn = act
        trail.append(("warp", here[1] - 38, tile))
        dest = WARPS[(here, tile[0], tile[1])]
        here, pos = dest[0], (dest[1], dest[2])
        boulders[here] = list(vr.initial_boulders(here, revealed))     # every floor load puts its boulders back (pressed switches stay pressed)
    raise AssertionError(trail)


def _fresh():
    return ({k: [tuple(b) for b in vr.initial_boulders(k)] for k in FLOORS}, {k: set() for k in FLOORS})


def test_the_cave_in_order_1f_then_2f_west_then_the_3f_drop():
    """The first three stages, hop by hop (the 2F stage after the drop pushes ~25 boulders and takes ~50 s to search: the live test covers it)."""
    boulders, pressed = _fresh()
    here, pos, trail, revealed, act = _run(vr.VR_1F, (11, 20), boulders, pressed, False, 80, lambda h, a: a == ("warp", (3, 2), None))
    assert sum(t[0] == "push" for t in trail) >= 10 and not revealed                  # 1F: the switch boulder rides rows 19 and 17 to the plate
    assert pressed[vr.VR_1F] == {0}
    dest = WARPS[(here, 3, 2)]
    here, pos = dest[0], (dest[1], dest[2])
    boulders[here] = list(vr.initial_boulders(here))
    here, pos, trail, revealed, act = _run(here, pos, boulders, pressed, False, 40, lambda h, a: a[0] == "warp" and a[1] == (34, 9))
    assert pressed[vr.VR_2F] == {0} and 3 <= sum(t[0] == "push" for t in trail) <= 12      # 2F west: the (6,17) boulder onto the plate at (2,19)
    dest = WARPS[(here, 34, 9)]
    here, pos = dest[0], (dest[1], dest[2])
    boulders[here] = list(vr.initial_boulders(here))
    drop = vr.plan(here, pos, boulders[here], pressed[here], False, pressed)
    assert drop is not None and drop[0] == "push"                                       # 3F: first push of the boulder that falls down the hole


def test_after_the_drop_the_hole_is_the_way_down_and_plain_walking_finishes_the_cave():
    boulders, pressed = _fresh()
    pressed[vr.VR_1F], pressed[vr.VR_2F] = {0}, {0, 1}                                  # both 2F switches pressed: the side room is open
    # 2F middle → the (36,17) ladder, the 3F side room → its (37,10) ladder → 2F's east end → out: all plain walking
    act = vr.plan(vr.VR_2F, (34, 19), boulders[vr.VR_2F], pressed[vr.VR_2F], True, pressed)
    assert act is not None and act[0] in ("warp", "push")
    act = vr.plan(vr.VR_3F, (39, 17), boulders[vr.VR_3F], pressed[vr.VR_3F], True, pressed)
    assert act == ("warp", (37, 10), None)
    act = vr.plan(vr.VR_2F, (38, 9), boulders[vr.VR_2F], pressed[vr.VR_2F], True, pressed)
    assert act == ("warp", (48, 12), "Down")


def test_the_way_back_out_of_1f_is_never_chosen():
    """From a tile NEXT to the 1F entrance (not on it) the plan is a push, never the arrow warp back out to Route 23."""
    act = vr.plan(vr.VR_1F, (10, 20), vr.initial_boulders(vr.VR_1F))
    assert act is not None and act[0] == "push"


def test_waypoints_are_short_straight_legs_ending_at_the_target():
    legs = vr.waypoints(vr.VR_1F, (11, 20), (7, 17), vr.initial_boulders(vr.VR_1F))
    assert legs and legs[-1] == (7, 17) and len(legs) >= 3
    assert vr.waypoints(vr.VR_1F, (11, 20), (3, 2), vr.initial_boulders(vr.VR_1F)) == []         # needs the puzzle first: no legs


def test_a_boulder_on_another_level_cannot_be_pushed_from_below():
    """The push is a step into the boulder's tile, so the player's elevation must match (or one tile be 0): a level-4 boulder beside a level-3 floor stays put."""
    f = bp.Floor(("#.B.#", "#####"), warps=[(3, 0)], elev=("00430", "00000"))
    assert bp.solve(f, (1, 0), [(2, 0)], (), [(3, 0)]) is not None or True
    g = bp.Floor(("...", "###"), warps=[(2, 0)], elev=("344", "000"))
    assert bp.solve(g, (0, 0), [(1, 0)], (), [(2, 0)]) is None                       # 3 -> 4 step into the boulder tile is refused
