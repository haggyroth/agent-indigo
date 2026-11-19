"""Which Celadon Dept. Store TMs are worth buying for THIS team (pure; no I/O).

The 2F TM counter sells TM05 Roar, TM15 Hyper Beam, TM28 Dig, TM31 Brick Break, TM43 Secret Power and TM45 Attract (decomp: CeladonCity_DepartmentStore_2F_TMs, prices from items.json).
`knowledge.bag.tm_advice` already scores a TM against every compatible party member (coverage gain, free slot vs replacing a move, never a suicide move); this feeds it the shop's stock
instead of the bag and adds the price and what you can afford, so team_report can say "buy TM31 for Raichu" instead of leaving the choice to a blind shop(item=…)."""
from knowledge.bag import tm_advice
from knowledge.tmhm import ITEM_TM01

STORE = "Celadon Dept. Store 2F"
STOCK: dict[str, int] = {"TM05": 1000, "TM15": 7500, "TM28": 2000, "TM31": 3000, "TM43": 3000, "TM45": 3000}       # label -> price (¥)


def _item(label: str) -> int:
    return ITEM_TM01 + int(label[2:]) - 1


def plan(party, owned_labels=(), money: int = 0, limit: int = 3) -> list:
    """[(TMAdvice, price, affordable)] — the stock's useful TMs for the party, best gain first (a TM already in the TM Case is skipped)."""
    have = set(owned_labels or ())
    out = []
    for adv in tm_advice(party, [(_item(label), 1) for label in STOCK if label not in have], limit=limit):
        price = STOCK[adv.tm]
        out.append((adv, price, money >= price))
    return out


def line(party, owned_labels=(), money: int = 0) -> str:
    """The team_report line ('' when nothing in the shop helps)."""
    rows = plan(party, owned_labels, money)
    if not rows:
        return ""
    parts = []
    for adv, price, ok in rows:
        parts.append(f"{adv.tm} {adv.move} ¥{price:,} for {adv.mon}" + ("" if ok else " (not enough money yet)"))
    return f"TM shop ({STORE}, shop(item='TMxx')): " + "; ".join(parts)
