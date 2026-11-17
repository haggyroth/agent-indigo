"""What the Bag could do for the party (pure): which TM is a real upgrade for whom, which stone evolves whom, and a
one-line digest of the interesting bag contents.

The model used to have to *remember* a TM picked up many turns ago (the observation only showed balls and potions),
so TMs and stones sat unused. `tm_advice` scores each owned TM against every compatible party member with the same
expected-damage function the battle ranker uses (knowledge.move_semantics.move_score) and only flags CLEAR upgrades.
"""
from dataclasses import dataclass

from knowledge.evolutions import EVO_BY_ITEM
from knowledge.shopping import ITEM_NAMES
from knowledge.tmhm import HM_MOVE_NAMES, ITEM_HM01, TMHM, pick_forget
from knowledge.tmhm_learnsets import can_learn

MIN_VALUE = 55            # a move worth teaching deals at least this much "power" per turn
REPLACE_RATIO = 1.3       # …and beats the move it would replace by this factor
COVERAGE_BONUS = 1.15     # a damaging move of a type none of the Pokémon's other attacks has
FREE_SLOT_RATIO = 1.2     # filling an empty slot must beat the best current attack unless it adds a new type

STONES = {93, 94, 95, 96, 97, 98}
CANDY_VITAMINS = {63, 64, 65, 66, 67, 68, 70}


@dataclass(frozen=True)
class TMAdvice:
    tm: str
    move: str
    mon: str
    forget: str | None
    gain: float
    text: str


def _types(mon) -> tuple:
    from knowledge.leafgreen_data import POKEMON_TYPES
    return POKEMON_TYPES.get((getattr(mon, "species_name", "") or "").upper().strip(), ())


def tm_advice(party, owned, limit: int = 2) -> list[TMAdvice]:
    """Clear TM upgrades for the party. `owned` is [(item_id, qty)] from the TM case. HMs are never advised here
    (their value is field utility). One suggestion per Pokémon and per TM, best gain first, at most `limit`."""
    from knowledge.leafgreen_data import MOVE_POWER, MOVE_TYPE, SUICIDE_MOVES
    from knowledge.move_semantics import move_score
    cands: list[tuple[float, TMAdvice, int, int]] = []
    for iid, _qty in owned:
        if iid not in TMHM or iid >= ITEM_HM01:
            continue
        label, move, move_id = TMHM[iid]
        if move in SUICIDE_MOVES:
            continue
        for slot, mon in enumerate(party):
            if not getattr(mon, "max_hp", 0) or move in (mon.move_names or []) or move_id in (mon.move_ids or []):
                continue
            if not can_learn(mon.species_id, iid):
                continue
            types = _types(mon)
            known = [m for m in (mon.move_names or []) if m]
            dmg_types = {MOVE_TYPE.get(m) for m in known if MOVE_POWER.get(m, 0) > 0}
            value = move_score(move, types)
            if value > 0 and MOVE_TYPE.get(move) not in dmg_types:
                value *= COVERAGE_BONUS
            if value < MIN_VALUE:
                continue
            best_now = max((move_score(m, types) for m in known), default=0.0)
            if len(known) < 4:
                if value < FREE_SLOT_RATIO * best_now and MOVE_TYPE.get(move) in dmg_types:
                    continue
                forget, old, how = None, 0.0, "fills an empty move slot"
            else:
                fi = pick_forget(mon.move_names, move, MOVE_POWER)
                if fi is None:
                    continue
                forget = mon.move_names[fi]
                old = move_score(forget, types)
                if value < REPLACE_RATIO * max(old, 1.0):
                    continue
                how = f"replaces {forget} (~{old:.0f})"
            who = getattr(mon, "nickname", "") or mon.species_name
            call = f"teach_move('{label}', pokemon='{mon.species_name}'" + (f", forget='{forget}'" if forget else "") + ")"
            text = f"{call} — {move} (~{value:.0f}) {how} on {who}"
            cands.append((value - old, TMAdvice(label, move, who, forget, value - old, text), slot, iid))
    cands.sort(key=lambda c: -c[0])
    out, used_mon, used_tm = [], set(), set()
    for _gain, adv, slot, iid in cands:
        if slot in used_mon or iid in used_tm:
            continue
        used_mon.add(slot)
        used_tm.add(iid)
        out.append(adv)
        if len(out) >= limit:
            break
    return out


def stone_notes(party, items, limit: int = 3) -> list[str]:
    """'Fire Stone: Growlithe can evolve (→ Arcanine)' for each evolution stone in the Items pocket."""
    from game.constants import SPECIES_NAMES
    have = {iid for iid, qty in items if qty > 0 and iid in STONES}
    out = []
    for iid in sorted(have):
        for mon in party:
            target = EVO_BY_ITEM.get((mon.species_id, iid))
            if target:
                out.append(f"{ITEM_NAMES.get(iid, iid)}: {mon.nickname or mon.species_name} can evolve "
                           f"(→ {SPECIES_NAMES.get(target, '?').title()})")
    return out[:limit]


def bag_digest(party, tmhm, items, limit_chars: int = 320) -> str:
    """One line of the interesting bag contents: TMs, HMs (and whether anyone knows them), stones / Rare Candy /
    vitamins. '' when there is nothing of the kind."""
    tms = [f"{TMHM[i][0]} {TMHM[i][1]}" for i, _ in tmhm if i in TMHM and i < ITEM_HM01]
    hms = []
    for i, _ in tmhm:
        if i in TMHM and i >= ITEM_HM01:
            label, move, mid = TMHM[i]
            if move in HM_MOVE_NAMES:
                knower = next((p for p in party if move in (p.move_names or [])), None)
                hms.append(f"{label} {move}" + (f" (known by {knower.species_name})" if knower else " (NOT taught yet)"))
    stuff = [f"{ITEM_NAMES.get(i, i)}" + (f"×{q}" if q > 1 else "") for i, q in items
             if i in STONES or i in CANDY_VITAMINS]
    parts = []
    if tms:
        parts.append("TMs: " + ", ".join(tms))
    if hms:
        parts.append("HMs: " + ", ".join(hms))
    if stuff:
        parts.append("Items: " + ", ".join(stuff))
    line = " | ".join(parts)
    return ("BAG — " + line)[:limit_chars] if line else ""
