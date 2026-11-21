"""Held items (pure): what each does, and who in the party should carry what you own.

Effects come from the decomp (`held_items_data`, generated). Advice is deliberately plain: a type-boost item goes to the highest-level
Pokémon that actually attacks with that type, Leftovers / Shell Bell to the ace, Exp. Share / Lucky Egg to whoever lags behind
(the holder levels without fighting). Berries live in the separate Berry Pouch and are not handled here.
"""
from knowledge.held_items_data import HELD_ITEMS

_TYPE_POWER = {"WATER": "WAT", "FIRE": "FIR", "GRASS": "GRS", "ELECTRIC": "ELE", "ICE": "ICE", "FIGHTING": "FIG", "POISON": "POI",
               "GROUND": "GRD", "ROCK": "ROC", "FLYING": "FLY", "PSYCHIC": "PSY", "GHOST": "GHO", "DRAGON": "DRG", "DARK": "DRK",
               "NORMAL": "NOR", "STEEL": "STL", "BUG": "BUG"}
_ACE = {"LEFTOVERS", "SHELL_BELL", "QUICK_CLAW", "FOCUS_BAND", "SCOPE_LENS", "KINGS_ROCK", "CHOICE_BAND"}
_LAGGING = {"EXP_SHARE", "LUCKY_EGG"}
_PLAIN = {
    "LEFTOVERS": "restores 1/16 of max HP every turn", "SHELL_BELL": "heals the holder by 1/8 of the damage it deals",
    "EXP_SHARE": "the holder gets half the Exp. of a battle even if it never fought", "LUCKY_EGG": "the holder gains 50% more Exp.",
    "QUICK_CLAW": "20% chance to move first", "FOCUS_BAND": "10% chance to survive a KO with 1 HP",
    "SCOPE_LENS": "higher critical-hit rate", "KINGS_ROCK": "10% flinch chance on damaging moves",
    "AMULET_COIN": "doubles prize money if the holder is in the fight", "EVERSTONE": "STOPS the holder evolving",
    "SMOKE_BALL": "the holder can always flee a wild battle", "CHOICE_BAND": "Attack ×1.5 but locked into one move",
    "LIGHT_BALL": "doubles Pikachu's Sp. Atk", "THICK_CLUB": "doubles Cubone / Marowak's Attack", "LUCKY_PUNCH": "raises Chansey's crit rate",
    "METAL_POWDER": "raises Ditto's Defense", "STICK": "raises Farfetch'd's crit rate", "SOUL_DEW": "Latios / Latias only",
    "MACHO_BRACE": "halves Speed but doubles EVs gained", "CLEANSE_TAG": "weakens wild encounters for the holder's party",
}
_ONLY = {"LIGHT_BALL": "Pikachu", "THICK_CLUB": ("Cubone", "Marowak"), "LUCKY_PUNCH": "Chansey", "METAL_POWDER": "Ditto",
         "STICK": "Farfetch'd"}


def name(item_id: int) -> str:
    return HELD_ITEMS[item_id][0] if item_id in HELD_ITEMS else (f"item #{item_id}" if item_id else "nothing")


def describe(item_id: int) -> str:
    """'Leftovers (restores 1/16 of max HP every turn)'."""
    if item_id not in HELD_ITEMS:
        return name(item_id)
    nm, eff, param = HELD_ITEMS[item_id]
    if eff in _TYPE_POWER or eff.removesuffix("_POWER") in _TYPE_POWER:
        return f"{nm} (+{param}% to {eff.removesuffix('_POWER').title()}-type moves)"
    return f"{nm} ({_PLAIN[eff]})" if eff in _PLAIN else nm


def _attack_types(mon) -> set:
    from knowledge.leafgreen_data import MOVE_POWER, MOVE_TYPE
    return {MOVE_TYPE.get(m) for m in (mon.move_names or []) if m and MOVE_POWER.get(m, 0) > 0}


def holder_for(item_id: int, party):
    """The party member who should carry `item_id`, or None when nobody fits."""
    if item_id not in HELD_ITEMS or not party:
        return None
    eff = HELD_ITEMS[item_id][1]
    alive = [p for p in party if getattr(p, "max_hp", 0)]
    if not alive:
        return None
    if eff.endswith("_POWER") and eff.removesuffix("_POWER") in _TYPE_POWER:
        code = _TYPE_POWER[eff.removesuffix("_POWER")]
        users = [p for p in alive if code in _attack_types(p)]
        return max(users, key=lambda p: p.level, default=None)
    if eff in _ONLY:
        only = _ONLY[eff] if isinstance(_ONLY[eff], tuple) else (_ONLY[eff],)
        return next((p for p in alive if p.species_name in only), None)
    if eff in _LAGGING:
        return min(alive, key=lambda p: p.level)
    if eff in _ACE:
        return max(alive, key=lambda p: p.level)
    return None


def suggest(party, items, limit: int = 3) -> list[str]:
    """Lines like "Leftovers: give_item('Leftovers', 'Venusaur') — restores 1/16 of max HP every turn" for held-item types in the
    Items pocket that someone should carry and nobody holds yet."""
    out = []
    held = {p.held_item for p in party if getattr(p, "held_item", 0)}
    for iid, qty in items:
        if qty <= 0 or iid not in HELD_ITEMS or iid in held:
            continue
        who = holder_for(iid, party)
        if who is None or getattr(who, "held_item", 0):
            continue
        nm = HELD_ITEMS[iid][0]
        out.append(f"{nm}: give_item('{nm}', '{who.nickname or who.species_name}') — {describe(iid).split('(', 1)[-1].rstrip(')')}")
    return out[:limit]


def holding_line(party) -> str:
    """'Holding: Venusaur — Leftovers; Pikachu — Light Ball' ('' when nobody holds anything)."""
    bits = [f"{p.nickname or p.species_name} — {name(p.held_item)}" for p in party if getattr(p, "held_item", 0)]
    return "Holding: " + "; ".join(bits) if bits else ""


EXP_SHARE = 182


def exp_share_plan(party, owns_one: bool):
    """(holder, target) for the adaptive Exp. Share: the Pokémon that should hold it NOW is the lowest-level one (it levels without fighting). `holder` is who carries it today (None when it is in the
    Bag), `target` is who should. Returns None when there is nothing to do: no Exp. Share, nobody valid, or the holder is already the lowest (a tie keeps the current holder, so equal levels never
    thrash). Fainted members count — a revived one is still the one to level."""
    members = [p for p in party if getattr(p, "max_hp", 0)]
    holder = next((p for p in members if getattr(p, "held_item", 0) == EXP_SHARE), None)
    if not members or not (holder or owns_one):
        return None
    target = min(members, key=lambda p: (p.level, p is not holder))                # lowest level; among equals the current holder wins
    if holder is not None and holder.level <= target.level:
        return None
    return holder, target
