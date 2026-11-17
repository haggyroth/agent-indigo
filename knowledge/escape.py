"""Getting out of places without walking (pure): Escape Rope, Dig and Teleport, as the game really treats them.

The rules are the decomp's (item_use.c, fldeff_dig.c, fldeff_teleport.c), via the generated `escape_maps`:
  * Escape Rope and the field move Dig work only where the map allows escaping (caves, forests, dungeons — NOT towns, routes or
    buildings) and take you to the entrance you came in by. Dig needs TM28 and no badge; the rope is a Poké Mart item.
  * Teleport (Abra line, level-up only) works only OUTDOORS (routes, towns, cities) and warps to the last Pokémon Center you
    healed at (your Pallet house before the first heal). It is the free "heal() shortcut" Fly doesn't give you.
A few maps are both (Viridian Forest is a 'route' that also allows escaping), so check the map, not the look of it.
Using any of them leaves the current map, so a trip or quest in progress is abandoned.
"""
from knowledge.escape_maps import ESCAPABLE, TELEPORT_OK

ROPE_ID, DIG_ID, TELEPORT_ID = 85, 91, 100

FACTS = ("Escape Rope / Dig: caves & dungeons only — warp to the entrance you came in by. Teleport: outdoors only — warp to the "
         "last Pokémon Center you healed at. None works in a town building or against a trainer; all abandon the current trip.")


def can_escape(cur) -> bool:
    return tuple(cur) in ESCAPABLE


def can_teleport(cur) -> bool:
    return tuple(cur) in TELEPORT_OK


def why_not(kind: str, cur) -> str:
    """'' when `kind` ('Escape Rope' / 'Dig' / 'Teleport') works on the map `cur`, else why it does not."""
    if kind == "Teleport":
        return "" if can_teleport(cur) else "Teleport only works outdoors (routes, towns, cities) — walk out of here first."
    return "" if can_escape(cur) else (f"{kind} only works inside a cave, forest or dungeon — not in towns, on routes or in buildings. "
                                       "Use go_to / go_to_map to leave.")


def hint(cur, move_ids, rope_count: int, pokecenter_known: bool = True) -> str:
    """One observation line: the shortcut available on THIS map with THIS party and bag, or ''."""
    ways = []
    if can_escape(cur):
        if DIG_ID in move_ids:
            ways.append("use_hm('Dig')")
        if rope_count:
            ways.append(f"use_item('Escape Rope') ({rope_count} left)")
        if ways:
            return "Exit shortcut: " + " or ".join(ways) + " warps you back to this place's entrance (abandons any trip)."
    elif can_teleport(cur) and TELEPORT_ID in move_ids:
        return "Shortcut: use_hm('Teleport') warps you to the last Pokémon Center you healed at (abandons any trip)."
    return ""
