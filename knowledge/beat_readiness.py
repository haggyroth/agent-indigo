"""How strong the party should be before a non-gym story beat (pure data + logic; no I/O).

Gyms warn through knowledge.gym_advice; the other beats just started. A watched Victory Road run walked a party 10-30 levels under the cave's wild L40+
Pokémon in and fainted its way through it. Numbers are the level ranges of the beat's trainers and wild Pokémon (decomp parties, as quoted in
knowledge.story_beats): `top` = the best Pokémon's level, `depth` Pokémon at `floor` or higher (a lone ace cannot carry a dungeon: it faints, or runs out of PP)."""
from dataclasses import dataclass

HEAL_ITEMS = frozenset({13, 22, 21, 20, 19})       # Potion, Super / Hyper / Max Potion, Full Restore
REVIVES = frozenset({24, 25})                      # Revive, Max Revive
HEAL_HP = {13: 20, 22: 50, 21: 200, 20: 999, 19: 999}      # HP each restores
GRADE_FROM_TOP = 40        # from this level up, a heal counts for what it restores: 10 Potions (20 HP) do not heal a L50 team (a watched run reached the League with ¥0 and no real heals)
HP_PER_LEVEL = 2.5         # one "full" heal restores about this × the best Pokémon's level in HP (a Hyper Potion's 200 at L80); smaller potions count for the fraction


@dataclass(frozen=True)
class Need:
    top: int
    floor: int
    depth: int
    why: str
    potions: int = 0           # HP-restoring items to carry (any grade counts as one)
    revives: int = 0


NEEDS: dict[str, Need] = {
    "rocket_hideout": Need(26, 20, 3, "about a dozen Rocket trainers (L20-29) and Giovanni", 5, 1),
    "pokemon_tower": Need(26, 20, 3, "your rival (~L25) and Gastly / Haunter / Cubone (L18-28)", 5, 2),
    "snorlax": Need(30, 22, 2, "a L30 Snorlax with a huge HP bar", 3, 0),
    "silph_co": Need(38, 28, 3, "Rocket trainers L25-37, your rival, and Giovanni (L35-41)", 8, 2),
    "pokemon_mansion": Need(34, 26, 3, "wild and trainer Pokémon L30-37 and the Fire-types that guard the Key", 6, 1),
    "victory_road": Need(42, 34, 4, "trainers and wild Pokémon L36-45", 10, 3),
    "elite_four": Need(54, 46, 5, "five back-to-back fights (Lorelei L51-56 … Lance L56-62, the Champion L53-65) with no healing between them", 12, 4),
}


def effective_heals(bag, top: int) -> float:
    """HP-restoring items in `bag` ({item id: count}) as full-strength heals for a team whose best Pokémon is L`top`: each grade counts min(1, HP restored / (HP_PER_LEVEL × top))
    — below GRADE_FROM_TOP every grade counts as one (the early beats' Potions are fine)."""
    cap = HP_PER_LEVEL * top if top >= GRADE_FROM_TOP else 0
    return sum(n * (min(1.0, HEAL_HP[i] / cap) if cap else 1.0) for i, n in bag.items() if i in HEAL_ITEMS)


def supplies_short(key: str, bag) -> list:
    """['N HP items (M recommended)', 'K Revives (J recommended)'] that fall short for beat `key`, [] when stocked or `bag` is None. `bag` is {item id: count}.
    For the late beats the HP items are counted by strength (see effective_heals) and the message says which grade to buy."""
    need = NEEDS.get(key)
    if need is None or bag is None:
        return []
    have_p = effective_heals(bag, need.top)
    have_r = sum(n for i, n in bag.items() if i in REVIVES)
    out = []
    if have_p < need.potions:
        shown = int(have_p) if have_p == int(have_p) else round(have_p, 1)
        graded = " — counted by strength: a Hyper Potion / Max Potion / Full Restore is 1, a Super Potion or Potion a fraction" if need.top >= GRADE_FROM_TOP and any(i in HEAL_ITEMS for i in bag) else ""
        out.append(f"{shown} Potions / Restores in the bag ({need.potions} recommended{graded})")
    if have_r < need.revives:
        out.append(f"{have_r} Revives ({need.revives} recommended)")
    return out


MAX_TOP, MAX_FLOOR = 70, 62                  # the raised League levels stop here (no team needs more; keeps the rule from asking for the impossible)


def league_need(losses: int = 0, bump: int = 0) -> Need:
    """The Elite Four's Need with the optional loss rule applied: `bump` levels more for the best Pokémon and the depth floor per loss so far."""
    base = NEEDS["elite_four"]
    extra = max(0, int(losses)) * max(0, int(bump))
    return Need(min(base.top + extra, MAX_TOP), min(base.floor + extra, MAX_FLOOR), base.depth, base.why, base.potions, base.revives)


def _shortfall(need: Need, party) -> list:
    if not party:
        return []
    levels = sorted((p.level for p in party), reverse=True)
    deep = sum(1 for lv in levels if lv >= need.floor)
    short = []
    if levels[0] < need.top:
        short.append(f"your best Pokémon is L{levels[0]} (L{need.top} recommended)")
    if deep < need.depth:
        short.append(f"only {deep} of your team {'is' if deep == 1 else 'are'} L{need.floor}+ ({need.depth} recommended)")
    return short


def loss_advice(party, losses: int, bump: int, rule: str = "advise") -> str:
    """The optional LEAGUE_LOSS_RULE's nudge: '' when the rule is off, there are no losses, or the party already meets the raised levels; else why the bar went up
    and what is short. Encouragement, not force: the caller shows it once per loss count in "advise" mode (the next call goes ahead) and on every call in "wall" mode."""
    if rule == "off" or bump <= 0 or losses <= 0:
        return ""
    short = _shortfall(league_need(losses, bump), party)
    if not short:
        return ""
    need = league_need(losses, bump)
    plural = "loss" if losses == 1 else "losses"
    tail = ("Training is encouraged, not required — call quest('elite_four') again to go anyway." if rule != "wall"
            else "Train first — this rule is set to refuse until the party meets them.")
    return (f"You have lost in the Pokémon League {losses} {plural} so far, so the bar has gone up {bump} level{'s' if bump != 1 else ''} per loss to L{need.top} for the best Pokémon and "
            f"{need.depth} at L{need.floor}+: {'; '.join(short)}. Each loss resets the whole League and the rooms are sealed, so the same team tends to fall at the same trainer. "
            f"grind() with no level lifts the weaker members, grind({need.top}) the ace; Victory Road's wild L32-48 are nearest. {tail}")


HARD_LEVELS = frozenset({"elite_four"})      # beats whose LEVEL shortfall is a wall, not a warning (a loss resets the whole League, the rooms seal, no Center): no 'call again to go anyway'


def level_shortfall(key: str, party) -> list[str]:
    """['your best Pokémon is L52 (L54 recommended)', 'only 3 of your team are L46+ (5 recommended)'] — the level gaps for beat `key`, [] when there are none."""
    need = NEEDS.get(key)
    return _shortfall(need, party) if need is not None else []


def hard_wall(key: str, party, losses: int = 0, bump: int = 0, rule: str = "advise") -> str:
    """'' unless beat `key` is level-gated for good (HARD_LEVELS) and the party falls short: then the refusal, which no second call overrides. With LEAGUE_LOSS_RULE="wall" the
    Elite Four's levels are the raised ones (after `losses` losses, `bump` levels each); otherwise the base levels."""
    if key not in HARD_LEVELS:
        return ""
    need = league_need(losses, bump) if (key == "elite_four" and rule == "wall") else NEEDS[key]
    short = _shortfall(need, party)
    if not short:
        return ""
    return (f"Not ready for quest('{key}') — and this one cannot be skipped: {'; '.join(short)}. It means {need.why}. Throwing a team this far under at it only costs "
            f"money and time: a loss resets the whole League and sends you back to the Plateau's Center, and the rooms are sealed (no Center, no shop), so every fight is the same fight "
            f"with what the Bag holds. Train first: grind() with no level lifts the weaker members, grind({need.top}) the ace (Victory Road's wild L32-48 are nearest); then call quest('{key}') again.")


def readiness(key: str, party, bag=None) -> str:
    """'' when the party (and, with `bag`, its healing supplies) is ready for beat `key` (or the beat has no requirement); else why not and what to do.
    A fainted Pokémon counts as present (a heal fixes it) — only its LEVEL matters here."""
    need = NEEDS.get(key)
    if need is None or not party:
        return ""
    short = level_shortfall(key, party)
    stock = supplies_short(key, bag)
    if not short and not stock:
        return ""
    parts = []
    if short:
        parts.append(f"{'; '.join(short)} — it means {need.why}. grind() with no level lifts the weaker members (grind({need.top}) the ace)")
    if stock:
        parts.append(f"only {'; '.join(stock)} — shop() for Potions and Revives — Hyper Potions (¥1,200, +200 HP) are the best value and are sold in Saffron, Fuchsia, Cinnabar and Celadon, not at the Plateau (its clerk has Max Potions ¥2,500 and Full Restores ¥3,000); fly_to a mart town first when you are at the Plateau (shop(sell=true) turns spare treasure into money)")
    return f"Not ready for quest('{key}'): " + "; and ".join(parts) + f". Call quest('{key}') again to go anyway."


def recommendation(key: str) -> str:
    """One plan line for quest(<key>)'s plan, or ''."""
    need = NEEDS.get(key)
    if not need:
        return ""
    sup = f", and carry {need.potions}+ Potions{f' and {need.revives}+ Revives' if need.revives else ''}" if need.potions else ""
    return f"Recommended: best Pokémon L{need.top}+ and {need.depth} at L{need.floor}+ ({need.why}){sup}."
