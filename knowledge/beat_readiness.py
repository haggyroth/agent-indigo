"""How strong the party should be before a non-gym story beat (pure data + logic; no I/O).

Gyms warn through knowledge.gym_advice; the other beats just started. A watched Victory Road run walked a party 10-30 levels under the cave's wild L40+
Pokémon in and fainted its way through it. Numbers are the level ranges of the beat's trainers and wild Pokémon (decomp parties, as quoted in
knowledge.story_beats): `top` = the best Pokémon's level, `depth` Pokémon at `floor` or higher (a lone ace cannot carry a dungeon: it faints, or runs out of PP)."""
from dataclasses import dataclass

HEAL_ITEMS = frozenset({13, 22, 21, 20, 19})       # Potion, Super / Hyper / Max Potion, Full Restore
REVIVES = frozenset({24, 25})                      # Revive, Max Revive


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


def supplies_short(key: str, bag) -> list:
    """['N HP items (M recommended)', 'K Revives (J recommended)'] that fall short for beat `key`, [] when stocked or `bag` is None. `bag` is {item id: count}."""
    need = NEEDS.get(key)
    if need is None or bag is None:
        return []
    have_p = sum(n for i, n in bag.items() if i in HEAL_ITEMS)
    have_r = sum(n for i, n in bag.items() if i in REVIVES)
    out = []
    if have_p < need.potions:
        out.append(f"{have_p} Potions / Restores in the bag ({need.potions} recommended)")
    if have_r < need.revives:
        out.append(f"{have_r} Revives ({need.revives} recommended)")
    return out


def readiness(key: str, party, bag=None) -> str:
    """'' when the party (and, with `bag`, its healing supplies) is ready for beat `key` (or the beat has no requirement); else why not and what to do.
    A fainted Pokémon counts as present (a heal fixes it) — only its LEVEL matters here."""
    need = NEEDS.get(key)
    if need is None or not party:
        return ""
    levels = sorted((p.level for p in party), reverse=True)
    deep = sum(1 for lv in levels if lv >= need.floor)
    short = []
    if levels[0] < need.top:
        short.append(f"your best Pokémon is L{levels[0]} (L{need.top} recommended)")
    if deep < need.depth:
        short.append(f"only {deep} of your team {'is' if deep == 1 else 'are'} L{need.floor}+ ({need.depth} recommended)")
    stock = supplies_short(key, bag)
    if not short and not stock:
        return ""
    parts = []
    if short:
        parts.append(f"{'; '.join(short)} — it means {need.why}. grind() with no level lifts the weaker members (grind({need.top}) the ace)")
    if stock:
        parts.append(f"only {'; '.join(stock)} — shop() for Potions and Revives (shop(sell=true) turns spare treasure into money)")
    return f"Not ready for quest('{key}'): " + "; and ".join(parts) + f". Call quest('{key}') again to go anyway."


def recommendation(key: str) -> str:
    """One plan line for quest(<key>)'s plan, or ''."""
    need = NEEDS.get(key)
    if not need:
        return ""
    sup = f", and carry {need.potions}+ Potions{f' and {need.revives}+ Revives' if need.revives else ''}" if need.potions else ""
    return f"Recommended: best Pokémon L{need.top}+ and {need.depth} at L{need.floor}+ ({need.why}){sup}."
