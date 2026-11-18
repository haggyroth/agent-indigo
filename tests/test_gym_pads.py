"""Teleport-pad search for Saffron Gym (no emulator)."""
from knowledge.gym_pads import SABRINA_PADS, plan


def test_pads_are_symmetric_pairs():
    assert len(SABRINA_PADS) == 30
    for a, b in SABRINA_PADS.items():
        assert b in SABRINA_PADS            # the partner is a pad too


def test_a_pad_is_a_teleport_not_a_wall():
    # a 1-row strip: start . P1 . . | partner far away | goal next to P2
    pads = {(2, 0): (8, 0), (8, 0): (2, 0)}
    floor = lambda x, y: y == 0 and 0 <= x <= 9 and (x, y) not in pads and not (3 <= x <= 7)       # a wall between the two halves
    out = plan((0, 0), (9, 0), floor, pads)
    assert out == [("goto", (1, 0)), ("pad", (2, 0)), ("goto", (9, 0))]


def test_no_route_without_a_usable_pad():
    floor = lambda x, y: y == 0 and x in (0, 1, 8, 9)
    assert plan((0, 0), (9, 0), floor, {}) is None
    assert plan((0, 0), (1, 0), floor, {}) == [("goto", (1, 0))] or plan((0, 0), (1, 0), floor, {}) == []


def test_already_there_needs_nothing():
    assert plan((3, 3), (3, 3), lambda x, y: True, {}) == []
