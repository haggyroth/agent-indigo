"""Battle roster + switch-in matchups (pure, no I/O).

The observation used to describe party[0] as "the lead" during a fight, so after a switch the model read a fainted
Ivysaur as the Pokémon on the field, tried to send it out again, and never saw which teammates were fainted or how
they matched up against the foe. This renders the whole party against the current foe in one short line:

    Party vs EKANS [Poison]: 1 Ivysaur FAINTED · 2 Zappy Boy(Pikachu) FAINTED · 3 Sir Wiggle(Kakuna) ACTIVE 16/25 ·
    4 Sky High(Pidgey) 7/22 — Gust ×2, takes ×1

and, when a teammate is clearly better placed than the active mon, names the switch.
"""
from __future__ import annotations

from dataclasses import dataclass

from knowledge.battle import _type_label, effectiveness_vs
from knowledge.leafgreen_data import GEN3_CATEGORY, MOVE_POWER, MOVE_TYPE, POKEMON_TYPES, STATUS_MOVES, SUICIDE_MOVES
from knowledge.move_semantics import move_score

SWITCH_HP_FLOOR = 0.4          # a teammate under this share of its HP is not offered as a switch-in
LOW_HP = 0.34                  # at or under this share of its HP the active mon gets "switch or heal" advice
KO_WATCH = 0.6                 # …and up to this share when the foe's best hit would KO it (a full-HP one-shot is not worth a line)
FINISH_FRAC = 0.25             # a foe at/below this share of its HP may be worth finishing instead of retreating
# abilities that make a whole attacking type do nothing (id -> (name, type)); ids are Gen III
ABILITY_IMMUNITY = {10: ("Volt Absorb", "ELE"), 11: ("Water Absorb", "WAT"), 18: ("Flash Fire", "FIR"), 26: ("Levitate", "GRD")}


@dataclass(frozen=True)
class Foe:
    """What is known about the opponent's active battler. Only `name` is required; the rest comes from gBattleMons[1]
    and sharpens the maths (0 / () = unknown)."""
    name: str
    level: int = 0
    hp: int = 0
    max_hp: int = 0
    moves: tuple = ()          # its move NAMES
    speed: int = 0
    attack: int = 0
    sp_attack: int = 0
    ability: int = 0

    @property
    def types(self) -> tuple:
        return POKEMON_TYPES.get((self.name or "").upper().strip(), ())

    @property
    def hp_frac(self) -> float:
        return self.hp / self.max_hp if self.max_hp else 1.0


def _foe(foe_name, foe_level=0, foe=None) -> Foe:
    return foe if foe is not None else Foe(name=foe_name or "", level=foe_level)


def types_of(mon) -> tuple:
    return POKEMON_TYPES.get((getattr(mon, "species_name", "") or "").upper().strip(), ())


def label(mon) -> str:
    """What switch_pokemon accepts and the player sees: 'Nickname(Species)' when they differ."""
    nick, sp = (mon.nickname or "").strip(), (mon.species_name or "?").strip()
    return f"{nick}({sp.title()})" if nick and nick.upper() != sp.upper() else (nick or sp.title())


def best_attack(mon, foe_types: tuple, foe_level: int = 0, foe_ability: int = 0) -> tuple[str, float]:
    """(move name, type multiplier) of `mon`'s best damaging move with PP left against `foe_types`; ('', 1.0) if none.
    A type the foe's ability absorbs (Levitate vs Ground, …) counts as ×0."""
    immune_type = ABILITY_IMMUNITY.get(foe_ability, ("", ""))[1]
    own, best, fallback = types_of(mon), ("", 1.0, 0.0), ("", 1.0, -1.0)
    for name, pp in zip(mon.move_names or [], mon.pp or []):
        if not name or pp <= 0 or name in STATUS_MOVES or name in SUICIDE_MOVES or MOVE_POWER.get(name, 0) <= 0:
            continue
        mt = MOVE_TYPE.get(name)
        if not mt:
            continue
        eff = 0.0 if mt == immune_type else (effectiveness_vs(mt, foe_types) if foe_types else 1.0)
        score = 0.0 if eff == 0 else move_score(name, own, foe_types, user_level=mon.level, foe_level=foe_level)
        if score > best[2]:
            best = (name, eff, score)
        if eff > fallback[2]:
            fallback = (name, eff, eff)
    if best[0]:
        return best[0], best[1]
    return (fallback[0], fallback[1]) if fallback[0] else ("", 1.0)      # only immune moves left: say so (×0), not "none"


def _damaging(moves) -> list:
    return [m for m in moves if m and m not in STATUS_MOVES and MOVE_POWER.get(m, 0) > 0 and MOVE_TYPE.get(m)]


def foe_pressure(foe_types: tuple, mon, foe_moves: tuple = ()) -> float:
    """How hard the foe hits `mon`: the best multiplier over its KNOWN damaging moves, or — when its moves are unknown —
    over its own types (STAB). 1.0 when nothing is known."""
    mine = types_of(mon)
    if not mine:
        return 1.0
    known = _damaging(foe_moves)
    attack_types = [MOVE_TYPE[m] for m in known] if known else list(foe_types)
    return max((effectiveness_vs(t, mine) for t in attack_types), default=1.0)


def my_speed(mon) -> int:
    """The game's computed Speed (halved while paralysed); 0 when unknown."""
    st = getattr(mon, "stats", ()) or ()
    v = st[3] if len(st) >= 6 else 0
    return v // 2 if v and "paraly" in (mon.status or "") else v


def _outspeeds(mon, foe: Foe):
    """True / False when both speeds are known and differ, else None."""
    a, b = my_speed(mon), foe.speed
    return None if not (a and b) or a == b else a > b


def foe_hit(foe: Foe, mon) -> int | None:
    """The most damage the foe's known moves can do to `mon` in one hit (max roll, no crit/weather/stat stages), by the
    Gen III formula; None when the foe's moves / stats or the mon's stats are unknown."""
    st = getattr(mon, "stats", ()) or ()
    if len(st) < 6 or not foe.level or not foe.attack or not foe.sp_attack:
        return None
    mine, best = types_of(mon), None
    for name in _damaging(foe.moves):
        mt, power = MOVE_TYPE[name], MOVE_POWER[name]
        phys = GEN3_CATEGORY.get(mt) == "Physical"
        atk, dfn = (foe.attack, st[2]) if phys else (foe.sp_attack, st[5])
        if not dfn:
            continue
        dmg = (2 * foe.level // 5 + 2) * power * atk // dfn // 50 + 2
        if mt in foe.types:
            dmg = dmg * 3 // 2
        dmg = int(dmg * (effectiveness_vs(mt, mine) if mine else 1.0))
        best = dmg if best is None else max(best, dmg)
    return best


def _fmt(x: float) -> str:
    return "×0" if x == 0 else f"×{x:g}"


def switch_options(party, active_species: int = 0) -> str:
    """'Can switch to: 3:Kakuna (16/25), 4:Pidgey (7/22)' — the living, not-already-fighting teammates (for refusals)."""
    opts = [f"{i + 1}:{label(p)} ({p.current_hp}/{p.max_hp})" for i, p in enumerate(party)
            if p.current_hp > 0 and p.species_id != active_species]
    return ("Can switch to: " + ", ".join(opts)) if opts else "Nobody else is able to fight."


def _header(foe: Foe) -> str:
    bits = "/".join(_type_label(t) for t in foe.types)
    ab = ABILITY_IMMUNITY.get(foe.ability)
    extra = f"{ab[0]}: {_type_label(ab[1])} moves do nothing" if ab else ""
    inner = "; ".join(x for x in (bits, extra) if x)
    return f"Party vs {foe.name.title()}" + (f" [{inner}]" if inner else "")


def roster(party, active_species: int, foe_name: str = "", foe_level: int = 0, foe: Foe | None = None) -> str:
    """One line: every party slot with FAINTED / ACTIVE / HP, and for each living one its best move against the foe, how
    hard the foe hits it, and (when known) who is faster. '' with fewer than two Pokémon."""
    if len(party) < 2:
        return ""
    foe = _foe(foe_name, foe_level, foe)
    bits = []
    for i, p in enumerate(party):
        tag = f"{i + 1} {label(p)}"
        if p.current_hp <= 0:
            bits.append(f"{tag} FAINTED")
            continue
        state = f"ACTIVE {p.current_hp}/{p.max_hp}" if p.species_id == active_species else f"{p.current_hp}/{p.max_hp}"
        move, mult = best_attack(p, foe.types, foe.level, foe.ability)
        detail = ""
        if foe.types and move:
            fast = _outspeeds(p, foe)
            detail = (f" — {move} {_fmt(mult)}, takes {_fmt(foe_pressure(foe.types, p, foe.moves))}"
                      + ("" if fast is None else ", outspeeds" if fast else ", outsped"))
        bits.append(f"{tag} {state}{detail}")
    return _header(foe) + " (FAINTED ones cannot be switched in): " + " · ".join(bits)


def better_matchup(party, active_species: int, foe_name: str = "", foe_level: int = 0, foe: Foe | None = None) -> str:
    """A switch suggestion, or '' — only when the active mon is badly placed (its best attack is resisted/useless, or the
    foe hits it super effectively) AND a healthy teammate hits better and takes less. Never for a marginal gain
    (a switch gives the foe a free hit)."""
    foe = _foe(foe_name, foe_level, foe)
    me_i = next((i for i, p in enumerate(party) if p.species_id == active_species and p.current_hp > 0), None)
    if not foe.types or me_i is None:
        return ""
    me = party[me_i]
    my_move, my_mult = best_attack(me, foe.types, foe.level, foe.ability)
    my_take = foe_pressure(foe.types, me, foe.moves)
    if my_mult >= 1 and my_take <= 1:
        return ""
    best = None
    for i, p in enumerate(party):
        if i == me_i or p.current_hp <= 0 or not p.max_hp or p.current_hp / p.max_hp < SWITCH_HP_FLOOR:
            continue
        move, mult = best_attack(p, foe.types, foe.level, foe.ability)
        take = foe_pressure(foe.types, p, foe.moves)
        if not move or mult < max(my_mult, 1) or take > max(my_take, 1) or (mult <= my_mult and take >= my_take):
            continue
        key = (mult, -take, bool(_outspeeds(p, foe)), -p.level)          # level only breaks a full tie, and the LOWER one wins: the same kill pays the same XP, so it levels the team evenly
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
    fast = _outspeeds(p, foe)
    return (f"Better matchup: switch_pokemon('{p.nickname or p.species_name}') — {move} {_fmt(mult)}, foe hits it {_fmt(take)}"
            f"{', and it outspeeds the foe' if fast else ''} ({'; '.join(why)}).")


def low_hp_advice(party, active_species: int, foe: Foe, heals=(), wild: bool = False) -> str:
    """'' unless the active mon is nearly dead or the foe's best hit would KO it; then the ways out: finish a nearly-dead
    foe, switch to a healthy teammate (the only thing that saves a mon the foe will KO), heal (only if it survives the
    hit), flee (wild). `heals` = [(item name, HP restored)] the bag actually holds."""
    me = next((p for p in party if p.species_id == active_species and p.current_hp > 0), None)
    if me is None or not me.max_hp:
        return ""
    dmg = foe_hit(foe, me)
    ko = dmg is not None and dmg >= me.current_hp
    frac = me.current_hp / me.max_hp
    if frac > KO_WATCH or (frac > LOW_HP and not ko):
        return ""
    fast = _outspeeds(me, foe)
    head = f"Low HP: {label(me)} {me.current_hp}/{me.max_hp}"
    if dmg is not None:
        head += f" — the foe's best hit is about {dmg}" + (", enough to KO it" if ko else "")
    ways = []
    move, mult = best_attack(me, foe.types, foe.level, foe.ability)
    if foe.max_hp and foe.hp_frac <= FINISH_FRAC and move and mult > 0 and (fast or not ko):
        ways.append(f"the foe is nearly down ({foe.hp}/{foe.max_hp}): use_move('{move}') may finish it first")
    cands = []
    for p in party:
        if p.species_id == active_species or p.current_hp <= 0 or not p.max_hp or p.current_hp / p.max_hp < SWITCH_HP_FLOOR:
            continue
        hit = foe_hit(foe, p)
        cands.append((hit is not None and hit >= p.current_hp, foe_pressure(foe.types, p, foe.moves), -p.current_hp, p))
    if cands:
        _dies, take, _hp, p = min(cands, key=lambda c: c[:3])
        ways.append(f"switch_pokemon('{p.nickname or p.species_name}') (foe hits it {_fmt(take)}; it has {p.current_hp}/{p.max_hp})"
                    + (" — the only way to keep this one alive" if ko else ""))
    usable = [(n, a) for n, a in sorted(heals, key=lambda h: h[1]) if not ko or me.current_hp + a > dmg]
    if usable:
        n, a = usable[0]
        ways.append(f"use_item('{n}') (+{a if a < 999 else 'full'} HP" + (", survives the hit" if ko else "") + ")")
    elif heals and ko:
        ways.append("healing items would not survive that hit")
    if wild:
        ways.append("flee_battle()")
    return head + ". " + ("Options: " + "; ".join(ways) + "." if ways else "No safe option — attack.")
