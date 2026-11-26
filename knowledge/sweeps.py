"""Area completion, read from the game's own flags (pure; the data is knowledge/area_sweeps.py, generated from the decomp — #366).

Every trainer has a defeat flag, every item ball a FLAG_HIDE_* that is set once it is taken, every hidden item a flag set once found; `progress` counts them per named area. Information for
the model — which areas are half-finished, what a missable area would cost to leave — never a wall, and nothing here walks anywhere (the `sweep(area)` driver is a separate step)."""
from knowledge.area_sweeps import AREAS

# (area, flag whose being SET ends the chance, why, what the model can still do) — only areas where leaving really loses things (verified in the decomp / the game).
MISSABLE = {
    "S.S. Anne": (0x237, "the ship sails once you have HM01 Cut from the Captain", "finish its trainers and items before you take Cut (quest('cut'))"),   # FLAG_GOT_HM01
}

MAP_AREA = {m: area for area, d in AREAS.items() for m in d["maps"]}      # (bank, id) -> area name (a map belongs to at most one named area)


def area_of_map(map_key) -> str | None:
    return MAP_AREA.get(tuple(map_key))


def progress(area: str, flag_set) -> dict:
    """{'trainers': (done, total), 'items': (done, total), 'hidden': (done, total)} for one area. `flag_set(n) -> bool`."""
    d = AREAS[area]
    return {kind: (sum(1 for f in d[kind] if flag_set(f)), len(d[kind])) for kind in ("trainers", "items", "hidden")}


def remaining(prog: dict, hidden: bool = False) -> int:
    return sum(t - done for kind, (done, t) in prog.items() if hidden or kind != "hidden")


def complete(prog: dict, hidden: bool = True) -> bool:
    return remaining(prog, hidden) == 0


def line(area: str, prog: dict) -> str:
    """'Mt. Moon: 11/11 trainers, 6/10 items, 2/8 hidden items (an Itemfinder finds most)' — kinds the area does not have are left out."""
    parts = [f"{done}/{total} {label}" for (kind, label) in (("trainers", "trainers"), ("items", "items"), ("hidden", "hidden items")) for done, total in [prog[kind]] if total]
    return f"{area}: " + ", ".join(parts)


def missable_note(area: str, prog: dict, flag_set) -> str:
    """The advice when this area would be lost by moving on and it is not finished ('' otherwise): what would be missed and what to do. Never a wall."""
    rule = MISSABLE.get(area)
    if not rule or flag_set(rule[0]):
        return ""
    open_ = remaining(prog)
    if not open_:
        return ""
    return (f"⚠ {area}: {prog['trainers'][1] - prog['trainers'][0]} trainers and {prog['items'][1] - prog['items'][0]} items still open — {rule[1]}; "
            f"{rule[2]} if you want them (your call).")


def started(flag_set) -> list[tuple[str, dict]]:
    """Areas with some progress but not all of it, most complete first — the half-finished ones."""
    out = []
    for area in AREAS:
        p = progress(area, flag_set)
        done = sum(d for d, _t in p.values())
        total = sum(t for _d, t in p.values())
        if 0 < done < total:
            out.append((done / total, area, p))
    return [(a, p) for _r, a, p in sorted(out, reverse=True)]
