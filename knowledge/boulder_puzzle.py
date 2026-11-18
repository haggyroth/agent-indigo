"""Strength-boulder puzzles (pure): a push-based search over one cave floor.

A floor is a collision grid plus pushable boulders, floor switches (a boulder pushed onto the plate opens its barrier tiles for good) and solid
objects. `solve` finds the pushes that let the player reach a goal tile. The state is (boulder set, pressed switches, the region the player can
walk) — the search only branches on pushes, so a floor with 3-4 boulders is small. knowledge.vr_route turns it into the FIRST action the live driver should
execute (it re-reads the boulders and plans again, like the Mansion / Silph planners)."""
from collections import deque

_DIRS = {"Up": (0, -1), "Down": (0, 1), "Left": (-1, 0), "Right": (1, 0)}


class Floor:
    """Immutable view of one floor: walls, solid objects, warp tiles, switches [(tile, barrier tiles)]."""

    def __init__(self, rows, solid=(), warps=(), switches=(), elev=None, holes=()):
        self.rows = rows
        self.elev = elev
        self.h, self.w = len(rows), len(rows[0])
        self.solid = frozenset(solid)
        self.warps = frozenset(warps)
        self.holes = frozenset(holes)                 # fall warps: a boulder pushed onto one vanishes
        self.switches = tuple((tuple(t), tuple(map(tuple, b))) for t, b in switches)
        self.switch_at = {t: i for i, (t, _b) in enumerate(self.switches)}
        self.barriers = [frozenset(b) for _t, b in self.switches]

    def step_ok(self, a, b) -> bool:
        """The game blocks a step between tiles of different elevation unless one is 0 or 15 (ramps / universal). No elevation data = free."""
        if self.elev is None:
            return True
        ea, eb = int(self.elev[a[1]][a[0]], 16), int(self.elev[b[1]][b[0]], 16)
        return ea == eb or ea in (0, 15) or eb in (0, 15)

    def wall(self, x, y, pressed) -> bool:
        if not (0 <= x < self.w and 0 <= y < self.h) or self.rows[y][x] == "#" or (x, y) in self.solid:
            return True
        return any(i not in pressed and (x, y) in b for i, b in enumerate(self.barriers))


def _region(floor, start, boulders, pressed, goal=frozenset()):
    """Tiles the player can walk to from `start` (boulders and warp tiles block; a goal warp tile is reachable but not passed through)."""
    seen = {start}
    stack = [start]
    while stack:
        x, y = stack.pop()
        if (x, y) in goal and (x, y) != start:
            continue
        for dx, dy in _DIRS.values():
            n = (x + dx, y + dy)
            if n in seen or n in boulders or floor.wall(n[0], n[1], pressed) or not floor.step_ok((x, y), n):
                continue
            if n in floor.warps and n not in goal:
                continue
            seen.add(n)
            stack.append(n)
    return seen


def walk_path(floor: Floor, start, end, boulders, pressed=frozenset()):
    """Shortest walking path start→end as a list of tiles (excluding start; boulders and other warp tiles block), or None."""
    start, end = tuple(start), tuple(end)
    if start == end:
        return []
    boulders = frozenset(map(tuple, boulders))
    prev = {start: None}
    queue = deque([start])
    while queue:
        cur = queue.popleft()
        if cur == end:
            break
        for dx, dy in _DIRS.values():
            n = (cur[0] + dx, cur[1] + dy)
            if n in prev or n in boulders or floor.wall(n[0], n[1], pressed) or not floor.step_ok(cur, n) or (n in floor.warps and n != end):
                continue
            prev[n] = cur
            queue.append(n)
    if end not in prev:
        return None
    out, cur = [], end
    while cur != start:
        out.append(cur)
        cur = prev[cur]
    return out[::-1]


def solve(floor: Floor, player, boulders, pressed=frozenset(), goal=(), limit: int = 200000, drop: bool = False):
    """Pushes that bring the player to a tile of `goal`. Returns [("push", stand, direction), …, ("goto", tile)] or None.
    `pressed` = indices of switches already pressed (their barriers are open). With `drop=True` the goal is to push a boulder into a hole instead
    (the result ends with that last push; `goal` is ignored)."""
    goal = frozenset(map(tuple, goal))
    boulders = frozenset(map(tuple, boulders))
    pressed = frozenset(pressed)
    player = tuple(player)

    def key(b, pr, region):
        return (b, pr, min(region))

    region = _region(floor, player, boulders, pressed, goal)
    seen = {key(boulders, pressed, region)}
    queue = deque([(boulders, pressed, player, region, ())])
    while queue and len(seen) < limit:
        b, pr, pos, region, pushes = queue.popleft()
        hit = None if drop else region & goal
        if hit:
            tile = min(hit)
            return [*pushes, ("goto", tile)]
        for bt in b:
            for name, (dx, dy) in _DIRS.items():
                stand = (bt[0] - dx, bt[1] - dy)
                dest = (bt[0] + dx, bt[1] + dy)
                if stand not in region or floor.wall(dest[0], dest[1], pr) or dest in b or (dest in floor.warps and dest not in floor.holes) or not floor.step_ok(bt, dest) \
                        or not floor.step_ok(stand, bt):                 # the push is a step INTO the boulder's tile: its elevation counts for the player too
                    continue
                if drop and dest in floor.holes:
                    return [*pushes, ("push", stand, name)]
                nb = (b - {bt}) if dest in floor.holes else (b - {bt}) | {dest}
                npr = pr | {floor.switch_at[dest]} if dest in floor.switch_at else pr
                nregion = _region(floor, bt, nb, npr, goal)
                k = key(nb, npr, nregion)
                if k in seen:
                    continue
                seen.add(k)
                queue.append((nb, npr, bt, nregion, (*pushes, ("push", stand, name))))
    return None
