"""Seafoam Islands (pure): the boulder pushes that stop B4F's current, from knowledge.seafoam_data (decomp, tools/gen_seafoam.py).

B3F's south-west room holds four boulders and two fall holes; any two boulders pushed through them stop the current on B4F (see seafoam_data / gen_seafoam).
`next_push` is the first push of the shortest plan from where the player stands; the live driver re-reads the boulders and plans again, like Victory Road."""
from knowledge import seafoam_data as sd
from knowledge.boulder_puzzle import Floor, solve

SEAFOAM_1F, SEAFOAM_B1F, SEAFOAM_B2F, SEAFOAM_B3F, SEAFOAM_B4F = (1, 83), (1, 84), (1, 85), (1, 86), (1, 87)
B3F_ARRIVAL = (12, 9)               # where B4F's ladder (15, 9) puts you
_FLOOR = None


def floor() -> Floor:
    global _FLOOR
    if _FLOOR is None:
        holes = frozenset(sd.B3F_HOLES)
        _FLOOR = Floor(sd.B3F_ROWS, (), [w for w in sd.B3F_WARPS if w not in holes], (), sd.B3F_ELEV, holes)
    return _FLOOR


def initial_boulders(read_flag) -> list:
    """The B3F boulders still standing: those whose hide flag is not set (a fallen boulder stays gone)."""
    return [t for t, flag in sd.B3F_BOULDER_FLAGS.items() if not read_flag(flag)]


def dropped(read_flag) -> int:
    """How many boulders have fallen to B4F (its reveal flags are cleared)."""
    return sum(1 for f in sd.B4F_REVEAL_FLAGS if not read_flag(f))


def next_push(pos, boulders):
    """("push", stand tile, direction) — the first push of the shortest plan that sends one more boulder through a hole — or None when there is no way."""
    plan = solve(floor(), tuple(pos), tuple(map(tuple, boulders)), drop=True, limit=600000)
    if not plan:
        return None
    return next((a for a in plan if a[0] == "push"), None)
