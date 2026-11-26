"""VS Seeker rematch progress, read from the game's own flags (pure; the data is knowledge/rematch_data.py, generated from the decomp — #367).

Each rematchable trainer has a ladder of parties; every party is its own trainer id, so "this rung is beaten" is that id's defeat flag. The game offers a rung only once its story flag is
set (TIER_UNLOCK) and the VS Seeker has made the trainer ready. This module counts where every ladder stands. Information only: nothing here walks anywhere or uses the item."""
from knowledge.rematch_data import REMATCHES, TIER_UNLOCK

VS_SEEKER_FLAG = 0x292            # FLAG_GOT_VS_SEEKER (the woman in Vermilion City's Pokémon Center)
VS_SEEKER_ITEM = 362
# what each unlock flag means, for the "waiting for" text
UNLOCK_WHY = {0x292: "the VS Seeker", 2198: "visiting Celadon City", 2199: "visiting Fuchsia City", 0x82C: "the Hall of Fame",
              2116: "the Sevii Islands' Network Machine (Celio)"}


def ladder(tiers) -> list[tuple[int, int]]:
    """[(rung index, defeat flag)] of the rungs the game really uses, in order (a SKIP rung and a rung that repeats the one before it are dropped)."""
    out: list[tuple[int, int]] = []
    for j, f in enumerate(tiers):
        if f is not None and (not out or out[-1][1] != f):
            out.append((j, f))
    return out


def status(flag_set) -> dict:
    """Where every ladder stands: totals, how many are at their top party, how many have a rung ready to fight (its story flag is set) and how many wait for story progress
    (grouped by the flag they wait for). `flag_set(n) -> bool`."""
    total = len(REMATCHES)
    started = at_top = ready = 0
    waiting: dict[int, int] = {}
    for _name, _mp, tiers in REMATCHES:
        rungs = ladder(tiers)
        beaten = 0
        for _j, f in rungs:
            if not flag_set(f):
                break
            beaten += 1
        if beaten:
            started += 1
        if beaten == len(rungs):
            at_top += 1
            continue
        if beaten == 0:
            continue                                   # the trainer's first fight has not happened: no rematch exists yet
        j, _f = rungs[beaten]
        need = TIER_UNLOCK.get(j)
        if need is None or flag_set(need):
            ready += 1
        else:
            waiting[need] = waiting.get(need, 0) + 1
    return {"total": total, "started": started, "at_top": at_top, "ready": ready, "waiting": waiting}


def line(flag_set) -> str:
    """'REMATCHES: 12/221 trainers at their top team · 31 have a rematch ready (use the VS Seeker) · 20 wait for the Hall of Fame, 5 for visiting Fuchsia City'."""
    s = status(flag_set)
    parts = [f"{s['at_top']}/{s['total']} trainers at their top team (only trainers you have beaten once count)"]
    if s["ready"]:
        parts.append(f"{s['ready']} have a rematch ready — use the VS Seeker outdoors near them")
    if s["waiting"]:
        parts.append("; ".join(f"{n} wait for {UNLOCK_WHY.get(flag, f'game flag {flag:#x}')}" for flag, n in sorted(s["waiting"].items(), key=lambda kv: -kv[1])))
    return "REMATCHES: " + " · ".join(parts)
