"""RetroAchievements progress, evaluated locally (pure; #358). Agent Indigo is not an RA client — nothing here unlocks anything on the website; this is the agent's own tracking of the LeafGreen set
(knowledge/ra_set.py) against the checks of knowledge/ra_map.py, read from the game's own flags, badges, bag and Pokédex.

States per achievement: 'yes' (every check holds), 'probably' (they hold but the check is only necessary — see ra_map.PARTIAL), 'no', or 'unknown' (no check yet — ra_map.MANUAL)."""
from knowledge.ra_map import CHECKS, MANUAL, PARTIAL
from knowledge.ra_set import ACHIEVEMENTS


def evaluate(check) -> dict:
    """{achievement id: 'yes' | 'probably' | 'no' | 'unknown'}. `check(spec) -> bool` answers one spec of knowledge/ra_map.py (every spec of an achievement must hold)."""
    out = {}
    for aid, *_ in ACHIEVEMENTS:
        if aid in MANUAL or aid not in CHECKS:
            out[aid] = "unknown"
            continue
        ok = True
        for spec in CHECKS[aid]:
            try:
                ok = bool(check(spec))
            except Exception:
                ok = False
            if not ok:
                break
        out[aid] = ("probably" if aid in PARTIAL else "yes") if ok else "no"
    return out


def totals(states: dict) -> dict:
    """{'yes': (n, points), 'probably': (n, points), 'no': (n, points), 'unknown': (n, points), 'all': (n, points)}."""
    out = {k: [0, 0] for k in ("yes", "probably", "no", "unknown", "all")}
    for aid, _t, _d, pts, _k in ACHIEVEMENTS:
        for key in (states.get(aid, "unknown"), "all"):
            out[key][0] += 1
            out[key][1] += pts
    return {k: tuple(v) for k, v in out.items()}


def line(states: dict) -> str:
    """'Achievements 31/128 (214/781 pts), 5 more probably; 12 have no check yet.'"""
    t = totals(states)
    text = f"Achievements {t['yes'][0]}/{t['all'][0]} ({t['yes'][1]}/{t['all'][1]} pts)"
    if t["probably"][0]:
        text += f", {t['probably'][0]} more probably"
    if t["unknown"][0]:
        text += f"; {t['unknown'][0]} have no check yet"
    return text + "."


def open_ones(states: dict, missable_first: bool = True) -> list:
    """The achievements not yet 'yes', as (id, title, description, points, type, state): missables first (they can be lost), then by points."""
    rows = [(aid, t, d, p, k, states.get(aid, "unknown")) for aid, t, d, p, k in ACHIEVEMENTS if states.get(aid) != "yes"]
    rows.sort(key=lambda r: (r[4] != "missable" if missable_first else 0, -r[3]))
    return rows
