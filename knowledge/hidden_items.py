"""Hidden items worth walking to (pure data + logic; no I/O).

knowledge.area_facts lists every item on every map from the decomp, hidden ones as 'Rare Candy (hidden)' with their tile. Sweeping all of them is a waste
(Potions, berries and the like), so `worthwhile` keeps what changes a run: PP Ups, Rare Candy, vitamins, Max Revive / Full Restore, Ether / Elixir, the sellable
treasure (Nugget, Pearls, Star Piece, Stardust, Big Mushroom — knowledge.selling) and a few strong balls / stones / TMs. A hidden item is picked by standing next to
its tile, facing it and pressing A; the Itemfinder only SHOWS where one is, the coordinates are known here."""
from knowledge.area_facts import AREA_FACTS

_WORTH = ("pp up", "pp max", "rare candy", "protein", "iron", "carbos", "calcium", "zinc", "hp up", "max revive", "revive", "full restore", "max potion",
          "ether", "elixir", "nugget", "pearl", "star piece", "stardust", "big mushroom", "ultra ball", "moon stone", "leaf stone", "fire stone",
          "water stone", "thunder stone", "sun stone", "tm", "hm")


def worthwhile(name: str) -> bool:
    n = str(name).lower().replace("(hidden)", "").strip()
    if n.startswith(("tm", "hm")):
        return n[2:].strip().isdigit()                       # 'Tm46', not 'Tm' as a substring of another word
    return any(k in n for k in _WORTH if k not in ("tm", "hm"))


def hidden_on(map_key, taken=()) -> list:
    """[(item name, x, y)] of the worthwhile hidden items on `map_key` (bank, id) that are not in `taken` ({'bank/id/x/y'} the run already collected or found empty)."""
    facts = AREA_FACTS.get(tuple(map_key))
    if not facts:
        return []
    out = []
    for name, x, y in facts[2]:
        if "(hidden)" in name and worthwhile(name) and f"{map_key[0]}/{map_key[1]}/{x}/{y}" not in taken:
            out.append((name.replace(" (hidden)", ""), x, y))
    return out
