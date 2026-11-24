"""Victory Road routing (pure): which warp to take next, and the boulder pushes that open the way.

knowledge.vr_data (decomp, via tools/gen_victory_road.py) has the three floors; knowledge.boulder_puzzle does the push search inside one floor.
Walking alone gets from the entrance to 2F, from 2F's far side round through 3F, and out — except 2F's west half, which a boulder on a floor
switch opens. `plan` returns the FIRST action (walk to a warp tile / push a boulder) for the live driver, which re-reads the boulders and plans again."""
from collections import deque

from knowledge.boulder_puzzle import _DIRS, Floor, _region, solve, walk_path
from knowledge.vr_data import FLOORS, WARPS

VR_1F, VR_2F, VR_3F = (1, 39), (1, 40), (1, 41)
EXIT = (VR_2F, (48, 12))                         # the arrow warp out to Route 23's north half (it leads to Indigo Plateau)
DOWN_ARROW = {(VR_2F, (48, 12)), (VR_1F, (11, 20))}      # 0x65: stand on the tile and hold Down
SOFT = DOWN_ARROW                    # arrow warps only fire when Down is held ON them: walking across one (or pushing a boulder past it) is fine
VAR_SWITCH = {VR_1F: (0x4064,), VR_2F: (0x4065, 0x4066), VR_3F: (0x4067,)}       # VAR_MAP_SCENE_VICTORY_ROAD_*: 100 = switch pressed
_FLOORS: dict = {}


def floor(key) -> Floor:
    if key not in _FLOORS:
        f = FLOORS[key]
        _FLOORS[key] = Floor(f["rows"], f["solid"], [(x, y) for (k, x, y) in WARPS if k == key and (k, (x, y)) not in SOFT], f["switches"], f["elev"], f["holes"])
    return _FLOORS[key]


def initial_boulders(key, revealed: bool = False):
    """Boulders a floor starts with. `revealed` = the 3F boulder has fallen through its hole, so 2F's hidden one (33,19) now stands there."""
    extra = FLOORS[key]["later_boulders"] if revealed else []
    return tuple(map(tuple, [*FLOORS[key]["boulders"], *extra]))


def button(key, tile):
    return "Down" if (key, tuple(tile)) in DOWN_ARROW else None


def _walk_path(key, start, boulders=None, pressed=frozenset(), revealed=False, all_pressed=None):
    """Hops [(floor, warp tile)] from (key, start) to the exit using ONLY walking (boulders fixed), or None."""
    node0 = (key, tuple(start))
    prev = {node0: None}
    queue = deque([node0])
    while queue:
        fl, pos = queue.popleft()
        bl = frozenset(boulders if (fl == key and boulders is not None) else initial_boulders(fl, revealed))
        pr = pressed if fl == key else frozenset((all_pressed or {}).get(fl, ()))      # a pressed switch stays pressed; the boulders reset on every entry
        f = floor(fl)
        goals = frozenset(f.warps)
        reg = _region(f, pos, bl, pr, goals)
        if fl == EXIT[0] and EXIT[1] in reg:
            hops, node = [(fl, EXIT[1])], (fl, pos)
            while prev[node] is not None:
                node, hop = prev[node]
                hops.append(hop)
            return hops[::-1]
        for w in f.warps & reg:
            if w == pos:
                continue
            dest = WARPS[(fl, w[0], w[1])]
            if dest is None:
                continue
            nxt = (dest[0], (dest[1], dest[2]))
            if nxt not in prev:
                prev[nxt] = ((fl, pos), (fl, w))
                queue.append(nxt)
    return None


def _stage_target(here, revealed, all_pressed):
    """The warp to head for on this floor in the cave's order of play (after plain walking to the exit has been ruled out):
    1F stairs up → 2F: press the west switch, go up the (34,9) ladder → 3F: drop the boulder down the hole (handled by the caller), jump in after it →
    2F: push it onto the second switch, take (36,17) to the side room → 3F → 2F's east end."""
    if here == VR_1F:
        return (3, 2)
    if here == VR_2F:
        return (36, 17) if revealed else (34, 9)
    if here == VR_3F and revealed and 1 not in set((all_pressed or {}).get(VR_2F, ())):
        return (34, 18)                                            # the hole: land beside the boulder that fell
    return None


_PLAN: dict = {}                                  # {(floor, boulders, pressed): action} for the push sequence last solved — the search runs once, not per push


def _state_key(here, f, pos, boulders, pressed):
    """(floor, boulders, pressed, the region the player can walk): the same boulders with the player somewhere else are a different plan."""
    reg = _region(f, tuple(pos), frozenset(boulders), frozenset(pressed), frozenset(f.warps))
    return (here, tuple(sorted(boulders)), frozenset(pressed), min(reg))


def _remember(here, pos, boulders, pressed, sol, goal_action):
    """Index a solved push sequence by the state before each step, so the next plan() calls are lookups (the live driver re-plans after every push)."""
    f = floor(here)
    for k in [k for k in _PLAN if k != "ctx"]:
        del _PLAN[k]
    b, pr, at = set(boulders), set(pressed), tuple(pos)
    for step in sol:
        key = _state_key(here, f, at, b, pr)
        if step[0] == "goto":
            _PLAN[key] = goal_action
            return
        _PLAN[key] = ("push", step[1], step[2])
        dx, dy = _DIRS[step[2]]
        old = (step[1][0] + dx, step[1][1] + dy)
        new = (old[0] + dx, old[1] + dy)
        b.discard(old)
        b.add(new)
        at = old                                         # a push leaves the player on the boulder's old tile
        if new in f.switch_at:
            pr.add(f.switch_at[new])


def plan(here, pos, boulders, pressed=frozenset(), revealed: bool = False, all_pressed=None, limit: int = 40000):
    """The next action on floor `here` from `pos` given the live `boulders` ([(x, y)]) and `pressed` switch indices:
    ("warp", tile, button or None) · ("push", stand, direction) · None when no route is found. `revealed`: the 3F boulder has already been dropped down
    its hole (FLAG_HIDE_VICTORY_ROAD_2F_BOULDER cleared), so 2F has its extra boulder. `all_pressed` = {floor: pressed switch indices} for every floor."""
    pos = tuple(pos)
    boulders = tuple(sorted(map(tuple, boulders)))
    pressed = frozenset(pressed)
    f = floor(here)
    ctx = (here, bool(revealed), tuple(sorted((k, tuple(sorted(v))) for k, v in (all_pressed or {}).items())))
    if _PLAN.get("ctx") != ctx:                        # a cached sequence is only valid in the situation it was solved in
        _PLAN.clear()
        _PLAN["ctx"] = ctx
    hit = _PLAN.get(_state_key(here, f, pos, boulders, pressed))
    if hit is not None:
        return hit
    hops = _walk_path(here, pos, boulders, pressed, revealed, all_pressed)
    if hops:
        fl, tile = hops[0]
        return ("warp", tile, button(fl, tile))
    if f.holes and not revealed:                       # 3F: the boulder that falls through the hole becomes 2F's switch boulder — drop it first
        drop = solve(f, pos, boulders, pressed, drop=True, limit=limit)
        if drop:
            _remember(here, pos, boulders, pressed, drop, None)
            return ("push", drop[0][1], drop[0][2])
    target = _stage_target(here, revealed, all_pressed)
    if target is not None and target != pos:                       # the cave's known order of play, solved one floor at a time
        sol = solve(f, pos, boulders, pressed, [target], limit=limit)
        if sol is not None:
            goal_action = ("warp", target, button(here, target))
            _remember(here, pos, boulders, pressed, sol, goal_action)
            return goal_action if sol[0][0] == "goto" else ("push", sol[0][1], sol[0][2])
    exit_tile = [EXIT[1]] if here == EXIT[0] else []
    cands = []
    for w in sorted(f.warps) + exit_tile:
        if w == pos:
            continue
        dest = WARPS[(here, w[0], w[1])]
        onward = dest is None or bool(_walk_path(dest[0], (dest[1], dest[2]), revealed=revealed, all_pressed=all_pressed))
        cands.append((not onward, w, dest))                       # warps that lead on by plain walking are tried first
    cands.sort(key=lambda c: c[0])
    fallback = None
    for budget in (3000, limit):                                  # cheap searches first: an unsolvable candidate costs its whole budget
        for no_onward, w, dest in cands:
            if no_onward and fallback is not None:
                continue
            sol = solve(f, pos, boulders, pressed, [w], limit=budget)
            if sol is None:
                continue
            goal_action = ("warp", w, button(here, w))
            action = goal_action if sol[0][0] == "goto" else ("push", sol[0][1], sol[0][2])
            if not no_onward:
                _remember(here, pos, boulders, pressed, sol, goal_action)
                return action
            fallback = (action, sol, goal_action)
        if fallback is not None:
            break
    if fallback:
        _remember(here, pos, boulders, pressed, fallback[1], fallback[2])
        return fallback[0]
    return None


def waypoints(here, pos, target, boulders, pressed=frozenset(), leg: int = 8):
    """Intermediate tiles for walking pos → target along the model's own path (its corners, and at most `leg` tiles apart), ending with the target.
    The live pathfinder balks at some long cave walks (boulders it half-understands), so the driver walks short straight legs instead. [] = no path."""
    path = walk_path(floor(here), pos, target, boulders, pressed)
    if path is None:
        return []
    out, prev_dir, run = [], None, 0
    for i, tile in enumerate(path):
        before = path[i - 1] if i else tuple(pos)
        d = (tile[0] - before[0], tile[1] - before[1])
        run = run + 1 if d == prev_dir else 1
        nxt = path[i + 1] if i + 1 < len(path) else None
        turns = nxt is not None and (nxt[0] - tile[0], nxt[1] - tile[1]) != d
        if turns or run >= leg or nxt is None:
            out.append(tile)
            run = 0
        prev_dir = d
    return out


def reset_action(here, pos, boulders, pressed=frozenset(), revealed: bool = False):
    """The way out of a wedged floor: ("warp", tile, button) to a warp the player can WALK to, to leave and come back — the cave puts every boulder back where the decomp has it each
    time a floor loads. None when the floor is untouched (nothing to reset: the puzzle itself has no route), or nothing is reachable. A watched run pushed a 1F boulder into the corridor's
    dead end and then looped on 'No route through Victory Road 1F' for 200 calls."""
    pos, boulders = tuple(pos), frozenset(map(tuple, boulders))
    if boulders == frozenset(initial_boulders(here, revealed)):
        return None
    f = floor(here)
    tiles = sorted(f.warps - {EXIT[1]} if here == EXIT[0] else f.warps) + [t for (k, t) in sorted(DOWN_ARROW) if k == here and (k, t) != EXIT]
    reach = _region(f, pos, boulders, frozenset(pressed), frozenset(tiles))
    for tile in sorted(tiles, key=lambda t: (t not in {d for (k, d) in DOWN_ARROW if k == here}, t)):       # the entrance arrow first: it lands outside, where the re-entry is the planner's own
        if tile in reach and tile != pos:
            return ("warp", tile, button(here, tile))
    return None


EXIT_SOUTH = (VR_1F, (11, 20))                   # the entrance arrow warp: holding Down on it walks out to Route 23's south half
_BACK: dict = {}                                 # the hop list last found by plan_back, keyed by the situation it was solved in


def _apply(f, boulders, pressed, pos, sol):
    """(boulders, pressed, end tile) after the push sequence `sol` ([("push", stand, dir)…, ("goto", tile)])."""
    b, pr = set(boulders), set(pressed)
    for step in sol:
        if step[0] == "goto":
            return b, pr, tuple(step[1])
        dx, dy = _DIRS[step[2]]
        old = (step[1][0] + dx, step[1][1] + dy)
        new = (old[0] + dx, old[1] + dy)
        b.discard(old)
        if new not in f.holes:
            b.add(new)
        if new in f.switch_at:
            pr.add(f.switch_at[new])
    return b, pr, tuple(pos)


_SOLVED: dict = {}                               # solve() results for plan_back, keyed by the whole situation: later floors repeat between re-plans


def _solve_cached(f, fl, at, boulders, pressed, w, limit):
    k = (fl, tuple(at), tuple(sorted(boulders)), tuple(sorted(pressed)), tuple(w), limit)
    if k not in _SOLVED:
        _SOLVED[k] = solve(f, at, boulders, pressed, [w], limit=limit)
    return _SOLVED[k]


def plan_back(here, pos, boulders, pressed=frozenset(), all_pressed=None, limit: int = 8000):
    """plan_back_once with a cheap pass first (limit 1500 per hop), then the full budget: the hops that matter are short, the expensive ones only slow the search down."""
    for lim in (1500, limit):
        out = _plan_back(here, pos, boulders, pressed, all_pressed, lim)
        if out is not None:
            return out
    return None


def _plan_back(here, pos, boulders, pressed, all_pressed, limit):
    """The next action for walking OUT of the cave to Route 23's south half from floor `here` (the way back after the Plateau, with no Fly):
    ("warp", tile, button) · ("push", stand, direction) · None when no route is found. The cave resets its switches and boulders when you leave it north, so the way down
    is the puzzle run in reverse (from the east door: 3F's push, 2F west's push, 1F's two pushes — found by a search over floor hops, `solve` per hop). Each call re-plans from the live floor
    state; later floors start from their decomp boulders with the switches `all_pressed` says are pressed."""
    pos = tuple(pos)
    boulders = tuple(sorted(map(tuple, boulders)))
    pressed = frozenset(pressed)
    ap = {fl: frozenset((all_pressed or {}).get(fl, ())) for fl in FLOORS}
    ap[here] = pressed
    key = (here, pos, boulders, tuple(sorted((k, tuple(sorted(v))) for k, v in ap.items())))
    key = key + (limit,)
    if key in _BACK:
        return _BACK[key]
    queue = deque([(here, pos, tuple(boulders), tuple(sorted((k, tuple(sorted(v))) for k, v in ap.items())), None)])
    seen = set()
    result = None
    while queue and result is None:
        fl, at, bl, prs, first = queue.popleft()
        if (fl, at, prs) in seen:
            continue
        seen.add((fl, at, prs))
        prd = {k: frozenset(v) for k, v in prs}
        f = floor(fl)
        cur_b = set(bl) if (fl == here and first is None) else set(initial_boulders(fl, False))
        targets = [(w, WARPS[(fl, w[0], w[1])]) for w in sorted(f.warps)]          # a ladder we stand on counts: the driver steps off it and back
        if fl == EXIT_SOUTH[0]:
            targets.insert(0, (EXIT_SOUTH[1], None))
        for w, dest in targets:
            sol = _solve_cached(f, fl, at, cur_b, prd[fl], w, limit)
            if sol is None:
                continue
            act = ("warp", w, button(fl, w)) if sol[0][0] == "goto" else ("push", sol[0][1], sol[0][2])
            nfirst = first or act
            if dest is None:
                if fl == EXIT_SOUTH[0] and w == EXIT_SOUTH[1]:
                    result = nfirst
                    break
                continue                                             # another exit (the north door): not the way we want
            b2, pr2, _end = _apply(f, cur_b, prd[fl], at, sol)
            nprd = dict(prd)
            nprd[fl] = frozenset(pr2)
            queue.append((dest[0], (dest[1], dest[2]), (), tuple(sorted((k, tuple(sorted(v))) for k, v in nprd.items())), nfirst))
    _BACK.clear()
    _BACK[key] = result
    return result

