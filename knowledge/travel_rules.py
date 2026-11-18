"""Hand-written travel facts the generic router cannot see (pure data + two lookups), kept out of the skill code so the
BFS, the tests and the prompts can all read them.

* `PC_TOWNS` — maps with a Pokémon Center whose first visit sets the blackout respawn point.
* `NO_WALK` — "you cannot go from A back to B on foot" rules. Route 4's east end is a pocket of one-way ledges: you can
  come OUT of Mt. Moon into it but never climb back (live-verified: no walkable path from Route 4's Cerulean side to
  Mt. Moon). The planner's region-blind fallback used to invent a "South edge" link and loop on
  "Reached the South edge but could not cross".
"""
from dataclasses import dataclass

# (bank, id) of towns with their own Pokémon Center (Pallet has none): Viridian, Pewter, Cerulean, Lavender?, Vermilion,
# Celadon, Fuchsia, Cinnabar(?), Saffron — as listed by the original first-visit logic.
PC_TOWNS = frozenset({(3, 1), (3, 2), (3, 3), (3, 4), (3, 5), (3, 6), (3, 7), (3, 8), (3, 10)})


@dataclass(frozen=True)
class NoWalk:
    start: frozenset          # maps you must be standing in
    unreachable: frozenset    # maps that cannot be reached on foot from there
    why: str
    ok_regions: tuple = ()    # (map, region tag) pairs where the rule does NOT apply: the Mt. Moon-side pocket of Route 4 opens straight onto Route 3


_WEST_OF_ROUTE4 = frozenset({(3, 0), (3, 1), (3, 2), (3, 19), (3, 20), (3, 21), (1, 0), (1, 1), (1, 2), (1, 3)})

NO_WALK: tuple[NoWalk, ...] = (
    NoWalk(frozenset({(3, 3), (3, 22)}), _WEST_OF_ROUTE4, "Route 4's ledges only go one way (out of Mt. Moon)",
           ok_regions=(((3, 22), "2"),)),
)


def no_walk_reason(current, target, pos=None) -> str | None:
    """Why `target` can't be reached on foot from `current` (standing at `pos`, when known), or None when the router should try.
    A watched run healed at Route 4's Pokémon Center, came out in the west pocket — one step from Route 3 — and was told it could not walk
    to Route 3, Viridian Forest or Route 2, so grind sent it all the way round to Route 22 (wild L2-5)."""
    cur, tgt = tuple(current[:2]), tuple(target[:2])
    for rule in NO_WALK:
        if cur in rule.start and tgt in rule.unreachable:
            if pos is not None and any(m == cur for m, _t in rule.ok_regions):
                from knowledge.map_graph import region_at
                if (cur, region_at(cur, pos[0], pos[1])) in rule.ok_regions:
                    continue
            return rule.why
    return None
