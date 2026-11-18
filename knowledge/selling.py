"""What is safe to SELL at a Poké Mart, and how much it is worth (pure data + logic; no I/O).

Prize money is the only income the agent has, and Elite Four prep (Full Restores, Revives, Max Potions, balls) and the Dept. Store's TMs are expensive.
The Items pocket often holds treasure that only exists to be sold: a Nugget sells for ¥5000. Everything the team can still use — evolution stones, Rare
Candy and vitamins, healing and status items, Repels / Escape Rope, Poké Balls — is protected; TMs/HMs and key items are not in the pocket the Sell list shows."""
from knowledge.bag import CANDY_VITAMINS, STONES

# item id -> (name, approximate sell price): the pure-treasure items (decomp constants/items.h; sell price = half the buy price)
TREASURE: dict[int, tuple[str, int]] = {
    103: ("Tiny Mushroom", 250), 104: ("Big Mushroom", 2500), 106: ("Pearl", 700), 107: ("Big Pearl", 3750),
    108: ("Stardust", 1000), 109: ("Star Piece", 4900), 110: ("Nugget", 5000),
}
# Never sold on request either: things the run uses (ids from knowledge.shopping): Poké/Great/Ultra/Master Ball, Potions + Revives + cures, Repels, Escape Rope
PROTECTED = frozenset(STONES | CANDY_VITAMINS | {1, 2, 3, 4, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 83, 84, 85, 86})


def _norm(text) -> str:
    return str(text or "").strip().lower().replace("é", "e")


def resolve(text: str) -> int | None:
    """Item id for a name or substring of a TREASURE / shop item name, or None (also None when the name is ambiguous)."""
    from knowledge.shopping import item_label
    from knowledge.shop_stock import ITEM_LABELS
    key = _norm(text)
    if not key:
        return None
    names = {i: n.lower() for i, (n, _p) in TREASURE.items()}
    for i in ITEM_LABELS:
        names.setdefault(i, _norm(item_label(i)))
    exact = [i for i, n in names.items() if n == key]
    hits = exact or [i for i, n in names.items() if key in n]
    return hits[0] if len(hits) == 1 else None


def sell_plan(bag: dict, item: str = "", quantity: int = 1) -> tuple[list, str]:
    """([(item id, count)], message). No `item`: every treasure in the bag, all of it. With `item`: that item, `quantity` of it (capped at what is held),
    unless it is protected. The plan is empty when there is nothing to do; the message then says why (or, with a plan, what will be sold)."""
    if not _norm(item):
        plan = [(i, bag[i]) for i in sorted(TREASURE) if bag.get(i, 0) > 0]
        if not plan:
            return [], ("Nothing spare to sell: no treasure in the bag (Nugget, Big Pearl, Star Piece, Pearl, Stardust, Big / Tiny Mushroom). "
                        "Name an item to sell it anyway, e.g. shop(sell=true, item='Nugget').")
        worth = sum(TREASURE[i][1] * n for i, n in plan)
        return plan, f"Selling {', '.join(f'{n}× {TREASURE[i][0]}' for i, n in plan)} (about ¥{worth})."
    iid = resolve(item)
    if iid is None:
        return [], f"Can't tell which item {item!r} is — use its name ('Nugget', 'Star Piece', 'Super Repel')."
    from knowledge.shopping import item_label
    label = TREASURE[iid][0] if iid in TREASURE else item_label(iid)
    if iid in PROTECTED:
        return [], (f"Not selling {label}: the team can still use it (stones, vitamins, healing, cures, Repels and Poké Balls are kept). "
                    "Use it instead, or sell treasure (Nugget, Pearl, Star Piece…).")
    have = bag.get(iid, 0)
    if have <= 0:
        return [], f"You don't have any {label} to sell."
    n = max(1, min(int(quantity or 1), have))
    return [(iid, n)], f"Selling {n}× {label}."
