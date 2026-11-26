"""The Celadon Game Corner as data + policy (pure): what the Prize Corner sells for coins, what coins cost, which machines work.

All numbers are the decomp's (`game_corner_data`, generated). The point of this module is the arithmetic the model should not
have to redo: "TM24 costs 4000 coins — you have 1200, that is 2800 more = 56 lots of 50 for ¥56,000"."""
from dataclasses import dataclass

from game.constants import SPECIES_NAMES
from knowledge.game_corner_data import COIN_LOTS, ITEM_LABELS, PRIZE_CLERKS
from knowledge.tmhm import TMHM, resolve_tmhm

MAX_COINS = 9999
MAX_SLOT_LOSS = 300                # stop a session after losing this many coins (a bad streak must not drain the run)
SPIN_BET = 3                        # a full bet lights all five lines and is the only one worth playing


@dataclass(frozen=True)
class Prize:
    kind: str                       # 'mon' | 'tm' | 'item'
    clerk: tuple                    # (x, y) of the clerk who sells it
    index: int                      # row in that clerk's menu
    id: int                         # species id (mon) or item id
    coins: int
    level: int                      # prize Pokémon's level (0 for items)

    @property
    def name(self) -> str:
        if self.kind == "mon":
            return SPECIES_NAMES.get(self.id, f"#{self.id}").title()
        if self.id in TMHM:
            return f"{TMHM[self.id][0]} {TMHM[self.id][1]}"
        return ITEM_LABELS.get(self.id, f"item #{self.id}")


PRIZES: list[Prize] = [Prize(k, (x, y), i, pid, c, lv) for k, _b, _m, x, y, rows in PRIZE_CLERKS for i, pid, c, lv in rows]


# The price of a prize in TIME, from the slot driver (not luck: it presses A on the frame that serves the machine's bias): about +16 coins net per spin, ~700 emulated frames a spin.
SPIN_NET_COINS = 16
SPIN_FRAMES = 700
# what each held-item prize is for (the decomp's own item descriptions: src/data/items.json)
ITEM_PURPOSE = {194: "held: the holder can always flee wild battles", 205: "held: boosts Grass-type moves", 215: "held: boosts Fire-type moves", 209: "held: boosts Water-type moves",
                40: "snaps one Pokémon out of confusion"}


def spin_cost(missing_coins: int) -> tuple[int, int]:
    """(slot spins, minutes of game time) to win `missing_coins` at the measured rate."""
    spins = -(-max(0, missing_coins) // SPIN_NET_COINS)
    return spins, round(spins * SPIN_FRAMES / 3600)


def prize_lines(coins: int, owned, party) -> list[str]:
    """The Prize Corner as information, cheapest first: price, what is missing, what that costs in slot time, and what the prize is FOR. Never a recommendation.
    `owned(species_id) -> bool | None` (the Pokédex), `party` = [(species_id, name)] of the team (who could learn each TM)."""
    from knowledge.tmhm_learnsets import can_learn
    out = []
    for p in sorted(PRIZES, key=lambda p: p.coins):
        if coins >= p.coins:
            cost = "you can afford it"
        else:
            spins, mins = spin_cost(p.coins - coins)
            cost = f"{p.coins - coins} more coins ≈ {spins} slot spins (~{mins} min of game time)"
        if p.kind == "mon":
            got = owned(p.id)
            purpose = f"Lv{p.level}; " + ("already in your Pokédex" if got else "a NEW Pokédex entry" if got is not None else "Pokédex entry unknown")
        elif p.kind == "tm":
            who = [n for sid, n in party if can_learn(sid, p.id)]
            purpose = ("your team's " + ", ".join(who) + " can learn it") if who else "nobody in your party can learn it"
        else:
            purpose = ITEM_PURPOSE.get(p.id, "an item")
        out.append(f"  {p.name} — {p.coins} coins — {cost} · {purpose}")
    return out


def resolve_prize(text: str) -> tuple[Prize | None, list[str]]:
    """(prize, []) for 'TM24', 'Thunderbolt', 'Abra', 'Smoke Ball'…, else (None, close names)."""
    key = str(text or "").strip().lower()
    tm = resolve_tmhm(key)
    hit = [p for p in PRIZES if p.kind == "tm" and p.id == tm] if tm else []
    hit = hit or [p for p in PRIZES if p.name.lower() == key] or [p for p in PRIZES if key and key in p.name.lower()]
    if len(hit) == 1:
        return hit[0], []
    return None, [p.name for p in hit[:6]]


def lots_for(coins_needed: int) -> tuple[int, int]:
    """(coins actually bought, yen) to buy at least `coins_needed` more coins with the fewest/cheapest lots (500s first)."""
    small, big = COIN_LOTS[0], COIN_LOTS[1]
    n_big, rest = divmod(max(0, coins_needed), big[0])
    n_small = -(-rest // small[0])
    return n_big * big[0] + n_small * small[0], n_big * big[1] + n_small * small[1]


def prize_plan(prize: Prize, coins: int, yen: int) -> str:
    """One sentence: can the player afford this prize, and if not what it would take."""
    if coins >= prize.coins:
        return f"{prize.name} costs {prize.coins} coins and you have {coins}."
    bought, cost = lots_for(prize.coins - coins)
    if coins + bought > MAX_COINS:
        return f"{prize.name} costs {prize.coins} coins; you have {coins} (the case holds {MAX_COINS})."
    afford = "you can afford it" if yen >= cost else f"you have ¥{yen}"
    return (f"{prize.name} costs {prize.coins} coins; you have {coins}, so {prize.coins - coins} more — buying {bought} coins costs "
            f"¥{cost} ({afford}), or win them at the slots.")
