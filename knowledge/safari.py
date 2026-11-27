"""The Safari Zone's grass encounters, by species (pure; read from knowledge/wild_locations.py, generated from the decomp — #362).

Four areas (Center / East / North / West = maps (1,63)-(1,66)); a visit is ¥500 for 30 Safari Balls and about 600 steps. Only the GRASS rows matter to a hunt (the water ones need a rod / Surf and
the Safari has its own battle menu: ball / bait / rock / run)."""
from knowledge.wild_locations import MAP_LABELS, WILD_LOCATIONS

SAFARI_MAPS = (63, 64, 65, 66)            # map ids in group 1


def areas_for(species_id: int, method: str = "grass") -> list[tuple[tuple[int, int], int, int]]:
    """[((1, map id), min level, max level)] of the Safari areas where `species_id` shows up by `method`, in map order."""
    return sorted({((1, r[1]), r[3], r[4]) for r in WILD_LOCATIONS.get(species_id, []) if r[0] == 1 and r[1] in SAFARI_MAPS and r[2] == method})


def species_by_name(query: str, names: dict) -> int | None:
    """A Safari grass species for a name (case / punctuation tolerant, unique prefix ok); None when it is not one."""
    q = "".join(ch for ch in str(query).lower() if ch.isalnum())
    if not q:
        return None
    cands = {sid: "".join(ch for ch in names.get(sid, "").lower() if ch.isalnum()) for sid in WILD_LOCATIONS if areas_for(sid)}
    exact = [sid for sid, n in cands.items() if n == q]
    hits = exact or [sid for sid, n in cands.items() if n.startswith(q)]
    return hits[0] if len(hits) == 1 else None


def listing(names: dict) -> str:
    """'Safari Zone grass: Chansey (Center L23, North L26), Tauros (North L28, West L25), …' — what a hunt can target."""
    rows = []
    for sid in sorted(WILD_LOCATIONS):
        a = areas_for(sid)
        if not a:
            continue
        where = []
        for m, lo, hi in a:
            area = MAP_LABELS[m].replace("Safari Zone ", "")
            where.append(f"{area} L{lo}" + (f"-{hi}" if hi != lo else ""))
        rows.append(f"{names.get(sid, sid)} ({', '.join(where)})")
    return "Safari Zone grass: " + ", ".join(rows)
