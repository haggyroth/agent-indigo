"""One-shot encounters (pure; no I/O): the Snorlaxes, the three legendary birds and Mewtwo appear ONCE — knock one out (or let it flee) and it is gone for good.

A normal wild fight is won by attacking; these must be CAUGHT, so the protocol is: save the game state when the battle starts, weaken it WITHOUT fainting (False Swipe, or the lowest-power
damaging move, stopping while the bar is still above red), put it to sleep or paralyse it (the best catch bonuses), throw an Ultra Ball (or the Master Ball for a legend — it never
fails), and reload the saved state when it faints or flees, then try again more gently. `protocol` turns the live numbers into that advice; the observation shows it for these species."""
SNORLAX, ARTICUNO, ZAPDOS, MOLTRES, MEWTWO = 143, 144, 145, 146, 150
ONE_SHOT = {SNORLAX: "Snorlax", ARTICUNO: "Articuno", ZAPDOS: "Zapdos", MOLTRES: "Moltres", MEWTWO: "Mewtwo"}
LEGENDS = frozenset({ARTICUNO, ZAPDOS, MOLTRES, MEWTWO})
SAVE_SLOT = 9                    # the battle-start state (load_state(9) retries); the pre-gym / pre-door saves use other slots
MASTER_BALL, ULTRA_BALL, GREAT_BALL, POKE_BALL = 1, 2, 3, 4
RED = 0.25                       # at or below this fraction the foe is weak enough: stop attacking, use status / balls


# Static encounters of an otherwise unobtainable species: the Power Plant's Electrodes (L34 — the wild tables only have Voltorb there; the only wild Electrodes are in Cerulean Cave at L58+).
# Keyed by the map they stand on, so a wild Electrode elsewhere is just a wild Electrode.
STATIC_BY_MAP: dict[tuple, dict[int, str]] = {(1, 95): {101: "Electrode"}}


def is_one_shot(species_id: int, map_key=None, shiny: bool = False) -> bool:
    """A foe that must be caught, not beaten: Snorlax, the legends, Mewtwo anywhere — a static Electrode in the Power Plant — and any SHINY wild Pokémon (1 in 8192: knock it out and it is gone)."""
    return shiny or species_id in ONE_SHOT or (map_key is not None and species_id in STATIC_BY_MAP.get(tuple(map_key[:2]), {}))


def one_shot_name(species_id: int, map_key=None, species_name: str = "", shiny: bool = False) -> str:
    if shiny:
        return f"SHINY {species_name or 'Pokémon'}"
    return ONE_SHOT.get(species_id) or STATIC_BY_MAP.get(tuple(map_key[:2]) if map_key is not None else (), {}).get(species_id, "")


def gentlest_move(move_names, pp, power) -> str:
    """The lowest-power DAMAGING move with PP left, or '' (the safest way to chip a foe down without fainting it). `power` is {move name: base power}."""
    best = None
    for i, n in enumerate(move_names or []):
        if not n or (pp is not None and i < len(pp) and pp[i] <= 0):
            continue
        p = power.get(n, 0)
        if p > 0 and (best is None or p < best[0]):
            best = (p, n)
    return best[1] if best else ""


def protocol(species_id: int, hp: int, max_hp: int, balls: dict, setup_hint: str = "", chip: str = "", asleep_or_para: bool = False, slot: int = SAVE_SLOT, map_key=None,
             shiny: bool = False, species_name: str = "") -> str:
    """The ONE-SHOT block for the battle observation, or '' for any other foe."""
    if not is_one_shot(species_id, map_key, shiny) or not max_hp or hp <= 0:
        return ""                                            # not one of them, or it already fainted (nothing left to protect)
    name = one_shot_name(species_id, map_key, species_name, shiny)
    frac = hp / max_hp
    ball = ("the MASTER BALL (it never fails)" if balls.get(MASTER_BALL) and species_id in LEGENDS else
            "an Ultra Ball" if balls.get(ULTRA_BALL) else "a Great Ball" if balls.get(GREAT_BALL) else "a Poké Ball" if balls.get(POKE_BALL) else "")
    head = ((f"✨ SHINY {species_name or 'Pokémon'}! A 1-in-8192 find — it must be CAUGHT whatever its species or level (even one you own or 'not worth a ball'): "
             "do NOT knock it out, flee, or let it flee. ") if shiny else f"ONE-SHOT: {name} appears once — do NOT knock it out or let it flee. ")
    head += (f"The battle-start state is saved in slot {slot}: if it faints or runs, "
             f"load_state({slot}) and try again, more gently.")
    if not ball:
        return head + " You have no Poké Balls: load_state, buy Ultra Balls (shop), and come back."
    if frac <= RED:
        step = (f"It is in the red ({hp}/{max_hp}): STOP attacking. " + ("It is already asleep / paralysed — " if asleep_or_para else "A status move first if you have one, then ")
                + f"throw {ball} with catch().")
    elif frac <= 0.5:
        step = (f"{hp}/{max_hp}: nearly there — one more careful chip" + (f" ({chip})" if chip else "") + " or a status move, then catch() with " + ball + ".")
    else:
        step = (f"{hp}/{max_hp}: weaken it carefully, one hit at a time" + (f" — use {chip}, your gentlest damaging move" if chip else "")
                + "; never use a strong move or a multi-hit one. Re-check its HP after every turn.")
    return f"{head} {step} {setup_hint}".strip()
