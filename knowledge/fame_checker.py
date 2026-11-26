"""Fame Checker progress (pure; the data is knowledge/fame_checker_data.py, generated from the decomp — #368).

The Gossip Checker achievement wants all 96 entries: 16 people x 6 flavor texts. Each entry is set by one script — talking to an NPC or a sign, or winning a battle / seeing a scene —
and some NPCs are only out at certain points (the magazine journals appear once you beat that Gym's leader, the gossipers after the Hall of Fame). This module counts what is owned,
says what can be had NOW (its NPC is out and its story gate is open) and what has to wait for what. Information only: it never walks anywhere."""
from knowledge.fame_checker_data import ENTRIES, PERSONS
from knowledge.navigation import MAP_NAMES

TOTAL = len(ENTRIES)
HIDE_WHY = {157: "the Hall of Fame (the gossipers come out)", 2092: "the Hall of Fame"}
_JOURNAL_GYM = {115: "beating Erika", 131: "beating Koga", 124: "beating Sabrina", 56: "beating Lt. Surge"}


def where(entry) -> str:
    """'Pewter City (21,28)' — the map's name when known, else its script's prefix."""
    _p, _i, mp, kind, x, y, label, _h, _n = entry
    name = MAP_NAMES.get(tuple(mp)) or label.split("_EventScript")[0].replace("_", " ")
    return f"{name} ({x},{y})" if x >= 0 else name


def gate(entry, flag_set) -> str:
    """'' when the entry is open, else what it waits for."""
    _p, _i, _mp, kind, _x, _y, _label, hide, need = entry
    if need and not flag_set(need):
        return "clearing the game (Hall of Fame)"
    if hide and flag_set(hide):
        return _JOURNAL_GYM.get(hide) or HIDE_WHY.get(hide) or f"a story step (flag {hide:#x})"
    return ""


def status(owned: dict, flag_set) -> dict:
    """{'total', 'have', 'missing': [entry], 'now': [open entry], 'waiting': {why: n}} — `owned` is {person: {flavor idx}} (read_fame_checker)."""
    missing = [e for e in ENTRIES if e[1] not in owned.get(e[0], set())]
    now, waiting = [], {}
    for e in missing:
        g = gate(e, flag_set)
        if g:
            waiting[g] = waiting.get(g, 0) + 1
        else:
            now.append(e)
    return {"total": TOTAL, "have": TOTAL - len(missing), "missing": missing, "now": now, "waiting": waiting}


def line(owned: dict, flag_set) -> str:
    """'FAME CHECKER: 41/96 entries · 9 are open (quest('fame')) · 12 wait for the Hall of Fame, 3 for beating Koga'."""
    s = status(owned, flag_set)
    if not s["missing"]:
        return f"FAME CHECKER: all {TOTAL} entries (Gossip Checker complete)"
    parts = [f"{s['have']}/{TOTAL} entries"]
    if s["now"]:
        parts.append(f"{len(s['now'])} are open (quest('fame'))")
    if s["waiting"]:
        parts.append("; ".join(f"{n} wait for {why}" for why, n in sorted(s["waiting"].items(), key=lambda kv: -kv[1])))
    return "FAME CHECKER: " + " · ".join(parts)


def view(owned: dict, flag_set) -> str:
    """quest('fame'): every missing entry grouped by person — where it is and what it waits for."""
    s = status(owned, flag_set)
    if not s["missing"]:
        return line(owned, flag_set)
    lines = [line(owned, flag_set), "Missing, by person (talk to the NPC / sign, or win the battle named; quest('fame go') walks to the next open one):"]
    by = {}
    for e in s["missing"]:
        by.setdefault(e[0], []).append(e)
    for p in sorted(by):
        rows = []
        for e in by[p]:
            g = gate(e, flag_set)
            how = {"npc": "talk", "sign": "read", "event": "scene"}[e[3]]
            rows.append(f"{how} @ {where(e)}" + (f" [after {g}]" if g else ""))
        lines.append(f"  {PERSONS[p]} ({6 - len(by[p])}/6): " + " | ".join(rows))
    return "\n".join(lines)


def next_target(owned: dict, flag_set, here: tuple, skip=(), dist=None) -> tuple | None:
    """The entry to walk to next: a talkable one (NPC / sign) that is open — the current map first, then the nearest by `dist(map) -> hops or None` (None = no route: left out), else data order.
    `skip` = (person, idx) given up on."""
    cand = [e for e in status(owned, flag_set)["now"] if e[3] in ("npc", "sign") and (e[0], e[1]) not in skip]
    keyed = []
    for e in cand:
        mp = tuple(e[2])
        d = 0 if mp == tuple(here) else (dist(mp) if dist else 1)
        if d is not None:
            keyed.append(((d, mp, e[0], e[1]), e))
    return min(keyed, key=lambda k: k[0])[1] if keyed else None
