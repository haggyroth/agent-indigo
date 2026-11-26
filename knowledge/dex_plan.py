"""Pokédex completion plan (pure; no I/O): which Kanto species are missing and where each one comes from.

Sources, in the order they are worth chasing: WILD (knowledge.wild_locations: the easiest spot), EVOLUTION (the pre-evolution is already caught — level, stone, trade), an IN-GAME TRADE
(the NPC's wanted species is owned), then the one-off sources — gifts, fossils, Game Corner prizes, static legends — curated below (each line verified against a `givemon` /
`setvar VAR_TEMP_1, SPECIES_*` in the decomp). Nothing here reads the game: pass the set of owned species ids (read_dex_owned_ids)."""
from game.constants import SPECIES_NAMES
from knowledge.dex_sources import EVOLVES_FROM, TRADES
from knowledge.navigation import MAP_NAMES
from knowledge.wild_locations import MAP_LABELS, WILD_LOCATIONS

KANTO = 151
# species id -> (source, quest key that does it or "")
SPECIAL: dict[int, tuple[str, str]] = {
    1: ("starter: one of the three Oak offers at the start", ""), 4: ("starter: one of the three Oak offers at the start", ""),
    7: ("starter: one of the three Oak offers at the start", ""),
    35: ("Game Corner prize (Celadon, coins)", ""), 63: ("Game Corner prize (Celadon, coins)", ""), 127: ("Game Corner prize (Celadon, coins)", ""),
    137: ("Game Corner prize (Celadon, coins)", ""), 147: ("Game Corner prize (Celadon, coins)", ""),
    101: ("Power Plant: the static Electrodes (L34, one-shot — weaken without fainting, then a ball; the only wild ones are in Cerulean Cave at L58+)", "zapdos"),
    106: ("Saffron Dojo: after Master Koichi, choose ONE of Hitmonlee / Hitmonchan", "hitmon"), 107: ("Saffron Dojo: after Master Koichi, choose ONE of Hitmonlee / Hitmonchan", "hitmon"),
    129: ("Route 4 Pokémon Center salesman for ¥500 (or fishing)", "magikarp"),
    131: ("Silph Co. 7F: the worker gives a Lapras once the Rockets are gone", "silph_co"),
    133: ("gift: the Pokéball in Celadon Mansion's roof room", "eevee"),
    138: ("fossil: Helix Fossil (Mt. Moon B2F) revived at the Cinnabar Pokémon Lab", ""),
    140: ("fossil: Dome Fossil (Mt. Moon B2F) revived at the Cinnabar Pokémon Lab", ""),
    142: ("fossil: Old Amber (Pewter Museum) revived at the Cinnabar Pokémon Lab", ""),
    143: ("a sleeping Snorlax on Route 12 / Route 16 (needs the Poké Flute)", "snorlax"),
    144: ("Seafoam Islands B4F (legendary: Surf + Strength boulders, then it appears once — catch it)", "articuno"),
    145: ("Power Plant (legendary: Surf, then it appears once — catch it)", "zapdos"), 146: ("Mt. Ember on Sevii (legendary)", ""),
    150: ("Cerulean Cave B1F (legendary; after the Network Machine)", ""), 151: ("event only (Mew)", ""),
}


def name(sid: int) -> str:
    return SPECIES_NAMES.get(sid, f"#{sid}").title()


ROD_QUEST = {"old rod": "old_rod", "good rod": "good_rod", "super rod": "super_rod"}      # a spot that needs a rod: the quest that gets it


def _wild_row(sid: int):
    rows = WILD_LOCATIONS.get(sid) or []
    return min(rows, key=lambda r: (r[3], r[4])) if rows else None


def wild_spot(sid: int):
    """'Route 24 (grass L8-12)' for the lowest-level wild spot of species `sid`, or None. A fishing spot names the rod it needs ('Route 12 (super rod L15-35)')."""
    row = _wild_row(sid)
    if row is None:
        return None
    bank, mid, method, lo, hi = row
    where = MAP_NAMES.get((bank, mid)) or MAP_LABELS.get((bank, mid)) or f"map {bank}/{mid}"
    return f"{where} ({method} L{lo}" + (f"-{hi}" if hi != lo else "") + ")"


def sources(sid: int, owned) -> list:
    """[(priority, text, quest)] for species `sid` — lower priority = easier now. Empty when the data knows no source."""
    out = []
    if (spot := wild_spot(sid)):
        out.append((0, f"wild: {spot}", ROD_QUEST.get(_wild_row(sid)[2], "")))
    if sid in EVOLVES_FROM:
        pre, how = EVOLVES_FROM[sid]
        out.append((1 if pre in owned else 4, f"evolve {name(pre)} ({how})" + ("" if pre in owned else " — catch it first"), ""))
    if sid in TRADES:
        want, place = TRADES[sid]
        out.append((2 if want in owned else 5, f"trade {name(want)} at {place}" + ("" if want in owned else " (you need one first)"), ""))
    if sid in SPECIAL:
        text, quest = SPECIAL[sid]
        out.append((3, text, quest))
    if not out:
        out.append((6, "a version exclusive of the other game: only an in-game trade or a link trade gets it", ""))
    return sorted(out)


def _level(sid: int) -> int:
    rows = WILD_LOCATIONS.get(sid) or []
    return min((r[3] for r in rows), default=0)


def missing(owned) -> list:
    return [s for s in range(1, KANTO + 1) if s not in owned]


def next_targets(owned, limit: int = 4) -> list:
    """[(species id, best source text, quest key)] — the easiest missing species to get next (evolutions of what you have and wild catches first)."""
    ranked = []
    for sid in missing(owned):
        src = sources(sid, owned)
        if src:
            ranked.append((src[0][0], _level(sid) if src[0][0] == 0 else 0, sid, src[0][1], src[0][2]))
    ranked.sort()                                                  # easiest source first; among wild catches the lowest-level spot first
    return [(sid, text, quest) for _p, _lv, sid, text, quest in ranked[:limit]]


def dex_line(owned, limit: int = 4) -> str:
    """One report line: the count and the easiest next catches with where / how. '' when the dex is full."""
    left = missing(owned)
    if not left:
        return "DEX: all 151 Kanto species caught."
    nxt = next_targets(owned, limit)
    tail = "; ".join(f"{name(s)} — {text}" + (f" [quest('{q}')]" if q else "") for s, text, q in nxt)
    return f"DEX: {len(owned)}/{KANTO} caught. Easiest next: {tail}." if nxt else f"DEX: {len(owned)}/{KANTO} caught."


# ── the dex view (#362) ──────────────────────────────────────────────────────────────────────────

REACH_NOW, REACH_AFTER, REACH_TRADE, REACH_EVENT = "reachable now", "after another catch", "needs a trade partner", "event only"
EVENT_ONLY = {151}                      # Mew


def reach(sid: int, owned) -> tuple[str, str, str]:
    """(reachability, best source text, quest key) of a MISSING species. A trade evolution (Kadabra -> Alakazam) and a version exclusive need a trade partner; Mew is an event."""
    if sid in EVENT_ONLY:
        return REACH_EVENT, "event only (Mew)", ""
    src = sources(sid, owned)
    prio, text, quest = src[0]
    trade_evo = sid in EVOLVES_FROM and "trade" in EVOLVES_FROM[sid][1] and not any(p in (0, 3) for p, _t, _q in src)
    if prio == 6 or trade_evo:
        return REACH_TRADE, ("evolve " + name(EVOLVES_FROM[sid][0]) + " by trade" if trade_evo else text), quest
    return (REACH_NOW if prio <= 3 else REACH_AFTER), text, quest


def dex_view(owned, seen: int = 0, per_group: int = 12) -> str:
    """The Kanto Pokédex as a view: caught / seen / missing, and every missing species grouped by whether it can be had here, after another catch, only with a trade partner,
    or only as an event — each with its best source. Information for the model, which decides what to chase."""
    left = missing(owned)
    if not left:
        return f"POKÉDEX: all {KANTO} Kanto species caught."
    groups: dict[str, list] = {REACH_NOW: [], REACH_AFTER: [], REACH_TRADE: [], REACH_EVENT: []}
    for sid in left:
        how, text, quest = reach(sid, owned)
        groups[how].append((sid, text, quest))
    reachable = len(groups[REACH_NOW]) + len(groups[REACH_AFTER])
    out = [f"POKÉDEX (Kanto): {len(owned)}/{KANTO} caught, {seen} seen, {len(left)} missing — {reachable} can be had in this game without a partner "
           f"({len(groups[REACH_NOW])} now, {len(groups[REACH_AFTER])} after another catch), {len(groups[REACH_TRADE])} need a trade partner, {len(groups[REACH_EVENT])} event-only."]
    for how in (REACH_NOW, REACH_AFTER, REACH_TRADE, REACH_EVENT):
        rows = groups[how]
        if not rows:
            continue
        out.append(f"{how.upper()} ({len(rows)}):")
        for sid, text, quest in rows[:per_group]:
            out.append(f"  {name(sid)} — {text}" + (f" [quest('{quest}')]" if quest else ""))
        if len(rows) > per_group:
            out.append(f"  … and {len(rows) - per_group} more")
    return "\n".join(out)
