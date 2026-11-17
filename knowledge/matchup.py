"""Battle roster + switch-in matchups (pure, no I/O).

The observation used to describe party[0] as "the lead" during a fight, so after a switch the model read a fainted
Ivysaur as the Pokémon on the field, tried to send it out again, and never saw which teammates were fainted or how
they matched up against the foe. This renders the whole party against the current foe in one short line:

    Party vs EKANS [Poison]: 1 Ivysaur FAINTED · 2 Zappy Boy(Pikachu) FAINTED · 3 Sir Wiggle(Kakuna) ACTIVE 16/25 ·
    4 Sky High(Pidgey) 7/22 — Gust ×2, takes ×1

and, when a teammate is clearly better placed than the active mon, names the switch.
"""
from __future__ import annotations

from knowledge.battle import _type_label, effectiveness_vs
from knowledge.leafgreen_data import MOVE_POWER, MOVE_TYPE, POKEMON_TYPES, STATUS_MOVES, SUICIDE_MOVES
from knowledge.move_semantics import move_score

SWITCH_HP_FLOOR = 0.4          # a teammate under this share of its HP is not offered as a switch-in


def types_of(mon) -> tuple:
    return POKEMON_TYPES.get((getattr(mon, "species_name", "") or "").upper().strip(), ())


def label(mon) -> str:
    """What switch_pokemon accepts and the player sees: 'Nickname(Species)' when they differ."""
    nick, sp = (mon.nickname or "").strip(), (mon.species_name or "?").strip()
    return f"{nick}({sp.title()})" if nick and nick.upper() != sp.upper() else (nick or sp.title())


def best_attack(mon, foe_types: tuple, foe_level: int = 0) -> tuple[str, float]:
    """(move name, type multiplier) of `mon`'s best damaging move with PP left against `foe_types`; ('', 1.0) if none."""
    own, best, fallback = types_of(mon), ("", 1.0, 0.0), ("", 1.0, -1.0)
    for name, pp in zip(mon.move_names or [], mon.pp or []):
        if not name or pp <= 0 or name in STATUS_MOVES or name in SUICIDE_MOVES or MOVE_POWER.get(name, 0) <= 0:
            continue
        mt = MOVE_TYPE.get(name)
        if not mt:
            continue
        eff = effectiveness_vs(mt, foe_types) if foe_types else 1.0
        score = move_score(name, own, foe_types, user_level=mon.level, foe_level=foe_level)
        if score > best[2]:
            best = (name, eff, score)
        if eff > fallback[2]:
            fallback = (name, eff, eff)
    if best[0]:
        return best[0], best[1]
    return (fallback[0], fallback[1]) if fallback[0] else ("", 1.0)      # only immune moves left: say so (×0), not "none"


def foe_pressure(foe_types: tuple, mon) -> float:
    """How hard the foe's own-type (STAB) moves hit `mon`: the best multiplier over the foe's types (1.0 when unknown)."""
    mine = types_of(mon)
    if not foe_types or not mine:
        return 1.0
    return max(effectiveness_vs(ft, mine) for ft in foe_types)


def _fmt(x: float) -> str:
    return "×0" if x == 0 else f"×{x:g}"


def switch_options(party, active_species: int = 0) -> str:
    """'Can switch to: 3:Kakuna (16/25), 4:Pidgey (7/22)' — the living, not-already-fighting teammates (for refusals)."""
    opts = [f"{i + 1}:{label(p)} ({p.current_hp}/{p.max_hp})" for i, p in enumerate(party)
            if p.current_hp > 0 and p.species_id != active_species]
    return ("Can switch to: " + ", ".join(opts)) if opts else "Nobody else is able to fight."


def roster(party, active_species: int, foe_name: str, foe_level: int = 0) -> str:
    """One line: every party slot with FAINTED / ACTIVE / HP, and for healthy teammates their best move and the foe's
    STAB pressure on them. '' with fewer than two Pokémon."""
    if len(party) < 2:
        return ""
    foe_types = POKEMON_TYPES.get((foe_name or "").upper().strip(), ())
    bits = []
    for i, p in enumerate(party):
        tag = f"{i + 1} {label(p)}"
        if p.current_hp <= 0:
            bits.append(f"{tag} FAINTED")
        elif p.species_id == active_species:
            bits.append(f"{tag} ACTIVE {p.current_hp}/{p.max_hp}")
        else:
            move, mult = best_attack(p, foe_types, foe_level)
            detail = f" — {move} {_fmt(mult)}, takes {_fmt(foe_pressure(foe_types, p))}" if foe_types and move else ""
            bits.append(f"{tag} {p.current_hp}/{p.max_hp}{detail}")
    head = f"Party vs {foe_name.title()}" + (f" [{'/'.join(_type_label(t) for t in foe_types)}]" if foe_types else "")
    return head + " (FAINTED ones cannot be switched in): " + " · ".join(bits)


def better_matchup(party, active_species: int, foe_name: str, foe_level: int = 0) -> str:
    """A switch suggestion, or '' — only when the active mon is badly placed (its best attack is resisted/useless, or the
    foe's STAB is super effective on it) AND a healthy teammate hits better and takes less. Never for a marginal gain
    (a switch gives the foe a free hit)."""
    foe_types = POKEMON_TYPES.get((foe_name or "").upper().strip(), ())
    me_i = next((i for i, p in enumerate(party) if p.species_id == active_species and p.current_hp > 0), None)
    if not foe_types or me_i is None:
        return ""
    me = party[me_i]
    my_move, my_mult = best_attack(me, foe_types, foe_level)
    my_take = foe_pressure(foe_types, me)
    if my_mult >= 1 and my_take <= 1:
        return ""
    best = None
    for i, p in enumerate(party):
        if i == me_i or p.current_hp <= 0 or not p.max_hp or p.current_hp / p.max_hp < SWITCH_HP_FLOOR:
            continue
        move, mult = best_attack(p, foe_types, foe_level)
        take = foe_pressure(foe_types, p)
        if not move or mult < max(my_mult, 1) or take > max(my_take, 1) or (mult <= my_mult and take >= my_take):
            continue
        key = (mult, -take, p.level)
        if best is None or key > best[0]:
            best = (key, p, move, mult, take)
    if best is None:
        return ""
    _k, p, move, mult, take = best
    why = []
    if my_mult < 1:
        why.append(f"{label(me)}'s best attack ({my_move or 'none'}) is {_fmt(my_mult)} here")
    if my_take > 1:
        why.append(f"the foe hits {label(me)} for {_fmt(my_take)}")
    return (f"Better matchup: switch_pokemon('{p.nickname or p.species_name}') — {move} {_fmt(mult)}, foe hits it {_fmt(take)}"
            f" ({'; '.join(why)}).")
