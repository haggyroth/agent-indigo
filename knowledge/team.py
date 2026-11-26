"""Team composition (pure): what the party can hit, what it is weak to, which HMs it can carry, whether it answers the
next gym — and what it lacks, stated as a NEED, never as a species to go and get: which Pokémon to catch, bring or box is the
model's decision, not a table's (an earlier version named a counter per gym and where to find it).

The questions answered: coverage from the moves actually known, shared weaknesses, HM carriers against what the story is about
to demand, and a fit check against the next Gym Leader's real party (generated from the decomp).
"""
from collections import Counter
from dataclasses import dataclass, field

from game.constants import SPECIES_NAMES
from knowledge.gym_teams import TRAINER_TEAMS
from knowledge.species_data import SPECIES_DATA
from knowledge.type_chart import get_effectiveness

TYPES = ("NOR", "FIR", "WAT", "ELE", "GRS", "ICE", "FIG", "POI", "GRD", "FLY", "PSY", "BUG", "ROC", "GHO", "DRG", "DRK", "STL")
TYPE_WORD = {"NOR": "Normal", "FIR": "Fire", "WAT": "Water", "ELE": "Electric", "GRS": "Grass", "ICE": "Ice",
             "FIG": "Fighting", "POI": "Poison", "GRD": "Ground", "FLY": "Flying", "PSY": "Psychic", "BUG": "Bug",
             "ROC": "Rock", "GHO": "Ghost", "DRG": "Dragon", "DRK": "Dark", "STL": "Steel"}
SHARED_WEAKNESS = 3         # this many members weak to one type = a shared weakness
ANSWERS_FRACTION = 0.6      # the team "answers" a leader if it can hit this share of his Pokémon super effectively

# HM -> (badges at which it starts to matter, why). Flash is optional and left out.
HM_NEEDS: dict[str, tuple[int, str]] = {
    "Cut": (2, "Vermilion Gym's door and several route trees"),
    "Fly": (3, "fast travel back to Centers and gyms"),
    "Surf": (4, "Cinnabar and every water route — Fuchsia itself does NOT need it: walk there by land (Routes 12-15) and the HM comes from its Safari Zone"),
    "Strength": (6, "Victory Road's boulders"),
}


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
    return trainer_fit(party, nxt["leader"], nxt["type"])


LEAGUE_FOES = (("Lorelei", "Ice"), ("Bruno", "Fighting"), ("Agatha", "Ghost"), ("Lance", "Dragon"), ("Gary (Squirtle)", "mixed"))      # the Champion's shared core: the Squirtle table


def league_fits(party) -> list:
    """GymFit for each Elite Four trainer and the Champion (the same numbers the gym report gives): who the party answers, who it does not."""
    return [f for f in (trainer_fit(party, name, kind) for name, kind in LEAGUE_FOES) if f is not None]


def trainer_fit(party, leader: str, gym_type: str) -> GymFit | None:
    if leader not in TRAINER_TEAMS or not party:
        return None
    foes = TRAINER_TEAMS[leader]
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
    return GymFit(leader.split(" (")[0].replace("Gary", "the Champion"), gym_type, covered, total, safe,
                  covered / max(total, 1) >= ANSWERS_FRACTION, missed)


def hm_status(party, hm: str):
    """(knower species or None, [party members that could learn it])."""
    from knowledge.tmhm import HM_MOVES, ITEM_HM01
    from knowledge.tmhm_learnsets import can_learn
    knower = next((p.species_name for p in party if hm in (p.move_names or [])), None)
    iid = ITEM_HM01 + HM_MOVES.index(hm)
    return knower, [p.species_name for p in party if can_learn(p.species_id, iid)]


@dataclass
class Gap:
    code: str                    # "gym" | "hm"
    text: str


def gaps(party, boxes=None, gyms_beaten=()) -> list[Gap]:
    """What the team is missing right now, most urgent first: the next gym, then the HMs the story is about to demand. It states the NEED (types the leader is
    weak to are in the gym brief; which HM nobody can learn) and what the model already OWNS that meets it — never which species to go and get: that is the model's call.
    `boxes` (PC contents) lets a hint name the stored Pokémon that can already do it."""
    out: list[Gap] = []
    boxed = {m["species_id"]: m for m in (boxes or [])}
    fit = next_gym_fit(party, gyms_beaten)
    if fit is not None and not fit.answers:
        bits = [f"{fit.leader}'s gym ({TYPE_WORD.get(fit.gym_type, fit.gym_type)}): your team hits only "
                f"{fit.covered}/{fit.total} of his Pokémon super effectively"]
        if fit.safe_members < max(1, len(party) // 2):
            bits.append(f"just {fit.safe_members}/{len(party)} of you can take his types")
        bits.append("the brief below lists the types he is weak to; pc('list', detail=true) shows what you have stored — who you bring is your decision")
        out.append(Gap("gym", "; ".join(bits)))
    badges = len(set(gyms_beaten or []))
    for hm, (need_at, why) in HM_NEEDS.items():
        if badges < need_at:
            continue
        knower, capable = hm_status(party, hm)
        if knower or capable:
            continue
        have_boxed = [m for sid, m in boxed.items() if _can_learn_hm(sid, hm)]
        if have_boxed:
            names = ", ".join(f"{m['species_name']} ({m['box'] + 1}:{m['slot']})" for m in have_boxed[:4])
            out.append(Gap("hm", f"nobody on the team can learn {hm} ({why}); in the PC that can: {names} — pc('swap') brings one into the team"))
        else:
            out.append(Gap("hm", f"nobody on the team can learn {hm} ({why}); a Pokémon that can must join the team (inspect_pokemon / pc('list', detail=true) show who can learn what)"))
    return out


def _can_learn_hm(species_id: int, hm: str) -> bool:
    from knowledge.tmhm import HM_MOVES, ITEM_HM01
    from knowledge.tmhm_learnsets import LEARNSETS
    iid = ITEM_HM01 + HM_MOVES.index(hm)
    return bool(LEARNSETS.get(species_id) is not None and LEARNSETS[species_id] >> (iid - 289) & 1)


def team_report(party, boxes=None, gyms_beaten=(), money_note: str = "") -> str:
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
        lines.append("Elite Four, in order (and how this team answers each):")
        fits = {f.leader: f for f in league_fits(party)}
        for n, label in (("Lorelei", "Lorelei"), ("Bruno", "Bruno"), ("Agatha", "Agatha"), ("Lance", "Lance"), ("Gary", "the Champion")):
            f = fits.get(label)
            lines.append("  " + brief(n))
            if f:
                lines.append(f"    → your team hits {f.covered}/{f.total} of {label}'s Pokémon, {f.safe_members}/{len(party)} members are safe from their types"
                             + (f"; no answer for {', '.join(f.uncovered_species)}" if f.uncovered_species else "") + (" ✔" if f.answers else " ✘ NOT answered"))
    for g in gaps(party, boxes, gyms_beaten):
        lines.append(f"Gap ({g.code}): {g.text}")
    if money_note:
        lines.append(money_note)
    return "\n".join(lines)
