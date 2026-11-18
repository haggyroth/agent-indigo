"""Teleport-pad gyms (pure): Saffron Gym's 30 pads, and the search that uses them.

Every pad is a warp event whose destination is ANOTHER pad of the same map (decomp SaffronCity_Gym/map.json: `dest_warp_id` indexes the same
list). Stepping onto a pad teleports you to its partner and lands you ON that partner (which does not re-trigger until you step off and on
again). Sabrina stands at (14,11); the entrance room is the bottom strip. `plan` finds the pads to take: BFS over tiles where a step onto a
pad tile is a teleport edge (pads are never walked across by accident)."""
from collections import deque

# pad tile -> its partner tile (SaffronCity_Gym warps 3..32; warps 0..2 are the exit to Saffron City)
SABRINA_PADS: dict = {
    (18, 20): (28, 23), (0, 4): (20, 7), (0, 7): (18, 15), (0, 12): (28, 15), (0, 15): (8, 7), (0, 20): (28, 7), (0, 23): (16, 7),
    (8, 4): (16, 4), (8, 7): (0, 15), (8, 12): (12, 7), (8, 15): (8, 23), (8, 20): (20, 23), (8, 23): (8, 15), (12, 4): (20, 15),
    (12, 7): (8, 12), (16, 4): (8, 4), (16, 7): (0, 23), (18, 15): (0, 7), (20, 4): (20, 12), (20, 7): (0, 4), (20, 12): (20, 4),
    (20, 15): (12, 4), (20, 20): (28, 4), (20, 23): (8, 20), (28, 4): (20, 20), (28, 7): (0, 20), (28, 12): (28, 20), (28, 15): (0, 12),
    (28, 20): (28, 12), (28, 23): (18, 20),
}
_N4 = ((0, -1), (0, 1), (-1, 0), (1, 0))


def plan(start, goal, passable, pads: dict, limit: int = 20000):
    """Actions from `start` to `goal`: [("goto", stand tile), ("pad", pad tile), …, ("goto", goal)] (a goto is a walk that touches no pad), or None.
    `passable(x, y)` = plain floor (pads are decided by `pads`, not by it)."""
    prev = {start: None}
    queue = deque([start])
    while queue and len(prev) < limit:
        cur = queue.popleft()
        if cur == goal:
            break
        for dx, dy in _N4:
            n = (cur[0] + dx, cur[1] + dy)
            if n in pads:
                dest = pads[n]
                if dest not in prev:
                    prev[dest] = (cur, ("pad", n))
                    queue.append(dest)
                continue
            if n in prev or not passable(*n):
                continue
            prev[n] = (cur, ("step", n))
            queue.append(n)
    if goal not in prev:
        return None
    seq, node = [], goal
    while prev[node] is not None:
        before, act = prev[node]
        seq.append((before, act))
        node = before
    seq.reverse()
    out, walk_end = [], None                 # walk_end = the tile the plain steps since the last pad lead to
    for before, act in seq:
        if act[0] == "step":
            walk_end = act[1]
            continue
        if walk_end is not None:             # walk to the tile beside the pad first
            out.append(("goto", before))
            walk_end = None
        out.append(act)
    if walk_end is not None:
        out.append(("goto", walk_end))
    return out
