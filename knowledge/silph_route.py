"""Silph Co. routing (pure): 11 floors joined by stairs and teleport pads, with card-key doors, solved as a search over (floor, tile).

knowledge.silph_data (generated from the decomp by tools/gen_silph.py) has every floor's collision grid with the doors OPEN, the doors themselves
(flag + the barrier tiles that close when the flag is clear), and the warps that fire (stairs, arrows, the teleport pads). `plan` returns the key
actions to reach a goal tile: goto / unlock / warp. The caller executes ONE action, re-reads the real state (which doors are open, who is in the
way) and plans again, so a trainer or a dropped input only costs a re-plan — the same shape as knowledge.mansion_route."""
from collections import deque

from knowledge.silph_data import FLOORS, WARPS

SILPH_1F, SILPH_5F, SILPH_7F, SILPH_11F = (1, 47), (1, 51), (1, 53), (1, 57)
CARD_KEY_BALL = (22, 21)             # 5F: an item ball (solid) — stand beside it
GIOVANNI_TRIGGER = (6, 15)           # 11F: stepping on (5,15) or (6,15) starts the Giovanni scene
PRESIDENT = (9, 9)                   # 11F: talk from the tile south of him
LAPRAS_WORKER = (0, 7)               # 7F: talk from the tile east of him
_N4 = ((0, -1), (0, 1), (-1, 0), (1, 0))
_FACE = {(0, -1): "Up", (0, 1): "Down", (-1, 0): "Left", (1, 0): "Right"}      # the button that faces (dx, dy) from a neighbouring tile


def _door_tiles(floor):
    """{(x, y): flag} of the barrier tiles that close each of this floor's doors while the flag is clear."""
    out = {}
    for flag, tiles in FLOORS[floor]["doors"]:
        for t in tiles:
            out[t] = flag
    return out


def is_blocked(floor, x, y) -> bool:
    """A wall or the lift doorway (a shut door is NOT blocked here: the plan unlocks it on the way)."""
    f = FLOORS[floor]
    rows = f["rows"]
    if not (0 <= y < len(rows) and 0 <= x < len(rows[0])):
        return True
    if (x, y) in f["elevator"]:
        return True
    return rows[y][x] == "#"


def shut_door(floor, x, y, open_flags):
    """The flag of the closed door that tile belongs to, or None."""
    flag = _door_tiles(floor).get((x, y))
    return flag if flag is not None and flag not in open_flags else None


def beside(target):
    """The four tiles around `target` with the button that faces it from each."""
    return [((target[0] - dx, target[1] - dy), _FACE[(dx, dy)]) for dx, dy in _N4]


def plan(floor, pos, open_flags=frozenset(), goal=None, has_key: bool = True, limit: int = 120000):
    """Key actions from (floor, pos) to a state where `goal(floor, x, y)` holds, or None.
    Actions: ("goto", floor, (x, y)) · ("unlock", floor, stand (x, y), face button) · ("warp", floor, warp tile, button to press on it or None).
    A shut door costs an unlock action and needs the Card Key (`has_key`); the plan goes through it as soon as it is opened."""
    if floor not in FLOORS or goal is None:
        return None
    start = (floor, pos[0], pos[1])
    prev = {start: None}
    queue = deque([start])
    end = None
    while queue and len(prev) < limit:
        node = queue.popleft()
        fl, x, y = node
        if goal(fl, x, y):
            end = node
            break
        for dx, dy in _N4:
            nx, ny = x + dx, y + dy
            if (fl, nx, ny) in WARPS:                                     # stepping onto a warp tile changes floor
                dest = WARPS[(fl, nx, ny)]
                if dest is None:
                    continue
                nxt = (dest[0], dest[1], dest[2])
                if nxt not in prev:
                    prev[nxt] = (node, ("warp", fl, (nx, ny), dest[3]))
                    queue.append(nxt)
                continue
            if is_blocked(fl, nx, ny):
                continue
            nxt = (fl, nx, ny)
            if nxt in prev:
                continue
            door = shut_door(fl, nx, ny, open_flags)
            if door is not None and shut_door(fl, x, y, open_flags) != door:       # entering a shut door from outside it
                if not has_key:
                    continue
                prev[nxt] = (node, ("unlock", fl, (x, y), _FACE[(dx, dy)]))
            else:
                prev[nxt] = (node, ("step", fl, (nx, ny)))
            queue.append(nxt)
    if end is None:
        return None
    steps = []
    node = end
    while prev[node] is not None:
        node, act = prev[node][0], prev[node][1]
        steps.append((node, act))
    steps.reverse()
    for before, act in steps:                    # only the FIRST key action: everything after it is on a floor / door state we re-read
        if act[0] != "step":
            stand = (before[1], before[2])
            return ([("goto", before[0], stand)] if stand != tuple(pos) else []) + [act]
    return [("goto", steps[-1][1][1], steps[-1][1][2])] if steps else []


def reach(tiles):
    """goal(): any (floor, (x, y)) in `tiles` — {floor: {(x, y), ...}}."""
    return lambda fl, x, y: (x, y) in tiles.get(fl, ())
