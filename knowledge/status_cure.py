"""Cures for a Pokémon's major status (pure): which Bag item fixes which condition, and the one-line nudge the battle observation gives.

A watched run bought Full Heals and used none in 1,700 calls — its Lapras fought on paralysed through a whole Elite Four room. Nothing in the observation ever connected the
status to the Bag, so the model never thought of it."""

# status word (game.memory_reader.decode_status, first word) -> item ids that cure it, cheapest first; Full Heal (23) and Full Restore (19) cure everything.
SPECIFIC = {"poisoned": (14,), "badly_poisoned": (14,), "burned": (15,), "frozen": (16,), "paralyzed": (18,), "asleep": (17,)}
UNIVERSAL = (23, 19)
NAMES = {14: "Antidote", 15: "Burn Heal", 16: "Ice Heal", 17: "Awakening", 18: "Paralyze Heal", 23: "Full Heal", 19: "Full Restore"}
_WHY = {
    "asleep": "it cannot act while asleep",
    "frozen": "it cannot act while frozen (it only thaws by luck)",
    "paralyzed": "it moves at a quarter speed and is fully paralysed about one turn in four",
    "burned": "its Attack is halved and it loses HP every turn",
    "poisoned": "it loses HP every turn",
    "badly_poisoned": "it loses more HP every turn",
}


def status_key(status) -> str:
    """'asleep (3 turns)' -> 'asleep'; '' / 'healthy' / 'unknown' -> ''."""
    word = str(status or "").split(" ")[0].strip()
    return word if word in SPECIFIC else ""


def cure_ids(status, bag) -> list[int]:
    """Item ids in `bag` ({id: count}) that cure `status`, the specific cure first, then Full Heal, then Full Restore."""
    key = status_key(status)
    if not key or not bag:
        return []
    return [i for i in (*SPECIFIC[key], *UNIVERSAL) if bag.get(i)]


def cure_hint(label: str, status, bag, hp_frac: float = 1.0) -> str:
    """'' unless the ACTIVE Pokémon has a major status the Bag can cure; else the nudge (using the item costs the turn)."""
    key = status_key(status)
    ids = cure_ids(status, bag)
    if not key or not ids:
        return ""
    best = NAMES[ids[0]]
    if ids[0] == 19 and hp_frac >= 0.6:
        # Full Restore is the Elite Four's lifeline: only spend it on a status when it also heals
        return ""
    urgency = "Cure it now" if key in ("asleep", "frozen") else ("Worth a turn" if key in ("paralyzed", "burned") else "Cure it when a turn is free")
    return f"STATUS: {label} is {key.replace('_', ' ')} — {_WHY[key]}. {urgency}: use_item('{best}') (you hold {bag[ids[0]]}), or switch to a healthy teammate."
