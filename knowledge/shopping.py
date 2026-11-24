"""Purchase policy for the Poké Mart — the "approved to buy" list with par levels
and badge-gated unlocks. Pure data + logic (no I/O), so it unit-tests without an
emulator. `compute_shopping_list` takes the current bag, badge count, and money and
returns what to restock, in priority order, capped by what you can afford.

The agent reads the bag/money from memory (memory_reader.read_bag/read_money) and
feeds them here; the deterministic `buy` skill (separate) executes the result.
"""
from dataclasses import dataclass

# Item ids (pokefirered constants/items.h) and display names — only the consumables
# the agent restocks. Balls, healing, status, escape.
ITEM_NAMES: dict[int, str] = {
    1: "Master Ball", 2: "Ultra Ball", 3: "Great Ball", 4: "Poké Ball",
    13: "Potion", 22: "Super Potion", 21: "Hyper Potion", 20: "Max Potion",
    19: "Full Restore",
    14: "Antidote", 18: "Paralyze Heal", 17: "Awakening", 15: "Burn Heal",
    16: "Ice Heal", 23: "Full Heal", 24: "Revive",
    86: "Repel", 83: "Super Repel", 84: "Max Repel", 85: "Escape Rope",
    # Field/battle items the Bag driver (agent/skills/items.py) can use (not sold in every Mart).
    63: "HP Up", 64: "Protein", 65: "Iron", 66: "Carbos", 67: "Calcium", 68: "Rare Candy", 70: "Zinc",
    93: "Sun Stone", 94: "Moon Stone", 95: "Fire Stone", 96: "Thunder Stone", 97: "Water Stone", 98: "Leaf Stone",
    73: "Guard Spec.", 74: "Dire Hit", 75: "X Attack", 76: "X Defend", 77: "X Speed", 78: "X Accuracy", 79: "X Special",
    25: "Max Revive", 26: "Fresh Water", 27: "Soda Pop", 28: "Lemonade", 34: "Ether", 35: "Max Ether",
    36: "Elixir", 37: "Max Elixir", 182: "Exp. Share",
}

# Mart buy prices (¥), from pokefirered src/data/items.json.
ITEM_PRICES: dict[int, str] = {
    2: 1200, 3: 600, 4: 200,
    13: 300, 22: 700, 21: 1200,
    14: 100, 18: 200, 17: 250, 15: 250, 16: 250, 23: 600, 24: 1500,
    86: 350, 83: 500, 85: 550,
}


@dataclass(frozen=True)
class BuyRule:
    """Keep `par` of `item_id` in the bag, but only while your badge count is in
    [min_badges, max_badges). max_badges lets a better item SUPERSEDE a worse one
    (e.g. stop buying Potions once Super Potions unlock)."""
    item_id: int
    par: int
    min_badges: int = 0
    max_badges: int = 99


# Ordered by PRIORITY (most important first) — when money is tight, earlier rules
# are funded first. Badge windows implement the "upgrade as you progress" idea:
#   Balls: Poké → Great(≥3) → Ultra(≥5)
#   Heals: Potion → Super Potion(≥3, after Surge) → Hyper Potion(≥5)
#   Status: individual cheap cures early → Full Heal(≥4) supersedes them
BUY_POLICY: list[BuyRule] = [
    # Catching stock — always keep balls on hand.
    BuyRule(4,  10, min_badges=0, max_badges=3),   # Poké Ball
    BuyRule(3,  10, min_badges=3, max_badges=5),   # Great Ball
    BuyRule(2,  10, min_badges=5),                  # Ultra Ball
    # Main healing — par grows as fights get harder.
    BuyRule(13, 6,  min_badges=0, max_badges=3),   # Potion
    BuyRule(22, 8,  min_badges=3, max_badges=5),   # Super Potion
    BuyRule(21, 8,  min_badges=5),                  # Hyper Potion
    # Status: cheap single-status cures early; Full Heal covers everything later.
    BuyRule(23, 5,  min_badges=4),                  # Full Heal
    BuyRule(14, 2,  min_badges=0, max_badges=4),   # Antidote
    BuyRule(18, 2,  min_badges=0, max_badges=4),   # Paralyze Heal
    BuyRule(17, 2,  min_badges=0, max_badges=4),   # Awakening
    BuyRule(15, 1,  min_badges=0, max_badges=4),   # Burn Heal
    BuyRule(16, 1,  min_badges=0, max_badges=4),   # Ice Heal
    # Revival — worth carrying a couple once fights can spike-KO.
    BuyRule(24, 2,  min_badges=4),                  # Revive
]


def compute_shopping_list(bag: dict[int, int], badges: int, money: int,
                          reserve: int = 0) -> dict:
    """Given the current bag ({item_id: qty}), badge count, and money, return the
    restock plan. Buys up to each active rule's par, in priority order, spending no
    more than (money - reserve). Returns:
      {"lines": [{item_id, name, qty, unit_price, subtotal}, ...],
       "total": <¥>, "affordable": bool}
    An empty `lines` means nothing to buy (already stocked, or can't afford any)."""
    budget = max(0, money - reserve)
    lines = []
    total = 0
    fully_affordable = True
    for rule in BUY_POLICY:
        if not (rule.min_badges <= badges < rule.max_badges):
            continue
        price = ITEM_PRICES.get(rule.item_id)
        if not price:
            continue
        need = rule.par - bag.get(rule.item_id, 0)
        if need <= 0:
            continue
        affordable_qty = min(need, (budget - total) // price)
        if affordable_qty < need:
            fully_affordable = False
        if affordable_qty <= 0:
            continue
        subtotal = affordable_qty * price
        total += subtotal
        lines.append({
            "item_id": rule.item_id,
            "name": ITEM_NAMES.get(rule.item_id, f"item#{rule.item_id}"),
            "qty": affordable_qty,
            "unit_price": price,
            "subtotal": subtotal,
        })
    return {"lines": lines, "total": total, "affordable": fully_affordable}


def shopping_summary(bag: dict[int, int], badges: int, money: int) -> str:
    """One-line human/agent-readable restock recommendation, or '' if nothing to buy."""
    plan = compute_shopping_list(bag, badges, money)
    if not plan["lines"]:
        return ""
    parts = [f"{ln['qty']}× {ln['name']} (¥{ln['subtotal']})" for ln in plan["lines"]]
    return f"Restock (¥{plan['total']} of ¥{money}): " + ", ".join(parts)


# ── buying a SPECIFIC item (shop(item=…)): which clerk sells it, where to stand ─────────────────────────────────────
# Things a clerk sells that the story also hands out for free (the model should not pay for what it can earn).
FREE_SOURCES: dict[int, str] = {
    316: "TM28 Dig is also a free reward in Cerulean City: beat the Rocket Grunt at the robbed house (he drops it)",
}


def item_label(item_id: int) -> str:
    """'TM28 Dig' for a TM/HM, else the shop's display name ('Super Repel')."""
    from knowledge.shop_stock import ITEM_LABELS
    from knowledge.tmhm import TMHM
    if item_id in TMHM:
        label, move, _ = TMHM[item_id]
        return f"{label} {move}"
    return ITEM_LABELS.get(item_id) or ITEM_NAMES.get(item_id, f"item #{item_id}")


def resolve_item(text: str) -> tuple[int | None, list[str]]:
    """(item id, []) for a name some clerk sells — 'TM28', 'Dig', 'super repel', 'protein' — else (None, close names)."""
    from knowledge.shop_stock import SHOPS
    from knowledge.tmhm import resolve_tmhm
    sold = {i for s in SHOPS for i in s[4]}
    key = str(text or "").strip().lower().replace("é", "e")
    tm = resolve_tmhm(key)
    if tm in sold:
        return tm, []
    names = {i: item_label(i).lower().replace("é", "e") for i in sold}
    exact = [i for i, n in names.items() if n == key]
    partial = exact or [i for i, n in names.items() if key and key in n]
    if len(partial) == 1:
        return partial[0], []
    return None, sorted(item_label(i) for i in (partial or [])[:6])


def shops_selling(item_id: int) -> list[tuple]:
    """[(map_bank, map_id, clerk_x, clerk_y)] for every clerk that sells `item_id`."""
    from knowledge.shop_stock import SHOPS
    return [(b, m, x, y) for b, m, x, y, items in SHOPS if item_id in items]


def approach_options(clerk: tuple, passable, reachable=None) -> list[tuple]:
    """[((x, y), facing)] — where the customer can stand to talk to `clerk`. A clerk sits behind a counter: the tile beside them is
    often counter or enclosure, so the answer is either that adjacent floor tile or, when it is not floor, the tile BEYOND it
    (talking across the counter works). `passable(x, y)` = floor; `reachable(x, y)` (default: any floor) = the player can get there,
    which rules out the clerk's own side of the counter."""
    reachable = reachable or passable
    cx, cy = clerk
    out = []
    for dx, dy, face in ((0, 1, "Up"), (1, 0, "Left"), (-1, 0, "Right"), (0, -1, "Down")):
        near, far = (cx + dx, cy + dy), (cx + 2 * dx, cy + 2 * dy)
        if reachable(*near):
            out.append((near, face))
        elif not passable(*near) and reachable(*far):
            out.append((far, face))
    return out


# ── the best of what THIS mart sells, and stocking up with spare money ──────────────────────────────────────────────
# BUY_POLICY above picks tiers by badge count, which is a guess about the mart: a Mart that sells Ultra Balls at 3 badges still got Great Balls, and a rich
# player (¥26,000, 17 balls, 1 Potion — a watched run) carried the same par of 10 as a broke one. This plan reads what the open buy menu actually lists.
BALL_TIERS = (2, 3, 4)               # Ultra, Great, Poké — best first
HEAL_TIERS = (19, 20, 21, 22, 13)    # Full Restore, Max Potion, Hyper, Super, Potion
FULL_HEAL, REVIVE = 23, 24
CURES = (14, 18, 17, 15, 16)         # Antidote, Paralyze Heal, Awakening, Burn Heal, Ice Heal
# par (what it keeps in the bag) and stock-up par (what it keeps when there is spare money), by item: the dearer the item, the fewer
BASE_PAR = {2: 10, 3: 10, 4: 10, 19: 3, 20: 4, 21: 6, 22: 8, 13: 8, 23: 5, 24: 2, 14: 2, 18: 2, 17: 2, 15: 1, 16: 1}
STOCK_PAR = {2: 25, 3: 25, 4: 25, 19: 5, 20: 6, 21: 10, 22: 15, 13: 15, 23: 10, 24: 5}
# the most of the budget each family may take in the base pass, so a ball tier cannot eat the potion money
FAMILY_SHARE = {"ball": 0.4, "heal": 0.5, "full_heal": 0.25, "revive": 0.25, "cure": 0.1}
LATE_BADGES = 7                      # the Elite Four is next: it wants ~12 strong heals (knowledge.beat_readiness) and no mart sells them past the Plateau, so stock deeper
# Revives and Hyper Potions are what the League runs on: a Revive (¥1500) brings a whole Pokémon back for the rest of the fight, a Hyper Potion (¥1200) heals 200 HP — twice the HP per yen of a Max
# Potion (¥2500) and 2.5× a Full Restore (¥3000). A watched League run (27 losses) bought Max Potions and Full Restores at the Plateau's clerk, which sells no Hyper Potion, and Revives last.
LATE_PAR = {19: 1, 20: 3, 21: 12, 24: 5, 23: 3}    # base par from LATE_BADGES badges (STOCK_PAR is raised to match when money allows); Full Restore / Max Potion only matter where no Hyper Potion is sold
LATE_STOCK_PAR = {19: 2, 20: 4, 21: 14, 24: 8, 23: 5}
LATE_HEAL_TIERS = (21, 22, 13)        # Hyper Potion heals 200 for ¥1200: a full heal for a L50-60 team, 2× the HP per yen of a Max Potion (¥2500) — so it wins whenever the mart sells it
LATE_NO_HYPER_TIERS = (20, 19)        # a mart with no Hyper Potion (the Plateau's): Max Potion (¥2500) before Full Restore (¥3000 for the same HP; Full Heals cure status for ¥600)
LATE_SHARE = {"ball": 0.1, "heal": 0.5, "revive": 0.45}   # the League is next: Balls matter less than the Revives and heals no mart will sell inside it
HYPER, HYPER_DETOUR_YEN = 21, 3600   # three Hyper Potions: the money from which shop() goes to a mart that sells them instead of buying Max Potions at one that does not
UPGRADE_HALF_PARS = 0.5              # a better tier is chosen once its budget covers this share of its par
STOCK_UP_FLOOR = 3000                # spare yen (after the base par) before it stocks up beyond par
STOCK_UP_SHARE = 0.6                 # …and it spends this share of the spare yen on the extra stock


def hyper_marts() -> list[tuple[int, int]]:
    """The Kanto marts that sell Hyper Potions, Saffron's first (the most central, and a Fly town): Saffron and Cinnabar. (The Sevii marts need a ferry ticket.)"""
    from knowledge.shop_stock import SHOPS
    return sorted(((b, m) for b, m, _x, _y, items in SHOPS if HYPER in items and b <= 14), key=lambda bm: bm != (14, 5))


def wants_hyper_mart(badges: int, money: int, here) -> bool:
    """Is it worth a trip to a mart that sells Hyper Potions before the Elite Four? From LATE_BADGES badges, with the money for a few of them, unless this IS such a mart."""
    return badges >= LATE_BADGES and money >= HYPER_DETOUR_YEN and tuple(here[:2]) not in hyper_marts()


def best_tier(tiers, sold, money: int, par=None, max_units: int = 99) -> int | None:
    """The best item of `tiers` (best first) that the mart sells and that `money` covers UPGRADE_HALF_PARS of its par of; else the cheapest tier it sells."""
    from knowledge.shop_stock import PRICES
    offered = [t for t in tiers if t in sold and PRICES.get(t)]
    for t in offered:
        if money >= PRICES[t] * max(1, min(max_units, int((par or BASE_PAR)[t] * UPGRADE_HALF_PARS))):
            return t
    return offered[-1] if offered else None


def compute_stock_plan(bag: dict[int, int], badges: int, money: int, sold, reserve: int = 0) -> dict:
    """What to buy at a mart whose buy menu lists `sold` (item ids): the best ball and healing tier it has that the money supports, up to par (priority order, each
    family within its share of the money), then — with spare yen beyond that — extra stock (more balls and potions, Revives, Full Heals). Returns the shape of
    compute_shopping_list plus "missing": better items a different mart sells, as names."""
    from knowledge.shop_stock import PRICES, SHOPS
    sold = set(sold)
    budget = max(0, money - reserve)
    late = badges >= LATE_BADGES
    par = {**BASE_PAR, **(LATE_PAR if late else {})}
    stock_par = {**STOCK_PAR, **(LATE_STOCK_PAR if late else {})}
    share = {**FAMILY_SHARE, **(LATE_SHARE if late else {})}
    heal_tiers = (LATE_HEAL_TIERS if HYPER in sold else LATE_NO_HYPER_TIERS) if late else HEAL_TIERS
    ball = best_tier(BALL_TIERS, sold, budget * share["ball"])
    heal = best_tier(heal_tiers, sold, budget * share["heal"], par, max_units=3 if late else 99)
    wants: list[tuple[int, str]] = []                       # (item id, family) in priority order
    if ball:
        wants.append((ball, "ball"))
    if heal:
        wants.append((heal, "heal"))
    if late and REVIVE in sold:
        wants.insert(1 if ball else 0, (REVIVE, "revive"))      # before the heals: the League's Revives cannot be bought inside it
    if badges >= 4 and FULL_HEAL in sold:
        wants.append((FULL_HEAL, "full_heal"))
    elif badges < 4:
        wants += [(c, "cure") for c in CURES if c in sold]
    if badges >= 4 and not late and REVIVE in sold:
        wants.append((REVIVE, "revive"))
    spent = 0
    got: dict[int, int] = {}                                 # item id -> quantity planned (the base pass and the stock-up pass add to one line)

    def stock_of(item_id: int) -> float:
        """What the bag already holds toward this item's par: itself, better tiers in full, cheaper tiers at half (17 Poké Balls make a Great Ball par half met)."""
        have = bag.get(item_id, 0) + got.get(item_id, 0)
        for tiers in (BALL_TIERS, HEAL_TIERS):
            if item_id in tiers:
                i = tiers.index(item_id)
                cheaper = sum(bag.get(t, 0) for t in tiers[i + 1:]) // 2
                if late and tiers is HEAL_TIERS:
                    cheaper = 0                                  # a Potion / Super Potion does not heal a L50+ team: it is no stock toward the Hyper Potions the Elite Four needs
                have += sum(bag.get(t, 0) for t in tiers[:i]) + cheaper
        return have

    def buy(item_id: int, upto: int, cap: int) -> None:
        nonlocal spent
        price = PRICES.get(item_id)
        room = min(max(cap, spent + (price or 0) if not got.get(item_id) else cap), budget) - spent        # a family always gets at least one unit when the money covers it
        qty = int(min(upto - stock_of(item_id), room // price)) if price else 0
        if qty > 0:
            got[item_id] = got.get(item_id, 0) + qty
            spent += qty * price

    base_spent: dict[str, int] = {}
    for item_id, fam in wants:
        before = spent
        buy(item_id, par[item_id], spent + max(0, int(budget * share[fam]) - base_spent.get(fam, 0)))
        base_spent[fam] = base_spent.get(fam, 0) + spent - before
    spare = budget - spent
    if spare >= STOCK_UP_FLOOR:
        cap = spent + int(spare * STOCK_UP_SHARE)
        for item_id, _fam in wants:
            if item_id in stock_par:
                buy(item_id, stock_par[item_id], cap)
    lines = [{"item_id": i, "name": ITEM_NAMES.get(i, item_label(i)), "qty": q, "unit_price": PRICES[i], "subtotal": q * PRICES[i]} for i, q in got.items()]
    others = {i for _b, _m, _x, _y, items in SHOPS for i in items}
    missing_hyper = ["Hyper Potion"] if late and HYPER not in sold and budget >= HYPER_DETOUR_YEN else []
    missing = missing_hyper + [ITEM_NAMES[t] for t in (next((t for t in BALL_TIERS if t in others and t not in sold), None), next((t for t in HEAL_TIERS if t in others and t not in sold), None)) if t
               and PRICES.get(t) and budget >= PRICES[t] * 4 and t not in (ball, heal)
               and ((t in BALL_TIERS and ball is not None and BALL_TIERS.index(t) < BALL_TIERS.index(ball)) or (t in HEAL_TIERS and heal is not None and HEAL_TIERS.index(t) < HEAL_TIERS.index(heal)))]
    return {"lines": lines, "total": spent, "affordable": True, "missing": missing}


# ── evolution stones ──────────────────────────────────────────────────────────────────────────────────────────────────
# Stones the Celadon Dept. Store (4F) sells, and the party members they evolve. Eevee is left out (three outcomes: the model should choose) and so are the Moon / Sun
# stones (not sold anywhere in Kanto).
SOLD_STONES = (95, 96, 97, 98)


def stone_wants(party, bag: dict[int, int], money: int, reserve: int = 0) -> list[tuple[int, str, str]]:
    """[(stone id, party member, what it becomes)] for the stones worth buying now: a party member evolves with a stone the Dept. Store sells, none is in the bag, and
    the money covers it. One entry per stone."""
    from game.constants import SPECIES_NAMES
    from knowledge.evolutions import EVO_BY_ITEM
    from knowledge.shop_stock import PRICES
    out, seen = [], set()
    for mon in party:
        for stone in SOLD_STONES:
            target = EVO_BY_ITEM.get((mon.species_id, stone))
            if target and mon.species_id != 133 and stone not in seen and not bag.get(stone) and money - reserve >= PRICES.get(stone, 10 ** 9):
                seen.add(stone)
                out.append((stone, getattr(mon, "nickname", "") or mon.species_name, SPECIES_NAMES.get(target, "?").title()))
    return out
