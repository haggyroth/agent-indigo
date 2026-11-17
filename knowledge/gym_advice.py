"""Gym Leader / Elite Four / Champion briefs (pure), derived from the generated decomp parties — never typed by hand (#211).

The hand-written `key_threat` / `counter` strings drifted from the game (Elite Four levels were off by 2-6) and nothing read
them. Everything here is computed from `knowledge.gym_teams.TRAINER_TEAMS` (species, level, moves per opponent), the type
chart and the move tables, so a number in advice can only be the decomp's number.
"""
from game.constants import SPECIES_NAMES
from knowledge.gym_teams import TRAINER_TEAMS
from knowledge.team import TYPE_WORD, TYPES, _attack_mult, _types

# Moves worth a warning on their own (the model should plan around them, not discover them mid-battle).
WATCH_MOVES = {
    "Sleep Powder": "puts you to sleep", "Hypnosis": "puts you to sleep", "Lovely Kiss": "puts you to sleep",
    "Sing": "puts you to sleep", "Spore": "puts you to sleep", "Toxic": "badly poisons", "Thunder Wave": "paralyzes",
    "Self-Destruct": "self-destructs", "Explosion": "self-destructs", "Recover": "heals itself",
    "Calm Mind": "boosts Sp. Atk", "Future Sight": "delayed hit", "Extreme Speed": "priority hit",
    "Smokescreen": "lowers accuracy", "Screech": "lowers Defense",
}
WEAK_SHARE = 0.5          # a type is worth naming when it is super effective against this share of the party


def _team(name: str) -> list:
    if name == "Gary":                                   # the Champion's shared core; the last Pokémon depends on your starter
        core = TRAINER_TEAMS["Gary (Squirtle)"][:5]
        return core
    return TRAINER_TEAMS.get(name, [])


def ace(name: str) -> tuple[str, int] | None:
    """(species name, level) of the leader's highest-level Pokémon."""
    team = _team(name)
    if not team:
        return None
    sid, lvl, _m = max(team, key=lambda r: r[1])
    return SPECIES_NAMES.get(sid, "?"), lvl


def ace_levels() -> dict[str, int]:
    return {n: max(l for _s, l, _m in t) for n, t in TRAINER_TEAMS.items() if not n.startswith("Gary")}


def types_used(name: str) -> list[str]:
    """Types of the damaging moves the team actually knows, most common first."""
    from knowledge.leafgreen_data import MOVE_POWER, MOVE_TYPE
    c: dict = {}
    for _s, _l, moves in _team(name):
        for m in moves:
            if MOVE_POWER.get(m, 0) > 0 and MOVE_TYPE.get(m):
                c[MOVE_TYPE[m]] = c.get(MOVE_TYPE[m], 0) + 1
    return sorted(c, key=lambda t: -c[t])


def weak_to(name: str) -> list[tuple[str, int, int]]:
    """[(attacking type, members hit super effectively, team size)] for the types that matter, best first."""
    team = _team(name)
    if not team:
        return []
    out = []
    for t in TYPES:
        n = sum(1 for sid, _l, _m in team if _attack_mult(t, _types(sid)) >= 2)
        if n / len(team) >= WEAK_SHARE:
            out.append((t, n, len(team)))
    return sorted(out, key=lambda r: -r[1])


def watch_list(name: str) -> list[str]:
    seen, out = set(), []
    for sid, _l, moves in _team(name):
        for m in moves:
            if m in WATCH_MOVES and m not in seen:
                seen.add(m)
                out.append(f"{m} ({SPECIES_NAMES.get(sid, '?')}: {WATCH_MOVES[m]})")
    return out


def brief(name: str) -> str:
    """'Koga — Koffing L37, Muk L39, … | their moves: Poison, Normal | weak to: Ground (4/4) | watch: …'"""
    team = _team(name)
    if not team:
        return ""
    mons = ", ".join(f"{SPECIES_NAMES.get(s, '?')} L{l}" for s, l, _m in team)
    if name == "Gary":
        mons += ", + the starter evolution that beats yours (Blastoise/Venusaur/Charizard L63)"
    parts = [f"{name}: {mons}"]
    used = types_used(name)
    if used:
        parts.append("their attacks are " + "/".join(TYPE_WORD.get(t, t) for t in used[:4]))
    weak = weak_to(name)
    if weak:
        parts.append("hit them with " + ", ".join(f"{TYPE_WORD[t]} ({n}/{m})" for t, n, m in weak[:3]))
    watch = watch_list(name)
    if watch:
        parts.append("watch for " + "; ".join(watch[:4]))
    return " | ".join(parts)
