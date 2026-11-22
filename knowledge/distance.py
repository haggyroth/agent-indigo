"""How far apart two places are, in walking tiles (pure; estimates from the map sizes, not a path search).

The map graph counts hops, and a hop is anything from a 10-tile doorway to Route 12's 120-tile pier. Grind-site choice needs the real cost of
walking: a watched run trained on Route 13, two routes from the nearest Pokémon Center, and spent a few hundred tiles to heal every time."""
from functools import lru_cache

from knowledge.map_dims import MAP_DIMS
from knowledge.map_graph import MAP_KIND, route_to

DEFAULT_DIM = (30, 30)
WARP_TILES = 14          # walking to a door / stairs and through the room beyond it
OBSTACLE_TILES = 8       # a Cut tree, a Snorlax, a stretch of water inside a map
ARRIVAL_SHARE = 0.3      # the last map: how far in from its edge the thing we want is, as a share of its length along the way in


def _span(map_key, direction: str) -> int:
    w, h = MAP_DIMS.get(tuple(map_key[:2]), DEFAULT_DIM)
    return h if direction in ("North", "South") else w


def route_tiles(route, start_map=None) -> float:
    """Estimated walking tiles along `route` (route_to's steps) from `start_map`: a seamless crossing walks the map being left end to end (half of it for the
    first map, where the player already is somewhere inside), a warp costs a flat WARP_TILES."""
    if not route:
        return 0.0
    total, cur = 0.0, tuple(start_map[:2]) if start_map else None
    for i, (kind, arg, dest) in enumerate(route):
        if kind == "connection":
            length = _span(cur if cur else dest, arg)
            total += length * 0.5 if i == 0 else length
        elif kind == "warp":
            total += WARP_TILES
        else:
            total += OBSTACLE_TILES
        cur = tuple(dest[:2])
    kind, arg, dest = route[-1]
    return total + ARRIVAL_SHARE * _span(dest, arg if kind == "connection" else "East")


def tiles_between(start, goal) -> float | None:
    """Estimated walking tiles from routing node `start` to map `goal`, or None when the graph has no route."""
    route = route_to(start, goal)
    return None if route is None else route_tiles(route, start)


PLATEAU_CENTER = (13, 0)


@lru_cache(maxsize=None)
def pokecenter_tiles(site: tuple) -> float | None:
    """Tiles from the nearest Pokémon Center to `site` (a map): what every heal trip costs one way."""
    best = None
    for pc, kind in MAP_KIND.items():
        if pc == PLATEAU_CENTER:
            continue            # past Victory Road's puzzles: counting it made the cave's floors look 63-104 tiles from a Center when the walk to Viridian's is 126+
        if kind in ("pokecenter", "home"):          # Mom's house heals too (once the rival is beaten — always true by the time anyone grinds far from Pallet)
            d = tiles_between(pc, tuple(site[:2]))
            if d is not None and (best is None or d < best):
                best = d
    return best
