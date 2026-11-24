"""What the next story beat costs and how to find the money (pure data + logic; no I/O).

The agent could buy (shop) and, since #286, sell treasure — but nothing told it HOW MUCH money a milestone needs or where to get it. The League (#259) is the
big one: Full Restores, Revives and Max Potions for five back-to-back fights with no healing. Targets are what restocking the beat's HEALING supplies costs
(knowledge.beat_readiness) at Mart prices, rounded; income is prize money from trainer battles, treasure sold at a Mart, and Pay Day."""
import math

from knowledge.selling import TREASURE

# beat key -> (yen to have on hand before starting it, what it buys)
MONEY_NEEDS: dict[str, tuple[int, str]] = {
    "rocket_hideout": (2500, "Potions and a Revive for the Rocket trainers"),
    "pokemon_tower": (3500, "Revives and Potions for the Tower's ghosts and your rival"),
    "snorlax": (1500, "Potions for the Snorlax fight"),
    "silph_co": (6000, "Hyper Potions and Revives for eleven floors of Rockets"),
    "pokemon_mansion": (4000, "Potions and a Revive for the Fire-types"),
    "victory_road": (9000, "Hyper Potions, Revives and Full Heals for the cave"),
    "elite_four": (20000, "about 12 strong heals and 4 Revives (¥1500) for five fights with no healing between them: Hyper Potions (¥1200, +200 HP) from a Saffron / Fuchsia / Cinnabar / Celadon "
                          "mart are the best value, the Plateau's clerk only has Max Potions (¥2500) and Full Restores (¥3000)"),
}
PAY_DAY = 6                                    # move id


def treasure_value(bag) -> int:
    """About how many yen the treasure in `bag` ({item id: count}) sells for at a Mart."""
    return sum(TREASURE[i][1] * n for i, n in bag.items() if i in TREASURE)


def earn_advice(bag, party, gap: int) -> str:
    """How to cover `gap` yen: sell treasure first, then Pay Day, then trainer prize money (wild Pokémon pay nothing)."""
    bits = []
    worth = treasure_value(bag)
    if worth:
        bits.append(f"shop(sell=true) sells your treasure for about ¥{worth}" + (" — that covers it" if worth >= gap else ""))
    if any(PAY_DAY in (getattr(p, "move_ids", None) or []) for p in party):
        bits.append("a Pokémon of yours knows Pay Day: lead it in trainer fights (it scatters coins that become money)")
    if not worth or worth < gap:
        bits.append("win TRAINER battles (prize money = their top level × a multiplier; wild Pokémon pay nothing) — routes with several trainers and gym trainers pay best")
    return "; ".join(bits)


def money_line(key: str, money: int, bag, party) -> str:
    """'' when the beat needs no money or you have enough; else one line: the gap and how to earn it."""
    need = MONEY_NEEDS.get(key)
    if need is None or money >= need[0]:
        return ""
    yen, what = need
    gap = yen - money
    return f"MONEY: ¥{money} — {key} wants about ¥{yen} on hand for {what}; short by ¥{gap}. {earn_advice(bag, party, gap)}."


REVIVE, MAX_POTION = 24, 20
_PRICE = {REVIVE: 1500, MAX_POTION: 2500}


def supply_purchases(key: str, money: int, bag) -> list:
    """[(item id, quantity)] to buy for beat `key`'s healing supplies with `money` (the Plateau clerk sells Revives, Max Potions and Full Restores; Max Potion is
    the cheaper full heal, ¥2500 vs ¥3000, and a Full Heal cures status for ¥600): Revives up to the recommended count first (a fainted team member is the worse hole),
    then Max Potions with what is left. Heals already in the bag count by strength (a Potion is a fraction of one). Never spends more than `money`; [] for a beat with no
    supply need. Pure."""
    from knowledge.beat_readiness import NEEDS, REVIVES, effective_heals
    need = NEEDS.get(key)
    if need is None:
        return []
    have_r = sum(n for i, n in bag.items() if i in REVIVES)
    have_p = effective_heals(bag, need.top)
    out, left = [], int(money)
    n = min(max(0, need.revives - have_r), left // _PRICE[REVIVE])
    if n:
        out.append((REVIVE, n))
        left -= n * _PRICE[REVIVE]
    n = min(max(0, math.ceil(need.potions - have_p)), left // _PRICE[MAX_POTION])
    if n:
        out.append((MAX_POTION, n))
    return out
