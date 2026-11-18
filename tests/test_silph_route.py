"""knowledge.silph_route: the Silph Co. planner over the generated decomp data."""
from knowledge import silph_route as r
from knowledge.silph_data import FLOORS, WARPS

ENTRY = (r.SILPH_1F, (8, 19))
_DIR = {"Left": (-1, 0), "Right": (1, 0), "Up": (0, -1), "Down": (0, 1)}


def walk(goal, has_key, start=ENTRY, opened=frozenset()):
    """Execute the plan's first action at a time (as the driver does) until it arrives. Returns the list of key actions taken."""
    fl, pos = start
    opened = set(opened)
    taken = []
    for _ in range(80):
        p = r.plan(fl, pos, frozenset(opened), r.reach(goal), has_key)
        assert p is not None, (fl, pos, taken)
        if not p:
            return taken
        a = p[-1]
        if a[0] == "warp":
            d = WARPS[(a[1], a[2][0], a[2][1])]
            fl, pos = d[0], (d[1], d[2])
        elif a[0] == "unlock":
            dx, dy = _DIR[a[3]]
            door = r.shut_door(a[1], a[2][0] + dx, a[2][1] + dy, opened)
            assert door is not None
            opened.add(door)
        else:
            pos = a[2]
        taken.append(a)
    raise AssertionError("never arrived")


def test_card_key_is_reachable_without_opening_a_door():
    taken = walk({r.SILPH_5F: {t for t, _f in r.beside(r.CARD_KEY_BALL)}}, has_key=False)
    assert taken and all(a[0] != "unlock" for a in taken)
    assert sum(a[0] == "warp" for a in taken) == 4                         # 1F → 2F → 3F → 4F → 5F by the stairs


def test_without_the_key_giovanni_is_out_of_reach():
    assert r.plan(*ENTRY, frozenset(), r.reach({r.SILPH_11F: {(6, 15)}}), has_key=False) is None


def test_giovanni_and_the_president_and_the_lapras_are_all_reachable_with_the_key():
    for goal in ({r.SILPH_11F: {(5, 15), (6, 15)}},
                 {r.SILPH_11F: {t for t, _f in r.beside(r.PRESIDENT)}},
                 {r.SILPH_7F: {t for t, _f in r.beside(r.LAPRAS_WORKER)}}):
        assert walk(goal, has_key=True)


def test_every_planned_door_unlock_faces_a_shut_door_tile():
    taken = walk({r.SILPH_11F: {(5, 15), (6, 15)}}, has_key=True)
    unlocks = [a for a in taken if a[0] == "unlock"]
    assert unlocks and all(a[3] in _DIR for a in unlocks)


def test_the_lift_doorway_is_never_walked_on():
    for fl, f in FLOORS.items():
        for t in f["elevator"]:
            assert r.is_blocked(fl, *t)


def test_open_doors_are_plain_floor():
    d = FLOORS[r.SILPH_7F]["doors"][0]
    flag, tiles = d
    assert r.shut_door(r.SILPH_7F, *tiles[0], frozenset()) == flag
    assert r.shut_door(r.SILPH_7F, *tiles[0], frozenset({flag})) is None
