"""How strong the party should be before a non-gym story beat (pure data + logic; no I/O).

Gyms warn through knowledge.gym_advice; the other beats just started. A watched Victory Road run walked a party 10-30 levels under the cave's wild L40+
Pokémon in and fainted its way through it. Numbers are the level ranges of the beat's trainers and wild Pokémon (decomp parties, as quoted in
knowledge.story_beats): `top` = the best Pokémon's level, `depth` Pokémon at `floor` or higher (a lone ace cannot carry a dungeon: it faints, or runs out of PP)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Need:
    top: int
    floor: int
    depth: int
    why: str


NEEDS: dict[str, Need] = {
    "rocket_hideout": Need(26, 20, 3, "about a dozen Rocket trainers (L20-29) and Giovanni"),
    "pokemon_tower": Need(26, 20, 3, "your rival (~L25) and Gastly / Haunter / Cubone (L18-28)"),
    "snorlax": Need(30, 22, 2, "a L30 Snorlax with a huge HP bar"),
    "silph_co": Need(38, 28, 3, "Rocket trainers L25-37, your rival, and Giovanni (L35-41)"),
    "pokemon_mansion": Need(34, 26, 3, "wild and trainer Pokémon L30-37 and the Fire-types that guard the Key"),
    "victory_road": Need(42, 34, 4, "trainers and wild Pokémon L36-45"),
    "elite_four": Need(54, 46, 5, "five back-to-back fights (Lorelei L51-56 … Lance L56-62, the Champion L53-65) with no healing between them"),
}


def readiness(key: str, party) -> str:
    """'' when the party is ready for beat `key` (or the beat has no requirement); else why not and what to do. A fainted Pokémon counts as present
    (a heal fixes it) — only its LEVEL matters here."""
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
    if not short:
        return ""
    return (f"Not ready for quest('{key}'): {'; '.join(short)} — it means {need.why}. grind() with no level lifts the weaker members "
            f"(grind({need.top}) the ace), then heal() and shop() for Potions and Revives. Call quest('{key}') again to go anyway.")


def recommendation(key: str) -> str:
    """One plan line for quest(<key>)'s plan, or ''."""
    need = NEEDS.get(key)
    return f"Recommended: best Pokémon L{need.top}+ and {need.depth} at L{need.floor}+ ({need.why})." if need else ""
