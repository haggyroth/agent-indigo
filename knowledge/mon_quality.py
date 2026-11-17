"""How good is THIS Pokémon, not just this species (pure): IVs, EVs, nature, role-weighted into one comparable score.

Two Pidgeys can differ by 30% in stat potential; the catch policy only knew species. Everything here is derived from data
the game already stores per Pokémon (decoded in game.memory_reader) plus the generated base stats:

  * `projected_stats`  — the game's own formula; the live test checks it against the stats stored in the party struct;
  * `role_weights`     — what the species is FOR (physical / special / mixed attacker), from its base stats and the
                         damaging moves it knows, so a special attacker's Attack IV and an Attack-lowering nature
                         don't count against it;
  * `assess`           — role-weighted IV%, nature fit and one score in [0, 1] with a plain-words grade;
  * `upgrade_swaps`    — "the Pidgey in your PC is clearly better than the one in your party".
"""
from dataclasses import dataclass

from knowledge.base_stats import BASE_STATS

STAT_NAMES = ("HP", "Atk", "Def", "Spe", "SpA", "SpD")
NATURES = ("Hardy", "Lonely", "Brave", "Adamant", "Naughty", "Bold", "Docile", "Relaxed", "Impish", "Lax", "Timid",
           "Hasty", "Serious", "Jolly", "Naive", "Modest", "Mild", "Quiet", "Bashful", "Rash", "Calm", "Gentle", "Sassy",
           "Careful", "Quirky")
# Hidden Power's type order in Gen III (decomp: ((type - 1) of FIGHTING..DARK without NORMAL / MYSTERY)).
HP_TYPES = ("FIG", "FLY", "POI", "GRD", "ROC", "BUG", "GHO", "STL", "FIR", "WAT", "GRS", "ELE", "PSY", "ICE", "DRG", "DRK")

IV_WEIGHT, NATURE_WEIGHT = 0.8, 0.2
GRADES = ((0.80, "excellent"), (0.68, "good"), (0.52, "average"), (0.0, "below average"))
UPGRADE_MARGIN = 0.12            # a boxed specimen must beat the party one by this much score to be worth a swap
LEVEL_COST_NOTE = 4              # …and we mention it when the swap costs more levels than this


def nature_name(personality: int) -> str:
    return NATURES[personality % 25]


def nature_effect(personality: int) -> tuple[int | None, int | None]:
    """(boosted stat index, lowered stat index) in HP, Atk, Def, Spe, SpA, SpD order; (None, None) for a neutral nature.
    Gen III: nature = PID % 25, boost = nature // 5, reduce = nature % 5 over (Atk, Def, Spe, SpA, SpD)."""
    n = personality % 25
    up, down = n // 5, n % 5
    return (None, None) if up == down else (up + 1, down + 1)


def calc_stat(base: int, iv: int, ev: int, level: int, idx: int, personality: int = 0) -> int:
    """One stat by the game's formula (pokefirered CalculateMonStats), integer arithmetic included."""
    if idx == 0:
        return (2 * base + iv + ev // 4) * level // 100 + level + 10
    n = (2 * base + iv + ev // 4) * level // 100 + 5
    up, down = nature_effect(personality)
    if idx == up:
        n = n * 110 // 100
    elif idx == down:
        n = n * 90 // 100
    return n


def projected_stats(species_id: int, ivs, evs, personality: int, level: int) -> tuple:
    """(HP, Atk, Def, Spe, SpA, SpD) at `level`. () for a species without base stats."""
    row = BASE_STATS.get(species_id)
    if row is None or len(ivs) != 6:
        return ()
    evs = evs if len(evs) == 6 else (0,) * 6
    return tuple(calc_stat(row[0][i], ivs[i], evs[i], level, i, personality) for i in range(6))


def hidden_power(ivs) -> tuple[str, int] | None:
    """(type code, power 30-70) from the IVs' low bits (Gen III). None when the IVs are unknown."""
    if len(ivs) != 6:
        return None
    t = sum((ivs[i] & 1) << i for i in range(6))
    p = sum(((ivs[i] >> 1) & 1) << i for i in range(6))
    return HP_TYPES[t * 15 // 63], p * 40 // 63 + 30


def _field(m, key, default=None):
    return m.get(key, default) if isinstance(m, dict) else getattr(m, key, default)


def role_weights(species_id: int, move_names=()) -> tuple:
    """Per-stat importance (HP, Atk, Def, Spe, SpA, SpD) for what this Pokémon is used for."""
    from knowledge.leafgreen_data import GEN3_CATEGORY, MOVE_POWER, MOVE_TYPE
    base = BASE_STATS.get(species_id, ((0,) * 6, (0,) * 6))[0]
    phys = sum(1 for m in move_names if m and MOVE_POWER.get(m, 0) > 0 and GEN3_CATEGORY.get(MOVE_TYPE.get(m)) == "Physical")
    spec = sum(1 for m in move_names if m and MOVE_POWER.get(m, 0) > 0 and GEN3_CATEGORY.get(MOVE_TYPE.get(m)) == "Special")
    p, s = base[1] + 20 * phys, base[4] + 20 * spec
    if abs(p - s) < 15:
        return (1.5, 2.0, 1.0, 2.0, 2.0, 1.0)            # mixed
    return (1.5, 3.0, 1.0, 2.0, 0.0, 1.0) if p > s else (1.5, 0.0, 1.0, 2.0, 3.0, 1.0)


@dataclass(frozen=True)
class Quality:
    score: float                 # 0..1
    grade: str
    iv_pct: float                # plain IV total / 186
    weighted_iv: float           # role-weighted IV share, 0..1
    nature: str
    nature_fit: float            # -1 (works against its role) .. +1 (boosts what it needs)
    role: str
    ivs: tuple
    evs: tuple

    def summary(self) -> str:
        iv = " ".join(f"{n}{v}" for n, v in zip(STAT_NAMES, self.ivs))
        return (f"{self.grade} ({self.score:.0%}) — IV {self.iv_pct:.0%} [{iv}], {self.nature} "
                f"({'helps' if self.nature_fit > 0.15 else 'hurts' if self.nature_fit < -0.15 else 'neutral for'} its {self.role} role)")


def assess(m) -> Quality | None:
    """Quality of a Pokémon (a PokemonStatus or a read_boxes() dict). None when its IVs couldn't be read."""
    ivs = tuple(_field(m, "ivs", ()) or ())
    if len(ivs) != 6:
        return None
    sid = _field(m, "species_id", 0)
    pid = _field(m, "personality", 0) or 0
    w = role_weights(sid, _field(m, "move_names", ()) or ())
    weighted = sum(wi * iv / 31 for wi, iv in zip(w, ivs)) / sum(w)
    up, down = nature_effect(pid)
    fit = 0.0 if up is None else (w[up] - w[down]) / max(w)
    score = IV_WEIGHT * weighted + NATURE_WEIGHT * (0.5 + 0.5 * fit)
    grade = next(name for floor, name in GRADES if score >= floor)
    role = "physical" if w[1] > w[4] else "special" if w[4] > w[1] else "mixed"
    return Quality(score, grade, sum(ivs) / 186, weighted, nature_name(pid), fit, role, ivs,
                   tuple(_field(m, "evs", ()) or ()))


def describe(m) -> str:
    """The 'inspect_pokemon' text for one Pokémon: stats, IVs, EVs, nature, Hidden Power, grade."""
    q = assess(m)
    name = _field(m, "nickname", "") or _field(m, "species_name", "?")
    lvl = _field(m, "level", 0)
    head = f"{name} ({_field(m, 'species_name', '?')} L{lvl})"
    if q is None:
        return head + ": IVs couldn't be read."
    lines = [f"{head}: {q.summary()}"]
    stats = tuple(_field(m, "stats", ()) or ()) or projected_stats(_field(m, "species_id", 0), q.ivs, q.evs,
                                                                   _field(m, "personality", 0) or 0, lvl)
    if stats:
        lines.append("Stats: " + ", ".join(f"{n} {v}" for n, v in zip(STAT_NAMES, stats)))
    if q.evs:
        spread = ", ".join(f"{n} {v}" for n, v in zip(STAT_NAMES, q.evs) if v) or "none"
        lines.append(f"EVs ({sum(q.evs)}/510): {spread}")
    hp = hidden_power(q.ivs)
    if hp:
        from knowledge.battle import _type_label
        lines.append(f"Hidden Power would be {_type_label(hp[0])} {hp[1]}.")
    return "\n".join(lines)


def upgrade_swaps(party, boxes, margin: float = UPGRADE_MARGIN, limit: int = 2) -> list[str]:
    """Boxed Pokémon of a species you already field that are clearly better individuals. Lines name the exact swap."""
    out = []
    for p in party:
        qp = assess(p)
        if qp is None:
            continue
        best = None
        for b in boxes or []:
            if b["species_id"] != p.species_id:
                continue
            qb = assess(b)
            if qb is not None and qb.score - qp.score >= margin and (best is None or qb.score > best[0].score):
                best = (qb, b)
        if best:
            qb, b = best
            cost = p.level - b["level"]
            note = f"; it is {cost} levels lower, so expect to retrain it" if cost > LEVEL_COST_NOTE else ""
            out.append(f"{b['nickname'] or b['species_name']} in the PC ({b['box'] + 1}:{b['slot']}) is a {qb.grade} "
                       f"{p.species_name} ({qb.score:.0%}) vs your {qp.grade} one ({qp.score:.0%}) — "
                       f"pc_swap('{p.nickname or p.species_name}', '{b['box'] + 1}:{b['slot']}'){note}")
    return out[:limit]


def compare_text(new, party) -> str:
    """After a catch: how the new Pokémon stacks up against the party member of the same species (or the team)."""
    qn = assess(new)
    if qn is None:
        return ""
    same = [p for p in party if p.species_id == _field(new, "species_id", -1) and _field(p, "personality", 0) != _field(new, "personality", 1)]
    if same:
        qo = assess(same[0])
        if qo is not None:
            diff = qn.score - qo.score
            verdict = ("a clear upgrade" if diff >= UPGRADE_MARGIN else "a clear downgrade" if diff <= -UPGRADE_MARGIN
                       else "about the same")
            return f"vs your {same[0].nickname or same[0].species_name} ({qo.score:.0%}): {verdict}"
    scores = [q.score for q in (assess(p) for p in party) if q is not None]
    if scores:
        mean = sum(scores) / len(scores)
        return f"team average {mean:.0%}: " + ("above it" if qn.score > mean + 0.05 else "below it" if qn.score < mean - 0.05 else "in line")
    return ""
