"""Seafoam Islands: the decomp data (tools/gen_seafoam.py) and the B3F push planner (no emulator)."""
from knowledge import seafoam_data as sd
from knowledge import seafoam_route as sr
from knowledge.boulder_puzzle import Floor, _region


def test_the_generated_data_matches_the_decomp_facts():
    assert sd.B3F_HOLES == [(6, 18), (9, 18)] and sorted(sd.B3F_BOULDERS) == [(6, 17), (9, 16), (12, 16), (13, 16)]
    assert sd.ARTICUNO_TILE == (9, 2) and sd.B4F_STAIRS == (15, 9) and sd.STOPPED_FLAG_B4F == 0x2D3
    assert sd.B4F_REVEAL_FLAGS == [0x4C, 0x4D] and set(sd.B3F_BOULDER_FLAGS.values()) == {0x48, 0x49, 0x4A, 0x4B}


def test_the_boulder_room_is_reachable_from_the_ladders_that_lead_to_it():
    f = sr.floor()
    assert isinstance(f, Floor)
    for start in ((8, 14), sr.B3F_ARRIVAL):
        assert (6, 16) in _region(f, start, frozenset(sd.B3F_BOULDERS), frozenset())


def _play(pos, boulders):
    """Execute next_push to the end with one-tile pushes; returns how many boulders went down a hole."""
    from knowledge.boulder_puzzle import _DIRS
    boulders, fallen = set(boulders), 0
    f = sr.floor()
    for _ in range(40):
        act = sr.next_push(pos, boulders)
        if act is None or fallen >= 2:
            break
        _k, stand, d = act
        dx, dy = _DIRS[d]
        bt = (stand[0] + dx, stand[1] + dy)
        assert bt in boulders, (act, boulders)
        nt = (bt[0] + dx, bt[1] + dy)
        boulders.discard(bt)
        if nt in f.holes:
            fallen += 1
        else:
            boulders.add(nt)
        pos = bt
    return fallen


def test_the_planner_drops_two_boulders_through_the_holes_one_push_at_a_time():
    assert _play(sr.B3F_ARRIVAL, sd.B3F_BOULDERS) == 2


def test_a_boulder_already_fallen_leaves_a_plan_for_the_second():
    assert _play((6, 17), [(9, 16), (12, 16), (13, 16)]) >= 1
    assert sr.dropped(lambda f: True) == 0 and sr.dropped(lambda f: False) == 2
    assert sr.initial_boulders(lambda f: f == 0x48) == [(12, 16), (13, 16), (9, 16)]
