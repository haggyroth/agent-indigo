"""Which grass to grind on (pure): a route whose wild levels fit the Pokémon being trained.

Wild XP scales with the foe's level and is split between participants, so a patch tuned for the ace levels the ace
and barely moves a L10 (and its foes can KO the L10). A human trains the weak one where the wild Pokémon are about its
own level. Data: knowledge.encounters (generated from the decomp)."""
from knowledge.encounters import LAND_LEVELS
from knowledge.map_graph import GRASS_MAPS, nearest_grass, route_to

AIM_ABOVE = 1.5        # ideal average wild level relative to the trainee
HOT_MARGIN = 6         # a route whose strongest wild Pokémon is this far above the trainee is too dangerous
COLD_MARGIN = 6        # …and one whose average is this far below wastes time
STEP_COST = 0.15       # one hop of travel counts as this many "levels of misfit"


def route_fit(map_key, level: int):
    """Misfit of a grass map for a trainee at `level` (0 = ideal), or None when the map has no data."""
    row = LAND_LEVELS.get(tuple(map_key[:2]))
    if row is None or not level:
        return None
    lo, avg, hi = row
    return abs(avg - (level + AIM_ABOVE)) + max(0.0, hi - (level + HOT_MARGIN))


def is_misfit(map_key, level: int) -> bool:
    """Too hot (dangerous, and it feeds whoever is strongest) or too cold (almost no XP) for `level`."""
    row = LAND_LEVELS.get(tuple(map_key[:2]))
    if row is None or not level:
        return False
    lo, avg, hi = row
    return hi > level + HOT_MARGIN or avg < level - COLD_MARGIN


def best_grass(start, level: int, exclude_current: bool = False, avoid=()):
    """(goal_map, steps) of the reachable grass map that best fits `level` (fit + a small travel cost), or the
    nearest grass when there is no level / no data. Same return shape as map_graph.nearest_grass."""
    avoid = {tuple(a[:2]) for a in avoid}
    if not level:
        return nearest_grass(start, exclude_current=exclude_current, avoid=avoid)
    best = None
    for m in GRASS_MAPS:
        if m in avoid or m not in LAND_LEVELS or (exclude_current and m == tuple(start[:2])):
            continue
        steps = route_to(start, m)
        if steps is None:
            steps = route_to(tuple(start[:2]), m)
        if steps is None:
            continue
        score = route_fit(m, level) + STEP_COST * len(steps)
        if best is None or score < best[0]:
            best = (score, m, steps)
    if best is None:
        return nearest_grass(start, exclude_current=exclude_current, avoid=avoid)
    return best[1], best[2]
