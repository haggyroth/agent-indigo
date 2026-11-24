"""Flying instead of walking (pure): when Fly beats the walk, and which visited town to fly to.

A watched run with Fly on the team walked from the Indigo Plateau back to Route 15 through Victory Road, Viridian Forest and Mt. Moon (a wild battle every few tiles, each
one a model decision), then to Saffron the same way and back — never once calling fly_to. The model picks places, not routes, so the travel code picks the cheaper way."""
from knowledge.distance import tiles_between

FLY_TILES = 40        # a flight (party menu, region map, fade out and in) costs about this many tiles of walking — and no wild battles
MIN_SAVING = 30       # fly only when it beats the walk by at least this many tiles: a short hop is not worth the menus


def best_flight(walk, target, visited, leave: float = 0.0, here=None):
    """(town map, tiles saved) of the best visited town to fly to on the way to the map `target`, or None when walking is as good.
    `walk` = estimated walking tiles to `target` (None = no walking route at all, so any flight wins); `visited` = the maps of the towns Fly can reach; `leave` = tiles to
    walk first to get outdoors (a Pokémon Center's door); `here` = the current map (flying to it is no flight)."""
    best = None
    for town in visited:
        town = tuple(town[:2])
        if here is not None and town == tuple(here[:2]):
            continue
        rest = 0.0 if town == tuple(target[:2]) else tiles_between(town, tuple(target[:2]))
        if rest is None:
            continue
        cost = leave + FLY_TILES + rest
        if best is None or cost < best[0]:
            best = (cost, town)
    if best is None:
        return None
    saved = float("inf") if walk is None else walk - best[0]
    return (best[1], saved) if saved >= MIN_SAVING else None
