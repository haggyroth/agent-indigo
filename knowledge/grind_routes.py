"""Which grass to grind on (pure): a route whose wild levels fit the Pokémon being trained.

Wild XP scales with the foe's level and is split between participants, so a patch tuned for the ace levels the ace
and barely moves a L10 (and its foes can KO the L10). A human trains the weak one where the wild Pokémon are about its
own level. Data: knowledge.encounters (generated from the decomp)."""
from knowledge.encounters import LAND_LEVELS
from knowledge.map_graph import GRASS_MAPS, VICTORY_ROAD_MAPS, nearest_grass, route_to

AIM_ABOVE = 1.5        # ideal average wild level relative to the trainee
HOT_MARGIN = 6         # a route whose strongest wild Pokémon is this far above the trainee is too dangerous
COLD_MARGIN = 6        # …and one whose average is this far below wastes time
STEP_COST = 0.15       # (no longer used by best_grass — kept for callers) one hop of travel counted as this many "levels of misfit"
TILES_PER_LEVEL = 80.0     # walking this many tiles costs as much as one level of misfit (about 25 s of game time per trip)
HEAL_TRIPS = 1.5           # a grind session heals about this often: each costs a round trip between the grass and the nearest Pokémon Center


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


def site_cost(map_key, level: int, to_site: float, to_pc: float, detour: float | None = None) -> float:
    """Total cost of grinding at `map_key` for a trainee at `level`, in levels of misfit: how badly the wild levels fit, plus the walk there (or, with an objective
    ahead, the EXTRA walk it adds to getting to that objective), plus the heal trips back to the nearest Pokémon Center."""
    trip = to_site if detour is None else detour
    return route_fit(map_key, level) + trip / TILES_PER_LEVEL + HEAL_TRIPS * 2 * to_pc / TILES_PER_LEVEL


def _with_fly(walk: float | None, site, fly_towns) -> float | None:
    """`walk` tiles to `site`, or the cheaper way when Fly can take the party to a visited town near it first (None stays None: no route either way)."""
    from knowledge.distance import tiles_between
    from knowledge.flight import FLY_TILES
    best = walk
    for town in fly_towns:
        rest = 0.0 if tuple(town[:2]) == tuple(site[:2]) else tiles_between(tuple(town[:2]), tuple(site[:2]))
        if rest is not None and (best is None or FLY_TILES + rest < best):
            best = FLY_TILES + rest
    return best


def best_grass(start, level: int, exclude_current: bool = False, avoid=(), objective=None, fly_towns=()):
    """(goal_map, steps) of the grass map that is the best place to train a Pokémon at `level`: wild levels that fit, close to the Pokémon Centers it will heal at,
    and (when `objective` — the map of the next goal — is given) on the way to it. Falls back to the nearest grass when there is no level / no data. Same return
    shape as map_graph.nearest_grass. `fly_towns` = the maps of the towns Fly can reach right now (empty without Fly): the walk to a site and the heal trips are priced at
    the cheaper of walking and flying to the town nearest it — a site two towns from the Center is not far when the party can fly there."""
    from knowledge.distance import pokecenter_tiles, route_tiles, tiles_between
    avoid = {tuple(a[:2]) for a in avoid}
    if not level:
        return nearest_grass(start, exclude_current=exclude_current, avoid=avoid)
    direct = tiles_between(start, tuple(objective[:2])) if objective else None
    best = None
    for m in GRASS_MAPS:
        if m in avoid or m not in LAND_LEVELS or (exclude_current and m == tuple(start[:2])):
            continue
        if m in VICTORY_ROAD_MAPS and m != (1, 39) and tuple(start[:2]) != m:
            continue             # 2F / 3F sit behind the boulder puzzles that go_to cannot solve (a watched run's relocation ended 'blocked' on 2F twelve times from 1F): a site only for someone already standing there
        steps = route_to(start, m)
        if steps is None:
            steps = route_to(tuple(start[:2]), m)
        if steps is None:
            continue
        to_site = route_tiles(steps, start)
        pc = pokecenter_tiles(m)
        if fly_towns:
            to_site = _with_fly(to_site, m, fly_towns)
            pc = _with_fly(pc, m, fly_towns) if pc is not None else None
        onward = tiles_between(m, tuple(objective[:2])) if objective else None
        detour = max(0.0, to_site + onward - direct) if onward is not None and direct is not None else None
        score = site_cost(m, level, to_site, pc if pc is not None else to_site, detour)
        if best is None or score < best[0]:
            best = (score, m, steps)
    if best is None:
        return nearest_grass(start, exclude_current=exclude_current, avoid=avoid)
    return best[1], best[2]
