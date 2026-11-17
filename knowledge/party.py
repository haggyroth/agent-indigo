"""Team-balance rules (pure): nobody trails the top level by more than BALANCE_GAP levels."""

BALANCE_GAP = 7         # max levels between the highest and the lowest party member (a gym team of L40/L7s loses)


def min_level_for(top: int) -> int:
    """Lowest acceptable level when the top party level is `top` (top - BALANCE_GAP)."""
    return max(1, top - BALANCE_GAP)


def grind_floor(top: int, gym_target: int | None = None, balance: bool = True) -> int:
    """The level every Pokémon should reach in ONE grind session, fixed when the session starts. It must not
    follow the ace's level (a moving target is how a 300-minute grind never finished): top − BALANCE_GAP,
    capped at the next gym's recommended level when that is lower (nobody needs to be stronger than the gym
    asks). In target-level mode `top` is the level being ground to."""
    floor = min_level_for(top)
    if balance and gym_target:
        floor = min(floor, max(1, gym_target))
    return floor


def ace_index(party) -> int | None:
    """Index of the highest-level living member (the 'ace': first on ties), or None."""
    alive = [(p.level, -i) for i, p in enumerate(party) if p.current_hp > 0]
    return -max(alive)[1] if alive else None


def ace_runaway(start_levels: dict, party, battles: int, min_battles: int = 20, ace_gain: int = 3) -> str:
    """'' normally; else why a balance session should stop: after `min_battles` fights the ace has gained
    `ace_gain`+ levels while the weakest member that started under the floor has gained at most one — the
    grind is feeding the ace, not the team. `start_levels` is {species_id: level at session start}."""
    if battles < min_battles or len(party) < 2:
        return ""
    ace = ace_index(party)
    if ace is None:
        return ""
    gains = {p.species_id: p.level - start_levels.get(p.species_id, p.level) for p in party}
    low_id = min(start_levels, key=lambda sid: start_levels[sid], default=None)
    a_gain = gains.get(party[ace].species_id, 0)
    if low_id is not None and low_id != party[ace].species_id and a_gain >= ace_gain and gains.get(low_id, 0) <= 1:
        return (f"after {battles} battles the ace gained {a_gain} levels but the lowest member only "
                f"{gains.get(low_id, 0)} — the fights are feeding the ace")
    return ""


def lagging_mons(party, floor: int | None = None) -> list:
    """[(index, mon)] of members below the balance floor, lowest level first. FAINTED members count: a team
    whose trainees are all knocked out is not balanced, it is just waiting for a heal (a fainted-excluded
    check used to report "Party balanced" for L7/L6/L5 beside an L38 ace). A party of fewer than two has
    nothing to balance."""
    if len(party) < 2:
        return []
    need = floor if floor is not None else min_level_for(max(p.level for p in party))
    lag = [(i, p) for i, p in enumerate(party) if p.level < need]
    return sorted(lag, key=lambda ip: (ip[1].level, ip[0]))


def pick_finisher(party, trainee_idx: int, foe_level: int = 0, bench=()):
    """Index of the teammate who finishes a training fight once the trainee has been tagged out: healthy
    (>= 40% HP), not the trainee, and CAPABLE (level >= the foe's). Among the capable ones the LOWEST level is
    chosen, so the finishing XP rotates through the whole team instead of always feeding the ace; with no
    capable teammate it is simply the strongest healthy one. None when nobody is fit."""
    fit = [(i, q) for i, q in enumerate(party)
           if i != trainee_idx and q.max_hp and q.current_hp > 0 and q.current_hp / q.max_hp >= 0.4]
    if not fit:
        return None
    benched = set(bench)
    if benched:            # keep the ace out of balance-mode fights unless nobody else is fit to finish
        rest = [(i, q) for i, q in fit if i not in benched]
        if rest:
            fit = rest
    capable = [(i, q) for i, q in fit if q.level >= foe_level]
    if capable:
        return min(capable, key=lambda iq: (iq[1].level, iq[0]))[0]
    return max(fit, key=lambda iq: (iq[1].level, -iq[0]))[0]


# ── PP awareness ────────────────────────────────────────────────────────────────
def attack_pp(mon) -> int:
    """Total PP left across `mon`'s DAMAGING moves (a status move like Growl/Harden never counts: a
    mon that only has those cannot make progress in a fight, however much PP they have)."""
    from knowledge.leafgreen_data import MOVE_POWER
    names = getattr(mon, "move_names", None) or []
    pps = getattr(mon, "pp", None) or []
    return sum(p for n, p in zip(names, pps) if n and p > 0 and MOVE_POWER.get(n, 0) > 0)


def can_attack(mon) -> bool:
    """True if `mon` has at least one damaging move with PP left."""
    return attack_pp(mon) > 0


def healthy_enough(mon, floor: float = 0.35) -> bool:
    return bool(mon.max_hp) and mon.current_hp > 0 and mon.current_hp / mon.max_hp >= floor


def party_needs_restock(party, hp_floor: float = 0.35, pp_floor: int = 2) -> str:
    """'' if the team can keep fighting, else why not. The CLOSER is the strongest healthy mon that
    can still attack; it must have more than `pp_floor` attack PP, or the next wild fight can end
    in a spam-the-status-move stalemate."""
    alive = [p for p in party if healthy_enough(p, hp_floor)]
    if not alive:
        return "everyone is hurt"
    strikers = [p for p in alive if can_attack(p)]
    if not strikers:
        return "no healthy Pokémon has attacking PP left"
    best = max(strikers, key=lambda p: (p.level, attack_pp(p)))
    if attack_pp(best) <= pp_floor:
        return f"{best.species_name or 'your best attacker'} is nearly out of attack PP"
    return ""


LOW_HP_SWITCH = 0.35        # an active Pokémon at or below this share of its HP is about to faint


def low_hp_switch_hint(party, active_idx: int, cur: int, mx: int, foe_level: int = 0) -> str:
    """'' normally; when the ACTIVE Pokémon is nearly out and a fit teammate exists, a warning naming the switch. A weak trainee
    (a fresh L3 catch) loses these exchanges every time and a model that keeps attacking just feeds the foe a free faint."""
    if not mx or cur <= 0 or cur / mx > LOW_HP_SWITCH or not 0 <= active_idx < len(party):
        return ""
    pick = pick_finisher(party, active_idx, foe_level)
    if pick is None:
        return ""
    me, mate = party[active_idx], party[pick]
    return (f"⚠ {me.nickname or me.species_name} is at {cur}/{mx} HP and the next hit may faint it (no XP and a Center trip): "
            f"switch_pokemon('{mate.nickname or mate.species_name}') now, or use a Potion.")
