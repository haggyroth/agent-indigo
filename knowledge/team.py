"""Team composition (pure): what the party can hit, what it is weak to, which HMs it can carry, whether it answers the
next gym — and what to go and catch if it does not.

Catching used to be a filter (`catch_policy.evaluate`: BST, "adds a new type"). Nothing asked what the TEAM needs. This is
that question: coverage from the moves actually known, shared weaknesses, HM carriers against what the story is about to
demand, and a fit check against the next Gym Leader's real party (generated from the decomp), with a short list of
Pokémon that fix a gap and WHERE they live in LeafGreen (generated wild-encounter data, not memory of another version).
"""
from collections import Counter
from dataclasses import dataclass, field

from game.constants import SPECIES_NAMES
from knowledge.gym_teams import TRAINER_TEAMS
from knowledge.species_data import SPECIES_DATA
from knowledge.type_chart import get_effectiveness
from knowledge.wild_locations import MAP_LABELS, WILD_LOCATIONS

_NAME_TO_ID = {v: k for k, v in SPECIES_NAMES.items()}
TYPES = ("NOR", "FIR", "WAT", "ELE", "GRS", "ICE", "FIG", "POI", "GRD", "FLY", "PSY", "BUG", "ROC", "GHO", "DRG", "DRK", "STL")
TYPE_WORD = {"NOR": "Normal", "FIR": "Fire", "WAT": "Water", "ELE": "Electric", "GRS": "Grass", "ICE": "Ice",
             "FIG": "Fighting", "POI": "Poison", "GRD": "Ground", "FLY": "Flying", "PSY": "Psychic", "BUG": "Bug",
             "ROC": "Rock", "GHO": "Ghost", "DRG": "Dragon", "DRK": "Dark", "STL": "Steel"}
SHARED_WEAKNESS = 3         # this many members weak to one type = a shared weakness
ANSWERS_FRACTION = 0.6      # the team "answers" a leader if it can hit this share of his Pokémon super effectively

# Pokémon worth hunting for each upcoming Gym (a counter to its type that the LeafGreen wild data says can be caught
# around that point of the story). Validated against WILD_LOCATIONS by the tests — a name with no location fails.
GYM_COUNTERS: dict[str, tuple[str, ...]] = {
    "Brock": ("Mankey", "Bellsprout"),
    "Misty": ("Pikachu", "Bellsprout"),
    "Lt. Surge": ("Diglett", "Sandshrew", "Geodude"),
    "Erika": ("Vulpix", "Spearow", "Pidgey"),
    "Koga": ("Abra", "Sandshrew", "Drowzee"),
    "Sabrina": ("Venonat", "Paras", "Gastly"),
    "Blaine": ("Krabby", "Staryu", "Geodude"),
    "Giovanni": ("Poliwag", "Staryu", "Bellsprout"),
}

# HM -> (badges at which it starts to matter, why). Flash is optional and left out.
HM_NEEDS: dict[str, tuple[int, str]] = {
    "Cut": (2, "Vermilion Gym's door and several route trees"),
    "Fly": (3, "fast travel back to Centers and gyms"),
    "Surf": (4, "Fuchsia / Cinnabar and every water route"),
    "Strength": (6, "Victory Road's boulders"),
}


def place(bank: int, mid: int) -> str:
    from knowledge.navigation import MAP_NAMES
    return MAP_NAMES.get((bank, mid)) or MAP_LABELS.get((bank, mid)) or f"map {bank}/{mid}"


def where_to_find(species_id: int, limit: int = 2) -> str:
    """'Route 4 (grass L10-12), Diglett's Cave B1F (grass L15-31)' — straight from the encounter tables."""
    rows = WILD_LOCATIONS.get(species_id, [])
    rows = sorted(rows, key=lambda r: ({"grass": 0, "surf": 1, "rock smash": 2, "fish": 3}.get(r[2], 4), r[3]))
    seen, out = set(), []
    for b, i, method, lo, hi in rows:
        name = place(b, i)
        if name in seen:
            continue
        seen.add(name)
        out.append(f"{name} ({method} L{lo}" + (f"-{hi}" if hi != lo else "") + ")")
        if len(out) >= limit:
            break
    return ", ".join(out)


def _types(species_id: int) -> tuple:
    return SPECIES_DATA.get(species_id, (0, (), 0))[1]


def _attack_mult(att: str, def_types) -> float:
    m = 1.0
    for d in def_types:
        m *= get_effectiveness(att, d)
    return m


def _damaging_move_types(mon) -> set:
    from knowledge.leafgreen_data import MOVE_POWER, MOVE_TYPE, SUICIDE_MOVES
    return {MOVE_TYPE.get(m) for m in (mon.move_names or [])
            if m and m not in SUICIDE_MOVES and MOVE_POWER.get(m, 0) > 0 and MOVE_TYPE.get(m)}


def coverage(party) -> set:
    """Defender types (single types) that at least one known damaging move hits super effectively."""
    att = set().union(*(_damaging_move_types(p) for p in party)) if party else set()
    return {t for t in TYPES if any(get_effectiveness(a, t) >= 2 for a in att)}


def shared_weaknesses(party) -> list[tuple[str, int]]:
    """[(attacking type, members weak to it)] for types that are super effective against >= SHARED_WEAKNESS members."""
    c = Counter()
    for p in party:
        for t in TYPES:
            if _attack_mult(t, _types(p.species_id)) >= 2:
                c[t] += 1
    return sorted(((t, n) for t, n in c.items() if n >= SHARED_WEAKNESS), key=lambda x: -x[1])


@dataclass
class GymFit:
    leader: str
    gym_type: str
    covered: int                 # leader Pokémon the team can hit super effectively
    total: int
    safe_members: int            # members not weak to any of the leader's types
    answers: bool
    uncovered_species: list = field(default_factory=list)


def next_gym_fit(party, gyms_beaten) -> GymFit | None:
    from knowledge.leafgreen_data import GYMS
    nxt = next((g for g in GYMS if g["leader"] not in set(gyms_beaten or [])), None)
    if nxt is None or nxt["leader"] not in TRAINER_TEAMS or not party:
        return None
    foes = TRAINER_TEAMS[nxt["leader"]]
    att = set().union(*(_damaging_move_types(p) for p in party))
    covered, missed = 0, []
    for sid, _lvl, _moves in dict.fromkeys(foes):
        if any(_attack_mult(a, _types(sid)) >= 2 for a in att):
            covered += 1
        else:
            missed.append(SPECIES_NAMES.get(sid, "?"))
    leader_types = {t for sid, _l, _m in foes for t in _types(sid)}
    safe = sum(1 for p in party if not any(_attack_mult(t, _types(p.species_id)) >= 2 for t in leader_types))
    total = len(dict.fromkeys(s for s, _l, _m in foes))
    return GymFit(nxt["leader"], nxt["type"], covered, total, safe,
                  covered / max(total, 1) >= ANSWERS_FRACTION, missed)


def hm_status(party, hm: str):
    """(knower species or None, [party members that could learn it])."""
    from knowledge.tmhm import HM_MOVES, ITEM_HM01
    from knowledge.tmhm_learnsets import can_learn
    knower = next((p.species_name for p in party if hm in (p.move_names or [])), None)
    iid = ITEM_HM01 + HM_MOVES.index(hm)
    return knower, [p.species_name for p in party if can_learn(p.species_id, iid)]


def hm_candidates(hm: str, limit: int = 3) -> list[int]:
    """Wild-catchable species that can learn `hm`, strongest evolution line first, one per line."""
    from knowledge.tmhm import HM_MOVES, ITEM_HM01
    from knowledge.tmhm_learnsets import LEARNSETS
    iid = ITEM_HM01 + HM_MOVES.index(hm)
    cands = [(SPECIES_DATA[s][2], s) for s in WILD_LOCATIONS
             if s in SPECIES_DATA and LEARNSETS.get(s) is not None and LEARNSETS[s] >> (iid - 289) & 1]
    out, lines = [], set()
    for line_best, sid in sorted(cands, reverse=True):
        if (line_best, SPECIES_DATA[sid][1]) in lines:
            continue
        lines.add((line_best, SPECIES_DATA[sid][1]))
        out.append(sid)
        if len(out) >= limit:
            break
    return out


@dataclass
class Gap:
    code: str                    # "gym" | "hm"
    text: str
    species: list = field(default_factory=list)      # species ids that would fix it


def gaps(party, boxes=None, gyms_beaten=()) -> list[Gap]:
    """What the team is missing right now, most urgent first: the next gym, then the HMs the story is about to
    demand. `boxes` (PC contents) lets a hint say 'you already own one — pc_swap it in'."""
    out: list[Gap] = []
    owned = {p.species_id for p in party}
    boxed = {m["species_id"]: m for m in (boxes or [])}
    fit = next_gym_fit(party, gyms_beaten)
    if fit is not None and not fit.answers:
        wanted = [_NAME_TO_ID[n] for n in GYM_COUNTERS.get(fit.leader, ()) if n in _NAME_TO_ID]
        wanted = [s for s in wanted if s not in owned]
        in_box = [s for s in wanted if s in boxed]
        bits = [f"{fit.leader}'s gym ({TYPE_WORD.get(fit.gym_type, fit.gym_type)}): your team hits only "
                f"{fit.covered}/{fit.total} of his Pokémon super effectively"]
        if fit.safe_members < max(1, len(party) // 2):
            bits.append(f"just {fit.safe_members}/{len(party)} of you can take his types")
        if in_box:
            m = boxed[in_box[0]]
            bits.append(f"you already own a {m['species_name']} in the PC ({m['box'] + 1}:{m['slot']}) — pc_swap it in")
            out.append(Gap("gym", "; ".join(bits), in_box))
        elif wanted:
            pick = wanted[:2]
            where = "; ".join(f"{SPECIES_NAMES[s]} — {where_to_find(s)}" for s in pick if where_to_find(s))
            bits.append("catch a counter: " + where if where else "catch a type counter")
            out.append(Gap("gym", "; ".join(bits), pick))
    badges = len(set(gyms_beaten or []))
    for hm, (need_at, why) in HM_NEEDS.items():
        if badges < need_at:
            continue
        knower, capable = hm_status(party, hm)
        if knower or capable:
            continue
        cands = hm_candidates(hm)
        have_boxed = [m for sid, m in boxed.items() if sid in set(hm_candidates(hm, 40))]
        if have_boxed:
            m = have_boxed[0]
            out.append(Gap("hm", f"nobody on the team can learn {hm} ({why}) — your {m['species_name']} in the PC "
                                 f"({m['box'] + 1}:{m['slot']}) can: pc_swap it in", [m["species_id"]]))
        elif cands:
            names = "; ".join(f"{SPECIES_NAMES[s]} — {where_to_find(s, 1)}" for s in cands[:2] if where_to_find(s, 1))
            out.append(Gap("hm", f"nobody on the team can learn {hm} ({why}); catch one that can: {names}", cands[:2]))
    return out


def wanted_species(party, boxes=None, gyms_beaten=()) -> dict[int, str]:
    """{species id: short reason} for catch_policy: catching these fills a gap, whatever their BST."""
    return {s: g.text.split(":")[0] for g in gaps(party, boxes, gyms_beaten) for s in g.species}


def team_report(party, boxes=None, gyms_beaten=()) -> str:
    """The full read-only report behind the `team_report` tool."""
    if not party:
        return "No party to analyse."
    cov = coverage(party)
    lines = [f"Team ({len(party)}): " + ", ".join(f"{p.nickname or p.species_name} L{p.level}" for p in party)]
    lines.append("Hits super effectively: " + (", ".join(TYPE_WORD[t] for t in TYPES if t in cov) or "nothing yet")
                 + ("  |  NOT covered: " + ", ".join(TYPE_WORD[t] for t in TYPES if t not in cov) if len(cov) < len(TYPES) else ""))
    sw = shared_weaknesses(party)
    lines.append("Shared weaknesses: " + (", ".join(f"{TYPE_WORD[t]} ({n} members)" for t, n in sw) or "none"))
    for hm in HM_NEEDS:
        knower, capable = hm_status(party, hm)
        lines.append(f"{hm}: " + (f"{knower} knows it" if knower else
                                  (f"{', '.join(capable)} can learn it" if capable else "nobody can learn it")))
    fit = next_gym_fit(party, gyms_beaten)
    if fit:
        lines.append(f"Next: {fit.leader} ({TYPE_WORD.get(fit.gym_type, fit.gym_type)}) — hits {fit.covered}/{fit.total} of his Pokémon, "
                     f"{fit.safe_members}/{len(party)} members safe from his types"
                     + (f"; no answer for {', '.join(fit.uncovered_species)}" if fit.uncovered_species else "")
                     + (" ✔ answered" if fit.answers else " ✘ NOT answered"))
        from knowledge.gym_advice import brief
        lines.append(brief(fit.leader))
    elif len(set(gyms_beaten or [])) >= 8:
        from knowledge.gym_advice import brief
        lines.append("Elite Four, in order:")
        lines.extend("  " + brief(n) for n in ("Lorelei", "Bruno", "Agatha", "Lance", "Gary"))
    for g in gaps(party, boxes, gyms_beaten):
        lines.append(f"Gap ({g.code}): {g.text}")
    return "\n".join(lines)
