"""Pokémon Mansion routing (pure): the one global statue switch + four floors, solved as a search over (floor, tile, switch state).

knowledge.mansion_data (generated from the decomp) gives each floor's collision grid with the switch clear and the tiles the switch changes.
A statue press flips the switch for EVERY floor; stepping onto a warp tile changes floor. `plan` returns the key actions to reach the Secret
Key's side: goto / press / warp. The caller executes ONE action, re-reads the real state and plans again, so a trainer in the way or a dropped
input only costs a re-plan."""
from collections import deque

from knowledge.mansion_data import FLOORS, WARPS

B1F = (1, 62)
SECRET_KEY_BALL = (5, 7)             # an item ball: solid, so the goal is any open tile beside it
_N4 = ((0, -1), (0, 1), (-1, 0), (1, 0))
_FACE = {(0, -1): "Up", (0, 1): "Down", (-1, 0): "Left", (1, 0): "Right"}      # the button that faces (dx, dy) from a neighbouring tile


def is_blocked(floor, x, y, flag: int) -> bool:
    f = FLOORS[floor]
    rows = f["rows"]
    if not (0 <= y < len(rows) and 0 <= x < len(rows[0])):
        return True
    if flag and (x, y) in f["press"]:
        return bool(f["press"][(x, y)])
    return rows[y][x] == "#"


def statue_neighbours(floor, x, y):
    """The statue this tile can press, or None. The statues are `sign` events that need the player facing NORTH (decomp
    BG_EVENT_PLAYER_FACING_NORTH): you press from the tile directly SOUTH of the statue, facing up."""
    for sx, sy in FLOORS[floor]["statues"]:
        if (x, y) == (sx, sy + 1):
            return (sx, sy)
    return None


def _goal(floor, x, y) -> bool:
    return floor == B1F and abs(x - SECRET_KEY_BALL[0]) + abs(y - SECRET_KEY_BALL[1]) == 1


def plan(floor, pos, flag: int, goal=_goal, limit: int = 60000):
    """Key actions from (floor, pos, flag) to a state where `goal(floor, x, y)` holds, or None.
    Actions: ("goto", floor, (x, y)) · ("press", floor, stand (x, y), face button) · ("warp", floor, warp tile, button to press on it or None)."""
    if floor not in FLOORS:
        return None
    start = (floor, pos[0], pos[1], flag)
    prev = {start: None}
    queue = deque([start])
    end = None
    while queue and len(prev) < limit:
        node = queue.popleft()
        fl, x, y, sw = node
        if goal(fl, x, y):
            end = node
            break
        for dx, dy in _N4:
            nx, ny = x + dx, y + dy
            if (fl, nx, ny) in WARPS:                                    # stepping onto a warp tile changes floor
                dest = WARPS[(fl, nx, ny)]
                if dest is None:
                    continue
                nxt = (dest[0], dest[1], dest[2], sw)
                if nxt not in prev:
                    prev[nxt] = (node, ("warp", fl, (nx, ny), dest[3]))
                    queue.append(nxt)
                continue
            if is_blocked(fl, nx, ny, sw):
                continue
            nxt = (fl, nx, ny, sw)
            if nxt not in prev:
                prev[nxt] = (node, ("step", fl, (nx, ny)))
                queue.append(nxt)
        s = statue_neighbours(fl, x, y)
        if s is not None:                                                  # pressing the statue flips the global switch
            nxt = (fl, x, y, 1 - sw)
            if nxt not in prev:
                prev[nxt] = (node, ("press", fl, (x, y), _FACE[(s[0] - x, s[1] - y)]))
                queue.append(nxt)
    if end is None:
        return None
    steps = []
    node = end
    while prev[node] is not None:
        node, act = prev[node][0], prev[node][1]
        steps.append((node, act))
    steps.reverse()
    # compress: runs of plain steps become one goto to the last tile before a special action / the goal
    out, here = [], (floor, pos)
    for i, (before, act) in enumerate(steps):
        kind = act[0]
        if kind == "step":
            here = (act[1], act[2])
            continue
        stand = (before[1], before[2])
        if here[1] != stand or not out and stand != pos:
            out.append(("goto", before[0], stand))
        out.append(act)
        here = (before[0], stand)
    last = steps[-1][1] if steps else None
    if last and last[0] == "step":
        out.append(("goto", last[1], last[2]))
    return out
